"""framewise's portable fingerprint Provider, built on DINOv2-small run by onnxruntime. It needs
the framewise-cull[portable] extra and reports itself unavailable without it."""

from pathlib import Path

from PIL import Image, ImageOps

from framewise import onnx_runtime
from framewise.analyzer import SimilarityThresholds
from framewise.models import DINOV2_SMALL
from framewise.providers import FINGERPRINT

try:
    import numpy
except ImportError:
    numpy = None

PRIORITY = 50
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
        return onnx_runtime.is_available()

    def fingerprint(self, jpg_path: Path) -> list[float]:
        """DINOv2's class token: the embedding it learns to describe the whole image."""
        [hidden_states] = onnx_runtime.session(DINOV2_SMALL).run(
            None, {"pixel_values": _pixel_values(jpg_path)}
        )
        return hidden_states[0, 0].tolist()


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
