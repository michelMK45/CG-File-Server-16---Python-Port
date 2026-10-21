from __future__ import annotations

import json
import re
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from server16_py import app_overlay
from server16_py.app_overlay import OverlayMixin
from server16_py.dialogs import KeyCaptureDialog, PadCaptureDialog
from server16_py.input_bindings import (
    ACTIONS, CAPTURE_VKS, HOLD, KIT_AWAY_NEXT, KIT_AWAY_PREV, KIT_HOME_NEXT, KIT_HOME_PREV, KIT_TYPE,
    NEEDS_FREE_BUTTON, OVERLAY_MENU, PRESS, RESERVED, TAP, TEAM_KITS, UNSUPPORTED, BindingTracker, InputBindings,
    KeyBinding, PadBinding, combo_held, key_binding_name, key_name, key_problem, kit_hotkey_hint, overlay_help_text,
    pad_binding_name, pad_name, pad_problem,
)
from server16_py.locales_data import LOCALE_CATALOGS
from server16_py.settings_store import SettingsStore
from server16_py.win32_types import (
    VK_ESCAPE, VK_F7, VK_F8, VK_F9, VK_F10, VK_F11, VK_F12, VK_RETURN, VK_SPACE,
    XINPUT_GAMEPAD_A, XINPUT_GAMEPAD_BACK, XINPUT_GAMEPAD_LEFT_SHOULDER, XINPUT_GAMEPAD_LEFT_THUMB,
    XINPUT_GAMEPAD_RIGHT_SHOULDER, XINPUT_GAMEPAD_START,
)

EN = LOCALE_CATALOGS["en"]
VK_F5 = 0x74
VK_K = 0x4B
START, BACK, A = XINPUT_GAMEPAD_START, XINPUT_GAMEPAD_BACK, XINPUT_GAMEPAD_A
LB, RB, LS = XINPUT_GAMEPAD_LEFT_SHOULDER, XINPUT_GAMEPAD_RIGHT_SHOULDER, XINPUT_GAMEPAD_LEFT_THUMB


def tr(key: str, **kwargs) -> str:
    text = EN.get(key, key)
    return text.format(**kwargs) if kwargs else text


class InputBindingsModelTests(unittest.TestCase):
    def test_the_defaults_are_the_shortcuts_the_app_always_had(self) -> None:
        bindings = InputBindings.defaults()
        self.assertEqual(bindings.key(OVERLAY_MENU), KeyBinding(VK_F12))
        self.assertEqual(bindings.key(TEAM_KITS), KeyBinding(VK_F12, True))      # F12 held
        self.assertEqual([bindings.key(a).vk for a in ACTIONS[2:]], [VK_F7, VK_F8, 0x78, VK_F10, VK_F11])
        self.assertFalse(any(bindings.key(a).hold for a in ACTIONS[2:]))
        self.assertEqual(bindings.pad(OVERLAY_MENU), PadBinding(START, True))
        self.assertEqual(bindings.pad(TEAM_KITS), PadBinding(BACK, True))
        self.assertFalse(bindings.kit_pads_bound)
        self.assertEqual(bindings.menu_hook_vks, frozenset({VK_F12}))
        self.assertEqual(bindings.hotkey_poll_vks, (VK_F12, VK_F7, VK_F8, 0x78, VK_F10, VK_F11))
        self.assertEqual(bindings.kit_vks, frozenset({VK_F7, VK_F8, 0x78, VK_F10, VK_F11}))
        # F12 still opens the overlay on the press (see the modes test).
        self.assertEqual((bindings.key_mode(OVERLAY_MENU), bindings.key_mode(TEAM_KITS)), (PRESS, HOLD))

    def test_with_key_returns_a_new_object_and_leaves_the_old_one_alone(self) -> None:
        old = InputBindings.defaults()
        new = old.with_key(OVERLAY_MENU, KeyBinding(VK_F5))
        self.assertEqual(old.key(OVERLAY_MENU), KeyBinding(VK_F12))
        self.assertEqual(new.key(OVERLAY_MENU), KeyBinding(VK_F5))
        self.assertEqual(new.menu_hook_vks, frozenset({VK_F5, VK_F12}))
        self.assertNotEqual(old, new)
        self.assertEqual(new, InputBindings.from_dict(new.to_dict()))

    def test_owners_report_the_action_already_using_a_key_or_combination_the_same_way(self) -> None:
        bindings = InputBindings.defaults()
        self.assertEqual(bindings.key_owner(KeyBinding(VK_F8)), KIT_HOME_NEXT)
        self.assertIsNone(bindings.key_owner(KeyBinding(VK_F8), exclude=KIT_HOME_NEXT))
        self.assertIsNone(bindings.key_owner(KeyBinding(VK_F8, True)))     # F8 held is free
        self.assertEqual(bindings.key_owner(KeyBinding(VK_F12)), OVERLAY_MENU)
        self.assertEqual(bindings.key_owner(KeyBinding(VK_F12, True)), TEAM_KITS)
        self.assertEqual(bindings.pad_owner(PadBinding(BACK, True)), TEAM_KITS)
        self.assertIsNone(bindings.pad_owner(PadBinding(BACK)))
        self.assertIsNone(bindings.pad_owner(PadBinding(BACK | START, True)))

    def test_modes_a_press_waits_for_the_release_when_another_action_holds_its_key(self) -> None:
        f7_twice = InputBindings.defaults().with_key(KIT_HOME_NEXT, KeyBinding(VK_F7, True))
        self.assertEqual((f7_twice.key_mode(KIT_HOME_PREV), f7_twice.key_mode(KIT_HOME_NEXT)), (TAP, HOLD))
        self.assertEqual(f7_twice.key_mode(KIT_TYPE), PRESS)
        self.assertEqual(f7_twice.hotkey_poll_vks.count(VK_F7), 1)
        # Opening the overlay is the exception, with Team Kits held only...
        defaults = InputBindings.defaults()
        self.assertEqual(defaults.key_mode(OVERLAY_MENU), PRESS)
        # ...not with another action held on its key.
        other = defaults.with_key(TEAM_KITS, KeyBinding()).with_key(KIT_TYPE, KeyBinding(VK_F12, True))
        self.assertEqual(other.key_mode(OVERLAY_MENU), TAP)
        reverse = defaults.with_key(OVERLAY_MENU, KeyBinding(VK_F12, True)).with_key(TEAM_KITS, KeyBinding(VK_F12))
        self.assertEqual(reverse.key_mode(TEAM_KITS), TAP)
        # The gamepad's Hold is its own: Start pressed and Start held.
        pads = defaults.with_pad(OVERLAY_MENU, PadBinding(START)).with_pad(KIT_TYPE, PadBinding(START, True))
        self.assertEqual((pads.pad_mode(OVERLAY_MENU), pads.pad_mode(KIT_TYPE)), (TAP, HOLD))
        self.assertEqual(pads.key_mode(OVERLAY_MENU), PRESS)
        self.assertEqual(pads.pad_state(OVERLAY_MENU, START, START), (True, True))
        self.assertEqual(pads.pad_state(KIT_TYPE, START, 0), (True, False))

    def test_key_and_pad_problems(self) -> None:
        self.assertEqual(key_problem(VK_RETURN), RESERVED)
        self.assertEqual(key_problem(VK_ESCAPE), RESERVED)
        self.assertEqual(key_problem(0x12), UNSUPPORTED)     # Alt
        self.assertIsNone(key_problem(VK_K))
        self.assertIsNone(key_problem(VK_SPACE))
        self.assertEqual(pad_problem(OVERLAY_MENU, A), NEEDS_FREE_BUTTON)
        self.assertEqual(pad_problem(TEAM_KITS, LB | RB), NEEDS_FREE_BUTTON)
        self.assertIsNone(pad_problem(OVERLAY_MENU, LB | RB | LS))
        self.assertIsNone(pad_problem(KIT_HOME_NEXT, RB))       # the menu is closed for the kit hotkeys
        self.assertEqual(pad_problem(KIT_HOME_NEXT, 0), UNSUPPORTED)
        self.assertEqual(pad_problem(KIT_HOME_NEXT, 0x0400), UNSUPPORTED)

    def test_capture_listens_for_the_reserved_keys_but_not_for_esc(self) -> None:
        self.assertIn(VK_RETURN, CAPTURE_VKS)
        self.assertNotIn(VK_ESCAPE, CAPTURE_VKS)


class InputBindingsStorageTests(unittest.TestCase):
    def test_missing_or_broken_data_gives_the_defaults(self) -> None:
        for data in (None, "x", {}, {"keyboard": 3, "gamepad": []}):
            self.assertEqual(InputBindings.from_dict(data), InputBindings.defaults(), data)

    def test_a_hand_edited_block_is_repaired_action_by_action(self) -> None:
        bindings = InputBindings.from_dict({
            "keyboard": {
                OVERLAY_MENU: {"vk": VK_RETURN, "hold": False},   # reserved -> default F12
                TEAM_KITS: {"vk": VK_F5, "hold": False},
                KIT_HOME_PREV: {"vk": VK_F5, "hold": True},       # F5 held is another binding: kept
                KIT_HOME_NEXT: {"vk": VK_F5, "hold": False},      # repeats Team Kits' -> default F8
                KIT_AWAY_NEXT: {"vk": True, "hold": False},       # not a key code -> default F10
                KIT_AWAY_PREV: VK_F7,                             # not a binding -> default F9
                KIT_TYPE: {"vk": 0, "hold": False},               # explicitly not set
            },
            "gamepad": {
                OVERLAY_MENU: {"buttons": A, "hold": True},          # needs Start/Select/LS/RS -> default
                TEAM_KITS: {"buttons": START, "hold": True},         # the overlay (checked first) has it
                KIT_HOME_NEXT: {"buttons": RB, "hold": False},
                KIT_HOME_PREV: {"buttons": RB, "hold": True},        # RB held: kept
                KIT_AWAY_NEXT: {"buttons": RB, "hold": False},       # repeats -> its default (none)
            },
        })
        self.assertEqual(bindings.key(OVERLAY_MENU), KeyBinding(VK_F12))
        self.assertEqual(bindings.key(TEAM_KITS), KeyBinding(VK_F5))
        self.assertEqual(bindings.key(KIT_HOME_PREV), KeyBinding(VK_F5, True))
        self.assertEqual(bindings.key(KIT_HOME_NEXT), KeyBinding(VK_F8))
        self.assertEqual(bindings.key(KIT_AWAY_NEXT), KeyBinding(VK_F10))
        self.assertEqual(bindings.key(KIT_AWAY_PREV), KeyBinding(0x78))
        self.assertEqual(bindings.key(KIT_TYPE), KeyBinding())
        self.assertEqual(bindings.pad(OVERLAY_MENU), PadBinding(START, True))
        self.assertEqual(bindings.pad(TEAM_KITS), PadBinding(BACK, True))
        self.assertEqual(bindings.pad(KIT_HOME_NEXT), PadBinding(RB, False))
        self.assertEqual(bindings.pad(KIT_HOME_PREV), PadBinding(RB, True))
        self.assertEqual(bindings.pad(KIT_AWAY_NEXT), PadBinding())

    def test_a_default_another_action_already_took_is_left_unset(self) -> None:
        bindings = InputBindings.from_dict({"keyboard": {OVERLAY_MENU: {"vk": VK_F12, "hold": True}}})
        self.assertEqual(bindings.key(OVERLAY_MENU), KeyBinding(VK_F12, True))
        self.assertEqual(bindings.key(TEAM_KITS), KeyBinding())     # its default, F12 held, is taken

    def test_an_overlay_without_any_binding_gets_f12_back(self) -> None:
        bindings = InputBindings.from_dict({
            "keyboard": {OVERLAY_MENU: {"vk": 0, "hold": False}},
            "gamepad": {OVERLAY_MENU: {"buttons": 0, "hold": True}},
        })
        self.assertEqual(bindings.key(OVERLAY_MENU), KeyBinding(VK_F12))

    def test_settings_store_saves_and_reloads_them(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            store = SettingsStore(path)
            self.assertEqual(store.input_bindings, InputBindings.defaults())
            changed = (
                store.input_bindings.with_key(KIT_TYPE, KeyBinding(VK_K, True))
                .with_pad(KIT_HOME_NEXT, PadBinding(RB, False))
            )
            store.input_bindings = changed
            saved = json.loads(path.read_text(encoding="utf-8"))["INPUT_BINDINGS"]
            self.assertEqual(saved["keyboard"][KIT_TYPE], {"vk": VK_K, "hold": True})
            self.assertEqual(SettingsStore(path).input_bindings, changed)


class ComboTests(unittest.TestCase):
    def test_start_and_select_together_are_neither(self) -> None:
        others_of_start = (BACK,)
        self.assertTrue(combo_held(START, START, others_of_start))
        self.assertFalse(combo_held(START, START | BACK, others_of_start))
        self.assertFalse(combo_held(BACK, START | BACK, (START,)))

    def test_the_bigger_combination_wins_over_the_one_inside_it(self) -> None:
        self.assertFalse(combo_held(START, START | BACK, (START | BACK,)))
        self.assertTrue(combo_held(START | BACK, START | BACK, (START,)))
        self.assertTrue(combo_held(START, START | A, ()))      # A isn't bound: doesn't matter


class BindingTrackerTests(unittest.TestCase):
    """update(mode, seen, held, now): `seen` = went down since the last tick
    (the latch), `held` = down right now."""

    def test_a_press_binding_fires_once_per_press_even_a_tap_between_two_ticks(self) -> None:
        tracker = BindingTracker()
        self.assertTrue(tracker.update(PRESS, True, False, 0.0))      # only the latch saw it
        self.assertFalse(tracker.update(PRESS, False, False, 0.1))
        self.assertTrue(tracker.update(PRESS, True, True, 0.2))
        self.assertFalse(tracker.update(PRESS, True, True, 0.3))      # still held (a key's auto-repeat)
        self.assertFalse(tracker.update(PRESS, True, False, 0.4))     # a repeat latched before the release
        self.assertFalse(tracker.update(PRESS, False, False, 0.5))

    def test_a_hold_binding_fires_once_after_the_hold_time(self) -> None:
        tracker = BindingTracker()
        self.assertFalse(tracker.update(HOLD, True, True, 0.0))
        self.assertFalse(tracker.update(HOLD, True, True, 0.5))
        self.assertTrue(tracker.update(HOLD, True, True, 0.61))
        self.assertFalse(tracker.update(HOLD, True, True, 2.0))
        self.assertFalse(tracker.update(HOLD, False, False, 2.1))
        self.assertFalse(tracker.update(HOLD, True, True, 2.2))
        self.assertTrue(tracker.update(HOLD, True, True, 2.9))
        self.assertFalse(tracker.update(HOLD, True, False, 3.5))      # a tap is no hold

    def test_a_tap_binding_fires_on_a_release_before_the_hold_time_only(self) -> None:
        tracker = BindingTracker()
        self.assertFalse(tracker.update(TAP, True, True, 0.0))
        self.assertFalse(tracker.update(TAP, True, True, 0.3))
        self.assertTrue(tracker.update(TAP, False, False, 0.4))       # let go at 0.4s
        self.assertFalse(tracker.update(TAP, False, False, 0.5))
        self.assertFalse(tracker.update(TAP, True, True, 1.0))
        self.assertFalse(tracker.update(TAP, True, True, 1.61))       # the hold binding's turn
        self.assertFalse(tracker.update(TAP, False, False, 1.8))
        self.assertTrue(tracker.update(TAP, True, False, 2.0))        # down and up between two ticks

    def test_tap_and_hold_on_one_key_never_both_fire(self) -> None:
        tap, hold = BindingTracker(), BindingTracker()
        for seen, held, now in ((True, True, 0.0), (True, True, 0.55), (False, False, 0.62)):
            self.assertFalse(hold.update(HOLD, seen, held, now))      # released before a tick saw 0.6s held
            fired_tap = tap.update(TAP, seen, held, now)
        self.assertTrue(fired_tap)
        for seen, held, now in ((True, True, 1.0), (True, True, 1.6), (False, False, 1.7)):
            self.assertEqual(hold.update(HOLD, seen, held, now), now == 1.6)
            self.assertFalse(tap.update(TAP, seen, held, now))

    def test_a_spent_press_fires_nothing_more(self) -> None:
        tap, hold = BindingTracker(), BindingTracker()
        tap.update(TAP, True, True, 0.0)
        hold.update(HOLD, True, True, 0.0)
        tap.spend()
        hold.spend()
        self.assertFalse(hold.update(HOLD, True, True, 0.7))
        self.assertFalse(hold.update(HOLD, False, False, 0.8))
        self.assertFalse(tap.update(TAP, False, False, 0.8))
        hold.update(HOLD, True, True, 1.0)                            # the next press is a new one
        self.assertTrue(hold.update(HOLD, True, True, 1.7))

    def test_a_primed_tracker_ignores_what_is_already_held(self) -> None:
        for mode in (PRESS, TAP, HOLD):
            with self.subTest(mode=mode):
                tracker = BindingTracker()
                tracker.prime(True, 0.0)
                self.assertFalse(tracker.update(mode, True, True, 0.1))
                self.assertFalse(tracker.update(mode, True, True, 0.8))
                self.assertFalse(tracker.update(mode, False, False, 0.9))
        tracker = BindingTracker()
        tracker.prime(True, 0.0)
        tracker.update(PRESS, False, False, 0.2)
        self.assertTrue(tracker.update(PRESS, True, True, 0.3))


class NameTests(unittest.TestCase):
    def test_key_names(self) -> None:
        self.assertEqual(key_name(VK_F12, tr), "F12")
        self.assertEqual(key_name(VK_K, tr), "K")
        self.assertEqual(key_name(0x35, tr), "5")
        self.assertEqual(key_name(0x65, tr), "Num 5")
        self.assertEqual(key_name(0x6B, tr), "Num +")
        self.assertEqual(key_name(VK_SPACE, tr), "Space")
        self.assertEqual(key_name(0xA2, tr), "Left Ctrl")
        self.assertEqual(key_binding_name(KeyBinding(VK_F12, True), tr), "F12 (hold)")
        self.assertEqual(key_binding_name(KeyBinding(VK_F12), tr), "F12")

    def test_pad_names(self) -> None:
        self.assertEqual(pad_name(START | LB | RB, tr), "LB+RB+Start")
        self.assertEqual(pad_name(BACK, tr), "Select")
        self.assertEqual(pad_name(LS | 0x0008, tr), "LS+D-pad Right")
        self.assertEqual(pad_binding_name(PadBinding(START, True), tr), "Start (hold)")
        self.assertEqual(pad_binding_name(PadBinding(START, False), tr), "Start")

    def test_the_help_line_and_the_kit_hint_follow_the_bindings(self) -> None:
        bindings = InputBindings.defaults()
        self.assertEqual(
            overlay_help_text(bindings, tr),
            "In-game overlay: F12 / Start (hold)  ·  Team Kits: F12 (hold) / Select (hold)",
        )
        self.assertEqual(kit_hotkey_hint(bindings, tr), "F7/F8 Home · F9/F10 Away · F11 Type")
        changed = (
            bindings.with_key(TEAM_KITS, KeyBinding(VK_F5)).with_key(KIT_TYPE, KeyBinding())
            .with_pad(KIT_TYPE, PadBinding(LB | RB, False)).with_key(KIT_HOME_NEXT, KeyBinding(VK_F7, True))
        )
        self.assertEqual(
            overlay_help_text(changed, tr),
            "In-game overlay: F12 / Start (hold)  ·  Team Kits: F5 / Select (hold)",
        )
        self.assertEqual(kit_hotkey_hint(changed, tr), "F7/F7 (hold) Home · F9/F10 Away · LB+RB Type")
        self.assertEqual(
            kit_hotkey_hint(bindings.with_key(KIT_TYPE, KeyBinding()), tr), "F7/F8 Home · F9/F10 Away · — Type",
        )


class ControlsLocaleKeyTests(unittest.TestCase):
    """Every string the Controls feature asks for exists in all three
    languages (a missing one would show up as its raw key)."""

    _PATTERN = re.compile(
        r"""["']((?:controls|key|pad|card\.controls|button\.controls|toggle\.controls|tooltip\.controls|"""
        r"""message\.controls|dialog\.binding_capture|button\.binding_capture)\.[a-z_.]+)["']"""
    )

    def test_every_controls_key_exists_in_every_language(self) -> None:
        package = Path(__file__).resolve().parent.parent / "server16_py"
        used = {f"controls.action.{action}" for action in ACTIONS} | {"help.overlay_toggle", "kitsimple.hotkey_hint"}
        for name in ("input_bindings.py", "app_ui.py", "dialogs.py"):
            used |= set(self._PATTERN.findall((package / name).read_text(encoding="utf-8")))
        self.assertGreater(len(used), 40)
        for language in ("en", "es", "pt"):
            strings = json.loads((package / "locales" / f"{language}.json").read_text(encoding="utf-8"))
            self.assertEqual(sorted(k for k in used if k not in strings), [], language)


class FakeKitHotkeyApp(OverlayMixin):
    """The real _sync_kit_hotkeys on a minimal host: what it would cycle is
    recorded in `actions`."""

    def __init__(self) -> None:
        self.input_bindings = InputBindings.defaults()
        self.enabled = True
        self.kit_hotkeys_var = SimpleNamespace(get=lambda: self.enabled)
        self._fifa_hwnd = 1
        self._d3d_menu_visible = False
        self.lastpagename = "TeamSelect"
        self.page_ok = True
        self.foreground = True
        self._kit_hotkey_ready_at = 0.0
        self._kit_key_trackers: dict = {}
        self._kit_pad_trackers: dict = {}
        self._kit_hotkey_pending: set[str] = set()
        self._kit_input_primed = False
        self.hotkey_edges: set[int] = set()
        self.keys_held: set[int] = set()
        self.gp_edge = self.gp_raw = 0
        self.actions: list = []

    def _page_can_have_match_context(self, _page: str) -> bool:
        return self.page_ok

    def _is_overlay_input_foreground(self) -> bool:
        return self.foreground

    def _install_hotkey_poll_thread(self) -> None:
        pass

    def _install_gamepad_poll_thread(self) -> None:
        pass

    def _consume_kit_hotkey_edge(self, vk: int) -> bool:
        if vk in self.hotkey_edges:
            self.hotkey_edges.discard(vk)
            return True
        return False

    def _is_hotkey_down(self, vk: int) -> bool:
        return vk in self.keys_held

    def _consume_kit_gamepad_state(self):
        return self.gp_edge, self.gp_raw

    def _trigger_kit_cycle(self, side: str, direction: int) -> None:
        self.actions.append((side, direction))

    def _cycle_kit_type(self) -> None:
        self.actions.append("type")

    def tick(self, at: float, buttons: int = 0, keys: tuple[int, ...] = ()) -> None:
        """One tick `at` seconds in with `buttons` and `keys` held; a key
        press (down since the last tick) goes in hotkey_edges."""
        self.gp_edge = self.gp_raw = buttons
        self.keys_held = set(keys)
        with mock.patch.object(app_overlay, "time", SimpleNamespace(monotonic=lambda: 1000.0 + at)):
            self._sync_kit_hotkeys()

    def press(self, at: float, vk: int) -> None:
        self.hotkey_edges.add(vk)
        self.tick(at, keys=(vk,))


class KitHotkeyBindingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = FakeKitHotkeyApp()

    def test_the_default_keys_still_cycle_the_kits(self) -> None:
        self.app.tick(-1.0)                      # first read: primes
        self.app.hotkey_edges.add(VK_F8)         # a tap between two ticks
        self.app.tick(0.0)
        self.app.press(0.5, VK_F11)
        self.app.tick(0.6, keys=(VK_F11,))       # still held
        self.assertEqual(self.app.actions, [("home", 1), "type"])

    def test_a_custom_key_replaces_the_default_one(self) -> None:
        self.app.input_bindings = InputBindings.defaults().with_key(KIT_AWAY_NEXT, KeyBinding(VK_K))
        self.app.tick(-1.0)
        self.app.hotkey_edges.update({VK_F10})
        self.app.tick(0.0)
        self.app.hotkey_edges.add(VK_K)
        self.app.tick(0.5)
        self.assertEqual(self.app.actions, [("away", 1)])

    def test_a_key_pressed_and_one_held_on_the_same_key(self) -> None:
        self.app.input_bindings = InputBindings.defaults().with_key(KIT_HOME_NEXT, KeyBinding(VK_F7, True))
        self.app.tick(-1.0)
        self.app.press(0.0, VK_F7)
        self.assertEqual(self.app.actions, [])   # F7's press waits for the release
        self.app.tick(0.2)
        self.assertEqual(self.app.actions, [("home", -1)])
        self.app.press(1.0, VK_F7)
        self.app.tick(1.3, keys=(VK_F7,))
        self.app.tick(1.65, keys=(VK_F7,))
        self.app.tick(1.8)
        self.assertEqual(self.app.actions, [("home", -1), ("home", 1)])

    def test_a_kit_key_whose_hold_is_team_kits_acts_on_a_quick_release(self) -> None:
        self.app.input_bindings = InputBindings.defaults().with_key(TEAM_KITS, KeyBinding(VK_F11, True))
        self.app.tick(-1.0)
        self.app.press(0.0, VK_F11)
        self.app.tick(0.1)
        self.app.press(1.0, VK_F11)
        self.app.tick(1.7, keys=(VK_F11,))       # held: Team Kits' (the overlay's side)
        self.app.tick(1.8)
        self.assertEqual(self.app.actions, ["type"])

    def test_keys_held_or_pressed_while_the_hotkeys_were_off_do_not_fire(self) -> None:
        self.app.tick(-1.0)
        self.app.enabled = False
        self.app.press(0.0, VK_F8)               # latched while off, still held when they come back
        self.app.hotkey_edges.add(VK_F9)         # tapped while off
        self.app.enabled = True
        self.app.tick(0.1, keys=(VK_F8,))
        self.app.tick(0.2, keys=(VK_F8,))
        self.app.tick(0.3)
        self.assertEqual(self.app.actions, [])
        self.app.press(0.5, VK_F8)
        self.assertEqual(self.app.actions, [("home", 1)])

    def test_a_press_outside_fifa_or_off_the_kit_screen_is_dropped_not_kept(self) -> None:
        self.app.tick(-1.0)
        self.app.foreground = False
        self.app.hotkey_edges.add(VK_F8)
        self.app.tick(0.0)
        self.app.foreground = True
        self.app.page_ok = False
        self.app.hotkey_edges.add(VK_F7)
        self.app.tick(0.5)
        self.app.page_ok = True
        self.app.tick(1.0)
        self.assertEqual(self.app.actions, [])
        self.assertEqual(self.app.hotkey_edges, set())

    def test_a_gamepad_kit_binding_fires_once_per_press(self) -> None:
        self.app.input_bindings = InputBindings.defaults().with_pad(KIT_HOME_NEXT, PadBinding(LB | RB, False))
        self.app.tick(0.0)                       # first read: primes
        self.app.tick(0.1, LB | RB)
        self.app.tick(0.2, LB | RB)              # still held
        self.app.tick(0.5)
        self.app.tick(0.6, LB | RB)
        self.assertEqual(self.app.actions, [("home", 1), ("home", 1)])

    def test_a_combination_already_held_when_reading_starts_does_not_fire(self) -> None:
        self.app.input_bindings = InputBindings.defaults().with_pad(KIT_TYPE, PadBinding(RB, False))
        self.app.tick(0.0, RB)
        self.app.tick(0.1, RB)
        self.assertEqual(self.app.actions, [])
        self.app.tick(0.2)
        self.app.tick(0.3, RB)
        self.assertEqual(self.app.actions, ["type"])

    def test_turning_the_hotkeys_back_on_reprimes_the_gamepad(self) -> None:
        self.app.input_bindings = InputBindings.defaults().with_pad(KIT_TYPE, PadBinding(RB, False))
        self.app.tick(0.0)
        self.app.enabled = False
        self.app.tick(0.1)
        self.app.enabled = True
        self.app.gp_edge, self.app.gp_raw = RB, 0      # pressed while they were off
        with mock.patch.object(app_overlay, "time", SimpleNamespace(monotonic=lambda: 1000.2)):
            self.app._sync_kit_hotkeys()
        self.assertEqual(self.app.actions, [])

    def test_a_gamepad_press_inside_the_cooldown_fires_right_after_it(self) -> None:
        self.app.input_bindings = InputBindings.defaults().with_pad(KIT_HOME_NEXT, PadBinding(RB, False))
        self.app.tick(0.0)
        self.app.tick(0.05, RB)
        self.app.tick(0.10)
        self.app.tick(0.15, RB)                  # inside the 0.25s cooldown
        self.assertEqual(self.app.actions, [("home", 1)])
        self.app.tick(0.20)
        self.app.tick(0.31)
        self.assertEqual(self.app.actions, [("home", 1), ("home", 1)])

    def test_a_gamepad_combination_pressed_and_held_for_two_hotkeys(self) -> None:
        self.app.input_bindings = (
            InputBindings.defaults().with_pad(KIT_HOME_NEXT, PadBinding(RB)).with_pad(KIT_TYPE, PadBinding(RB, True))
        )
        self.app.tick(0.0)
        self.app.tick(0.1, RB)
        self.app.tick(0.2)
        self.app.tick(1.0, RB)
        self.app.tick(1.7, RB)
        self.app.tick(1.8)
        self.assertEqual(self.app.actions, [("home", 1), "type"])


class _CaptureDialogTestBase(unittest.TestCase):
    def setUp(self) -> None:
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:  # no display available
            self.skipTest(f"Tk unavailable: {exc}")
        self.root.withdraw()
        self.root.tr = tr
        self.addCleanup(self.root.destroy)

    @staticmethod
    def message(dialog) -> str:
        return dialog.message_label.cget("text")


class KeyCaptureDialogTests(_CaptureDialogTestBase):
    def open(self, validate=lambda _vk: None):
        self.down: set[int] = set()
        return KeyCaptureDialog(
            self.root, "Open / close the overlay", "F12", validate,
            lambda vk: 0x8000 if vk in self.down else 0, CAPTURE_VKS,
        )

    def test_a_key_held_when_it_opens_only_counts_after_being_pressed_again(self) -> None:
        self.down = {VK_SPACE}
        dialog = KeyCaptureDialog(
            self.root, "x", "F12", lambda _vk: None, lambda vk: 0x8000 if vk in self.down else 0, CAPTURE_VKS,
        )
        dialog._poll()
        self.assertTrue(dialog.winfo_exists())
        self.down = set()
        dialog._poll()
        self.down = {VK_SPACE}
        dialog._poll()
        self.assertEqual(dialog.result, VK_SPACE)

    def test_a_refused_key_shows_why_and_it_keeps_listening(self) -> None:
        dialog = self.open(lambda vk: "reserved" if vk == VK_RETURN else None)
        self.down = {VK_RETURN}
        dialog._poll()
        self.assertEqual(self.message(dialog), "reserved")
        self.assertIsNone(dialog.result)
        self.down = {VK_RETURN, VK_F5}
        dialog._poll()
        self.assertEqual(dialog.result, VK_F5)

    def test_clear_gives_zero_unless_refused(self) -> None:
        dialog = self.open(lambda vk: "needs one" if vk == 0 else None)
        self.assertFalse(dialog._offer(0))
        self.assertEqual(self.message(dialog), "needs one")
        dialog = self.open()
        self.assertTrue(dialog._offer(0))
        self.assertEqual(dialog.result, 0)


class PadCaptureDialogTests(_CaptureDialogTestBase):
    def open(self, validate=lambda _b: None, held: int | None = 0):
        self.buttons = held
        return PadCaptureDialog(
            self.root, "Go to Team Kits", "Select", validate, lambda: self.buttons, lambda b: pad_name(b, tr),
        )

    def poll(self, dialog, buttons) -> None:
        self.buttons = buttons
        dialog._poll()

    def test_a_combination_pressed_one_button_at_a_time_is_taken_on_release(self) -> None:
        dialog = self.open()
        self.poll(dialog, 0)
        self.poll(dialog, LB)
        self.poll(dialog, LB | RB)
        self.poll(dialog, LB | RB | START)
        self.assertEqual(dialog.live_label.cget("text"), "LB+RB+Start")
        self.poll(dialog, RB)
        self.assertIsNone(dialog.result)
        self.poll(dialog, 0)
        self.assertEqual(dialog.result, LB | RB | START)

    def test_what_is_held_when_it_opens_has_to_be_released_first(self) -> None:
        dialog = self.open(held=A)
        self.poll(dialog, A)
        self.poll(dialog, A | START)
        self.poll(dialog, 0)
        self.assertIsNone(dialog.result)
        self.poll(dialog, START)
        self.poll(dialog, 0)
        self.assertEqual(dialog.result, START)

    def test_a_refused_combination_shows_why_and_it_keeps_listening(self) -> None:
        dialog = self.open(lambda b: "needs Start" if not b & START else None)
        self.poll(dialog, 0)
        self.poll(dialog, A)
        self.poll(dialog, 0)
        self.assertEqual(self.message(dialog), "needs Start")
        self.poll(dialog, START | A)
        self.poll(dialog, 0)
        self.assertEqual(dialog.result, START | A)

    def test_without_a_gamepad_it_says_so(self) -> None:
        dialog = self.open(held=None)
        dialog._poll()
        self.assertEqual(self.message(dialog), EN["dialog.binding_capture.no_gamepad"])
        self.poll(dialog, 0)
        self.assertEqual(self.message(dialog), "")


if __name__ == "__main__":
    unittest.main()
