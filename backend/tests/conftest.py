from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from framewise.review import open_session
from framewise.server import create_app

EXIF_RATING_TAG = 0x4746


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
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    options = {}
    if stars is not None or label is not None:
        options["xmp"] = xmp_packet(stars, label)
    if exif_stars is not None:
        exif = Image.Exif()
        exif[EXIF_RATING_TAG] = exif_stars
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


@pytest.fixture
def review(session_dir: Path, data_dir: Path):
    def start() -> TestClient:
        return TestClient(create_app(open_session(session_dir, data_dir)))

    return start
