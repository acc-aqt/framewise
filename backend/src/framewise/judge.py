"""The Judge: turns Groups of analysed Frames into a Proposal of Verdicts with Reasons.

Each Frame is first assessed on its own: its signals become Scores, and each flaw check may
find a Flaw that caps its Verdict at Unsure or Reject. Then each Group picks its Winner and
proposes the rest as Keepers, Unsure or Rejects.
"""

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePosixPath

from framewise.analyzer import FrameSignals
from framewise.store import AnalyzedFrame, FrameKind

BLURRY_BELOW = 0.25
SOFT_BELOW = 0.5
MOTION_BLUR_FROM = 0.5
POSSIBLE_MOTION_BLUR_FROM = 0.35
EXPOSURE_TOLERANCE_STOPS = 0.7
# Beyond these, a Frame is a Reject; between the tolerance and these, it is Unsure. A RAW+JPG
# Frame is judged more leniently because its RAW holds detail its JPG has clipped.
EXPOSURE_REJECT_BEYOND_STOPS: dict[FrameKind, float] = {"jpg-only": 1.25, "raw+jpg": 2.0}
# A Frame scoring within this margin of its Group's Winner is a Keeper.
KEEPER_MARGIN = 0.1
WEIGHTS = {"sharpness": 0.35, "steadiness": 0.15, "exposure": 0.2, "aesthetics": 0.3}


class Verdict(StrEnum):
    WINNER = "winner"
    KEEPER = "keeper"
    REJECT = "reject"
    UNSURE = "unsure"


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
    total: float


@dataclass(frozen=True)
class Judgement:
    verdict: Verdict
    reasons: list[Reason]
    scores: Scores


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


def judge(groups: list[list[AnalyzedFrame]]) -> Proposal:
    proposal: Proposal = {}
    for group in groups:
        proposal.update(_judge_group([_assess(analyzed) for analyzed in group]))
    return proposal


def _judge_group(assessments: list[_Assessment]) -> Proposal:
    winner = min(assessments, key=_winner_rank)
    proposal = {winner.analyzed.frame.id: Judgement(Verdict.WINNER, winner.reasons, winner.scores)}
    for assessment in assessments:
        if assessment is not winner:
            proposal[assessment.analyzed.frame.id] = _judge_against_winner(assessment, winner)
    return proposal


def _winner_rank(assessment: _Assessment) -> tuple[int, float, str]:
    flaw_rank = {None: 0, Verdict.UNSURE: 1, Verdict.REJECT: 2}[assessment.worst]
    return flaw_rank, -assessment.scores.total, assessment.analyzed.frame.jpg_path


def _judge_against_winner(assessment: _Assessment, winner: _Assessment) -> Judgement:
    if assessment.worst is not None:
        return Judgement(assessment.worst, assessment.reasons, assessment.scores)
    if assessment.scores.total >= winner.scores.total - KEEPER_MARGIN:
        return Judgement(Verdict.KEEPER, [], assessment.scores)
    winner_name = PurePosixPath(winner.analyzed.frame.jpg_path).stem
    reason = Reason("weaker-duplicate", "Weaker duplicate", f"Weaker duplicate of {winner_name}")
    return Judgement(Verdict.REJECT, [reason], assessment.scores)


def _assess(analyzed: AnalyzedFrame) -> _Assessment:
    flaws = [flaw for check in FLAW_CHECKS for flaw in check(analyzed)]
    return _Assessment(analyzed, _scores(analyzed), flaws)


def _scores(analyzed: AnalyzedFrame) -> Scores:
    signals = analyzed.signals
    components = {
        "sharpness": _clamp(signals.sharpness),
        "steadiness": _clamp(1 - signals.motion_blur),
        "exposure": _exposure_score(signals, analyzed.frame.kind),
        "aesthetics": None if signals.aesthetics is None else _clamp((signals.aesthetics + 1) / 2),
    }
    available = {name: value for name, value in components.items() if value is not None}
    total_weight = sum(WEIGHTS[name] for name in available)
    total = sum(WEIGHTS[name] * value for name, value in available.items()) / total_weight
    return Scores(**components, total=total)


def _exposure_score(signals: FrameSignals, kind: FrameKind) -> float:
    if _is_deliberate_key(signals):
        return 1.0
    excess = max(0.0, abs(signals.exposure_stops) - EXPOSURE_TOLERANCE_STOPS)
    return _clamp(1 - excess / (EXPOSURE_REJECT_BEYOND_STOPS[kind] - EXPOSURE_TOLERANCE_STOPS))


def _sharpness_flaws(analyzed: AnalyzedFrame) -> list[Flaw]:
    sharpness = analyzed.signals.sharpness
    if sharpness < BLURRY_BELOW:
        return [Flaw(Reason("blurry", "Blurry", "Blurry"), Verdict.REJECT)]
    if sharpness < SOFT_BELOW:
        return [Flaw(Reason("soft", "Slightly soft", "Slightly soft"), Verdict.UNSURE)]
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
