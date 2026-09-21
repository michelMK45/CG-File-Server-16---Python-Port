from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from server16_py.file_tools import (
    clear_generated_cache,
    copy_goalpost_sources,
    resolve_goalpost_model_preview_path,
    resolve_goalpost_texture_rx3_path,
    slot_specific_goalpost_name,
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

    def test_without_a_stadium_id_filenames_are_left_exactly_as_shipped(self) -> None:
        # The legacy per-stadium GoalpostGBD path: its filenames are deliberate
        # overrides of the vanilla names and must never be rewritten.
        legacy = self._make_source("GoalpostGBD", {"specificgoalpost_0_0.rx3": b"legacy", "goalpost_1.rx3": b"tri"})
        copied = copy_goalpost_sources([legacy], self.dst, self.manifest)
        self.assertEqual(sorted(copied), ["goalpost_1.rx3", "specificgoalpost_0_0.rx3"])
        self.assertEqual((self.dst / "specificgoalpost_0_0.rx3").read_bytes(), b"legacy")

    def test_with_a_stadium_id_pack_files_are_installed_under_the_slot_specific_names(self) -> None:
        model = self._make_source("GoalpostModel", {"specificgoalpost_18_0.rx3": b"model", "preview.png": b"img"})
        texture = self._make_source("GoalpostColor", {"specificnetsupportpost_0_0_textures.rx3": b"texture"})
        copied = copy_goalpost_sources([model, texture], self.dst, self.manifest, stadium_id="176")
        expected = {"specificgoalpost_0_176.rx3", "specificnetsupportpost_0_176_textures.rx3"}
        self.assertEqual(set(copied), expected)
        self.assertEqual((self.dst / "specificgoalpost_0_176.rx3").read_bytes(), b"model")
        self.assertEqual((self.dst / "specificnetsupportpost_0_176_textures.rx3").read_bytes(), b"texture")
        # Neither the pack's own name nor the shared *_0_0 fallback name may be left behind,
        # or the engine would have a second, cache-prone path to resolve.
        self.assertFalse((self.dst / "specificgoalpost_18_0.rx3").exists())
        self.assertFalse((self.dst / "specificnetsupportpost_0_0_textures.rx3").exists())
        self.assertEqual(set(self.manifest.read_text(encoding="utf-8").splitlines()), expected)

    def test_two_stadiums_whose_packs_share_a_filename_land_on_different_paths_per_slot(self) -> None:
        # The reported bug: two stadiums picking different goalposts whose packs both ship
        # specificgoalpost_0_0.rx3 / specificnetsupportpost_0_0_textures.rx3 resolved to the
        # very same path, so the engine kept serving the first one it loaded.
        model_a = self._make_source("ModelA", {"specificgoalpost_0_0.rx3": b"model-a"})
        model_b = self._make_source("ModelB", {"specificgoalpost_0_0.rx3": b"model-b"})
        red = self._make_source("Red", {"specificnetsupportpost_0_0_textures.rx3": b"red"})
        blue = self._make_source("Blue", {"specificnetsupportpost_0_0_textures.rx3": b"blue"})
        first = copy_goalpost_sources([model_a, red], self.dst, self.manifest, stadium_id="176")
        second = copy_goalpost_sources([model_b, blue], self.dst, self.manifest, stadium_id="261")
        self.assertTrue(set(first).isdisjoint(second))
        # The second load evicts the first slot's files (they're in the manifest under
        # their slot-specific names) and leaves only its own.
        self.assertFalse((self.dst / "specificgoalpost_0_176.rx3").exists())
        self.assertFalse((self.dst / "specificnetsupportpost_0_176_textures.rx3").exists())
        self.assertEqual((self.dst / "specificgoalpost_0_261.rx3").read_bytes(), b"model-b")
        self.assertEqual((self.dst / "specificnetsupportpost_0_261_textures.rx3").read_bytes(), b"blue")

    def test_reusing_a_slot_replaces_its_content_with_the_new_pick(self) -> None:
        red = self._make_source("Red", {"specificnetsupportpost_0_0_textures.rx3": b"red"})
        blue = self._make_source("Blue", {"specificnetsupportpost_0_0_textures.rx3": b"blue"})
        copy_goalpost_sources([red], self.dst, self.manifest, stadium_id="176")
        copy_goalpost_sources([blue], self.dst, self.manifest, stadium_id="176")
        self.assertEqual((self.dst / "specificnetsupportpost_0_176_textures.rx3").read_bytes(), b"blue")

    def test_unrecognized_pack_files_keep_their_name_and_subfolders_are_preserved(self) -> None:
        model = self._make_source("GoalpostModel", {"goalpost_1.rx3": b"tri", "notes.txt": b"n"})
        nested = model / "sub"
        nested.mkdir()
        (nested / "specificgoalpost_9_0_textures.rx3").write_bytes(b"post-tex")
        copied = copy_goalpost_sources([model], self.dst, self.manifest, stadium_id="261")
        self.assertEqual(
            set(copied),
            {"goalpost_1.rx3", "notes.txt", str(Path("sub") / "specificgoalpost_0_261_textures.rx3")},
        )
        self.assertEqual((self.dst / "sub" / "specificgoalpost_0_261_textures.rx3").read_bytes(), b"post-tex")


class SlotSpecificGoalpostNameTests(unittest.TestCase):
    """The rename table copy_goalpost_sources uses for GoalpostModel/GoalpostColor pack
    files -- mirrors the specific*_0_{stadiumID} candidates in goalnet.lua's
    GetRMGoalPost/GetRMGoalPostTex/GetRMSupportPost."""

    def test_model_files_map_to_specificgoalpost_0_slot_whatever_team_id_the_pack_used(self) -> None:
        for shipped in ("specificgoalpost_18_0.rx3", "specificgoalpost_0_0.rx3", "specificgoalpost_9_0.rx3", "specificgoalpost_10_0.rx3"):
            with self.subTest(shipped=shipped):
                self.assertEqual(slot_specific_goalpost_name(shipped, "176"), "specificgoalpost_0_176.rx3")
        self.assertEqual(slot_specific_goalpost_name("specificgoalpost_0_0.rx3", "261"), "specificgoalpost_0_261.rx3")

    def test_texture_files_keep_their_textures_suffix(self) -> None:
        self.assertEqual(
            slot_specific_goalpost_name("specificnetsupportpost_0_0_textures.rx3", "176"),
            "specificnetsupportpost_0_176_textures.rx3",
        )
        self.assertEqual(
            slot_specific_goalpost_name("specificgoalpost_0_0_textures.rx3", "261"),
            "specificgoalpost_0_261_textures.rx3",
        )

    def test_matching_is_case_insensitive_and_output_is_lowercase(self) -> None:
        self.assertEqual(slot_specific_goalpost_name("SpecificGoalPost_9_0.RX3", "176"), "specificgoalpost_0_176.rx3")

    def test_anything_else_is_not_renamed(self) -> None:
        for other in ("goalpost_1.rx3", "goalpost_0_textures.rx3", "specificgoalnet_0_0.rx3", "specificgoalpost_0_0.txt", "preview.rx3", "specificgoalpost_x_0.rx3"):
            with self.subTest(other=other):
                self.assertIsNone(slot_specific_goalpost_name(other, "176"))


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
