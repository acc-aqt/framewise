import pytest

from framewise.focus_point import focus_area

# Recorded with `exiftool -j -n` from a Fujifilm X-T50 JPG, trimmed to the focus tags.
X_T50_PORTRAIT = {
    "FocusPixel": "6136 2334",
    "ExifImageWidth": 7728,
    "ExifImageHeight": 5152,
    "Orientation": 8,
}


def test_the_focus_point_is_turned_the_way_the_frame_is_displayed():
    """Turned 270 CW the X-T50 portrait is 5152 wide and 7728 high, and the point lands at
    (0.453, 0.206). The area is a square 10% of the shorter side: 515 pixels."""
    assert focus_area(X_T50_PORTRAIT) == pytest.approx((0.403, 0.173, 0.1, 0.0667), abs=1e-3)


def test_a_frame_turned_90_cw_moves_the_point_the_other_way():
    tags = X_T50_PORTRAIT | {"Orientation": 6}

    assert focus_area(tags) == pytest.approx((0.497, 0.761, 0.1, 0.0667), abs=1e-3)


@pytest.mark.parametrize(
    ("orientation", "center"),
    [
        (1, (0.25, 0.1)),
        (2, (0.75, 0.1)),
        (3, (0.75, 0.9)),
        (4, (0.25, 0.9)),
        (5, (0.1, 0.25)),
        (6, (0.9, 0.25)),
        (7, (0.9, 0.75)),
        (8, (0.1, 0.75)),
    ],
)
def test_every_exif_orientation_moves_the_point_with_the_frame(orientation, center):
    tags = {
        "FocusPixel": "1000 400",
        "ExifImageWidth": 4000,
        "ExifImageHeight": 4000,
        "Orientation": orientation,
    }

    x, y, width, height = focus_area(tags)

    assert (x + width / 2, y + height / 2) == pytest.approx(center)


def test_without_an_orientation_the_frame_is_displayed_as_stored():
    tags = {"FocusPixel": "3864 2576", "ExifImageWidth": 7728, "ExifImageHeight": 5152}

    assert focus_area(tags) == pytest.approx((0.467, 0.45, 0.0667, 0.1), abs=1e-3)


def test_an_area_reaching_past_the_edge_is_cut_to_the_frame():
    tags = X_T50_PORTRAIT | {"FocusPixel": "10 10", "Orientation": 1}

    x, y, width, height = focus_area(tags)

    assert x == 0 and y == 0
    assert 0 < width < 0.1 and 0 < height < 0.1


@pytest.mark.parametrize(
    "tags",
    [
        {"ExifImageWidth": 7728, "ExifImageHeight": 5152},
        X_T50_PORTRAIT | {"FocusPixel": "0 0"},
        X_T50_PORTRAIT | {"FocusPixel": "7728 100"},
        X_T50_PORTRAIT | {"FocusPixel": "100 6000"},
        X_T50_PORTRAIT | {"FocusPixel": "not a point"},
        {"FocusPixel": "6136 2334", "Orientation": 8},
    ],
    ids=["no point", "zero", "past the width", "past the height", "unreadable", "no size"],
)
def test_without_a_usable_focus_point_there_is_no_focus_area(tags):
    assert focus_area(tags) is None
