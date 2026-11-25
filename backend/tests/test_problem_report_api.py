from urllib.parse import parse_qs, urlsplit

from conftest import wait_until
from test_group_fixes_api import beach_burst, ids

NEW_ISSUE_PAGE = "https://github.com/acc-aqt/framewise/issues/new"


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
