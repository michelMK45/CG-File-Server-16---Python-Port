from __future__ import annotations

import json
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from types import SimpleNamespace

from server16_py.app_localization import LocalizationMixin
from server16_py.app_settings import SettingsMixin
from server16_py.app_ui import UIMixin
from server16_py.ini_file import SessionIniFile
from server16_py.localization import SUPPORTED_LANGUAGES, LocalizationManager
from server16_py.module_catalog import (
    INI_MODULE_NAMES,
    MODULE_CATEGORIES,
    MODULE_SLUGS,
    module_category_key,
    module_label_key,
    module_tooltip_key,
)

LOCALES_DIR = Path(__file__).resolve().parents[1] / "server16_py" / "locales"


def _tk_available() -> bool:
    try:
        root = tk.Tk()
        root.destroy()
        return True
    except tk.TclError:
        return False


_TK_AVAILABLE = _tk_available()


class ModuleCatalogTests(unittest.TestCase):
    def test_categories_group_the_modules_as_the_dashboard_card_shows_them(self) -> None:
        self.assertEqual(
            [(category, list(names)) for category, names in MODULE_CATEGORIES],
            [
                ("stadium", ["Stadium", "EntranceCam", "Goalposts", "StadiumNet"]),
                ("ui", ["TvLogo", "ScoreBoard", "StadiumName", "Movies"]),
                ("sound", ["Chants", "AwayChants", "AwayClubSong", "TeamEntrance"]),
                ("game", ["Ball", "Adboard", "Referee", "Wipe"]),
                ("other", ["Autorun", "DiscordRPC"]),
            ],
        )

    def test_every_module_is_in_exactly_one_category_and_has_a_slug(self) -> None:
        listed = [name for _category, names in MODULE_CATEGORIES for name in names]
        self.assertEqual(len(listed), len(set(listed)))
        self.assertEqual(set(listed), set(MODULE_SLUGS))

    def test_ini_module_names_are_every_module_but_discord_rpc(self) -> None:
        self.assertNotIn("DiscordRPC", INI_MODULE_NAMES)
        self.assertEqual(set(INI_MODULE_NAMES), set(MODULE_SLUGS) - {"DiscordRPC"})

    def test_every_label_tooltip_and_category_heading_exists_in_every_language(self) -> None:
        for language in SUPPORTED_LANGUAGES:
            catalog = json.loads((LOCALES_DIR / f"{language}.json").read_text(encoding="utf-8"))
            keys = [module_label_key(name) for name in MODULE_SLUGS]
            keys += [module_tooltip_key(name) for name in MODULE_SLUGS]
            keys += [module_category_key(category) for category, _names in MODULE_CATEGORIES]
            missing = [key for key in keys if not str(catalog.get(key, "")).strip()]
            self.assertEqual(missing, [], f"{language}.json is missing module strings")


class LoadModuleStatesTests(unittest.TestCase):
    """Goalposts joined the Modules list after existing installs were set up: with no
    [Modules] Goalposts entry yet it must come up ON, so a stadium that already has a
    [stadiumgoalpost] pick keeps its goalposts after the upgrade."""

    def make_app(self, ini_path: Path) -> SimpleNamespace:
        return SimpleNamespace(
            settings_ini=SessionIniFile(ini_path),
            fifaEXE="C:/FIFA16/fifa16.exe",
            exedir=ini_path.parent,
            _discord_rpc_enabled=False,
            discord_rpc=SimpleNamespace(is_connected=lambda: False, connect=lambda: True, disconnect=lambda: None),
            module_vars={},
            module_states={},
            log=lambda *args, **kwargs: None,
        )

    def test_goalposts_defaults_to_on_when_the_ini_has_no_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = self.make_app(Path(tmp) / "settings.ini")
            SettingsMixin._load_module_states(app)
            self.assertTrue(app.module_states["Goalposts"])
            self.assertEqual(app.settings_ini.read("Goalposts", "Modules"), "1")

    def test_an_explicit_off_is_kept(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ini_path = Path(tmp) / "settings.ini"
            ini_path.write_text("[Modules]\nGoalposts=0\n", encoding="utf-8")
            app = self.make_app(ini_path)
            SettingsMixin._load_module_states(app)
            self.assertFalse(app.module_states["Goalposts"])

    def test_stadium_name_defaults_to_on_when_absent_but_an_explicit_off_is_kept(self) -> None:
        # The switch only started gating the stadium-name patch recently: an old settings.ini
        # without the entry must keep showing the custom name, while a user who set it to 0
        # gets exactly what they set.
        with tempfile.TemporaryDirectory() as tmp:
            app = self.make_app(Path(tmp) / "settings.ini")
            SettingsMixin._load_module_states(app)
            self.assertTrue(app.module_states["StadiumName"])
        with tempfile.TemporaryDirectory() as tmp:
            ini_path = Path(tmp) / "settings.ini"
            ini_path.write_text("[Modules]\nStadiumName=0\n", encoding="utf-8")
            app = self.make_app(ini_path)
            SettingsMixin._load_module_states(app)
            self.assertFalse(app.module_states["StadiumName"])

    def test_autorun_is_never_switched_on_by_default(self) -> None:
        # It launches FIFA at startup, so unlike the other late modules a missing entry means off.
        with tempfile.TemporaryDirectory() as tmp:
            app = self.make_app(Path(tmp) / "settings.ini")
            SettingsMixin._load_module_states(app)
            self.assertFalse(app.module_states["Autorun"])

    def test_every_listed_module_gets_a_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = self.make_app(Path(tmp) / "settings.ini")
            SettingsMixin._load_module_states(app)
            self.assertTrue(set(INI_MODULE_NAMES) <= set(app.module_states))


@unittest.skipUnless(_TK_AVAILABLE, "Tk is not available")
class ModulesCardTests(unittest.TestCase):
    """The real UIMixin._build_modules_card on a minimal Tk host."""

    class Host(LocalizationMixin, UIMixin, tk.Tk):
        def __init__(self, language: str) -> None:
            super().__init__()
            self.withdraw()
            self.localization = LocalizationManager(LOCALES_DIR, language)
            self.module_vars, self.module_checks, self.module_category_labels = {}, {}, {}
            self._discord_rpc_enabled = False
            self._configure_theme()

        def _on_module_toggle(self, name, var) -> None:
            pass

    def build(self, language: str = "en") -> "ModulesCardTests.Host":
        host = self.Host(language)
        self.addCleanup(host.destroy)
        holder = tk.Frame(host)
        holder.pack()
        host._build_modules_card(holder, 0)
        host.update_idletasks()
        return host

    def test_each_category_gets_a_heading_and_its_own_switches(self) -> None:
        host = self.build()
        self.assertEqual(set(host.module_category_labels), {category for category, _names in MODULE_CATEGORIES})
        for category, names in MODULE_CATEGORIES:
            block = host.module_category_labels[category].master
            for name in names:
                self.assertIs(host.module_checks[name].master, block, f"{name} is not under its {category} heading")
        self.assertEqual(host.module_category_labels["stadium"].cget("text"), "Stadium")
        self.assertEqual(host.module_checks["EntranceCam"].cget("text"), "Entrance Camera")
        self.assertEqual(host.module_checks["TeamEntrance"].cget("text"), "Team Entrance Anthem")

    def test_every_switch_has_a_tooltip_and_a_variable(self) -> None:
        host = self.build()
        for name in MODULE_SLUGS:
            self.assertIn(name, host.module_vars)
            self.assertTrue(host.module_checks[name].bind("<Enter>"), f"{name} has no tooltip bound")

    def test_relabelling_follows_the_language(self) -> None:
        host = self.build("es")
        host._apply_module_labels()
        self.assertEqual(host.module_category_labels["game"].cget("text"), "Juego")
        host.localization.set_language("en")
        host._apply_module_labels()
        self.assertEqual(host.module_category_labels["game"].cget("text"), "Game")
        self.assertEqual(host.module_checks["Goalposts"].cget("text"), "Goalposts")


if __name__ == "__main__":
    unittest.main()
