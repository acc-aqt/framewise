"""Rating write-back: writes the reviewed Verdicts into the Frames' files as XMP ratings and color
labels, so Lightroom Classic reads them on import (ADR-0001).

Only xmp:Rating and xmp:Label change. Each file's original values are recorded in the Session
store before its first write, so undo can restore them however often write-back is re-applied.
"""

import os
import threading
from dataclasses import dataclass
from pathlib import Path

from framewise.exiftool import ExifTool
from framewise.judge import Verdict
from framewise.lightroom import LabelSet
from framewise.store import Frame, SessionStore, WrittenFileOriginal

# Lightroom ignores sidecars for these, so their XMP is embedded. Other RAWs get a sidecar.
EMBEDDED_XMP_EXTENSIONS = {".jpg", ".jpeg", ".dng"}
SIDECAR_EXTENSION = ".xmp"
READ_ONLY_ERROR = "File is read-only"
# Each Verdict's stars and color label (ADR-0001).
VERDICT_RATINGS: dict[Verdict, tuple[int, str | None]] = {
    Verdict.WINNER: (3, None),
    Verdict.KEEPER: (2, None),
    Verdict.REJECT: (0, "red"),
    Verdict.UNSURE: (0, "yellow"),
}


@dataclass(frozen=True)
class Rating:
    stars: int | None
    label: str | None


@dataclass(frozen=True)
class FileChange:
    frame_id: int
    path: str
    """The Frame's file, relative to the Session folder."""
    written_to: str
    """The file the XMP goes into: the file itself, or its sidecar."""
    verdict: Verdict
    old: Rating
    new: Rating


@dataclass(frozen=True)
class FileFailure:
    path: str
    error: str


@dataclass(frozen=True)
class WriteBackResult:
    written: list[str]
    failed: list[FileFailure]


@dataclass(frozen=True)
class ReviewedFrame:
    """A Frame's final Verdict, and the stars and color label of its Override, if any."""

    frame: Frame
    verdict: Verdict
    stars: int | None = None
    color: str | None = None


def rating_for(reviewed: ReviewedFrame, label_set: LabelSet) -> Rating:
    """The Verdict's stars and label, each replaced by the Override's if it has one."""
    stars, color = VERDICT_RATINGS[reviewed.verdict]
    if reviewed.stars is not None:
        stars = reviewed.stars
    if reviewed.color is not None:
        color = reviewed.color
    return Rating(stars, None if color is None else label_set.name(color))


class RatingWriteBack:
    def __init__(self, store: SessionStore, exiftool: ExifTool):
        self._store = store
        self._exiftool = exiftool
        self._lock = threading.Lock()

    def dry_run(self, reviewed: list[ReviewedFrame], label_set: LabelSet) -> list[FileChange]:
        planned = [(item, path) for item in reviewed for path in _files_of(item.frame)]
        old_ratings = self._read_ratings([self._rating_source(path) for _, path in planned])
        return [
            FileChange(
                frame_id=item.frame.id,
                path=path,
                written_to=_written_to(path),
                verdict=item.verdict,
                old=old,
                new=rating_for(item, label_set),
            )
            for (item, path), old in zip(planned, old_ratings, strict=True)
        ]

    def apply(self, reviewed: list[ReviewedFrame], label_set: LabelSet) -> WriteBackResult:
        with self._lock:
            written, failed = [], []
            for change in self.dry_run(reviewed, label_set):
                if change.old == change.new:
                    continue
                error = self._apply_change(change)
                if error is None:
                    written.append(change.path)
                else:
                    failed.append(FileFailure(change.path, error))
            return WriteBackResult(written, failed)

    def undo(self) -> WriteBackResult:
        with self._lock:
            written, failed = [], []
            for original in self._store.write_back_originals():
                error = self._restore(original)
                if error is None:
                    self._store.forget_write_back_original(original.path)
                    written.append(original.path)
                else:
                    failed.append(FileFailure(original.path, error))
            return WriteBackResult(written, failed)

    def can_undo(self) -> bool:
        return bool(self._store.write_back_originals())

    def _apply_change(self, change: FileChange) -> str | None:
        target = self._absolute(change.written_to)
        created = not target.exists()
        if not created and not os.access(target, os.W_OK):
            return READ_ONLY_ERROR
        recorded = self._store.record_write_back_original(
            WrittenFileOriginal(
                path=change.written_to,
                stars=None if created else change.old.stars,
                label=None if created else change.old.label,
                created=created,
            )
        )
        error = self._write(target, change.new)
        if error is not None and recorded:
            self._store.forget_write_back_original(change.written_to)
        return error

    def _restore(self, original: WrittenFileOriginal) -> str | None:
        target = self._absolute(original.path)
        if original.created:
            target.unlink(missing_ok=True)
            return None
        if not target.exists():
            return "File no longer exists"
        if not os.access(target, os.W_OK):
            return READ_ONLY_ERROR
        return self._write(target, Rating(original.stars, original.label))

    def _write(self, target: Path, rating: Rating) -> str | None:
        """Writes the rating and label, removing either when it is None. Keeps the file's
        modification time, and its thumbnail and analysis current, since the image data stays
        the same."""
        before = target.stat() if target.exists() else None
        result = self._exiftool.run(
            "-overwrite_original",
            "-preserve",
            f"-XMP-xmp:Rating={'' if rating.stars is None else rating.stars}",
            f"-XMP-xmp:Label={rating.label or ''}",
            target,
        )
        if result.errors:
            return "; ".join(result.errors)
        if before is not None:
            self._store.keep_current_after_metadata_write(
                target, before.st_size, before.st_mtime_ns
            )
        return None

    def _rating_source(self, path: str) -> Path:
        """The file Lightroom would read the current rating from: a RAW's sidecar if it has
        one, otherwise the file itself."""
        sidecar = self._absolute(_written_to(path))
        return sidecar if sidecar.exists() else self._absolute(path)

    def _read_ratings(self, paths: list[Path]) -> list[Rating]:
        if not paths:
            return []
        entries = self._exiftool.read_json("-n", "-XMP-xmp:Rating", "-XMP-xmp:Label", *paths)
        by_path = {entry["SourceFile"]: entry for entry in entries}
        return [_rating_from(by_path.get(str(path), {})) for path in paths]

    def _absolute(self, relative: str) -> Path:
        return self._store.root / relative


def _files_of(frame: Frame) -> list[str]:
    return [frame.jpg_path] if frame.raw_path is None else [frame.jpg_path, frame.raw_path]


def _written_to(path: str) -> str:
    file = Path(path)
    if file.suffix.lower() in EMBEDDED_XMP_EXTENSIONS:
        return path
    return file.with_suffix(SIDECAR_EXTENSION).as_posix()


def _rating_from(entry: dict) -> Rating:
    stars = entry.get("Rating")
    label = entry.get("Label")
    return Rating(
        stars=None if stars is None else int(float(stars)),
        label=None if label in (None, "") else str(label),
    )
