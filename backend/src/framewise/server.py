from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, HTTPException, Response
from fastapi.staticfiles import StaticFiles

from framewise.grouper import group_frames
from framewise.judge import Judgement, judge
from framewise.review import SessionAnalysis
from framewise.store import AnalyzedFrame, Frame, SessionStore


def create_app(
    store: SessionStore, analysis: SessionAnalysis, ui_dir: Path | None = None
) -> FastAPI:
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

    @app.get("/api/progress")
    def analysis_progress() -> dict:
        progress = analysis.progress()
        return {
            "frames_done": progress.frames_done,
            "frames_left": progress.frames_left,
            "seconds_remaining": progress.seconds_remaining,
        }

    @app.get("/api/frames")
    def frame_list() -> list[dict]:
        return [_frame_json(frame) for frame in store.frames()]

    @app.get("/api/groups")
    def group_list() -> list[dict]:
        groups = group_frames(store.analyzed_frames())
        proposal = judge(groups)
        return [
            {
                "id": group[0].frame.id,
                "frames": [
                    _judged_frame_json(analyzed, proposal[analyzed.frame.id]) for analyzed in group
                ],
            }
            for group in groups
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


def _judged_frame_json(analyzed: AnalyzedFrame, judgement: Judgement) -> dict:
    signals = asdict(analyzed.signals)
    del signals["fingerprint"]
    return {
        **_frame_json(analyzed.frame),
        "verdict": judgement.verdict.value,
        "reasons": [asdict(reason) for reason in judgement.reasons],
        "scores": {
            name: None if value is None else round(value, 3)
            for name, value in asdict(judgement.scores).items()
        },
        "signals": signals,
    }
