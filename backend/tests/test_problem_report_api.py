import platform
from importlib.metadata import version
from urllib.parse import parse_qs, urlsplit

from conftest import make_jpg, wait_until
from test_group_fixes_api import BEACH, beach_burst, ids, mountain, move, seconds, shoot, split
from test_overrides_api import override
from test_verdicts_api import frames_by_name, keep_every_clean_frame

from framewise.analyzer import ActiveProvider, CapabilityLineup

NEW_ISSUE_PAGE = "https://github.com/acc-aqt/framewise/issues/new"


def table(body: str) -> dict[str, dict[str, str]]:
    """The Frame table of a report body, as each row's cells by column, keyed by Frame."""
    lines = [line for line in body.splitlines() if line.startswith("|")]
    header = [cell.strip() for cell in lines[0].strip("|").split("|")]
    rows = [
        dict(zip(header, (cell.strip() for cell in line.strip("|").split("|")), strict=True))
        for line in lines[2:]
    ]
    return {row["Frame"]: row for row in rows}


def report(client, group_id: int, text: str, **options):
    return client.post(f"/api/groups/{group_id}/problem-report", json={"text": text, **options})


def test_a_problem_report_opens_a_prefilled_new_issue_page_with_the_judging_template(
    session_dir, review, analyzer
):
    beach_burst(session_dir, analyzer)
    client = review()
    [group_id] = ids(client, "DSCF0001.JPG")

    response = report(client, group_id, "DSCF0003 is sharper and should be the Winner.")

    assert response.status_code == 200
    built = response.json()
    assert built["title"] == "Judging problem: DSCF0003 is sharper and should be the Winner."
    assert "DSCF0003 is sharper and should be the Winner." in built["body"]
    url = urlsplit(built["issue_url"])
    assert f"{url.scheme}://{url.netloc}{url.path}" == NEW_ISSUE_PAGE
    assert parse_qs(url.query) == {
        "template": ["judging-problem.md"],
        "title": [built["title"]],
        "body": [built["body"]],
    }
    assert built["body_fits_url"] is True


def test_a_long_text_is_cut_at_a_word_for_the_title_and_kept_whole_in_the_body(
    session_dir, review, analyzer
):
    beach_burst(session_dir, analyzer)
    client = review()
    [group_id] = ids(client, "DSCF0001.JPG")
    text = (
        "The second Frame has closed eyes\nbut it became the Winner anyway, "
        "although the third one is clearly better."
    )

    built = report(client, group_id, text).json()

    assert built["title"] == (
        "Judging problem: The second Frame has closed eyes but it became the Winner…"
    )
    assert text in built["body"]


def test_only_a_groups_first_frame_identifies_it(session_dir, review, analyzer):
    beach_burst(session_dir, analyzer)
    client = review()
    [second_frame_id] = ids(client, "DSCF0002.JPG")

    assert report(client, second_frame_id, "Wrong Winner").status_code == 404
    assert report(client, 9999, "Wrong Winner").status_code == 404


def test_a_blank_text_is_refused(session_dir, review, analyzer):
    beach_burst(session_dir, analyzer)
    client = review()
    [group_id] = ids(client, "DSCF0001.JPG")

    assert report(client, group_id, " \n\t ").status_code == 422
    assert report(client, group_id, "").status_code == 422


def test_a_group_can_be_reported_while_analysis_is_still_running(
    session_dir, live_review, analyzer
):
    beach_burst(session_dir, analyzer)
    analyzer.hold(session_dir / "DSCF0004.JPG")
    client = live_review()
    wait_until(lambda: client.get("/api/progress").json()["frames_done"] == 3)
    [group_id] = ids(client, "DSCF0001.JPG")

    response = report(client, group_id, "This Group looks stuck.")

    analyzer.release_all()
    assert response.status_code == 200
    assert "This Group looks stuck." in response.json()["body"]


def test_a_report_too_long_for_the_url_asks_to_paste_it_from_the_clipboard(
    session_dir, review, analyzer
):
    beach_burst(session_dir, analyzer)
    client = review()
    [group_id] = ids(client, "DSCF0001.JPG")
    text = "The Winner has closed eyes and DSCF0003 is better. " * 200

    built = report(client, group_id, text).json()

    assert built["body_fits_url"] is False
    assert text.strip() in built["body"]
    assert len(built["issue_url"]) <= 8000
    url_body = parse_qs(urlsplit(built["issue_url"]).query)["body"][0]
    assert "paste" in url_body.lower()
    assert "clipboard" in url_body.lower()
    assert "didn't fit" in url_body
    assert "closed eyes" not in url_body


def test_the_url_limit_counts_encoded_characters(session_dir, review, analyzer):
    beach_burst(session_dir, analyzer)
    client = review()
    [group_id] = ids(client, "DSCF0001.JPG")

    short_ascii = report(client, group_id, "a" * 3000).json()
    long_once_encoded = report(client, group_id, "ü" * 3000).json()

    assert short_ascii["body_fits_url"] is True
    assert long_once_encoded["body_fits_url"] is False


def test_the_group_state_names_the_version_os_providers_and_keeper_budget_by_default(
    session_dir, review, analyzer
):
    beach_burst(session_dir, analyzer)
    client = review(
        provider_lineup={
            "fingerprint": CapabilityLineup(ActiveProvider("dinov2", 2, "automatic")),
            "faces": CapabilityLineup(None),
        }
    )
    client.patch("/api/session", json={"keeper_budget": 0.25})
    [group_id] = ids(client, "DSCF0001.JPG")

    body = report(client, group_id, "Wrong Winner").json()["body"]

    assert body.startswith("Wrong Winner\n")
    assert f"- framewise: {version('framewise-cull')}\n" in body
    assert f"- OS: {platform.platform()}\n" in body
    assert "- Providers: fingerprint: dinov2 v2, faces: none\n" in body
    assert "- Keeper budget: 25%\n" in body


def test_the_group_state_has_one_row_per_frame_with_its_verdict_reasons_flaws_and_scores(
    session_dir, review, analyzer
):
    shoot(
        session_dir,
        analyzer,
        BEACH,
        ("DSCF0001", 0, {"aesthetics": 0.95}),
        ("DSCF0002", 0.3, {"sharpness": 0.05}),
        ("DSCF0003", 0.6, {"aesthetics": 0.4}),
    )
    client = review()
    client.patch("/api/session", json={"keeper_budget": 0})
    [group_id] = ids(client, "DSCF0001.JPG")

    rows = table(report(client, group_id, "Wrong Winner").json()["body"])

    assert list(rows) == ["DSCF0001.JPG", "DSCF0002.JPG", "DSCF0003.JPG"]
    winner, blurry, duplicate = rows.values()
    assert (winner["Verdict"], winner["Reasons"], winner["Flaws"]) == ("Winner", "–", "–")
    assert (blurry["Verdict"], blurry["Reasons"], blurry["Flaws"]) == (
        "Reject",
        "Blurry",
        "Blurry (caps at Reject)",
    )
    assert (duplicate["Verdict"], duplicate["Reasons"], duplicate["Flaws"]) == (
        "Reject",
        "Weaker duplicate of DSCF0001",
        "–",
    )
    assert winner["Aesthetics"] == "0.95"
    assert winner["Steadiness"] == "0.95"
    assert winner["Face quality"] == winner["Expression"] == "–"
    total = frames_by_name(client)["DSCF0001.JPG"]["scores"]["total"]
    assert abs(float(winner["Total"]) - total) <= 0.005
    assert set(winner) == {
        "Frame",
        "Verdict",
        "Reasons",
        "Flaws",
        "Sharpness",
        "Steadiness",
        "Exposure",
        "Aesthetics",
        "Face quality",
        "Expression",
        "Camera rating",
        "Total",
    }


def test_an_overridden_frame_shows_framewise_own_proposal_next_to_the_override(
    session_dir, review, analyzer
):
    beach_burst(session_dir, analyzer)
    client = keep_every_clean_frame(review())
    override(client, "DSCF0002.JPG", verdict="reject")
    override(client, "DSCF0003.JPG", stars=4)
    [group_id] = ids(client, "DSCF0001.JPG")

    rows = table(report(client, group_id, "Wrong Winner").json()["body"])

    assert rows["DSCF0002.JPG"]["Verdict"] == "Reject (Override; framewise proposed Keeper)"
    assert rows["DSCF0003.JPG"]["Verdict"] == "Keeper"


def test_frames_fixed_by_a_group_override_are_marked_with_framewise_own_grouping(
    session_dir, review, analyzer
):
    beach_burst(session_dir, analyzer)
    mountain(session_dir, analyzer)
    client = review()
    split(client, "DSCF0003.JPG", "DSCF0004.JPG")
    move(client, "DSCF0009.JPG", "DSCF0003.JPG")
    [group_id] = ids(client, "DSCF0003.JPG")

    body = report(client, group_id, "Wrong Group").json()["body"]

    assert "### Group Overrides\n" in body
    assert (
        "- DSCF0003.JPG: put in this Group by a Group Override; framewise grouped it with "
        "DSCF0004.JPG and 2 Frames of other Groups\n"
    ) in body
    assert (
        "- DSCF0009.JPG: put in this Group by a Group Override; framewise grouped it alone\n"
    ) in body


def test_a_report_built_during_analysis_says_how_many_frames_were_pending_without_naming_them(
    session_dir, live_review, analyzer
):
    beach_burst(session_dir, analyzer)
    mountain(session_dir, analyzer)
    analyzer.hold(session_dir / "DSCF0004.JPG")
    analyzer.hold(session_dir / "DSCF0009.JPG")
    client = live_review()
    wait_until(lambda: client.get("/api/progress").json()["frames_done"] == 3)
    [group_id] = ids(client, "DSCF0001.JPG")

    body = report(client, group_id, "This Group looks stuck.").json()["body"]

    analyzer.release_all()
    assert (
        "Analysis was still running: 2 Frames of the Session were not analyzed yet, "
        "so this Group may still change.\n"
    ) in body
    assert "DSCF0004" not in body
    assert "DSCF0009" not in body


def test_the_group_state_holds_nothing_from_other_groups_and_no_folders(
    session_dir, review, analyzer
):
    (session_dir / "Day 1").mkdir()
    for index, name in enumerate(["DSCF0001", "DSCF0002"]):
        jpg = make_jpg(session_dir / "Day 1" / f"{name}.JPG", captured_at=seconds(index * 0.3))
        analyzer.script(jpg, BEACH)
    mountain(session_dir, analyzer)
    client = review()
    [group_id] = ids(client, "Day 1/DSCF0001.JPG")

    body = report(client, group_id, "Wrong Winner").json()["body"]

    assert list(table(body)) == ["DSCF0001.JPG", "DSCF0002.JPG"]
    assert "DSCF0009" not in body
    assert "Day 1" not in body
    assert str(session_dir) not in body
    assert session_dir.name not in body


def test_with_include_group_state_unticked_the_body_is_only_the_text(session_dir, review, analyzer):
    beach_burst(session_dir, analyzer)
    client = review()
    [group_id] = ids(client, "DSCF0001.JPG")

    body = report(client, group_id, "  Wrong Winner\n", include_state=False).json()["body"]

    assert body == "Wrong Winner\n"


def test_a_report_built_after_analysis_has_no_analysis_note(session_dir, review, analyzer):
    beach_burst(session_dir, analyzer)
    client = review()
    [group_id] = ids(client, "DSCF0001.JPG")

    assert "Analysis was still running" not in report(client, group_id, "Wrong").json()["body"]
