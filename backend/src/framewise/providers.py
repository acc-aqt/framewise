"""Analysis Providers: one interchangeable implementation per Capability, composed into a
FrameAnalyzer with the built-in image maths."""

import sys
from collections.abc import Iterable
from importlib.metadata import EntryPoint, entry_points
from pathlib import Path
from typing import Protocol

from framewise.analyzer import Face, FrameSignals, ProviderSignature
from framewise.image_measures import Region, measure_image

FINGERPRINT = "fingerprint"
FACE_DETECTION = "face-detection"
EYE_STATE = "eye-state"
FACE_QUALITY = "face-quality"
AESTHETICS = "aesthetics"
CAPABILITIES = (FINGERPRINT, FACE_DETECTION, EYE_STATE, FACE_QUALITY, AESTHETICS)
ENTRY_POINT_GROUP = "framewise.providers"


class MissingCapabilityError(RuntimeError):
    """No available Provider for a mandatory Capability."""


class Provider(Protocol):
    capability: str
    id: str
    """Stable across releases, so a saved analysis can name the Provider that made it."""
    version: int
    """Bumped whenever the Provider's output may change."""
    priority: int
    """The highest-priority available Provider of a Capability is chosen by default."""

    def is_available(self) -> bool:
        """Whether it can run here. Never raises."""
        ...


class FingerprintProvider(Provider, Protocol):
    def fingerprint(self, jpg_path: Path) -> list[float]: ...


class FaceDetectionProvider(Provider, Protocol):
    def detect_faces(self, jpg_path: Path) -> list[Region]:
        """Boxes as fractions of the Frame as it is displayed, after its EXIF orientation,
        measured from the top left."""
        ...


class EyeStateProvider(Provider, Protocol):
    def eyes_open(self, jpg_path: Path, faces: list[Region]) -> list[bool | None]:
        """For each face, whether its eyes are open, or None where it cannot tell."""
        ...


class FaceQualityProvider(Provider, Protocol):
    def face_quality(self, jpg_path: Path, faces: list[Region]) -> list[float | None]: ...


class AestheticsProvider(Provider, Protocol):
    def aesthetics(self, jpg_path: Path) -> float | None: ...


class ProviderAnalyzer:
    """Analyses a Frame's Analysis source with one Provider per Capability and the built-in
    image maths. The face detection Provider alone decides which faces a Frame has; the eye
    state and face quality Providers and the image maths look inside its boxes."""

    def __init__(
        self,
        fingerprint: FingerprintProvider,
        face_detection: FaceDetectionProvider | None = None,
        eye_state: EyeStateProvider | None = None,
        face_quality: FaceQualityProvider | None = None,
        aesthetics: AestheticsProvider | None = None,
    ):
        self.fingerprint = fingerprint
        self.face_detection = face_detection
        self.eye_state = eye_state
        self.face_quality = face_quality
        self.aesthetics = aesthetics

    @property
    def signature(self) -> ProviderSignature:
        providers = (
            self.fingerprint,
            self.face_detection,
            self.eye_state,
            self.face_quality,
            self.aesthetics,
        )
        return {
            provider.capability: f"{provider.id}@{provider.version}"
            for provider in providers
            if provider is not None
        }

    def analyze(self, jpg_path: Path) -> FrameSignals:
        boxes = self.face_detection.detect_faces(jpg_path) if self.face_detection else []
        measures = measure_image(jpg_path, boxes)
        return FrameSignals(
            fingerprint=self.fingerprint.fingerprint(jpg_path),
            sharpness=measures.sharpness,
            motion_blur=measures.motion_blur,
            exposure_stops=measures.exposure_stops,
            low_key=measures.low_key,
            high_key=measures.high_key,
            aesthetics=self.aesthetics.aesthetics(jpg_path) if self.aesthetics else None,
            faces=self._faces(jpg_path, boxes, measures.face_sharpness),
        )

    def _faces(
        self, jpg_path: Path, boxes: list[Region], sharpness: list[float | None]
    ) -> list[Face]:
        """Leaves out faces too small to measure, such as distant passers-by."""
        unknown_per_face: list = [None] * len(boxes)
        eyes = (
            self.eye_state.eyes_open(jpg_path, boxes)
            if self.eye_state and boxes
            else unknown_per_face
        )
        quality = (
            self.face_quality.face_quality(jpg_path, boxes)
            if self.face_quality and boxes
            else unknown_per_face
        )
        return [
            Face(*box, eyes_open=open_eyes, sharpness=face_sharpness, quality=face_quality)
            for box, open_eyes, face_sharpness, face_quality in zip(
                boxes, eyes, sharpness, quality, strict=True
            )
            if face_sharpness is not None
        ]


def resolve_analyzer() -> ProviderAnalyzer:
    """The analyzer made of the installed Providers, framewise's own included."""
    return compose_analyzer(discover_providers())


def discover_providers(found: Iterable[EntryPoint] | None = None) -> list[Provider]:
    """Creates a Provider from each entry point in the framewise.providers group. Each names a
    class or function that takes no arguments. One that fails to load is skipped with a
    warning, so a broken plug-in cannot stop framewise."""
    if found is None:
        found = entry_points(group=ENTRY_POINT_GROUP)
    providers = []
    for entry_point in found:
        try:
            providers.append(entry_point.load()())
        except Exception as error:
            print(
                f"framewise: warning: skipped the Provider {entry_point.name}: {error}",
                file=sys.stderr,
            )
    return providers


def compose_analyzer(providers: Iterable[Provider]) -> ProviderAnalyzer:
    chosen = select_providers(providers)
    if FINGERPRINT not in chosen:
        raise MissingCapabilityError(
            f"no available Provider for the {FINGERPRINT} Capability, which framewise needs "
            "to group Frames"
        )
    return ProviderAnalyzer(
        fingerprint=chosen[FINGERPRINT],
        face_detection=chosen.get(FACE_DETECTION),
        eye_state=chosen.get(EYE_STATE),
        face_quality=chosen.get(FACE_QUALITY),
        aesthetics=chosen.get(AESTHETICS),
    )


def select_providers(providers: Iterable[Provider]) -> dict[str, Provider]:
    """The highest-priority available Provider of each Capability."""
    chosen: dict[str, Provider] = {}
    for provider in providers:
        if not _is_available(provider):
            continue
        current = chosen.get(provider.capability)
        if current is None or provider.priority > current.priority:
            chosen[provider.capability] = provider
    return chosen


def _is_available(provider: Provider) -> bool:
    """Treats a Provider whose availability check raises, against its contract, as unavailable."""
    try:
        return provider.is_available()
    except Exception as error:
        print(f"framewise: warning: skipped the Provider {provider.id}: {error}", file=sys.stderr)
        return False
