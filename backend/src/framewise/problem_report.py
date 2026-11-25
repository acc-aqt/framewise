"""Problem reports: a photographer's description of a judging problem in one Group, built into a
prefilled GitHub new-issue page that the photographer reviews and submits themselves."""

from dataclasses import dataclass
from urllib.parse import urlencode

NEW_ISSUE_PAGE = "https://github.com/acc-aqt/framewise/issues/new"
ISSUE_TEMPLATE = "judging-problem.md"
TITLE_PREFIX = "Judging problem: "
TITLE_TEXT_LENGTH = 60


@dataclass(frozen=True)
class ProblemReport:
    title: str
    body: str
    issue_url: str
    body_fits_url: bool
    """Whether `issue_url` carries the whole body. The body is always returned in full, for
    copying and saving."""


def build_problem_report(text: str) -> ProblemReport:
    title = TITLE_PREFIX + _title_text(text)
    body = text.strip() + "\n"
    query = urlencode({"template": ISSUE_TEMPLATE, "title": title, "body": body})
    return ProblemReport(title, body, f"{NEW_ISSUE_PAGE}?{query}", body_fits_url=True)


def _title_text(text: str) -> str:
    """The start of the photographer's text on one line, cut at a word near 60 characters."""
    words = " ".join(text.split())
    if len(words) <= TITLE_TEXT_LENGTH:
        return words
    cut = words[: TITLE_TEXT_LENGTH + 1].rsplit(" ", 1)[0]
    return cut[:TITLE_TEXT_LENGTH].rstrip() + "…"
