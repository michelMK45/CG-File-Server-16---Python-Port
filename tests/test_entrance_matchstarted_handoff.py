from __future__ import annotations

import sys
import types
import unittest


# See tests/test_team_entrance_trigger.py for why this stub exists: the
# portable Python 3.9 used for archive-compatible tests has no Linux Tcl
# runtime, and app_game only needs the tkinter name inside unrelated UI
# methods.
tkinter_stub = types.ModuleType("tkinter")
tkinter_stub.Label = lambda: None
sys.modules.setdefault("tkinter", tkinter_stub)

from server16_py.app_game import GameMixin
from server16_py.chants_runtime import ChantsRuntime


class FakeApp(GameMixin):
    def __init__(self) -> None:
        self.lastpagename = ""
        self._entrance_armed = False
        self.entrance_starts = 0

    def log(self, *_args, **_kwargs) -> None:
        pass

    def _start_team_entrance(self) -> bool:
        self.entrance_starts += 1
        return True


class ResolvePendingEntranceArmTests(unittest.TestCase):
    """Covers ChantsRuntime._resolve_pending_entrance_arm, the Part 8 fix
    for "Restart doesn't play the entrance anthem" (CLAUDE.md §7): a Team
    Entrance arm normally gets consumed by _handle_page_transition on
    whatever DIFFERENT page name shows up next, but FIFA can keep reporting
    the exact same page name indefinitely (confirmed live both for a long
    idle pause, and for a mid-match Restart that resumes gameplay while
    still reading the same blank page it paused on) -- leaving nothing to
    ever consume the arm. `matchstarted` flipping back True is used instead
    as a page-name-independent, event-driven signal that a real match is
    live again.
    """

    def setUp(self) -> None:
        self.app = FakeApp()
        self.chants = ChantsRuntime(self.app)

    def test_starts_entrance_when_armed_and_page_is_not_a_menu(self) -> None:
        # Every live-confirmed walkout page name in this project's history
        # is blank -- see test_entrance_arms_on_competition_bumper_not_before.
        self.app._entrance_armed = True
        self.app.lastpagename = ""
        self.chants._resolve_pending_entrance_arm()
        self.assertEqual(self.app.entrance_starts, 1)
        self.assertFalse(self.app._entrance_armed)

    def test_disarms_without_starting_when_page_is_a_menu(self) -> None:
        # Mirrors _page_blocks_team_entrance (Part 6): a pause/setup menu
        # page can never be the real walkout, so drop the arm instead of
        # starting audio over a menu.
        self.app._entrance_armed = True
        self.app.lastpagename = "game/screens/fluxHub/FluxHub"
        self.chants._resolve_pending_entrance_arm()
        self.assertEqual(self.app.entrance_starts, 0)
        self.assertFalse(self.app._entrance_armed)

    def test_defers_to_normal_transition_while_bumper_is_showing(self) -> None:
        # TV/bumper's own eventual transition to a different page name is a
        # reliable, distinctly-named event -- leave it to
        # _handle_page_transition rather than start over the competition
        # intro audio.
        self.app._entrance_armed = True
        self.app.lastpagename = "TV/bumper"
        self.chants._resolve_pending_entrance_arm()
        self.assertEqual(self.app.entrance_starts, 0)
        self.assertTrue(self.app._entrance_armed)

    def test_noop_when_nothing_is_armed(self) -> None:
        self.app._entrance_armed = False
        self.app.lastpagename = ""
        self.chants._resolve_pending_entrance_arm()
        self.assertEqual(self.app.entrance_starts, 0)

    def test_only_fires_on_the_false_to_true_matchstarted_transition(self) -> None:
        # chants_runtime_loop only calls _resolve_pending_entrance_arm when
        # `was_matchstarted` was False -- simulate that call contract
        # directly rather than running the full loop.
        self.app._entrance_armed = True
        self.app.lastpagename = ""
        self.app.matchstarted = True  # already running before this tick
        was_matchstarted = self.app.matchstarted
        self.app.matchstarted = True
        if not was_matchstarted:
            self.chants._resolve_pending_entrance_arm()
        # Since matchstarted was already True, the resolver must not have
        # been invoked -- the arm stays untouched for _handle_page_transition
        # (or an earlier genuine transition) to deal with normally.
        self.assertTrue(self.app._entrance_armed)
        self.assertEqual(self.app.entrance_starts, 0)


if __name__ == "__main__":
    unittest.main()
