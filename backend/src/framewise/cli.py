import argparse
import os
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from collections.abc import Callable, Iterator, Sequence
from contextlib import AbstractContextManager, contextmanager, nullcontext
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from starlette.types import ASGIApp

from framewise.analyzer import FrameAnalyzer
from framewise.changelog import CHANGELOG_PATH
from framewise.exiftool import ExifTool
from framewise.lightroom import LIGHTROOM_PREFERENCES
from framewise.models import MODELS, Model, ModelError, ensure_model
from framewise.providers import ProviderError, resolve_analyzer
from framewise.review import (
    SessionAnalysis,
    hard_reset_session,
    open_session,
    resolve_config_path,
    resolve_data_dir,
    session_database_path,
)
from framewise.server import LocalOnly, SessionPicker, create_app

HOST = "127.0.0.1"
DEFAULT_PORT = 8765
UI_DIR = Path(__file__).resolve().parents[3] / "frontend" / "dist" / "frontend" / "browser"

Serve = Callable[[ASGIApp, str, int, Callable[[], None]], None]
ChooseFolder = Callable[[], Path | None]
KeepAwake = Callable[[], AbstractContextManager[object]]


def serve_with_uvicorn(app: ASGIApp, host: str, port: int, on_ready: Callable[[], None]) -> None:
    server = uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_level="warning"))
    thread = threading.Thread(target=server.run)
    thread.start()
    while not server.started and thread.is_alive():
        time.sleep(0.05)
    if server.started:
        on_ready()
    try:
        thread.join()
    except KeyboardInterrupt:
        server.should_exit = True
        thread.join()


@contextmanager
def keep_machine_awake() -> Iterator[None]:
    """Stops idle sleep until the block ends, or until framewise exits if it ends first."""
    if sys.platform == "win32":
        with _keep_windows_awake():
            yield
        return
    command = _wake_lock_command()
    if command is None:
        print("framewise: warning: cannot keep the machine awake here", file=sys.stderr)
        yield
        return
    try:
        wake_lock = subprocess.Popen(command)
    except OSError as error:
        print(f"framewise: warning: cannot keep the machine awake: {error}", file=sys.stderr)
        yield
        return
    try:
        yield
    finally:
        wake_lock.terminate()
        wake_lock.wait()


ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001


@contextmanager
def _keep_windows_awake() -> Iterator[None]:
    """Asks Windows to stay awake while this thread is in the block. Windows also drops the
    request when the thread ends."""
    import ctypes

    set_state = ctypes.windll.kernel32.SetThreadExecutionState
    set_state.restype = ctypes.c_uint32
    set_state.argtypes = [ctypes.c_uint32]
    if set_state(ES_CONTINUOUS | ES_SYSTEM_REQUIRED) == 0:
        print("framewise: warning: cannot keep the machine awake", file=sys.stderr)
        yield
        return
    try:
        yield
    finally:
        set_state(ES_CONTINUOUS)


def _wake_lock_command() -> list[str] | None:
    pid = str(os.getpid())
    if sys.platform == "darwin":
        return ["caffeinate", "-i", "-w", pid]
    if shutil.which("systemd-inhibit"):
        return [
            "systemd-inhibit",
            "--what=idle",
            "--who=framewise",
            "--why=Analyzing a Session",
            "tail",
            f"--pid={pid}",
            "-f",
            "/dev/null",
        ]
    return None


def choose_folder_in_dialog() -> Path | None:
    """Asks for a Session folder with the system's folder dialog, or None if canceled or
    there is none."""
    command = folder_dialog_command(sys.platform)
    if command is None:
        print(
            "framewise: warning: no folder dialog here, pass the Session folder to "
            "`framewise review` instead",
            file=sys.stderr,
        )
        return None
    result = subprocess.run(command, capture_output=True, encoding="utf-8")
    if result.returncode != 0:
        return None
    return Path(result.stdout.strip())


# Tk's folder dialog is the Explorer one on Windows. It prints the chosen folder as UTF-8, so a
# name outside the console's code page survives, and exits non-zero when canceled.
TK_FOLDER_DIALOG = """
import sys, tkinter, tkinter.filedialog
root = tkinter.Tk()
root.withdraw()
root.attributes("-topmost", True)
folder = tkinter.filedialog.askdirectory(title="Choose a Session folder", mustexist=True)
if not folder:
    sys.exit(1)
sys.stdout.reconfigure(encoding="utf-8")
print(folder)
"""


def folder_dialog_command(platform: str) -> list[str] | None:
    """The command that shows the system's folder dialog and prints the chosen folder, or None
    where there is no dialog."""
    if platform == "darwin":
        script = 'activate\nPOSIX path of (choose folder with prompt "Choose a Session folder")'
        return ["osascript", "-e", script]
    if platform == "win32":
        return [sys.executable, "-c", TK_FOLDER_DIALOG]
    if shutil.which("zenity"):
        return ["zenity", "--file-selection", "--directory", "--title=Choose a Session folder"]
    return None


def analyze_in_background(analysis: SessionAnalysis, keep_awake: KeepAwake) -> None:
    def run() -> None:
        with keep_awake():
            analysis.run()

    threading.Thread(target=run, daemon=True).start()


def hard_reset(folder: Path) -> None:
    data_dir = resolve_data_dir()
    if not session_database_path(folder.resolve(), data_dir).exists():
        print(f"framewise: no Session store for {folder.resolve()}, nothing to reset")
        return
    print("framewise: restoring the ratings framewise wrote, DNGs can take minutes")
    exiftool = ExifTool()
    try:
        result = hard_reset_session(folder, data_dir, exiftool)
    finally:
        exiftool.close()
    if result is None:
        return
    print(f"framewise: restored {len(result.written)} files")
    if result.failed:
        for failure in result.failed:
            print(f"framewise: could not restore {failure.path}: {failure.error}", file=sys.stderr)
        print("framewise: kept the Session store, so the reset can be retried", file=sys.stderr)
        sys.exit(1)
    print(
        f"framewise: deleted the Session store, the next review analyzes {folder.resolve()} again"
    )


def download_models(models: Sequence[Model]) -> None:
    data_dir = resolve_data_dir()
    for model in models:
        try:
            path = ensure_model(model, data_dir)
        except ModelError as error:
            print(f"framewise: error: {error}", file=sys.stderr)
            sys.exit(1)
        print(f"framewise: {model.file_name} is ready at {path}")


def main(
    argv: list[str] | None = None,
    serve: Serve = serve_with_uvicorn,
    open_browser: Callable[[str], object] = webbrowser.open,
    analyzer: FrameAnalyzer | None = None,
    keep_awake: KeepAwake = keep_machine_awake,
    choose_folder: ChooseFolder = choose_folder_in_dialog,
    models: Sequence[Model] = MODELS,
) -> None:
    parser = argparse.ArgumentParser(prog="framewise")
    commands = parser.add_subparsers(dest="command", required=True)
    review = commands.add_parser("review", help="Scan a Session and open the Review UI")
    review.add_argument(
        "session_folder",
        type=Path,
        nargs="?",
        help="Leave out to choose the Session folder in the Review UI",
    )
    review.add_argument("--port", type=int, default=DEFAULT_PORT)
    review.add_argument(
        "--background",
        action="store_true",
        help="Analyze on fewer cores at low priority, so other apps stay responsive",
    )
    review.add_argument(
        "--allow-sleep",
        action="store_true",
        help="Let the machine go to sleep while analysis runs",
    )
    reset = commands.add_parser(
        "reset",
        help="Undo Rating write-back and delete the Session store, "
        "so the next review analyzes every Frame again",
    )
    reset.add_argument("session_folder", type=Path)
    models_command = commands.add_parser("models", help="Manage the portable Providers' models")
    models_actions = models_command.add_subparsers(dest="action", required=True)
    models_actions.add_parser(
        "download", help="Fetch every model the portable Providers need, for offline use"
    )
    args = parser.parse_args(argv)

    if args.command == "models":
        download_models(models)
        return

    if args.session_folder is not None and not args.session_folder.is_dir():
        parser.error(f"not a folder: {args.session_folder}")

    if args.command == "reset":
        hard_reset(args.session_folder)
        return

    if analyzer is None:
        analyzer = _resolve_analyzer()

    def start_session(folder: Path) -> FastAPI:
        store = open_session(folder, resolve_data_dir())
        analysis = SessionAnalysis(store, analyzer, background=args.background)
        analyze_in_background(analysis, nullcontext if args.allow_sleep else keep_awake)
        print(f"framewise: {len(store.frames())} Frames in {store.root}")
        return create_app(
            store,
            analysis,
            UI_DIR,
            lightroom_preferences=LIGHTROOM_PREFERENCES,
            provider_lineup=analyzer.provider_lineup,
            config_path=resolve_config_path().absolute(),
            changelog_path=CHANGELOG_PATH,
        )

    url = f"http://{HOST}:{args.port}/"
    if args.session_folder is None:
        app: ASGIApp = SessionPicker(choose_folder, start_session, UI_DIR, CHANGELOG_PATH)
        print(f"framewise: Review UI at {url}, choose a Session folder there")
    else:
        app = start_session(args.session_folder)
        print(f"framewise: Review UI at {url}")
    if not (UI_DIR / "index.html").is_file():
        print(
            f"framewise: warning: no Review UI build in {UI_DIR}, run scripts/setup.sh first",
            file=sys.stderr,
        )
    serve(LocalOnly(app), HOST, args.port, lambda: open_browser(url))


def _resolve_analyzer() -> FrameAnalyzer:
    try:
        return resolve_analyzer(resolve_config_path())
    except ProviderError as error:
        print(f"framewise: error: {error}", file=sys.stderr)
        sys.exit(1)
