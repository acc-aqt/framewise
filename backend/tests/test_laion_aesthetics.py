import platform
import sys
from pathlib import Path

import pytest
from PIL import Image
from test_apple_vision import gaussian_blurred

from framewise import apple_vision, clip_image
from framewise.apple_vision import AppleAesthetics
from framewise.laion_aesthetics import LaionAesthetics
from framewise.models import CLIP_VIT_B_32_IMAGE, LAION_AESTHETICS_VIT_B_32, is_verified
from framewise.providers import discover_providers, select_providers
from framewise.review import resolve_data_dir

FACES = Path(__file__).parent / "fixtures" / "faces"

needs_portable_models = pytest.mark.skipif(
    not (
        LaionAesthetics().is_available()
        and all(
            is_verified(model, resolve_data_dir())
            for model in (CLIP_VIT_B_32_IMAGE, LAION_AESTHETICS_VIT_B_32)
        )
    ),
    reason="needs framewise-cull[portable] and its models, from `framewise models download`",
)


@needs_portable_models
def test_a_blurred_frame_scores_lower_than_the_sharp_one(tmp_path):
    provider = LaionAesthetics()
    sharp = FACES / "eyes-open.jpg"
    blurred = gaussian_blurred(sharp, tmp_path / "blurred.jpg")

    assert 0 <= provider.aesthetics(blurred) < provider.aesthetics(sharp) <= 1


@needs_portable_models
def test_a_flat_grey_frame_scores_lower_than_a_portrait(tmp_path):
    provider = LaionAesthetics()
    grey = tmp_path / "grey.jpg"
    Image.new("RGB", (640, 480), (128, 128, 128)).save(grey, "JPEG", quality=90)

    assert provider.aesthetics(grey) < provider.aesthetics(FACES / "neutral.jpg")


@needs_portable_models
@pytest.mark.parametrize("face", sorted(path.name for path in FACES.glob("*.jpg")))
def test_every_reference_face_scores_from_zero_to_one(face):
    assert 0 <= LaionAesthetics().aesthetics(FACES / face) <= 1


def test_framewise_registers_its_laion_aesthetics_below_apple_vision():
    providers = {provider.id: provider for provider in discover_providers()}
    chosen = select_providers(providers.values())

    assert providers["laion-aesthetics"].priority < apple_vision.PRIORITY
    if AppleAesthetics().is_available():
        assert chosen["aesthetics"].id == "apple-vision-aesthetics"
    elif LaionAesthetics().is_available():
        assert chosen["aesthetics"].id == "laion-aesthetics"


@pytest.mark.parametrize(("macos", "available"), [("13.6.1", False), ("14.0", True), ("", False)])
def test_on_macos_the_provider_needs_macos_14(monkeypatch, macos, available):
    monkeypatch.setattr(clip_image, "onnxruntime", object())
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(platform, "mac_ver", lambda: (macos, ("", "", ""), ""))

    assert LaionAesthetics().is_available() is available
