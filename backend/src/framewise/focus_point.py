"""The area a camera focused on, read from the maker notes of a Frame's Analysis source."""

from collections.abc import Mapping
from pathlib import Path

from framewise.exiftool import ExifTool
from framewise.image_measures import Region

# A square this share of the Frame's shorter side, centered on the focus point. Fujifilm records
# an AF point size, but not what it means in pixels.
FOCUS_AREA_SHARE = 0.1
FOCUS_TAGS = ("-FocusPixel", "-ExifImageWidth", "-ExifImageHeight", "-Orientation")
# Where a point (u, v), as fractions of the stored image, lands in the Frame as displayed, and
# whether the displayed Frame is turned on its side, by EXIF orientation.
ORIENTATIONS = {
    1: (lambda u, v: (u, v), False),
    2: (lambda u, v: (1 - u, v), False),
    3: (lambda u, v: (1 - u, 1 - v), False),
    4: (lambda u, v: (u, 1 - v), False),
    5: (lambda u, v: (v, u), True),
    6: (lambda u, v: (1 - v, u), True),
    7: (lambda u, v: (1 - v, 1 - u), True),
    8: (lambda u, v: (v, 1 - u), True),
}


def read_focus_area(exiftool: ExifTool, jpg_path: Path) -> Region | None:
    """The focus area of the JPG, or None where it records none or ExifTool can't run."""
    try:
        [tags] = exiftool.read_json("-n", *FOCUS_TAGS, jpg_path)
    except (OSError, ValueError):
        return None
    return focus_area(tags)


def focus_area(tags: Mapping) -> Region | None:
    """The focus area in the Frame as displayed, from `exiftool -j -n` tags, or None without a
    point inside the stored JPG."""
    try:
        x, y = (float(value) for value in str(tags["FocusPixel"]).split())
        width, height = float(tags["ExifImageWidth"]), float(tags["ExifImageHeight"])
    except (KeyError, ValueError):
        return None
    if not (0 < x < width and 0 < y < height):
        return None
    turn, sideways = ORIENTATIONS.get(tags.get("Orientation"), ORIENTATIONS[1])
    center_x, center_y = turn(x / width, y / height)
    shown_width, shown_height = (height, width) if sideways else (width, height)
    side = FOCUS_AREA_SHARE * min(shown_width, shown_height)
    return _square(center_x, center_y, side / shown_width, side / shown_height)


def _square(center_x: float, center_y: float, width: float, height: float) -> Region:
    left, top = max(0.0, center_x - width / 2), max(0.0, center_y - height / 2)
    right, bottom = min(1.0, center_x + width / 2), min(1.0, center_y + height / 2)
    return left, top, right - left, bottom - top
