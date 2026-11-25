"""Reads the Changelog in the shape the Review UI renders (ADR-0007)."""

import re
from dataclasses import dataclass, field
from pathlib import Path

PACKAGED_CHANGELOG = Path(__file__).resolve().parent / "CHANGELOG.md"
CHANGELOG_PATH = (
    PACKAGED_CHANGELOG
    if PACKAGED_CHANGELOG.is_file()
    else PACKAGED_CHANGELOG.parents[3] / "CHANGELOG.md"
)
"""The Changelog an installed wheel carries, or the checkout's when running from a clone."""

UNRELEASED_HEADING = "## Unreleased"
RELEASE_HEADING = re.compile(r"^## (\d+\.\d+\.\d+) — (\d{4}-\d{2}-\d{2})$")
SUBHEADING = re.compile(r"^### (\S.*)$")
BULLET = re.compile(r"^- (\S.*)$")
TITLE = re.compile(r"^# \S")
SUPPORTED_INLINE = re.compile(r"\*\*[^*]+\*\*|`[^`]+`")
UNSUPPORTED_INLINE = re.compile(r"\[[^\]]*\]\(|<[A-Za-z/!]|[*_`]")
PLATFORM_MARKER = re.compile(r"\s*<!--(.*?)-->$")
PLATFORMS = frozenset({"macos", "linux", "windows"})
PLATFORM_NAMES = {"macos": "macOS", "linux": "Linux", "windows": "Windows"}


class ChangelogError(ValueError):
    pass


@dataclass
class ChangelogItem:
    text: str
    """The bullet as photographers read it, without its platform marker."""
    platforms: frozenset[str]
    """The platforms the bullet applies to; every platform when it has no marker."""


@dataclass
class ChangelogSection:
    heading: str | None
    """The `###` subheading, or None for the bullets before any subheading."""
    items: list[ChangelogItem] = field(default_factory=list)


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
    text, platforms = _split_platform_marker(item, line_number)
    if UNSUPPORTED_INLINE.search(SUPPORTED_INLINE.sub("", text)):
        raise ChangelogError(f"line {line_number}: only **bold** and `code` are shown")
    if not entry.sections:
        entry.sections.append(ChangelogSection(None))
    entry.sections[-1].items.append(ChangelogItem(text, platforms))


def _split_platform_marker(item: str, line_number: int) -> tuple[str, frozenset[str]]:
    """The bullet without its trailing `<!-- linux windows -->` marker, and the platforms it
    names."""
    match = PLATFORM_MARKER.search(item)
    if match is None:
        return item, PLATFORMS
    tokens = match[1].split()
    unknown = [token for token in tokens if token not in PLATFORMS]
    if not tokens or unknown:
        raise ChangelogError(
            f"line {line_number}: a platform marker names only macos, linux and windows"
        )
    platforms = frozenset(tokens)
    if platforms == PLATFORMS:
        raise ChangelogError(
            f"line {line_number}: leave a bullet for every platform without a marker"
        )
    return item[: match.start()], platforms


def changelog_platform(sys_platform: str) -> str:
    """The Changelog platform token for `sys_platform`, as named by sys.platform."""
    if sys_platform == "darwin":
        return "macos"
    if sys_platform == "win32":
        return "windows"
    return "linux"


def for_platform(versions: list[ChangelogVersion], platform: str) -> list[ChangelogVersion]:
    """The versions with only the bullets that apply to `platform`. A version left with no
    bullets stays, with no sections, so the version numbers don't seem to skip."""
    filtered = []
    for entry in versions:
        sections = [
            ChangelogSection(
                section.heading, [item for item in section.items if platform in item.platforms]
            )
            for section in entry.sections
        ]
        filtered.append(
            ChangelogVersion(
                entry.version, entry.date, [section for section in sections if section.items]
            )
        )
    return filtered


def _semver(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))
