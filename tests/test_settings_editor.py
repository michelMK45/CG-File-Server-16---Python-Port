from __future__ import annotations

import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from server16_py.ini_file import SessionIniFile
from server16_py.settings_editor import SectionSpec, SettingsSectionFrame


def _tk_available() -> bool:
    try:
        root = tk.Tk()
        root.destroy()
        return True
    except tk.TclError:
        return False


_TK_AVAILABLE = _tk_available()


class FakeApp:
    """Minimal stand-in for Server16App -- just enough attributes for
    SettingsSectionFrame's kind="stadium" UI to construct and for
    save_entry() to run to completion."""

    def __init__(self, exedir: Path, ini: SessionIniFile) -> None:
        self.card = "#111111"
        self.card_soft = "#222222"
        self.bg = "#000000"
        self.fg = "#ffffff"
        self.muted = "#888888"
        self.accent = "#00ff00"
        self.gold = "#ffff00"
        self.error = "#ff0000"
        self.panel = "#333333"
        self.panel_alt = "#444444"
        self.exedir = exedir
        self.settings_ini = ini
        self.PitchMowsource = exedir / "FSW" / "PitchMowPattern"
        self.Nsource = exedir / "FSW" / "Nets"
        self.stadium_runtime = SimpleNamespace()

    def tr(self, translation_key: str, **kwargs) -> str:
        # Deliberately not named "key" -- save_entry() calls
        # self.tr("dialog.editor.saved", section=..., key=key), which would
        # collide with a same-named positional parameter here.
        return translation_key

    def wait_window(self, _dialog) -> None:
        pass

    def apply_all_runtime(self) -> None:
        pass

    def refresh_modules(self) -> None:
        pass

    def log(self, *args, **kwargs) -> None:
        pass


@unittest.skipUnless(_TK_AVAILABLE, "requires a Tk display")
class StadiumEditorSaveGoalpostOverridesTests(unittest.TestCase):
    """Regression tests for the 2026-09-11 bug reported live: saving a
    stadium's Police/Pitch/Net/Goalpost from the "Stadium Settings" editor
    (Edit Stadium Assets) silently never wrote [stadiumgoalpost]/
    [stadiumgoalposttexture] -- and, worse, could silently drop the
    [stadium]/[comp] assignment itself. Root cause: SessionIniFile.
    delete_key() unconditionally reloads from disk before deleting (see
    ini_file.py), which discards any write() made earlier in the same save
    cycle that hasn't reached disk yet. save_entry() used to write() the
    [stadium] value, then call _save_stadium_goalpost_overrides(), which
    interleaved write()/delete_key() across two dicts -- whichever category
    happened to be "None" (the common case) triggered a delete_key() that
    wiped out everything written earlier in the very same save_entry() call.
    Fixed by splitting into a delete-only pass (_clear_stale_stadium_
    goalpost_overrides, called BEFORE the [stadium] write) and a write-only
    pass (_write_stadium_goalpost_overrides, called after), so no delete_key()
    call in this cycle ever has anything pending to discard.

    These tests build a REAL SettingsSectionFrame (kind="stadium") against a
    REAL SessionIniFile -- a lightweight fake ini (plain dict, no reload
    semantics) would hide this exact bug, which is how it shipped unnoticed
    the first time."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.exedir = Path(self._tmp.name)
        (self.exedir / "FSW").mkdir(parents=True)
        self.ini = SessionIniFile(self.exedir / "FSW" / "settings.ini")
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.app = FakeApp(self.exedir, self.ini)

    def make_stadium_frame(self) -> SettingsSectionFrame:
        spec = SectionSpec("stadium", "Team Stadiums", kind="stadium", directory="StadiumGBD")
        return SettingsSectionFrame(self.root, self.app, spec)

    def test_model_only_override_and_the_stadium_assignment_both_persist(self) -> None:
        frame = self.make_stadium_frame()
        frame.key_var.set("176")
        frame.assigned_stadium_list.insert("end", "Anfield")
        frame._stadium_params["Anfield"] = ("4", "0", "0")
        frame._stadium_goalpost["Anfield"] = "1"
        frame._stadium_goalpost_texture["Anfield"] = "None"
        frame.save_entry()

        reloaded = SessionIniFile(self.ini.path)
        self.assertEqual(reloaded.read("176", "stadium"), "Anfield,4,0,0")
        self.assertEqual(reloaded.read("Anfield", "stadiumgoalpost"), "1")
        self.assertFalse(reloaded.key_exists("Anfield", "stadiumgoalposttexture"))

    def test_texture_only_override_and_the_stadium_assignment_both_persist(self) -> None:
        frame = self.make_stadium_frame()
        frame.key_var.set("176")
        frame.assigned_stadium_list.insert("end", "Anfield")
        frame._stadium_params["Anfield"] = ("4", "0", "0")
        frame._stadium_goalpost["Anfield"] = "None"
        frame._stadium_goalpost_texture["Anfield"] = "Azul"
        frame.save_entry()

        reloaded = SessionIniFile(self.ini.path)
        self.assertEqual(reloaded.read("176", "stadium"), "Anfield,4,0,0")
        self.assertFalse(reloaded.key_exists("Anfield", "stadiumgoalpost"))
        self.assertEqual(reloaded.read("Anfield", "stadiumgoalposttexture"), "Azul")

    def test_neither_override_set_still_persists_the_stadium_assignment(self) -> None:
        # Both categories "None" -- two delete_key() calls in a row, right
        # after the [stadium] write, was the original reported failure mode.
        frame = self.make_stadium_frame()
        frame.key_var.set("176")
        frame.assigned_stadium_list.insert("end", "Anfield")
        frame._stadium_params["Anfield"] = ("4", "0", "0")
        frame._stadium_goalpost["Anfield"] = "None"
        frame._stadium_goalpost_texture["Anfield"] = "None"
        frame.save_entry()

        reloaded = SessionIniFile(self.ini.path)
        self.assertEqual(reloaded.read("176", "stadium"), "Anfield,4,0,0")


@unittest.skipUnless(_TK_AVAILABLE, "requires a Tk display")
class StadiumEditorAssetPickerTests(unittest.TestCase):
    """The small button beside each preview-bearing combo of the stadium
    editor (Police/Pitch/Net/Goalpost Model/Goalpost Texture) opens
    AssetGridPickerDialog. The dialog itself is covered by
    test_asset_grid_picker_dialog.py -- here it's replaced by a recorder, so
    these tests only pin what the EDITOR feeds it (option lists, preview
    locations, current value) and what it does with the answer."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.exedir = Path(self._tmp.name)
        fsw = self.exedir / "FSW"
        # Preview dirs are resolved once when the frame is built, so the
        # files have to exist before make_frame().
        for rel in (
            "Images/Police/3.png",
            "Images/PitchMowPattern/2.png",
            "PitchMowPattern/pitchmowpattern_2_textures.rx3",
            "PitchMowPattern/pitchmowpattern_10_textures.rx3",
            "Images/Nets/1.png",
            "Nets/netcolor_1_textures.rx3",
            "Goalpost/GoalpostModel/1/preview.png",
            "Goalpost/GoalpostModel/2/specificgoalpost_0_0.rx3",
            "Goalpost/GoalpostColor/Azul/specificnetsupportpost_0_0_textures.rx3",
        ):
            path = fsw / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"x")
        (fsw / "Goalpost" / "GoalpostColor" / "Rojo").mkdir()  # a colour pack with no .rx3
        self.ini = SessionIniFile(fsw / "settings.ini")
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.addCleanup(self.root.update_idletasks)
        self.app = FakeApp(self.exedir, self.ini)

    def make_frame(self) -> SettingsSectionFrame:
        spec = SectionSpec("stadium", "Team Stadiums", kind="stadium", directory="StadiumGBD")
        return SettingsSectionFrame(self.root, self.app, spec)

    def select_stadium(self, frame: SettingsSectionFrame, name: str = "Anfield") -> None:
        frame.assigned_stadium_list.insert("end", name)
        frame.assigned_stadium_list.selection_set("end")
        frame._refresh_stadium_assigned_state()

    def run_picker(self, frame: SettingsSectionFrame, field: str, result: str | None) -> SimpleNamespace:
        """Runs _pick_stadium_asset with the dialog replaced by a recorder that
        answers `result`; returns the recorded call."""
        calls = []

        def fake_dialog(master, field_label, items, current="", **_kwargs):
            call = SimpleNamespace(master=master, field_label=field_label, items=items, current=current, result=result)
            calls.append(call)
            return call

        with mock.patch("server16_py.settings_editor.AssetGridPickerDialog", fake_dialog):
            frame._pick_stadium_asset(field)
        self.assertEqual(len(calls), 1)
        return calls[0]

    # ------------------------------------------------------------ option lists

    def test_police_offers_every_pattern_with_its_png(self) -> None:
        frame = self.make_frame()
        variable, label_key, items = frame._stadium_picker_setup("police")
        self.assertIs(variable, frame.police_var)
        self.assertEqual(label_key, "dialog.editor.field.police")
        self.assertEqual([item.value for item in items], [str(n) for n in range(1, 11)])
        self.assertEqual(items[2].image_path, self.exedir / "FSW" / "Images" / "Police" / "3.png")

    def test_pitch_and_net_offer_the_variant_index_the_combo_stores(self) -> None:
        frame = self.make_frame()
        _, _, pitch_items = frame._stadium_picker_setup("pitch")
        # "pitchmowpattern_10_textures.rx3" -> "10", sorted numerically (2 before 10).
        self.assertEqual([item.value for item in pitch_items], ["2", "10"])
        self.assertEqual(pitch_items[0].image_path, self.exedir / "FSW" / "Images" / "PitchMowPattern" / "2.png")
        _, _, net_items = frame._stadium_picker_setup("net")
        self.assertEqual([item.value for item in net_items], ["1"])
        self.assertEqual(net_items[0].image_path, self.exedir / "FSW" / "Images" / "Nets" / "1.png")

    def test_goalpost_model_offers_none_first_and_previews_only_where_a_preview_file_exists(self) -> None:
        frame = self.make_frame()
        variable, _, items = frame._stadium_picker_setup("goalpost")
        self.assertIs(variable, frame.goalpost_var)
        self.assertEqual([item.value for item in items], ["None", "1", "2"])
        by_value = {item.value: item for item in items}
        self.assertIsNone(by_value["None"].image_path)
        self.assertEqual(by_value["1"].image_path, self.exedir / "FSW" / "Goalpost" / "GoalpostModel" / "1" / "preview.png")
        self.assertIsNone(by_value["2"].image_path)  # no preview.<ext> in that pack

    def test_goalpost_texture_previews_are_rendered_from_the_rx3_reusing_the_cache(self) -> None:
        rendered = self.exedir / "azul.png"
        calls = []
        self.app.stadium_runtime.render_goalpost_texture_preview = (
            lambda rx3, cache_key, **kwargs: calls.append((rx3, cache_key, kwargs)) or rendered
        )
        frame = self.make_frame()
        variable, _, items = frame._stadium_picker_setup("goalposttexture")
        self.assertIs(variable, frame.goalpost_texture_var)
        by_value = {item.value: item for item in items}
        self.assertEqual(list(by_value), ["None", "Azul", "Rojo"])
        self.assertIsNone(by_value["None"].render)
        self.assertIsNone(by_value["Rojo"].render)  # pack without an .rx3: nothing to render
        self.assertIsNone(by_value["Azul"].image_path)
        self.assertEqual(by_value["Azul"].render(), rendered)
        source = self.exedir / "FSW" / "Goalpost" / "GoalpostColor" / "Azul" / "specificnetsupportpost_0_0_textures.rx3"
        self.assertEqual(calls, [(source, "Azul", {"reuse_cached": True})])

    def test_an_unknown_field_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.make_frame()._stadium_picker_setup("shape")

    # ------------------------------------------------------------------ result

    def test_choosing_sets_the_field_and_writes_through_to_the_selected_stadium(self) -> None:
        frame = self.make_frame()
        self.select_stadium(frame)
        call = self.run_picker(frame, "police", "7")
        self.assertEqual(call.current, "4")  # the police default the row started with
        self.assertEqual(call.field_label, "dialog.editor.field.police")
        self.assertEqual(frame.police_var.get(), "7")
        self.assertEqual(frame._stadium_params["Anfield"], ("7", "0", "0"))

    def test_choosing_a_goalpost_lands_in_that_stadiums_goalpost_dicts(self) -> None:
        frame = self.make_frame()
        self.select_stadium(frame)
        # Setting a real texture pack also kicks off the editor's own async
        # preview render (a thread that reports back through after(), which
        # needs a running mainloop) -- irrelevant to what's asserted here.
        with mock.patch.object(frame, "_update_goalpost_texture_preview"):
            self.run_picker(frame, "goalposttexture", "Azul")
        self.assertEqual(frame._stadium_goalpost_texture["Anfield"], "Azul")
        self.run_picker(frame, "goalpost", "1")
        self.assertEqual(frame._stadium_goalpost["Anfield"], "1")

    def test_the_current_value_is_passed_so_the_grid_can_highlight_it(self) -> None:
        frame = self.make_frame()
        self.select_stadium(frame)
        frame.goalpost_var.set("2")
        call = self.run_picker(frame, "goalpost", None)
        self.assertEqual(call.current, "2")

    def test_cancelling_leaves_the_field_and_the_stadium_untouched(self) -> None:
        frame = self.make_frame()
        self.select_stadium(frame)
        before = dict(frame._stadium_params)
        self.run_picker(frame, "net", None)
        self.assertEqual(frame.net_var.get(), "0")
        self.assertEqual(frame._stadium_params, before)

    # ----------------------------------------------------------------- buttons

    def test_every_preview_combo_has_a_picker_button_that_follows_the_combo_state(self) -> None:
        frame = self.make_frame()
        combos = (frame.police_combo, frame.pitch_combo, frame.net_combo, frame.goalpost_combo, frame.goalpost_texture_combo)
        for combo in combos:
            self.assertTrue(combo.picker_button.instate(["disabled"]), "no stadium row selected yet")
        self.select_stadium(frame)
        for combo in combos:
            self.assertTrue(combo.picker_button.instate(["!disabled"]))
        frame.assigned_stadium_list.selection_clear(0, "end")
        frame._on_assigned_selection_changed()
        for combo in combos:
            self.assertTrue(combo.picker_button.instate(["disabled"]))

    def test_combos_outside_the_stadium_editor_get_no_picker_button(self) -> None:
        # Only the stadium editor's preview-bearing fields opt in; the shared
        # _add_combo_row leaves every other editor's combos exactly as they were.
        spec = SectionSpec("scoreboard", "Scoreboards", kind="simple", directory="ScoreBoardGBD")
        frame = SettingsSectionFrame(self.root, self.app, spec)
        self.assertFalse(hasattr(frame.value_combo, "picker_button"))


if __name__ == "__main__":
    unittest.main()
