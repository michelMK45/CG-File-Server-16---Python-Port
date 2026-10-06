"""Ball / Referee / Wipe / Adboard packs are renamed to the id the game will ask for
(the match's league id, read live) when they are installed -- see match_asset_ids."""
from __future__ import annotations

import queue
import tempfile
import unittest
import unittest.mock
from pathlib import Path

from server16_py.asset_runtime import AssetRuntime


class FakeIni:
    def __init__(self, data: dict[str, dict[str, str]]) -> None:
        self._data = data

    def read(self, key: str, section: str) -> str:
        return self._data.get(section, {}).get(key, "")


class FakeApp:
    def __init__(self, base: Path, league: str, ini: dict[str, dict[str, str]]) -> None:
        self.exedir = base
        self.TOURROUNDID = "967"
        self.LEAGUEID = league
        self.curstad = ""
        self.settings_ini = FakeIni(ini)
        self.enabled = {"Ball": True, "Referee": True, "Wipe": True, "Adboard": True, "Stadium": False}
        self._kickoff_generation = 1
        self._active_ball_runtime = None
        self._active_adboard_injected_files: list[str] = []
        self._stadium_task_running = False
        self._worker_queue: "queue.Queue" = queue.Queue()
        self.logs: list[str] = []

    def module_enabled(self, name: str) -> bool:
        return self.enabled.get(name, False)

    def stadium_picker_awaiting_selection(self) -> bool:
        return False

    def tr(self, key: str) -> str:
        return key

    def log(self, *parts) -> None:
        self.logs.append(" ".join(str(p) for p in parts))


class _RuntimeCase(unittest.TestCase):
    # NOTE: copy_file_atomic skips a copy when source and destination have the same size AND mtime,
    # and files written back to back share an mtime -- so a "game" file and the pack file that
    # replaces it must differ in length in these tests, or the replacement is (correctly) skipped.
    league = "208"
    ini: dict[str, dict[str, str]] = {}

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)
        self.app = FakeApp(self.base, self.league, self.ini)
        self.runtime = AssetRuntime(self.app)
        self.runtime._show_asset_toast = unittest.mock.Mock()
        self.runtime._show_warning_toast = unittest.mock.Mock()

    def write(self, path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def scene(self, *parts: str) -> Path:
        return self.base.joinpath("data", "sceneassets", *parts)

    def lua(self, name: str, text: str) -> None:
        self.write(self.base / "data" / "fifarna" / "lua" / "assignments" / name, text.encode("utf-8"))

    def logged(self) -> str:
        return "\n".join(self.app.logs)


class BallRemapTests(_RuntimeCase):
    ini = {"ball": {"967": "CAF"}}

    def setUp(self) -> None:
        super().setUp()
        self.write(self.scene("ball", "specificball_0_208_0.rx3"), b"game ball model 208")
        self.write(self.scene("ball", "ball_110.rx3"), b"native 110")
        pack = self.base / "FSW" / "balls" / "CAF"
        self.write(pack / "specificball_0_967_0.rx3", b"pack model")
        self.write(pack / "specificball_0_967_0_textures.rx3", b"pack tex")

    def test_the_pack_is_installed_under_the_match_league_id(self) -> None:
        self.runtime.apply_ball_runtime()
        self.assertEqual(self.scene("ball", "specificball_0_208_0.rx3").read_bytes(), b"pack model")
        self.assertEqual(self.scene("ball", "specificball_0_208_0_textures.rx3").read_bytes(), b"pack tex")
        self.assertFalse(self.scene("ball", "specificball_0_967_0.rx3").exists())
        self.assertIn("pack id 967 -> 208", self.logged())

    def test_the_game_file_that_was_overwritten_comes_back(self) -> None:
        self.runtime.apply_ball_runtime()
        self.app.TOURROUNDID = "999"
        self.runtime.apply_ball_runtime()
        self.assertEqual(self.scene("ball", "specificball_0_208_0.rx3").read_bytes(), b"game ball model 208")
        self.assertFalse(self.scene("ball", "specificball_0_208_0_textures.rx3").exists())
        self.assertEqual(self.scene("ball", "ball_110.rx3").read_bytes(), b"native 110")

    def test_the_tv_bumper_reapply_keeps_the_renaming(self) -> None:
        self.runtime.apply_ball_runtime()
        self.write(self.scene("ball", "specificball_0_208_0.rx3"), b"overwritten by someone")
        self.assertTrue(self.runtime.reapply_active_ball_runtime(reason="test"))
        self.assertEqual(self.scene("ball", "specificball_0_208_0.rx3").read_bytes(), b"pack model")
        self.assertFalse(self.scene("ball", "specificball_0_967_0.rx3").exists())

    def test_without_a_league_id_the_pack_is_installed_as_before(self) -> None:
        self.app.LEAGUEID = ""
        self.runtime.apply_ball_runtime()
        self.assertEqual(self.scene("ball", "specificball_0_967_0.rx3").read_bytes(), b"pack model")
        self.assertEqual(self.scene("ball", "specificball_0_208_0.rx3").read_bytes(), b"game ball model 208")

    def test_a_pack_already_addressed_to_the_match_is_not_touched(self) -> None:
        pack = self.base / "FSW" / "balls" / "CAF"
        for item in list(pack.iterdir()):
            item.rename(pack / item.name.replace("_967_", "_208_"))
        self.runtime.apply_ball_runtime()
        self.assertEqual(self.scene("ball", "specificball_0_208_0.rx3").read_bytes(), b"pack model")
        self.assertNotIn("renamed", self.logged())

    def test_a_pack_with_several_ids_is_installed_untouched(self) -> None:
        self.write(self.base / "FSW" / "balls" / "CAF" / "specificball_0_991_0.rx3", b"other competition")
        self.runtime.apply_ball_runtime()
        self.assertEqual(self.scene("ball", "specificball_0_967_0.rx3").read_bytes(), b"pack model")
        self.assertEqual(self.scene("ball", "specificball_0_991_0.rx3").read_bytes(), b"other competition")
        self.assertEqual(self.scene("ball", "specificball_0_208_0.rx3").read_bytes(), b"game ball model 208")
        self.assertIn("several ids", self.logged())


class RefereeRemapTests(_RuntimeCase):
    league = "54"
    ini = {"referee": {"967": "UEFAQ"}}

    def setUp(self) -> None:
        super().setUp()
        self.write(self.scene("kit", "kit_6004_5_53.rx3"), b"native 53")
        self.write(self.scene("kit", "kit_6004_5_54.rx3"), b"native 54")
        pack = self.base / "FSW" / "referee" / "UEFAQ"
        self.write(pack / "kit_6004_5_967.rx3", b"pack kit")

    def test_the_clone_table_decides_the_id(self) -> None:
        # general.lua clones league 54's referee kits from 53, so that is the file the game asks for.
        self.lua("general.lua", "copyTournamentRefereeKitAssets(54,53)\n")
        self.runtime.apply_referee_runtime()
        self.assertEqual(self.scene("kit", "kit_6004_5_53.rx3").read_bytes(), b"pack kit")
        self.assertEqual(self.scene("kit", "kit_6004_5_54.rx3").read_bytes(), b"native 54")
        self.assertIn("pack id 967 -> 53", self.logged())

    def test_without_a_clone_the_league_id_is_used(self) -> None:
        self.runtime.apply_referee_runtime()
        self.assertEqual(self.scene("kit", "kit_6004_5_54.rx3").read_bytes(), b"pack kit")

    def test_team_kits_sharing_the_folder_are_never_touched(self) -> None:
        self.write(self.scene("kit", "kit_1_0_0.rx3"), b"team kit")
        self.runtime.apply_referee_runtime()
        self.app.TOURROUNDID = "999"
        self.runtime.apply_referee_runtime()
        self.assertEqual(self.scene("kit", "kit_1_0_0.rx3").read_bytes(), b"team kit")
        self.assertEqual(self.scene("kit", "kit_6004_5_54.rx3").read_bytes(), b"native 54")


class WipeRemapTests(_RuntimeCase):
    league = "322"
    ini = {"wipe": {"967": "AFC"}}

    def test_a_swapped_league_resolves_to_its_partner(self) -> None:
        self.lua("patch.lua", "swapTournamentID(322, 66)\n")
        self.write(self.scene("wipe3d", "specificwipe_0_66_0.rx3"), b"game wipe 66 original")
        self.write(self.base / "FSW" / "wipe" / "AFC" / "specificwipe_0_993_0.rx3", b"pack wipe")
        self.runtime.apply_wipe_runtime()
        self.assertEqual(self.scene("wipe3d", "specificwipe_0_66_0.rx3").read_bytes(), b"pack wipe")
        self.app.TOURROUNDID = "999"
        self.runtime.apply_wipe_runtime()
        self.assertEqual(self.scene("wipe3d", "specificwipe_0_66_0.rx3").read_bytes(), b"game wipe 66 original")

    def test_toasts_carry_the_wipe_icon(self) -> None:
        self.write(self.scene("wipe3d", "specificwipe_0_322_0.rx3"), b"game wipe 322 original")
        self.write(self.base / "FSW" / "wipe" / "AFC" / "specificwipe_0_993_0.rx3", b"pack wipe")
        self.runtime.apply_wipe_runtime()
        self.assertEqual(self.runtime._show_asset_toast.call_args.kwargs["icon"], "wipe")
        self.app.enabled["Wipe"] = False
        self.runtime.apply_wipe_runtime()
        self.assertEqual(self.runtime._show_warning_toast.call_args.kwargs["icon"], "wipe")


class AdboardRemapTests(_RuntimeCase):
    ini = {"adboard": {"967": "AFC"}}

    def setUp(self) -> None:
        super().setUp()
        self.write(self.scene("adboard", "specificadboard_0_208_0_0.rx3"), b"native board 208")
        pack = self.base / "FSW" / "adboards" / "AFC"
        self.write(pack / "specificadboard_0_967_0_0.rx3", b"pack board")
        self.write(pack / "cornerflag_0_990_0.rx3", b"pack flag")

    def test_boards_and_flags_are_each_renamed_to_the_match_id(self) -> None:
        self.runtime.apply_adboard_runtime()
        self.assertEqual(self.scene("adboard", "specificadboard_0_208_0_0.rx3").read_bytes(), b"pack board")
        self.assertEqual(self.scene("flag", "cornerflag_0_208_0.rx3").read_bytes(), b"pack flag")
        self.assertFalse(self.scene("adboard", "specificadboard_0_967_0_0.rx3").exists())
        self.assertIn("specificadboard_0_208_0_0.rx3", self.app._active_adboard_injected_files)

    def test_the_game_board_it_replaced_comes_back_instead_of_being_deleted(self) -> None:
        self.runtime.apply_adboard_runtime()
        self.app.TOURROUNDID = "999"
        self.runtime.apply_adboard_runtime()
        self.assertEqual(self.scene("adboard", "specificadboard_0_208_0_0.rx3").read_bytes(), b"native board 208")
        self.assertFalse(self.scene("flag", "cornerflag_0_208_0.rx3").exists())
        self.assertEqual(self.app._active_adboard_injected_files, [])

    def test_turning_the_module_off_gives_the_game_files_back(self) -> None:
        self.runtime.apply_adboard_runtime()
        self.app.enabled["Adboard"] = False
        self.runtime.apply_adboard_runtime()
        self.assertEqual(self.scene("adboard", "specificadboard_0_208_0_0.rx3").read_bytes(), b"native board 208")

    def test_the_restore_survives_an_app_restart(self) -> None:
        # The old code remembered what it injected in memory only; the manifest lives on disk.
        self.runtime.apply_adboard_runtime()
        self.app._active_adboard_injected_files = []  # what a fresh process would know
        self.runtime._clear_active_adboard_files()
        self.assertEqual(self.scene("adboard", "specificadboard_0_208_0_0.rx3").read_bytes(), b"native board 208")

    def test_a_folder_named_after_the_stadium_is_ignored(self) -> None:
        # Adboards are competition-only: the old FSW/adboards/<stadium>/ override is gone.
        self.app.curstad = "Anfield"
        stadium = self.base / "FSW" / "adboards" / "Anfield"
        self.write(stadium / "specificadboard_0_990_0_0.rx3", b"stadium board")
        self.runtime.apply_adboard_runtime()
        self.assertFalse(self.scene("adboard", "specificadboard_0_990_0_0.rx3").exists())
        self.assertEqual(self.scene("adboard", "specificadboard_0_208_0_0.rx3").read_bytes(), b"pack board")

    def test_without_a_league_id_the_pack_is_installed_as_before(self) -> None:
        self.app.LEAGUEID = ""
        self.runtime.apply_adboard_runtime()
        self.assertEqual(self.scene("adboard", "specificadboard_0_967_0_0.rx3").read_bytes(), b"pack board")
        self.assertEqual(self.scene("flag", "cornerflag_0_990_0.rx3").read_bytes(), b"pack flag")


if __name__ == "__main__":
    unittest.main()
