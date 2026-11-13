from datetime import datetime
from pathlib import Path

from PIL import Image

EXIF_IFD_TAG = 0x8769
DATE_TIME_ORIGINAL_TAG = 0x9003
SUBSEC_TIME_ORIGINAL_TAG = 0x9291


def read_capture_time(jpg_path: Path) -> datetime | None:
    try:
        with Image.open(jpg_path) as image:
            exif_ifd = image.getexif().get_ifd(EXIF_IFD_TAG)
    except OSError:
        return None
    try:
        captured_at = datetime.strptime(str(exif_ifd[DATE_TIME_ORIGINAL_TAG]), "%Y:%m:%d %H:%M:%S")
    except (KeyError, ValueError):
        return None
    return captured_at.replace(microsecond=_subsecond_microseconds(exif_ifd))


def _subsecond_microseconds(exif_ifd: dict) -> int:
    digits = str(exif_ifd.get(SUBSEC_TIME_ORIGINAL_TAG, "")).strip()
    if not digits.isdigit():
        return 0
    return int(digits[:6].ljust(6, "0"))
