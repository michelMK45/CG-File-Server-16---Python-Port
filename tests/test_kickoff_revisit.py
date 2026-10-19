from __future__ import annotations

import sys
import types
import unittest

# app_game only needs the tkinter name inside unrelated UI methods -- same
# minimal stub pattern as tests/test_team_entrance_trigger.py.
tkinter_stub = types.ModuleType("tkinter")
tkinter_stub.Label = lambda: None
sys.modules.setdefault("tkinter", tkinter_stub)

from server16_py.app_game import GameMixin

KICKOFF = "game/screens/playNow/KickOffHub"
TEAM_MANAGEMENT = "game/screens/teamsheets/TeamSheets"
SETTINGS = "game/screens/settings/GameSettings"


class FakeOffsets:
    ORIHTIDBASE = 100
    ORIFRIHTIDBASE = 200
    ORISTADIDBASE = 300
    ORITOURIDBASE = 400
    HT = [1, 2, 3, 4, 5, 6]
    HT2 = [7, 8, 9, 10, 11, 12]
    S = [1, 2, 3, 4, 5, 6]
    T = [1, 2, 3, 4, 5, 6]
    TLEAGUE = [1, 2, 3, 4, 7]


class FakeGame(GameMixin):
    """The real page-transition state machine and refresh_live_context, with
    the memory reads scripted through `self.reads` (trace name -> value)."""

    def __init__(self) -> None:
        self.lastpagename = "menu"
        self.pagechange = False
        self.skillgamechange = False
        self.bumperpagechange = False
        self.matchstarted = False
        self._entrance_sequence = 0
        self._entrance_armed = False
        self._entrance_pre_match_guard = False
        self._stadium_picker_pending = False
        self._stadium_picker_resolved = False
        self._stadium_task_running = False
        self._left_match_reset_done = False
        self._kickoff_generation = 0
        self._kickoff_retry_remaining = 0
        self._last_stadium_applied_signature = None
        self._last_runtime_signature = None
        self._match_prep_context = None
        self._match_prep_ignored_context = None
        self._kickoff_revisit = False
        self._closing = False
        self.offsets = FakeOffsets()
        self.settings = types.SimpleNamespace(auto_apply_substitution_count=False)
        self.curstad = ""
        self.HID = self.AID = self.STADID = self.TOURNAME = self.TOURROUNDID = self.LEAGUEID = ""
        self.Stadiumtype = "first"
        self.derby = ""
        self.reads = {"HT-HID": "10", "HT-AID": "20", "S-FIRST": "176", "T-TOUR": "1", "T-ROUND": "504"}
        self.applies: list[tuple[str, str, str, str]] = []
        self.clears = 0
        self.chants_resets = 0
        self.sub_resets = 0
        self.logs: list[str] = []

        class _Subs:
            def reset_for_new_match(inner) -> None:
                self.sub_resets += 1

        self.substitution_runtime = _Subs()

    # --- collaborators of the real methods -------------------------------
    def log(self, *parts, **_kwargs) -> None:
        self.logs.append(" ".join(str(p) for p in parts))

    def stadium_picker_awaiting_selection(self) -> bool:
        return bool(self._stadium_picker_pending and not self._stadium_picker_resolved)

    def _should_auto_apply_runtime(self, page_name: str) -> bool:
        # Mirrors app_settings.py.
        return page_name == KICKOFF

    def apply_all_runtime(self) -> None:
        self.applies.append((self.HID, self.AID, self.TOURNAME, self.TOURROUNDID))

    def _clear_live_context(self) -> None:
        self.clears += 1
        self.HID = self.AID = self.STADID = self.TOURNAME = self.TOURROUNDID = ""
        self._last_runtime_signature = None

    def _reset_chants_state(self) -> None:
        self.chants_resets += 1
        self.matchstarted = False

    def _schedule_kickoff_retry(self) -> None:
        pass

    def _start_team_entrance(self) -> bool:
        return True

    def _start_chants_runtime(self) -> None:
        pass

    def _start_scoreboard_name_fast_watch(self) -> None:
        pass

    def tv_bumper_page(self) -> None:
        pass

    def _read_legacy_team_context(self):
        return None, None

    def _try_read_context_int(self, trace_name, _static_ptr, _offsets, _page_name):
        return self.reads.get(trace_name)

    def _read_dashboard_pointer(self, _base_attr, _offsets_attr):
        return None

    def _set_display(self, *_args) -> None:
        pass

    def _update_team_logo(self, *_args) -> None:
        pass

    def _resolve_team_name(self, _team_id) -> str:
        return ""

    def tr(self, key, **_kwargs) -> str:
        return key

    def _update_live_match_stats(self, _page_name) -> None:
        pass

    # --- driving helper ----------------------------------------------------
    def goto(self, page: str) -> None:
        """What update_page_name does for one poll on `page`."""
        self._handle_page_transition(page)
        if self._page_can_have_match_context(page):
            self.refresh_live_context(page)


class KickOffHubRevisitTests(unittest.TestCase):
    def enter_match(self) -> FakeGame:
        game = FakeGame()
        game.goto(KICKOFF)
        self.assertEqual(game.applies, [("10", "20", "1", "504")])
        self.assertEqual(game._kickoff_generation, 1)
        return game

    def test_return_from_team_management_keeps_the_runtime(self) -> None:
        game = self.enter_match()
        game.goto(TEAM_MANAGEMENT)
        game.goto(KICKOFF)
        game.goto(KICKOFF)  # later polls on the same page

        self.assertEqual(len(game.applies), 1)
        self.assertEqual(game._kickoff_generation, 1)
        self.assertEqual((game.clears, game.chants_resets), (1, 1))
        self.assertEqual((game.HID, game.AID, game.TOURNAME, game.TOURROUNDID), ("10", "20", "1", "504"))
        self.assertTrue(any("KickOffHub revisit" in line for line in game.logs))

    def test_return_from_side_select_keeps_the_runtime(self) -> None:
        # SideSelect is also reachable from KickOffHub before playing: same match.
        game = self.enter_match()
        game.goto("game/screens/playNow/SideSelect")
        game.goto(KICKOFF)
        self.assertTrue(game._kickoff_revisit)
        self.assertEqual(len(game.applies), 1)
        self.assertEqual(game._kickoff_generation, 1)

    def test_select_team_is_always_a_new_match_even_with_the_same_teams(self) -> None:
        game = self.enter_match()
        game.goto("game/screens/playNow/SideSelect")
        game.goto("game/screens/playNow/SelectTeam")
        game.goto("game/screens/playNow/SideSelect")
        game.goto(KICKOFF)
        self.assertFalse(game._kickoff_revisit)
        self.assertEqual(game._kickoff_generation, 2)
        self.assertEqual(game.applies, [("10", "20", "1", "504")] * 2)

    def test_return_from_settings_keeps_the_runtime_several_times(self) -> None:
        game = self.enter_match()
        for page in (SETTINGS, KICKOFF, TEAM_MANAGEMENT, KICKOFF, SETTINGS, KICKOFF):
            game.goto(page)
        self.assertEqual(len(game.applies), 1)
        self.assertEqual(game._kickoff_generation, 1)

    def test_a_running_stadium_load_is_not_restarted(self) -> None:
        # The reported case: the player leaves KickOffHub while the stadium
        # is still being copied and comes back before it finishes.
        game = self.enter_match()
        game._stadium_task_running = True
        game.goto(TEAM_MANAGEMENT)
        game.goto(KICKOFF)
        self.assertEqual(len(game.applies), 1)
        self.assertTrue(any("load still running" in line for line in game.logs))

    def test_transient_context_reads_are_ignored_until_the_match_loads(self) -> None:
        game = self.enter_match()
        game.reads["T-ROUND"] = "77"
        game.goto(TEAM_MANAGEMENT)
        self.assertEqual(game.TOURROUNDID, "504")
        game.goto(KICKOFF)
        game.goto(KICKOFF)
        self.assertEqual(game.TOURROUNDID, "504")
        self.assertEqual(len(game.applies), 1)
        # Logged once, not on every poll.
        self.assertEqual(sum("context kept" in line for line in game.logs), 1)

    def test_the_first_visit_still_reapplies_while_the_context_resolves(self) -> None:
        game = FakeGame()
        game.reads.pop("HT-AID")
        game.goto(KICKOFF)
        game.reads["HT-AID"] = "20"
        game.refresh_live_context(KICKOFF)
        self.assertEqual(game.applies, [("10", "", "1", "504"), ("10", "20", "1", "504")])
        self.assertEqual(game._match_prep_context, ("10", "20", "1", "504"))

    def test_leaving_before_the_teams_were_known_is_not_a_revisit(self) -> None:
        game = FakeGame()
        game.reads.pop("HT-AID")
        game.goto(KICKOFF)
        game.reads["HT-AID"] = "20"
        game.goto(TEAM_MANAGEMENT)
        self.assertEqual(game.AID, "20")  # an incomplete context is never locked
        game.goto(KICKOFF)
        self.assertEqual(game._kickoff_generation, 2)
        self.assertEqual(game.applies[-1], ("10", "20", "1", "504"))

    def test_pages_that_end_the_match_preparation(self) -> None:
        for page in (
            "",
            "game/screens/TV/bumper",
            "game/screens/matchIntro/",
            "game/screens/fluxHub/FluxHub",
            "game/screens/playNow/SelectTeam",
            "game/screens/tournamentMode/SelectTeams",
            "game/screens/career/Scheduling",
            "game/screens/training/SkillGamesHub",
            "game/screens/skillGames/SkillGameResults",
        ):
            with self.subTest(page=page):
                game = self.enter_match()
                game.goto(page)
                generation = game._kickoff_generation
                game.goto(KICKOFF)
                self.assertFalse(game._kickoff_revisit)
                self.assertEqual(game._kickoff_generation, generation + 1)
                self.assertEqual(len(game.applies), 2)

    def test_next_match_after_playing_gets_a_fresh_preparation(self) -> None:
        game = self.enter_match()
        for page in ("", "game/screens/TV/bumper", "", "game/screens/fluxHub/FluxHub"):
            game.goto(page)
        game.goto(KICKOFF)  # rematch, same teams
        self.assertEqual(game._kickoff_generation, 2)
        self.assertEqual(len(game.applies), 2)
        self.assertFalse(game._kickoff_revisit)

    def test_another_team_picked_after_backing_out_is_applied(self) -> None:
        game = self.enter_match()
        game.goto("game/screens/playNow/SideSelect")
        game.goto("game/screens/playNow/SelectTeam")
        game.reads["HT-AID"] = "30"
        game.goto("game/screens/playNow/SideSelect")
        game.goto(KICKOFF)
        self.assertEqual(game.applies[-1], ("10", "30", "1", "504"))

    def test_fifa_closing_ends_the_preparation(self) -> None:
        game = self.enter_match()
        game.goto(SETTINGS)
        game._end_match_preparation("<process ended>")
        game.goto(KICKOFF)
        self.assertEqual(game._kickoff_generation, 2)
        self.assertEqual(len(game.applies), 2)


if __name__ == "__main__":
    unittest.main()
