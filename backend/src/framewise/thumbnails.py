import io
from pathlib import Path

from PIL import Image, ImageOps

THUMBNAIL_BOX = (480, 480)


def make_thumbnail(jpg_path: Path) -> bytes:
    with Image.open(jpg_path) as image:
        image.draft("RGB", THUMBNAIL_BOX)
        thumbnail = ImageOps.exif_transpose(image).convert("RGB")
    thumbnail.thumbnail(THUMBNAIL_BOX)
    output = io.BytesIO()
    thumbnail.save(output, "JPEG", quality=85)
    return output.getvalue()
