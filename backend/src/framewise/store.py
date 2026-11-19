import hashlib
import json
import sqlite3
import threading
import uuid
from array import array
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from framewise.analyzer import ANALYSIS_VERSION, Face, FrameSignals, ProviderSignature, Subject
from framewise.camera_rating import CameraRating
from framewise.scan import ScannedFrame

SCHEMA = """
CREATE TABLE IF NOT EXISTS frames (
    id INTEGER PRIMARY KEY,
    main_path TEXT NOT NULL UNIQUE,
    raw_path TEXT,
    camera_stars INTEGER,
    camera_label TEXT,
    jpg_path TEXT
);
CREATE TABLE IF NOT EXISTS thumbnails (
    main_path TEXT PRIMARY KEY,
    source_size INTEGER NOT NULL,
    source_mtime_ns INTEGER NOT NULL,
    image BLOB NOT NULL,
    source_path TEXT
);
CREATE TABLE IF NOT EXISTS analyses (
    main_path TEXT PRIMARY KEY,
    source_size INTEGER NOT NULL,
    source_mtime_ns INTEGER NOT NULL,
    fingerprint BLOB NOT NULL,
    captured_at TEXT,
    version INTEGER,
    signals TEXT,
    providers TEXT,
    source_path TEXT
);
CREATE TABLE IF NOT EXISTS skipped_files (
    path TEXT PRIMARY KEY,
    reason TEXT
);
CREATE TABLE IF NOT EXISTS previews (
    main_path TEXT PRIMARY KEY,
    source_path TEXT NOT NULL,
    source_size INTEGER NOT NULL,
    source_mtime_ns INTEGER NOT NULL,
    width INTEGER NOT NULL,
    height INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS group_overrides (
    main_path TEXT PRIMARY KEY,
    group_key TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS overrides (
    main_path TEXT PRIMARY KEY,
    verdict TEXT,
    stars INTEGER,
    label TEXT
);
CREATE TABLE IF NOT EXISTS write_back_originals (
    path TEXT PRIMARY KEY,
    stars INTEGER,
    label TEXT,
    created INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
    name TEXT PRIMARY KEY,
    value
);
"""

# Columns added to tables after the first release. Adding them to an existing Session store keeps
# its rows; analyses saved before then have no version or Providers, so they no longer count as
# current.
ADDED_COLUMNS = {
    "analyses": {"version": "INTEGER", "signals": "TEXT", "providers": "TEXT"},
    "skipped_files": {"reason": "TEXT"},
}

SCHEMA_VERSION = 1
"""Bumped whenever an upgrade must change a Session store's existing tables, not just add to them.
Stores up to framewise 0.2.0 are version 0."""

# Version 1 identifies a Frame by its main file rather than its JPG, and calls the file a
# thumbnail or analysis was made from its Analysis source.
RENAMED_COLUMNS = {
    "frames": {"jpg_path": "main_path"},
    "thumbnails": {
        "jpg_path": "main_path",
        "jpg_size": "source_size",
        "jpg_mtime_ns": "source_mtime_ns",
    },
    "analyses": {
        "jpg_path": "main_path",
        "jpg_size": "source_size",
        "jpg_mtime_ns": "source_mtime_ns",
    },
    "group_overrides": {"jpg_path": "main_path"},
    "overrides": {"jpg_path": "main_path"},
}
# The file columns version 1 adds, each filled from the main file: up to version 0 a Frame's main
# file was always its JPG, and so was the Analysis source of its thumbnail and analysis.
FILLED_COLUMNS = {
    "frames": "jpg_path",
    "thumbnails": "source_path",
    "analyses": "source_path",
}

FrameKind = Literal["jpg-only", "raw+jpg", "raw-only"]
FRAME_TABLES = ("frames", "thumbnails", "analyses", "previews")
"""The tables holding a Frame's own rows, which go when it leaves the Session."""


@dataclass(frozen=True)
class Frame:
    id: int
    main_path: str
    """The file that identifies the Frame, relative to the Session folder. Its Overrides, fixed
    Group, thumbnail and analysis are keyed by it. It is the JPG of a JPG-only or RAW+JPG
    Frame, and the RAW of a RAW-only Frame."""
    jpg_path: str | None
    raw_path: str | None
    camera_rating: CameraRating

    @property
    def kind(self) -> FrameKind:
        if self.jpg_path is None:
            return "raw-only"
        return "jpg-only" if self.raw_path is None else "raw+jpg"

    @property
    def analysis_source(self) -> str:
        """The file holding the pixels the Frame is judged by: its JPG, or the RAW whose embedded
        preview a RAW-only Frame is judged by. Thumbnails and analyses are current while this file
        is unchanged."""
        return self.jpg_path or self.raw_path


@dataclass(frozen=True)
class Override:
    """The photographer's Override of one Frame. A field left None keeps framewise's judgment.

    Keyed by the Frame's main file, so it survives re-analysis and Groups being recomputed."""

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
class WrittenFileOriginal:
    """A file's rating and label before Rating write-back first changed it. `created` means
    write-back created the file, a sidecar, so undo removes it."""

    path: str
    stars: int | None
    label: str | None
    created: bool


@dataclass(frozen=True)
class SkippedFile:
    path: str
    """Relative to the Session folder."""
    reason: str
    """Why framewise skipped the file."""


@dataclass(frozen=True)
class SessionSummary:
    total_frames: int
    jpg_only_count: int
    raw_jpg_count: int
    raw_only_count: int
    skipped: list[SkippedFile]


def preview_cache_dir(database_path: Path) -> Path:
    """The folder next to a Session store that holds its RAW-only Frames' embedded previews."""
    return database_path.with_name(f"{database_path.stem}-previews")


BUSY_TIMEOUT_SECONDS = 30


class SessionStore:
    def __init__(self, database_path: Path, root: Path):
        self.root = root
        database_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self._database_path = database_path
        self.preview_dir = preview_cache_dir(database_path)
        self._connections = threading.local()
        self._db.execute("PRAGMA journal_mode=WAL")
        self._upgrade()
        self._db.executescript(SCHEMA)
        self._add_missing_columns()

    @property
    def _db(self) -> sqlite3.Connection:
        """This thread's connection. The analysis thread saves Frames while the server's threads
        read them, and a sqlite3 connection must not be used by two threads at once."""
        connection = getattr(self._connections, "connection", None)
        if connection is None:
            connection = sqlite3.connect(self._database_path, timeout=BUSY_TIMEOUT_SECONDS)
            connection.row_factory = sqlite3.Row
            self._connections.connection = connection
        return connection

    def close(self) -> None:
        """Closes this thread's connection."""
        connection = getattr(self._connections, "connection", None)
        if connection is not None:
            connection.close()
            self._connections.connection = None

    def save_frame(self, frame: ScannedFrame, rating: CameraRating) -> None:
        with self._db:
            self._db.execute(
                "INSERT INTO frames (main_path, jpg_path, raw_path, camera_stars, camera_label) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT (main_path) DO UPDATE SET jpg_path = excluded.jpg_path, "
                "raw_path = excluded.raw_path, camera_stars = excluded.camera_stars, "
                "camera_label = excluded.camera_label",
                (
                    self._relative(frame.main_path),
                    self._relative(frame.jpg_path),
                    self._relative(frame.raw_path),
                    rating.stars,
                    rating.label,
                ),
            )

    def remove_frames_except(self, frames: list[ScannedFrame]) -> None:
        current = json.dumps([self._relative(frame.main_path) for frame in frames])
        self._remove_frames_where("NOT IN", current)

    def remove_frames(self, main_paths: list[str]) -> None:
        """Takes these Frames out of the Session, keeping their Overrides and Group Overrides
        as for Frames that vanish from the Session folder."""
        self._remove_frames_where("IN", json.dumps(main_paths))

    def _remove_frames_where(self, operator: str, paths: str) -> None:
        condition = f"main_path {operator} (SELECT value FROM json_each(?))"
        previews = self._db.execute(f"SELECT main_path FROM previews WHERE {condition}", (paths,))
        for row in previews.fetchall():
            self.preview_file(row["main_path"]).unlink(missing_ok=True)
        with self._db:
            for table in FRAME_TABLES:
                self._db.execute(f"DELETE FROM {table} WHERE {condition}", (paths,))

    def has_current_preview(self, frame: ScannedFrame) -> bool:
        """Whether the RAW-only Frame's cached preview was extracted from its RAW as it is now."""
        main_path = self._relative(frame.main_path)
        if not self.preview_file(main_path).is_file():
            return False
        row = self._db.execute(
            "SELECT 1 FROM previews WHERE main_path = ? AND source_path = ? AND source_size = ? "
            "AND source_mtime_ns = ?",
            (main_path, *self._file_key(frame.raw_path)),
        ).fetchone()
        return row is not None

    def new_preview_file(self, frame: ScannedFrame) -> Path:
        """Where to extract the RAW-only Frame's preview to, in the preview cache."""
        self.preview_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        return self.preview_file(self._relative(frame.main_path))

    def save_preview(self, frame: ScannedFrame, width: int, height: int) -> None:
        with self._db:
            self._db.execute(
                "INSERT OR REPLACE INTO previews (main_path, source_path, source_size, "
                "source_mtime_ns, width, height) VALUES (?, ?, ?, ?, ?, ?)",
                (self._relative(frame.main_path), *self._file_key(frame.raw_path), width, height),
            )

    def preview_file(self, main_path: str) -> Path:
        """The cached preview of the RAW-only Frame with this main file."""
        digest = hashlib.sha256(main_path.encode()).hexdigest()[:32]
        return self.preview_dir / f"{digest}.jpg"

    def analysis_image(self, frame: Frame) -> Path:
        """The JPG the Frame's Analysis source is read from: its JPG, or a RAW-only Frame's cached
        preview."""
        if frame.jpg_path is None:
            return self.preview_file(frame.main_path)
        return self.root / frame.jpg_path

    def has_current_thumbnail(self, frame: Frame) -> bool:
        return self._has_current_row("thumbnails", frame)

    def has_current_analysis(self, frame: Frame, signature: ProviderSignature) -> bool:
        """Whether the Frame's saved analysis is of its Analysis source's current contents, made
        by the given Providers."""
        row = self._db.execute(
            "SELECT 1 FROM analyses WHERE main_path = ? AND source_path = ? AND source_size = ? "
            "AND source_mtime_ns = ? AND version = ? AND providers = ?",
            (*self._source_key(frame), ANALYSIS_VERSION, _signature_text(signature)),
        ).fetchone()
        return row is not None

    def save_analysis(
        self,
        frame: Frame,
        signals: FrameSignals,
        captured_at: datetime | None,
        signature: ProviderSignature,
    ) -> None:
        with self._db:
            self._db.execute(
                "INSERT OR REPLACE INTO analyses (main_path, source_path, source_size, "
                "source_mtime_ns, fingerprint, captured_at, version, signals, providers) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    *self._source_key(frame),
                    array("f", signals.fingerprint).tobytes(),
                    None if captured_at is None else captured_at.isoformat(),
                    ANALYSIS_VERSION,
                    json.dumps(_signals_without_fingerprint(signals)),
                    _signature_text(signature),
                ),
            )

    def save_thumbnail(self, frame: Frame, image: bytes) -> None:
        with self._db:
            self._db.execute(
                "INSERT OR REPLACE INTO thumbnails (main_path, source_path, source_size, "
                "source_mtime_ns, image) VALUES (?, ?, ?, ?, ?)",
                (*self._source_key(frame), image),
            )

    def save_skipped_files(self, reasons: dict[Path, str]) -> None:
        """Replaces the skipped files with these, each with the reason it was skipped."""
        with self._db:
            self._db.execute("DELETE FROM skipped_files")
            self._db.executemany(
                "INSERT INTO skipped_files (path, reason) VALUES (?, ?)",
                [(self._relative(path), reason) for path, reason in reasons.items()],
            )

    def save_override(self, main_path: str, override: Override) -> None:
        with self._db:
            if override.is_empty:
                self._db.execute("DELETE FROM overrides WHERE main_path = ?", (main_path,))
                return
            self._db.execute(
                "INSERT OR REPLACE INTO overrides (main_path, verdict, stars, label) "
                "VALUES (?, ?, ?, ?)",
                (main_path, override.verdict, override.stars, override.label),
            )

    def overrides(self) -> dict[str, Override]:
        """The photographer's Overrides, by the main file of their Frame."""
        rows = self._db.execute("SELECT * FROM overrides")
        return {
            row["main_path"]: Override(row["verdict"], row["stars"], row["label"]) for row in rows
        }

    def save_group_overrides(self, groups: list[list[str]]) -> None:
        """Fixes each list of Frames, given by their main files, as one Group, taking its Frames
        out of any Group they were fixed in before."""
        with self._db:
            for group in groups:
                key = uuid.uuid4().hex
                self._db.executemany(
                    "INSERT OR REPLACE INTO group_overrides (main_path, group_key) VALUES (?, ?)",
                    [(main_path, key) for main_path in group],
                )

    def group_overrides(self) -> dict[str, str]:
        """The Group key of each Frame in a Group the photographer fixed, by its main file."""
        rows = self._db.execute("SELECT main_path, group_key FROM group_overrides")
        return {row["main_path"]: row["group_key"] for row in rows}

    def clear_group_overrides(self, main_paths: list[str]) -> None:
        """Hands the fixed Groups of these Frames back to automatic grouping, including Frames
        of those Groups that are missing from the Session folder."""
        with self._db:
            self._db.execute(
                "DELETE FROM group_overrides WHERE group_key IN "
                "(SELECT group_key FROM group_overrides "
                "WHERE main_path IN (SELECT value FROM json_each(?)))",
                (json.dumps(main_paths),),
            )

    def save_keeper_budget(self, share: float) -> None:
        with self._db:
            self._db.execute(
                "INSERT OR REPLACE INTO settings (name, value) VALUES ('keeper_budget', ?)",
                (share,),
            )

    def keeper_budget(self) -> float | None:
        row = self._db.execute("SELECT value FROM settings WHERE name = 'keeper_budget'").fetchone()
        return None if row is None else row["value"]

    def clear_review(self) -> None:
        """Forgets the photographer's Overrides, fixed Groups and Session settings, keeping the
        analysis and the write-back originals."""
        with self._db:
            for table in ("overrides", "group_overrides", "settings"):
                self._db.execute(f"DELETE FROM {table}")

    def frame(self, frame_id: int) -> Frame | None:
        row = self._db.execute("SELECT * FROM frames WHERE id = ?", (frame_id,)).fetchone()
        return None if row is None else _frame(row)

    def keep_current_after_metadata_write(self, path: Path, size: int, mtime_ns: int) -> None:
        """Moves the thumbnails and analyses made from a file, if they were current at the given
        size and modification time, to its new size and modification time, because writing
        metadata leaves the image data that they were made from unchanged."""
        relative, new_size, new_mtime_ns = self._file_key(path)
        with self._db:
            for table in ("thumbnails", "analyses", "previews"):
                self._db.execute(
                    f"UPDATE {table} SET source_size = ?, source_mtime_ns = ? "
                    "WHERE source_path = ? AND source_size = ? AND source_mtime_ns = ?",
                    (new_size, new_mtime_ns, relative, size, mtime_ns),
                )

    def record_write_back_original(self, original: WrittenFileOriginal) -> bool:
        """Records a file's original rating and label, unless an earlier write-back already
        recorded them. Returns whether it recorded them."""
        with self._db:
            cursor = self._db.execute(
                "INSERT OR IGNORE INTO write_back_originals (path, stars, label, created) "
                "VALUES (?, ?, ?, ?)",
                (original.path, original.stars, original.label, original.created),
            )
        return cursor.rowcount == 1

    def write_back_originals(self) -> list[WrittenFileOriginal]:
        rows = self._db.execute("SELECT * FROM write_back_originals ORDER BY path")
        return [
            WrittenFileOriginal(
                path=row["path"],
                stars=row["stars"],
                label=row["label"],
                created=bool(row["created"]),
            )
            for row in rows
        ]

    def forget_write_back_original(self, path: str) -> None:
        with self._db:
            self._db.execute("DELETE FROM write_back_originals WHERE path = ?", (path,))

    def frames(self) -> list[Frame]:
        rows = self._db.execute("SELECT * FROM frames ORDER BY main_path")
        return [_frame(row) for row in rows]

    def analyzed_frames(self, signature: ProviderSignature) -> list[AnalyzedFrame]:
        """The Frames whose saved analysis the given Providers made. Fingerprints from different
        Providers can't be compared, so Frames waiting for re-analysis are left out."""
        rows = self._db.execute(
            "SELECT frames.*, analyses.fingerprint, analyses.signals, analyses.captured_at "
            "FROM frames JOIN analyses ON analyses.main_path = frames.main_path "
            "WHERE analyses.version = ? AND analyses.providers = ? ORDER BY frames.main_path",
            (ANALYSIS_VERSION, _signature_text(signature)),
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
        kinds = [frame.kind for frame in self.frames()]
        return SessionSummary(
            total_frames=len(kinds),
            jpg_only_count=kinds.count("jpg-only"),
            raw_jpg_count=kinds.count("raw+jpg"),
            raw_only_count=kinds.count("raw-only"),
            skipped=self.skipped_files(),
        )

    def thumbnail(self, frame_id: int) -> bytes | None:
        row = self._db.execute(
            "SELECT thumbnails.image FROM frames "
            "JOIN thumbnails ON thumbnails.main_path = frames.main_path WHERE frames.id = ?",
            (frame_id,),
        ).fetchone()
        return None if row is None else row["image"]

    def skipped_files(self) -> list[SkippedFile]:
        rows = self._db.execute("SELECT path, reason FROM skipped_files ORDER BY path")
        return [SkippedFile(row["path"], row["reason"]) for row in rows]

    def _upgrade(self) -> None:
        """Brings a Session store from an earlier release up to SCHEMA_VERSION, after copying it
        to a backup next to it. The upgrade runs in one transaction, so if it fails the store is
        left as it was. A new store only gets the version."""
        version = self._db.execute("PRAGMA user_version").fetchone()[0]
        if version >= SCHEMA_VERSION:
            return
        tables = self._tables()
        if tables:
            self._back_up(version)
        self._db.execute("BEGIN")
        with self._db:
            for table, columns in RENAMED_COLUMNS.items():
                if table in tables:
                    for old, new in columns.items():
                        self._db.execute(f"ALTER TABLE {table} RENAME COLUMN {old} TO {new}")
            for table, column in FILLED_COLUMNS.items():
                if table in tables:
                    self._db.execute(f"ALTER TABLE {table} ADD COLUMN {column} TEXT")
                    self._db.execute(f"UPDATE {table} SET {column} = main_path")
            self._db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    def _tables(self) -> set[str]:
        rows = self._db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        return {row["name"] for row in rows}

    def _back_up(self, version: int) -> None:
        database = self._database_path
        backup = sqlite3.connect(
            database.with_name(f"{database.stem}-v{version}-backup{database.suffix}")
        )
        try:
            self._db.backup(backup)
        finally:
            backup.close()

    def _add_missing_columns(self) -> None:
        for table, columns in ADDED_COLUMNS.items():
            existing = {row["name"] for row in self._db.execute(f"PRAGMA table_info({table})")}
            with self._db:
                for name, column_type in columns.items():
                    if name not in existing:
                        self._db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {column_type}")

    def _has_current_row(self, table: str, frame: Frame) -> bool:
        row = self._db.execute(
            f"SELECT 1 FROM {table} WHERE main_path = ? AND source_path = ? AND source_size = ? "
            "AND source_mtime_ns = ?",
            self._source_key(frame),
        ).fetchone()
        return row is not None

    def _source_key(self, frame: Frame) -> tuple[str, str, int, int]:
        """The Frame's main file, then its Analysis source with that file's current size and
        modification time."""
        return frame.main_path, *self._file_key(self.root / frame.analysis_source)

    def _file_key(self, path: Path) -> tuple[str, int, int]:
        stat = path.stat()
        return self._relative(path), stat.st_size, stat.st_mtime_ns

    def _relative(self, path: Path | None) -> str | None:
        return None if path is None else path.relative_to(self.root).as_posix()


def _signature_text(signature: ProviderSignature) -> str:
    return json.dumps(dict(signature), sort_keys=True)


def _signals_without_fingerprint(signals: FrameSignals) -> dict:
    values = asdict(signals)
    del values["fingerprint"]
    return values


def _signals(row: sqlite3.Row) -> FrameSignals:
    values = json.loads(row["signals"])
    faces = [Face(**face) for face in values.pop("faces")]
    subject = values.pop("subject")
    return FrameSignals(
        fingerprint=array("f", row["fingerprint"]).tolist(),
        faces=faces,
        subject=None if subject is None else Subject(**subject),
        **values,
    )


def _frame(row: sqlite3.Row) -> Frame:
    return Frame(
        id=row["id"],
        main_path=row["main_path"],
        jpg_path=row["jpg_path"],
        raw_path=row["raw_path"],
        camera_rating=CameraRating(stars=row["camera_stars"], label=row["camera_label"]),
    )
