import os
from dataclasses import dataclass
from pathlib import Path

JPG_EXTENSIONS = {".jpg", ".jpeg"}
RAW_EXTENSIONS = {".dng", ".raf", ".arw", ".nef", ".cr3"}


@dataclass(frozen=True)
class ScannedFrame:
    jpg_path: Path
    raw_path: Path | None = None


@dataclass(frozen=True)
class ScanResult:
    frames: list[ScannedFrame]
    skipped: list[Path]


def scan_session(root: Path) -> ScanResult:
    frames: list[ScannedFrame] = []
    skipped: list[Path] = []
    for folder, subfolders, names in os.walk(root):
        subfolders.sort()
        files = [Path(folder) / name for name in names if not name.startswith(".")]
        result = _pair_folder(files)
        frames.extend(result.frames)
        skipped.extend(result.skipped)
    return ScanResult(frames=frames, skipped=skipped)


def _pair_folder(files: list[Path]) -> ScanResult:
    raws_by_stem = {
        path.stem.lower(): path for path in files if path.suffix.lower() in RAW_EXTENSIONS
    }
    jpgs = sorted(path for path in files if path.suffix.lower() in JPG_EXTENSIONS)
    frames = [
        ScannedFrame(jpg_path=jpg, raw_path=raws_by_stem.pop(jpg.stem.lower(), None))
        for jpg in jpgs
    ]
    return ScanResult(frames=frames, skipped=sorted(raws_by_stem.values()))
