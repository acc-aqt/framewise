import plistlib
from dataclasses import dataclass
from pathlib import Path

LIGHTROOM_PREFERENCES = (
    Path.home() / "Library" / "Preferences" / "com.adobe.LightroomClassicCC7.plist"
)
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
        with preferences.open("rb") as file:
            values = plistlib.load(file)
    except (OSError, plistlib.InvalidFileException):
        return ENGLISH_DEFAULTS
    names = [values.get(f"label{number}") for number in range(1, len(COLORS) + 1)]
    if not all(isinstance(name, str) and name for name in names):
        return ENGLISH_DEFAULTS
    return LabelSet(**dict(zip(COLORS, names, strict=True)), from_lightroom=True)
