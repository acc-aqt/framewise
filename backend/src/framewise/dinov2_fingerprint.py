"""framewise's portable fingerprint Provider, built on DINOv2-small run by onnxruntime. It needs
the framewise-cull[portable] extra and reports itself unavailable without it."""

import platform
import sys
import threading
from pathlib import Path

from PIL import Image, ImageOps

from framewise.analyzer import SimilarityThresholds
from framewise.models import DINOV2_SMALL, ensure_model
from framewise.providers import FINGERPRINT
from framewise.review import resolve_data_dir

try:
    import numpy
    import onnxruntime
except ImportError:
    onnxruntime = None

PRIORITY = 50
MIN_MACOS = 14
"""onnxruntime's wheels for macOS need macOS 14 or later."""
SHORTEST_EDGE = 256
CROP = 224
IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)


class DinoV2Fingerprint:
    capability = FINGERPRINT
    id = "dinov2-small-fingerprint"
    version = 1
    priority = PRIORITY
    # Calibrated on the reference benchmark against Apple Vision's Groups: near_duplicate 0.82
    # matches them best (pairwise same-Group F1 0.93, 33 Groups to Apple's 30), with 0.80 to 0.83
    # close behind.
    # Any burst threshold from 0.4 to 0.76 gives the same Groups there; 0.7 sits inside that.
    similarity = SimilarityThresholds(burst=0.7, near_duplicate=0.82)

    def is_available(self) -> bool:
        return onnxruntime is not None and _onnxruntime_supports_this_os()

    def fingerprint(self, jpg_path: Path) -> list[float]:
        """DINOv2's class token: the embedding it learns to describe the whole image."""
        [hidden_states] = _session().run(None, {"pixel_values": _pixel_values(jpg_path)})
        return hidden_states[0, 0].tolist()


def _onnxruntime_supports_this_os() -> bool:
    if sys.platform != "darwin":
        return True
    try:
        return int(platform.mac_ver()[0].split(".")[0]) >= MIN_MACOS
    except ValueError:
        return False


_session_lock = threading.Lock()
_shared_session = None


def _session():
    """One session for every analysis thread, made on first use, when its model is downloaded
    if it is missing. onnxruntime runs a session from several threads at once; with one thread
    of its own per run, it runs on the thread that calls it, as many at once as framewise
    analyzes Frames."""
    global _shared_session
    with _session_lock:
        if _shared_session is None:
            options = onnxruntime.SessionOptions()
            options.intra_op_num_threads = 1
            options.inter_op_num_threads = 1
            _shared_session = onnxruntime.InferenceSession(
                str(ensure_model(DINOV2_SMALL, resolve_data_dir())),
                sess_options=options,
                providers=["CPUExecutionProvider"],
            )
    return _shared_session


def _pixel_values(jpg_path: Path):
    """The Frame as it is displayed, after its EXIF orientation, prepared as DINOv2 was trained:
    its shortest edge resized to 256, its center cropped to 224 square and normalized by
    ImageNet's mean and spread, channels first."""
    with Image.open(jpg_path) as image:
        image.draft("RGB", (SHORTEST_EDGE, SHORTEST_EDGE))
        upright = ImageOps.exif_transpose(image).convert("RGB")
    scale = SHORTEST_EDGE / min(upright.size)
    width, height = round(upright.width * scale), round(upright.height * scale)
    resized = upright.resize((width, height), Image.Resampling.BICUBIC)
    left, top = (width - CROP) // 2, (height - CROP) // 2
    cropped = resized.crop((left, top, left + CROP, top + CROP))
    pixels = numpy.asarray(cropped, dtype=numpy.float32) / 255
    normalised = (pixels - IMAGENET_MEAN) / IMAGENET_STD
    return normalised.transpose(2, 0, 1)[numpy.newaxis].astype(numpy.float32)
