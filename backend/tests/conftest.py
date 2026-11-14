import hashlib
import os
import sys
import threading
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from framewise.analyzer import FrameSignals
from framewise.review import SessionAnalysis, open_session
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


CLEAN_SIGNALS = {
    "sharpness": 0.9,
    "motion_blur": 0.05,
    "exposure_stops": 0.0,
    "low_key": False,
    "high_key": False,
    "aesthetics": 0.0,
}


def clean_signals(fingerprint: list[float]) -> FrameSignals:
    """The signals of a sharp, well-exposed Frame of average aesthetics."""
    return FrameSignals(fingerprint=fingerprint, **CLEAN_SIGNALS)


class FakeAnalyzer:
    """Returns scripted fingerprints and signals. An unscripted Frame gets a fingerprint unlike any
    other and the signals of a sharp, well-exposed Frame of average aesthetics.
    A held Frame's analysis blocks until released, to observe a run in progress. Records whether
    each analysing thread runs at Darwin background priority on macOS."""

    def __init__(self):
        self.fingerprints: dict[Path, list[float]] = {}
        self.signals: dict[Path, dict] = {}
        self.analyzed: list[Path] = []
        self.in_flight = 0
        self.peak_in_flight = 0
        self.at_background_priority: list[bool] = []
        self._held: dict[Path, threading.Event] = {}
        self._failing: set[Path] = set()
        self._lock = threading.Lock()

    def script(self, jpg_path: Path, fingerprint: list[float] | None = None, **signals) -> Path:
        if fingerprint is not None:
            self.fingerprints[jpg_path.resolve()] = fingerprint
        self.signals[jpg_path.resolve()] = signals
        return jpg_path

    def hold(self, jpg_path: Path) -> Path:
        self._held[jpg_path.resolve()] = threading.Event()
        return jpg_path

    def fail(self, jpg_path: Path) -> Path:
        self._failing.add(jpg_path.resolve())
        return jpg_path

    def release(self, jpg_path: Path) -> None:
        self._held[jpg_path.resolve()].set()

    def release_all(self) -> None:
        for gate in self._held.values():
            gate.set()

    def analyze(self, jpg_path: Path) -> FrameSignals:
        with self._lock:
            self.in_flight += 1
            self.peak_in_flight = max(self.peak_in_flight, self.in_flight)
            if sys.platform == "darwin":
                self.at_background_priority.append(os.getpriority(os.PRIO_DARWIN_THREAD, 0) != 0)
        gate = self._held.get(jpg_path.resolve())
        released = gate is None or gate.wait(timeout=5)
        with self._lock:
            self.in_flight -= 1
            self.analyzed.append(jpg_path)
        if not released:
            raise TimeoutError(f"held Frame was never released: {jpg_path}")
        if jpg_path.resolve() in self._failing:
            raise RuntimeError(f"cannot analyse {jpg_path}")
        fingerprint = self.fingerprints.get(jpg_path.resolve()) or _unrelated_fingerprint(jpg_path)
        scripted = self.signals.get(jpg_path.resolve(), {})
        return FrameSignals(fingerprint=fingerprint, **(CLEAN_SIGNALS | scripted))


def _unrelated_fingerprint(jpg_path: Path) -> list[float]:
    digest = hashlib.sha512(str(jpg_path.resolve()).encode()).digest()
    return [byte - 127.5 for byte in digest]


def wait_until(condition: Callable[[], bool], timeout: float = 5) -> None:
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            raise AssertionError("condition not met in time")
        time.sleep(0.01)


class FakeClock:
    """A monotonic clock that only moves when a test sets it."""

    def __init__(self):
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def analyzer():
    fake = FakeAnalyzer()
    yield fake
    fake.release_all()


@pytest.fixture
def review(session_dir: Path, data_dir: Path, analyzer: FakeAnalyzer):
    """Opens the Review UI after analysis has finished."""

    def start() -> TestClient:
        store = open_session(session_dir, data_dir)
        analysis = SessionAnalysis(store, analyzer)
        analysis.run()
        return TestClient(create_app(store, analysis))

    return start


@pytest.fixture
def live_review(session_dir: Path, data_dir: Path, analyzer: FakeAnalyzer, clock: FakeClock):
    """Opens the Review UI while analysis runs in the background."""

    def start(background: bool = False) -> TestClient:
        store = open_session(session_dir, data_dir)
        analysis = SessionAnalysis(store, analyzer, background=background, clock=clock)
        threading.Thread(target=analysis.run, daemon=True).start()
        return TestClient(create_app(store, analysis))

    return start
