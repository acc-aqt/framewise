"""Problem reports: a photographer's description of a judging problem in one Group, built into a
prefilled GitHub new-issue page that the photographer reviews and submits themselves."""

from dataclasses import dataclass
from urllib.parse import urlencode

NEW_ISSUE_PAGE = "https://github.com/acc-aqt/framewise/issues/new"
ISSUE_TEMPLATE = "judging-problem.md"
TITLE_PREFIX = "Judging problem: "
TITLE_TEXT_LENGTH = 60
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


def build_problem_report(text: str) -> ProblemReport:
    title = TITLE_PREFIX + _title_text(text)
    body = text.strip() + "\n"
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
