from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

# Bump whenever FrameSignals gains or changes a signal, so a re-run re-analyses Frames whose
# saved analysis predates it.
ANALYSIS_VERSION = 4


@dataclass(frozen=True)
class Face:
    """One face Apple Vision found in a Frame. Its box is a fraction of the Frame's width and
    height, measured from the top left."""

    x: float
    y: float
    width: float
    height: float
    eyes_open: bool | None
    """None where Apple Vision could not place the eyes."""
    sharpness: float
    """Like the Frame's sharpness, measured on the face alone."""
    quality: float | None
    """Apple Vision's face capture quality from 0 to 1, or None where it is unavailable."""


@dataclass(frozen=True)
class FrameSignals:
    fingerprint: list[float]
    sharpness: float
    """0 for a completely blurred Frame, 1 for crisp edges."""
    motion_blur: float
    """0 when the Frame is equally sharp in every direction, towards 1 when it is smeared along
    one direction."""
    exposure_stops: float
    """How far the Frame is over (positive) or under (negative) a mid-grey exposure."""
    low_key: bool
    """Dark overall but with bright highlights, so deliberately dark rather than underexposed."""
    high_key: bool
    """Bright overall but with its highlights intact, so deliberately bright rather than
    overexposed. With faces, only the faces' highlights count, so a person against a blown-out
    white wall is high key."""
    aesthetics: float | None
    """Apple Vision's overall aesthetics score from -1 to 1, or None where it is unavailable."""
    faces: list[Face]


class FrameAnalyzer(Protocol):
    def analyze(self, jpg_path: Path) -> FrameSignals: ...
