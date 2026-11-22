import platform
import sys
from pathlib import Path

import pytest
from test_apple_vision import FIXTURE_FACE_BOX, gaussian_blurred, portrait, side_by_side

from framewise import ediffiqa_face_quality
from framewise.apple_vision import PRIORITY, AppleFaceQuality
from framewise.ediffiqa_face_quality import EDifFIQAFaceQuality
from framewise.models import EDIFFIQA_TINY, FACE_LANDMARKER, is_verified
from framewise.providers import discover_providers, select_providers
from framewise.review import resolve_data_dir

FACES = Path(__file__).parent / "fixtures" / "faces"

needs_portable_models = pytest.mark.skipif(
    not (
        EDifFIQAFaceQuality().is_available()
        and all(
            is_verified(model, resolve_data_dir()) for model in (EDIFFIQA_TINY, FACE_LANDMARKER)
        )
    ),
    reason="needs framewise-cull[portable] and its models, from `framewise models download`",
)


@needs_portable_models
@pytest.mark.parametrize("face", sorted(FACES.glob("*.jpg")), ids=lambda path: path.stem)
def test_each_reference_face_gets_a_quality_from_zero_to_one(face):
    [quality] = EDifFIQAFaceQuality().face_quality(face, [FIXTURE_FACE_BOX])

    assert quality is not None and 0 <= quality <= 1


@needs_portable_models
def test_a_blurred_face_has_a_lower_quality(tmp_path):
    provider = EDifFIQAFaceQuality()
    blurred = gaussian_blurred(FACES / "eyes-open.jpg", tmp_path / "blurred.jpg")

    [sharp_quality] = provider.face_quality(FACES / "eyes-open.jpg", [FIXTURE_FACE_BOX])
    [blurred_quality] = provider.face_quality(blurred, [FIXTURE_FACE_BOX])

    assert sharp_quality > 0.6
    assert sharp_quality - blurred_quality > 0.3


@needs_portable_models
def test_a_box_without_a_face_has_no_quality(tmp_path):
    frame = portrait(tmp_path / "portrait.jpg", background=200)
    face_box = (64 / 768 + 0.28 / 3, 128 / 512 + 0.27 / 2, 0.42 / 3, 0.42 / 2)
    wall_box = (0.7, 0.2, 0.15, 0.2)

    face_quality, wall_quality = EDifFIQAFaceQuality().face_quality(frame, [face_box, wall_box])

    assert face_quality is not None and wall_quality is None


@needs_portable_models
def test_each_face_in_a_group_shot_keeps_its_own_quality(tmp_path):
    sharp = FACES / "eyes-open.jpg"
    blurred = gaussian_blurred(sharp, tmp_path / "blurred.jpg")
    group_shot = side_by_side([sharp, blurred, sharp], tmp_path / "group-shot.jpg")
    x, y, width, height = FIXTURE_FACE_BOX
    boxes = [((index + x) / 3, y, width / 3, height) for index in range(3)]

    qualities = EDifFIQAFaceQuality().face_quality(group_shot, boxes)

    assert qualities[1] < qualities[0] - 0.3 and qualities[1] < qualities[2] - 0.3


@pytest.mark.parametrize(("macos", "available"), [("13.6.1", False), ("14.0", True)])
def test_on_macos_the_provider_needs_macos_14(monkeypatch, macos, available):
    monkeypatch.setattr(ediffiqa_face_quality, "onnxruntime", object())
    monkeypatch.setattr(ediffiqa_face_quality.mediapipe_faces, "mediapipe", object())
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(platform, "mac_ver", lambda: (macos, ("", "", ""), ""))

    assert EDifFIQAFaceQuality().is_available() is available


def test_without_mediapipe_the_provider_is_unavailable(monkeypatch):
    monkeypatch.setattr(ediffiqa_face_quality, "onnxruntime", object())
    monkeypatch.setattr(ediffiqa_face_quality.mediapipe_faces, "mediapipe", None)
    monkeypatch.setattr(sys, "platform", "linux")

    assert EDifFIQAFaceQuality().is_available() is False


def test_framewise_registers_its_ediffiqa_face_quality_below_apple_vision():
    providers = {provider.id: provider for provider in discover_providers()}
    chosen = select_providers(providers.values())

    assert providers["ediffiqa-face-quality"].priority < PRIORITY
    if AppleFaceQuality().is_available():
        assert chosen["face-quality"].id == "apple-vision-face-quality"
    elif EDifFIQAFaceQuality().is_available():
        assert chosen["face-quality"].id == "ediffiqa-face-quality"
