from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

# Bump whenever FrameSignals gains or changes a signal, so a re-run re-analyses Frames whose
# saved analysis predates it.
ANALYSIS_VERSION = 2


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
    """Bright overall but with deep shadows, so deliberately bright rather than overexposed."""
    aesthetics: float | None
    """Apple Vision's overall aesthetics score from -1 to 1, or None where it is unavailable."""


class FrameAnalyzer(Protocol):
    def analyze(self, jpg_path: Path) -> FrameSignals: ...
