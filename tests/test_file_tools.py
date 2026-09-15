from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from server16_py.file_tools import (
    clear_generated_cache,
    copy_goalpost_sources,
    resolve_goalpost_model_preview_path,
    resolve_goalpost_texture_rx3_path,
)


class CopyGoalpostSourcesTests(unittest.TestCase):
    """copy_goalpost_sources merges files from several independent source
    directories (e.g. a GoalpostModel pack and a separate GoalpostColor
    pack, each selected on its own -- see
    StadiumRuntime.resolve_goalpost_sources) into one destination under a
    single shared manifest, so a later clear_goalpost can evict all of them
    together regardless of which source each file came from."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.dst = self.root / "goalnet"
        self.dst.mkdir(parents=True)
        self.manifest = self.root / ".goalpost_manifest"

    def _make_source(self, name: str, files: dict[str, bytes]) -> Path:
        src = self.root / name
        src.mkdir(parents=True)
        for rel_name, content in files.items():
            (src / rel_name).write_bytes(content)
        return src

    def test_merges_files_from_two_sources_into_one_shared_manifest(self) -> None:
        model = self._make_source("GoalpostModel", {"specificgoalpost_18_0.rx3": b"model"})
        texture = self._make_source("GoalpostColor", {"specificnetsupportpost_0_0_textures.rx3": b"texture"})
        copy_goalpost_sources([model, texture], self.dst, self.manifest)
        self.assertEqual((self.dst / "specificgoalpost_18_0.rx3").read_bytes(), b"model")
        self.assertEqual((self.dst / "specificnetsupportpost_0_0_textures.rx3").read_bytes(), b"texture")
        manifest_lines = set(self.manifest.read_text(encoding="utf-8").splitlines())
        self.assertEqual(manifest_lines, {"specificgoalpost_18_0.rx3", "specificnetsupportpost_0_0_textures.rx3"})

    def test_skips_png_preview_images_from_every_source(self) -> None:
        model = self._make_source("GoalpostModel", {"specificgoalpost_18_0.rx3": b"model", "preview.png": b"img"})
        copy_goalpost_sources([model], self.dst, self.manifest)
        self.assertTrue((self.dst / "specificgoalpost_18_0.rx3").exists())
        self.assertFalse((self.dst / "preview.png").exists())

    def test_a_missing_source_directory_is_silently_skipped(self) -> None:
        texture = self._make_source("GoalpostColor", {"specificnetsupportpost_0_0_textures.rx3": b"texture"})
        missing_model = self.root / "GoalpostModel" / "DoesNotExist"
        copy_goalpost_sources([missing_model, texture], self.dst, self.manifest)
        self.assertEqual((self.dst / "specificnetsupportpost_0_0_textures.rx3").read_bytes(), b"texture")

    def test_a_later_call_evicts_everything_the_previous_call_copied_from_both_sources(self) -> None:
        model = self._make_source("GoalpostModel", {"specificgoalpost_18_0.rx3": b"model"})
        texture = self._make_source("GoalpostColor", {"specificnetsupportpost_0_0_textures.rx3": b"texture"})
        copy_goalpost_sources([model, texture], self.dst, self.manifest)
        # Next stadium has no goalpost override at all -- resolve_goalpost_sources
        # would return the legacy GoalpostGBD source, which is empty/missing
        # here; the point is that BOTH previously-copied files must be gone.
        empty_legacy = self.root / "GoalpostGBD"
        copy_goalpost_sources([empty_legacy], self.dst, self.manifest)
        self.assertFalse((self.dst / "specificgoalpost_18_0.rx3").exists())
        self.assertFalse((self.dst / "specificnetsupportpost_0_0_textures.rx3").exists())
        self.assertFalse(self.manifest.exists())

    def test_a_filename_collision_across_sources_is_not_duplicated_in_the_manifest(self) -> None:
        first = self._make_source("First", {"shared.rx3": b"first"})
        second = self._make_source("Second", {"shared.rx3": b"second"})
        copy_goalpost_sources([first, second], self.dst, self.manifest)
        # Later source wins on disk; the manifest still only lists it once.
        self.assertEqual((self.dst / "shared.rx3").read_bytes(), b"second")
        self.assertEqual(self.manifest.read_text(encoding="utf-8").splitlines(), ["shared.rx3"])

    def test_no_sources_produce_any_files_leaves_no_manifest(self) -> None:
        copy_goalpost_sources([], self.dst, self.manifest)
        self.assertFalse(self.manifest.exists())


class ResolveGoalpostModelPreviewPathTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.model_root = Path(self._tmp.name)

    def test_finds_preview_png_by_convention(self) -> None:
        pack = self.model_root / "1"
        pack.mkdir()
        (pack / "specificgoalpost_18_0.rx3").write_bytes(b"model")
        (pack / "preview.png").write_bytes(b"img")
        result = resolve_goalpost_model_preview_path(self.model_root, "1")
        self.assertEqual(result, pack / "preview.png")

    def test_no_fuzzy_fallback_to_some_other_image_in_the_folder(self) -> None:
        # Matches a real contributor-supplied pack before it's renamed to the
        # "preview" convention -- e.g. a raw screenshot filename like
        # "2026-09-11 09 51 30.png". Deliberately not picked up: see the
        # function's own docstring on why there's no fuzzy fallback here,
        # unlike resolve_stadium_preview_path's.
        pack = self.model_root / "1"
        pack.mkdir()
        (pack / "specificgoalpost_18_0.rx3").write_bytes(b"model")
        (pack / "2026-09-11 09 51 30.png").write_bytes(b"img")
        self.assertIsNone(resolve_goalpost_model_preview_path(self.model_root, "1"))

    def test_none_or_missing_name_returns_none(self) -> None:
        self.assertIsNone(resolve_goalpost_model_preview_path(self.model_root, "None"))
        self.assertIsNone(resolve_goalpost_model_preview_path(self.model_root, ""))
        self.assertIsNone(resolve_goalpost_model_preview_path(self.model_root, "DoesNotExist"))


class ResolveGoalpostTextureRx3PathTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.color_root = Path(self._tmp.name)

    def test_finds_the_rx3_regardless_of_its_exact_filename(self) -> None:
        pack = self.color_root / "Azul"
        pack.mkdir()
        (pack / "specificnetsupportpost_0_0_textures.rx3").write_bytes(b"texture")
        (pack / "goalpost_cm.png").write_bytes(b"img")
        result = resolve_goalpost_texture_rx3_path(self.color_root, "Azul")
        self.assertEqual(result, pack / "specificnetsupportpost_0_0_textures.rx3")

    def test_none_or_missing_name_returns_none(self) -> None:
        self.assertIsNone(resolve_goalpost_texture_rx3_path(self.color_root, "None"))
        self.assertIsNone(resolve_goalpost_texture_rx3_path(self.color_root, ""))
        self.assertIsNone(resolve_goalpost_texture_rx3_path(self.color_root, "DoesNotExist"))

    def test_a_pack_with_no_rx3_at_all_returns_none(self) -> None:
        pack = self.color_root / "Empty"
        pack.mkdir()
        (pack / "goalpost_cm.png").write_bytes(b"img")
        self.assertIsNone(resolve_goalpost_texture_rx3_path(self.color_root, "Empty"))


class ClearGeneratedCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base_dir = Path(self._tmp.name)
        self.runtime_dir = self.base_dir / "runtime"
        self.runtime_dir.mkdir()

    def test_removes_known_cache_subdirs_and_reports_freed_bytes(self) -> None:
        for name in ("goalpost_texture_previews", "kitmix_previews", "kitmix_imports"):
            d = self.runtime_dir / name
            d.mkdir()
            (d / "a.png").write_bytes(b"x" * 10)

        bytes_freed, folders_removed = clear_generated_cache(self.base_dir)

        self.assertEqual(bytes_freed, 30)
        self.assertEqual(folders_removed, 3)
        for name in ("goalpost_texture_previews", "kitmix_previews", "kitmix_imports"):
            self.assertFalse((self.runtime_dir / name).exists())

    def test_removes_orphaned_stadium_extraction_temp_folders(self) -> None:
        leftover = self.runtime_dir / "server16_stad_ab12cd"
        leftover.mkdir()
        (leftover / "model.rx3").write_bytes(b"data")

        bytes_freed, folders_removed = clear_generated_cache(self.base_dir)

        self.assertEqual(bytes_freed, 4)
        self.assertEqual(folders_removed, 1)
        self.assertFalse(leftover.exists())

    def test_never_touches_log_or_settings_files(self) -> None:
        (self.runtime_dir / "server16.log").write_text("log")
        (self.runtime_dir / "settings.json").write_text("{}")

        clear_generated_cache(self.base_dir)

        self.assertTrue((self.runtime_dir / "server16.log").exists())
        self.assertTrue((self.runtime_dir / "settings.json").exists())

    def test_missing_runtime_dir_is_a_no_op(self) -> None:
        empty_base = self.base_dir / "no_runtime_here"
        self.assertEqual(clear_generated_cache(empty_base), (0, 0))

    def test_no_cache_subdirs_present_is_a_no_op(self) -> None:
        self.assertEqual(clear_generated_cache(self.base_dir), (0, 0))


if __name__ == "__main__":
    unittest.main()
