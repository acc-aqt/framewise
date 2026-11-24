from datetime import datetime, timedelta

import pytest

from framewise.analyzer import Face, FrameSignals
from framewise.camera_rating import CameraRating
from framewise.judge import Verdict, judge
from framewise.store import AnalyzedFrame, Frame

START = datetime(2026, 6, 20, 14, 30, 0)
STANDINGS = ["rank", "z-score"]


def portrait(
    frame_id: int,
    face_sharpness: float = 0.6,
    face_quality: float = 0.6,
    aesthetics: float = 0.5,
    motion_blur: float = 0.05,
) -> AnalyzedFrame:
    name = f"DSCF{frame_id:04d}.JPG"
    face = Face(0.4, 0.3, 0.2, 0.3, True, face_sharpness, face_quality, None)
    signals = FrameSignals(
        fingerprint=[1.0, 0.0],
        sharpness=0.9,
        motion_blur=motion_blur,
        exposure_stops=0.0,
        low_key=False,
        high_key=False,
        aesthetics=aesthetics,
        faces=[face],
    )
    frame = Frame(frame_id, name, name, None, CameraRating(None, None))
    return AnalyzedFrame(frame, signals, START + timedelta(seconds=frame_id))


def winner(group: list[AnalyzedFrame], **options) -> str:
    proposal = judge([group], keeper_budget=1.0, **options)
    [name] = [
        analyzed.frame.main_path
        for analyzed in group
        if proposal[analyzed.frame.id].verdict == Verdict.WINNER
    ]
    return name


def sharper_against_better_face() -> list[AnalyzedFrame]:
    """DSCF0001 is a little sharper; DSCF0002 has a much better face. On absolute Scores the
    face quality's large gap outweighs the small sharpness gap, but sharpness weighs more."""
    return [
        portrait(1, face_sharpness=0.60, face_quality=0.4),
        portrait(2, face_sharpness=0.55, face_quality=0.9),
    ]


def test_absolute_scores_pick_the_frame_with_the_larger_gap():
    assert winner(sharper_against_better_face()) == "DSCF0002.JPG"


@pytest.mark.parametrize("pick", STANDINGS)
def test_standings_pick_the_frame_that_stands_higher_on_the_heavier_components(pick):
    assert winner(sharper_against_better_face(), winner_pick=pick) == "DSCF0001.JPG"


def near_identical() -> list[AnalyzedFrame]:
    """DSCF0002 scores a hair higher on every component, within the standing tolerance."""
    return [
        portrait(1, face_sharpness=0.600, face_quality=0.600, aesthetics=0.500),
        portrait(2, face_sharpness=0.605, face_quality=0.605, aesthetics=0.505),
        portrait(3, face_sharpness=0.300, face_quality=0.300, aesthetics=0.300),
    ]


def test_absolute_scores_pick_the_frame_a_hair_higher():
    assert winner(near_identical()) == "DSCF0002.JPG"


@pytest.mark.parametrize("pick", STANDINGS)
def test_near_identical_frames_tie_on_standing_and_fall_through_to_the_tie_break(pick):
    assert winner(near_identical(), winner_pick=pick) == "DSCF0001.JPG"


@pytest.mark.parametrize("pick", STANDINGS)
def test_a_group_of_one_frame_has_it_as_winner(pick):
    assert winner([portrait(1)], winner_pick=pick) == "DSCF0001.JPG"


@pytest.mark.parametrize("pick", STANDINGS)
def test_a_winner_override_still_wins(pick):
    overrides = {"DSCF0002.JPG": Verdict.WINNER}

    assert winner(sharper_against_better_face(), verdict_overrides=overrides, winner_pick=pick) == (
        "DSCF0002.JPG"
    )


@pytest.mark.parametrize("pick", STANDINGS)
def test_a_frame_overridden_to_another_verdict_is_not_picked(pick):
    overrides = {"DSCF0001.JPG": Verdict.KEEPER}

    assert winner(sharper_against_better_face(), verdict_overrides=overrides, winner_pick=pick) == (
        "DSCF0002.JPG"
    )


@pytest.mark.parametrize("pick", STANDINGS)
def test_when_every_frame_is_flawed_the_least_flawed_wins(pick):
    group = [
        portrait(1, face_quality=0.9, motion_blur=0.6),
        portrait(2, face_quality=0.3, motion_blur=0.4),
    ]

    assert winner(group, winner_pick=pick) == winner(group) == "DSCF0002.JPG"


@pytest.mark.parametrize("pick", STANDINGS)
def test_a_component_missing_from_one_frame_is_left_out_for_the_group(pick):
    group = [
        portrait(1, face_sharpness=0.60, face_quality=0.4, aesthetics=None),
        portrait(2, face_sharpness=0.55, face_quality=0.9, aesthetics=0.9),
    ]

    assert winner(group, winner_pick=pick) == "DSCF0001.JPG"


@pytest.mark.parametrize("pick", STANDINGS)
def test_scores_and_the_keeper_budget_keep_absolute_scores(pick):
    group = [portrait(1, face_quality=0.9), portrait(2, face_quality=0.5), portrait(3)]

    absolute = judge([group], keeper_budget=0.67)
    by_standing = judge([group], keeper_budget=0.67, winner_pick=pick)

    assert {i: j.scores for i, j in by_standing.items()} == {
        i: j.scores for i, j in absolute.items()
    }
    assert {i: j.verdict for i, j in by_standing.items()} == {
        i: j.verdict for i, j in absolute.items()
    }
