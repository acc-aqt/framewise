"""onnxruntime, which runs framewise's portable Models, and the one session each Model shares.
It needs the framewise-cull[portable] extra."""

import platform
import sys
import threading

from framewise.models import Model, ensure_model
from framewise.review import resolve_data_dir

try:
    import onnxruntime
except ImportError:
    onnxruntime = None

MIN_MACOS = 14
"""onnxruntime's wheels for macOS need macOS 14 or later."""


def is_available() -> bool:
    return onnxruntime is not None and supports_this_os()


def supports_this_os() -> bool:
    if sys.platform != "darwin":
        return True
    try:
        return int(platform.mac_ver()[0].split(".")[0]) >= MIN_MACOS
    except ValueError:
        return False


_sessions_lock = threading.Lock()
_sessions = {}


def session(model: Model):
    """The Model's one session for every analysis thread, made on first use, when the Model is
    downloaded if it is missing. onnxruntime runs a session from several threads at once; with
    one thread of its own per run, it runs on the thread that calls it, as many at once as
    framewise analyzes Frames."""
    with _sessions_lock:
        if model not in _sessions:
            options = onnxruntime.SessionOptions()
            options.intra_op_num_threads = 1
            options.inter_op_num_threads = 1
            _sessions[model] = onnxruntime.InferenceSession(
                str(ensure_model(model, resolve_data_dir())),
                sess_options=options,
                providers=["CPUExecutionProvider"],
            )
        return _sessions[model]
