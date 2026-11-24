"""Plugins tab logic (app_plugins.PluginsTabMixin), without Tk widgets."""
from __future__ import annotations

from pathlib import Path

from server16_py.app_plugins import PLUGINS_LOADED_CHECK_DELAY_MS, PluginsTabMixin
from server16_py.app_ui import UIMixin
from server16_py.plugin_loader import plugins_dir

LOADER_BYTES = b"MZ" + "FIFA Plugin Loader".encode("utf-16-le")


class FakeMemory:
    def __init__(self) -> None:
        self.open = False
        self.modules: list[str] = []

    def is_open(self) -> bool:
        return self.open

    def list_module_paths(self) -> list[str]:
        return list(self.modules)


class FakeApp(PluginsTabMixin, UIMixin):
    def __init__(self, game_dir: Path | None) -> None:
        self.fifaEXE = str(game_dir / "fifa16.exe") if game_dir is not None else "default"
        self.memory = FakeMemory()
        self._plugins_toggled: set[str] = set()
        self._plugins_game_running = False
        self._plugins_icons_ready = False
        self._plugins_rows_frame = None
        self.logged: list[str] = []
        self.scheduled: list[tuple[int, object]] = []
        self.refreshes = 0

    def log(self, message, *args, **kwargs) -> None:
        self.logged.append(message)

    def tr(self, key, **kwargs):
        return key

    def after(self, delay, callback):
        self.scheduled.append((delay, callback))

    def refresh_plugins_tab(self) -> None:
        self.refreshes += 1


def _game(tmp_path: Path, loader: bool = True) -> Path:
    plugins = plugins_dir(tmp_path)
    plugins.mkdir()
    (plugins / "A.asi").write_bytes(b"MZ")
    (plugins / "a.ini").write_bytes(b"[x]\nk=1\n")
    (plugins / "B.asi").write_bytes(b"MZ")
    if loader:
        (tmp_path / "winmm.dll").write_bytes(LOADER_BYTES)
    return tmp_path


def _rows(view):
    return [(r.name, r.enabled, r.has_ini, r.loaded) for r in view.rows]


def test_main_tab_order():
    assert [key for _attr, key in UIMixin._MAIN_TAB_ORDER] == [
        "tab.dashboard", "tab.kits", "tab.chants", "tab.camera", "tab.setup",
        "tab.plugins", "tab.settings", "tab.gamepads", "tab.logs",
    ]
    assert dict(UIMixin._MAIN_TAB_ORDER)["plugins_tab"] == "tab.plugins"


def test_view_model_no_game_dir():
    view = FakeApp(None)._plugins_view_model()
    assert view.state == "no_game_dir" and view.rows == [] and view.folder is None


def test_view_model_rows_without_fifa_have_no_icons(tmp_path):
    app = FakeApp(_game(tmp_path))
    view = app._plugins_view_model()
    assert view.state == "ok" and view.loader_installed is True
    assert view.folder == plugins_dir(tmp_path)
    assert _rows(view) == [("A", True, True, None), ("B", True, False, None)]


def test_view_model_loaded_icons_while_fifa_runs(tmp_path):
    app = FakeApp(_game(tmp_path))
    app._plugins_game_running = True
    app._plugins_icons_ready = True
    app.memory.open = True
    app.memory.modules = [str(plugins_dir(tmp_path) / "A.asi")]
    assert _rows(app._plugins_view_model()) == [("A", True, True, True), ("B", True, False, False)]


def test_no_icons_until_the_delayed_check_runs(tmp_path):
    app = FakeApp(_game(tmp_path))
    app.on_plugins_game_running(True)
    app.memory.open = True
    app.memory.modules = [str(plugins_dir(tmp_path) / "A.asi")]   # B not loaded *yet*
    app._toggle_plugin("A")
    app._toggle_plugin("A")
    assert all(r.loaded is None for r in app._plugins_view_model().rows)
    (_delay, callback), = app.scheduled
    callback()
    # A is loaded (✔ even though it was switched); B is ON, never loaded -> ✖ now that it's ready
    assert {r.name: r.loaded for r in app._plugins_view_model().rows} == {"A": True, "B": False}
    app.on_plugins_game_running(False)
    app.on_plugins_game_running(True)
    assert all(r.loaded is None for r in app._plugins_view_model().rows)


def test_row_carries_the_ini_path(tmp_path):
    app = FakeApp(_game(tmp_path))
    rows = {r.name: r for r in app._plugins_view_model().rows}
    assert rows["A"].ini_path == plugins_dir(tmp_path) / "a.ini"
    assert rows["B"].ini_path is None


def test_running_but_not_attached_shows_no_icons(tmp_path):
    app = FakeApp(_game(tmp_path))
    app._plugins_game_running = True
    assert all(r.loaded is None for r in app._plugins_view_model().rows)


def test_loader_missing_flag(tmp_path):
    assert FakeApp(_game(tmp_path, loader=False))._plugins_view_model().loader_installed is False


def test_second_loader_warning_in_view_model(tmp_path):
    game = _game(tmp_path)
    assert FakeApp(game)._plugins_view_model().second_loader is None
    (game / "d3d11.dll").write_bytes(b"MZ")
    assert FakeApp(game)._plugins_view_model().second_loader == game / "d3d11.dll"


def test_no_second_loader_warning_without_plugin_loader(tmp_path):
    game = _game(tmp_path, loader=False)
    (game / "d3d11.dll").write_bytes(b"MZ")
    assert FakeApp(game)._plugins_view_model().second_loader is None


def test_second_loader_warning_key_in_all_locales():
    import json

    locales = Path(__file__).resolve().parents[1] / "server16_py" / "locales"
    for lang in ("en", "es", "pt"):
        text = json.loads((locales / f"{lang}.json").read_text(encoding="utf-8"))["warning.plugins.second_loader"]
        assert "{path}" in text and "d3d11.dll" in text and "winmm.dll" in text


def test_toggle_renames_logs_and_refreshes(tmp_path):
    app = FakeApp(_game(tmp_path))
    app._toggle_plugin("B")
    assert (plugins_dir(tmp_path) / "B.asi.disabled").exists()
    assert app.logged == ["Plugins: B.asi -> B.asi.disabled"]
    assert app.refreshes == 1
    assert app._plugins_toggled == set()   # FIFA not running: nothing to hide


def test_toggle_while_running_hides_icon_until_restart(tmp_path):
    app = FakeApp(_game(tmp_path))
    app.on_plugins_game_running(True)
    app._plugins_icons_ready = True
    app.memory.open = True
    app.memory.modules = [str(plugins_dir(tmp_path) / "A.asi")]
    app._toggle_plugin("B")
    app._toggle_plugin("B")
    assert app._plugins_toggled == {"B"}
    assert {r.name: r.loaded for r in app._plugins_view_model().rows}["B"] is None

    app.on_plugins_game_running(False)
    app.on_plugins_game_running(True)
    assert app._plugins_toggled == set()


def test_game_start_schedules_one_delayed_check(tmp_path):
    app = FakeApp(_game(tmp_path))
    app.on_plugins_game_running(True)
    app.on_plugins_game_running(True)   # poll_process repeats it every 500 ms
    assert [delay for delay, _ in app.scheduled] == [PLUGINS_LOADED_CHECK_DELAY_MS]
    assert PLUGINS_LOADED_CHECK_DELAY_MS == 10000
    app.on_plugins_game_running(False)
    assert app.refreshes == 1 and app._plugins_game_running is False
