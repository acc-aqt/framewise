from importlib.metadata import version

from fastapi.testclient import TestClient

from framewise.server import SessionPicker


def test_about_names_the_running_version(review):
    about = review().get("/api/about").json()

    assert about["version"] == version("framewise")


def test_about_answers_before_a_session_is_open():
    picker = SessionPicker(choose_folder=lambda: None, start_session=lambda folder: None)

    about = TestClient(picker).get("/api/about").json()

    assert about["version"] == version("framewise")
