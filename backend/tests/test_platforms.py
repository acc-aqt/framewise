from pathlib import Path

from framewise.benchmark import active_catalog
from framewise.lightroom import lightroom_preferences
from framewise.review import default_data_dir

HOME = Path("/home/me")


def test_on_macos_the_data_directory_is_under_application_support():
    assert default_data_dir("darwin", {}, HOME) == HOME / "Library/Application Support/framewise"


def test_on_linux_the_data_directory_follows_xdg():
    assert default_data_dir("linux", {"XDG_DATA_HOME": "/data"}, HOME) == Path("/data/framewise")


def test_on_linux_without_xdg_data_home_the_data_directory_is_under_local_share():
    assert default_data_dir("linux", {}, HOME) == HOME / ".local/share/framewise"


def test_on_windows_the_data_directory_is_under_local_app_data():
    environ = {"LOCALAPPDATA": r"C:\Users\me\AppData\Local"}
    assert default_data_dir("win32", environ, HOME) == Path(r"C:\Users\me\AppData\Local/framewise")


def test_on_windows_without_local_app_data_the_data_directory_is_under_the_home_folder():
    assert default_data_dir("win32", {}, HOME) == HOME / "AppData/Local/framewise"


def test_on_macos_lightroom_classics_preferences_are_a_plist_under_library():
    assert lightroom_preferences("darwin", {}, HOME) == (
        HOME / "Library/Preferences/com.adobe.LightroomClassicCC7.plist"
    )


def test_on_windows_lightroom_classics_preferences_are_an_agprefs_under_app_data():
    environ = {"APPDATA": r"C:\Users\me\AppData\Roaming"}
    assert lightroom_preferences("win32", environ, HOME) == Path(
        r"C:\Users\me\AppData\Roaming/Adobe/Lightroom/Preferences"
        "/Lightroom Classic CC 7 Preferences.agprefs"
    )


def test_on_windows_without_app_data_lightroom_classics_preferences_are_under_the_home_folder():
    assert lightroom_preferences("win32", {}, HOME) == (
        HOME
        / "AppData/Roaming/Adobe/Lightroom/Preferences/Lightroom Classic CC 7 Preferences.agprefs"
    )


def test_lightroom_classic_does_not_run_on_linux():
    assert lightroom_preferences("linux", {}, HOME) is None


def test_without_lightroom_classics_preferences_there_is_no_active_catalog(tmp_path):
    assert active_catalog(None) is None
    assert active_catalog(tmp_path / "missing.plist") is None
