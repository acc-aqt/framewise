"""The reference benchmark: how often the Proposal agrees with the photographer's Reference
ratings in Lightroom Classic, and how long a cold first pass over a Session takes.

Run by hand, not in CI. It reads a copy of the Lightroom Classic catalog, never the catalog
itself, and keeps its Session store in a temporary folder, so it writes nothing outside the
report.
"""

import argparse
import json
import plistlib
import shutil
import sqlite3
import sys
import tempfile
import time
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from itertools import combinations
from pathlib import Path

from framewise.analyzer import FrameAnalyzer, FrameSignals
from framewise.judge import KEPT, WEIGHTS, Proposal, Scores, Verdict, judge, judged_sharpness
from framewise.lightroom import LIGHTROOM_PREFERENCES
from framewise.previews import PreviewConfigError, read_min_preview_long_edge
from framewise.providers import Provider, ProviderError, resolve_analyzer
from framewise.review import SessionAnalysis, open_session, resolve_config_path
from framewise.store import AnalyzedFrame, Frame
from framewise.weight_fit import fit_weights

ACTIVE_CATALOG_KEY = "libraryToLoad20"
# ADR-0002: 15 minutes for a 200-Frame Session on the first pass.
BUDGET_SECONDS_PER_FRAME = 15 * 60 / 200
NOT_KEPT = {Verdict.REJECT, Verdict.UNSURE}
FOLDS = 5
FIT_WEIGHTS_HELP = """\
Also fit the Score weights to the Reference ratings and print them; nothing is changed. Two
Frames of a Group with different Reference ratings (none counts as 0 stars) make a pair, the
higher rated one preferred. The proposed weights are fitted to every pair, on the scale of
today's. Held-out figures come from cross-validation by Group: each Group is judged with weights
fitted to the other Groups only, next to the current weights. "Pairs ranked as rated" is how
often the preferred Frame gets the higher total Score; "Winners among their Group's top-rated
Frames" is Winner agreement. Copy the proposed weights into judge.py only if they do better."""

REFERENCE_RATINGS_QUERY = """
SELECT root.absolutePath || folder.pathFromRoot || file.baseName || '.' || file.extension AS path,
       image.rating AS rating
FROM Adobe_images AS image
JOIN AgLibraryFile AS file ON file.id_local = image.rootFile
JOIN AgLibraryFolder AS folder ON folder.id_local = file.folder
JOIN AgLibraryRootFolder AS root ON root.id_local = folder.rootFolder
WHERE image.rating >= 1 AND image.masterImage IS NULL
"""


@dataclass(frozen=True)
class Agreement:
    kept: int
    kept_with_reference: int
    rejected: int
    rejected_with_reference: int
    with_reference: int
    with_reference_rejected_or_unsure: int
    verdicts_by_reference_stars: dict[int, dict[str, int]]
    reasons_on_rated_rejects_or_unsure: dict[str, int]


@dataclass(frozen=True)
class WinnerAgreement:
    agreeing: int
    groups: int
    share: float | None


@dataclass(frozen=True)
class HeldOut:
    ranked_as_rated: int
    pairs: int
    winners: WinnerAgreement


@dataclass(frozen=True)
class WeightFit:
    pairs: int
    folds: int
    proposed: dict[str, float] | None
    """Fitted to every pair, or None when the pairs favor no Score component."""
    current: HeldOut | None
    """The current weights on the held-out Groups, or None with fewer than two Groups."""
    fitted: HeldOut | None
    """Weights fitted without each held-out Group, on that Group."""


@dataclass(frozen=True)
class Timing:
    frames: int
    seconds: float
    seconds_per_frame: float
    budget_seconds: float
    within_budget: bool


def active_catalog(prefs: Path | None = LIGHTROOM_PREFERENCES) -> Path | None:
    """The catalog Lightroom Classic loads, or None without its preferences."""
    if prefs is None:
        return None
    try:
        with prefs.open("rb") as file:
            catalog = plistlib.load(file).get(ACTIVE_CATALOG_KEY)
    except (OSError, plistlib.InvalidFileException):
        return None
    return None if catalog is None else Path(catalog)


def copy_catalog(catalog: Path, into: Path) -> Path:
    """Copies the catalog and its write-ahead log, which holds changes Lightroom has not yet
    folded into the catalog file. Only the copy is ever opened."""
    copy = into / catalog.name
    shutil.copyfile(catalog, copy)
    wal = Path(f"{catalog}-wal")
    if wal.exists():
        shutil.copyfile(wal, Path(f"{copy}-wal"))
    return copy


def read_reference_ratings(catalog_copy: Path, session_root: Path) -> dict[Path, int]:
    """Star ratings of the catalog's photos inside the Session folder, by file path.
    Virtual copies are left out because they share their master's file."""
    prefix = _folder_key(session_root)
    with sqlite3.connect(f"file:{catalog_copy}?mode=ro", uri=True) as db:
        rows = db.execute(REFERENCE_RATINGS_QUERY).fetchall()
    return {Path(path): int(rating) for path, rating in rows if _path_key(path).startswith(prefix)}


def match_references(
    frames: list[Frame], session_root: Path, ratings: dict[Path, int]
) -> dict[int, int]:
    """Each Frame's Reference rating, by Frame id, matched on its main file's path. Paths compare
    case-insensitively, as macOS file systems do."""
    by_path = {_path_key(path): stars for path, stars in ratings.items()}
    references = {}
    for frame in frames:
        stars = by_path.get(_path_key(session_root / frame.main_path))
        if stars is not None:
            references[frame.id] = stars
    return references


def agreement(proposal: Proposal, references: dict[int, int]) -> Agreement:
    kept = [frame_id for frame_id, j in proposal.items() if j.verdict in KEPT]
    rejected = [frame_id for frame_id, j in proposal.items() if j.verdict == Verdict.REJECT]
    rated = [frame_id for frame_id in proposal if frame_id in references]
    rated_not_kept = [frame_id for frame_id in rated if proposal[frame_id].verdict in NOT_KEPT]
    by_stars: dict[int, Counter[str]] = {}
    for frame_id in rated:
        by_stars.setdefault(references[frame_id], Counter())[proposal[frame_id].verdict.value] += 1
    reasons = Counter(
        reason.code for frame_id in rated_not_kept for reason in proposal[frame_id].reasons
    )
    return Agreement(
        kept=len(kept),
        kept_with_reference=sum(frame_id in references for frame_id in kept),
        rejected=len(rejected),
        rejected_with_reference=sum(frame_id in references for frame_id in rejected),
        with_reference=len(rated),
        with_reference_rejected_or_unsure=len(rated_not_kept),
        verdicts_by_reference_stars={
            stars: dict(counts) for stars, counts in sorted(by_stars.items())
        },
        reasons_on_rated_rejects_or_unsure=dict(reasons.most_common()),
    )


def winner_agreement(
    proposal: Proposal, groups: list[list[int]], references: dict[int, int]
) -> WinnerAgreement:
    """How many Groups with a Reference rating have a Winner among their highest-rated Frames.
    `groups` holds each Group's Frame ids. A Group of one Frame is left out, as its Winner
    could not disagree, and an unrated Frame ranks below every rated one."""
    counted = [
        group
        for group in groups
        if len(group) > 1 and any(frame_id in references for frame_id in group)
    ]
    agreeing = [group for group in counted if _winner_is_top_rated(proposal, group, references)]
    return WinnerAgreement(
        agreeing=len(agreeing),
        groups=len(counted),
        share=len(agreeing) / len(counted) if counted else None,
    )


def _winner_is_top_rated(proposal: Proposal, group: list[int], references: dict[int, int]) -> bool:
    top = max(references[frame_id] for frame_id in group if frame_id in references)
    return any(
        proposal[frame_id].verdict == Verdict.WINNER and references.get(frame_id) == top
        for frame_id in group
    )


def weight_fit(
    groups: list[list[AnalyzedFrame]], references: dict[int, int], folds: int = FOLDS
) -> WeightFit:
    """Fits the Score weights to the Reference ratings and cross-validates them by Group, so
    no Group is used for fitting and testing at once. A fold whose training pairs favor no
    Score component is judged with the current weights."""
    scores = {frame_id: j.scores for frame_id, j in judge(groups).items()}
    proposed = fit_weights(_score_pairs(groups, references, scores))
    pairs = len(_preference_pairs(groups, references))
    folds = min(folds, len(groups))
    if folds < 2:
        return WeightFit(pairs, folds, proposed, current=None, fitted=None)
    current, fitted = [], []
    for fold in range(folds):
        held_out = groups[fold::folds]
        training = [group for index, group in enumerate(groups) if index % folds != fold]
        weights = fit_weights(_score_pairs(training, references, scores)) or WEIGHTS
        current.append(_held_out(held_out, references, WEIGHTS))
        fitted.append(_held_out(held_out, references, weights))
    return WeightFit(pairs, folds, proposed, _sum_held_out(current), _sum_held_out(fitted))


def _preference_pairs(
    groups: list[list[AnalyzedFrame]], references: dict[int, int]
) -> list[tuple[int, int]]:
    """Pairs of Frame ids in the same Group with different Reference ratings, the higher rated
    first. An unrated Frame counts as 0 stars."""
    pairs = []
    for group in groups:
        for first, second in combinations([analyzed.frame.id for analyzed in group], 2):
            first_stars, second_stars = references.get(first, 0), references.get(second, 0)
            if first_stars > second_stars:
                pairs.append((first, second))
            elif second_stars > first_stars:
                pairs.append((second, first))
    return pairs


def _score_pairs(
    groups: list[list[AnalyzedFrame]], references: dict[int, int], scores: dict[int, Scores]
) -> list[tuple[Scores, Scores]]:
    return [
        (scores[better], scores[worse]) for better, worse in _preference_pairs(groups, references)
    ]


def _held_out(
    groups: list[list[AnalyzedFrame]], references: dict[int, int], weights: Mapping[str, float]
) -> HeldOut:
    proposal = judge(groups, weights=weights)
    pairs = _preference_pairs(groups, references)
    ranked = sum(
        proposal[better].scores.total > proposal[worse].scores.total for better, worse in pairs
    )
    group_ids = [[analyzed.frame.id for analyzed in group] for group in groups]
    return HeldOut(ranked, len(pairs), winner_agreement(proposal, group_ids, references))


def _sum_held_out(parts: list[HeldOut]) -> HeldOut:
    agreeing = sum(part.winners.agreeing for part in parts)
    groups = sum(part.winners.groups for part in parts)
    return HeldOut(
        ranked_as_rated=sum(part.ranked_as_rated for part in parts),
        pairs=sum(part.pairs for part in parts),
        winners=WinnerAgreement(agreeing, groups, agreeing / groups if groups else None),
    )


def timing(frames: int, seconds: float) -> Timing:
    budget = frames * BUDGET_SECONDS_PER_FRAME
    return Timing(
        frames=frames,
        seconds=seconds,
        seconds_per_frame=seconds / frames if frames else 0.0,
        budget_seconds=budget,
        within_budget=seconds <= budget,
    )


def main(
    argv: list[str] | None = None,
    analyzer: FrameAnalyzer | None = None,
    clock: Callable[[], float] = time.perf_counter,
    providers: list[Provider] | None = None,
    platform: str = sys.platform,
) -> None:
    parser = argparse.ArgumentParser(
        prog="framewise-benchmark",
        description="Measure agreement with Lightroom Reference ratings and analysis time.",
    )
    parser.add_argument("session_folder", type=Path)
    parser.add_argument(
        "--catalog",
        type=Path,
        help="Lightroom Classic catalog to copy (default: the active one from Lightroom's prefs)",
    )
    parser.add_argument("--report", type=Path, default=Path("framewise-benchmark.json"))
    parser.add_argument(
        "--provider",
        dest="overrides",
        metavar="CAPABILITY=ID",
        type=_provider_override,
        action="append",
        default=[],
        help="Use this Provider for the Capability, over config.toml's choice (repeatable)",
    )
    parser.add_argument("--fit-weights", action="store_true", help=FIT_WEIGHTS_HELP)
    args = parser.parse_args(argv)
    if platform == "win32":
        parser.error("does not run on Windows, where Lightroom's catalog paths are not read yet")

    session_root = args.session_folder.resolve()
    if not session_root.is_dir():
        parser.error(f"not a folder: {args.session_folder}")
    if args.report.resolve().is_relative_to(session_root):
        parser.error("the report must not be written into the Session folder")
    catalog = args.catalog or active_catalog()
    if catalog is None:
        parser.error("no active Lightroom Classic catalog found, pass --catalog")
    if not catalog.is_file():
        parser.error(f"no catalog at {catalog}")

    if analyzer is None:
        analyzer = _resolve_analyzer(dict(args.overrides), providers)
    min_preview_long_edge = _read_min_preview_long_edge()

    with tempfile.TemporaryDirectory(prefix="framewise-benchmark-") as temp:
        catalog_copy = copy_catalog(catalog, Path(temp))
        ratings = read_reference_ratings(catalog_copy, session_root)
        report = _run(
            session_root,
            Path(temp) / "session-store",
            analyzer,
            ratings,
            clock,
            min_preview_long_edge,
            args.fit_weights,
        )

    args.report.write_text(json.dumps(report, indent=2))
    print(_summary(report, catalog, args.report))


def _run(
    session_root: Path,
    data_dir: Path,
    analyzer: FrameAnalyzer,
    ratings: dict[Path, int],
    clock: Callable[[], float],
    min_preview_long_edge: int,
    fit: bool,
) -> dict:
    """A cold first pass: a fresh Session store, so every Frame is analyzed."""
    started = clock()
    store = open_session(session_root, data_dir, min_preview_long_edge=min_preview_long_edge)
    analysis = SessionAnalysis(store, analyzer)
    analysis.run()
    analysed = clock()
    groups = analysis.groups()
    proposal = judge(groups)
    judged = clock()

    frames = store.frames()
    references = match_references(frames, session_root, ratings)
    group_ids = [[analyzed.frame.id for analyzed in group] for group in groups]
    signals = {analyzed.frame.id: analyzed.signals for group in groups for analyzed in group}
    report = {
        "session": str(session_root),
        "frames": len(frames),
        "frames_analysed": sum(len(group) for group in groups),
        "providers": dict(analyzer.signature),
        "agreement": asdict(agreement(proposal, references)),
        "winner_agreement": asdict(winner_agreement(proposal, group_ids, references)),
        "timing": asdict(timing(len(frames), judged - started)),
        "analysis_seconds": analysed - started,
        "judging_seconds": judged - analysed,
        "frame_results": [
            _frame_result(frame, proposal, references, signals[frame.id])
            for frame in frames
            if frame.id in proposal
        ],
    }
    if fit:
        report["weight_fit"] = asdict(weight_fit(groups, references))
    return report


def _frame_result(
    frame: Frame, proposal: Proposal, references: dict[int, int], signals: FrameSignals
) -> dict:
    judgement = proposal[frame.id]
    measured_on, sharpness = judged_sharpness(signals)
    return {
        "main_path": frame.main_path,
        "reference_stars": references.get(frame.id),
        "verdict": judgement.verdict.value,
        "reasons": [reason.code for reason in judgement.reasons],
        "scores": asdict(judgement.scores),
        "sharpness_measured_on": measured_on,
        "sharpness": sharpness,
    }


def _summary(report: dict, catalog: Path, report_path: Path) -> str:
    result = report["agreement"]
    winners = report["winner_agreement"]
    time_taken = report["timing"]
    by_stars = "; ".join(
        f"{stars}★ → " + ", ".join(f"{verdict} {count}" for verdict, count in verdicts.items())
        for stars, verdicts in result["verdicts_by_reference_stars"].items()
    )
    reasons = ", ".join(
        f"{code} {count}" for code, count in result["reasons_on_rated_rejects_or_unsure"].items()
    )
    budget_verdict = "within budget" if time_taken["within_budget"] else "OVER budget"
    return "\n".join(
        [
            f"framewise benchmark: {report['frames']} Frames in {report['session']}",
            f"Reference ratings from a copy of {catalog}",
            "",
            "Providers",
            *(
                f"  {capability}: {provider}"
                for capability, provider in report["providers"].items()
            ),
            "",
            "Agreement",
            f"  Rated Frames: {result['with_reference']} of {report['frames']}",
            "  Winners and Keepers with a Reference rating: "
            + _share(result["kept_with_reference"], result["kept"]),
            "  Rejects with a Reference rating: "
            + _share(result["rejected_with_reference"], result["rejected"]),
            "  Rated Frames proposed as Reject or Unsure: "
            + _share(result["with_reference_rejected_or_unsure"], result["with_reference"]),
            f"  Verdicts by Reference rating: {by_stars or 'none'}",
            f"  Reasons on rated Rejects and Unsure: {reasons or 'none'}",
            "  Winners among their Group's top-rated Frames: "
            + _share(winners["agreeing"], winners["groups"]),
            "",
            "Timing",
            f"  Analysis: {report['analysis_seconds']:.1f} s, "
            f"grouping and judging: {report['judging_seconds']:.1f} s",
            f"  Total: {time_taken['seconds']:.1f} s ({time_taken['seconds'] / 60:.1f} min), "
            f"{time_taken['seconds_per_frame']:.2f} s per Frame",
            f"  Budget: {time_taken['budget_seconds']:.0f} s "
            f"({time_taken['budget_seconds'] / 60:.1f} min, "
            f"{BUDGET_SECONDS_PER_FRAME:.2f} s per Frame): {budget_verdict}",
            *(_weight_fit_summary(report["weight_fit"]) if "weight_fit" in report else []),
            "",
            f"Report: {report_path}",
        ]
    )


def _weight_fit_summary(fit: dict) -> list[str]:
    proposed = fit["proposed"]
    lines = [
        "",
        "Score weights fitted to the Reference ratings (nothing changed)",
        f"  Pairs of differently rated Frames in a Group: {fit['pairs']}",
        f"  Current weights: {_weights(WEIGHTS)}",
        "  Proposed weights: "
        + (_weights(proposed) if proposed else "none, the pairs favor no Score component"),
    ]
    if fit["current"] is None:
        return [*lines, "  Held-out figures need at least 2 Groups"]
    current, fitted = fit["current"], fit["fitted"]
    return [
        *lines,
        f"  {fit['folds']}-fold cross-validation by Group",
        "  Held-out pairs ranked as rated: "
        f"current {_share(current['ranked_as_rated'], current['pairs'])}, "
        f"proposed {_share(fitted['ranked_as_rated'], fitted['pairs'])}",
        "  Held-out Winners among their Group's top-rated Frames: "
        f"current {_share(current['winners']['agreeing'], current['winners']['groups'])}, "
        f"proposed {_share(fitted['winners']['agreeing'], fitted['winners']['groups'])}",
    ]


def _weights(weights: Mapping[str, float]) -> str:
    return ", ".join(f"{name} {weight:.2f}" for name, weight in weights.items())


def _share(part: int, whole: int) -> str:
    percent = f" ({part / whole:.0%})" if whole else ""
    return f"{part} of {whole}{percent}"


def _folder_key(folder: Path) -> str:
    return _path_key(folder).rstrip("/") + "/"


def _path_key(path: Path | str) -> str:
    return str(path).lower()


def _provider_override(text: str) -> tuple[str, str]:
    capability, separator, provider_id = text.partition("=")
    if not separator or not capability or not provider_id:
        raise argparse.ArgumentTypeError(f"expected CAPABILITY=ID, got {text!r}")
    return capability, provider_id


def _read_min_preview_long_edge() -> int:
    try:
        return read_min_preview_long_edge(resolve_config_path())
    except PreviewConfigError as error:
        print(f"framewise-benchmark: error: {error}", file=sys.stderr)
        sys.exit(1)


def _resolve_analyzer(overrides: dict[str, str], providers: list[Provider] | None) -> FrameAnalyzer:
    try:
        return resolve_analyzer(resolve_config_path(), overrides, providers)
    except ProviderError as error:
        print(f"framewise-benchmark: error: {error}", file=sys.stderr)
        sys.exit(1)
