from dataclasses import dataclass, field
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFilter

from framewise.analyzer import SimilarityThresholds
from framewise.providers import (
    MissingCapabilityError,
    ProviderConfigError,
    compose_analyzer,
    discover_providers,
    read_provider_overrides,
    select_providers,
)


def draw_frame(path: Path) -> Path:
    """A checkerboard, crisp on the left half and blurred on the right."""
    image = Image.new("L", (800, 600), 128)
    draw = ImageDraw.Draw(image)
    for top in range(0, 600, 20):
        for left in range(0, 800, 20):
            if (top + left) // 20 % 2:
                draw.rectangle((left, top, left + 19, top + 19), fill=40)
    blurred = image.crop((400, 0, 800, 600)).filter(ImageFilter.GaussianBlur(6))
    image.paste(blurred, (400, 0))
    image.save(path, "JPEG", quality=95)
    return path


@dataclass
class FakeProvider:
    capability: str
    id: str
    priority: int = 0
    available: bool = True
    version: int = 1

    def is_available(self) -> bool:
        return self.available


@dataclass
class FakeFingerprint(FakeProvider):
    capability: str = "fingerprint"
    id: str = "fake-fingerprint"
    similarity: SimilarityThresholds = SimilarityThresholds(burst=0.8, near_duplicate=0.9)

    def fingerprint(self, jpg_path: Path) -> list[float]:
        return [float(len(self.id))]


def test_each_capability_uses_its_highest_priority_available_provider(tmp_path):
    frame = draw_frame(tmp_path / "frame.jpg")
    analyzer = compose_analyzer(
        [
            FakeFingerprint(id="low", priority=1),
            FakeFingerprint(id="unavailable-top", priority=9, available=False),
            FakeFingerprint(id="chosen", priority=5),
        ]
    )

    assert analyzer.analyze(frame).fingerprint == [float(len("chosen"))]


def test_without_an_available_fingerprint_provider_framewise_refuses_to_start():
    with pytest.raises(MissingCapabilityError, match="fingerprint"):
        compose_analyzer([FakeFingerprint(available=False)])


CRISP_BOX = (0.1, 0.2, 0.3, 0.4)
BLURRED_BOX = (0.6, 0.2, 0.3, 0.4)
TINY_BOX = (0.45, 0.5, 0.01, 0.01)


@dataclass
class FakeFaceDetection(FakeProvider):
    capability: str = "face-detection"
    id: str = "fake-face-detection"
    boxes: list = field(default_factory=lambda: [CRISP_BOX, BLURRED_BOX])

    def detect_faces(self, jpg_path: Path) -> list:
        return self.boxes


@dataclass
class FakeEyeState(FakeProvider):
    capability: str = "eye-state"
    id: str = "fake-eye-state"
    received: list = field(default_factory=list)

    def eyes_open(self, jpg_path: Path, faces: list) -> list:
        self.received.append(faces)
        return [face[0] < 0.5 for face in faces]


@dataclass
class FakeFaceQuality(FakeProvider):
    capability: str = "face-quality"
    id: str = "fake-face-quality"
    received: list = field(default_factory=list)

    def face_quality(self, jpg_path: Path, faces: list) -> list:
        self.received.append(faces)
        return [face[0] for face in faces]


@dataclass
class FakeAesthetics(FakeProvider):
    capability: str = "aesthetics"
    id: str = "fake-aesthetics"

    def aesthetics(self, jpg_path: Path) -> float | None:
        return 0.25


def full_stack() -> list:
    return [
        FakeFingerprint(),
        FakeFaceDetection(),
        FakeEyeState(),
        FakeFaceQuality(),
        FakeAesthetics(),
    ]


def without(capability: str) -> list:
    return [provider for provider in full_stack() if provider.capability != capability]


def test_the_detectors_boxes_reach_the_eye_state_and_face_quality_providers(tmp_path):
    frame = draw_frame(tmp_path / "frame.jpg")
    eye_state, face_quality = FakeEyeState(), FakeFaceQuality()
    providers = [FakeFingerprint(), FakeFaceDetection(), eye_state, face_quality, FakeAesthetics()]

    signals = compose_analyzer(providers).analyze(frame)

    assert eye_state.received == [[CRISP_BOX, BLURRED_BOX]]
    assert face_quality.received == [[CRISP_BOX, BLURRED_BOX]]
    assert [(face.x, face.y, face.width, face.height) for face in signals.faces] == [
        CRISP_BOX,
        BLURRED_BOX,
    ]
    assert [face.eyes_open for face in signals.faces] == [True, False]
    assert [face.quality for face in signals.faces] == [0.1, 0.6]
    assert signals.aesthetics == 0.25


def test_per_face_sharpness_is_measured_inside_the_detectors_boxes(tmp_path):
    frame = draw_frame(tmp_path / "frame.jpg")

    crisp, blurred = compose_analyzer(full_stack()).analyze(frame).faces

    assert crisp.sharpness > 0.8
    assert blurred.sharpness < 0.2


def test_faces_too_small_to_measure_are_left_out(tmp_path):
    frame = draw_frame(tmp_path / "frame.jpg")
    providers = without("face-detection") + [FakeFaceDetection(boxes=[TINY_BOX, CRISP_BOX])]

    faces = compose_analyzer(providers).analyze(frame).faces

    assert [(face.x, face.y, face.width, face.height) for face in faces] == [CRISP_BOX]


def test_without_face_detection_a_frame_has_no_faces(tmp_path):
    frame = draw_frame(tmp_path / "frame.jpg")
    assert compose_analyzer(without("face-detection")).analyze(frame).faces == []


def test_without_eye_state_the_eyes_are_unknown(tmp_path):
    frame = draw_frame(tmp_path / "frame.jpg")
    providers = without("eye-state") + [FakeEyeState(available=False)]

    faces = compose_analyzer(providers).analyze(frame).faces

    assert [face.eyes_open for face in faces] == [None, None]


def test_without_face_quality_the_quality_is_none(tmp_path):
    frame = draw_frame(tmp_path / "frame.jpg")
    faces = compose_analyzer(without("face-quality")).analyze(frame).faces

    assert [face.quality for face in faces] == [None, None]


def test_without_aesthetics_the_score_is_none(tmp_path):
    frame = draw_frame(tmp_path / "frame.jpg")
    assert compose_analyzer(without("aesthetics")).analyze(frame).aesthetics is None


def test_the_signature_names_the_provider_and_version_serving_each_capability():
    analyzer = compose_analyzer([FakeFingerprint(version=3), FakeEyeState()])

    assert analyzer.signature == {
        "fingerprint": "fake-fingerprint@3",
        "eye-state": "fake-eye-state@1",
    }


@dataclass
class FakeEntryPoint:
    name: str
    target: object

    def load(self):
        if isinstance(self.target, Exception):
            raise self.target
        return self.target


def test_providers_are_discovered_through_entry_points():
    entry_points = [
        FakeEntryPoint("fingerprint", lambda: FakeFingerprint(id="from-entry-point")),
        FakeEntryPoint("eye-state", FakeEyeState),
        FakeEntryPoint("broken", ImportError("missing dependency")),
    ]

    providers = discover_providers(entry_points)

    assert [provider.id for provider in providers] == ["from-entry-point", "fake-eye-state"]


@dataclass
class BrokenFingerprint(FakeFingerprint):
    id: str = "broken"
    priority: int = 9

    def is_available(self) -> bool:
        raise OSError("cannot probe")


def test_a_provider_whose_availability_check_raises_counts_as_unavailable(tmp_path):
    frame = draw_frame(tmp_path / "frame.jpg")
    analyzer = compose_analyzer([BrokenFingerprint(), FakeFingerprint(id="fallback")])

    assert analyzer.analyze(frame).fingerprint == [float(len("fallback"))]


def test_an_override_wins_over_the_higher_priority_default():
    providers = without("eye-state") + [
        FakeEyeState(id="default", priority=9),
        FakeEyeState(id="chosen", priority=1),
    ]

    chosen = select_providers(providers, {"eye-state": "chosen"})

    assert chosen["eye-state"].id == "chosen"
    assert chosen["fingerprint"].id == "fake-fingerprint"


def test_overriding_with_an_unknown_provider_is_an_error():
    with pytest.raises(
        ProviderConfigError, match='the eye-state Provider "mediapipe" is not installed'
    ):
        select_providers(full_stack(), {"eye-state": "mediapipe"})


def test_overriding_with_an_unavailable_provider_is_an_error():
    providers = without("eye-state") + [FakeEyeState(id="mediapipe", available=False)]

    with pytest.raises(
        ProviderConfigError,
        match='the eye-state Provider "mediapipe" is not available on this machine',
    ):
        select_providers(providers, {"eye-state": "mediapipe"})


def test_overriding_an_unknown_capability_is_an_error():
    with pytest.raises(ProviderConfigError, match='unknown Capability "eyes"'):
        select_providers(full_stack(), {"eyes": "fake-eye-state"})


def test_the_config_file_chooses_the_providers(tmp_path):
    frame = draw_frame(tmp_path / "frame.jpg")
    config = tmp_path / "config.toml"
    config.write_text('[providers]\nfingerprint = "chosen"\n')
    providers = [FakeFingerprint(id="default", priority=9), FakeFingerprint(id="chosen")]

    analyzer = compose_analyzer(providers, read_provider_overrides(config))

    assert analyzer.analyze(frame).fingerprint == [float(len("chosen"))]


def test_without_a_config_file_the_automatic_defaults_are_chosen(tmp_path):
    providers = full_stack() + [FakeEyeState(id="lower", priority=-1)]

    overrides = read_provider_overrides(tmp_path / "config.toml")

    assert overrides == {}
    assert select_providers(providers, overrides)["eye-state"].id == "fake-eye-state"


def test_a_config_file_that_is_not_toml_is_an_error(tmp_path):
    config = tmp_path / "config.toml"
    config.write_text("[providers\n")

    with pytest.raises(ProviderConfigError, match="invalid TOML"):
        read_provider_overrides(config)


def test_a_provider_id_that_is_not_a_string_is_an_error(tmp_path):
    config = tmp_path / "config.toml"
    config.write_text("[providers]\neye-state = 3\n")

    with pytest.raises(ProviderConfigError, match="eye-state"):
        read_provider_overrides(config)
