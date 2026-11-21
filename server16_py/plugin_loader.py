"""Plugins of the third-party FIFA Plugin Loader (``winmm.dll`` next to ``fifa16.exe``).

What the loader does (Ghidra, FIP test install's ``winmm.dll``, sha256 7136fc75…):
``FindFirstFileW("plugins\\*.asi")`` / ``FindNextFileW`` → ``LoadLibraryW`` on every non-directory
match whose name is not already loaded. No count limit, no subfolders, order is whatever Windows
returns. ``*.asi.disabled`` does not match, so renaming is the ON/OFF switch. ``plugins\\loader.ini``
``[LOADER]`` only has ``DEBUG_MODE`` (0 silent; 1/2 message boxes, incl. "Failed to load plugin %s
(error %d)") and ``ANY_PROCESS``. Forum thread: ``LOADER_THREAD_URL``.

Turning a plugin OFF only stops it from loading next time; whatever it installed (DB tables,
assets) stays. CGFS16 never touches FIFA memory here: the "loaded" state comes from the module
list Windows reports for the FIFA process (``Memory.list_module_paths``).

See docs/superpowers/specs/2026-11-20-plugins-tab-design.md.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

LOADER_DLL_NAME = "winmm.dll"
PLUGINS_DIR_NAME = "plugins"
PLUGIN_SUFFIX = ".asi"
DISABLED_SUFFIX = ".disabled"
LOADER_THREAD_URL = "https://soccergaming.com/forums/threads/fifa-16-plugin-loader.6475276/"
_LOADER_MARKER = "FIFA Plugin Loader".encode("utf-16-le")


@dataclass(frozen=True)
class PluginEntry:
    name: str               # display name: file name without ".asi" / ".asi.disabled"
    path: Path              # the file as it is now (the ".asi" one when both exist)
    enabled: bool
    ini_path: Path | None
    conflict: bool = False  # both X.asi and X.asi.disabled exist


def plugins_dir(game_dir: Path) -> Path:
    return Path(game_dir) / PLUGINS_DIR_NAME


def is_loader_installed(game_dir: Path) -> bool:
    try:
        return _LOADER_MARKER in (Path(game_dir) / LOADER_DLL_NAME).read_bytes()
    except OSError:
        return False


def _split_plugin_name(file_name: str) -> tuple[str, bool] | None:
    """(display name, enabled) for an .asi / .asi.disabled file name, else None."""
    lower = file_name.lower()
    if lower.endswith(PLUGIN_SUFFIX + DISABLED_SUFFIX):
        return file_name[: -len(PLUGIN_SUFFIX + DISABLED_SUFFIX)], False
    if lower.endswith(PLUGIN_SUFFIX):
        return file_name[: -len(PLUGIN_SUFFIX)], True
    return None


def _find_ini(game_dir: Path, name: str) -> Path | None:
    wanted = (name + ".ini").casefold()
    for folder in (plugins_dir(game_dir), Path(game_dir)):
        try:
            candidates = sorted(folder.iterdir())
        except OSError:
            continue
        for candidate in candidates:
            if candidate.name.casefold() == wanted and candidate.is_file():
                return candidate
    return None


def scan(game_dir: Path) -> list[PluginEntry]:
    folder = plugins_dir(game_dir)
    try:
        files = [path for path in folder.iterdir() if path.is_file()]
    except OSError:
        return []
    found: dict[str, dict[bool, Path]] = {}
    names: dict[str, str] = {}
    for path in files:
        parsed = _split_plugin_name(path.name)
        if parsed is None or not parsed[0]:
            continue
        name, enabled = parsed
        key = name.casefold()
        found.setdefault(key, {})[enabled] = path
        if enabled or key not in names:
            names[key] = name
    entries = []
    for key, forms in found.items():
        name = names[key]
        enabled = True in forms
        entries.append(PluginEntry(
            name=name,
            path=forms[True] if enabled else forms[False],
            enabled=enabled,
            ini_path=_find_ini(game_dir, name),
            conflict=len(forms) == 2,
        ))
    return sorted(entries, key=lambda entry: entry.name.casefold())


def set_enabled(entry: PluginEntry, enabled: bool) -> Path:
    """Rename ``X.asi`` <-> ``X.asi.disabled``; returns the plugin's new path. Raises
    ``FileExistsError`` for a conflict entry (both files exist) and lets other ``OSError``s through.
    Takes effect the next time FIFA starts (a loaded DLL can still be renamed on Windows)."""
    if entry.conflict:
        raise FileExistsError(f"both {entry.name}.asi and {entry.name}.asi.disabled exist")
    if entry.enabled == enabled:
        return entry.path
    if enabled:
        target = entry.path.with_name(entry.path.name[: -len(DISABLED_SUFFIX)])
    else:
        target = entry.path.with_name(entry.path.name + DISABLED_SUFFIX)
    entry.path.rename(target)
    return target


def _norm(path: str | Path) -> str:
    return os.path.normcase(os.path.abspath(str(path)))


def loaded_states(entries: list[PluginEntry], module_paths: list[str],
                  toggled: set[str]) -> dict[str, bool | None]:
    """Per plugin name: True = loaded in FIFA now, False = ON but not loaded (failed), None = no
    icon (OFF and not loaded, or switched during this FIFA session so the answer would mislead).
    An empty module list means the snapshot failed (a live process always has modules): all None."""
    if not module_paths:
        return {entry.name: None for entry in entries}
    loaded = {_norm(path) for path in module_paths}
    result: dict[str, bool | None] = {}
    for entry in entries:
        expected = _norm(entry.path.parent / (entry.name + PLUGIN_SUFFIX))
        if expected in loaded:
            result[entry.name] = True
        elif entry.enabled and entry.name not in toggled:
            result[entry.name] = False
        else:
            result[entry.name] = None
    return result
