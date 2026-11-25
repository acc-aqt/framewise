"""Checks `main`'s Changelog for a Release newer than the running one (ADR-0012)."""

import json
import os
import threading
import tomllib
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path

from framewise.changelog import ChangelogVersion, for_platform, parse_changelog, semver

MAIN_CHANGELOG_URL = "https://raw.githubusercontent.com/acc-aqt/framewise/main/CHANGELOG.md"
TIMEOUT_SECONDS = 5
CACHE_SECONDS = 24 * 60 * 60
CACHE_FILE_NAME = "update-check.json"
CONFIG_KEY = "check_for_updates"
OPT_OUT_VARIABLE = "FRAMEWISE_NO_UPDATE_CHECK"

FetchChangelog = Callable[[], str]
Clock = Callable[[], float]


def fetch_main_changelog() -> str:
    """The Changelog on `main`, with a plain GET that sends nothing about the photographer."""
    with urllib.request.urlopen(MAIN_CHANGELOG_URL, timeout=TIMEOUT_SECONDS) as response:
        if response.status != 200:
            raise OSError(f"{MAIN_CHANGELOG_URL} answered {response.status}")
        return response.read().decode("utf-8")


def is_checkout(changelog_path: Path | None) -> bool:
    """Whether framewise runs from a clone, whose Changelog sits at the root of the git checkout,
    rather than from a wheel, which carries its own."""
    return changelog_path is not None and (changelog_path.parent / ".git").exists()


def update_command(platform_token: str, checkout: bool) -> str:
    """The command that updates framewise as it was installed, as the README gives it."""
    if checkout and platform_token == "windows":
        return r"git pull; powershell -ExecutionPolicy Bypass -File scripts\setup.ps1"
    if checkout:
        return "git pull && scripts/setup.sh"
    package = (
        "framewise-cull@latest"
        if platform_token == "macos"
        else '"framewise-cull[portable]@latest"'
    )
    return f"uvx --python 3.13 --from {package} framewise review"


def update_check_enabled(config_path: Path) -> bool:
    """Off with `check_for_updates = false` at the top of the config file, or with
    FRAMEWISE_NO_UPDATE_CHECK=1 in the environment."""
    if os.environ.get(OPT_OUT_VARIABLE, "") not in ("", "0"):
        return False
    try:
        with config_path.open("rb") as file:
            config = tomllib.load(file)
    except (OSError, tomllib.TOMLDecodeError):
        return True
    return config.get(CONFIG_KEY) is not False


@dataclass
class Update:
    version: str
    command: str
    releases: list[ChangelogVersion]
    """Every Release newer than the running one, newest first, filtered to the platform."""


class UpdateCheck:
    """Checks on a background thread from the moment it starts, so asking for its result waits
    at most for the fetch's timeout."""

    def __init__(
        self,
        platform_token: str,
        checkout: bool,
        fetch_changelog: FetchChangelog,
        clock: Clock,
        data_dir: Path,
        config_path: Path,
    ):
        self._platform_token = platform_token
        self._command = update_command(platform_token, checkout)
        self._fetch_changelog = fetch_changelog
        self._clock = clock
        self._cache_path = data_dir / CACHE_FILE_NAME
        self._update: Update | None = None
        self._done = threading.Event()
        if update_check_enabled(config_path):
            threading.Thread(target=self._run, daemon=True).start()
        else:
            self._done.set()

    def update(self) -> Update | None:
        self._done.wait(TIMEOUT_SECONDS)
        return self._update

    def _run(self) -> None:
        """Any failure, such as being offline or a Changelog out of shape, means no update, and
        the photographer is not told about it."""
        try:
            self._update = self._newer_release(self._main_changelog())
        except Exception:
            self._update = None
        finally:
            self._done.set()

    def _main_changelog(self) -> str:
        """The Changelog fetched within the last day, or a fresh fetch, remembered for a day."""
        now = self._clock()
        try:
            cached = json.loads(self._cache_path.read_text(encoding="utf-8"))
            if 0 <= now - cached["fetched_at"] < CACHE_SECONDS:
                return cached["changelog"]
        except (OSError, ValueError, KeyError, TypeError):
            pass
        changelog = self._fetch_changelog()
        try:
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            self._cache_path.write_text(
                json.dumps({"fetched_at": now, "changelog": changelog}), encoding="utf-8"
            )
        except OSError:
            pass
        return changelog

    def _newer_release(self, changelog: str) -> Update | None:
        running = semver(version("framewise-cull"))
        newer = [
            entry
            for entry in parse_changelog(changelog)
            if entry.version is not None and semver(entry.version) > running
        ]
        releases = for_platform(newer, self._platform_token)
        if not any(entry.sections for entry in releases):
            return None
        return Update(newer[0].version, self._command, releases)
