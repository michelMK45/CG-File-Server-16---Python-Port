from __future__ import annotations

import unittest
import sys
import types


# The portable Python 3.9 used for archive-compatible tests has no Linux Tcl
# runtime. app_game only needs the tkinter name inside unrelated UI methods, so
# a minimal import stub is sufficient for this state-machine unit test.
tkinter_stub = types.ModuleType("tkinter")
tkinter_stub.Label = lambda: None
sys.modules.setdefault("tkinter", tkinter_stub)

from server16_py.app_game import GameMixin


class FakeGame(GameMixin):
    def __init__(self) -> None:
        self.lastpagename = "menu"
        self.pagechange = False
        self.skillgamechange = False
        self.bumperpagechange = False
        self.matchstarted = False
        self._entrance_sequence = 0
        self._entrance_armed = False
        self._entrance_pre_match_guard = False
        self.curstad = ""
        self.entrance_starts = 0
        self.chants_starts = 0
        self.bumper_calls = 0

    def log(self, *_args, **_kwargs) -> None:
        pass

    def _start_team_entrance(self) -> bool:
        self.entrance_starts += 1
        return True

    def _start_chants_runtime(self) -> None:
        self.chants_starts += 1

    def tv_bumper_page(self) -> None:
        self.bumper_calls += 1


class TeamEntranceTriggerTests(unittest.TestCase):
    def test_entrance_arms_on_competition_bumper_not_before(self) -> None:
        game = FakeGame()

        # The blank page reached right after KickOffHub now arms Team
        # Entrance too (mirroring Chants' own second trigger — see the
        # restart test below) — but the very next transition here is the
        # TV/bumper page itself, which the "already armed" check ignores
        # (it contains the substring "TV/bumper"), so entrance still does
        # not start yet. _entrance_sequence increments an extra time here
        # (this call, then again in the bumper block) versus before that
        # fallback existed — that's a harmless side effect, it is only ever
        # used to distinguish match attempts, never compared to an absolute
        # value elsewhere.
        game._handle_page_transition("")
        self.assertEqual(game.entrance_starts, 0)
        self.assertEqual(game.chants_starts, 1)

        game._handle_page_transition("game/screens/TV/bumper")
        self.assertEqual(game.bumper_calls, 1)
        self.assertEqual(game._entrance_sequence, 2)
        self.assertEqual(game.entrance_starts, 0)
        self.assertEqual(game.chants_starts, 2)
        self.assertTrue(game._entrance_armed)
        self.assertTrue(game._entrance_pre_match_guard)

        game._handle_page_transition("")
        self.assertEqual(game._entrance_sequence, 2)
        self.assertEqual(game.entrance_starts, 1)
        # skillgamechange is now True (set while handling the bumper page
        # above), so the blank-page fallback's own guard keeps this call
        # from also calling _start_chants_runtime() a third time.
        self.assertEqual(game.chants_starts, 2)
        self.assertFalse(game._entrance_armed)

        # Re-reading the same blank page must not start the entrance twice.
        game._handle_page_transition("")
        self.assertEqual(game.entrance_starts, 1)

    def test_entrance_rearms_on_restart_that_skips_the_bumper(self) -> None:
        # Models FIFA's "Restart Match" (chosen mid-match from the pause
        # menu): reported live 2026-08-28 to skip the TV/bumper competition
        # intro entirely, going straight from a blank transitional page into
        # the new attempt's own walkout page. Before this fix, Team Entrance
        # was armed *only* by TV/bumper, so it silently never fired again for
        # a restarted match. The blank-page fallback below is Chants' own
        # second, independent trigger for exactly this class of problem.
        game = FakeGame()
        # A real restart's matchstarted=False comes from ChantsRuntime's own
        # generic running/not-running detection (chants_runtime.py), not
        # from _handle_page_transition — set directly since this test only
        # exercises _handle_page_transition in isolation.
        game.matchstarted = False
        game._handle_page_transition("")
        self.assertTrue(game._entrance_armed)
        self.assertEqual(game.entrance_starts, 0)

        # No TV/bumper this time — straight to the new attempt's walkout.
        # Deliberately NOT a "playNow/..." page: that family is reserved for
        # pre-match SETUP menus (SideSelect/SelectTeam/KickOffHub, see
        # entrance_runtime.py's own "playnow" stop-check) and is now blocked
        # by _page_blocks_team_entrance below — a genuine walkout page must
        # live outside that family the same way the real, live-confirmed
        # walkout page name is blank (see test_entrance_arms_on_competition_bumper_not_before).
        game._handle_page_transition("game/screens/matchIntro/3dPresentation")
        self.assertEqual(game.entrance_starts, 1)
        self.assertFalse(game._entrance_armed)

    def test_entrance_does_not_restart_when_abandon_bounces_through_menus(self) -> None:
        # Reproduces runtime/server16.log 2026-08-30 12:51:50-12:52:11 (and
        # the equivalent 2026-08-29 trail) verbatim: entrance starts playing
        # during the walkout, the player opens FluxHub and abandons, and the
        # page name bounces blank/FluxHub a couple of times before finally
        # landing on a playNow setup menu. FIFA's started/ran_time flags can
        # read stale/reset values during this bounce, so matchstarted reads
        # False the whole time -- which used to let the blank-page fallback
        # arm Team Entrance again, and the menu page right after it "consume"
        # that arm as if a new match had begun, restarting the anthem
        # audibly inside the menu. None of these transitions may ever start
        # the entrance worker.
        game = FakeGame()
        game.matchstarted = False

        for page_name in (
            "game/screens/fluxHub/FluxHub",
            "",
            "game/screens/fluxHub/FluxHub",
            "",
            "game/screens/playNow/SelectTeam",
        ):
            game._handle_page_transition(page_name)

        self.assertEqual(game.entrance_starts, 0)
        self.assertFalse(game._entrance_armed)

        # A second bounce pattern seen live: blank -> straight to SelectTeam
        # with no repeated FluxHub in between.
        game2 = FakeGame()
        game2.matchstarted = False
        game2._handle_page_transition("game/screens/fluxHub/FluxHub")
        game2._handle_page_transition("")
        game2._handle_page_transition("game/screens/playNow/SelectTeam")
        self.assertEqual(game2.entrance_starts, 0)
        self.assertFalse(game2._entrance_armed)

    def test_matchstarted_flips_false_immediately_on_pause_menu_page(self) -> None:
        # Leading hypothesis for "Restart doesn't stop/restart the anthem"
        # (reported live 2026-08-30, still not confirmed by a captured
        # Restart log -- see CLAUDE.md §7 Part 7): ChantsRuntime's own
        # `matchstarted` flag only flips False after 3 consecutive
        # 0.5s-spaced memory reads report the match not running -- up to
        # ~1.5s of lag behind the page transition that actually caused it.
        # A Restart chosen quickly after opening the pause menu could reach
        # the new attempt's blank/walkout page before that lag clears, so
        # the blank-page arm fallback's `not self.matchstarted` guard would
        # silently skip re-arming Team Entrance -- leaving the previous
        # attempt's worker as the only one that ever ran. Reaching a
        # pause/setup menu page must flip `matchstarted` immediately rather
        # than waiting on Chants' independently-clocked poll to catch up.
        game = FakeGame()
        game.matchstarted = True  # Chants hasn't caught up yet
        game._handle_page_transition("game/screens/fluxHub/FluxHub")
        self.assertFalse(game.matchstarted)

        # A blank page right after must now be able to arm -- before this
        # fix it would have been silently skipped since matchstarted was
        # still (stale) True.
        game._handle_page_transition("")
        self.assertTrue(game._entrance_armed)


if __name__ == "__main__":
    unittest.main()
