"""Sharpness, motion blur and exposure from image maths on a Frame's downscaled JPG, turned the
way it is displayed, and the sharpness of the faces in it."""

import math
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageChops, ImageOps, ImageStat

MEASURE_BOX = (1024, 1024)
EDGE_MARGIN = 8
DIRECTIONS = [(1, 0), (0, 1), (1, 1), (1, -1)]
FAR_STEP = 4
# The ratio of 1-pixel to 4-pixel squared differences is 1/4 across a crisp edge and falls to
# 1/16 once an edge is smeared over 4 or more pixels, whatever the edge's contrast.
CRISP_RATIO = 1 / 4
SMEARED_RATIO = 1 / 16
MID_GREY_LINEAR = 0.18
DARKEST_STOPS = -6.0
KEY_FROM_STOPS = 0.7
# A low-key Frame is dark yet keeps some bright highlights; an underexposed one has none.
LOW_KEY_HIGHLIGHT_TONE = 200
LOW_KEY_MIN_HIGHLIGHT_SHARE = 0.005
# A high-key Frame is bright yet keeps its highlights; an overexposed one clips them. With faces,
# the highlights that count are the faces': a white wall behind a person may clip, their skin
# must not. A face's centre leaves out the hair and background at the edges of its box.
CLIPPED_TONE = 250
HIGH_KEY_MAX_CLIPPED_SHARE = 0.01
HIGH_KEY_MAX_CLIPPED_FACE_SHARE = 0.1
FACE_CENTRE_INSET = 0.2
# Regions narrower or shorter than this, in pixels of the downscaled JPG, are too small to measure.
MIN_REGION_SIDE = 32

Region = tuple[float, float, float, float]
"""x, y, width and height as fractions of the image, measured from the top left."""


@dataclass(frozen=True)
class ImageMeasures:
    sharpness: float
    motion_blur: float
    exposure_stops: float
    low_key: bool
    high_key: bool
    face_sharpness: list[float | None]
    """The sharpness of each face asked for, or None where it is too small to measure."""
    face_contrast: list[float | None]
    """The contrast of each face asked for, or None where it is too small to measure."""


def measure_image(jpg_path: Path, faces: list[Region] | None = None) -> ImageMeasures:
    """`faces` are boxes in the Frame as it is displayed, after its EXIF orientation."""
    with Image.open(jpg_path) as image:
        image.draft("L", MEASURE_BOX)
        grey = ImageOps.exif_transpose(image).convert("L")
    grey.thumbnail(MEASURE_BOX)
    ratios = _edge_ratios(grey)
    sharpest, softest = max(ratios), min(ratios)
    histogram = grey.histogram()
    stops = _exposure_stops(histogram)
    face_boxes = [_pixel_box(grey, face) for face in faces or []]
    return ImageMeasures(
        sharpness=_sharpness(ratios),
        motion_blur=0.0 if sharpest == 0 else 1 - softest / sharpest,
        exposure_stops=stops,
        low_key=stops <= -KEY_FROM_STOPS
        and _share_from(histogram, LOW_KEY_HIGHLIGHT_TONE) >= LOW_KEY_MIN_HIGHLIGHT_SHARE,
        high_key=stops >= KEY_FROM_STOPS and _keeps_highlights(grey, histogram, face_boxes),
        face_sharpness=[None if box is None else _box_sharpness(grey, box) for box in face_boxes],
        face_contrast=[None if box is None else _box_contrast(grey, box) for box in face_boxes],
    )


def _sharpness(ratios: list[float]) -> float:
    return _clamp((max(ratios) - SMEARED_RATIO) / (CRISP_RATIO - SMEARED_RATIO))


Box = tuple[int, int, int, int]


def _pixel_box(grey: Image.Image, region: Region) -> Box | None:
    """The region's left, top, right and bottom in pixels, or None where it is too small to
    measure."""
    width, height = grey.size
    x, y, region_width, region_height = region
    left, top = round(x * width), round(y * height)
    right, bottom = round((x + region_width) * width), round((y + region_height) * height)
    if min(right - left, bottom - top) < MIN_REGION_SIDE:
        return None
    return left, top, right, bottom


def _keeps_highlights(grey: Image.Image, histogram: list[int], faces: list[Box | None]) -> bool:
    """Whether the centre of every measurable face keeps its highlights or, without one, the whole
    Frame does."""
    measurable = [box for box in faces if box is not None]
    if not measurable:
        return _share_from(histogram, CLIPPED_TONE) < HIGH_KEY_MAX_CLIPPED_SHARE
    return all(
        _share_from(grey.crop(_centre(box)).histogram(), CLIPPED_TONE)
        < HIGH_KEY_MAX_CLIPPED_FACE_SHARE
        for box in measurable
    )


def _centre(box: Box) -> Box:
    left, top, right, bottom = box
    inset_x = round((right - left) * FACE_CENTRE_INSET)
    inset_y = round((bottom - top) * FACE_CENTRE_INSET)
    return left + inset_x, top + inset_y, right - inset_x, bottom - inset_y


def _box_sharpness(grey: Image.Image, box: Box) -> float:
    """Measures the box with a margin of the pixels around it, which the edge shifts use."""
    width, height = grey.size
    left, top, right, bottom = box
    crop = grey.crop(
        (
            max(0, left - EDGE_MARGIN),
            max(0, top - EDGE_MARGIN),
            min(width, right + EDGE_MARGIN),
            min(height, bottom + EDGE_MARGIN),
        )
    )
    return _sharpness(_edge_ratios(crop))


def _box_contrast(grey: Image.Image, box: Box) -> float:
    """The standard deviation of the grey levels in the centre of the box over their mean."""
    stats = ImageStat.Stat(grey.crop(_centre(box)))
    return stats.stddev[0] / max(stats.mean[0], 1)


def _edge_ratios(grey: Image.Image) -> list[float]:
    """For each direction, how much of the edge energy sits in 1-pixel steps. Defocus lowers it
    in every direction; motion blur lowers it only along the direction of motion."""
    base = _shifted(grey, 0, 0)
    ratios = []
    for dx, dy in DIRECTIONS:
        near = _energy(base, _shifted(grey, dx, dy))
        far = _energy(base, _shifted(grey, FAR_STEP * dx, FAR_STEP * dy))
        ratios.append(0.0 if far == 0 else near / far)
    return ratios


def _shifted(grey: Image.Image, dx: int, dy: int) -> Image.Image:
    width, height = grey.size
    margin = EDGE_MARGIN
    return grey.crop((margin + dx, margin + dy, width - margin + dx, height - margin + dy))


def _energy(first: Image.Image, second: Image.Image) -> float:
    histogram = ImageChops.difference(first, second).histogram()
    return sum(count * value * value for value, count in enumerate(histogram)) / sum(histogram)


def _exposure_stops(histogram: list[int]) -> float:
    mean_tone = sum(value * count for value, count in enumerate(histogram)) / sum(histogram)
    linear = _linear(mean_tone / 255)
    if linear == 0:
        return DARKEST_STOPS
    return max(DARKEST_STOPS, math.log2(linear / MID_GREY_LINEAR))


def _linear(encoded: float) -> float:
    if encoded <= 0.04045:
        return encoded / 12.92
    return ((encoded + 0.055) / 1.055) ** 2.4


def _share_from(histogram: list[int], tone: int) -> float:
    return sum(histogram[tone:]) / sum(histogram)


def _clamp(value: float) -> float:
    return min(1.0, max(0.0, value))
