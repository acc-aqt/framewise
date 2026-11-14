import json
import sqlite3

from conftest import CLEAN_SIGNALS, make_jpg, wait_until

from framewise.review import session_database_path

APPLE = {"fingerprint": "apple-vision-fingerprint@1", "eye-state": "apple-vision-eye-state@1"}
BEACH = [1.0, 0.0, 0.0]
MOUNTAIN = [0.0, 1.0, 0.0]


def analysed_names(analyzer) -> list[str]:
    return sorted(path.name for path in analyzer.analyzed)


def group_paths(client) -> list[list[str]]:
    return [
        [frame["jpg_path"] for frame in group["frames"]]
        for group in client.get("/api/groups").json()
    ]


def test_a_re_run_with_the_same_providers_performs_no_analysis(session_dir, review, analyzer):
    analyzer.signature = APPLE
    make_jpg(session_dir / "DSCF0001.JPG")
    review()
    analyzer.analyzed.clear()

    review()

    assert analyzer.analyzed == []


def test_changing_a_capabilitys_provider_re_analyses_only_the_frames_the_old_one_analysed(
    session_dir, review, analyzer
):
    analyzer.signature = APPLE
    make_jpg(session_dir / "DSCF0001.JPG")
    make_jpg(session_dir / "DSCF0002.JPG")
    review()
    analyzer.signature = APPLE | {"eye-state": "mediapipe-eye-state@1"}
    analyzer.fail(session_dir / "DSCF0002.JPG")
    review()
    analyzer.analyzed.clear()

    analyzer.signature = APPLE
    review()

    assert analysed_names(analyzer) == ["DSCF0001.JPG"]


def test_a_new_provider_version_re_analyses_the_frames_the_old_one_analysed(
    session_dir, review, analyzer
):
    analyzer.signature = APPLE
    make_jpg(session_dir / "DSCF0001.JPG")
    make_jpg(session_dir / "DSCF0002.JPG")
    review()
    analyzer.analyzed.clear()

    analyzer.signature = APPLE | {"eye-state": "apple-vision-eye-state@2"}
    review()

    assert analysed_names(analyzer) == ["DSCF0001.JPG", "DSCF0002.JPG"]


def test_a_new_fingerprint_provider_groups_frames_by_its_fingerprints_alone(
    session_dir, review, analyzer
):
    analyzer.signature = APPLE
    analyzer.script(make_jpg(session_dir / "DSCF0001.JPG"), BEACH)
    analyzer.script(make_jpg(session_dir / "DSCF0002.JPG"), BEACH)
    review()
    analyzer.analyzed.clear()

    analyzer.signature = APPLE | {"fingerprint": "dinov2-small@1"}
    analyzer.script(session_dir / "DSCF0002.JPG", MOUNTAIN)
    client = review()

    assert analysed_names(analyzer) == ["DSCF0001.JPG", "DSCF0002.JPG"]
    assert group_paths(client) == [["DSCF0001.JPG"], ["DSCF0002.JPG"]]


def test_while_frames_wait_for_re_analysis_they_are_left_out_of_groups(
    session_dir, live_review, review, analyzer
):
    analyzer.signature = APPLE
    analyzer.script(make_jpg(session_dir / "DSCF0001.JPG"), BEACH)
    analyzer.script(make_jpg(session_dir / "DSCF0002.JPG"), BEACH)
    review()

    analyzer.signature = APPLE | {"fingerprint": "dinov2-small@1"}
    analyzer.script(session_dir / "DSCF0001.JPG", [0.0, 0.0, 1.0, 0.0])
    analyzer.hold(session_dir / "DSCF0002.JPG")
    client = live_review()
    wait_until(lambda: client.get("/api/progress").json()["frames_done"] == 1)

    assert group_paths(client) == [["DSCF0001.JPG"]]


def test_analyses_saved_before_providers_were_recorded_are_re_analysed(
    session_dir, data_dir, review, analyzer
):
    jpg = make_jpg(session_dir / "DSCF0001.JPG")
    make_store_from_before_provider_signatures(session_dir, data_dir, jpg)

    client = review()

    assert analysed_names(analyzer) == ["DSCF0001.JPG"]
    assert group_paths(client) == [["DSCF0001.JPG"]]


def make_store_from_before_provider_signatures(session_dir, data_dir, jpg) -> None:
    """Writes a Session store as framewise saved it before analyses recorded their Providers."""
    data_dir.mkdir(parents=True)
    database = sqlite3.connect(session_database_path(session_dir.resolve(), data_dir))
    stat = jpg.stat()
    with database:
        database.executescript(
            """
            CREATE TABLE analyses (
                jpg_path TEXT PRIMARY KEY,
                jpg_size INTEGER NOT NULL,
                jpg_mtime_ns INTEGER NOT NULL,
                fingerprint BLOB NOT NULL,
                captured_at TEXT,
                version INTEGER,
                signals TEXT
            );
            """
        )
        database.execute(
            "INSERT INTO analyses VALUES (?, ?, ?, ?, NULL, 5, ?)",
            (jpg.name, stat.st_size, stat.st_mtime_ns, b"\0\0\x80\x3f", json.dumps(CLEAN_SIGNALS)),
        )
    database.close()
