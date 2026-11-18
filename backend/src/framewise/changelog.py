"""Reads the Changelog in the shape the Review UI renders (ADR-0007)."""

import re
from dataclasses import dataclass, field
from pathlib import Path

CHANGELOG_PATH = Path(__file__).resolve().parents[3] / "CHANGELOG.md"

UNRELEASED_HEADING = "## Unreleased"
RELEASE_HEADING = re.compile(r"^## (\d+\.\d+\.\d+) — (\d{4}-\d{2}-\d{2})$")
SUBHEADING = re.compile(r"^### (\S.*)$")
BULLET = re.compile(r"^- (\S.*)$")
UNSUPPORTED_INLINE = re.compile(r"\[[^\]]*\]\(|<[A-Za-z/!]")


class ChangelogError(ValueError):
    pass


@dataclass(frozen=True)
class ChangelogSection:
    heading: str | None
    """The `###` subheading, or None for the bullets before any subheading."""
    items: list[str] = field(default_factory=list)


@dataclass(frozen=True)
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
    versions: list[ChangelogVersion] = []
    for number, line in enumerate(text.splitlines(), start=1):
        line = line.rstrip()
        if not line:
            continue
        if line.startswith("## "):
            versions.append(_version(line, number, versions))
        elif not versions:
            continue
        elif match := SUBHEADING.match(line):
            versions[-1].sections.append(ChangelogSection(match[1]))
        elif match := BULLET.match(line):
            _add_item(versions[-1], match[1], number)
        else:
            raise ChangelogError(f"line {number}: expected a bullet or a ### subheading")
    for entry in versions:
        if entry.version is not None and not any(section.items for section in entry.sections):
            raise ChangelogError(f"{entry.version} has no entries")
    return versions


def _version(line: str, number: int, earlier: list[ChangelogVersion]) -> ChangelogVersion:
    if line == UNRELEASED_HEADING:
        if earlier:
            raise ChangelogError(f"line {number}: Unreleased must be the first version")
        return ChangelogVersion(None, None)
    match = RELEASE_HEADING.match(line)
    if match is None:
        raise ChangelogError(f"line {number}: expected '## Unreleased' or '## X.Y.Z — YYYY-MM-DD'")
    previous = next((entry.version for entry in reversed(earlier) if entry.version), None)
    if previous is not None and _semver(match[1]) >= _semver(previous):
        raise ChangelogError(f"line {number}: {match[1]} must be older than {previous}")
    return ChangelogVersion(match[1], match[2])


def _add_item(entry: ChangelogVersion, item: str, number: int) -> None:
    if UNSUPPORTED_INLINE.search(item):
        raise ChangelogError(f"line {number}: links, images and HTML are not shown")
    if not entry.sections:
        entry.sections.append(ChangelogSection(None))
    entry.sections[-1].items.append(item)


def _semver(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))
