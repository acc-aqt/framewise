"""framewise's portable face Providers, built on MediaPipe's Face Landmarker. They need the
framewise-cull[portable] extra and report themselves unavailable without it."""

import math
import threading
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps

from framewise.analyzer import Expression
from framewise.image_measures import Region
from framewise.models import FACE_LANDMARKER, ensure_model
from framewise.providers import EXPRESSION, EYE_STATE, FACE_DETECTION
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
SMILES = ("mouthSmileLeft", "mouthSmileRight")
# The blendshapes of both eyes looking each way. They run from 0 for eyes looking straight ahead
# from the head to 1 for eyes turned fully that way, so they say where the eyes look relative to
# the head, not to the camera.
EYES_LEFT = ("eyeLookOutLeft", "eyeLookInRight")
EYES_RIGHT = ("eyeLookInLeft", "eyeLookOutRight")
EYES_UP = ("eyeLookUpLeft", "eyeLookUpRight")
EYES_DOWN = ("eyeLookDownLeft", "eyeLookDownRight")
EYE_TURN_DEGREES = 35.0
"""How far, in degrees, eyes turn from the head at a blendshape of 1. The blendshapes carry no
angle, so the eyes' angle is taken as linear in them: how far they look one way less how far
they look the other, times this. 35 degrees is about as far as eyes turn in a glance, and on the
reference faces it brings a head turned 31 degrees whose eyes look back into the lens to within
3 degrees of it."""
# How far the head may turn, in degrees of yaw and pitch combined, and still face the camera
# fully, and from how far it is turned away. On the reference faces, frontal portraits read 7 to
# 9 degrees, mostly pitch, and a three-quarter profile 34 degrees.
FACING_WITHIN_DEGREES = 15.0
TURNED_AWAY_FROM_DEGREES = 40.0
# How far the gaze, the head's angle plus the eyes', may miss the lens, in degrees, and still
# look into it fully, and from how far it looks aside. On the reference faces, eyes looking into
# the lens read 3 to 9 degrees, and eyes looking aside or following a turned head 26 to 33.
LOOKING_WITHIN_DEGREES = 12.0
LOOKING_ASIDE_FROM_DEGREES = 22.0
MIN_OVERLAP = 0.3
"""How much a box from another detector must overlap a landmarked face to be read as it."""
FIVE_POINTS = (468, 473, 1, 61, 291)
"""The Face Mesh landmarks of the five points faces are aligned by: the centres of the irises on
the image's left and right, the nose tip and the mouth corners on the image's left and right."""
CROP_SIZE = 2.0
"""How many times the longer side of a face's box its crop spans, so the whole face and its
landmarks fit and the face is large enough for the landmarker's detector."""


class _MediaPipeProvider:
    version = 1
    priority = PRIORITY

    def is_available(self) -> bool:
        return mediapipe is not None


def five_points(
    jpg_path: Path, faces: list[Region]
) -> list[tuple[tuple[float, float], ...] | None]:
    """The five points of the face in each box, in pixels of the Frame as it is displayed, or
    None where the landmarker finds no face in the box. See FIVE_POINTS."""
    return [None if face is None else face.five_points for face in _faces_in_boxes(jpg_path, faces)]


class MediaPipeFaceDetection(_MediaPipeProvider):
    capability = FACE_DETECTION
    id = "mediapipe-face-detection"

    def detect_faces(self, jpg_path: Path) -> list[Region]:
        return [face.box for face in _landmark(_upright_frame(jpg_path))]


class MediaPipeEyeState(_MediaPipeProvider):
    capability = EYE_STATE
    id = "mediapipe-eye-state"
    version = 2

    def eyes_open(self, jpg_path: Path, faces: list[Region]) -> list[bool | None]:
        return [_eyes_open(face) for face in _faces_in_boxes(jpg_path, faces)]


class MediaPipeExpression(_MediaPipeProvider):
    capability = EXPRESSION
    id = "mediapipe-expression"
    version = 4

    def expression(self, jpg_path: Path, faces: list[Region]) -> list[Expression | None]:
        return [_expression(face) for face in _faces_in_boxes(jpg_path, faces)]


@dataclass(frozen=True)
class _LandmarkedFace:
    box: Region
    """Where the face is, as fractions of the Frame or crop the landmarker ran on."""
    blink: float
    """The mean of both eyes' blink blendshapes."""
    smile: float
    """The mean of both mouth corners' smile blendshapes."""
    looking: float
    """From 0 for eyes looking aside to 1 for eyes looking into the lens, wherever the head
    turns."""
    facing: float
    """From 0 for a head turned away from the camera to 1 for a head facing it."""
    five_points: tuple[tuple[float, float], ...]
    """See FIVE_POINTS, in pixels of the upright Frame."""


_this_thread = threading.local()


def _faces_in_boxes(jpg_path: Path, boxes: list[Region]) -> list[_LandmarkedFace | None]:
    """The landmarked face in each box, read from a crop around it, so a face too small for the
    landmarker's own detector in the whole Frame is large in its crop. The eye state and
    expression Providers get the same boxes and share the result, so the landmarker runs once
    per face per Frame."""
    key = (jpg_path, jpg_path.stat().st_mtime_ns, tuple(boxes))
    if getattr(_this_thread, "boxes_key", None) != key:
        frame = _upright_frame(jpg_path)
        _this_thread.faces_in_boxes = [_face_in_box(frame, box) for box in boxes]
        _this_thread.boxes_key = key
    return _this_thread.faces_in_boxes


def _upright_frame(jpg_path: Path) -> Image.Image:
    """The Frame as it is displayed, after its EXIF orientation, which the detector's boxes are
    fractions of."""
    with Image.open(jpg_path) as image:
        return ImageOps.exif_transpose(image).convert("RGB")


def _face_in_box(frame: Image.Image, box: Region) -> _LandmarkedFace | None:
    crop = _crop_around(box, frame.width, frame.height)
    left, top, right, bottom = crop
    if right <= left or bottom <= top:
        return None
    faces = _landmark(frame.crop(crop), origin=(left, top))
    return _overlapping_face(_box_in_crop(box, crop, frame), faces)


def _crop_around(box: Region, frame_width: int, frame_height: int) -> tuple[int, int, int, int]:
    """A square around the box, CROP_SIZE times its longer side, within the Frame."""
    x, y, width, height = box
    center_x, center_y = (x + width / 2) * frame_width, (y + height / 2) * frame_height
    half = CROP_SIZE * max(width * frame_width, height * frame_height) / 2
    return (
        max(0, round(center_x - half)),
        max(0, round(center_y - half)),
        min(frame_width, round(center_x + half)),
        min(frame_height, round(center_y + half)),
    )


def _box_in_crop(box: Region, crop: tuple[int, int, int, int], frame: Image.Image) -> Region:
    left, top, right, bottom = crop
    x, y, width, height = box
    return (
        (x * frame.width - left) / (right - left),
        (y * frame.height - top) / (bottom - top),
        width * frame.width / (right - left),
        height * frame.height / (bottom - top),
    )


def _landmark(image: Image.Image, origin: tuple[int, int] = (0, 0)) -> list[_LandmarkedFace]:
    """The faces in the image, which sits at origin in the upright Frame."""
    result = _landmarker().detect(mediapipe.Image(mediapipe.ImageFormat.SRGB, numpy.asarray(image)))
    left, top = origin
    return [
        _landmarked_face(
            landmarks,
            blendshapes,
            matrix,
            tuple(
                (left + landmarks[i].x * image.width, top + landmarks[i].y * image.height)
                for i in FIVE_POINTS
            ),
        )
        for landmarks, blendshapes, matrix in zip(
            result.face_landmarks,
            result.face_blendshapes,
            result.facial_transformation_matrixes,
            strict=True,
        )
    ]


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
            output_facial_transformation_matrixes=True,
        )
        landmarker = FaceLandmarker.create_from_options(options)
        _this_thread.landmarker = landmarker
    return landmarker


def _box(landmarks) -> Region:
    xs = [_clamp(landmark.x) for landmark in landmarks]
    ys = [_clamp(landmark.y) for landmark in landmarks]
    return min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)


def _landmarked_face(landmarks, blendshapes, matrix, five_points) -> _LandmarkedFace:
    scores = {category.category_name: category.score for category in blendshapes}
    head_yaw, head_pitch = _head_angle(matrix)
    eyes_yaw, eyes_pitch = _eyes_angle(scores)
    return _LandmarkedFace(
        _box(landmarks),
        blink=_mean(scores, BLINKS),
        smile=_mean(scores, SMILES),
        looking=_within(
            math.hypot(head_yaw + eyes_yaw, head_pitch + eyes_pitch),
            LOOKING_WITHIN_DEGREES,
            LOOKING_ASIDE_FROM_DEGREES,
        ),
        facing=_within(
            math.hypot(head_yaw, head_pitch), FACING_WITHIN_DEGREES, TURNED_AWAY_FROM_DEGREES
        ),
        five_points=five_points,
    )


def _head_angle(matrix) -> tuple[float, float]:
    """The head's yaw and pitch from the camera, in degrees, from the landmarker's facial
    transformation matrix."""
    rotation = numpy.asarray(matrix)[:3, :3]
    yaw = math.degrees(math.atan2(-rotation[2, 0], math.hypot(rotation[2, 1], rotation[2, 2])))
    pitch = math.degrees(math.atan2(rotation[2, 1], rotation[2, 2]))
    return yaw, pitch


def _eyes_angle(scores: dict[str, float]) -> tuple[float, float]:
    """The eyes' yaw and pitch from the head, in degrees, on the same axes as the head's, so the
    two add up to the gaze from the camera. See EYE_TURN_DEGREES."""
    yaw = _mean(scores, EYES_LEFT) - _mean(scores, EYES_RIGHT)
    pitch = _mean(scores, EYES_DOWN) - _mean(scores, EYES_UP)
    return yaw * EYE_TURN_DEGREES, pitch * EYE_TURN_DEGREES


def _within(degrees: float, fully_within: float, none_from: float) -> float:
    """1 up to fully_within degrees, falling evenly to 0 at none_from."""
    return 1 - _clamp((degrees - fully_within) / (none_from - fully_within))


def _mean(scores: dict[str, float], names: tuple[str, ...]) -> float:
    return sum(scores[name] for name in names) / len(names)


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


def _expression(face: _LandmarkedFace | None) -> Expression | None:
    if face is None:
        return None
    return Expression(smile=face.smile, looking=face.looking, facing=face.facing)


def _clamp(value: float) -> float:
    return min(1.0, max(0.0, value))
