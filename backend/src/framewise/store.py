import json
import sqlite3
from array import array
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from framewise.analyzer import ANALYSIS_VERSION, Face, FrameSignals
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
CREATE TABLE IF NOT EXISTS analyses (
    jpg_path TEXT PRIMARY KEY,
    jpg_size INTEGER NOT NULL,
    jpg_mtime_ns INTEGER NOT NULL,
    fingerprint BLOB NOT NULL,
    captured_at TEXT,
    version INTEGER,
    signals TEXT
);
CREATE TABLE IF NOT EXISTS skipped_files (
    path TEXT PRIMARY KEY
);
CREATE TABLE IF NOT EXISTS overrides (
    jpg_path TEXT PRIMARY KEY,
    verdict TEXT,
    stars INTEGER,
    label TEXT
);
"""

# Columns added to tables after the first release. Adding them to an existing Session store keeps
# its rows; analyses saved before then have no version, so they no longer count as current.
ADDED_COLUMNS = {"analyses": {"version": "INTEGER", "signals": "TEXT"}}

FrameKind = Literal["jpg-only", "raw+jpg"]


@dataclass(frozen=True)
class Frame:
    id: int
    jpg_path: str
    raw_path: str | None
    camera_rating: CameraRating

    @property
    def kind(self) -> FrameKind:
        return "jpg-only" if self.raw_path is None else "raw+jpg"


@dataclass(frozen=True)
class Override:
    """The photographer's Override of one Frame. A field left None keeps framewise's judgement.

    Keyed by the Frame's JPG path, so it survives re-analysis and Groups being recomputed."""

    verdict: str | None = None
    stars: int | None = None
    label: str | None = None

    @property
    def is_empty(self) -> bool:
        return self == Override()


@dataclass(frozen=True)
class AnalyzedFrame:
    frame: Frame
    signals: FrameSignals
    captured_at: datetime | None


@dataclass(frozen=True)
class SessionSummary:
    total_frames: int
    jpg_only_count: int
    raw_jpg_count: int
    skipped: list[str]


class SessionStore:
    def __init__(self, database_path: Path, root: Path):
        self.root = root
        database_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(database_path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.executescript(SCHEMA)
        self._add_missing_columns()

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
        current = json.dumps([self._relative(frame.jpg_path) for frame in frames])
        with self._db:
            self._db.execute(
                "DELETE FROM frames WHERE jpg_path NOT IN (SELECT value FROM json_each(?))",
                (current,),
            )
            for table in ("thumbnails", "analyses"):
                self._db.execute(
                    f"DELETE FROM {table} WHERE jpg_path NOT IN (SELECT value FROM json_each(?))",
                    (current,),
                )

    def has_current_thumbnail(self, jpg_path: Path) -> bool:
        return self._has_current_row("thumbnails", jpg_path)

    def has_current_analysis(self, jpg_path: Path) -> bool:
        row = self._db.execute(
            "SELECT 1 FROM analyses "
            "WHERE jpg_path = ? AND jpg_size = ? AND jpg_mtime_ns = ? AND version = ?",
            (*self._file_key(jpg_path), ANALYSIS_VERSION),
        ).fetchone()
        return row is not None

    def save_analysis(
        self, jpg_path: Path, signals: FrameSignals, captured_at: datetime | None
    ) -> None:
        with self._db:
            self._db.execute(
                "INSERT OR REPLACE INTO analyses "
                "(jpg_path, jpg_size, jpg_mtime_ns, fingerprint, captured_at, version, signals) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    *self._file_key(jpg_path),
                    array("f", signals.fingerprint).tobytes(),
                    None if captured_at is None else captured_at.isoformat(),
                    ANALYSIS_VERSION,
                    json.dumps(_signals_without_fingerprint(signals)),
                ),
            )

    def save_thumbnail(self, jpg_path: Path, image: bytes) -> None:
        with self._db:
            self._db.execute(
                "INSERT OR REPLACE INTO thumbnails (jpg_path, jpg_size, jpg_mtime_ns, image) "
                "VALUES (?, ?, ?, ?)",
                (*self._file_key(jpg_path), image),
            )

    def save_skipped_files(self, paths: list[Path]) -> None:
        with self._db:
            self._db.execute("DELETE FROM skipped_files")
            self._db.executemany(
                "INSERT INTO skipped_files (path) VALUES (?)",
                [(self._relative(path),) for path in paths],
            )

    def save_override(self, jpg_path: str, override: Override) -> None:
        with self._db:
            if override.is_empty:
                self._db.execute("DELETE FROM overrides WHERE jpg_path = ?", (jpg_path,))
                return
            self._db.execute(
                "INSERT OR REPLACE INTO overrides (jpg_path, verdict, stars, label) "
                "VALUES (?, ?, ?, ?)",
                (jpg_path, override.verdict, override.stars, override.label),
            )

    def overrides(self) -> dict[str, Override]:
        rows = self._db.execute("SELECT * FROM overrides")
        return {
            row["jpg_path"]: Override(row["verdict"], row["stars"], row["label"]) for row in rows
        }

    def frame(self, frame_id: int) -> Frame | None:
        row = self._db.execute("SELECT * FROM frames WHERE id = ?", (frame_id,)).fetchone()
        return None if row is None else _frame(row)

    def frames(self) -> list[Frame]:
        rows = self._db.execute("SELECT * FROM frames ORDER BY jpg_path")
        return [_frame(row) for row in rows]

    def analyzed_frames(self) -> list[AnalyzedFrame]:
        rows = self._db.execute(
            "SELECT frames.*, analyses.fingerprint, analyses.signals, analyses.captured_at "
            "FROM frames JOIN analyses ON analyses.jpg_path = frames.jpg_path "
            "WHERE analyses.version = ? ORDER BY frames.jpg_path",
            (ANALYSIS_VERSION,),
        )
        return [
            AnalyzedFrame(
                frame=_frame(row),
                signals=_signals(row),
                captured_at=(
                    None
                    if row["captured_at"] is None
                    else datetime.fromisoformat(row["captured_at"])
                ),
            )
            for row in rows
        ]

    def summary(self) -> SessionSummary:
        frames = self.frames()
        raw_jpg_count = sum(1 for frame in frames if frame.kind == "raw+jpg")
        return SessionSummary(
            total_frames=len(frames),
            jpg_only_count=len(frames) - raw_jpg_count,
            raw_jpg_count=raw_jpg_count,
            skipped=self.skipped_files(),
        )

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

    def _add_missing_columns(self) -> None:
        for table, columns in ADDED_COLUMNS.items():
            existing = {row["name"] for row in self._db.execute(f"PRAGMA table_info({table})")}
            with self._db:
                for name, column_type in columns.items():
                    if name not in existing:
                        self._db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {column_type}")

    def _has_current_row(self, table: str, jpg_path: Path) -> bool:
        row = self._db.execute(
            f"SELECT 1 FROM {table} WHERE jpg_path = ? AND jpg_size = ? AND jpg_mtime_ns = ?",
            self._file_key(jpg_path),
        ).fetchone()
        return row is not None

    def _file_key(self, jpg_path: Path) -> tuple[str, int, int]:
        stat = jpg_path.stat()
        return self._relative(jpg_path), stat.st_size, stat.st_mtime_ns

    def _relative(self, path: Path | None) -> str | None:
        return None if path is None else path.relative_to(self.root).as_posix()


def _signals_without_fingerprint(signals: FrameSignals) -> dict:
    values = asdict(signals)
    del values["fingerprint"]
    return values


def _signals(row: sqlite3.Row) -> FrameSignals:
    values = json.loads(row["signals"])
    faces = [Face(**face) for face in values.pop("faces")]
    return FrameSignals(fingerprint=array("f", row["fingerprint"]).tolist(), faces=faces, **values)


def _frame(row: sqlite3.Row) -> Frame:
    return Frame(
        id=row["id"],
        jpg_path=row["jpg_path"],
        raw_path=row["raw_path"],
        camera_rating=CameraRating(stars=row["camera_stars"], label=row["camera_label"]),
    )
