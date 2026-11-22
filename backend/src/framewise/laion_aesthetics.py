"""framewise's portable aesthetics Provider: LAION's Aesthetics Predictor V1 over CLIP ViT-B/32's
image embedding, run by onnxruntime. It needs the framewise-cull[portable] extra and reports
itself unavailable without it."""

import threading
import zipfile
from pathlib import Path

from framewise import clip_image
from framewise.models import LAION_AESTHETICS_VIT_B_32, ensure_model
from framewise.providers import AESTHETICS
from framewise.review import resolve_data_dir

try:
    import numpy
except ImportError:
    numpy = None

PRIORITY = 50
EMBEDDING_SIZE = 512
# The predictor rates images from 1 to 10. Photos land from about 5.5 to 7, a heavily blurred
# one about 3.5 and a flat grey Frame below 3, so 3 to 8 spreads them over 0..1 like the other
# Scores. Bump version when these change.
LOWEST_RATING = 3.0
HIGHEST_RATING = 8.0


class LaionAesthetics:
    capability = AESTHETICS
    id = "laion-aesthetics"
    version = 1
    priority = PRIORITY

    def is_available(self) -> bool:
        return numpy is not None and clip_image.is_available()

    def aesthetics(self, jpg_path: Path) -> float | None:
        weight, bias = _head()
        rating = float(clip_image.image_embedding(jpg_path) @ weight + bias)
        return _clamp((rating - LOWEST_RATING) / (HIGHEST_RATING - LOWEST_RATING))


_head_lock = threading.Lock()
_shared_head = None


def _head():
    """The predictor's linear layer, read from its PyTorch archive as raw little-endian floats:
    the weights in storage 0, the bias in storage 1. Nothing in it is unpickled; its pinned
    SHA-256 fixes that layout."""
    global _shared_head
    with _head_lock:
        if _shared_head is None:
            path = ensure_model(LAION_AESTHETICS_VIT_B_32, resolve_data_dir())
            with zipfile.ZipFile(path) as archive:
                weight = numpy.frombuffer(archive.read("archive/data/0"), "<f4")
                bias = numpy.frombuffer(archive.read("archive/data/1"), "<f4")
            assert weight.shape == (EMBEDDING_SIZE,) and bias.shape == (1,)
            _shared_head = (weight, float(bias[0]))
    return _shared_head


def _clamp(value: float) -> float:
    return min(1.0, max(0.0, value))
