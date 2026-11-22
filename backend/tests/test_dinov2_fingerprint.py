import platform
import shutil
import sys
from pathlib import Path

import pytest
from conftest import review_app
from test_apple_vision import a_moment_later, draw_landscape, draw_still_life, similarity
from test_groups_api import group_paths
from test_verdicts_api import frames_by_name, reasons

from framewise import onnx_runtime
from framewise.apple_vision import PRIORITY
from framewise.dinov2_fingerprint import DinoV2Fingerprint
from framewise.mediapipe_faces import MediaPipeEyeState, MediaPipeFaceDetection
from framewise.models import DINOV2_SMALL, FACE_LANDMARKER, is_verified
from framewise.providers import compose_analyzer, discover_providers, select_providers
from framewise.review import SessionAnalysis, open_session, resolve_data_dir

FACES = Path(__file__).parent / "fixtures" / "faces"

needs_portable_models = pytest.mark.skipif(
    not (
        DinoV2Fingerprint().is_available()
        and MediaPipeFaceDetection().is_available()
        and all(is_verified(model, resolve_data_dir()) for model in (DINOV2_SMALL, FACE_LANDMARKER))
    ),
    reason="needs framewise-cull[portable] and its models, from `framewise models download`",
)


@needs_portable_models
def test_near_identical_frames_are_near_duplicates_and_unrelated_frames_are_not(tmp_path):
    provider = DinoV2Fingerprint()
    landscape = draw_landscape(tmp_path / "landscape.jpg")
    landscape_again = a_moment_later(landscape, tmp_path / "landscape-again.jpg")
    still_life = draw_still_life(tmp_path / "still-life.jpg")

    near_identical = similarity(
        provider.fingerprint(landscape), provider.fingerprint(landscape_again)
    )
    unrelated = similarity(provider.fingerprint(landscape), provider.fingerprint(still_life))

    assert near_identical >= provider.similarity.near_duplicate > unrelated


@needs_portable_models
def test_a_session_analysed_only_with_portable_providers_gets_a_proposal(session_dir, data_dir):
    landscape = draw_landscape(session_dir / "DSCF0001.JPG")
    a_moment_later(landscape, session_dir / "DSCF0002.JPG")
    draw_still_life(session_dir / "DSCF0003.JPG")
    shutil.copy(FACES / "eyes-closed.jpg", session_dir / "DSCF0004.JPG")
    store = open_session(session_dir, data_dir)
    analyzer = compose_analyzer(
        [DinoV2Fingerprint(), MediaPipeFaceDetection(), MediaPipeEyeState()]
    )
    analysis = SessionAnalysis(store, analyzer)
    analysis.run()

    client = review_app(store, analysis)
    frames = frames_by_name(client)

    assert group_paths(client) == [
        ["DSCF0001.JPG", "DSCF0002.JPG"],
        ["DSCF0003.JPG"],
        ["DSCF0004.JPG"],
    ]
    landscape_verdicts = [frames[name]["verdict"] for name in ("DSCF0001.JPG", "DSCF0002.JPG")]
    assert landscape_verdicts.count("winner") == 1
    assert frames["DSCF0003.JPG"]["verdict"] == "winner"
    assert reasons(frames["DSCF0004.JPG"]) == ["Eyes closed"]


@pytest.mark.parametrize(("macos", "available"), [("13.6.1", False), ("14.0", True), ("", False)])
def test_on_macos_the_provider_needs_macos_14(monkeypatch, macos, available):
    monkeypatch.setattr(onnx_runtime, "onnxruntime", object())
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(platform, "mac_ver", lambda: (macos, ("", "", ""), ""))

    assert DinoV2Fingerprint().is_available() is available


def test_framewise_registers_its_dinov2_fingerprint_below_apple_vision():
    providers = {provider.id: provider for provider in discover_providers()}
    chosen = select_providers(providers.values())

    assert providers["dinov2-small-fingerprint"].priority < PRIORITY
    expected = "apple-vision" if sys.platform == "darwin" else "dinov2-small"
    assert chosen["fingerprint"].id == f"{expected}-fingerprint"
