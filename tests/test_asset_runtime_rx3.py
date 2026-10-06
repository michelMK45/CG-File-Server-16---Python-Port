from __future__ import annotations

import os
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from server16_py.asset_runtime import AssetRuntime


class RenderRx3TexturesTests(unittest.TestCase):
    """AssetRuntime.render_rx3_textures renders EVERY texture of an .rx3 (a wipe
    pack has about eight) through the 32-bit bridge and caches them, so the Match
    Assets preview and the grid picker never re-run that seconds-long subprocess
    for a file that has not changed."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)
        self.runtime = AssetRuntime(SimpleNamespace(base_dir=self.base))
        self.pack = self.base / "FSW" / "wipe" / "Pack"
        self.pack.mkdir(parents=True)
        self.rx3 = self.pack / "specificwipe_0_996_0.rx3"
        self.rx3.write_bytes(b"rx3")
        self.worker_calls: list[dict] = []
        self.texture_count = 3

    def fake_worker(self, config: dict, worker_name: str = "kit_worker.py") -> dict:
        self.worker_calls.append((worker_name, config))
        out_dir = Path(config["output_dir"])
        out_dir.mkdir(parents=True, exist_ok=True)
        outputs = []
        for index in range(self.texture_count):
            path = out_dir / f"{index}.png"
            path.write_bytes(b"png")
            outputs.append(str(path))
        return {"ok": True, "outputs": outputs}

    def render(self, **kwargs) -> list[Path]:
        with mock.patch("server16_py.asset_runtime.run_fifalibrary_worker", self.fake_worker):
            return self.runtime.render_rx3_textures(self.rx3, cache_key="wipe/Pack/specificwipe_0_996_0", **kwargs)

    def test_asks_the_preview_worker_for_every_texture(self) -> None:
        textures = self.render()
        (worker_name, config), = self.worker_calls
        self.assertEqual(worker_name, "kit_preview_worker.py")
        self.assertEqual(config["role"], "rx3_all_textures")
        self.assertEqual(config["source"], str(self.rx3))
        self.assertEqual([path.name for path in textures], ["0.png", "1.png", "2.png"])
        self.assertTrue(all(path.is_file() for path in textures))

    def test_textures_land_in_a_per_file_cache_folder(self) -> None:
        textures = self.render()
        expected = self.base / "runtime" / "match_asset_previews" / "wipe" / "Pack" / "specificwipe_0_996_0"
        self.assertEqual({path.parent for path in textures}, {expected})

    def test_a_current_cache_skips_the_subprocess_and_keeps_the_texture_order(self) -> None:
        first = self.render()
        second = self.render()
        self.assertEqual(len(self.worker_calls), 1)
        self.assertEqual(second, first)

    def test_reuse_cached_false_always_re_renders(self) -> None:
        self.render()
        self.render(reuse_cached=False)
        self.assertEqual(len(self.worker_calls), 2)

    def test_a_replaced_rx3_is_re_rendered_even_when_it_is_older(self) -> None:
        # A pack swapped for a file that keeps an OLDER modification date: the
        # cache must compare for equality, not "newer than".
        self.render()
        older = self.rx3.stat().st_mtime_ns - 10_000_000_000
        os.utime(self.rx3, ns=(older, older))
        self.render()
        self.assertEqual(len(self.worker_calls), 2)
        self.render()  # ...and that render is cached in turn
        self.assertEqual(len(self.worker_calls), 2)

    def test_a_deleted_texture_png_invalidates_the_cache(self) -> None:
        textures = self.render()
        textures[1].unlink()
        self.render()
        self.assertEqual(len(self.worker_calls), 2)

    def test_a_corrupt_manifest_just_re_renders(self) -> None:
        textures = self.render()
        (textures[0].parent / "manifest.json").write_text("{not json", encoding="utf-8")
        self.render()
        self.assertEqual(len(self.worker_calls), 2)

    def test_a_file_that_now_holds_fewer_textures_leaves_no_stale_pngs(self) -> None:
        self.render()
        self.texture_count = 1
        os.utime(self.rx3, ns=(1, 1))  # a changed source
        textures = self.render()
        self.assertEqual([path.name for path in textures], ["0.png"])
        self.assertEqual(sorted(path.name for path in textures[0].parent.glob("*.png")), ["0.png"])

    def test_a_missing_source_is_never_treated_as_cached(self) -> None:
        self.render()
        self.rx3.unlink()
        self.render()  # the fake bridge still answers: only the cache decision is under test
        self.assertEqual(len(self.worker_calls), 2)

    def test_a_failing_bridge_raises_and_caches_nothing(self) -> None:
        def broken(config, worker_name="kit_worker.py"):
            raise RuntimeError("32-bit Python not found")

        with mock.patch("server16_py.asset_runtime.run_fifalibrary_worker", broken):
            with self.assertRaises(RuntimeError):
                self.runtime.render_rx3_textures(self.rx3, cache_key="wipe/Pack/x")
        self.assertEqual(len(self.render()), 3)  # a later working bridge renders normally
        self.assertEqual(len(self.worker_calls), 1)  # i.e. the failure left no cache behind

    def test_match_asset_textures_use_kind_pack_and_file_in_the_cache_key(self) -> None:
        sub = self.pack / "extra"
        sub.mkdir()
        nested = sub / "Second.RX3"
        nested.write_bytes(b"rx3")
        with mock.patch("server16_py.asset_runtime.run_fifalibrary_worker", self.fake_worker):
            plain = self.runtime.render_match_asset_textures("wipe", self.pack, self.rx3)
            deep = self.runtime.render_match_asset_textures("wipe", self.pack, nested)
        root = self.base / "runtime" / "match_asset_previews" / "wipe" / "Pack"
        self.assertEqual(plain[0].parent, root / "specificwipe_0_996_0")
        self.assertEqual(deep[0].parent, root / "extra" / "Second")

    def test_two_threads_asking_for_the_same_file_render_it_once(self) -> None:
        # The preview panel and the grid picker can both ask at the same time.
        gate = threading.Event()
        original = self.fake_worker

        def slow_worker(config, worker_name="kit_worker.py"):
            gate.wait(2)
            return original(config, worker_name)

        results: list[list[Path]] = []

        def ask() -> None:
            results.append(self.runtime.render_rx3_textures(self.rx3, cache_key="wipe/Pack/shared"))

        with mock.patch("server16_py.asset_runtime.run_fifalibrary_worker", slow_worker):
            threads = [threading.Thread(target=ask) for _ in range(2)]
            for thread in threads:
                thread.start()
            gate.set()
            for thread in threads:
                thread.join(5)
        self.assertEqual(len(self.worker_calls), 1)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0], results[1])


if __name__ == "__main__":
    unittest.main()
