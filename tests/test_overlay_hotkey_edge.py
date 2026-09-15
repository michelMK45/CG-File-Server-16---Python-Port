from __future__ import annotations

import threading
import time
import unittest

from server16_py.app_overlay import OverlayMixin
from server16_py.win32_types import VK_F12


class FakeUser32:
    """Threadsafe stand-in for ctypes' user32: a plain set of "currently
    physically held" virtual-key codes, toggled by the test driver from the
    main thread while _hotkey_poll_thread_func polls it from a real
    background thread -- the actual concurrency this bug lives in."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._down: set[int] = set()

    def GetAsyncKeyState(self, vk: int) -> int:
        with self._lock:
            return 0x8000 if vk in self._down else 0

    def press(self, vk: int) -> None:
        with self._lock:
            self._down.add(vk)

    def release(self, vk: int) -> None:
        with self._lock:
            self._down.discard(vk)


class FakeOverlayApp(OverlayMixin):
    """Minimal host for the real OverlayMixin hotkey machinery -- only the
    attributes _install_hotkey_poll_thread/_consume_hotkey_edge/
    _uninstall_hotkey_poll_thread actually touch, plus a tiny stand-in for
    the menu open/close toggle (mirrors _sync_d3d_menu_input's own
    F12-branch decision and _overlay_back_or_close's final-close branch)."""

    def __init__(self) -> None:
        self.user32 = FakeUser32()
        self._hotkey_poll_thread = None
        self._hotkey_poll_stop = threading.Event()
        self._overlay_hotkey_edge_pending: set[int] = set()
        self._overlay_key_edge_pending: set[int] = set()
        self._d3d_menu_visible = False
        self._stadium_picker_pending = False
        self._keyboard_hook = None
        self._overlay_toggle_ready_at = 0.0

    def toggle_tick(self, now: float) -> bool:
        f12_toggle = self._consume_hotkey_edge(VK_F12)
        can_toggle = now >= self._overlay_toggle_ready_at
        if f12_toggle and can_toggle:
            self._d3d_menu_visible = not self._d3d_menu_visible
            self._overlay_toggle_ready_at = now + 0.22
            self._keyboard_hook = object() if self._d3d_menu_visible else None
            return True
        return False

    def close_via_escape(self, now: float) -> None:
        """Mirrors _overlay_back_or_close's final (top-level) close branch."""
        self._d3d_menu_visible = False
        self._overlay_toggle_ready_at = now + 0.22
        self._keyboard_hook = None
        self._overlay_key_edge_pending.clear()


class HotkeyEdgeReopenRegressionTests(unittest.TestCase):
    """Regression coverage for the F12-menu spontaneously reopening itself
    right after being closed via Escape or the on-screen Close button
    (reported live 2026-09-15).

    Root cause: _hotkey_poll_thread_func runs continuously, independent of
    menu state, and (before this fix) added a key to
    _overlay_hotkey_edge_pending on EVERY iteration it observed that key
    down -- not just on the down transition. While the menu is open,
    _consume_hotkey_edge takes the keyboard-hook branch for F12 instead of
    ever draining that poll-based set, so for as long as the SAME physical
    F12 press that opened the menu stayed held (an ordinary keypress often
    lasts 100-500ms), the poll thread kept re-latching it, unconsumed. The
    moment the menu closed by ANY means, the very next tick took the
    poll-based branch again, found that stale entry, and treated it as a
    brand new press -- reopening the menu once the 0.22s
    _overlay_toggle_ready_at cooldown allowed it, often within a fraction
    of a second of the close. Confirmed live via direct simulation before
    this fix: an F12 hold as ordinary as ~300ms, combined with closing the
    menu within ~100ms of opening it, reproduced this on every run.

    Fixed by (1) making _hotkey_poll_thread_func itself edge-triggered
    (only latches on a genuine not-down -> down transition, so a single
    held press can never re-arm the pending set no matter how long it's
    held), and (2) having _consume_hotkey_edge's hook branch also drain any
    poll-based entry for F12 every tick the menu is open, so even a
    genuine SECOND press occurring while the menu is already open (e.g. an
    attempt to close via F12 itself) can't survive unconsumed until a
    later close by some other method."""

    def _run_scenario(self, hold_seconds: float, close_delay_seconds: float, total_seconds: float | None = None):
        """Presses F12 to open the menu, releases it after `hold_seconds`,
        closes the menu via Escape `close_delay_seconds` after it opened
        (independent of whether F12 has been released yet), then keeps
        polling watching for a spontaneous reopen -- just long enough to
        clear _overlay_toggle_ready_at's 0.22s post-close cooldown with a
        comfortable margin, not a fixed long duration, so this stays fast.
        Returns the list of (tick-relative) times a reopen fired."""
        if total_seconds is None:
            total_seconds = max(hold_seconds, close_delay_seconds) + 0.22 + 0.3
        app = FakeOverlayApp()
        app._install_hotkey_poll_thread()
        try:
            start = time.perf_counter()
            app.user32.press(VK_F12)
            opened = False
            opened_at: float | None = None
            closed = False
            released = False
            reopened: list[float] = []
            while True:
                now = time.perf_counter() - start
                if now >= total_seconds:
                    break
                if not released and now >= hold_seconds:
                    app.user32.release(VK_F12)
                    released = True
                if not opened:
                    if app.toggle_tick(now):
                        opened = True
                        opened_at = now
                else:
                    if not closed and opened_at is not None and now >= opened_at + close_delay_seconds:
                        app.close_via_escape(now)
                        closed = True
                    elif closed and not app._d3d_menu_visible:
                        if app.toggle_tick(now):
                            reopened.append(now)
                time.sleep(0.01)
            self.assertTrue(opened, "menu never opened -- test harness itself is broken")
            self.assertTrue(closed, "menu never closed -- test harness itself is broken")
            return reopened
        finally:
            app._uninstall_hotkey_poll_thread()

    def test_ordinary_hold_with_quick_close_does_not_reopen(self) -> None:
        # A representative sample of the exact envelope confirmed live to
        # reproduce the bug before this fix: F12 held ~300-500ms (an
        # unremarkable keypress duration) while the menu is closed only a
        # fraction of a second after opening. (The pre-fix bug was
        # confirmed via a much larger parameter sweep during development;
        # kept small here so this test stays fast.)
        for close_delay, hold in ((0.02, 0.30), (0.05, 0.40), (0.15, 0.50)):
            with self.subTest(close_delay=close_delay, hold=hold):
                reopened = self._run_scenario(hold_seconds=hold, close_delay_seconds=close_delay)
                self.assertEqual(reopened, [])

    def test_long_hold_spanning_past_the_close_does_not_reopen(self) -> None:
        # F12 still physically held well past the close and its 0.22s
        # cooldown -- the other shape of the original bug (CLAUDE.md's own
        # "Overlay input reliability" history documents users holding F12
        # a beat longer than usual out of doubt it registered).
        for hold in (0.5, 0.8):
            with self.subTest(hold=hold):
                reopened = self._run_scenario(hold_seconds=hold, close_delay_seconds=0.35)
                self.assertEqual(reopened, [])

    def test_second_f12_tap_while_menu_already_open_does_not_survive_to_reopen_later(self) -> None:
        """A genuine second F12 press while the menu is open (e.g. trying
        to close with F12 itself, handled correctly via the keyboard-hook
        branch) must not leave a poll-based ghost that fires once the menu
        is later closed by a completely different method."""
        app = FakeOverlayApp()
        app._install_hotkey_poll_thread()
        try:
            start = time.perf_counter()
            app.user32.press(VK_F12)
            opened = False
            second_tap_done = False
            closed = False
            reopened: list[float] = []
            while True:
                now = time.perf_counter() - start
                if now >= 0.5 + 0.22 + 0.3:
                    break
                if not opened:
                    if now >= 0.10:
                        app.user32.release(VK_F12)
                    if app.toggle_tick(now):
                        opened = True
                else:
                    if not second_tap_done and now >= 0.30:
                        app.user32.press(VK_F12)
                        second_tap_done = True
                    elif second_tap_done and now >= 0.34 and app.user32.GetAsyncKeyState(VK_F12):
                        app.user32.release(VK_F12)
                    if not closed and now >= 0.5:
                        app.close_via_escape(now)
                        closed = True
                    elif closed and not app._d3d_menu_visible:
                        if app.toggle_tick(now):
                            reopened.append(now)
                time.sleep(0.01)
            self.assertTrue(opened)
            self.assertTrue(closed)
            self.assertEqual(reopened, [])
            self.assertEqual(app._overlay_hotkey_edge_pending, set())
        finally:
            app._uninstall_hotkey_poll_thread()


if __name__ == "__main__":
    unittest.main()
