from __future__ import annotations

import tempfile
import tkinter as tk
import unittest
from pathlib import Path

from server16_py.competition_db import FCE_DIR, find_language_db, load_competitions, parse_compobj
from server16_py.competition_picker_dialog import CompetitionPickerDialog

# id,type,code,nameKey,parentId -- types: 1 confederation, 2 nation, 3 competition, 4 stage
COMPOBJ = "\n".join([
    "1,0,ROOT,FCE_Root,0",
    "2,1,UEFA,FCE_UEFA,1",
    "3,2,ENG,Nation_14,2",
    "4,3,C13,FCE_Premier_League,3",
    "5,4,R1,FCE_Round_of_16,4",
    "6,4,R2,FCE_Final,4",
    "7,3,C99,FCE_Friendlies,1",
    "8,4,R3,FCE_Group_Stage,7",
    "garbage line",
    "x,y,z,w,v",
    "",
])


def _write_compobj(exedir: Path, text: str = COMPOBJ) -> Path:
    path = exedir.joinpath(*FCE_DIR, "data", "compdata", "compobj.txt")
    path.parent.mkdir(parents=True)
    path.write_text(text, encoding="utf-8")
    return path


class ParseCompobjTests(unittest.TestCase):
    def test_competitions_stages_and_ancestors(self) -> None:
        data = parse_compobj(COMPOBJ)
        by_tour = {comp.tour_id: comp for comp in data.competitions}
        self.assertEqual(set(by_tour), {4, 7})

        premier = by_tour[4]
        self.assertEqual((premier.code, premier.gfx), ("C13", 13))
        self.assertEqual((premier.nation_id, premier.conf_id), (3, 2))
        self.assertEqual([stage.round_id for stage in premier.stages], [5, 6])
        self.assertEqual([stage.label for stage in premier.stages], ["R1 · Round of 16", "R2 · Final"])

        # Directly under the root: no nation, no confederation.
        friendlies = by_tour[7]
        self.assertEqual((friendlies.nation_id, friendlies.conf_id), (None, None))
        self.assertEqual([stage.round_id for stage in friendlies.stages], [8])

    def test_nation_number_comes_from_the_name_key(self) -> None:
        data = parse_compobj(COMPOBJ)
        self.assertEqual([nation.number for nation in data.nations], ["14"])
        self.assertEqual(data.nation_label(data.nations[0]), "ENG")
        data.apply_names({"13": "Premier League"}, {"14": "England"})
        self.assertEqual(data.nation_label(data.nations[0]), "England")
        self.assertEqual(data.competition_label(data.competitions[0]), "Premier League")

    def test_name_key_with_commas_is_kept_whole(self) -> None:
        data = parse_compobj("1,0,ROOT,Root,0\n2,3,C5,Cup, The Big One,1\n")
        self.assertEqual(data.competitions[0].name_key, "Cup, The Big One")


class LoadCompetitionsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.exedir = Path(self._tmp.name)

    def test_loose_file_is_read(self) -> None:
        _write_compobj(self.exedir)
        result = load_competitions(self.exedir)
        self.assertTrue(result.ok)
        self.assertEqual(len(result.data.competitions), 2)

    def test_missing_file(self) -> None:
        result = load_competitions(self.exedir)
        self.assertEqual((result.ok, result.reason), (False, "missing"))

    def test_vanilla_install_reports_packed(self) -> None:
        dll = self.exedir.joinpath(*FCE_DIR, "FootballCompEngzf.dll")
        dll.parent.mkdir(parents=True)
        dll.write_bytes(b"MZ")
        self.assertEqual(load_competitions(self.exedir).reason, "packed")

    def test_file_without_competitions_is_invalid(self) -> None:
        _write_compobj(self.exedir, "1,0,ROOT,FCE_Root,0\n")
        self.assertEqual(load_competitions(self.exedir).reason, "invalid")

    def test_language_db_prefers_english_and_skips_patch_and_copy_files(self) -> None:
        loc = self.exedir / "data" / "loc"
        loc.mkdir(parents=True)
        for name in ("spa_es", "eng_us", "_1_eng_us", "eng_us_upd", "fra_fr"):
            (loc / f"{name}.db").write_bytes(b"")
        for name in ("spa_es", "eng_us", "_1_eng_us", "eng_us_upd"):  # fra_fr has no meta xml
            (loc / f"{name}-meta.xml").write_text("<x/>")
        self.assertEqual(find_language_db(self.exedir), (loc / "eng_us.db", loc / "eng_us-meta.xml"))
        self.assertIsNone(find_language_db(self.exedir / "nowhere"))


def _tk_available() -> bool:
    try:
        root = tk.Tk()
        root.destroy()
        return True
    except tk.TclError:
        return False


@unittest.skipUnless(_tk_available(), "requires a Tk display")
class CompetitionPickerDialogTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.exedir = Path(self._tmp.name)
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        for name, value in dict(
            bg="#000000", panel="#333333", panel_alt="#444444", card="#111111", card_soft="#222222",
            fg="#ffffff", muted="#888888", accent="#00ff00", gold="#ffff00",
        ).items():
            setattr(self.root, name, value)
        self.root.tr = lambda key, **kwargs: f"{key} {kwargs}" if kwargs else key

    def make(self, **kwargs) -> CompetitionPickerDialog:
        dialog = CompetitionPickerDialog(self.root, self.exedir, name_loader=None, **kwargs)
        self.addCleanup(lambda: dialog.winfo_exists() and dialog.destroy())
        return dialog

    def select(self, dialog: CompetitionPickerDialog, iid: str) -> None:
        dialog.tree.selection_set(iid)
        dialog.update()  # <<TreeviewSelect>> is a queued virtual event

    def test_stage_row_gives_the_round_id(self) -> None:
        _write_compobj(self.exedir)
        dialog = self.make()
        self.select(dialog, "round:5")
        dialog._confirm()
        self.assertEqual(dialog.result, "5")

    def test_competition_row_gives_the_tournament_id(self) -> None:
        _write_compobj(self.exedir)
        dialog = self.make()
        self.select(dialog, "tour:4")
        dialog._confirm()
        self.assertEqual(dialog.result, "4")

    def test_round_only_section_cannot_pick_a_competition(self) -> None:
        _write_compobj(self.exedir)
        dialog = self.make(allow_tournament=False)
        self.select(dialog, "tour:4")
        self.assertEqual(str(dialog.select_button.cget("state")), "disabled")
        dialog._confirm()
        self.assertIsNone(dialog.result)
        self.select(dialog, "round:5")
        self.assertEqual(str(dialog.select_button.cget("state")), "normal")

    def test_tournament_only_section_cannot_pick_a_stage(self) -> None:
        _write_compobj(self.exedir)
        dialog = self.make(allow_round=False)
        self.select(dialog, "round:5")
        dialog._confirm()
        self.assertIsNone(dialog.result)

    def test_country_and_confederation_filters(self) -> None:
        _write_compobj(self.exedir)
        dialog = self.make()
        self.assertEqual(set(dialog.tree.get_children()), {"tour:4", "tour:7"})

        dialog.nation_combo.current(dialog._nation_ids.index("-"))
        dialog._refresh_tree()
        self.assertEqual(set(dialog.tree.get_children()), {"tour:7"})

        dialog.nation_combo.current(dialog._nation_ids.index(3))
        dialog._refresh_tree()
        self.assertEqual(set(dialog.tree.get_children()), {"tour:4"})

    def test_search_by_stage_expands_only_the_matching_stage(self) -> None:
        _write_compobj(self.exedir)
        dialog = self.make()
        dialog.search_var.set("round of")
        dialog._refresh_tree()
        self.assertEqual(set(dialog.tree.get_children()), {"tour:4"})
        self.assertEqual(dialog.tree.get_children("tour:4"), ("round:5",))
        # A competition match keeps all of its stages.
        dialog.search_var.set("c13")
        dialog._refresh_tree()
        self.assertEqual(dialog.tree.get_children("tour:4"), ("round:5", "round:6"))

    def test_names_arrive_from_the_worker_thread_and_relabel_the_tree(self) -> None:
        _write_compobj(self.exedir)
        dialog = CompetitionPickerDialog(
            self.root, self.exedir, name_loader=lambda _exedir, _data: ({"13": "Premier League"}, {"14": "England"}),
        )
        self.addCleanup(lambda: dialog.winfo_exists() and dialog.destroy())
        for _ in range(100):
            dialog.update()
            if not dialog._names_loading:
                break
            dialog.after(20)
        self.assertFalse(dialog._names_loading)
        self.assertIn("Premier League", dialog.tree.item("tour:4", "text"))

    def test_failing_name_loader_keeps_the_code_labels(self) -> None:
        _write_compobj(self.exedir)

        def boom(_exedir, _data):
            raise RuntimeError("no bridge")

        dialog = CompetitionPickerDialog(self.root, self.exedir, name_loader=boom)
        self.addCleanup(lambda: dialog.winfo_exists() and dialog.destroy())
        for _ in range(100):
            dialog.update()
            if not dialog._names_loading:
                break
            dialog.after(20)
        self.assertFalse(dialog._names_loading)
        self.assertIn("C13", dialog.tree.item("tour:4", "text"))

    def test_missing_compobj_shows_the_reason_and_picks_nothing(self) -> None:
        dialog = self.make()
        self.assertIn("unavailable_missing", dialog.status_label.cget("text"))
        self.assertEqual(dialog.tree.get_children(), ())
        dialog._confirm()
        self.assertIsNone(dialog.result)


if __name__ == "__main__":
    unittest.main()
