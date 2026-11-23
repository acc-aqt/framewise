"""OpenAI's CLIP ViT-B/32 image encoder run by onnxruntime: the portable Providers that read a
Frame's CLIP embedding share it. It needs the framewise-cull[portable] extra."""

from pathlib import Path

from PIL import Image, ImageOps

from framewise import onnx_runtime
from framewise.models import CLIP_VIT_B_32_IMAGE

try:
    import numpy
except ImportError:
    numpy = None

SIZE = 224
CLIP_MEAN = (0.48145466, 0.4578275, 0.40821073)
CLIP_STD = (0.26862954, 0.26130258, 0.27577711)


def is_available() -> bool:
    return onnx_runtime.is_available()


def image_embedding(jpg_path: Path):
    """CLIP's image embedding of the Frame, scaled to length 1, as 512 floats."""
    [embeds] = onnx_runtime.session(CLIP_VIT_B_32_IMAGE).run(
        ["image_embeds"], {"pixel_values": _pixel_values(jpg_path)}
    )
    embedding = embeds[0]
    return embedding / numpy.linalg.norm(embedding)


def _pixel_values(jpg_path: Path):
    """The Frame as it is displayed, after its EXIF orientation, prepared as CLIP was trained:
    its shortest edge resized to 224, its center cropped to 224 square and normalized by CLIP's
    mean and spread, channels first."""
    with Image.open(jpg_path) as image:
        image.draft("RGB", (SIZE, SIZE))
        upright = ImageOps.exif_transpose(image).convert("RGB")
    scale = SIZE / min(upright.size)
    width = max(SIZE, round(upright.width * scale))
    height = max(SIZE, round(upright.height * scale))
    resized = upright.resize((width, height), Image.Resampling.BICUBIC)
    left, top = (width - SIZE) // 2, (height - SIZE) // 2
    cropped = resized.crop((left, top, left + SIZE, top + SIZE))
    pixels = numpy.asarray(cropped, dtype=numpy.float32) / 255
    normalised = (pixels - CLIP_MEAN) / CLIP_STD
    return normalised.transpose(2, 0, 1)[numpy.newaxis].astype(numpy.float32)
