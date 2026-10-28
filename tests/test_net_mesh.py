from __future__ import annotations

import json
import os
import struct
import tempfile
import unittest
import zlib
from pathlib import Path

from PIL import Image

from server16_py.file_tools import clear_goalpost, copy_goalpost_sources
from server16_py.net_mesh import (
    GOALNET_CM_INDEX,
    GOALNET_NM_INDEX,
    NET_MESH_TEXTURE_COUNT,
    build_net_mesh_rx3,
    decompress_chunkzip,
    generate_normal_map,
    pack_has_net_mesh,
    resolve_net_mesh_images,
    resolve_net_mesh_preview_path,
    slot_net_mesh_name,
)


def make_chunkzip(payload: bytes, chunk_size: int = 64, align: int = 16) -> bytes:
    """Same layout as the vanilla files (verified against 24 of them, 1 to 11 chunks)."""
    chunks = [payload[i:i + chunk_size] for i in range(0, len(payload), chunk_size)]
    out = bytearray(b"chunkzip")
    out += struct.pack(">IIIIII", 2, len(payload), chunk_size, len(chunks), align, 0)
    for index, chunk in enumerate(chunks):
        while (len(out) + 8) % align:
            out += b"\0"
        if index % 2:
            data, kind = chunk, 0  # stored
        else:
            compressor = zlib.compressobj(9, zlib.DEFLATED, -15)
            data, kind = compressor.compress(chunk) + compressor.flush(), 1
        out += struct.pack(">II", len(data), kind) + data
    return bytes(out)


def write_pattern(path: Path, size: int = 32) -> Path:
    """A grid of opaque strands over transparent holes, like the real patterns."""
    img = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    for i in range(size):
        for j in (0, size // 2):
            img.putpixel((i, j), (255, 255, 255, 255))
            img.putpixel((j, i), (255, 255, 255, 255))
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)
    return path


class DecompressChunkzipTests(unittest.TestCase):
    def test_round_trips_deflated_and_stored_chunks(self) -> None:
        payload = b"RX3l" + bytes(range(256)) * 3
        self.assertEqual(decompress_chunkzip(make_chunkzip(payload)), payload)

    def test_non_chunkzip_data_is_returned_unchanged(self) -> None:
        self.assertEqual(decompress_chunkzip(b"RX3l\x04\0\0\0"), b"RX3l\x04\0\0\0")

    def test_size_mismatch_raises(self) -> None:
        data = bytearray(make_chunkzip(b"RX3l" * 10))
        data[12:16] = struct.pack(">I", 999)
        with self.assertRaises(ValueError):
            decompress_chunkzip(bytes(data))


class ResolveNetMeshFilesTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.pack = self.root / "Hex"
        self.pack.mkdir()

    def test_net_png_is_the_pattern_and_net_nm_the_normal_map(self) -> None:
        for name in ("net.png", "net_nm.png", "preview.png", "other.png"):
            (self.pack / name).write_bytes(b"x")
        self.assertEqual(resolve_net_mesh_images(self.pack), (self.pack / "net.png", self.pack / "net_nm.png"))

    def test_a_lone_image_with_any_name_is_the_pattern(self) -> None:
        (self.pack / "Hex1.png").write_bytes(b"x")
        (self.pack / "preview.jpg").write_bytes(b"x")
        self.assertEqual(resolve_net_mesh_images(self.pack), (self.pack / "Hex1.png", None))

    def test_several_unnamed_images_are_ambiguous(self) -> None:
        (self.pack / "a.png").write_bytes(b"x")
        (self.pack / "b.png").write_bytes(b"x")
        self.assertEqual(resolve_net_mesh_images(self.pack), (None, None))
        self.assertFalse(pack_has_net_mesh(self.pack))

    def test_rx3_only_pack_is_installable(self) -> None:
        (self.pack / "goalnet_1.rx3").write_bytes(b"RX3l")
        self.assertTrue(pack_has_net_mesh(self.pack))
        self.assertIsNone(resolve_net_mesh_preview_path(self.root, "Hex"))

    def test_preview_prefers_preview_image_then_the_pattern(self) -> None:
        (self.pack / "net.png").write_bytes(b"x")
        self.assertEqual(resolve_net_mesh_preview_path(self.root, "Hex"), self.pack / "net.png")
        (self.pack / "preview.png").write_bytes(b"x")
        self.assertEqual(resolve_net_mesh_preview_path(self.root, "Hex"), self.pack / "preview.png")

    def test_none_and_missing_packs_have_no_preview(self) -> None:
        self.assertIsNone(resolve_net_mesh_preview_path(self.root, "None"))
        self.assertIsNone(resolve_net_mesh_preview_path(self.root, ""))
        self.assertIsNone(resolve_net_mesh_preview_path(self.root, "Missing"))
        self.assertFalse(pack_has_net_mesh(self.root / "Missing"))

    def test_slot_name_matches_goalnet_lua_get_rm_net_shape(self) -> None:
        self.assertEqual(slot_net_mesh_name("261"), "specificgoalnet_0_261.rx3")


class GenerateNormalMapTests(unittest.TestCase):
    def test_flat_areas_point_straight_out_and_strand_edges_tilt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pattern = write_pattern(Path(tmp) / "net.png")
            out = generate_normal_map(pattern, Path(tmp) / "nm.png")
            with Image.open(out) as img:
                self.assertEqual(img.mode, "RGBA")
                self.assertEqual(img.size, (32, 32))
                r, g, b, a = img.getpixel((8, 8))  # middle of a hole
                self.assertEqual((r, g, b, a), (128, 128, 255, 255))
                edge = img.getpixel((8, 2))  # just beside a horizontal strand
                self.assertNotEqual(edge[1], 128)
                self.assertEqual(img.getchannel("B").getextrema(), (255, 255))


class BuildNetMeshRx3Tests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        self.pack = root / "NetMesh" / "Hex"
        self.pack.mkdir(parents=True)
        self.cache = root / "cache"
        self.template = root / "goalnet_0.rx3"
        self.template_payload = b"RX3l" + bytes(200)
        self.template.write_bytes(make_chunkzip(self.template_payload))
        self.calls: list[dict] = []

    def fake_worker(self, config: dict, worker_name: str) -> dict:
        self.assertEqual(worker_name, "net_mesh_worker.py")
        self.assertEqual(Path(config["template"]).read_bytes(), self.template_payload)
        for entry in config["replace"]:
            self.assertTrue(Path(entry["image"]).is_file(), entry)
        self.calls.append(config)
        Path(config["output"]).write_bytes(b"built")
        return {"ok": True, "output": config["output"]}

    def build(self) -> Path:
        return build_net_mesh_rx3(self.pack, self.template, self.cache, self.fake_worker)

    def test_ready_made_rx3_is_used_as_is_without_the_worker(self) -> None:
        (self.pack / "goalnet_1.rx3").write_bytes(b"RX3l")
        self.assertEqual(self.build(), self.pack / "goalnet_1.rx3")
        self.assertEqual(self.calls, [])

    def test_pattern_replaces_goalnet_cm_and_a_generated_goalnet_nm(self) -> None:
        write_pattern(self.pack / "net.png")
        built = self.build()
        self.assertEqual(built.read_bytes(), b"built")
        (config,) = self.calls
        self.assertEqual(config["expected_count"], NET_MESH_TEXTURE_COUNT)
        self.assertEqual([e["index"] for e in config["replace"]], [GOALNET_CM_INDEX, GOALNET_NM_INDEX])
        self.assertEqual(config["replace"][0]["image"], str(self.pack / "net.png"))
        # Temporaries (decompressed template, generated normal map) are gone afterwards.
        self.assertEqual(sorted(p.name for p in built.parent.iterdir()), ["goalnet.rx3", "source.json"])

    def test_shipped_normal_map_is_used_instead_of_a_generated_one(self) -> None:
        write_pattern(self.pack / "net.png")
        write_pattern(self.pack / "net_nm.png")
        self.build()
        self.assertEqual(self.calls[0]["replace"][1]["image"], str(self.pack / "net_nm.png"))

    def test_second_build_reuses_the_cache_until_the_pattern_changes(self) -> None:
        pattern = write_pattern(self.pack / "net.png")
        first = self.build()
        self.assertEqual(self.build(), first)
        self.assertEqual(len(self.calls), 1)
        st = pattern.stat()
        os.utime(pattern, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000))
        self.build()
        self.assertEqual(len(self.calls), 2)
        stamp = json.loads((first.parent / "source.json").read_text(encoding="utf-8"))
        self.assertIn(str(pattern), stamp)

    def test_failed_build_leaves_no_stamp_so_the_next_try_rebuilds(self) -> None:
        write_pattern(self.pack / "net.png")

        def failing(config: dict, worker_name: str) -> dict:
            raise RuntimeError("Rx3File.Save() returned False")

        with self.assertRaises(RuntimeError):
            build_net_mesh_rx3(self.pack, self.template, self.cache, failing)
        self.assertFalse((self.cache / "Hex" / "source.json").exists())
        self.assertFalse((self.cache / "Hex" / "template.rx3").exists())
        self.build()
        self.assertEqual(len(self.calls), 1)

    def test_pack_without_pattern_or_rx3_raises(self) -> None:
        with self.assertRaises(FileNotFoundError):
            self.build()

    def test_missing_template_raises(self) -> None:
        write_pattern(self.pack / "net.png")
        self.template.unlink()
        with self.assertRaises(FileNotFoundError):
            self.build()


class CopyGoalpostSourcesExtraFilesTests(unittest.TestCase):
    def test_extra_file_is_installed_under_its_name_and_evicted_by_the_next_clear(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            model = root / "Model"
            model.mkdir()
            (model / "specificgoalpost_0_0.rx3").write_bytes(b"model")
            built = root / "goalnet.rx3"
            built.write_bytes(b"net")
            dst = root / "goalnet"
            manifest = root / ".goalpost_manifest"
            copied = copy_goalpost_sources(
                [model], dst, manifest, stadium_id="176", extra_files=[(built, "specificgoalnet_0_176.rx3")],
            )
            self.assertEqual(copied, ["specificgoalpost_0_176.rx3", "specificgoalnet_0_176.rx3"])
            self.assertEqual((dst / "specificgoalnet_0_176.rx3").read_bytes(), b"net")
            clear_goalpost(dst, manifest)
            self.assertFalse((dst / "specificgoalnet_0_176.rx3").exists())
            self.assertFalse((dst / "specificgoalpost_0_176.rx3").exists())

    def test_missing_extra_file_is_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            copied = copy_goalpost_sources([], root / "goalnet", root / ".m", extra_files=[(root / "nope.rx3", "x.rx3")])
            self.assertEqual(copied, [])


if __name__ == "__main__":
    unittest.main()
