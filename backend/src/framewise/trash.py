"""Trash: moves Frames' files to the OS Trash and takes the Frames out of the Session (ADR-0006).

Nothing is ever deleted outright. Where the volume has no Trash, trashing fails instead."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from send2trash import send2trash

from framewise.store import Frame, SessionStore
from framewise.write_back import SIDECAR_EXTENSION

MoveToTrash = Callable[[Path], None]
OUTSIDE_SESSION_ERROR = "File is outside the Session folder"
RAW_ONLY_ERROR = "framewise can't trash RAW-only Frames yet"


@dataclass(frozen=True)
class TrashFailure:
    path: str
    error: str


@dataclass(frozen=True)
class TrashResult:
    trashed: list[int]
    """The ids of the Frames that left the Session."""
    failed: list[TrashFailure]


def files_to_trash(frame: Frame) -> list[str]:
    """The files of a JPG-only or RAW+JPG Frame relative to the Session folder, its main file last.
    A RAW's sidecar belongs to the Frame, so it is trashed with it."""
    if frame.raw_path is None:
        return [frame.jpg_path]
    sidecar = Path(frame.raw_path).with_suffix(SIDECAR_EXTENSION).as_posix()
    return [frame.raw_path, sidecar, frame.jpg_path]


def trash_frames(
    store: SessionStore, frames: list[Frame], move_to_trash: MoveToTrash = send2trash
) -> TrashResult:
    """Trashes each Frame's files. A Frame leaves the Session once its main file is in the Trash;
    its Overrides are kept, as for any Frame that vanishes, so they come back if it is
    restored. RAW-only Frames are refused and stay, until #151."""
    trashed, failed = [], []
    for frame in frames:
        if frame.kind == "raw-only":
            failed.append(TrashFailure(frame.main_path, RAW_ONLY_ERROR))
            continue
        errors = [
            TrashFailure(path, error)
            for path in files_to_trash(frame)
            if (error := _trash(store.root, path, move_to_trash)) is not None
        ]
        failed.extend(errors)
        if not (store.root / frame.main_path).exists():
            trashed.append(frame)
    store.remove_frames([frame.main_path for frame in trashed])
    return TrashResult([frame.id for frame in trashed], failed)


def _trash(root: Path, relative: str, move_to_trash: MoveToTrash) -> str | None:
    path = root / relative
    if not path.exists() and not path.is_symlink():
        return None
    if not path.parent.resolve().is_relative_to(root.resolve()):
        return OUTSIDE_SESSION_ERROR
    try:
        move_to_trash(path)
    except OSError as error:
        return str(error) or type(error).__name__
    return None
