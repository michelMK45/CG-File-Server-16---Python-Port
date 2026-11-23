"""Goal-net rope level per stadium, for the SERVER16_Ropes.asi FIFA Plugin Loader plugin.

The level is the 6th field of a [stadiumnetname]/[stadiumnetid] net value
(``down,high,rig,shape,tension,ropes``) -- the format of the forum author's Server 16 build:
0 all ropes, 1 hide the centre ropes, 2 hide centre + top rope, 3 hide all ropes.
Only the first five fields go into the game's memory (AssetRuntime.tv_bumper_page); the rope
level goes to the plugin through the named shared memory below, and the plugin cuts the rope
draw at render time (server16_py/ropes_plugin/SERVER16_Ropes.cpp, docs/ropes-plugin.md).

A net value without a 6th field has no rope level: the plugin then uses Level= of its own
plugins\\SERVER16_Ropes.ini. Fields after the 6th (the author's 7th "physics" field) are kept
untouched by the editor. The author's earlier 8-field test format (three 0/1 flags
hide_centre,hide_top,hide_all in fields 6-8) is read as the matching level.

_RopesShared MUST match ``RopesShared`` in SERVER16_Ropes.cpp by hand (64 bytes, pack 4).
"""
from __future__ import annotations

import ctypes
import shutil
from ctypes import wintypes
from pathlib import Path
from typing import Callable

from . import plugin_loader

PLUGIN_FILE = "SERVER16_Ropes.asi"  # bundled as <resource_dir>/bin/SERVER16_Ropes.asi, installed in <game>/plugins/
PLUGIN_INI = "SERVER16_Ropes.ini"   # the plugin's own settings (Level=, Log=), created by the plugin
# Name of the first builds (2026-11-23, renamed the same day). Setup removes these copies (two loaded
# copies would both hook D3D11) and carries the old ini over; until then the state reads "outdated".
LEGACY_PLUGIN_FILES = ("cgfs16_ropes.asi",)
LEGACY_PLUGIN_INI = "cgfs16_ropes.ini"
LEGACY_PLUGIN_LOG = "cgfs16_ropes.log"

# plugin_state() results
STATE_INSTALLED = "installed"
STATE_OUTDATED = "outdated"    # differs from the copy bundled with this Server
STATE_DISABLED = "disabled"    # only plugins/SERVER16_Ropes.asi.disabled (switched off in the Plugins tab)
STATE_MISSING = "missing"
STATE_NO_LOADER = "no_loader"  # FIFA Plugin Loader (winmm.dll) not installed: no .asi can load

ROPE_FIELD = 5  # index of the rope level in the comma-separated net value
ROPE_LEVELS = (0, 1, 2, 3)
NOT_SET = -1  # shared-memory level meaning "no level from the Server": the plugin ini decides

SHARED_NAME = "Local\\CGFS16_Ropes_v1"
MAGIC = 0x50524743  # 'CGRP'
VERSION = 1
FLAG_DEVICE_HOOKED = 1 << 1  # plugin_flags bit: the plugin is loaded in FIFA and hooked D3D11


class _RopesShared(ctypes.Structure):
    _pack_ = 4
    _fields_ = [
        ("magic", ctypes.c_uint32),
        ("version", ctypes.c_uint32),
        ("level", ctypes.c_int32),
        ("plugin_flags", ctypes.c_int32),
        ("rope_draws", ctypes.c_int32),
        ("rope_draws_cut", ctypes.c_int32),
        ("effective_level", ctypes.c_int32),
        ("reserved", ctypes.c_uint32 * 9),
    ]


assert ctypes.sizeof(_RopesShared) == 64, "RopesShared layout is part of the plugin contract"


def _parts(net_value: str | None) -> list[str]:
    return [part.strip() for part in (net_value or "").split(",")] if net_value else []


def _is_legacy_flags(parts: list[str]) -> bool:
    return len(parts) >= 8 and all(p in {"0", "1"} for p in parts[5:8])


def rope_level(net_value: str | None) -> int | None:
    """The rope level of a net value, or None when it has none (5 fields, empty or invalid 6th)."""
    parts = _parts(net_value)
    if _is_legacy_flags(parts):
        return 3 if parts[7] == "1" else 2 if parts[6] == "1" else 1 if parts[5] == "1" else 0
    if len(parts) > ROPE_FIELD and parts[ROPE_FIELD] in {"0", "1", "2", "3"}:
        return int(parts[ROPE_FIELD])
    return None


def split_net_value(net_value: str | None) -> tuple[int, list[str]]:
    """(rope level for the editor, the fields after it to keep). Missing level -> 0."""
    parts = _parts(net_value)
    level = rope_level(net_value)
    extra = [] if _is_legacy_flags(parts) else parts[ROPE_FIELD + 1:]
    return (level if level is not None else 0), extra


def compose_net_value(first_five: list[str], level: int, extra: list[str] | None = None) -> str:
    """Net value with the rope level as 6th field. Level 0 with nothing after it keeps the
    classic 5-field value, so a stadium that does not use ropes is saved exactly as before."""
    extra = list(extra or [])
    fields = list(first_five[:ROPE_FIELD])
    if level == 0 and not extra:
        return ",".join(fields)
    return ",".join(fields + [str(level)] + extra)


# ---------------------------------------------------------------------------------------------
# Plugin file (Setup installs it, the net editor warns when it is not usable)
# ---------------------------------------------------------------------------------------------
def bundled_plugin(resource_dir: Path | None) -> Path | None:
    """The plugin shipped with this Server (bin/), or None when this build has none."""
    if resource_dir is None:
        return None
    path = Path(resource_dir) / "bin" / PLUGIN_FILE
    return path if path.is_file() else None


def _find(folder: Path, file_name: str) -> tuple[Path, bool] | None:
    for path, enabled in ((folder / file_name, True),
                          (folder / (file_name + plugin_loader.DISABLED_SUFFIX), False)):
        if path.is_file():
            return path, enabled
    return None


def installed_plugin(game_dir: Path) -> tuple[Path, bool] | None:
    """(file, enabled) of the plugin in <game>/plugins/, or None. An enabled copy wins."""
    return _find(plugin_loader.plugins_dir(game_dir), PLUGIN_FILE)


def legacy_plugins(game_dir: Path) -> list[tuple[Path, bool]]:
    """Copies under an old plugin name, enabled or switched off."""
    folder = plugin_loader.plugins_dir(game_dir)
    return [found for name in LEGACY_PLUGIN_FILES if (found := _find(folder, name))]


def _same_file(a: Path, b: Path) -> bool:
    try:
        return a.stat().st_size == b.stat().st_size and a.read_bytes() == b.read_bytes()
    except OSError:
        return False


def plugin_state(game_dir: Path, bundled: Path | None) -> str:
    """One of the STATE_* values. A missing loader comes first: without it no plugin loads."""
    if not plugin_loader.is_loader_installed(game_dir):
        return STATE_NO_LOADER
    found = installed_plugin(game_dir)
    legacy = legacy_plugins(game_dir)
    if found is None:
        return STATE_OUTDATED if legacy else STATE_MISSING
    path, enabled = found
    if not enabled:
        return STATE_DISABLED
    if legacy or (bundled is not None and not _same_file(path, bundled)):
        return STATE_OUTDATED
    return STATE_INSTALLED


def install_plugin(game_dir: Path, bundled: Path) -> Path:
    """Copies the bundled plugin into <game>/plugins/. A copy switched off in the Plugins tab is
    updated in place and stays off; so does a switched-off copy under an old name, which is
    removed, its ini carried over when the new one does not exist yet. Raises OSError
    (PermissionError while FIFA has a plugin file loaded)."""
    folder = plugin_loader.plugins_dir(game_dir)
    found = installed_plugin(game_dir)
    legacy = legacy_plugins(game_dir)
    if found:
        target = found[0]
    else:
        enabled = all(on for _path, on in legacy) if legacy else True
        target = folder / (PLUGIN_FILE if enabled else PLUGIN_FILE + plugin_loader.DISABLED_SUFFIX)
    folder.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(bundled, target)
    for path, _enabled in legacy:
        path.unlink()
    old_ini, new_ini = folder / LEGACY_PLUGIN_INI, folder / PLUGIN_INI
    if old_ini.is_file() and not new_ini.exists():
        old_ini.rename(new_ini)
    (folder / LEGACY_PLUGIN_LOG).unlink(missing_ok=True)
    return target


# ---------------------------------------------------------------------------------------------
# Shared memory
# ---------------------------------------------------------------------------------------------
_PAGE_READWRITE = 0x04
_FILE_MAP_ALL_ACCESS = 0x000F001F
_ERROR_ALREADY_EXISTS = 183
_INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

_k32 = None


def _kernel32():
    """Own kernel32 handle with its own argtypes (other modules set theirs on the shared one)."""
    global _k32
    if _k32 is None:
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateFileMappingW.restype = wintypes.HANDLE
        k32.CreateFileMappingW.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD,
                                           wintypes.DWORD, wintypes.LPCWSTR]
        k32.MapViewOfFile.restype = ctypes.c_void_p
        k32.MapViewOfFile.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
                                      ctypes.c_size_t]
        k32.UnmapViewOfFile.argtypes = [ctypes.c_void_p]
        k32.CloseHandle.argtypes = [wintypes.HANDLE]
        _k32 = k32
    return _k32


class RopesBridge:
    """Server side of Local\\CGFS16_Ropes_v1. Opened lazily; whichever side creates the mapping
    (FIFA's plugin or the Server) initialises magic/version and level = NOT_SET."""

    def __init__(self, log: Callable[[str], None] = lambda _m: None) -> None:
        self._log = log
        self._handle = None
        self._view = None
        self._shared: _RopesShared | None = None
        self._failed_logged = False

    def _open(self) -> bool:
        if self._shared is not None:
            return True
        try:
            k32 = _kernel32()
            handle = k32.CreateFileMappingW(_INVALID_HANDLE_VALUE, None, _PAGE_READWRITE, 0,
                                            ctypes.sizeof(_RopesShared), SHARED_NAME)
            if not handle:
                raise OSError(f"CreateFileMappingW error {ctypes.get_last_error()}")
            view = k32.MapViewOfFile(handle, _FILE_MAP_ALL_ACCESS, 0, 0, ctypes.sizeof(_RopesShared))
            if not view:
                error = ctypes.get_last_error()
                k32.CloseHandle(handle)
                raise OSError(f"MapViewOfFile error {error}")
        except (OSError, AttributeError) as exc:
            if not self._failed_logged:
                self._log(f"Net ropes: shared memory {SHARED_NAME} unavailable ({exc})")
                self._failed_logged = True
            return False
        shared = _RopesShared.from_address(view)
        if shared.magic != MAGIC or shared.version != VERSION:
            shared.level = NOT_SET
            shared.plugin_flags = 0
            shared.version = VERSION
            shared.magic = MAGIC
        self._handle, self._view, self._shared = handle, view, shared
        return True

    def set_level(self, level: int | None) -> bool:
        """Hand the stadium's rope level to the plugin; None = no level (the plugin ini decides)."""
        if not self._open():
            return False
        self._shared.level = level if level in ROPE_LEVELS else NOT_SET
        return True

    def plugin_active(self) -> bool:
        """True once SERVER16_Ropes.asi, loaded in the running FIFA, has hooked D3D11."""
        return bool(self._open() and self._shared.plugin_flags & FLAG_DEVICE_HOOKED)

    def close(self) -> None:
        if self._shared is None:
            return
        k32 = _kernel32()
        k32.UnmapViewOfFile(self._view)
        k32.CloseHandle(self._handle)
        self._handle = self._view = self._shared = None
