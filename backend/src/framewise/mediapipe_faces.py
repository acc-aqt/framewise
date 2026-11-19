"""framewise's portable face Providers, built on MediaPipe's Face Landmarker. They need the
framewise-cull[portable] extra and report themselves unavailable without it."""

import threading
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps

from framewise.image_measures import Region
from framewise.models import FACE_LANDMARKER, ensure_model
from framewise.providers import EYE_STATE, FACE_DETECTION
from framewise.review import resolve_data_dir

try:
    import mediapipe
    import numpy
    from mediapipe.tasks.python import BaseOptions
    from mediapipe.tasks.python.vision import FaceLandmarker, FaceLandmarkerOptions
except ImportError:
    mediapipe = None

PRIORITY = 50
MAX_FACES = 20
# MediaPipe's default of 0.5 misses some faces whose eyes are closed, such as the eyes-closed
# reference face in a group shot; from 0.3 it finds them, and around 0.1 it finds faces twice.
MIN_DETECTION_CONFIDENCE = 0.3
BLINKS = ("eyeBlinkLeft", "eyeBlinkRight")
# The blink blendshapes run from 0 for an open eye to 1 for a shut one. On the reference faces,
# open eyes score 0.03 for both eyes and the painted-shut eyes 0.75 and 0.76, so the threshold
# sits between them.
EYES_CLOSED_FROM = 0.5
MIN_OVERLAP = 0.3
"""How much a box from another detector must overlap a landmarked face to be read as it."""


class _MediaPipeProvider:
    version = 1
    priority = PRIORITY

    def is_available(self) -> bool:
        return mediapipe is not None


class MediaPipeFaceDetection(_MediaPipeProvider):
    capability = FACE_DETECTION
    id = "mediapipe-face-detection"

    def detect_faces(self, jpg_path: Path) -> list[Region]:
        return [face.box for face in _landmarked_faces(jpg_path)]


class MediaPipeEyeState(_MediaPipeProvider):
    capability = EYE_STATE
    id = "mediapipe-eye-state"

    def eyes_open(self, jpg_path: Path, faces: list[Region]) -> list[bool | None]:
        landmarked = _landmarked_faces(jpg_path)
        return [_eyes_open(_overlapping_face(face, landmarked)) for face in faces]


@dataclass(frozen=True)
class _LandmarkedFace:
    box: Region
    blink: float
    """The mean of both eyes' blink blendshapes."""


_this_thread = threading.local()


def _landmarked_faces(jpg_path: Path) -> list[_LandmarkedFace]:
    """The faces in the Analysis source this thread analyzes. The Providers share them, so the
    landmarker runs once per Frame."""
    key = (jpg_path, jpg_path.stat().st_mtime_ns)
    if getattr(_this_thread, "key", None) != key:
        result = _landmarker().detect(_mediapipe_image(jpg_path))
        _this_thread.faces = [
            _LandmarkedFace(_box(landmarks), _blink(blendshapes))
            for landmarks, blendshapes in zip(
                result.face_landmarks, result.face_blendshapes, strict=True
            )
        ]
        _this_thread.key = key
    return _this_thread.faces


def _landmarker():
    """This thread's own Face Landmarker, made on first use, when its model is downloaded if
    it is missing."""
    landmarker = getattr(_this_thread, "landmarker", None)
    if landmarker is None:
        model = ensure_model(FACE_LANDMARKER, resolve_data_dir())
        options = FaceLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(model)),
            num_faces=MAX_FACES,
            min_face_detection_confidence=MIN_DETECTION_CONFIDENCE,
            output_face_blendshapes=True,
        )
        landmarker = FaceLandmarker.create_from_options(options)
        _this_thread.landmarker = landmarker
    return landmarker


def _mediapipe_image(jpg_path: Path):
    """The Frame as it is displayed, after its EXIF orientation, so the landmarks are too."""
    with Image.open(jpg_path) as image:
        upright = ImageOps.exif_transpose(image).convert("RGB")
    return mediapipe.Image(mediapipe.ImageFormat.SRGB, numpy.asarray(upright))


def _box(landmarks) -> Region:
    xs = [_clamp(landmark.x) for landmark in landmarks]
    ys = [_clamp(landmark.y) for landmark in landmarks]
    return min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)


def _blink(blendshapes) -> float:
    scores = {category.category_name: category.score for category in blendshapes}
    return sum(scores[name] for name in BLINKS) / len(BLINKS)


def _overlapping_face(box: Region, faces: list[_LandmarkedFace]) -> _LandmarkedFace | None:
    """The landmarked face that overlaps the box most, if it overlaps enough to be the same."""
    overlaps = [(_overlap(box, face.box), face) for face in faces]
    best = max(overlaps, key=lambda overlap: overlap[0], default=None)
    return best[1] if best and best[0] >= MIN_OVERLAP else None


def _overlap(first: Region, second: Region) -> float:
    """Intersection over union."""
    width = min(first[0] + first[2], second[0] + second[2]) - max(first[0], second[0])
    height = min(first[1] + first[3], second[1] + second[3]) - max(first[1], second[1])
    if width <= 0 or height <= 0:
        return 0.0
    intersection = width * height
    return intersection / (first[2] * first[3] + second[2] * second[3] - intersection)


def _eyes_open(face: _LandmarkedFace | None) -> bool | None:
    return None if face is None else face.blink < EYES_CLOSED_FROM


def _clamp(value: float) -> float:
    return min(1.0, max(0.0, value))
