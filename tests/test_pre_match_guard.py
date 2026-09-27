from __future__ import annotations

import unittest
from unittest.mock import patch

from server16_py.chants_runtime import ChantsRuntime


class FakeOffsets:
    GAMESTATSBASE = 0x1
    GAMERANTIME = [0x1]


class FakeMemory:
    """Feeds a scripted sequence of GAMERANTIME reads, one per call --
    None means "read failed" (mirrors a real Memory.get_int raising,
    caught internally). Same pattern as tests/test_scoreboard_name_progress.py.
    """

    def __init__(self, readings: list[int | None] | None = None) -> None:
        self._readings = list(readings or [])

    def get_int(self, *_args, **_kwargs) -> int:
        if not self._readings:
            raise RuntimeError("no more scripted readings")
        value = self._readings.pop(0)
        if value is None:
            raise RuntimeError("simulated read failure")
        return value


class FakeApp:
    def __init__(self) -> None:
        self.offsets = FakeOffsets()
        self._entrance_pre_match_guard = True
        self._entrance_pre_match_guard_set_at = 0.0
        self.logs: list[str] = []

    def log(self, *parts) -> None:
        self.logs.append(" ".join(str(p) for p in parts))


class PreMatchGuardTickTests(unittest.TestCase):
    """Covers ChantsRuntime._pre_match_guard_tick, the sole thing that can
    ever clear `app._entrance_pre_match_guard` once TeamEntrance's own
    worker gives up without confirming kick-off (or never runs at all --
    the guard is armed unconditionally on TV/bumper regardless of whether
    TeamEntrance is configured/enabled, see app_game.py). Reported live
    2026-09-27: with real gameplay's clock speed never sustaining the
    `speed >= 6.0` threshold this heuristic requires (theorized, not yet
    confirmed live, to be a long FIFA "Half Length" setting -- see the
    class-level comment on MAX_PRE_MATCH_GUARD_SECONDS), Support chants
    stayed stuck on "Waiting for kick-off" for an entire match. See
    docs/bugs-entrance.md Part 14.
    """

    def setUp(self) -> None:
        self.app = FakeApp()
        self.chants = ChantsRuntime(self.app)

    def test_releases_on_three_consecutive_high_speed_hits(self) -> None:
        memory = FakeMemory([0, 10, 20, 30])
        times = iter([0.0, 0.2, 0.4, 0.6, 0.8])
        pre_match_last_time: int | None = None
        pre_match_last_real: float | None = None
        pre_match_speed_hits = 0
        released = False
        with patch("server16_py.chants_runtime.time.time", side_effect=lambda: next(times)):
            for _ in range(4):
                released, pre_match_last_time, pre_match_last_real, pre_match_speed_hits = (
                    self.chants._pre_match_guard_tick(
                        memory, pre_match_last_time, pre_match_last_real, pre_match_speed_hits
                    )
                )
                if released:
                    break
        self.assertTrue(released)
        self.assertFalse(self.app._entrance_pre_match_guard)
        self.assertTrue(any("released at clock speed" in line for line in self.app.logs))

    def test_holds_guard_while_clock_is_static_like_the_walkout(self) -> None:
        # The walkout's own clock reads as static/near-static (per
        # docs/team-entrance.md) -- must never be mistaken for kick-off.
        memory = FakeMemory([0, 0, 0, 0])
        times = iter([0.0, 0.2, 0.4, 0.6])
        pre_match_last_time: int | None = None
        pre_match_last_real: float | None = None
        pre_match_speed_hits = 0
        with patch("server16_py.chants_runtime.time.time", side_effect=lambda: next(times)):
            for _ in range(4):
                released, pre_match_last_time, pre_match_last_real, pre_match_speed_hits = (
                    self.chants._pre_match_guard_tick(
                        memory, pre_match_last_time, pre_match_last_real, pre_match_speed_hits
                    )
                )
                self.assertFalse(released)
        self.assertTrue(self.app._entrance_pre_match_guard)

    def test_force_releases_after_max_duration_even_if_speed_never_confirms(self) -> None:
        # The regression this test guards against: real gameplay whose
        # observed speed never reaches the 6.0 threshold (e.g. a long Half
        # Length) used to leave the guard held forever, since nothing else
        # ever clears it. A slow-but-nonzero clock (never 3 consecutive
        # speed>=6.0 hits) must still get force-released once
        # MAX_PRE_MATCH_GUARD_SECONDS has elapsed since it was armed.
        memory = FakeMemory([0, 1, 2, 3])
        guard_set_at = 1000.0
        self.app._entrance_pre_match_guard_set_at = guard_set_at
        times = iter(
            [
                guard_set_at + 0.2,
                guard_set_at + 0.4,
                guard_set_at + 0.6,
                guard_set_at + self.chants.MAX_PRE_MATCH_GUARD_SECONDS + 1.0,
            ]
        )
        pre_match_last_time: int | None = None
        pre_match_last_real: float | None = None
        pre_match_speed_hits = 0
        released = False
        with patch("server16_py.chants_runtime.time.time", side_effect=lambda: next(times)):
            for _ in range(4):
                released, pre_match_last_time, pre_match_last_real, pre_match_speed_hits = (
                    self.chants._pre_match_guard_tick(
                        memory, pre_match_last_time, pre_match_last_real, pre_match_speed_hits
                    )
                )
                if released:
                    break
        self.assertTrue(released)
        self.assertFalse(self.app._entrance_pre_match_guard)
        self.assertTrue(any("force-released" in line for line in self.app.logs))

    def test_does_not_force_release_before_max_duration(self) -> None:
        memory = FakeMemory([0])
        guard_set_at = 1000.0
        self.app._entrance_pre_match_guard_set_at = guard_set_at
        with patch(
            "server16_py.chants_runtime.time.time",
            return_value=guard_set_at + self.chants.MAX_PRE_MATCH_GUARD_SECONDS - 1.0,
        ):
            released, _, _, _ = self.chants._pre_match_guard_tick(memory, None, None, 0)
        self.assertFalse(released)
        self.assertTrue(self.app._entrance_pre_match_guard)
        self.assertFalse(any("force-released" in line for line in self.app.logs))


if __name__ == "__main__":
    unittest.main()
