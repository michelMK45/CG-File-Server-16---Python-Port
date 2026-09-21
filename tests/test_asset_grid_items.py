from __future__ import annotations

import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from types import SimpleNamespace
from tkinter import ttk

from server16_py.asset_grid_items import (
    PICKER_ICON,
    AssetGridItem,
    goalpost_model_items,
    goalpost_texture_items,
    make_picker_button,
    png_items,
)


def _tk_available() -> bool:
    try:
        root = tk.Tk()
        root.destroy()
        return True
    except tk.TclError:
        return False


_TK_AVAILABLE = _tk_available()


class ItemBuilderTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def touch(self, rel: str) -> Path:
        path = self.tmp / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x")
        return path

    def test_png_items_preview_each_value_by_its_own_png(self) -> None:
        items = png_items(["2", "10"], self.tmp / "Nets")
        self.assertEqual(items, [
            AssetGridItem("2", "2", self.tmp / "Nets" / "2.png"),
            AssetGridItem("10", "10", self.tmp / "Nets" / "10.png"),
        ])

    def test_png_items_do_not_require_the_png_to_exist(self) -> None:
        # A missing file is the dialog's job to show as a placeholder; the
        # option itself must still be offered.
        (item,) = png_items(["7"], self.tmp / "absent")
        self.assertEqual(item.value, "7")
        self.assertFalse(item.image_path.exists())

    def test_goalpost_model_items_use_the_pack_preview_file_where_there_is_one(self) -> None:
        preview = self.touch("Model/1/preview.png")
        self.touch("Model/2/specificgoalpost_0_0.rx3")
        items = goalpost_model_items(self.tmp / "Model", ["None", "1", "2"])
        self.assertEqual([item.value for item in items], ["None", "1", "2"])
        self.assertEqual([item.image_path for item in items], [None, preview, None])
        self.assertTrue(all(item.render is None for item in items))

    def test_goalpost_texture_items_render_each_pack_from_its_own_rx3(self) -> None:
        azul_rx3 = self.touch("Color/Azul/tex.rx3")
        rojo_rx3 = self.touch("Color/Rojo/other.rx3")
        (self.tmp / "Color" / "Vacio").mkdir()  # a pack folder without any .rx3
        calls = []

        def render(source, cache_key, **kwargs):
            calls.append((source, cache_key, kwargs))
            return self.tmp / f"{cache_key}.png"

        runtime = SimpleNamespace(render_goalpost_texture_preview=render)
        items = {i.value: i for i in goalpost_texture_items(self.tmp / "Color", ["None", "Azul", "Rojo", "Vacio"], runtime)}

        self.assertIsNone(items["None"].render)
        self.assertIsNone(items["Vacio"].render)  # nothing to render
        self.assertTrue(all(i.image_path is None for i in items.values()))
        # Each closure must be bound to ITS pack (the classic late-binding trap:
        # every lambda ending up rendering the last pack of the loop).
        self.assertEqual(items["Azul"].render(), self.tmp / "Azul.png")
        self.assertEqual(items["Rojo"].render(), self.tmp / "Rojo.png")
        self.assertEqual(calls, [
            (azul_rx3, "Azul", {"reuse_cached": True}),
            (rojo_rx3, "Rojo", {"reuse_cached": True}),
        ])

    def test_builders_accept_any_iterable_not_just_lists(self) -> None:
        self.assertEqual([i.value for i in png_items(iter(("1", "2")), self.tmp)], ["1", "2"])
        self.assertEqual([i.value for i in goalpost_model_items(self.tmp, (n for n in ("None",)))], ["None"])


@unittest.skipUnless(_TK_AVAILABLE, "requires a Tk display")
class MakePickerButtonTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.addCleanup(self.root.update_idletasks)

    def test_button_shows_the_picker_glyph_and_runs_the_command(self) -> None:
        clicks = []
        button = make_picker_button(self.root, SimpleNamespace(), lambda: clicks.append(1))
        self.assertIsInstance(button, ttk.Button)
        self.assertEqual(button.cget("text"), PICKER_ICON)
        self.assertEqual(str(button.cget("style")), "Server16.Picker.TButton")
        button.invoke()
        self.assertEqual(clicks, [1])

    def test_a_tooltip_is_attached_when_the_app_offers_one(self) -> None:
        tooltips = []
        app = SimpleNamespace(_add_tooltip=lambda widget, key: tooltips.append((widget, key)))
        button = make_picker_button(self.root, app, lambda: None)
        self.assertEqual(tooltips, [(button, "tooltip.asset_grid_picker")])

    def test_no_tooltip_support_is_not_an_error(self) -> None:
        make_picker_button(self.root, SimpleNamespace(), lambda: None)  # must simply not raise


if __name__ == "__main__":
    unittest.main()
