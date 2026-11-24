"""The Winner comparison: judges an analyzed Session once for each way of picking the Winner and
writes a page that shows, blind, the Winners of the Groups where those ways disagree. The
photographer clicks the Frame they would keep, and the page tallies which way agreed with them
(#174).

Run by hand, not in CI. It opens the Session store that `framewise review` keeps, so a Session
already reviewed is not analyzed again, and it writes nothing into the Session folder.
"""

import argparse
import base64
import html
import io
import random
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import get_args

from PIL import Image, ImageOps

from framewise.analyzer import FrameAnalyzer
from framewise.judge import Verdict, WinnerPick, judge
from framewise.previews import PreviewConfigError, read_min_preview_long_edge
from framewise.providers import ProviderError, resolve_analyzer
from framewise.review import SessionAnalysis, open_session, resolve_config_path, resolve_data_dir
from framewise.store import AnalyzedFrame, Frame, SessionStore

WINNER_PICKS: tuple[WinnerPick, ...] = get_args(WinnerPick)
IMAGE_LONG_EDGE = 1280


@dataclass(frozen=True)
class Candidate:
    frame: Frame
    picks: list[WinnerPick]
    """The ways of picking the Winner that chose this Frame."""


@dataclass(frozen=True)
class Comparison:
    candidates: list[Candidate]
    """The Group's Winners, one per Frame some way of picking chose."""


def compare_winner_picks(groups: list[list[AnalyzedFrame]]) -> list[Comparison]:
    """The Groups whose Winner depends on how it is picked, with each Winner and the ways that
    picked it."""
    winners = {
        pick: {
            frame_id
            for frame_id, judgement in judge(groups, winner_pick=pick).items()
            if judgement.verdict == Verdict.WINNER
        }
        for pick in WINNER_PICKS
    }
    comparisons = []
    for group in groups:
        candidates = [
            Candidate(
                analyzed.frame,
                [pick for pick in WINNER_PICKS if analyzed.frame.id in winners[pick]],
            )
            for analyzed in group
        ]
        chosen = [candidate for candidate in candidates if candidate.picks]
        if len(chosen) > 1:
            comparisons.append(Comparison(chosen))
    return comparisons


def main(argv: list[str] | None = None, analyzer: FrameAnalyzer | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="framewise-compare-winners",
        description="Show, blind, the Winners that absolute Scores and standings within the "
        "Group pick differently, to choose between them.",
    )
    parser.add_argument("session_folder", type=Path)
    parser.add_argument("--page", type=Path, default=Path("framewise-winner-comparison.html"))
    args = parser.parse_args(argv)

    session_root = args.session_folder.resolve()
    if not session_root.is_dir():
        parser.error(f"not a folder: {args.session_folder}")
    if args.page.resolve().is_relative_to(session_root):
        parser.error("the page must not be written into the Session folder")

    if analyzer is None:
        analyzer = _resolve_analyzer()
    store = open_session(
        session_root, resolve_data_dir(), min_preview_long_edge=_read_min_preview_long_edge()
    )
    analysis = SessionAnalysis(store, analyzer)
    analysis.run()
    groups = analysis.groups(store.group_overrides())
    comparisons = compare_winner_picks(groups)

    compared = sum(len(group) > 1 for group in groups)
    print(f"Winners differ in {len(comparisons)} of {compared} Groups of more than one Frame")
    if comparisons:
        args.page.write_text(_page(store, comparisons))
        print(f"Page: {args.page}")


def _page(store: SessionStore, comparisons: list[Comparison]) -> str:
    shuffle = random.Random()
    sections = []
    for index, comparison in enumerate(comparisons):
        candidates = list(comparison.candidates)
        shuffle.shuffle(candidates)
        buttons = "".join(_candidate(store, candidate) for candidate in candidates)
        sections.append(
            f'<section class="comparison" data-group="{index}">'
            f"<h2>Group {index + 1} of {len(comparisons)}</h2>"
            f'<div class="candidates">{buttons}</div>'
            '<button type="button" class="cant-tell" data-name="">Can\'t tell</button>'
            "</section>"
        )
    session = html.escape(f"{store.root}:{time.time()}")
    return PAGE.replace("{session}", session).replace("{sections}", "".join(sections))


def _candidate(store: SessionStore, candidate: Candidate) -> str:
    name = html.escape(candidate.frame.main_path)
    picks = " ".join(candidate.picks)
    image = _image_data(store.analysis_image(candidate.frame))
    return (
        f'<button type="button" class="candidate" data-name="{name}" data-picks="{picks}">'
        f'<img src="data:image/jpeg;base64,{image}" alt=""><span>{name}</span></button>'
    )


def _image_data(path: Path) -> str:
    with Image.open(path) as image:
        upright = ImageOps.exif_transpose(image).convert("RGB")
    upright.thumbnail((IMAGE_LONG_EDGE, IMAGE_LONG_EDGE))
    buffer = io.BytesIO()
    upright.save(buffer, "JPEG", quality=85)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def _read_min_preview_long_edge() -> int:
    try:
        return read_min_preview_long_edge(resolve_config_path())
    except PreviewConfigError as error:
        print(f"framewise-compare-winners: error: {error}", file=sys.stderr)
        sys.exit(1)


def _resolve_analyzer() -> FrameAnalyzer:
    try:
        return resolve_analyzer(resolve_config_path())
    except ProviderError as error:
        print(f"framewise-compare-winners: error: {error}", file=sys.stderr)
        sys.exit(1)


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>framewise: which Winner would you keep?</title>
<style>
  body { margin: 0; padding: 24px; background: #1b1b1d; color: #e8e8ea;
         font: 15px/1.5 -apple-system, system-ui, sans-serif; }
  header { max-width: 72rem; margin: 0 auto 24px; }
  h1 { font-size: 20px; margin: 0 0 4px; }
  h2 { font-size: 14px; font-weight: 600; color: #a0a0a6; margin: 0 0 8px; }
  .comparison { max-width: 72rem; margin: 0 auto 40px; }
  .candidates { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
                gap: 12px; }
  button { font: inherit; color: inherit; cursor: pointer; }
  .candidate { display: flex; flex-direction: column; gap: 6px; padding: 6px;
               background: #262629; border: 3px solid transparent; border-radius: 8px; }
  .candidate img { width: 100%; height: auto; border-radius: 4px; }
  .candidate span { font-size: 12px; color: #a0a0a6; }
  .candidate[aria-pressed="true"] { border-color: #4f9cf7; }
  .cant-tell { margin-top: 8px; padding: 4px 10px; background: none;
               border: 1px solid #4a4a50; border-radius: 6px; }
  .cant-tell[aria-pressed="true"] { border-color: #4f9cf7; color: #4f9cf7; }
  footer { position: sticky; bottom: 0; max-width: 72rem; margin: 0 auto; padding: 12px 16px;
           background: #262629; border-radius: 8px; display: flex; gap: 16px;
           align-items: center; flex-wrap: wrap; }
  #reveal { padding: 6px 14px; background: #4f9cf7; color: #fff; border: 0;
            border-radius: 6px; }
</style>
</head>
<body data-session="{session}">
<header>
  <h1>Which Winner would you keep?</h1>
  <p>In each Group below, framewise's ways of picking the Winner disagree. Click the Frame you
  would keep. The order is shuffled, and which way picked which Frame stays hidden until you
  show the tally. Choices are kept in this browser if you reload the page.</p>
</header>
{sections}
<footer>
  <span id="progress"></span>
  <button type="button" id="reveal">Show the tally</button>
  <span id="tally"></span>
</footer>
<script>
  const key = "framewise-winner-comparison:" + document.body.dataset.session;
  const choices = JSON.parse(localStorage.getItem(key) || "{}");
  const sections = [...document.querySelectorAll(".comparison")];

  function render() {
    for (const section of sections) {
      const choice = choices[section.dataset.group];
      for (const button of section.querySelectorAll("[data-name]")) {
        button.setAttribute("aria-pressed", String(button.dataset.name === choice));
      }
    }
    const answered = sections.filter((s) => s.dataset.group in choices).length;
    document.getElementById("progress").textContent =
      answered + " of " + sections.length + " Groups answered";
  }

  for (const section of sections) {
    for (const button of section.querySelectorAll("[data-name]")) {
      button.addEventListener("click", () => {
        choices[section.dataset.group] = button.dataset.name;
        localStorage.setItem(key, JSON.stringify(choices));
        render();
      });
    }
  }

  document.getElementById("reveal").addEventListener("click", () => {
    const wins = { scores: 0, rank: 0, "z-score": 0 };
    let decided = 0;
    let cantTell = 0;
    for (const section of sections) {
      const choice = choices[section.dataset.group];
      if (choice === undefined) continue;
      if (choice === "") { cantTell += 1; continue; }
      decided += 1;
      const chosen = [...section.querySelectorAll(".candidate")]
        .find((button) => button.dataset.name === choice);
      for (const pick of chosen.dataset.picks.split(" ")) wins[pick] += 1;
    }
    document.getElementById("tally").textContent =
      "Absolute Scores " + wins.scores + " of " + decided +
      " · rank " + wins.rank + " of " + decided +
      " · z-score " + wins["z-score"] + " of " + decided +
      " · can't tell " + cantTell;
  });

  render();
</script>
</body>
</html>
"""
