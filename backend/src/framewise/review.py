import hashlib
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from framewise.analyzer import FrameAnalyzer, FrameSignals
from framewise.camera_rating import read_camera_rating
from framewise.capture_time import read_capture_time
from framewise.scan import scan_session
from framewise.store import SessionStore
from framewise.thumbnails import make_thumbnail

DEFAULT_DATA_DIR = Path.home() / "Library" / "Application Support" / "framewise"
BACKGROUND_CORE_DIVISOR = 4


def resolve_data_dir() -> Path:
    return Path(os.environ.get("FRAMEWISE_DATA_DIR", DEFAULT_DATA_DIR))


def session_database_path(root: Path, data_dir: Path) -> Path:
    digest = hashlib.sha256(str(root).encode()).hexdigest()[:16]
    return data_dir / f"{root.name}-{digest}.sqlite"


def open_session(folder: Path, data_dir: Path) -> SessionStore:
    root = folder.resolve()
    store = SessionStore(session_database_path(root, data_dir), root)
    scan = scan_session(root)
    store.remove_frames_except(scan.frames)
    for frame in scan.frames:
        store.save_frame(frame, read_camera_rating(frame.jpg_path, frame.raw_path))
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

    def __init__(self, store: SessionStore, analyzer: FrameAnalyzer, background: bool = False):
        self._store = store
        self._analyzer = analyzer
        self._background = background
        self._lock = threading.Lock()
        work = [self._work_for(store.root / frame.jpg_path) for frame in store.frames()]
        self._pending = [item for item in work if item.needs_thumbnail or item.needs_analysis]
        self._frames_total = len(work)
        self._frames_done = len(work) - len(self._pending)
        self._frames_done_this_run = 0
        self._started_at = time.monotonic()

    def run(self) -> None:
        with self._lock:
            self._started_at = time.monotonic()
        with ThreadPoolExecutor(
            max_workers=self._worker_count(), initializer=self._prepare_worker
        ) as pool:
            futures = {pool.submit(self._process, item): item for item in self._pending}
            for future in as_completed(futures):
                try:
                    self._save(future.result())
                except Exception as error:
                    jpg_path = futures[future].jpg_path
                    print(
                        f"framewise: warning: could not analyse {jpg_path}: {error}",
                        file=sys.stderr,
                    )
                    self._count_done()

    def progress(self) -> AnalysisProgress:
        with self._lock:
            frames_left = self._frames_total - self._frames_done
            if frames_left == 0:
                seconds_remaining = 0.0
            elif self._frames_done_this_run == 0:
                seconds_remaining = None
            else:
                elapsed = time.monotonic() - self._started_at
                seconds_remaining = elapsed / self._frames_done_this_run * frames_left
            return AnalysisProgress(self._frames_done, frames_left, seconds_remaining)

    def _work_for(self, jpg_path: Path) -> _FrameWork:
        return _FrameWork(
            jpg_path=jpg_path,
            needs_thumbnail=not self._store.has_current_thumbnail(jpg_path),
            needs_analysis=not self._store.has_current_analysis(jpg_path),
        )

    def _process(self, item: _FrameWork) -> _FrameResult:
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
        self._count_done()

    def _count_done(self) -> None:
        with self._lock:
            self._frames_done += 1
            self._frames_done_this_run += 1

    def _worker_count(self) -> int:
        cores = os.cpu_count() or 1
        return max(1, cores // BACKGROUND_CORE_DIVISOR) if self._background else cores

    def _prepare_worker(self) -> None:
        if self._background and sys.platform == "darwin":
            os.setpriority(os.PRIO_DARWIN_THREAD, 0, os.PRIO_DARWIN_BG)
