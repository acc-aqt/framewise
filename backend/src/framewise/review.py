import hashlib
import os
import shutil
import sys
import threading
import time
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from framewise.analyzer import FrameAnalyzer, FrameSignals
from framewise.camera_rating import CameraRating, read_camera_rating
from framewise.capture_time import read_capture_time
from framewise.exiftool import ExifTool
from framewise.grouper import group_frames
from framewise.previews import (
    DEFAULT_MIN_PREVIEW_LONG_EDGE,
    ExifToolPreviews,
    ExtractPreview,
    cache_previews,
)
from framewise.scan import scan_session
from framewise.store import AnalyzedFrame, Frame, SessionStore, preview_cache_dir
from framewise.thumbnails import make_thumbnail
from framewise.write_back import RatingWriteBack, WriteBackResult

BACKGROUND_CORE_DIVISOR = 4
LOWEST_PRIORITY_NICENESS = 19


def default_data_dir(platform: str, environ: Mapping[str, str], home: Path) -> Path:
    """Application Support on macOS, local application data on Windows, the XDG data directory
    elsewhere."""
    if platform == "darwin":
        return home / "Library" / "Application Support" / "framewise"
    if platform == "win32":
        return Path(environ.get("LOCALAPPDATA") or home / "AppData" / "Local") / "framewise"
    return Path(environ.get("XDG_DATA_HOME") or home / ".local" / "share") / "framewise"


def resolve_data_dir() -> Path:
    if "FRAMEWISE_DATA_DIR" in os.environ:
        return Path(os.environ["FRAMEWISE_DATA_DIR"])
    return default_data_dir(sys.platform, os.environ, Path.home())


def resolve_config_path() -> Path:
    return resolve_data_dir() / "config.toml"


def session_database_path(root: Path, data_dir: Path) -> Path:
    """One store per Session folder. On Windows, where paths ignore case, a folder reached
    through a differently cased path is the same Session."""
    digest = hashlib.sha256(os.path.normcase(root).encode()).hexdigest()[:16]
    return data_dir / f"{root.name}-{digest}.sqlite"


def hard_reset_session(folder: Path, data_dir: Path, exiftool: ExifTool) -> WriteBackResult | None:
    """Undoes Rating write-back, then deletes the Session store and its preview cache, so the next
    review analyzes every Frame again. Keeps the store if a file fails to restore, so the reset
    can be retried. None if the folder has no Session store."""
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
        shutil.rmtree(preview_cache_dir(database), ignore_errors=True)
    return result


def open_session(
    folder: Path,
    data_dir: Path,
    extract_preview: ExtractPreview | None = None,
    min_preview_long_edge: int = DEFAULT_MIN_PREVIEW_LONG_EDGE,
) -> SessionStore:
    """Scans the Session folder into its Session store. RAW-only Frames get their embedded
    preview cached first, with ExifTool unless `extract_preview` is given; a RAW without a usable
    preview, or with one whose long edge is below `min_preview_long_edge`, is skipped."""
    root = folder.resolve()
    store = SessionStore(session_database_path(root, data_dir), root)
    exiftool = ExifTool()
    try:
        frames, skipped = cache_previews(
            store,
            scan_session(root),
            extract_preview or ExifToolPreviews(exiftool),
            min_preview_long_edge,
        )
    finally:
        exiftool.close()
    store.remove_frames_except(frames)
    originals = {
        root / original.path: CameraRating(original.stars, original.label)
        for original in store.write_back_originals()
    }
    for frame in frames:
        store.save_frame(frame, read_camera_rating(frame.jpg_path, frame.raw_path, originals))
    store.save_skipped_files(skipped)
    return store


@dataclass(frozen=True)
class AnalysisProgress:
    frames_done: int
    frames_left: int
    seconds_remaining: float | None


@dataclass(frozen=True)
class _FrameWork:
    frame: Frame
    source: Path
    """The JPG the Frame's Analysis source is read from."""
    needs_thumbnail: bool
    needs_analysis: bool


@dataclass(frozen=True)
class _FrameResult:
    frame: Frame
    thumbnail: bytes | None
    signals: FrameSignals | None
    captured_at: datetime | None


class SessionAnalysis:
    """Makes thumbnails and analyzes a Session's Frames in parallel, saving each Frame as it
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
        work = [self._work_for(frame) for frame in store.frames()]
        self._pending = [item for item in work if item.needs_thumbnail or item.needs_analysis]
        self._frames_total = len(work)
        self._frames_done = len(work) - len(self._pending)
        self._analyses_left = sum(item.needs_analysis for item in self._pending)
        self._analyses_started_at: dict[str, float] = {}
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
                    # A Frame trashed while it was analyzed fails quietly.
                    if item.source.exists():
                        print(
                            f"framewise: warning: could not analyze {item.source}: {error}",
                            file=sys.stderr,
                        )
                self._count_done(item)

    def groups(self, group_overrides: Mapping[str, str] | None = None) -> list[list[AnalyzedFrame]]:
        """The Groups of the Frames analyzed so far by the current Providers."""
        return group_frames(
            self._store.analyzed_frames(self._analyzer.signature),
            self._analyzer.similarity,
            group_overrides,
        )

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

    def _work_for(self, frame: Frame) -> _FrameWork:
        return _FrameWork(
            frame=frame,
            source=self._store.analysis_image(frame),
            needs_thumbnail=not self._store.has_current_thumbnail(frame),
            needs_analysis=not self._store.has_current_analysis(frame, self._analyzer.signature),
        )

    def _process(self, item: _FrameWork) -> _FrameResult:
        if item.needs_analysis:
            with self._lock:
                self._analyses_started_at[item.frame.main_path] = self._clock()
        return _FrameResult(
            frame=item.frame,
            thumbnail=make_thumbnail(item.source) if item.needs_thumbnail else None,
            signals=self._analyzer.analyze(item.source) if item.needs_analysis else None,
            captured_at=read_capture_time(item.source) if item.needs_analysis else None,
        )

    def _save(self, result: _FrameResult) -> None:
        if result.thumbnail is not None:
            self._store.save_thumbnail(result.frame, result.thumbnail)
        if result.signals is not None:
            self._store.save_analysis(
                result.frame, result.signals, result.captured_at, self._analyzer.signature
            )

    def _count_done(self, item: _FrameWork) -> None:
        with self._lock:
            self._frames_done += 1
            if item.needs_analysis:
                started_at = self._analyses_started_at.pop(item.frame.main_path)
                self._analysis_seconds_total += self._clock() - started_at
                self._analyses_done += 1
                self._analyses_left -= 1

    def _worker_count(self) -> int:
        cores = os.cpu_count() or 1
        return max(1, cores // BACKGROUND_CORE_DIVISOR) if self._background else cores

    def _prepare_worker(self) -> None:
        if not self._background:
            return
        if sys.platform == "darwin":
            os.setpriority(os.PRIO_DARWIN_THREAD, 0, os.PRIO_DARWIN_BG)
        elif sys.platform == "win32":
            _enter_windows_background_mode()
        elif sys.platform == "linux":
            # Linux keeps a niceness per thread, addressed by its thread id.
            os.setpriority(os.PRIO_PROCESS, threading.get_native_id(), LOWEST_PRIORITY_NICENESS)


THREAD_MODE_BACKGROUND_BEGIN = 0x00010000


def _enter_windows_background_mode() -> None:
    """Lowers this thread's CPU and I/O priority, like macOS's background thread priority."""
    import ctypes

    kernel32 = ctypes.windll.kernel32
    kernel32.GetCurrentThread.restype = ctypes.c_void_p
    kernel32.SetThreadPriority.argtypes = [ctypes.c_void_p, ctypes.c_int]
    kernel32.SetThreadPriority(kernel32.GetCurrentThread(), THREAD_MODE_BACKGROUND_BEGIN)
