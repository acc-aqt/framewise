import json
import sqlite3
from array import array
from dataclasses import asdict

import pytest
from conftest import clean_signals, make_jpg, make_raw

from framewise import store as session_store
from framewise.analyzer import ANALYSIS_VERSION
from framewise.review import session_database_path

# The Session store's tables as framewise 0.2.0 created them, when a Frame was identified by its
# JPG.
SCHEMA_0_2_0 = """
CREATE TABLE frames (
    id INTEGER PRIMARY KEY,
    jpg_path TEXT NOT NULL UNIQUE,
    raw_path TEXT,
    camera_stars INTEGER,
    camera_label TEXT
);
CREATE TABLE thumbnails (
    jpg_path TEXT PRIMARY KEY,
    jpg_size INTEGER NOT NULL,
    jpg_mtime_ns INTEGER NOT NULL,
    image BLOB NOT NULL
);
CREATE TABLE analyses (
    jpg_path TEXT PRIMARY KEY,
    jpg_size INTEGER NOT NULL,
    jpg_mtime_ns INTEGER NOT NULL,
    fingerprint BLOB NOT NULL,
    captured_at TEXT,
    version INTEGER,
    signals TEXT,
    providers TEXT
);
CREATE TABLE skipped_files (
    path TEXT PRIMARY KEY
);
CREATE TABLE group_overrides (
    jpg_path TEXT PRIMARY KEY,
    group_key TEXT NOT NULL
);
CREATE TABLE overrides (
    jpg_path TEXT PRIMARY KEY,
    verdict TEXT,
    stars INTEGER,
    label TEXT
);
CREATE TABLE write_back_originals (
    path TEXT PRIMARY KEY,
    stars INTEGER,
    label TEXT,
    created INTEGER NOT NULL
);
CREATE TABLE settings (
    name TEXT PRIMARY KEY,
    value
);
"""

FINGERPRINTS = {
    "DSCF0001.JPG": [1.0, 0.0, 0.0],
    "DSCF0002.JPG": [0.0, 1.0, 0.0],
    "DSCF0003.JPG": [0.0, 0.0, 1.0],
}


def make_store_from_0_2_0(session_dir, data_dir, analyzer):
    """A reviewed Session as framewise 0.2.0 saved it: analyzed, with DSCF0001 and DSCF0002 fixed
    as one Group, DSCF0003 overridden to a Reject with 2 stars, a raised Keeper budget, and
    DSCF0002's rating written back."""
    make_jpg(session_dir / "DSCF0001.JPG")
    make_raw(session_dir / "DSCF0001.RAF")
    make_jpg(session_dir / "DSCF0002.JPG")
    make_jpg(session_dir / "DSCF0003.JPG")
    data_dir.mkdir(parents=True)
    database_path = session_database_path(session_dir.resolve(), data_dir)
    database = sqlite3.connect(database_path)
    with database:
        database.executescript(SCHEMA_0_2_0)
        database.executemany(
            "INSERT INTO frames VALUES (?, ?, ?, ?, ?)",
            [
                (1, "DSCF0001.JPG", "DSCF0001.RAF", None, None),
                (2, "DSCF0002.JPG", None, None, None),
                (3, "DSCF0003.JPG", None, None, None),
            ],
        )
        for name, fingerprint in FINGERPRINTS.items():
            stat = (session_dir / name).stat()
            signals = asdict(clean_signals(fingerprint))
            del signals["fingerprint"]
            database.execute(
                "INSERT INTO thumbnails VALUES (?, ?, ?, ?)",
                (name, stat.st_size, stat.st_mtime_ns, f"thumbnail of {name}".encode()),
            )
            database.execute(
                "INSERT INTO analyses VALUES (?, ?, ?, ?, NULL, ?, ?, ?)",
                (
                    name,
                    stat.st_size,
                    stat.st_mtime_ns,
                    array("f", fingerprint).tobytes(),
                    ANALYSIS_VERSION,
                    json.dumps(signals),
                    json.dumps(dict(analyzer.signature), sort_keys=True),
                ),
            )
        database.executemany(
            "INSERT INTO group_overrides VALUES (?, ?)",
            [("DSCF0001.JPG", "beach"), ("DSCF0002.JPG", "beach")],
        )
        database.execute("INSERT INTO overrides VALUES ('DSCF0003.JPG', 'reject', 2, NULL)")
        database.execute("INSERT INTO settings VALUES ('keeper_budget', 1.0)")
        database.execute("INSERT INTO write_back_originals VALUES ('DSCF0002.JPG', NULL, NULL, 0)")
    database.close()
    return database_path


def frames_by_name(client) -> dict[str, dict]:
    return {
        frame["main_path"]: frame
        for group in client.get("/api/groups").json()
        for frame in group["frames"]
    }


def test_a_store_from_0_2_0_keeps_its_review_without_re_analysis(
    session_dir, data_dir, analyzer, review
):
    make_store_from_0_2_0(session_dir, data_dir, analyzer)

    client = review()

    assert analyzer.analyzed == []
    groups = client.get("/api/groups").json()
    assert sorted(
        ([frame["main_path"] for frame in group["frames"]], group["fixed"]) for group in groups
    ) == [(["DSCF0001.JPG", "DSCF0002.JPG"], True), (["DSCF0003.JPG"], False)]
    frames = frames_by_name(client)
    assert (frames["DSCF0001.JPG"]["kind"], frames["DSCF0001.JPG"]["raw_path"]) == (
        "raw+jpg",
        "DSCF0001.RAF",
    )
    assert (frames["DSCF0002.JPG"]["verdict"], frames["DSCF0002.JPG"]["verdict_overridden"]) == (
        "keeper",
        False,
    )
    assert frames["DSCF0003.JPG"]["verdict_overridden"] is True
    assert frames["DSCF0003.JPG"]["override"] == {"verdict": "reject", "stars": 2, "label": None}
    assert client.get("/api/session").json()["keeper_budget"] == 1.0
    thumbnail = client.get(f"/api/frames/{frames['DSCF0002.JPG']['id']}/thumbnail")
    assert thumbnail.content == b"thumbnail of DSCF0002.JPG"
    assert client.get("/api/write-back").json()["can_undo"] is True


def test_a_store_from_0_2_0_is_backed_up_before_it_is_upgraded(
    session_dir, data_dir, analyzer, review
):
    make_store_from_0_2_0(session_dir, data_dir, analyzer)

    review()

    [backup] = data_dir.glob("*backup*")
    with sqlite3.connect(backup) as database:
        rows = database.execute("SELECT jpg_path, verdict FROM overrides").fetchall()
    assert rows == [("DSCF0003.JPG", "reject")]


def test_an_upgraded_store_is_not_backed_up_again(session_dir, data_dir, analyzer, review):
    make_store_from_0_2_0(session_dir, data_dir, analyzer)
    review()
    [backup] = data_dir.glob("*backup*")
    backup.unlink()

    review()

    assert list(data_dir.glob("*backup*")) == []


def test_a_failed_upgrade_leaves_the_store_untouched(
    session_dir, data_dir, analyzer, review, monkeypatch
):
    database_path = make_store_from_0_2_0(session_dir, data_dir, analyzer)
    monkeypatch.setitem(
        session_store.RENAMED_COLUMNS, "settings", {"no_such_column": "still_missing"}
    )

    with pytest.raises(sqlite3.OperationalError):
        review()

    with sqlite3.connect(database_path) as database:
        overrides = database.execute("SELECT jpg_path, verdict FROM overrides").fetchall()
        thumbnail_columns = [row[1] for row in database.execute("PRAGMA table_info(thumbnails)")]
    assert overrides == [("DSCF0003.JPG", "reject")]
    assert thumbnail_columns == ["jpg_path", "jpg_size", "jpg_mtime_ns", "image"]
