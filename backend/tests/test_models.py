import hashlib
from pathlib import Path

import pytest

from framewise.models import Model, ModelError, ensure_model

CONTENT = b"a tiny stand-in for a model file"


def hosted_model(tmp_path: Path, content: bytes = CONTENT, sha256: str | None = None) -> Model:
    """A model served from a local file, as if from its pinned URL."""
    source = tmp_path / "hosted" / "detector.task"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(content)
    return Model(
        file_name="detector.task",
        url=source.as_uri(),
        sha256=sha256 or hashlib.sha256(content).hexdigest(),
    )


def test_a_model_whose_checksum_does_not_match_is_rejected(tmp_path, data_dir):
    model = hosted_model(tmp_path, sha256=hashlib.sha256(b"the real model").hexdigest())

    with pytest.raises(ModelError, match="SHA-256"):
        ensure_model(model, data_dir)

    assert [path for path in data_dir.rglob("*") if path.is_file()] == []


def test_a_verified_model_is_not_downloaded_again(tmp_path, data_dir):
    model = hosted_model(tmp_path)
    path = ensure_model(model, data_dir)
    (tmp_path / "hosted" / "detector.task").write_bytes(b"a newer upload at the same URL")

    assert ensure_model(model, data_dir) == path
    assert path.read_bytes() == CONTENT


def test_a_missing_model_that_cannot_be_downloaded_points_to_the_download_command(
    tmp_path, data_dir
):
    model = hosted_model(tmp_path)
    (tmp_path / "hosted" / "detector.task").unlink()

    with pytest.raises(ModelError, match="`framewise models download`"):
        ensure_model(model, data_dir)

    assert [path for path in data_dir.rglob("*") if path.is_file()] == []
