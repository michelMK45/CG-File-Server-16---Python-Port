from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from server16_py import kit_preview_worker


class FakeBitmap:
    """Stand-in for System.Drawing.Bitmap: records what was saved instead of
    encoding a PNG, so the worker's own logic runs without pythonnet/the DLL."""

    saved: list[tuple[str, int, int]] = []
    fail_names: set[str] = set()

    def __init__(self, width: int, height: int) -> None:
        self.Width = width
        self.Height = height

    def Save(self, path: str, _fmt) -> None:
        if Path(path).name in self.fail_names:
            raise OSError("GDI+ could not save")
        Path(path).write_bytes(b"png")
        FakeBitmap.saved.append((Path(path).name, self.Width, self.Height))


class FakeGraphics:
    @staticmethod
    def FromImage(_bitmap) -> "FakeGraphics":
        return FakeGraphics()

    def DrawImage(self, *args) -> None:
        pass

    def Dispose(self) -> None:
        pass


class FakeRx3File:
    bitmaps: list[FakeBitmap] = []

    def Load(self, _path: str) -> bool:
        return True

    def GetBitmaps(self) -> list[FakeBitmap]:
        return list(FakeRx3File.bitmaps)


class FakeDdsFile:
    def Load(self, _path: str) -> bool:
        return True


class RxAllTexturesWorkerTests(unittest.TestCase):
    """role="rx3_all_textures" of kit_preview_worker.py: every texture of an
    .rx3 to its own PNG (the Match Assets preview). The FifaLibrary/GDI+ side is
    faked -- the real 32-bit bridge can't run in this suite."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.dll = self.tmp / "FifaLibrary16.dll"
        self.dll.write_bytes(b"dll")
        self.source = self.tmp / "pack.rx3"
        self.source.write_bytes(b"rx3")
        FakeBitmap.saved = []
        FakeBitmap.fail_names = set()
        FakeRx3File.bitmaps = [FakeBitmap(1024, 512), FakeBitmap(128, 128), FakeBitmap(64, 256)]

        drawing = types.ModuleType("System.Drawing")
        drawing.Bitmap = FakeBitmap
        drawing.Graphics = FakeGraphics
        imaging = types.ModuleType("System.Drawing.Imaging")
        imaging.ImageFormat = types.SimpleNamespace(Png="png")
        system = types.ModuleType("System")
        system.Drawing = drawing
        fifalibrary = types.ModuleType("FifaLibrary")
        fifalibrary.Rx3File = FakeRx3File
        fifalibrary.DdsFile = FakeDdsFile
        clr = types.ModuleType("clr")
        clr.AddReference = lambda _path: None
        patcher = mock.patch.dict(sys.modules, {
            "clr": clr, "System": system, "System.Drawing": drawing, "System.Drawing.Imaging": imaging,
            "FifaLibrary": fifalibrary,
        })
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_worker(self, **config) -> tuple[dict, int | None]:
        """Runs main() with `config` (+ source) and returns (stdout JSON, exit code or None)."""
        config_path = self.tmp / "config.json"
        config_path.write_text(json.dumps({"source": str(self.source), **config}), encoding="utf-8")
        out = io.StringIO()
        code = None
        with mock.patch.object(sys, "argv", ["kit_preview_worker.py", str(self.dll), str(config_path)]):
            with contextlib.redirect_stdout(out):
                try:
                    kit_preview_worker.main()
                except SystemExit as exc:
                    code = exc.code
        return json.loads(out.getvalue().strip().splitlines()[-1]), code

    def test_writes_every_texture_as_its_own_numbered_png(self) -> None:
        out_dir = self.tmp / "textures"
        result, code = self.run_worker(role="rx3_all_textures", output_dir=str(out_dir), max_size=2048)
        self.assertIsNone(code)
        self.assertEqual(result["ok"], True)
        self.assertEqual(result["outputs"], [str(out_dir / f"{i}.png") for i in range(3)])
        self.assertTrue(all(Path(path).is_file() for path in result["outputs"]))

    def test_each_texture_is_scaled_down_keeping_its_aspect_ratio(self) -> None:
        self.run_worker(role="rx3_all_textures", output_dir=str(self.tmp / "t"), max_size=256)
        # 1024x512 -> 256x128; 128x128 already fits and is saved as-is; 64x256 fits too.
        self.assertEqual(FakeBitmap.saved, [("0.png", 256, 128), ("1.png", 128, 128), ("2.png", 64, 256)])

    def test_creates_the_output_folder(self) -> None:
        out_dir = self.tmp / "deep" / "er" / "textures"
        result, _ = self.run_worker(role="rx3_all_textures", output_dir=str(out_dir), max_size=256)
        self.assertTrue(result["ok"])
        self.assertTrue(out_dir.is_dir())

    def test_a_texture_that_cannot_be_saved_is_skipped_not_fatal(self) -> None:
        FakeBitmap.fail_names = {"1.png"}
        out_dir = self.tmp / "t"
        result, code = self.run_worker(role="rx3_all_textures", output_dir=str(out_dir), max_size=256)
        self.assertIsNone(code)
        # The index in the name is the texture's real position, so the order survives the gap.
        self.assertEqual(result["outputs"], [str(out_dir / "0.png"), str(out_dir / "2.png")])

    def test_when_no_texture_can_be_saved_it_fails(self) -> None:
        FakeBitmap.fail_names = {"0.png", "1.png", "2.png"}
        result, code = self.run_worker(role="rx3_all_textures", output_dir=str(self.tmp / "t"), max_size=256)
        self.assertEqual(code, 1)
        self.assertFalse(result["ok"])
        self.assertIn("No texture", result["error"])

    def test_a_file_without_textures_fails(self) -> None:
        FakeRx3File.bitmaps = []
        result, code = self.run_worker(role="rx3_all_textures", output_dir=str(self.tmp / "t"), max_size=256)
        self.assertEqual(code, 1)
        self.assertEqual(result, {"ok": False, "error": "Source has no textures"})

    def test_it_needs_an_output_dir(self) -> None:
        result, code = self.run_worker(role="rx3_all_textures", output=str(self.tmp / "x.png"))
        self.assertEqual(code, 1)
        self.assertFalse(result["ok"])
        self.assertIn("output_dir", result["error"])

    # The pre-existing single-output roles must be untouched by the new one.

    def test_rx3_texture_still_writes_only_the_first_bitmap_to_output(self) -> None:
        output = self.tmp / "first.png"
        result, code = self.run_worker(role="rx3_texture", output=str(output), max_size=256)
        self.assertIsNone(code)
        self.assertEqual(result, {"ok": True, "output": str(output)})
        self.assertEqual(FakeBitmap.saved, [("first.png", 256, 128)])

    def test_the_single_output_roles_still_require_output(self) -> None:
        result, code = self.run_worker(role="rx3_texture", max_size=256)
        self.assertEqual(code, 1)
        self.assertFalse(result["ok"])
        self.assertIn("output", result["error"])


if __name__ == "__main__":
    unittest.main()
