"""Sharpness, motion blur and exposure from image maths on a Frame's downscaled JPG, and the
sharpness of regions of it such as faces."""

import math
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageChops

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
# A high-key Frame is bright yet keeps its highlights; an overexposed one clips them.
CLIPPED_TONE = 250
HIGH_KEY_MAX_CLIPPED_SHARE = 0.01
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
    region_sharpness: list[float | None]
    """The sharpness of each region asked for, or None where it is too small to measure."""


def measure_image(jpg_path: Path, regions: list[Region] | None = None) -> ImageMeasures:
    with Image.open(jpg_path) as image:
        image.draft("L", MEASURE_BOX)
        grey = image.convert("L")
    grey.thumbnail(MEASURE_BOX)
    ratios = _edge_ratios(grey)
    sharpest, softest = max(ratios), min(ratios)
    histogram = grey.histogram()
    stops = _exposure_stops(histogram)
    return ImageMeasures(
        sharpness=_sharpness(ratios),
        motion_blur=0.0 if sharpest == 0 else 1 - softest / sharpest,
        exposure_stops=stops,
        low_key=stops <= -KEY_FROM_STOPS
        and _share_from(histogram, LOW_KEY_HIGHLIGHT_TONE) >= LOW_KEY_MIN_HIGHLIGHT_SHARE,
        high_key=stops >= KEY_FROM_STOPS
        and _share_from(histogram, CLIPPED_TONE) < HIGH_KEY_MAX_CLIPPED_SHARE,
        region_sharpness=[_region_sharpness(grey, region) for region in regions or []],
    )


def _sharpness(ratios: list[float]) -> float:
    return _clamp((max(ratios) - SMEARED_RATIO) / (CRISP_RATIO - SMEARED_RATIO))


def _region_sharpness(grey: Image.Image, region: Region) -> float | None:
    """Measures the region with a margin of the pixels around it, which the edge shifts use."""
    width, height = grey.size
    x, y, region_width, region_height = region
    left, top = round(x * width), round(y * height)
    right, bottom = round((x + region_width) * width), round((y + region_height) * height)
    if min(right - left, bottom - top) < MIN_REGION_SIDE:
        return None
    crop = grey.crop(
        (
            max(0, left - EDGE_MARGIN),
            max(0, top - EDGE_MARGIN),
            min(width, right + EDGE_MARGIN),
            min(height, bottom + EDGE_MARGIN),
        )
    )
    return _sharpness(_edge_ratios(crop))


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
