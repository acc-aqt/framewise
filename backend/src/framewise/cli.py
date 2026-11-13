import argparse
import sys
import threading
import time
import webbrowser
from collections.abc import Callable
from pathlib import Path

import uvicorn
from fastapi import FastAPI

from framewise.review import open_session, resolve_data_dir
from framewise.server import create_app

HOST = "127.0.0.1"
DEFAULT_PORT = 8765
UI_DIR = Path(__file__).resolve().parents[3] / "frontend" / "dist" / "frontend" / "browser"

Serve = Callable[[FastAPI, str, int, Callable[[], None]], None]


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


def main(
    argv: list[str] | None = None,
    serve: Serve = serve_with_uvicorn,
    open_browser: Callable[[str], object] = webbrowser.open,
) -> None:
    parser = argparse.ArgumentParser(prog="framewise")
    commands = parser.add_subparsers(dest="command", required=True)
    review = commands.add_parser("review", help="Scan a Session and open the Review UI")
    review.add_argument("session_folder", type=Path)
    review.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args(argv)

    if not args.session_folder.is_dir():
        parser.error(f"not a folder: {args.session_folder}")

    store = open_session(args.session_folder, resolve_data_dir())
    url = f"http://{HOST}:{args.port}/"
    print(f"framewise: {len(store.frames())} Frames in {store.root}, Review UI at {url}")
    if not (UI_DIR / "index.html").is_file():
        print(
            f"framewise: warning: no Review UI build in {UI_DIR}, "
            "run `npx ng build` in frontend/ first",
            file=sys.stderr,
        )
    serve(create_app(store, UI_DIR), HOST, args.port, lambda: open_browser(url))
