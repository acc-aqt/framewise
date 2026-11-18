"""Reads the Changelog in the shape the Review UI renders (ADR-0007)."""

import re
from dataclasses import dataclass, field
from pathlib import Path

CHANGELOG_PATH = Path(__file__).resolve().parents[3] / "CHANGELOG.md"

UNRELEASED_HEADING = "## Unreleased"
RELEASE_HEADING = re.compile(r"^## (\d+\.\d+\.\d+) — (\d{4}-\d{2}-\d{2})$")
SUBHEADING = re.compile(r"^### (\S.*)$")
BULLET = re.compile(r"^- (\S.*)$")
TITLE = re.compile(r"^# \S")
SUPPORTED_INLINE = re.compile(r"\*\*[^*]+\*\*|`[^`]+`")
UNSUPPORTED_INLINE = re.compile(r"\[[^\]]*\]\(|<[A-Za-z/!]|[*_`]")


class ChangelogError(ValueError):
    pass


@dataclass
class ChangelogSection:
    heading: str | None
    """The `###` subheading, or None for the bullets before any subheading."""
    items: list[str] = field(default_factory=list)


@dataclass
class ChangelogVersion:
    version: str | None
    """None for Unreleased."""
    date: str | None
    sections: list[ChangelogSection] = field(default_factory=list)


def read_changelog(path: Path | None) -> list[ChangelogVersion]:
    """The Changelog at `path`, or none when it is missing or out of shape, so the Review UI
    still shows the version."""
    if path is None:
        return []
    try:
        return parse_changelog(path.read_text(encoding="utf-8"))
    except (OSError, ChangelogError):
        return []


def parse_changelog(text: str) -> list[ChangelogVersion]:
    """The versions in a Changelog: a `# ` title and an optional introduction, then one
    `## ` section per version, newest first."""
    lines = [
        (line_number, line.rstrip())
        for line_number, line in enumerate(text.splitlines(), start=1)
        if line.strip()
    ]
    if not lines or not TITLE.match(lines[0][1]):
        raise ChangelogError("line 1: expected the '# ' title")
    versions: list[ChangelogVersion] = []
    for line_number, line in lines[1:]:
        if line.startswith("## "):
            versions.append(_parse_version_heading(line, line_number, versions))
        elif not versions:
            if line.startswith(("#", "- ")):
                raise ChangelogError(f"line {line_number}: expected introduction text")
        elif match := SUBHEADING.match(line):
            versions[-1].sections.append(ChangelogSection(match[1]))
        elif match := BULLET.match(line):
            _add_item(versions[-1], match[1], line_number)
        else:
            raise ChangelogError(f"line {line_number}: expected a bullet or a ### subheading")
    for entry in versions:
        if entry.version is not None and not any(section.items for section in entry.sections):
            raise ChangelogError(f"{entry.version} has no entries")
    return versions


def _parse_version_heading(
    line: str, line_number: int, earlier: list[ChangelogVersion]
) -> ChangelogVersion:
    if line == UNRELEASED_HEADING:
        if earlier:
            raise ChangelogError(f"line {line_number}: Unreleased must be the first version")
        return ChangelogVersion(None, None)
    match = RELEASE_HEADING.match(line)
    if match is None:
        raise ChangelogError(
            f"line {line_number}: expected '## Unreleased' or '## X.Y.Z — YYYY-MM-DD'"
        )
    previous = next((entry.version for entry in reversed(earlier) if entry.version), None)
    if previous is not None and _semver(match[1]) >= _semver(previous):
        raise ChangelogError(f"line {line_number}: {match[1]} must be older than {previous}")
    return ChangelogVersion(match[1], match[2])


def _add_item(entry: ChangelogVersion, item: str, line_number: int) -> None:
    if UNSUPPORTED_INLINE.search(SUPPORTED_INLINE.sub("", item)):
        raise ChangelogError(f"line {line_number}: only **bold** and `code` are shown")
    if not entry.sections:
        entry.sections.append(ChangelogSection(None))
    entry.sections[-1].items.append(item)


def _semver(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))
