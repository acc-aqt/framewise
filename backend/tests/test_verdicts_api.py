import sqlite3
from datetime import datetime, timedelta

from conftest import make_jpg, make_raw, wait_until

from framewise.review import session_database_path

START = datetime(2026, 6, 20, 14, 30, 0)
BEACH = [1.0, 0.0, 0.0]
MOUNTAIN = [0.0, 1.0, 0.0]


def seconds(count: float) -> datetime:
    return START + timedelta(seconds=count)


def frames_by_name(client) -> dict[str, dict]:
    return {
        frame["jpg_path"]: frame
        for group in client.get("/api/groups").json()
        for frame in group["frames"]
    }


def verdicts(client) -> dict[str, str]:
    return {name: frame["verdict"] for name, frame in frames_by_name(client).items()}


def reasons(frame: dict) -> list[str]:
    return [reason["text"] for reason in frame["reasons"]]


def burst(session_dir, analyzer, *frames: tuple[str, dict], raw: bool = False) -> None:
    """Scripts Frames captured a fraction of a second apart that look alike, so they form one
    Group."""
    for index, (name, signals) in enumerate(frames):
        if raw:
            make_raw(session_dir / f"{name}.RAF")
        jpg = make_jpg(session_dir / f"{name}.JPG", captured_at=seconds(index * 0.3))
        analyzer.script(jpg, BEACH, **signals)


def test_every_group_has_exactly_one_winner(session_dir, review, analyzer):
    burst(
        session_dir,
        analyzer,
        ("DSCF0001", {"aesthetics": 0.1}),
        ("DSCF0002", {"aesthetics": 0.4}),
        ("DSCF0003", {"aesthetics": 0.3}),
    )
    analyzer.script(make_jpg(session_dir / "DSCF0009.JPG", captured_at=seconds(60)), MOUNTAIN)

    groups = review().get("/api/groups").json()

    winners = [
        [frame["jpg_path"] for frame in group["frames"] if frame["verdict"] == "winner"]
        for group in groups
    ]
    assert winners == [["DSCF0002.JPG"], ["DSCF0009.JPG"]]


def test_a_clean_winner_and_keepers_have_no_reasons(session_dir, review, analyzer):
    burst(session_dir, analyzer, ("DSCF0001", {"aesthetics": 0.4}), ("DSCF0002", {}))

    frames = frames_by_name(review())

    assert [(frame["verdict"], frame["reasons"]) for frame in frames.values()] == [
        ("winner", []),
        ("keeper", []),
    ]


def test_a_blurry_frame_becomes_a_reject(session_dir, review, analyzer):
    burst(session_dir, analyzer, ("DSCF0001", {}), ("DSCF0002", {"sharpness": 0.1}))

    blurry = frames_by_name(review())["DSCF0002.JPG"]

    assert blurry["verdict"] == "reject"
    assert reasons(blurry) == ["Blurry"]


def test_a_frame_with_motion_blur_becomes_a_reject(session_dir, review, analyzer):
    burst(session_dir, analyzer, ("DSCF0001", {}), ("DSCF0002", {"motion_blur": 0.7}))

    shaken = frames_by_name(review())["DSCF0002.JPG"]

    assert shaken["verdict"] == "reject"
    assert reasons(shaken) == ["Motion blur"]


def test_a_slightly_soft_frame_is_unsure(session_dir, review, analyzer):
    burst(session_dir, analyzer, ("DSCF0001", {}), ("DSCF0002", {"sharpness": 0.4}))

    soft = frames_by_name(review())["DSCF0002.JPG"]

    assert soft["verdict"] == "unsure"
    assert reasons(soft) == ["Slightly soft"]


def test_the_sharp_frame_of_a_burst_wins_over_a_blurry_one_with_better_aesthetics(
    session_dir, review, analyzer
):
    burst(
        session_dir,
        analyzer,
        ("DSCF0001", {"sharpness": 0.1, "aesthetics": 0.9}),
        ("DSCF0002", {"aesthetics": -0.2}),
    )

    assert verdicts(review()) == {"DSCF0001.JPG": "reject", "DSCF0002.JPG": "winner"}


def test_a_much_weaker_duplicate_becomes_a_reject_naming_the_winner(session_dir, review, analyzer):
    burst(
        session_dir, analyzer, ("DSCF0412", {"aesthetics": 0.8}), ("DSCF0413", {"aesthetics": -0.6})
    )

    weaker = frames_by_name(review())["DSCF0413.JPG"]

    assert weaker["verdict"] == "reject"
    assert reasons(weaker) == ["Weaker duplicate of DSCF0412"]


def test_a_jpg_only_frame_1_5_stops_under_is_a_reject(session_dir, review, analyzer):
    burst(session_dir, analyzer, ("DSCF0001", {}), ("DSCF0002", {"exposure_stops": -1.5}))

    dark = frames_by_name(review())["DSCF0002.JPG"]

    assert dark["verdict"] == "reject"
    assert reasons(dark) == ["Underexposed 1.5 stops"]


def test_a_raw_jpg_frame_1_5_stops_under_is_unsure(session_dir, review, analyzer):
    burst(session_dir, analyzer, ("DSCF0001", {}), ("DSCF0002", {"exposure_stops": -1.5}), raw=True)

    dark = frames_by_name(review())["DSCF0002.JPG"]

    assert dark["verdict"] == "unsure"
    assert reasons(dark) == ["Underexposed 1.5 stops"]


def test_a_raw_jpg_frame_more_than_2_stops_off_is_a_reject(session_dir, review, analyzer):
    burst(session_dir, analyzer, ("DSCF0001", {}), ("DSCF0002", {"exposure_stops": 2.5}), raw=True)

    bright = frames_by_name(review())["DSCF0002.JPG"]

    assert bright["verdict"] == "reject"
    assert reasons(bright) == ["Overexposed 2.5 stops"]


def test_a_frame_slightly_off_is_unsure_even_when_jpg_only(session_dir, review, analyzer):
    burst(session_dir, analyzer, ("DSCF0001", {}), ("DSCF0002", {"exposure_stops": -1.0}))

    dark = frames_by_name(review())["DSCF0002.JPG"]

    assert dark["verdict"] == "unsure"
    assert reasons(dark) == ["Underexposed 1 stop"]


def test_low_key_and_high_key_frames_are_not_penalised(session_dir, review, analyzer):
    burst(
        session_dir,
        analyzer,
        ("DSCF0001", {}),
        ("DSCF0002", {"exposure_stops": -2.5, "low_key": True}),
        ("DSCF0003", {"exposure_stops": 2.5, "high_key": True}),
    )

    frames = frames_by_name(review())

    for name in ("DSCF0002.JPG", "DSCF0003.JPG"):
        assert frames[name]["verdict"] == "keeper"
        assert frames[name]["reasons"] == []
        assert frames[name]["scores"]["exposure"] == frames["DSCF0001.JPG"]["scores"]["exposure"]


def test_a_flawed_frame_alone_in_its_group_is_its_winner_with_reasons(
    session_dir, review, analyzer
):
    analyzer.script(make_jpg(session_dir / "DSCF0001.JPG"), sharpness=0.1)

    [frame] = frames_by_name(review()).values()

    assert frame["verdict"] == "winner"
    assert reasons(frame) == ["Blurry"]


def test_each_frame_carries_its_score_breakdown_and_signals(session_dir, review, analyzer):
    analyzer.script(
        make_jpg(session_dir / "DSCF0001.JPG"),
        sharpness=0.9,
        motion_blur=0.1,
        exposure_stops=-0.3,
        aesthetics=0.5,
    )

    [frame] = frames_by_name(review()).values()

    assert set(frame["scores"]) == {
        "sharpness",
        "steadiness",
        "exposure",
        "aesthetics",
        "face_quality",
        "total",
    }
    assert frame["scores"]["face_quality"] is None
    assert all(0 <= value <= 1 for value in frame["scores"].values() if value is not None)
    assert frame["scores"]["aesthetics"] == 0.75
    assert frame["signals"] == {
        "sharpness": 0.9,
        "motion_blur": 0.1,
        "exposure_stops": -0.3,
        "low_key": False,
        "high_key": False,
        "aesthetics": 0.5,
        "faces": [],
    }


def test_frames_are_judged_without_an_aesthetics_score_when_it_is_unavailable(
    session_dir, review, analyzer
):
    burst(
        session_dir,
        analyzer,
        ("DSCF0001", {"aesthetics": None}),
        ("DSCF0002", {"aesthetics": None, "sharpness": 0.1}),
    )

    frames = frames_by_name(review())

    assert frames["DSCF0001.JPG"]["verdict"] == "winner"
    assert frames["DSCF0001.JPG"]["scores"]["aesthetics"] is None
    assert frames["DSCF0002.JPG"]["verdict"] == "reject"


def test_reasons_carry_a_code_to_filter_by(session_dir, review, analyzer):
    burst(session_dir, analyzer, ("DSCF0001", {}), ("DSCF0002", {"exposure_stops": -1.5}))

    dark = frames_by_name(review())["DSCF0002.JPG"]

    assert dark["reasons"] == [
        {"code": "underexposed", "label": "Underexposed", "text": "Underexposed 1.5 stops"}
    ]


def test_verdicts_are_recomputed_as_more_frames_are_analysed(session_dir, live_review, analyzer):
    burst(session_dir, analyzer, ("DSCF0001", {}), ("DSCF0002", {"aesthetics": 0.6}))
    analyzer.hold(session_dir / "DSCF0002.JPG")

    client = live_review()
    wait_until(lambda: client.get("/api/progress").json()["frames_done"] == 1)
    assert verdicts(client) == {"DSCF0001.JPG": "winner"}

    analyzer.release_all()
    wait_until(lambda: client.get("/api/progress").json()["frames_left"] == 0)
    assert verdicts(client) == {"DSCF0001.JPG": "keeper", "DSCF0002.JPG": "winner"}


def test_a_re_run_re_analyses_frames_analysed_before_the_current_signals_existed(
    session_dir, data_dir, review, analyzer
):
    jpg = make_jpg(session_dir / "DSCF0001.JPG")
    make_store_from_before_verdicts(session_dir, data_dir, jpg)

    client = review()

    assert [path.name for path in analyzer.analyzed] == ["DSCF0001.JPG"]
    assert verdicts(client) == {"DSCF0001.JPG": "winner"}


def make_store_from_before_verdicts(session_dir, data_dir, jpg) -> None:
    """Writes a Session store as framewise saved it before Frames had sharpness, exposure and
    aesthetics signals."""
    data_dir.mkdir(parents=True)
    database = sqlite3.connect(session_database_path(session_dir.resolve(), data_dir))
    stat = jpg.stat()
    with database:
        database.executescript(
            """
            CREATE TABLE analyses (
                jpg_path TEXT PRIMARY KEY,
                jpg_size INTEGER NOT NULL,
                jpg_mtime_ns INTEGER NOT NULL,
                fingerprint BLOB NOT NULL,
                captured_at TEXT
            );
            """
        )
        database.execute(
            "INSERT INTO analyses VALUES (?, ?, ?, ?, NULL)",
            (jpg.name, stat.st_size, stat.st_mtime_ns, b"\0\0\x80\x3f"),
        )
    database.close()
