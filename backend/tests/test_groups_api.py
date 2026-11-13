from datetime import datetime, timedelta

from conftest import make_jpg, make_raw

START = datetime(2026, 6, 20, 14, 30, 0)
BEACH = [1.0, 0.0, 0.0]
BEACH_A_MOMENT_LATER = [0.85, 0.53, 0.0]
MOUNTAIN = [0.0, 1.0, 0.0]


def seconds(count: float) -> datetime:
    return START + timedelta(seconds=count)


def group_paths(client) -> list[list[str]]:
    return [
        [frame["jpg_path"] for frame in group["frames"]]
        for group in client.get("/api/groups").json()
    ]


def test_a_frame_with_no_near_duplicates_forms_a_group_of_one(session_dir, review, analyzer):
    analyzer.script(make_jpg(session_dir / "DSCF0001.JPG", captured_at=seconds(0)), BEACH)
    analyzer.script(make_jpg(session_dir / "DSCF0002.JPG", captured_at=seconds(1)), MOUNTAIN)

    assert group_paths(review()) == [["DSCF0001.JPG"], ["DSCF0002.JPG"]]


def test_a_burst_of_similar_frames_forms_one_group(session_dir, review, analyzer):
    analyzer.script(make_jpg(session_dir / "DSCF0001.JPG", captured_at=seconds(0)), BEACH)
    analyzer.script(
        make_jpg(session_dir / "DSCF0002.JPG", captured_at=seconds(0.3)), BEACH_A_MOMENT_LATER
    )
    analyzer.script(make_jpg(session_dir / "DSCF0003.JPG", captured_at=seconds(0.6)), BEACH)
    analyzer.script(make_jpg(session_dir / "DSCF0004.JPG", captured_at=seconds(2)), MOUNTAIN)

    assert group_paths(review()) == [
        ["DSCF0001.JPG", "DSCF0002.JPG", "DSCF0003.JPG"],
        ["DSCF0004.JPG"],
    ]


def test_similar_frames_captured_far_apart_in_time_form_separate_groups(
    session_dir, review, analyzer
):
    analyzer.script(make_jpg(session_dir / "DSCF0001.JPG", captured_at=seconds(0)), BEACH)
    analyzer.script(
        make_jpg(session_dir / "DSCF0002.JPG", captured_at=seconds(30)), BEACH_A_MOMENT_LATER
    )
    analyzer.script(make_jpg(session_dir / "DSCF0003.JPG", captured_at=seconds(3600)), BEACH)

    assert group_paths(review()) == [["DSCF0001.JPG"], ["DSCF0002.JPG"], ["DSCF0003.JPG"]]


def test_near_duplicates_from_two_cameras_group_across_subfolders(session_dir, review, analyzer):
    analyzer.script(
        make_jpg(session_dir / "card-a" / "L1000001.JPG", captured_at=seconds(0)), BEACH
    )
    analyzer.script(
        make_jpg(session_dir / "card-b" / "DSCF0001.JPG", captured_at=seconds(40)), BEACH
    )
    analyzer.script(
        make_jpg(session_dir / "card-a" / "L1000002.JPG", captured_at=seconds(41)), MOUNTAIN
    )

    assert group_paths(review()) == [
        ["card-a/L1000001.JPG", "card-b/DSCF0001.JPG"],
        ["card-a/L1000002.JPG"],
    ]


def test_frames_without_a_capture_time_group_only_with_each_other_as_near_duplicates(
    session_dir, review, analyzer
):
    analyzer.script(make_jpg(session_dir / "DSCF0001.JPG", captured_at=seconds(0)), BEACH)
    analyzer.script(make_jpg(session_dir / "DSCF0002.JPG", captured_at=seconds(3600)), BEACH)
    analyzer.script(make_jpg(session_dir / "scan-1.JPG"), BEACH)
    analyzer.script(make_jpg(session_dir / "scan-2.JPG"), BEACH)
    analyzer.script(make_jpg(session_dir / "scan-3.JPG"), BEACH_A_MOMENT_LATER)

    assert group_paths(review()) == [
        ["DSCF0001.JPG"],
        ["DSCF0002.JPG"],
        ["scan-1.JPG", "scan-2.JPG"],
        ["scan-3.JPG"],
    ]


def test_a_re_run_without_file_changes_performs_no_analysis(session_dir, review, analyzer):
    analyzer.script(make_jpg(session_dir / "DSCF0001.JPG", captured_at=seconds(0)), BEACH)
    analyzer.script(make_jpg(session_dir / "DSCF0002.JPG", captured_at=seconds(1)), BEACH)
    first_run = group_paths(review())
    analyzer.analyzed.clear()

    second_run = group_paths(review())

    assert analyzer.analyzed == []
    assert second_run == first_run == [["DSCF0001.JPG", "DSCF0002.JPG"]]


def test_a_re_run_analyses_only_new_or_changed_frames(session_dir, review, analyzer):
    analyzer.script(make_jpg(session_dir / "DSCF0001.JPG", captured_at=seconds(0)), BEACH)
    analyzer.script(make_jpg(session_dir / "DSCF0002.JPG", captured_at=seconds(1)), BEACH)
    review()
    analyzer.analyzed.clear()

    analyzer.script(
        make_jpg(session_dir / "DSCF0002.JPG", captured_at=seconds(1), size=(80, 60)), MOUNTAIN
    )
    analyzer.script(make_jpg(session_dir / "DSCF0003.JPG", captured_at=seconds(2)), BEACH)
    client = review()

    assert sorted(path.name for path in analyzer.analyzed) == ["DSCF0002.JPG", "DSCF0003.JPG"]
    assert group_paths(client) == [["DSCF0001.JPG", "DSCF0003.JPG"], ["DSCF0002.JPG"]]


def test_each_group_carries_its_frames_with_kind_camera_rating_and_thumbnail(
    session_dir, review, analyzer
):
    make_raw(session_dir / "DSCF0001.RAF")
    analyzer.script(
        make_jpg(session_dir / "DSCF0001.JPG", stars=2, captured_at=seconds(0)), MOUNTAIN
    )
    client = review()

    [group] = client.get("/api/groups").json()

    [frame] = client.get("/api/frames").json()
    assert group == {"id": frame["id"], "frames": [frame]}
    assert frame["kind"] == "raw+jpg"
    assert frame["camera_rating"] == {"stars": 2, "label": None}
    assert client.get(frame["thumbnail_url"]).status_code == 200
