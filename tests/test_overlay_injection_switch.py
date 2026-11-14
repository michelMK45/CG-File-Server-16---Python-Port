"""Settings > Overlay "Inject overlay into FIFA" (D3D_OVERLAY_INJECTION).

Off = cgfs16_overlay.dll is never injected: _ensure_d3d_overlay_injected (the only injection path)
returns before even creating the injector, so _d3d_injector stays None and every overlay feature
takes its no-overlay path. Switching it off mid-session clears what the DLL could still draw and
drops the injector. For the forum report "FIFA closes ~6 s after injection" (docs/overlay-d3d.md).
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from server16_py import app_ui
from server16_py.app_ui import UIMixin
from server16_py.settings_store import SettingsStore

PID = 4242


class _Var:
    def __init__(self, value: bool) -> None:
        self.value = value

    def get(self) -> bool:
        return self.value

    def set(self, value: bool) -> None:
        self.value = value


class _Switch:
    def __init__(self) -> None:
        self.disabled = False

    def state(self, spec: list[str]) -> None:
        self.disabled = spec == ["disabled"]


class FakeInjector:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def hide(self) -> None:
        self.calls.append("hide")

    def hide_toast(self, slot: int = -1) -> None:
        self.calls.append(f"hide_toast({slot})")

    def hide_kit_carousel(self) -> None:
        self.calls.append("hide_kit_carousel")

    def hide_stadium_picker(self) -> None:
        self.calls.append("hide_stadium_picker")

    def set_video_playing(self, playing: bool) -> None:
        self.calls.append(f"set_video_playing({playing})")

    def destroy(self) -> None:
        self.calls.append("destroy")


class FakeApp(UIMixin):
    def __init__(self, injection: bool) -> None:
        self.overlay_injection_var = _Var(injection)
        # Saved choices: overlay on, performance mode on, manual stadium pick.
        self.settings = SimpleNamespace(overlay_injection=injection, show_overlay=True,
                                        overlay_performance_mode=True, random_stadium_selection=False,
                                        show_stadium_loading_notification=True)
        self.show_overlay_var = _Var(True)
        self.show_stadium_loading_var = _Var(True)
        self._stadium_loading_visible = False
        self.overlay_performance_mode_var = _Var(True)
        self.random_stadium_selection_var = _Var(False)
        self.overlay_switch = _Switch()
        self.performance_mode_switch = _Switch()
        self.random_stadium_switch = _Switch()
        self.notification_switch = _Switch()
        self._overlay_injection_off_logged_pid = 0
        self._d3d_injector = None
        self._d3d_menu_visible = False
        self._stadium_picker_pending = False
        self.resource_dir = Path(tempfile.gettempdir()) / "cgfs16-no-such-resource-dir"
        self.logs: list[str] = []
        self.events: list[str] = []

    def log(self, message, *args, **kwargs) -> None:
        self.logs.append(str(message))

    def _resolve_fifa_pid(self) -> int:
        return PID

    def _clear_overlay_wizard_state(self) -> None:
        self.events.append("clear_wizard")

    def _uninstall_mouse_wheel_hook(self) -> None:
        self.events.append("uninstall_mouse")

    def _uninstall_keyboard_hook(self) -> None:
        self.events.append("uninstall_keyboard")

    def _publish_overlay_menu_state(self) -> None:
        self.events.append(f"publish(menu={self._d3d_menu_visible})")

    def _resolve_stadium_picker(self, chosen) -> None:
        self.events.append(f"resolve_picker({chosen})")

    def _hide_stadium_loading_modal(self, delay_ms: int = 0) -> None:
        self.events.append("hide_loading_notice")
        self._stadium_loading_visible = False

    def _kit_hotkeys_need_key_poll(self) -> bool:
        return False

    def _kit_hotkeys_need_pad_poll(self) -> bool:
        return True

    def _uninstall_hotkey_poll_thread(self) -> None:
        self.events.append("uninstall_key_poll")

    def _uninstall_gamepad_poll_thread(self) -> None:
        self.events.append("uninstall_pad_poll")


class SettingsStoreTests(unittest.TestCase):
    def test_default_on_and_persists_off(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            store = SettingsStore(path)
            self.assertTrue(store.overlay_injection)
            store.overlay_injection = False
            self.assertFalse(SettingsStore(path).overlay_injection)

    def test_missing_key_in_old_settings_file_means_on(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            path.write_text('{"SHOW_OVERLAY": false}', encoding="utf-8")
            self.assertTrue(SettingsStore(path).overlay_injection)


class EnsureInjectedTests(unittest.TestCase):
    def test_off_never_creates_the_injector(self) -> None:
        app = FakeApp(injection=False)
        factory = mock.Mock(side_effect=AssertionError("injector must not be created"))
        with mock.patch.object(app_ui, "_D3DOverlayInjector", factory):
            self.assertFalse(app._ensure_d3d_overlay_injected(log_errors=False))
            self.assertFalse(app._ensure_d3d_overlay_injected(log_errors=False))
        factory.assert_not_called()
        self.assertIsNone(app._d3d_injector)

    def test_off_logs_once_per_fifa_pid(self) -> None:
        app = FakeApp(injection=False)
        for _ in range(5):
            app._ensure_d3d_overlay_injected(log_errors=False)
        self.assertEqual(
            app.logs,
            [f"D3D overlay: injection disabled in Settings; FIFA pid {PID} runs without the overlay DLL"],
        )

    def test_on_still_reaches_the_dll_check(self) -> None:
        # resource_dir has no bin/cgfs16_overlay.dll -> the usual "DLL not found" path,
        # proving the switch does not short-circuit when on.
        app = FakeApp(injection=True)
        self.assertFalse(app._ensure_d3d_overlay_injected(log_errors=True))
        self.assertTrue(any("DLL not found" in line for line in app.logs), app.logs)


class ReleaseTests(unittest.TestCase):
    def test_switching_off_clears_overlay_and_drops_injector(self) -> None:
        app = FakeApp(injection=True)
        inj = FakeInjector()
        app._d3d_injector = inj
        app._d3d_menu_visible = True
        app._stadium_picker_pending = True
        app.overlay_injection_var.value = False

        app._toggle_overlay_injection()

        self.assertFalse(app.settings.overlay_injection)
        self.assertIsNone(app._d3d_injector)
        self.assertFalse(app._d3d_menu_visible)
        self.assertIn("publish(menu=False)", app.events)
        self.assertIn("resolve_picker(None)", app.events)
        self.assertEqual(inj.calls[-1], "destroy")
        for call in ("hide", "hide_toast(-1)", "hide_kit_carousel", "hide_stadium_picker",
                     "set_video_playing(False)"):
            self.assertIn(call, inj.calls)

    def test_switching_on_does_not_inject_by_itself(self) -> None:
        app = FakeApp(injection=False)
        app.overlay_injection_var.value = True
        app._toggle_overlay_injection()
        self.assertTrue(app.settings.overlay_injection)
        self.assertIsNone(app._d3d_injector)
        self.assertEqual(app.events, [])


class DependentSwitchesTests(unittest.TestCase):
    def test_off_greys_out_and_shows_effective_values_without_saving(self) -> None:
        app = FakeApp(injection=False)
        app._sync_overlay_dependent_switches()
        self.assertFalse(app.show_overlay_var.get())
        self.assertFalse(app.overlay_performance_mode_var.get())
        self.assertFalse(app.show_stadium_loading_var.get())
        self.assertTrue(app.random_stadium_selection_var.get())  # no picker without the DLL
        for switch in (app.overlay_switch, app.notification_switch, app.performance_mode_switch,
                       app.random_stadium_switch):
            self.assertTrue(switch.disabled)
        self.assertEqual(
            (app.settings.show_overlay, app.settings.overlay_performance_mode,
             app.settings.random_stadium_selection, app.settings.show_stadium_loading_notification),
            (True, True, False, True),
        )
        # Kit hotkeys still need the pad poll thread here, only the key one goes.
        self.assertIn("uninstall_key_poll", app.events)
        self.assertNotIn("uninstall_pad_poll", app.events)

    def test_on_again_restores_saved_choices(self) -> None:
        app = FakeApp(injection=False)
        app._sync_overlay_dependent_switches()
        app.overlay_injection_var.value = True
        app._toggle_overlay_injection()
        self.assertTrue(app.show_overlay_var.get())
        self.assertTrue(app.overlay_performance_mode_var.get())
        self.assertTrue(app.show_stadium_loading_var.get())
        self.assertFalse(app.random_stadium_selection_var.get())
        for switch in (app.overlay_switch, app.notification_switch, app.performance_mode_switch,
                       app.random_stadium_switch):
            self.assertFalse(switch.disabled)

    def test_off_hides_a_loading_notice_already_on_screen(self) -> None:
        app = FakeApp(injection=False)
        app._stadium_loading_visible = True
        app._sync_overlay_dependent_switches()
        self.assertIn("hide_loading_notice", app.events)

    def test_switching_off_live_releases_then_greys_out(self) -> None:
        app = FakeApp(injection=True)
        app._d3d_injector = FakeInjector()
        app.overlay_injection_var.value = False
        app._toggle_overlay_injection()
        self.assertIsNone(app._d3d_injector)
        self.assertTrue(app.overlay_switch.disabled)
        self.assertTrue(app.random_stadium_selection_var.get())


if __name__ == "__main__":
    unittest.main()
