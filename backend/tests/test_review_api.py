import io
from pathlib import Path

import pytest
from conftest import make_jpg, make_raw, make_sidecar
from fastapi.testclient import TestClient
from PIL import Image

from framewise.review import open_session
from framewise.server import create_app


def test_a_lone_jpg_becomes_a_jpg_only_frame(session_dir, review):
    make_jpg(session_dir / "DSCF0001.JPG")

    summary = review().get("/api/session").json()

    assert summary["total_frames"] == 1
    assert summary["jpg_only_count"] == 1
    assert summary["raw_jpg_count"] == 0
    assert summary["skipped"] == []


@pytest.mark.parametrize(
    "raw_name", ["L1000001.DNG", "DSCF0001.RAF", "DSC00001.arw", "DSC_0001.NEF", "IMG_0001.Cr3"]
)
@pytest.mark.parametrize("jpg_extension", [".JPG", ".jpg", ".jpeg", ".JPEG"])
def test_a_raw_and_jpg_with_the_same_base_name_become_one_raw_jpg_frame(
    session_dir, review, raw_name, jpg_extension
):
    raw = make_raw(session_dir / raw_name)
    make_jpg(session_dir / f"{raw.stem}{jpg_extension}")

    summary = review().get("/api/session").json()

    assert summary["total_frames"] == 1
    assert summary["raw_jpg_count"] == 1
    assert summary["jpg_only_count"] == 0
    assert summary["skipped"] == []


def test_a_raw_without_a_matching_jpg_is_reported_as_skipped(session_dir, review):
    make_raw(session_dir / "L1000001.DNG")
    make_jpg(session_dir / "L1000001.JPG")
    make_raw(session_dir / "L1000001-Pano.dng")

    summary = review().get("/api/session").json()

    assert summary["total_frames"] == 1
    assert summary["skipped"] == ["L1000001-Pano.dng"]


def test_raws_sharing_a_base_name_without_a_jpg_are_all_reported_as_skipped(session_dir, review):
    make_raw(session_dir / "DSCF0001.RAF")
    make_raw(session_dir / "DSCF0001.DNG")

    summary = review().get("/api/session").json()

    assert summary["total_frames"] == 0
    assert summary["skipped"] == ["DSCF0001.DNG", "DSCF0001.RAF"]


def test_only_one_of_several_raws_sharing_a_base_name_pairs_with_the_jpg(session_dir, review):
    make_raw(session_dir / "DSCF0001.RAF")
    make_raw(session_dir / "DSCF0001.DNG")
    make_jpg(session_dir / "DSCF0001.JPG")

    client = review()
    summary = client.get("/api/session").json()
    [frame] = client.get("/api/frames").json()

    assert summary["raw_jpg_count"] == 1
    assert sorted([frame["raw_path"], *summary["skipped"]]) == ["DSCF0001.DNG", "DSCF0001.RAF"]


def test_subfolders_are_scanned_and_pairing_stays_within_one_folder(session_dir, review):
    make_raw(session_dir / "day1" / "DSCF0001.RAF")
    make_jpg(session_dir / "day1" / "DSCF0001.JPG")
    make_jpg(session_dir / "day2" / "evening" / "DSCF0002.JPG")
    make_raw(session_dir / "day2" / "DSCF0002.RAF")

    client = review()
    summary = client.get("/api/session").json()
    frames = client.get("/api/frames").json()

    assert summary["total_frames"] == 2
    assert summary["raw_jpg_count"] == 1
    assert summary["jpg_only_count"] == 1
    assert summary["skipped"] == ["day2/DSCF0002.RAF"]
    assert [(frame["jpg_path"], frame["raw_path"], frame["kind"]) for frame in frames] == [
        ("day1/DSCF0001.JPG", "day1/DSCF0001.RAF", "raw+jpg"),
        ("day2/evening/DSCF0002.JPG", None, "jpg-only"),
    ]


def test_each_frame_has_a_reduced_size_jpeg_thumbnail(session_dir, review):
    make_jpg(session_dir / "DSCF0001.JPG", size=(2400, 1600))
    client = review()
    [frame] = client.get("/api/frames").json()

    response = client.get(frame["thumbnail_url"])

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    thumbnail = Image.open(io.BytesIO(response.content))
    assert thumbnail.size == (480, 320)


def test_an_unknown_frame_has_no_thumbnail(session_dir, review):
    make_jpg(session_dir / "DSCF0001.JPG")

    assert review().get("/api/frames/999/thumbnail").status_code == 404


def snapshot(folder: Path) -> dict[str, tuple[int, bytes]]:
    return {
        path.relative_to(folder).as_posix(): (path.stat().st_mtime_ns, path.read_bytes())
        for path in folder.rglob("*")
        if path.is_file()
    }


def test_nothing_is_written_into_the_session_folder(session_dir, review):
    make_raw(session_dir / "L1000001.DNG", stars=1)
    make_jpg(session_dir / "L1000001.JPG", stars=1)
    make_raw(session_dir / "sub" / "orphan.RAF")
    before = snapshot(session_dir)

    client = review()
    for frame in client.get("/api/frames").json():
        client.get(frame["thumbnail_url"])

    assert snapshot(session_dir) == before


def test_re_running_on_the_same_folder_reuses_the_session_store(session_dir, data_dir, review):
    make_jpg(session_dir / "DSCF0001.JPG")
    make_jpg(session_dir / "DSCF0002.JPG")
    first_run = review().get("/api/frames").json()

    (session_dir / "DSCF0002.JPG").unlink()
    make_jpg(session_dir / "DSCF0003.JPG")
    second_run = review().get("/api/frames").json()

    assert len(list(data_dir.iterdir())) == 1
    assert [frame["jpg_path"] for frame in second_run] == ["DSCF0001.JPG", "DSCF0003.JPG"]
    assert second_run[0]["id"] == first_run[0]["id"]


def test_the_review_ui_build_is_served_at_the_root(session_dir, data_dir, tmp_path):
    ui_dir = tmp_path / "ui"
    ui_dir.mkdir()
    (ui_dir / "index.html").write_text("<app-root></app-root>")
    (ui_dir / "main.js").write_text("console.log('framewise')")
    client = TestClient(create_app(open_session(session_dir, data_dir), ui_dir))

    assert "<app-root>" in client.get("/").text
    assert "framewise" in client.get("/main.js").text
    assert client.get("/api/session").status_code == 200


def camera_ratings(client) -> dict[str, dict]:
    return {frame["jpg_path"]: frame["camera_rating"] for frame in client.get("/api/frames").json()}


def test_camera_ratings_and_labels_are_read_from_jpg_xmp_and_exif(session_dir, review):
    make_jpg(session_dir / "rated.JPG", stars=1, label="Rot")
    make_jpg(session_dir / "exif.JPG", exif_stars=2)
    make_jpg(session_dir / "plain.JPG")

    assert camera_ratings(review()) == {
        "exif.JPG": {"stars": 2, "label": None},
        "plain.JPG": {"stars": None, "label": None},
        "rated.JPG": {"stars": 1, "label": "Rot"},
    }


def test_camera_ratings_fall_back_to_the_raw_file_and_its_sidecar(session_dir, review):
    make_raw(session_dir / "L1000001.DNG", stars=1, label="Gelb")
    make_jpg(session_dir / "L1000001.JPG")
    make_raw(session_dir / "DSCF0001.RAF")
    make_sidecar(session_dir / "DSCF0001.xmp", label="Yellow")
    make_jpg(session_dir / "DSCF0001.JPG")

    assert camera_ratings(review()) == {
        "DSCF0001.JPG": {"stars": None, "label": "Yellow"},
        "L1000001.JPG": {"stars": 1, "label": "Gelb"},
    }
