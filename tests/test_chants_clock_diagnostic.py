from __future__ import annotations

import struct
import unittest
from types import SimpleNamespace

from server16_py.chants_runtime import ChantsRuntime


class FakeMemory:
    STATS_ADDRESS = 0x1000

    def __init__(self) -> None:
        self.started: int | None = 1
        self.clock: int | None = 0
        self.dash: dict[str, int] = {}
        # Offset -> value for the window around the clock; None = unreadable.
        self.stats: dict[int, int] | None = None

    def get_int(self, base, _offsets) -> int:
        if base in ("dash_minutes", "dash_seconds"):
            return self.dash[base]
        value = self.started if base == "started" else self.clock
        if value is None:
            raise OSError("unreadable")
        return value

    def resolve_pointer(self, base, offsets) -> int:
        if base != "stats" or self.stats is None:
            raise OSError("unreadable")
        self.window_start = offsets[-1]
        return self.STATS_ADDRESS

    def read_process_memory(self, address: int, size: int) -> bytes:
        assert address == self.STATS_ADDRESS
        offsets = range(self.window_start, self.window_start + size, 4)
        return struct.pack(f"<{size // 4}I", *(self.stats.get(offset, 0) for offset in offsets))


class FakeApp:
    def __init__(self) -> None:
        self.offsets = SimpleNamespace(
            GAMESTARTEDBINARYBASE="started",
            GAMESTARTEDBINARY=[0],
            GAMESTATSBASE="stats",
            GAMERANTIME=[0],
            DASHBOARDMINUTESBASE="dash_minutes",
            DASHBOARDMINUTES=[0],
            DASHBOARDSECONDSBASE="dash_seconds",
            DASHBOARDSECONDS=[0],
        )
        self.lastpagename = ""
        self._entrance_pre_match_guard = True
        self._entrance_active = False
        self.logs: list[str] = []

    def log(self, message: str, *_args, **_kwargs) -> None:
        self.logs.append(message)


class ClockDiagnosticTests(unittest.TestCase):
    """ChantsRuntime._log_clock_diagnostic: the log line added to settle the
    "Waiting for kick-off" reports (docs/bugs-entrance.md Part 18)."""

    def setUp(self) -> None:
        self.app = FakeApp()
        self.memory = FakeMemory()
        self.chants = ChantsRuntime(self.app)

    def test_reports_the_rate_over_the_window_not_per_tick(self) -> None:
        # 4.5 units/s is what the guard's own 0.2s tick can never see: one
        # unit per tick reads as 4.8/s there, under its 6.0 threshold.
        self.memory.clock = 100
        self.chants._log_clock_diagnostic(self.memory, now=10.0)
        self.memory.clock = 109
        self.chants._log_clock_diagnostic(self.memory, now=12.0)
        self.assertEqual(len(self.app.logs), 2)
        self.assertIn("first sample", self.app.logs[0])
        self.assertIn("clock=109 (+9 in 2.0s = 4.5/s)", self.app.logs[1])
        self.assertIn("started=1", self.app.logs[1])
        self.assertIn("guard=True entrance=False page=''", self.app.logs[1])

    def test_samples_every_two_seconds_with_the_guard_and_five_without(self) -> None:
        self.chants._log_clock_diagnostic(self.memory, now=10.0)
        self.memory.clock = 5
        self.chants._log_clock_diagnostic(self.memory, now=11.9)
        self.assertEqual(len(self.app.logs), 1)
        self.chants._log_clock_diagnostic(self.memory, now=12.0)
        self.assertEqual(len(self.app.logs), 2)

        self.app._entrance_pre_match_guard = False
        self.memory.clock = 20
        self.chants._log_clock_diagnostic(self.memory, now=16.9)
        self.assertEqual(len(self.app.logs), 2)
        self.chants._log_clock_diagnostic(self.memory, now=17.0)
        self.assertEqual(len(self.app.logs), 3)
        self.assertIn("(+15 in 5.0s = 3.0/s) guard=False", self.app.logs[2])

    def test_a_frozen_clock_is_logged_once_until_something_changes(self) -> None:
        self.memory.clock = 300
        for now in (10.0, 12.0, 14.0, 16.0):
            self.chants._log_clock_diagnostic(self.memory, now=now)
        self.assertEqual(len(self.app.logs), 2)
        self.assertIn("(+0 in 2.0s = 0.0/s)", self.app.logs[1])

        # A page change is worth a line even though the clock is still frozen.
        self.app.lastpagename = "game/screens/fluxHub/FluxHub"
        self.chants._log_clock_diagnostic(self.memory, now=18.0)
        self.assertEqual(len(self.app.logs), 3)

        # Movement after the frozen stretch is measured over the last window
        # only, not since the clock stopped.
        self.memory.clock = 304
        self.chants._log_clock_diagnostic(self.memory, now=20.0)
        self.assertIn("(+4 in 2.0s = 2.0/s)", self.app.logs[3])

    def test_a_clock_restart_shows_as_a_negative_delta(self) -> None:
        self.memory.clock = 2700
        self.chants._log_clock_diagnostic(self.memory, now=10.0)
        self.memory.clock = 3
        self.chants._log_clock_diagnostic(self.memory, now=12.0)
        self.assertIn("clock=3 (-2697 in 2.0s", self.app.logs[1])

    def test_unreadable_memory_is_logged_once_and_never_raises(self) -> None:
        self.memory.started = None
        self.memory.clock = None
        for now in (10.0, 12.0, 14.0):
            self.chants._log_clock_diagnostic(self.memory, now=now)
        self.assertEqual(len(self.app.logs), 2)
        self.assertIn("started=None clock=None (unreadable)", self.app.logs[1])

    def test_stats_window_is_dumped_once_then_only_its_changes(self) -> None:
        self.memory.stats = {5484: 1, 5488: 0, 5492: 7, 5500: 100}
        self.memory.clock = 100
        self.chants._log_clock_diagnostic(self.memory, now=10.0)
        first = self.app.logs[0]
        self.assertIn("stats[+5436=0 ", first)
        self.assertIn(" +5484=1 +5488=0 +5492=7 +5496=0 +5500=100 ", first)
        self.assertTrue(first.endswith("+5560=0]"))

        self.memory.stats[5492] = 8
        self.memory.stats[5500] = 109
        self.memory.clock = 109
        self.chants._log_clock_diagnostic(self.memory, now=12.0)
        self.assertTrue(self.app.logs[1].endswith("stats[+5492:7>8 +5500:100>109]"))

    def test_a_neighbouring_field_changing_is_logged_over_a_frozen_clock(self) -> None:
        # The whole point of the dump: a "period"/"state" field would flip at
        # kick-off or half-time while the clock itself stands still.
        self.memory.stats = {5496: 0}
        for now in (10.0, 12.0, 14.0):
            self.chants._log_clock_diagnostic(self.memory, now=now)
        self.assertEqual(len(self.app.logs), 2)
        self.assertTrue(self.app.logs[1].endswith("stats[=]"))

        self.memory.stats[5496] = 1
        self.chants._log_clock_diagnostic(self.memory, now=16.0)
        self.assertEqual(len(self.app.logs), 3)
        self.assertTrue(self.app.logs[2].endswith("stats[+5496:0>1]"))

    def test_dashboard_clock_is_reported_and_tolerates_a_dead_chain(self) -> None:
        self.chants._log_clock_diagnostic(self.memory, now=10.0)
        self.assertIn("dash=None:None stats[unreadable]", self.app.logs[0])

        self.memory.dash = {"dash_minutes": 12, "dash_seconds": 34}
        self.chants._log_clock_diagnostic(self.memory, now=12.0)
        self.assertIn("dash=12:34 ", self.app.logs[1])


if __name__ == "__main__":
    unittest.main()
