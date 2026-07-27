from __future__ import annotations

import ctypes
import struct
from ctypes import wintypes
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .win32_types import MEMORY_BASIC_INFORMATION

if TYPE_CHECKING:
    from .app import Server16App

# Only 1-5 was ever exercised live against fifa16.exe (vanilla + FIP, kickoff + tournament).
# The UI still allows up to SUBSTITUTION_MAX by user request, but callers should treat values
# above SUBSTITUTION_VALIDATED_MAX as unverified.
SUBSTITUTION_MIN = 1
SUBSTITUTION_MAX = 9
SUBSTITUTION_VALIDATED_MAX = 5

# Two full pages: page 0 stays PAGE_READWRITE forever (the scratch/slot data the shellcode
# itself writes into at runtime); page 1 holds the actual instructions and is flipped to
# PAGE_EXECUTE_READ once written. Keeping data and code on separate pages means the shellcode
# never has to write into the same page it executes from, so that page can be non-writable
# (avoids ever holding a PAGE_EXECUTE_READWRITE page, and avoids a self-write fault against a
# read-only-executable page).
_PAGE_SIZE = 0x1000
_CAVE_ALLOC_SIZE = 0x2000
_DATA_SCRATCH_OFFSET = 0
_DATA_SLOT_OFFSET = 8

_MEM_COMMIT = 0x1000
_MEM_RESERVE = 0x2000
_MEM_FREE = 0x10000
_PAGE_READWRITE = 0x04
_PAGE_EXECUTE_READ = 0x20
_PAGE_EXECUTE_READWRITE = 0x40
_PAGE_GUARD = 0x100
_PAGE_NOACCESS = 0x01
_WRITABLE_PROTECTIONS = {0x04, 0x08, 0x40, 0x80}  # RW, WRITECOPY, EXECUTE_RW, EXECUTE_WRITECOPY

# 64KB is the required granularity for VirtualAlloc address hints (SYSTEM_INFO.dwAllocationGranularity).
_ALLOC_GRANULARITY = 0x10000
# Comfortably under the true 2GB signed-rel32 limit, leaving margin for the jmp's own instruction length.
_MAX_CAVE_DISTANCE = 0x70000000

_HOOK_PATCH_SIZE = 8  # length of the original instruction being replaced

POLL_INTERVAL_MS = 500
POLL_TIMEOUT_MS = 180_000  # generous: tournament mode may not resolve until the player's first sub
# The hook is shared code: it fires for whichever team (home or away) just processed a
# substitution, recording THAT team's own "rules" address into the slot each time. After the
# first side is armed, the other side's own first substitution can happen much later in the
# match (e.g. a tactical sub in the 70th minute), so give it a much longer window than the
# first-resolution timeout above.
POLL_TIMEOUT_SECOND_SIDE_MS = 3_600_000  # 1 hour
# FIFA matches always have exactly two sides sharing this one hook — stop once both have had
# their "rules" address armed at least once.
EXPECTED_SIDES = 2


@dataclass
class _HookState:
    process_id: int
    hook_address: int
    code_address: int
    slot_address: int


def _rel32(instr_addr: int, instr_len: int, target_addr: int) -> bytes:
    delta = target_addr - (instr_addr + instr_len)
    return struct.pack("<i", delta)  # raises struct.error if delta doesn't fit in int32


class SubstitutionRuntime:
    """Lets the user override FIFA 16's hardcoded 3-substitution limit, for BOTH teams.

    Unlike every other memory feature in this codebase, this one patches executable code in
    fifa16.exe (a small, purely observational code cave at a hook point confirmed safe in prior
    manual testing — see offsets.py's SUBHOOKRVA comment) rather than only reading/writing data
    at already-resolved addresses. Treat any change to the hook mechanics here with the same
    care as a change to offsets.py itself.

    The hooked instruction is shared code: it runs once per substitution, for whichever team
    (home or away) just made that substitution, recording that team's own "rules" struct address
    into the slot each time (confirmed live: the recorded address alternates between two values
    exactly 0x458 bytes apart depending on which side just subbed — see
    fifa16-sustituciones-5-contexto.md, "Extensión a equipo VISITANTE"). A single write to
    whichever address shows up first only ever fixes ONE side — usually the local/home side,
    since it tends to substitute first. `_poll_tick` therefore keeps watching (re-arming) after
    the first side is armed, until both known sides have received the write.
    """

    def __init__(self, app: "Server16App") -> None:
        self.app = app
        self._hook: _HookState | None = None
        self._poll_job = None
        self._poll_generation = 0
        self._pending_count = 0
        self._armed_addresses: set[int] = set()

    # ── Public entry point ──────────────────────────────────────────────────

    def apply_substitution_count(self, count: int) -> None:
        app = self.app
        self._poll_generation += 1
        generation = self._poll_generation
        self._cancel_poll()

        if not app.memory.is_open():
            self._report("not_attached")
            return

        ok, reason = self._ensure_hook_installed()
        if not ok:
            self._report(reason)
            return

        assert self._hook is not None
        # Zero the recorded-pointer slot before polling: the hook re-arms on every match load
        # AND every substitution, so a stale pointer from a *previous* match could otherwise
        # look "valid" here and cause a write into memory that's no longer the rules struct.
        try:
            app.memory.write_process_memory(self._hook.slot_address, b"\x00" * 8)
        except Exception as exc:
            app.log("Substitution hook: failed to clear recorded-pointer slot", exc, exc_info=True)
            self._report("patch_failed")
            return

        self._pending_count = count
        self._armed_addresses = set()
        self._report("waiting")
        self._poll_tick(generation, attempts_left=POLL_TIMEOUT_MS // POLL_INTERVAL_MS)

    def cancel(self) -> None:
        """Called from Server16App.on_close() so a live poll never fires after shutdown."""
        self._poll_generation += 1
        self._cancel_poll()

    # ── Hook install ─────────────────────────────────────────────────────────

    def _ensure_hook_installed(self) -> tuple[bool, str]:
        app = self.app
        pid = app.memory.process_id
        if self._hook is not None and self._hook.process_id == pid:
            return True, "ok"
        self._hook = None

        hook_addr = app.memory.base_module + app.offsets.SUBHOOKRVA
        try:
            live_bytes = app.memory.read_process_memory(hook_addr, _HOOK_PATCH_SIZE)
        except Exception as exc:
            app.log("Substitution hook: failed to read hook site", exc, exc_info=True)
            return False, "patch_failed"

        expected = bytes(app.offsets.SUBHOOKORIGBYTES)
        if live_bytes == expected:
            pass  # untouched, safe to patch
        elif len(live_bytes) == 8 and live_bytes[0] == 0xE9 and live_bytes[5:8] == b"\x90\x90\x90":
            app.log("Substitution hook: hook site already patched by an earlier CGFS session")
            return False, "already_hooked"
        else:
            app.log(
                "Substitution hook: unrecognized bytes at hook site "
                f"0x{hook_addr:X} (expected {expected.hex()}, found {live_bytes.hex()}) — aborting"
            )
            return False, "unsafe_build"

        cave_addr = self._find_cave_address(hook_addr)
        if cave_addr is None:
            app.log("Substitution hook: could not allocate a code cave within jmp range")
            return False, "alloc_failed"

        data_addr = cave_addr
        code_addr = cave_addr + _PAGE_SIZE
        slot_addr = data_addr + _DATA_SLOT_OFFSET
        shellcode = self._build_shellcode(hook_addr, code_addr, data_addr, expected)

        try:
            app.memory.write_process_memory(data_addr, b"\x00" * 16)
            app.memory.write_process_memory(code_addr, shellcode)
        except Exception as exc:
            app.log("Substitution hook: failed to write code cave", exc, exc_info=True)
            return False, "alloc_failed"

        if not self._set_protection(code_addr, _PAGE_SIZE, _PAGE_EXECUTE_READ):
            app.log("Substitution hook: failed to mark code cave executable")
            return False, "alloc_failed"

        patch = self._build_hook_patch(hook_addr, code_addr)
        if not self._patch_hook_site(hook_addr, patch):
            app.log("Substitution hook: failed to patch hook site")
            return False, "patch_failed"

        try:
            readback = app.memory.read_process_memory(hook_addr, _HOOK_PATCH_SIZE)
        except Exception as exc:
            app.log("Substitution hook: readback failed after patching", exc, exc_info=True)
            return False, "patch_failed"
        if readback != patch:
            app.log(
                "Substitution hook: readback mismatch after patching hook site — "
                "hook may be partially applied, restart FIFA to be safe"
            )
            return False, "patch_failed"

        self._hook = _HookState(process_id=pid, hook_address=hook_addr, code_address=code_addr, slot_address=slot_addr)
        app.log(f"Substitution hook installed: hook=0x{hook_addr:X} cave=0x{cave_addr:X}")
        return True, "ok"

    def _build_shellcode(self, hook_addr: int, code_addr: int, data_addr: int, orig_bytes: bytes) -> bytes:
        scratch_addr = data_addr + _DATA_SCRATCH_OFFSET
        slot_addr = data_addr + _DATA_SLOT_OFFSET

        save_rax_addr = code_addr
        save_rax = b"\x48\x89\x05" + _rel32(save_rax_addr, 7, scratch_addr)

        lea_addr = save_rax_addr + len(save_rax)
        lea_rax = bytes.fromhex("4B8D84348CA70000")  # lea rax,[r12+r14+0xA78C]

        store_slot_addr = lea_addr + len(lea_rax)
        store_slot = b"\x48\x89\x05" + _rel32(store_slot_addr, 7, slot_addr)

        restore_rax_addr = store_slot_addr + len(store_slot)
        restore_rax = b"\x48\x8B\x05" + _rel32(restore_rax_addr, 7, scratch_addr)

        replay_addr = restore_rax_addr + len(restore_rax)
        replay = bytes(orig_bytes)

        jmp_back_addr = replay_addr + len(replay)
        jmp_back = b"\xE9" + _rel32(jmp_back_addr, 5, hook_addr + _HOOK_PATCH_SIZE)

        return save_rax + lea_rax + store_slot + restore_rax + replay + jmp_back

    @staticmethod
    def _build_hook_patch(hook_addr: int, code_addr: int) -> bytes:
        return b"\xE9" + _rel32(hook_addr, 5, code_addr) + b"\x90\x90\x90"

    # ── Bounded poll + final write ──────────────────────────────────────────

    def _poll_tick(self, generation: int, attempts_left: int) -> None:
        self._poll_job = None
        app = self.app
        if generation != self._poll_generation or app._closing:
            return
        hook = self._hook
        if hook is None or not app.memory.is_open() or app.memory.process_id != hook.process_id:
            app.log("Substitution hook: FIFA closed or restarted mid-poll")
            self._hook = None
            self._report("fifa_changed")
            return

        try:
            raw = app.memory.read_int64(hook.slot_address)
        except Exception as exc:
            app.log("Substitution hook: failed to read recorded pointer", exc, exc_info=True)
            raw = 0

        if raw == 0:
            if attempts_left <= 0:
                if self._armed_addresses:
                    # One side (whichever subbed first) already got the write — report that
                    # instead of a bare timeout, and let the user re-trigger for the other side.
                    self._report("armed_partial", count=self._pending_count)
                else:
                    self._report("timeout")
                return
            self._poll_job = app.after(POLL_INTERVAL_MS, lambda: self._poll_tick(generation, attempts_left - 1))
            return

        if not self._is_plausible_target(raw):
            app.log(f"Substitution hook: resolved pointer 0x{raw:X} failed plausibility check — aborting write")
            self._report("invalid_pointer")
            return

        try:
            app.memory.write_process_memory(raw, struct.pack("<i", self._pending_count))
        except Exception as exc:
            app.log("Substitution hook: final write failed", exc, exc_info=True)
            self._report("write_failed", error=str(exc))
            return

        is_new_side = raw not in self._armed_addresses
        self._armed_addresses.add(raw)
        app.log(
            f"Substitution hook: armed {self._pending_count} substitutions at 0x{raw:X} "
            f"({len(self._armed_addresses)}/{EXPECTED_SIDES} sides)"
        )

        if len(self._armed_addresses) >= EXPECTED_SIDES:
            self._report("armed", count=self._pending_count)
            return

        # Only one side armed so far. Re-zero the slot so the SAME team's next substitution
        # isn't mistaken for the other side's first one, then keep watching — the other team's
        # own first substitution may not happen for a long time yet.
        try:
            app.memory.write_process_memory(hook.slot_address, b"\x00" * 8)
        except Exception as exc:
            app.log("Substitution hook: failed to re-clear recorded-pointer slot", exc, exc_info=True)
            self._report("write_failed", error=str(exc))
            return

        if is_new_side:
            self._report("armed_progress", count=self._pending_count, armed=len(self._armed_addresses))
        self._poll_job = app.after(
            POLL_INTERVAL_MS,
            lambda: self._poll_tick(generation, POLL_TIMEOUT_SECOND_SIDE_MS // POLL_INTERVAL_MS),
        )

    def _cancel_poll(self) -> None:
        if self._poll_job is not None:
            try:
                self.app.after_cancel(self._poll_job)
            except Exception:
                pass
            self._poll_job = None

    def _report(self, code: str, **kwargs) -> None:
        self.app._on_substitution_status(code, **kwargs)

    # ── Low-level WinAPI helpers (raw ctypes against app.memory.kernel32 /
    # app.memory.process_handle, following the match_string_patcher.py precedent for
    # specialized needs that don't belong in the shared Memory class) ─────────

    def _find_cave_address(self, hook_addr: int) -> int | None:
        app = self.app
        kernel32 = app.memory.kernel32
        kernel32.VirtualAllocEx.restype = wintypes.LPVOID
        kernel32.VirtualAllocEx.argtypes = [
            wintypes.HANDLE, wintypes.LPVOID, ctypes.c_size_t, wintypes.DWORD, wintypes.DWORD,
        ]
        handle = app.memory.process_handle
        distance = _ALLOC_GRANULARITY
        while distance <= _MAX_CAVE_DISTANCE:
            for candidate in (hook_addr + distance, hook_addr - distance):
                aligned = candidate - (candidate % _ALLOC_GRANULARITY)
                if aligned <= 0:
                    continue
                addr = kernel32.VirtualAllocEx(
                    handle, ctypes.c_void_p(aligned), _CAVE_ALLOC_SIZE,
                    _MEM_COMMIT | _MEM_RESERVE, _PAGE_READWRITE,
                )
                if addr:
                    return addr
            distance *= 2
        return self._find_cave_address_via_scan(hook_addr)

    def _find_cave_address_via_scan(self, hook_addr: int) -> int | None:
        app = self.app
        kernel32 = app.memory.kernel32
        handle = app.memory.process_handle
        kernel32.VirtualQueryEx.restype = ctypes.c_size_t
        kernel32.VirtualQueryEx.argtypes = [
            wintypes.HANDLE, ctypes.c_void_p, ctypes.POINTER(MEMORY_BASIC_INFORMATION), ctypes.c_size_t,
        ]
        kernel32.VirtualAllocEx.restype = wintypes.LPVOID
        kernel32.VirtualAllocEx.argtypes = [
            wintypes.HANDLE, wintypes.LPVOID, ctypes.c_size_t, wintypes.DWORD, wintypes.DWORD,
        ]
        start = max(_ALLOC_GRANULARITY, hook_addr - _MAX_CAVE_DISTANCE)
        end = hook_addr + _MAX_CAVE_DISTANCE
        addr = start - (start % _ALLOC_GRANULARITY)
        mbi = MEMORY_BASIC_INFORMATION()
        while addr < end:
            ret = kernel32.VirtualQueryEx(handle, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi))
            if ret == 0:
                break
            if mbi.State == _MEM_FREE and mbi.RegionSize >= _CAVE_ALLOC_SIZE:
                aligned = addr - (addr % _ALLOC_GRANULARITY)
                if aligned < addr:
                    aligned += _ALLOC_GRANULARITY
                allocated = kernel32.VirtualAllocEx(
                    handle, ctypes.c_void_p(aligned), _CAVE_ALLOC_SIZE,
                    _MEM_COMMIT | _MEM_RESERVE, _PAGE_READWRITE,
                )
                if allocated:
                    return allocated
            addr += max(mbi.RegionSize, _ALLOC_GRANULARITY)
        return None

    def _set_protection(self, address: int, size: int, protect: int) -> bool:
        app = self.app
        kernel32 = app.memory.kernel32
        kernel32.VirtualProtectEx.restype = wintypes.BOOL
        kernel32.VirtualProtectEx.argtypes = [
            wintypes.HANDLE, wintypes.LPVOID, ctypes.c_size_t, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
        ]
        old = wintypes.DWORD()
        ok = kernel32.VirtualProtectEx(app.memory.process_handle, ctypes.c_void_p(address), size, protect, ctypes.byref(old))
        return bool(ok)

    def _patch_hook_site(self, hook_addr: int, patch: bytes) -> bool:
        # Deliberately NOT using Memory.write_process_memory here: it leaves the target page(s)
        # PAGE_READWRITE afterward with no restore, which is harmless for ordinary data writes
        # (heap pages are PAGE_READWRITE anyway) but would leave this *code* page non-executable
        # — the very next time the game's control flow reaches this address, it would fault.
        # Restore the original (executable) protection after writing, exactly like the existing
        # match_string_patcher.py precedent.
        app = self.app
        kernel32 = app.memory.kernel32
        kernel32.VirtualProtectEx.restype = wintypes.BOOL
        kernel32.VirtualProtectEx.argtypes = [
            wintypes.HANDLE, wintypes.LPVOID, ctypes.c_size_t, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
        ]
        kernel32.WriteProcessMemory.restype = wintypes.BOOL
        kernel32.WriteProcessMemory.argtypes = [
            wintypes.HANDLE, wintypes.LPVOID, wintypes.LPCVOID, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t),
        ]
        handle = app.memory.process_handle
        old_protect = wintypes.DWORD()
        if not kernel32.VirtualProtectEx(handle, ctypes.c_void_p(hook_addr), len(patch), _PAGE_EXECUTE_READWRITE, ctypes.byref(old_protect)):
            return False
        written = ctypes.c_size_t()
        ok = kernel32.WriteProcessMemory(handle, ctypes.c_void_p(hook_addr), patch, len(patch), ctypes.byref(written))
        restore_dummy = wintypes.DWORD()
        kernel32.VirtualProtectEx(handle, ctypes.c_void_p(hook_addr), len(patch), old_protect.value, ctypes.byref(restore_dummy))
        return bool(ok) and written.value == len(patch)

    def _is_plausible_target(self, address: int) -> bool:
        if not (0x10000 <= address < 0x00007FFFFFFFFFFF):
            return False
        app = self.app
        kernel32 = app.memory.kernel32
        kernel32.VirtualQueryEx.restype = ctypes.c_size_t
        kernel32.VirtualQueryEx.argtypes = [
            wintypes.HANDLE, ctypes.c_void_p, ctypes.POINTER(MEMORY_BASIC_INFORMATION), ctypes.c_size_t,
        ]
        mbi = MEMORY_BASIC_INFORMATION()
        ret = kernel32.VirtualQueryEx(app.memory.process_handle, ctypes.c_void_p(address), ctypes.byref(mbi), ctypes.sizeof(mbi))
        if ret == 0 or mbi.State != _MEM_COMMIT:
            return False
        if mbi.Protect & _PAGE_GUARD or (mbi.Protect & 0xFF) == _PAGE_NOACCESS:
            return False
        return (mbi.Protect & 0xFF) in _WRITABLE_PROTECTIONS
