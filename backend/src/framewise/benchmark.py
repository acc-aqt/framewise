"""The sewts benchmark: how often the Proposal agrees with the photographer's Reference ratings in
Lightroom Classic, and how long a cold first pass over a Session takes.

Run by hand, not in CI. It reads a copy of the Lightroom Classic catalog, never the catalog
itself, and keeps its Session store in a temporary folder, so it writes nothing outside the
report.
"""

import argparse
import json
import plistlib
import shutil
import sqlite3
import tempfile
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

from framewise.analyzer import FrameAnalyzer
from framewise.grouper import group_frames
from framewise.judge import Proposal, Verdict, judge
from framewise.review import SessionAnalysis, open_session
from framewise.store import Frame

LIGHTROOM_PREFS = Path.home() / "Library" / "Preferences" / "com.adobe.LightroomClassicCC7.plist"
ACTIVE_CATALOG_KEY = "libraryToLoad20"
# ADR-0002: 15 minutes for a 200-Frame Session on the first pass.
BUDGET_SECONDS_PER_FRAME = 15 * 60 / 200
KEPT = {Verdict.WINNER, Verdict.KEEPER}
NOT_KEPT = {Verdict.REJECT, Verdict.UNSURE}

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
class Timing:
    frames: int
    seconds: float
    seconds_per_frame: float
    budget_seconds: float
    within_budget: bool


def active_catalog(prefs: Path = LIGHTROOM_PREFS) -> Path:
    with prefs.open("rb") as file:
        return Path(plistlib.load(file)[ACTIVE_CATALOG_KEY])


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
    """Each Frame's Reference rating, by Frame id, matched on its JPG's path. Paths compare
    case-insensitively, as macOS file systems do."""
    by_path = {_path_key(path): stars for path, stars in ratings.items()}
    references = {}
    for frame in frames:
        stars = by_path.get(_path_key(session_root / frame.jpg_path))
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
    args = parser.parse_args(argv)

    session_root = args.session_folder.resolve()
    if not session_root.is_dir():
        parser.error(f"not a folder: {args.session_folder}")
    if args.report.resolve().is_relative_to(session_root):
        parser.error("the report must not be written into the Session folder")
    catalog = args.catalog or active_catalog()
    if not catalog.is_file():
        parser.error(f"no catalog at {catalog}")

    if analyzer is None:
        # Imported here so the rest of framewise imports where Apple Vision doesn't exist.
        from framewise.vision_analyzer import VisionAnalyzer

        analyzer = VisionAnalyzer()

    with tempfile.TemporaryDirectory(prefix="framewise-benchmark-") as temp:
        catalog_copy = copy_catalog(catalog, Path(temp))
        ratings = read_reference_ratings(catalog_copy, session_root)
        report = _run(session_root, Path(temp) / "session-store", analyzer, ratings, clock)

    args.report.write_text(json.dumps(report, indent=2))
    print(_summary(report, catalog, args.report))


def _run(
    session_root: Path,
    data_dir: Path,
    analyzer: FrameAnalyzer,
    ratings: dict[Path, int],
    clock: Callable[[], float],
) -> dict:
    """A cold first pass: a fresh Session store, so every Frame is analysed."""
    started = clock()
    store = open_session(session_root, data_dir)
    SessionAnalysis(store, analyzer).run()
    analysed = clock()
    analyzed_frames = store.analyzed_frames()
    proposal = judge(group_frames(analyzed_frames))
    judged = clock()

    frames = store.frames()
    references = match_references(frames, session_root, ratings)
    return {
        "session": str(session_root),
        "frames": len(frames),
        "frames_analysed": len(analyzed_frames),
        "agreement": asdict(agreement(proposal, references)),
        "timing": asdict(timing(len(frames), judged - started)),
        "analysis_seconds": analysed - started,
        "judging_seconds": judged - analysed,
        "frame_results": [
            _frame_result(frame, proposal, references) for frame in frames if frame.id in proposal
        ],
    }


def _frame_result(frame: Frame, proposal: Proposal, references: dict[int, int]) -> dict:
    judgement = proposal[frame.id]
    return {
        "jpg_path": frame.jpg_path,
        "reference_stars": references.get(frame.id),
        "verdict": judgement.verdict.value,
        "reasons": [reason.code for reason in judgement.reasons],
        "scores": asdict(judgement.scores),
    }


def _summary(report: dict, catalog: Path, report_path: Path) -> str:
    result = report["agreement"]
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
            "",
            "Timing",
            f"  Analysis: {report['analysis_seconds']:.1f} s, "
            f"grouping and judging: {report['judging_seconds']:.1f} s",
            f"  Total: {time_taken['seconds']:.1f} s ({time_taken['seconds'] / 60:.1f} min), "
            f"{time_taken['seconds_per_frame']:.2f} s per Frame",
            f"  Budget: {time_taken['budget_seconds']:.0f} s "
            f"({time_taken['budget_seconds'] / 60:.1f} min, "
            f"{BUDGET_SECONDS_PER_FRAME:.2f} s per Frame): {budget_verdict}",
            "",
            f"Report: {report_path}",
        ]
    )


def _share(part: int, whole: int) -> str:
    percent = f" ({part / whole:.0%})" if whole else ""
    return f"{part} of {whole}{percent}"


def _folder_key(folder: Path) -> str:
    return _path_key(folder).rstrip("/") + "/"


def _path_key(path: Path | str) -> str:
    return str(path).lower()
