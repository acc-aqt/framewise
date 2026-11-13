import hashlib
import os
from pathlib import Path

from framewise.analyzer import FrameAnalyzer
from framewise.camera_rating import read_camera_rating
from framewise.capture_time import read_capture_time
from framewise.scan import scan_session
from framewise.store import SessionStore
from framewise.thumbnails import make_thumbnail

DEFAULT_DATA_DIR = Path.home() / "Library" / "Application Support" / "framewise"


def resolve_data_dir() -> Path:
    return Path(os.environ.get("FRAMEWISE_DATA_DIR", DEFAULT_DATA_DIR))


def session_database_path(root: Path, data_dir: Path) -> Path:
    digest = hashlib.sha256(str(root).encode()).hexdigest()[:16]
    return data_dir / f"{root.name}-{digest}.sqlite"


def open_session(folder: Path, data_dir: Path, analyzer: FrameAnalyzer) -> SessionStore:
    root = folder.resolve()
    store = SessionStore(session_database_path(root, data_dir), root)
    scan = scan_session(root)
    store.remove_frames_except(scan.frames)
    for frame in scan.frames:
        store.save_frame(frame, read_camera_rating(frame.jpg_path, frame.raw_path))
        if not store.has_current_thumbnail(frame.jpg_path):
            store.save_thumbnail(frame.jpg_path, make_thumbnail(frame.jpg_path))
        if not store.has_current_analysis(frame.jpg_path):
            store.save_analysis(
                frame.jpg_path, analyzer.analyze(frame.jpg_path), read_capture_time(frame.jpg_path)
            )
    store.save_skipped_files(scan.skipped)
    return store
