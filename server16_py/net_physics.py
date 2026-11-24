"""Goal-net physics preset per stadium, written into FIFA's resident attribdb "soccernet" records.

Port of the forum author's Server 16 build (``net_physics.py``, 2026-11-13; docs/net-physics.md),
same idea and same values, with these deliberate differences:

- records are found by the attribdb **field hash** in front of each value (the author searched for
  known float values first), so any attribdb works, modified or stock, and a stray float equal to a
  preset value can never be taken for a record;
- only slots whose hash was checked are written (the author's fallback that wrote by fixed offsets
  when the hashes were missing is gone), and every write re-reads the hash right before writing;
- no absolute addresses from the author's PC, no address cache file, no 6-hour watcher: the search
  runs when a match is being prepared and is retried until shortly after the TV bumper page;
- a verbose log (what is found, where, the hashes, every value before/after, a read-back at the TV
  bumper page) so a failing install can be diagnosed from server16.log alone.

The author's findings (not yet confirmed on our side):
- The attribdb soccernet presets (mass / tension / support weighting...) stay resident in FIFA's
  memory; the match's net is built from them when the match loads, so rewriting them *before* the
  load changes the net. Writing later has no effect.
- With exactly ONE net line active in cl.ini or rna.ini, ``SOCCERNET_BOX_NORMAL_NORMAL_4_SUPPORTS=1``,
  the engine builds every net that is not a 2-supports net from the "box4" records, whatever its
  depth -- so the preset applies to every depth (our NTTT tension selector only acts on "Tri deep").
- A 2-supports net needs the "box2" values; with the 4-supports line active it is still built from
  the box4 records, so for a 2-supports stadium the box2 values go into every record.

Memory layout of a record: each attribdb value sits in a 24-byte slot [key hash 8][value 4][pad 4][8],
the hash's low 32 bits identify the field (H_* below, found by the author). Seen from the tension value:
  box4: mass slot right before the tension (-0x18); weighting / Support_Tension slots after it.
  box2: mass -0x60, seam relaxation -0x48, weighting -0x30, Support_Tension -0x18, tension.

Net value: ``down,high,rig,shape,tension,ropes,physics`` ([stadiumnetname]/[stadiumnetid]); physics
(7th field) 0 game default, 1 loose, 2 normal, 3 tense; the number of supports is the 3rd field (rig).
Optional ``FSW/net_physics.json`` (the author's format): {"all": {"loose": {"mass": .., "tension": ..,
"weighting": .., "support_tension": .., "seam_relaxation": ..}, "normal": {..}, "tense": {..}},
"2": {...}, "7": {...}} -- one block per number of supports, missing fields keep the defaults.
"""
from __future__ import annotations

import ctypes
import json
import re
import struct
import threading
import time
from ctypes import wintypes
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Iterator

PHYSICS_FIELD = 6  # index of the physics level in the comma-separated net value
LEVEL_NAMES = {1: "loose", 2: "normal", 3: "tense"}

# Defaults: (mass, tension, weighting) -- the author's values.
DEFAULT_PRESETS = {
    "loose": (0.002, -0.06, 10.0),
    "normal": (0.001, -0.001, 10.0),
    "tense": (0.002, 0.08, 5.0),
}
DEFAULT_BOX2_PRESETS = {
    "loose": (0.002, 0.05, 1.9),
    "normal": (0.001, 0.06, 5.7),
    "tense": (0.002, 0.10, 11.0),
}
# EATech_Support_Tension per number of supports (box4 records only): stock 0; a 2-supports net
# collapses with 0 and is over-stretched with 1 (author).
DEFAULT_SUPPORT_TENSION = {"base": 0.0, "by_supports": {2: 0.5}}

# Low 32 bits of the attribdb key hash in front of each value (author).
H_MASS, H_TENSION, H_SEAM, H_WEIGHT, H_ST = 0x4BCA27D6, 0xCE490447, 0x216BD386, 0x18511C59, 0x76FCEC38
HASH_NAMES = {H_MASS: "mass", H_TENSION: "tension", H_SEAM: "seam", H_WEIGHT: "weight", H_ST: "st"}
SLOT = 0x18
BOX2_SLOTS = (("mass", -0x60), ("seam", -0x48), ("weight", -0x30), ("st", -0x18))
WINDOW_BEFORE, WINDOW_AFTER = 0x70, 0x70  # bytes read around a tension value to parse its record

SCAN_CHUNK = 16 << 20
RETRY_SECONDS = 5.0
AFTER_BUMPER_SECONDS = 60.0  # keep looking this long after the TV bumper page (diagnostics)
MAX_REQUEST_SECONDS = 300.0
MAX_LOGGED_RECORDS = 40


def F(value: float) -> bytes:
    return struct.pack("<f", value)


def _f(raw: bytes) -> float:
    return struct.unpack("<f", raw)[0]


def _parts(net_value: str | None) -> list[str]:
    return [p.strip() for p in (net_value or "").split(",")] if net_value else []


def physics_level(net_value: str | None) -> int:
    """7th field of the net value (0..3); 0 when absent. The author's 8-field rope-flag test format
    has no physics field."""
    parts = _parts(net_value)
    if len(parts) >= 8 and all(p in {"0", "1"} for p in parts[5:8]):
        return 0
    if len(parts) > PHYSICS_FIELD and parts[PHYSICS_FIELD] in {"1", "2", "3"}:
        return int(parts[PHYSICS_FIELD])
    return 0


def supports_of(net_value: str | None) -> int | None:
    parts = _parts(net_value)
    try:
        return int(parts[2])
    except (IndexError, ValueError):
        return None


# ---------------------------------------------------------------------------------------------
# Presets (FSW/net_physics.json)
# ---------------------------------------------------------------------------------------------
@dataclass
class Preset:
    mass: float
    tension: float
    weighting: float
    support_tension: float | None = None  # None: the per-supports default
    seam_relaxation: float | None = None  # None: leave the record's own value


@dataclass
class PresetTable:
    by_supports: dict = field(default_factory=dict)  # supports (int) or "all" -> {name: Preset}
    support_tension_base: float = DEFAULT_SUPPORT_TENSION["base"]
    support_tension_by_supports: dict = field(default_factory=lambda: dict(DEFAULT_SUPPORT_TENSION["by_supports"]))
    source: str = "defaults"

    def preset(self, level: int, supports: int | None) -> Preset:
        name = LEVEL_NAMES[level]
        if supports is not None and supports in self.by_supports and name in self.by_supports[supports]:
            return self.by_supports[supports][name]
        if supports == 2:
            return self.by_supports[2][name]
        return self.by_supports["all"][name]

    def support_tension(self, level: int, supports: int | None) -> float:
        if level in LEVEL_NAMES:
            own = self.preset(level, supports).support_tension
            if own is not None:
                return own
        if supports is not None and supports in self.support_tension_by_supports:
            return self.support_tension_by_supports[supports]
        return self.support_tension_base


def _num(value) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def load_presets(exedir: Path | None, log: Callable[[str], None] = lambda _m: None) -> PresetTable:
    table = PresetTable()
    table.by_supports["all"] = {n: Preset(*v) for n, v in DEFAULT_PRESETS.items()}
    table.by_supports[2] = {n: Preset(*v) for n, v in DEFAULT_BOX2_PRESETS.items()}
    if exedir is None:
        return table
    path = Path(exedir) / "FSW" / "net_physics.json"
    if not path.is_file():
        return table
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))  # Notepad may add a BOM
    except (OSError, ValueError) as exc:
        log(f"Net physics: {path} not read ({exc}); defaults used")
        return table
    if not isinstance(data, dict):
        log(f"Net physics: {path} is not a JSON object; defaults used")
        return table
    for key, block in data.items():
        if not isinstance(block, dict) or not (key == "all" or str(key).strip().isdigit()):
            log(f"Net physics: {path.name}: key {key!r} ignored (expected \"all\" or a number of supports)")
            continue
        slot = "all" if key == "all" else int(key)
        base_table = table.by_supports.get(slot) or table.by_supports["all"]
        own = dict(table.by_supports.get(slot, {}))
        for name in LEVEL_NAMES.values():
            entry = block.get(name)
            if not isinstance(entry, dict):
                continue
            base = base_table.get(name) or table.by_supports["all"][name]
            weighting = entry.get("weighting", entry.get("weight"))
            own[name] = Preset(
                mass=_num(entry.get("mass")) if _num(entry.get("mass")) is not None else base.mass,
                tension=_num(entry.get("tension")) if _num(entry.get("tension")) is not None else base.tension,
                weighting=_num(weighting) if _num(weighting) is not None else base.weighting,
                support_tension=_num(entry.get("support_tension")),
                seam_relaxation=_num(entry.get("seam_relaxation")),
            )
        for name in LEVEL_NAMES.values():  # a block that names only some presets inherits the rest
            own.setdefault(name, base_table.get(name) or table.by_supports["all"][name])
        table.by_supports[slot] = own
    table.source = str(path)
    return table


# ---------------------------------------------------------------------------------------------
# Record parsing
# ---------------------------------------------------------------------------------------------
@dataclass
class Record:
    tension_addr: int
    family: str                                   # "box4" | "box2"
    slots: dict[str, int]                         # field -> address of its value
    hashes: dict[str, int] = field(default_factory=dict)   # field -> full 64-bit key (log/diagnostics)
    original: dict[str, float] | None = None      # values before our first write (this FIFA process)

    def describe(self, values: dict[str, float]) -> str:
        order = ("mass", "seam", "weight", "st", "tension")
        return " ".join(f"{n}={values[n]:g}" for n in order if n in values)


def _lo(buf: bytes, offset: int) -> int | None:
    if offset < 0 or offset + 4 > len(buf):
        return None
    return struct.unpack_from("<I", buf, offset)[0]


def parse_record(window: bytes, window_base: int, tension_addr: int) -> Record | None:
    """The record whose tension value is at tension_addr, from a buffer read at window_base."""
    t = tension_addr - window_base

    def lo(addr_off: int) -> int | None:  # low hash bits of the slot whose value is at t + addr_off
        return _lo(window, t + addr_off - 8)

    if lo(0) != H_TENSION:
        return None
    if all(lo(off) == {"mass": H_MASS, "seam": H_SEAM, "weight": H_WEIGHT, "st": H_ST}[name] for name, off in BOX2_SLOTS):
        slots = {name: tension_addr + off for name, off in BOX2_SLOTS}
        slots["tension"] = tension_addr
        family = "box2"
    elif lo(-SLOT) == H_MASS:
        slots = {"mass": tension_addr - SLOT, "tension": tension_addr}
        off = SLOT
        for _ in range(4):
            name = HASH_NAMES.get(lo(off) or 0)
            if name is None or name in slots or name == "mass":
                break
            slots[name] = tension_addr + off
            off += SLOT
        # Live log 2026-11-23 (FIP, the author's modified attribdb): the 2-supports presets also come in
        # this order (mass, tension, then seam/weight/st by hash). The seam field is what marks them.
        family = "box2" if "seam" in slots else "box4"
    else:
        return None
    hashes = {}
    for name, addr in slots.items():
        o = addr - window_base - 8
        if 0 <= o and o + 8 <= len(window):
            hashes[name] = struct.unpack_from("<Q", window, o)[0]
    return Record(tension_addr, family, slots, hashes)


def find_records(regions: Iterable[tuple[int, int]], read: Callable[[int, int], bytes],
                 stats: dict | None = None) -> list[Record]:
    """Every record in the given (base, size) regions: hash-first search, 8-byte aligned."""
    needle = struct.pack("<I", H_TENSION)
    found: dict[int, Record] = {}
    stats = stats if stats is not None else {}
    stats.setdefault("regions", 0)
    stats.setdefault("bytes", 0)
    stats.setdefault("tension_hashes", 0)
    stats.setdefault("rejected", 0)
    for base, size in regions:
        stats["regions"] += 1
        offset = 0
        while offset < size:
            n = min(SCAN_CHUNK, size - offset)
            chunk_base = base + offset
            data = read(chunk_base, n)
            stats["bytes"] += len(data)
            pos = data.find(needle)
            while pos != -1:
                hash_addr = chunk_base + pos
                if hash_addr % 8 == 0:
                    stats["tension_hashes"] += 1
                    tension_addr = hash_addr + 8
                    if tension_addr not in found:
                        # Only bytes of this chunk: reading before a region's start fails as a whole in
                        # FIFA's process. The chunks overlap by more than the window, so a record cut
                        # by a chunk edge is parsed whole in the neighbouring chunk.
                        lo_off = max(0, pos + 8 - WINDOW_BEFORE)
                        hi_off = min(len(data), pos + 8 + WINDOW_AFTER)
                        rec = parse_record(data[lo_off:hi_off], chunk_base + lo_off, tension_addr)
                        if rec is None:
                            stats["rejected"] += 1
                        else:
                            found[tension_addr] = rec
                pos = data.find(needle, pos + 1)
            if n < SCAN_CHUNK or not data:
                break
            offset += n - 0x100  # overlap, so a record across two chunks is still seen
    return sorted(found.values(), key=lambda r: r.tension_addr)


# ---------------------------------------------------------------------------------------------
# Live memory glue
# ---------------------------------------------------------------------------------------------
class _MBI(ctypes.Structure):
    _fields_ = [("BaseAddress", ctypes.c_void_p), ("AllocationBase", ctypes.c_void_p),
                ("AllocationProtect", wintypes.DWORD), ("PartitionId", wintypes.WORD),
                ("RegionSize", ctypes.c_size_t), ("State", wintypes.DWORD),
                ("Protect", wintypes.DWORD), ("Type", wintypes.DWORD)]


_MEM_COMMIT, _MEM_PRIVATE = 0x1000, 0x20000
_READABLE = {0x02, 0x04, 0x08, 0x20, 0x40, 0x80}
_k32 = None


def _kernel32():
    """Own kernel32 handle (other modules set their own argtypes on the shared one)."""
    global _k32
    if _k32 is None:
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.VirtualQueryEx.restype = ctypes.c_size_t
        k32.VirtualQueryEx.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.POINTER(_MBI), ctypes.c_size_t]
        _k32 = k32
    return _k32


def private_regions(process_handle) -> Iterator[tuple[int, int, int]]:
    """(base, size, protect) of every committed, readable, private region of the process."""
    k32 = _kernel32()
    mbi, addr = _MBI(), 0
    while addr < 0x7FFFFFFF0000 and k32.VirtualQueryEx(process_handle, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi)):
        base, size = int(mbi.BaseAddress or 0), int(mbi.RegionSize)
        if (mbi.State == _MEM_COMMIT and mbi.Type == _MEM_PRIVATE and not mbi.Protect & 0x101
                and mbi.Protect & 0xFF in _READABLE):
            yield base, size, int(mbi.Protect)
        addr = base + size


_SOCCERNET_LINE = re.compile(r"(?im)^[ \t]*(soccernet_[a-z0-9_]+|net_id|goalnetropes_pbr|animatenet_pbr)[ \t]*=[ \t]*([^\r\n;]*)")


def active_net_ini_lines(exedir: Path) -> dict[str, list[str]]:
    """{ini name: ["KEY=value", ...]} of the uncommented net lines in cl.ini / rna.ini (read only)."""
    out: dict[str, list[str]] = {}
    for name in ("cl.ini", "rna.ini"):
        path = Path(exedir) / name
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        lines = [f"{m.group(1)}={m.group(2).strip()}" for m in _SOCCERNET_LINE.finditer(text)]
        out[name] = lines
    return out


AUTHOR_NET_LINE = "SOCCERNET_BOX_NORMAL_NORMAL_4_SUPPORTS=1"


def author_line_active(exedir: Path) -> bool:
    """True when cl.ini or rna.ini has SOCCERNET_BOX_NORMAL_NORMAL_4_SUPPORTS=1 uncommented
    (live 2026-11-24: with it the loose/tense presets showed in game)."""
    key, value = AUTHOR_NET_LINE.split("=")
    return any(line.upper() == f"{key}={value}" for lines in active_net_ini_lines(exedir).values() for line in lines)


def add_author_line(exedir: Path) -> Path:
    """Appends the author's net line to the game's cl.ini (created when missing). The first time,
    the original cl.ini is kept as cl.ini.cgfs16.bak. FIFA reads cl.ini at start-up."""
    path = Path(exedir) / "cl.ini"
    data = path.read_bytes() if path.exists() else b""
    backup = path.with_name("cl.ini.cgfs16.bak")
    if data and not backup.exists():
        backup.write_bytes(data)
    if data and not data.endswith((b"\n", b"\r")):
        data += b"\r\n"
    path.write_bytes(data + AUTHOR_NET_LINE.encode("ascii") + b"\r\n")
    return path


class ProcessIO:
    """A process handle of our own. The shared Memory object is re-attached by poll_process every
    500 ms (Memory.attack closes and reopens its handle), which broke this worker's reads and writes
    mid-search (live log 2026-11-23: "Process handle not open", a 0 MB search).
    Writes never change page protection: the records live in plain read/write heap pages."""

    _RIGHTS = 0x0400 | 0x0010 | 0x0020 | 0x0008  # QUERY_INFORMATION | VM_READ | VM_WRITE | VM_OPERATION

    def __init__(self, process_id: int) -> None:
        k32 = _kernel32()
        k32.OpenProcess.restype = wintypes.HANDLE
        k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        k32.ReadProcessMemory.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t,
                                          ctypes.POINTER(ctypes.c_size_t)]
        k32.WriteProcessMemory.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t,
                                           ctypes.POINTER(ctypes.c_size_t)]
        k32.CloseHandle.argtypes = [wintypes.HANDLE]
        self._k32 = k32
        self.process_id = process_id
        self.process_handle = k32.OpenProcess(self._RIGHTS, False, process_id) if process_id else None

    def is_open(self) -> bool:
        return bool(self.process_handle)

    def read_process_memory_partial(self, address: int, size: int) -> bytes:
        if not self.process_handle or size <= 0:
            return b""
        buffer = ctypes.create_string_buffer(size)
        done = ctypes.c_size_t()
        self._k32.ReadProcessMemory(self.process_handle, ctypes.c_void_p(address), buffer, size, ctypes.byref(done))
        return buffer.raw[:done.value]

    def read_process_memory(self, address: int, size: int) -> bytes:
        data = self.read_process_memory_partial(address, size)
        if len(data) != size:
            raise OSError(f"ReadProcessMemory failed at 0x{address:X} (error {ctypes.get_last_error()})")
        return data

    def write_process_memory(self, address: int, payload: bytes) -> None:
        done = ctypes.c_size_t()
        ok = self._k32.WriteProcessMemory(self.process_handle, ctypes.c_void_p(address), payload, len(payload),
                                          ctypes.byref(done))
        if not ok or done.value != len(payload):
            raise OSError(f"WriteProcessMemory failed at 0x{address:X} (error {ctypes.get_last_error()})")

    def close(self) -> None:
        if self.process_handle:
            self._k32.CloseHandle(self.process_handle)
            self.process_handle = None


# ---------------------------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------------------------
def _read_hash_lo(memory, value_addr: int) -> int | None:
    try:
        raw = memory.read_process_memory(value_addr - 8, 4)
    except Exception:  # noqa: BLE001
        return None
    return struct.unpack("<I", raw)[0] if len(raw) == 4 else None


_FIELD_HASH = {"mass": H_MASS, "tension": H_TENSION, "seam": H_SEAM, "weight": H_WEIGHT, "st": H_ST}


def record_still_there(memory, rec: Record) -> bool:
    return all(_read_hash_lo(memory, addr) == _FIELD_HASH[name] for name, addr in rec.slots.items())


def read_values(memory, rec: Record) -> dict[str, float]:
    return {name: _f(memory.read_process_memory(addr, 4)) for name, addr in rec.slots.items()}


def targets_for(rec: Record, level: int, supports: int | None, table: PresetTable) -> dict[str, float]:
    """Field -> value to write. Level 0 = the record's original values (Support_Tension of a box4
    record still follows the stadium's number of supports, as in the author's build)."""
    original = rec.original or {}
    if level not in LEVEL_NAMES:
        out = {name: original[name] for name in ("mass", "tension", "weight", "seam") if name in original}
        if "st" in rec.slots and rec.family == "box4":
            out["st"] = original["st"] if supports is None and "st" in original else table.support_tension(0, supports)
        return out
    preset = table.preset(level, supports)
    out = {"mass": preset.mass, "tension": preset.tension}
    if "weight" in rec.slots:
        out["weight"] = preset.weighting
    if "seam" in rec.slots:
        seam = preset.seam_relaxation
        out["seam"] = seam if seam is not None else original.get("seam", 0.0)
        if seam is None and "seam" not in original:
            out.pop("seam")
    if "st" in rec.slots and rec.family == "box4":  # box2 records: Support_Tension left alone (author)
        out["st"] = table.support_tension(level, supports)
    return out


def write_record(memory, rec: Record, values: dict[str, float], log: Callable[[str], None]) -> bool:
    """Writes the values, each only after re-reading its slot hash; logs before -> after -> read back."""
    before = read_values(memory, rec)
    if rec.original is None:
        rec.original = dict(before)
    changes = []
    for name, value in values.items():
        addr = rec.slots.get(name)
        if addr is None:
            continue
        if _read_hash_lo(memory, addr) != _FIELD_HASH[name]:
            log(f"Net physics: 0x{rec.tension_addr:X} {name} slot hash changed: record dropped, nothing more written")
            return False
        memory.write_process_memory(addr, F(value))
        back = _f(memory.read_process_memory(addr, 4))
        mark = "" if back == _f(F(value)) else f" (read back {back:g}!)"
        changes.append(f"{name} {before[name]:g}->{value:g}{mark}")
    log(f"Net physics: 0x{rec.tension_addr:X} {rec.family} " + (", ".join(changes) or "nothing to write"))
    return True


# ---------------------------------------------------------------------------------------------
# Runtime (one per app): match-prep requests, a worker thread, TV-bumper read-back
# ---------------------------------------------------------------------------------------------
LIVE_COPY_DELAY = 20.0  # seconds after the TV bumper page: the match's net exists by then


class NetPhysicsRuntime:
    def __init__(self, memory, exedir_getter: Callable[[], Path | None], log: Callable[[str], None],
                 io_factory: Callable[[int], object] | None = None) -> None:
        self.memory = memory                  # the shared Memory object: only its process id / is_open
        self._io_factory = io_factory or ProcessIO
        self._io = None                       # our own process handle (see ProcessIO)
        self._io_lock = threading.Lock()
        self._exedir = exedir_getter
        self.log = log
        self._lock = threading.Lock()
        self._pending: tuple | None = None    # (level, supports, label)
        self._current: tuple | None = None    # the request being served
        self._worker: threading.Thread | None = None
        self._records: list[Record] = []
        self._records_pid = 0
        self._written_pid = 0                 # pid in which we wrote at least once (level 0 restores)
        self._written_tensions: set[float] = set()
        self._bumper_at: float | None = None
        self._restart = threading.Event()

    def _pid(self) -> int:
        return getattr(self.memory, "process_id", 0) if self.memory.is_open() else 0

    def _get_io(self):
        pid = self._pid()
        with self._io_lock:
            if self._io is None or self._io.process_id != pid or not self._io.is_open():
                if self._io is not None:
                    self._io.close()
                self._io = self._io_factory(pid) if pid else None
            return self._io

    # -- public ----------------------------------------------------------------------------------
    def request(self, net_value: str | None, label: str) -> None:
        """Match preparation: the stadium's physics level (7th net-value field) for the next match."""
        level = physics_level(net_value)
        supports = supports_of(net_value)
        if level == 0 and self._written_pid != self._pid():
            return  # never changed in this FIFA session: nothing to restore
        with self._lock:
            if self._current == (level, supports, label) and self._worker and self._worker.is_alive():
                return  # the same request is already being served
            self._pending = (level, supports, label)
            self._bumper_at = None
            self._restart.set()
            if self._worker is None or not self._worker.is_alive():
                self._worker = threading.Thread(target=self._run, name="net-physics", daemon=True)
                self._worker.start()

    def tv_bumper(self) -> None:
        """The match is loading: log what the records hold now (were our values kept?), then, once the
        match's net exists, which tension its live copies use."""
        self._bumper_at = time.time()
        threading.Thread(target=self._report, name="net-physics-report", daemon=True).start()

    # -- worker ----------------------------------------------------------------------------------
    def _run(self) -> None:
        while True:
            with self._lock:
                job = self._pending
                self._pending = None
                self._current = job
                self._restart.clear()
                if job is None:
                    self._worker = None
                    return
            try:
                self._serve(*job)
            except Exception as exc:  # noqa: BLE001 - never break the match flow
                self.log(f"Net physics failed: {exc!r}")

    def _serve(self, level: int, supports: int | None, label: str) -> None:
        exedir = self._exedir()
        table = load_presets(exedir, self.log)
        name = LEVEL_NAMES.get(level, "game default")
        self.log(f"Net physics: {name} (level {level}, supports {supports}) for {label}; presets from {table.source}")
        if exedir is not None:
            lines = active_net_ini_lines(exedir)
            author_line = author_line_active(exedir)
            self.log(f"Net physics: active net lines {lines or 'none (no cl.ini / rna.ini)'}"
                     + ("" if author_line else
                        " -- the author's setup needs SOCCERNET_BOX_NORMAL_NORMAL_4_SUPPORTS=1 as the only active net line"))
        started = time.time()
        attempt = 0
        while True:
            io = self._get_io()
            if io is None or not io.is_open():
                self.log("Net physics: FIFA is not running (or its process could not be opened)")
                return
            records = self._valid_records(io)
            if not records:
                attempt += 1
                records = self._scan(io, attempt)
            if records:
                when = ""
                if self._bumper_at is not None:
                    when = f" ({time.time() - self._bumper_at:.1f}s AFTER the TV bumper: likely too late for this match)"
                self._write_all(io, records, level, supports, table, when)
                return
            deadline_hit = (time.time() - started > MAX_REQUEST_SECONDS
                            or (self._bumper_at is not None and time.time() - self._bumper_at > AFTER_BUMPER_SECONDS))
            if deadline_hit:
                self.log(f"Net physics: no soccernet records found after {attempt} searches -- nothing written")
                return
            if self._restart.wait(RETRY_SECONDS):
                return  # a newer request replaces this one

    def _valid_records(self, io) -> list[Record]:
        if self._records_pid != io.process_id:
            self._records, self._records_pid = [], io.process_id
            self._written_tensions = set()
            return []
        alive = [r for r in self._records if record_still_there(io, r)]
        if len(alive) != len(self._records):
            self.log(f"Net physics: {len(self._records) - len(alive)} of {len(self._records)} known records are gone (memory reused)")
        self._records = alive
        return alive

    def _scan(self, io, attempt: int) -> list[Record]:
        stats: dict = {}
        protects: dict[int, int] = {}
        region_list = []
        for base, size, protect in private_regions(io.process_handle):
            region_list.append((base, size))
            protects[base] = protect
        started = time.time()
        records = find_records(region_list, io.read_process_memory_partial, stats)
        took = time.time() - started
        families: dict[str, int] = {}
        for r in records:
            families[r.family] = families.get(r.family, 0) + 1
        self.log(f"Net physics: search {attempt}: {len(records)} records {families or ''} in {stats['regions']} private regions, "
                 f"{stats['bytes'] / 1048576:.0f} MB, {took:.1f}s (tension hashes {stats['tension_hashes']}, "
                 f"not a record {stats['rejected']})")
        for r in records[:MAX_LOGGED_RECORDS]:
            region = max((b for b, _s in region_list if b <= r.tension_addr), default=0)
            try:
                values = read_values(io, r)
            except Exception:  # noqa: BLE001
                values = {}
            hashes = " ".join(f"{n}:{h:016X}" for n, h in sorted(r.hashes.items()))
            self.log(f"Net physics:   0x{r.tension_addr:X} {r.family} [{r.describe(values)}] region 0x{region:X} "
                     f"protect 0x{protects.get(region, 0):X} hashes {hashes}")
        if len(records) > MAX_LOGGED_RECORDS:
            self.log(f"Net physics:   ... {len(records) - MAX_LOGGED_RECORDS} more")
        self._records = records
        self._records_pid = io.process_id
        return records

    def _write_all(self, io, records: list[Record], level: int, supports: int | None, table: PresetTable,
                   when: str = "") -> None:
        written = 0
        tensions: set[float] = set()
        for rec in list(records):
            try:
                if rec.original is None:  # first sight: originals come from the record itself
                    rec.original = read_values(io, rec)
                values = targets_for(rec, level, supports, table)
                if write_record(io, rec, values, self.log):
                    written += 1
                    if "tension" in values:
                        tensions.add(_f(F(values["tension"])))
                else:
                    records.remove(rec)
            except Exception as exc:  # noqa: BLE001
                self.log(f"Net physics: 0x{rec.tension_addr:X} not written ({exc})")
        if written:
            self._written_pid = io.process_id
            self._written_tensions = tensions
        self.log(f"Net physics: {LEVEL_NAMES.get(level, 'game default')} written to {written} of {len(records)} records{when}")

    def _report(self) -> None:
        try:
            io = self._get_io()
            records = list(self._records)
            if io is None or not records or self._records_pid != io.process_id:
                self.log("Net physics: TV bumper -- no records known yet")
                return
            lines = []
            for rec in records[:MAX_LOGGED_RECORDS]:
                if not record_still_there(io, rec):
                    lines.append(f"0x{rec.tension_addr:X} gone")
                    continue
                lines.append(f"0x{rec.tension_addr:X} [{rec.describe(read_values(io, rec))}]")
            self.log("Net physics: TV bumper read-back: " + "; ".join(lines))
            time.sleep(LIVE_COPY_DELAY)
            self._report_live_copies(records)
        except Exception as exc:  # noqa: BLE001
            self.log(f"Net physics: TV bumper read-back failed ({exc!r})")

    def _report_live_copies(self, records: list[Record]) -> None:
        """Diagnostics: the author saw the running match's net keep its tension as 4 equal floats in a
        row. Counting those for our written tensions and for the records' original ones tells which
        values the engine took for this match (heuristic: other data may repeat a float too)."""
        io = self._get_io()
        if io is None:
            return
        labels: dict[float, set[str]] = {}
        for value in self._written_tensions:
            labels.setdefault(value, set()).add("written")
        for rec in records:
            if rec.original and "tension" in rec.original:
                labels.setdefault(_f(F(rec.original["tension"])), set()).add("original")
        if not labels:
            return
        needles = {value: F(value) * 4 for value in labels}
        hits: dict[float, list[int]] = {value: [] for value in labels}
        counts = {value: 0 for value in labels}
        for base, size, _protect in private_regions(io.process_handle):
            offset = 0
            while offset < size:
                n = min(SCAN_CHUNK, size - offset)
                data = io.read_process_memory_partial(base + offset, n)
                for value, needle in needles.items():
                    pos = data.find(needle)
                    while pos != -1:
                        if pos % 4 == 0:
                            counts[value] += 1
                            if len(hits[value]) < 3:
                                hits[value].append(base + offset + pos)
                        pos = data.find(needle, pos + 16)
                if n < SCAN_CHUNK or not data:
                    break
                offset += n - 0x10
        parts = [f"tension {value:g} ({'/'.join(sorted(labels[value]))}) x{counts[value]}"
                 + (" at " + " ".join(f"0x{a:X}" for a in hits[value]) if hits[value] else "")
                 for value in sorted(labels)]
        self.log(f"Net physics: {LIVE_COPY_DELAY:.0f}s after the TV bumper, 4-in-a-row copies: " + "; ".join(parts))
