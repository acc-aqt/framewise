from array import array
from dataclasses import dataclass
from pathlib import Path

import Foundation
import Vision

from framewise.analyzer import Face, FrameSignals
from framewise.image_measures import Region, measure_image

FLOAT_ELEMENT_TYPE = 1
FEATURE_PRINT_REVISION = 2
# Apple Vision's aesthetics request exists from macOS 15 on.
HAS_AESTHETICS = hasattr(Vision, "VNCalculateImageAestheticsScoresRequest")
# An eye's landmarks outline its opening, so a closed eye's outline is a flat line: open eyes
# measure about 0.3 high for each unit wide, closed ones under 0.1.
EYES_CLOSED_BELOW = 0.15


@dataclass(frozen=True)
class _VisionFace:
    region: Region
    eyes_open: bool | None
    quality: float | None


class VisionAnalyzer:
    """Analyses a Frame's Analysis source with Apple Vision and image maths on this Mac."""

    def analyze(self, jpg_path: Path) -> FrameSignals:
        feature_print, aesthetics, vision_faces = _vision_signals(jpg_path)
        measures = measure_image(jpg_path, [face.region for face in vision_faces])
        return FrameSignals(
            fingerprint=feature_print,
            sharpness=measures.sharpness,
            motion_blur=measures.motion_blur,
            exposure_stops=measures.exposure_stops,
            low_key=measures.low_key,
            high_key=measures.high_key,
            aesthetics=aesthetics,
            faces=_faces(vision_faces, measures.region_sharpness),
        )


def _faces(vision_faces: list[_VisionFace], sharpness: list[float | None]) -> list[Face]:
    """Leaves out faces too small to measure, such as distant passers-by."""
    return [
        Face(*face.region, eyes_open=face.eyes_open, sharpness=face_sharpness, quality=face.quality)
        for face, face_sharpness in zip(vision_faces, sharpness, strict=True)
        if face_sharpness is not None
    ]


def _vision_signals(jpg_path: Path) -> tuple[list[float], float | None, list[_VisionFace]]:
    url = Foundation.NSURL.fileURLWithPath_(str(jpg_path))
    handler = Vision.VNImageRequestHandler.alloc().initWithURL_options_(
        url, Foundation.NSDictionary.dictionary()
    )
    feature_print_request = Vision.VNGenerateImageFeaturePrintRequest.alloc().init()
    feature_print_request.setRevision_(FEATURE_PRINT_REVISION)
    landmarks_request = Vision.VNDetectFaceLandmarksRequest.alloc().init()
    requests = [feature_print_request, landmarks_request]
    if HAS_AESTHETICS:
        aesthetics_request = Vision.VNCalculateImageAestheticsScoresRequest.alloc().init()
        requests.append(aesthetics_request)
    _perform(handler, requests, jpg_path)
    aesthetics = float(aesthetics_request.results()[0].overallScore()) if HAS_AESTHETICS else None
    faces = list(landmarks_request.results() or [])
    qualities = _face_qualities(handler, faces, jpg_path)
    vision_faces = [
        _VisionFace(_region(face), _eyes_open(face), quality)
        for face, quality in zip(faces, qualities, strict=True)
    ]
    return _feature_print(feature_print_request.results()[0]), aesthetics, vision_faces


def _face_qualities(handler, faces: list, jpg_path: Path) -> list[float | None]:
    """Asks for the capture quality of the faces the landmarks request found, so each quality
    belongs to the same face as its landmarks."""
    if not faces:
        return []
    quality_request = Vision.VNDetectFaceCaptureQualityRequest.alloc().init()
    quality_request.setInputFaceObservations_(faces)
    _perform(handler, [quality_request], jpg_path)
    return [_quality(observation) for observation in quality_request.results()]


def _perform(handler, requests: list, jpg_path: Path) -> None:
    succeeded, error = handler.performRequests_error_(requests, None)
    if not succeeded:
        raise RuntimeError(f"Apple Vision could not analyse {jpg_path}: {error}")


def _region(face) -> Region:
    """Converts Apple Vision's box, measured from the bottom left, to one from the top left."""
    box = face.boundingBox()
    x = _clamp(box.origin.x)
    y = _clamp(1 - box.origin.y - box.size.height)
    width = _clamp(box.origin.x + box.size.width) - x
    height = _clamp(1 - box.origin.y) - y
    return x, y, width, height


def _eyes_open(face) -> bool | None:
    landmarks = face.landmarks()
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
    quality = observation.faceCaptureQuality()
    return None if quality is None else float(quality)


def _feature_print(observation) -> list[float]:
    type_code = "f" if observation.elementType() == FLOAT_ELEMENT_TYPE else "d"
    return array(type_code, bytes(observation.data())).tolist()


def _clamp(value: float) -> float:
    return min(1.0, max(0.0, value))
