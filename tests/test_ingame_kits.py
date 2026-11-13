from __future__ import annotations

import tempfile
import unittest
import unittest.mock
from pathlib import Path

from server16_py import ingame_images, ingame_kits, ingame_menu_texts
from server16_py import kit_classic as kc
from server16_py.ingame_menu_runtime import MENU_PAGE, NO_MATCH, InGameMenuRuntime
from tests.test_ingame_menu_runtime import FakeApp, read_data

SUPPORTED_PLAYER_LUA = "\n".join(f"function {name}(a,b,c)\nend" for name in kc.REQUIRED_PLAYER_LUA_FUNCTIONS) + "\n"


def spa(key: str, **fields) -> str:
    return ingame_menu_texts.render(ingame_menu_texts.token(key, **fields), "spa")


class KitsFixture(unittest.TestCase):
    """The in-game menu runtime on a game folder with Rev Mod V1.3.5's player.lua, loose kits 0, 1, 3 for teams
    241 and 73, and team 241 saved with two combinations ("A" mixes kit 0; the second has a "|" in its name)."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        base = Path(self._tmp.name)
        self.app = FakeApp(base)
        self.app.base_dir = base
        self.app.kit_classic = self.runtime = kc.KitClassicRuntime(self.app)
        self.runtime.team_lua_dir().mkdir(parents=True)
        self.install_player_lua()
        kit_dir = self.runtime.kit_dir()
        kit_dir.mkdir(parents=True)
        for team in (241, 73):
            for ktype in (0, 1, 3):
                (kit_dir / f"kit_{team}_{ktype}_0.rx3").write_bytes(b"x")
        self.runtime.kits(refresh=True)
        self.runtime.save(kc.TeamCombinations(241, [kc.Combination("A", [kc.Mix(0, 0, 0, 1, 0)]),
                                                    kc.Combination("Combinación|2")], home=1))
        self.rt = InGameMenuRuntime(self.app)
        self.rt._images_started = True                     # no stadium preview thread
        self.started: list[int] = []
        self.rt.kits.start_pictures = lambda: self.started.append(1)   # no kit picture thread (Task 4 tests it)

    def install_player_lua(self, text: str = SUPPORTED_PLAYER_LUA) -> None:
        path = self.runtime.player_lua_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


class InGameKitsDataTests(KitsFixture):
    def test_no_match_is_one_value(self) -> None:
        self.rt.write_data("test")
        d = read_data(self.app)
        self.assertEqual(d["KITS"], NO_MATCH)
        self.assertNotIn("KITSAWAY", d)
        self.assertNotIn("ROWS_KITS", d)

    def test_unsupported_player_lua(self) -> None:
        self.install_player_lua("function swapTeamKit(team,type1,type2)\nend\n")
        self.app.HID, self.app.AID = "241", "73"
        self.rt.write_data("test")
        d = read_data(self.app)
        self.assertEqual(d["KITS"], spa("kits_unsupported"))
        self.assertEqual(d["KITSAWAY"], spa("kits_unsupported"))

    def test_rows_values_and_selection(self) -> None:
        self.app.HID, self.app.AID = "241", "73"
        self.rt.write_data("test")
        d = read_data(self.app)
        self.assertEqual(d["ROWS_KITS"], "KITS|KITSAWAY")
        self.assertEqual(d["TITLE_KITS"], "Local · FC Barcelona")
        self.assertEqual(d["TITLE_KITSAWAY"], "Visitante · 73")
        self.assertEqual(d["KITS"].split("|"), ["Equipaciones originales", "A", "Combinación/2"])
        self.assertEqual(d["KITS_SEL"], "2")
        self.assertEqual(d["KITSAWAY"], "Equipaciones originales")
        self.assertEqual(d["KITSAWAY_SEL"], "0")
        self.assertEqual(d["DESC_KITS"], spa("kits_desc"))
        self.assertEqual(d["DESC_KITSAWAY"], spa("kits_none"))

    def test_team_plays_itself(self) -> None:
        tc = self.runtime.load(241)
        tc.away = 0
        self.runtime.save(tc)
        self.app.HID = self.app.AID = "241"
        self.rt.write_data("test")
        d = read_data(self.app)
        self.assertEqual((d["KITS_SEL"], d["KITSAWAY_SEL"]), ("2", "1"))
        self.assertEqual(d["KITSAWAY"], d["KITS"])

    def test_pictures_paths(self) -> None:
        self.app.HID, self.app.AID = "241", "73"
        self.rt.write_data("test")
        self.assertEqual(read_data(self.app)["IMG_KITS"], "||")      # neither pictures nor placeholder yet
        self.assertEqual(self.started, [1])                          # so the worker is started
        placeholder = self.app.exedir / "data" / "ui" / ingame_kits.PLACEHOLDER_REL
        placeholder.parent.mkdir(parents=True, exist_ok=True)
        placeholder.write_bytes(b"DDS ")
        sources = self.runtime.kit_sources(241, 0, 0, 1, 0)          # "A": its mix of kit 0
        png = self.runtime.art.drawing_path(*sources, size=ingame_kits.ART_SIZE)
        self.assertIsNotNone(png)
        rel = ingame_images.asset_image_rel("kit", png.name)
        target = self.app.exedir / "data" / "ui" / rel
        target.write_bytes(b"DDS ")
        self.rt.write_data("again", force=True)
        images = read_data(self.app)["IMG_KITS"].split("|")
        self.assertEqual(images, [ingame_kits.PLACEHOLDER_REL, rel, ingame_kits.PLACEHOLDER_REL])


def dds_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    return int.from_bytes(data[16:20], "little"), int.from_bytes(data[12:16], "little")   # width, height


class InGameKitsPictureTests(KitsFixture):
    def setUp(self) -> None:
        super().setUp()
        self.app.HID, self.app.AID = "241", "73"
        self.rt.write_data("test")

    def picture_files(self) -> list[Path]:
        folder = self.app.exedir / "data" / "ui" / "cgfs16" / "img" / "kit"
        return sorted(p for p in folder.glob("*.dds") if p.name != "placeholder.dds") if folder.exists() else []

    def test_make_pictures_creates_dds_once(self) -> None:
        jobs = self.rt.kits.jobs()
        self.assertEqual(len(jobs), 3)        # 241: original kits (= the empty combination), "A"; 73: original
        self.assertEqual(self.rt.kits.make_pictures(jobs), 4)   # + the placeholder
        files = self.picture_files()
        self.assertEqual(len(files), 3)
        self.assertEqual({dds_size(p) for p in files}, {ingame_images.SIZE})
        self.assertTrue((self.app.exedir / "data" / "ui" / ingame_kits.PLACEHOLDER_REL).exists())
        self.assertEqual(self.rt.kits.make_pictures(jobs), 0)

    def test_render_failure_keeps_going(self) -> None:
        real = self.runtime.art.render_path
        calls = []

        def render(*args, **kwargs):
            calls.append(args)
            if len(calls) == 1:
                raise ValueError("bad texture")
            return real(*args, **kwargs)

        with unittest.mock.patch.object(self.runtime.art, "render_path", side_effect=render):
            self.rt.kits.make_pictures(self.rt.kits.jobs())
        self.assertEqual(len(self.picture_files()), 2)

    def test_worker_starts_only_when_pictures_are_missing(self) -> None:
        self.assertEqual(self.started, [1])
        self.rt.kits.make_pictures(self.rt.kits.jobs())
        self.rt.write_data("again", force=True)
        self.assertEqual(self.started, [1])              # all there: no worker
        for path in self.picture_files():
            path.unlink()
        self.rt.kits.pictures_busy = True
        self.rt.write_data("again", force=True)
        self.assertEqual(self.started, [1])              # one is already running

    def test_worker_posts_its_result(self) -> None:
        ingame_kits.InGameKits.start_pictures(self.rt.kits)
        self.assertTrue(self.rt.kits.pictures_busy)
        event = self.app._worker_queue.get(timeout=30)
        self.assertEqual(event, ("ingame_menu_kit_images", 4, None, []))
        self.assertGreaterEqual(self.app.polls, 1)
        self.rt.kits.on_pictures_done(*event[1:])
        self.assertFalse(self.rt.kits.pictures_busy)
        self.assertTrue(any("data.big written (kit previews)" in line for line in self.app.logs))
        images = read_data(self.app)["IMG_KITS"].split("|")
        self.assertTrue(all(rel.startswith("cgfs16/img/kit/") and rel != ingame_kits.PLACEHOLDER_REL
                            for rel in images), images)

    def test_failed_worker_is_logged_and_writes_nothing(self) -> None:
        self.rt.kits.pictures_busy = True
        self.rt.kits.on_pictures_done(0, "boom")
        self.assertFalse(self.rt.kits.pictures_busy)
        self.assertTrue(any("boom" in line for line in self.app.logs))
        self.assertFalse(any("data.big written (kit previews)" in line for line in self.app.logs))

    def test_app_poll_keeps_waiting_for_the_kit_pictures(self) -> None:
        """The app's worker-queue poll only re-arms while a worker it knows of is busy: the kit pictures' too."""
        from server16_py.app_settings import SettingsMixin
        self.app.ingame_menu = self.rt
        self.app._stadium_task_running = self.app._kit_cycle_task_running = False
        self.rt.kits.pictures_busy = True
        polls = self.app.polls
        SettingsMixin._poll_worker_queue(self.app)
        self.assertEqual(self.app.polls, polls + 1)
        self.rt.kits.pictures_busy = False
        SettingsMixin._poll_worker_queue(self.app)
        self.assertEqual(self.app.polls, polls + 1)

    def test_app_poll_hands_the_result_over(self) -> None:
        from server16_py.app_settings import SettingsMixin
        self.app.ingame_menu = self.rt
        self.app._stadium_task_running = self.app._kit_cycle_task_running = False
        self.rt.kits.pictures_busy = True
        self.app._worker_queue.put(("ingame_menu_kit_images", 0, None, ["kit preview failed (x): bad"]))
        SettingsMixin._poll_worker_queue(self.app)
        self.assertFalse(self.rt.kits.pictures_busy)
        self.assertTrue(any("kit preview failed (x): bad" in line for line in self.app.logs))

    def test_worker_does_not_log_from_its_thread(self) -> None:
        """app.log touches the Tk log widget: a drawing's failure is reported with the result, on the Tk thread."""
        import threading
        threads = []
        self.app.log = lambda *parts, **_k: threads.append((threading.current_thread().name, " ".join(map(str, parts))))
        with unittest.mock.patch.object(self.runtime.art, "render_path", side_effect=ValueError("bad texture")):
            ingame_kits.InGameKits.start_pictures(self.rt.kits)
            event = self.app._worker_queue.get(timeout=30)
        self.assertNotIn("ingame-menu-kits", [name for name, _text in threads])
        self.assertEqual(event[0], "ingame_menu_kit_images")
        self.assertEqual(len(event[3]), 3)                      # one failure per drawing
        self.rt.kits.on_pictures_done(*event[1:])
        failed = [name for name, text in threads if "kit preview failed" in text]
        self.assertEqual(failed, [threading.current_thread().name] * 3)

    def test_combinations_changed_in_the_app_rewrite_the_data(self) -> None:
        self.app.ingame_menu = self.rt
        tc = self.runtime.load(241)
        tc.items[0].name = "Nueva"
        self.runtime.save(tc)
        self.assertEqual(read_data(self.app)["KITS"].split("|")[1], "Nueva")


ORIGINAL = "Equipaciones originales"


class InGameKitsSaveTests(KitsFixture):
    def setUp(self) -> None:
        super().setUp()
        self.runtime.save(kc.TeamCombinations(73, [kc.Combination("X", [kc.Mix(0, 1, 1, 0, 1)])], away=0))
        self.app.kit_classic_view = unittest.mock.Mock()
        self.app.HID, self.app.AID = "241", "73"
        self.app.ingame_menu = self.rt          # as the app: every KitClassicRuntime.save rewrites the data
        self.seq = 0

    def leave_menu(self, *fields) -> None:
        """The menu's record of a BACK, read back from FIFA (the data written first, as when the menu opened)."""
        self.seq += 1
        self.rt.on_scan_done(5, [(self.seq, tuple(fields))], [], 1.0, 0.1, None)

    def open_menu(self) -> None:
        self.rt.write_data("test", force=True)
        self.rt.on_page("game/screens/playNow/KickOffHub", MENU_PAGE, 5)   # FIFA reads data.big now

    def test_both_sides_saved(self) -> None:
        self.open_menu()
        self.leave_menu(("KITS", (1, "A")), ("KITSAWAY", (0, ORIGINAL)))
        self.assertEqual(self.runtime.load(241).home, 0)
        self.assertIsNone(self.runtime.load(73).selection_valid(self.runtime.load(73).away))
        self.assertIn("In-game menu: team 241 (home) now uses A", self.app.logs)
        self.assertIn(f"In-game menu: team 73 (away) now uses {ORIGINAL}", self.app.logs)
        self.assertEqual(self.app.runtime_applied, 0)          # not settings.ini: nothing to reload
        invalidated = sorted(c.args[0] for c in self.app.kit_classic_view.invalidate.call_args_list)
        self.assertEqual(invalidated, [73, 241])

    def test_unchanged_record_writes_nothing(self) -> None:
        self.open_menu()
        path = self.runtime.team_lua_path(241)
        before = (path.read_bytes(), path.stat().st_mtime_ns)
        with unittest.mock.patch.object(self.runtime, "save", wraps=self.runtime.save) as save:
            self.leave_menu(("KITS", (2, "Combinación/2")), ("KITSAWAY", (1, "X")), ("SCOREBOARD", (1, "Bundesliga")))
        save.assert_not_called()
        self.assertEqual((path.read_bytes(), path.stat().st_mtime_ns), before)
        self.assertFalse(any("now uses" in line for line in self.app.logs))

    def test_list_moved_is_ignored(self) -> None:
        self.open_menu()
        tc = self.runtime.load(241)
        tc.items[0].name = "B"                                   # renamed in the app while the menu was open
        self.runtime.save(tc)
        self.leave_menu(("KITS", (1, "A")))
        self.assertEqual(self.runtime.load(241).home, 1)
        self.assertTrue(any("team 241" in line and "ignored" in line for line in self.app.logs))

    def test_deleted_combination_with_a_repeated_name_is_ignored(self) -> None:
        self.runtime.save(kc.TeamCombinations(241, [kc.Combination("A", [kc.Mix(0, 0, 0, 1, 0)]),
                                                    kc.Combination("A", [kc.Mix(0, 0, 1, 1, 1)])], home=None))
        self.open_menu()                          # shows Original, A, A
        tc = self.runtime.load(241)
        del tc.items[0]                           # the app deletes the first "A" while the menu is open
        self.runtime.save(tc)
        self.leave_menu(("KITS", (1, "A")))      # the user picked the first "A"
        self.assertIsNone(self.runtime.load(241).home)
        self.assertFalse(any("now uses" in line for line in self.app.logs))
        self.assertTrue(any("team 241" in line and "ignored" in line for line in self.app.logs))

    def test_edit_before_the_menu_opens_still_saves(self) -> None:
        tc = self.runtime.load(241)
        tc.items[0].name = "B"
        self.runtime.save(tc)                     # data rewritten before FIFA reads it
        self.open_menu()
        self.leave_menu(("KITS", (1, "B")))
        self.assertEqual(self.runtime.load(241).home, 0)

    def test_no_data_written_halfway_through_a_save(self) -> None:
        self.open_menu()
        self.leave_menu(("KITS", (1, "A")), ("KITSAWAY", (0, ORIGINAL)))
        self.assertFalse(any("(kit combinations)" in line for line in self.app.logs))
        self.assertTrue(any("(after save #1)" in line for line in self.app.logs))

    def test_wrong_text_for_the_index_is_ignored(self) -> None:
        self.open_menu()
        self.leave_menu(("KITS", (1, "Combinación/2")))
        self.assertEqual(self.runtime.load(241).home, 1)
        self.assertTrue(any("ignored" in line for line in self.app.logs))

    def test_context_changed_is_ignored(self) -> None:
        self.open_menu()
        self.app.HID = "100"
        self.leave_menu(("KITS", (1, "A")))
        self.assertEqual(self.runtime.load(241).home, 1)
        self.assertTrue(any("match context changed" in line for line in self.app.logs))

    def test_team_plays_itself_saves_both(self) -> None:
        self.app.AID = "241"
        self.open_menu()
        with unittest.mock.patch.object(self.runtime, "save", wraps=self.runtime.save) as save:
            self.leave_menu(("KITS", (1, "A")), ("KITSAWAY", (2, "Combinación/2")))
        self.assertEqual(save.call_count, 1)
        tc = self.runtime.load(241)
        self.assertEqual((tc.home, tc.away), (0, 1))

    def test_save_error_is_logged(self) -> None:
        self.open_menu()
        with unittest.mock.patch.object(self.runtime, "save", side_effect=RuntimeError("disk full")):
            self.leave_menu(("KITS", (1, "A")))
        self.assertTrue(any("could not save team 241" in line and "disk full" in line for line in self.app.logs))


if __name__ == "__main__":
    unittest.main()
