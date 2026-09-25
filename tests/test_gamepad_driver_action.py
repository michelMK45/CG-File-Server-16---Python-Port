from __future__ import annotations

import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from server16_py import app_ui


class RestartDialogAfterDriverInstallTests(unittest.TestCase):
    """vgamepad only connects to ViGEmBus while it is imported at launch, so
    right after Install Driver the app must be relaunched before bridging can
    start -- the button tells the user so. It must not nag after an uninstall
    or a failed install, where relaunching changes nothing."""

    def _press_button(self, installed_before: bool, success: bool) -> mock.Mock:
        """Presses the driver button with the bridge reporting `installed_before`;
        the (un)install completes at once with `success`. Returns showinfo's mock."""
        calls: list[tuple[bool, str]] = []

        def finish(on_done):
            on_done(success, "message")
            return True

        bridge = SimpleNamespace(
            is_vigembus_installed=lambda: installed_before,
            install_vigembus=lambda on_done: finish(on_done),
            uninstall_vigembus=lambda on_done: finish(on_done),
        )
        fake = SimpleNamespace(
            gamepad_bridge=bridge,
            gamepad_driver_action_button=SimpleNamespace(configure=lambda **kw: calls.append(kw)),
            log=lambda _text: None,
            tr=lambda key, **kw: key,
            _refresh_gamepad_driver_status=lambda: None,
            _refresh_gamepad_slot_rows=lambda: None,
        )
        with mock.patch.object(app_ui.messagebox, "showinfo") as showinfo:
            app_ui.UIMixin._on_gamepad_driver_action(fake)
        return showinfo

    def test_shown_after_a_successful_install(self) -> None:
        showinfo = self._press_button(installed_before=False, success=True)
        showinfo.assert_called_once_with("dialog.gamepads.restart_title", "message.gamepads.restart_required")

    def test_not_shown_after_a_failed_install(self) -> None:
        self._press_button(installed_before=False, success=False).assert_not_called()

    def test_not_shown_after_an_uninstall(self) -> None:
        self._press_button(installed_before=True, success=True).assert_not_called()


class RestartDialogLocaleTests(unittest.TestCase):
    def test_text_exists_in_every_language(self) -> None:
        locales = Path(app_ui.__file__).parent / "locales"
        for language in ("en", "es", "pt"):
            with self.subTest(language=language):
                catalog = json.loads((locales / f"{language}.json").read_text(encoding="utf-8"))
                self.assertTrue(catalog["dialog.gamepads.restart_title"].strip())
                self.assertTrue(catalog["message.gamepads.restart_required"].strip())


if __name__ == "__main__":
    unittest.main()
