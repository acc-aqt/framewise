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
