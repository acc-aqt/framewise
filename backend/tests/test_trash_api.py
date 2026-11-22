from conftest import make_raw, make_sidecar, wait_until
from test_group_fixes_api import beach_burst, group_paths, groups, ids, mountain
from test_verdicts_api import keep_every_clean_frame
from test_write_back_api import BLURRY, jpg, lightroom_preferences, rating


def trash_frames(client, *names: str):
    return client.post("/api/frames/trash", json={"frame_ids": ids(client, *names)})


def test_trashing_a_frame_moves_its_file_to_the_trash_and_takes_it_out_of_the_session(
    session_dir, review, analyzer, trash
):
    beach_burst(session_dir, analyzer)
    client = review(move_to_trash=trash)
    [frame_id] = ids(client, "DSCF0002.JPG")

    response = trash_frames(client, "DSCF0002.JPG")

    assert response.json() == {"trashed": [frame_id], "failed": []}
    assert trash.trashed == [session_dir / "DSCF0002.JPG"]
    assert not (session_dir / "DSCF0002.JPG").exists()
    assert group_paths(client) == [["DSCF0001.JPG", "DSCF0003.JPG", "DSCF0004.JPG"]]
    assert client.get("/api/session").json()["total_frames"] == 3
    assert client.get(f"/api/frames/{frame_id}/thumbnail").status_code == 404


def test_a_raw_jpg_frame_is_trashed_whole_with_its_sidecar(session_dir, review, analyzer, trash):
    raf = make_raw(session_dir / "DSCF0001.RAF")
    sidecar = make_sidecar(session_dir / "DSCF0001.xmp", stars=1)
    jpg(session_dir, analyzer, "DSCF0001.JPG")
    client = review(move_to_trash=trash)

    trash_frames(client, "DSCF0001.JPG")

    assert set(trash.trashed) == {raf, sidecar, session_dir / "DSCF0001.JPG"}
    assert client.get("/api/session").json()["total_frames"] == 0


def test_trashing_every_frame_of_a_group_removes_the_group(session_dir, review, analyzer, trash):
    beach_burst(session_dir, analyzer)
    mountain(session_dir, analyzer)
    client = review(move_to_trash=trash)
    burst = ["DSCF0001.JPG", "DSCF0002.JPG", "DSCF0003.JPG", "DSCF0004.JPG"]

    response = trash_frames(client, *burst)

    assert len(response.json()["trashed"]) == 4
    assert group_paths(client) == [["DSCF0009.JPG"]]


def test_trashing_the_winner_makes_framewise_pick_another(session_dir, review, analyzer, trash):
    beach_burst(session_dir, analyzer)
    client = keep_every_clean_frame(review(move_to_trash=trash))
    assert groups(client)[0][0] == ("DSCF0001.JPG", "winner")

    trash_frames(client, "DSCF0001.JPG")

    assert groups(client)[0][0] == ("DSCF0002.JPG", "winner")


def test_a_frame_on_a_volume_without_a_trash_stays_and_is_reported(
    session_dir, review, analyzer, trash
):
    beach_burst(session_dir, analyzer)
    trash.refuse(session_dir / "DSCF0002.JPG")
    client = review(move_to_trash=trash)
    [kept_id, trashed_id] = ids(client, "DSCF0002.JPG", "DSCF0003.JPG")

    response = trash_frames(client, "DSCF0002.JPG", "DSCF0003.JPG").json()

    assert response["trashed"] == [trashed_id]
    assert [failure["path"] for failure in response["failed"]] == ["DSCF0002.JPG"]
    assert (session_dir / "DSCF0002.JPG").exists()
    assert kept_id in ids(client, "DSCF0002.JPG")


def test_a_restored_frame_comes_back_with_its_overrides(session_dir, review, analyzer, trash):
    beach_burst(session_dir, analyzer)
    client = review(move_to_trash=trash)
    [frame_id] = ids(client, "DSCF0003.JPG")
    client.patch(f"/api/frames/{frame_id}/override", json={"verdict": "reject", "stars": 4})
    trash_frames(client, "DSCF0003.JPG")

    trash.restore(session_dir / "DSCF0003.JPG")
    client = review(move_to_trash=trash)

    [restored] = [
        frame
        for group in client.get("/api/groups").json()
        for frame in group["frames"]
        if frame["main_path"] == "DSCF0003.JPG"
    ]
    assert restored["override"] == {"verdict": "reject", "stars": 4, "label": None}


def test_undo_write_back_skips_trashed_files_and_restores_them_once_they_are_back(
    session_dir, review, analyzer, trash, tmp_path
):
    english = {"lightroom_preferences": lightroom_preferences(tmp_path, "Red", "Yellow")}
    jpg(session_dir, analyzer, "DSCF0001.JPG", stars=1, aesthetics=0.75)
    trashed = jpg(session_dir, analyzer, "DSCF0002.JPG", 0.3, stars=1, **BLURRY)
    client = review(move_to_trash=trash, **english)
    client.post("/api/write-back")
    trash_frames(client, "DSCF0002.JPG")

    result = client.post("/api/write-back/undo").json()

    assert result == {"written": ["DSCF0001.JPG"], "failed": []}
    assert client.get("/api/write-back").json()["can_undo"] is False

    trash.restore(trashed)
    client = review(move_to_trash=trash, **english)
    assert client.get("/api/write-back").json()["can_undo"] is True
    assert client.post("/api/write-back/undo").json()["failed"] == []
    assert rating(trashed) == {"stars": 1, "label": None}


def test_a_frame_trashed_while_it_is_analyzed_is_skipped_quietly(
    session_dir, live_review, analyzer, trash, capsys
):
    beach_burst(session_dir, analyzer)
    held = analyzer.hold(session_dir / "DSCF0004.JPG")
    client = live_review(move_to_trash=trash)
    wait_until(lambda: client.get("/api/progress").json()["frames_left"] == 1)
    [frame_id] = [
        frame["id"]
        for frame in client.get("/api/frames").json()
        if frame["main_path"] == "DSCF0004.JPG"
    ]

    client.post("/api/frames/trash", json={"frame_ids": [frame_id]})
    analyzer.release(held)

    wait_until(lambda: client.get("/api/progress").json()["frames_left"] == 0)
    assert group_paths(client) == [["DSCF0001.JPG", "DSCF0002.JPG", "DSCF0003.JPG"]]
    assert "could not analyze" not in capsys.readouterr().err


def test_trashing_an_unknown_frame_is_refused(session_dir, review, analyzer, trash):
    beach_burst(session_dir, analyzer)
    client = review(move_to_trash=trash)

    response = client.post("/api/frames/trash", json={"frame_ids": [9999]})

    assert response.status_code == 404
    assert trash.trashed == []
