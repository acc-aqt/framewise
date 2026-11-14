import sys

import pytest
from conftest import make_jpg, wait_until
from fastapi.testclient import TestClient

from framewise.review import SessionAnalysis, open_session
from framewise.server import create_app


def progress(client) -> dict:
    return client.get("/api/progress").json()


def group_paths(client) -> list[list[str]]:
    return [
        [frame["jpg_path"] for frame in group["frames"]]
        for group in client.get("/api/groups").json()
    ]


def test_groups_and_progress_appear_before_analysis_finishes(session_dir, live_review, analyzer):
    make_jpg(session_dir / "DSCF0001.JPG")
    analyzer.hold(make_jpg(session_dir / "DSCF0002.JPG"))

    client = live_review()
    wait_until(lambda: progress(client)["frames_done"] == 1)

    partial = progress(client)
    assert partial["frames_left"] == 1
    assert partial["seconds_remaining"] >= 0
    assert group_paths(client) == [["DSCF0001.JPG"]]

    analyzer.release_all()
    wait_until(lambda: progress(client)["frames_left"] == 0)

    assert progress(client) == {"frames_done": 2, "frames_left": 0, "seconds_remaining": 0}
    assert group_paths(client) == [["DSCF0001.JPG"], ["DSCF0002.JPG"]]


def test_frames_are_analysed_in_parallel(session_dir, live_review, analyzer):
    analyzer.hold(make_jpg(session_dir / "DSCF0001.JPG"))
    analyzer.hold(make_jpg(session_dir / "DSCF0002.JPG"))

    live_review()

    wait_until(lambda: analyzer.in_flight == 2)


def test_a_re_run_counts_frames_analysed_before_as_done(session_dir, review, analyzer):
    make_jpg(session_dir / "DSCF0001.JPG")
    make_jpg(session_dir / "DSCF0002.JPG")
    review()
    make_jpg(session_dir / "DSCF0003.JPG")

    assert progress(review()) == {"frames_done": 3, "frames_left": 0, "seconds_remaining": 0}


@pytest.mark.skipif(sys.platform != "darwin", reason="Darwin background priority is macOS-only")
def test_background_mode_analyses_frames_at_background_priority(session_dir, live_review, analyzer):
    make_jpg(session_dir / "DSCF0001.JPG")

    client = live_review(background=True)
    wait_until(lambda: progress(client)["frames_left"] == 0)

    assert analyzer.at_background_priority == [True]


@pytest.mark.skipif(sys.platform != "darwin", reason="Darwin background priority is macOS-only")
def test_analysis_runs_at_normal_priority_by_default(session_dir, live_review, analyzer):
    make_jpg(session_dir / "DSCF0001.JPG")

    client = live_review()
    wait_until(lambda: progress(client)["frames_left"] == 0)

    assert analyzer.at_background_priority == [False]


def test_a_frame_that_cannot_be_analysed_is_reported_and_the_rest_still_finish(
    session_dir, live_review, analyzer, capsys
):
    analyzer.fail(make_jpg(session_dir / "DSCF0001.JPG"))
    make_jpg(session_dir / "DSCF0002.JPG")

    client = live_review()
    wait_until(lambda: progress(client)["frames_left"] == 0)

    assert group_paths(client) == [["DSCF0002.JPG"]]
    assert "DSCF0001.JPG" in capsys.readouterr().err


def test_progress_counts_frames_analysed_before_as_done_before_the_run_starts(
    session_dir, data_dir, review, analyzer
):
    make_jpg(session_dir / "DSCF0001.JPG")
    review()

    store = open_session(session_dir, data_dir)
    client = TestClient(create_app(store, SessionAnalysis(store, analyzer)))

    assert progress(client)["frames_left"] == 0
