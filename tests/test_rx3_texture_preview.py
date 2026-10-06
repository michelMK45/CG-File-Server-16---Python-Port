from __future__ import annotations

import tempfile
import threading
import time
import tkinter as tk
import unittest
from pathlib import Path

from PIL import Image

from server16_py.rx3_texture_preview import NEXT_ICON, PREV_ICON, Rx3TexturePreview


def _tk_available() -> bool:
    try:
        root = tk.Tk()
        root.destroy()
        return True
    except tk.TclError:
        return False


_TK_AVAILABLE = _tk_available()


class FakeApp:
    card_soft = "#222222"
    panel = "#333333"
    fg = "#ffffff"
    muted = "#888888"

    def tr(self, translation_key: str, **kwargs) -> str:
        if translation_key == "dialog.editor.preview.rx3_caption":
            return f"{kwargs['file']} texture {kwargs['index']}/{kwargs['count']}"
        return translation_key


@unittest.skipUnless(_TK_AVAILABLE, "requires a Tk display")
class Rx3TexturePreviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.pack = self.tmp / "Pack"
        self.pack.mkdir()
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.addCleanup(self.root.update_idletasks)
        self.preview = Rx3TexturePreview(self.root, FakeApp(), "Pack Textures", image_size=(200, 120))
        self.preview.pack()
        self.render_calls: list[Path] = []

    # -------------------------------------------------------------- helpers

    def make_png(self, name: str, size=(64, 32), color=(200, 40, 40, 255)) -> Path:
        path = self.tmp / name
        Image.new("RGBA", size, color).save(path)
        return path

    def add_rx3(self, name: str) -> Path:
        path = self.pack / name
        path.write_bytes(b"rx3")
        return path

    def pump(self, until, timeout: float = 5.0) -> None:
        deadline = time.monotonic() + timeout
        while not until():
            self.assertLess(time.monotonic(), deadline, "timed out waiting for the preview")
            self.root.update()
            time.sleep(0.005)

    def renderer(self, textures: dict[str, int]):
        """render_file stand-in: `textures` maps an .rx3 name to how many textures it holds."""
        def render(rx3: Path) -> list[Path]:
            self.render_calls.append(rx3)
            return [self.make_png(f"{rx3.stem}_{i}.png", color=(10 * i, 40, 40, 255)) for i in range(textures[rx3.name])]
        return render

    def counter(self) -> str:
        return self.preview._counter_label.cget("text")

    def caption(self) -> str:
        return self.preview._caption_label.cget("text")

    def buttons_enabled(self) -> tuple[bool, bool]:
        return (self.preview._prev_button.instate(["!disabled"]), self.preview._next_button.instate(["!disabled"]))

    # ----------------------------------------------------------------- tests

    def test_starts_empty_with_the_arrows_disabled(self) -> None:
        self.assertEqual(self.preview._image_label.cget("text"), "placeholder.no_preview")
        self.assertEqual(self.buttons_enabled(), (False, False))
        self.assertEqual(self.preview._prev_button.cget("text"), PREV_ICON)
        self.assertEqual(self.preview._next_button.cget("text"), NEXT_ICON)

    def test_shows_the_first_texture_then_steps_through_all_of_them_wrapping_around(self) -> None:
        self.add_rx3("specificwipe_0_996_0.rx3")
        self.preview.show_pack(self.pack, self.renderer({"specificwipe_0_996_0.rx3": 8}))
        self.pump(lambda: len(self.preview.frames) == 8)
        self.assertEqual(self.counter(), "1 / 8")
        self.assertEqual(self.caption(), "specificwipe_0_996_0.rx3 texture 1/8")
        self.assertEqual(self.buttons_enabled(), (True, True))
        self.assertNotEqual(str(self.preview._image_label.cget("image")), "")  # a picture is showing

        for expected in range(2, 9):
            self.preview.step(1)
            self.assertEqual(self.counter(), f"{expected} / 8")
        self.assertEqual(self.caption(), "specificwipe_0_996_0.rx3 texture 8/8")
        self.preview.step(1)  # past the last -> back to the first
        self.assertEqual(self.counter(), "1 / 8")
        self.preview.step(-1)  # before the first -> the last
        self.assertEqual(self.counter(), "8 / 8")

    def test_the_arrow_buttons_step(self) -> None:
        self.add_rx3("a.rx3")
        self.preview.show_pack(self.pack, self.renderer({"a.rx3": 3}))
        self.pump(lambda: len(self.preview.frames) == 3)
        self.preview._next_button.invoke()
        self.assertEqual(self.counter(), "2 / 3")
        self.preview._prev_button.invoke()
        self.preview._prev_button.invoke()
        self.assertEqual(self.counter(), "3 / 3")

    def test_clicking_the_image_gives_it_focus_so_the_arrow_keys_step(self) -> None:
        self.add_rx3("a.rx3")
        self.preview.show_pack(self.pack, self.renderer({"a.rx3": 3}))
        self.pump(lambda: len(self.preview.frames) == 3)
        # Key events only reach a focused window of a mapped toplevel.
        self.root.deiconify()
        self.root.update()
        self.addCleanup(self.root.withdraw)
        label = self.preview._image_label
        label.event_generate("<Button-1>", x=5, y=5)
        self.root.update()
        self.assertIs(self.root.focus_get(), label)
        label.event_generate("<Right>")
        self.root.update()
        self.assertEqual(self.counter(), "2 / 3")
        label.event_generate("<Left>")
        label.event_generate("<Left>")
        self.root.update()
        self.assertEqual(self.counter(), "3 / 3")

    def test_textures_of_several_rx3_files_form_one_sequence_with_each_files_own_caption(self) -> None:
        self.add_rx3("a.rx3")
        self.add_rx3("b.rx3")
        self.preview.show_pack(self.pack, self.renderer({"a.rx3": 2, "b.rx3": 3}))
        self.pump(lambda: len(self.preview.frames) == 5)
        self.assertEqual([(f.rx3, f.index, f.count) for f in self.preview.frames],
                         [("a.rx3", 0, 2), ("a.rx3", 1, 2), ("b.rx3", 0, 3), ("b.rx3", 1, 3), ("b.rx3", 2, 3)])
        self.preview.step(2)
        self.assertEqual(self.counter(), "3 / 5")
        self.assertEqual(self.caption(), "b.rx3 texture 1/3")

    def test_textures_join_as_each_file_finishes_without_moving_the_one_being_viewed(self) -> None:
        self.add_rx3("a.rx3")
        self.add_rx3("b.rx3")
        release_b = threading.Event()

        def render(rx3: Path) -> list[Path]:
            if rx3.name == "b.rx3":
                release_b.wait(5)
            return [self.make_png(f"{rx3.stem}_{i}.png") for i in range(2)]

        self.preview.show_pack(self.pack, render)
        self.pump(lambda: len(self.preview.frames) == 2)
        self.assertEqual(self.counter(), "1 / 2+")  # "+": more may still arrive
        self.preview.step(1)
        release_b.set()
        self.pump(lambda: len(self.preview.frames) == 4)
        self.pump(lambda: self.counter() == "2 / 4")  # still on the texture the user was looking at

    def test_a_pack_without_rx3_files_says_so_and_never_calls_the_renderer(self) -> None:
        (self.pack / "preview.png").write_bytes(b"x")
        self.preview.show_pack(self.pack, self.renderer({}))
        self.assertEqual(self.preview._image_label.cget("text"), "dialog.editor.preview.rx3_empty")
        self.assertEqual(self.buttons_enabled(), (False, False))
        self.assertEqual(self.render_calls, [])

    def test_no_pack_shows_the_plain_placeholder(self) -> None:
        self.add_rx3("a.rx3")
        self.preview.show_pack(self.pack, self.renderer({"a.rx3": 2}))
        self.pump(lambda: len(self.preview.frames) == 2)
        self.preview.show_pack(None, self.renderer({}))
        self.assertEqual(self.preview.frames, [])
        self.assertEqual(self.preview._image_label.cget("text"), "placeholder.no_preview")
        self.assertEqual(self.counter(), "")
        self.assertEqual(self.caption(), "")

    def test_a_failing_file_is_skipped_but_the_others_still_show(self) -> None:
        self.add_rx3("a.rx3")
        self.add_rx3("b.rx3")

        def render(rx3: Path) -> list[Path]:
            if rx3.name == "a.rx3":
                raise RuntimeError("bridge failed")
            return [self.make_png("b0.png")]

        self.preview.show_pack(self.pack, render)
        self.pump(lambda: len(self.preview.frames) == 1)
        self.assertEqual(self.preview.frames[0].rx3, "b.rx3")
        self.assertEqual(self.buttons_enabled(), (False, False))  # a single texture: nothing to step

    def test_when_every_file_fails_the_preview_reports_unavailable(self) -> None:
        self.add_rx3("a.rx3")

        def render(rx3: Path) -> list[Path]:
            raise RuntimeError("32-bit Python not found")

        self.preview.show_pack(self.pack, render)
        self.pump(lambda: self.preview._image_label.cget("text") == "dialog.kitmix.preview_error")
        self.assertEqual(self.preview.frames, [])

    def test_a_texture_the_bridge_reported_but_cannot_be_read_shows_the_error_placeholder(self) -> None:
        self.add_rx3("a.rx3")
        broken = self.tmp / "broken.png"
        broken.write_bytes(b"not a png")
        self.preview.show_pack(self.pack, lambda rx3: [broken])
        self.pump(lambda: len(self.preview.frames) == 1)
        self.assertEqual(self.preview._image_label.cget("text"), "dialog.kitmix.preview_error")

    def test_a_newer_pack_supersedes_one_that_is_still_rendering(self) -> None:
        slow_pack = self.tmp / "Slow"
        slow_pack.mkdir()
        (slow_pack / "slow.rx3").write_bytes(b"rx3")
        self.add_rx3("fast.rx3")
        release = threading.Event()

        def slow(rx3: Path) -> list[Path]:
            release.wait(5)
            return [self.make_png("slow0.png"), self.make_png("slow1.png")]

        self.preview.show_pack(slow_pack, slow)
        self.root.update()
        self.preview.show_pack(self.pack, self.renderer({"fast.rx3": 1}))
        self.pump(lambda: len(self.preview.frames) == 1)
        release.set()  # the stale render now finishes -- its textures must be dropped
        for _ in range(20):
            self.root.update()
            time.sleep(0.01)
        self.assertEqual([f.rx3 for f in self.preview.frames], ["fast.rx3"])

    def test_the_rest_of_a_superseded_pack_is_never_rendered(self) -> None:
        # Switching pack must stop the old worker from burning a 32-bit subprocess
        # per remaining file.
        for name in ("a.rx3", "b.rx3", "c.rx3"):
            self.add_rx3(name)
        first_started = threading.Event()
        release = threading.Event()
        rendered: list[str] = []

        def render(rx3: Path) -> list[Path]:
            rendered.append(rx3.name)
            first_started.set()
            release.wait(5)
            return [self.make_png(f"{rx3.stem}.png")]

        self.preview.show_pack(self.pack, render)
        self.assertTrue(first_started.wait(5))
        self.preview.show_pack(None, render)  # supersede while a.rx3 is rendering
        release.set()
        time.sleep(0.2)
        self.assertEqual(rendered, ["a.rx3"])

    def test_destroying_the_widget_mid_render_is_safe(self) -> None:
        self.add_rx3("a.rx3")
        release = threading.Event()
        finished = threading.Event()

        def render(rx3: Path) -> list[Path]:
            release.wait(5)
            finished.set()
            return [self.make_png("late.png")]

        self.preview.show_pack(self.pack, render)
        self.root.update()
        self.preview.destroy()
        release.set()
        self.assertTrue(finished.wait(5))
        for _ in range(10):  # no stray `after` callback may hit the dead widget
            self.root.update()
            time.sleep(0.01)


if __name__ == "__main__":
    unittest.main()
