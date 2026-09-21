from __future__ import annotations

import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from tkinter import ttk
from types import SimpleNamespace
from unittest import mock

from PIL import Image

from server16_py.asset_grid_items import PICKER_ICON
from server16_py.asset_grid_picker_dialog import AssetGridPickerDialog
from server16_py.dialogs import StadiumDialog


def _tk_available() -> bool:
    try:
        root = tk.Tk()
        root.destroy()
        return True
    except tk.TclError:
        return False


_TK_AVAILABLE = _tk_available()


def _walk(widget: tk.Misc):
    yield widget
    for child in widget.winfo_children():
        yield from _walk(child)


@unittest.skipUnless(_TK_AVAILABLE, "requires a Tk display")
class StadiumDialogAssetPickerTests(unittest.TestCase):
    """The Assign Stadium dialog's Police / Pitch / Net / Goalpost Model /
    Goalpost Texture combos each get a small button that opens the preview
    grid. StadiumDialog is itself modal, so the interesting part beyond
    "the choice lands in the field" is that opening a second modal on top of it
    must not leave it without its input grab afterwards."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.exedir = Path(self._tmp.name)
        fsw = self.exedir / "FSW"
        for rel in (
            "Images/Police/1.png", "Images/Police/3.png", "Images/Police/7.png",
            "Images/PitchMowPattern/2.png", "Images/PitchMowPattern/5.png",
            "Images/Nets/1.png",
            "Goalpost/GoalpostModel/1/preview.png",
        ):
            path = fsw / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGBA", (40, 30), "red").save(path)
        rx3 = fsw / "Goalpost" / "GoalpostColor" / "Azul" / "tex.rx3"
        rx3.parent.mkdir(parents=True)
        rx3.write_bytes(b"x")

        # StadiumDialog reads its theme + tr() straight off `master`, which must
        # also be a real widget (it becomes the Toplevel's owner).
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.addCleanup(self.root.update_idletasks)
        for name, value in dict(
            bg="#000000", panel="#333333", panel_alt="#444444", card="#111111", card_soft="#222222",
            fg="#ffffff", muted="#888888", accent="#00ff00", gold="#ffff00",
        ).items():
            setattr(self.root, name, value)
        self.root.tr = lambda key, **kwargs: f"{key} {kwargs}" if kwargs else key
        self.root.settings_ini = SimpleNamespace()
        self.root.stadium_runtime = SimpleNamespace()
        self.tooltips: list[tuple[tk.Misc, str]] = []
        self.root._add_tooltip = lambda widget, key: self.tooltips.append((widget, key))

        self.dialog = StadiumDialog(self.root, self.exedir)
        self.addCleanup(lambda: self.dialog.winfo_exists() and self.dialog.destroy())

    def run_pick(self, field: str, result: str | None) -> SimpleNamespace:
        """Runs _pick_asset with the grid dialog replaced by a recorder that
        answers `result`; returns what it was opened with."""
        opened = []

        def fake_picker(master, field_label, items, current="", **_kwargs):
            call = SimpleNamespace(master=master, field_label=field_label, items=items, current=current, result=result)
            opened.append(call)
            return call

        with mock.patch("server16_py.asset_grid_picker_dialog.AssetGridPickerDialog", fake_picker), \
                mock.patch.object(self.dialog, "wait_window"):  # the recorder is not a real widget
            self.dialog._pick_asset(field)
        self.assertEqual(len(opened), 1)
        return opened[0]

    # --------------------------------------------------------------- buttons

    def test_each_of_the_five_visual_combos_has_a_picker_button(self) -> None:
        buttons = [w for w in _walk(self.dialog) if isinstance(w, ttk.Button) and w.cget("text") == PICKER_ICON]
        self.assertEqual(len(buttons), 5)
        self.assertEqual([key for _, key in self.tooltips], ["tooltip.asset_grid_picker"] * 5)

    def test_buttons_sit_beside_their_combo_not_below_it(self) -> None:
        for button in (w for w in _walk(self.dialog) if isinstance(w, ttk.Button) and w.cget("text") == PICKER_ICON):
            siblings = [w for w in button.master.winfo_children() if isinstance(w, ttk.Combobox)]
            self.assertEqual(len(siblings), 1, "a picker button must share its wrapper with exactly one combo")
            self.assertEqual(int(siblings[0].grid_info()["row"]), int(button.grid_info()["row"]))
            self.assertEqual(int(button.grid_info()["column"]), int(siblings[0].grid_info()["column"]) + 1)

    # ---------------------------------------------------------- option lists

    def test_option_lists_match_the_combos_and_their_preview_folders(self) -> None:
        images = self.exedir / "FSW" / "Images"
        _, _, police, _ = self.dialog._asset_picker_setup("police")
        self.assertEqual([i.value for i in police], [str(n) for n in range(1, 11)])
        self.assertEqual(police[2].image_path, images / "Police" / "3.png")
        _, _, pitch, _ = self.dialog._asset_picker_setup("pitch")
        self.assertEqual([(i.value, i.image_path) for i in pitch], [
            ("2", images / "PitchMowPattern" / "2.png"), ("5", images / "PitchMowPattern" / "5.png"),
        ])
        _, _, net, _ = self.dialog._asset_picker_setup("net")
        self.assertEqual([(i.value, i.image_path) for i in net], [("1", images / "Nets" / "1.png")])
        _, _, models, _ = self.dialog._asset_picker_setup("goalpost")
        self.assertEqual([i.value for i in models], ["None", "1"])
        self.assertEqual(models[1].image_path, self.exedir / "FSW" / "Goalpost" / "GoalpostModel" / "1" / "preview.png")
        _, _, textures, _ = self.dialog._asset_picker_setup("goalposttexture")
        self.assertEqual([i.value for i in textures], ["None", "Azul"])
        self.assertIsNone(textures[0].render)
        self.assertIsNotNone(textures[1].render)

    def test_each_field_is_bound_to_its_own_variable_and_refresh_callback(self) -> None:
        d = self.dialog
        expected = {
            "police": (d.selectedpolice, d._on_police_changed),
            "pitch": (d.selectedpitch, d._on_pitch_changed),
            "net": (d.selectednet, d._on_net_changed),
            "goalpost": (d.selectedgoalpost, d._on_goalpost_model_changed),
            "goalposttexture": (d.selectedgoalposttexture, d._on_goalpost_texture_changed),
        }
        for field, (variable, refresh) in expected.items():
            got_variable, _label, _items, got_refresh = d._asset_picker_setup(field)
            self.assertIs(got_variable, variable, field)
            self.assertEqual(got_refresh, refresh, field)

    def test_an_unknown_field_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.dialog._asset_picker_setup("shape")

    # ---------------------------------------------------------------- result

    def test_a_pick_sets_the_field_and_refreshes_its_preview(self) -> None:
        # Setting a StringVar doesn't fire <<ComboboxSelected>>, so without the
        # explicit refresh the preview box would keep showing the OLD pattern.
        police_preview = self.dialog._preview_labels["police"]
        before = str(police_preview.cget("image"))  # the dialog already shows the default pattern's image
        self.assertNotEqual(before, "")
        call = self.run_pick("police", "7")
        self.assertEqual(call.field_label, "dialog.stadium.police_pattern")
        self.assertEqual(call.current, "1")  # the dialog's own default
        self.assertEqual(self.dialog.selectedpolice.get(), "7")
        after = str(police_preview.cget("image"))
        self.assertNotEqual(after, "")
        self.assertNotEqual(after, before, "the preview box was not refreshed for the new value")

    def test_a_pick_for_each_field_lands_in_that_fields_variable(self) -> None:
        for field, value, variable in (
            ("pitch", "5", self.dialog.selectedpitch),
            ("net", "1", self.dialog.selectednet),
            ("goalpost", "1", self.dialog.selectedgoalpost),
            ("goalposttexture", "Azul", self.dialog.selectedgoalposttexture),
        ):
            with mock.patch.object(self.dialog, "_on_goalpost_texture_changed"):  # would spawn the render thread
                self.run_pick(field, value)
            self.assertEqual(variable.get(), value, field)

    def test_cancelling_leaves_the_field_alone(self) -> None:
        before = self.dialog.selectedpolice.get()
        self.run_pick("police", None)
        self.assertEqual(self.dialog.selectedpolice.get(), before)

    # ------------------------------------------------------- modal behaviour

    def find_picker(self) -> AssetGridPickerDialog:
        return next(w for w in self.root.winfo_children() if isinstance(w, AssetGridPickerDialog))

    def test_this_dialog_regains_the_input_grab_after_the_picker_closes(self) -> None:
        self.assertIs(self.dialog.grab_current(), self.dialog, "precondition: the dialog is modal")
        # Real picker, real wait_window: double-click the third cell once it's up.
        self.root.after(80, lambda: self.find_picker()._activate(2))
        self.dialog._pick_asset("police")
        self.assertEqual(self.dialog.selectedpolice.get(), "3")
        self.assertIs(self.dialog.grab_current(), self.dialog, "Tk drops the grab when the picker dies; it must be retaken")

    def test_cancelling_the_real_picker_also_restores_the_grab(self) -> None:
        self.root.after(80, lambda: self.find_picker().destroy())
        self.dialog._pick_asset("police")
        self.assertEqual(self.dialog.selectedpolice.get(), "1")
        self.assertIs(self.dialog.grab_current(), self.dialog)

    def test_closing_this_dialog_while_the_picker_is_open_is_harmless(self) -> None:
        def close_both() -> None:
            picker = self.find_picker()
            self.dialog.destroy()
            picker.destroy()

        self.root.after(80, close_both)
        self.dialog._pick_asset("police")  # must return without raising
        self.assertFalse(self.dialog.winfo_exists())


if __name__ == "__main__":
    unittest.main()
