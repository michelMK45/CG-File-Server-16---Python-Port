from __future__ import annotations

import tempfile
import threading
import time
import tkinter as tk
import unittest
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from server16_py.asset_grid_items import AssetGridItem
from server16_py.asset_grid_picker_dialog import AssetGridPickerDialog


def _tk_available() -> bool:
    try:
        root = tk.Tk()
        root.destroy()
        return True
    except tk.TclError:
        return False


_TK_AVAILABLE = _tk_available()


def _make_app_root() -> tk.Tk:
    """A real Tk root wearing just the attributes BaseDialog reads off its
    `master` (theme colours + tr()) -- BaseDialog needs the owner to be an
    actual widget AND the theme source, so a plain fake app object won't do."""
    root = tk.Tk()
    root.withdraw()
    for name, value in dict(
        bg="#000000", panel="#333333", panel_alt="#444444", card="#111111", card_soft="#222222",
        fg="#ffffff", muted="#888888", accent="#00ff00", gold="#ffff00",
    ).items():
        setattr(root, name, value)
    # Echo kwargs back so tests can see which placeholders were filled in.
    root.tr = lambda key, **kwargs: f"{key} {kwargs}" if kwargs else key
    return root


@unittest.skipUnless(_TK_AVAILABLE, "requires a Tk display")
class AssetGridPickerDialogTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.root = _make_app_root()
        self.addCleanup(self.root.destroy)
        # Let ttk's deferred <<ThemeChanged>> idle callback run while the
        # interpreter still exists, or destroying the root prints a Tcl error.
        self.addCleanup(self.root.update_idletasks)

    def png(self, name: str, color: str = "red") -> Path:
        path = self.tmp / name
        Image.new("RGBA", (300, 200), color).save(path)
        return path

    def make_dialog(self, items: list[AssetGridItem], current: str = "") -> AssetGridPickerDialog:
        dialog = AssetGridPickerDialog(self.root, "Police", items, current=current)
        self.addCleanup(lambda: dialog.winfo_exists() and dialog.destroy())
        return dialog

    def pump(self, predicate, timeout: float = 5.0) -> bool:
        """Runs the Tk event loop until predicate() -- the dialog's deferred
        work (batched image loading, draining finished renders) is driven by
        after() callbacks, which only fire while events are pumped."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.root.update()
            if predicate():
                return True
            time.sleep(0.01)
        return False

    @staticmethod
    def plain_items(count: int) -> list[AssetGridItem]:
        return [AssetGridItem(f"v{i}", f"Item {i}") for i in range(count)]

    # ------------------------------------------------------------- selection

    def test_one_cell_per_item_and_current_is_preselected(self) -> None:
        dialog = self.make_dialog(self.plain_items(5), current="v2")
        self.assertEqual(len(dialog._cells), 5)
        self.assertEqual(dialog._selected, 2)
        self.assertIn("'name': 'Item 2'", dialog._selected_label.cget("text"))
        self.assertTrue(dialog._select_button.instate(["!disabled"]))

    def test_a_current_value_not_in_the_grid_leaves_nothing_selected(self) -> None:
        # The combos are free-text, so the field can hold a value with no cell.
        dialog = self.make_dialog(self.plain_items(3), current="typed by hand")
        self.assertIsNone(dialog._selected)
        self.assertTrue(dialog._select_button.instate(["disabled"]))
        dialog._confirm()
        self.assertIsNone(dialog.result)
        self.assertTrue(dialog.winfo_exists())

    def test_confirm_returns_the_value_not_the_label(self) -> None:
        dialog = self.make_dialog([AssetGridItem("val-a", "Label A"), AssetGridItem("val-b", "Label B")])
        dialog._select(1)
        dialog._confirm()
        self.assertEqual(dialog.result, "val-b")
        self.assertFalse(dialog.winfo_exists())

    def test_activate_selects_and_confirms_in_one_step(self) -> None:
        dialog = self.make_dialog(self.plain_items(4))
        dialog._activate(3)
        self.assertEqual(dialog.result, "v3")

    def test_closing_without_confirming_returns_none(self) -> None:
        dialog = self.make_dialog(self.plain_items(4), current="v1")
        dialog.destroy()
        self.assertIsNone(dialog.result)

    def test_selecting_moves_the_highlight(self) -> None:
        dialog = self.make_dialog(self.plain_items(3), current="v0")
        dialog._select(2)
        self.assertEqual(dialog._cells[0].cget("highlightbackground"), AssetGridPickerDialog.BORDER)
        self.assertEqual(dialog._cells[2].cget("highlightbackground"), self.root.accent)

    def test_arrow_keys_step_by_one_and_by_row(self) -> None:
        dialog = self.make_dialog(self.plain_items(8))
        dialog._relayout(4)
        dialog._move_selection(1)  # nothing selected yet -> first cell
        self.assertEqual(dialog._selected, 0)
        dialog._move_selection(1)
        self.assertEqual(dialog._selected, 1)
        dialog._move_selection(dialog._columns)  # Down
        self.assertEqual(dialog._selected, 5)
        dialog._move_selection(-dialog._columns)  # Up
        self.assertEqual(dialog._selected, 1)
        dialog._move_selection(-1)
        dialog._move_selection(-1)  # already first: stays put
        self.assertEqual(dialog._selected, 0)

    def test_empty_grid_shows_no_cells_and_cannot_be_confirmed(self) -> None:
        dialog = self.make_dialog([])
        self.assertEqual(dialog._cells, [])
        self.assertTrue(dialog._select_button.instate(["disabled"]))
        dialog._move_selection(1)
        dialog._confirm()
        self.assertIsNone(dialog.result)

    # ---------------------------------------------------------------- layout

    def test_column_count_follows_the_available_width(self) -> None:
        dialog = self.make_dialog(self.plain_items(7))
        # 170px thumbnail + 26px of per-cell chrome = 196px per column.
        for width, expected_columns in ((1000, 5), (400, 2), (100, 1)):
            dialog._on_canvas_configure(SimpleNamespace(width=width))
            self.assertEqual(dialog._columns, expected_columns)
            for index, cell in enumerate(dialog._cells):
                info = cell.grid_info()
                self.assertEqual((int(info["row"]), int(info["column"])), divmod(index, expected_columns))

    def assert_selected_cell_in_view(self, dialog: AssetGridPickerDialog) -> None:
        cell = dialog._cells[dialog._selected]
        top = cell.winfo_y()
        view_top = dialog._canvas.canvasy(0)
        view_bottom = view_top + dialog._canvas.winfo_height()
        self.assertGreaterEqual(top, view_top)
        self.assertLessEqual(top + cell.winfo_height(), view_bottom)

    def test_preselected_cell_is_scrolled_into_view_once_the_window_is_laid_out(self) -> None:
        # Needs a genuinely mapped window (a dialog owned by a withdrawn root
        # never maps), so make root + dialog visible-but-fully-transparent.
        self.root.attributes("-alpha", 0.0)
        self.root.deiconify()
        dialog = self.make_dialog(self.plain_items(40), current="v35")
        dialog.attributes("-alpha", 0.0)
        self.assertTrue(self.pump(lambda: dialog._laid_out and dialog._visible_job is None))
        self.pump(lambda: False, timeout=0.3)  # let the final layout and scroll settle
        self.assertGreater(dialog._canvas.canvasy(0), 0, "still at the top: the selection was never scrolled to")
        self.assert_selected_cell_in_view(dialog)

        # A resize that changes the column count moves every cell; the
        # selection must be brought back into view rather than left behind.
        dialog.geometry("560x520")
        self.pump(lambda: False, timeout=0.3)
        self.assertEqual(dialog._columns, dialog._columns_for_width(dialog._canvas.winfo_width()))
        self.assert_selected_cell_in_view(dialog)

    def test_scrolling_is_skipped_while_the_canvas_has_no_real_size_yet(self) -> None:
        # Unmapped: the canvas reports a 1px height, and scrolling by that would
        # fling the view thousands of pixels past the selection.
        dialog = self.make_dialog(self.plain_items(40), current="v35")
        dialog._ensure_visible(35)
        self.assertEqual(dialog._canvas.canvasy(0), 0)

    # -------------------------------------------------------------- previews

    def test_static_previews_load_a_batch_at_a_time(self) -> None:
        count = AssetGridPickerDialog.LOAD_BATCH + 3
        items = [AssetGridItem(str(i), str(i), self.png(f"{i}.png")) for i in range(count)]
        dialog = self.make_dialog(items)
        # Only the first batch is decoded before the dialog is handed back;
        # the rest arrive on later event-loop ticks instead of blocking it.
        self.assertEqual(len(dialog._photos), AssetGridPickerDialog.LOAD_BATCH)
        self.assertTrue(self.pump(lambda: len(dialog._photos) == count))
        for thumb in dialog._thumbs:
            self.assertNotEqual(str(thumb.cget("image")), "")

    def test_missing_and_corrupt_images_fall_back_to_placeholders(self) -> None:
        corrupt = self.tmp / "corrupt.png"
        corrupt.write_text("not an image")
        dialog = self.make_dialog([
            AssetGridItem("a", "a", self.tmp / "absent.png"),
            AssetGridItem("b", "b", corrupt),
            AssetGridItem("c", "c"),
        ])
        self.assertEqual(dialog._thumbs[0].cget("text"), "placeholder.no_preview")
        self.assertEqual(dialog._thumbs[1].cget("text"), "dialog.kitmix.preview_error")
        self.assertEqual(dialog._thumbs[2].cget("text"), "placeholder.no_preview")

    def test_generated_previews_fill_in_from_a_background_thread(self) -> None:
        rendered = self.png("rendered.png")
        render_threads: list[threading.Thread] = []
        gate = threading.Event()
        self.addCleanup(gate.set)

        def render() -> Path:
            render_threads.append(threading.current_thread())
            gate.wait(5)  # hold the result back so the "loading" state is observable
            return rendered

        dialog = self.make_dialog([AssetGridItem("a", "a", render=render), AssetGridItem("none", "None")])
        self.assertEqual(dialog._thumbs[0].cget("text"), "dialog.kitmix.loading")
        self.assertEqual(dialog._thumbs[1].cget("text"), "placeholder.no_preview")
        gate.set()
        self.assertTrue(self.pump(lambda: 0 in dialog._photos))
        self.assertIsNot(render_threads[0], threading.main_thread())
        self.assertNotIn(1, dialog._photos)

    def test_generated_previews_render_one_at_a_time_in_order(self) -> None:
        order: list[str] = []
        png = self.png("rendered.png")

        def renderer(name: str):
            def render() -> Path:
                order.append(name)
                return png
            return render

        items = [AssetGridItem(name, name, render=renderer(name)) for name in ("a", "b", "c")]
        dialog = self.make_dialog(items)
        self.assertTrue(self.pump(lambda: len(dialog._photos) == 3))
        self.assertEqual(order, ["a", "b", "c"])

    def test_a_failing_render_only_marks_its_own_cell(self) -> None:
        good = self.png("good.png")

        def boom() -> Path:
            raise RuntimeError("32-bit bridge missing")

        dialog = self.make_dialog([AssetGridItem("bad", "bad", render=boom), AssetGridItem("ok", "ok", render=lambda: good)])
        self.assertTrue(self.pump(lambda: 1 in dialog._photos))
        self.assertEqual(dialog._thumbs[0].cget("text"), "dialog.kitmix.preview_error")

    def test_a_static_image_wins_over_a_render_hook(self) -> None:
        calls: list[int] = []
        dialog = self.make_dialog([AssetGridItem("a", "a", self.png("a.png"), render=lambda: calls.append(1))])
        self.pump(lambda: False, timeout=0.2)
        self.assertEqual(calls, [])
        self.assertIn(0, dialog._photos)

    def test_no_further_renders_start_once_the_dialog_is_closed(self) -> None:
        started, release = threading.Event(), threading.Event()
        second_calls: list[int] = []

        def slow() -> None:
            started.set()
            release.wait(5)

        dialog = self.make_dialog([
            AssetGridItem("a", "a", render=slow),
            AssetGridItem("b", "b", render=lambda: second_calls.append(1)),
        ])
        self.assertTrue(started.wait(5))
        dialog.destroy()
        release.set()
        # Give the (now unblocked) worker time to reach its next iteration and
        # see the dialog is gone, with the event loop still being serviced.
        self.pump(lambda: False, timeout=0.4)
        self.assertEqual(second_calls, [])

    def test_closing_cancels_every_pending_after_job(self) -> None:
        # An after() callback firing once its widget is gone is a Tcl "invalid
        # command name" (and a Tk error dialog), so destroy() must cancel all
        # three: the batched image loader, the render poll, and the
        # scroll-to-selection idle job.
        release = threading.Event()
        self.addCleanup(release.set)
        count = AssetGridPickerDialog.LOAD_BATCH + 2
        items = [AssetGridItem(str(i), str(i), self.png(f"{i}.png")) for i in range(count)]
        items.append(AssetGridItem("slow", "slow", render=lambda: release.wait(5) and None))
        dialog = self.make_dialog(items, current="1")

        jobs = {dialog._load_job, dialog._render_poll_job, dialog._visible_job}
        self.assertNotIn(None, jobs)
        pending = set(self.root.tk.splitlist(self.root.tk.call("after", "info")))
        self.assertTrue(jobs <= pending)

        dialog.destroy()
        pending = set(self.root.tk.splitlist(self.root.tk.call("after", "info")))
        self.assertFalse(jobs & pending)


if __name__ == "__main__":
    unittest.main()
