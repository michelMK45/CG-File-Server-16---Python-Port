from __future__ import annotations

import queue
import tempfile
import unittest
import unittest.mock
from pathlib import Path

from server16_py import ingame_datafile, ingame_menu_runtime
from server16_py.ingame_menu_runtime import DEFAULT_LABEL, NOT_YET, InGameMenuRuntime
from server16_py.ini_file import SessionIniFile


class FakeApp:
    """Enough of Server16App for InGameMenuRuntime: a game folder with the menu installed (or not), the
    packs' folders and the real SessionIniFile."""

    def __init__(self, base: Path, installed: bool = True) -> None:
        self.exedir = base
        self.ScoreBoard = base / "ScoreBoardGBD"
        self.TVLogo = base / "TVLogoGBD"
        for folder, packs in ((self.ScoreBoard, ("LaLiga", "Bundesliga", "UCL")), (self.TVLogo, ("ESPN", "DAZN"))):
            for pack in packs:
                (folder / pack).mkdir(parents=True)
        (self.TVLogo / "bad=name").mkdir()  # "=" cannot travel in the data text ("|" is not a valid folder name)
        (base / "FSW").mkdir()
        self.settings_ini = SessionIniFile(base / "FSW" / "settings.ini")
        if installed:
            menu = base / ingame_menu_runtime.MENU_MOVIE
            menu.parent.mkdir(parents=True)
            menu.write_bytes(b"BIG4")
        self._worker_queue: queue.Queue = queue.Queue()
        self.logs: list[str] = []
        self.polls = 0

    def log(self, *parts, **_kwargs) -> None:
        self.logs.append(" ".join(str(p) for p in parts))

    def _schedule_worker_poll(self) -> None:
        self.polls += 1


def read_data(app: FakeApp) -> dict[str, str]:
    """The key=value lines of the data.big the runtime wrote."""
    data = (app.exedir / ingame_menu_runtime.DATA_MOVIE).read_bytes()
    _entry, items = ingame_datafile.read_const(dict(ingame_datafile.big_entries(data))["1"])
    text = next(v for t, v in items if t == 1 and v.startswith(b"SOURCE=")).decode("utf-8")
    return dict(line.split("=", 1) for line in text.split("\n"))


class InGameMenuRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.app = FakeApp(Path(self._tmp.name))
        self.rt = InGameMenuRuntime(self.app)

    def test_not_installed_does_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as other:
            app = FakeApp(Path(other), installed=False)
            rt = InGameMenuRuntime(app)
            self.assertFalse(rt.write_data("test"))
            rt.on_page("game/screens/cgfs16/CGFS16Menu", "game/screens/fluxHub/FluxHub", 123)
            self.assertFalse((Path(other) / ingame_menu_runtime.DATA_MOVIE).exists())
            self.assertEqual(app.polls, 0)

    def test_data_carries_the_packs_and_the_default_assignment(self) -> None:
        self.app.settings_ini.write("0", "UCL", "Scoreboard")
        self.app.settings_ini.save()
        self.assertTrue(self.rt.write_data("test"))
        d = read_data(self.app)
        self.assertEqual(d["SCOREBOARD"].split("|"), [DEFAULT_LABEL, "Bundesliga", "LaLiga", "UCL"])
        self.assertEqual(d["SCOREBOARD_SEL"], "3")
        self.assertEqual(d["TVLOGO"].split("|"), [DEFAULT_LABEL, "DAZN", "ESPN"])  # "bad=name" left out
        self.assertEqual(d["TVLOGO_SEL"], "0")
        self.assertEqual(d["STADIUM"], NOT_YET)
        self.assertEqual(d["ACK"], "0")
        self.assertFalse(self.rt.write_data("again"))            # nothing changed
        self.assertTrue(self.rt.write_data("again", force=True))

    def test_leaving_the_menu_scans_in_a_worker_and_applies_the_save(self) -> None:
        record = (1, (("SCOREBOARD", (1, "Bundesliga")), ("TVLOGO", (2, "ESPN")), ("STADIUM", (0, NOT_YET))))
        with unittest.mock.patch.object(ingame_menu_runtime.ingame_recordscan, "scan",
                                        return_value=([record], 3700.0, 3.4)) as scan:
            self.rt.on_page("game/screens/fluxHub/FluxHub", ingame_menu_runtime.MENU_PAGE, 77)
            self.rt.on_page(ingame_menu_runtime.MENU_PAGE, "game/screens/fluxHub/FluxHub", 77)
            event = self.app._worker_queue.get(timeout=5)
        self.assertEqual(scan.call_args.args[:3], (77, [], 0))
        self.assertTrue(self.rt.busy)
        self.assertEqual(event[0], "ingame_menu_scan")
        self.rt.on_scan_done(*event[1:])
        self.assertFalse(self.rt.busy)
        self.assertEqual(self.app.settings_ini.read("0", "Scoreboard"), "Bundesliga")
        self.assertEqual(self.app.settings_ini.read("0", "TVLogo"), "ESPN")
        self.assertEqual(self.rt.last_seq, 1)
        d = read_data(self.app)                                   # written again for the menu, with the ack
        self.assertEqual((d["ACK"], d["SCOREBOARD_SEL"], d["TVLOGO_SEL"]), ("1", "1", "2"))

    def test_same_or_older_save_is_not_applied_again(self) -> None:
        self.rt.attached(5)
        self.rt.last_seq = 3
        self.rt.on_scan_done(5, [(3, (("TVLOGO", (1, "DAZN")),))], [], 1.0, 0.1, None)
        self.assertEqual(self.app.settings_ini.read("0", "TVLogo"), "")
        self.assertIn("without a new save", self.app.logs[-1])
        self.rt.on_scan_done(6, [(4, (("TVLOGO", (1, "DAZN")),))], [], 1.0, 0.1, None)  # another FIFA
        self.assertEqual(self.app.settings_ini.read("0", "TVLogo"), "")

    def test_default_resets_and_texts_win_over_moved_indices(self) -> None:
        ini = self.app.settings_ini
        ini.write("0", "LaLiga", "Scoreboard")
        ini.write("0", "DAZN", "TVLogo")
        ini.save()
        # the scoreboard back to default (index 0), the TV logo by text (its index is stale)
        self.rt.apply({"SCOREBOARD": (0, DEFAULT_LABEL), "TVLOGO": (1, "ESPN"), "KITS": (0, NOT_YET)})
        reloaded = SessionIniFile(self.app.exedir / "FSW" / "settings.ini")
        self.assertFalse(reloaded.key_exists("0", "Scoreboard"))
        self.assertEqual(reloaded.read("0", "TVLogo"), "ESPN")
        self.rt.apply({"TVLOGO": (9, "Gone")})                    # not a pack any more: ignored
        self.assertEqual(SessionIniFile(self.app.exedir / "FSW" / "settings.ini").read("0", "TVLogo"), "ESPN")

    def test_new_fifa_session_resets_the_sequence(self) -> None:
        self.rt.attached(10)
        self.rt.last_seq, self.rt.hot = 4, [(1, 2)]
        self.rt.attached(10)
        self.assertEqual(self.rt.last_seq, 4)
        self.rt.attached(11)
        self.assertEqual((self.rt.last_seq, self.rt.hot), (0, []))

    def test_scan_error_is_logged(self) -> None:
        self.rt.busy = True
        self.rt.on_scan_done(1, [], [], 0.0, 0.0, "OpenProcess failed (5)")
        self.assertFalse(self.rt.busy)
        self.assertIn("scan failed", self.app.logs[-1])


if __name__ == "__main__":
    unittest.main()
