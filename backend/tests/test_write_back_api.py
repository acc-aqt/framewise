import json
import plistlib
import shutil
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from conftest import make_jpg, make_raw, make_sidecar, wait_until
from PIL import Image
from test_review_api import camera_ratings
from test_verdicts_api import keep_every_clean_frame

EXIFTOOL = shutil.which("exiftool") or "/opt/homebrew/bin/exiftool"
START = datetime(2026, 6, 20, 14, 30, 0)
BEACH = [1.0, 0.0, 0.0]
BLURRY = {"sharpness": 0.1}
SOFT = {"sharpness": 0.3}


def exiftool(*args: str | Path) -> str:
    return subprocess.run(
        [EXIFTOOL, *map(str, args)], check=True, capture_output=True, text=True
    ).stdout


def read_back(path: Path, *tags: str) -> dict:
    """Reads tags back from a file with exiftool, by their group-qualified names."""
    output = exiftool("-j", "-n", "-G1", *(f"-{tag}" for tag in tags), path)
    values = json.loads(output)[0]
    del values["SourceFile"]
    return values


def rating(path: Path) -> dict:
    values = read_back(path, "XMP-xmp:Rating", "XMP-xmp:Label")
    return {"stars": values.get("XMP-xmp:Rating"), "label": values.get("XMP-xmp:Label")}


def image_data_hash(path: Path) -> str:
    return read_back(path, "ImageDataHash")["File:ImageDataHash"]


def make_dng(path: Path, stars: int | None = None, label: str | None = None) -> Path:
    """A minimal DNG: a small TIFF that exiftool tags with a DNG version."""
    Image.new("RGB", (32, 24), (90, 140, 200)).save(path, "TIFF")
    tags = ["-DNGVersion=1.4.0.0", "-IFD0:Make=Leica Camera AG", "-IFD0:Model=LEICA Q3"]
    if stars is not None:
        tags.append(f"-XMP-xmp:Rating={stars}")
    if label is not None:
        tags.append(f"-XMP-xmp:Label={label}")
    exiftool("-overwrite_original", *tags, path)
    return path


def lightroom_preferences(folder: Path, red: str, yellow: str) -> Path:
    path = folder / "com.adobe.LightroomClassicCC7.plist"
    labels = {
        "label1": red,
        "label2": yellow,
        "label3": "Grün",
        "label4": "Blau",
        "label5": "Lila",
    }
    path.write_bytes(plistlib.dumps(labels, fmt=plistlib.FMT_BINARY))
    return path


def jpg(
    session_dir, analyzer, name: str, second: float = 0, stars: int | None = None, **signals
) -> Path:
    path = make_jpg(session_dir / name, stars=stars, captured_at=START + timedelta(seconds=second))
    analyzer.script(path, BEACH, **signals)
    return path


def files_by_path(dry_run: dict) -> dict[str, dict]:
    return {file["path"]: file for file in dry_run["files"]}


@pytest.fixture
def english(tmp_path: Path) -> dict:
    return {"lightroom_preferences": lightroom_preferences(tmp_path, "Red", "Yellow")}


def test_the_dry_run_lists_every_file_with_its_old_and_new_rating_and_writes_nothing(
    session_dir, review, analyzer, english
):
    winner = jpg(session_dir, analyzer, "DSCF0001.JPG", stars=1, aesthetics=0.5)
    raf = make_raw(session_dir / "DSCF0002.RAF")
    reject = jpg(session_dir, analyzer, "DSCF0002.JPG", 0.3, **BLURRY)
    before = {path: path.read_bytes() for path in (winner, raf, reject)}

    dry_run = review(**english).get("/api/write-back").json()

    assert files_by_path(dry_run) == {
        "DSCF0001.JPG": {
            "frame_id": 1,
            "path": "DSCF0001.JPG",
            "written_to": "DSCF0001.JPG",
            "verdict": "winner",
            "old": {"stars": 1, "label": None},
            "new": {"stars": 3, "label": None},
        },
        "DSCF0002.JPG": {
            "frame_id": 2,
            "path": "DSCF0002.JPG",
            "written_to": "DSCF0002.JPG",
            "verdict": "reject",
            "old": {"stars": None, "label": None},
            "new": {"stars": 0, "label": "Red"},
        },
        "DSCF0002.RAF": {
            "frame_id": 2,
            "path": "DSCF0002.RAF",
            "written_to": "DSCF0002.xmp",
            "verdict": "reject",
            "old": {"stars": None, "label": None},
            "new": {"stars": 0, "label": "Red"},
        },
    }
    assert {path: path.read_bytes() for path in before} == before
    assert not (session_dir / "DSCF0002.xmp").exists()
    assert dry_run["can_undo"] is False


def test_each_verdict_is_written_as_its_stars_and_color_label(
    session_dir, review, analyzer, english
):
    winner = jpg(session_dir, analyzer, "DSCF0001.JPG", aesthetics=0.5)
    keeper = jpg(session_dir, analyzer, "DSCF0002.JPG", 0.3)
    reject = jpg(session_dir, analyzer, "DSCF0003.JPG", 0.6, **BLURRY)
    unsure = jpg(session_dir, analyzer, "DSCF0004.JPG", 0.9, **SOFT)

    result = review(**english).post("/api/write-back").json()

    assert result["failed"] == []
    assert rating(winner) == {"stars": 3, "label": None}
    assert rating(keeper) == {"stars": 2, "label": None}
    assert rating(reject) == {"stars": 0, "label": "Red"}
    assert rating(unsure) == {"stars": 0, "label": "Yellow"}


def test_a_dng_gets_embedded_xmp_and_keeps_its_metadata_and_image_data(
    session_dir, review, analyzer, english
):
    dng = make_dng(session_dir / "L1000001.DNG", stars=1)
    jpg(session_dir, analyzer, "L1000001.JPG")
    image_before = image_data_hash(dng)

    review(**english).post("/api/write-back")

    assert rating(dng) == {"stars": 3, "label": None}
    assert read_back(dng, "DNGVersion", "IFD0:Make", "IFD0:Model") == {
        "IFD0:DNGVersion": "1 4 0 0",
        "IFD0:Make": "Leica Camera AG",
        "IFD0:Model": "LEICA Q3",
    }
    assert image_data_hash(dng) == image_before
    assert not (session_dir / "L1000001.xmp").exists()


def test_without_a_sidecar_the_dry_run_shows_the_rating_in_the_raw_itself(
    session_dir, review, analyzer, english
):
    # A TIFF-based RAW, as ARW and NEF files are, carrying an in-camera rating.
    arw = make_dng(session_dir / "DSC00001.ARW", stars=1)
    jpg(session_dir, analyzer, "DSC00001.JPG")

    dry_run = files_by_path(review(**english).get("/api/write-back").json())

    assert dry_run["DSC00001.ARW"]["old"] == {"stars": 1, "label": None}
    assert dry_run["DSC00001.ARW"]["written_to"] == "DSC00001.xmp"
    assert rating(arw) == {"stars": 1, "label": None}


@pytest.mark.parametrize(
    "raw_name", ["DSCF0001.RAF", "DSC00001.ARW", "DSC_0001.NEF", "IMG_0001.CR3"]
)
def test_other_raws_get_a_sidecar_and_their_jpg_gets_embedded_xmp(
    session_dir, review, analyzer, english, raw_name
):
    raw = make_raw(session_dir / raw_name)
    raw_before = raw.read_bytes()
    jpg_path = jpg(session_dir, analyzer, f"{raw.stem}.JPG")

    review(**english).post("/api/write-back")

    assert rating(raw.with_suffix(".xmp")) == {"stars": 3, "label": None}
    assert rating(jpg_path) == {"stars": 3, "label": None}
    assert raw.read_bytes() == raw_before


def test_an_existing_sidecar_is_merged_and_keeps_its_develop_settings(
    session_dir, review, analyzer, english
):
    make_raw(session_dir / "DSCF0001.RAF")
    jpg(session_dir, analyzer, "DSCF0001.JPG", **BLURRY)
    jpg(session_dir, analyzer, "DSCF0002.JPG", 0.3, aesthetics=0.5)
    sidecar = make_sidecar(session_dir / "DSCF0001.xmp", stars=1)
    exiftool(
        "-overwrite_original",
        "-XMP-crs:Exposure2012=+0.35",
        "-XMP-crs:CropTop=0.1",
        "-XMP-dc:Title=Beach",
        sidecar,
    )

    review(**english).post("/api/write-back")

    assert rating(sidecar) == {"stars": 0, "label": "Red"}
    assert read_back(sidecar, "XMP-crs:Exposure2012", "XMP-crs:CropTop", "XMP-dc:Title") == {
        "XMP-crs:Exposure2012": "+0.35",
        "XMP-crs:CropTop": 0.1,
        "XMP-dc:Title": "Beach",
    }


def test_a_jpg_keeps_its_other_metadata_and_image_data(session_dir, review, analyzer, english):
    path = jpg(session_dir, analyzer, "DSCF0001.JPG")
    exiftool(
        "-overwrite_original",
        "-IFD0:Make=FUJIFILM",
        "-ExifIFD:ExposureTime=1/250",
        "-XMP-dc:Title=Beach",
        "-XMP-xmp:Rating=1",
        path,
    )
    image_before = image_data_hash(path)

    review(**english).post("/api/write-back")

    assert rating(path) == {"stars": 3, "label": None}
    assert read_back(path, "IFD0:Make", "ExifIFD:ExposureTime", "XMP-dc:Title") == {
        "IFD0:Make": "FUJIFILM",
        "ExifIFD:ExposureTime": 0.004,
        "XMP-dc:Title": "Beach",
    }
    assert image_data_hash(path) == image_before


def test_label_names_come_from_the_active_lightroom_color_label_set(
    session_dir, review, analyzer, tmp_path
):
    jpg(session_dir, analyzer, "DSCF0001.JPG", aesthetics=0.5)
    reject = jpg(session_dir, analyzer, "DSCF0002.JPG", 0.3, **BLURRY)
    unsure = jpg(session_dir, analyzer, "DSCF0003.JPG", 0.6, **SOFT)
    client = review(lightroom_preferences=lightroom_preferences(tmp_path, "Rot", "Gelb"))

    dry_run = client.get("/api/write-back").json()
    client.post("/api/write-back")

    assert dry_run["label_set"] == {
        "red": "Rot",
        "yellow": "Gelb",
        "green": "Grün",
        "blue": "Blau",
        "purple": "Lila",
        "from_lightroom": True,
    }
    assert dry_run["notice"] is None
    assert rating(reject)["label"] == "Rot"
    assert rating(unsure)["label"] == "Gelb"


def test_without_a_lightroom_label_set_the_english_defaults_are_used_and_the_dry_run_says_so(
    session_dir, review, analyzer, tmp_path
):
    reject = jpg(session_dir, analyzer, "DSCF0002.JPG", 0.3, **BLURRY)
    jpg(session_dir, analyzer, "DSCF0001.JPG", aesthetics=0.5)
    client = review(lightroom_preferences=tmp_path / "missing.plist")

    dry_run = client.get("/api/write-back").json()
    client.post("/api/write-back")

    assert dry_run["label_set"]["red"] == "Red"
    assert dry_run["label_set"]["yellow"] == "Yellow"
    assert dry_run["label_set"]["from_lightroom"] is False
    assert "English defaults" in dry_run["notice"]
    assert rating(reject)["label"] == "Red"


def test_undo_restores_old_values_and_removes_sidecars_framewise_created(
    session_dir, review, analyzer, english
):
    dng = make_dng(session_dir / "L1000001.DNG", stars=1, label="Blue")
    dng_jpg = jpg(session_dir, analyzer, "L1000001.JPG", stars=1, aesthetics=0.5)
    new_sidecar_raf = make_raw(session_dir / "DSCF0002.RAF")
    jpg(session_dir, analyzer, "DSCF0002.JPG", 0.3, **BLURRY)
    make_raw(session_dir / "DSCF0003.RAF")
    jpg(session_dir, analyzer, "DSCF0003.JPG", 0.6, **SOFT)
    existing_sidecar = make_sidecar(session_dir / "DSCF0003.xmp", stars=1, label="Green")
    client = review(**english)

    client.post("/api/write-back")
    assert client.get("/api/write-back").json()["can_undo"] is True
    result = client.post("/api/write-back/undo").json()

    assert result["failed"] == []
    assert rating(dng) == {"stars": 1, "label": "Blue"}
    assert rating(dng_jpg) == {"stars": 1, "label": None}
    assert rating(session_dir / "DSCF0002.JPG") == {"stars": None, "label": None}
    assert not new_sidecar_raf.with_suffix(".xmp").exists()
    assert rating(existing_sidecar) == {"stars": 1, "label": "Green"}
    assert client.get("/api/write-back").json()["can_undo"] is False


def test_re_applying_after_the_verdicts_change_writes_the_final_state_and_undo_restores_the_first(
    session_dir, review, analyzer, english
):
    first = jpg(session_dir, analyzer, "DSCF0001.JPG", stars=1, aesthetics=0.5)
    review(**english).post("/api/write-back")
    assert rating(first) == {"stars": 3, "label": None}

    better = jpg(session_dir, analyzer, "DSCF0002.JPG", 0.3, aesthetics=1.0, sharpness=1.0)
    client = review(**english)
    assert client.post("/api/write-back").json()["failed"] == []

    assert rating(first) == {"stars": 0, "label": "Red"}
    assert rating(better) == {"stars": 3, "label": None}

    client.post("/api/write-back/undo")

    assert rating(first) == {"stars": 1, "label": None}
    assert rating(better) == {"stars": None, "label": None}


def test_a_file_that_cannot_be_written_is_reported_and_the_rest_still_complete(
    session_dir, review, analyzer, english
):
    good = make_jpg(session_dir / "DSCF0001.JPG")
    locked = make_jpg(session_dir / "DSCF0003.JPG")
    locked.chmod(0o444)
    make_raw(session_dir / "L1000002.DNG")
    unbroken_jpg = make_jpg(session_dir / "L1000002.JPG")

    result = review(**english).post("/api/write-back").json()

    assert [failure["path"] for failure in result["failed"]] == ["DSCF0003.JPG", "L1000002.DNG"]
    assert all(failure["error"] for failure in result["failed"])
    assert result["written"] == ["DSCF0001.JPG", "L1000002.JPG"]
    assert rating(good) == {"stars": 3, "label": None}
    assert rating(unbroken_jpg) == {"stars": 3, "label": None}
    assert rating(locked) == {"stars": None, "label": None}


def test_write_back_waits_until_analysis_has_finished(session_dir, live_review, analyzer, english):
    analyzer.hold(make_jpg(session_dir / "DSCF0001.JPG"))
    client = live_review(**english)

    response = client.post("/api/write-back")

    assert response.status_code == 409
    analyzer.release_all()
    wait_until(lambda: client.get("/api/progress").json()["frames_left"] == 0)
    assert client.post("/api/write-back").status_code == 200


def test_frames_are_not_analysed_again_after_write_back(session_dir, review, analyzer, english):
    jpg(session_dir, analyzer, "DSCF0001.JPG")
    review(**english).post("/api/write-back")
    analyzer.analyzed.clear()

    review(**english)

    assert analyzer.analyzed == []


def test_the_camera_rating_is_kept_after_write_back_and_a_re_run(
    session_dir, review, analyzer, english
):
    jpg(session_dir, analyzer, "DSCF0001.JPG", stars=1, aesthetics=0.5)
    make_raw(session_dir / "DSCF0002.RAF")
    jpg(session_dir, analyzer, "DSCF0002.JPG", 0.3, **BLURRY)
    review(**english).post("/api/write-back")

    assert camera_ratings(review(**english)) == {
        "DSCF0001.JPG": {"stars": 1, "label": None},
        "DSCF0002.JPG": {"stars": None, "label": None},
    }


def test_after_undo_and_a_re_run_the_camera_rating_is_read_from_the_files_again(
    session_dir, review, analyzer, english
):
    winner = jpg(session_dir, analyzer, "DSCF0001.JPG", stars=1, aesthetics=0.5)
    client = review(**english)
    client.post("/api/write-back")
    client.post("/api/write-back/undo")
    exiftool("-overwrite_original", "-XMP-xmp:Rating=2", winner)

    assert camera_ratings(review(**english)) == {"DSCF0001.JPG": {"stars": 2, "label": None}}


def override(client, name: str, **change) -> None:
    frames = client.get("/api/frames").json()
    frame_id = next(frame["id"] for frame in frames if frame["jpg_path"] == name)
    assert client.patch(f"/api/frames/{frame_id}/override", json=change).status_code == 200


def test_the_final_verdict_with_overrides_is_written(session_dir, review, analyzer, english):
    framewise_winner = jpg(session_dir, analyzer, "DSCF0001.JPG", aesthetics=0.5)
    chosen_winner = jpg(session_dir, analyzer, "DSCF0002.JPG", 0.3)
    client = keep_every_clean_frame(review(**english))

    override(client, "DSCF0002.JPG", verdict="winner")
    client.post("/api/write-back")

    assert rating(chosen_winner) == {"stars": 3, "label": None}
    assert rating(framewise_winner) == {"stars": 2, "label": None}


def test_override_stars_and_label_beat_the_verdict_mapping(session_dir, review, analyzer, tmp_path):
    winner = jpg(session_dir, analyzer, "DSCF0001.JPG", aesthetics=0.5)
    reject = jpg(session_dir, analyzer, "DSCF0002.JPG", 0.3, **BLURRY)
    client = review(lightroom_preferences=lightroom_preferences(tmp_path, "Rot", "Gelb"))

    override(client, "DSCF0001.JPG", stars=5)
    override(client, "DSCF0002.JPG", label="green")
    dry_run = files_by_path(client.get("/api/write-back").json())
    client.post("/api/write-back")

    assert dry_run["DSCF0001.JPG"]["new"] == {"stars": 5, "label": None}
    assert dry_run["DSCF0002.JPG"]["new"] == {"stars": 0, "label": "Grün"}
    assert rating(winner) == {"stars": 5, "label": None}
    assert rating(reject) == {"stars": 0, "label": "Grün"}


def test_re_applying_after_more_overrides_writes_the_final_state(
    session_dir, review, analyzer, english
):
    first = jpg(session_dir, analyzer, "DSCF0001.JPG", stars=1, aesthetics=0.5)
    raw = make_raw(session_dir / "DSCF0002.RAF")
    second = jpg(session_dir, analyzer, "DSCF0002.JPG", 0.3)
    client = review(**english)
    client.post("/api/write-back")

    override(client, "DSCF0001.JPG", verdict="reject")
    override(client, "DSCF0002.JPG", verdict="winner", stars=4)
    assert client.post("/api/write-back").json()["failed"] == []

    assert rating(first) == {"stars": 0, "label": "Red"}
    assert rating(second) == {"stars": 4, "label": None}
    assert rating(raw.with_suffix(".xmp")) == {"stars": 4, "label": None}

    client.post("/api/write-back/undo")

    assert rating(first) == {"stars": 1, "label": None}
    assert rating(second) == {"stars": None, "label": None}
    assert not raw.with_suffix(".xmp").exists()


def test_resetting_the_session_restores_the_files_and_forgets_the_review(
    session_dir, review, analyzer, english
):
    first = jpg(session_dir, analyzer, "DSCF0001.JPG", stars=1, aesthetics=0.5)
    raw = make_raw(session_dir / "DSCF0002.RAF")
    second = jpg(session_dir, analyzer, "DSCF0002.JPG", 0.3)
    client = review(**english)
    override(client, "DSCF0002.JPG", verdict="winner", stars=4)
    assert client.post("/api/groups/split", json={"frame_ids": [2]}).status_code == 204
    client.patch("/api/session", json={"keeper_budget": 0.9})
    client.post("/api/write-back")

    result = client.post("/api/session/reset").json()

    assert result["failed"] == []
    assert rating(first) == {"stars": 1, "label": None}
    assert rating(second) == {"stars": None, "label": None}
    assert not raw.with_suffix(".xmp").exists()
    groups = client.get("/api/groups").json()
    assert [[frame["id"] for frame in group["frames"]] for group in groups] == [[1, 2]]
    assert all(frame["override"] is None for group in groups for frame in group["frames"])
    assert client.get("/api/session").json()["keeper_budget"] == 0.4
    assert client.get("/api/write-back").json()["can_undo"] is False


def test_resetting_a_session_without_write_back_forgets_the_review(
    session_dir, review, analyzer, english
):
    jpg(session_dir, analyzer, "DSCF0001.JPG")
    client = review(**english)
    override(client, "DSCF0001.JPG", verdict="reject")

    assert client.post("/api/session/reset").json() == {"written": [], "failed": []}
    assert client.get("/api/groups").json()[0]["frames"][0]["override"] is None


def test_a_file_that_fails_to_restore_on_reset_stays_undoable(
    session_dir, review, analyzer, english
):
    locked = jpg(session_dir, analyzer, "DSCF0001.JPG", stars=1)
    client = review(**english)
    client.post("/api/write-back")
    locked.chmod(0o444)

    result = client.post("/api/session/reset").json()

    assert [failure["path"] for failure in result["failed"]] == ["DSCF0001.JPG"]
    assert client.get("/api/write-back").json()["can_undo"] is True


def test_reset_waits_until_analysis_has_finished(session_dir, live_review, analyzer, english):
    analyzer.hold(make_jpg(session_dir / "DSCF0001.JPG"))

    assert live_review(**english).post("/api/session/reset").status_code == 409
