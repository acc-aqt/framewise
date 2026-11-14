from datetime import datetime, timedelta

from conftest import make_jpg
from test_verdicts_api import keep_every_clean_frame

START = datetime(2026, 6, 20, 14, 30, 0)
BEACH = [1.0, 0.0, 0.0]
MOUNTAIN = [0.0, 1.0, 0.0]


def seconds(count: float) -> datetime:
    return START + timedelta(seconds=count)


def burst(session_dir, analyzer, *frames: tuple[str, dict]) -> None:
    """Scripts Frames captured a fraction of a second apart that look alike, so they form one
    Group."""
    for index, (name, signals) in enumerate(frames):
        jpg = make_jpg(session_dir / f"{name}.JPG", captured_at=seconds(index * 0.3))
        analyzer.script(jpg, BEACH, **signals)


def frames_by_name(client) -> dict[str, dict]:
    return {
        frame["jpg_path"]: frame
        for group in client.get("/api/groups").json()
        for frame in group["frames"]
    }


def verdicts(client) -> dict[str, str]:
    return {name: frame["verdict"] for name, frame in frames_by_name(client).items()}


def override(client, name: str, **change):
    frame_id = frames_by_name(client)[name]["id"]
    return client.patch(f"/api/frames/{frame_id}/override", json=change)


def test_framewise_verdicts_carry_no_override(session_dir, review, analyzer):
    burst(session_dir, analyzer, ("DSCF0001", {"aesthetics": 0.4}), ("DSCF0002", {}))

    frames = frames_by_name(keep_every_clean_frame(review()))

    assert [(f["verdict"], f["verdict_overridden"], f["override"]) for f in frames.values()] == [
        ("winner", False, None),
        ("keeper", False, None),
    ]


def test_an_override_beats_framewise_verdict(session_dir, review, analyzer):
    burst(session_dir, analyzer, ("DSCF0001", {"aesthetics": 0.4}), ("DSCF0002", {}))
    client = review()

    response = override(client, "DSCF0002.JPG", verdict="reject")

    assert response.status_code == 200
    rejected = frames_by_name(client)["DSCF0002.JPG"]
    assert rejected["verdict"] == "reject"
    assert rejected["verdict_overridden"] is True
    assert rejected["override"] == {"verdict": "reject", "stars": None, "label": None}


def test_stars_and_a_color_label_are_saved_without_changing_the_verdict(
    session_dir, review, analyzer
):
    burst(session_dir, analyzer, ("DSCF0001", {"aesthetics": 0.4}), ("DSCF0002", {}))
    client = keep_every_clean_frame(review())

    override(client, "DSCF0002.JPG", stars=4)
    override(client, "DSCF0002.JPG", label="green")

    keeper = frames_by_name(client)["DSCF0002.JPG"]
    assert keeper["override"] == {"verdict": None, "stars": 4, "label": "green"}
    assert (keeper["verdict"], keeper["verdict_overridden"]) == ("keeper", False)


def test_a_field_set_to_null_is_cleared_and_others_are_kept(session_dir, review, analyzer):
    burst(session_dir, analyzer, ("DSCF0001", {}))
    client = review()
    override(client, "DSCF0001.JPG", stars=5, label="red")

    override(client, "DSCF0001.JPG", label=None)

    assert frames_by_name(client)["DSCF0001.JPG"]["override"] == {
        "verdict": None,
        "stars": 5,
        "label": None,
    }


def test_clearing_an_override_returns_to_framewise_verdict(session_dir, review, analyzer):
    burst(session_dir, analyzer, ("DSCF0001", {"aesthetics": 0.4}), ("DSCF0002", {}))
    client = keep_every_clean_frame(review())
    override(client, "DSCF0002.JPG", verdict="reject", stars=1)
    frame_id = frames_by_name(client)["DSCF0002.JPG"]["id"]

    response = client.delete(f"/api/frames/{frame_id}/override")

    assert response.status_code == 204
    keeper = frames_by_name(client)["DSCF0002.JPG"]
    assert (keeper["verdict"], keeper["verdict_overridden"], keeper["override"]) == (
        "keeper",
        False,
        None,
    )


def test_overrides_persist_across_a_re_run(session_dir, review, analyzer):
    burst(session_dir, analyzer, ("DSCF0001", {"aesthetics": 0.4}), ("DSCF0002", {}))
    override(review(), "DSCF0002.JPG", verdict="reject", stars=1, label="red")

    rejected = frames_by_name(review())["DSCF0002.JPG"]

    assert rejected["verdict"] == "reject"
    assert rejected["override"] == {"verdict": "reject", "stars": 1, "label": "red"}


def test_overrides_survive_a_re_run_with_re_analysis(session_dir, review, analyzer):
    burst(session_dir, analyzer, ("DSCF0001", {"aesthetics": 0.4}), ("DSCF0002", {}))
    override(review(), "DSCF0002.JPG", verdict="unsure", stars=2)
    analyzer.analyzed.clear()

    make_jpg(session_dir / "DSCF0002.JPG", captured_at=seconds(0.3), size=(80, 60))
    client = review()

    assert [path.name for path in analyzer.analyzed] == ["DSCF0002.JPG"]
    changed = frames_by_name(client)["DSCF0002.JPG"]
    assert changed["verdict"] == "unsure"
    assert changed["override"] == {"verdict": "unsure", "stars": 2, "label": None}


def test_choosing_a_new_winner_re_judges_the_previous_winner(session_dir, review, analyzer):
    burst(
        session_dir,
        analyzer,
        ("DSCF0001", {"aesthetics": 0.9}),
        ("DSCF0002", {"aesthetics": -0.6}),
    )
    client = review()
    assert verdicts(client) == {"DSCF0001.JPG": "winner", "DSCF0002.JPG": "reject"}

    override(keep_every_clean_frame(client), "DSCF0002.JPG", verdict="winner")

    frames = frames_by_name(client)
    assert (frames["DSCF0002.JPG"]["verdict"], frames["DSCF0002.JPG"]["verdict_overridden"]) == (
        "winner",
        True,
    )
    previous = frames["DSCF0001.JPG"]
    assert (previous["verdict"], previous["verdict_overridden"]) == ("keeper", False)


def test_the_rest_of_the_group_is_re_judged_against_the_new_winner(session_dir, review, analyzer):
    burst(
        session_dir,
        analyzer,
        ("DSCF0001", {"aesthetics": 0.4}),
        ("DSCF0002", {"aesthetics": 0.4, "sharpness": 0.1}),
        ("DSCF0003", {"aesthetics": 0.4, "sharpness": 0.35}),
    )
    client = keep_every_clean_frame(review())

    override(client, "DSCF0003.JPG", verdict="winner")

    assert verdicts(client) == {
        "DSCF0001.JPG": "keeper",
        "DSCF0002.JPG": "reject",
        "DSCF0003.JPG": "winner",
    }


def test_choosing_a_winner_twice_keeps_exactly_one_winner_per_group(session_dir, review, analyzer):
    burst(session_dir, analyzer, ("DSCF0001", {}), ("DSCF0002", {}), ("DSCF0003", {}))
    analyzer.script(make_jpg(session_dir / "DSCF0009.JPG", captured_at=seconds(60)), MOUNTAIN)
    client = review()

    override(client, "DSCF0002.JPG", verdict="winner")
    override(client, "DSCF0003.JPG", verdict="winner")

    groups = client.get("/api/groups").json()
    winners = [
        [frame["jpg_path"] for frame in group["frames"] if frame["verdict"] == "winner"]
        for group in groups
    ]
    assert winners == [["DSCF0003.JPG"], ["DSCF0009.JPG"]]
    assert frames_by_name(client)["DSCF0002.JPG"]["override"] is None


def test_rejecting_the_winner_makes_framewise_pick_another(session_dir, review, analyzer):
    burst(
        session_dir,
        analyzer,
        ("DSCF0001", {"aesthetics": 0.9}),
        ("DSCF0002", {"aesthetics": 0.4}),
        ("DSCF0003", {"aesthetics": 0.0}),
    )
    client = keep_every_clean_frame(review())

    override(client, "DSCF0001.JPG", verdict="reject")

    assert verdicts(client) == {
        "DSCF0001.JPG": "reject",
        "DSCF0002.JPG": "winner",
        "DSCF0003.JPG": "keeper",
    }


def test_an_override_rejects_invalid_values(session_dir, review, analyzer):
    burst(session_dir, analyzer, ("DSCF0001", {}))
    client = review()

    assert override(client, "DSCF0001.JPG", stars=6).status_code == 422
    assert override(client, "DSCF0001.JPG", label="pink").status_code == 422
    assert override(client, "DSCF0001.JPG", verdict="maybe").status_code == 422
    assert frames_by_name(client)["DSCF0001.JPG"]["override"] is None


def test_overriding_an_unknown_frame_is_not_found(session_dir, review, analyzer):
    burst(session_dir, analyzer, ("DSCF0001", {}))
    client = review()

    assert client.patch("/api/frames/999/override", json={"stars": 3}).status_code == 404
    assert client.delete("/api/frames/999/override").status_code == 404


def test_each_frame_links_its_full_size_jpg_for_the_loupe(session_dir, review, analyzer):
    jpg = make_jpg(session_dir / "DSCF0001.JPG", size=(640, 480))
    analyzer.script(jpg, BEACH)
    client = review()

    [frame] = frames_by_name(client).values()
    response = client.get(frame["image_url"])

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert response.content == jpg.read_bytes()
