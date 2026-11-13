from pathlib import Path

from fastapi import FastAPI, HTTPException, Response
from fastapi.staticfiles import StaticFiles

from framewise.grouper import group_frames
from framewise.store import Frame, SessionStore


def create_app(store: SessionStore, ui_dir: Path | None = None) -> FastAPI:
    app = FastAPI(title="framewise")

    @app.get("/api/session")
    def session_summary() -> dict:
        summary = store.summary()
        return {
            "root": str(store.root),
            "total_frames": summary.total_frames,
            "jpg_only_count": summary.jpg_only_count,
            "raw_jpg_count": summary.raw_jpg_count,
            "skipped": summary.skipped,
        }

    @app.get("/api/frames")
    def frame_list() -> list[dict]:
        return [_frame_json(frame) for frame in store.frames()]

    @app.get("/api/groups")
    def group_list() -> list[dict]:
        return [
            {
                "id": group[0].frame.id,
                "frames": [_frame_json(analyzed.frame) for analyzed in group],
            }
            for group in group_frames(store.analyzed_frames())
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


def _frame_json(frame: Frame) -> dict:
    return {
        "id": frame.id,
        "jpg_path": frame.jpg_path,
        "raw_path": frame.raw_path,
        "kind": frame.kind,
        "camera_rating": {"stars": frame.camera_rating.stars, "label": frame.camera_rating.label},
        "thumbnail_url": f"/api/frames/{frame.id}/thumbnail",
    }
