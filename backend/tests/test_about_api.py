from importlib.metadata import version

import pytest
from fastapi.testclient import TestClient

from framewise.changelog import CHANGELOG_PATH
from framewise.server import SessionPicker


def test_about_names_the_running_version(review):
    about = review().get("/api/about").json()

    assert about["version"] == version("framewise-cull")


def test_about_answers_before_a_session_is_open():
    picker = SessionPicker(choose_folder=lambda: None, start_session=lambda folder: None)

    about = TestClient(picker).get("/api/about").json()

    assert about["version"] == version("framewise-cull")


def changelog(client) -> list[dict]:
    return client.get("/api/about").json()["changelog"]


def test_about_lists_the_changelog_newest_first(review, tmp_path):
    path = tmp_path / "CHANGELOG.md"
    path.write_text(
        "# Changelog\n"
        "\n"
        "What changed, for photographers.\n"
        "\n"
        "## Unreleased\n"
        "\n"
        "- Faster grouping\n"
        "\n"
        "## 0.2.0 — 2026-12-01\n"
        "\n"
        "- **What's new** lists the Changelog\n"
        "\n"
        "### Fixed\n"
        "\n"
        "- `framewise review` opens the browser again\n"
        "\n"
        "## 0.1.0 — 2026-11-20\n"
        "\n"
        "- First Release\n",
        encoding="utf-8",
    )

    assert changelog(review(changelog_path=path)) == [
        {
            "version": None,
            "date": None,
            "sections": [{"heading": None, "items": ["Faster grouping"]}],
        },
        {
            "version": "0.2.0",
            "date": "2026-12-01",
            "sections": [
                {"heading": None, "items": ["**What's new** lists the Changelog"]},
                {"heading": "Fixed", "items": ["`framewise review` opens the browser again"]},
            ],
        },
        {
            "version": "0.1.0",
            "date": "2026-11-20",
            "sections": [{"heading": None, "items": ["First Release"]}],
        },
    ]


def test_about_has_no_changelog_when_the_file_is_missing(review, tmp_path):
    client = review(changelog_path=tmp_path / "CHANGELOG.md")

    assert client.get("/api/about").json() == {
        "version": version("framewise-cull"),
        "changelog": [],
    }


@pytest.mark.parametrize(
    "body",
    [
        "## Next\n\n- Faster grouping\n",
        "## 0.1.0 - 2026-11-20\n\n- First Release\n",
        "## 0.1.0 — 2026-11-20\n\n- First Release\n\n## Unreleased\n\n- Faster grouping\n",
        "## 0.1.0 — 2026-11-20\n\n- First Release\n\n## 0.2.0 — 2026-12-01\n\n- Faster\n",
        "## 0.1.0 — 2026-11-20\n\n### Added\n",
        "## 0.1.0 — 2026-11-20\n\n- First Release\n  - with a nested bullet\n",
        "## 0.1.0 — 2026-11-20\n\nA paragraph instead of a bullet.\n",
        "## 0.1.0 — 2026-11-20\n\n- See [the README](README.md)\n",
        "## 0.1.0 — 2026-11-20\n\n- <b>First</b> Release\n",
        "## 0.1.0 — 2026-11-20\n\n- *First* Release\n",
        "## 0.1.0 — 2026-11-20\n\n- _First_ Release\n",
        "## 0.1.0 — 2026-11-20\n\n- **First Release\n",
        "- A bullet above the first version\n\n## 0.1.0 — 2026-11-20\n\n- First Release\n",
        "### A subheading above the first version\n\n## 0.1.0 — 2026-11-20\n\n- First\n",
    ],
    ids=[
        "unknown heading",
        "hyphen instead of em dash",
        "Unreleased after a Release",
        "oldest first",
        "Release without entries",
        "nested bullet",
        "paragraph",
        "link",
        "HTML",
        "italic",
        "underscore emphasis",
        "unclosed bold",
        "bullet above the first version",
        "subheading above the first version",
    ],
)
def test_about_has_no_changelog_when_it_is_out_of_shape(review, tmp_path, body):
    path = tmp_path / "CHANGELOG.md"
    path.write_text("# Changelog\n\n" + body, encoding="utf-8")

    assert changelog(review(changelog_path=path)) == []


def test_about_has_no_changelog_without_its_title(review, tmp_path):
    path = tmp_path / "CHANGELOG.md"
    path.write_text("## 0.1.0 — 2026-11-20\n\n- First Release\n", encoding="utf-8")

    assert changelog(review(changelog_path=path)) == []


def test_the_changelog_is_in_the_shape_the_review_ui_shows(review):
    entries = changelog(review(changelog_path=CHANGELOG_PATH))

    assert entries, "CHANGELOG.md is missing or out of shape, see ADR-0007"
    released = [entry["version"] for entry in entries if entry["version"] is not None]
    if released:
        assert released[0] == version("framewise-cull")
