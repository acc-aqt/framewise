from array import array
from pathlib import Path

import Foundation
import Vision

from framewise.analyzer import FrameSignals
from framewise.image_measures import measure_image

FLOAT_ELEMENT_TYPE = 1
FEATURE_PRINT_REVISION = 2
# Apple Vision's aesthetics request exists from macOS 15 on.
HAS_AESTHETICS = hasattr(Vision, "VNCalculateImageAestheticsScoresRequest")


class VisionAnalyzer:
    """Analyses a Frame's Analysis source with Apple Vision and image maths on this Mac."""

    def analyze(self, jpg_path: Path) -> FrameSignals:
        feature_print, aesthetics = _vision_signals(jpg_path)
        measures = measure_image(jpg_path)
        return FrameSignals(
            fingerprint=feature_print,
            sharpness=measures.sharpness,
            motion_blur=measures.motion_blur,
            exposure_stops=measures.exposure_stops,
            low_key=measures.low_key,
            high_key=measures.high_key,
            aesthetics=aesthetics,
        )


def _vision_signals(jpg_path: Path) -> tuple[list[float], float | None]:
    url = Foundation.NSURL.fileURLWithPath_(str(jpg_path))
    handler = Vision.VNImageRequestHandler.alloc().initWithURL_options_(
        url, Foundation.NSDictionary.dictionary()
    )
    feature_print_request = Vision.VNGenerateImageFeaturePrintRequest.alloc().init()
    feature_print_request.setRevision_(FEATURE_PRINT_REVISION)
    requests = [feature_print_request]
    if HAS_AESTHETICS:
        aesthetics_request = Vision.VNCalculateImageAestheticsScoresRequest.alloc().init()
        requests.append(aesthetics_request)
    succeeded, error = handler.performRequests_error_(requests, None)
    if not succeeded:
        raise RuntimeError(f"Apple Vision could not analyse {jpg_path}: {error}")
    aesthetics = float(aesthetics_request.results()[0].overallScore()) if HAS_AESTHETICS else None
    return _feature_print(feature_print_request.results()[0]), aesthetics


def _feature_print(observation) -> list[float]:
    type_code = "f" if observation.elementType() == FLOAT_ELEMENT_TYPE else "d"
    return array(type_code, bytes(observation.data())).tolist()
