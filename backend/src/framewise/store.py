import sqlite3
from pathlib import Path

from framewise.camera_rating import CameraRating
from framewise.scan import ScannedFrame

SCHEMA = """
CREATE TABLE IF NOT EXISTS frames (
    id INTEGER PRIMARY KEY,
    jpg_path TEXT NOT NULL UNIQUE,
    raw_path TEXT,
    camera_stars INTEGER,
    camera_label TEXT
);
CREATE TABLE IF NOT EXISTS thumbnails (
    jpg_path TEXT PRIMARY KEY,
    jpg_size INTEGER NOT NULL,
    jpg_mtime_ns INTEGER NOT NULL,
    image BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS skipped_files (
    path TEXT PRIMARY KEY
);
"""


class SessionStore:
    def __init__(self, database_path: Path, root: Path):
        self.root = root
        database_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(database_path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.executescript(SCHEMA)

    def save_frame(self, frame: ScannedFrame, rating: CameraRating) -> None:
        with self._db:
            self._db.execute(
                "INSERT INTO frames (jpg_path, raw_path, camera_stars, camera_label) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT (jpg_path) DO UPDATE SET raw_path = excluded.raw_path, "
                "camera_stars = excluded.camera_stars, camera_label = excluded.camera_label",
                (
                    self._relative(frame.jpg_path),
                    self._relative(frame.raw_path),
                    rating.stars,
                    rating.label,
                ),
            )

    def remove_frames_except(self, frames: list[ScannedFrame]) -> None:
        current = {self._relative(frame.jpg_path) for frame in frames}
        with self._db:
            for table in ("frames", "thumbnails"):
                stored = self._db.execute(f"SELECT jpg_path FROM {table}").fetchall()
                self._db.executemany(
                    f"DELETE FROM {table} WHERE jpg_path = ?",
                    [(row["jpg_path"],) for row in stored if row["jpg_path"] not in current],
                )

    def has_current_thumbnail(self, jpg_path: Path) -> bool:
        stat = jpg_path.stat()
        row = self._db.execute(
            "SELECT 1 FROM thumbnails WHERE jpg_path = ? AND jpg_size = ? AND jpg_mtime_ns = ?",
            (self._relative(jpg_path), stat.st_size, stat.st_mtime_ns),
        ).fetchone()
        return row is not None

    def save_thumbnail(self, jpg_path: Path, image: bytes) -> None:
        stat = jpg_path.stat()
        with self._db:
            self._db.execute(
                "INSERT OR REPLACE INTO thumbnails (jpg_path, jpg_size, jpg_mtime_ns, image) "
                "VALUES (?, ?, ?, ?)",
                (self._relative(jpg_path), stat.st_size, stat.st_mtime_ns, image),
            )

    def save_skipped_files(self, paths: list[Path]) -> None:
        with self._db:
            self._db.execute("DELETE FROM skipped_files")
            self._db.executemany(
                "INSERT INTO skipped_files (path) VALUES (?)",
                [(self._relative(path),) for path in paths],
            )

    def frames(self) -> list[sqlite3.Row]:
        return self._db.execute("SELECT * FROM frames ORDER BY jpg_path").fetchall()

    def thumbnail(self, frame_id: int) -> bytes | None:
        row = self._db.execute(
            "SELECT thumbnails.image FROM frames "
            "JOIN thumbnails ON thumbnails.jpg_path = frames.jpg_path WHERE frames.id = ?",
            (frame_id,),
        ).fetchone()
        return None if row is None else row["image"]

    def skipped_files(self) -> list[str]:
        rows = self._db.execute("SELECT path FROM skipped_files ORDER BY path")
        return [row["path"] for row in rows]

    def _relative(self, path: Path | None) -> str | None:
        return None if path is None else path.relative_to(self.root).as_posix()
