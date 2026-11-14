"""The Judge: turns Groups of analysed Frames into a Proposal of Verdicts with Reasons.

Each Frame is first assessed on its own: its signals become Scores, and each flaw check may
find a Flaw that caps its Verdict at Unsure or Reject. A Camera rating nudges a Frame's Scores up
a little, never past a Flaw. Then each Group picks its Winner and proposes its flawed Frames as
Unsure or Rejects. The Keeper budget decides how many of the remaining Frames, best first across
the whole Session, become Keepers; the rest are Rejects.

A Frame with faces is judged on its faces: its sharpness is that of its softest face, and every
face must have open eyes and be sharp for the Frame to pass. A face much fainter than the Frame's
other faces, such as a reflection in glass, is left out.

The photographer's Verdict Overrides steer the Winner: a Frame they made the Winner wins its
Group, and a Frame they overrode to another Verdict is not picked, so the rest of the Group is
re-judged against the Winner that remains. Applying the Overrides themselves is up to the caller.
"""

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import PurePosixPath

from framewise.analyzer import Face, FrameSignals
from framewise.camera_rating import CameraRating
from framewise.store import AnalyzedFrame, FrameKind

# A whole Frame's sharpness counts its blurred background and plain walls too, so a Frame with a
# sharp subject and a shallow depth of field measures about 0.45 (sewts benchmark, #24). A face
# is measured on its own. Skin has few hard edges, so a sharp face measures only about 0.67 and
# scores full sharpness from there; sharp faces on sewts measure 0.57 to 1 (#30).
BLURRY_BELOW = 0.25
SOFT_BELOW = 0.4
FACE_BLURRY_BELOW = 0.25
FACE_SOFT_BELOW = 0.5
FACE_SHARP_FROM = 0.67
MOTION_BLUR_FROM = 0.5
POSSIBLE_MOTION_BLUR_FROM = 0.35
EXPOSURE_TOLERANCE_STOPS = 0.7
# Beyond these, a Frame is a Reject; between the tolerance and these, it is Unsure. A RAW+JPG
# Frame is judged more leniently because its RAW holds detail its JPG has clipped.
EXPOSURE_REJECT_BEYOND_STOPS: dict[FrameKind, float] = {"jpg-only": 1.25, "raw+jpg": 2.0}
# The share of a Session's Frames kept as Winners or Keepers until the photographer moves it.
DEFAULT_KEEPER_BUDGET = 0.4
# Added to the total Score of a Frame with in-camera stars.
CAMERA_RATING_HINT = 0.05
WEIGHTS = {
    "sharpness": 0.35,
    "steadiness": 0.15,
    "exposure": 0.2,
    "aesthetics": 0.3,
    "face_quality": 0.2,
}
EYES_CLOSED = "eyes-closed"
# Contrast is measured relative to a face's brightness, so a face in the shade keeps it. On sewts,
# faces reflected in glass keep at most 0.15 of the contrast of the Frame's most contrasty face,
# real faces at least 0.39, such as a pale child's face beside an adult's (#38).
FAINT_FACE_CONTRAST_SHARE = 1 / 4


class Verdict(StrEnum):
    WINNER = "winner"
    KEEPER = "keeper"
    REJECT = "reject"
    UNSURE = "unsure"


KEPT = {Verdict.WINNER, Verdict.KEEPER}


@dataclass(frozen=True)
class Reason:
    code: str
    label: str
    text: str


@dataclass(frozen=True)
class Scores:
    """Each Frame's score components from 0 (worst) to 1 (best), and their weighted total."""

    sharpness: float
    steadiness: float
    exposure: float
    aesthetics: float | None
    face_quality: float | None
    """The quality of the Frame's weakest face, or None without faces."""
    camera_rating: float
    """The hint a Camera rating adds to the total, or 0 without one."""
    total: float


@dataclass(frozen=True)
class FaceCheck:
    face: Face
    eyes_closed: bool
    soft: bool


@dataclass(frozen=True)
class Judgement:
    verdict: Verdict
    reasons: list[Reason]
    scores: Scores
    faces: list[FaceCheck]


Proposal = dict[int, Judgement]
"""Each Frame's Judgement, by Frame id."""


@dataclass(frozen=True)
class Flaw:
    reason: Reason
    caps_at: Verdict
    """Verdict.UNSURE or Verdict.REJECT."""


@dataclass(frozen=True)
class _Assessment:
    analyzed: AnalyzedFrame
    scores: Scores
    flaws: list[Flaw]

    @property
    def worst(self) -> Verdict | None:
        caps = {flaw.caps_at for flaw in self.flaws}
        for verdict in (Verdict.REJECT, Verdict.UNSURE):
            if verdict in caps:
                return verdict
        return None

    @property
    def reasons(self) -> list[Reason]:
        return [flaw.reason for flaw in self.flaws]

    @property
    def faces(self) -> list[FaceCheck]:
        return [_check_face(face) for face in self.analyzed.signals.faces]

    @property
    def has_eyes_closed(self) -> bool:
        return any(flaw.reason.code == EYES_CLOSED for flaw in self.flaws)

    @property
    def is_clean_with_open_eyes(self) -> bool:
        faces = self.analyzed.signals.faces
        return self.worst is None and bool(faces) and all(face.eyes_open for face in faces)

    def judgement(self, verdict: Verdict, reasons: list[Reason]) -> Judgement:
        return Judgement(verdict, reasons, self.scores, self.faces)


def judge(
    groups: list[list[AnalyzedFrame]],
    verdict_overrides: Mapping[str, Verdict] | None = None,
    keeper_budget: float = DEFAULT_KEEPER_BUDGET,
) -> Proposal:
    """Judges each Group, then keeps roughly `keeper_budget` of the Frames as Winners and
    Keepers. `verdict_overrides` holds the photographer's Verdict Overrides by JPG path; the
    Frames they kept count towards the budget and those they overrode are never re-judged by it."""
    overrides = verdict_overrides or {}
    proposal: Proposal = {}
    candidates: list[tuple[_Assessment, _Assessment]] = []
    kept = 0
    for group in groups:
        assessments = [_assess(analyzed) for analyzed in group]
        winner = _pick_winner(assessments, overrides)
        for assessment in assessments:
            override = _non_winner_override(assessment, overrides)
            if assessment is winner:
                judgement = winner.judgement(Verdict.WINNER, winner.reasons)
            else:
                judgement = _judge_flaws_against_winner(assessment, winner)
                if judgement is None and override is None:
                    candidates.append((assessment, winner))
                    continue
                judgement = judgement or assessment.judgement(Verdict.KEEPER, [])
            proposal[assessment.analyzed.frame.id] = judgement
            kept += (override or judgement.verdict) in KEPT
    frame_count = sum(len(group) for group in groups)
    keeper_slots = max(0, math.floor(keeper_budget * frame_count + 0.5) - kept)
    proposal.update(_judge_by_keeper_budget(candidates, keeper_slots))
    return proposal


def _non_winner_override(
    assessment: _Assessment, overrides: Mapping[str, Verdict]
) -> Verdict | None:
    """The photographer's Verdict Override of the Frame unless it is Winner, which only steers
    the Winner and falls back to framewise's Verdict when it lost to another one."""
    override = overrides.get(assessment.analyzed.frame.jpg_path)
    return None if override == Verdict.WINNER else override


def _judge_by_keeper_budget(
    candidates: list[tuple[_Assessment, _Assessment]], keeper_slots: int
) -> Proposal:
    """Keeps the best of the Frames without Flaws, across the whole Session, while the budget
    lasts. The rest are weaker duplicates of their Group's Winner."""
    ranked = sorted(candidates, key=lambda candidate: _keeper_rank(candidate[0]))
    proposal: Proposal = {}
    for index, (assessment, winner) in enumerate(ranked):
        if index < keeper_slots:
            judgement = assessment.judgement(Verdict.KEEPER, [])
        else:
            winner_name = PurePosixPath(winner.analyzed.frame.jpg_path).stem
            reason = Reason(
                "weaker-duplicate", "Weaker duplicate", f"Weaker duplicate of {winner_name}"
            )
            judgement = assessment.judgement(Verdict.REJECT, [reason])
        proposal[assessment.analyzed.frame.id] = judgement
    return proposal


def _keeper_rank(assessment: _Assessment) -> tuple[float, str]:
    return -assessment.scores.total, assessment.analyzed.frame.jpg_path


def _pick_winner(assessments: list[_Assessment], overrides: Mapping[str, Verdict]) -> _Assessment:
    """The first Frame the photographer made the Winner, or else framewise's best Frame among
    those without a Verdict Override. If every Frame has one, framewise's best Frame is the
    Winner only for the others to be judged against."""
    for assessment in assessments:
        if overrides.get(assessment.analyzed.frame.jpg_path) == Verdict.WINNER:
            return assessment
    candidates = [
        assessment
        for assessment in assessments
        if assessment.analyzed.frame.jpg_path not in overrides
    ]
    return min(candidates or assessments, key=_winner_rank)


def _winner_rank(assessment: _Assessment) -> tuple[int, float, str]:
    flaw_rank = {None: 0, Verdict.UNSURE: 1, Verdict.REJECT: 2}[assessment.worst]
    return flaw_rank, -assessment.scores.total, assessment.analyzed.frame.jpg_path


def _judge_flaws_against_winner(assessment: _Assessment, winner: _Assessment) -> Judgement | None:
    """The Verdict a Frame's Flaws give it, or None without Flaws. Closed eyes alone only make a
    Frame Unsure, as they may be deliberate, unless the Group's Winner shows the same moment with
    every eye open."""
    if assessment.has_eyes_closed and winner.is_clean_with_open_eyes:
        return assessment.judgement(Verdict.REJECT, assessment.reasons)
    if assessment.worst is not None:
        return assessment.judgement(assessment.worst, assessment.reasons)
    return None


def _assess(analyzed: AnalyzedFrame) -> _Assessment:
    signals = analyzed.signals
    analyzed = replace(analyzed, signals=replace(signals, faces=_judged_faces(signals.faces)))
    flaws = [flaw for check in FLAW_CHECKS for flaw in check(analyzed)]
    return _Assessment(analyzed, _scores(analyzed), flaws)


def _scores(analyzed: AnalyzedFrame) -> Scores:
    signals = analyzed.signals
    components = {
        "sharpness": _sharpness_score(signals),
        "steadiness": _clamp(1 - signals.motion_blur),
        "exposure": _exposure_score(signals, analyzed.frame.kind),
        "aesthetics": None if signals.aesthetics is None else _clamp((signals.aesthetics + 1) / 2),
        "face_quality": _face_quality(signals.faces),
    }
    available = {name: value for name, value in components.items() if value is not None}
    total_weight = sum(WEIGHTS[name] for name in available)
    weighted = sum(WEIGHTS[name] * value for name, value in available.items()) / total_weight
    hint = _camera_rating_hint(analyzed.frame.camera_rating)
    return Scores(**components, camera_rating=hint, total=weighted + hint)


def _camera_rating_hint(rating: CameraRating) -> float:
    """In-camera stars hint the photographer liked the Frame. A color label carries no
    agreed meaning, so it is no hint."""
    return CAMERA_RATING_HINT if (rating.stars or 0) > 0 else 0.0


def _exposure_score(signals: FrameSignals, kind: FrameKind) -> float:
    if _is_deliberate_key(signals):
        return 1.0
    excess = max(0.0, abs(signals.exposure_stops) - EXPOSURE_TOLERANCE_STOPS)
    return _clamp(1 - excess / (EXPOSURE_REJECT_BEYOND_STOPS[kind] - EXPOSURE_TOLERANCE_STOPS))


def _sharpness_score(signals: FrameSignals) -> float:
    if signals.faces:
        return _clamp(_judged_sharpness(signals) / FACE_SHARP_FROM)
    return _clamp(signals.sharpness)


def _judged_sharpness(signals: FrameSignals) -> float:
    if signals.faces:
        return min(face.sharpness for face in signals.faces)
    return signals.sharpness


def _judged_faces(faces: list[Face]) -> list[Face]:
    """Leaves out faces much fainter than the Frame's most contrasty face."""
    if not faces:
        return []
    contrast_from = FAINT_FACE_CONTRAST_SHARE * max(face.contrast for face in faces)
    return [face for face in faces if face.contrast >= contrast_from]


def _face_quality(faces: list[Face]) -> float | None:
    qualities = [face.quality for face in faces if face.quality is not None]
    return _clamp(min(qualities)) if qualities else None


def _check_face(face: Face) -> FaceCheck:
    soft = face.sharpness < FACE_SOFT_BELOW
    return FaceCheck(face, eyes_closed=face.eyes_open is False, soft=soft)


def _sharpness_flaws(analyzed: AnalyzedFrame) -> list[Flaw]:
    sharpness = _judged_sharpness(analyzed.signals)
    if analyzed.signals.faces:
        blurry = Reason("blurry-face", "Blurry face", "Blurry face")
        soft = Reason("soft-face", "Soft face", "Soft face")
        blurry_below, soft_below = FACE_BLURRY_BELOW, FACE_SOFT_BELOW
    else:
        blurry = Reason("blurry", "Blurry", "Blurry")
        soft = Reason("soft", "Slightly soft", "Slightly soft")
        blurry_below, soft_below = BLURRY_BELOW, SOFT_BELOW
    if sharpness < blurry_below:
        return [Flaw(blurry, Verdict.REJECT)]
    if sharpness < soft_below:
        return [Flaw(soft, Verdict.UNSURE)]
    return []


def _eyes_flaws(analyzed: AnalyzedFrame) -> list[Flaw]:
    if any(face.eyes_open is False for face in analyzed.signals.faces):
        return [Flaw(Reason(EYES_CLOSED, "Eyes closed", "Eyes closed"), Verdict.UNSURE)]
    return []


def _motion_blur_flaws(analyzed: AnalyzedFrame) -> list[Flaw]:
    motion_blur = analyzed.signals.motion_blur
    if motion_blur >= MOTION_BLUR_FROM:
        return [Flaw(Reason("motion-blur", "Motion blur", "Motion blur"), Verdict.REJECT)]
    if motion_blur >= POSSIBLE_MOTION_BLUR_FROM:
        reason = Reason("possible-motion-blur", "Possible motion blur", "Possible motion blur")
        return [Flaw(reason, Verdict.UNSURE)]
    return []


def _exposure_flaws(analyzed: AnalyzedFrame) -> list[Flaw]:
    signals = analyzed.signals
    stops = signals.exposure_stops
    if abs(stops) <= EXPOSURE_TOLERANCE_STOPS or _is_deliberate_key(signals):
        return []
    label = "Underexposed" if stops < 0 else "Overexposed"
    reason = Reason(label.lower(), label, f"{label} {_format_stops(abs(stops))}")
    beyond = abs(stops) > EXPOSURE_REJECT_BEYOND_STOPS[analyzed.frame.kind]
    return [Flaw(reason, Verdict.REJECT if beyond else Verdict.UNSURE)]


FLAW_CHECKS: tuple[Callable[[AnalyzedFrame], list[Flaw]], ...] = (
    _eyes_flaws,
    _sharpness_flaws,
    _motion_blur_flaws,
    _exposure_flaws,
)


def _is_deliberate_key(signals: FrameSignals) -> bool:
    return (signals.low_key and signals.exposure_stops < 0) or (
        signals.high_key and signals.exposure_stops > 0
    )


def _format_stops(stops: float) -> str:
    rounded = round(stops, 1)
    number = f"{rounded:g}"
    return f"{number} stop" if rounded == 1 else f"{number} stops"


def _clamp(value: float) -> float:
    return min(1.0, max(0.0, value))
