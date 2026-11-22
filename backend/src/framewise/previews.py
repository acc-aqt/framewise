"""Embedded previews: a RAW-only Frame is analyzed from the largest preview JPG embedded in its RAW
(ADR-0011). Previews are extracted with ExifTool into the Session store's preview cache, never into
the Session folder."""

import base64
import re
import tomllib
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
UNDECODABLE_PREVIEW = "ExifTool returned the preview in a form framewise could not decode"
DEFAULT_MIN_PREVIEW_LONG_EDGE = 1600
"""The smallest long edge, in pixels, of a preview that sharpness and faces can be judged on."""
CONFIG_SECTION = "raw_only"
MIN_PREVIEW_LONG_EDGE_KEY = "min_preview_long_edge"


@dataclass(frozen=True)
class Preview:
    width: int
    height: int


class PreviewError(Exception):
    """Why a RAW's embedded preview could not be extracted."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class PreviewConfigError(ValueError):
    """The [raw_only] settings in the config file are invalid."""


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
        try:
            preview = self._extract_largest(raw, partial)
            self._copy_metadata(raw, partial)
            partial.replace(destination)
            return preview
        finally:
            partial.unlink(missing_ok=True)

    def _extract_largest(self, raw: Path, path: Path) -> Preview:
        """Writes the largest preview Pillow can read to `path`. Raises PreviewError, with
        ExifTool's last error if it gave one, when there is none."""
        error = None
        for tag in self._previews_largest_first(raw):
            path.unlink(missing_ok=True)
            tag_error = self._write_binary(raw, tag, path)
            if tag_error is not None:
                error = tag_error
                continue
            preview = _jpg_size(path)
            if preview is not None:
                return preview
        raise PreviewError(NO_PREVIEW if error is None else f"{NO_PREVIEW}: {error}")

    def _copy_metadata(self, raw: Path, preview: Path) -> None:
        """Copies the RAW's metadata into the preview. A preview without it is refused, because
        its orientation and capture time would be wrong."""
        result = self._exiftool.run(
            "-overwrite_original", "-tagsFromFile", raw, "-all:all", preview
        )
        if result.errors:
            raise PreviewError(
                f"ExifTool could not copy the RAW's metadata into its preview: {result.errors[0]}"
            )

    def _write_binary(self, raw: Path, tag: str, path: Path) -> str | None:
        """Writes the tag's binary value to `path`, returning why it could not, if it could not.
        ExifTool's -W writes it directly, but reads % in the path as the start of a format code,
        so a path with % takes the slower way through ExifTool's JSON, which carries the value in
        base64."""
        if "%" not in str(path):
            errors = self._exiftool.run("-b", f"-{tag}", "-W!", path, raw).errors
            return errors[0] if errors else None
        try:
            [entry] = self._exiftool.read_json("-b", f"-{tag}", raw)
            [value] = [value for name, value in entry.items() if name != "SourceFile"]
            if not (isinstance(value, str) and value.startswith("base64:")):
                return UNDECODABLE_PREVIEW
            path.write_bytes(base64.b64decode(value.removeprefix("base64:"), validate=True))
        except ValueError:
            return UNDECODABLE_PREVIEW
        return None

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


def read_min_preview_long_edge(config_path: Path) -> int:
    """The minimum long edge of a RAW-only Frame's preview, from the [raw_only] table of a config
    file. A missing file or setting keeps the default."""
    try:
        with config_path.open("rb") as file:
            config = tomllib.load(file)
    except FileNotFoundError:
        return DEFAULT_MIN_PREVIEW_LONG_EDGE
    except tomllib.TOMLDecodeError as error:
        raise PreviewConfigError(f"{config_path}: invalid TOML: {error}") from error
    settings = config.get(CONFIG_SECTION, {})
    if not isinstance(settings, dict):
        raise PreviewConfigError(f"{config_path}: [{CONFIG_SECTION}] must be a table")
    for key in settings:
        if key != MIN_PREVIEW_LONG_EDGE_KEY:
            raise PreviewConfigError(f"{config_path}: [{CONFIG_SECTION}] has unknown setting {key}")
    value = settings.get(MIN_PREVIEW_LONG_EDGE_KEY, DEFAULT_MIN_PREVIEW_LONG_EDGE)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise PreviewConfigError(
            f"{config_path}: {MIN_PREVIEW_LONG_EDGE_KEY} must be a whole number of pixels, "
            "1 or more"
        )
    return value


def cache_previews(
    store: SessionStore,
    frames: list[ScannedFrame],
    extract_preview: ExtractPreview,
    min_long_edge: int = DEFAULT_MIN_PREVIEW_LONG_EDGE,
) -> tuple[list[ScannedFrame], dict[Path, str]]:
    """Makes sure each RAW-only Frame has a current preview in the preview cache, reusing one while
    its RAW's size and modification time are unchanged. Returns the Frames that can be analyzed,
    and the RAWs without a usable preview, or with one whose long edge is below `min_long_edge`,
    with the reason."""
    usable, skipped = [], {}
    for frame in frames:
        if frame.jpg_path is not None:
            usable.append(frame)
            continue
        try:
            preview = _current_preview(store, frame, extract_preview)
        except PreviewError as error:
            skipped[frame.raw_path] = error.reason
            continue
        long_edge = max(preview.width, preview.height)
        if long_edge < min_long_edge:
            skipped[frame.raw_path] = (
                f"The embedded preview is too small to judge: {long_edge} px on its long edge, "
                f"below the minimum of {min_long_edge} px"
            )
            continue
        usable.append(frame)
    return usable, skipped


def _current_preview(
    store: SessionStore, frame: ScannedFrame, extract_preview: ExtractPreview
) -> Preview:
    cached = store.current_preview_size(frame)
    if cached is not None:
        return Preview(*cached)
    preview = extract_preview(frame.raw_path, store.new_preview_file(frame))
    store.save_preview(frame, preview.width, preview.height)
    return preview


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
