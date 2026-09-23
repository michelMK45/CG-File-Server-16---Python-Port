from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import winreg
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, TYPE_CHECKING

from .win_elevation import shell_execute_elevated_and_wait

if TYPE_CHECKING:
    from .app import Server16App

# Sources disagreed on the exact vendor-folder spelling Nefarius' HidHide
# installer uses (seen reported as both "Nefarius Software Solutions e.U"
# and plain "Nefarius") -- confirmed live 2026-09-24 against a real install
# (HidHide_1.5.230_x64.exe) that NEITHER guess was right: the real path is
# "C:\Program Files\Nefarius Software Solutions\HidHide\x64\HidHideCLI.exe"
# (no "e.U", CLI nested one level deeper under an x64\ subfolder -- the
# existing root.rglob() fallback in find_hidhide_cli() already handles that
# nesting once the root itself is right). Keeping the two earlier guesses
# alongside the confirmed one costs nothing and covers an installer/vendor
# folder rename in a future release.
_CLI_CANDIDATE_DIRS = (
    r"C:\Program Files\Nefarius Software Solutions\HidHide",
    r"C:\Program Files\Nefarius Software Solutions e.U\HidHide",
    r"C:\Program Files\Nefarius\HidHide",
)

_INSTALL_PATH_REGISTRY_KEY = r"SOFTWARE\Nefarius Software Solutions e.U.\Nefarius Software Solutions e.U. HidHide"


def decode_vid_pid_from_sdl_guid(sdl_guid: str) -> tuple[int, int] | None:
    """Decodes (vendor_id, product_id) from an SDL2 joystick GUID hex
    string. SDL2's USB/HID joystick GUID layout: bytes[4:6] = vendor id
    (little-endian uint16), bytes[8:10] = product id (little-endian
    uint16) -- confirmed live this session by decoding a real Switch Pro
    Controller's guid ('030056fb7e0500000920000010026803') and matching
    the result (vendor=0x057E, product=0x2009) against the same device's
    real VID/PID independently confirmed via `Get-PnpDevice`. Shared here
    rather than duplicated in gamepad_bridge_runtime.py, since both modules
    need the same decode (that module only needs the *name* for Switch Pro
    detection today, but this one needs the numeric VID/PID to match
    against HidHideCLI's own device listing)."""
    try:
        raw = bytes.fromhex(sdl_guid)
    except ValueError:
        return None
    if len(raw) < 10:
        return None
    vendor = raw[4] | (raw[5] << 8)
    product = raw[8] | (raw[9] << 8)
    return vendor, product


@dataclass
class HidHideDevice:
    instance_path: str
    xusb_instance_path: str
    vendor: int
    product: int
    description: str
    gaming_device: bool


_VID_RE = re.compile(r"VID[_&]([0-9A-F]{4,8})", re.IGNORECASE)
_PID_RE = re.compile(r"PID[_&]([0-9A-F]{4})", re.IGNORECASE)


def parse_vid_pid_from_instance_path(path: str) -> tuple[int, int] | None:
    """Extracts (vendor_id, product_id) from a PnP instance path or symbolic
    link. Handles both USB-style `HID\\VID_057E&PID_2009\\...` (confirmed
    live) and Bluetooth-style `..._VID&0002057E_PID&2009...`, whose VID
    field carries a 4-digit source prefix (0002 = Bluetooth) before the real
    vendor id -- hence "last four hex digits"."""
    vid_match = _VID_RE.search(path or "")
    pid_match = _PID_RE.search(path or "")
    if vid_match is None or pid_match is None:
        return None
    return int(vid_match.group(1)[-4:], 16), int(pid_match.group(1), 16)


def _as_int_id(value) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def parse_dev_gaming_json(text: str) -> list[HidHideDevice]:
    """Parses `HidHideCLI.exe --dev-gaming`'s JSON output into a flat list of
    HidHideDevice.

    The real output (captured live 2026-09-23 from HidHide 1.5.230) is a
    list of GROUPS, one per physical controller -- `[{"friendlyName": ...,
    "devices": [{...}, ...]}]` -- and each device's `vendor`/`product` are
    human-readable STRINGS ("Nintendo Co., Ltd.", "Pro Controller"), not
    numeric ids. The original parser assumed a flat list with integer ids,
    so every real device came back with vendor=0/product=0 and an empty
    instance path, resolve_device_for_guid() never matched anything, and
    "Hide from FIFA" silently hid nothing -- the reason FIFA kept showing
    the physical pad next to the virtual one. VID/PID now come from the
    instance path/symbolic link instead; an integer vendor/product field is
    still honored if a future HidHide version ever emits one.

    Tolerant of flat lists, a single object, missing fields, and garbage --
    returns an empty list rather than raising, since this always runs
    against real subprocess output that can be empty or malformed for
    reasons unrelated to this parser."""
    try:
        data = json.loads(text)
    except Exception:
        return []
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        return []
    entries: list[tuple[dict, str]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        nested = item.get("devices")
        if isinstance(nested, list):
            group_name = str(item.get("friendlyName", "") or "")
            entries.extend((child, group_name) for child in nested if isinstance(child, dict))
        else:
            entries.append((item, ""))
    devices: list[HidHideDevice] = []
    for entry, group_name in entries:
        instance_path = str(entry.get("deviceInstancePath", "") or "")
        vendor = _as_int_id(entry.get("vendor"))
        product = _as_int_id(entry.get("product"))
        if vendor is None or product is None:
            decoded = parse_vid_pid_from_instance_path(instance_path) or parse_vid_pid_from_instance_path(
                str(entry.get("symbolicLink", "") or "")
            )
            vendor, product = decoded if decoded is not None else (vendor or 0, product or 0)
        devices.append(
            HidHideDevice(
                instance_path=instance_path,
                xusb_instance_path=str(entry.get("xusbDeviceInstancePath", "") or ""),
                vendor=vendor,
                product=product,
                description=group_name or str(entry.get("description", "") or ""),
                gaming_device=bool(entry.get("gamingDevice", True)),
            )
        )
    return devices


def _run_exe(
    app, exe_path: str, args: list[str], *, elevated: bool, timeout: float, label: str
) -> tuple[int | None, str]:
    """Runs exe_path with args as a plain child process -- NEVER through a
    .bat file/cmd.exe. Confirmed live 2026-09-23: routing HidHideCLI.exe
    through a generated `.bat` (cmd.exe running `"exe" "args" >> file 2>&1`
    -- the technique win_elevation.run_elevated_capture[_many] uses to work
    around ShellExecuteExW not being able to share a pipe/file handle with
    an elevated child directly) reproducibly broke it: the batch-invoked
    call printed "The command is not recognized." and silently failed to
    apply --dev-hide/--cloak-on/--app-reg, on EVERY attempt, elevated or
    not -- while the exact same argv run directly (`subprocess.run([cli,
    *args])`, no cmd.exe involved at all) worked correctly every single
    time in the same session, live-verified via --dev-list/--cloak-state
    both before and after. Root cause not fully pinned down (a
    console/stdio-handling quirk specific to HidHideCLI.exe's own binary,
    not a generic Windows/cmd.exe limitation -- the SAME .bat mechanism
    correctly ran pnputil.exe and captured its real, correctly-formatted
    output in the same test session), but the fix doesn't need to know why:
    never launch HidHideCLI.exe via a .bat again.

    This also means an elevated call here gets NO captured output --
    ShellExecuteExW's "runas" verb can't share a handle with the elevated
    child, and the one workaround for that (the .bat trick above) is
    exactly what breaks this exe. Callers never rely on this call's own
    output or exit code for correctness -- they always re-verify real
    state afterward via a separate UNELEVATED call (see
    hide_device_for_slot/unhide_device_for_slot's own retry-elevated-only-
    if-unelevated-didn't-verify design), the same "never trust an elevated
    call's exit code" principle this codebase already applies everywhere
    else (ViGEmBus install/uninstall, etc.)."""
    app.log(f"HidHide: running {'(elevated) ' if elevated else ''}{label} {' '.join(args)}")
    if not elevated:
        try:
            result = subprocess.run(
                [exe_path, *args],
                # Confirmed live 2026-09-23: after running its arguments,
                # HidHideCLI.exe drops into its interactive prompt and only
                # SAVES and exits on EOF. An inherited, still-open stdin
                # left it hanging forever with the changes unsaved (and
                # holding the driver's single config handle, so every later
                # call failed with "Acceso denegado"). DEVNULL = immediate EOF.
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=timeout,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            app.log(f"HidHide: exit={result.returncode}")
            return result.returncode, (result.stdout or "") + (result.stderr or "")
        except Exception as exc:
            app.log(f"HidHide: unelevated run of {label} failed ({exc})")
            return None, ""
    params = " ".join(f'"{a}"' for a in args)
    launched = shell_execute_elevated_and_wait(exe_path, params)
    if not launched:
        app.log(f"HidHide: elevation of {label} was declined, or it could not be launched")
        return None, ""
    app.log(f"HidHide: elevated {label} call finished (no output captured -- see the re-verification that follows)")
    return 0, ""


def parse_app_list(text: str) -> list[str]:
    """Parses `HidHideCLI.exe --app-list`'s output into a list of
    whitelisted executable paths. Confirmed from source: this command does
    NOT emit JSON -- it echoes back `--app-reg "<path>"` lines, one per
    registered app -- so this extracts the quoted path from each such
    line rather than attempting to JSON-decode it."""
    marker = '--app-reg "'
    paths: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith(marker) and line.endswith('"'):
            paths.append(line[len(marker):-1])
    return paths


class HidHideRuntime:
    """Wraps HidHideCLI.exe to hide a specific physical gamepad from FIFA
    specifically (per-slot, opt-in), while this app's own pygame.joystick
    reads of that same device keep working unaffected -- FIFA is otherwise
    known to read a raw, non-Xbox controller directly (as a generic
    DirectInput/legacy joystick) *at the same time* as GamepadBridgeRuntime's
    virtual Xbox 360 pad, producing garbled input (confirmed live 2026-09-24,
    see gamepad_bridge_runtime.py's plan history). Entirely independent of
    ViGEmBus's own install state -- a second, optional driver, never
    presented as required for the core bridging feature to work.

    NOT yet confirmed live against a real HidHide install in this codebase
    -- every command/path/elevation assumption here is grounded in reading
    the real nefarius/HidHide source and docs, not in having run it. See
    this feature's own plan file for what to check first if something here
    turns out wrong, the same "confirm live, then trust it" discipline this
    project's own history (CLAUDE.md §7) already applies to every other
    memory/hardware-dependent feature."""

    def __init__(self, app: "Server16App") -> None:
        self.app = app
        self._cli_path_cache: Path | None = None

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def is_hidhide_installed(self) -> bool:
        """Pure registry-presence read, deliberately never a CLI/driver
        round-trip -- mirrors GamepadBridgeRuntime.is_vigembus_installed()
        exactly, including the reason why (a live-confirmed device
        connect/disconnect side effect from over-eager status probing was
        a real, reported bug for that one; this avoids the same class of
        mistake here from the start)."""
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Services\HidHide"):
                return True
        except OSError:
            return False

    def find_hidhide_installer(self) -> Path | None:
        """bin\\HidHide\\*.{exe,msi} only -- unlike ViGEmBus, no Python
        package vendors a copy of this installer, so there is no automatic
        fallback: a contributor must download the installer from
        https://github.com/nefarius/HidHide/releases and place it here.
        Confirmed live this session: the actual current release is an .exe
        (HidHide_1.5.230_x64.exe) -- an earlier assumption in this module
        that it was an .msi (HidHideMSI.msi) was wrong and has been
        corrected; .exe is matched first for that reason, mirroring
        find_vigembus_installer()'s own "prefer whichever format the
        current release actually uses" ordering. .msi is still matched as
        a fallback in case an older release is ever placed here instead.

        Searches app.base_dir (the folder holding the deployed .exe -- a
        manual override, e.g. dropping a newer installer next to an
        already-built app without rebuilding) BEFORE app.resource_dir (in a
        frozen build, PyInstaller's onefile extraction dir, sys._MEIPASS --
        where Server16Python.spec's bin\\HidHide datas entry actually lands
        at runtime). Missing the resource_dir check was a real, live-
        reported bug: the installer placed in the source repo's bin\\HidHide\\
        at build time got bundled into the onefile exe correctly, but this
        function only ever looked next to the deployed exe, so the button
        found nothing unless a contributor *also* manually copied the
        installer there after building -- same base_dir-first-then-
        resource_dir pattern already used for KitExtractorHost.exe
        (app_ui.py's _kit_extractor_exe_candidates)."""
        for candidate_root in self._installer_search_roots():
            base = candidate_root / "bin" / "HidHide"
            if not base.is_dir():
                continue
            exe_matches = sorted(base.glob("*.exe"))
            if exe_matches:
                return exe_matches[0]
            msi_matches = sorted(base.glob("*.msi"))
            if msi_matches:
                return msi_matches[0]
        return None

    def _installer_search_roots(self) -> list[Path]:
        roots = [Path(self.app.base_dir)]
        resource_dir = getattr(self.app, "resource_dir", None)
        if resource_dir is not None and Path(resource_dir) != roots[0]:
            roots.append(Path(resource_dir))
        return roots

    def find_hidhide_cli(self) -> Path | None:
        """Locates HidHideCLI.exe. Tries, in order: (1) the MSI-populated
        vendor-key install-path registry marker (unconfirmed to exist on a
        real install -- see below), (2) the `InstallLocation` value on
        HidHide's own Add/Remove Programs uninstall entry (the SAME
        registry entry _find_uninstall_registry_entry() already reads for
        uninstall_hidhide() -- confirmed live 2026-09-24 to exist and hold
        the real install root, `C:\\Program Files\\Nefarius Software
        Solutions\\HidHide\\`, on a machine where the vendor-key lookup in
        (1) found nothing at all), then (3) a short list of hardcoded
        candidate directories as a last resort. Every root is searched both
        directly and recursively (root.rglob), since the real install nests
        HidHideCLI.exe one level deeper under an architecture subfolder
        (`x64\\HidHideCLI.exe`), not at the install root itself."""
        if self._cli_path_cache is not None and self._cli_path_cache.exists():
            return self._cli_path_cache
        search_roots: list[Path] = []
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _INSTALL_PATH_REGISTRY_KEY) as key:
                install_path, _ = winreg.QueryValueEx(key, "Path")
                if install_path:
                    search_roots.append(Path(install_path))
        except OSError:
            pass
        uninstall_entry = self._find_uninstall_registry_entry()
        install_location = (uninstall_entry or {}).get("install_location")
        if install_location:
            search_roots.append(Path(install_location))
        search_roots.extend(Path(p) for p in _CLI_CANDIDATE_DIRS)
        for root in search_roots:
            if not root.is_dir():
                continue
            direct = root / "HidHideCLI.exe"
            if direct.exists():
                self._cli_path_cache = direct
                return direct
            try:
                match = next(root.rglob("HidHideCLI.exe"), None)
            except OSError:
                match = None
            if match is not None:
                self._cli_path_cache = match
                return match
        return None

    # ------------------------------------------------------------------
    # Install / uninstall
    # ------------------------------------------------------------------

    def install_hidhide(self, on_done: Callable[[bool, str], None] | None = None) -> bool:
        installer_path = self.find_hidhide_installer()
        if installer_path is None:
            return False
        self._run_elevated_installer(installer_path, uninstall=False, on_done=on_done)
        return True

    def uninstall_hidhide(self, on_done: Callable[[bool, str], None] | None = None) -> bool:
        """Prefers the real, OS-registered uninstall command over re-running
        the original installer with a guessed flag. Confirmed live this
        session (unlike the old, ad hoc ViGEmBus leftover this project dealt
        with earlier): a real HidHide install (HidHide_1.5.230_x64.exe, NOT
        an .msi -- an earlier assumption in this file that current releases
        ship an .msi was wrong, corrected here) does register a normal
        Add/Remove Programs entry, with the exact command line Windows
        itself would use for "Uninstall" -- reading that is strictly more
        reliable than guessing silent-uninstall flags on the installer exe,
        whose actual installer technology this codebase was never able to
        fingerprint (no Inno Setup/NSIS/WiX Burn marker strings found in the
        binary). Falls back to re-running the installer with a guessed flag
        only if no such registry entry exists."""
        entry = self._find_uninstall_registry_entry()
        command = (entry or {}).get("quiet_uninstall_string") or (entry or {}).get("uninstall_string")
        if command:
            self._cli_path_cache = None
            self._run_elevated_command(command, uninstall=True, on_done=on_done)
            return True
        installer_path = self.find_hidhide_installer()
        if installer_path is None:
            return False
        self._cli_path_cache = None
        self._run_elevated_installer(installer_path, uninstall=True, on_done=on_done)
        return True

    @staticmethod
    def _find_uninstall_registry_entry() -> dict[str, str] | None:
        """Scans the standard Add/Remove Programs registry locations for an
        entry whose DisplayName mentions "HidHide", returning its
        UninstallString / QuietUninstallString (when present -- many
        installers populate this second key specifically so other tools
        don't have to guess silent flags, which is exactly this use case)
        and InstallLocation (confirmed live 2026-09-24 to be present and
        accurate on a real install -- find_hidhide_cli() uses it as a
        search root, since the dedicated vendor-key lookup it tries first
        turned out not to exist at all on that same machine)."""
        roots = (
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        )
        for hive, base_path in roots:
            try:
                base_key = winreg.OpenKey(hive, base_path)
            except OSError:
                continue
            with base_key:
                index = 0
                while True:
                    try:
                        subkey_name = winreg.EnumKey(base_key, index)
                    except OSError:
                        break
                    index += 1
                    try:
                        with winreg.OpenKey(base_key, subkey_name) as subkey:
                            display_name = str(winreg.QueryValueEx(subkey, "DisplayName")[0])
                            if "hidhide" not in display_name.lower():
                                continue
                            result: dict[str, str] = {}
                            try:
                                result["uninstall_string"] = str(winreg.QueryValueEx(subkey, "UninstallString")[0])
                            except OSError:
                                pass
                            try:
                                result["quiet_uninstall_string"] = str(
                                    winreg.QueryValueEx(subkey, "QuietUninstallString")[0]
                                )
                            except OSError:
                                pass
                            try:
                                result["install_location"] = str(
                                    winreg.QueryValueEx(subkey, "InstallLocation")[0]
                                )
                            except OSError:
                                pass
                            return result
                    except OSError:
                        continue
        return None

    @staticmethod
    def _split_command_line(command: str) -> tuple[str, str]:
        """Splits a registry-style command line ('"C:\\path\\to.exe" /flag')
        into (executable_path, remaining_params) for ShellExecuteExW, which
        needs them separately."""
        command = command.strip()
        if command.startswith('"'):
            end = command.find('"', 1)
            if end != -1:
                return command[1:end], command[end + 1:].strip()
        parts = command.split(None, 1)
        if not parts:
            return command, ""
        return parts[0], parts[1] if len(parts) > 1 else ""

    def _run_elevated_command(
        self, command: str, uninstall: bool, on_done: Callable[[bool, str], None] | None
    ) -> None:
        exe, params = self._split_command_line(command)

        def _worker() -> None:
            launched = shell_execute_elevated_and_wait(exe, params)
            if not launched:
                self._finish_action(on_done, False, "Elevation was declined, or the uninstaller could not be launched.")
                return
            self._cli_path_cache = None
            installed = self.is_hidhide_installed()
            success = not installed if uninstall else installed
            message = "HidHide uninstalled." if success else "Uninstall finished but HidHide still looks installed."
            self._finish_action(on_done, success, message)

        threading.Thread(target=_worker, name="hidhide-uninstaller", daemon=True).start()

    def _run_elevated_installer(
        self, installer_path: Path, uninstall: bool, on_done: Callable[[bool, str], None] | None
    ) -> None:
        """Same .msi/.exe extension dispatch as GamepadBridgeRuntime's own
        installer launcher. NOT confirmed which of the two branches HidHide
        actually needs: a real installed copy in this session turned out to
        be HidHide_1.5.230_x64.exe (an .exe, not the .msi this module
        originally assumed) with no identifiable installer-technology
        marker strings (Inno Setup/NSIS/WiX Burn) found in the binary, so
        the /exenoui /qn /norestart flags below are the same best-effort,
        commonly-recognized-across-frameworks guess ViGEmBus's own .exe
        branch uses -- genuinely unconfirmed whether HidHide's installer
        honors them or just shows its UI regardless. Either way this still
        waits for the process and re-verifies real state afterward, so a
        wrong guess here costs the user one extra click-through, not a
        silent failure. uninstall_hidhide() prefers the real registered
        uninstall command instead of this path whenever one exists (see
        above) precisely because this guess is this uncertain."""
        is_msi = installer_path.suffix.lower() == ".msi"
        if is_msi:
            flag = "/x" if uninstall else "/i"
            launch_file = "msiexec.exe"
            params = f'{flag} "{installer_path}" /qn'
        else:
            launch_file = str(installer_path)
            params = ("/uninstall " if uninstall else "") + "/exenoui /qn /norestart"

        def _worker() -> None:
            launched = shell_execute_elevated_and_wait(launch_file, params)
            if not launched:
                self._finish_action(on_done, False, "Elevation was declined, or the installer could not be launched.")
                return
            self._cli_path_cache = None
            installed = self.is_hidhide_installed()
            success = (not installed) if uninstall else installed
            if success:
                message = "HidHide uninstalled." if uninstall else "HidHide installed."
            else:
                message = (
                    "Uninstall finished but HidHide still looks installed."
                    if uninstall
                    else "Installer finished but HidHide still isn't detected."
                )
            self._finish_action(on_done, success, message)

        threading.Thread(target=_worker, name="hidhide-installer", daemon=True).start()

    def _finish_action(self, on_done: Callable[[bool, str], None] | None, success: bool, message: str) -> None:
        if on_done is None:
            return
        try:
            self.app.after(0, lambda: on_done(success, message))
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Command execution
    # ------------------------------------------------------------------

    def _run_command(self, args: list[str], elevated: bool, timeout: float = 20.0) -> tuple[int | None, str]:
        """Runs HidHideCLI.exe with args. Elevation requirements for this
        CLI are NOT settled by reading source alone (no permission checks
        are visible in the real Commands.cpp), but ARE now confirmed live
        2026-09-23: on a real machine, a plain unelevated call to
        --dev-hide/--cloak-on/--app-reg genuinely hid a real device and
        turned cloaking on -- enforcement, if it exists at all, happens
        below this CLI, and does not require this process to be elevated.
        `elevated=False` tries a plain subprocess call; `elevated=True`
        is now ONLY used as a last-resort fallback (see hide_device_for_slot/
        unhide_device_for_slot) after an unelevated attempt's own
        verification came back negative -- it no longer routes through a
        .bat file (see _run_exe_elevated's docstring for why that mattered).
        Every call is logged (command + outcome) -- given how many rounds
        this project's other driver-adjacent features (ViGEmBus install/
        uninstall, the scoreboardstdname memory patcher, CLAUDE.md §7)
        needed exactly this kind of trail to correct a wrong first guess,
        this is not optional here."""
        cli = self.find_hidhide_cli()
        if cli is None:
            self.app.log("HidHide: HidHideCLI.exe not found -- is the driver installed?")
            return None, ""
        return _run_exe(self.app, str(cli), args, elevated=elevated, timeout=timeout, label="HidHideCLI.exe")

    # ------------------------------------------------------------------
    # Device resolution
    # ------------------------------------------------------------------

    def find_gaming_devices(self) -> list[HidHideDevice]:
        _exit_code, output = self._run_command(["--dev-gaming"], elevated=False)
        return parse_dev_gaming_json(output)

    def resolve_devices_for_guid(self, sdl_guid: str) -> list[HidHideDevice]:
        """Every HID collection of the physical pad behind an SDL GUID. A
        Bluetooth pad can expose several collections (Col01, Col02...) --
        all of them must be hidden, or FIFA keeps reading the one left
        visible."""
        decoded = decode_vid_pid_from_sdl_guid(sdl_guid)
        if decoded is None:
            return []
        vendor, product = decoded
        return [
            device
            for device in self.find_gaming_devices()
            if device.vendor == vendor and device.product == product and device.instance_path
        ]

    def resolve_device_for_guid(self, sdl_guid: str) -> HidHideDevice | None:
        matches = self.resolve_devices_for_guid(sdl_guid)
        return matches[0] if matches else None

    @staticmethod
    def _pnputil_path() -> str:
        # A 32-bit process on 64-bit Windows would be redirected to
        # SysWOW64, which has no pnputil.exe; Sysnative reaches the real one.
        system_root = os.environ.get("SystemRoot", r"C:\Windows")
        sysnative = Path(system_root) / "Sysnative" / "pnputil.exe"
        if sysnative.exists():
            return str(sysnative)
        return str(Path(system_root) / "System32" / "pnputil.exe")

    def _hidden_instance_paths(self) -> tuple[list[str], bool]:
        """(instance paths HidHide currently hides, whether cloaking is on),
        read back unelevated -- confirmed live that --dev-list /
        --cloak-state work without elevation. --dev-list echoes one
        `--dev-hide "<path>"` line per hidden device, the same shape
        --app-list uses (see parse_app_list)."""
        _exit, listing = self._run_command(["--dev-list"], elevated=False)
        _exit, cloak = self._run_command(["--cloak-state"], elevated=False)
        hidden = re.findall(r'"([^"]+)"', listing.replace("\\\\", "\\"))
        return hidden, "--cloak-on" in cloak

    def _restart_devices(self, instance_paths: list[str], elevated: bool) -> None:
        """Best-effort `pnputil /restart-device` per path -- this is what
        makes HidHide's cloak apply to a program that ALREADY had the
        device open (see hide_device_for_slot's own docstring for why this
        matters at all). A failure here (a device with a reboot already
        pending from an earlier restart, or the account genuinely lacking
        rights) is logged but never treated as fatal to hiding itself --
        the cloak/allow-list state (checked separately by
        _verify_hidden) is what actually determines the return value."""
        pnputil = self._pnputil_path()
        for path in instance_paths:
            exit_code, output = _run_exe(
                self.app, pnputil, ["/restart-device", path], elevated=elevated, timeout=20.0, label="pnputil.exe"
            )
            if exit_code not in (0, None):
                self.app.log(f"HidHide: pnputil restart of '{path}' returned {exit_code}: {output.strip()[:300]}")

    # ------------------------------------------------------------------
    # High-level actions -- the only entry points GamepadBridgeRuntime calls
    # ------------------------------------------------------------------

    def ensure_hidden_for_slot(self, sdl_guid: str, own_exe: str | None = None) -> bool:
        """Startup counterpart of hide_device_for_slot(): makes HidHide's
        real state match a slot whose Hide from FIFA was already checked in
        a previous session, WITHOUT ever elevating (no UAC prompt at app
        launch). Does nothing -- not even the device restart -- when the
        pad is already hidden and cloaking is on.

        Reported live 2026-09-23: the checkbox showed checked, but HidHide
        had nothing hidden (the device had been unhidden outside that
        session), and since startup deliberately never touched HidHide,
        FIFA kept listing the physical pad as player 1 next to the virtual
        one. Startup used to skip this only because hiding needed a UAC
        prompt; it no longer does (see hide_device_for_slot)."""
        if not self.is_hidhide_installed():
            return False
        devices = self.resolve_devices_for_guid(sdl_guid)
        if not devices:
            self.app.log(f"HidHide: Hide from FIFA is on but the controller (guid {sdl_guid}) isn't connected yet")
            return False
        hidden_paths, cloak_on = self._hidden_instance_paths()
        hidden = {path.lower() for path in hidden_paths}
        own_listed = True
        if own_exe:
            # The allow-list entry is by exe path -- a build run from a new
            # folder would otherwise lose sight of its own hidden pad.
            _exit, listing = self._run_command(["--app-list"], elevated=False)
            own_listed = any(p.lower() == own_exe.lower() for p in parse_app_list(listing))
        if cloak_on and own_listed and all(d.instance_path.lower() in hidden for d in devices):
            return True
        self.app.log("HidHide: Hide from FIFA is on but the controller isn't hidden -- hiding it now")
        return self.hide_device_for_slot(sdl_guid, own_exe=own_exe, allow_elevation=False)

    def hide_device_for_slot(self, sdl_guid: str, own_exe: str | None = None, allow_elevation: bool = True) -> bool:
        """Hides every HID collection of the pad from every app except
        HidHide's allow-list, registers own_exe on that allow-list, then
        restarts those devices so the cloak also applies to a program that
        ALREADY had the pad open (HidHide only filters new opens/
        enumerations -- confirmed live 2026-09-23 that Steam keeps the
        Switch Pro Controller open the whole time it runs, so without the
        restart, Steam -- and FIFA, if it was already running -- keeps its
        stale handle to the raw device even after hiding).

        Tries everything UNELEVATED first. Confirmed live 2026-09-23,
        directly against a real device: on this machine, a plain,
        non-admin HidHideCLI.exe call genuinely hid the pad and turned
        cloaking on, and a plain, non-admin pnputil restarted it -- zero
        UAC prompts needed. This module's own long-standing "elevation
        requirements for this CLI are NOT settled" note (still true from
        reading the source alone) is now backed by a live result, not just
        a guess. Only if the unelevated attempt's own re-verification
        (--dev-list/--cloak-state, always unelevated, always reliable)
        comes back negative does this retry the exact same sequence
        elevated -- seeing a UAC prompt at all should now be rare, and
        firing on every single checkbox toggle (reported live 2026-09-23)
        was itself a symptom of the elevated path being the ONLY path this
        used to try, combined with the .bat-based elevation mechanism
        silently failing every time (see _run_exe's docstring) -- so it
        kept re-prompting for something that was never actually working.

        Returns True only once --dev-list/--cloak-state confirm the pad is
        actually hidden -- never off either attempt's own exit code."""
        if not self.is_hidhide_installed():
            return False
        devices = self.resolve_devices_for_guid(sdl_guid)
        if not devices:
            self.app.log(
                f"HidHide: the controller (guid {sdl_guid}) isn't in HidHide's device list -- connect it and "
                "toggle Hide from FIFA again; nothing hidden"
            )
            return False
        args: list[str] = []
        for device in devices:
            args += ["--dev-hide", device.instance_path]
        args.append("--cloak-on")
        if own_exe:
            args += ["--app-reg", own_exe]
        paths = [device.instance_path for device in devices]
        names = ", ".join(sorted({d.description for d in devices}))

        self._run_command(args, elevated=False)
        self._restart_devices(paths, elevated=False)
        if self._verify_hidden(paths, names, own_exe):
            return True
        if not allow_elevation:
            return False

        self.app.log(f"HidHide: unelevated attempt did not hide '{names}' -- retrying elevated")
        self._run_command(args, elevated=True)
        self._restart_devices(paths, elevated=True)
        return self._verify_hidden(paths, names, own_exe)

    def _verify_hidden(self, paths: list[str], names: str, own_exe: str | None) -> bool:
        hidden_paths, cloak_on = self._hidden_instance_paths()
        hidden = {path.lower() for path in hidden_paths}
        missing = [path for path in paths if path.lower() not in hidden]
        if missing or not cloak_on:
            self.app.log(
                f"HidHide: hiding '{names}' did NOT take effect (cloak {'on' if cloak_on else 'off'}, "
                f"not hidden: {missing})"
            )
            return False
        suffix = f", self-excluded {own_exe}" if own_exe else ""
        self.app.log(f"HidHide: confirmed '{names}' hidden from every other program, FIFA included{suffix}")
        return True

    def unhide_device_for_slot(self, sdl_guid: str) -> bool:
        """Unhides by what HidHide itself reports as hidden (matched by
        VID/PID), so this also works while the pad is unplugged -- a
        disconnected pad isn't in --dev-gaming's list at all. Same
        unelevated-first, elevated-only-if-unverified design as
        hide_device_for_slot -- see its docstring for why."""
        if not self.is_hidhide_installed():
            return False
        decoded = decode_vid_pid_from_sdl_guid(sdl_guid)
        if decoded is None:
            return False
        hidden_paths, _cloak_on = self._hidden_instance_paths()
        paths = [path for path in hidden_paths if parse_vid_pid_from_instance_path(path) == decoded]
        if not paths:
            self.app.log(f"HidHide: nothing hidden for guid {sdl_guid} -- nothing to unhide")
            return False
        args: list[str] = []
        for path in paths:
            args += ["--dev-unhide", path]

        self._run_command(args, elevated=False)
        if self._verify_unhidden(paths):
            return True
        self.app.log("HidHide: unelevated unhide attempt did not take effect -- retrying elevated")
        self._run_command(args, elevated=True)
        return self._verify_unhidden(paths)

    def _verify_unhidden(self, paths: list[str]) -> bool:
        remaining, _cloak_on = self._hidden_instance_paths()
        still_hidden = [p for p in paths if p.lower() in {r.lower() for r in remaining}]
        if still_hidden:
            self.app.log(f"HidHide: unhiding did NOT take effect for {still_hidden}")
            return False
        self.app.log(f"HidHide: confirmed unhidden {paths}")
        return True

    def ensure_own_process_excluded(self) -> bool:
        """Registers THIS APP'S OWN running process (sys.executable) with
        HidHide's application allow-list -- NOT FIFA's. This corrects a real,
        live-confirmed bug: an earlier version of this method (named
        ensure_fifa_whitelisted, registering self.app.fifaEXE instead)
        had HidHide's whitelist semantics backwards.

        HidHide's allow-list is an EXCLUSION list: every app NOT on it is
        blind to a hidden/cloaked device once cloaking is on; every app ON
        it can still see hidden devices exactly as if they weren't hidden.
        The goal here is the opposite of what the old code did -- FIFA must
        stay OFF the list (so it stays blind to the raw physical pad), while
        THIS process must be ON it (so GamepadBridgeRuntime's own
        pygame.joystick reads of that same physical device keep working so
        it can still translate it). Registering FIFA instead exempted it
        from the cloak entirely, so hiding the device had zero effect on
        FIFA -- reported live 2026-09-24 as "buttons pressing themselves in
        FIFA" even with Hide from FIFA enabled and (once find_hidhide_cli()
        was also fixed the same session) the device genuinely on the hidden
        list.

        No-ops with a log line, not an error, if HidHideCLI.exe can't be
        located (e.g. find_hidhide_cli() still can't find a given install)."""
        if not self.is_hidhide_installed():
            return False
        own_exe = sys.executable
        if not own_exe or not Path(own_exe).exists():
            self.app.log("HidHide: could not resolve this app's own executable path -- skipping self-exclusion")
            return False
        _exit_code, listing = self._run_command(["--app-list"], elevated=False)
        own_resolved = Path(own_exe).resolve()
        already_listed = any(
            Path(p).resolve() == own_resolved for p in parse_app_list(listing) if p
        )
        if already_listed:
            return True
        self._run_command(["--app-reg", own_exe], elevated=True)
        # Never trust the elevated call's own exit code for "did it work"
        # (same principle this codebase already applies to every other
        # elevated driver action, e.g. GamepadBridgeRuntime's ViGEmBus
        # install/uninstall) -- re-read the real whitelist state instead.
        _exit_code, listing_after = self._run_command(["--app-list"], elevated=False)
        confirmed = any(Path(p).resolve() == own_resolved for p in parse_app_list(listing_after) if p)
        if not confirmed:
            self.app.log(f"HidHide: self-exclude of {own_exe} did not take effect")
            return False
        self.app.log(f"HidHide: self-excluded {own_exe} (keeps reading the hidden device to translate it)")
        return True
