from __future__ import annotations

import ctypes
import threading
import time
import unittest

from server16_py.app_overlay import OverlayMixin
from server16_py.win32_types import XINPUT_STATE, XINPUT_SUCCESS


class FakeXInputDll:
    """Stand-in for the real xinput1_4.dll XInputGetState entry point.
    Writes directly into the caller's XINPUT_STATE via the byref proxy's
    own _obj backref -- the same struct-by-reference calling convention
    _get_gamepad_snapshot actually uses against the real DLL."""

    def __init__(self) -> None:
        self.buttons = 0
        self.rx = 0
        self.ry = 0
        self.ly = 0
        self.lx = 0

    def XInputGetState(self, _index: int, state_ref) -> int:
        state: XINPUT_STATE = state_ref._obj
        state.Gamepad.wButtons = self.buttons
        state.Gamepad.sThumbLX = self.lx
        state.Gamepad.sThumbLY = self.ly
        state.Gamepad.sThumbRX = self.rx
        state.Gamepad.sThumbRY = self.ry
        return XINPUT_SUCCESS


class FakeOverlayApp(OverlayMixin):
    """Minimal host for the real OverlayMixin gamepad-snapshot machinery --
    only the attributes _get_gamepad_snapshot/_consume_gamepad_state/
    _gamepad_poll_thread_func actually touch."""

    def __init__(self, xinput: FakeXInputDll) -> None:
        self._xinput = xinput
        self._active_gamepad_index = 0
        self._gamepad_poll_thread: threading.Thread | None = None
        self._gamepad_poll_stop = threading.Event()
        self._gamepad_poll_lock = threading.Lock()
        self._overlay_gp_latched_buttons = 0
        self._overlay_gp_raw_buttons = 0
        self._overlay_gp_raw_rx = 0
        self._overlay_gp_raw_ry = 0
        self._overlay_gp_raw_ly = 0
        self._overlay_gp_raw_lx = 0


class GamepadLeftStickXAxisTests(unittest.TestCase):
    """Regression coverage for the Stadiums filter grid's left analog stick
    only ever moving the selection up/down, never left/right (reported live
    2026-09-15), while the D-pad worked correctly in all four directions.

    Root cause: _get_gamepad_snapshot never read XINPUT_GAMEPAD.sThumbLX at
    all -- only sThumbRX/sThumbRY/sThumbLY were ever pulled out of the
    struct and threaded through _gamepad_poll_thread_func /
    _consume_gamepad_state. No left/right stick deadzone check in
    _sync_d3d_menu_input's filter-grid navigation block could ever fire,
    since the value feeding it was never captured in the first place -- the
    D-pad was unaffected because DPAD_LEFT/RIGHT come from the separate
    wButtons bitmask, not a thumbstick axis."""

    def test_snapshot_reads_left_stick_x_axis(self) -> None:
        xinput = FakeXInputDll()
        xinput.lx = 20000
        app = FakeOverlayApp(xinput)
        _buttons, _rx, _ry, _ly, lx = app._get_gamepad_snapshot()
        self.assertEqual(lx, 20000)

    def test_consume_gamepad_state_fallback_path_propagates_lx(self) -> None:
        """No poll thread running -- _consume_gamepad_state falls back to a
        direct single sample, and that fallback tuple must include LX too."""
        xinput = FakeXInputDll()
        xinput.lx = -15000
        app = FakeOverlayApp(xinput)
        _edge, _raw, _rx, _ry, _ly, lx = app._consume_gamepad_state()
        self.assertEqual(lx, -15000)

    def test_poll_thread_latches_and_consume_returns_lx(self) -> None:
        """The real path used while the overlay menu is open: a background
        poll thread samples XInput continuously, and _consume_gamepad_state
        reads back whatever it last latched -- LX must survive that trip
        too, not just the direct fallback sample above."""
        xinput = FakeXInputDll()
        app = FakeOverlayApp(xinput)
        app._install_gamepad_poll_thread()
        try:
            xinput.lx = 18000
            deadline = time.perf_counter() + 1.0
            lx = 0
            while time.perf_counter() < deadline:
                _edge, _raw, _rx, _ry, _ly, lx = app._consume_gamepad_state()
                if lx == 18000:
                    break
                time.sleep(0.01)
            self.assertEqual(lx, 18000)
        finally:
            app._uninstall_gamepad_poll_thread()


if __name__ == "__main__":
    unittest.main()
