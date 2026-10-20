from __future__ import annotations

import gc
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from server16_py import app_overlay
from server16_py import d3d_injector
from server16_py import kit_classic as kc
from server16_py.app_overlay import OverlayMixin
from server16_py.d3d_injector import D3DOverlayInjector
from server16_py.kit_mixer import KIT_TYPES
from server16_py.locales_data import LOCALE_CATALOGS
from server16_py.win32_types import (
    VK_F12, VK_LEFT, VK_RETURN, VK_RIGHT, XINPUT_GAMEPAD_A, XINPUT_GAMEPAD_BACK, XINPUT_GAMEPAD_DPAD_LEFT,
    XINPUT_GAMEPAD_RIGHT_SHOULDER, XINPUT_GAMEPAD_START,
)

EN = LOCALE_CATALOGS["en"]
SUPPORTED_PLAYER_LUA = "\n".join(
    f"function {name}(a,b,c)\nend" for name in kc.REQUIRED_PLAYER_LUA_FUNCTIONS
) + "\n"
KITS = 4   # index of the Kits tab


class FakeInjector:
    """Records what the overlay pushes into shared memory; every other setter
    is accepted and ignored."""

    def __init__(self) -> None:
        self.header = ""
        self.items: list[str] = []
        self.dashboard: list[str] = []
        self.preview_paths: list[str] = []
        self.kit_editor: dict | None = None
        self.kit_editor_writes = 0
        self.event = (0, 0, 0)

    def set_kit_editor(self, state) -> None:
        self.kit_editor = state
        self.kit_editor_writes += 1

    def get_menu_event(self):
        return self.event

    def set_list_header(self, header: str) -> None:
        self.header = header

    def set_menu_content(self, items, _sel, _scroll, **_kwargs) -> None:
        self.items = list(items)

    def set_dashboard_content(self, items) -> None:
        self.dashboard = list(items)

    def set_preview_image(self, path: str) -> None:
        self.preview_paths.append(path)

    def get_menu_metrics(self):
        return 1, 0, 0, 20

    def get_filter_grid_cols(self) -> int:
        return 0

    def __getattr__(self, _name):
        return lambda *_a, **_k: None


class FakeTab:
    def __init__(self) -> None:
        self.invalidated: list[int] = []

    def invalidate(self, team: int) -> None:
        self.invalidated.append(team)


class FakeOverlayApp(OverlayMixin):
    """Real OverlayMixin (menu content, wizard steps, the whole input tick) on a
    minimal host, with a REAL KitClassicRuntime on a temporary FIFA folder."""

    def __init__(self, root: Path) -> None:
        self.exedir = root / "fifa"
        self.base_dir = root / "app"
        self.fifaEXE = str(self.exedir / "fifa16.exe")
        self.logs: list[str] = []
        self.toasts: list[tuple] = []
        self.kit_classic = kc.KitClassicRuntime(self)
        self.kit_classic_view = FakeTab()
        # Custom Kits' kit set list: no sets, and its "Default" entry finds no
        # kit UI thumbnail (the preview falls back to the placeholder).
        self.kit_mixer = SimpleNamespace(
            list_kit_sets=lambda _team, _kittype: [],
            live_kitui_path=lambda _team, _kittype: root / "missing_kitui.dds",
            backup_path=lambda path: Path(f"{path}.original"),
        )
        self.kitmix_kittype_labels = {key: key.capitalize() for key in KIT_TYPES}
        self.team_names = {"383": "Palmeiras", "100": "Santos"}
        self.HID, self.AID = "383", "100"
        self.performance = False
        self.overlay_performance_mode_var = SimpleNamespace(get=lambda: self.performance)
        self.movie_preview_runtime = SimpleNamespace(stop=lambda: None)
        self.show_overlay_var = SimpleNamespace(get=lambda: True)
        self.user32 = SimpleNamespace(GetForegroundWindow=lambda: 1)
        self.labels: dict = {}
        self.info_labels: dict = {}
        self._stadium_assignment_type = self._scoreboard_assignment_type = ""
        self._tvlogo_assignment_type = self._movie_assignment_type = ""
        self._home_crest_png_large = self._home_crest_png = "home.png"
        self._away_crest_png_large = self._away_crest_png = "away.png"
        self._d3d_injector = FakeInjector()
        self._fifa_hwnd = 1
        self._stadium_picker_pending = False

        # Input simulation, read by the overrides below.
        self.keys_held: set[int] = set()
        self.key_edges: set[int] = set()
        self.hotkey_edges: set[int] = set()
        self.gp_edge = 0
        self.gp_raw = 0

        # Overlay state, as Server16App.__init__ sets it.
        for name in ("up", "down", "left", "right", "escape", "pgup", "pgdn", "home", "end", "enter"):
            setattr(self, f"_overlay_{name}_down", False)
        self._overlay_mouse_wheel_steps = 0
        self._overlay_input_mode = "keyboard"
        self._overlay_b_close_pending = False
        self._overlay_toggle_ready_at = 0.0
        self._overlay_tab_ready_at = 0.0
        self._overlay_gp_prev_buttons = 0
        for name in ("start", "back", "left", "right", "y"):
            setattr(self, f"_overlay_gp_{name}_pressed_at", 0.0)
        self._overlay_gp_start_hold_latched = False
        self._overlay_gp_back_hold_latched = False
        self._overlay_f12_held_since = 0.0
        self._overlay_f12_hold_latched = False
        self._overlay_gp_y_hold_latched = False
        self._overlay_gp_rstick_repeat_at = 0.0
        self._overlay_gp_lstick_repeat_at = 0.0
        self._overlay_gp_lstick_prev_in_zone = False
        self._overlay_gp_lstick_lr_repeat_at = 0.0
        self._overlay_gp_lstick_lr_prev_in_zone = False
        self._overlay_blocked_key_down: set[int] = set()
        self._overlay_key_edge_pending: set[int] = set()
        self._overlay_tab_names = ["scoreboards", "stadiums", "movies", "tvlogos", "kits"]
        self._overlay_tab_index = 0
        self._overlay_selected_scope = None
        self._overlay_selected_kittype = None
        self._overlay_kit_sets_cache: list = []
        self._overlay_kit_preview_cache: dict[str, str] = {}
        self._overlay_kit_preview_pending: set[str] = set()
        self._overlay_kit_mode_last = "team"
        self._overlay_team_kit_sides = None
        self._overlay_team_kit_rows: list = []
        self._overlay_team_kit_repeat_at = 0.0
        self._overlay_team_kit_art: dict = {}
        self._overlay_team_kit_art_dirty = False
        self._overlay_team_kit_jobs: list = []
        self._overlay_team_kit_job_keys: set = set()
        self._overlay_team_kit_job_lock = threading.Lock()
        self._overlay_team_kit_worker = None
        self._rmlui_menu_event_last_seq = 0
        self._overlay_list_header = ""
        self._overlay_scope_phase = True
        self._overlay_filter_phase = False
        self._overlay_stadium_country_filter: set[str] = set()
        self._overlay_stadium_sort_desc = False
        self._overlay_stadium_thumb_cache: dict[str, str] = {}
        self._d3d_menu_visible = True
        self._overlay_items: list[str] = []
        self._overlay_item_checked: list[bool] = []
        self._overlay_item_count = 0
        self._overlay_selected_index = 0
        self._overlay_scroll_offset = 0
        self._overlay_window_base = 0
        self._overlay_visible_rows = 20
        self._overlay_filter_grid_cols = 0
        self._overlay_nav_repeat_at = 0.0
        self._clear_overlay_wizard_state()

    # --- host methods ---
    def tr(self, key: str, **kwargs) -> str:
        text = EN.get(key, key)
        return text.format(**kwargs) if kwargs else text

    def display_value(self, key: str, fallback=None, **_kwargs) -> str:
        return fallback or key

    def log(self, message: str, *_args, **_kwargs) -> None:
        self.logs.append(message)

    def _resolve_team_name(self, team_id: str):
        return self.team_names.get(team_id)

    def _show_toast_notification(self, title: str, body: str = "", style: int = 0, icon: str = "") -> int:
        self.toasts.append((title, body, style))
        return 0

    # --- the parts of the input tick this test doesn't exercise ---
    def _ensure_d3d_overlay_injected(self, log_errors: bool = True) -> bool:
        return True

    def _refresh_fifa_hwnd_if_needed(self, _now: float) -> None:
        pass

    def _install_hotkey_poll_thread(self) -> None:
        pass

    def _install_gamepad_poll_thread(self) -> None:
        pass

    def _sync_rmlui_menu_mouse_feed(self, *_args) -> None:
        pass

    def _handle_rmlui_menu_event(self, *_args) -> None:
        pass

    def _best_effort_neutralize_game_keys(self) -> None:
        pass

    def _install_mouse_wheel_hook(self) -> None:
        pass

    def _install_keyboard_hook(self) -> None:
        pass

    def _uninstall_mouse_wheel_hook(self) -> None:
        pass

    def _uninstall_keyboard_hook(self) -> None:
        pass

    def stadium_picker_awaiting_selection(self) -> bool:
        return False

    def _is_overlay_key_down(self, vk: int, _foreground: bool) -> bool:
        return vk in self.keys_held

    def _consume_overlay_key_edge(self, vk: int) -> bool:
        if vk in self.key_edges:
            self.key_edges.discard(vk)
            return True
        return False

    def _consume_hotkey_edge(self, vk: int) -> bool:
        if vk in self.hotkey_edges:
            self.hotkey_edges.discard(vk)
            return True
        return False

    def _consume_gamepad_state(self):
        return self.gp_edge, self.gp_raw, 0, 0, 0, 0

    # --- test drivers ---
    @property
    def inj(self) -> FakeInjector:
        return self._d3d_injector

    def open_kits_tab(self) -> None:
        self._set_overlay_tab(KITS, "test")

    def pick(self, label: str) -> None:
        self._overlay_selected_index = self._overlay_items.index(label)
        self._activate_overlay_selected_item("test")

    def press_key(self, vk: int) -> None:
        """One real input tick with the key going down, one with it back up."""
        self.keys_held.add(vk)
        self.key_edges.add(vk)
        self._sync_d3d_menu_input()
        self.keys_held.discard(vk)
        self._sync_d3d_menu_input()

    def press_button(self, bit: int) -> None:
        self.gp_edge = self.gp_raw = bit
        self._sync_d3d_menu_input()
        self.gp_edge = self.gp_raw = 0
        self._sync_d3d_menu_input()

    def click(self, kind: int, index: int) -> None:
        """A click the DLL reported (menu_event_*), handled by the real handler
        (the input tick's own call to it is stubbed out above)."""
        seq = self.inj.event[0] + 1
        self.inj.event = (seq, kind, index)
        OverlayMixin._handle_rmlui_menu_event(self, self.inj, 0.0)

    def wait_for_kit_art(self, timeout: float = 15.0) -> None:
        """Lets the editor's drawing worker finish, then one input tick writes
        the screen again with what it drew."""
        deadline = time.monotonic() + timeout
        worker = self._overlay_team_kit_worker
        while worker is not None and worker.is_alive() and time.monotonic() < deadline:
            worker.join(timeout=0.05)
            worker = self._overlay_team_kit_worker
        self._sync_d3d_menu_input()


class OverlayTeamKitsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        # Runs first (cleanups are LIFO): a kit still being drawn writes into
        # the temporary folder.
        self.addCleanup(self._join_art_threads)
        self.app = FakeOverlayApp(Path(self._tmp.name))
        # Performance mode: the editor draws only the kits on screen, not every
        # kit of both teams (the prerender test turns it off).
        self.app.performance = True
        # Garbage left by earlier tests in the same run (Tk images/variables)
        # is collected here, on the main thread: a collection the worker
        # thread's allocations trigger would free it there instead, and Tcl
        # aborts the process (0x80000003) when its objects are freed off the
        # thread that owns them.
        gc.collect()
        self.runtime = self.app.kit_classic
        self._install_player_lua(SUPPORTED_PLAYER_LUA)
        self.runtime.team_lua_dir().mkdir(parents=True)
        kit_dir = self.runtime.kit_dir()
        kit_dir.mkdir(parents=True)
        for team, types in ((383, (0, 1, 2, 3, 12)), (100, (0, 1))):
            for ktype in types:
                (kit_dir / f"kit_{team}_{ktype}_0.rx3").write_bytes(b"x")   # unreadable: drawn grey

    @staticmethod
    def _join_art_threads() -> None:
        for thread in threading.enumerate():
            if thread.name == "team-kit-art":
                thread.join(timeout=15)

    def _install_player_lua(self, text: str) -> None:
        path = self.runtime.player_lua_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def enter_team_kits(self) -> None:
        self.app.open_kits_tab()
        self.app.pick("Team Kits")
        self.assertEqual(self.app._overlay_wizard_phase, "teamkits")

    def row(self, index: int) -> str:
        return self.app._overlay_items[index]

    # --- chooser and Custom Kits ---
    def test_kits_tab_starts_on_the_team_or_custom_chooser(self) -> None:
        self.app.open_kits_tab()
        self.assertTrue(self.app._overlay_scope_phase)
        self.assertEqual(self.app._overlay_items, ["Team Kits", "Custom Kits"])
        self.assertEqual(self.app.inj.header, EN["overlay.kits.mode_header"])

    def test_custom_kits_asks_for_the_side_then_the_kit_type_and_backs_out_the_same_way(self) -> None:
        self.app.open_kits_tab()
        self.app.pick("Custom Kits")
        self.assertEqual(self.app._overlay_wizard_phase, "kitside")
        self.assertEqual(self.app._overlay_items, ["Home Team", "Away Team"])
        self.assertEqual(self.app.inj.preview_paths[-1], "home.png")
        self.app.pick("Away Team")
        self.assertEqual((self.app._overlay_wizard_phase, self.app._overlay_selected_scope), ("kittype", "away"))
        self.assertEqual(self.app.inj.header, "Away Team  ->  Select Kit Type")
        self.app.pick("Home")                          # kit type: the kit set list follows
        self.assertIsNone(self.app._overlay_wizard_phase)
        self.assertEqual(self.app.inj.header, "[Away Team]  ->  Home")
        self.app._overlay_scope_back()
        self.assertEqual(self.app._overlay_wizard_phase, "kittype")
        self.app._wizard_back()
        self.assertEqual(self.app._overlay_wizard_phase, "kitside")
        self.app._wizard_back()
        self.assertTrue(self.app._overlay_scope_phase)
        self.assertEqual(self.app._overlay_selected_index, 1)   # starts on the mode used last

    # --- Team Kits editor ---
    def test_team_kits_lists_both_sides_rows(self) -> None:
        self.enter_team_kits()
        self.assertEqual(len(self.app._overlay_items), 12)
        self.assertEqual(self.row(0), "HOME · Combination:  ‹ Original kits ›")
        self.assertEqual(self.row(2), "HOME · Shirt:  ‹ Kit 0 ›")
        self.assertEqual(self.row(5), "HOME · Goalkeeper:  ‹ Automatic ›")
        self.assertEqual(self.row(7), "AWAY · Kit:  ‹ Kit 1 ›")
        self.assertEqual(self.app.inj.header, "Team Kits  ·  Palmeiras  vs  Santos")
        self.assertEqual(self.app.inj.dashboard[0], "-- TEAM KITS --")

    def test_arrow_keys_change_the_row_and_enter_saves_like_the_tab(self) -> None:
        self.enter_team_kits()
        self.app._set_menu_selection(2)                # HOME · Shirt
        self.app.press_key(VK_RIGHT)
        self.assertEqual(self.app._overlay_tab_index, KITS)   # no tab switch
        self.assertEqual(self.row(2), "HOME · Shirt:  ‹ Kit 1 ›  •")
        self.assertFalse(self.runtime.team_lua_path(383).exists())

        self.app.press_key(VK_RETURN)
        tc = self.runtime.load(383)
        self.assertEqual([c.name for c in tc.items], ["Combination 1"])
        self.assertEqual(tc.items[0].mixes, [kc.Mix(0, 0, 1, 0, 0)])
        self.assertEqual((tc.home, tc.away), (0, None))
        self.assertEqual(self.app.kit_classic_view.invalidated, [383])
        self.assertEqual(self.row(0), "HOME · Combination:  ‹ 1. Combination 1 ›")
        self.assertEqual(self.row(2), "HOME · Shirt:  ‹ Kit 1 ›")
        self.assertEqual(self.app.inj.items, self.app._overlay_items)

    def test_gamepad_d_pad_changes_the_row_and_rb_still_switches_tabs(self) -> None:
        self.enter_team_kits()
        self.app._set_menu_selection(10)               # AWAY · Socks (kit 1)
        self.app.press_button(XINPUT_GAMEPAD_DPAD_LEFT)
        self.assertEqual(self.row(10), "AWAY · Socks:  ‹ Kit 0 ›  •")
        self.app.press_button(XINPUT_GAMEPAD_A)
        self.assertEqual(self.runtime.load(100).items[0].mixes, [kc.Mix(0, 1, 1, 1, 0)])
        self.app.press_button(XINPUT_GAMEPAD_RIGHT_SHOULDER)
        self.assertEqual(self.app._overlay_tab_index, 0)

    def test_arrow_keys_still_switch_tabs_outside_the_editor(self) -> None:
        self.app.open_kits_tab()
        self.app.press_key(VK_LEFT)
        self.assertEqual(self.app._overlay_tab_index, KITS - 1)

    def test_combination_row_saves_the_sides_choice_at_once(self) -> None:
        self.runtime.save(kc.TeamCombinations(383, [kc.Combination("Retro", [kc.Mix(0, 0, 0, 1, 0)])], home=None, away=None))
        self.enter_team_kits()
        self.app._set_menu_selection(0)
        self.app._cycle_team_kit_row(1)
        self.assertEqual(self.runtime.load(383).home, 0)
        self.assertEqual(self.row(0), "HOME · Combination:  ‹ 1. Retro ›")
        self.assertEqual(self.row(3), "HOME · Shorts:  ‹ Kit 1 ›")   # the combination's mix for kit 0
        self.assertEqual(self.app.kit_classic_view.invalidated, [383])

    def test_back_returns_to_the_chooser_on_team_kits(self) -> None:
        self.enter_team_kits()
        self.app._wizard_back()
        self.assertTrue(self.app._overlay_scope_phase)
        self.assertEqual(self.app._overlay_selected_index, 0)

    def test_without_a_match_there_is_nothing_to_edit(self) -> None:
        self.app.HID = ""
        self.enter_team_kits()
        self.assertEqual(self.app._overlay_items, [EN["overlay.teamkits.no_match"]])
        self.app.press_key(VK_RIGHT)
        self.app.press_key(VK_RETURN)
        self.assertEqual(self.app._overlay_items, [EN["overlay.teamkits.no_match"]])
        self.assertEqual(list(self.runtime.team_lua_dir().glob("*.lua")), [])

    def test_without_rev_mod_support_the_editor_is_read_only(self) -> None:
        self._install_player_lua("function swapTeamKit(team,type1,type2)\nend\n")
        self.enter_team_kits()
        self.assertTrue(self.app.inj.header.endswith(EN["overlay.teamkits.readonly"]))
        self.app._set_menu_selection(2)
        self.app.press_key(VK_RIGHT)
        self.assertEqual(self.row(2), "HOME · Shirt:  ‹ Kit 0 ›")

    def test_a_failed_save_is_reported_and_the_rows_show_the_file_again(self) -> None:
        self.enter_team_kits()

        def refuse(_tc):
            raise OSError("locked")

        self.runtime.save = refuse
        self.app._set_menu_selection(2)
        self.app._cycle_team_kit_row(1)
        self.app._commit_team_kit_row("test")
        self.assertEqual(self.app.toasts, [("Team Kits", "Could not save: locked", 1)])
        self.assertEqual(self.row(0), "HOME · Combination:  ‹ Original kits ›")
        self.assertEqual(self.row(2), "HOME · Shirt:  ‹ Kit 0 ›")

    # --- the DLL's two-kit screen (set_kit_editor) ---
    def test_the_screen_gets_both_halves_and_no_hero_preview(self) -> None:
        self.enter_team_kits()
        state = self.app.inj.kit_editor
        self.assertEqual((state["editable"], state["message"], state["save_label"]), (True, "", "Save"))
        self.assertEqual(state["row_names"], ["Combination", "Kit", "Shirt", "Shorts", "Socks", "Goalkeeper"])
        home, away = state["sides"]
        self.assertEqual((home["badge"], home["team_name"], home["crest_path"]), ("HOME", "Palmeiras", "home.png"))
        self.assertEqual((away["badge"], away["team_name"], away["crest_path"]), ("AWAY", "Santos", "away.png"))
        self.assertEqual(home["row_values"], ["Original kits", "Kit 0", "Kit 0", "Kit 0", "Kit 0", "Automatic"])
        self.assertEqual(away["row_values"][1], "Kit 1")
        self.assertEqual(home["row_pending"], [False] * 6)
        self.assertEqual(self.app.inj.preview_paths[-1], "")

    def test_leaving_the_editor_hides_its_screen(self) -> None:
        self.enter_team_kits()
        self.assertIsNotNone(self.app.inj.kit_editor)
        self.app._wizard_back()
        self.assertIsNone(self.app.inj.kit_editor)
        self.app.pick("Team Kits")
        self.app.press_button(XINPUT_GAMEPAD_RIGHT_SHOULDER)   # another tab
        self.assertIsNone(self.app.inj.kit_editor)

    def test_without_a_match_the_screen_shows_the_message(self) -> None:
        self.app.AID = "0"
        self.enter_team_kits()
        self.assertEqual(self.app.inj.kit_editor["message"], EN["overlay.teamkits.no_match"])
        self.assertEqual(self.app.inj.kit_editor["sides"], [])

    def test_clicks_select_rows_and_arrows_change_them(self) -> None:
        self.enter_team_kits()
        self.app.click(9, 8)                           # AWAY · Shirt
        self.assertEqual(self.app._overlay_selected_index, 8)
        self.app.click(10, 8 * 2 + 1)                  # its ›: team 100 has kits 0 and 1, 1 wraps to 0
        self.assertEqual(self.row(8), "AWAY · Shirt:  ‹ Kit 0 ›  •")
        self.assertTrue(self.app.inj.kit_editor["sides"][1]["row_pending"][2])
        self.app.click(10, 2 * 2)                      # HOME · Shirt ‹: 0 wraps to 12
        self.assertEqual(self.app._overlay_selected_index, 2)
        self.assertEqual(self.row(2), "HOME · Shirt:  ‹ Kit 12 ›  •")

    def test_a_sides_save_button_saves_that_side(self) -> None:
        self.enter_team_kits()
        self.app.click(10, 9 * 2)                      # AWAY · Shorts ‹ (kit 1 -> 0)
        self.app._set_menu_selection(3)                # cursor back on the home side
        self.app.click(11, 1)                          # away save
        self.assertEqual(self.runtime.load(100).items[0].mixes, [kc.Mix(0, 1, 1, 0, 1)])
        self.assertFalse(self.runtime.team_lua_path(383).exists())
        self.assertEqual(self.app._overlay_selected_index, 9)
        self.assertFalse(self.app.inj.kit_editor["sides"][1]["row_pending"][3])

    def test_kits_are_drawn_as_garment_layers_off_the_tk_thread(self) -> None:
        self.enter_team_kits()
        self.assertEqual(self.app.inj.kit_editor["sides"][0]["layer_paths"], ["", "", ""])   # not drawn yet
        self.app.wait_for_kit_art()
        cache = self.app.base_dir / "runtime" / "kit_art_cache"
        for side in self.app.inj.kit_editor["sides"]:
            paths = [Path(p) for p in side["layer_paths"]]
            self.assertEqual([p.parent for p in paths], [cache] * 3)
            self.assertTrue(all(p.is_file() for p in paths))
            self.assertEqual([("_socks_" in p.name, "_shorts_" in p.name, "_shirt_" in p.name) for p in paths],
                             [(True, False, False), (False, True, False), (False, False, True)])
        # Performance mode: only what is on screen (3 layers per side).
        self.assertEqual(len(self.app._overlay_team_kit_art), 6)

    def test_every_kit_of_both_teams_is_drawn_in_advance(self) -> None:
        self.app.performance = False
        self.enter_team_kits()
        self.app.wait_for_kit_art()
        # 383: kits 0, 1, 2, 3, 12 x 3 layers + goalkeepers 2 and 12; 100: kits 0, 1 x 3 + goalkeeper 2 (grey).
        self.assertEqual(len(self.app._overlay_team_kit_art), 15 + 2 + 6 + 1)
        self.app._set_menu_selection(5)                # HOME · Goalkeeper
        self.app.press_key(VK_RIGHT)                   # Automatic -> 2, drawn already
        self.assertTrue(Path(self.app.inj.kit_editor["sides"][0]["gk_path"]).is_file())

    # --- Select / F12 held: straight to Team Kits ---
    def tick(self, at: float, buttons: int = 0, f12: bool = False) -> None:
        """One input tick `at` seconds in, with `buttons` and F12 as what is
        held; an F12 press (or Windows repeating it) goes in hotkey_edges."""
        self.app.gp_edge = self.app.gp_raw = buttons
        if f12:
            self.app.keys_held.add(VK_F12)
        else:
            self.app.keys_held.discard(VK_F12)
        with mock.patch.object(app_overlay, "perf_counter", lambda: 1000.0 + at):
            self.app._sync_d3d_menu_input()

    def test_holding_select_opens_the_menu_on_team_kits(self) -> None:
        self.app._d3d_menu_visible = False
        self.tick(0.0, XINPUT_GAMEPAD_BACK)
        self.tick(0.3, XINPUT_GAMEPAD_BACK)
        self.assertFalse(self.app._d3d_menu_visible)
        self.tick(0.65, XINPUT_GAMEPAD_BACK)
        self.assertTrue(self.app._d3d_menu_visible)
        self.assertEqual(self.app._overlay_tab_index, KITS)
        self.assertTrue(self.app._overlay_team_kits_active())
        self.assertEqual(self.row(0), "HOME · Combination:  ‹ Original kits ›")
        self.tick(1.4, XINPUT_GAMEPAD_BACK)            # still the same hold
        self.tick(1.5)
        self.assertTrue(self.app._overlay_team_kits_active())

    def test_a_short_select_press_or_start_and_select_together_do_nothing(self) -> None:
        self.app._d3d_menu_visible = False
        self.tick(0.0, XINPUT_GAMEPAD_BACK)
        self.tick(0.3)
        self.tick(1.0)
        both = XINPUT_GAMEPAD_BACK | XINPUT_GAMEPAD_START
        self.tick(2.0, both)
        self.tick(2.7, both)
        self.assertFalse(self.app._d3d_menu_visible)

    def test_holding_select_moves_an_open_menu_to_team_kits(self) -> None:
        self.assertEqual(self.app._overlay_tab_index, 0)
        self.tick(0.0, XINPUT_GAMEPAD_BACK)
        self.tick(0.65, XINPUT_GAMEPAD_BACK)
        self.assertTrue(self.app._d3d_menu_visible)
        self.assertTrue(self.app._overlay_team_kits_active())

    def test_an_f12_tap_still_opens_the_menu_where_it_was(self) -> None:
        self.app._d3d_menu_visible = False
        self.app.hotkey_edges.add(VK_F12)
        self.tick(0.0, f12=True)
        self.assertTrue(self.app._d3d_menu_visible)
        self.tick(0.1)                                 # released
        self.tick(0.8)
        self.assertEqual(self.app._overlay_tab_index, 0)
        self.assertTrue(self.app._overlay_scope_phase)
        self.app.hotkey_edges.add(VK_F12)
        self.tick(1.0, f12=True)                       # the next press closes it
        self.assertFalse(self.app._d3d_menu_visible)

    def test_holding_f12_moves_the_new_menu_to_team_kits_and_its_repeats_do_not_close_it(self) -> None:
        self.app._d3d_menu_visible = False
        self.app.hotkey_edges.add(VK_F12)
        self.tick(0.0, f12=True)
        self.assertEqual((self.app._d3d_menu_visible, self.app._overlay_tab_index), (True, 0))
        self.app.hotkey_edges.add(VK_F12)              # Windows' auto-repeat
        self.tick(0.5, f12=True)
        self.assertEqual((self.app._d3d_menu_visible, self.app._overlay_tab_index), (True, 0))
        self.app.hotkey_edges.add(VK_F12)
        self.tick(0.65, f12=True)
        self.assertTrue(self.app._overlay_team_kits_active())
        self.app.hotkey_edges.add(VK_F12)              # a repeat latched right before the release
        self.tick(0.9)
        self.assertTrue(self.app._overlay_team_kits_active())
        self.app.hotkey_edges.add(VK_F12)              # a new press closes it as always
        self.tick(1.2, f12=True)
        self.assertFalse(self.app._d3d_menu_visible)


class KitEditorSharedMemoryTests(unittest.TestCase):
    """set_kit_editor on the real ctypes struct (no mapping: a plain instance)."""

    def setUp(self) -> None:
        self.inj = D3DOverlayInjector.__new__(D3DOverlayInjector)
        self.inj._ready = True
        self.inj._shared = d3d_injector._OverlayShared()

    def test_writes_every_field_and_none_hides_it(self) -> None:
        side = {
            "badge": "HOME", "team_name": "Brighton & Hove Albion", "crest_path": "c.png",
            "layer_paths": ["socks.png", "shorts.png", "shirt.png"], "gk_path": "gk.png",
            "row_values": ["1. Retro", "Kit 0", "Kit 1", "Kit 0", "Kit 0", "Kit 2"],
            "row_pending": [False, False, True, False, False, False],
        }
        self.inj.set_kit_editor({"editable": True, "message": "", "save_label": "Save",
                                 "row_names": ["A", "B", "C", "D", "E", "F"], "sides": [side, {}]})
        editor = self.inj._shared.kit_editor
        self.assertEqual((editor.active, editor.editable, editor.save_label), (1, 1, "Save"))
        self.assertEqual([editor.row_names[i].value for i in range(6)], ["A", "B", "C", "D", "E", "F"])
        home = editor.sides[0]
        self.assertEqual((home.badge, home.team_name, home.gk_path), ("HOME", "Brighton & Hove Albion", "gk.png"))
        self.assertEqual([home.layer_paths[i].value for i in range(3)], ["socks.png", "shorts.png", "shirt.png"])
        self.assertEqual([home.row_values[i].value for i in range(6)], side["row_values"])
        self.assertEqual(list(home.row_pending), [0, 0, 1, 0, 0, 0])
        self.assertEqual(editor.sides[1].team_name, "")
        self.inj.set_kit_editor(None)
        self.assertEqual(editor.active, 0)

    def test_long_text_is_cut_to_the_field(self) -> None:
        self.inj.set_kit_editor({"sides": [{"team_name": "x" * 500}]})
        self.assertEqual(len(self.inj._shared.kit_editor.sides[0].team_name), d3d_injector._KIT_EDITOR_TEXT - 1)


if __name__ == "__main__":
    unittest.main()
