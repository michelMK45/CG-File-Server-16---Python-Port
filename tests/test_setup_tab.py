from __future__ import annotations

import json
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from types import SimpleNamespace

from server16_py.app_ui import UIMixin


def _tk_available() -> bool:
    try:
        root = tk.Tk()
        root.destroy()
        return True
    except tk.TclError:
        return False


_TK_AVAILABLE = _tk_available()
LOCALES = Path(__file__).resolve().parent.parent / "server16_py" / "locales"


class FakeSetupApp(UIMixin):
    """The real Setup tab builder + refresh on a minimal host."""

    def __init__(self, root: tk.Tk, exedir: Path) -> None:
        self.root = root
        for name, value in dict(
            bg="#000000", panel="#333333", panel_alt="#444444", card="#111111", card_soft="#222222",
            fg="#ffffff", muted="#888888", accent="#00ff00", gold="#ffff00", success="#00ff00", error="#ff0000",
        ).items():
            setattr(self, name, value)
        self.settings = SimpleNamespace(custom_kit_numbers=False)
        self._setup_status_vars: dict = {}
        self._setup_install_vars: dict = {}
        self.exedir = exedir
        self.fifaEXE = str(exedir / "fifa16.exe")
        fsw = exedir / "FSW"
        self.Psource, self.Nsource, self.PitchMowsource = fsw / "Police", fsw / "Nets", fsw / "PitchMowPattern"
        self.Pdest = self.Ndest = self.PitchMowdest = exedir / "data"
        self.TVdata = self.Scoredata = exedir / "data"
        self.targetpath = self.TVLogo = self.ScoreBoard = self.Movies = exedir / "GBD"

    def tr(self, key: str, **_kwargs) -> str:
        return key

    def _card(self, parent, _title_key, _subtitle_key=""):
        return tk.Frame(parent)

    def _on_setup_mousewheel(self, _event=None) -> None:
        pass

    def _lua_assets_missing_files(self):
        return None

    def _update_setup_notice(self) -> None:
        pass


@unittest.skipUnless(_TK_AVAILABLE, "requires a Tk display")
class SetupGeneralTabTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.exedir = Path(self._tmp.name)
        (self.exedir / "FSW").mkdir()
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.app = FakeSetupApp(self.root, self.exedir)
        self.app._build_setup_general_tab(tk.Frame(self.root))

    def labels(self) -> list[str]:
        found: list[str] = []

        def walk(widget: tk.Misc) -> None:
            if isinstance(widget, tk.Label):
                found.append(str(widget.cget("text")))
            for child in widget.winfo_children():
                walk(child)

        walk(self.root)
        return found

    def test_extras_are_split_into_assets_and_rev_mod_sections_all_unchecked(self) -> None:
        labels = self.labels()
        assets = labels.index("setup.section.extra_assets")
        revmod = labels.index("setup.section.extra_revmod")
        for item in ("setup.item.fsw_goalpost", "setup.item.fsw_camera", "setup.item.fsw_netmesh"):
            self.assertTrue(assets < labels.index(item) < revmod, item)
        for item in ("setup.item.revmod_lua", "setup.item.custom_kit_numbers"):
            self.assertGreater(labels.index(item), revmod, item)
        for key in ("fsw_goalpost", "fsw_camera", "fsw_netmesh", "revmod_lua"):
            self.assertFalse(self.app._setup_install_vars[key].get(), key)

    def test_every_checkbox_is_in_the_left_column_and_status_info_on_the_right(self) -> None:
        columns = self.app._setup_canvas_body.winfo_children()
        left, right = sorted(columns, key=lambda f: int(f.grid_info()["column"]))

        def checkbuttons(frame: tk.Misc) -> list[tk.Checkbutton]:
            out = [frame] if isinstance(frame, tk.Checkbutton) else []
            for child in frame.winfo_children():
                out += checkbuttons(child)
            return out

        self.assertEqual(len(checkbuttons(left)), len(self.app._setup_install_vars))
        self.assertEqual(checkbuttons(right), [])

        def section_titles(frame: tk.Misc) -> list[str]:
            return [str(w.cget("text")) for w in frame.winfo_children()
                    if isinstance(w, tk.Label) and str(w.cget("text")).startswith("setup.section.")]

        self.assertEqual(section_titles(left), [
            "setup.section.prerequisites", "setup.section.fsw_sources",
            "setup.section.extra_assets", "setup.section.extra_revmod",
        ])
        self.assertEqual(section_titles(right), ["setup.section.user_folders", "setup.section.dest_folders"])
        self.assertIn("dest_lua", self.app._setup_status_vars)

    def test_settings_ini_is_unchecked_when_the_file_exists(self) -> None:
        (self.exedir / "FSW" / "settings.ini").write_text("[Modules]\n", encoding="utf-8")
        self.app.refresh_setup_tab()
        self.assertFalse(self.app._setup_install_vars["settings_ini"].get())

    def test_settings_ini_is_checked_only_while_the_file_is_missing(self) -> None:
        var = self.app._setup_install_vars["settings_ini"]
        self.app.refresh_setup_tab()
        self.assertTrue(var.get())
        (self.exedir / "FSW" / "settings.ini").write_text("[Modules]\n", encoding="utf-8")
        self.app.refresh_setup_tab()
        self.assertFalse(var.get())

    def test_a_manual_choice_survives_a_plain_refresh(self) -> None:
        (self.exedir / "FSW" / "settings.ini").write_text("[Modules]\n", encoding="utf-8")
        self.app.refresh_setup_tab()
        var = self.app._setup_install_vars["settings_ini"]
        var.set(True)
        self.app.refresh_setup_tab()
        self.assertTrue(var.get())


class SetupLocaleTests(unittest.TestCase):
    def test_new_setup_strings_exist_in_every_language(self) -> None:
        for lang in ("en", "es", "pt"):
            catalog = json.loads((LOCALES / f"{lang}.json").read_text(encoding="utf-8"))
            for key in ("setup.section.extra_assets", "setup.section.extra_revmod", "setup.item.fsw_netmesh"):
                self.assertTrue(catalog.get(key), f"{lang}: {key}")


if __name__ == "__main__":
    unittest.main()
