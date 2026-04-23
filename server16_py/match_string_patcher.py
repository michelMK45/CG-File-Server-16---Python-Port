from __future__ import annotations

import ctypes
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .app import Server16App

# How much memory to scan at a time (4MB chunks)
SCAN_CHUNK = 4 * 1024 * 1024
# Max memory to scan total (512MB should be enough)
SCAN_MAX = 512 * 1024 * 1024


def _scan_memory(app: "Server16App", pattern: bytes) -> list[int]:
    """Scan FIFA process memory for a byte pattern. Returns list of addresses."""
    kernel32 = app.memory.kernel32
    handle = app.memory.process_handle
    if not handle:
        return []

    MEM_COMMIT = 0x1000
    PAGE_READABLE = {0x02, 0x04, 0x20, 0x40}  # READONLY, READWRITE, EXECUTE_READ, EXECUTE_READWRITE
    PAGE_GUARD = 0x100
    PAGE_NOACCESS = 0x01

    class MEMORY_BASIC_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("BaseAddress",       ctypes.c_ulonglong),
            ("AllocationBase",    ctypes.c_ulonglong),
            ("AllocationProtect", ctypes.c_ulong),
            ("RegionSize",        ctypes.c_ulonglong),
            ("State",             ctypes.c_ulong),
            ("Protect",           ctypes.c_ulong),
            ("Type",              ctypes.c_ulong),
        ]

    VirtualQueryEx = kernel32.VirtualQueryEx
    VirtualQueryEx.restype = ctypes.c_size_t
    VirtualQueryEx.argtypes = [
        ctypes.c_void_p, ctypes.c_ulonglong,
        ctypes.POINTER(MEMORY_BASIC_INFORMATION), ctypes.c_size_t
    ]

    results = []
    addr = 0
    scanned = 0
    mbi = MEMORY_BASIC_INFORMATION()

    while scanned < SCAN_MAX:
        ret = VirtualQueryEx(handle, addr, ctypes.byref(mbi), ctypes.sizeof(mbi))
        if ret == 0:
            break
        region_size = mbi.RegionSize
        base_protect = mbi.Protect & 0xFF
        is_readable = base_protect in PAGE_READABLE
        has_guard = (mbi.Protect & PAGE_GUARD) != 0
        no_access = base_protect == PAGE_NOACCESS
        if (mbi.State == MEM_COMMIT and
                is_readable and
                not has_guard and
                not no_access and
                region_size > 0):
            # Read this region in chunks
            offset = 0
            while offset < region_size:
                chunk_size = min(SCAN_CHUNK, region_size - offset)
                buf = ctypes.create_string_buffer(chunk_size)
                read = ctypes.c_size_t()
                ok = kernel32.ReadProcessMemory(
                    handle,
                    ctypes.c_void_p(addr + offset),
                    buf, chunk_size,
                    ctypes.byref(read)
                )
                if ok and read.value > 0:
                    data = buf.raw[:read.value]
                    pos = 0
                    while True:
                        idx = data.find(pattern, pos)
                        if idx == -1:
                            break
                        results.append(addr + offset + idx)
                        pos = idx + 1
                offset += chunk_size
            scanned += region_size
        if region_size <= 0:
            # Defensive step to avoid infinite loops on malformed region metadata.
            addr += 0x1000
        else:
            addr += region_size
        if addr >= 0x7FFFFFFFFFFF:
            break

    return list(dict.fromkeys(results))


def patch_match_string(app: "Server16App", stad_name: str) -> bool:
    """
    Scan FIFA memory for the pipe-delimited match context string and
    replace the stadium name field (field index 2) with stad_name.
    Uses HID and AID together to identify the correct string instance.
    Returns True if at least one patch was applied.
    """
    if not app.memory.is_open():
        app.log("Match string patcher: memory not open")
        return False

    hid = getattr(app, "HID", "")
    aid = getattr(app, "AID", "")
    if not hid or not aid:
        app.log("Match string patcher: HID/AID not available yet")
        return False

    # Search for |HID|...|AID| pattern — both IDs together make it unique
    # The string structure is: XX|MatchType|StadName|Country|Country|HID|Country|Country|AID|...
    # So we search for |HID| and then verify AID is nearby
    search_pattern = f"|{hid}|".encode("utf-8")
    app.log(f"Match string patcher: scanning memory for pattern '|{hid}|'...")

    addresses = _scan_memory(app, search_pattern)
    app.log(f"Match string patcher: found {len(addresses)} candidate(s)")

    patched = 0
    for addr in addresses:
        try:
            # Read 1024 bytes around the match to get the full string
            # The string starts well before |HID| so read 300 bytes back
            read_start = max(0, addr - 300)
            buf = ctypes.create_string_buffer(1024)
            read = ctypes.c_size_t()
            ok = app.memory.kernel32.ReadProcessMemory(
                app.memory.process_handle,
                ctypes.c_void_p(read_start),
                buf, 1024,
                ctypes.byref(read)
            )
            if not ok or read.value < 10:
                continue

            data = buf.raw[:read.value]

            # Find all null-terminated strings in this region and look for the one
            # that contains both HID and AID as pipe-delimited fields
            pos = 0
            found_string = None
            found_start = -1
            while pos < len(data):
                # Find next null byte to delimit a string
                null = data.find(b"\x00", pos)
                if null == -1:
                    break
                chunk = data[pos:null]
                if b"|" in chunk and search_pattern in chunk:
                    text = chunk.decode("utf-8", errors="ignore")
                    parts = text.split("|")
                    # Validate structure strictly:
                    # Field 5 must be exactly HID, field 8 must be exactly AID
                    # Field 2 must be a non-numeric string (the stadium name)
                    if (len(parts) >= 9
                            and parts[5] == hid
                            and parts[8] == aid
                            and parts[2]
                            and not parts[2].lstrip("-").isdigit()):
                        found_string = text
                        found_start = read_start + pos
                        break
                pos = null + 1

            if found_string is None:
                continue

            parts = found_string.split("|")
            # Field 2 is the stadium name
            old_name = parts[2]
            if old_name == stad_name:
                app.log(f"Match string patcher: already correct '{stad_name}'")
                continue

            # Replace field 2 with new stadium name
            parts[2] = stad_name
            new_full = "|".join(parts)

            old_bytes = found_string.encode("utf-8") + b"\x00"
            new_bytes = new_full.encode("utf-8") + b"\x00"
            if len(new_bytes) > len(old_bytes):
                new_bytes = new_bytes[:len(old_bytes)]
            else:
                new_bytes = new_bytes + b"\x00" * (len(old_bytes) - len(new_bytes))

            # Unprotect and write
            old_protect = ctypes.c_ulong()
            changed = app.memory.kernel32.VirtualProtectEx(
                app.memory.process_handle,
                ctypes.c_void_p(found_start),
                len(new_bytes), 0x40,
                ctypes.byref(old_protect)
            )
            if not changed:
                app.log(f"Match string patcher: VirtualProtectEx failed at 0x{found_start:X}")
                continue
            written = ctypes.c_size_t()
            ok = app.memory.kernel32.WriteProcessMemory(
                app.memory.process_handle,
                ctypes.c_void_p(found_start),
                new_bytes, len(new_bytes),
                ctypes.byref(written)
            )
            # Restore previous protection flags regardless of write result.
            restore_dummy = ctypes.c_ulong()
            app.memory.kernel32.VirtualProtectEx(
                app.memory.process_handle,
                ctypes.c_void_p(found_start),
                len(new_bytes), old_protect.value,
                ctypes.byref(restore_dummy)
            )

            if ok and written.value == len(new_bytes):
                app.log(f"Match string patcher: replaced '{old_name}' -> '{stad_name}' at 0x{found_start:X}")
                patched += 1
            else:
                app.log(
                    f"Match string patcher: write failed at 0x{found_start:X} "
                    f"(ok={bool(ok)} bytes={written.value}/{len(new_bytes)})"
                )

        except Exception as exc:
            app.log(f"Match string patcher: error at 0x{addr:X}", exc)

    if patched == 0:
        app.log("Match string patcher: no matches patched")
    return patched > 0
