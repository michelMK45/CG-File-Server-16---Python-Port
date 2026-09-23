from __future__ import annotations

import ctypes
import os
import tempfile
from ctypes import wintypes
from pathlib import Path


class _SHELLEXECUTEINFOW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("fMask", ctypes.c_ulong),
        ("hwnd", wintypes.HWND),
        ("lpVerb", wintypes.LPCWSTR),
        ("lpFile", wintypes.LPCWSTR),
        ("lpParameters", wintypes.LPCWSTR),
        ("lpDirectory", wintypes.LPCWSTR),
        ("nShow", ctypes.c_int),
        ("hInstApp", wintypes.HINSTANCE),
        ("lpIDList", ctypes.c_void_p),
        ("lpClass", wintypes.LPCWSTR),
        ("hKeyClass", wintypes.HKEY),
        ("dwHotKey", wintypes.DWORD),
        ("hIcon", wintypes.HANDLE),
        ("hProcess", wintypes.HANDLE),
    ]


_SEE_MASK_NOCLOSEPROCESS = 0x00000040
_SW_SHOWNORMAL = 1


def shell_execute_elevated_and_wait(file: str, params: str) -> bool:
    """Launches `file` with `params` elevated (UAC "runas" verb) and blocks
    the calling thread until the elevated process exits.

    Returns whether the process was actually launched (elevation accepted)
    -- NOT whether whatever it did succeeded. Callers must re-check
    real-world state afterward (a registry key, a re-run listing command)
    rather than trust an exit code alone: neither msiexec's nor an
    arbitrary bootstrapper .exe's exit code has proven reliably meaningful
    for every install/uninstall outcome in this codebase's own live testing
    (see gamepad_bridge_runtime.py's install/uninstall docstrings).

    Blocks the calling thread -- callers running this from the Tk main
    thread must dispatch it to a background thread first."""
    info = _SHELLEXECUTEINFOW()
    info.cbSize = ctypes.sizeof(_SHELLEXECUTEINFOW)
    info.fMask = _SEE_MASK_NOCLOSEPROCESS
    info.hwnd = None
    info.lpVerb = "runas"
    info.lpFile = file
    info.lpParameters = params
    info.lpDirectory = None
    info.nShow = _SW_SHOWNORMAL
    try:
        ok = ctypes.windll.shell32.ShellExecuteExW(ctypes.byref(info))
    except Exception:
        return False
    if not ok or not info.hProcess:
        return False
    try:
        ctypes.windll.kernel32.WaitForSingleObject(info.hProcess, 0xFFFFFFFF)
    finally:
        ctypes.windll.kernel32.CloseHandle(info.hProcess)
    return True


def run_elevated_capture(exe_path: Path, args: list[str]) -> tuple[int | None, str]:
    """Runs exe_path with args elevated, capturing combined stdout+stderr.

    ShellExecuteExW alone can't share stdout handles with an elevated child
    process, so this writes a small one-shot .bat file that redirects the
    real command's output to a temp file, elevates *that* .bat (no
    nested-quoting headaches versus trying to elevate cmd.exe /c "..."
    directly), waits for it, then reads the temp file back -- the same
    technique already used once, ad hoc, for a manual ViGEmBus driver-store
    cleanup during this project's own development (see hidhide_runtime.py
    for why HidHideCLI.exe needs this rather than the simpler
    shell_execute_elevated_and_wait above: its listing commands need their
    JSON/text output captured, not just a pass/fail outcome).

    Returns (exit_code, output); exit_code is None if elevation was
    declined or nothing could be launched at all, in which case output is
    an empty string. Blocks the calling thread, same as the function above."""
    exit_codes, text = run_elevated_capture_many([(exe_path, args)])
    return (exit_codes[0] if exit_codes else None), text


_EXIT_MARKER = "EXITCODE:"


def run_elevated_capture_many(commands: list[tuple[Path | str, list[str]]]) -> tuple[list[int | None], str]:
    """Like run_elevated_capture(), but runs several commands in order from
    the SAME elevated .bat -- one UAC prompt for all of them (e.g. HidHide's
    --dev-hide followed by a pnputil device restart). Every command runs
    even if an earlier one fails.

    Returns (exit_codes, combined_output): one exit code per command (None
    where it couldn't be parsed), or an empty list if elevation was
    declined. Blocks the calling thread."""
    fd_out, out_path_str = tempfile.mkstemp(prefix="cgfs16_elevated_out_", suffix=".log")
    os.close(fd_out)
    fd_bat, bat_path_str = tempfile.mkstemp(prefix="cgfs16_elevated_run_", suffix=".bat")
    os.close(fd_bat)
    out_path, bat_path = Path(out_path_str), Path(bat_path_str)
    lines = ["@echo off"]
    for exe_path, args in commands:
        quoted_args = " ".join(f'"{a}"' for a in args)
        lines.append(f'"{exe_path}" {quoted_args} >> "{out_path}" 2>&1')
        lines.append(f'echo {_EXIT_MARKER}%errorlevel%>> "{out_path}"')
    script = "\r\n".join(lines) + "\r\n"
    try:
        bat_path.write_text(script, encoding="utf-8")
        launched = shell_execute_elevated_and_wait(str(bat_path), "")
        if not launched:
            return [], ""
        try:
            text = out_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            text = ""
    finally:
        for p in (bat_path, out_path):
            try:
                p.unlink()
            except OSError:
                pass
    return _split_exit_markers(text)


def _split_exit_markers(text: str) -> tuple[list[int | None], str]:
    exit_codes: list[int | None] = []
    output_lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(_EXIT_MARKER):
            try:
                exit_codes.append(int(stripped[len(_EXIT_MARKER):].strip()))
            except ValueError:
                exit_codes.append(None)
        else:
            output_lines.append(line)
    output = "\n".join(output_lines)
    if output_lines:
        output += "\n"
    return exit_codes, output
