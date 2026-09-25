"""Complete ViGEmBus removal for the Gamepads tab's Uninstall Driver button.

Why this is more than "run the installer with /uninstall": reported live
2026-09-24, the button left the driver behind. Two independent causes, both
handled here / in GamepadBridgeRuntime.uninstall_vigembus():

- The button used to re-run whatever installer it would *install* with
  (bin\\ViGEmBus's 1.22.0 bootstrapper) with an /uninstall switch. That only
  removes the exact product that installer registered. A machine with a
  different ViGEmBus build (this one had 1.17.333 from vgamepad's bundled
  .msi -- a different Windows Installer product) got a silent no-op. The
  right handle on "the installed copy" is Add/Remove Programs'
  own registration, whichever build put it there.
- Even a correct MSI uninstall leaves things behind: the ViGEmBus.sys copy
  in System32\\drivers, the driver-store package (vigembus.inf), the
  root-enumerated device node, sometimes the service key itself. Those are
  what "restos" looks like, so they're removed explicitly.

Everything here is matched against ViGEmBus specifically (its INF name +
publisher, its hardware ID, its service name). Other virtual-pad drivers
that commonly sit next to it -- Rainway's IreulBus, Steam's virtual Xbox
bus, Logitech's, Nefarius' own HidGuardian/HidHide -- are never touched.
"""
from __future__ import annotations

import os
import re
import subprocess
import winreg
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

from .win_elevation import RawArg

SERVICE_NAME = "ViGEmBus"
HARDWARE_ID = "Nefarius\\ViGEmBus\\Gen1"
DRIVER_INF_NAME = "vigembus.inf"
_PUBLISHER_HINT = "nefarius"

# The MSI's install folder under Program Files. Its parent is shared with the
# other Nefarius products (HidHide installs there too), so the parent is only
# ever removed when it has been left empty.
_PRODUCT_FOLDER = ("Nefarius Software Solutions", "Virtual Gamepad Emulation Bus Driver")

_UNINSTALL_KEY = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
_DISPLAY_NAME_HINTS = ("virtual gamepad emulation bus", "vigembus", "vigem bus")
_REGISTRY_VIEWS = (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY)

_MSI_UNINSTALL_COMMAND = re.compile(
    r"msiexec(?:\.exe)?\"?\s+/[xi]\s*(\{[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\})",
    re.IGNORECASE,
)
_GUID = re.compile(r"^\{[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\}$", re.IGNORECASE)
_OEM_INF = re.compile(r"\boem\d+\.inf\b", re.IGNORECASE)
_BLANK_LINE = re.compile(r"\r?\n[ \t]*\r?\n")

_CREATE_NO_WINDOW = 0x08000000


@dataclass(frozen=True)
class RegisteredUninstall:
    display_name: str
    # "{GUID}" of the Windows Installer product, or None for a registration
    # that isn't an MSI (nothing here knows a silent switch for those; the
    # explicit cleanup still removes the driver itself).
    product_code: str | None


@dataclass
class ViGEmBusState:
    uninstalls: list[RegisteredUninstall] = field(default_factory=list)
    service_present: bool = False
    # DeleteFlag=1: `sc delete` accepted but the driver is still loaded, so
    # Windows finishes the removal at the next restart.
    service_pending_delete: bool = False
    devices: list[str] = field(default_factory=list)
    driver_packages: list[str] = field(default_factory=list)
    paths: list[Path] = field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        return not (self.leftovers())

    @property
    def restart_pending(self) -> bool:
        """Only things that can't be released while the driver is loaded are
        left -- a restart finishes the job, another attempt wouldn't."""
        if self.uninstalls or self.devices or self.driver_packages:
            return False
        if self.service_present and not self.service_pending_delete:
            return False
        return self.service_pending_delete or bool(self.paths)

    def leftovers(self) -> list[str]:
        items = [f"'{entry.display_name}' in Apps & Features" for entry in self.uninstalls]
        if self.service_present:
            items.append(
                f"driver service '{SERVICE_NAME}'" + (" (removal pending restart)" if self.service_pending_delete else "")
            )
        items += [f"device {instance}" for instance in self.devices]
        items += [f"driver package {package}" for package in self.driver_packages]
        items += [str(path) for path in self.paths]
        return items


# ----------------------------------------------------------------------
# Reading the real state
# ----------------------------------------------------------------------


def _enum_subkeys(key) -> Iterator[str]:
    index = 0
    while True:
        try:
            yield winreg.EnumKey(key, index)
        except OSError:
            return
        index += 1


def _query(key, name: str):
    try:
        return winreg.QueryValueEx(key, name)[0]
    except OSError:
        return None


def product_code_for(key_name: str, uninstall_string: str, windows_installer) -> str | None:
    match = _MSI_UNINSTALL_COMMAND.search(uninstall_string or "")
    if match:
        return match.group(1).upper()
    if windows_installer == 1 and _GUID.match(key_name):
        return key_name.upper()
    return None


def registered_uninstalls() -> list[RegisteredUninstall]:
    found: dict[str, RegisteredUninstall] = {}
    for view in _REGISTRY_VIEWS:
        try:
            base = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _UNINSTALL_KEY, 0, winreg.KEY_READ | view)
        except OSError:
            continue
        with base:
            for name in _enum_subkeys(base):
                try:
                    with winreg.OpenKey(base, name) as sub:
                        display_name = str(_query(sub, "DisplayName") or "")
                        uninstall_string = str(_query(sub, "UninstallString") or "")
                        windows_installer = _query(sub, "WindowsInstaller")
                except OSError:
                    continue
                if not any(hint in display_name.lower() for hint in _DISPLAY_NAME_HINTS):
                    continue
                found.setdefault(
                    name.upper(),
                    RegisteredUninstall(display_name, product_code_for(name, uninstall_string, windows_installer)),
                )
    return list(found.values())


def service_state() -> tuple[bool, bool]:
    """(service key exists, marked for deletion but still loaded)."""
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, rf"SYSTEM\CurrentControlSet\Services\{SERVICE_NAME}") as key:
            try:
                pending = int(_query(key, "DeleteFlag") or 0) == 1
            except (TypeError, ValueError):
                pending = False
            return True, pending
    except OSError:
        return False, False


def is_vigembus_device(hardware_ids, service) -> bool:
    if isinstance(hardware_ids, str):
        hardware_ids = [hardware_ids]
    if any(str(hid).lower() == HARDWARE_ID.lower() for hid in (hardware_ids or [])):
        return True
    return str(service or "").lower() == SERVICE_NAME.lower()


def device_instances() -> list[str]:
    """Root-enumerated device nodes ViGEmBus created (the installer adds one
    with `devcon install`). Read from the registry rather than a localized
    pnputil listing."""
    instances: list[str] = []
    try:
        root = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Enum\ROOT")
    except OSError:
        return instances
    with root:
        for group in _enum_subkeys(root):
            try:
                group_key = winreg.OpenKey(root, group)
            except OSError:
                continue
            with group_key:
                for instance in _enum_subkeys(group_key):
                    try:
                        with winreg.OpenKey(group_key, instance) as instance_key:
                            hardware_ids = _query(instance_key, "HardwareID")
                            service = _query(instance_key, "Service")
                    except OSError:
                        continue
                    if is_vigembus_device(hardware_ids, service):
                        instances.append(f"ROOT\\{group}\\{instance}")
    return instances


def parse_driver_packages(pnputil_output: str) -> list[str]:
    """Published names (oemNN.inf) of ViGEmBus packages in a `pnputil
    /enum-drivers` listing. Labels are localized ("Nombre publicado"...), so
    this keys on the values instead: a block naming vigembus.inf from
    Nefarius, and the first oemNN.inf in it."""
    packages: list[str] = []
    for block in _BLANK_LINE.split(pnputil_output):
        lowered = block.lower()
        if DRIVER_INF_NAME not in lowered or _PUBLISHER_HINT not in lowered:
            continue
        match = _OEM_INF.search(block)
        if match and match.group(0).lower() not in packages:
            packages.append(match.group(0).lower())
    return packages


def driver_packages() -> list[str]:
    try:
        result = subprocess.run(
            ["pnputil.exe", "/enum-drivers"],
            capture_output=True,
            timeout=60,
            creationflags=_CREATE_NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    try:
        text = result.stdout.decode("oem", errors="replace")
    except LookupError:
        text = result.stdout.decode("utf-8", errors="replace")
    return parse_driver_packages(text)


def _candidate_paths() -> list[Path]:
    candidates: list[Path] = []
    for variable in ("ProgramW6432", "ProgramFiles"):
        base = os.environ.get(variable)
        if base:
            path = Path(base, *_PRODUCT_FOLDER)
            if path not in candidates:
                candidates.append(path)
    candidates.append(Path(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "drivers", "ViGEmBus.sys"))
    return candidates


def leftover_paths() -> list[Path]:
    return [path for path in _candidate_paths() if path.exists()]


def scan() -> ViGEmBusState:
    service_present, service_pending_delete = service_state()
    return ViGEmBusState(
        uninstalls=registered_uninstalls(),
        service_present=service_present,
        service_pending_delete=service_pending_delete,
        devices=device_instances(),
        driver_packages=driver_packages(),
        paths=leftover_paths(),
    )


# ----------------------------------------------------------------------
# Building the removal
# ----------------------------------------------------------------------


def _powershell_quote(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def _powershell_remove_script(paths: list[Path]) -> str:
    quoted = ", ".join(_powershell_quote(str(path)) for path in paths)
    script = (
        f"foreach ($p in @({quoted})) "
        "{ if (Test-Path -LiteralPath $p) { Remove-Item -LiteralPath $p -Recurse -Force -ErrorAction SilentlyContinue } }"
    )
    for path in paths:
        if path.name == _PRODUCT_FOLDER[1]:
            vendor = _powershell_quote(str(path.parent))
            script += (
                f"; if ((Test-Path -LiteralPath {vendor}) -and -not (Get-ChildItem -LiteralPath {vendor} -Force)) "
                f"{{ Remove-Item -LiteralPath {vendor} -Force -ErrorAction SilentlyContinue }}"
            )
    return script


def build_cleanup_commands(state: ViGEmBusState) -> list[tuple[str, list[str]]]:
    """Every command to run elevated, in order, from ONE UAC prompt. Each is
    idempotent and harmless when its target is already gone -- the state was
    read before the registered uninstaller runs, so some targets will be
    removed by it before their own command gets a turn."""
    commands: list[tuple[str, list[str]]] = []
    for entry in state.uninstalls:
        if entry.product_code:
            # RawArg: msiexec shows its usage window instead of uninstalling
            # when its switches arrive quoted (see win_elevation.RawArg).
            msiexec_args = ["/x", entry.product_code, "/qn", "/norestart"]
            commands.append(("msiexec.exe", [RawArg(arg) for arg in msiexec_args]))
    if state.service_present:
        commands.append(("sc.exe", ["stop", SERVICE_NAME]))
    for instance in state.devices:
        commands.append(("pnputil.exe", ["/remove-device", instance]))
    for package in state.driver_packages:
        commands.append(("pnputil.exe", ["/delete-driver", package, "/uninstall", "/force"]))
    if state.service_present:
        commands.append(("sc.exe", ["delete", SERVICE_NAME]))
    if state.paths:
        commands.append(
            ("powershell.exe", ["-NoProfile", "-NonInteractive", "-Command", _powershell_remove_script(state.paths)])
        )
    return commands
