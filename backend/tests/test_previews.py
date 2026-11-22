"""Extracting embedded previews with the real ExifTool, skipped where it is not installed."""

import io
import struct
from pathlib import Path

import pytest
from conftest import make_raw
from PIL import Image

from framewise.exiftool import ExifTool, ExifToolResult, find_exiftool
from framewise.previews import NO_PREVIEW, ExifToolPreviews, PreviewError
from framewise.review import open_session

pytestmark = pytest.mark.skipif(find_exiftool() is None, reason="ExifTool is not installed")

ORIENTATION_ROTATE_90_CW = 6


def make_dng_with_previews(path: Path, sizes: list[tuple[int, int]], orientation: int = 1) -> Path:
    """A minimal DNG holding a JPG preview of each size: the first in IFD0, the rest in SubIFDs,
    where ExifTool reads the second as PreviewImage and the third as JpgFromRaw. Real DNGs keep the
    raw data in the first SubIFD, so ExifTool reads no preview there."""
    jpgs = [_jpg(size) for size in sizes]
    body, offsets = b"", []
    for jpg in jpgs:
        offsets.append(8 + len(body))
        body += jpg
    sub_ifds = []
    for size, jpg, offset in list(zip(sizes, jpgs, offsets, strict=True))[1:]:
        sub_ifds.append(8 + len(body))
        body += _ifd(_image_entries(size, offset, len(jpg)), 8 + len(body))
    entries = [
        *_image_entries(sizes[0], offsets[0], len(jpgs[0])),
        (0x112, 3, 1, struct.pack("<H", orientation)),
        (0xC612, 1, 4, bytes([1, 4, 0, 0])),
    ]
    if sub_ifds:
        entries.append((0x14A, 4, len(sub_ifds), struct.pack(f"<{len(sub_ifds)}I", *sub_ifds)))
    ifd0_offset = 8 + len(body)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"II*\0" + struct.pack("<I", ifd0_offset) + body + _ifd(entries, ifd0_offset))
    return path


def _jpg(size: tuple[int, int]) -> bytes:
    output = io.BytesIO()
    Image.new("RGB", size, (10, 200, 30)).save(output, "JPEG")
    return output.getvalue()


def _image_entries(size: tuple[int, int], offset: int, length: int) -> list[tuple]:
    """A reduced-resolution JPEG image's TIFF tags."""
    width, height = size
    return [
        (0xFE, 4, 1, struct.pack("<I", 1)),
        (0x100, 3, 1, struct.pack("<H", width)),
        (0x101, 3, 1, struct.pack("<H", height)),
        (0x103, 3, 1, struct.pack("<H", 7)),
        (0x106, 3, 1, struct.pack("<H", 6)),
        (0x111, 4, 1, struct.pack("<I", offset)),
        (0x115, 3, 1, struct.pack("<H", 3)),
        (0x117, 4, 1, struct.pack("<I", length)),
    ]


def _ifd(entries: list[tuple], offset: int) -> bytes:
    """A TIFF directory placed at `offset`, followed by the values too long to fit in it."""
    entries = sorted(entries)
    values_offset = offset + 2 + 12 * len(entries) + 4
    directory, values = struct.pack("<H", len(entries)), b""
    for tag, value_type, count, value in entries:
        if len(value) <= 4:
            directory += struct.pack("<HHI", tag, value_type, count) + value.ljust(4, b"\0")
        else:
            pointer = struct.pack("<I", values_offset + len(values))
            directory += struct.pack("<HHI", tag, value_type, count) + pointer
            values += value
    return directory + struct.pack("<I", 0) + values


class FlakyExifTool(ExifTool):
    """The real ExifTool, except for the commands `fail` answers itself, by returning a result or
    raising."""

    def __init__(self, fail):
        super().__init__()
        self._fail = fail

    def run(self, *args):
        injected = self._fail([str(arg) for arg in args])
        return super().run(*args) if injected is None else injected


@pytest.fixture
def flaky_extract():
    started = []

    def make(fail):
        exiftool = FlakyExifTool(fail)
        started.append(exiftool)
        return ExifToolPreviews(exiftool)

    yield make
    for exiftool in started:
        exiftool.close()


@pytest.fixture
def extract():
    exiftool = ExifTool()
    yield ExifToolPreviews(exiftool)
    exiftool.close()


def test_the_largest_embedded_preview_is_extracted_with_the_raws_orientation(tmp_path, extract):
    raw = make_dng_with_previews(
        tmp_path / "L1000001.DNG",
        [(96, 64), (32, 24), (150, 100), (500, 300)],
        orientation=ORIENTATION_ROTATE_90_CW,
    )
    destination = tmp_path / "cache" / "preview.jpg"
    destination.parent.mkdir()

    preview = extract(raw, destination)

    assert (preview.width, preview.height) == (500, 300)
    with Image.open(destination) as image:
        assert image.size == (500, 300)
        assert image.getexif()[0x112] == ORIENTATION_ROTATE_90_CW
    assert sorted(path.name for path in destination.parent.iterdir()) == ["preview.jpg"]


def test_a_preview_cache_with_a_percent_sign_in_its_path_still_gets_the_preview(tmp_path, extract):
    raw = make_dng_with_previews(tmp_path / "L1000001.DNG", [(96, 64), (32, 24), (150, 100)])
    destination = tmp_path / "100%d cache" / "preview.jpg"
    destination.parent.mkdir()

    preview = extract(raw, destination)

    assert (preview.width, preview.height) == (150, 100)
    assert sorted(path.name for path in destination.parent.iterdir()) == ["preview.jpg"]


def test_a_raw_without_an_embedded_preview_cannot_be_extracted(tmp_path, extract):
    raw = make_raw(tmp_path / "DSCF0001.RAF")

    with pytest.raises(PreviewError) as raised:
        extract(raw, tmp_path / "preview.jpg")

    assert raised.value.reason == NO_PREVIEW
    assert not (tmp_path / "preview.jpg").exists()


def test_a_session_of_raws_opens_with_previews_extracted_by_exiftool(tmp_path):
    session_dir = tmp_path / "100% done"
    make_dng_with_previews(session_dir / "L1000001.DNG", [(96, 64), (32, 24), (400, 300)])
    make_raw(session_dir / "DSCF0002.RAF")

    store = open_session(session_dir, tmp_path / "data", min_preview_long_edge=400)

    [frame] = store.frames()
    assert (frame.main_path, frame.kind) == ("L1000001.DNG", "raw-only")
    with Image.open(store.analysis_image(frame)) as image:
        assert image.size == (400, 300)
    assert [(skipped.path, skipped.reason) for skipped in store.summary().skipped] == [
        ("DSCF0002.RAF", NO_PREVIEW)
    ]


def test_a_preview_exiftool_fails_to_extract_gives_way_to_the_next_largest(tmp_path, flaky_extract):
    raw = make_dng_with_previews(tmp_path / "L1000001.DNG", [(96, 64), (32, 24), (150, 100)])
    destination = tmp_path / "cache" / "preview.jpg"
    destination.parent.mkdir()
    failed = []

    def fail_first_extraction(args):
        if "-W!" in args and not failed:
            failed.append(args)
            return ExifToolResult(output="", errors=["Error: Error creating file"])
        return None

    preview = flaky_extract(fail_first_extraction)(raw, destination)

    assert (preview.width, preview.height) == (96, 64)
    assert sorted(path.name for path in destination.parent.iterdir()) == ["preview.jpg"]


def test_a_raw_whose_previews_all_fail_to_extract_is_refused_with_exiftools_error(
    tmp_path, flaky_extract
):
    raw = make_dng_with_previews(tmp_path / "L1000001.DNG", [(96, 64), (32, 24), (150, 100)])
    destination = tmp_path / "cache" / "preview.jpg"
    destination.parent.mkdir()

    def fail_extraction(args):
        if "-W!" in args:
            return ExifToolResult(output="", errors=["Error: Error creating file"])
        return None

    with pytest.raises(PreviewError) as raised:
        flaky_extract(fail_extraction)(raw, destination)

    assert raised.value.reason == f"{NO_PREVIEW}: Error: Error creating file"
    assert list(destination.parent.iterdir()) == []


def test_a_preview_without_the_raws_metadata_is_not_used(tmp_path, flaky_extract):
    raw = make_dng_with_previews(tmp_path / "L1000001.DNG", [(96, 64)])
    destination = tmp_path / "cache" / "preview.jpg"
    destination.parent.mkdir()

    def fail_metadata_copy(args):
        if "-tagsFromFile" in args:
            return ExifToolResult(output="", errors=["Error: Not a valid JPEG"])
        return None

    with pytest.raises(PreviewError) as raised:
        flaky_extract(fail_metadata_copy)(raw, destination)

    assert raised.value.reason == (
        "ExifTool could not copy the RAW's metadata into its preview: Error: Not a valid JPEG"
    )
    assert list(destination.parent.iterdir()) == []


def test_exiftool_failing_mid_extraction_leaves_no_partial_preview(tmp_path, flaky_extract):
    raw = make_dng_with_previews(tmp_path / "L1000001.DNG", [(96, 64)])
    destination = tmp_path / "cache" / "preview.jpg"
    destination.parent.mkdir()

    def crash_on_metadata_copy(args):
        if "-tagsFromFile" in args:
            raise BrokenPipeError("ExifTool stopped")
        return None

    with pytest.raises(PreviewError):
        flaky_extract(crash_on_metadata_copy)(raw, destination)

    assert list(destination.parent.iterdir()) == []


def test_a_preview_exiftool_returns_undecodable_through_a_percent_path_is_refused_with_why(
    tmp_path, flaky_extract
):
    raw = make_dng_with_previews(tmp_path / "L1000001.DNG", [(96, 64)])
    destination = tmp_path / "100%d cache" / "preview.jpg"
    destination.parent.mkdir()

    def garble_base64(args):
        if "-json" in args and "-b" in args:
            return ExifToolResult(
                output='[{"SourceFile": "L1000001.DNG", "PreviewImage": "base64:not base64!"}]',
                errors=[],
            )
        return None

    with pytest.raises(PreviewError) as raised:
        flaky_extract(garble_base64)(raw, destination)

    assert raised.value.reason == (
        f"{NO_PREVIEW}: ExifTool returned the preview in a form framewise could not decode"
    )
    assert list(destination.parent.iterdir()) == []
