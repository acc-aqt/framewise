"""Analysis Providers: one interchangeable implementation per Capability, composed into a
FrameAnalyzer with the built-in image maths."""

import sys
import tomllib
from collections.abc import Callable, Iterable, Mapping
from functools import partial
from importlib.metadata import EntryPoint, entry_points
from pathlib import Path
from typing import Protocol

from PIL import Image

from framewise.analyzer import (
    ActiveProvider,
    AlternativeProvider,
    CapabilityLineup,
    Face,
    FrameSignals,
    ProviderLineup,
    ProviderSignature,
    SimilarityThresholds,
    Subject,
)
from framewise.exiftool import ExifTool, find_exiftool
from framewise.focus_point import read_focus_area
from framewise.image_measures import ImageMeasures, Region, measure_image

FINGERPRINT = "fingerprint"
FACE_DETECTION = "face-detection"
EYE_STATE = "eye-state"
FACE_QUALITY = "face-quality"
AESTHETICS = "aesthetics"
SUBJECT = "subject"
CAPABILITIES = (FINGERPRINT, FACE_DETECTION, EYE_STATE, FACE_QUALITY, AESTHETICS, SUBJECT)
ENTRY_POINT_GROUP = "framewise.providers"

FOCUS_POINT = "focus-point"
FOCUS_POINT_READER = "exiftool@1"
"""Names the focus point reader in the signature, so installing ExifTool re-analyzes Frames."""
FocusAreaReader = Callable[[Path], Region | None]
"""The area the camera focused on in a JPG, as displayed, or None where it recorded none."""


class ProviderError(RuntimeError):
    """The Providers cannot be composed into an analyzer."""


class MissingCapabilityError(ProviderError):
    """No available Provider for a mandatory Capability."""


class ProviderConfigError(ProviderError):
    """The Provider choices in the config cannot be honored."""


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
    similarity: SimilarityThresholds

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
    def face_quality(self, jpg_path: Path, faces: list[Region]) -> list[float | None]:
        """For each face, a score from 0 to 1, or None where it cannot tell."""
        ...


class AestheticsProvider(Provider, Protocol):
    def aesthetics(self, jpg_path: Path) -> float | None:
        """A score from 0 to 1, or None where it cannot tell."""
        ...


class SubjectProvider(Provider, Protocol):
    def subject_mask(self, jpg_path: Path) -> Image.Image | None:
        """A greyscale mask of the Frame's main subject, of any size, covering the Frame as it is
        displayed, after its EXIF orientation: 255 inside the subject, 0 outside it. None where
        it finds no subject."""
        ...


class ProviderAnalyzer:
    """Analyzes a Frame's Analysis source with one Provider per Capability and the built-in
    image maths. The face detection Provider alone decides which faces a Frame has; the eye
    state and face quality Providers and the image maths look inside its boxes. The image maths
    also measure the subject: the area the camera focused on, where `focus_area` finds one, else
    the subject Provider's mask."""

    def __init__(
        self,
        fingerprint: FingerprintProvider,
        face_detection: FaceDetectionProvider | None = None,
        eye_state: EyeStateProvider | None = None,
        face_quality: FaceQualityProvider | None = None,
        aesthetics: AestheticsProvider | None = None,
        subject: SubjectProvider | None = None,
        *,
        provider_lineup: ProviderLineup,
        focus_area: FocusAreaReader | None = None,
    ):
        self.fingerprint = fingerprint
        self.face_detection = face_detection
        self.eye_state = eye_state
        self.face_quality = face_quality
        self.aesthetics = aesthetics
        self.subject = subject
        self.provider_lineup = provider_lineup
        self.focus_area = focus_area

    @property
    def similarity(self) -> SimilarityThresholds:
        return self.fingerprint.similarity

    @property
    def signature(self) -> ProviderSignature:
        providers = (
            self.fingerprint,
            self.face_detection,
            self.eye_state,
            self.face_quality,
            self.aesthetics,
            self.subject,
        )
        signature = {
            provider.capability: f"{provider.id}@{provider.version}"
            for provider in providers
            if provider is not None
        }
        if self.focus_area is not None:
            signature[FOCUS_POINT] = FOCUS_POINT_READER
        return signature

    def analyze(self, jpg_path: Path) -> FrameSignals:
        boxes = self.face_detection.detect_faces(jpg_path) if self.face_detection else []
        focus_area = self.focus_area(jpg_path) if self.focus_area else None
        subject_mask = (
            self.subject.subject_mask(jpg_path) if self.subject and focus_area is None else None
        )
        measures = measure_image(jpg_path, boxes, focus_area, subject_mask)
        return FrameSignals(
            fingerprint=self.fingerprint.fingerprint(jpg_path),
            sharpness=measures.sharpness,
            motion_blur=measures.motion_blur,
            exposure_stops=measures.exposure_stops,
            low_key=measures.low_key,
            high_key=measures.high_key,
            aesthetics=self.aesthetics.aesthetics(jpg_path) if self.aesthetics else None,
            faces=self._faces(jpg_path, boxes, measures.face_sharpness),
            subject=_subject(focus_area, measures),
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


def _subject(focus_area: Region | None, measures: ImageMeasures) -> Subject | None:
    if focus_area is not None and measures.focus_sharpness is not None:
        return Subject(*focus_area, measures.focus_sharpness, found_by="focus-point")
    if measures.subject is not None:
        return Subject(*measures.subject.box, measures.subject.sharpness, found_by="subject-mask")
    return None


def resolve_analyzer(
    config_path: Path | None = None,
    overrides: Mapping[str, str] | None = None,
    providers: list[Provider] | None = None,
) -> ProviderAnalyzer:
    """The analyzer made of the installed Providers, framewise's own included, with the
    Providers chosen in the config file at config_path, if there is one. overrides, such as
    those given on the command line, win over the config file's."""
    installed = _check_availability(discover_providers() if providers is None else providers)
    overrides = dict(overrides or {})
    configured = read_provider_overrides(config_path) if config_path else {}
    still_configured = {
        capability: provider_id
        for capability, provider_id in configured.items()
        if capability not in overrides
    }
    try:
        _select(installed, still_configured)
    except ProviderConfigError as error:
        raise ProviderConfigError(f"{config_path}: {error}") from error
    exiftool = find_exiftool()
    focus_area = None if exiftool is None else partial(read_focus_area, ExifTool(exiftool))
    return _compose(installed, still_configured | overrides, focus_area)


def read_provider_overrides(config_path: Path) -> dict[str, str]:
    """The [providers] table of a config file, mapping Capability to Provider id. A missing
    file chooses nothing."""
    try:
        with config_path.open("rb") as file:
            config = tomllib.load(file)
    except FileNotFoundError:
        return {}
    except tomllib.TOMLDecodeError as error:
        raise ProviderConfigError(f"{config_path}: invalid TOML: {error}") from error
    overrides = config.get("providers", {})
    if not isinstance(overrides, dict):
        raise ProviderConfigError(f"{config_path}: [providers] must be a table")
    for capability, provider_id in overrides.items():
        if not isinstance(provider_id, str):
            raise ProviderConfigError(
                f"{config_path}: the {capability} Provider must be a Provider id in quotes"
            )
    return overrides


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


_Installed = list[tuple[Provider, bool]]
"""Each installed Provider with whether it is available, checked once so that a check that
raises warns only once."""


def compose_analyzer(
    providers: Iterable[Provider],
    overrides: Mapping[str, str] | None = None,
    focus_area: FocusAreaReader | None = None,
) -> ProviderAnalyzer:
    return _compose(_check_availability(providers), overrides or {}, focus_area)


def select_providers(
    providers: Iterable[Provider], overrides: Mapping[str, str] | None = None
) -> dict[str, Provider]:
    """The Provider that overrides names for a Capability, else the highest-priority available
    one."""
    return _select(_check_availability(providers), overrides or {})


def _check_availability(providers: Iterable[Provider]) -> _Installed:
    return [(provider, _is_available(provider)) for provider in providers]


def _compose(
    installed: _Installed,
    overrides: Mapping[str, str],
    focus_area: FocusAreaReader | None = None,
) -> ProviderAnalyzer:
    chosen = _select(installed, overrides)
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
        subject=chosen.get(SUBJECT),
        provider_lineup=_describe_provider_lineup(installed, chosen, overrides),
        focus_area=focus_area,
    )


def _describe_provider_lineup(
    installed: _Installed, chosen: Mapping[str, Provider], overrides: Mapping[str, str]
) -> ProviderLineup:
    lineup = {}
    for capability in CAPABILITIES:
        active = chosen.get(capability)
        lineup[capability] = CapabilityLineup(
            active=_active_provider(active, configured=capability in overrides),
            alternatives=_alternatives(installed, capability, active),
        )
    return lineup


def _alternatives(
    installed: _Installed, capability: str, active: Provider | None
) -> tuple[AlternativeProvider, ...]:
    others = [
        (provider, available)
        for provider, available in installed
        if provider.capability == capability and provider is not active
    ]
    others.sort(key=lambda pair: pair[0].priority, reverse=True)
    return tuple(
        AlternativeProvider(id=provider.id, version=provider.version, available=available)
        for provider, available in others
    )


def _active_provider(provider: Provider | None, configured: bool) -> ActiveProvider | None:
    if provider is None:
        return None
    return ActiveProvider(
        id=provider.id,
        version=provider.version,
        source="config" if configured else "automatic",
    )


def _select(installed: _Installed, overrides: Mapping[str, str]) -> dict[str, Provider]:
    chosen: dict[str, Provider] = {}
    for provider, available in installed:
        if not available:
            continue
        current = chosen.get(provider.capability)
        if current is None or provider.priority > current.priority:
            chosen[provider.capability] = provider
    for capability, provider_id in overrides.items():
        chosen[capability] = _overriding_provider(installed, capability, provider_id)
    return chosen


def _overriding_provider(installed: _Installed, capability: str, provider_id: str) -> Provider:
    if capability not in CAPABILITIES:
        raise ProviderConfigError(
            f'unknown Capability "{capability}", expected one of {", ".join(CAPABILITIES)}'
        )
    for provider, available in installed:
        if provider.capability == capability and provider.id == provider_id:
            if not available:
                raise ProviderConfigError(
                    f'the {capability} Provider "{provider_id}" is not available on this machine'
                )
            return provider
    raise ProviderConfigError(f'the {capability} Provider "{provider_id}" is not installed')


def _is_available(provider: Provider) -> bool:
    """Treats a Provider whose availability check raises, against its contract, as unavailable."""
    try:
        return provider.is_available()
    except Exception as error:
        print(f"framewise: warning: skipped the Provider {provider.id}: {error}", file=sys.stderr)
        return False
