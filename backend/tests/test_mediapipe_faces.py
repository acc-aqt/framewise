import shutil
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_apple_vision import (
    FIXTURE_FACE_BOX,
    draw_landscape,
    portrait,
    side_by_side,
    stored_rotated,
)
from test_groups_api import BEACH, ScriptedFingerprint
from test_verdicts_api import frames_by_name, reasons

from framewise.analyzer import SimilarityThresholds
from framewise.apple_vision import PRIORITY
from framewise.mediapipe_faces import MediaPipeEyeState, MediaPipeFaceDetection
from framewise.models import FACE_LANDMARKER, is_verified
from framewise.providers import compose_analyzer, discover_providers, select_providers
from framewise.review import SessionAnalysis, open_session, resolve_data_dir
from framewise.server import create_app

pytestmark = pytest.mark.skipif(
    not (
        MediaPipeFaceDetection().is_available() and is_verified(FACE_LANDMARKER, resolve_data_dir())
    ),
    reason="needs framewise[portable] and its models, from `framewise models download`",
)

FACES = Path(__file__).parent / "fixtures" / "faces"


@pytest.mark.parametrize("fixture", ["eyes-open.jpg", "eyes-closed.jpg"])
def test_the_face_in_each_reference_frame_is_found_where_it_appears(fixture):
    [(x, y, width, height)] = MediaPipeFaceDetection().detect_faces(FACES / fixture)

    assert 0.2 < x < 0.4 and 0.2 < y < 0.4
    assert 0.3 < width < 0.5 and 0.3 < height < 0.5


def eyes_open(jpg_path: Path) -> list[bool | None]:
    return MediaPipeEyeState().eyes_open(jpg_path, MediaPipeFaceDetection().detect_faces(jpg_path))


def test_eye_state_tells_open_from_closed_eyes():
    assert eyes_open(FACES / "eyes-open.jpg") == [True]
    assert eyes_open(FACES / "eyes-closed.jpg") == [False]


def test_a_frame_without_faces_has_none(tmp_path):
    assert MediaPipeFaceDetection().detect_faces(draw_landscape(tmp_path / "landscape.jpg")) == []


def test_eye_state_checks_every_face_in_a_group_shot(tmp_path):
    group_shot = side_by_side(
        [FACES / "eyes-open.jpg", FACES / "eyes-closed.jpg", FACES / "eyes-open.jpg"],
        tmp_path / "group-shot.jpg",
    )
    faces = sorted(MediaPipeFaceDetection().detect_faces(group_shot))

    assert MediaPipeEyeState().eyes_open(group_shot, faces) == [True, False, True]


def test_eye_state_reads_the_eyes_inside_boxes_from_another_detector():
    eye_state = MediaPipeEyeState()
    elsewhere = (0.0, 0.0, 0.1, 0.1)

    assert eye_state.eyes_open(FACES / "eyes-open.jpg", [FIXTURE_FACE_BOX, elsewhere]) == [
        True,
        None,
    ]
    assert eye_state.eyes_open(FACES / "eyes-closed.jpg", [FIXTURE_FACE_BOX]) == [False]


def test_a_face_is_found_where_it_appears_in_a_frame_stored_on_its_side(tmp_path):
    upright = portrait(tmp_path / "upright.jpg", background=128)
    on_its_side = stored_rotated(upright, tmp_path / "on-its-side.jpg")

    [upright_face] = MediaPipeFaceDetection().detect_faces(upright)
    [face] = MediaPipeFaceDetection().detect_faces(on_its_side)

    assert face == pytest.approx(upright_face, abs=0.02)


def test_a_closed_eyes_frame_gets_the_eyes_closed_reason_from_mediapipe(session_dir, data_dir):
    shutil.copy(FACES / "eyes-closed.jpg", session_dir / "DSCF0001.JPG")
    fingerprint = ScriptedFingerprint(
        similarity=SimilarityThresholds(burst=0.8, near_duplicate=0.9),
        fingerprints={"DSCF0001.JPG": BEACH},
    )
    store = open_session(session_dir, data_dir)
    analysis = SessionAnalysis(
        store, compose_analyzer([fingerprint, MediaPipeFaceDetection(), MediaPipeEyeState()])
    )
    analysis.run()

    frames = frames_by_name(TestClient(create_app(store, analysis)))

    assert reasons(frames["DSCF0001.JPG"]) == ["Eyes closed"]


def test_framewise_registers_its_mediapipe_providers_below_apple_vision():
    providers = {provider.id: provider for provider in discover_providers()}
    chosen = select_providers(providers.values())

    assert providers["mediapipe-face-detection"].priority < PRIORITY
    assert providers["mediapipe-eye-state"].priority < PRIORITY
    expected = "apple-vision" if sys.platform == "darwin" else "mediapipe"
    assert chosen["face-detection"].id == f"{expected}-face-detection"
    assert chosen["eye-state"].id == f"{expected}-eye-state"
