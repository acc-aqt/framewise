"""OpenAI's CLIP ViT-B/32 image encoder run by onnxruntime: the portable Providers that read a
Frame's CLIP embedding share it. It needs the framewise-cull[portable] extra."""

import threading
from pathlib import Path

from PIL import Image, ImageOps

from framewise.dinov2_fingerprint import onnxruntime_supports_this_os
from framewise.models import CLIP_VIT_B_32_IMAGE, ensure_model
from framewise.review import resolve_data_dir

try:
    import numpy
    import onnxruntime
except ImportError:
    onnxruntime = None

SIZE = 224
CLIP_MEAN = (0.48145466, 0.4578275, 0.40821073)
CLIP_STD = (0.26862954, 0.26130258, 0.27577711)


def is_available() -> bool:
    return onnxruntime is not None and onnxruntime_supports_this_os()


def image_embedding(jpg_path: Path):
    """CLIP's image embedding of the Frame, scaled to length 1, as 512 floats."""
    [embeds] = _session().run(["image_embeds"], {"pixel_values": _pixel_values(jpg_path)})
    embedding = embeds[0]
    return embedding / numpy.linalg.norm(embedding)


_session_lock = threading.Lock()
_shared_session = None


def _session():
    """One session for every analysis thread, made on first use, when its model is downloaded
    if it is missing. With one thread of its own per run, it runs on the thread that calls it."""
    global _shared_session
    with _session_lock:
        if _shared_session is None:
            options = onnxruntime.SessionOptions()
            options.intra_op_num_threads = 1
            options.inter_op_num_threads = 1
            _shared_session = onnxruntime.InferenceSession(
                str(ensure_model(CLIP_VIT_B_32_IMAGE, resolve_data_dir())),
                sess_options=options,
                providers=["CPUExecutionProvider"],
            )
    return _shared_session


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
