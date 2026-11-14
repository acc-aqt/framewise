import argparse
import os
import subprocess
import sys
import threading
import time
import webbrowser
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager, nullcontext
from pathlib import Path

import uvicorn
from fastapi import FastAPI

from framewise.analyzer import FrameAnalyzer
from framewise.review import SessionAnalysis, open_session, resolve_data_dir
from framewise.server import create_app

HOST = "127.0.0.1"
DEFAULT_PORT = 8765
UI_DIR = Path(__file__).resolve().parents[3] / "frontend" / "dist" / "frontend" / "browser"

Serve = Callable[[FastAPI, str, int, Callable[[], None]], None]
KeepAwake = Callable[[], AbstractContextManager[object]]


def serve_with_uvicorn(app: FastAPI, host: str, port: int, on_ready: Callable[[], None]) -> None:
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
def keep_mac_awake() -> Iterator[None]:
    """Stops idle sleep until the block ends, or until framewise exits if it ends first."""
    try:
        caffeinate = subprocess.Popen(["caffeinate", "-i", "-w", str(os.getpid())])
    except OSError as error:
        print(f"framewise: warning: cannot keep the Mac awake: {error}", file=sys.stderr)
        yield
        return
    try:
        yield
    finally:
        caffeinate.terminate()
        caffeinate.wait()


def analyze_in_background(analysis: SessionAnalysis, keep_awake: KeepAwake) -> None:
    def run() -> None:
        with keep_awake():
            analysis.run()

    threading.Thread(target=run, daemon=True).start()


def main(
    argv: list[str] | None = None,
    serve: Serve = serve_with_uvicorn,
    open_browser: Callable[[str], object] = webbrowser.open,
    analyzer: FrameAnalyzer | None = None,
    keep_awake: KeepAwake = keep_mac_awake,
) -> None:
    parser = argparse.ArgumentParser(prog="framewise")
    commands = parser.add_subparsers(dest="command", required=True)
    review = commands.add_parser("review", help="Scan a Session and open the Review UI")
    review.add_argument("session_folder", type=Path)
    review.add_argument("--port", type=int, default=DEFAULT_PORT)
    review.add_argument(
        "--background",
        action="store_true",
        help="Analyse on fewer cores at low priority, so other apps stay responsive",
    )
    review.add_argument(
        "--allow-sleep",
        action="store_true",
        help="Let the Mac go to sleep while analysis runs",
    )
    args = parser.parse_args(argv)

    if not args.session_folder.is_dir():
        parser.error(f"not a folder: {args.session_folder}")

    if analyzer is None:
        # Imported here so the rest of framewise imports where Apple Vision doesn't exist.
        from framewise.vision_analyzer import VisionAnalyzer

        analyzer = VisionAnalyzer()
    store = open_session(args.session_folder, resolve_data_dir())
    analysis = SessionAnalysis(store, analyzer, background=args.background)
    analyze_in_background(analysis, nullcontext if args.allow_sleep else keep_awake)
    url = f"http://{HOST}:{args.port}/"
    print(f"framewise: {len(store.frames())} Frames in {store.root}, Review UI at {url}")
    if not (UI_DIR / "index.html").is_file():
        print(
            f"framewise: warning: no Review UI build in {UI_DIR}, "
            "run `npx ng build` in frontend/ first",
            file=sys.stderr,
        )
    serve(create_app(store, analysis, UI_DIR), HOST, args.port, lambda: open_browser(url))
