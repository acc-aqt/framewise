from array import array
from pathlib import Path

import Foundation
import Vision

from framewise.analyzer import FrameSignals

FLOAT_ELEMENT_TYPE = 1
FEATURE_PRINT_REVISION = 2


class VisionAnalyzer:
    """Analyses a Frame's Analysis source with Apple Vision on this Mac."""

    def analyze(self, jpg_path: Path) -> FrameSignals:
        return FrameSignals(fingerprint=_feature_print(jpg_path))


def _feature_print(jpg_path: Path) -> list[float]:
    url = Foundation.NSURL.fileURLWithPath_(str(jpg_path))
    handler = Vision.VNImageRequestHandler.alloc().initWithURL_options_(
        url, Foundation.NSDictionary.dictionary()
    )
    request = Vision.VNGenerateImageFeaturePrintRequest.alloc().init()
    request.setRevision_(FEATURE_PRINT_REVISION)
    succeeded, error = handler.performRequests_error_([request], None)
    if not succeeded:
        raise RuntimeError(f"Apple Vision could not analyse {jpg_path}: {error}")
    observation = request.results()[0]
    type_code = "f" if observation.elementType() == FLOAT_ELEMENT_TYPE else "d"
    return array(type_code, bytes(observation.data())).tolist()
