from __future__ import annotations

import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from server16_py.chants_runtime import (
    ChantsRuntime,
    LiveMatchTracker,
    OpenPlayDetector,
    read_open_play_inputs,
)


OPEN_PLAY = OpenPlayDetector.OPEN_PLAY
KICKOFF_PENDING = LiveMatchTracker.KICKOFF_PENDING
NO_LIVE_PLAY = LiveMatchTracker.NO_LIVE_PLAY
LOADING = LiveMatchTracker.LOADING


class OpenPlayDetectorTests(unittest.TestCase):
    """The clock-rate-independent kick-off signal (docs/bugs-entrance.md Part 18)."""

    def test_needs_open_play_and_a_gain_of_two_period_seconds(self) -> None:
        detector = OpenPlayDetector()
        self.assertFalse(detector.update(OPEN_PLAY, 10))
        self.assertFalse(detector.update(OPEN_PLAY, 11))
        self.assertTrue(detector.update(OPEN_PLAY, 12))

    def test_integer_clock_at_real_tick_spacing_for_every_half_length(self) -> None:
        # Period seconds per real second for a 20 / 10 / 6 / 4 minute half. The
        # old "speed >= 6.0 on three consecutive ticks" check needs two units
        # per 0.2s tick, so only the last of these passed reliably.
        for rate in (2.25, 4.5, 7.5, 11.25):
            with self.subTest(rate=rate):
                detector = OpenPlayDetector()
                released_at = None
                for tick in range(1, 40):
                    elapsed = tick * 0.2
                    if detector.update(OPEN_PLAY, int(rate * elapsed)):
                        released_at = elapsed
                        break
                self.assertIsNotNone(released_at)
                self.assertLessEqual(released_at, 2.0)

    def test_a_frozen_clock_never_passes_however_long_it_reads_open_play(self) -> None:
        # Stale match memory (practice arena after Abandon): the flags can say
        # "playing" forever, the clock does not move.
        detector = OpenPlayDetector()
        self.assertFalse(any(detector.update(OPEN_PLAY, 500) for _ in range(200)))

    def test_a_creeping_clock_outside_open_play_never_passes(self) -> None:
        # TV/bumper and dead balls: the clock creeps at ~1 unit/s.
        for state in (NO_LIVE_PLAY, KICKOFF_PENDING, 4, 6, 14, 13, None):
            with self.subTest(state=state):
                detector = OpenPlayDetector()
                self.assertFalse(any(detector.update(state, seconds) for seconds in range(60)))

    def test_every_tick_outside_open_play_starts_the_gain_over(self) -> None:
        detector = OpenPlayDetector()
        self.assertFalse(detector.update(OPEN_PLAY, 10))
        self.assertFalse(detector.update(4, 11))
        self.assertFalse(detector.update(OPEN_PLAY, 12))
        self.assertFalse(detector.update(OPEN_PLAY, 13))
        self.assertTrue(detector.update(OPEN_PLAY, 14))

    def test_an_unreadable_clock_and_reset_start_over_too(self) -> None:
        detector = OpenPlayDetector()
        detector.update(OPEN_PLAY, 10)
        self.assertFalse(detector.update(OPEN_PLAY, None))
        self.assertFalse(detector.update(OPEN_PLAY, 12))
        detector.reset()
        self.assertFalse(detector.update(OPEN_PLAY, 20))

    def test_the_period_clock_restarting_rebases_instead_of_passing(self) -> None:
        # Added time and the second half both restart GAMEPERIODSECONDS.
        detector = OpenPlayDetector()
        detector.update(OPEN_PLAY, 2699)
        self.assertFalse(detector.update(OPEN_PLAY, 0))
        self.assertFalse(detector.update(OPEN_PLAY, 1))
        self.assertTrue(detector.update(OPEN_PLAY, 2))

    def test_reading_the_inputs_tolerates_missing_offsets_and_dead_chains(self) -> None:
        class Memory:
            def get_int(self, _base, offsets):
                if offsets == "state":
                    raise OSError("unreadable")
                return 77

        offsets = SimpleNamespace(GAMESTATSBASE="stats", GAMEPLAYSTATE="state", GAMEPERIODSECONDS="period")
        self.assertEqual(read_open_play_inputs(Memory(), offsets), (None, 77))
        self.assertEqual(read_open_play_inputs(Memory(), SimpleNamespace(GAMESTATSBASE="stats")), (None, None))


class LiveMatchTrackerTests(unittest.TestCase):
    """Readings are (started, play state, clock, period seconds), taken from
    the maintainer's logs of 2026-10-05 (docs/bugs-entrance.md Parts 18-20)."""

    def feed(self, tracker: LiveMatchTracker, readings) -> bool:
        live = tracker.live
        for reading in readings:
            live = tracker.update(*reading)
        return live

    def kicked_off(self) -> LiveMatchTracker:
        tracker = LiveMatchTracker()
        bumper = [(0, NO_LIVE_PLAY, 1, 1), (1, NO_LIVE_PLAY, 3, 3)]
        scene = [(0, KICKOFF_PENDING, 0, 0)] * 3 + [(1, KICKOFF_PENDING, 0, 0)]
        self.assertFalse(self.feed(tracker, bumper + scene + [(1, OPEN_PLAY, 1, 1), (1, OPEN_PLAY, 2, 2)]))
        self.assertTrue(tracker.update(1, OPEN_PLAY, 3, 3))
        return tracker

    def test_goes_live_when_open_play_follows_a_pending_kick_off(self) -> None:
        self.kicked_off()

    def test_the_practice_arena_never_goes_live(self) -> None:
        # Main menu, then the arena: ball "in play", started flag up, clock
        # running at ~7/s -- everything a match has except a kick-off.
        tracker = LiveMatchTracker()
        menu = [(0, NO_LIVE_PLAY, 0, 0)] * 3
        arena = [(1, LOADING, 0, 0)] + [(1, OPEN_PLAY, clock, clock) for clock in range(0, 400, 2)]
        self.assertFalse(self.feed(tracker, menu + arena))

    def test_stays_live_through_a_pause_a_stoppage_and_added_time(self) -> None:
        tracker = self.kicked_off()
        pause = [(0, 4, 418, 418)] * 5
        stoppage = [(1, 14, 419, 419), (1, 6, 420, 420), (1, KICKOFF_PENDING, 421, 421)]
        # First-half added time: the clock stands at 2700, the period restarts.
        added_time = [(1, OPEN_PLAY, 2700, 2699), (1, OPEN_PLAY, 2700, 12), (1, OPEN_PLAY, 2700, 70)]
        self.assertTrue(self.feed(tracker, pause + stoppage + added_time))

    def test_stays_live_across_half_time_into_the_second_half(self) -> None:
        tracker = self.kicked_off()
        half_time = [(1, NO_LIVE_PLAY, 2700, 141)] * 4
        second_half = [(1, KICKOFF_PENDING, 2700, 0), (1, OPEN_PLAY, 2701, 1), (1, OPEN_PLAY, 2745, 45)]
        self.assertTrue(self.feed(tracker, half_time + second_half))

    def test_abandon_forgets_the_match_before_the_arena(self) -> None:
        # 16:44:40-16:46:09: pause menu, back to the main menu (clock zeroed),
        # then the arena -- whose clock later climbs past where the match was.
        tracker = self.kicked_off()
        self.feed(tracker, [(1, OPEN_PLAY, 418, 418), (0, 4, 418, 418)])
        self.assertFalse(tracker.update(0, NO_LIVE_PLAY, 0, 0))
        arena = [(1, OPEN_PLAY, clock, clock) for clock in range(0, 900, 3)]
        self.assertFalse(self.feed(tracker, arena))

    def test_each_sign_of_the_match_leaving_memory_forgets_it(self) -> None:
        for name, reading in (
            ("clock went backwards", (1, OPEN_PLAY, 0, 0)),
            ("loading", (1, LOADING, 500, 500)),
            ("no live play with the started flag down", (0, NO_LIVE_PLAY, 500, 500)),
        ):
            with self.subTest(name):
                tracker = self.kicked_off()
                tracker.update(1, OPEN_PLAY, 500, 500)
                self.assertFalse(tracker.update(*reading))

    def test_abandoning_during_the_walkout_does_not_leave_a_kick_off_pending(self) -> None:
        tracker = LiveMatchTracker()
        self.feed(tracker, [(0, KICKOFF_PENDING, 0, 0), (1, KICKOFF_PENDING, 0, 0)])
        self.feed(tracker, [(0, NO_LIVE_PLAY, 0, 0)])
        arena = [(1, OPEN_PLAY, clock, clock) for clock in range(0, 60)]
        self.assertFalse(self.feed(tracker, arena))

    def test_a_restart_goes_live_again_at_its_own_kick_off(self) -> None:
        tracker = self.kicked_off()
        self.assertFalse(tracker.update(0, KICKOFF_PENDING, 0, 0))
        self.assertTrue(self.feed(tracker, [(1, KICKOFF_PENDING, 0, 0), (1, OPEN_PLAY, 1, 1), (1, OPEN_PLAY, 3, 3)]))

    def test_a_tick_with_the_started_flag_down_discards_the_open_play_baseline(self) -> None:
        # Pause menu: started drops to 0 while the period clock stays put. A
        # baseline taken before it must not survive, or the first tick back
        # would read the whole pause as "gained" and confirm without any
        # sustained open play (found by review, 2026-10-05).
        tracker = LiveMatchTracker()
        self.feed(tracker, [(1, KICKOFF_PENDING, 0, 0), (1, OPEN_PLAY, 5, 5)])
        self.assertFalse(tracker.update(0, OPEN_PLAY, 5, 5))
        self.assertFalse(tracker.update(1, OPEN_PLAY, 9, 9))
        self.assertTrue(tracker.update(1, OPEN_PLAY, 11, 11))

    def test_unreadable_values_change_nothing(self) -> None:
        tracker = self.kicked_off()
        self.assertTrue(self.feed(tracker, [(None, None, None, None)] * 3))
        self.assertTrue(tracker.update(1, OPEN_PLAY, 10, 10))


class LiveMatch:
    """What FIFA's memory reads back, driven by the real clock so the loop's
    own ~0.2s ticks see an integer clock exactly as they do live.

    With `kickoff_after`, the first that-many seconds read "kick-off pending"
    over a clock at 0, as the pre-match scene does; without it the play state
    is there from the start, as in the practice arena."""

    def __init__(
        self, *, rate: float, play_state: int, start_clock: int = 1, kickoff_after: float | None = None
    ) -> None:
        self.rate = rate
        self.play_state = play_state
        self.start_clock = start_clock
        self.kickoff_after = kickoff_after
        self.started_at = time.time()

    def _since_kickoff(self) -> float:
        return time.time() - self.started_at - (self.kickoff_after or 0.0)

    def state(self) -> int:
        return KICKOFF_PENDING if self._since_kickoff() < 0 else self.play_state

    def clock(self) -> int:
        elapsed = self._since_kickoff()
        return 0 if elapsed < 0 else self.start_clock + int(self.rate * elapsed)


class FakeMemory:
    match: LiveMatch

    def attack(self, _process: str) -> bool:
        return True

    def is_open(self) -> bool:
        return True

    def get_int(self, base, offsets) -> int:
        if base == "started":
            return 1
        if offsets in ("clock", "period"):
            return self.match.clock()
        if offsets == "state":
            return self.match.state()
        return 0

    def close(self) -> None:
        pass


class FakeIni:
    def key_exists(self, _section: str, _key: str) -> bool:
        return False


class FakeApp:
    def __init__(self) -> None:
        self.MP = "fifa16"
        self.HID = "1"
        self.AID = "2"
        self.settings_ini = FakeIni()
        self.offsets = SimpleNamespace(
            GAMESTARTEDBINARYBASE="started",
            GAMESTARTEDBINARY="flag",
            GAMESTATSBASE="stats",
            GAMERANTIME="clock",
            GAMEPERIODSECONDS="period",
            GAMEPLAYSTATE="state",
            GAMEHOMEGOALSCORE="home",
            GAMEAWAYGOALSCORE="away",
        )
        self.lastpagename = ""
        self.matchstarted = False
        self.chants_thread_started = True
        self._chants_stop = threading.Event()
        self._chants_reset_requested = False
        self._chants_player = None
        self._chants_paused = False
        self._chants_target_volume = 0.0
        self._last_chants_score_snapshot = None
        self._entrance_armed = False
        self._entrance_active = False
        self._entrance_pre_match_guard = True
        self.logs: list[str] = []

    def module_enabled(self, _name: str) -> bool:
        return True

    def _is_game_running_with(self, memory: FakeMemory) -> bool:
        return memory.get_int("started", "flag") == 1 and memory.get_int("stats", "clock") >= 1

    def _set_display_async(self, _key: str, _value: str) -> None:
        pass

    def log(self, message: str, *_args, **_kwargs) -> None:
        self.logs.append(message)


class PreMatchGuardLoopTests(unittest.TestCase):
    """chants_runtime_loop's pre-match guard against a clock that runs in real
    time -- time.sleep is NOT mocked, so the tick-rate arithmetic that hid this
    bug stays in the picture."""

    def run_loop(self, match: LiveMatch, seconds: float) -> FakeApp:
        app = FakeApp()
        FakeMemory.match = match
        with patch("server16_py.chants_runtime.Memory", FakeMemory):
            thread = threading.Thread(target=ChantsRuntime(app).chants_runtime_loop, daemon=True)
            thread.start()
            deadline = time.time() + seconds
            while time.time() < deadline and app._entrance_pre_match_guard:
                time.sleep(0.05)
            app._chants_stop.set()
            thread.join(3.0)
        self.assertFalse(thread.is_alive())
        return app

    def test_releases_at_kick_off_on_a_ten_and_a_twenty_minute_half(self) -> None:
        # 4.5 and 2.25 clock units per second: the cases the reports were about.
        for rate in (4.5, 2.25):
            with self.subTest(rate=rate):
                match = LiveMatch(rate=rate, play_state=OPEN_PLAY, kickoff_after=0.6)
                app = self.run_loop(match, seconds=4.0)
                self.assertFalse(app._entrance_pre_match_guard)
                self.assertTrue(any("guard released: ball in play" in line for line in app.logs))
                # The old check must not have been what released it.
                self.assertFalse(any("released at clock speed" in line for line in app.logs))

    def test_holds_through_the_bumper_where_the_clock_creeps(self) -> None:
        app = self.run_loop(LiveMatch(rate=1.0, play_state=NO_LIVE_PLAY), seconds=2.0)
        self.assertTrue(app._entrance_pre_match_guard)

    def test_holds_over_stale_open_play_with_a_frozen_clock(self) -> None:
        app = self.run_loop(LiveMatch(rate=0.0, play_state=OPEN_PLAY, start_clock=676), seconds=2.0)
        self.assertTrue(app._entrance_pre_match_guard)

    def test_the_practice_arena_is_not_released_as_ball_in_play(self) -> None:
        # Reported live 2026-10-05 on the first build with the play-state
        # path: "ball in play" over a ~7/s clock, but no kick-off before it.
        # (The old speed check may or may not fire at 7/s -- not asserted.)
        app = self.run_loop(LiveMatch(rate=7.0, play_state=OPEN_PLAY), seconds=3.0)
        self.assertFalse(any("ball in play" in line for line in app.logs))
        self.assertFalse(any("kick-off confirmed" in line for line in app.logs))

    def test_a_pause_re_arm_releases_again_but_the_arena_after_abandon_does_not(self) -> None:
        def released_count() -> int:
            return sum("guard released: ball in play" in line for line in app.logs)

        def wait_for_release(seconds: float) -> None:
            deadline = time.time() + seconds
            while time.time() < deadline and app._entrance_pre_match_guard:
                time.sleep(0.05)

        app = FakeApp()
        FakeMemory.match = LiveMatch(rate=4.5, play_state=OPEN_PLAY, kickoff_after=0.6)
        with patch("server16_py.chants_runtime.Memory", FakeMemory):
            thread = threading.Thread(target=ChantsRuntime(app).chants_runtime_loop, daemon=True)
            thread.start()
            try:
                wait_for_release(4.0)
                self.assertEqual(released_count(), 1)
                # A pause through a blank page: app_game arms the guard again
                # for the very same match.
                app._entrance_pre_match_guard = True
                wait_for_release(4.0)
                self.assertEqual(released_count(), 2)
                # Abandon: the main menu zeroes the clock, then the arena.
                FakeMemory.match = LiveMatch(rate=0.0, play_state=NO_LIVE_PLAY, start_clock=0)
                time.sleep(1.5)
                FakeMemory.match = LiveMatch(rate=7.0, play_state=OPEN_PLAY)
                app._entrance_pre_match_guard = True
                time.sleep(2.5)
                self.assertEqual(released_count(), 2)
                self.assertTrue(any("no longer in memory" in line for line in app.logs))
            finally:
                app._chants_stop.set()
                thread.join(3.0)
        self.assertFalse(thread.is_alive())

    def test_the_fast_clock_path_still_works_without_a_readable_play_state(self) -> None:
        # A build where GAMEPLAYSTATE reads something else entirely must behave
        # exactly as before: 11.25 units/s passes the speed check on its own.
        app = self.run_loop(LiveMatch(rate=11.25, play_state=0), seconds=4.0)
        self.assertFalse(app._entrance_pre_match_guard)
        self.assertTrue(any("released at clock speed" in line for line in app.logs))


if __name__ == "__main__":
    unittest.main()
