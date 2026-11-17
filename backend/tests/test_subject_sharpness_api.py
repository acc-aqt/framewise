import pytest
from test_face_checks_api import face
from test_verdicts_api import burst, frames_by_name, reasons

from framewise.analyzer import Subject


def at_focus_point(sharpness: float) -> Subject:
    return Subject(
        x=0.45, y=0.2, width=0.1, height=0.07, sharpness=sharpness, found_by="focus-point"
    )


def on_subject_mask(sharpness: float) -> Subject:
    return Subject(
        x=0.3, y=0.25, width=0.25, height=0.6, sharpness=sharpness, found_by="subject-mask"
    )


def test_a_frame_whose_subject_is_blurred_is_a_reject_however_sharp_the_rest(
    session_dir, review, analyzer
):
    burst(
        session_dir,
        analyzer,
        ("DSCF0001", {}),
        ("DSCF0002", {"sharpness": 1.0, "subject": on_subject_mask(0.15)}),
    )

    frame = frames_by_name(review())["DSCF0002.JPG"]

    assert frame["verdict"] == "reject"
    assert reasons(frame) == ["Blurry subject"]
    assert [reason["code"] for reason in frame["reasons"]] == ["blurry"]


def test_a_frame_whose_subject_is_slightly_soft_is_unsure(session_dir, review, analyzer):
    burst(
        session_dir,
        analyzer,
        ("DSCF0001", {}),
        ("DSCF0002", {"sharpness": 1.0, "subject": on_subject_mask(0.3)}),
    )

    frame = frames_by_name(review())["DSCF0002.JPG"]

    assert frame["verdict"] == "unsure"
    assert reasons(frame) == ["Slightly soft subject"]
    assert [reason["code"] for reason in frame["reasons"]] == ["soft"]


def test_a_frame_blurred_at_its_focus_point_is_a_reject_however_sharp_the_rest(
    session_dir, review, analyzer
):
    burst(
        session_dir,
        analyzer,
        ("DSCF0001", {}),
        ("DSCF0002", {"sharpness": 0.9, "subject": at_focus_point(0.1)}),
    )

    frame = frames_by_name(review())["DSCF0002.JPG"]

    assert frame["verdict"] == "reject"
    assert reasons(frame) == ["Blurry at focus point"]
    assert [reason["code"] for reason in frame["reasons"]] == ["blurry"]


def test_a_frame_slightly_soft_at_its_focus_point_is_unsure(session_dir, review, analyzer):
    burst(session_dir, analyzer, ("DSCF0001", {}), ("DSCF0002", {"subject": at_focus_point(0.4)}))

    frame = frames_by_name(review())["DSCF0002.JPG"]

    assert frame["verdict"] == "unsure"
    assert reasons(frame) == ["Slightly soft at focus point"]


def test_a_frame_sharp_at_its_focus_point_is_not_soft_however_blurred_the_rest(
    session_dir, review, analyzer
):
    burst(
        session_dir,
        analyzer,
        ("DSCF0001", {}),
        ("DSCF0002", {"sharpness": 0.2, "subject": at_focus_point(0.8)}),
    )

    frame = frames_by_name(review())["DSCF0002.JPG"]

    assert frame["verdict"] in {"winner", "keeper"}
    assert frame["reasons"] == []


def test_the_frame_sharp_at_its_focus_point_wins_over_one_sharp_elsewhere(
    session_dir, review, analyzer
):
    burst(
        session_dir,
        analyzer,
        ("DSCF0001", {"sharpness": 1.0, "subject": at_focus_point(0.55)}),
        ("DSCF0002", {"sharpness": 0.5, "subject": at_focus_point(0.9)}),
    )

    frames = frames_by_name(review())

    assert frames["DSCF0002.JPG"]["verdict"] == "winner"


def test_a_frame_with_faces_is_still_judged_on_its_faces(session_dir, review, analyzer):
    burst(
        session_dir,
        analyzer,
        ("DSCF0001", {}),
        ("DSCF0002", {"faces": [face()], "subject": at_focus_point(0.1)}),
    )

    frame = frames_by_name(review())["DSCF0002.JPG"]

    assert frame["verdict"] in {"winner", "keeper"}
    assert frame["reasons"] == []
    assert frame["sharpness_measured_on"] == "faces"


@pytest.mark.parametrize(
    ("signals", "measured_on", "sharpness_score"),
    [
        ({"sharpness": 0.9, "subject": at_focus_point(0.5)}, "focus-point", 0.746),
        ({"sharpness": 0.9, "subject": on_subject_mask(0.5)}, "subject-mask", 0.746),
        ({"sharpness": 0.9}, "frame", 0.9),
    ],
)
def test_each_frame_says_what_its_sharpness_was_measured_on(
    session_dir, review, analyzer, signals, measured_on, sharpness_score
):
    burst(session_dir, analyzer, ("DSCF0001", signals))

    [frame] = frames_by_name(review()).values()

    assert frame["sharpness_measured_on"] == measured_on
    assert frame["scores"]["sharpness"] == sharpness_score
