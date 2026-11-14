from dataclasses import asdict, replace
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from framewise.exiftool import ExifTool
from framewise.grouper import group_frames
from framewise.judge import DEFAULT_KEEPER_BUDGET, FaceCheck, Judgement, Proposal, Verdict, judge
from framewise.lightroom import read_label_set
from framewise.review import SessionAnalysis
from framewise.store import AnalyzedFrame, Frame, Override, SessionStore
from framewise.write_back import (
    FileChange,
    Rating,
    RatingWriteBack,
    ReviewedFrame,
    WriteBackResult,
)

ENGLISH_DEFAULTS_NOTICE = (
    "No Lightroom Classic color label set was found, so Lightroom's English defaults "
    "Red, Yellow, Green, Blue and Purple are used."
)

ColorLabel = Literal["red", "yellow", "green", "blue", "purple"]


class OverrideChange(BaseModel):
    """The fields of an Override to change. A field sent as null is cleared; one left out is
    kept."""

    verdict: Verdict | None = None
    stars: int | None = Field(default=None, ge=0, le=5)
    label: ColorLabel | None = None


class FrameSelection(BaseModel):
    frame_ids: list[int] = Field(min_length=1)


class FrameMove(BaseModel):
    to_frame_id: int


class SessionChange(BaseModel):
    keeper_budget: float = Field(ge=0, le=1)
    """The share of the Session's Frames the photographer roughly wants to keep."""


def create_app(
    store: SessionStore,
    analysis: SessionAnalysis,
    ui_dir: Path | None = None,
    lightroom_preferences: Path | None = None,
) -> FastAPI:
    app = FastAPI(title="framewise")
    write_back = RatingWriteBack(store, ExifTool())

    def _groups() -> list[list[AnalyzedFrame]]:
        return group_frames(store.analyzed_frames(), store.group_overrides())

    def _group_paths() -> list[list[str]]:
        return [[analyzed.frame.jpg_path for analyzed in group] for group in _groups()]

    def reviewed_proposal() -> tuple[list[list[AnalyzedFrame]], dict[str, Override], Proposal]:
        groups = _groups()
        overrides = store.overrides()
        verdict_overrides = {
            path: Verdict(override.verdict)
            for path, override in overrides.items()
            if override.verdict is not None
        }
        return groups, overrides, judge(groups, verdict_overrides, _keeper_budget())

    def reviewed_frames() -> list[ReviewedFrame]:
        groups, overrides, proposal = reviewed_proposal()
        reviewed = []
        for analyzed in sorted(
            (analyzed for group in groups for analyzed in group),
            key=lambda analyzed: analyzed.frame.jpg_path,
        ):
            override = overrides.get(analyzed.frame.jpg_path) or Override()
            verdict, _ = _reviewed_verdict(proposal[analyzed.frame.id], override)
            reviewed.append(ReviewedFrame(analyzed.frame, verdict, override.stars, override.label))
        return reviewed

    def require_finished_analysis() -> None:
        if analysis.progress().frames_left > 0:
            raise HTTPException(
                status_code=409, detail="Rating write-back waits until analysis has finished"
            )

    @app.get("/api/session")
    def session_summary() -> dict:
        summary = store.summary()
        return {
            "root": str(store.root),
            "total_frames": summary.total_frames,
            "jpg_only_count": summary.jpg_only_count,
            "raw_jpg_count": summary.raw_jpg_count,
            "skipped": summary.skipped,
            "keeper_budget": _keeper_budget(),
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
        groups, overrides, proposal = reviewed_proposal()
        group_overrides = store.group_overrides()
        return [
            {
                "id": group[0].frame.id,
                "fixed": any(analyzed.frame.jpg_path in group_overrides for analyzed in group),
                "frames": [
                    _judged_frame_json(
                        analyzed,
                        proposal[analyzed.frame.id],
                        overrides.get(analyzed.frame.jpg_path),
                    )
                    for analyzed in group
                ],
            }
            for group in groups
        ]

    @app.patch("/api/session")
    def change_session(change: SessionChange) -> dict:
        store.save_keeper_budget(change.keeper_budget)
        return session_summary()

    def _keeper_budget() -> float:
        share = store.keeper_budget()
        return DEFAULT_KEEPER_BUDGET if share is None else share

    @app.patch("/api/frames/{frame_id}/override")
    def change_override(frame_id: int, change: OverrideChange) -> dict:
        frame = _known_frame(frame_id)
        current = store.overrides().get(frame.jpg_path, Override())
        updated = replace(current, **change.model_dump(mode="json", exclude_unset=True))
        store.save_override(frame.jpg_path, updated)
        if updated.verdict == Verdict.WINNER:
            _unchoose_other_winners(frame)
        return _override_json(updated)

    @app.delete("/api/frames/{frame_id}/override", status_code=204)
    def clear_override(frame_id: int) -> None:
        store.save_override(_known_frame(frame_id).jpg_path, Override())

    @app.get("/api/frames/{frame_id}/image")
    def frame_image(frame_id: int) -> FileResponse:
        path = store.root / _known_frame(frame_id).jpg_path
        if not path.is_file():
            raise HTTPException(status_code=404, detail="JPG not found")
        return FileResponse(path, media_type="image/jpeg")

    def _known_frame(frame_id: int) -> Frame:
        frame = store.frame(frame_id)
        if frame is None:
            raise HTTPException(status_code=404, detail="Frame not found")
        return frame

    def _unchoose_other_winners(winner: Frame) -> None:
        """Keeps one Winner per Group: the Frames the photographer made the Winner before in the
        new Winner's Group are judged by framewise again."""
        overrides = store.overrides()
        for path in _group_of(winner.jpg_path, _group_paths()) or []:
            override = overrides.get(path)
            if path != winner.jpg_path and override and override.verdict == Verdict.WINNER:
                store.save_override(path, replace(override, verdict=None))

    @app.post("/api/groups/split", status_code=204)
    def split_group(selection: FrameSelection) -> None:
        """Splits the selected Frames off their Group into a Group of their own."""
        selected = {frame.jpg_path for frame in _known_frames(selection.frame_ids)}
        holding = _groups_holding(selected, _group_paths())
        if len(holding) != 1:
            raise HTTPException(status_code=422, detail="The Frames must lie in one Group")
        [group] = holding
        rest = [path for path in group if path not in selected]
        if not rest:
            raise HTTPException(status_code=422, detail="Cannot split off a whole Group")
        store.save_group_overrides([rest, [path for path in group if path in selected]])

    @app.post("/api/groups/merge", status_code=204)
    def merge_groups(selection: FrameSelection) -> None:
        """Merges the Groups holding the selected Frames into one."""
        selected = {frame.jpg_path for frame in _known_frames(selection.frame_ids)}
        merged = _groups_holding(selected, _group_paths())
        if len(merged) < 2:
            raise HTTPException(status_code=422, detail="The Frames must lie in two Groups or more")
        store.save_group_overrides([[path for group in merged for path in group]])

    @app.post("/api/frames/{frame_id}/move", status_code=204)
    def move_frame(frame_id: int, move: FrameMove) -> None:
        """Moves a Frame into the Group of another Frame."""
        groups = _group_paths()
        frame = _known_frame(frame_id)
        source = _grouped(frame, groups)
        target = _grouped(_known_frame(move.to_frame_id), groups)
        if source == target:
            raise HTTPException(status_code=422, detail="The Frame is in that Group already")
        rest = [path for path in source if path != frame.jpg_path]
        store.save_group_overrides([group for group in (rest, [*target, frame.jpg_path]) if group])

    @app.post("/api/groups/reset", status_code=204)
    def reset_groups(selection: FrameSelection) -> None:
        """Hands the fixed Groups of the selected Frames back to framewise's grouping."""
        store.clear_group_overrides(
            [frame.jpg_path for frame in _known_frames(selection.frame_ids)]
        )

    def _known_frames(frame_ids: list[int]) -> list[Frame]:
        return [_known_frame(frame_id) for frame_id in frame_ids]

    @app.get("/api/write-back")
    def write_back_dry_run() -> dict:
        label_set = read_label_set(lightroom_preferences)
        return {
            "label_set": asdict(label_set),
            "notice": None if label_set.from_lightroom else ENGLISH_DEFAULTS_NOTICE,
            "files": [
                _file_change_json(change)
                for change in write_back.dry_run(reviewed_frames(), label_set)
            ],
            "can_undo": write_back.can_undo(),
        }

    @app.post("/api/write-back")
    def write_back_apply() -> dict:
        require_finished_analysis()
        label_set = read_label_set(lightroom_preferences)
        return _write_back_result_json(write_back.apply(reviewed_frames(), label_set))

    @app.post("/api/write-back/undo")
    def write_back_undo() -> dict:
        require_finished_analysis()
        return _write_back_result_json(write_back.undo())

    @app.get("/api/frames/{frame_id}/thumbnail")
    def frame_thumbnail(frame_id: int) -> Response:
        thumbnail = store.thumbnail(frame_id)
        if thumbnail is None:
            raise HTTPException(status_code=404, detail="Frame not found")
        return Response(content=thumbnail, media_type="image/jpeg")

    if ui_dir is not None and (ui_dir / "index.html").is_file():
        app.mount("/", StaticFiles(directory=ui_dir, html=True), name="review-ui")

    return app


def _group_of(jpg_path: str, groups: list[list[str]]) -> list[str] | None:
    return next((group for group in groups if jpg_path in group), None)


def _grouped(frame: Frame, groups: list[list[str]]) -> list[str]:
    """The Group of a Frame, which must be analysed already to be in one."""
    group = _group_of(frame.jpg_path, groups)
    if group is None:
        raise HTTPException(status_code=422, detail="The Frame is not in a Group yet")
    return group


def _groups_holding(paths: set[str], groups: list[list[str]]) -> list[list[str]]:
    """The distinct Groups holding the Frames at `paths`, all of which must be in a Group."""
    holding = [group for group in groups if paths.intersection(group)]
    if any(_group_of(path, holding) is None for path in paths):
        raise HTTPException(status_code=422, detail="A Frame is not in a Group yet")
    return holding


def _frame_json(frame: Frame) -> dict:
    return {
        "id": frame.id,
        "jpg_path": frame.jpg_path,
        "raw_path": frame.raw_path,
        "kind": frame.kind,
        "camera_rating": {"stars": frame.camera_rating.stars, "label": frame.camera_rating.label},
        "thumbnail_url": f"/api/frames/{frame.id}/thumbnail",
        "image_url": f"/api/frames/{frame.id}/image",
    }


def _file_change_json(change: FileChange) -> dict:
    return {
        "frame_id": change.frame_id,
        "path": change.path,
        "written_to": change.written_to,
        "verdict": change.verdict.value,
        "old": _rating_json(change.old),
        "new": _rating_json(change.new),
    }


def _rating_json(rating: Rating) -> dict:
    return {"stars": rating.stars, "label": rating.label}


def _write_back_result_json(result: WriteBackResult) -> dict:
    return {"written": result.written, "failed": [asdict(failure) for failure in result.failed]}


def _override_json(override: Override) -> dict:
    return {"verdict": override.verdict, "stars": override.stars, "label": override.label}


def _reviewed_verdict(judgement: Judgement, override: Override | None) -> tuple[Verdict, bool]:
    """The Verdict to show and whether it is the photographer's Override. A Winner Override
    that lost to another one after Groups merged falls back to framewise's Verdict."""
    if override is None or override.verdict is None:
        return judgement.verdict, False
    if override.verdict == Verdict.WINNER:
        return judgement.verdict, judgement.verdict == Verdict.WINNER
    return Verdict(override.verdict), True


def _judged_frame_json(
    analyzed: AnalyzedFrame, judgement: Judgement, override: Override | None
) -> dict:
    signals = asdict(analyzed.signals)
    del signals["fingerprint"]
    verdict, overridden = _reviewed_verdict(judgement, override)
    return {
        **_frame_json(analyzed.frame),
        "verdict": verdict.value,
        "verdict_overridden": overridden,
        "override": None if override is None else _override_json(override),
        "reasons": [asdict(reason) for reason in judgement.reasons],
        "scores": {
            name: None if value is None else round(value, 3)
            for name, value in asdict(judgement.scores).items()
        },
        "signals": signals,
        "faces": [_face_json(check) for check in judgement.faces],
    }


def _face_json(check: FaceCheck) -> dict:
    face = check.face
    if face.eyes_open is None:
        eyes = "unknown"
    else:
        eyes = "closed" if check.eyes_closed else "open"
    return {
        "box": {"x": face.x, "y": face.y, "width": face.width, "height": face.height},
        "eyes": eyes,
        "focus": "soft" if check.soft else "sharp",
    }
