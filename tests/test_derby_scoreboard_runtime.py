from __future__ import annotations

import tempfile
import unittest
import unittest.mock
from pathlib import Path

from server16_py.asset_runtime import AssetRuntime
from server16_py.ini_file import SessionIniFile


class FakeScoreboardApp:
    """Enough of Server16App for AssetRuntime.apply_scoreboard_runtime to run
    against a real on-disk install (ScoreBoardGBD/TVLogoGBD packs, the game's
    data folders) and the real SessionIniFile."""

    def __init__(self, base: Path) -> None:
        self.exedir = base
        self.ScoreBoard = base / "ScoreBoardGBD"
        self.TVLogo = base / "TVLogoGBD"
        self.Scoredata = base / "data" / "ui"
        self.TVdata = base / "data" / "ui" / "game" / "overlays"
        (base / "FSW").mkdir(parents=True)
        self.settings_ini = SessionIniFile(base / "FSW" / "settings.ini")
        self.HID = "241"
        self.AID = "243"
        self.derby = "241vs243"
        self.TOURNAME = ""
        self.TOURROUNDID = ""
        self.display: dict[str, str] = {}
        self.logs: list[str] = []

    def module_enabled(self, name: str) -> bool:
        return name in {"ScoreBoard", "TvLogo"}

    def _set_display(self, key: str, value: str) -> None:
        self.display[key] = value

    def display_value(self, key: str, **_kwargs) -> str:
        return key

    def tr(self, key: str) -> str:
        return key

    def log(self, *parts) -> None:
        self.logs.append(" ".join(str(p) for p in parts))


class DerbyScoreboardRuntimeTests(unittest.TestCase):
    """[DerbyScoreBoard]/[DerbyTvLogo] are keyed "{home}vs{away}" like the
    movies' [DerbyMatch], and sit in the same place of the lookup order:
    round, tournament, derby, home team, default."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.app = FakeScoreboardApp(Path(self._tmp.name))
        for pack in ("LaLiga", "Barca", "UCL", "Generic"):
            self.write(self.app.ScoreBoard / pack / "game" / "scoreboard.big", pack.encode())
            self.write(self.app.TVLogo / pack / "overlay_9105.big", pack.encode())
        self.runtime = AssetRuntime(self.app)
        self.runtime._show_asset_toast = unittest.mock.Mock()
        self.runtime._show_warning_toast = unittest.mock.Mock()
        self.runtime.update_audio_overview = unittest.mock.Mock()

    def write(self, path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def assign(self, section: str, key: str, value: str) -> None:
        self.app.settings_ini.write(key, value, section)
        self.app.settings_ini.save()

    def installed_scoreboard(self) -> bytes:
        return (self.app.Scoredata / "game" / "scoreboard.big").read_bytes()

    def installed_tvlogo(self) -> bytes:
        return (self.app.TVdata / "overlay_9105.big").read_bytes()

    def test_derby_scoreboard_is_applied_for_that_matchup(self) -> None:
        self.assign("DerbyScoreBoard", "241vs243", "LaLiga")
        self.runtime.apply_scoreboard_runtime()
        self.assertEqual(self.installed_scoreboard(), b"LaLiga")
        self.assertEqual(self.app.display["scoreboard"], "LaLiga")
        self.assertEqual(self.app._scoreboard_assignment_type, "Derby")

    def test_derby_beats_the_home_team_and_the_default(self) -> None:
        self.assign("HomeTeamScoreBoard", "241", "Barca")
        self.assign("Scoreboard", "0", "Generic")
        self.assign("DerbyScoreBoard", "241vs243", "LaLiga")
        self.runtime.apply_scoreboard_runtime()
        self.assertEqual(self.installed_scoreboard(), b"LaLiga")
        self.assertEqual(self.app._scoreboard_assignment_type, "Derby")

    def test_round_and_tournament_beat_the_derby(self) -> None:
        self.assign("DerbyScoreBoard", "241vs243", "LaLiga")
        self.assign("Scoreboard", "223", "UCL")
        self.app.TOURNAME = "223"
        self.runtime.apply_scoreboard_runtime()
        self.assertEqual(self.installed_scoreboard(), b"UCL")
        self.assertEqual(self.app._scoreboard_assignment_type, "Tournament")

    def test_the_reverse_fixture_is_a_different_derby(self) -> None:
        self.assign("DerbyScoreBoard", "243vs241", "LaLiga")
        self.assign("HomeTeamScoreBoard", "241", "Barca")
        self.runtime.apply_scoreboard_runtime()
        self.assertEqual(self.installed_scoreboard(), b"Barca")
        self.assertEqual(self.app._scoreboard_assignment_type, "Home Team")

    def test_another_opponent_falls_through_to_the_home_team(self) -> None:
        self.assign("DerbyScoreBoard", "241vs243", "LaLiga")
        self.assign("HomeTeamScoreBoard", "241", "Barca")
        self.app.AID = "240"
        self.app.derby = "241vs240"
        self.runtime.apply_scoreboard_runtime()
        self.assertEqual(self.installed_scoreboard(), b"Barca")

    def test_derby_tvlogo_is_resolved_the_same_way(self) -> None:
        self.assign("HomeTeamTvLogo", "241", "Barca")
        self.assign("DerbyTvLogo", "241vs243", "LaLiga")
        self.runtime.apply_scoreboard_runtime()
        self.assertEqual(self.installed_tvlogo(), b"LaLiga")
        self.assertEqual(self.app.display["tvlogo"], "LaLiga")
        self.assertEqual(self.app._tvlogo_assignment_type, "Derby")

    def test_tournament_tvlogo_beats_the_derby_tvlogo(self) -> None:
        self.assign("DerbyTvLogo", "241vs243", "LaLiga")
        self.assign("TVLogo", "223", "UCL")
        self.app.TOURNAME = "223"
        self.runtime.apply_scoreboard_runtime()
        self.assertEqual(self.installed_tvlogo(), b"UCL")
        self.assertEqual(self.app._tvlogo_assignment_type, "Tournament")


if __name__ == "__main__":
    unittest.main()
