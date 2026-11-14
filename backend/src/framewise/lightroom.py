import plistlib
from dataclasses import dataclass
from pathlib import Path

LIGHTROOM_PREFERENCES = (
    Path.home() / "Library" / "Preferences" / "com.adobe.LightroomClassicCC7.plist"
)
# Lightroom Classic keeps the names of the active color label set's labels in its preferences,
# in the order red, yellow, green, blue, purple.
RED_KEY = "label1"
YELLOW_KEY = "label2"


@dataclass(frozen=True)
class LabelSet:
    red: str
    yellow: str
    from_lightroom: bool


ENGLISH_DEFAULTS = LabelSet(red="Red", yellow="Yellow", from_lightroom=False)


def read_label_set(preferences: Path | None) -> LabelSet:
    """Reads the active color label set's names without changing Lightroom's preferences."""
    if preferences is None:
        return ENGLISH_DEFAULTS
    try:
        with preferences.open("rb") as file:
            values = plistlib.load(file)
    except (OSError, plistlib.InvalidFileException):
        return ENGLISH_DEFAULTS
    red, yellow = values.get(RED_KEY), values.get(YELLOW_KEY)
    if not (isinstance(red, str) and red and isinstance(yellow, str) and yellow):
        return ENGLISH_DEFAULTS
    return LabelSet(red=red, yellow=yellow, from_lightroom=True)
