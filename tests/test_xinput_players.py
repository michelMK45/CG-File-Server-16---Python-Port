from __future__ import annotations

import ctypes
import unittest

from server16_py import xinput_players as xp
from server16_py.win32_types import XINPUT_CAPABILITIES_EX

A, B, GUIDE = 0x1000, 0x2000, 0x0400


class PlayerIdentityTests(unittest.TestCase):
    def test_struct_matches_what_xinput1_4_fills(self) -> None:
        # Checked live against xinput1_4.dll 2026-10-05: 32 bytes, VID/PID
        # right after the 20-byte XINPUT_CAPABILITIES.
        self.assertEqual(ctypes.sizeof(XINPUT_CAPABILITIES_EX), 32)
        self.assertEqual(XINPUT_CAPABILITIES_EX.VendorId.offset, 20)
        self.assertEqual(XINPUT_CAPABILITIES_EX.ProductId.offset, 22)

    def test_reads_vendor_and_product_id(self) -> None:
        def capabilities_ex(one, index, flags, caps_ref) -> int:
            self.assertEqual((one, index, flags), (1, 2, 0))
            caps = ctypes.cast(caps_ref, ctypes.POINTER(XINPUT_CAPABILITIES_EX)).contents
            caps.VendorId, caps.ProductId = 0x045E, 0x0B12
            return 0

        self.assertEqual(xp.read_player_identity(capabilities_ex, 2), (0x045E, 0x0B12))

    def test_unknown_without_the_function_or_when_it_fails(self) -> None:
        def boom(*_args):
            raise OSError("access violation")

        self.assertIsNone(xp.read_player_identity(None, 0))
        self.assertIsNone(xp.read_player_identity(lambda *_args: 1167, 0))
        self.assertIsNone(xp.read_player_identity(boom, 0))

    def test_bind_gives_up_quietly_on_a_dll_without_ordinal_108(self) -> None:
        class NoSuchExport:
            def __getitem__(self, ordinal):
                raise AttributeError(ordinal)

        self.assertIsNone(xp.bind_capabilities_ex(NoSuchExport()))

    def test_only_a_different_identity_rules_a_virtual_pad_out(self) -> None:
        self.assertTrue(xp.may_be_virtual_pad((0x045E, 0x028E)))
        self.assertTrue(xp.may_be_virtual_pad(None))
        self.assertFalse(xp.may_be_virtual_pad((0x045E, 0x0B12)))


class ResolveWithoutInputTests(unittest.TestCase):
    """What can be said before anyone presses anything."""

    def test_one_virtual_pad_and_one_candidate_is_certain(self) -> None:
        # The driver index (0) is NOT the player: the candidate is player 2.
        self.assertEqual(xp.VirtualPadMatcher().resolve({0: 0}, [1]), {1: 0})

    def test_several_virtual_pads_are_handed_out_in_driver_index_order(self) -> None:
        # Slot 3's pad was plugged in before slot 1's.
        self.assertEqual(xp.VirtualPadMatcher().resolve({0: 1, 2: 0}, [1, 3]), {1: 2, 3: 0})

    def test_pads_without_a_driver_index_go_last_in_slot_order(self) -> None:
        self.assertEqual(xp.VirtualPadMatcher().resolve({0: None, 1: None, 2: 0}, [0, 1, 2]), {0: 2, 1: 0, 2: 1})

    def test_more_candidates_than_virtual_pads_stays_open(self) -> None:
        self.assertEqual(xp.VirtualPadMatcher().resolve({0: 0}, [0, 1]), {})

    def test_a_virtual_pad_xinput_does_not_list_yet_stays_open(self) -> None:
        self.assertEqual(xp.VirtualPadMatcher().resolve({0: 0, 1: 1}, [2]), {})

    def test_nothing_bridged_means_nothing_is_virtual(self) -> None:
        self.assertEqual(xp.VirtualPadMatcher().resolve({}, [0]), {})


class MatchByInputTests(unittest.TestCase):
    """A virtual pad shows exactly the buttons its slot sent -- what tells it
    from a real pad with the same identity."""

    def _confirm(self, matcher: xp.VirtualPadMatcher, sent: dict[int, int], players: dict[int, int]) -> None:
        for _ in range(xp.SIGHTINGS_TO_CONFIRM):
            matcher.observe(sent, players)

    def test_the_player_showing_the_slots_buttons_is_its_virtual_pad(self) -> None:
        matcher = xp.VirtualPadMatcher()
        self.assertFalse(matcher.observe({0: A}, {0: 0, 1: A}))  # one sighting is not enough
        self.assertEqual(matcher.resolve({0: 0}, [0, 1]), {})
        self.assertTrue(matcher.observe({0: A}, {0: 0, 1: A}))
        self.assertEqual(matcher.resolve({0: 0}, [0, 1]), {1: 0})

    def test_sightings_add_up_across_separate_taps(self) -> None:
        matcher = xp.VirtualPadMatcher()
        matcher.observe({0: A}, {0: 0, 1: A})
        matcher.observe({0: 0}, {0: 0, 1: 0})  # released
        self.assertTrue(matcher.observe({0: B}, {0: 0, 1: B}))

    def test_an_idle_slot_says_nothing(self) -> None:
        matcher = xp.VirtualPadMatcher()
        self._confirm(matcher, {0: 0}, {0: 0, 1: 0})
        self.assertEqual(matcher.resolve({0: 0}, [0, 1]), {})

    def test_two_players_showing_the_same_buttons_says_nothing(self) -> None:
        # The real pad's owner happens to hold the same button.
        matcher = xp.VirtualPadMatcher()
        self._confirm(matcher, {0: A}, {0: A, 1: A})
        self.assertEqual(matcher.resolve({0: 0}, [0, 1]), {})

    def test_two_slots_sending_the_same_buttons_say_nothing(self) -> None:
        matcher = xp.VirtualPadMatcher()
        self._confirm(matcher, {0: A, 1: A}, {0: A, 1: 0, 2: 0})
        self.assertEqual(matcher.resolve({0: 0, 1: 1}, [0, 1, 2]), {})

    def test_a_sighting_of_a_different_player_starts_the_count_again(self) -> None:
        matcher = xp.VirtualPadMatcher()
        matcher.observe({0: A}, {0: A, 1: 0})
        self.assertFalse(matcher.observe({0: A}, {0: 0, 1: A}))
        self.assertTrue(matcher.observe({0: A}, {0: 0, 1: A}))
        self.assertEqual(matcher.resolve({0: 0}, [0, 1]), {1: 0})

    def test_guide_is_ignored_because_xinput_never_reports_it(self) -> None:
        matcher = xp.VirtualPadMatcher()
        self._confirm(matcher, {0: A | GUIDE}, {0: 0, 1: A})
        self.assertEqual(matcher.resolve({0: 0}, [0, 1]), {1: 0})
        # Guide alone is "nothing pressed" as far as XInput can show.
        other = xp.VirtualPadMatcher()
        self._confirm(other, {0: GUIDE}, {0: 0, 1: 0})
        self.assertEqual(other.resolve({0: 0}, [0, 1]), {})

    def test_input_overrides_a_wrong_driver_index_order(self) -> None:
        matcher = xp.VirtualPadMatcher()
        self.assertEqual(matcher.resolve({0: 0, 1: 1}, [2, 3]), {2: 0, 3: 1})
        self._confirm(matcher, {0: A, 1: 0}, {2: 0, 3: A})
        # Slot 1 is player 4 after all -- which leaves player 3 for slot 2.
        self.assertEqual(matcher.resolve({0: 0, 1: 1}, [2, 3]), {3: 0, 2: 1})

    def test_a_confirmed_player_is_not_offered_to_another_slot(self) -> None:
        matcher = xp.VirtualPadMatcher()
        self._confirm(matcher, {0: A, 1: 0}, {1: A, 2: 0})
        # Slot 2 sends B while slot 1's player (lagging a look) shows it too.
        self._confirm(matcher, {0: A, 1: B}, {1: B, 2: 0})
        self.assertEqual(matcher.resolve({0: 0, 1: 1}, [1, 2, 3]), {1: 0})

    def test_a_pair_survives_the_one_look_lag_around_a_press(self) -> None:
        matcher = xp.VirtualPadMatcher()
        self._confirm(matcher, {0: A}, {0: 0, 1: A})
        for _ in range(xp.MISSES_TO_FORGET - 1):
            matcher.observe({0: B}, {0: 0, 1: A})
        matcher.observe({0: B}, {0: 0, 1: B})  # caught up: the misses are forgiven
        for _ in range(xp.MISSES_TO_FORGET - 1):
            matcher.observe({0: A}, {0: 0, 1: B})
        self.assertEqual(matcher.resolve({0: 0}, [0, 1]), {1: 0})

    def test_a_pair_is_dropped_once_the_player_keeps_not_showing_the_slots_buttons(self) -> None:
        # Windows moved the virtual pad to another player.
        matcher = xp.VirtualPadMatcher()
        self._confirm(matcher, {0: A}, {0: 0, 1: A})
        changed = [matcher.observe({0: A}, {0: A, 1: 0}) for _ in range(xp.MISSES_TO_FORGET)]
        self.assertEqual(changed, [False] * (xp.MISSES_TO_FORGET - 1) + [True])
        self._confirm(matcher, {0: A}, {0: A, 1: 0})
        self.assertEqual(matcher.resolve({0: 0}, [0, 1]), {0: 0})

    def test_a_pair_is_dropped_when_the_slot_loses_its_pad_or_the_player_leaves(self) -> None:
        matcher = xp.VirtualPadMatcher()
        self._confirm(matcher, {0: A}, {0: 0, 1: A})
        self.assertTrue(matcher.observe({}, {0: 0, 1: 0}))  # bridge turned off
        self.assertEqual(matcher.resolve({0: 0}, [0, 1]), {})
        self._confirm(matcher, {0: A}, {0: 0, 1: A})
        self.assertTrue(matcher.observe({0: A}, {0: 0}))  # player 2 unplugged
        self.assertEqual(matcher.resolve({0: 0}, [0, 1]), {})


if __name__ == "__main__":
    unittest.main()
