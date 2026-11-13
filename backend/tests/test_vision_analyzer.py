import math
import sys
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageEnhance

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
