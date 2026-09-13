from __future__ import annotations

import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from types import SimpleNamespace

from server16_py.ini_file import SessionIniFile
from server16_py.settings_editor import SectionSpec, SettingsSectionFrame


def _tk_available() -> bool:
    try:
        root = tk.Tk()
        root.destroy()
        return True
    except tk.TclError:
        return False


_TK_AVAILABLE = _tk_available()


class FakeApp:
    """Minimal stand-in for Server16App -- just enough attributes for
    SettingsSectionFrame's kind="stadium" UI to construct and for
    save_entry() to run to completion."""

    def __init__(self, exedir: Path, ini: SessionIniFile) -> None:
        self.card = "#111111"
        self.card_soft = "#222222"
        self.bg = "#000000"
        self.fg = "#ffffff"
        self.muted = "#888888"
        self.accent = "#00ff00"
        self.gold = "#ffff00"
        self.error = "#ff0000"
        self.panel = "#333333"
        self.panel_alt = "#444444"
        self.exedir = exedir
        self.settings_ini = ini
        self.PitchMowsource = exedir / "FSW" / "PitchMowPattern"
        self.Nsource = exedir / "FSW" / "Nets"
        self.stadium_runtime = SimpleNamespace()

    def tr(self, translation_key: str, **kwargs) -> str:
        # Deliberately not named "key" -- save_entry() calls
        # self.tr("dialog.editor.saved", section=..., key=key), which would
        # collide with a same-named positional parameter here.
        return translation_key

    def apply_all_runtime(self) -> None:
        pass

    def refresh_modules(self) -> None:
        pass

    def log(self, *args, **kwargs) -> None:
        pass


@unittest.skipUnless(_TK_AVAILABLE, "requires a Tk display")
class StadiumEditorSaveGoalpostOverridesTests(unittest.TestCase):
    """Regression tests for the 2026-09-11 bug reported live: saving a
    stadium's Police/Pitch/Net/Goalpost from the "Stadium Settings" editor
    (Edit Stadium Assets) silently never wrote [stadiumgoalpost]/
    [stadiumgoalposttexture] -- and, worse, could silently drop the
    [stadium]/[comp] assignment itself. Root cause: SessionIniFile.
    delete_key() unconditionally reloads from disk before deleting (see
    ini_file.py), which discards any write() made earlier in the same save
    cycle that hasn't reached disk yet. save_entry() used to write() the
    [stadium] value, then call _save_stadium_goalpost_overrides(), which
    interleaved write()/delete_key() across two dicts -- whichever category
    happened to be "None" (the common case) triggered a delete_key() that
    wiped out everything written earlier in the very same save_entry() call.
    Fixed by splitting into a delete-only pass (_clear_stale_stadium_
    goalpost_overrides, called BEFORE the [stadium] write) and a write-only
    pass (_write_stadium_goalpost_overrides, called after), so no delete_key()
    call in this cycle ever has anything pending to discard.

    These tests build a REAL SettingsSectionFrame (kind="stadium") against a
    REAL SessionIniFile -- a lightweight fake ini (plain dict, no reload
    semantics) would hide this exact bug, which is how it shipped unnoticed
    the first time."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.exedir = Path(self._tmp.name)
        (self.exedir / "FSW").mkdir(parents=True)
        self.ini = SessionIniFile(self.exedir / "FSW" / "settings.ini")
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.app = FakeApp(self.exedir, self.ini)

    def make_stadium_frame(self) -> SettingsSectionFrame:
        spec = SectionSpec("stadium", "Team Stadiums", kind="stadium", directory="StadiumGBD")
        return SettingsSectionFrame(self.root, self.app, spec)

    def test_model_only_override_and_the_stadium_assignment_both_persist(self) -> None:
        frame = self.make_stadium_frame()
        frame.key_var.set("176")
        frame.assigned_stadium_list.insert("end", "Anfield")
        frame._stadium_params["Anfield"] = ("4", "0", "0")
        frame._stadium_goalpost["Anfield"] = "1"
        frame._stadium_goalpost_texture["Anfield"] = "None"
        frame.save_entry()

        reloaded = SessionIniFile(self.ini.path)
        self.assertEqual(reloaded.read("176", "stadium"), "Anfield,4,0,0")
        self.assertEqual(reloaded.read("Anfield", "stadiumgoalpost"), "1")
        self.assertFalse(reloaded.key_exists("Anfield", "stadiumgoalposttexture"))

    def test_texture_only_override_and_the_stadium_assignment_both_persist(self) -> None:
        frame = self.make_stadium_frame()
        frame.key_var.set("176")
        frame.assigned_stadium_list.insert("end", "Anfield")
        frame._stadium_params["Anfield"] = ("4", "0", "0")
        frame._stadium_goalpost["Anfield"] = "None"
        frame._stadium_goalpost_texture["Anfield"] = "Azul"
        frame.save_entry()

        reloaded = SessionIniFile(self.ini.path)
        self.assertEqual(reloaded.read("176", "stadium"), "Anfield,4,0,0")
        self.assertFalse(reloaded.key_exists("Anfield", "stadiumgoalpost"))
        self.assertEqual(reloaded.read("Anfield", "stadiumgoalposttexture"), "Azul")

    def test_neither_override_set_still_persists_the_stadium_assignment(self) -> None:
        # Both categories "None" -- two delete_key() calls in a row, right
        # after the [stadium] write, was the original reported failure mode.
        frame = self.make_stadium_frame()
        frame.key_var.set("176")
        frame.assigned_stadium_list.insert("end", "Anfield")
        frame._stadium_params["Anfield"] = ("4", "0", "0")
        frame._stadium_goalpost["Anfield"] = "None"
        frame._stadium_goalpost_texture["Anfield"] = "None"
        frame.save_entry()

        reloaded = SessionIniFile(self.ini.path)
        self.assertEqual(reloaded.read("176", "stadium"), "Anfield,4,0,0")


if __name__ == "__main__":
    unittest.main()
