import hashlib
import os
import sys
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from framewise.analyzer import FrameAnalyzer, FrameSignals
from framewise.camera_rating import CameraRating, read_camera_rating
from framewise.capture_time import read_capture_time
from framewise.exiftool import ExifTool
from framewise.scan import scan_session
from framewise.store import SessionStore
from framewise.thumbnails import make_thumbnail
from framewise.write_back import RatingWriteBack, WriteBackResult

DEFAULT_DATA_DIR = Path.home() / "Library" / "Application Support" / "framewise"
BACKGROUND_CORE_DIVISOR = 4


def resolve_data_dir() -> Path:
    return Path(os.environ.get("FRAMEWISE_DATA_DIR", DEFAULT_DATA_DIR))


def session_database_path(root: Path, data_dir: Path) -> Path:
    digest = hashlib.sha256(str(root).encode()).hexdigest()[:16]
    return data_dir / f"{root.name}-{digest}.sqlite"


def hard_reset_session(folder: Path, data_dir: Path, exiftool: ExifTool) -> WriteBackResult | None:
    """Undoes Rating write-back, then deletes the Session store, so the next review analyses
    every Frame again. Keeps the store if a file fails to restore, so the reset can be retried.
    None if the folder has no Session store."""
    root = folder.resolve()
    database = session_database_path(root, data_dir)
    if not database.exists():
        return None
    store = SessionStore(database, root)
    try:
        result = RatingWriteBack(store, exiftool).undo()
    finally:
        store.close()
    if not result.failed:
        for suffix in ("", "-wal", "-shm"):
            database.with_name(database.name + suffix).unlink(missing_ok=True)
    return result


def open_session(folder: Path, data_dir: Path) -> SessionStore:
    root = folder.resolve()
    store = SessionStore(session_database_path(root, data_dir), root)
    scan = scan_session(root)
    store.remove_frames_except(scan.frames)
    originals = {
        root / original.path: CameraRating(original.stars, original.label)
        for original in store.write_back_originals()
    }
    for frame in scan.frames:
        store.save_frame(frame, read_camera_rating(frame.jpg_path, frame.raw_path, originals))
    store.save_skipped_files(scan.skipped)
    return store


@dataclass(frozen=True)
class AnalysisProgress:
    frames_done: int
    frames_left: int
    seconds_remaining: float | None


@dataclass(frozen=True)
class _FrameWork:
    jpg_path: Path
    needs_thumbnail: bool
    needs_analysis: bool


@dataclass(frozen=True)
class _FrameResult:
    jpg_path: Path
    thumbnail: bytes | None
    signals: FrameSignals | None
    captured_at: datetime | None


class SessionAnalysis:
    """Makes thumbnails and analyses a Session's Frames in parallel, saving each Frame as it
    finishes so the Review UI can show Groups before the whole Session is done."""

    def __init__(
        self,
        store: SessionStore,
        analyzer: FrameAnalyzer,
        background: bool = False,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._store = store
        self._analyzer = analyzer
        self._background = background
        self._clock = clock
        self._workers = self._worker_count()
        self._lock = threading.Lock()
        work = [self._work_for(store.root / frame.jpg_path) for frame in store.frames()]
        self._pending = [item for item in work if item.needs_thumbnail or item.needs_analysis]
        self._frames_total = len(work)
        self._frames_done = len(work) - len(self._pending)
        self._analyses_left = sum(item.needs_analysis for item in self._pending)
        self._analyses_started_at: dict[Path, float] = {}
        self._analysis_seconds_total = 0.0
        self._analyses_done = 0

    def run(self) -> None:
        with ThreadPoolExecutor(
            max_workers=self._workers, initializer=self._prepare_worker
        ) as pool:
            futures = {pool.submit(self._process, item): item for item in self._pending}
            for future in as_completed(futures):
                item = futures[future]
                try:
                    self._save(future.result())
                except Exception as error:
                    print(
                        f"framewise: warning: could not analyse {item.jpg_path}: {error}",
                        file=sys.stderr,
                    )
                self._count_done(item)

    def progress(self) -> AnalysisProgress:
        with self._lock:
            frames_left = self._frames_total - self._frames_done
            return AnalysisProgress(self._frames_done, frames_left, self._seconds_remaining())

    def _seconds_remaining(self) -> float | None:
        """Spreads the analyses left over the workers, allowing for the time the Frames in
        analysis have already had. Frames that only need a thumbnail count as free."""
        if self._analyses_left == 0:
            return 0.0
        if self._analyses_done == 0:
            return None
        seconds_per_analysis = self._analysis_seconds_total / self._analyses_done
        now = self._clock()
        head_start = sum(
            min(now - started_at, seconds_per_analysis)
            for started_at in self._analyses_started_at.values()
        )
        work_left = self._analyses_left * seconds_per_analysis - head_start
        return work_left / min(self._workers, self._analyses_left)

    def _work_for(self, jpg_path: Path) -> _FrameWork:
        return _FrameWork(
            jpg_path=jpg_path,
            needs_thumbnail=not self._store.has_current_thumbnail(jpg_path),
            needs_analysis=not self._store.has_current_analysis(jpg_path),
        )

    def _process(self, item: _FrameWork) -> _FrameResult:
        if item.needs_analysis:
            with self._lock:
                self._analyses_started_at[item.jpg_path] = self._clock()
        return _FrameResult(
            jpg_path=item.jpg_path,
            thumbnail=make_thumbnail(item.jpg_path) if item.needs_thumbnail else None,
            signals=self._analyzer.analyze(item.jpg_path) if item.needs_analysis else None,
            captured_at=read_capture_time(item.jpg_path) if item.needs_analysis else None,
        )

    def _save(self, result: _FrameResult) -> None:
        if result.thumbnail is not None:
            self._store.save_thumbnail(result.jpg_path, result.thumbnail)
        if result.signals is not None:
            self._store.save_analysis(result.jpg_path, result.signals, result.captured_at)

    def _count_done(self, item: _FrameWork) -> None:
        with self._lock:
            self._frames_done += 1
            if item.needs_analysis:
                started_at = self._analyses_started_at.pop(item.jpg_path)
                self._analysis_seconds_total += self._clock() - started_at
                self._analyses_done += 1
                self._analyses_left -= 1

    def _worker_count(self) -> int:
        cores = os.cpu_count() or 1
        return max(1, cores // BACKGROUND_CORE_DIVISOR) if self._background else cores

    def _prepare_worker(self) -> None:
        if self._background and sys.platform == "darwin":
            os.setpriority(os.PRIO_DARWIN_THREAD, 0, os.PRIO_DARWIN_BG)
