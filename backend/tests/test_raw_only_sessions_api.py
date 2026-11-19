import io
import os

from conftest import make_jpg, make_raw, make_sidecar
from PIL import Image
from test_review_api import snapshot
from test_trash_api import trash_frames
from test_verdicts_api import BEACH, frames_by_name, reasons
from test_write_back_api import files_by_path, lightroom_preferences

from framewise.exiftool import ExifTool
from framewise.review import hard_reset_session, session_database_path
from framewise.store import preview_cache_dir


def test_a_session_of_only_raws_becomes_raw_only_frames(session_dir, review):
    make_raw(session_dir / "DSCF0001.RAF")
    make_raw(session_dir / "L1000002.DNG")

    client = review()
    summary = client.get("/api/session").json()
    frames = client.get("/api/frames").json()

    assert summary["total_frames"] == 2
    assert summary["raw_only_count"] == 2
    assert summary["jpg_only_count"] == 0
    assert summary["raw_jpg_count"] == 0
    assert summary["skipped"] == []
    assert [(frame["main_path"], frame["raw_path"], frame["kind"]) for frame in frames] == [
        ("DSCF0001.RAF", "DSCF0001.RAF", "raw-only"),
        ("L1000002.DNG", "L1000002.DNG", "raw-only"),
    ]


def test_a_mixed_folder_pairs_raws_with_jpgs_and_keeps_lone_raws_as_raw_only_frames(
    session_dir, review
):
    make_raw(session_dir / "L1000001.DNG")
    make_jpg(session_dir / "L1000001.JPG")
    make_raw(session_dir / "L1000001-Pano.dng")
    make_jpg(session_dir / "L1000002.JPG")
    make_raw(session_dir / "day2" / "DSCF0003.RAF")
    make_jpg(session_dir / "day2" / "evening" / "DSCF0003.JPG")

    client = review()
    summary = client.get("/api/session").json()
    frames = client.get("/api/frames").json()

    assert (summary["raw_jpg_count"], summary["jpg_only_count"], summary["raw_only_count"]) == (
        1,
        2,
        2,
    )
    assert [(frame["main_path"], frame["kind"]) for frame in frames] == [
        ("L1000001-Pano.dng", "raw-only"),
        ("L1000001.JPG", "raw+jpg"),
        ("L1000002.JPG", "jpg-only"),
        ("day2/DSCF0003.RAF", "raw-only"),
        ("day2/evening/DSCF0003.JPG", "jpg-only"),
    ]


def test_raws_sharing_a_base_name_without_a_jpg_each_become_a_raw_only_frame(session_dir, review):
    make_raw(session_dir / "DSCF0001.RAF")
    make_raw(session_dir / "DSCF0001.DNG")

    frames = review().get("/api/frames").json()

    assert [frame["main_path"] for frame in frames] == ["DSCF0001.DNG", "DSCF0001.RAF"]


def test_a_raw_without_a_usable_preview_is_skipped_with_the_reason(session_dir, review, previews):
    make_raw(session_dir / "DSCF0001.RAF")
    previews.without_preview(make_raw(session_dir / "DSCF0002.RAF"))

    client = review()
    summary = client.get("/api/session").json()

    assert summary["total_frames"] == 1
    assert summary["skipped"] == [
        {"path": "DSCF0002.RAF", "reason": "The RAW holds no embedded preview"}
    ]
    assert [frame["main_path"] for frame in client.get("/api/frames").json()] == ["DSCF0001.RAF"]


def test_a_raw_only_frame_is_grouped_judged_and_shown_from_its_preview(
    session_dir, review, analyzer, previews
):
    previews.size = (2400, 1600)
    analyzer.script(make_raw(session_dir / "DSCF0001.RAF"), BEACH, aesthetics=0.75)
    analyzer.script(make_raw(session_dir / "DSCF0002.RAF"), BEACH, sharpness=0.1)

    client = review()
    frames = frames_by_name(client)

    assert [frames[name]["verdict"] for name in ("DSCF0001.RAF", "DSCF0002.RAF")] == [
        "winner",
        "reject",
    ]
    assert len(client.get("/api/groups").json()) == 1
    thumbnail = client.get(frames["DSCF0001.RAF"]["thumbnail_url"])
    assert Image.open(io.BytesIO(thumbnail.content)).size == (480, 320)
    image = client.get(frames["DSCF0001.RAF"]["image_url"])
    assert image.headers["content-type"] == "image/jpeg"
    assert Image.open(io.BytesIO(image.content)).size == (2400, 1600)


def test_a_raw_only_frame_gets_the_exposure_leniency_of_a_raw_jpg_frame(
    session_dir, review, analyzer
):
    analyzer.script(make_raw(session_dir / "DSCF0001.RAF"), BEACH)
    analyzer.script(make_raw(session_dir / "DSCF0002.RAF"), BEACH, exposure_stops=-1.5)

    dark = frames_by_name(review())["DSCF0002.RAF"]

    assert dark["verdict"] == "unsure"
    assert reasons(dark) == ["Underexposed 1.5 stops"]


def test_a_raw_only_frame_takes_its_camera_rating_from_its_raw_and_sidecar(session_dir, review):
    make_raw(session_dir / "L1000001.DNG", stars=1)
    make_raw(session_dir / "DSCF0002.RAF")
    make_sidecar(session_dir / "DSCF0002.xmp", label="Blue")

    frames = review().get("/api/frames").json()

    assert [frame["camera_rating"] for frame in frames] == [
        {"stars": None, "label": "Blue"},
        {"stars": 1, "label": None},
    ]


def test_nothing_is_written_into_a_session_folder_of_raws(session_dir, review):
    make_raw(session_dir / "DSCF0001.RAF")
    make_raw(session_dir / "sub" / "L1000002.DNG")
    before = snapshot(session_dir)

    client = review()
    for frame in client.get("/api/frames").json():
        client.get(frame["thumbnail_url"])
        client.get(frame["image_url"])

    assert snapshot(session_dir) == before


def test_re_runs_reuse_the_cached_preview_and_analysis_while_the_raw_is_unchanged(
    session_dir, review, analyzer, previews
):
    make_raw(session_dir / "DSCF0001.RAF")
    changed = make_raw(session_dir / "DSCF0002.RAF")
    review()

    changed.write_bytes(changed.read_bytes() + b"\0")
    previews.extracted.clear()
    analyzer.analyzed.clear()
    review()

    assert previews.extracted == [changed]
    assert analyzer.analyzed == [changed]


def test_a_vanished_raw_takes_its_cached_preview_with_it(session_dir, data_dir, review):
    raw = make_raw(session_dir / "DSCF0001.RAF")
    make_raw(session_dir / "DSCF0002.RAF")
    review()
    cache = preview_cache_dir(session_database_path(session_dir.resolve(), data_dir))
    assert len(list(cache.iterdir())) == 2

    raw.unlink()
    review()

    assert len(list(cache.iterdir())) == 1


def test_hard_reset_deletes_the_preview_cache(session_dir, data_dir, review):
    make_raw(session_dir / "DSCF0001.RAF")
    review()
    cache = preview_cache_dir(session_database_path(session_dir.resolve(), data_dir))

    hard_reset_session(session_dir, data_dir, ExifTool())

    assert not cache.exists()


def test_rating_write_back_leaves_raw_only_frames_out_and_says_so(
    session_dir, review, analyzer, tmp_path
):
    english = {"lightroom_preferences": lightroom_preferences(tmp_path, "Red", "Yellow")}
    make_jpg(session_dir / "DSCF0001.JPG")
    raw = make_raw(session_dir / "DSCF0002.RAF")
    client = review(**english)

    dry_run = client.get("/api/write-back").json()
    client.post("/api/write-back")

    assert list(files_by_path(dry_run)) == ["DSCF0001.JPG"]
    assert dry_run["raw_only_notice"] == (
        "1 RAW-only Frame is left out: framewise can't write ratings into RAW-only Frames yet."
    )
    assert not raw.with_suffix(".xmp").exists()


def test_trashing_a_raw_only_frame_is_refused_and_moves_nothing(session_dir, review, trash):
    raw = make_raw(session_dir / "DSCF0001.RAF")
    client = review(move_to_trash=trash)

    response = trash_frames(client, "DSCF0001.RAF")

    assert response.json() == {
        "trashed": [],
        "failed": [{"path": "DSCF0001.RAF", "error": "framewise can't trash RAW-only Frames yet"}],
    }
    assert trash.trashed == []
    assert os.path.exists(raw)
    assert client.get("/api/session").json()["total_frames"] == 1
