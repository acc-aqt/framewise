import os
from dataclasses import dataclass
from pathlib import Path

JPG_EXTENSIONS = {".jpg", ".jpeg"}
RAW_EXTENSIONS = {".dng", ".raf", ".arw", ".nef", ".cr3"}
IGNORE_MARKER = ".framewise-ignore"


@dataclass(frozen=True)
class ScannedFrame:
    jpg_path: Path | None
    raw_path: Path | None = None

    @property
    def main_path(self) -> Path:
        """The file that identifies the Frame: its JPG, or the RAW of a RAW-only Frame."""
        return self.jpg_path or self.raw_path


def scan_session(root: Path) -> list[ScannedFrame]:
    frames: list[ScannedFrame] = []
    for folder, subfolders, names in os.walk(root):
        if IGNORE_MARKER in names:
            subfolders.clear()
            continue
        subfolders.sort()
        files = [
            Path(folder) / name
            for name in names
            if not name.startswith(".") and _is_plain_file(Path(folder) / name)
        ]
        frames.extend(_pair_folder(files))
    return frames


def _is_plain_file(path: Path) -> bool:
    """A regular file in the Session itself: not a symbolic link, which could point outside it,
    and without a line break in its name, which ExifTool cannot take."""
    return not path.is_symlink() and path.is_file() and not any(c in path.name for c in "\r\n")


def _pair_folder(files: list[Path]) -> list[ScannedFrame]:
    """A RAW and a JPG with the same base name make a RAW+JPG Frame. Each JPG and RAW left over
    makes a Frame of its own."""
    raws_by_stem: dict[str, list[Path]] = {}
    for path in sorted(files):
        if path.suffix.lower() in RAW_EXTENSIONS:
            raws_by_stem.setdefault(path.stem.lower(), []).append(path)
    jpgs = sorted(path for path in files if path.suffix.lower() in JPG_EXTENSIONS)
    frames = [ScannedFrame(jpg_path=jpg, raw_path=_take_raw(raws_by_stem, jpg)) for jpg in jpgs]
    lone_raws = sorted(raw for raws in raws_by_stem.values() for raw in raws)
    return frames + [ScannedFrame(jpg_path=None, raw_path=raw) for raw in lone_raws]


def _take_raw(raws_by_stem: dict[str, list[Path]], jpg: Path) -> Path | None:
    raws = raws_by_stem.get(jpg.stem.lower())
    return raws.pop(0) if raws else None
