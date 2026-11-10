"""Menu -> app record: its format and the scan of FIFA 16's memory that finds it (read only).

Shared by the cgfs-ingame project (tools/recordscan.py, the original) and the CG Server 16 app
(server16_py/ingame_recordscan.py, a byte-identical copy: keep them in sync; cgfs-ingame's
tests/test_repo_copies.py checks it). Self-contained: standard library only, Python 3.9+.

On "Guardar y salir" the menu sets _global.CGFS16Out to
  CGFS16OUT|v1|<seq>|STADIUM=<index>:<text>|SCOREBOARD=...|...|END
ActionScript strings live in FIFA's heap as UTF-8, so the record can be found by its marker. Memory
also holds stale copies (earlier saves, freed strings not yet overwritten) and partial strings from the
concatenation; partials never end in |END, and the newest save has the highest seq.
"""
import ctypes
import re
import time
from ctypes import wintypes

RECORD = re.compile(rb'CGFS16OUT\|v1\|(\d+)\|((?:[A-Z][A-Z0-9_]*=-?\d+:[^|\x00\r\n]*\|)*)END')
PREFIX = b'CGFS16OUT|v1|'

PROCESS_QUERY_INFORMATION, PROCESS_VM_READ = 0x0400, 0x0010
MEM_COMMIT, MEM_PRIVATE = 0x1000, 0x20000
READABLE = {0x02, 0x04, 0x08, 0x20, 0x40, 0x80}  # READONLY, READWRITE, WRITECOPY, EXECUTE_READ(+WRITE/COPY)
GUARD, NOACCESS = 0x100, 0x01
CHUNK = 4 << 20


class MEMORY_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [('BaseAddress', ctypes.c_void_p), ('AllocationBase', ctypes.c_void_p),
                ('AllocationProtect', wintypes.DWORD), ('PartitionId', wintypes.WORD),
                ('RegionSize', ctypes.c_size_t), ('State', wintypes.DWORD), ('Protect', wintypes.DWORD),
                ('Type', wintypes.DWORD)]


def parse(buf):
    """[(seq, {NAME: (index, text)})] of the complete records in buf."""
    out = []
    for m in RECORD.finditer(buf):
        fields = {}
        for part in m.group(2).split(b'|')[:-1]:
            name, _, rest = part.partition(b'=')
            index, _, text = rest.partition(b':')
            fields[name.decode()] = (int(index), text.decode('utf-8', 'replace'))
        out.append((int(m.group(1)), fields))
    return out


def newest(records):
    return max(records, key=lambda r: r[0]) if records else None


def scan(pid, hot=None, newer_than=None, found=None):
    """(records found, MB scanned, seconds) over FIFA's committed, readable private memory.

    hot: [(base, size)] regions to read first (where records were found before: the Apt heap);
    newer_than: if one of them holds a record with a higher seq, stop there (one save per menu visit,
    so it is the new one) -- ~instant instead of ~4 s for the whole of FIFA's memory;
    found: a list that gets the (base, size) of every region that held a record (the next call's hot)."""
    k = ctypes.windll.kernel32
    k.OpenProcess.restype = wintypes.HANDLE
    k.VirtualQueryEx.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.POINTER(MEMORY_BASIC_INFORMATION),
                                 ctypes.c_size_t]
    k.ReadProcessMemory.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t,
                                    ctypes.POINTER(ctypes.c_size_t)]
    h = k.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
    if not h:
        raise OSError(f'OpenProcess failed ({ctypes.GetLastError()})')
    t0, total, records = time.time(), 0, []
    buf = ctypes.create_string_buffer(CHUNK)
    got = ctypes.c_size_t()

    def region(base, size):
        nonlocal total
        overlap, here = b'', []
        for off in range(0, size, CHUNK):
            n = min(CHUNK, size - off)
            if not k.ReadProcessMemory(h, ctypes.c_void_p(base + off), buf, n, ctypes.byref(got)):
                overlap = b''
                continue
            data = overlap + ctypes.string_at(buf, got.value)  # (buf.raw would copy all 4 MB)
            total += got.value
            if PREFIX in data:
                here += parse(data)
            overlap = data[-512:]  # a record cut by the chunk boundary
        if here and found is not None and (base, size) not in found:
            found.append((base, size))
        return here

    def result():
        # a record found twice (in the overlap, or in a hot region and again) is the same save
        return sorted(set((s, tuple(sorted(f.items()))) for s, f in records)), total / 2 ** 20, time.time() - t0
    try:
        mbi = MEMORY_BASIC_INFORMATION()
        for base, size in hot or []:
            if not k.VirtualQueryEx(h, ctypes.c_void_p(base), ctypes.byref(mbi), ctypes.sizeof(mbi)):
                continue
            if (mbi.BaseAddress or 0) != base or mbi.State != MEM_COMMIT or mbi.Protect & (GUARD | NOACCESS):
                continue  # gone or changed since
            records += region(base, min(size, mbi.RegionSize))
            if newer_than is not None and any(s > newer_than for s, _f in records):
                return result()
        addr = 0
        while k.VirtualQueryEx(h, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi)):
            base, size = mbi.BaseAddress or 0, mbi.RegionSize
            if (mbi.State == MEM_COMMIT and mbi.Type == MEM_PRIVATE and not mbi.Protect & (GUARD | NOACCESS)
                    and mbi.Protect & 0xFF in READABLE and (base, size) not in (hot or [])):
                records += region(base, size)
            addr = base + size
            if addr >= 0x7FFFFFFFFFFF:
                break
    finally:
        k.CloseHandle(h)
    return result()
