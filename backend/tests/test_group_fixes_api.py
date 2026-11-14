from datetime import datetime, timedelta

from conftest import make_jpg

START = datetime(2026, 6, 20, 14, 30, 0)
BEACH = [1.0, 0.0, 0.0]
MOUNTAIN = [0.0, 1.0, 0.0]


def seconds(count: float) -> datetime:
    return START + timedelta(seconds=count)


def shoot(session_dir, analyzer, fingerprint, *frames: tuple[str, float, dict]) -> None:
    for name, at, signals in frames:
        jpg = make_jpg(session_dir / f"{name}.JPG", captured_at=seconds(at))
        analyzer.script(jpg, fingerprint, **signals)


def beach_burst(session_dir, analyzer) -> None:
    shoot(
        session_dir,
        analyzer,
        BEACH,
        ("DSCF0001", 0, {"aesthetics": 0.9}),
        ("DSCF0002", 0.3, {"aesthetics": 0.4}),
        ("DSCF0003", 0.6, {"aesthetics": 0.0}),
        ("DSCF0004", 0.9, {"aesthetics": -0.6}),
    )


def mountain(session_dir, analyzer) -> None:
    shoot(session_dir, analyzer, MOUNTAIN, ("DSCF0009", 60, {}))


def groups(client) -> list[list[tuple[str, str]]]:
    return [
        [(frame["jpg_path"], frame["verdict"]) for frame in group["frames"]]
        for group in client.get("/api/groups").json()
    ]


def group_paths(client) -> list[list[str]]:
    return [[path for path, _ in group] for group in groups(client)]


def winner_counts(client) -> list[int]:
    return [sum(verdict == "winner" for _, verdict in group) for group in groups(client)]


def ids(client, *names: str) -> list[int]:
    by_name = {
        frame["jpg_path"]: frame["id"]
        for group in client.get("/api/groups").json()
        for frame in group["frames"]
    }
    return [by_name[name] for name in names]


def split(client, *names: str):
    return client.post("/api/groups/split", json={"frame_ids": ids(client, *names)})


def merge(client, *names: str):
    return client.post("/api/groups/merge", json={"frame_ids": ids(client, *names)})


def move(client, name: str, to: str):
    frame_id, to_frame_id = ids(client, name, to)
    return client.post(f"/api/frames/{frame_id}/move", json={"to_frame_id": to_frame_id})


def test_splitting_a_group_at_a_frame_gives_each_part_one_winner(session_dir, review, analyzer):
    beach_burst(session_dir, analyzer)
    client = review()

    response = split(client, "DSCF0003.JPG", "DSCF0004.JPG")

    assert response.status_code == 204
    assert groups(client) == [
        [("DSCF0001.JPG", "winner"), ("DSCF0002.JPG", "keeper")],
        [("DSCF0003.JPG", "winner"), ("DSCF0004.JPG", "keeper")],
    ]


def test_splitting_off_a_selection_keeps_the_rest_together(session_dir, review, analyzer):
    beach_burst(session_dir, analyzer)
    client = review()

    split(client, "DSCF0002.JPG", "DSCF0004.JPG")

    assert group_paths(client) == [
        ["DSCF0001.JPG", "DSCF0003.JPG"],
        ["DSCF0002.JPG", "DSCF0004.JPG"],
    ]
    assert winner_counts(client) == [1, 1]


def test_merging_two_groups_leaves_one_winner(session_dir, review, analyzer):
    beach_burst(session_dir, analyzer)
    mountain(session_dir, analyzer)
    client = review()
    assert winner_counts(client) == [1, 1]

    response = merge(client, "DSCF0002.JPG", "DSCF0009.JPG")

    assert response.status_code == 204
    assert group_paths(client) == [
        ["DSCF0001.JPG", "DSCF0002.JPG", "DSCF0003.JPG", "DSCF0004.JPG", "DSCF0009.JPG"]
    ]
    assert winner_counts(client) == [1]


def test_moving_a_frame_re_judges_both_groups(session_dir, review, analyzer):
    beach_burst(session_dir, analyzer)
    mountain(session_dir, analyzer)
    client = review()

    response = move(client, "DSCF0001.JPG", to="DSCF0009.JPG")

    assert response.status_code == 204
    assert groups(client) == [
        [("DSCF0001.JPG", "winner"), ("DSCF0009.JPG", "reject")],
        [("DSCF0002.JPG", "winner"), ("DSCF0003.JPG", "keeper"), ("DSCF0004.JPG", "reject")],
    ]


def test_moving_the_only_frame_of_a_group_merges_it_away(session_dir, review, analyzer):
    beach_burst(session_dir, analyzer)
    mountain(session_dir, analyzer)
    client = review()

    move(client, "DSCF0009.JPG", to="DSCF0001.JPG")

    assert len(group_paths(client)) == 1
    assert winner_counts(client) == [1]


def test_group_fixes_survive_a_re_run(session_dir, review, analyzer):
    beach_burst(session_dir, analyzer)
    mountain(session_dir, analyzer)
    client = review()
    split(client, "DSCF0003.JPG", "DSCF0004.JPG")
    move(client, "DSCF0002.JPG", to="DSCF0009.JPG")
    fixed = group_paths(client)

    assert (
        group_paths(review())
        == fixed
        == [
            ["DSCF0001.JPG"],
            ["DSCF0002.JPG", "DSCF0009.JPG"],
            ["DSCF0003.JPG", "DSCF0004.JPG"],
        ]
    )


def test_re_analysis_does_not_undo_a_group_fix(session_dir, review, analyzer):
    beach_burst(session_dir, analyzer)
    split(review(), "DSCF0003.JPG", "DSCF0004.JPG")
    analyzer.analyzed.clear()

    make_jpg(session_dir / "DSCF0003.JPG", captured_at=seconds(0.6), size=(80, 60))
    client = review()

    assert [path.name for path in analyzer.analyzed] == ["DSCF0003.JPG"]
    assert group_paths(client) == [
        ["DSCF0001.JPG", "DSCF0002.JPG"],
        ["DSCF0003.JPG", "DSCF0004.JPG"],
    ]


def test_a_frame_analysed_after_a_group_fix_does_not_undo_it(session_dir, review, analyzer):
    beach_burst(session_dir, analyzer)
    split(review(), "DSCF0003.JPG", "DSCF0004.JPG")

    shoot(session_dir, analyzer, BEACH, ("DSCF0005", 1.2, {}), ("DSCF0006", 1.5, {}))
    client = review()

    assert group_paths(client) == [
        ["DSCF0001.JPG", "DSCF0002.JPG"],
        ["DSCF0003.JPG", "DSCF0004.JPG"],
        ["DSCF0005.JPG", "DSCF0006.JPG"],
    ]


def test_verdict_overrides_still_win_after_group_fixes(session_dir, review, analyzer):
    beach_burst(session_dir, analyzer)
    mountain(session_dir, analyzer)
    client = review()
    [keeper_id, winner_id] = ids(client, "DSCF0002.JPG", "DSCF0004.JPG")
    client.patch(f"/api/frames/{keeper_id}/override", json={"verdict": "reject", "stars": 2})
    client.patch(f"/api/frames/{winner_id}/override", json={"verdict": "winner"})

    split(client, "DSCF0001.JPG", "DSCF0002.JPG")
    move(client, "DSCF0004.JPG", to="DSCF0009.JPG")

    assert groups(client) == [
        [("DSCF0001.JPG", "winner"), ("DSCF0002.JPG", "reject")],
        [("DSCF0003.JPG", "winner")],
        [("DSCF0004.JPG", "winner"), ("DSCF0009.JPG", "keeper")],
    ]
    frames = {
        frame["jpg_path"]: frame
        for group in client.get("/api/groups").json()
        for frame in group["frames"]
    }
    assert frames["DSCF0002.JPG"]["verdict_overridden"] is True
    assert frames["DSCF0002.JPG"]["override"] == {"verdict": "reject", "stars": 2, "label": None}
    assert frames["DSCF0004.JPG"]["verdict_overridden"] is True


def test_merging_groups_with_two_chosen_winners_keeps_the_first(session_dir, review, analyzer):
    beach_burst(session_dir, analyzer)
    mountain(session_dir, analyzer)
    client = review()
    [beach_id, mountain_id] = ids(client, "DSCF0003.JPG", "DSCF0009.JPG")
    client.patch(f"/api/frames/{beach_id}/override", json={"verdict": "winner"})
    client.patch(f"/api/frames/{mountain_id}/override", json={"verdict": "winner"})

    merge(client, "DSCF0001.JPG", "DSCF0009.JPG")

    [merged] = groups(client)
    assert [path for path, verdict in merged if verdict == "winner"] == ["DSCF0003.JPG"]


def test_choosing_a_winner_after_a_split_keeps_the_other_parts_winner(
    session_dir, review, analyzer
):
    beach_burst(session_dir, analyzer)
    client = review()
    [second_id] = ids(client, "DSCF0002.JPG")
    client.patch(f"/api/frames/{second_id}/override", json={"verdict": "winner"})
    split(client, "DSCF0003.JPG", "DSCF0004.JPG")

    [fourth_id] = ids(client, "DSCF0004.JPG")
    client.patch(f"/api/frames/{fourth_id}/override", json={"verdict": "winner"})

    assert groups(client) == [
        [("DSCF0001.JPG", "keeper"), ("DSCF0002.JPG", "winner")],
        [("DSCF0003.JPG", "keeper"), ("DSCF0004.JPG", "winner")],
    ]


def test_group_fixes_reject_impossible_changes(session_dir, review, analyzer):
    beach_burst(session_dir, analyzer)
    mountain(session_dir, analyzer)
    client = review()

    assert split(client, *[f"DSCF000{n}.JPG" for n in range(1, 5)]).status_code == 422
    assert split(client, "DSCF0004.JPG", "DSCF0009.JPG").status_code == 422
    assert client.post("/api/groups/split", json={"frame_ids": []}).status_code == 422
    assert merge(client, "DSCF0001.JPG", "DSCF0002.JPG").status_code == 422
    assert move(client, "DSCF0001.JPG", to="DSCF0002.JPG").status_code == 422
    assert group_paths(client) == [
        ["DSCF0001.JPG", "DSCF0002.JPG", "DSCF0003.JPG", "DSCF0004.JPG"],
        ["DSCF0009.JPG"],
    ]


def test_group_fixes_of_unknown_frames_are_not_found(session_dir, review, analyzer):
    mountain(session_dir, analyzer)
    client = review()
    [frame_id] = ids(client, "DSCF0009.JPG")

    assert client.post("/api/groups/split", json={"frame_ids": [999]}).status_code == 404
    assert client.post("/api/groups/merge", json={"frame_ids": [frame_id, 999]}).status_code == 404
    assert client.post("/api/frames/999/move", json={"to_frame_id": frame_id}).status_code == 404
    assert client.post(f"/api/frames/{frame_id}/move", json={"to_frame_id": 999}).status_code == 404


def test_rating_write_back_follows_the_fixed_groups(session_dir, review, analyzer):
    beach_burst(session_dir, analyzer)
    client = review()

    split(client, "DSCF0003.JPG", "DSCF0004.JPG")

    dry_run = client.get("/api/write-back").json()
    assert {file["path"]: file["verdict"] for file in dry_run["files"]} == {
        "DSCF0001.JPG": "winner",
        "DSCF0002.JPG": "keeper",
        "DSCF0003.JPG": "winner",
        "DSCF0004.JPG": "keeper",
    }


def reset(client, *names: str):
    return client.post("/api/groups/reset", json={"frame_ids": ids(client, *names)})


def fixed_flags(client) -> list[bool]:
    return [group["fixed"] for group in client.get("/api/groups").json()]


def test_groups_say_whether_the_photographer_fixed_them(session_dir, review, analyzer):
    beach_burst(session_dir, analyzer)
    mountain(session_dir, analyzer)
    client = review()
    assert fixed_flags(client) == [False, False]

    split(client, "DSCF0003.JPG", "DSCF0004.JPG")

    assert fixed_flags(client) == [True, True, False]


def test_resetting_a_fixed_group_regroups_it_with_unpinned_frames(session_dir, review, analyzer):
    beach_burst(session_dir, analyzer)
    split(review(), "DSCF0003.JPG", "DSCF0004.JPG")
    shoot(session_dir, analyzer, BEACH, ("DSCF0005", 1.2, {}))
    client = review()
    assert group_paths(client) == [
        ["DSCF0001.JPG", "DSCF0002.JPG"],
        ["DSCF0003.JPG", "DSCF0004.JPG"],
        ["DSCF0005.JPG"],
    ]

    response = reset(client, "DSCF0003.JPG")

    assert response.status_code == 204
    assert group_paths(client) == [
        ["DSCF0001.JPG", "DSCF0002.JPG"],
        ["DSCF0003.JPG", "DSCF0004.JPG", "DSCF0005.JPG"],
    ]
    assert winner_counts(client) == [1, 1]
    assert fixed_flags(client) == [True, False]


def test_resetting_every_fixed_group_restores_framewises_grouping(session_dir, review, analyzer):
    beach_burst(session_dir, analyzer)
    mountain(session_dir, analyzer)
    client = review()
    framewises = groups(client)
    move(client, "DSCF0001.JPG", to="DSCF0009.JPG")

    reset(client, "DSCF0001.JPG")
    reset(client, "DSCF0002.JPG")

    assert groups(client) == framewises
    assert group_paths(client) == [
        ["DSCF0001.JPG", "DSCF0002.JPG", "DSCF0003.JPG", "DSCF0004.JPG"],
        ["DSCF0009.JPG"],
    ]
    assert fixed_flags(client) == [False, False]


def test_resetting_a_group_keeps_verdict_overrides(session_dir, review, analyzer):
    beach_burst(session_dir, analyzer)
    client = review()
    [fourth_id] = ids(client, "DSCF0004.JPG")
    client.patch(f"/api/frames/{fourth_id}/override", json={"verdict": "winner", "stars": 3})
    split(client, "DSCF0003.JPG", "DSCF0004.JPG")

    reset(client, "DSCF0001.JPG")
    reset(client, "DSCF0003.JPG")

    frames = {
        frame["jpg_path"]: frame
        for group in client.get("/api/groups").json()
        for frame in group["frames"]
    }
    assert len(group_paths(client)) == 1
    assert frames["DSCF0004.JPG"]["verdict"] == "winner"
    assert frames["DSCF0004.JPG"]["override"] == {"verdict": "winner", "stars": 3, "label": None}


def test_resetting_a_group_nobody_fixed_changes_nothing(session_dir, review, analyzer):
    beach_burst(session_dir, analyzer)
    client = review()

    assert reset(client, "DSCF0001.JPG").status_code == 204
    assert client.post("/api/groups/reset", json={"frame_ids": [999]}).status_code == 404
    assert group_paths(client) == [["DSCF0001.JPG", "DSCF0002.JPG", "DSCF0003.JPG", "DSCF0004.JPG"]]
