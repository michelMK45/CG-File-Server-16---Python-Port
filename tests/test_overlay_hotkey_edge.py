from __future__ import annotations

import ctypes
import threading
import time
import types
import unittest

from server16_py.app_overlay import OverlayMixin
from server16_py.input_bindings import KIT_TYPE, OVERLAY_MENU, TEAM_KITS, InputBindings, KeyBinding
from server16_py.win32_types import HC_ACTION, KBDLLHOOKSTRUCT, VK_F12, WM_KEYDOWN, WM_KEYUP

VK_F5 = 0x74


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
        self.input_bindings = InputBindings.defaults()
        self._hotkey_poll_thread = None
        self._hotkey_poll_stop = threading.Event()
        self._overlay_hotkey_edge_pending: set[int] = set()
        self._kit_hotkey_edge_pending: set[int] = set()
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


class CustomBindingHotkeyEdgeTests(unittest.TestCase):
    """Settings > Controls: the poll thread and _consume_hotkey_edge follow
    whatever keys are bound, not F12/F7-F11."""

    @staticmethod
    def _wait_until(condition, timeout: float = 1.0) -> bool:
        deadline = time.perf_counter() + timeout
        while time.perf_counter() < deadline:
            if condition():
                return True
            time.sleep(0.01)
        return condition()

    def test_a_key_bound_while_held_is_not_latched_but_its_next_press_is(self) -> None:
        app = FakeOverlayApp()
        app._install_hotkey_poll_thread()
        try:
            app.user32.press(VK_F5)                  # pressed in the capture dialog...
            time.sleep(0.05)
            app.input_bindings = app.input_bindings.with_key(OVERLAY_MENU, KeyBinding(VK_F5))   # ...and bound
            time.sleep(0.05)
            self.assertNotIn(VK_F5, app._overlay_hotkey_edge_pending)
            app.user32.release(VK_F5)
            time.sleep(0.05)
            app.user32.press(VK_F5)
            self.assertTrue(self._wait_until(lambda: VK_F5 in app._overlay_hotkey_edge_pending))
            self.assertNotIn(VK_F5, app._kit_hotkey_edge_pending)    # not a kit hotkey's key
        finally:
            app._uninstall_hotkey_poll_thread()

    def test_a_key_the_overlay_and_a_kit_hotkey_share_reaches_both(self) -> None:
        app = FakeOverlayApp()
        # F12 opens the overlay, F12 held changes the kit type.
        app.input_bindings = (
            app.input_bindings.with_key(TEAM_KITS, KeyBinding()).with_key(KIT_TYPE, KeyBinding(VK_F12, True))
        )
        app._install_hotkey_poll_thread()
        try:
            time.sleep(0.03)
            app.user32.press(VK_F12)
            self.assertTrue(self._wait_until(
                lambda: VK_F12 in app._overlay_hotkey_edge_pending and VK_F12 in app._kit_hotkey_edge_pending
            ))
            self.assertTrue(app._consume_hotkey_edge(VK_F12))
            self.assertTrue(app._consume_kit_hotkey_edge(VK_F12))
            self.assertFalse(app._consume_kit_hotkey_edge(VK_F12))
        finally:
            app._uninstall_hotkey_poll_thread()

    def test_a_custom_overlay_key_closes_the_open_menu_through_the_hook(self) -> None:
        app = FakeOverlayApp()
        app.input_bindings = (
            app.input_bindings.with_key(OVERLAY_MENU, KeyBinding(VK_F5)).with_key(TEAM_KITS, KeyBinding())
        )
        app._d3d_menu_visible = True
        app._keyboard_hook = object()
        app._overlay_hotkey_edge_pending.add(VK_F5)  # the poll thread's latch of the opening press
        app._overlay_key_edge_pending.add(VK_F5)     # the hook's latch of the new one
        self.assertTrue(app._consume_hotkey_edge(VK_F5))
        self.assertEqual(app._overlay_hotkey_edge_pending, set())
        # F12 isn't the menu's key any more: the hook doesn't track it.
        app._overlay_key_edge_pending.add(VK_F12)
        self.assertFalse(app._consume_hotkey_edge(VK_F12))


class FakeHookUser32(FakeUser32):
    """user32 for _keyboard_hook_thread_func run on the test thread: keeps the
    hook procedure it installs (so the test can call it with real
    KBDLLHOOKSTRUCTs), records what is passed on, and ends the message loop
    at once. GetAsyncKeyState is the system's view of the keys."""

    PASSED = 7   # what CallNextHookEx returns, to tell "passed on" from "eaten" (1)

    def __init__(self) -> None:
        super().__init__()
        self.proc = None
        self.passed: list[tuple[int, int]] = []

    def SetWindowsHookExW(self, _kind, proc, _module, _thread) -> int:
        self.proc = proc
        return 1

    def CallNextHookEx(self, _hook, _code, w_param, l_param) -> int:
        info = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
        self.passed.append((int(w_param), int(info.vkCode)))
        return self.PASSED

    def GetMessageW(self, *_args) -> int:
        return 0

    def UnhookWindowsHookEx(self, _hook) -> int:
        return 1


class KeyboardHookReleaseTests(unittest.TestCase):
    """The menu's keyboard hook eats its keys from FIFA, but a key's release
    goes where its press went: eating the WM_KEYUP of a press the system saw
    (the F12 press that opened the menu) left GetAsyncKeyState reporting F12
    down after the menu closed, and "F12 held" reopened it on Team Kits."""

    def setUp(self) -> None:
        app = FakeOverlayApp()
        app.user32 = FakeHookUser32()
        app.kernel32 = types.SimpleNamespace(GetModuleHandleW=lambda _name: 0, GetCurrentThreadId=lambda: 1)
        app._overlay_blocked_key_down = set()
        app._d3d_menu_visible = True
        app._is_overlay_input_foreground = lambda: True
        app._keyboard_hook_thread_func()   # installs the hook, the loop ends at once
        self.assertIsNotNone(app.user32.proc)
        app._keyboard_hook = 1
        self.app = app

    def send(self, msg: int, vk: int) -> int:
        info = KBDLLHOOKSTRUCT(vkCode=vk)
        return int(self.app.user32.proc(HC_ACTION, msg, ctypes.addressof(info)))

    def test_releasing_the_key_that_opened_the_menu_reaches_the_system(self) -> None:
        self.app.user32.press(VK_F12)                    # went down before the hook was in
        self.app._overlay_blocked_key_down.add(VK_F12)   # seeded when it was installed
        self.assertEqual(self.send(WM_KEYUP, VK_F12), FakeHookUser32.PASSED)
        self.assertEqual(self.app.user32.passed, [(WM_KEYUP, VK_F12)])
        self.assertNotIn(VK_F12, self.app._overlay_blocked_key_down)

    def test_a_key_pressed_with_the_menu_open_stays_eaten_both_ways(self) -> None:
        self.assertEqual(self.send(WM_KEYDOWN, VK_F12), 1)
        self.assertIn(VK_F12, self.app._overlay_blocked_key_down)
        self.assertIn(VK_F12, self.app._overlay_key_edge_pending)
        self.assertEqual(self.send(WM_KEYUP, VK_F12), 1)
        self.assertNotIn(VK_F12, self.app._overlay_blocked_key_down)
        self.assertEqual(self.app.user32.passed, [])


if __name__ == "__main__":
    unittest.main()
