import hashlib
import json
import plistlib
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import pytest
from conftest import FakeAnalyzer, make_jpg

from framewise.analyzer import SimilarityThresholds
from framewise.benchmark import (
    active_catalog,
    agreement,
    copy_catalog,
    main,
    match_references,
    read_reference_ratings,
    timing,
    winner_agreement,
)
from framewise.camera_rating import CameraRating
from framewise.judge import Judgement, Scores, Verdict
from framewise.store import Frame

CATALOG_SCHEMA = """
CREATE TABLE AgLibraryRootFolder (id_local INTEGER PRIMARY KEY, absolutePath NOT NULL);
CREATE TABLE AgLibraryFolder (
    id_local INTEGER PRIMARY KEY, pathFromRoot NOT NULL, rootFolder INTEGER NOT NULL
);
CREATE TABLE AgLibraryFile (
    id_local INTEGER PRIMARY KEY, baseName NOT NULL, extension NOT NULL, folder INTEGER NOT NULL
);
CREATE TABLE Adobe_images (
    id_local INTEGER PRIMARY KEY, rootFile INTEGER NOT NULL, rating, masterImage INTEGER
);
"""
DUPLICATE = [1.0] + [0.0] * 63
OTHER_DUPLICATE = [0.0, 1.0] + [0.0] * 62


class FakeCatalog:
    """A Lightroom Classic catalog with only the tables and columns framewise reads."""

    def __init__(self, path: Path):
        self.path = path
        self._db = sqlite3.connect(path)
        self._db.executescript(CATALOG_SCHEMA)

    def add_photo(
        self, file: Path, rating: float | None, virtual_copy_of: int | None = None
    ) -> int:
        root, relative = f"{file.parent.parent}/", f"{file.parent.name}/"
        with self._db:
            root_id = self._id("AgLibraryRootFolder", "absolutePath", root)
            folder_id = self._folder_id(root_id, relative)
            file_id = self._db.execute(
                "INSERT INTO AgLibraryFile (baseName, extension, folder) VALUES (?, ?, ?)",
                (file.stem, file.suffix.lstrip("."), folder_id),
            ).lastrowid
            return self._db.execute(
                "INSERT INTO Adobe_images (rootFile, rating, masterImage) VALUES (?, ?, ?)",
                (file_id, rating, virtual_copy_of),
            ).lastrowid

    def close(self) -> None:
        self._db.close()

    def _id(self, table: str, column: str, value: str) -> int:
        row = self._db.execute(f"SELECT id_local FROM {table} WHERE {column} = ?", (value,))
        found = row.fetchone()
        if found:
            return found[0]
        return self._db.execute(f"INSERT INTO {table} ({column}) VALUES (?)", (value,)).lastrowid

    def _folder_id(self, root_id: int, relative: str) -> int:
        found = self._db.execute(
            "SELECT id_local FROM AgLibraryFolder WHERE rootFolder = ? AND pathFromRoot = ?",
            (root_id, relative),
        ).fetchone()
        if found:
            return found[0]
        return self._db.execute(
            "INSERT INTO AgLibraryFolder (pathFromRoot, rootFolder) VALUES (?, ?)",
            (relative, root_id),
        ).lastrowid


@pytest.fixture
def catalog(tmp_path: Path):
    folder = tmp_path / "Lightroom"
    folder.mkdir()
    fake = FakeCatalog(folder / "Lightroom Catalog.lrcat")
    yield fake
    fake.close()


def fingerprint_of(folder: Path) -> dict[str, str]:
    return {
        str(path.relative_to(folder)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(folder.rglob("*"))
        if path.is_file()
    }


def judgement(verdict: Verdict) -> Judgement:
    scores = Scores(
        sharpness=1,
        steadiness=1,
        exposure=1,
        aesthetics=None,
        face_quality=None,
        camera_rating=0,
        total=1,
    )
    return Judgement(verdict, [], scores, faces=[])


def frame(frame_id: int, jpg_path: str) -> Frame:
    return Frame(frame_id, jpg_path, None, CameraRating(None, None))


def test_the_active_catalog_is_the_one_lightroom_classic_loads(tmp_path):
    prefs = tmp_path / "com.adobe.LightroomClassicCC7.plist"
    prefs.write_bytes(plistlib.dumps({"libraryToLoad20": "/Users/me/Lightroom/Catalog.lrcat"}))

    assert active_catalog(prefs) == Path("/Users/me/Lightroom/Catalog.lrcat")


def test_copying_the_catalog_takes_its_write_ahead_log_along(catalog, tmp_path):
    wal = Path(f"{catalog.path}-wal")
    wal.write_bytes(b"")
    into = tmp_path / "copy"
    into.mkdir()

    copy = copy_catalog(catalog.path, into)

    assert copy.parent == into
    assert copy.read_bytes() == catalog.path.read_bytes()
    assert Path(f"{copy}-wal").exists()


def test_reference_ratings_are_read_for_the_session_only_by_file_path(catalog, session_dir):
    rated = session_dir / "DSCF0001.JPG"
    catalog.add_photo(rated, 3.0)
    catalog.add_photo(session_dir / "DSCF0002.JPG", None)
    catalog.add_photo(session_dir / "DSCF0003.RAF", 2.0)
    catalog.add_photo(session_dir.parent / "other" / "DSCF0001.JPG", 4.0)

    ratings = read_reference_ratings(catalog.path, session_dir)

    assert ratings == {rated: 3, session_dir / "DSCF0003.RAF": 2}


def test_virtual_copies_carry_no_reference_rating(catalog, session_dir):
    master = catalog.add_photo(session_dir / "DSCF0001.JPG", None)
    catalog.add_photo(session_dir / "DSCF0001.JPG", 5.0, virtual_copy_of=master)

    assert read_reference_ratings(catalog.path, session_dir) == {}


def test_frames_match_reference_ratings_by_their_jpg_path(session_dir):
    frames = [frame(1, "DSCF0001.JPG"), frame(2, "sub/DSCF0002.JPG"), frame(3, "DSCF0003.JPG")]
    ratings = {session_dir / "DSCF0001.JPG": 2, session_dir / "sub" / "dscf0002.jpg": 3}

    assert match_references(frames, session_dir, ratings) == {1: 2, 2: 3}


def test_agreement_counts_kept_and_rejected_frames_with_a_reference_rating():
    proposal = {
        1: judgement(Verdict.WINNER),
        2: judgement(Verdict.KEEPER),
        3: judgement(Verdict.KEEPER),
        4: judgement(Verdict.REJECT),
        5: judgement(Verdict.REJECT),
        6: judgement(Verdict.UNSURE),
    }
    references = {1: 3, 2: 2, 4: 2, 6: 3}

    result = agreement(proposal, references)

    assert result.kept == 3
    assert result.kept_with_reference == 2
    assert result.rejected == 2
    assert result.rejected_with_reference == 1
    assert result.with_reference == 4
    assert result.with_reference_rejected_or_unsure == 2
    assert result.verdicts_by_reference_stars == {
        2: {"keeper": 1, "reject": 1},
        3: {"winner": 1, "unsure": 1},
    }


def test_winner_agreement_counts_groups_whose_winner_is_among_the_top_rated_frames():
    proposal = {
        1: judgement(Verdict.WINNER),
        2: judgement(Verdict.KEEPER),
        3: judgement(Verdict.REJECT),
        4: judgement(Verdict.WINNER),
        5: judgement(Verdict.KEEPER),
    }
    groups = [[1, 2, 3], [4, 5]]
    references = {1: 4, 2: 2, 4: 1, 5: 3}

    result = winner_agreement(proposal, groups, references)

    assert result.agreeing == 1
    assert result.groups == 2
    assert result.share == 0.5


def test_a_winner_tied_for_the_top_rating_agrees():
    proposal = {1: judgement(Verdict.KEEPER), 2: judgement(Verdict.WINNER)}

    result = winner_agreement(proposal, [[1, 2]], {1: 3, 2: 3})

    assert result.agreeing == 1
    assert result.groups == 1


def test_groups_without_a_reference_rating_are_not_counted():
    proposal = {1: judgement(Verdict.WINNER), 2: judgement(Verdict.KEEPER)}

    result = winner_agreement(proposal, [[1, 2]], {})

    assert result.groups == 0
    assert result.share is None


def test_an_unrated_winner_disagrees_with_a_rated_frame_in_its_group():
    proposal = {1: judgement(Verdict.WINNER), 2: judgement(Verdict.REJECT)}

    result = winner_agreement(proposal, [[1, 2]], {2: 1})

    assert result.agreeing == 0
    assert result.groups == 1


def test_groups_of_one_frame_are_not_counted():
    proposal = {1: judgement(Verdict.WINNER)}

    result = winner_agreement(proposal, [[1]], {1: 3})

    assert result.groups == 0


def test_timing_is_measured_against_15_minutes_per_200_frames():
    result = timing(frames=261, seconds=900.0)

    assert result.seconds_per_frame == pytest.approx(900 / 261)
    assert result.budget_seconds == pytest.approx(261 * 4.5)
    assert result.within_budget


def test_benchmark_reports_agreement_and_timing_without_touching_session_or_catalog(
    session_dir, catalog, tmp_path, monkeypatch, capsys
):
    data_dir = tmp_path / "app-support"
    monkeypatch.setenv("FRAMEWISE_DATA_DIR", str(data_dir))
    analyzer = FakeAnalyzer()
    make_jpg(session_dir / "DSCF0001.JPG")
    analyzer.script(make_jpg(session_dir / "DSCF0002.JPG"), DUPLICATE, sharpness=0.1)
    analyzer.script(make_jpg(session_dir / "DSCF0003.JPG"), DUPLICATE)
    catalog.add_photo(session_dir / "DSCF0001.JPG", 3.0)
    catalog.add_photo(session_dir / "DSCF0002.JPG", 2.0)
    catalog.close()
    session_before = fingerprint_of(session_dir)
    catalog_before = fingerprint_of(catalog.path.parent)
    report = tmp_path / "report.json"

    main(
        [str(session_dir), "--catalog", str(catalog.path), "--report", str(report)],
        analyzer=analyzer,
    )

    result = json.loads(report.read_text())
    assert result["frames"] == 3
    assert result["agreement"]["with_reference"] == 2
    assert result["agreement"]["with_reference_rejected_or_unsure"] == 1
    assert result["agreement"]["rejected_with_reference"] == 1
    assert result["timing"]["budget_seconds"] == pytest.approx(3 * 4.5)
    assert result["providers"] == {"fingerprint": "fake-fingerprint@1"}
    assert result["winner_agreement"] == {"agreeing": 0, "groups": 1, "share": 0.0}
    out = capsys.readouterr().out
    assert "Rated Frames proposed as Reject or Unsure: 1 of 2" in out
    assert "Winners among their Group's top-rated Frames: 0 of 1 (0%)" in out
    assert fingerprint_of(session_dir) == session_before
    assert fingerprint_of(catalog.path.parent) == catalog_before
    assert not data_dir.exists()


def test_fitting_the_weights_reports_them_with_held_out_agreement_and_writes_nothing(
    session_dir, catalog, tmp_path, monkeypatch, capsys
):
    data_dir = tmp_path / "app-support"
    monkeypatch.setenv("FRAMEWISE_DATA_DIR", str(data_dir))
    analyzer = FakeAnalyzer()
    for number, fingerprint in ((1, DUPLICATE), (3, OTHER_DUPLICATE)):
        sharper_but_shaken = session_dir / f"DSCF000{number}.JPG"
        steady = session_dir / f"DSCF000{number + 1}.JPG"
        analyzer.script(make_jpg(sharper_but_shaken), fingerprint, sharpness=1.0, motion_blur=0.3)
        analyzer.script(make_jpg(steady), fingerprint, sharpness=0.8, motion_blur=0.0)
        catalog.add_photo(sharper_but_shaken, 2.0)
        catalog.add_photo(steady, 4.0)
    catalog.close()
    session_before = fingerprint_of(session_dir)
    catalog_before = fingerprint_of(catalog.path.parent)

    main(
        [
            str(session_dir),
            "--catalog",
            str(catalog.path),
            "--report",
            str(tmp_path / "report.json"),
            "--fit-weights",
        ],
        analyzer=analyzer,
    )

    out = capsys.readouterr().out
    assert (
        "  Proposed weights: sharpness 0.00, steadiness 1.20, exposure 0.00, aesthetics 0.00, "
        "face_quality 0.00" in out
    )
    assert "  Held-out pairs ranked as rated: current 0 of 2 (0%), proposed 2 of 2 (100%)" in out
    assert (
        "  Held-out Winners among their Group's top-rated Frames: "
        "current 0 of 2 (0%), proposed 2 of 2 (100%)" in out
    )
    assert fingerprint_of(session_dir) == session_before
    assert fingerprint_of(catalog.path.parent) == catalog_before
    assert not data_dir.exists()


def test_benchmark_refuses_to_write_its_report_into_the_session_folder(
    session_dir, catalog, tmp_path
):
    with pytest.raises(SystemExit) as exit_info:
        main(
            [
                str(session_dir),
                "--catalog",
                str(catalog.path),
                "--report",
                str(session_dir / "report.json"),
            ],
            analyzer=FakeAnalyzer(),
        )

    assert exit_info.value.code == 2


@dataclass
class NamedFingerprint:
    id: str
    priority: int = 0
    available: bool = True
    capability: str = "fingerprint"
    version: int = 1
    similarity: SimilarityThresholds = SimilarityThresholds(burst=0.8, near_duplicate=0.9)

    def is_available(self) -> bool:
        return self.available

    def fingerprint(self, jpg_path: Path) -> list[float]:
        return DUPLICATE


def run_benchmark(session_dir, catalog, tmp_path, *options, providers) -> dict:
    make_jpg(session_dir / "DSCF0001.JPG")
    report = tmp_path / "report.json"
    main(
        [str(session_dir), "--catalog", str(catalog.path), "--report", str(report), *options],
        providers=providers,
    )
    return json.loads(report.read_text())


def test_a_provider_override_serves_its_capability_and_the_report_names_it(
    session_dir, catalog, tmp_path, isolated_data_dir, capsys
):
    providers = [NamedFingerprint("default", priority=9), NamedFingerprint("chosen")]

    report = run_benchmark(
        session_dir, catalog, tmp_path, "--provider", "fingerprint=chosen", providers=providers
    )

    assert report["providers"] == {"fingerprint": "chosen@1"}
    assert "fingerprint: chosen@1" in capsys.readouterr().out


def test_a_provider_override_wins_over_the_config_file(
    session_dir, catalog, tmp_path, isolated_data_dir
):
    isolated_data_dir.mkdir()
    (isolated_data_dir / "config.toml").write_text('[providers]\nfingerprint = "configured"\n')
    providers = [NamedFingerprint("configured"), NamedFingerprint("chosen")]

    report = run_benchmark(
        session_dir, catalog, tmp_path, "--provider", "fingerprint=chosen", providers=providers
    )

    assert report["providers"] == {"fingerprint": "chosen@1"}


@pytest.mark.parametrize(
    ("override", "error"),
    [
        ("fingerprint=missing", 'the fingerprint Provider "missing" is not installed'),
        ("fingerprint=offline", 'the fingerprint Provider "offline" is not available'),
        ("eyes=chosen", 'unknown Capability "eyes"'),
    ],
)
def test_an_override_that_cannot_be_honoured_is_an_error(
    session_dir, catalog, tmp_path, isolated_data_dir, capsys, override, error
):
    providers = [NamedFingerprint("default"), NamedFingerprint("offline", available=False)]

    with pytest.raises(SystemExit) as exit_info:
        run_benchmark(session_dir, catalog, tmp_path, "--provider", override, providers=providers)

    assert exit_info.value.code == 1
    assert f"framewise-benchmark: error: {error}" in capsys.readouterr().err


def test_an_override_without_a_capability_and_id_is_a_usage_error(
    session_dir, catalog, tmp_path, isolated_data_dir
):
    with pytest.raises(SystemExit) as exit_info:
        run_benchmark(session_dir, catalog, tmp_path, "--provider", "fingerprint", providers=[])

    assert exit_info.value.code == 2


def test_a_provider_override_replaces_a_config_choice_that_cannot_be_honoured(
    session_dir, catalog, tmp_path, isolated_data_dir
):
    isolated_data_dir.mkdir()
    (isolated_data_dir / "config.toml").write_text('[providers]\nfingerprint = "offline"\n')
    providers = [NamedFingerprint("offline", available=False), NamedFingerprint("chosen")]

    report = run_benchmark(
        session_dir, catalog, tmp_path, "--provider", "fingerprint=chosen", providers=providers
    )

    assert report["providers"] == {"fingerprint": "chosen@1"}
