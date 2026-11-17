"""Dashboard substitutions/bench through dinput8 L9 (app_ui + l9_extender), without Tk."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from server16_py import l9_extender as l9
from server16_py.app_settings import SettingsMixin
from server16_py.app_ui import UIMixin

INI = "[Ersatzbank]\nAktiv=1\nBank=12\nMinSpieler=18\n\n[Wechsel]\nAktiv=1\nAnzahl=5\nErzwingen=1\n"


class _Var:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class _Widget:
    def __init__(self):
        self.disabled = False
        self.packed = False
        self.text = ""

    def state(self, spec):
        self.disabled = spec == ["disabled"]

    def pack(self, **_kw):
        self.packed = True

    def pack_forget(self):
        self.packed = False

    def configure(self, **kw):
        self.text = kw.get("text", self.text)


class FakeApp(UIMixin):
    def __init__(self, game_dir: Path, legacy: bool = False):
        self.fifaEXE = str(game_dir / "fifa16.exe")
        self.settings = SimpleNamespace(legacy_features=legacy)
        self.legacy_features_var = _Var(legacy)
        self._substitution_legacy_frame = _Widget()
        self._substitution_l9_frame = _Widget()
        self.l9_subs_entry, self.l9_bench_entry, self.l9_confirm_button = _Widget(), _Widget(), _Widget()
        self.l9_subs_var, self.l9_bench_var = _Var(), _Var()
        self.extender_status_label = _Widget()
        self._extender_status = None
        self._l9_mode = False
        self._l9_game_running = False
        self._l9_save_message = ""
        self.displays: dict[str, str] = {}
        self.logs: list[str] = []
        self.scheduled = []

    def tr(self, key, **kwargs):
        return key + (repr(sorted(kwargs.items())) if kwargs else "")

    def _set_display(self, key, text):
        self.displays[key] = text

    def log(self, message, *args, **kwargs):
        self.logs.append(str(message))

    def after(self, ms, func):
        self.scheduled.append((ms, func))


def _install_l9(game_dir: Path, ini: str = INI) -> Path:
    (game_dir / l9.L9_INI_NAME).write_text(ini, encoding="utf-8")
    (game_dir / l9.L9_DLL_NAME).write_bytes(b"MZ dinput8_L9.ini")
    return game_dir / l9.L9_INI_NAME


class _StartupApp(SettingsMixin, FakeApp):
    """app.py order: widgets are built (fifaEXE unknown), THEN setuppaths() resolves the game."""

    def __init__(self, game_dir: Path):
        super().__init__(game_dir)
        del self.fifaEXE
        self.settings.fifa_exe = str(game_dir / "fifa16.exe")
        self.base_dir = self.resource_dir = game_dir
        self.assets_runtime = SimpleNamespace(cleanup_startup_adboard_files=lambda: None)

    def _load_module_states(self):
        pass

    def _update_audio_overview(self):
        pass


def test_startup_detects_l9_once_paths_are_resolved(tmp_path):
    _install_l9(tmp_path)
    app = _StartupApp(tmp_path)
    app._refresh_extender_state()            # what the widget builders do, before setuppaths
    assert not app._l9_mode_active() and app._substitution_legacy_frame.packed
    app.setuppaths(load_team_database=False)
    assert app._l9_mode_active()
    assert app._substitution_l9_frame.packed and not app._substitution_legacy_frame.packed
    assert app.l9_subs_var.get() == "5"


def test_without_l9_the_legacy_row_stays(tmp_path):
    app = FakeApp(tmp_path)
    app._refresh_extender_state()
    assert app._l9_mode is False
    assert app._substitution_legacy_frame.packed and not app._substitution_l9_frame.packed
    assert "extender.mode.legacy_no_l9" in app.extender_status_label.text
    assert not app._l9_mode_active()


def test_with_l9_the_new_row_shows_ini_values(tmp_path):
    _install_l9(tmp_path)
    app = FakeApp(tmp_path)
    app._refresh_extender_state()
    assert app._l9_mode_active()
    assert app._substitution_l9_frame.packed and not app._substitution_legacy_frame.packed
    assert (app.l9_subs_var.get(), app.l9_bench_var.get()) == ("5", "12")
    assert "extender.mode.l9" in app.extender_status_label.text
    assert "substitutions.l9.pending" in app.displays["l9_status"]   # no log yet


def test_legacy_switch_keeps_hook_and_warns_about_l9(tmp_path):
    _install_l9(tmp_path)
    app = FakeApp(tmp_path, legacy=True)
    app._refresh_extender_state()
    assert not app._l9_mode_active() and app._substitution_legacy_frame.packed
    assert app.displays["substitution_status"] == "substitutions.l9.legacy_conflict"
    app.legacy_features_var.set(False)
    app._toggle_legacy_features()
    assert app.settings.legacy_features is False and app._l9_mode_active()


def test_confirm_saves_both_values(tmp_path):
    ini_path = _install_l9(tmp_path)
    app = FakeApp(tmp_path)
    app._refresh_extender_state()
    app.l9_subs_var.set("4")
    app.l9_bench_var.set("11")
    app._confirm_l9_values()
    assert l9.read_values(ini_path) == l9.L9Values(True, 4, True, 11)
    assert "substitutions.l9.saved" in app.displays["l9_status"]
    assert "substitutions.l9.bench_high" in app.displays["l9_status"]


@pytest.mark.parametrize(("subs", "bench", "code"), [("9", "8", "subs_over_bench"), ("x", "8", "subs_range"),
                                                     ("3", "6", "bench_range")])
def test_confirm_rejects_invalid_values(tmp_path, subs, bench, code):
    ini_path = _install_l9(tmp_path)
    before = ini_path.read_bytes()
    app = FakeApp(tmp_path)
    app._refresh_extender_state()
    app.l9_subs_var.set(subs)
    app.l9_bench_var.set(bench)
    app._confirm_l9_values()
    assert ini_path.read_bytes() == before
    assert f"substitutions.l9.error.{code}" in app.displays["l9_status"]


def test_fields_lock_while_fifa_runs_and_reload_after(tmp_path):
    ini_path = _install_l9(tmp_path)
    app = FakeApp(tmp_path)
    app._refresh_extender_state()
    app.on_extender_game_running(True)
    assert app.l9_subs_entry.disabled and app.l9_bench_entry.disabled and app.l9_confirm_button.disabled
    assert "substitutions.l9.locked" in app.displays["l9_status"]
    app.l9_subs_var.set("2")
    app._confirm_l9_values()                      # ignored while running
    assert l9.read_values(ini_path).subs_count == 5
    # L9's log after the start, and the user edited the ini by hand meanwhile.
    (tmp_path / l9.L9_LOG_NAME).write_text(
        "[L9] Stand: L9-39 Wechsel @ exe+4B89094 gesetzt: 5 je Team\n"
        "[L9-38] ant.cbac: 1 Byte, sub_home_11_Config/sub_away_11_Config FEHLEN\n"
        "[L9-38] Bank 12 NICHT gesetzt - Bankplaetze fehlen\n", encoding="utf-8")
    ini_path.write_text(INI.replace("Anzahl=5", "Anzahl=6"), encoding="utf-8")
    app.on_extender_game_running(False)
    assert not app.l9_subs_entry.disabled and not app.l9_confirm_button.disabled
    assert app.l9_subs_var.get() == "6"
    status = app.displays["l9_status"]
    assert "substitutions.l9.applied" in status and "('bench', 7)" in status
    assert "substitutions.l9.cbac_missing" in status
