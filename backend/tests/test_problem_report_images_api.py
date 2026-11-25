from conftest import make_jpg, make_raw
from test_group_fixes_api import BEACH, beach_burst, ids, mountain, seconds
from test_write_back_api import exiftool, image_data_hash, read_back

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


def test_the_session_summary_says_whether_exiftool_is_available(review):
    available = review(find_exiftool=lambda: "/usr/bin/exiftool").get("/api/session").json()
    missing = review(find_exiftool=lambda: None).get("/api/session").json()

    assert available["exiftool"]["available"] is True
    assert missing["exiftool"]["available"] is False
    assert "https://exiftool.org" in missing["exiftool"]["install_hint"]


PERSONAL_INFO = {
    "GPS:GPSLatitude": 46.6186,
    "GPS:GPSLongitude": 12.3027,
    "ExifIFD:SerialNumber": "1234567",
    "ExifIFD:LensSerialNumber": "7654321",
    "ExifIFD:OwnerName": "Jane Doe",
    "IFD0:Artist": "Jane Doe",
    "XMP-aux:SerialNumber": "1234567",
    "XMP-dc:Creator": "Jane Doe",
}
ORDINARY_EXIF = {
    "ExifIFD:ExposureTime": 0.004,
    "ExifIFD:FNumber": 8,
    "ExifIFD:FocalLength": 23,
    "ExifIFD:DateTimeOriginal": "2026:06:20 14:30:00",
}


def tag_camera_info(path):
    exiftool(
        "-overwrite_original",
        *(f"-{tag}={value}" for tag, value in {**PERSONAL_INFO, **ORDINARY_EXIF}.items()),
        path,
    )


def test_removing_personal_info_strips_location_serials_owner_and_artist_from_the_copies_only(
    session_dir, data_dir, review, analyzer, reveal
):
    beach_burst(session_dir, analyzer)
    original = session_dir / "DSCF0001.JPG"
    tag_camera_info(original)
    original_bytes = original.read_bytes()
    client = review(reveal_folder=reveal)
    [group_id] = ids(client, "DSCF0001.JPG")

    prepared = prepare_images(client, group_id, remove_personal_info=True).json()

    copy = data_dir / REPORT_IMAGES / "DSCF0001.JPG"
    assert prepared["personal_info_removed"] is True
    assert read_back(copy, *PERSONAL_INFO) == {}
    assert read_back(copy, *ORDINARY_EXIF) == ORDINARY_EXIF
    assert image_data_hash(copy) == image_data_hash(original)
    assert original.read_bytes() == original_bytes
    assert prepared["files"][0]["size"] == copy.stat().st_size


def test_without_removal_copies_keep_personal_info_byte_for_byte(
    session_dir, data_dir, review, analyzer, reveal
):
    beach_burst(session_dir, analyzer)
    original = session_dir / "DSCF0001.JPG"
    tag_camera_info(original)
    client = review(reveal_folder=reveal)
    [group_id] = ids(client, "DSCF0001.JPG")

    prepared = prepare_images(client, group_id, remove_personal_info=False).json()

    assert prepared["personal_info_removed"] is False
    assert (data_dir / REPORT_IMAGES / "DSCF0001.JPG").read_bytes() == original.read_bytes()


def test_without_exiftool_removal_copies_anyway_and_says_nothing_was_removed(
    session_dir, data_dir, review, analyzer, reveal
):
    beach_burst(session_dir, analyzer)
    original = session_dir / "DSCF0001.JPG"
    tag_camera_info(original)
    client = review(reveal_folder=reveal, find_exiftool=lambda: None)
    [group_id] = ids(client, "DSCF0001.JPG")

    response = prepare_images(client, group_id, remove_personal_info=True)

    assert response.status_code == 200
    assert response.json()["personal_info_removed"] is False
    assert (data_dir / REPORT_IMAGES / "DSCF0001.JPG").read_bytes() == original.read_bytes()
    assert reveal.revealed == [data_dir / REPORT_IMAGES]
