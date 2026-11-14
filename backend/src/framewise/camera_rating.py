import mmap
import xml.etree.ElementTree as ElementTree
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

XMP_NAMESPACE = "{http://ns.adobe.com/xap/1.0/}"
XMP_START = b"<x:xmpmeta"
XMP_END = b"</x:xmpmeta>"
EXIF_RATING_TAG = 0x4746


@dataclass(frozen=True)
class CameraRating:
    stars: int | None = None
    label: str | None = None

    def or_else(self, fallback: "CameraRating") -> "CameraRating":
        return CameraRating(
            stars=self.stars if self.stars is not None else fallback.stars,
            label=self.label if self.label is not None else fallback.label,
        )


def read_camera_rating(
    jpg_path: Path, raw_path: Path | None, originals: Mapping[Path, CameraRating]
) -> CameraRating:
    """Reads the rating and label the camera wrote. `originals` holds the XMP values files had
    before Rating write-back changed them; they are read instead of those files' XMP."""
    rating = _read_xmp(jpg_path, originals).or_else(_read_exif(jpg_path))
    if raw_path is not None:
        rating = rating.or_else(_read_xmp(raw_path, originals))
        rating = rating.or_else(_read_sidecar(raw_path, originals))
    return rating


def _read_sidecar(raw_path: Path, originals: Mapping[Path, CameraRating]) -> CameraRating:
    sidecar = raw_path.with_suffix(".xmp")
    if sidecar in originals or sidecar.is_file():
        return _read_xmp(sidecar, originals)
    return CameraRating()


def _read_exif(jpg_path: Path) -> CameraRating:
    try:
        with Image.open(jpg_path) as image:
            stars = image.getexif().get(EXIF_RATING_TAG)
    except OSError:
        return CameraRating()
    return CameraRating(stars=_parse_stars(stars))


def _read_xmp(path: Path, originals: Mapping[Path, CameraRating]) -> CameraRating:
    if path in originals:
        return originals[path]
    packet = _find_xmp_packet(path)
    if packet is None:
        return CameraRating()
    try:
        root = ElementTree.fromstring(packet)
    except ElementTree.ParseError:
        return CameraRating()
    return CameraRating(
        stars=_parse_stars(_xmp_value(root, "Rating")), label=_xmp_value(root, "Label")
    )


def _parse_stars(value: int | str | None) -> int | None:
    return None if value is None else int(float(value))


def _find_xmp_packet(path: Path) -> bytes | None:
    with path.open("rb") as file:
        if path.stat().st_size == 0:
            return None
        with mmap.mmap(file.fileno(), 0, access=mmap.ACCESS_READ) as content:
            start = content.find(XMP_START)
            if start == -1:
                return None
            end = content.find(XMP_END, start)
            if end == -1:
                return None
            return content[start : end + len(XMP_END)]


def _xmp_value(root: ElementTree.Element, name: str) -> str | None:
    key = XMP_NAMESPACE + name
    for element in root.iter():
        if key in element.attrib:
            return element.attrib[key]
        if element.tag == key and element.text:
            return element.text.strip()
    return None
