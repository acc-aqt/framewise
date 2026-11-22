"""The model files the portable Providers need. Each is downloaded on first use into the
framewise data directory from a pinned URL and verified by its SHA-256."""

import hashlib
import shutil
import threading
import urllib.request
from dataclasses import dataclass
from pathlib import Path

DOWNLOAD_TIMEOUT_SECONDS = 60
_downloading = threading.Lock()


class ModelError(RuntimeError):
    """A model file is missing and cannot be downloaded, or does not match its checksum."""


@dataclass(frozen=True)
class Model:
    file_name: str
    url: str
    sha256: str


# Google's MediaPipe Face Landmarker bundle: BlazeFace short range, Face Mesh V2 and Blendshape
# V2. Their model cards each state "Licensed under Apache License, Version 2.0":
# https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker#models
FACE_LANDMARKER = Model(
    file_name="face_landmarker.task",
    url="https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task",
    sha256="64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff",
)
# DINOv2-small, quantized to 8 bits and exported to ONNX for Transformers.js. Its base model
# card states "license: apache-2.0": https://huggingface.co/facebook/dinov2-small
DINOV2_SMALL = Model(
    file_name="dinov2_small_quantized.onnx",
    url="https://huggingface.co/onnx-community/dinov2-small/resolve/8b1f705a3a7f6f062f6bdd21986c1583d3ef105d/onnx/model_quantized.onnx",
    sha256="c179f8f7f592449c4c1bca4cd124a7538021428c5ffb89afde9503935b197efb",
)
# OpenAI's CLIP ViT-B/32 image encoder, its weights stored as 16-bit floats and exported to ONNX
# for Transformers.js. Its model card states "license: mit", as does OpenAI's original:
# https://huggingface.co/Xenova/clip-vit-base-patch32, https://github.com/openai/CLIP
CLIP_VIT_B_32_IMAGE = Model(
    file_name="clip_vit_b_32_vision_fp16.onnx",
    url="https://huggingface.co/Xenova/clip-vit-base-patch32/resolve/6b7c523703ae26e39be4b03774966f8571c7f523/onnx/vision_model_fp16.onnx",
    sha256="35c4e0fb0aeee527dcde1693520b214a34424a786babd530f35366bad5844efd",
)
# LAION's Aesthetics Predictor V1 for CLIP ViT-B/32: one linear layer over its image embedding,
# trained on people's ratings of how much they like an image. MIT licensed:
# https://github.com/LAION-AI/aesthetic-predictor/blob/6d122adad522ab246644d9dc1c6d7a3810ee255f/LICENSE
LAION_AESTHETICS_VIT_B_32 = Model(
    file_name="laion_aesthetics_vit_b_32_linear.pth",
    url="https://raw.githubusercontent.com/LAION-AI/aesthetic-predictor/6d122adad522ab246644d9dc1c6d7a3810ee255f/sa_0_4_vit_b_32_linear.pth",
    sha256="c7b14cead230694acc7b9447974d3cad78003c72da032e402a303b6c2429e85f",
)
MODELS = (FACE_LANDMARKER, DINOV2_SMALL, CLIP_VIT_B_32_IMAGE, LAION_AESTHETICS_VIT_B_32)
"""Every model the portable Providers need."""


def ensure_model(model: Model, data_dir: Path) -> Path:
    """The model's verified file, downloaded first unless a verified copy is already there.
    Analysis threads that need it at once wait for a single download."""
    path = model_path(model, data_dir)
    with _downloading:
        if not is_verified(model, data_dir):
            _download(model, path)
    return path


def model_path(model: Model, data_dir: Path) -> Path:
    return data_dir / "models" / model.file_name


def is_verified(model: Model, data_dir: Path) -> bool:
    path = model_path(model, data_dir)
    return path.is_file() and _sha256(path) == model.sha256


def _download(model: Model, path: Path) -> None:
    """Downloads next to the model's place and moves it there only once verified, so a partial
    or tampered download is never taken for the model."""
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    partial = path.with_name(path.name + ".part")
    try:
        _fetch(model, partial)
        if _sha256(partial) != model.sha256:
            raise ModelError(
                f"the model {model.file_name} from {model.url} does not match its pinned SHA-256"
            )
        partial.replace(path)
    finally:
        partial.unlink(missing_ok=True)


def _fetch(model: Model, destination: Path) -> None:
    try:
        with (
            urllib.request.urlopen(model.url, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response,
            destination.open("wb") as file,
        ):
            shutil.copyfileobj(response, file)
    except OSError as error:
        raise ModelError(
            f"the model {model.file_name} is missing and cannot be downloaded from {model.url}: "
            f"{error}. Run `framewise models download` while online to fetch it ahead of time."
        ) from error


def _sha256(path: Path) -> str:
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()
