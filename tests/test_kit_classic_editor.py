from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from server16_py import kit_classic as kc
from server16_py import kit_classic_editor as ed

SUPPORTED_PLAYER_LUA = "\n".join(
    f"function {name}(a,b,c)\nend" for name in kc.REQUIRED_PLAYER_LUA_FUNCTIONS
) + "\n"


def _name(n: int) -> str:
    return f"Combinación {n}"


class TeamKitSideTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.exedir = Path(self._tmp.name)
        self.runtime = kc.KitClassicRuntime(SimpleNamespace(exedir=self.exedir, log=lambda *a: None))
        self.runtime.team_lua_dir().mkdir(parents=True)
        self._install_player_lua()
        self.kit_dir = self.runtime.kit_dir()
        self.kit_dir.mkdir(parents=True)
        for team, types in ((383, (0, 1, 2, 3, 12)), (100, (0, 1))):
            for ktype in types:
                (self.kit_dir / f"kit_{team}_{ktype}_0.rx3").write_bytes(b"x")
        self.runtime.kits(refresh=True)

    def tearDown(self):
        self._tmp.cleanup()

    def _install_player_lua(self, text: str = SUPPORTED_PLAYER_LUA) -> None:
        path = self.runtime.player_lua_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def _sides(self, home: int = 383, away: int = 100) -> tuple[ed.TeamKitSide, ed.TeamKitSide]:
        return ed.open_sides(self.runtime, home, away, _name)

    def _save_two_combinations(self) -> None:
        self.runtime.save(kc.TeamCombinations(383, [kc.Combination("A", [kc.Mix(0, 0, 0, 1, 0)]), kc.Combination("B")],
                                              home=0, away=1))

    def test_new_team_starts_on_the_original_kits_with_the_usual_kit_per_side(self):
        home, away = self._sides()
        self.assertEqual((home.slot, away.slot), (0, 1))
        self.assertIsNone(home.combination_cursor)
        self.assertEqual((home.parts, away.parts), ((0, 0, 0), (1, 1, 1)))
        self.assertFalse(home.pending)
        self.assertEqual(home.combination_choices(), [None, ed.NEW])

    def test_garments_are_a_preview_until_commit_creates_a_combination_for_that_side_only(self):
        home, _ = self._sides()
        self.assertFalse(home.cycle(ed.ROW_SHORTS, +1))
        self.assertEqual(home.parts, (0, 1, 0))
        self.assertTrue(home.pending)
        self.assertFalse(self.runtime.team_lua_path(383).exists())

        self.assertTrue(home.commit())
        expected = kc.TeamCombinations(383, [kc.Combination("Combinación 1", [kc.Mix(0, 0, 0, 1, 0)])], home=0, away=None)
        self.assertEqual(kc.read_lua_text(self.runtime.team_lua_path(383)), kc.apply_team_block("", expected))
        tc = self.runtime.load(383)
        self.assertEqual((tc.home, tc.away), (0, None))   # the away side keeps the original kits
        self.assertEqual(home.combination_cursor, 0)
        self.assertFalse(home.pending)
        self.assertFalse(home.commit())   # nothing left to save

    def test_editing_the_sides_combination_writes_what_the_tab_would(self):
        self._save_two_combinations()
        before = kc.read_lua_text(self.runtime.team_lua_path(383))
        home, _ = self._sides()
        self.assertEqual(home.parts, (0, 1, 0))
        home.cycle(ed.ROW_SOCKS, -1)   # 0 wraps round to the last loose kit
        self.assertEqual(home.parts, (0, 1, 12))
        self.assertTrue(home.commit())
        expected = kc.TeamCombinations(383, [kc.Combination("A", [kc.Mix(0, 0, 0, 1, 12)]), kc.Combination("B")],
                                       home=0, away=1)
        self.assertEqual(kc.read_lua_text(self.runtime.team_lua_path(383)), kc.apply_team_block(before, expected))

    def test_combination_row_saves_the_sides_choice_except_on_new(self):
        self._save_two_combinations()
        home, _ = self._sides()
        self.assertEqual(home.combination_choices(), [None, 0, 1, ed.NEW])
        self.assertTrue(home.cycle(ed.ROW_COMBINATION, +1))
        self.assertEqual((self.runtime.load(383).home, self.runtime.load(383).away), (1, 1))
        before = kc.read_lua_text(self.runtime.team_lua_path(383))
        self.assertFalse(home.cycle(ed.ROW_COMBINATION, +1))
        self.assertEqual(home.combination_cursor, ed.NEW)
        self.assertEqual(home.parts, (0, 0, 0))   # an empty combination shows the kit itself
        self.assertEqual(kc.read_lua_text(self.runtime.team_lua_path(383)), before)
        self.assertTrue(home.cycle(ed.ROW_COMBINATION, +1))   # wraps round to the original kits
        self.assertIsNone(self.runtime.load(383).home)
        self.assertFalse(home.cycle(ed.ROW_COMBINATION, -1))  # back onto NEW
        self.assertEqual(home.combination_cursor, ed.NEW)

    def test_commit_on_new_creates_the_combination_and_selects_it(self):
        self._save_two_combinations()
        home, _ = self._sides()
        home.cycle(ed.ROW_COMBINATION, -1)   # None
        home.cycle(ed.ROW_COMBINATION, -1)   # NEW
        self.assertTrue(home.commit())
        tc = self.runtime.load(383)
        self.assertEqual([c.name for c in tc.items], ["A", "B", "Combinación 3"])
        self.assertEqual((tc.home, tc.away), (2, 1))
        self.assertEqual(tc.items[2].mixes, [])

        home.cycle(ed.ROW_COMBINATION, +1)   # NEW again
        home.cycle(ed.ROW_SHIRT, +1)
        self.assertTrue(home.commit())
        tc = self.runtime.load(383)
        self.assertEqual(tc.items[3].mixes, [kc.Mix(0, 0, 1, 0, 0)])
        self.assertEqual(tc.home, 3)

    def test_changing_kit_or_combination_drops_uncommitted_garments(self):
        self._save_two_combinations()
        home, _ = self._sides()
        home.cycle(ed.ROW_SHIRT, +1)
        self.assertTrue(home.pending)
        home.cycle(ed.ROW_KIT, +1)
        self.assertEqual((home.slot, home.parts, home.pending), (1, (1, 1, 1), False))
        home.cycle(ed.ROW_KIT, -1)
        self.assertEqual(home.parts, (0, 1, 0))   # the combination's mix for kit 0
        home.cycle(ed.ROW_SHIRT, +1)
        home.cycle(ed.ROW_COMBINATION, +1)
        self.assertFalse(home.pending)
        self.assertEqual(self.runtime.load(383).items[0].mixes, [kc.Mix(0, 0, 0, 1, 0)])

    def test_goalkeeper_row_saves_the_sides_choice(self):
        home, _ = self._sides()
        self.assertEqual(home.gk_choices(), [None, 2, 12])
        self.assertIsNone(home.gk_layer_sources())
        self.assertTrue(home.cycle(ed.ROW_GK, +1))
        tc = self.runtime.load(383)
        self.assertEqual((tc.gk_home, tc.gk_away), (2, None))
        self.assertEqual(home.gk_layer_sources()["shirt"], self.kit_dir / "kit_383_2_0.rx3")
        home.cycle(ed.ROW_GK, +1)
        self.assertTrue(home.cycle(ed.ROW_GK, +1))   # 12 -> automatic
        self.assertFalse(self.runtime.load(383).has_gk)

    def test_without_rev_mod_support_only_the_kit_row_moves(self):
        self._install_player_lua("function swapTeamKit(team,type1,type2)\nend\n")
        home, _ = self._sides()
        self.assertFalse(home.editable)
        for row in (ed.ROW_COMBINATION, ed.ROW_SHIRT, ed.ROW_GK):
            self.assertFalse(home.cycle(row, +1))
        self.assertEqual((home.combination_cursor, home.parts), (None, (0, 0, 0)))
        self.assertFalse(home.commit())
        home.cycle(ed.ROW_KIT, +1)
        self.assertEqual(home.slot, 1)
        self.assertFalse(self.runtime.team_lua_path(383).exists())

    def test_team_playing_itself_shares_one_set_of_combinations(self):
        home, away = self._sides(383, 383)
        self.assertIs(home.tc, away.tc)
        home.cycle(ed.ROW_SHORTS, +1)
        home.commit()
        away.cycle(ed.ROW_SHIRT, +1)   # away looks at kit 1: shirt 1 -> 2
        away.commit()
        tc = self.runtime.load(383)
        self.assertEqual([c.mixes for c in tc.items], [[kc.Mix(0, 0, 0, 1, 0)], [kc.Mix(0, 1, 2, 1, 1)]])
        self.assertEqual((tc.home, tc.away), (0, 1))
        self.assertEqual(away.conflicts(), [])

    def test_a_kit_that_is_not_loose_is_stepped_from_where_it_is(self):
        self.runtime.save(kc.TeamCombinations(383, [kc.Combination("A", [kc.Mix(0, 0, 5, 0, 0)])], home=0, away=None))
        home, _ = self._sides()
        self.assertEqual(home.parts, (5, 0, 0))
        home.cycle(ed.ROW_SHIRT, +1)
        self.assertEqual(home.parts, (12, 0, 0))
        home.cycle(ed.ROW_SHIRT, -1)
        self.assertEqual(home.parts, (3, 0, 0))   # 5 isn't offered once left

    def test_layer_sources_follow_the_garments_shown(self):
        home, away = self._sides()
        home.cycle(ed.ROW_SHORTS, +1)
        self.assertEqual(home.layer_sources(), {
            "shirt": self.kit_dir / "kit_383_0_0.rx3",
            "shorts": self.kit_dir / "kit_383_1_0.rx3",
            "socks": self.kit_dir / "kit_383_0_0.rx3",
        })
        away.cycle(ed.ROW_KIT, +1)   # team 100 only has kits 0 and 1: wraps to 0
        self.assertEqual(away.layer_sources()["shirt"], self.kit_dir / "kit_100_0_0.rx3")

    def test_unknown_row_is_rejected(self):
        home, _ = self._sides()
        with self.assertRaises(ValueError):
            home.cycle(99, +1)


if __name__ == "__main__":
    unittest.main()
