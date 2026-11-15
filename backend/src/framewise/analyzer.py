from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

# Bump whenever the built-in image maths or the shape of FrameSignals changes, so a re-run
# re-analyses Frames whose saved analysis predates it. A Provider's own changes are covered by
# its version, in the ProviderSignature.
ANALYSIS_VERSION = 5

ProviderSignature = Mapping[str, str]
"""The Provider that served each Capability of an analysis, as "<id>@<version>" by Capability."""

ProviderSource = Literal["automatic", "config"]


@dataclass(frozen=True)
class ActiveProvider:
    id: str
    version: int
    source: ProviderSource
    """Whether it was picked as the highest-priority available Provider or chosen in the config."""


@dataclass(frozen=True)
class AlternativeProvider:
    id: str
    version: int
    available: bool
    """Whether it can run on this machine."""


@dataclass(frozen=True)
class CapabilityLineup:
    active: ActiveProvider | None
    """None where no Provider serves the Capability."""
    alternatives: tuple[AlternativeProvider, ...] = ()
    """The other installed Providers of the Capability, in descending priority."""


ProviderLineup = Mapping[str, CapabilityLineup]
"""What serves each Capability in the running analyzer, by Capability in the fixed order."""


@dataclass(frozen=True)
class SimilarityThresholds:
    """The fingerprint similarity from which two Frames belong in one Group. Each fingerprint
    Provider declares its own, because similarities from different Providers aren't comparable."""

    burst: float
    """For Frames captured within moments of each other."""
    near_duplicate: float
    """For Frames captured minutes apart, or without a capture time."""


@dataclass(frozen=True)
class Face:
    """One face the face detection Provider found in a Frame. Its box is a fraction of the
    Frame's width and height, measured from the top left."""

    x: float
    y: float
    width: float
    height: float
    eyes_open: bool | None
    """None where the eye state Provider could not tell, or there is none."""
    sharpness: float
    """Like the Frame's sharpness, measured on the face alone."""
    quality: float | None
    """The face quality Provider's score from 0 to 1, or None where it is unavailable."""


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
    """The aesthetics Provider's score from 0 to 1, or None where it is unavailable."""
    faces: list[Face]


class FrameAnalyzer(Protocol):
    signature: ProviderSignature
    """Saved with each analysis, so a re-run re-analyses the Frames whose Providers changed."""
    similarity: SimilarityThresholds
    lineup: ProviderLineup
    """Shown in the Review UI, so the photographer can see how new analyses are made."""

    def analyze(self, jpg_path: Path) -> FrameSignals: ...
