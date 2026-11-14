import os
import sys
import threading

import pytest
from conftest import clean_signals, make_jpg, wait_until
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


@pytest.mark.parametrize(("background", "expected_peak"), [(True, 2), (False, 8)])
def test_background_mode_analyses_fewer_frames_at_once(
    session_dir, live_review, analyzer, monkeypatch, background, expected_peak
):
    monkeypatch.setattr(os, "cpu_count", lambda: 8)
    for number in range(1, 13):
        analyzer.hold(make_jpg(session_dir / f"DSCF{number:04d}.JPG"))

    client = live_review(background=background)
    wait_until(lambda: analyzer.in_flight >= expected_peak)
    analyzer.release_all()
    wait_until(lambda: progress(client)["frames_left"] == 0)

    assert analyzer.peak_in_flight == expected_peak


def test_time_remaining_allows_for_frames_still_being_analysed(
    session_dir, live_review, analyzer, clock, monkeypatch
):
    monkeypatch.setattr(os, "cpu_count", lambda: 4)
    for number in range(1, 9):
        analyzer.hold(make_jpg(session_dir / f"DSCF{number:04d}.JPG"))

    client = live_review()
    wait_until(lambda: analyzer.in_flight == 4)
    assert progress(client)["seconds_remaining"] is None

    clock.now = 10
    analyzer.release(session_dir / "DSCF0001.JPG")
    wait_until(lambda: progress(client)["frames_done"] == 1 and analyzer.in_flight == 4)

    # 7 Frames of 10 s left on 4 workers, 3 of them 10 s in already
    assert progress(client)["seconds_remaining"] == 10


def test_time_remaining_ignores_frames_that_only_needed_a_thumbnail(
    session_dir, data_dir, analyzer, clock, monkeypatch
):
    monkeypatch.setattr(os, "cpu_count", lambda: 1)
    for number in range(1, 4):
        make_jpg(session_dir / f"DSCF{number:04d}.JPG")
    analyzer.hold(make_jpg(session_dir / "DSCF0004.JPG"))
    analyzer.hold(make_jpg(session_dir / "DSCF0005.JPG"))
    store = open_session(session_dir, data_dir)
    for number in range(1, 4):
        store.save_analysis(session_dir / f"DSCF{number:04d}.JPG", clean_signals([1.0]), None)

    analysis = SessionAnalysis(store, analyzer, clock=clock)
    threading.Thread(target=analysis.run, daemon=True).start()
    client = TestClient(create_app(store, analysis))
    wait_until(lambda: progress(client)["frames_done"] == 3 and analyzer.in_flight == 1)
    assert progress(client)["seconds_remaining"] is None

    clock.now = 12
    analyzer.release(session_dir / "DSCF0004.JPG")
    wait_until(lambda: progress(client)["frames_done"] == 4 and analyzer.in_flight == 1)

    assert progress(client)["seconds_remaining"] == 12


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


def test_the_review_ui_can_load_thumbnails_and_groups_while_frames_are_saved(
    session_dir, live_review
):
    for number in range(1, 61):
        make_jpg(session_dir / f"DSCF{number:04d}.JPG")
    client = live_review()
    app = client.app
    errors: list[BaseException] = []

    def browse() -> None:
        browser = TestClient(app)
        try:
            while progress(browser)["frames_left"] > 0:
                for frame_id in range(1, 61):
                    browser.get(f"/api/frames/{frame_id}/thumbnail")
                browser.get("/api/groups")
        except BaseException as error:
            errors.append(error)

    browsers = [threading.Thread(target=browse) for _ in range(6)]
    for browser in browsers:
        browser.start()
    for browser in browsers:
        browser.join(timeout=30)

    assert errors == []
