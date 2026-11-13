from pathlib import Path

from fastapi import FastAPI, HTTPException, Response
from fastapi.staticfiles import StaticFiles

from framewise.store import SessionStore


def create_app(store: SessionStore, ui_dir: Path | None = None) -> FastAPI:
    app = FastAPI(title="framewise")

    @app.get("/api/session")
    def session_summary() -> dict:
        frames = store.frames()
        raw_jpg_count = sum(1 for frame in frames if frame["raw_path"] is not None)
        return {
            "root": str(store.root),
            "total_frames": len(frames),
            "jpg_only_count": len(frames) - raw_jpg_count,
            "raw_jpg_count": raw_jpg_count,
            "skipped": store.skipped_files(),
        }

    @app.get("/api/frames")
    def frame_list() -> list[dict]:
        return [
            {
                "id": frame["id"],
                "jpg_path": frame["jpg_path"],
                "raw_path": frame["raw_path"],
                "kind": "jpg-only" if frame["raw_path"] is None else "raw+jpg",
                "camera_rating": {
                    "stars": frame["camera_stars"],
                    "label": frame["camera_label"],
                },
                "thumbnail_url": f"/api/frames/{frame['id']}/thumbnail",
            }
            for frame in store.frames()
        ]

    @app.get("/api/frames/{frame_id}/thumbnail")
    def frame_thumbnail(frame_id: int) -> Response:
        thumbnail = store.thumbnail(frame_id)
        if thumbnail is None:
            raise HTTPException(status_code=404, detail="Frame not found")
        return Response(content=thumbnail, media_type="image/jpeg")

    if ui_dir is not None and (ui_dir / "index.html").is_file():
        app.mount("/", StaticFiles(directory=ui_dir, html=True), name="review-ui")

    return app
