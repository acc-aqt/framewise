import pytest
from conftest import make_jpg
from fastapi.testclient import TestClient

from framewise.cli import main


class FakeServer:
    def __init__(self):
        self.app = None
        self.host = None
        self.port = None

    def __call__(self, app, host, port, on_ready):
        self.app, self.host, self.port = app, host, port
        on_ready()


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

    main(["review", str(session_dir), "--port", "9123"], serve=server, open_browser=opened.append)

    assert (server.host, server.port) == ("127.0.0.1", 9123)
    assert opened == ["http://127.0.0.1:9123/"]
    assert TestClient(server.app).get("/api/session").json()["total_frames"] == 1
    assert len(list(isolated_data_dir.iterdir())) == 1


def test_review_refuses_a_folder_that_does_not_exist(tmp_path, isolated_data_dir):
    with pytest.raises(SystemExit) as exit_info:
        main(["review", str(tmp_path / "missing")], serve=FakeServer(), open_browser=print)

    assert exit_info.value.code == 2
