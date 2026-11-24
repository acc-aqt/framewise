import re

import pytest
from conftest import FakeAnalyzer, make_jpg
from test_write_back_api import jpg

from framewise.winner_comparison import main

MOUNTAIN = [0.0, 1.0, 0.0]


def sharper_against_more_pleasing(session_dir, analyzer) -> None:
    """A Burst where DSCF0001 is a little sharper and DSCF0002 much more pleasing: absolute
    Scores pick DSCF0002, standings DSCF0001. DSCF0009 stands alone."""
    jpg(session_dir, analyzer, "DSCF0001.JPG", sharpness=0.90, aesthetics=0.4)
    jpg(session_dir, analyzer, "DSCF0002.JPG", 0.3, sharpness=0.85, aesthetics=0.9)
    analyzer.script(make_jpg(session_dir / "DSCF0009.JPG"), MOUNTAIN)


def test_the_page_shows_the_winners_of_groups_where_the_picks_differ(
    session_dir, isolated_data_dir, tmp_path, capsys
):
    analyzer = FakeAnalyzer()
    sharper_against_more_pleasing(session_dir, analyzer)
    page = tmp_path / "comparison.html"

    main([str(session_dir), "--page", str(page)], analyzer=analyzer)

    html = page.read_text()
    assert html.count('class="candidate"') == 2
    assert set(re.findall(r"DSCF\d{4}\.JPG", html)) == {"DSCF0001.JPG", "DSCF0002.JPG"}
    assert html.count("data:image/jpeg;base64,") == 2
    out = capsys.readouterr().out
    assert "Winners differ in 1 of 1 Groups of more than one Frame" in out
    assert str(page) in out


def test_the_page_says_which_pick_chose_each_winner_only_in_its_hidden_tally(
    session_dir, isolated_data_dir, tmp_path
):
    analyzer = FakeAnalyzer()
    sharper_against_more_pleasing(session_dir, analyzer)
    page = tmp_path / "comparison.html"

    main([str(session_dir), "--page", str(page)], analyzer=analyzer)

    html = page.read_text()
    picks = dict(re.findall(r'data-name="(DSCF\d{4}\.JPG)" data-picks="([^"]*)"', html))
    assert picks == {"DSCF0001.JPG": "rank z-score", "DSCF0002.JPG": "scores"}


def test_nothing_is_written_when_the_picks_agree_everywhere(
    session_dir, isolated_data_dir, tmp_path, capsys
):
    analyzer = FakeAnalyzer()
    jpg(session_dir, analyzer, "DSCF0001.JPG", sharpness=0.9, aesthetics=0.9)
    jpg(session_dir, analyzer, "DSCF0002.JPG", 0.3, sharpness=0.5, aesthetics=0.4)
    page = tmp_path / "comparison.html"

    main([str(session_dir), "--page", str(page)], analyzer=analyzer)

    assert not page.exists()
    assert "Winners differ in 0 of 1 Groups" in capsys.readouterr().out


def test_the_page_must_not_go_into_the_session_folder(session_dir, isolated_data_dir):
    with pytest.raises(SystemExit):
        main([str(session_dir), "--page", str(session_dir / "comparison.html")])
