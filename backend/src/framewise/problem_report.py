"""Problem reports: a photographer's description of a judging problem in one Group, built into a
prefilled GitHub new-issue page that the photographer reviews and submits themselves."""

import platform
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, fields
from importlib.metadata import version
from urllib.parse import urlencode

from framewise.analyzer import ProviderLineup
from framewise.judge import Flaw, Proposal, Reason, Scores, Verdict, frame_flaws
from framewise.store import AnalyzedFrame, main_file_name

NEW_ISSUE_PAGE = "https://github.com/acc-aqt/framewise/issues/new"
ISSUE_TEMPLATE = "judging-problem.md"
TITLE_PREFIX = "Judging problem: "
TITLE_TEXT_LENGTH = 60
MISSING = "–"
URL_LIMIT = 8000
"""The longest new-issue URL that browsers and GitHub reliably accept, in encoded characters."""
PASTE_BODY = (
    "The full report didn't fit in this link. framewise copied it to your clipboard. "
    "Paste it here in place of this text.\n"
)


@dataclass(frozen=True)
class ProblemReport:
    title: str
    body: str
    issue_url: str
    body_fits_url: bool
    """Whether `issue_url` carries the whole body. The body is always returned in full, for
    copying and saving."""


@dataclass(frozen=True)
class GroupFix:
    """How framewise grouped a Frame that a Group Override put in the reported Group."""

    grouped_with: list[str]
    """The names of the Frames of the reported Group that framewise grouped it with."""
    other_groups_count: int
    """How many Frames of other Groups framewise grouped it with, which stay unnamed."""


@dataclass(frozen=True)
class FrameState:
    name: str
    """The main file's name, without its folder."""
    verdict: Verdict
    proposed_verdict: Verdict | None
    """framewise's own Verdict where the photographer's Verdict Override decides it."""
    reasons: list[Reason]
    flaws: list[Flaw]
    scores: Scores
    group_fix: GroupFix | None


@dataclass(frozen=True)
class GroupState:
    """What framewise knew about the reported Group, so a maintainer can see why it judged it as
    it did. It holds nothing from other Groups and no paths beyond file names."""

    version: str
    os: str
    providers: Mapping[str, str | None]
    """The Provider serving each Capability as "id vN", or None where none does."""
    keeper_budget: float
    frames: list[FrameState]
    frames_pending: int
    """How many Frames of the Session were not analyzed yet when the report was made."""


def group_state(
    group: list[AnalyzedFrame],
    *,
    proposal: Proposal,
    own_proposal: Proposal,
    shown_verdicts: Mapping[int, tuple[Verdict, bool]],
    fixed_paths: Iterable[str],
    own_groups: list[list[AnalyzedFrame]],
    provider_lineup: ProviderLineup,
    keeper_budget: float,
    frames_pending: int,
) -> GroupState:
    """The reported Group's state. `proposal` judges with the photographer's Overrides and
    `own_proposal` without them; `shown_verdicts` gives each Frame's shown Verdict and whether it
    is an Override, by Frame id. `fixed_paths` are the main files a Group Override placed, and
    `own_groups` are framewise's Groups before Group Overrides."""
    fixed = set(fixed_paths)
    group_paths = [analyzed.frame.main_path for analyzed in group]
    frames = []
    for analyzed in group:
        frame = analyzed.frame
        judgement = proposal[frame.id]
        verdict, overridden = shown_verdicts[frame.id]
        frames.append(
            FrameState(
                name=main_file_name(frame.main_path),
                verdict=verdict,
                proposed_verdict=own_proposal[frame.id].verdict if overridden else None,
                reasons=judgement.reasons,
                flaws=frame_flaws(analyzed),
                scores=judgement.scores,
                group_fix=_group_fix(frame.main_path, group_paths, own_groups)
                if frame.main_path in fixed
                else None,
            )
        )
    return GroupState(
        version=version("framewise-cull"),
        os=platform.platform(),
        providers={
            capability: None
            if lineup.active is None
            else f"{lineup.active.id} v{lineup.active.version}"
            for capability, lineup in provider_lineup.items()
        },
        keeper_budget=keeper_budget,
        frames=frames,
        frames_pending=frames_pending,
    )


def _group_fix(
    main_path: str, group_paths: list[str], own_groups: list[list[AnalyzedFrame]]
) -> GroupFix:
    """How framewise grouped a Frame on its own, naming only the Frames of its current Group."""
    own_group = next(
        group for group in own_groups if any(a.frame.main_path == main_path for a in group)
    )
    others = [a.frame.main_path for a in own_group if a.frame.main_path != main_path]
    in_group = [path for path in others if path in group_paths]
    return GroupFix([main_file_name(path) for path in in_group], len(others) - len(in_group))


def build_problem_report(text: str, state: GroupState | None = None) -> ProblemReport:
    title = TITLE_PREFIX + _title_text(text)
    body = text.strip() + "\n"
    if state is not None:
        body += "\n" + _state_markdown(state)
    issue_url = _issue_url(title, body)
    if len(issue_url) <= URL_LIMIT:
        return ProblemReport(title, body, issue_url, body_fits_url=True)
    return ProblemReport(title, body, _issue_url(title, PASTE_BODY), body_fits_url=False)


def _issue_url(title: str, body: str) -> str:
    query = urlencode({"template": ISSUE_TEMPLATE, "title": title, "body": body})
    return f"{NEW_ISSUE_PAGE}?{query}"


def _title_text(text: str) -> str:
    """The start of the photographer's text on one line, cut at a word near 60 characters."""
    words = " ".join(text.split())
    if len(words) <= TITLE_TEXT_LENGTH:
        return words
    cut = words[: TITLE_TEXT_LENGTH + 1].rsplit(" ", 1)[0]
    return cut[:TITLE_TEXT_LENGTH].rstrip() + "…"


def _state_markdown(state: GroupState) -> str:
    providers = _listed(
        f"{capability}: {provider or 'none'}" for capability, provider in state.providers.items()
    )
    return (
        "## Group state\n\n"
        f"- framewise: {state.version}\n"
        f"- OS: {state.os}\n"
        f"- Providers: {providers}\n"
        f"- Keeper budget: {state.keeper_budget:.0%}\n"
        + _pending_note(state.frames_pending)
        + "\n"
        + _frame_table(state.frames)
        + _group_fixes(state.frames)
    )


def _pending_note(frames_pending: int) -> str:
    """Says analysis was incomplete. The pending Frames are in no Group yet, so naming them would
    name Frames outside the reported Group."""
    if frames_pending == 0:
        return ""
    verb = "was" if frames_pending == 1 else "were"
    return (
        f"\nAnalysis was still running: {frame_count(frames_pending)} of the Session {verb} "
        "not analyzed yet, so this Group may still change.\n"
    )


def _frame_table(frames: list[FrameState]) -> str:
    score_names = [field.name for field in fields(Scores)]
    header = ["Frame", "Verdict", "Reasons", "Flaws"] + [
        name.replace("_", " ").capitalize() for name in score_names
    ]
    rows = [header, ["---"] * len(header)]
    for frame in frames:
        scores = [getattr(frame.scores, name) for name in score_names]
        flaw_texts = (
            f"{flaw.reason.label} (caps at {flaw.caps_at.capitalize()})" for flaw in frame.flaws
        )
        rows.append(
            [
                frame.name,
                _verdict(frame),
                _listed(reason.text for reason in frame.reasons),
                _listed(flaw_texts),
            ]
            + [MISSING if score is None else f"{score:.2f}" for score in scores]
        )
    return "".join(f"| {' | '.join(_cell(cell) for cell in row)} |\n" for row in rows)


def _verdict(frame: FrameState) -> str:
    if frame.proposed_verdict is None:
        return frame.verdict.capitalize()
    return (
        f"{frame.verdict.capitalize()} "
        f"(Override; framewise proposed {frame.proposed_verdict.capitalize()})"
    )


def _group_fixes(frames: list[FrameState]) -> str:
    fixed = [frame for frame in frames if frame.group_fix is not None]
    if not fixed:
        return ""
    lines = "".join(
        f"- {frame.name}: put in this Group by a Group Override; "
        f"framewise grouped it {_grouping(frame.group_fix)}\n"
        for frame in fixed
    )
    return f"\n### Group Overrides\n\n{lines}"


def _grouping(fix: GroupFix) -> str:
    named = list(fix.grouped_with)
    if fix.other_groups_count:
        named.append(f"{frame_count(fix.other_groups_count)} of other Groups")
    if not named:
        return "alone"
    if len(named) == 1:
        return f"with {named[0]}"
    return f"with {', '.join(named[:-1])} and {named[-1]}"


def frame_count(count: int) -> str:
    """ "1 Frame" or "N Frames"."""
    return "1 Frame" if count == 1 else f"{count} Frames"


def _listed(items: Iterable[str]) -> str:
    return ", ".join(items) or MISSING


def _cell(text: str) -> str:
    return text.replace("|", "\\|")
