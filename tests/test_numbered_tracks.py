from __future__ import annotations

import random
import tempfile
import unittest
import unittest.mock
from pathlib import Path

from server16_py.chants_runtime import ChantsRuntime, numbered_tracks, pick_numbered_track


class FakeIni:
    def __init__(self, values: dict[tuple[str, str], str]) -> None:
        self.values = values

    def key_exists(self, key: str, section: str) -> bool:
        return (key, section) in self.values

    def read(self, key: str, section: str) -> str:
        return self.values.get((key, section), "")


class FakeApp:
    """Enough of Server16App for ChantsRuntime._play_club_song."""

    def __init__(self, root: Path) -> None:
        self.exedir = root
        self.settings_ini = FakeIni({("1", "chantsid"): "Arsenal,0.1,0.1,0.1,0.1,0.1,0.3"})
        self._chants_rng = random.Random(7)
        self._chants_player = None
        self._chants_target_volume = 0.0
        self.displays: dict[str, str] = {}
        self.logs: list[str] = []

    def _set_display_async(self, key: str, value: str) -> None:
        self.displays[key] = value

    def log(self, message: str, *_args, **_kwargs) -> None:
        self.logs.append(message)


class NumberedTracksTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.folder = Path(self._tmp.name)

    def touch(self, *names: str) -> None:
        for name in names:
            (self.folder / name).write_bytes(b"test")

    def names(self, base_name: str) -> list[str]:
        return [path.name for path in numbered_tracks(self.folder, base_name)]

    def test_name_plus_optional_number_in_any_case(self) -> None:
        self.touch("ClubSong.mp3", "ClubSong2.mp3", "clubsong03.MP3", "ClubSong10.mp3")
        self.assertEqual(self.names("ClubSong"), ["ClubSong.mp3", "clubsong03.MP3", "ClubSong10.mp3", "ClubSong2.mp3"])

    def test_anything_else_starting_with_the_name_is_not_a_variant(self) -> None:
        self.touch(
            "ClubSong.mp3", "ClubSong_old.mp3", "ClubSong - copy.mp3", "ClubSong2b.mp3",
            "ClubSong.original.mp3", "ClubSong2.wav", "MyClubSong.mp3", "Entrance.mp3",
        )
        (self.folder / "ClubSong3.mp3").mkdir()
        self.assertEqual(self.names("ClubSong"), ["ClubSong.mp3"])

    def test_subfolders_are_not_searched(self) -> None:
        (self.folder / "Support").mkdir()
        (self.folder / "Support" / "ClubSong.mp3").write_bytes(b"test")
        self.assertEqual(self.names("ClubSong"), [])

    def test_missing_folder_has_no_tracks(self) -> None:
        self.assertEqual(numbered_tracks(self.folder / "nope", "ClubSong"), [])
        self.assertIsNone(pick_numbered_track(self.folder / "nope", "ClubSong", random.Random()))

    def test_a_single_track_is_always_picked(self) -> None:
        self.touch("Entrance.mp3")
        for _ in range(5):
            self.assertEqual(pick_numbered_track(self.folder, "Entrance", random.Random()), self.folder / "Entrance.mp3")

    def test_the_pick_is_plainly_random_so_a_track_can_repeat(self) -> None:
        self.touch("ClubSong.mp3", "ClubSong2.mp3", "ClubSong3.mp3")
        rng = random.Random(3)
        picks = [pick_numbered_track(self.folder, "ClubSong", rng).name for _ in range(60)]
        self.assertEqual(set(picks), {"ClubSong.mp3", "ClubSong2.mp3", "ClubSong3.mp3"})
        self.assertTrue(any(first == second for first, second in zip(picks, picks[1:])))


class ClubSongVariantTests(unittest.TestCase):
    """ChantsRuntime._play_club_song: ClubSong.mp3, ClubSong2.mp3... one at
    random per goal."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.app = FakeApp(Path(self._tmp.name))
        self.folder = self.app.exedir / "FSW" / "Chants" / "Arsenal"
        self.folder.mkdir(parents=True)
        self.chants = ChantsRuntime(self.app)
        self.chants._special_audio_locked = lambda: False
        self.chants._play_goal_track = unittest.mock.Mock(return_value=True)

    def touch(self, *names: str) -> None:
        for name in names:
            (self.folder / name).write_bytes(b"test")

    def played(self) -> list[str]:
        return [call.args[0].name for call in self.chants._play_goal_track.call_args_list]

    def test_a_lone_clubsong_plays_as_before(self) -> None:
        self.touch("ClubSong.mp3")
        for _ in range(3):
            self.assertTrue(self.chants._play_club_song("1"))
        self.assertEqual(self.played(), ["ClubSong.mp3"] * 3)
        self.assertEqual(self.chants._play_goal_track.call_args.args[1], 0.3)

    def test_each_goal_draws_from_every_variant_and_may_repeat(self) -> None:
        self.touch("ClubSong.mp3", "ClubSong2.mp3", "ClubSong3.mp3", "ClubSong_old.mp3")
        for _ in range(40):
            self.assertTrue(self.chants._play_club_song("1"))
        played = self.played()
        self.assertEqual(set(played), {"ClubSong.mp3", "ClubSong2.mp3", "ClubSong3.mp3"})
        self.assertTrue(any(first == second for first, second in zip(played, played[1:])))

    def test_the_status_panel_names_the_variant_that_played(self) -> None:
        self.touch("ClubSong2.mp3")
        self.chants._play_club_song("1")
        self.assertEqual(self.chants._play_goal_track.call_args.args[2], "ClubSong2")
        self.assertEqual(self.app.displays["audio_current"], "ClubSong2")

    def test_no_variant_skips_the_song_and_says_so(self) -> None:
        self.touch("ClubSong_old.mp3")
        self.assertFalse(self.chants._play_club_song("1"))
        self.chants._play_goal_track.assert_not_called()
        self.assertTrue(any("Goal club song skipped for 1: missing" in line for line in self.app.logs))


if __name__ == "__main__":
    unittest.main()
