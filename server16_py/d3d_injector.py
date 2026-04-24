"""
d3d_injector.py
───────────────
Manages the D3D overlay DLL injection into FIFA 16 and the shared-memory
channel used to control what the overlay displays.

Usage (from app.py):
    injector = D3DOverlayInjector(dll_path="runtime/cgfs16_overlay.dll")
    injector.inject(fifa_pid)       # call once when FIFA is detected
    injector.show("Bernabéu", "Copying files...", 0.0)
    injector.update(42.0, "Copying files...")
    injector.hide()
    injector.destroy()              # call on app exit
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import logging
import os
import threading
from pathlib import Path

log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Shared memory layout — MUST match OverlayShared in cgfs16_overlay.cpp
# ─────────────────────────────────────────────────────────────────────────────
_SHMEM_NAME = "Local\\CGFS16_Overlay_v1"
_MAX_STR    = 256
_MAX_IMG    = 512


class _OverlayShared(ctypes.Structure):
    _fields_ = [
        ("visible",       ctypes.c_long),           # 0 = hide, 1 = show
        ("progress_x100", ctypes.c_long),           # progress * 100  (0–10000)
        ("stadium_name",  ctypes.c_wchar * _MAX_STR),
        ("detail_text",   ctypes.c_wchar * _MAX_STR),
        ("image_path",    ctypes.c_wchar * _MAX_IMG),  # abs path to preview image
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Win32 constants & kernel32 setup
# ─────────────────────────────────────────────────────────────────────────────
_PROCESS_CREATE_THREAD    = 0x0002
_PROCESS_VM_OPERATION     = 0x0008
_PROCESS_VM_WRITE         = 0x0020
_PROCESS_VM_READ          = 0x0010
_PROCESS_QUERY_INFORMATION = 0x0400
_MEM_COMMIT               = 0x1000
_MEM_RESERVE              = 0x2000
_MEM_RELEASE              = 0x8000
_PAGE_READWRITE           = 0x04
_FILE_MAP_ALL_ACCESS      = 0xF001F
_INVALID_HANDLE_VALUE     = ctypes.c_void_p(-1).value


def _configure_kernel32() -> ctypes.WinDLL:
    k = ctypes.WinDLL("kernel32", use_last_error=True)

    HANDLE  = wintypes.HANDLE
    BOOL    = wintypes.BOOL
    DWORD   = wintypes.DWORD
    LPCWSTR = wintypes.LPCWSTR
    LPVOID  = ctypes.c_void_p
    SIZE_T  = ctypes.c_size_t

    k.OpenProcess.argtypes  = [DWORD, BOOL, DWORD]
    k.OpenProcess.restype   = HANDLE

    k.VirtualAllocEx.argtypes = [HANDLE, LPVOID, SIZE_T, DWORD, DWORD]
    k.VirtualAllocEx.restype  = LPVOID

    k.WriteProcessMemory.argtypes = [
        HANDLE, LPVOID, LPVOID, SIZE_T, ctypes.POINTER(SIZE_T)]
    k.WriteProcessMemory.restype  = BOOL

    k.VirtualFreeEx.argtypes  = [HANDLE, LPVOID, SIZE_T, DWORD]
    k.VirtualFreeEx.restype   = BOOL

    k.CreateRemoteThread.argtypes = [
        HANDLE, LPVOID, SIZE_T, LPVOID, LPVOID, DWORD, ctypes.POINTER(DWORD)]
    k.CreateRemoteThread.restype  = HANDLE

    k.WaitForSingleObject.argtypes = [HANDLE, DWORD]
    k.WaitForSingleObject.restype  = DWORD

    k.CloseHandle.argtypes  = [HANDLE]
    k.CloseHandle.restype   = BOOL

    k.GetModuleHandleW.argtypes = [LPCWSTR]
    k.GetModuleHandleW.restype  = wintypes.HMODULE

    k.GetProcAddress.argtypes = [wintypes.HMODULE, ctypes.c_char_p]
    k.GetProcAddress.restype  = LPVOID

    k.CreateFileMappingW.argtypes = [
        HANDLE, LPVOID, DWORD, DWORD, DWORD, LPCWSTR]
    k.CreateFileMappingW.restype  = HANDLE

    k.MapViewOfFile.argtypes = [HANDLE, DWORD, DWORD, DWORD, SIZE_T]
    k.MapViewOfFile.restype  = LPVOID

    k.UnmapViewOfFile.argtypes = [LPVOID]
    k.UnmapViewOfFile.restype  = BOOL

    return k


_k32 = _configure_kernel32()


# ─────────────────────────────────────────────────────────────────────────────
# D3DOverlayInjector
# ─────────────────────────────────────────────────────────────────────────────
class D3DOverlayInjector:
    """Injects cgfs16_overlay.dll into FIFA 16 and drives it via shared memory."""

    def __init__(self, dll_path: str | Path) -> None:
        self._dll_path     = str(Path(dll_path).resolve())
        self._hmap: int    = 0
        self._shared_ptr   = 0          # raw address returned by MapViewOfFile
        self._shared: _OverlayShared | None = None
        self._injected_pid = 0
        self._lock         = threading.Lock()
        self._ready        = False

        self._open_shared_memory()

    # ── Public ────────────────────────────────────────────────────────────────

    def is_ready(self) -> bool:
        """True if shared memory is mapped, the DLL exists, and the injector exe exists."""
        return (self._ready
                and os.path.isfile(self._dll_path)
                and self._find_inject_exe() is not None)

    def is_injected(self, pid: int = 0) -> bool:
        if pid:
            return self._injected_pid == pid
        return self._injected_pid != 0

    def inject(self, pid: int) -> bool:
        """Inject the DLL into *pid*.  Safe to call multiple times for the same pid."""
        if not self._ready:
            log.error("D3DOverlay: shared memory not ready")
            return False
        if not os.path.isfile(self._dll_path):
            log.error("D3DOverlay: DLL not found: %s", self._dll_path)
            return False
        with self._lock:
            if self._injected_pid == pid:
                return True
            ok = self._do_inject(pid)
            if ok:
                self._injected_pid = pid
            return ok

    def show(self, stadium_name: str, detail: str = "", progress: float = 0.0,
             image_path: str = "") -> None:
        if not self._ready or self._shared is None:
            return
        self._shared.stadium_name  = stadium_name[:_MAX_STR - 1]
        self._shared.detail_text   = detail[:_MAX_STR - 1]
        self._shared.image_path    = image_path[:_MAX_IMG - 1]
        self._shared.progress_x100 = int(max(0.0, min(100.0, progress)) * 100)
        # Write visible LAST so the DLL sees consistent data
        self._shared.visible = 1

    def update(self, progress: float, detail: str = "") -> None:
        if not self._ready or self._shared is None:
            return
        if detail:
            self._shared.detail_text = detail[:_MAX_STR - 1]
        self._shared.progress_x100 = int(max(0.0, min(100.0, progress)) * 100)

    def hide(self) -> None:
        if self._shared is not None:
            self._shared.visible = 0

    def reset_injected(self) -> None:
        """Call when FIFA exits so we re-inject on the next launch."""
        with self._lock:
            self._injected_pid = 0

    def destroy(self) -> None:
        self.hide()
        if self._shared_ptr:
            try:
                _k32.UnmapViewOfFile(self._shared_ptr)
            except Exception:
                pass
            self._shared_ptr = 0
            self._shared     = None
        if self._hmap:
            try:
                _k32.CloseHandle(self._hmap)
            except Exception:
                pass
            self._hmap = 0
        self._ready = False

    # ── Private ───────────────────────────────────────────────────────────────

    def _open_shared_memory(self) -> None:
        hmap = _k32.CreateFileMappingW(
            _INVALID_HANDLE_VALUE, None, _PAGE_READWRITE,
            0, ctypes.sizeof(_OverlayShared),
            _SHMEM_NAME)
        if not hmap:
            log.error("D3DOverlay: CreateFileMappingW failed (err=%d)",
                      ctypes.get_last_error())
            return

        ptr = _k32.MapViewOfFile(
            hmap, _FILE_MAP_ALL_ACCESS, 0, 0,
            ctypes.sizeof(_OverlayShared))
        if not ptr:
            log.error("D3DOverlay: MapViewOfFile failed (err=%d)",
                      ctypes.get_last_error())
            _k32.CloseHandle(hmap)
            return

        self._hmap       = hmap
        self._shared_ptr = ptr
        self._shared     = _OverlayShared.from_address(ptr)
        # Reset to hidden on startup
        self._shared.visible       = 0
        self._shared.progress_x100 = 0
        self._shared.stadium_name  = ""
        self._shared.detail_text   = ""
        self._shared.image_path    = ""
        self._ready = True
        log.debug("D3DOverlay: shared memory opened at 0x%X, size=%d",
                  ptr, ctypes.sizeof(_OverlayShared))

    def _find_inject_exe(self) -> str | None:
        """Locate the x86 injector helper exe (next to DLL or in runtime/)."""
        dll_p = Path(self._dll_path)
        candidates = [
            dll_p.parent / "cgfs16_inject.exe",           # e.g. bin/
            dll_p.parent.parent / "runtime" / "cgfs16_inject.exe",
        ]
        for c in candidates:
            if c.exists():
                return str(c)
        return None

    def _do_inject(self, pid: int) -> bool:
        """Inject via the x86 cgfs16_inject.exe helper.

        FIFA 16 is a 32-bit process.  Our Python host is 64-bit, so any
        GetProcAddress(LoadLibraryW) we obtain here is a 64-bit address
        that is invalid inside the 32-bit target.  The x86 helper exe
        solves this: being 32-bit itself, it holds the correct 32-bit
        LoadLibraryW address for the WOW64 target.
        """
        import subprocess

        injector = self._find_inject_exe()
        if not injector:
            log.error("D3DOverlay: cgfs16_inject.exe not found "
                      "(run build.bat to compile it)")
            return False

        log.debug("D3DOverlay: running injector: %s %s %s",
                  injector, pid, self._dll_path)
        try:
            result = subprocess.run(
                [injector, str(pid), self._dll_path],
                capture_output=True,
                timeout=12,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except subprocess.TimeoutExpired:
            log.error("D3DOverlay: cgfs16_inject.exe timed out")
            return False
        except Exception as exc:
            log.error("D3DOverlay: failed to run injector: %s", exc)
            return False

        # The C exe writes narrow (ANSI) text to stderr/stdout even though
        # it uses fwprintf — on Windows pipes the CRT converts wide chars
        # to the ANSI codepage, so decode with 'mbcs' (system ANSI codepage).
        def _decode(b: bytes) -> str:
            for enc in ('mbcs', 'latin-1', 'utf-8'):
                try:
                    return b.decode(enc, errors='replace').strip()
                except Exception:
                    continue
            return repr(b)

        stdout = _decode(result.stdout)
        stderr = _decode(result.stderr)
        log.debug("D3DOverlay: inject helper stdout=%r stderr=%r rc=%d",
                  stdout, stderr, result.returncode)
        if result.returncode != 0:
            log.error("D3DOverlay: inject helper failed (rc=%d): %s",
                      result.returncode, stderr or stdout)
            return False

        log.info("D3DOverlay: DLL injected into pid %d (%s)", pid, stdout)
        return True
