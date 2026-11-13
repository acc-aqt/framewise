import hashlib
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from framewise.analyzer import FrameSignals
from framewise.review import open_session
from framewise.server import create_app

EXIF_RATING_TAG = 0x4746
EXIF_IFD_TAG = 0x8769
DATE_TIME_ORIGINAL_TAG = 0x9003
SUBSEC_TIME_ORIGINAL_TAG = 0x9291


def xmp_packet(stars: int | None = None, label: str | None = None) -> bytes:
    attributes = ""
    if stars is not None:
        attributes += f' xmp:Rating="{stars}"'
    if label is not None:
        attributes += f' xmp:Label="{label}"'
    return (
        '<?xpacket begin="" id="W5M0MpCehiHzreSzNTczkc9d"?>'
        '<x:xmpmeta xmlns:x="adobe:ns:meta/">'
        '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
        '<rdf:Description rdf:about="" xmlns:xmp="http://ns.adobe.com/xap/1.0/"'
        f"{attributes}/>"
        "</rdf:RDF></x:xmpmeta>"
        '<?xpacket end="w"?>'
    ).encode()


def make_jpg(
    path: Path,
    stars: int | None = None,
    label: str | None = None,
    exif_stars: int | None = None,
    size: tuple[int, int] = (64, 48),
    captured_at: datetime | None = None,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    options = {}
    if stars is not None or label is not None:
        options["xmp"] = xmp_packet(stars, label)
    exif = Image.Exif()
    if exif_stars is not None:
        exif[EXIF_RATING_TAG] = exif_stars
    if captured_at is not None:
        exif_ifd = exif.get_ifd(EXIF_IFD_TAG)
        exif_ifd[DATE_TIME_ORIGINAL_TAG] = captured_at.strftime("%Y:%m:%d %H:%M:%S")
        exif_ifd[SUBSEC_TIME_ORIGINAL_TAG] = f"{captured_at.microsecond // 10000:02d}"
    if exif_stars is not None or captured_at is not None:
        options["exif"] = exif
    Image.new("RGB", size, (200, 120, 40)).save(path, "JPEG", **options)
    return path


def make_raw(path: Path, stars: int | None = None, label: str | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = b"FAKE-RAW-HEADER" + b"\0" * 256
    if stars is not None or label is not None:
        content += xmp_packet(stars, label) + b"\0" * 64
    path.write_bytes(content)
    return path


def make_sidecar(path: Path, stars: int | None = None, label: str | None = None) -> Path:
    path.write_bytes(xmp_packet(stars, label))
    return path


@pytest.fixture
def session_dir(tmp_path: Path) -> Path:
    folder = tmp_path / "session"
    folder.mkdir()
    return folder


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    return tmp_path / "app-support"


class FakeAnalyzer:
    """Returns scripted fingerprints, and a fingerprint unlike any other for unscripted Frames."""

    def __init__(self):
        self.fingerprints: dict[Path, list[float]] = {}
        self.analyzed: list[Path] = []

    def script(self, jpg_path: Path, fingerprint: list[float]) -> Path:
        self.fingerprints[jpg_path.resolve()] = fingerprint
        return jpg_path

    def analyze(self, jpg_path: Path) -> FrameSignals:
        self.analyzed.append(jpg_path)
        fingerprint = self.fingerprints.get(jpg_path.resolve()) or _unrelated_fingerprint(jpg_path)
        return FrameSignals(fingerprint=fingerprint)


def _unrelated_fingerprint(jpg_path: Path) -> list[float]:
    digest = hashlib.sha512(str(jpg_path.resolve()).encode()).digest()
    return [byte - 127.5 for byte in digest]


@pytest.fixture
def analyzer() -> FakeAnalyzer:
    return FakeAnalyzer()


@pytest.fixture
def review(session_dir: Path, data_dir: Path, analyzer: FakeAnalyzer):
    def start() -> TestClient:
        return TestClient(create_app(open_session(session_dir, data_dir, analyzer)))

    return start
