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

    def request_db_name_patch(self, injid: str, std_name: str) -> None:
        self.request_calls.append((injid, std_name))


class FakeGame(GameMixin):
    def __init__(self) -> None:
        self._closing = False
        self._kickoff_generation = 1
        self.injID = "176"
        self.stadium_db_name_patcher = FakeCoordinator()
        self.stadium_runtime = FakeStadiumRuntime()
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


if __name__ == "__main__":
    unittest.main()
