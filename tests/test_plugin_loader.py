"""FIFA Plugin Loader plugins: scan, ON/OFF, loader detection, loaded state (plugin_loader.py)."""
from __future__ import annotations

from pathlib import Path

import pytest

from server16_py.plugin_loader import (
    LOADER_THREAD_URL,
    PluginEntry,
    is_loader_installed,
    loaded_states,
    plugins_dir,
    scan,
    set_enabled,
)


def _touch(path: Path, data: bytes = b"MZ") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def _by_name(game: Path) -> dict[str, PluginEntry]:
    return {entry.name: entry for entry in scan(game)}


def test_thread_url_is_the_forum_thread():
    assert LOADER_THREAD_URL == "https://soccergaming.com/forums/threads/fifa-16-plugin-loader.6475276/"


def test_scan_lists_on_off_sorted_and_skips_dirs(tmp_path):
    plugins = plugins_dir(tmp_path)
    _touch(plugins / "zeta.asi")
    _touch(plugins / "Adboards.asi")
    _touch(plugins / "borderless.ASI.Disabled")
    _touch(plugins / "notes.txt")
    _touch(plugins / "loader.ini")
    (plugins / "folder.asi").mkdir()
    assert [(e.name, e.enabled) for e in scan(tmp_path)] == [
        ("Adboards", True),
        ("borderless", False),
        ("zeta", True),
    ]


def test_scan_missing_plugins_folder_is_empty(tmp_path):
    assert scan(tmp_path) == []


def test_ini_lookup_plugins_first_then_game_root_case_insensitive(tmp_path):
    plugins = plugins_dir(tmp_path)
    _touch(plugins / "Adboards.asi")
    _touch(plugins / "ADBOARDS.ini", b"")
    _touch(tmp_path / "Adboards.ini", b"")
    _touch(plugins / "Ext.asi.disabled")
    _touch(tmp_path / "ext.ini", b"")
    _touch(plugins / "None.asi")
    entries = _by_name(tmp_path)
    assert entries["Adboards"].ini_path == plugins / "ADBOARDS.ini"
    assert entries["Ext"].ini_path == tmp_path / "ext.ini"
    assert entries["None"].ini_path is None


def test_conflict_when_both_forms_exist(tmp_path):
    plugins = plugins_dir(tmp_path)
    _touch(plugins / "X.asi")
    _touch(plugins / "X.asi.disabled")
    entries = scan(tmp_path)
    assert len(entries) == 1
    entry = entries[0]
    assert (entry.name, entry.enabled, entry.conflict, entry.path) == ("X", True, True, plugins / "X.asi")
    with pytest.raises(FileExistsError):
        set_enabled(entry, False)
    assert (plugins / "X.asi").exists() and (plugins / "X.asi.disabled").exists()


def test_set_enabled_renames_both_ways(tmp_path):
    plugins = plugins_dir(tmp_path)
    _touch(plugins / "Adboards.asi")
    entry = _by_name(tmp_path)["Adboards"]
    assert set_enabled(entry, True) == plugins / "Adboards.asi"

    new_path = set_enabled(entry, False)
    assert new_path == plugins / "Adboards.asi.disabled"
    assert new_path.exists() and not (plugins / "Adboards.asi").exists()

    entry = _by_name(tmp_path)["Adboards"]
    assert entry.enabled is False
    assert set_enabled(entry, True) == plugins / "Adboards.asi"
    assert (plugins / "Adboards.asi").exists()


def test_set_enabled_keeps_mixed_case_extension_stem(tmp_path):
    plugins = plugins_dir(tmp_path)
    _touch(plugins / "Foo.ASI")
    entry = _by_name(tmp_path)["Foo"]
    off = set_enabled(entry, False)
    assert off.name.lower() == "foo.asi.disabled"
    entry = _by_name(tmp_path)["Foo"]
    on = set_enabled(entry, True)
    assert on.name.lower() == "foo.asi" and on.exists()


def test_is_loader_installed(tmp_path):
    assert is_loader_installed(tmp_path) is False
    _touch(tmp_path / "winmm.dll", b"MZ some other winmm proxy")
    assert is_loader_installed(tmp_path) is False
    _touch(tmp_path / "winmm.dll", b"MZ\x00\x00" + "FIFA Plugin Loader".encode("utf-16-le") + b"\x00\x00")
    assert is_loader_installed(tmp_path) is True


def test_empty_module_list_means_unknown(tmp_path):
    _touch(plugins_dir(tmp_path) / "A.asi")
    assert loaded_states(scan(tmp_path), [], set()) == {"A": None}


def test_loaded_states(tmp_path):
    plugins = plugins_dir(tmp_path)
    for name in ("A.asi", "B.asi", "C.asi.disabled", "D.asi", "E.asi.disabled"):
        _touch(plugins / name)
    entries = scan(tmp_path)
    modules = [
        str(plugins / "a.ASI").upper(),
        str(plugins / "E.asi"),
        r"C:\other\B.asi",
    ]
    assert loaded_states(entries, modules, {"D"}) == {
        "A": True,
        "B": False,
        "C": None,
        "D": None,
        "E": True,
    }
