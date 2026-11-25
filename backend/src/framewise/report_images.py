"""A Problem report's images: exact copies of a Group's Analysis sources in a folder of
framewise's data folder, which the photographer attaches to the issue themselves (ADR-0012).

framewise never uploads them."""

import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from framewise.exiftool import ExifTool
from framewise.store import main_file_name

RevealFolder = Callable[[Path], None]
FOLDER_NAME = "problem-report-images"
GITHUB_IMAGE_LIMIT = 10_000_000
"""GitHub's 10 MB limit on an image attached to an issue."""
PERSONAL_INFO_DELETIONS = (
    "-gps*=",
    "-*SerialNumber=",
    "-OwnerName=",
    "-Artist=",
    "-XMP-dc:Creator=",
    "-IPTC:By-line=",
)
"""ExifTool arguments that delete location, camera and lens serial numbers, also those in maker
notes where ExifTool can write them, the owner's name and the artist, in every group. ExifTool
rewrites only the metadata, so image data, focus, exposure and maker notes stay."""


@dataclass(frozen=True)
class ReportImage:
    name: str
    size: int
    too_large: bool
    """Whether the file is over GitHub's image limit, so it has to be shared another way."""


@dataclass(frozen=True)
class SourceImage:
    main_path: str
    """The Frame's main file, relative to the Session folder."""
    path: Path
    """The Frame's Analysis source."""
    from_raw: bool
    """Whether the source is a RAW-only Frame's embedded preview."""


def copy_report_images(sources: list[SourceImage], folder: Path) -> list[ReportImage]:
    """Replaces the folder with byte-for-byte copies of the sources, each named after its
    Frame's main file."""
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(mode=0o700, parents=True)
    copied = []
    for source in sources:
        target = _free_name(folder, _copy_name(source))
        shutil.copyfile(source.path, target)
        copied.append(report_image(target))
    return copied


def report_image(path: Path) -> ReportImage:
    size = path.stat().st_size
    return ReportImage(path.name, size, size > GITHUB_IMAGE_LIMIT)


def remove_personal_info(exiftool: ExifTool, images: list[Path]) -> bool:
    """Deletes location and owner info from the images in place, and says whether ExifTool
    managed it for every image."""
    if not images:
        return True
    result = exiftool.run("-overwrite_original", *PERSONAL_INFO_DELETIONS, *images)
    return not result.errors


def _copy_name(source: SourceImage) -> str:
    name = main_file_name(source.main_path)
    return f"{name}.jpg" if source.from_raw else name


def _free_name(folder: Path, name: str) -> Path:
    """The name, or for a second Frame of the same name from another subfolder, the name with a
    number."""
    target = folder / name
    number = 2
    while target.exists():
        stem, dot, suffix = name.partition(".")
        target = folder / f"{stem} ({number}){dot}{suffix}"
        number += 1
    return target


def reveal_folder(folder: Path) -> None:
    """Opens the folder in the OS file manager, or warns where there is none."""
    command = reveal_folder_command(sys.platform, folder)
    if command is None:
        print(
            f"framewise: warning: no file manager to open, the images are in {folder}",
            file=sys.stderr,
        )
        return
    # Explorer exits non-zero even when it opened the folder, so the exit code says nothing.
    subprocess.run(command)


def reveal_folder_command(platform: str, folder: Path) -> list[str] | None:
    """The command that opens the folder in Finder, Explorer or the Linux file manager, or None
    where there is none."""
    if platform == "darwin":
        return ["open", str(folder)]
    if platform == "win32":
        return ["explorer", str(folder)]
    if shutil.which("xdg-open"):
        return ["xdg-open", str(folder)]
    return None
