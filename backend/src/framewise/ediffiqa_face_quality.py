"""framewise's portable face quality Provider, built on eDifFIQA(T) run by onnxruntime, with
faces aligned by MediaPipe's landmarks. It needs the framewise-cull[portable] extra and reports
itself unavailable without it."""

import threading
from pathlib import Path

from PIL import Image, ImageOps

from framewise import mediapipe_faces
from framewise.dinov2_fingerprint import onnxruntime_supports_this_os
from framewise.image_measures import Region
from framewise.models import EDIFFIQA_TINY, ensure_model
from framewise.providers import FACE_QUALITY
from framewise.review import resolve_data_dir

try:
    import numpy
    import onnxruntime
except ImportError:
    onnxruntime = None

PRIORITY = 50
ALIGNED_SIZE = 112
REFERENCE_POINTS = (
    (38.2946, 51.6963),
    (73.5318, 51.5014),
    (56.0252, 71.7366),
    (41.5493, 92.3655),
    (70.729904, 92.2041),
)
"""Where eDifFIQA expects the five points of mediapipe_faces.FIVE_POINTS in its 112 pixel square:
the alignment template of ArcFace, as in the OpenCV Model Zoo's demo."""


class EDifFIQAFaceQuality:
    capability = FACE_QUALITY
    id = "ediffiqa-face-quality"
    version = 1
    priority = PRIORITY

    def is_available(self) -> bool:
        return (
            onnxruntime is not None
            and onnxruntime_supports_this_os()
            and mediapipe_faces.MediaPipeFaceDetection().is_available()
        )

    def face_quality(self, jpg_path: Path, faces: list[Region]) -> list[float | None]:
        """eDifFIQA's quality of each face, already about 0 to 1, or None where MediaPipe finds
        no face in the box to align."""
        points = mediapipe_faces.five_points(jpg_path, faces)
        found = [face_points for face_points in points if face_points is not None]
        if not found:
            return [None] * len(faces)
        with Image.open(jpg_path) as image:
            frame = ImageOps.exif_transpose(image).convert("RGB")
        batch = numpy.stack([_aligned(frame, face_points) for face_points in found])
        [scores] = _session().run(None, {"input": batch})
        qualities = iter(_clamp(float(score)) for score in scores[:, 0])
        return [None if face_points is None else next(qualities) for face_points in points]


_session_lock = threading.Lock()
_shared_session = None


def _session():
    """One session for every analysis thread, made on first use, when its model is downloaded
    if it is missing. See dinov2_fingerprint._session."""
    global _shared_session
    with _session_lock:
        if _shared_session is None:
            options = onnxruntime.SessionOptions()
            options.intra_op_num_threads = 1
            options.inter_op_num_threads = 1
            _shared_session = onnxruntime.InferenceSession(
                str(ensure_model(EDIFFIQA_TINY, resolve_data_dir())),
                sess_options=options,
                providers=["CPUExecutionProvider"],
            )
    return _shared_session


def _aligned(frame: Image.Image, points: tuple[tuple[float, float], ...]):
    """The face turned, scaled and moved so its five points land on REFERENCE_POINTS, as
    eDifFIQA was trained: RGB from -1 to 1, channels first."""
    matrix = numpy.vstack(
        [_similarity(numpy.asarray(points), numpy.asarray(REFERENCE_POINTS)), [0, 0, 1]]
    )
    inverse = numpy.linalg.inv(matrix)[:2]
    face = frame.transform(
        (ALIGNED_SIZE, ALIGNED_SIZE),
        Image.Transform.AFFINE,
        tuple(inverse.ravel()),
        Image.Resampling.BILINEAR,
    )
    pixels = numpy.asarray(face, dtype=numpy.float32) / 255
    return ((pixels - 0.5) / 0.5).transpose(2, 0, 1)


def _similarity(source, target):
    """The rotation, uniform scale and shift that best map the source points onto the target
    points, as a 2 by 3 matrix, by Umeyama's least squares method."""
    source_mean, target_mean = source.mean(axis=0), target.mean(axis=0)
    centred_source, centred_target = source - source_mean, target - target_mean
    u, spread, vt = numpy.linalg.svd(centred_target.T @ centred_source / len(source))
    reflection = numpy.eye(2)
    if numpy.linalg.det(u @ vt) < 0:
        reflection[1, 1] = -1
    rotation = u @ reflection @ vt
    scale = (spread * numpy.diag(reflection)).sum() / (centred_source**2).sum(axis=1).mean()
    shift = target_mean - scale * rotation @ source_mean
    return numpy.hstack([scale * rotation, shift[:, numpy.newaxis]])


def _clamp(value: float) -> float:
    return min(1.0, max(0.0, value))
