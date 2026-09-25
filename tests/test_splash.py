from __future__ import annotations

import importlib.util
import io
import tempfile
import time
import tkinter as tk
import unittest
from pathlib import Path

from PIL import Image

from server16_py import splash as splash_module
from server16_py.splash import SplashScreen, _blend, compute_layout, find_icon_path, icon_png

_PNG = bytes.fromhex('89504e470d0a1a0a')


class BlendTests(unittest.TestCase):
    def test_endpoints_and_midpoint(self) -> None:
        self.assertEqual(_blend("#000000", "#ffffff", 0.0), "#000000")
        self.assertEqual(_blend("#000000", "#ffffff", 1.0), "#ffffff")
        self.assertEqual(_blend("#000000", "#fefefe", 0.5), "#7f7f7f")

    def test_amount_is_clamped(self) -> None:
        self.assertEqual(_blend("#102030", "#405060", -3.0), "#102030")
        self.assertEqual(_blend("#102030", "#405060", 9.0), "#405060")


class ComputeLayoutTests(unittest.TestCase):
    def test_is_a_wide_rectangle_with_the_icon_on_the_left(self) -> None:
        layout = compute_layout(1.0)
        self.assertEqual((layout.width, layout.height), (520, 200))
        self.assertGreater(layout.width, layout.height * 2)
        self.assertEqual(layout.icon_px, 128)
        self.assertLess(layout.icon_x, layout.text_x)
        self.assertGreaterEqual(layout.text_x, layout.icon_x + layout.icon_px)
        # Icon vertically centered.
        self.assertEqual(layout.icon_y, (layout.height - layout.icon_px) // 2)

    def test_text_column_fits_inside_the_window(self) -> None:
        for scale in (1.0, 1.25, 1.5, 2.0, 3.0):
            layout = compute_layout(scale)
            self.assertLess(layout.message_x, layout.width, scale)
            self.assertGreater(layout.height, layout.icon_px, scale)
            self.assertGreater(layout.message_x, layout.spin_cx + layout.spin_r, scale)

    def test_scales_with_the_display(self) -> None:
        small, large = compute_layout(1.0), compute_layout(2.0)
        self.assertEqual(large.width, small.width * 2)
        self.assertEqual(large.icon_px, small.icon_px * 2)


class IconPngTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ico = find_icon_path()
        if self.ico is None:
            self.skipTest("server16.ico not found")

    @staticmethod
    def _size(png: bytes) -> tuple[int, int]:
        return Image.open(io.BytesIO(png)).size

    def test_exact_entry_is_used_as_is(self) -> None:
        png = icon_png(self.ico, 128)
        self.assertTrue(png.startswith(_PNG))
        self.assertEqual(self._size(png), (128, 128))

    def test_other_sizes_come_back_at_exactly_that_size(self) -> None:
        for target in (100, 160, 192):
            self.assertEqual(self._size(icon_png(self.ico, target)), (target, target), target)

    def test_missing_or_broken_icon_yields_none(self) -> None:
        self.assertIsNone(icon_png(None, 128))
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.ico"
            bad.write_bytes(b"not an icon at all")
            self.assertIsNone(icon_png(bad, 128))
            self.assertIsNone(icon_png(Path(tmp) / "missing.ico", 128))


class BootSplashImageTests(unittest.TestCase):
    def test_renders_the_live_splash_geometry(self) -> None:
        script = Path(__file__).resolve().parent.parent / "scripts" / "make_boot_splash.py"
        spec = importlib.util.spec_from_file_location("make_boot_splash", script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        layout = compute_layout(1.0)
        with tempfile.TemporaryDirectory() as tmp:
            out = module.render(Path(tmp) / "nested" / "boot.png")
            image = Image.open(out)
            image.load()
        self.assertEqual(image.size, (layout.width, layout.height))
        # Panel color inside, the icon painted over it on the left, and no
        # magenta (PyInstaller's transparency key on Windows) anywhere.
        panel = tuple(int(splash_module.PANEL[i:i + 2], 16) for i in (1, 3, 5))
        self.assertEqual(image.getpixel((layout.width - 40, layout.height // 2)), panel)
        icon_center = (layout.icon_x + layout.icon_px // 2, layout.icon_y + layout.icon_px // 2)
        self.assertNotEqual(image.getpixel(icon_center), panel)
        self.assertNotIn((255, 0, 255), {pixel for _count, pixel in image.getcolors(maxcolors=200000)})


class SplashScreenTests(unittest.TestCase):
    def _open(self, message: str = "") -> SplashScreen:
        splash = SplashScreen(message)
        if not splash._shown_at:
            self.skipTest("no display available for a Tk window")
        self.addCleanup(splash.close)
        return splash

    def test_shows_then_closes_and_ends_its_thread(self) -> None:
        splash = self._open("Starting")
        self.assertTrue(splash._thread.is_alive())
        splash.set_message("Still starting")
        splash.close()
        self.assertFalse(splash._thread.is_alive())

    def test_close_can_be_called_twice(self) -> None:
        splash = self._open()
        splash.close()
        splash.close()
        self.assertFalse(splash._thread.is_alive())

    def test_min_visible_holds_the_window_up(self) -> None:
        splash = self._open()
        started = time.perf_counter()
        splash.close(min_visible=0.4)
        self.assertGreaterEqual(time.perf_counter() - started, 0.35)
        self.assertFalse(splash._thread.is_alive())

    def test_does_not_become_tkinters_default_root(self) -> None:
        # The app builds Variables/PhotoImages without a master on the main
        # thread; if the splash's interpreter (which lives on its own
        # thread) were picked up as the default root, they would land on
        # the wrong interpreter.
        previous = getattr(tk, "_default_root", None)
        tk._default_root = None
        try:
            splash = self._open()
            self.assertIsNone(tk._default_root)
            splash.close()
        finally:
            tk._default_root = previous

    def test_failure_to_create_the_window_never_blocks_the_caller(self) -> None:
        original = splash_module._SplashWindow

        def broken(_owner):
            raise RuntimeError("no display")

        splash_module._SplashWindow = broken
        try:
            started = time.perf_counter()
            splash = SplashScreen("x")
            self.assertLess(time.perf_counter() - started, 1.5)
            splash.close()
            self.assertFalse(splash._thread.is_alive())
        finally:
            splash_module._SplashWindow = original


if __name__ == "__main__":
    unittest.main()
