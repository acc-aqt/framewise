from test_verdicts_api import burst, frames_by_name, keep_every_clean_frame, reasons, verdicts

from framewise.analyzer import Face


def face(
    eyes_open: bool | None = True,
    sharpness: float = 0.9,
    quality: float | None = 0.7,
    x: float = 0.4,
) -> Face:
    return Face(
        x=x,
        y=0.3,
        width=0.2,
        height=0.25,
        eyes_open=eyes_open,
        sharpness=sharpness,
        quality=quality,
    )


def test_closed_eyes_make_a_frame_unsure_when_no_open_eyes_frame_beats_it(
    session_dir, review, analyzer
):
    burst(
        session_dir,
        analyzer,
        ("DSCF0001", {"faces": [face(eyes_open=False)], "aesthetics": 0.5}),
        ("DSCF0002", {"faces": [face(eyes_open=False)]}),
    )

    frames = frames_by_name(review())

    assert frames["DSCF0002.JPG"]["verdict"] == "unsure"
    assert reasons(frames["DSCF0002.JPG"]) == ["Eyes closed"]
    assert reasons(frames["DSCF0001.JPG"]) == ["Eyes closed"]


def test_a_closed_eyes_frame_still_beats_a_blurry_one(session_dir, review, analyzer):
    burst(
        session_dir,
        analyzer,
        ("DSCF0001", {"faces": [face(eyes_open=False)]}),
        ("DSCF0002", {"sharpness": 0.1}),
    )

    frames = frames_by_name(review())

    assert frames["DSCF0001.JPG"]["verdict"] == "winner"
    assert reasons(frames["DSCF0001.JPG"]) == ["Eyes closed"]
    assert frames["DSCF0002.JPG"]["verdict"] == "reject"


def test_closed_eyes_become_a_reject_when_the_group_has_a_better_open_eyes_frame(
    session_dir, review, analyzer
):
    burst(
        session_dir,
        analyzer,
        ("DSCF0001", {"faces": [face(eyes_open=False)], "aesthetics": 0.6}),
        ("DSCF0002", {"faces": [face()]}),
    )

    frames = frames_by_name(review())

    assert frames["DSCF0002.JPG"]["verdict"] == "winner"
    assert frames["DSCF0001.JPG"]["verdict"] == "reject"
    assert reasons(frames["DSCF0001.JPG"]) == ["Eyes closed"]


def test_closed_eyes_stay_unsure_when_the_open_eyes_frame_is_itself_flawed(
    session_dir, review, analyzer
):
    burst(
        session_dir,
        analyzer,
        ("DSCF0001", {"faces": [face(eyes_open=False)], "aesthetics": -0.6}),
        ("DSCF0002", {"faces": [face()], "exposure_stops": -1.0, "aesthetics": 0.6}),
    )

    assert verdicts(review()) == {"DSCF0001.JPG": "unsure", "DSCF0002.JPG": "winner"}


def test_eyes_vision_could_not_read_do_not_count_as_closed(session_dir, review, analyzer):
    burst(session_dir, analyzer, ("DSCF0001", {"faces": [face(eyes_open=None)]}), ("DSCF0002", {}))

    frame = frames_by_name(keep_every_clean_frame(review()))["DSCF0001.JPG"]

    assert frame["reasons"] == []
    assert frame["faces"][0]["eyes"] == "unknown"


def test_in_a_group_shot_one_closed_pair_of_eyes_loses_to_a_frame_where_everyone_passes(
    session_dir, review, analyzer
):
    burst(
        session_dir,
        analyzer,
        (
            "DSCF0001",
            {"faces": [face(x=0.1), face(x=0.4, eyes_open=False), face(x=0.7)], "aesthetics": 0.9},
        ),
        ("DSCF0002", {"faces": [face(x=0.1), face(x=0.4), face(x=0.7)], "aesthetics": -0.5}),
    )

    frames = frames_by_name(review())

    assert frames["DSCF0002.JPG"]["verdict"] == "winner"
    assert frames["DSCF0001.JPG"]["verdict"] == "reject"
    assert reasons(frames["DSCF0001.JPG"]) == ["Eyes closed"]


def test_in_a_group_shot_one_soft_face_loses_to_a_frame_where_every_face_is_sharp(
    session_dir, review, analyzer
):
    burst(
        session_dir,
        analyzer,
        ("DSCF0001", {"faces": [face(x=0.1), face(x=0.6, sharpness=0.4)], "aesthetics": 0.9}),
        ("DSCF0002", {"faces": [face(x=0.1), face(x=0.6)], "aesthetics": -0.5}),
    )

    frames = frames_by_name(review())

    assert frames["DSCF0002.JPG"]["verdict"] == "winner"
    assert frames["DSCF0001.JPG"]["verdict"] == "unsure"
    assert reasons(frames["DSCF0001.JPG"]) == ["Soft face"]


def test_a_blurry_face_makes_a_frame_a_reject(session_dir, review, analyzer):
    burst(session_dir, analyzer, ("DSCF0001", {}), ("DSCF0002", {"faces": [face(sharpness=0.1)]}))

    blurry = frames_by_name(review())["DSCF0002.JPG"]

    assert blurry["verdict"] == "reject"
    assert reasons(blurry) == ["Blurry face"]


def test_a_sharp_background_with_a_soft_face_does_not_win_over_a_sharp_face(
    session_dir, review, analyzer
):
    burst(
        session_dir,
        analyzer,
        ("DSCF0001", {"sharpness": 0.95, "faces": [face(sharpness=0.55)], "aesthetics": 0.3}),
        ("DSCF0002", {"sharpness": 0.6, "faces": [face(sharpness=0.95)]}),
    )

    frames = frames_by_name(review())

    assert frames["DSCF0002.JPG"]["verdict"] == "winner"
    assert frames["DSCF0001.JPG"]["scores"]["sharpness"] < 1
    assert frames["DSCF0002.JPG"]["scores"]["sharpness"] == 1


def test_a_face_as_sharp_as_the_sharp_reference_face_scores_full_sharpness(
    session_dir, review, analyzer
):
    """Skin has few hard edges, so a sharp face measures only about 0.67."""
    burst(
        session_dir,
        analyzer,
        ("DSCF0001", {"faces": [face(sharpness=0.67)], "aesthetics": 0.5}),
        ("DSCF0002", {"faces": [face(sharpness=1.0)], "aesthetics": 0.3}),
    )

    frames = frames_by_name(review())

    assert frames["DSCF0001.JPG"]["scores"]["sharpness"] == 1
    assert frames["DSCF0001.JPG"]["verdict"] == "winner"


def test_a_sharp_face_against_a_soft_background_is_not_soft(session_dir, review, analyzer):
    burst(session_dir, analyzer, ("DSCF0001", {"sharpness": 0.2, "faces": [face()]}))

    [frame] = frames_by_name(review()).values()

    assert frame["reasons"] == []


def test_face_quality_decides_between_otherwise_equal_frames(session_dir, review, analyzer):
    burst(
        session_dir,
        analyzer,
        ("DSCF0001", {"faces": [face(quality=0.2)]}),
        ("DSCF0002", {"faces": [face(quality=0.8)]}),
    )

    frames = frames_by_name(review())

    assert frames["DSCF0002.JPG"]["verdict"] == "winner"
    assert frames["DSCF0002.JPG"]["scores"]["face_quality"] == 0.8
    assert frames["DSCF0001.JPG"]["scores"]["face_quality"] == 0.2


def test_a_frame_without_faces_has_no_face_quality_score(session_dir, review, analyzer):
    burst(session_dir, analyzer, ("DSCF0001", {}))

    [frame] = frames_by_name(review()).values()

    assert frame["scores"]["face_quality"] is None
    assert frame["faces"] == []


def test_each_face_carries_its_box_and_badges(session_dir, review, analyzer):
    burst(
        session_dir,
        analyzer,
        ("DSCF0001", {"faces": [face(x=0.1), face(x=0.6, eyes_open=False, sharpness=0.3)]}),
    )

    [frame] = frames_by_name(review()).values()

    assert frame["faces"] == [
        {
            "box": {"x": 0.1, "y": 0.3, "width": 0.2, "height": 0.25},
            "eyes": "open",
            "focus": "sharp",
        },
        {
            "box": {"x": 0.6, "y": 0.3, "width": 0.2, "height": 0.25},
            "eyes": "closed",
            "focus": "soft",
        },
    ]
