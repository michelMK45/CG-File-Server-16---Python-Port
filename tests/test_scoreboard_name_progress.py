from __future__ import annotations

import sys
import types
import unittest
from unittest.mock import patch

# The portable Python 3.9 used for archive-compatible tests has no Linux Tcl
# runtime. app_game only needs the tkinter name inside unrelated UI methods, so
# a minimal import stub is sufficient for this state-machine unit test (same
# pattern as tests/test_team_entrance_trigger.py).
tkinter_stub = types.ModuleType("tkinter")
tkinter_stub.Label = lambda: None
sys.modules.setdefault("tkinter", tkinter_stub)

from server16_py.app_game import GameMixin


class FakeCoordinator:
    def __init__(self) -> None:
        self.confirmed_name: str | None = None

    def get_current_name(self, injid: str) -> str | None:
        return self.confirmed_name


class FakeStadiumRuntime:
    def __init__(self) -> None:
        self.request_calls: list[tuple[str, str]] = []
        self.fast_watch_calls: list[tuple[str, str]] = []

    def request_db_name_patch(self, injid: str, std_name: str) -> None:
        self.request_calls.append((injid, std_name))

    def resolve_scoreboard_display_name(self, stad_name: str) -> str:
        return f"display:{stad_name}"

    def start_db_name_fast_watch(self, injid: str, std_name: str) -> None:
        self.fast_watch_calls.append((injid, std_name))


class FakeOffsets:
    GAMESTATSBASE = 0x1
    GAMERANTIME = [0x1]


class FakeMemory:
    """Feeds a scripted sequence of GAMERANTIME reads to
    _db_name_patch_kickoff_detected, one per call -- None means "read
    failed" (mirrors a real Memory.get_int raising, caught internally)."""

    def __init__(self, readings: list[int | None] | None = None) -> None:
        self._readings = list(readings or [])

    def get_int(self, *_args, **_kwargs) -> int:
        if not self._readings:
            raise RuntimeError("no more scripted readings")
        value = self._readings.pop(0)
        if value is None:
            raise RuntimeError("simulated read failure")
        return value


class FakeGame(GameMixin):
    def __init__(self) -> None:
        self._closing = False
        self._kickoff_generation = 1
        self.injID = "176"
        self.curstad = ""
        self.stadium_db_name_patcher = FakeCoordinator()
        self.stadium_runtime = FakeStadiumRuntime()
        self.offsets = FakeOffsets()
        self.memory = FakeMemory()
        # Tests that call _db_name_patch_retry_tick/_schedule_db_name_patch_retry
        # directly are simulating an already-running cycle, so default True;
        # _start_scoreboard_name_progress itself also sets this.
        self._scoreboard_name_progress_active = True
        self._scoreboard_name_progress_std_name: str | None = None
        self._scoreboard_name_progress_injid: str | None = None
        self.after_calls: list[tuple[int, object]] = []
        self.show_calls: list[tuple] = []
        self.update_calls: list[tuple] = []
        self.hide_calls: list[int] = []
        self.logs: list[str] = []

    def log(self, *parts) -> None:
        self.logs.append(" ".join(str(p) for p in parts))

    def after(self, delay_ms, callback):
        self.after_calls.append((delay_ms, callback))
        return len(self.after_calls)

    def _show_stadium_loading_modal(self, name, detail, progress=0.0) -> None:
        self.show_calls.append((name, detail, progress))

    def _update_stadium_loading_modal(self, progress, detail) -> None:
        self.update_calls.append((progress, detail))

    def _hide_stadium_loading_modal(self, delay_ms=0) -> None:
        self.hide_calls.append(delay_ms)


class ScoreboardNameProgressTests(unittest.TestCase):
    def test_start_shows_modal_and_schedules_first_retry(self) -> None:
        game = FakeGame()
        with patch("server16_py.app_game.time.monotonic", return_value=1000.0):
            game._start_scoreboard_name_progress("176", "Anfield")
        self.assertEqual(game.show_calls, [("Anfield", "Applying scoreboard name...", 0)])
        self.assertEqual(len(game.after_calls), 1)
        self.assertEqual(game.after_calls[0][0], 900)

    def test_tick_completes_bar_once_coordinator_confirms_the_exact_name(self) -> None:
        # get_current_name() only ever reports a name StadiumDbNamePatchCoordinator
        # itself write-verified or read-confirmed live -- so this must be
        # trusted as a genuine "done" signal, filling the bar to 100 and
        # closing it, rather than requiring one more scheduled retry.
        game = FakeGame()
        game.stadium_db_name_patcher.confirmed_name = "Anfield"
        game._db_name_patch_retry_tick(
            "176", "Anfield", baseline_name=None, generation=1, started_at=1000.0, deadline=1060.0
        )
        self.assertEqual(game.update_calls[-1], (100, "Scoreboard name applied: Anfield"))
        self.assertEqual(game.hide_calls, [1200])
        self.assertEqual(game.stadium_runtime.request_calls, [])
        self.assertEqual(game.after_calls, [])

    def test_tick_completes_bar_on_a_confirmed_truncated_name_too(self) -> None:
        # Real bug found live 2026-09-10: FIFA's own buffer for a slot can be
        # too small for the full requested text (a real, expected capacity
        # limit -- CLAUDE.md §7 Part 10, "Campos de Sport de El Sardinero"
        # truncated to "Campos de S" for slot 176's 12-byte name buffer).
        # StadiumDbNamePatchCoordinator still confirms the truncated value,
        # but it can never exactly equal `std_name` -- requiring an exact
        # match used to make this look like it never succeeded at all,
        # burning the whole retry window before falsely reporting failure.
        game = FakeGame()
        game.stadium_db_name_patcher.confirmed_name = "Campos de S"
        game._db_name_patch_retry_tick(
            "176",
            "Campos de Sport de El Sardinero",
            baseline_name="Waldstadion",
            generation=1,
            started_at=1000.0,
            deadline=1060.0,
        )
        self.assertEqual(game.update_calls[-1], (100, "Scoreboard name applied (shortened): Campos de S"))
        self.assertEqual(game.hide_calls, [1200])
        self.assertEqual(game.stadium_runtime.request_calls, [])

    def test_tick_does_not_finish_while_still_only_showing_the_baseline(self) -> None:
        # Nothing has changed yet -- get_current_name() still reports
        # whatever was there before this cycle even started, so this must
        # keep retrying, not be mistaken for "confirmed".
        game = FakeGame()
        game.stadium_db_name_patcher.confirmed_name = "Waldstadion"
        with patch("server16_py.app_game.time.monotonic", return_value=1010.0):
            game._db_name_patch_retry_tick(
                "176",
                "Campos de Sport de El Sardinero",
                baseline_name="Waldstadion",
                generation=1,
                started_at=1000.0,
                deadline=1060.0,
            )
        self.assertEqual(game.stadium_runtime.request_calls, [("176", "Campos de Sport de El Sardinero")])
        self.assertEqual(game.hide_calls, [])

    def test_tick_updates_progress_and_reschedules_while_unconfirmed(self) -> None:
        game = FakeGame()
        with patch("server16_py.app_game.time.monotonic", return_value=1030.0):
            game._db_name_patch_retry_tick(
                "176", "Anfield", baseline_name=None, generation=1, started_at=1000.0, deadline=1060.0
            )
        self.assertEqual(game.stadium_runtime.request_calls, [("176", "Anfield")])
        progress, detail = game.update_calls[-1]
        self.assertAlmostEqual(progress, 50.0, delta=0.01)
        self.assertEqual(detail, "Applying scoreboard name...")
        self.assertEqual(len(game.after_calls), 1)
        self.assertEqual(game.hide_calls, [])

    def test_progress_never_reports_100_without_a_confirmed_success(self) -> None:
        # A bar that reaches 100% on its own while still just guessing would
        # misreport an unresolved patch as done -- only an actual confirmed
        # success (or the deadline giving up) may show a full bar.
        game = FakeGame()
        with patch("server16_py.app_game.time.monotonic", return_value=1059.9):
            game._db_name_patch_retry_tick(
                "176", "Anfield", baseline_name=None, generation=1, started_at=1000.0, deadline=1060.0
            )
        progress, _detail = game.update_calls[-1]
        self.assertLessEqual(progress, 95.0)

    def test_deadline_reached_finishes_as_unconfirmed(self) -> None:
        game = FakeGame()
        with patch("server16_py.app_game.time.monotonic", return_value=2000.0):
            game._schedule_db_name_patch_retry(
                "176", "Anfield", baseline_name=None, generation=1, started_at=1000.0, deadline=1060.0
            )
        self.assertEqual(game.update_calls[-1], (100, "Scoreboard name not confirmed"))
        self.assertEqual(game.hide_calls, [1200])
        self.assertEqual(game.after_calls, [])

    def test_injid_mismatch_stops_and_finishes_as_unconfirmed(self) -> None:
        game = FakeGame()
        game.injID = "261"  # a different stadium has since taken over this slot
        game._db_name_patch_retry_tick(
            "176", "Anfield", baseline_name=None, generation=1, started_at=1000.0, deadline=1060.0
        )
        self.assertEqual(game.update_calls[-1], (100, "Scoreboard name not confirmed"))
        self.assertEqual(game.hide_calls, [1200])
        self.assertEqual(game.stadium_runtime.request_calls, [])

    def test_stale_generation_never_touches_the_shared_modal(self) -> None:
        # A newer match already started (a real KickOffHub visit) -- this
        # chain's own bar may already have been overwritten by that new
        # match's own fresh _start_scoreboard_name_progress call. A stale
        # chain must not touch the shared widget at all (no update, no
        # hide) -- doing so could hide/corrupt the newer match's own bar.
        game = FakeGame()
        game._kickoff_generation = 2  # newer match already started

        game._schedule_db_name_patch_retry(
            "176", "Anfield", baseline_name=None, generation=1, started_at=1000.0, deadline=1060.0
        )
        self.assertEqual(game.update_calls, [])
        self.assertEqual(game.hide_calls, [])
        self.assertEqual(game.after_calls, [])

        game._db_name_patch_retry_tick(
            "176", "Anfield", baseline_name=None, generation=1, started_at=1000.0, deadline=1060.0
        )
        self.assertEqual(game.update_calls, [])
        self.assertEqual(game.hide_calls, [])
        self.assertEqual(game.stadium_runtime.request_calls, [])


class KickoffStopsLoadingBarTests(unittest.TestCase):
    """Reported live 2026-09-14: the "Applying scoreboard name..." bar could
    stay on screen for the full 60s retry window regardless of match state,
    including well after real kick-off. These cover the new
    _db_name_patch_kickoff_detected heuristic (same sustained-clock-speed
    signal already proven live for ChantsRuntime/TeamEntranceRuntime) and its
    wiring into the retry tick.
    """

    def test_stays_false_during_the_protection_window(self) -> None:
        game = FakeGame()
        game.memory = FakeMemory([100])
        with patch("server16_py.app_game.time.monotonic", return_value=1002.0):
            detected = game._db_name_patch_kickoff_detected({}, started_at=1000.0)
        self.assertFalse(detected)

    def test_stays_false_when_the_clock_read_fails(self) -> None:
        game = FakeGame()
        game.memory = FakeMemory([None])
        with patch("server16_py.app_game.time.monotonic", return_value=1010.0):
            detected = game._db_name_patch_kickoff_detected({}, started_at=1000.0)
        self.assertFalse(detected)

    def test_requires_three_consecutive_fast_ticks_after_the_protection_window(self) -> None:
        game = FakeGame()
        game.memory = FakeMemory([100, 108, 116, 124])
        speed_state: dict = {}
        times = [1006.0, 1006.9, 1007.8, 1008.7]
        results = []
        for t in times:
            with patch("server16_py.app_game.time.monotonic", return_value=t):
                results.append(game._db_name_patch_kickoff_detected(speed_state, started_at=1000.0))
        self.assertEqual(results, [False, False, False, True])

    def test_a_slow_reading_resets_the_streak(self) -> None:
        # Two fast hits, then one slow (celebration-speed) reading, then two
        # more fast hits must NOT trip early -- only a fresh run of three
        # consecutive fast hits after the reset may.
        game = FakeGame()
        game.memory = FakeMemory([100, 108, 116, 117, 125, 133, 141])
        speed_state: dict = {}
        times = [1006.0, 1006.9, 1007.8, 1008.7, 1009.6, 1010.5, 1011.4]
        results = []
        for t in times:
            with patch("server16_py.app_game.time.monotonic", return_value=t):
                results.append(game._db_name_patch_kickoff_detected(speed_state, started_at=1000.0))
        self.assertEqual(results, [False, False, False, False, False, False, True])

    def test_tick_stops_and_hides_when_kickoff_detected_before_confirmation(self) -> None:
        game = FakeGame()
        game.memory = FakeMemory([124])  # completes a 3rd consecutive fast hit
        speed_state = {"last_game_time": 116, "last_real_time": 1007.8, "hits": 2}
        with patch("server16_py.app_game.time.monotonic", return_value=1008.7):
            game._db_name_patch_retry_tick(
                "176", "Anfield", baseline_name=None, generation=1,
                started_at=1000.0, deadline=1060.0, speed_state=speed_state,
            )
        self.assertEqual(game.update_calls[-1], (100, "Scoreboard name not confirmed"))
        self.assertEqual(game.hide_calls, [1200])
        # The coordinator itself is never re-requested once kick-off has
        # already been confirmed -- the pre-match screen this patch targets
        # is gone, so there is nothing left worth polling for.
        self.assertEqual(game.stadium_runtime.request_calls, [])
        self.assertTrue(any("kick-off detected" in log for log in game.logs))

    def test_a_confirmed_success_still_wins_over_kickoff_detection_on_the_same_tick(self) -> None:
        game = FakeGame()
        game.stadium_db_name_patcher.confirmed_name = "Anfield"
        game.memory = FakeMemory([124])
        speed_state = {"last_game_time": 116, "last_real_time": 1007.8, "hits": 2}
        with patch("server16_py.app_game.time.monotonic", return_value=1008.7):
            game._db_name_patch_retry_tick(
                "176", "Anfield", baseline_name=None, generation=1,
                started_at=1000.0, deadline=1060.0, speed_state=speed_state,
            )
        self.assertEqual(game.update_calls[-1], (100, "Scoreboard name applied: Anfield"))
        self.assertFalse(any("kick-off detected" in log for log in game.logs))


class HideForStadiumSceneTests(unittest.TestCase):
    """Requested live 2026-09-14: hide the scoreboardstdname loading bar the
    instant Team Entrance's own trigger fires (app.py's _start_team_entrance)
    -- reaching that trigger means the walkout/stadium scene has already
    begun, so there is nothing left worth showing the notification for.
    """

    def test_hides_immediately_using_the_coordinators_confirmed_name(self) -> None:
        game = FakeGame()
        game._scoreboard_name_progress_active = True
        game._scoreboard_name_progress_std_name = "Anfield"
        game._scoreboard_name_progress_injid = "176"
        game.stadium_db_name_patcher.confirmed_name = "Anfield"
        game._hide_scoreboard_name_progress_for_stadium_scene()
        self.assertEqual(game.update_calls[-1], (100, "Scoreboard name applied: Anfield"))
        self.assertEqual(game.hide_calls, [1200])
        self.assertFalse(game._scoreboard_name_progress_active)

    def test_hides_as_not_confirmed_when_nothing_landed_yet(self) -> None:
        game = FakeGame()
        game._scoreboard_name_progress_active = True
        game._scoreboard_name_progress_std_name = "Anfield"
        game._scoreboard_name_progress_injid = "176"
        game.stadium_db_name_patcher.confirmed_name = None
        game._hide_scoreboard_name_progress_for_stadium_scene()
        self.assertEqual(game.update_calls[-1], (100, "Scoreboard name not confirmed"))
        self.assertEqual(game.hide_calls, [1200])

    def test_is_a_no_op_when_no_progress_cycle_is_active(self) -> None:
        # No custom scoreboardstdname assignment this match (no cycle was
        # ever started) -- must not touch the shared widget at all.
        game = FakeGame()
        game._scoreboard_name_progress_active = False
        game._hide_scoreboard_name_progress_for_stadium_scene()
        self.assertEqual(game.update_calls, [])
        self.assertEqual(game.hide_calls, [])

    def test_a_scheduled_tick_arriving_after_the_entrance_hide_is_a_no_op(self) -> None:
        # The chain's own self.after(900, ...) can still be queued when the
        # entrance trigger hides the bar out-of-band -- the next tick to
        # fire must see the cycle already inactive and do nothing further
        # (no re-request, no re-show, no duplicate finish).
        game = FakeGame()
        game._scoreboard_name_progress_active = True
        game._scoreboard_name_progress_std_name = "Anfield"
        game._scoreboard_name_progress_injid = "176"
        game._hide_scoreboard_name_progress_for_stadium_scene()
        game.update_calls.clear()
        game.hide_calls.clear()

        with patch("server16_py.app_game.time.monotonic", return_value=1010.0):
            game._db_name_patch_retry_tick(
                "176", "Anfield", baseline_name=None, generation=1, started_at=1000.0, deadline=1060.0
            )
        self.assertEqual(game.update_calls, [])
        self.assertEqual(game.hide_calls, [])
        self.assertEqual(game.stadium_runtime.request_calls, [])


class FastWatchTriggerTests(unittest.TestCase):
    """Found live 2026-09-21: the second match of a session displayed
    "Sanderson Park" because the slow scan attempts caught FIFA's freshly
    allocated name buffer only some of the time (the winning patch landed 1s
    before "TV/bumper" in one match, right after it in the next). The fast
    watch is started when match loading begins and again at the bumper."""

    def test_starts_the_fast_watch_for_the_applied_stadium(self) -> None:
        game = FakeGame()
        game.curstad = "Anfield"
        game._start_scoreboard_name_fast_watch()
        self.assertEqual(game.stadium_runtime.fast_watch_calls, [("176", "display:Anfield")])

    def test_noop_without_an_applied_stadium(self) -> None:
        game = FakeGame()
        game.curstad = ""
        game._start_scoreboard_name_fast_watch()
        self.assertEqual(game.stadium_runtime.fast_watch_calls, [])

    def test_noop_while_closing(self) -> None:
        game = FakeGame()
        game.curstad = "Anfield"
        game._closing = True
        game._start_scoreboard_name_fast_watch()
        self.assertEqual(game.stadium_runtime.fast_watch_calls, [])

    def test_a_failure_starting_the_watch_is_logged_not_raised(self) -> None:
        game = FakeGame()
        game.curstad = "Anfield"

        def boom(injid, std_name):
            raise RuntimeError("no team_db")

        game.stadium_runtime.start_db_name_fast_watch = boom
        game._start_scoreboard_name_fast_watch()
        self.assertTrue(any("fast watch start error" in line for line in game.logs))


if __name__ == "__main__":
    unittest.main()
