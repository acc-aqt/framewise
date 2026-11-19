"""Embedded previews: a RAW-only Frame is analyzed from the largest preview JPG embedded in its RAW
(ADR-0011). Previews are extracted with ExifTool into the Session store's preview cache, never into
the Session folder."""

import base64
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from framewise.exiftool import ExifTool
from framewise.scan import ScannedFrame
from framewise.store import SessionStore

PREVIEW_TAGS = ("PreviewImage", "JpgFromRaw", "OtherImage")
BINARY_SIZE = re.compile(r"\(Binary data (\d+) bytes")
NO_PREVIEW = "The RAW holds no embedded preview framewise can read"


@dataclass(frozen=True)
class Preview:
    width: int
    height: int


class PreviewError(Exception):
    """Why a RAW's embedded preview could not be extracted."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


ExtractPreview = Callable[[Path, Path], Preview]
"""Extracts the largest preview embedded in a RAW into a JPG at the destination, or raises
PreviewError."""


class ExifToolPreviews:
    """Extracts embedded previews with ExifTool, then copies the RAW's metadata into the preview, so
    its orientation, capture time and focus point are read as from a camera JPG."""

    def __init__(self, exiftool: ExifTool):
        self._exiftool = exiftool

    def __call__(self, raw: Path, destination: Path) -> Preview:
        try:
            return self._extract(raw, destination)
        except OSError as error:
            raise PreviewError(f"ExifTool could not read the RAW: {error}") from error

    def _extract(self, raw: Path, destination: Path) -> Preview:
        partial = destination.with_name(f"{destination.stem}.partial{destination.suffix}")
        for tag in self._previews_largest_first(raw):
            partial.unlink(missing_ok=True)
            self._write_binary(raw, tag, partial)
            preview = _jpg_size(partial)
            if preview is None:
                continue
            self._exiftool.run("-overwrite_original", "-tagsFromFile", raw, "-all:all", partial)
            partial.replace(destination)
            return preview
        partial.unlink(missing_ok=True)
        raise PreviewError(NO_PREVIEW)

    def _write_binary(self, raw: Path, tag: str, path: Path) -> None:
        """Writes the tag's binary value to `path`. ExifTool's -W writes it directly, but reads %
        in the path as the start of a format code, so a path with % takes the slower way through
        ExifTool's JSON, which carries the value in base64."""
        if "%" not in str(path):
            self._exiftool.run("-b", f"-{tag}", "-W!", path, raw)
            return
        try:
            [entry] = self._exiftool.read_json("-b", f"-{tag}", raw)
            [value] = [value for name, value in entry.items() if name != "SourceFile"]
            if isinstance(value, str) and value.startswith("base64:"):
                path.write_bytes(base64.b64decode(value.removeprefix("base64:"), validate=True))
        except ValueError:
            return

    def _previews_largest_first(self, raw: Path) -> list[str]:
        """The RAW's embedded preview tags, group-qualified, largest first."""
        try:
            [tags] = self._exiftool.read_json(
                "-a", "-G1", *(f"-{tag}" for tag in PREVIEW_TAGS), raw
            )
        except ValueError:
            return []
        sizes = {
            name: int(match.group(1))
            for name, value in tags.items()
            if isinstance(value, str) and (match := BINARY_SIZE.match(value))
        }
        return sorted(sizes, key=sizes.__getitem__, reverse=True)


def cache_previews(
    store: SessionStore, frames: list[ScannedFrame], extract_preview: ExtractPreview
) -> tuple[list[ScannedFrame], dict[Path, str]]:
    """Makes sure each RAW-only Frame has a current preview in the preview cache, reusing one while
    its RAW's size and modification time are unchanged. Returns the Frames that can be analyzed,
    and the RAWs without a usable preview with the reason."""
    usable, skipped = [], {}
    for frame in frames:
        if frame.jpg_path is not None or store.has_current_preview(frame):
            usable.append(frame)
            continue
        try:
            preview = extract_preview(frame.raw_path, store.new_preview_file(frame))
        except PreviewError as error:
            skipped[frame.raw_path] = error.reason
            continue
        store.save_preview(frame, preview.width, preview.height)
        usable.append(frame)
    return usable, skipped


def _jpg_size(path: Path) -> Preview | None:
    """The size of the JPG at `path` if Pillow can read it, otherwise None."""
    if not path.is_file():
        return None
    try:
        with Image.open(path) as image:
            if image.format != "JPEG":
                return None
            image.verify()
            return Preview(*image.size)
    except (OSError, ValueError, Image.DecompressionBombError):
        return None
