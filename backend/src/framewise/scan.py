import os
from dataclasses import dataclass
from pathlib import Path

JPG_EXTENSIONS = {".jpg", ".jpeg"}
RAW_EXTENSIONS = {".dng", ".raf", ".arw", ".nef", ".cr3"}
IGNORE_MARKER = ".framewise-ignore"


@dataclass(frozen=True)
class ScannedFrame:
    jpg_path: Path
    raw_path: Path | None = None


@dataclass(frozen=True)
class Scan:
    frames: list[ScannedFrame]
    skipped: list[Path]


def scan_session(root: Path) -> Scan:
    frames: list[ScannedFrame] = []
    skipped: list[Path] = []
    for folder, subfolders, names in os.walk(root):
        if IGNORE_MARKER in names:
            subfolders.clear()
            continue
        subfolders.sort()
        files = [Path(folder) / name for name in names if not name.startswith(".")]
        result = _pair_folder(files)
        frames.extend(result.frames)
        skipped.extend(result.skipped)
    return Scan(frames=frames, skipped=skipped)


def _pair_folder(files: list[Path]) -> Scan:
    raws_by_stem: dict[str, list[Path]] = {}
    for path in sorted(files):
        if path.suffix.lower() in RAW_EXTENSIONS:
            raws_by_stem.setdefault(path.stem.lower(), []).append(path)
    jpgs = sorted(path for path in files if path.suffix.lower() in JPG_EXTENSIONS)
    frames = [ScannedFrame(jpg_path=jpg, raw_path=_take_raw(raws_by_stem, jpg)) for jpg in jpgs]
    skipped = sorted(raw for raws in raws_by_stem.values() for raw in raws)
    return Scan(frames=frames, skipped=skipped)


def _take_raw(raws_by_stem: dict[str, list[Path]], jpg: Path) -> Path | None:
    raws = raws_by_stem.get(jpg.stem.lower())
    return raws.pop(0) if raws else None
