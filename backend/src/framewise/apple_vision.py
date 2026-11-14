"""framewise's own Providers, built on Apple Vision on macOS. Elsewhere they report themselves
unavailable."""

import threading
from array import array
from dataclasses import dataclass, field
from pathlib import Path

from framewise.analyzer import SimilarityThresholds
from framewise.image_measures import Region
from framewise.providers import AESTHETICS, EYE_STATE, FACE_DETECTION, FACE_QUALITY, FINGERPRINT

try:
    import Foundation
    import Vision
except ImportError:
    Foundation = Vision = None

PRIORITY = 100
FLOAT_ELEMENT_TYPE = 1
FEATURE_PRINT_REVISION = 2
# An eye's landmarks outline its opening, so a closed eye's outline is a flat line: open eyes
# measure about 0.3 high for each unit wide, closed ones under 0.1. On sewts, blinks and
# half-closed eyes measure up to 0.158, laughing squints from 0.17 and the photographer's rated
# faces from 0.205 (#30).
EYES_CLOSED_BELOW = 0.16


class _AppleVisionProvider:
    version = 1
    priority = PRIORITY

    def is_available(self) -> bool:
        return Vision is not None


class AppleFingerprint(_AppleVisionProvider):
    capability = FINGERPRINT
    id = "apple-vision-fingerprint"
    similarity = SimilarityThresholds(burst=0.8, near_duplicate=0.9)

    def fingerprint(self, jpg_path: Path) -> list[float]:
        request = Vision.VNGenerateImageFeaturePrintRequest.alloc().init()
        request.setRevision_(FEATURE_PRINT_REVISION)
        _perform(_vision_image(jpg_path), [request])
        observation = request.results()[0]
        type_code = "f" if observation.elementType() == FLOAT_ELEMENT_TYPE else "d"
        return array(type_code, bytes(observation.data())).tolist()


class AppleFaceDetection(_AppleVisionProvider):
    capability = FACE_DETECTION
    id = "apple-vision-face-detection"

    def detect_faces(self, jpg_path: Path) -> list[Region]:
        image = _vision_image(jpg_path)
        request = Vision.VNDetectFaceLandmarksRequest.alloc().init()
        _perform(image, [request])
        observations = list(request.results() or [])
        regions = [_region(observation) for observation in observations]
        image.faces = dict(zip(regions, observations, strict=True))
        return regions


class AppleEyeState(_AppleVisionProvider):
    capability = EYE_STATE
    id = "apple-vision-eye-state"

    def eyes_open(self, jpg_path: Path, faces: list[Region]) -> list[bool | None]:
        image = _vision_image(jpg_path)
        if all(face in image.faces for face in faces):
            observations = [image.faces[face] for face in faces]
        else:
            observations = _perform_on_faces(
                image,
                Vision.VNDetectFaceLandmarksRequest.alloc().init(),
                [_observation(face) for face in faces],
            )
        return [_eyes_open(observation) for observation in observations]


class AppleFaceQuality(_AppleVisionProvider):
    capability = FACE_QUALITY
    id = "apple-vision-face-quality"

    def face_quality(self, jpg_path: Path, faces: list[Region]) -> list[float | None]:
        image = _vision_image(jpg_path)
        observations = _perform_on_faces(
            image,
            Vision.VNDetectFaceCaptureQualityRequest.alloc().init(),
            [image.faces.get(face) or _observation(face) for face in faces],
        )
        return [_quality(observation) for observation in observations]


class AppleAesthetics(_AppleVisionProvider):
    capability = AESTHETICS
    id = "apple-vision-aesthetics"
    version = 2

    def is_available(self) -> bool:
        """Apple Vision's aesthetics request exists from macOS 15 on."""
        return Vision is not None and hasattr(Vision, "VNCalculateImageAestheticsScoresRequest")

    def aesthetics(self, jpg_path: Path) -> float | None:
        """Apple Vision scores from -1 to 1."""
        request = Vision.VNCalculateImageAestheticsScoresRequest.alloc().init()
        _perform(_vision_image(jpg_path), [request])
        return _clamp((float(request.results()[0].overallScore()) + 1) / 2)


@dataclass
class _VisionImage:
    key: tuple[Path, int]
    handler: object
    faces: dict[Region, object] = field(default_factory=dict)
    """The face observations the face detection Provider found, by their box."""


_this_thread = threading.local()


def _vision_image(jpg_path: Path) -> _VisionImage:
    """The Vision handler of the Analysis source this thread analyses. The Providers share it,
    so Vision reads the image once, and the eye state and face quality Providers reuse the face
    detection Provider's own observations, landmarks and all, for the boxes it found."""
    key = (jpg_path, jpg_path.stat().st_mtime_ns)
    image = getattr(_this_thread, "image", None)
    if image is None or image.key != key:
        url = Foundation.NSURL.fileURLWithPath_(str(jpg_path))
        handler = Vision.VNImageRequestHandler.alloc().initWithURL_options_(
            url, Foundation.NSDictionary.dictionary()
        )
        image = _VisionImage(key, handler)
        _this_thread.image = image
    return image


def _perform(image: _VisionImage, requests: list) -> None:
    succeeded, error = image.handler.performRequests_error_(requests, None)
    if not succeeded:
        raise RuntimeError(f"Apple Vision could not analyse {image.key[0]}: {error}")


def _perform_on_faces(image: _VisionImage, request, faces: list) -> list:
    """Runs a request on the given face observations and returns its results in their order,
    None for a face Vision returned nothing for. Vision returns them in any order, each with the
    uuid of the face it belongs to."""
    request.setInputFaceObservations_(faces)
    _perform(image, [request])
    by_face = {observation.uuid(): observation for observation in request.results() or []}
    return [by_face.get(face.uuid()) for face in faces]


def _region(face) -> Region:
    """Converts Apple Vision's box, measured from the bottom left, to one from the top left."""
    box = face.boundingBox()
    x = _clamp(box.origin.x)
    y = _clamp(1 - box.origin.y - box.size.height)
    width = _clamp(box.origin.x + box.size.width) - x
    height = _clamp(1 - box.origin.y) - y
    return x, y, width, height


def _observation(region: Region):
    """A face observation for a box another detector found, measured from the bottom left."""
    x, y, width, height = region
    return Vision.VNFaceObservation.faceObservationWithRequestRevision_boundingBox_roll_yaw_(
        Vision.VNDetectFaceRectanglesRequestRevision3,
        ((x, 1 - y - height), (width, height)),
        None,
        None,
    )


def _eyes_open(face) -> bool | None:
    landmarks = None if face is None else face.landmarks()
    if landmarks is None:
        return None
    eyes = [landmarks.leftEye(), landmarks.rightEye()]
    if any(eye is None for eye in eyes):
        return None
    openness = sum(_openness(eye) for eye in eyes) / len(eyes)
    return openness >= EYES_CLOSED_BELOW


def _openness(eye) -> float:
    points = eye.normalizedPoints()
    xs = [points[index].x for index in range(eye.pointCount())]
    ys = [points[index].y for index in range(eye.pointCount())]
    width = max(xs) - min(xs)
    return 0.0 if width == 0 else (max(ys) - min(ys)) / width


def _quality(observation) -> float | None:
    quality = None if observation is None else observation.faceCaptureQuality()
    return None if quality is None else float(quality)


def _clamp(value: float) -> float:
    return min(1.0, max(0.0, value))
