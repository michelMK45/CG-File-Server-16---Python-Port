from __future__ import annotations

import tempfile
import unittest
import unittest.mock
import zipfile
from pathlib import Path

from server16_py.asset_runtime import AssetRuntime
from tests.test_derby_scoreboard_runtime import FakeScoreboardApp

CREST = Path("imgAssets") / "crest" / "light" / "l241.dds"
CREST64 = Path("imgAssets") / "crest64x64" / "dark" / "l241.dds"


class ToggleableScoreboardApp(FakeScoreboardApp):
    def __init__(self, base: Path) -> None:
        super().__init__(base)
        self.enabled = {"ScoreBoard", "TvLogo"}

    def module_enabled(self, name: str) -> bool:
        return name in self.enabled


class ScoreboardUiTrackingTests(unittest.TestCase):
    """What a scoreboard pack installs into data/ui outside game/ (crests,
    fonts, ...) is backed up and put back as soon as a later match no longer
    wants it, so a competition's special crests don't stay in FIFA's menus.
    FSW/ScoreBoardDefaults/ (optional, mirrors data/ui) holds the user's own
    "normal" files and is laid down on every apply, under the current pack."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.app = ToggleableScoreboardApp(Path(self._tmp.name))
        self.ui = self.app.Scoredata
        self.write(self.ui / CREST, b"original crest")
        self.write(self.app.ScoreBoard / "WorldCup" / "game" / "scoreboard.big", b"wc")
        self.write(self.app.ScoreBoard / "WorldCup" / CREST, b"world cup crest, longer")
        self.write(self.app.ScoreBoard / "WorldCup" / CREST64, b"wc 64 crest")
        self.write(self.app.ScoreBoard / "Plain" / "game" / "scoreboard.big", b"plain")
        self.runtime = AssetRuntime(self.app)
        self.runtime._show_asset_toast = unittest.mock.Mock()
        self.runtime._show_warning_toast = unittest.mock.Mock()
        self.runtime.update_audio_overview = unittest.mock.Mock()

    def write(self, path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def assign(self, value: str) -> None:
        self.app.settings_ini.write("0", value, "Scoreboard")
        self.app.settings_ini.save()

    def unassign(self) -> None:
        self.app.settings_ini.delete_key("0", "Scoreboard")
        self.app.settings_ini.save()

    def test_pack_crest_is_installed(self) -> None:
        self.assign("WorldCup")
        self.runtime.apply_scoreboard_runtime()
        self.assertEqual((self.ui / CREST).read_bytes(), b"world cup crest, longer")
        self.assertEqual((self.ui / CREST64).read_bytes(), b"wc 64 crest")

    def test_next_match_without_scoreboard_restores_the_original_crest(self) -> None:
        self.assign("WorldCup")
        self.runtime.apply_scoreboard_runtime()
        self.unassign()
        self.runtime.apply_scoreboard_runtime()
        self.assertEqual((self.ui / CREST).read_bytes(), b"original crest")
        self.assertFalse((self.ui / CREST64).exists())

    def test_switching_to_a_pack_without_crests_restores_them(self) -> None:
        self.assign("WorldCup")
        self.runtime.apply_scoreboard_runtime()
        self.assign("Plain")
        self.runtime.apply_scoreboard_runtime()
        self.assertEqual((self.ui / CREST).read_bytes(), b"original crest")
        self.assertFalse((self.ui / CREST64).exists())
        self.assertEqual((self.ui / "game" / "scoreboard.big").read_bytes(), b"plain")

    def test_missing_pack_restores_the_original_crest(self) -> None:
        self.assign("WorldCup")
        self.runtime.apply_scoreboard_runtime()
        self.assign("Gone")
        self.runtime.apply_scoreboard_runtime()
        self.assertEqual((self.ui / CREST).read_bytes(), b"original crest")

    def test_module_off_restores_the_original_crest(self) -> None:
        self.assign("WorldCup")
        self.runtime.apply_scoreboard_runtime()
        self.app.enabled.discard("ScoreBoard")
        self.runtime.apply_scoreboard_runtime()
        self.assertEqual((self.ui / CREST).read_bytes(), b"original crest")
        self.assertFalse((self.ui / CREST64).exists())

    def test_archive_pack_crests_are_tracked_too(self) -> None:
        archive = self.app.ScoreBoard / "Euro.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("Euro/game/scoreboard.big", b"euro")
            zf.writestr(f"Euro/{CREST.as_posix()}", b"euro crest from zip")
        self.assign("Euro")
        self.runtime.apply_scoreboard_runtime()
        self.assertEqual((self.ui / CREST).read_bytes(), b"euro crest from zip")
        self.unassign()
        self.runtime.apply_scoreboard_runtime()
        self.assertEqual((self.ui / CREST).read_bytes(), b"original crest")

    def test_defaults_folder_replaces_a_polluted_crest(self) -> None:
        # data/ui already holds a special crest left by an older CGFS copy:
        # the backup alone would keep it, ScoreBoardDefaults fixes it.
        self.write(self.ui / CREST, b"stale special crest")
        self.write(self.app.exedir / "FSW" / "ScoreBoardDefaults" / CREST, b"normal crest")
        self.runtime.apply_scoreboard_runtime()
        self.assertEqual((self.ui / CREST).read_bytes(), b"normal crest")

    def test_defaults_folder_does_not_override_the_current_pack(self) -> None:
        self.write(self.app.exedir / "FSW" / "ScoreBoardDefaults" / CREST, b"normal crest")
        self.assign("WorldCup")
        self.runtime.apply_scoreboard_runtime()
        self.assertEqual((self.ui / CREST).read_bytes(), b"world cup crest, longer")
        self.unassign()
        self.runtime.apply_scoreboard_runtime()
        self.assertEqual((self.ui / CREST).read_bytes(), b"normal crest")

    def test_select_team_restores_the_original_crest(self) -> None:
        self.write(self.app.exedir / "FSW" / "ScoreBoardDefaults" / CREST64, b"normal 64")
        self.assign("WorldCup")
        self.runtime.apply_scoreboard_runtime()
        self.runtime.restore_scoreboard_ui_after_match("game/screens/playNow/SelectTeam")
        self.assertEqual((self.ui / CREST).read_bytes(), b"original crest")
        self.assertEqual((self.ui / CREST64).read_bytes(), b"normal 64")
        self.assertEqual((self.ui / "game" / "scoreboard.big").read_bytes(), b"wc")
        self.assertTrue(any("left the match" in line for line in self.app.logs))

    def test_select_team_with_the_module_off_only_undoes_cgfs_files(self) -> None:
        self.write(self.app.exedir / "FSW" / "ScoreBoardDefaults" / CREST64, b"normal 64")
        self.assign("WorldCup")
        self.runtime.apply_scoreboard_runtime()
        self.app.enabled.discard("ScoreBoard")
        self.runtime.restore_scoreboard_ui_after_match("game/screens/playNow/SelectTeam")
        self.assertEqual((self.ui / CREST).read_bytes(), b"original crest")
        self.assertFalse((self.ui / CREST64).exists())

    def test_defaults_folder_is_not_applied_with_the_module_off(self) -> None:
        self.write(self.app.exedir / "FSW" / "ScoreBoardDefaults" / CREST, b"normal crest")
        self.app.enabled.discard("ScoreBoard")
        self.runtime.apply_scoreboard_runtime()
        self.assertEqual((self.ui / CREST).read_bytes(), b"original crest")


if __name__ == "__main__":
    unittest.main()
