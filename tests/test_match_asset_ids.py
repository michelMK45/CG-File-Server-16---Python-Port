from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from server16_py.match_asset_ids import (
    LuaIdMaps,
    engine_id,
    pack_ids,
    plan_pack_remap,
    read_lua_id_maps,
)
from server16_py.offsets import Offsets


class EngineIdTests(unittest.TestCase):
    maps = LuaIdMaps(swaps={322: 66, 66: 322}, referee_clone={54: 53, 66: 65})

    def test_unlisted_league_is_used_as_it_is(self) -> None:
        for kind in ("ball", "wipe", "adboard", "cornerflag", "referee"):
            self.assertEqual(engine_id(kind, 208, self.maps), 208)

    def test_swap_applies_to_every_kind(self) -> None:
        for kind in ("ball", "wipe", "adboard", "cornerflag"):
            self.assertEqual(engine_id(kind, 322, self.maps), 66)
            self.assertEqual(engine_id(kind, 66, self.maps), 322)

    def test_referee_kits_follow_the_clone_table(self) -> None:
        # Seen live: league 54 -> the referee asked for kit_..._53 while the wipe asked for 54.
        self.assertEqual(engine_id("referee", 54, self.maps), 53)
        self.assertEqual(engine_id("ball", 54, self.maps), 54)

    def test_referee_clone_is_applied_after_the_swap(self) -> None:
        # player.lua: tournidref = getCloneTournamentRefereeKits(getTournamentGraphics(leagueID))
        # 322 -swap-> 66 -clone-> 65
        self.assertEqual(engine_id("referee", 322, self.maps), 65)

    def test_global_override_wins_for_everything(self) -> None:
        maps = LuaIdMaps(swaps={322: 66}, referee_clone={223: 5}, forced=223)
        self.assertEqual(engine_id("ball", 208, maps), 223)
        self.assertEqual(engine_id("referee", 208, maps), 5)

    def test_no_maps_is_the_identity(self) -> None:
        self.assertEqual(engine_id("referee", 54), 54)


class ReadLuaIdMapsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.exedir = Path(self._tmp.name)
        self.assignments = self.exedir / "data" / "fifarna" / "lua" / "assignments"
        self.assignments.mkdir(parents=True)

    def write(self, name: str, text: str) -> None:
        (self.assignments / name).write_text(text, encoding="utf-8")

    def test_parses_swaps_clones_and_ignores_comments(self) -> None:
        self.write(
            "patch.lua",
            "--Patch Settings\nswapTournamentID(322, 66)\n -- swapTournamentID(1, 2)\nswapTournamentID( 326 ,335 ) --note\n",
        )
        self.write(
            "general.lua",
            "copyTournamentRefereeKitAssets(54,53)\n--copyTournamentRefereeKitAssets(9,8)\n"
            "copyTournamentNameAndNumberAssets(224,223)\n--useGlobalTournamentGraphics(223)\n",
        )
        maps = read_lua_id_maps(self.exedir)
        self.assertEqual(maps.swaps, {322: 66, 66: 322, 326: 335, 335: 326})
        self.assertEqual(maps.referee_clone, {54: 53})
        self.assertIsNone(maps.forced)

    def test_global_override_and_its_unset_value(self) -> None:
        self.write("a.lua", "useGlobalTournamentGraphics(223)\n")
        self.assertEqual(read_lua_id_maps(self.exedir).forced, 223)
        time.sleep(0.01)
        self.write("a.lua", "useGlobalTournamentGraphics(223)\nuseGlobalTournamentGraphics(-1)\n")
        self.assertIsNone(read_lua_id_maps(self.exedir).forced)

    def test_sub_folders_are_not_read(self) -> None:
        (self.assignments / "teams").mkdir()
        (self.assignments / "teams" / "team_1.lua").write_text("swapTournamentID(1, 2)\n", encoding="utf-8")
        self.assertEqual(dict(read_lua_id_maps(self.exedir).swaps), {})

    def test_missing_folder_means_no_mapping(self) -> None:
        maps = read_lua_id_maps(self.exedir / "nowhere")
        self.assertEqual((dict(maps.swaps), dict(maps.referee_clone), maps.forced), ({}, {}, None))

    def test_an_edited_file_is_picked_up_again(self) -> None:
        self.write("patch.lua", "swapTournamentID(1, 2)\n")
        self.assertEqual(read_lua_id_maps(self.exedir).swaps, {1: 2, 2: 1})
        self.write("patch.lua", "swapTournamentID(1, 2)\nswapTournamentID(3, 4)\n")
        self.assertEqual(read_lua_id_maps(self.exedir).swaps, {1: 2, 2: 1, 3: 4, 4: 3})


class PlanPackRemapTests(unittest.TestCase):
    def test_ball_models_and_textures_keep_everything_but_the_id(self) -> None:
        plan = plan_pack_remap(
            "ball", ["specificball_0_967_0.rx3", "specificball_0_967_0_textures.rx3", "specificball_0_967_4.rx3"], 208
        )
        self.assertEqual(plan.reason, "remapped")
        self.assertEqual(plan.source_ids, (967,))
        self.assertEqual(
            plan.rename,
            {
                "specificball_0_967_0.rx3": "specificball_0_208_0.rx3",
                "specificball_0_967_0_textures.rx3": "specificball_0_208_0_textures.rx3",
                "specificball_0_967_4.rx3": "specificball_0_208_4.rx3",
            },
        )

    def test_ball_per_team_and_per_stadium_names(self) -> None:
        plan = plan_pack_remap(
            "ball", ["specificball_463_967_-1.rx3", "specificball_0_967_0_182_textures.rx3"], 53
        )
        self.assertEqual(
            plan.rename,
            {
                "specificball_463_967_-1.rx3": "specificball_463_53_-1.rx3",
                "specificball_0_967_0_182_textures.rx3": "specificball_0_53_0_182_textures.rx3",
            },
        )

    def test_the_generic_id_zero_is_left_alone(self) -> None:
        plan = plan_pack_remap("ball", ["specificball_0_0_0.rx3", "specificball_0_967_0.rx3"], 208)
        self.assertEqual(plan.rename, {"specificball_0_967_0.rx3": "specificball_0_208_0.rx3"})

    def test_wipe(self) -> None:
        plan = plan_pack_remap("wipe", ["specificwipe_0_993_0.rx3", "specificwipe_0_993_0_textures.rx3"], 208)
        self.assertEqual(
            plan.rename,
            {
                "specificwipe_0_993_0.rx3": "specificwipe_0_208_0.rx3",
                "specificwipe_0_993_0_textures.rx3": "specificwipe_0_208_0_textures.rx3",
            },
        )

    def test_adboard_board_id_in_the_second_slot(self) -> None:
        plan = plan_pack_remap("adboard", ["specificadboard_0_967_0_0.rx3"], 208)
        self.assertEqual(plan.rename, {"specificadboard_0_967_0_0.rx3": "specificadboard_0_208_0_0.rx3"})

    def test_adboard_old_naming_has_the_id_in_the_last_slot(self) -> None:
        plan = plan_pack_remap("adboard", ["specificadboard_0_0_0_54.rx3"], 208)
        self.assertEqual(plan.rename, {"specificadboard_0_0_0_54.rx3": "specificadboard_0_0_0_208.rx3"})

    def test_adboard_last_slot_of_a_per_team_name_is_not_an_id(self) -> None:
        plan = plan_pack_remap("adboard", ["specificadboard_472_0_0_3.rx3", "specificadboard_0_0_182_0.rx3"], 208)
        self.assertEqual((plan.reason, plan.rename), ("no-id", {}))

    def test_corner_flags_are_planned_apart_from_the_boards(self) -> None:
        names = ["specificadboard_0_993_0_0.rx3", "cornerflag_0_990_0.rx3"]
        self.assertEqual(plan_pack_remap("adboard", names, 208).rename, {"specificadboard_0_993_0_0.rx3": "specificadboard_0_208_0_0.rx3"})
        self.assertEqual(plan_pack_remap("cornerflag", names, 208).rename, {"cornerflag_0_990_0.rx3": "cornerflag_0_208_0.rx3"})

    def test_referee_kits_and_specific_kits(self) -> None:
        plan = plan_pack_remap(
            "referee", ["kit_6004_5_967.rx3", "kit_6007_105_967.rx3", "specifickit_6004_5_967_463_1853.rx3"], 53
        )
        self.assertEqual(
            plan.rename,
            {
                "kit_6004_5_967.rx3": "kit_6004_5_53.rx3",
                "kit_6007_105_967.rx3": "kit_6007_105_53.rx3",
                "specifickit_6004_5_967_463_1853.rx3": "specifickit_6004_5_53_463_1853.rx3",
            },
        )

    def test_team_kits_in_a_referee_pack_are_not_touched_or_counted(self) -> None:
        plan = plan_pack_remap("referee", ["kit_6004_5_967.rx3", "kit_1_0_0.rx3", "kit_10_2_967.rx3"], 53)
        self.assertEqual(plan.source_ids, (967,))
        self.assertEqual(plan.rename, {"kit_6004_5_967.rx3": "kit_6004_5_53.rx3"})

    def test_a_pack_with_several_ids_is_installed_untouched(self) -> None:
        plan = plan_pack_remap("referee", ["kit_6004_5_991.rx3", "kit_6004_5_967.rx3"], 53)
        self.assertEqual((plan.reason, plan.source_ids, plan.rename), ("multiple-ids", (967, 991), {}))

    def test_a_pack_that_already_answers_to_the_match_id_needs_nothing(self) -> None:
        plan = plan_pack_remap("ball", ["specificball_0_208_0.rx3"], 208)
        self.assertEqual((plan.reason, plan.rename), ("same-id", {}))

    def test_a_pack_with_the_match_id_and_another_is_treated_as_multi_id(self) -> None:
        plan = plan_pack_remap("ball", ["specificball_0_208_0.rx3", "specificball_0_967_0.rx3"], 208)
        self.assertEqual((plan.reason, plan.rename), ("multiple-ids", {}))

    def test_a_pack_without_ids_is_left_alone(self) -> None:
        plan = plan_pack_remap("ball", ["ball_110.rx3", "readme.txt"], 208)
        self.assertEqual((plan.reason, plan.rename), ("no-id", {}))

    def test_invalid_target_never_renames(self) -> None:
        for target in (0, -1):
            self.assertEqual(plan_pack_remap("ball", ["specificball_0_967_0.rx3"], target).rename, {})

    def test_nested_names_only_change_their_base_name(self) -> None:
        plan = plan_pack_remap("wipe", ["sub/specificwipe_0_993_0.rx3"], 208)
        self.assertEqual(plan.rename, {"sub/specificwipe_0_993_0.rx3": "sub/specificwipe_0_208_0.rx3"})

    def test_case_is_preserved_outside_the_id(self) -> None:
        plan = plan_pack_remap("wipe", ["SpecificWipe_0_993_0.RX3"], 208)
        self.assertEqual(plan.rename, {"SpecificWipe_0_993_0.RX3": "SpecificWipe_0_208_0.RX3"})

    def test_pack_ids(self) -> None:
        self.assertEqual(pack_ids("ball", ["specificball_0_967_0.rx3", "specificball_0_12_0.rx3", "x.rx3"]), {12, 967})


class LeagueOffsetTests(unittest.TestCase):
    def test_league_chain_is_the_tournament_struct_plus_0xD4(self) -> None:
        o = Offsets()
        # Same struct as TOUR/ROUND (T[:4] resolves to its base); only the final leaf differs.
        self.assertEqual(o.TLEAGUE[:4], o.T[:4])
        self.assertEqual(o.TLEAGUE[4], 0xD4)

    def test_is_configured_still_true(self) -> None:
        self.assertTrue(Offsets().is_configured())


if __name__ == "__main__":
    unittest.main()
