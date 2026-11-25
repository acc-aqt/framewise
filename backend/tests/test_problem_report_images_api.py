from conftest import make_jpg, make_raw
from test_group_fixes_api import BEACH, beach_burst, ids, mountain, seconds

from framewise.review import session_database_path
from framewise.store import preview_cache_dir

REPORT_IMAGES = "problem-report-images"


def prepare_images(client, group_id: int, remove_personal_info: bool = False):
    return client.post(
        f"/api/groups/{group_id}/problem-report/images",
        json={"remove_personal_info": remove_personal_info},
    )


def test_a_groups_analysis_sources_are_copied_exactly_into_a_folder_in_the_data_folder(
    session_dir, data_dir, review, analyzer, reveal
):
    beach_burst(session_dir, analyzer)
    client = review(reveal_folder=reveal)
    [group_id] = ids(client, "DSCF0001.JPG")

    response = prepare_images(client, group_id)

    assert response.status_code == 200
    prepared = response.json()
    folder = data_dir / REPORT_IMAGES
    assert prepared["folder"] == str(folder)
    names = ["DSCF0001.JPG", "DSCF0002.JPG", "DSCF0003.JPG", "DSCF0004.JPG"]
    assert prepared["files"] == [
        {"name": name, "size": (session_dir / name).stat().st_size, "too_large": False}
        for name in names
    ]
    for name in names:
        assert (folder / name).read_bytes() == (session_dir / name).read_bytes()
    assert sorted(path.name for path in folder.iterdir()) == names
    assert prepared["personal_info_removed"] is False
    assert reveal.revealed == [folder]


def test_a_raw_only_frame_is_attached_as_its_embedded_preview_under_its_raws_name(
    session_dir, data_dir, review, reveal
):
    make_raw(session_dir / "DSCF0001.RAF")
    client = review(reveal_folder=reveal)
    [group_id] = ids(client, "DSCF0001.RAF")

    prepared = prepare_images(client, group_id).json()

    cache = preview_cache_dir(session_database_path(session_dir.resolve(), data_dir))
    [preview] = cache.iterdir()
    assert [file["name"] for file in prepared["files"]] == ["DSCF0001.RAF.jpg"]
    copy = data_dir / REPORT_IMAGES / "DSCF0001.RAF.jpg"
    assert copy.read_bytes() == preview.read_bytes()


def test_a_second_report_replaces_the_first_reports_images_and_leaves_the_session_alone(
    session_dir, data_dir, review, analyzer, reveal
):
    beach_burst(session_dir, analyzer)
    mountain(session_dir, analyzer)
    client = review(reveal_folder=reveal)
    beach_id, mountain_id = ids(client, "DSCF0001.JPG", "DSCF0009.JPG")
    session_files = sorted(session_dir.rglob("*"))

    prepare_images(client, beach_id)
    prepare_images(client, mountain_id)

    folder = data_dir / REPORT_IMAGES
    assert [path.name for path in folder.iterdir()] == ["DSCF0009.JPG"]
    assert reveal.revealed == [folder, folder]
    assert sorted(session_dir.rglob("*")) == session_files


def test_frames_of_the_same_name_from_different_subfolders_each_get_their_own_copy(
    session_dir, data_dir, review, analyzer, reveal
):
    for folder, at in (("card-a", 0), ("card-b", 0.3)):
        jpg = make_jpg(session_dir / folder / "DSCF0001.JPG", captured_at=seconds(at))
        analyzer.script(jpg, BEACH)
    client = review(reveal_folder=reveal)
    [group_id] = ids(client, "card-a/DSCF0001.JPG")

    prepared = prepare_images(client, group_id).json()

    assert [file["name"] for file in prepared["files"]] == ["DSCF0001.JPG", "DSCF0001 (2).JPG"]
    folder = data_dir / REPORT_IMAGES
    assert (folder / "DSCF0001 (2).JPG").read_bytes() == (
        session_dir / "card-b/DSCF0001.JPG"
    ).read_bytes()


def test_an_image_over_githubs_10_mb_limit_is_flagged(session_dir, review, analyzer, reveal):
    beach_burst(session_dir, analyzer)
    with (session_dir / "DSCF0002.JPG").open("ab") as jpg:
        jpg.write(b"\0" * 10_000_000)
    client = review(reveal_folder=reveal)
    [group_id] = ids(client, "DSCF0001.JPG")

    prepared = prepare_images(client, group_id).json()

    assert [(file["name"], file["too_large"]) for file in prepared["files"]] == [
        ("DSCF0001.JPG", False),
        ("DSCF0002.JPG", True),
        ("DSCF0003.JPG", False),
        ("DSCF0004.JPG", False),
    ]


def test_images_are_prepared_only_for_a_known_group(session_dir, review, analyzer, reveal):
    beach_burst(session_dir, analyzer)
    client = review(reveal_folder=reveal)
    [second_frame_id] = ids(client, "DSCF0002.JPG")

    assert prepare_images(client, second_frame_id).status_code == 404
    assert prepare_images(client, 9999).status_code == 404
    assert reveal.revealed == []
