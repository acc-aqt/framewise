from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

# Bump whenever the built-in image maths or the shape of FrameSignals changes, so a re-run
# re-analyzes Frames whose saved analysis predates it. A Provider's own changes are covered by
# its version, in the ProviderSignature.
ANALYSIS_VERSION = 9

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


@dataclass(frozen=True)
class CapabilityLineup:
    active: ActiveProvider | None
    """None where no Provider serves the Capability."""
    alternatives: tuple[AlternativeProvider, ...] = ()
    """The other installed Providers of the Capability, in descending priority."""


ProviderLineup = Mapping[str, CapabilityLineup]
"""What serves each Capability in new analyses, keyed by Capability in the order to show them."""


@dataclass(frozen=True)
class SimilarityThresholds:
    """The fingerprint similarity from which two Frames belong in one Group. Each fingerprint
    Provider declares its own, because similarities from different Providers aren't comparable."""

    burst: float
    """For Frames captured within moments of each other."""
    near_duplicate: float
    """For Frames captured minutes apart, or without a capture time."""


@dataclass(frozen=True)
class Expression:
    """How a face looks, as the expression Provider reads it."""

    smile: float | None
    """From 0 for a neutral or downturned mouth to 1 for a broad smile, or None where the
    Provider cannot tell."""
    looking: float | None = None
    """From 0 for eyes looking fully aside to 1 for eyes looking into the lens, or None where the
    Provider cannot tell. It is the gaze from the camera, whatever the head does: a head turned
    away whose eyes look back into the lens scores high. A Provider that reads gaze relative to
    the head, as MediaPipe's blendshapes do, adds the head's turn to it."""
    facing: float | None = None
    """From 0 for a head turned fully away to 1 for a head facing the camera, or None where the
    Provider cannot tell."""


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
    expression: Expression | None
    """None where the expression Provider could not read the face, or there is none."""


SubjectSource = Literal["focus-point", "subject-mask"]


@dataclass(frozen=True)
class Subject:
    """The part of a Frame that matters most, as a box measured like a face's. Frames without
    faces are judged on it rather than on the whole Frame."""

    x: float
    y: float
    width: float
    height: float
    sharpness: float
    """Like the Frame's sharpness, measured on the subject alone."""
    found_by: SubjectSource
    """"focus-point" where the camera recorded the area it focused on, else "subject-mask" where
    the subject Provider found the Frame's main subject. A subject mask's box is the box around
    it, but its sharpness is measured on the mask alone."""


@dataclass(frozen=True)
class FrameSignals:
    fingerprint: list[float]
    sharpness: float
    """0 for a completely blurred Frame, 1 for crisp edges."""
    motion_blur: float
    """0 when the Frame is equally sharp in every direction, towards 1 when it is smeared along
    one direction."""
    exposure_stops: float
    """How far the Frame is over (positive) or under (negative) a mid-gray exposure."""
    low_key: bool
    """Dark overall but with bright highlights that aren't clipped, such as a lit face, so
    deliberately dark rather than underexposed. A blown-out lamp or screen alone doesn't count."""
    high_key: bool
    """Bright overall but with its highlights intact, so deliberately bright rather than
    overexposed. With faces, only the faces' highlights count, so a person against a blown-out
    white wall is high key."""
    aesthetics: float | None
    """The aesthetics Provider's score from 0 to 1, or None where it is unavailable."""
    faces: list[Face]
    subject: Subject | None = None
    """None where framewise can't tell where the subject is."""


class FrameAnalyzer(Protocol):
    signature: ProviderSignature
    """Saved with each analysis, so a re-run re-analyzes the Frames whose Providers changed."""
    similarity: SimilarityThresholds
    provider_lineup: ProviderLineup
    """Shown in the Review UI, so the photographer can see how new analyses are made."""

    def analyze(self, jpg_path: Path) -> FrameSignals: ...
