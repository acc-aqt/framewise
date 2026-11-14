import sys
from contextlib import contextmanager

import pytest
from conftest import FakeAnalyzer, make_jpg, wait_until
from fastapi.testclient import TestClient

from framewise.cli import main


class FakeServer:
    def __init__(self):
        self.app = None
        self.host = None
        self.port = None
        self.progress_when_ready = None

    def __call__(self, app, host, port, on_ready):
        self.app, self.host, self.port = app, host, port
        self.progress_when_ready = self.progress()
        on_ready()

    def progress(self) -> dict:
        return TestClient(self.app).get("/api/progress").json()


class FakeWakeLock:
    def __init__(self):
        self.held = False
        self.times_held = 0

    @contextmanager
    def __call__(self):
        self.held = True
        self.times_held += 1
        try:
            yield
        finally:
            self.held = False


@pytest.fixture
def isolated_data_dir(data_dir, monkeypatch):
    monkeypatch.setenv("FRAMEWISE_DATA_DIR", str(data_dir))
    return data_dir


def test_review_scans_the_folder_serves_on_localhost_and_opens_the_browser(
    session_dir, isolated_data_dir
):
    make_jpg(session_dir / "DSCF0001.JPG")
    server = FakeServer()
    opened = []

    main(
        ["review", str(session_dir), "--port", "9123"],
        serve=server,
        open_browser=opened.append,
        analyzer=FakeAnalyzer(),
        keep_awake=FakeWakeLock(),
    )

    assert (server.host, server.port) == ("127.0.0.1", 9123)
    assert opened == ["http://127.0.0.1:9123/"]
    assert TestClient(server.app).get("/api/session").json()["total_frames"] == 1
    assert len(list(isolated_data_dir.iterdir())) == 1


def test_review_refuses_a_folder_that_does_not_exist(tmp_path, isolated_data_dir):
    with pytest.raises(SystemExit) as exit_info:
        main(
            ["review", str(tmp_path / "missing")],
            serve=FakeServer(),
            open_browser=print,
            analyzer=FakeAnalyzer(),
            keep_awake=FakeWakeLock(),
        )

    assert exit_info.value.code == 2


def test_review_warns_when_the_review_ui_has_not_been_built(
    session_dir, isolated_data_dir, tmp_path, monkeypatch, capsys
):
    monkeypatch.setattr("framewise.cli.UI_DIR", tmp_path / "missing-build")

    main(
        ["review", str(session_dir)],
        serve=FakeServer(),
        open_browser=print,
        analyzer=FakeAnalyzer(),
        keep_awake=FakeWakeLock(),
    )

    assert "ng build" in capsys.readouterr().err


def test_review_opens_the_review_ui_before_analysis_finishes(session_dir, isolated_data_dir):
    analyzer = FakeAnalyzer()
    make_jpg(session_dir / "DSCF0001.JPG")
    analyzer.hold(make_jpg(session_dir / "DSCF0002.JPG"))
    server = FakeServer()
    opened = []

    main(
        ["review", str(session_dir)],
        serve=server,
        open_browser=opened.append,
        analyzer=analyzer,
        keep_awake=FakeWakeLock(),
    )
    analyzer.release_all()

    assert opened == ["http://127.0.0.1:8765/"]
    assert server.progress_when_ready["frames_left"] >= 1


def test_review_keeps_the_mac_awake_while_analysis_runs(session_dir, isolated_data_dir):
    analyzer = FakeAnalyzer()
    analyzer.hold(make_jpg(session_dir / "DSCF0001.JPG"))
    server = FakeServer()
    wake_lock = FakeWakeLock()

    main(
        ["review", str(session_dir)],
        serve=server,
        open_browser=print,
        analyzer=analyzer,
        keep_awake=wake_lock,
    )
    wait_until(lambda: wake_lock.held)
    analyzer.release_all()
    wait_until(lambda: server.progress()["frames_left"] == 0 and not wake_lock.held)

    assert wake_lock.times_held == 1


def test_review_lets_the_mac_sleep_when_asked(session_dir, isolated_data_dir):
    make_jpg(session_dir / "DSCF0001.JPG")
    server = FakeServer()
    wake_lock = FakeWakeLock()

    main(
        ["review", str(session_dir), "--allow-sleep"],
        serve=server,
        open_browser=print,
        analyzer=FakeAnalyzer(),
        keep_awake=wake_lock,
    )
    wait_until(lambda: server.progress()["frames_left"] == 0)

    assert wake_lock.times_held == 0


@pytest.mark.skipif(sys.platform != "darwin", reason="Darwin background priority is macOS-only")
def test_review_in_background_mode_analyses_at_background_priority(session_dir, isolated_data_dir):
    analyzer = FakeAnalyzer()
    make_jpg(session_dir / "DSCF0001.JPG")
    server = FakeServer()

    main(
        ["review", str(session_dir), "--background"],
        serve=server,
        open_browser=print,
        analyzer=analyzer,
        keep_awake=FakeWakeLock(),
    )
    wait_until(lambda: server.progress()["frames_left"] == 0)

    assert analyzer.at_background_priority == [True]
