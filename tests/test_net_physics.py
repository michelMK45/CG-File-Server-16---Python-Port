from __future__ import annotations

import json
import struct
import tempfile
import threading
import unittest
import unittest.mock
from pathlib import Path

from server16_py import net_physics as np_
from server16_py.net_physics import (
    H_MASS, H_SEAM, H_ST, H_TENSION, H_WEIGHT, NetPhysicsRuntime, find_records, load_presets,
    parse_record, physics_level, supports_of, targets_for,
)

BASE = 0x10000000


def slot(hash_lo: int, value: float) -> bytes:
    """One 24-byte attribdb slot: [key hash 8][value 4][pad 4][flags 8]."""
    return struct.pack("<II", hash_lo, 0xABCD0000 | (hash_lo & 0xFFFF)) + struct.pack("<f", value) + b"\0" * 4 + b"\x01" * 8


def box4(mass: float, tension: float, weight: float, st: float) -> bytes:
    return slot(H_MASS, mass) + slot(H_TENSION, tension) + slot(H_WEIGHT, weight) + slot(H_ST, st)


def box2(mass: float, seam: float, weight: float, st: float, tension: float) -> bytes:
    return slot(H_MASS, mass) + slot(H_SEAM, seam) + slot(H_WEIGHT, weight) + slot(H_ST, st) + slot(H_TENSION, tension)


class FakeMemory:
    def __init__(self, image: bytes) -> None:
        self.buf = bytearray(image)
        self.process_id = 4242
        self.process_handle = 1
        self.writes: list[tuple[int, bytes]] = []

    def is_open(self) -> bool:
        return True

    def read_process_memory(self, address: int, size: int) -> bytes:
        o = address - BASE
        if o < 0 or o + size > len(self.buf):
            raise OSError(hex(address))
        return bytes(self.buf[o:o + size])

    def read_process_memory_partial(self, address: int, size: int) -> bytes:
        o = max(0, address - BASE)
        return bytes(self.buf[o:o + size])

    def write_process_memory(self, address: int, payload: bytes) -> None:
        self.writes.append((address, payload))
        o = address - BASE
        self.buf[o:o + len(payload)] = payload

    def close(self) -> None:
        pass


class SharedMemoryObject:
    """The app's shared Memory: only its process id and is_open may be used (poll_process closes and
    reopens its handle every 500 ms), never its handle for reads or writes."""

    process_id = 4242

    def is_open(self) -> bool:
        return True

    def __getattr__(self, name):
        raise AssertionError(f"the shared Memory object was used for {name}")


def image() -> tuple[bytes, int, int]:
    """Filler, a box4 record, a stray 0.05 float, a box2 record. Returns (bytes, tension4, tension2)."""
    data = b"\x11" * 0x100
    t4 = BASE + len(data) + 0x18 + 8
    data += box4(20.0, 0.05, 23.0, 0.0)
    data += b"\x22" * 0x40 + struct.pack("<f", 0.05) + b"\x22" * 0x44  # a lone 0.05 is not a record
    t2 = BASE + len(data) + 4 * 0x18 + 8
    data += box2(0.005, 1.0, 8.0, 1.0, 0.05)
    data += b"\x33" * 0x100
    return data, t4, t2


class ParsingTests(unittest.TestCase):
    def test_net_value_fields(self) -> None:
        self.assertEqual(physics_level("1,2,4,0,0"), 0)
        self.assertEqual(physics_level("1,2,4,0,0,1,3"), 3)
        self.assertEqual(physics_level("1,2,4,0,0,0,2"), 2)
        self.assertEqual(physics_level("1,2,4,0,0,1,1,0"), 0)  # author's 8-field rope flags: no physics
        self.assertEqual(supports_of("1,2,4,0,0"), 4)
        self.assertIsNone(supports_of(""))

    def test_records_are_found_by_hash_not_by_value(self) -> None:
        data, t4, t2 = image()
        mem = FakeMemory(data)
        records = find_records([(BASE, len(data))], mem.read_process_memory_partial)
        self.assertEqual([(r.tension_addr, r.family) for r in records], [(t4, "box4"), (t2, "box2")])
        r4 = records[0]
        self.assertEqual(set(r4.slots), {"mass", "tension", "weight", "st"})
        self.assertEqual(r4.slots["mass"], t4 - 0x18)
        self.assertEqual(r4.slots["weight"], t4 + 0x18)
        self.assertEqual(records[1].slots["seam"], t2 - 0x48)
        self.assertEqual(r4.hashes["tension"] & 0xFFFFFFFF, H_TENSION)

    def test_seam_after_the_tension_is_a_two_supports_record(self) -> None:
        # Order seen live on FIP (the author's modified attribdb): mass, tension, seam, weight, st.
        data = b"\0" * 0x40 + slot(H_MASS, 0.002) + slot(H_TENSION, 0.05) + slot(H_SEAM, 1.0) + slot(H_WEIGHT, 1.9) + slot(H_ST, 1.0) + b"\0" * 0x80
        t = BASE + 0x40 + 0x18 + 8
        records = find_records([(BASE, len(data))], FakeMemory(data).read_process_memory_partial)
        self.assertEqual([(r.tension_addr, r.family, sorted(r.slots)) for r in records],
                         [(t, "box2", ["mass", "seam", "st", "tension", "weight"])])
        rec = records[0]
        rec.original = {"mass": 0.002, "tension": 0.05, "seam": 1.0, "weight": 1.9, "st": 1.0}
        self.assertNotIn("st", targets_for(rec, 3, 2, load_presets(None)))  # box2: Support_Tension left alone

    def test_a_tension_hash_without_its_mass_slot_is_not_a_record(self) -> None:
        data = b"\0" * 0x40 + slot(H_TENSION, 0.05) + b"\0" * 0x40
        window = data
        self.assertIsNone(parse_record(window, BASE, BASE + 0x40 + 8))

    def test_record_across_two_chunks(self) -> None:
        data, t4, _t2 = image()
        with unittest.mock.patch.object(np_, "SCAN_CHUNK", 0x120):
            records = find_records([(BASE, len(data))], FakeMemory(data).read_process_memory_partial)
        self.assertIn(t4, [r.tension_addr for r in records])


class PresetTests(unittest.TestCase):
    def test_defaults_and_json_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            exedir = Path(tmp)
            table = load_presets(exedir)
            self.assertEqual(table.preset(3, 4).tension, 0.08)
            self.assertEqual(table.preset(3, 2).tension, 0.10)
            self.assertEqual(table.support_tension(3, 2), 0.5)
            (exedir / "FSW").mkdir()
            (exedir / "FSW" / "net_physics.json").write_text(json.dumps({
                "all": {"tense": {"tension": 0.2}},
                "3": {"loose": {"mass": 0.007, "seam_relaxation": 0.1, "support_tension": 0.3}},
            }), encoding="utf-8")
            table = load_presets(exedir)
            self.assertEqual((table.preset(3, 4).tension, table.preset(3, 4).weighting), (0.2, 5.0))
            loose3 = table.preset(1, 3)
            self.assertEqual((loose3.mass, loose3.tension, loose3.seam_relaxation), (0.007, -0.06, 0.1))
            self.assertEqual(table.support_tension(1, 3), 0.3)
            self.assertEqual(table.preset(3, 3).tension, 0.2)  # a block inherits presets it does not name


class WriteTests(unittest.TestCase):
    def setUp(self) -> None:
        data, self.t4, self.t2 = image()
        self.mem = FakeMemory(data)
        self.records = find_records([(BASE, len(data))], self.mem.read_process_memory_partial)
        self.table = load_presets(None)
        self.logs: list[str] = []

    def value(self, addr: int) -> float:
        return struct.unpack("<f", self.mem.read_process_memory(addr, 4))[0]

    def test_tense_writes_only_hash_checked_slots(self) -> None:
        r4, r2 = self.records
        for rec in self.records:
            rec.original = np_.read_values(self.mem, rec)
            self.assertTrue(np_.write_record(self.mem, rec, targets_for(rec, 3, 4, self.table), self.logs.append))
        self.assertAlmostEqual(self.value(r4.slots["tension"]), 0.08, places=6)
        self.assertAlmostEqual(self.value(r4.slots["mass"]), 0.002, places=6)
        self.assertEqual(self.value(r4.slots["weight"]), 5.0)
        self.assertEqual(self.value(r4.slots["st"]), 0.0)
        self.assertEqual(self.value(r2.slots["st"]), 1.0)     # box2 Support_Tension left alone
        self.assertEqual(self.value(r2.slots["seam"]), 1.0)   # seam not configured: original kept
        written = {addr for addr, _ in self.mem.writes}
        allowed = {a for rec in self.records for a in rec.slots.values()}
        self.assertTrue(written <= allowed)

    def test_level_zero_restores_the_originals(self) -> None:
        r4 = self.records[0]
        r4.original = np_.read_values(self.mem, r4)
        np_.write_record(self.mem, r4, targets_for(r4, 1, None, self.table), self.logs.append)
        np_.write_record(self.mem, r4, targets_for(r4, 0, None, self.table), self.logs.append)
        self.assertEqual(np_.read_values(self.mem, r4), r4.original)

    def test_a_changed_slot_hash_stops_the_write(self) -> None:
        r4 = self.records[0]
        r4.original = np_.read_values(self.mem, r4)
        o = r4.slots["weight"] - 8 - BASE
        self.mem.buf[o:o + 4] = b"\0\0\0\0"  # the memory was reused
        ok = np_.write_record(self.mem, r4, targets_for(r4, 3, 4, self.table), self.logs.append)
        self.assertFalse(ok)
        self.assertNotIn(r4.slots["weight"], [a for a, _ in self.mem.writes])
        self.assertIn("slot hash changed", self.logs[-1])


class RuntimeTests(unittest.TestCase):
    def test_request_searches_writes_and_logs(self) -> None:
        data, t4, _t2 = image()
        mem = FakeMemory(data)
        logs: list[str] = []
        done = threading.Event()

        def log(line: str) -> None:
            logs.append(line)
            if "written to" in line:
                done.set()

        runtime = NetPhysicsRuntime(SharedMemoryObject(), lambda: None, log, io_factory=lambda pid: mem)
        with unittest.mock.patch.object(np_, "private_regions", lambda _h: iter([(BASE, len(data), 0x04)])):
            runtime.request("1,2,4,0,0,0,3", "[stadiumnetname] Anfield")
            self.assertTrue(done.wait(5))
        self.assertAlmostEqual(struct.unpack("<f", mem.read_process_memory(t4, 4))[0], 0.08, places=6)
        text = "\n".join(logs)
        self.assertIn("tense (level 3, supports 4) for [stadiumnetname] Anfield", text)
        self.assertIn("search 1: 2 records", text)
        self.assertIn("written to 2 of 2 records", text)

    def test_level_zero_before_any_write_does_nothing(self) -> None:
        mem = FakeMemory(image()[0])
        runtime = NetPhysicsRuntime(SharedMemoryObject(), lambda: None, lambda _l: None, io_factory=lambda pid: mem)
        runtime.request("1,2,4,0,0", "x")
        self.assertIsNone(runtime._worker)
        self.assertEqual(mem.writes, [])


class IniLinesTests(unittest.TestCase):
    def test_active_lines_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            exedir = Path(tmp)
            (exedir / "cl.ini").write_text("SOCCERNET_BOX_NORMAL_NORMAL_4_SUPPORTS=1\n;SOCCERNET_BOX_DEEP_TENSE_2_SUPPORTS=1\n// net_id=3\n", encoding="utf-8")
            (exedir / "rna.ini").write_text("[LOCALE]\nSKU=WW\n", encoding="utf-8")
            self.assertEqual(np_.active_net_ini_lines(exedir),
                             {"cl.ini": ["SOCCERNET_BOX_NORMAL_NORMAL_4_SUPPORTS=1"], "rna.ini": []})

    def test_author_line_active_needs_the_uncommented_line_with_1(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            exedir = Path(tmp)
            self.assertFalse(np_.author_line_active(exedir))  # no inis at all
            (exedir / "cl.ini").write_text(";SOCCERNET_BOX_NORMAL_NORMAL_4_SUPPORTS=1\n", encoding="utf-8")
            self.assertFalse(np_.author_line_active(exedir))
            (exedir / "cl.ini").write_text("soccernet_box_normal_normal_4_supports = 0\n", encoding="utf-8")
            self.assertFalse(np_.author_line_active(exedir))
            (exedir / "rna.ini").write_text("[LOCALE]\nSOCCERNET_BOX_NORMAL_NORMAL_4_SUPPORTS=1\n", encoding="utf-8")
            self.assertTrue(np_.author_line_active(exedir))

    def test_add_author_line_keeps_the_file_and_a_backup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            exedir = Path(tmp)
            (exedir / "cl.ini").write_bytes(b"SIMPLECLOTH=7")  # the FIP file: no trailing newline
            np_.add_author_line(exedir)
            self.assertEqual((exedir / "cl.ini").read_bytes(),
                             b"SIMPLECLOTH=7\r\nSOCCERNET_BOX_NORMAL_NORMAL_4_SUPPORTS=1\r\n")
            self.assertEqual((exedir / "cl.ini.cgfs16.bak").read_bytes(), b"SIMPLECLOTH=7")
            self.assertTrue(np_.author_line_active(exedir))

    def test_add_author_line_creates_a_missing_cl_ini(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            exedir = Path(tmp)
            np_.add_author_line(exedir)
            self.assertEqual((exedir / "cl.ini").read_bytes(), b"SOCCERNET_BOX_NORMAL_NORMAL_4_SUPPORTS=1\r\n")
            self.assertFalse((exedir / "cl.ini.cgfs16.bak").exists())


if __name__ == "__main__":
    unittest.main()
