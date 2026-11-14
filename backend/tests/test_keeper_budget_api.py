from conftest import make_jpg
from test_overrides_api import override
from test_verdicts_api import MOUNTAIN, burst, frames_by_name, reasons, seconds, verdicts


def set_keeper_budget(client, share: float):
    return client.patch("/api/session", json={"keeper_budget": share})


def five_of_falling_quality(session_dir, analyzer) -> None:
    burst(
        session_dir,
        analyzer,
        ("DSCF0001", {"aesthetics": 0.8}),
        ("DSCF0002", {"aesthetics": 0.6}),
        ("DSCF0003", {"aesthetics": 0.4}),
        ("DSCF0004", {"aesthetics": 0.2}),
        ("DSCF0005", {"aesthetics": 0.0}),
    )


def test_the_keeper_budget_starts_at_40_percent(session_dir, review, analyzer):
    burst(session_dir, analyzer, ("DSCF0001", {}))

    assert review().get("/api/session").json()["keeper_budget"] == 0.4


def test_the_keeper_budget_is_stored_per_session(session_dir, review, analyzer):
    burst(session_dir, analyzer, ("DSCF0001", {}))

    response = set_keeper_budget(review(), 0.25)

    assert response.status_code == 200
    assert response.json()["keeper_budget"] == 0.25
    assert review().get("/api/session").json()["keeper_budget"] == 0.25


def test_a_keeper_budget_outside_0_to_1_is_refused(session_dir, review, analyzer):
    burst(session_dir, analyzer, ("DSCF0001", {}))
    client = review()

    assert set_keeper_budget(client, 1.5).status_code == 422
    assert set_keeper_budget(client, -0.1).status_code == 422
    assert client.get("/api/session").json()["keeper_budget"] == 0.4


def test_raising_the_keeper_budget_moves_the_cutoff_down_the_best_frames(
    session_dir, review, analyzer
):
    five_of_falling_quality(session_dir, analyzer)
    client = review()

    set_keeper_budget(client, 0.6)
    assert verdicts(client) == {
        "DSCF0001.JPG": "winner",
        "DSCF0002.JPG": "keeper",
        "DSCF0003.JPG": "keeper",
        "DSCF0004.JPG": "reject",
        "DSCF0005.JPG": "reject",
    }

    set_keeper_budget(client, 1.0)
    assert list(verdicts(client).values()) == ["winner"] + ["keeper"] * 4


def test_frames_over_the_keeper_budget_are_weaker_duplicates_of_the_winner(
    session_dir, review, analyzer
):
    five_of_falling_quality(session_dir, analyzer)
    client = review()

    set_keeper_budget(client, 0.2)

    assert list(verdicts(client).values()) == ["winner"] + ["reject"] * 4
    assert reasons(frames_by_name(client)["DSCF0005.JPG"]) == ["Weaker duplicate of DSCF0001"]


def test_winners_stay_even_with_no_keeper_budget(session_dir, review, analyzer):
    five_of_falling_quality(session_dir, analyzer)
    analyzer.script(
        make_jpg(session_dir / "DSCF0009.JPG", captured_at=seconds(60)), MOUNTAIN, sharpness=0.1
    )
    client = review()

    set_keeper_budget(client, 0.0)

    frames = verdicts(client)
    assert frames["DSCF0001.JPG"] == "winner"
    assert frames["DSCF0009.JPG"] == "winner"
    assert "keeper" not in frames.values()


def test_a_flawed_frame_never_becomes_a_keeper_however_large_the_budget(
    session_dir, review, analyzer
):
    burst(
        session_dir,
        analyzer,
        ("DSCF0001", {}),
        ("DSCF0002", {"sharpness": 0.1}),
        ("DSCF0003", {"sharpness": 0.4}),
    )
    client = review()

    set_keeper_budget(client, 1.0)

    assert verdicts(client) == {
        "DSCF0001.JPG": "winner",
        "DSCF0002.JPG": "reject",
        "DSCF0003.JPG": "unsure",
    }


def test_the_keeper_budget_never_changes_an_override(session_dir, review, analyzer):
    five_of_falling_quality(session_dir, analyzer)
    client = review()
    override(client, "DSCF0002.JPG", verdict="reject")
    override(client, "DSCF0005.JPG", verdict="keeper")

    set_keeper_budget(client, 1.0)
    assert verdicts(client)["DSCF0002.JPG"] == "reject"

    set_keeper_budget(client, 0.0)
    assert verdicts(client)["DSCF0005.JPG"] == "keeper"


def test_the_photographers_keepers_count_towards_the_keeper_budget(session_dir, review, analyzer):
    five_of_falling_quality(session_dir, analyzer)
    client = review()
    set_keeper_budget(client, 0.6)

    override(client, "DSCF0005.JPG", verdict="keeper")

    assert verdicts(client) == {
        "DSCF0001.JPG": "winner",
        "DSCF0002.JPG": "keeper",
        "DSCF0003.JPG": "reject",
        "DSCF0004.JPG": "reject",
        "DSCF0005.JPG": "keeper",
    }


def test_a_camera_rating_tips_the_balance_between_near_equal_frames(session_dir, review, analyzer):
    burst(session_dir, analyzer, ("DSCF0001", {"aesthetics": 0.3}), ("DSCF0002", {}))
    make_jpg(session_dir / "DSCF0002.JPG", stars=1, captured_at=seconds(0.3))

    frames = frames_by_name(review())

    assert frames["DSCF0002.JPG"]["verdict"] == "winner"
    assert frames["DSCF0002.JPG"]["scores"]["camera_rating"] == 0.05
    assert frames["DSCF0001.JPG"]["scores"]["camera_rating"] == 0.0


def test_a_camera_rating_does_not_lift_a_frame_past_a_clearly_better_one(
    session_dir, review, analyzer
):
    burst(session_dir, analyzer, ("DSCF0001", {"aesthetics": 0.9}), ("DSCF0002", {}))
    make_jpg(session_dir / "DSCF0002.JPG", stars=1, captured_at=seconds(0.3))

    assert verdicts(review())["DSCF0001.JPG"] == "winner"


def test_a_camera_rating_does_not_override_a_technical_defect(session_dir, review, analyzer):
    burst(
        session_dir,
        analyzer,
        ("DSCF0001", {"aesthetics": -0.5}),
        ("DSCF0002", {"sharpness": 0.1, "aesthetics": 0.9}),
        ("DSCF0003", {"motion_blur": 0.4, "aesthetics": 0.9}),
    )
    make_jpg(session_dir / "DSCF0002.JPG", stars=5, captured_at=seconds(0.3))
    make_jpg(session_dir / "DSCF0003.JPG", stars=5, captured_at=seconds(0.6))
    client = review()

    set_keeper_budget(client, 1.0)

    assert verdicts(client) == {
        "DSCF0001.JPG": "winner",
        "DSCF0002.JPG": "reject",
        "DSCF0003.JPG": "unsure",
    }


def test_a_camera_rating_lifts_a_frame_within_the_keeper_budget(session_dir, review, analyzer):
    burst(
        session_dir,
        analyzer,
        ("DSCF0001", {"aesthetics": 0.8}),
        ("DSCF0002", {"aesthetics": 0.3}),
        ("DSCF0003", {"aesthetics": 0.2}),
        ("DSCF0004", {"aesthetics": 0.0}),
    )
    make_jpg(session_dir / "DSCF0003.JPG", stars=1, captured_at=seconds(0.6))
    client = review()

    set_keeper_budget(client, 0.5)

    assert verdicts(client) == {
        "DSCF0001.JPG": "winner",
        "DSCF0002.JPG": "reject",
        "DSCF0003.JPG": "keeper",
        "DSCF0004.JPG": "reject",
    }
