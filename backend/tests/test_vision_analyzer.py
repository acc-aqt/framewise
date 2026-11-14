import math
import platform
import sys
from pathlib import Path

import pytest
from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter

pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="Apple Vision runs on macOS only")


def draw_landscape(path: Path, shift: int = 0) -> Path:
    image = Image.new("RGB", (800, 600))
    draw = ImageDraw.Draw(image)
    for y in range(360):
        draw.line([(0, y), (800, y)], fill=(70 + y // 4, 130 + y // 6, 230))
    draw.ellipse((560 + shift, 70, 680 + shift, 190), fill=(255, 215, 90))
    draw.polygon(
        [(0, 420), (220 + shift, 170), (430 + shift, 400), (800, 260), (800, 600), (0, 600)],
        fill=(70, 95, 70),
    )
    draw.rectangle((0, 470, 800, 600), fill=(45, 120, 50))
    image.save(path, "JPEG", quality=90)
    return path


def draw_still_life(path: Path) -> Path:
    image = Image.new("RGB", (800, 600), (235, 225, 210))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 420, 800, 600), fill=(120, 75, 40))
    draw.rectangle((180, 180, 330, 440), fill=(30, 60, 150))
    draw.ellipse((420, 260, 620, 440), fill=(200, 40, 40))
    draw.polygon([(640, 440), (700, 220), (760, 440)], fill=(60, 60, 60))
    image.save(path, "JPEG", quality=90)
    return path


def a_moment_later(source: Path, path: Path) -> Path:
    with Image.open(source) as image:
        brighter = ImageEnhance.Brightness(image).enhance(1.06)
        brighter.crop((8, 6, 800, 600)).resize((800, 600)).save(path, "JPEG", quality=80)
    return path


def similarity(first: list[float], second: list[float]) -> float:
    dot = sum(a * b for a, b in zip(first, second, strict=True))
    return dot / (math.hypot(*first) * math.hypot(*second))


def test_near_identical_frames_are_more_similar_than_unrelated_frames(tmp_path):
    from framewise.vision_analyzer import VisionAnalyzer

    analyzer = VisionAnalyzer()
    landscape = draw_landscape(tmp_path / "landscape.jpg")
    landscape_again = a_moment_later(landscape, tmp_path / "landscape-again.jpg")
    still_life = draw_still_life(tmp_path / "still-life.jpg")

    fingerprints = {
        path.stem: analyzer.analyze(path).fingerprint
        for path in (landscape, landscape_again, still_life)
    }

    near_identical = similarity(fingerprints["landscape"], fingerprints["landscape-again"])
    unrelated = similarity(fingerprints["landscape"], fingerprints["still-life"])
    assert near_identical > unrelated


def gaussian_blurred(source: Path, path: Path) -> Path:
    with Image.open(source) as image:
        image.filter(ImageFilter.GaussianBlur(4)).save(path, "JPEG", quality=90)
    return path


def motion_blurred(source: Path, path: Path, length: int = 15) -> Path:
    with Image.open(source) as image:
        original = image.convert("RGB")
    smeared = original
    for step in range(1, length):
        shifted = ImageChops.offset(original, step - length // 2, 0)
        smeared = Image.blend(smeared, shifted, 1 / (step + 1))
    smeared.save(path, "JPEG", quality=90)
    return path


def re_exposed(source: Path, path: Path, stops: float) -> Path:
    factor = 2**stops
    with Image.open(source) as image:
        adjusted = image.point(
            lambda value: round(255 * min(1, (value / 255) ** 2.2 * factor) ** (1 / 2.2))
        )
    adjusted.save(path, "JPEG", quality=90)
    return path


def draw_low_key_portrait(path: Path) -> Path:
    image = Image.new("RGB", (800, 600), (12, 12, 14))
    draw = ImageDraw.Draw(image)
    draw.ellipse((330, 150, 470, 330), fill=(235, 200, 175))
    draw.rectangle((300, 330, 500, 600), fill=(40, 40, 48))
    image.save(path, "JPEG", quality=90)
    return path


def test_sharpness_separates_sharp_from_blurred_frames(tmp_path):
    from framewise.vision_analyzer import VisionAnalyzer

    analyzer = VisionAnalyzer()
    sharp = draw_landscape(tmp_path / "sharp.jpg")
    blurred = gaussian_blurred(sharp, tmp_path / "blurred.jpg")

    assert analyzer.analyze(sharp).sharpness > 0.8
    assert analyzer.analyze(blurred).sharpness < 0.2


def test_motion_blur_separates_steady_from_smeared_frames(tmp_path):
    from framewise.vision_analyzer import VisionAnalyzer

    analyzer = VisionAnalyzer()
    steady = draw_still_life(tmp_path / "steady.jpg")
    smeared = motion_blurred(steady, tmp_path / "smeared.jpg")
    defocused = gaussian_blurred(steady, tmp_path / "defocused.jpg")

    assert analyzer.analyze(steady).motion_blur < 0.2
    assert analyzer.analyze(defocused).motion_blur < 0.2
    assert analyzer.analyze(smeared).motion_blur > 0.5


def test_exposure_separates_correct_from_underexposed_frames(tmp_path):
    from framewise.vision_analyzer import VisionAnalyzer

    analyzer = VisionAnalyzer()
    correct = draw_landscape(tmp_path / "correct.jpg")
    dark = re_exposed(correct, tmp_path / "dark.jpg", stops=-2)

    correct_signals = analyzer.analyze(correct)
    dark_signals = analyzer.analyze(dark)

    assert abs(correct_signals.exposure_stops) < 0.5
    assert dark_signals.exposure_stops == pytest.approx(-2, abs=0.5)
    assert not dark_signals.low_key


def test_a_dark_frame_with_bright_highlights_is_low_key(tmp_path):
    from framewise.vision_analyzer import VisionAnalyzer

    signals = VisionAnalyzer().analyze(draw_low_key_portrait(tmp_path / "low-key.jpg"))

    assert signals.exposure_stops < -1
    assert signals.low_key


def test_a_bright_frame_with_intact_highlights_is_high_key_and_a_clipped_one_is_not(tmp_path):
    from framewise.vision_analyzer import VisionAnalyzer

    analyzer = VisionAnalyzer()
    bright = draw_still_life(tmp_path / "bright.jpg")
    clipped = re_exposed(bright, tmp_path / "clipped.jpg", stops=1.5)

    bright_signals = analyzer.analyze(bright)
    clipped_signals = analyzer.analyze(clipped)

    assert bright_signals.exposure_stops > 0.7
    assert bright_signals.high_key
    assert clipped_signals.exposure_stops > 1
    assert not clipped_signals.high_key


@pytest.mark.skipif(
    sys.platform == "darwin" and int(platform.mac_ver()[0].split(".")[0]) < 15,
    reason="Apple Vision's aesthetics request needs macOS 15",
)
def test_the_aesthetics_score_ranges_from_minus_one_to_one(tmp_path):
    from framewise.vision_analyzer import VisionAnalyzer

    aesthetics = VisionAnalyzer().analyze(draw_still_life(tmp_path / "still-life.jpg")).aesthetics

    assert aesthetics is not None
    assert -1 <= aesthetics <= 1


FACES = Path(__file__).parent / "fixtures" / "faces"


def side_by_side(paths: list[Path], path: Path) -> Path:
    """A group shot made of the reference faces next to each other."""
    images = [Image.open(source).convert("RGB") for source in paths]
    width = sum(image.width for image in images)
    group_shot = Image.new("RGB", (width, max(image.height for image in images)))
    left = 0
    for image in images:
        group_shot.paste(image, (left, 0))
        left += image.width
    group_shot.save(path, "JPEG", quality=90)
    return path


def test_a_frame_without_faces_has_none(tmp_path):
    from framewise.vision_analyzer import VisionAnalyzer

    assert VisionAnalyzer().analyze(draw_landscape(tmp_path / "landscape.jpg")).faces == []


def test_the_real_analyzer_tells_open_from_closed_eyes():
    from framewise.vision_analyzer import VisionAnalyzer

    analyzer = VisionAnalyzer()
    [open_face] = analyzer.analyze(FACES / "eyes-open.jpg").faces
    [closed_face] = analyzer.analyze(FACES / "eyes-closed.jpg").faces

    assert open_face.eyes_open is True
    assert closed_face.eyes_open is False


def test_each_face_has_a_box_from_the_top_left_a_sharpness_and_a_quality():
    from framewise.vision_analyzer import VisionAnalyzer

    [face] = VisionAnalyzer().analyze(FACES / "eyes-open.jpg").faces

    assert 0.2 < face.x < 0.4 and 0.2 < face.y < 0.4
    assert 0.3 < face.width < 0.5 and 0.3 < face.height < 0.5
    assert face.sharpness > 0.5
    assert face.quality is not None and 0 <= face.quality <= 1


def test_a_blurred_face_is_less_sharp(tmp_path):
    from framewise.vision_analyzer import VisionAnalyzer

    analyzer = VisionAnalyzer()
    blurred = gaussian_blurred(FACES / "eyes-open.jpg", tmp_path / "blurred.jpg")

    [sharp_face] = analyzer.analyze(FACES / "eyes-open.jpg").faces
    [blurred_face] = analyzer.analyze(blurred).faces

    assert blurred_face.sharpness < 0.25 < sharp_face.sharpness


EXIF_ORIENTATION_TAG = 0x0112
ROTATED_90_CLOCKWISE = 8


def portrait(path: Path, background: int, face: Path = FACES / "eyes-open.jpg") -> Path:
    """The reference face on the left of a plain background, like a Frame of a person in a
    room."""
    image = Image.new("RGB", (768, 512), (background,) * 3)
    with Image.open(face) as face_image:
        image.paste(face_image.convert("RGB"), (64, 128))
    image.save(path, "JPEG", quality=90)
    return path


def stored_rotated(source: Path, path: Path) -> Path:
    """The same Frame as a camera held upright stores it: pixels on their side and an EXIF
    orientation that turns them back."""
    with Image.open(source) as image:
        exif = Image.Exif()
        exif[EXIF_ORIENTATION_TAG] = ROTATED_90_CLOCKWISE
        image.transpose(Image.Transpose.ROTATE_270).save(path, "JPEG", quality=90, exif=exif)
    return path


def test_a_face_is_measured_where_it_appears_in_a_frame_stored_on_its_side(tmp_path):
    from framewise.vision_analyzer import VisionAnalyzer

    analyzer = VisionAnalyzer()
    upright = portrait(tmp_path / "upright.jpg", background=128)
    on_its_side = stored_rotated(upright, tmp_path / "on-its-side.jpg")

    [upright_face] = analyzer.analyze(upright).faces
    [face] = analyzer.analyze(on_its_side).faces

    assert face.sharpness == pytest.approx(upright_face.sharpness, abs=0.05)


def test_a_portrait_against_a_blown_out_white_wall_is_high_key(tmp_path):
    from framewise.vision_analyzer import VisionAnalyzer

    signals = VisionAnalyzer().analyze(portrait(tmp_path / "white-wall.jpg", background=255))

    assert signals.exposure_stops > 1.25
    assert signals.high_key


def test_a_portrait_whose_face_is_blown_out_is_not_high_key(tmp_path):
    from framewise.vision_analyzer import VisionAnalyzer

    white_wall = portrait(tmp_path / "white-wall.jpg", background=255)
    blown_out = re_exposed(white_wall, tmp_path / "blown-out.jpg", stops=1.5)

    signals = VisionAnalyzer().analyze(blown_out)

    assert signals.faces
    assert signals.exposure_stops > 1.25
    assert not signals.high_key


def test_the_real_analyzer_checks_every_face_in_a_group_shot(tmp_path):
    from framewise.vision_analyzer import VisionAnalyzer

    group_shot = side_by_side(
        [FACES / "eyes-open.jpg", FACES / "eyes-closed.jpg", FACES / "eyes-open.jpg"],
        tmp_path / "group-shot.jpg",
    )

    faces = sorted(VisionAnalyzer().analyze(group_shot).faces, key=lambda face: face.x)

    assert [face.eyes_open for face in faces] == [True, False, True]
