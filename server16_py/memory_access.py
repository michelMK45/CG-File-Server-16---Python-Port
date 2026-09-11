from __future__ import annotations

import ctypes
import struct
from ctypes import wintypes
from pathlib import Path


PROCESS_VM_READ = 0x0010
PROCESS_VM_WRITE = 0x0020
PROCESS_VM_OPERATION = 0x0008
PROCESS_QUERY_INFORMATION = 0x0400
PAGE_READWRITE = 0x04
TH32CS_SNAPMODULE = 0x00000008
TH32CS_SNAPMODULE32 = 0x00000010
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
MAX_MODULE_NAME32 = 255
MAX_PATH = 260


class MODULEENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("th32ModuleID", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("GlblcntUsage", wintypes.DWORD),
        ("ProccntUsage", wintypes.DWORD),
        ("modBaseAddr", ctypes.POINTER(ctypes.c_ubyte)),
        ("modBaseSize", wintypes.DWORD),
        ("hModule", wintypes.HMODULE),
        ("szModule", wintypes.WCHAR * (MAX_MODULE_NAME32 + 1)),
        ("szExePath", wintypes.WCHAR * MAX_PATH),
    ]


class MemoryAccessError(RuntimeError):
    pass


class Memory:
    def __init__(self) -> None:
        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel32.OpenProcess.restype = wintypes.HANDLE
        self.kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self.kernel32.ReadProcessMemory.restype = wintypes.BOOL
        self.kernel32.ReadProcessMemory.argtypes = [
            wintypes.HANDLE,
            wintypes.LPCVOID,
            wintypes.LPVOID,
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_size_t),
        ]
        self.kernel32.WriteProcessMemory.restype = wintypes.BOOL
        self.kernel32.WriteProcessMemory.argtypes = [
            wintypes.HANDLE,
            wintypes.LPVOID,
            wintypes.LPCVOID,
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_size_t),
        ]
        self.kernel32.VirtualProtectEx.restype = wintypes.BOOL
        self.kernel32.VirtualProtectEx.argtypes = [
            wintypes.HANDLE,
            wintypes.LPVOID,
            ctypes.c_size_t,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
        ]
        self.kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        self.kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
        self.kernel32.Module32FirstW.restype = wintypes.BOOL
        self.kernel32.Module32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MODULEENTRY32W)]
        self.kernel32.Module32NextW.restype = wintypes.BOOL
        self.kernel32.Module32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MODULEENTRY32W)]
        self.kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        self.process_handle = None
        self.process_name = ""
        self.process_id = 0
        self.base_module = 0

    def close(self) -> None:
        if self.process_handle:
            self.kernel32.CloseHandle(self.process_handle)
            self.process_handle = None

    def __del__(self) -> None:
        self.close()

    def attack(self, process_name: str) -> bool:
        import psutil

        self.close()
        for proc in psutil.process_iter(["pid", "name", "exe"]):
            name = (proc.info.get("name") or "").lower()
            if Path(name).stem == process_name.lower():
                self.process_id = proc.info["pid"]
                self.process_name = process_name
                rights = PROCESS_QUERY_INFORMATION | PROCESS_VM_READ | PROCESS_VM_WRITE | PROCESS_VM_OPERATION
                self.process_handle = self.kernel32.OpenProcess(rights, False, self.process_id)
                if not self.process_handle:
                    return False
                self.base_module = self._get_base_address(proc.info.get("exe"))
                return True
        return False

    def _get_base_address(self, exe_path: str | None) -> int:
        snapshot = self.kernel32.CreateToolhelp32Snapshot(
            TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32,
            self.process_id,
        )
        if snapshot == INVALID_HANDLE_VALUE:
            return 0
        try:
            entry = MODULEENTRY32W()
            entry.dwSize = ctypes.sizeof(MODULEENTRY32W)
            ok = self.kernel32.Module32FirstW(snapshot, ctypes.byref(entry))
            target_name = Path(exe_path).name.lower() if exe_path else ""
            while ok:
                module_name = entry.szModule.lower()
                module_path = entry.szExePath.lower()
                if not target_name or module_name == target_name or Path(module_path).name.lower() == target_name:
                    return ctypes.addressof(entry.modBaseAddr.contents)
                ok = self.kernel32.Module32NextW(snapshot, ctypes.byref(entry))
        finally:
            self.kernel32.CloseHandle(snapshot)
        return 0

    def is_open(self) -> bool:
        return bool(self.process_handle)

    def read_process_memory(self, address: int, size: int) -> bytes:
        if not self.process_handle:
            raise MemoryAccessError("Process handle not open")
        buffer = ctypes.create_string_buffer(size)
        read = ctypes.c_size_t()
        ok = self.kernel32.ReadProcessMemory(
            self.process_handle,
            ctypes.c_void_p(address),
            buffer,
            size,
            ctypes.byref(read),
        )
        if not ok:
            raise MemoryAccessError(f"ReadProcessMemory failed at 0x{address:X}")
        return buffer.raw[: read.value]

    def read_process_memory_partial(self, address: int, size: int) -> bytes:
        """Like read_process_memory, but never raises -- returns whatever
        prefix of `size` bytes Windows actually copied, even when the API
        call as a whole reports failure.

        ReadProcessMemory can genuinely partially succeed: when part of the
        requested range crosses from accessible into inaccessible memory
        (e.g. the edge of a heap allocation), Windows can still copy the
        accessible prefix and set *lpNumberOfBytesRead to that count while
        the call still returns FALSE overall (ERROR_PARTIAL_COPY) -- this is
        the same partial-copy behavior memory-scanning tools like Cheat
        Engine already account for. read_process_memory's own all-or-nothing
        "raise unless ok" check discards that legitimately-read prefix
        entirely, which was a real bug found live 2026-09-10 (CLAUDE.md §7's
        scoreboardstdname saga): a capacity probe requesting up to 512 bytes
        past a string's own terminator got credited with ZERO extra room the
        moment even the very last requested byte crossed into unmapped
        memory, even when hundreds of genuinely safe-to-write bytes existed
        right after the terminator -- exactly the gap between "Cheat Engine
        could write a longer name here" and CGFS's own probe reporting no
        room at all. Any other failure (no process handle, an invalid
        address) is also swallowed, returning an empty/short result rather
        than raising -- callers use this only to measure how much is safely
        readable, never to assert that a read must fully succeed.
        """
        if not self.process_handle or size <= 0:
            return b""
        try:
            buffer = ctypes.create_string_buffer(size)
            read = ctypes.c_size_t()
            self.kernel32.ReadProcessMemory(
                self.process_handle,
                ctypes.c_void_p(address),
                buffer,
                size,
                ctypes.byref(read),
            )
            return buffer.raw[: read.value]
        except Exception:
            return b""

    def write_process_memory(self, address: int, payload: bytes) -> None:
        if not self.process_handle:
            raise MemoryAccessError("Process handle not open")
        old = wintypes.DWORD()
        self.kernel32.VirtualProtectEx(
            self.process_handle,
            ctypes.c_void_p(address),
            len(payload),
            PAGE_READWRITE,
            ctypes.byref(old),
        )
        written = ctypes.c_size_t()
        ok = self.kernel32.WriteProcessMemory(
            self.process_handle,
            ctypes.c_void_p(address),
            payload,
            len(payload),
            ctypes.byref(written),
        )
        if not ok:
            raise MemoryAccessError(f"WriteProcessMemory failed at 0x{address:X}")

    def read_uint32(self, address: int) -> int:
        return struct.unpack("<I", self.read_process_memory(address, 4))[0]

    def read_int64(self, address: int) -> int:
        return struct.unpack("<q", self.read_process_memory(address, 8))[0]

    def read_string(self, address: int, size: int) -> str:
        raw = self.read_process_memory(address, size)
        return raw.split(b"\x00", 1)[0].decode("utf-8", errors="ignore")

    def resolve_pointer(self, static_ptr: int, offsets: list[int]) -> int:
        pointer = self.read_int64(self.base_module + static_ptr)
        if pointer == 0:
            raise MemoryAccessError(
                f"Null pointer at base chain start 0x{self.base_module + static_ptr:X}"
            )
        for offset in offsets[:-1]:
            address = pointer + offset
            pointer = self.read_int64(address)
            if pointer == 0:
                raise MemoryAccessError(f"Null pointer while resolving chain at 0x{address:X}")
        return pointer + offsets[-1]

    def trace_pointer_chain(self, static_ptr: int, offsets: list[int]) -> list[str]:
        trace: list[str] = []
        base_address = self.base_module + static_ptr
        trace.append(f"base_module=0x{self.base_module:X}")
        trace.append(f"static_ptr=0x{static_ptr:X}")
        trace.append(f"read [0x{base_address:X}]")
        pointer = self.read_int64(base_address)
        trace.append(f" -> 0x{pointer:X}")
        if pointer == 0:
            return trace
        for index, offset in enumerate(offsets[:-1]):
            address = pointer + offset
            trace.append(f"step {index}: read [0x{address:X}] (offset=0x{offset:X})")
            pointer = self.read_int64(address)
            trace.append(f" -> 0x{pointer:X}")
            if pointer == 0:
                return trace
        trace.append(f"final address=0x{pointer + offsets[-1]:X} (last offset=0x{offsets[-1]:X})")
        return trace

    def get_int(self, static_ptr: int, offsets: list[int]) -> int:
        return self.read_uint32(self.resolve_pointer(static_ptr, offsets))

    def get_string(self, static_ptr: int, offsets: list[int], size: int = 64) -> str:
        return self.read_string(self.resolve_pointer(static_ptr, offsets), size)

    def write_int(self, static_ptr: int, offsets: list[int], value: str | int) -> None:
        address = self.resolve_pointer(static_ptr, offsets)
        self.write_process_memory(address, struct.pack("<I", int(value)))

    def write_string_with_offsets(self, static_ptr: int, offsets: list[int], value: str) -> None:
        address = self.resolve_pointer(static_ptr, offsets)
        self.write_process_memory(address, value.encode("utf-8") + b"\x00")

    @staticmethod
    def _truncate_utf8(value: str, max_bytes: int) -> bytes:
        if max_bytes <= 0:
            return b""
        encoded = value.encode("utf-8")
        if len(encoded) <= max_bytes:
            return encoded
        # Cutting raw UTF-8 at a fixed byte count can split a multibyte
        # character. Decode with errors="ignore" and re-encode so the final
        # payload is always valid UTF-8.
        return encoded[:max_bytes].decode("utf-8", errors="ignore").encode("utf-8")

    def write_string_safe(
        self,
        address: int,
        value: str,
        *,
        max_bytes: int = 63,
        validation_size: int = 256,
        require_printable_existing: bool = True,
        max_extra_capacity: int = 512,
    ) -> tuple[str, int]:
        """Validate, bound, write and verify a NUL-terminated UTF-8 string.

        Returns ``(written_text, address)``. ``max_bytes`` is a FLOOR, not a
        hard ceiling: after confirming the existing string's own NUL
        terminator (the guard below), this also counts how many further
        bytes are genuinely zero right now -- first within what was already
        read, then (only if that ran out without hitting a non-zero byte) via
        one more probe read of up to ``max_extra_capacity`` bytes -- and uses
        whichever is larger, `max_bytes` or that measured real capacity
        (which already covers reusing the *existing* string's own footprint
        even with zero extra padding, since everything up to and including
        its own NUL is provably safe to overwrite). Reported live 2026-09-10:
        a user editing one of these buffers directly in Cheat Engine saw no
        practical length limit, while this function's old fixed
        ``max_bytes=63`` silently truncated the same field. This is the same
        "count contiguous zero bytes, never manufacture room that isn't
        there" technique already proven for
        ``StadiumDbNamePatchCoordinator``'s own buffer writes
        (``match_string_patcher.py``'s ``_probe_available_capacity``,
        CLAUDE.md §7 Part 10) -- it was never applied to this pointer-chain
        write path until now. The probe read goes through
        ``read_process_memory_partial`` (not ``read_process_memory``)
        specifically so a request that only partially fits inside readable
        memory still credits the accessible prefix instead of being
        discarded wholesale the instant any part of it crosses into unmapped
        memory (see that method's own docstring -- this exact gap was found
        live 2026-09-10 to still be silently truncating a genuinely-writable
        buffer even after the byte-value gating above was already removed).
        It can only ever shrink what gets written (truncating more of
        `value`), never grow the amount of memory actually touched beyond
        what's been read back as zero.

        Unlike ``write_process_memory`` (used by ``write_string_with_offsets``
        above), this refuses to touch an address that does not currently look
        like a short, NUL-terminated string -- the guard that lets a caller
        try several candidate pointer chains (some of which may not resolve
        to a string buffer at all on a given FIFA build/mod) without risking
        corrupting unrelated memory.
        """
        if max_bytes <= 0:
            raise ValueError("max_bytes must be greater than zero")
        read_size = max(max_bytes + 1, validation_size)
        existing = self.read_process_memory(address, read_size)
        null_index = existing.find(b"\x00")
        if null_index == -1:
            raise MemoryAccessError(
                f"Safe string write rejected at 0x{address:X}: "
                f"no NUL terminator within {read_size} bytes"
            )
        existing_text = existing[:null_index]
        if require_printable_existing and existing_text and not all(
            0x20 <= byte < 0x7F or byte in (0x09, 0x0A, 0x0D)
            for byte in existing_text
        ):
            raise MemoryAccessError(
                f"Safe string write rejected at 0x{address:X}: "
                "existing bytes are not printable text"
            )

        zero_run = 0
        i = null_index + 1
        while i < len(existing) and existing[i] == 0:
            zero_run += 1
            i += 1
        if i >= len(existing) and max_extra_capacity > 0:
            probe = self.read_process_memory_partial(address + len(existing), max_extra_capacity)
            for byte in probe:
                if byte != 0:
                    break
                zero_run += 1
        effective_max_bytes = max(max_bytes, null_index + zero_run)

        encoded = self._truncate_utf8(value, effective_max_bytes)
        payload = encoded + b"\x00"
        # Clear only the remainder of the previous visible string. Never pad
        # past the old string's own terminator -- bytes beyond it may belong
        # to a different field/structure (the newly-measured extra capacity
        # above is already known-zero, so there's nothing to clear there).
        clear_length = min(null_index + 1, effective_max_bytes + 1)
        if clear_length > len(payload):
            payload += b"\x00" * (clear_length - len(payload))
        self.write_process_memory(address, payload)

        verify = self.read_process_memory(address, len(encoded) + 1)
        expected = encoded + b"\x00"
        if verify != expected:
            raise MemoryAccessError(f"Safe string write verification failed at 0x{address:X}")
        return encoded.decode("utf-8", errors="ignore"), address

    def write_string_with_offsets_safe(
        self,
        static_ptr: int,
        offsets: list[int],
        value: str,
        *,
        max_bytes: int = 63,
        validation_size: int = 256,
        require_printable_existing: bool = True,
        max_extra_capacity: int = 512,
    ) -> tuple[str, int]:
        address = self.resolve_pointer(static_ptr, offsets)
        return self.write_string_safe(
            address,
            value,
            max_bytes=max_bytes,
            validation_size=validation_size,
            require_printable_existing=require_printable_existing,
            max_extra_capacity=max_extra_capacity,
        )
