from email.message import Message
from importlib.metadata import version
from urllib.error import HTTPError, URLError

import pytest
from fastapi.testclient import TestClient

from framewise.server import SessionPicker
from framewise.update_check import MAIN_CHANGELOG_URL

RUNNING = version("framewise-cull")


def newer(minor_steps: int = 1) -> str:
    major, minor, _ = (int(part) for part in RUNNING.split("."))
    return f"{major}.{minor + minor_steps}.0"


class FakeMainChangelog:
    """Stands in for fetching the Changelog on `main`: returns the text it holds, or raises the
    error it is told to, and counts the fetches."""

    def __init__(self):
        self.text = ""
        self.error: Exception | None = None
        self.fetches = 0

    def __call__(self) -> str:
        self.fetches += 1
        if self.error is not None:
            raise self.error
        return self.text


@pytest.fixture
def main_changelog(monkeypatch, isolated_data_dir) -> FakeMainChangelog:
    monkeypatch.delenv("FRAMEWISE_NO_UPDATE_CHECK")
    return FakeMainChangelog()


def changelog_text(*releases: str) -> str:
    return "# Changelog\n\n## Unreleased\n\n- Faster grouping\n\n" + "".join(releases)


def release(release_version: str, *bullets: str) -> str:
    items = "".join(f"- {bullet}\n" for bullet in bullets)
    return f"## {release_version} — 2026-12-01\n\n{items}\n"


def update(client) -> dict | None:
    return client.get("/api/update").json()["available"]


def test_update_reports_the_newest_release_with_its_entries(review, main_changelog, clock):
    main_changelog.text = changelog_text(
        release(newer(2), "**Trash** asks before it empties"),
        release(newer(1), "Faster grouping"),
        release(RUNNING, "First Release"),
    )

    available = update(review(fetch_changelog=main_changelog, clock=clock, platform="linux"))

    assert available["version"] == newer(2)
    assert available["releases"] == [
        {
            "version": newer(2),
            "date": "2026-12-01",
            "sections": [{"heading": None, "items": ["**Trash** asks before it empties"]}],
        },
        {
            "version": newer(1),
            "date": "2026-12-01",
            "sections": [{"heading": None, "items": ["Faster grouping"]}],
        },
    ]


@pytest.mark.parametrize(
    ("platform", "command"),
    [
        ("darwin", "uvx --python 3.13 --from framewise-cull@latest framewise review"),
        ("linux", 'uvx --python 3.13 --from "framewise-cull[portable]@latest" framewise review'),
        ("win32", 'uvx --python 3.13 --from "framewise-cull[portable]@latest" framewise review'),
    ],
)
def test_update_names_the_command_for_an_installed_wheel(
    review, main_changelog, clock, tmp_path, platform, command
):
    main_changelog.text = changelog_text(release(newer(), "Faster grouping"))
    installed = tmp_path / "site-packages" / "framewise" / "CHANGELOG.md"
    installed.parent.mkdir(parents=True)
    installed.write_text(changelog_text(release(RUNNING, "First Release")), encoding="utf-8")

    client = review(
        fetch_changelog=main_changelog, clock=clock, platform=platform, changelog_path=installed
    )

    assert update(client)["command"] == command


@pytest.mark.parametrize(
    ("platform", "command"),
    [
        ("darwin", "git pull && scripts/setup.sh"),
        ("linux", "git pull && scripts/setup.sh"),
        ("win32", r"git pull; powershell -ExecutionPolicy Bypass -File scripts\setup.ps1"),
    ],
)
def test_update_names_the_command_for_a_checkout(
    review, main_changelog, clock, tmp_path, platform, command
):
    main_changelog.text = changelog_text(release(newer(), "Faster grouping"))
    checkout = tmp_path / "framewise"
    (checkout / ".git").mkdir(parents=True)
    (checkout / "CHANGELOG.md").write_text(
        changelog_text(release(RUNNING, "First Release")), encoding="utf-8"
    )

    client = review(
        fetch_changelog=main_changelog,
        clock=clock,
        platform=platform,
        changelog_path=checkout / "CHANGELOG.md",
    )

    assert update(client)["command"] == command


def test_update_shows_only_the_entries_for_the_platform(review, main_changelog, clock):
    main_changelog.text = changelog_text(
        release(newer(2), "Apple Vision finds the subject <!-- macos -->"),
        release(newer(1), "Faster on Windows <!-- windows -->", "Faster grouping"),
        release(RUNNING, "First Release"),
    )

    available = update(review(fetch_changelog=main_changelog, clock=clock, platform="win32"))

    assert available["version"] == newer(2)
    assert available["releases"] == [
        {"version": newer(2), "date": "2026-12-01", "sections": []},
        {
            "version": newer(1),
            "date": "2026-12-01",
            "sections": [{"heading": None, "items": ["Faster on Windows", "Faster grouping"]}],
        },
    ]


def test_update_reports_nothing_when_the_newer_releases_have_nothing_for_the_platform(
    review, main_changelog, clock
):
    main_changelog.text = changelog_text(
        release(newer(2), "Apple Vision finds the subject <!-- macos -->"),
        release(newer(1), "Apple Vision finds the eyes <!-- macos -->"),
        release(RUNNING, "First Release"),
    )

    assert update(review(fetch_changelog=main_changelog, clock=clock, platform="linux")) is None


@pytest.mark.parametrize(
    "newest",
    [RUNNING, "0.0.1"],
    ids=["running version is the newest", "running version is newer"],
)
def test_update_reports_nothing_without_a_newer_release(review, main_changelog, clock, newest):
    main_changelog.text = changelog_text(release(newest, "Faster grouping"))

    assert update(review(fetch_changelog=main_changelog, clock=clock)) is None


@pytest.mark.parametrize(
    "error",
    [
        URLError("offline"),
        TimeoutError("timed out"),
        HTTPError(MAIN_CHANGELOG_URL, 404, "Not Found", Message(), None),
    ],
    ids=["offline", "timeout", "not found"],
)
def test_update_reports_nothing_when_the_fetch_fails(review, main_changelog, clock, error):
    main_changelog.error = error

    assert update(review(fetch_changelog=main_changelog, clock=clock)) is None


@pytest.mark.parametrize(
    "text",
    [
        "",
        "<html>Rate limited</html>",
        changelog_text(release(newer(), "<b>Faster</b> grouping")),
        changelog_text(release(f"{newer()}-rc.1", "Faster grouping")),
    ],
    ids=["empty", "not a Changelog", "HTML", "pre-release"],
)
def test_update_reports_nothing_when_the_changelog_is_out_of_shape(
    review, main_changelog, clock, text
):
    main_changelog.text = text

    assert update(review(fetch_changelog=main_changelog, clock=clock)) is None


def test_update_checks_nothing_when_turned_off_in_the_config(
    review, main_changelog, clock, isolated_data_dir
):
    main_changelog.text = changelog_text(release(newer(), "Faster grouping"))
    config_path = isolated_data_dir / "config.toml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("check_for_updates = false\n", encoding="utf-8")

    client = review(fetch_changelog=main_changelog, clock=clock, config_path=config_path)

    assert update(client) is None
    assert main_changelog.fetches == 0


def test_update_checks_when_turned_on_in_the_config(
    review, main_changelog, clock, isolated_data_dir
):
    main_changelog.text = changelog_text(release(newer(), "Faster grouping"))
    config_path = isolated_data_dir / "config.toml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("check_for_updates = true\n", encoding="utf-8")

    client = review(fetch_changelog=main_changelog, clock=clock, config_path=config_path)

    assert update(client)["version"] == newer()


def test_update_checks_nothing_when_turned_off_by_the_environment(
    review, main_changelog, clock, monkeypatch
):
    main_changelog.text = changelog_text(release(newer(), "Faster grouping"))
    monkeypatch.setenv("FRAMEWISE_NO_UPDATE_CHECK", "1")

    assert update(review(fetch_changelog=main_changelog, clock=clock)) is None
    assert main_changelog.fetches == 0


HOUR = 60 * 60


def test_update_checks_at_most_once_a_day(review, main_changelog, clock):
    main_changelog.text = changelog_text(release(newer(), "Faster grouping"))
    clock.now = 1_800_000_000.0
    update(review(fetch_changelog=main_changelog, clock=clock))
    main_changelog.error = URLError("offline")
    clock.now += 23 * HOUR

    available = update(review(fetch_changelog=main_changelog, clock=clock))

    assert main_changelog.fetches == 1
    assert available["version"] == newer()


def test_update_checks_again_after_a_day(review, main_changelog, clock):
    main_changelog.text = changelog_text(release(newer(1), "Faster grouping"))
    clock.now = 1_800_000_000.0
    update(review(fetch_changelog=main_changelog, clock=clock))
    main_changelog.text = changelog_text(
        release(newer(2), "Faster culling"), release(newer(1), "Faster grouping")
    )
    clock.now += 25 * HOUR

    available = update(review(fetch_changelog=main_changelog, clock=clock))

    assert main_changelog.fetches == 2
    assert available["version"] == newer(2)


def test_update_checks_again_after_a_failed_check(review, main_changelog, clock):
    main_changelog.error = URLError("offline")
    update(review(fetch_changelog=main_changelog, clock=clock))
    main_changelog.error = None
    main_changelog.text = changelog_text(release(newer(), "Faster grouping"))

    available = update(review(fetch_changelog=main_changelog, clock=clock))

    assert main_changelog.fetches == 2
    assert available["version"] == newer()


def picker(**options) -> TestClient:
    return TestClient(
        SessionPicker(choose_folder=lambda: None, start_session=lambda folder: None, **options)
    )


def test_update_answers_before_a_session_is_open(main_changelog, clock):
    main_changelog.text = changelog_text(release(newer(), "Faster on Linux <!-- linux -->"))

    available = update(picker(fetch_changelog=main_changelog, clock=clock, platform="linux"))

    assert available["version"] == newer()
    assert available["releases"][0]["sections"] == [{"heading": None, "items": ["Faster on Linux"]}]


def test_the_folder_picker_checks_nothing_when_turned_off_in_the_config(
    main_changelog, clock, isolated_data_dir
):
    main_changelog.text = changelog_text(release(newer(), "Faster grouping"))
    isolated_data_dir.mkdir(parents=True, exist_ok=True)
    (isolated_data_dir / "config.toml").write_text("check_for_updates = false\n", encoding="utf-8")

    assert update(picker(fetch_changelog=main_changelog, clock=clock)) is None
    assert main_changelog.fetches == 0
