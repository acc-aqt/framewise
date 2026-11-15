import sys
from contextlib import contextmanager

import pytest
from conftest import BACKGROUND_PRIORITY_PLATFORMS, FakeAnalyzer, make_jpg, wait_until
from fastapi.testclient import TestClient
from test_models import CONTENT, hosted_model
from test_providers import FakeFingerprint
from test_write_back_api import rating

from framewise.cli import main
from framewise.providers import compose_analyzer


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

    def client(self) -> TestClient:
        """A client for the Review UI at the address framewise serves it on."""
        return TestClient(self.app, base_url=f"http://{self.host}:{self.port}")

    def progress(self) -> dict:
        return self.client().get("/api/progress").json()


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
    assert server.client().get("/api/session").json()["total_frames"] == 1
    assert len(list(isolated_data_dir.glob("*.sqlite"))) == 1


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

    assert "scripts/setup.sh" in capsys.readouterr().err


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


def test_review_lets_the_machine_sleep_when_asked(session_dir, isolated_data_dir):
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


@pytest.mark.skipif(
    sys.platform not in BACKGROUND_PRIORITY_PLATFORMS,
    reason="Background priority needs macOS or Linux",
)
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


def test_review_without_a_folder_opens_the_review_ui_with_no_session(isolated_data_dir):
    server = FakeServer()
    opened = []

    main(
        ["review"],
        serve=server,
        open_browser=opened.append,
        analyzer=FakeAnalyzer(),
        keep_awake=FakeWakeLock(),
        choose_folder=lambda: None,
    )

    assert opened == ["http://127.0.0.1:8765/"]
    assert server.client().get("/api/session").status_code == 404
    assert list(isolated_data_dir.glob("*.sqlite")) == []


def test_review_without_a_folder_opens_the_session_chosen_in_the_review_ui(
    session_dir, isolated_data_dir
):
    make_jpg(session_dir / "DSCF0001.JPG")
    server = FakeServer()
    main(
        ["review"],
        serve=server,
        open_browser=print,
        analyzer=FakeAnalyzer(),
        keep_awake=FakeWakeLock(),
        choose_folder=lambda: session_dir,
    )
    client = server.client()

    assert client.post("/api/session/choose").json() == {"opened": True}
    assert client.get("/api/session").json()["total_frames"] == 1
    wait_until(lambda: server.progress()["frames_left"] == 0)
    assert len(client.get("/api/groups").json()) == 1


def test_review_without_a_folder_stays_without_a_session_when_the_dialog_is_cancelled(
    isolated_data_dir,
):
    server = FakeServer()
    main(
        ["review"],
        serve=server,
        open_browser=print,
        analyzer=FakeAnalyzer(),
        keep_awake=FakeWakeLock(),
        choose_folder=lambda: None,
    )
    client = server.client()

    assert client.post("/api/session/choose").json() == {"opened": False}
    assert client.get("/api/session").status_code == 404


def test_reset_restores_the_files_and_deletes_the_session_store(
    session_dir, isolated_data_dir, review, analyzer, capsys
):
    photo = make_jpg(session_dir / "DSCF0001.JPG", stars=1)
    analyzer.script(photo, [1.0, 0.0, 0.0])
    review().post("/api/write-back")
    assert rating(photo) == {"stars": 3, "label": None}

    main(["reset", str(session_dir)])

    assert rating(photo) == {"stars": 1, "label": None}
    assert list(isolated_data_dir.glob("*.sqlite*")) == []
    assert "restored 1 files" in capsys.readouterr().out
    analyzer.analyzed.clear()
    review()
    assert analyzer.analyzed == [photo]


def test_reset_keeps_the_session_store_when_a_file_cannot_be_restored(
    session_dir, isolated_data_dir, review, analyzer, capsys
):
    photo = make_jpg(session_dir / "DSCF0001.JPG", stars=1)
    review().post("/api/write-back")
    photo.chmod(0o444)

    with pytest.raises(SystemExit) as exit_info:
        main(["reset", str(session_dir)])

    assert exit_info.value.code == 1
    assert len(list(isolated_data_dir.glob("*.sqlite"))) == 1
    assert "could not restore DSCF0001.JPG" in capsys.readouterr().err


def test_reset_of_a_folder_without_a_session_store_changes_nothing(
    session_dir, isolated_data_dir, capsys
):
    main(["reset", str(session_dir)])

    assert "nothing to reset" in capsys.readouterr().out


def test_review_refuses_to_start_with_a_broken_config(session_dir, isolated_data_dir, capsys):
    isolated_data_dir.mkdir(parents=True)
    (isolated_data_dir / "config.toml").write_text("[providers\n")

    with pytest.raises(SystemExit) as exit_info:
        main(
            ["review", str(session_dir)],
            serve=FakeServer(),
            open_browser=print,
            keep_awake=FakeWakeLock(),
        )

    assert exit_info.value.code == 1
    assert "config.toml: invalid TOML" in capsys.readouterr().err


def test_models_download_fetches_every_model_into_the_data_dir(tmp_path, isolated_data_dir, capsys):
    model = hosted_model(tmp_path)

    main(["models", "download"], models=[model])

    assert (isolated_data_dir / "models" / "detector.task").read_bytes() == CONTENT
    assert "detector.task" in capsys.readouterr().out


def test_models_download_fails_with_the_reason_when_a_model_cannot_be_fetched(
    tmp_path, isolated_data_dir, capsys
):
    model = hosted_model(tmp_path)
    (tmp_path / "hosted" / "detector.task").unlink()

    with pytest.raises(SystemExit) as exit_info:
        main(["models", "download"], models=[model])

    assert exit_info.value.code == 1
    assert "cannot be downloaded" in capsys.readouterr().err


def test_review_shows_the_providers_of_the_running_analyzer(session_dir, isolated_data_dir):
    server = FakeServer()

    main(
        ["review", str(session_dir)],
        serve=server,
        open_browser=print,
        analyzer=compose_analyzer([FakeFingerprint(id="fake-fingerprint", version=2)]),
        keep_awake=FakeWakeLock(),
    )

    providers = server.client().get("/api/session").json()["providers"]
    assert providers["fingerprint"]["active"] == {
        "id": "fake-fingerprint",
        "version": 2,
        "source": "automatic",
    }


def test_review_shows_the_config_path_in_the_data_directory_even_without_the_file(
    session_dir, isolated_data_dir
):
    server = FakeServer()

    main(
        ["review", str(session_dir)],
        serve=server,
        open_browser=print,
        analyzer=FakeAnalyzer(),
        keep_awake=FakeWakeLock(),
    )

    config_path = server.client().get("/api/session").json()["config_path"]
    assert config_path == str(isolated_data_dir / "config.toml")
    assert not (isolated_data_dir / "config.toml").exists()


def serve_review(session_dir) -> FakeServer:
    make_jpg(session_dir / "DSCF0001.JPG")
    server = FakeServer()
    main(
        ["review", str(session_dir)],
        serve=server,
        open_browser=print,
        analyzer=FakeAnalyzer(),
        keep_awake=FakeWakeLock(),
    )
    wait_until(lambda: server.progress()["frames_left"] == 0)
    return server


def test_review_refuses_requests_for_a_host_other_than_this_machine(session_dir, isolated_data_dir):
    client = serve_review(session_dir).client()

    for host in ("attacker.example:8765", "attacker.example", "192.168.1.20:8765"):
        assert client.get("/api/session", headers={"host": host}).status_code == 403
        assert client.get("/api/frames/1/image", headers={"host": host}).status_code == 403
    assert client.get("/api/session", headers={"host": "localhost:8765"}).status_code == 200


@pytest.mark.parametrize(
    "headers",
    [
        {"sec-fetch-site": "cross-site", "origin": "https://attacker.example"},
        {"sec-fetch-site": "same-site", "origin": "http://localhost:3000"},
        {"origin": "https://attacker.example"},
        {"origin": "null"},
    ],
)
def test_review_refuses_changes_sent_by_other_sites(session_dir, isolated_data_dir, headers):
    client = serve_review(session_dir).client()
    client.patch("/api/frames/1/override", json={"stars": 4})

    for path in ("/api/session/reset", "/api/write-back", "/api/write-back/undo"):
        assert client.post(path, headers=headers).status_code == 403
    assert (
        client.patch("/api/session", json={"keeper_budget": 0.1}, headers=headers).status_code
        == 403
    )

    [group] = client.get("/api/groups").json()
    assert group["frames"][0]["override"]["stars"] == 4


def test_review_accepts_changes_from_its_own_review_ui(session_dir, isolated_data_dir):
    client = serve_review(session_dir).client()
    own_ui = {"sec-fetch-site": "same-origin", "origin": "http://127.0.0.1:8765"}

    response = client.patch("/api/frames/1/override", json={"stars": 4}, headers=own_ui)

    assert response.status_code == 200
    assert client.post("/api/session/reset", headers=own_ui).status_code == 200


def test_review_lets_other_sites_open_the_review_ui_but_not_fetch_from_it(
    session_dir, isolated_data_dir
):
    client = serve_review(session_dir).client()
    embedded = {"sec-fetch-site": "cross-site", "sec-fetch-mode": "no-cors"}
    link = {"sec-fetch-site": "cross-site", "sec-fetch-mode": "navigate"}

    assert client.get("/api/frames/1/image", headers=embedded).status_code == 403
    assert client.get("/api/write-back", headers=embedded).status_code == 403
    assert client.get("/", headers=link).status_code != 403


def test_review_without_a_folder_refuses_another_site_opening_the_folder_dialog(
    isolated_data_dir,
):
    server = FakeServer()
    dialogs = []
    main(
        ["review"],
        serve=server,
        open_browser=print,
        analyzer=FakeAnalyzer(),
        keep_awake=FakeWakeLock(),
        choose_folder=lambda: dialogs.append(True),
    )

    response = server.client().post("/api/session/choose", headers={"sec-fetch-site": "cross-site"})

    assert response.status_code == 403
    assert dialogs == []
