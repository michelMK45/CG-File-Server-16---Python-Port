from __future__ import annotations

import sys
import types
import unittest

# app_game only needs the tkinter name inside unrelated UI methods -- same
# minimal stub pattern as tests/test_scoreboard_name_progress.py.
tkinter_stub = types.ModuleType("tkinter")
tkinter_stub.Label = lambda: None
sys.modules.setdefault("tkinter", tkinter_stub)

from server16_py.app_game import GameMixin
from server16_py.memory_access import MemoryAccessError


class FakeMemory:
    """Scriptable stand-in for memory_access.Memory -- tracks calls instead
    of touching real process memory."""

    def __init__(self) -> None:
        self.open = True
        self.get_int_calls: list[tuple[int, tuple[int, ...]]] = []
        # static_ptr -> either an int result or an Exception instance to raise
        self.responses: dict[int, object] = {}

    def is_open(self) -> bool:
        return self.open

    def get_int(self, static_ptr: int, offsets: list[int]) -> int:
        self.get_int_calls.append((static_ptr, tuple(offsets)))
        response = self.responses.get(static_ptr, MemoryAccessError(f"Null pointer at 0x{static_ptr:X}"))
        if isinstance(response, Exception):
            raise response
        return response


class FakeOffsets:
    ORIHTIDBASE = 100
    ORIFRIHTIDBASE = 200
    HT = [1, 2, 3, 4, 5, 6]
    HT2 = [7, 8, 9, 10, 11, 12]


class FakeGame(GameMixin):
    def __init__(self) -> None:
        self.MP = "fifa16"
        self.memory = FakeMemory()
        self.offsets = FakeOffsets()
        self._last_context_error: dict[str, str] = {}
        self.logs: list[str] = []
        self.pointer_debug_calls = 0

    def log(self, *parts) -> None:
        self.logs.append(" ".join(str(p) for p in parts))

    def _log_pointer_debug(self) -> None:
        self.pointer_debug_calls += 1


class TryReadContextIntDedupTests(unittest.TestCase):
    """Real bug found live 2026-09-21 while investigating a user report of
    "memory read errors during runtime": `_last_context_error` used to be a
    single shared string, but refresh_live_context checks up to 8 different
    trace_name fields (HT-HID, HT-AID, S-FIRST, ...) every cycle -- so
    whichever field was checked most recently always overwrote the slot,
    and every OTHER field's "same failure as last time" check compared
    against the wrong field's message and always came out True, defeating
    the de-duplication entirely. In practice this meant every one of those
    8 fields logged its full message plus a full 8-line pointer-trace dump
    on essentially every ~250-500ms poll tick throughout all pre-match menu
    navigation, not just once per genuinely new failure.
    """

    def test_two_different_fields_each_log_their_own_first_failure(self) -> None:
        game = FakeGame()
        game._try_read_context_int("HT-HID", 100, [1, 2], "team/Select")
        game._try_read_context_int("HT-AID", 100, [3, 4], "team/Select")
        self.assertEqual(len(game.logs), 2)
        self.assertEqual(game.pointer_debug_calls, 2)

    def test_repeating_the_same_field_failure_does_not_log_again(self) -> None:
        # The exact bug: field A fails, a DIFFERENT field B fails (changing
        # the old single shared slot), then field A fails again with the
        # IDENTICAL message -- must not be mistaken for a new failure.
        game = FakeGame()
        game._try_read_context_int("HT-HID", 100, [1, 2], "team/Select")
        game._try_read_context_int("HT-AID", 100, [3, 4], "team/Select")
        game.logs.clear()
        game.pointer_debug_calls = 0

        game._try_read_context_int("HT-HID", 100, [1, 2], "team/Select")
        self.assertEqual(game.logs, [])
        self.assertEqual(game.pointer_debug_calls, 0)

    def test_a_genuinely_new_message_for_the_same_field_still_logs(self) -> None:
        game = FakeGame()
        game._try_read_context_int("HT-HID", 100, [1, 2], "team/Select")
        game.logs.clear()

        # Different page name -> different message text for the same field.
        game._try_read_context_int("HT-HID", 100, [1, 2], "playNow/KickOffHub")
        self.assertEqual(len(game.logs), 1)

    def test_a_success_for_one_field_does_not_wipe_another_fields_memory(self) -> None:
        # Old bug: get_int succeeding for field B set the single shared slot
        # to None, so field A's next IDENTICAL failure looked "new" again.
        game = FakeGame()
        game.memory.responses[100] = MemoryAccessError("Null pointer at 0x100")
        game.memory.responses[200] = 42  # field B always succeeds
        game._try_read_context_int("HT-HID", 100, [1, 2], "team/Select")
        game._try_read_context_int("HT2-HID", 200, [7, 8], "team/Select")
        game.logs.clear()
        game.pointer_debug_calls = 0

        game._try_read_context_int("HT-HID", 100, [1, 2], "team/Select")
        self.assertEqual(game.logs, [])
        self.assertEqual(game.pointer_debug_calls, 0)


class ReadLegacyTeamContextTests(unittest.TestCase):
    """Reported live as "memory read errors during runtime": this used to
    open and close a brand new Memory() instance -- a full psutil
    process-wide scan plus OpenProcess plus a Toolhelp32 module snapshot --
    on every single call, even though self.memory is already open and
    freshly re-attacked by poll_process just before this runs every ~250-
    500ms throughout all pre-match menu navigation. It also logged a full
    exception traceback with no de-duplication on every expected "not
    resolved yet" failure. Fixed to reuse self.memory and fail silently
    (the caller's own _try_read_context_int fallback already reports a
    genuinely unresolved context, de-duplicated).
    """

    def test_uses_the_existing_open_memory_handle_not_a_new_one(self) -> None:
        game = FakeGame()
        game.memory.responses[100] = 456  # HT[:5] chain (HID)
        game.memory.responses[200] = 0  # never hit unless HID resolves to "0"
        hid, aid = game._read_legacy_team_context()
        self.assertEqual(hid, "456")
        # Confirms the real self.memory instance (tracking calls) was used.
        self.assertTrue(game.memory.get_int_calls)

    def test_failure_is_silent_no_log_no_traceback_spam(self) -> None:
        game = FakeGame()
        # Default FakeMemory response for any unconfigured static_ptr is a
        # MemoryAccessError -- simulates the common "context not ready yet"
        # case during pre-match menu navigation.
        hid, aid = game._read_legacy_team_context()
        self.assertEqual((hid, aid), (None, None))
        self.assertEqual(game.logs, [])

    def test_returns_none_none_when_memory_is_not_open(self) -> None:
        game = FakeGame()
        game.memory.open = False
        hid, aid = game._read_legacy_team_context()
        self.assertEqual((hid, aid), (None, None))
        self.assertEqual(game.memory.get_int_calls, [])


if __name__ == "__main__":
    unittest.main()
