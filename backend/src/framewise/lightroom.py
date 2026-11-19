import os
import plistlib
import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


def lightroom_preferences(platform: str, environ: Mapping[str, str], home: Path) -> Path | None:
    """Where Lightroom Classic keeps its preferences, or None where it does not run."""
    if platform == "darwin":
        return home / "Library" / "Preferences" / "com.adobe.LightroomClassicCC7.plist"
    if platform == "win32":
        app_data = Path(environ.get("APPDATA") or home / "AppData" / "Roaming")
        return (
            app_data
            / "Adobe"
            / "Lightroom"
            / "Preferences"
            / "Lightroom Classic CC 7 Preferences.agprefs"
        )
    return None


LIGHTROOM_PREFERENCES = lightroom_preferences(sys.platform, os.environ, Path.home())
# Lightroom Classic keeps the names of the active color label set's labels in its preferences,
# as label1 to label5 in the order red, yellow, green, blue, purple.
COLORS = ("red", "yellow", "green", "blue", "purple")


@dataclass(frozen=True)
class LabelSet:
    red: str
    yellow: str
    green: str
    blue: str
    purple: str
    from_lightroom: bool

    def name(self, color: str) -> str:
        """The label name of a color, one of COLORS."""
        return getattr(self, color)


ENGLISH_DEFAULTS = LabelSet(
    red="Red", yellow="Yellow", green="Green", blue="Blue", purple="Purple", from_lightroom=False
)


def read_label_set(preferences: Path | None) -> LabelSet:
    """Reads the active color label set's names without changing Lightroom's preferences."""
    if preferences is None:
        return ENGLISH_DEFAULTS
    try:
        if preferences.suffix == ".agprefs":
            values = _read_agprefs(preferences.read_bytes())
        else:
            with preferences.open("rb") as file:
                values = plistlib.load(file)
    except (OSError, ValueError, plistlib.InvalidFileException):
        return ENGLISH_DEFAULTS
    names = [values.get(f"label{number}") for number in range(1, len(COLORS) + 1)]
    if not all(isinstance(name, str) and name for name in names):
        return ENGLISH_DEFAULTS
    return LabelSet(**dict(zip(COLORS, names, strict=True)), from_lightroom=True)


# On Windows, Lightroom Classic keeps its preferences as a Lua table, one `key = "value",` per
# line. Not yet checked against a preferences file from a real Windows machine.
_AGPREFS_STRING = re.compile(rb'^\s*(\w+)\s*=\s*"((?:[^"\\]|\\.)*)"', re.MULTILINE | re.DOTALL)
_LUA_ESCAPE = re.compile(rb"\\(\d{1,3}|.)", re.DOTALL)
_LUA_ESCAPES = {b"n": b"\n", b"t": b"\t", b"r": b"\r"}


def _read_agprefs(text: bytes) -> dict[str, str]:
    """The string values of an .agprefs file, by key."""
    return {
        key.decode("ascii"): _unescape_lua(value).decode("utf-8")
        for key, value in _AGPREFS_STRING.findall(text)
    }


def _unescape_lua(value: bytes) -> bytes:
    def unescape(match: re.Match[bytes]) -> bytes:
        escaped = match.group(1)
        if escaped.isdigit():
            return bytes([int(escaped)])
        return _LUA_ESCAPES.get(escaped, escaped)

    return _LUA_ESCAPE.sub(unescape, value)
