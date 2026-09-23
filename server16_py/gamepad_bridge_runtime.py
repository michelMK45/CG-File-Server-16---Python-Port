from __future__ import annotations

import ctypes
import importlib.util
import os
import sys
import threading
import time
import winreg
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, TYPE_CHECKING

from .win_elevation import shell_execute_elevated_and_wait

try:
    import pygame

    PYGAME_AVAILABLE = True
except Exception:
    PYGAME_AVAILABLE = False

# SDL's GameController API: maps any gamepad SDL knows (its built-in
# database covers Switch Pro/Joy-Cons, PS3/4/5, 8BitDo, Stadia, most generic
# USB pads...) onto one standard Xbox-style layout -- see
# read_controller_state(). Optional: pads SDL doesn't recognize, or a pygame
# build without _sdl2, fall back to the raw-index button maps below.
try:
    from pygame._sdl2 import controller as sdl_controller

    SDL_CONTROLLER_AVAILABLE = True
except Exception:
    sdl_controller = None
    SDL_CONTROLLER_AVAILABLE = False

# vgamepad's own package connects to ViGEmBus (vigem_connect) as a
# MODULE-LEVEL side effect the instant it's imported --
# `vgamepad/win/virtual_gamepad.py` does `VBUS = VBus()` at module scope,
# not lazily inside VX360Gamepad.__init__() as the library's README example
# implies. Reported live 2026-09-24: uninstalling ViGEmBus (via this tab's
# own Uninstall Driver button) made the WHOLE APP crash at every subsequent
# startup with an uncaught `Exception: VIGEM_ERROR_BUS_NOT_FOUND` the moment
# this module was imported from app.py -- a bare `except ImportError:` here
# never catches it, since it's a plain Exception, not an ImportError. This is
# the same class of native-dependency import failure `video_preview.py`'s
# `_load_player_class()` already guards against with `except Exception` for
# ffpyplayer; this needed the identical treatment.
#
# VGAMEPAD_AVAILABLE: True only once vgamepad fully imported (package
# present AND ViGEmBus present/connectable) -- gates actual bridging.
# VGAMEPAD_PACKAGE_PRESENT: True whenever the `vgamepad` package itself is
# installed, independent of whether the import above actually completed --
# located via importlib.util.find_spec (metadata only, never executes
# __init__.py, so it can't trigger the same VBus-connect failure) so the
# Gamepads tab can still find vgamepad's own bundled installer and offer
# "Install Driver" even in the exact state that crashes a plain import.
VGAMEPAD_AVAILABLE = False
VGAMEPAD_PACKAGE_PRESENT = False
VGAMEPAD_IMPORT_ERROR: str | None = None
try:
    import vgamepad as vg

    VGAMEPAD_AVAILABLE = True
    VGAMEPAD_PACKAGE_PRESENT = True
except Exception as _vgamepad_exc:
    VGAMEPAD_IMPORT_ERROR = str(_vgamepad_exc)
    try:
        VGAMEPAD_PACKAGE_PRESENT = importlib.util.find_spec("vgamepad") is not None
    except Exception:
        VGAMEPAD_PACKAGE_PRESENT = False


if TYPE_CHECKING:
    from .app import Server16App

SLOT_COUNT = 4
# What the test dialog asks the SDL thread to keep open and sampled:
# (device GUID, slot index), slot index None meaning "any pad with this GUID".
WatchKey = tuple[str, "int | None"]
POLL_INTERVAL_SECONDS = 0.008  # ~125Hz, same "cheap read on a dedicated thread" idiom as
# app_overlay.py's _gamepad_poll_thread_func / _hotkey_poll_thread_func.
# Full device-list rescan cadence, on top of the immediate rescan every
# JOYDEVICEADDED/REMOVED event triggers -- a safety net in case a backend
# ever hot-plugs without SDL posting an event.
RESCAN_INTERVAL_SECONDS = 1.0
# How long to wait before retrying a failed open. Confirmed live 2026-09-23:
# with Steam running, Steam keeps the Switch Pro Controller's HID device open
# (shared, not exclusive) and talks to it constantly, so SDL's own USB
# handshake fails ~half the time ("Couldn't setup USB mode", 3 of 6 attempts)
# -- a retry nearly always gets through within a few seconds.
OPEN_RETRY_SECONDS = 1.0
# A device the test dialog stops polling for this long is closed again
# (unless a slot still needs it).
RAW_WATCH_TIMEOUT_SECONDS = 2.0
# How long list_devices() waits for the SDL thread's first scan when it has
# to start the thread itself (the Gamepads tab is built before app.py calls
# start()).
FIRST_SCAN_TIMEOUT_SECONDS = 2.0

# ViGEm's virtual Xbox 360 pad reports the real wired Xbox 360 controller's
# identity (confirmed live: VID 045E, PID 028E, named "Xbox 360 Controller").
_VIGEM_X360_VID_PID = (0x045E, 0x028E)
# SDL2 GUID byte 14 is the backend "driver signature". 'x' (XInput) and 'r'
# (RawInput -- which in SDL2 only ever handles XInput-class devices) mark a
# pad FIFA already reads natively -- including this app's own virtual pads,
# confirmed live 2026-09-23 as signature 'r'. Offering those in the slot
# combo let a slot bridge its own virtual pad into a second virtual pad
# (seen in server16.log: "bridging 'Xbox 360 Controller'").
_XINPUT_GUID_SIGNATURES = (ord("x"), ord("r"))

PROFILE_AUTO = "auto"
PROFILE_SWITCH_PRO = "switch_pro"
PROFILE_GENERIC = "generic"

_SWITCH_PRO_NAME_HINTS = ("pro controller", "switch pro", "nintendo switch")

# Raw Windows HID button index -> target Xbox button, for the Nintendo Switch
# Pro Controller via SDL2/pygame's hidapi Switch driver. This performs a
# POSITIONAL remap (not SDL's default label-based one, which is confirmed to
# swap A/B and X/Y on this exact controller): physical B (bottom) lands on
# Xbox's bottom button (A), physical A (right) on Xbox's right button (B),
# physical Y (left) on Xbox's left button (X), physical X (top) on Xbox's top
# button (Y).
#
# FALLBACK ONLY since 2026-09-23: any pad SDL's GameController database
# recognizes (the real Switch Pro Controller included) now goes through
# read_controller_state() instead. And this table is known to be WRONG for
# SDL's HIDAPI Switch driver: SDL's own mapping for the real pad reports
# back=b4, guide=b5, start=b6, leftstick=b7, rightstick=b8, shoulders=b9/b10,
# D-pad as buttons b11-b14 and ZL/ZR as analog axes 4/5 -- not the indices
# below. It only still applies to a Switch-named pad SDL doesn't recognize.
#
# NOT YET CONFIRMED LIVE against real hardware in this codebase -- this index
# order is the commonly reported one for this controller/backend combination,
# but if a live test shows the wrong physical button lighting up the wrong
# Xbox button, use GamepadBridgeRuntime.describe_raw_state() to see the real
# raw button/axis/hat indices and adjust this table. Keep the mapping
# isolated here so a fix never has to touch the polling/threading code below.
SWITCH_PRO_BUTTON_MAP: dict[int, str] = {
    0: "XUSB_GAMEPAD_A",
    1: "XUSB_GAMEPAD_B",
    2: "XUSB_GAMEPAD_X",
    3: "XUSB_GAMEPAD_Y",
    4: "XUSB_GAMEPAD_LEFT_SHOULDER",
    5: "XUSB_GAMEPAD_RIGHT_SHOULDER",
    8: "XUSB_GAMEPAD_BACK",   # Minus
    9: "XUSB_GAMEPAD_START",  # Plus
    10: "XUSB_GAMEPAD_LEFT_THUMB",
    11: "XUSB_GAMEPAD_RIGHT_THUMB",
}
SWITCH_PRO_ZL_INDEX = 6
SWITCH_PRO_ZR_INDEX = 7

# Fallback for any other detected pad: a plain positional passthrough (raw
# button i -> the i-th button in a conventional Xbox-like order). Also
# unconfirmed for any specific controller -- this is a best-effort default,
# not a verified mapping, for whatever shows up that isn't a Switch Pro.
GENERIC_BUTTON_MAP: dict[int, str] = {
    0: "XUSB_GAMEPAD_A",
    1: "XUSB_GAMEPAD_B",
    2: "XUSB_GAMEPAD_X",
    3: "XUSB_GAMEPAD_Y",
    4: "XUSB_GAMEPAD_LEFT_SHOULDER",
    5: "XUSB_GAMEPAD_RIGHT_SHOULDER",
    6: "XUSB_GAMEPAD_BACK",
    7: "XUSB_GAMEPAD_START",
    8: "XUSB_GAMEPAD_LEFT_THUMB",
    9: "XUSB_GAMEPAD_RIGHT_THUMB",
}

# Every XUSB_BUTTON name either button map can produce, plus the four D-pad
# directions (never in the maps themselves -- those come from the hat, see
# _apply_dpad/resolve_mapped_state). Used by resolve_mapped_state() to seed
# a "everything starts unpressed" dict without needing the real vgamepad
# XUSB_BUTTON enum (which requires ViGEmBus to be connectable to import,
# see the guarded import at the top of this file) -- GamepadTestDialog must
# keep working to show raw input even when vgamepad/ViGEmBus isn't.
_ALL_XUSB_BUTTON_NAMES = (
    "XUSB_GAMEPAD_A",
    "XUSB_GAMEPAD_B",
    "XUSB_GAMEPAD_X",
    "XUSB_GAMEPAD_Y",
    "XUSB_GAMEPAD_LEFT_SHOULDER",
    "XUSB_GAMEPAD_RIGHT_SHOULDER",
    "XUSB_GAMEPAD_BACK",
    "XUSB_GAMEPAD_START",
    "XUSB_GAMEPAD_LEFT_THUMB",
    "XUSB_GAMEPAD_RIGHT_THUMB",
    "XUSB_GAMEPAD_DPAD_UP",
    "XUSB_GAMEPAD_DPAD_DOWN",
    "XUSB_GAMEPAD_DPAD_LEFT",
    "XUSB_GAMEPAD_DPAD_RIGHT",
)


def _clamp(value: float) -> float:
    return max(-1.0, min(1.0, value))


PROFILE_STANDARD = "standard"

# SDL GameController button -> Xbox button. SDL's own layout IS the Xbox one
# (A = bottom face button, B = right, X = left, Y = top), so this is 1:1 --
# SDL does the per-controller translation from its mapping database.
_CONTROLLER_BUTTON_MAP: tuple[tuple[str, str], ...] = (
    ("CONTROLLER_BUTTON_A", "XUSB_GAMEPAD_A"),
    ("CONTROLLER_BUTTON_B", "XUSB_GAMEPAD_B"),
    ("CONTROLLER_BUTTON_X", "XUSB_GAMEPAD_X"),
    ("CONTROLLER_BUTTON_Y", "XUSB_GAMEPAD_Y"),
    ("CONTROLLER_BUTTON_LEFTSHOULDER", "XUSB_GAMEPAD_LEFT_SHOULDER"),
    ("CONTROLLER_BUTTON_RIGHTSHOULDER", "XUSB_GAMEPAD_RIGHT_SHOULDER"),
    ("CONTROLLER_BUTTON_BACK", "XUSB_GAMEPAD_BACK"),
    ("CONTROLLER_BUTTON_START", "XUSB_GAMEPAD_START"),
    ("CONTROLLER_BUTTON_GUIDE", "XUSB_GAMEPAD_GUIDE"),
    ("CONTROLLER_BUTTON_LEFTSTICK", "XUSB_GAMEPAD_LEFT_THUMB"),
    ("CONTROLLER_BUTTON_RIGHTSTICK", "XUSB_GAMEPAD_RIGHT_THUMB"),
    ("CONTROLLER_BUTTON_DPAD_UP", "XUSB_GAMEPAD_DPAD_UP"),
    ("CONTROLLER_BUTTON_DPAD_DOWN", "XUSB_GAMEPAD_DPAD_DOWN"),
    ("CONTROLLER_BUTTON_DPAD_LEFT", "XUSB_GAMEPAD_DPAD_LEFT"),
    ("CONTROLLER_BUTTON_DPAD_RIGHT", "XUSB_GAMEPAD_DPAD_RIGHT"),
)
_SDL_AXIS_MAX = 32767.0


def read_controller_state(controller, constants=None) -> dict:
    """Reads an SDL GameController into the same dict shape
    resolve_mapped_state() returns -- buttons by XUSB name, sticks as
    (x, y) in [-1, 1] with Y up-positive (XInput convention; SDL reports
    down as positive), analog triggers in [0, 1]."""
    constants = constants if constants is not None else pygame

    def axis(name: str) -> float:
        return _clamp(controller.get_axis(getattr(constants, name)) / _SDL_AXIS_MAX)

    buttons = {
        xusb_name: bool(controller.get_button(getattr(constants, sdl_name)))
        for sdl_name, xusb_name in _CONTROLLER_BUTTON_MAP
    }
    return {
        "buttons": buttons,
        "left_stick": (axis("CONTROLLER_AXIS_LEFTX"), _clamp(-axis("CONTROLLER_AXIS_LEFTY"))),
        "right_stick": (axis("CONTROLLER_AXIS_RIGHTX"), _clamp(-axis("CONTROLLER_AXIS_RIGHTY"))),
        "left_trigger": max(0.0, axis("CONTROLLER_AXIS_TRIGGERLEFT")),
        "right_trigger": max(0.0, axis("CONTROLLER_AXIS_TRIGGERRIGHT")),
    }


def apply_mapped_state(pad, state: dict) -> None:
    """Pushes a read_controller_state()/resolve_mapped_state()-shaped dict
    onto a virtual Xbox 360 pad."""
    for xusb_name, pressed in state["buttons"].items():
        button = getattr(vg.XUSB_BUTTON, xusb_name, None)
        if button is None:
            continue
        if pressed:
            pad.press_button(button=button)
        else:
            pad.release_button(button=button)
    pad.left_joystick_float(x_value_float=state["left_stick"][0], y_value_float=state["left_stick"][1])
    pad.right_joystick_float(x_value_float=state["right_stick"][0], y_value_float=state["right_stick"][1])
    pad.left_trigger_float(value_float=state["left_trigger"])
    pad.right_trigger_float(value_float=state["right_trigger"])


@dataclass
class DeviceInfo:
    """One physical pad as of the SDL thread's last scan. `index` is only
    meaningful inside the SDL thread during that same scan (SDL device
    indices shift on every hot-plug); everything outside it identifies a
    device by `instance_id` (unique per connection) or `guid` (stable across
    reconnects, but shared by two identical pads)."""

    index: int
    name: str
    guid: str
    instance_id: int = -1
    # True when SDL's GameController database recognizes this pad, i.e. the
    # bridge will use the standard Xbox layout for it (PROFILE_STANDARD).
    is_controller: bool = False


@dataclass
class SlotState:
    enabled: bool = False
    device_guid: str = ""
    profile: str = PROFILE_AUTO
    status: str = "disconnected"  # disconnected | busy | active
    # Phase 2 (HidHide): whether this slot's physical device should be
    # cloaked from fifa16.exe specifically, independent of whether the
    # bridge itself is enabled -- see hidhide_runtime.py. Defaults False:
    # hiding a system device is a more invasive change than just
    # translating input, so it's opt-in per slot rather than automatic.
    hide_from_fifa: bool = False
    # Everything below is owned by the SDL thread (_sdl_thread_main) --
    # never touched from any other thread.
    instance_id: int | None = None
    pad: object | None = None
    mapper: Callable | None = None
    device_name: str = ""
    busy_logged: bool = False
    was_connected: bool = False
    bound_guid: str = ""


def _guid_signature(guid: str) -> int:
    try:
        return bytes.fromhex(guid)[14]
    except (ValueError, IndexError):
        return 0


def _guid_vid_pid(guid: str) -> tuple[int, int]:
    try:
        raw = bytes.fromhex(guid)
    except ValueError:
        return 0, 0
    if len(raw) < 10:
        return 0, 0
    return raw[4] | (raw[5] << 8), raw[8] | (raw[9] << 8)


def _same_model(guid_a: str, guid_b: str) -> bool:
    """True when two SDL GUIDs name the same pad model -- what HidHide
    itself keys on (VID/PID), not the full GUID string."""
    if not guid_a or not guid_b:
        return False
    if guid_a == guid_b:
        return True
    vid_pid = _guid_vid_pid(guid_a)
    return vid_pid != (0, 0) and vid_pid == _guid_vid_pid(guid_b)


def is_xinput_device(guid: str) -> bool:
    """True for pads FIFA already reads natively through XInput -- including
    this app's own ViGEm virtual pads, which must never be offered as a
    bridge source (see _XINPUT_GUID_SIGNATURES)."""
    return _guid_signature(guid) in _XINPUT_GUID_SIGNATURES or _guid_vid_pid(guid) == _VIGEM_X360_VID_PID


class _SDLJoystickGUID(ctypes.Structure):
    _fields_ = [("data", ctypes.c_ubyte * 16)]


class _SdlDeviceApi:
    """Reads SDL's per-device-index metadata (name, GUID, instance id)
    WITHOUT opening the device, via the SDL2.dll pygame already loaded.
    pygame itself can only report a name/GUID for a device it has
    successfully opened, and opening is exactly what fails while Steam is
    talking to the same pad (see OPEN_RETRY_SECONDS) -- which is why the pad
    used to vanish from the slot combo whenever Steam was running.

    Must only be called from the SDL thread (same rule as every other SDL
    call in this module)."""

    def __init__(self, dll: ctypes.CDLL) -> None:
        self._dll = dll
        dll.SDL_NumJoysticks.restype = ctypes.c_int
        dll.SDL_JoystickNameForIndex.restype = ctypes.c_char_p
        dll.SDL_JoystickNameForIndex.argtypes = [ctypes.c_int]
        dll.SDL_JoystickGetDeviceGUID.restype = _SDLJoystickGUID
        dll.SDL_JoystickGetDeviceGUID.argtypes = [ctypes.c_int]
        dll.SDL_JoystickGetDeviceInstanceID.restype = ctypes.c_int32
        dll.SDL_JoystickGetDeviceInstanceID.argtypes = [ctypes.c_int]
        dll.SDL_IsGameController.restype = ctypes.c_int
        dll.SDL_IsGameController.argtypes = [ctypes.c_int]

    @classmethod
    def load(cls) -> "_SdlDeviceApi | None":
        # GetModuleHandleW first: reuse the exact SDL2.dll instance pygame
        # already loaded (a second, separate copy would have its own empty
        # joystick list). pygame's own package folder is only a fallback.
        try:
            # Own WinDLL instance with an explicit pointer-sized restype --
            # the default int restype truncates a 64-bit module handle
            # (confirmed live: 0x7ffb01530000 came back as 0x1530000).
            kernel32 = ctypes.WinDLL("kernel32")
            kernel32.GetModuleHandleW.restype = ctypes.c_void_p
            kernel32.GetModuleHandleW.argtypes = [ctypes.c_wchar_p]
            handle = kernel32.GetModuleHandleW("SDL2.dll")
            if handle:
                return cls(ctypes.CDLL("SDL2.dll", handle=handle))
            return cls(ctypes.CDLL(os.path.join(os.path.dirname(pygame.__file__), "SDL2.dll")))
        except Exception:
            return None

    def scan(self) -> list[DeviceInfo]:
        devices: list[DeviceInfo] = []
        for index in range(max(0, self._dll.SDL_NumJoysticks())):
            raw_name = self._dll.SDL_JoystickNameForIndex(index)
            guid = bytes(self._dll.SDL_JoystickGetDeviceGUID(index).data).hex()
            devices.append(
                DeviceInfo(
                    index=index,
                    name=raw_name.decode("utf-8", errors="replace") if raw_name else f"Joystick {index}",
                    guid=guid,
                    instance_id=int(self._dll.SDL_JoystickGetDeviceInstanceID(index)),
                    is_controller=bool(self._dll.SDL_IsGameController(index)),
                )
            )
        return devices


class GamepadBridgeRuntime:
    """Translates up to SLOT_COUNT physical gamepads into virtual Xbox 360
    pads (via ViGEmBus/vgamepad) so FIFA -- which only reliably reads
    XInput/Xbox-layout controllers -- can use pads it otherwise ignores
    (Switch Pro Controller, etc). Entirely independent of FIFA's process
    lifecycle: started once at app startup and stopped at app shutdown, never
    gated on FIFA being detected/running (see app.py).

    Threading model -- ONE thread owns SDL. Every pygame/SDL call (init,
    event pumping, opening/closing joysticks, reading them) and every
    virtual-pad update happens on _sdl_thread_main. The Tk thread only
    reads snapshots that thread publishes under self._lock (list_devices,
    read_raw_state, get_slot_snapshot) and hands it config changes
    (set_slot_config). This replaced one thread per slot plus direct
    pygame calls from the Tk thread: several threads pumping SDL events
    while a pad was unplugged/replugged crashed the whole app natively
    (reported live 2026-09-23 -- server16.log just stops, no traceback),
    and opening pads by SDL device *index* meant a replug could shift the
    indices and make a slot open a different device -- its own virtual
    pad, as server16.log showed ("bridging 'Xbox 360 Controller'")."""

    def __init__(self, app: "Server16App") -> None:
        self.app = app
        self._slots: list[SlotState] = [SlotState() for _ in range(SLOT_COUNT)]
        self._lock = threading.Lock()
        self._devices: list[DeviceInfo] = []
        # Keyed by (device GUID, slot index), not instance id: instance ids
        # change on every reconnect (and on every joystick re-init, see
        # _reinit_joysticks), and the test dialog must keep working across
        # both. The slot index is part of the key because a GUID names a
        # MODEL, not one unit -- two identical pads share it, so the GUID
        # alone can't say which of them a slot's Test button means.
        self._raw_states: dict[WatchKey, dict] = {}
        self._raw_watch: dict[WatchKey, float] = {}
        # SDL-thread-only: which instance id each watch key resolved to on
        # the last _sync_devices() pass, so _publish_raw_states() samples
        # exactly the device that pass opened.
        self._watch_targets: dict[WatchKey, int] = {}
        self._busy_guids: set[str] = set()
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._wake_event = threading.Event()
        self._first_scan_done = threading.Event()
        # SDL-thread-only: earliest monotonic time a failed open may be
        # retried, per instance id.
        self._open_retry_at: dict[int, float] = {}
        # SDL-thread-only: devices SDL dropped from its own list right after
        # a failed open (see _open_device), kept listed as "busy" until the
        # next _reinit_joysticks() brings them back.
        self._vanished: dict[int, DeviceInfo] = {}
        self._reinit_at: float | None = None
        self._reinit_logged = False
        self._api: _SdlDeviceApi | None = None
        # SDL-thread-only: SDL GameController handle per open instance id,
        # for pads SDL's mapping database recognizes (see _open_device).
        self._controllers: dict[int, object] = {}

    # ------------------------------------------------------------------
    # Dependency / driver state
    # ------------------------------------------------------------------

    @staticmethod
    def dependencies_available() -> bool:
        """Gates actual gamepad bridging -- needs vgamepad to have fully
        imported (package present AND ViGEmBus present/connectable)."""
        return PYGAME_AVAILABLE and VGAMEPAD_AVAILABLE

    @staticmethod
    def dependencies_installed() -> bool:
        """True once the required Python packages are genuinely on disk,
        even if vgamepad's own import failed for a reason OTHER than a
        missing package -- i.e. ViGEmBus not being present/connectable (see
        the import guard at the top of this module). Used to decide whether
        to show a generic "install pygame/vgamepad" notice at all: once the
        package is confirmed present, the driver-status card's own
        Install/Uninstall Driver button is the right next step, not a
        redundant "missing dependency" message."""
        return PYGAME_AVAILABLE and VGAMEPAD_PACKAGE_PRESENT

    def is_vigembus_installed(self) -> bool:
        """Checks driver presence via its Windows service registry key --
        deliberately NOT by constructing a vg.VX360Gamepad() (an earlier
        version of this method did). Reported live 2026-09-24: that
        constructed a real virtual USB/XInput device, then immediately
        destroyed it, on every single call -- including every Gamepads tab
        visit and every language switch (_apply_gamepads_tab_localization) --
        which plugs and unplugs an actual device on the bus each time,
        audibly triggering Windows' device-connected/disconnected sound
        repeatedly for no reason. ViGEmBus registers itself as a standard
        kernel-mode service named "ViGEmBus"; the key's mere presence under
        Services means the driver package is installed, independent of
        whether the service happens to be running right now -- the same
        registry-presence check other ViGEm-based tools use for this."""
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Services\ViGEmBus"):
                return True
        except OSError:
            return False

    def find_vigembus_installer(self) -> Path | None:
        """Prefers whatever installer a contributor has placed under
        bin\\ViGEmBus\\ (matched by extension, not a hardcoded name --
        Nefarius has changed the installer's own naming/format at least
        once already: older releases shipped per-arch
        ViGEmBusSetup_x64.msi/_x86.msi, the current one, as of 1.22.0, ships
        one combined ViGEmBus_<version>_x64_x86_arm64.exe bootstrapper
        instead; .exe wins when both are present since that's the current
        format). bin\\ViGEmBus\\ is an OVERRIDE, not the primary source --
        falls back to the installer vgamepad's own package already vendors
        (confirmed present: win/vigem/install/{x64,x86}/ViGEmBusSetup_*.msi
        inside the installed vgamepad package) when nothing is placed there,
        so most builds need nothing manually downloaded/placed at all.

        Searches app.base_dir (the deployed .exe's own folder -- a manual
        override) BEFORE app.resource_dir (sys._MEIPASS in a frozen onefile
        build, where Server16Python.spec's bin\\ViGEmBus datas entry actually
        extracts to at runtime) -- see hidhide_runtime.py's
        find_hidhide_installer() for the live-reported bug this mirrors:
        base_dir alone never sees a repo-time-only bin\\ViGEmBus placement
        once it's bundled into a onefile build. This one was masked here by
        the vgamepad-bundled-msi fallback below, so it never surfaced as a
        broken button the way HidHide's did (no fallback exists there)."""
        for candidate_root in self._installer_search_roots():
            base = candidate_root / "bin" / "ViGEmBus"
            if not base.is_dir():
                continue
            exe_matches = sorted(base.glob("*.exe"))
            if exe_matches:
                return exe_matches[0]
            msi_matches = sorted(base.glob("*.msi"))
            if msi_matches:
                return msi_matches[0]
        return self._vgamepad_bundled_installer()

    def _installer_search_roots(self) -> list[Path]:
        roots = [Path(self.app.base_dir)]
        resource_dir = getattr(self.app, "resource_dir", None)
        if resource_dir is not None and Path(resource_dir) != roots[0]:
            roots.append(Path(resource_dir))
        return roots

    def _vgamepad_bundled_installer(self) -> Path | None:
        package_dir = self._vgamepad_package_dir()
        if package_dir is None:
            return None
        arch = "x64" if ctypes.sizeof(ctypes.c_void_p) == 8 else "x86"
        candidate = package_dir / "win" / "vigem" / "install" / arch / f"ViGEmBusSetup_{arch}.msi"
        return candidate if candidate.exists() else None

    @staticmethod
    def _vgamepad_package_dir() -> Path | None:
        """Locates vgamepad's package directory via import *metadata* only
        (importlib.util.find_spec) -- deliberately never a plain `import
        vgamepad`, which has the module-level ViGEmBus-connect side effect
        documented at the top of this file. This must keep working even
        when vgamepad fails to fully import, since that's exactly the state
        right after the driver was uninstalled -- precisely the moment the
        Install Driver button most needs to still find its bundled
        installer."""
        if VGAMEPAD_AVAILABLE:
            return Path(vg.__file__).resolve().parent
        try:
            spec = importlib.util.find_spec("vgamepad")
        except Exception:
            return None
        if spec is None or not spec.origin:
            return None
        return Path(spec.origin).resolve().parent

    def install_vigembus(self, on_done: Callable[[bool, str], None] | None = None) -> bool:
        """Launches the bundled ViGEmBus installer elevated (UAC). Never
        blocks the caller -- on_done(success, message) fires later on the Tk
        main thread once the elevated installer finishes. Returns False
        immediately (no on_done call) only if the installer couldn't even be
        launched, e.g. nothing is bundled under bin/ViGEmBus."""
        installer_path = self.find_vigembus_installer()
        if installer_path is None:
            return False
        self._run_elevated_installer(installer_path, uninstall=False, on_done=on_done)
        return True

    def uninstall_vigembus(self, on_done: Callable[[bool, str], None] | None = None) -> bool:
        installer_path = self.find_vigembus_installer()
        if installer_path is None:
            return False
        # A virtual pad can't be torn down mid-use by the driver it depends
        # on -- release every slot first.
        self.stop()
        self._run_elevated_installer(installer_path, uninstall=True, on_done=on_done)
        return True

    def _run_elevated_installer(
        self, installer_path: Path, uninstall: bool, on_done: Callable[[bool, str], None] | None
    ) -> None:
        """Launches the installer elevated and waits for it on a background
        thread. Dispatches by extension:
        - .msi (older ViGEmBusSetup_x64.msi/_x86.msi releases): via
          msiexec.exe, `/i`/`/x` + `/qn` -- well-documented, standard.
        - .exe (the current, as of 1.22.0, combined
          ViGEmBus_<version>_x64_x86_arm64.exe bootstrapper): launched
          directly. `/exenoui /qn /norestart` for install and
          `/uninstall /exenoui /qn /norestart` for uninstall are the
          community-sourced best-effort silent switches for this newer
          installer format -- Nefarius's own docs are still written for the
          old .msi and don't cover this one, and there's at least one open
          upstream report of the silent switch not always fully suppressing
          UI (nefarius/ViGEmBus#108). That's why success here is decided by
          re-checking is_vigembus_installed() after the process exits, never
          by the exit code or by assuming the switches worked -- if the
          installer's own UI ends up showing anyway, this still waits for it
          and still reports the real outcome once the user closes it."""
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
                self._finish_install_action(
                    on_done, False, "Elevation was declined, or the installer could not be launched."
                )
                return
            installed = self.is_vigembus_installed()
            success = (not installed) if uninstall else installed
            if success:
                message = "ViGEmBus uninstalled." if uninstall else "ViGEmBus installed."
            else:
                message = (
                    "Uninstall finished but the driver still looks installed -- if the installer showed its "
                    "own window, check whether it was actually confirmed, or uninstall from Windows' Apps & "
                    "Features (\"Nefarius Virtual Gamepad Emulation Bus\")."
                    if uninstall
                    else "Installer finished but the driver still isn't detected -- if a window appeared, "
                    "check whether the install was actually completed/confirmed there."
                )
            self._finish_install_action(on_done, success, message)

        threading.Thread(target=_worker, name="vigembus-installer", daemon=True).start()

    def _finish_install_action(
        self, on_done: Callable[[bool, str], None] | None, success: bool, message: str
    ) -> None:
        if on_done is None:
            return
        try:
            self.app.after(0, lambda: on_done(success, message))
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Public, Tk-thread-safe API -- snapshots published by the SDL thread
    # ------------------------------------------------------------------

    def list_devices(self) -> list[DeviceInfo]:
        """Bridgeable physical pads as of the SDL thread's last scan. Never
        touches SDL itself. XInput pads (including this app's own virtual
        pads) are excluded -- see is_xinput_device()."""
        if not self._ensure_thread():
            return []
        self._first_scan_done.wait(FIRST_SCAN_TIMEOUT_SECONDS)
        with self._lock:
            return list(self._devices)

    def resolve_profile(self, name: str, guid: str, override: str = PROFILE_AUTO) -> str:
        if override in (PROFILE_SWITCH_PRO, PROFILE_GENERIC):
            return override
        lowered = (name or "").lower()
        if any(hint in lowered for hint in _SWITCH_PRO_NAME_HINTS):
            return PROFILE_SWITCH_PRO
        return PROFILE_GENERIC

    def read_raw_state(self, device_guid: str, slot_index: int | None = None) -> dict | None:
        """Latest snapshot of one physical device's raw button/axis/hat
        state -- {"buttons": [bool, ...], "axes": [float, ...],
        "hats": [(x, y), ...]} -- or None if it isn't readable right now
        (unplugged, or still failing to open, see is_device_busy()). Each
        call also asks the SDL thread to keep the device open and sampled
        for RAW_WATCH_TIMEOUT_SECONDS, so GamepadTestDialog works for a
        device no enabled slot is using.

        Pass slot_index whenever the caller means "the pad THIS slot
        controls": a GUID only identifies a model, so with two identical
        pads plugged in, the GUID alone always resolves to the same (first)
        one -- every slot's Test showed slot 1's pad (reported live
        2026-09-24). None keeps that any-pad-with-this-GUID behavior."""
        if not self._ensure_thread():
            return None
        key: WatchKey = (device_guid, slot_index)
        with self._lock:
            self._raw_watch[key] = time.monotonic()
            state = self._raw_states.get(key)
        return dict(state) if state is not None else None

    def is_device_busy(self, device_guid: str) -> bool:
        """True while the device is present but opening it keeps failing --
        in practice, another program (Steam) talking to it at the same time."""
        with self._lock:
            return device_guid in self._busy_guids

    def describe_raw_state(self, device_guid: str) -> str:
        """Human-readable dump of read_raw_state() -- for calibrating
        SWITCH_PRO_BUTTON_MAP / the stick-axis assumptions above against
        real hardware, printed to the runtime log."""
        state = self.read_raw_state(device_guid)
        if state is None:
            return "pygame joystick subsystem unavailable"
        buttons_down = [i for i, pressed in enumerate(state["buttons"]) if pressed]
        axes = [round(a, 3) for a in state["axes"]]
        return f"buttons_down={buttons_down} axes={axes} hats={state['hats']}"

    # ------------------------------------------------------------------
    # Slot configuration
    # ------------------------------------------------------------------

    def get_slot_snapshot(self, index: int) -> dict:
        slot = self._slots[index]
        with self._lock:
            return {
                "enabled": slot.enabled,
                "device_guid": slot.device_guid,
                "profile": slot.profile,
                "status": slot.status,
                "hide_from_fifa": slot.hide_from_fifa,
            }

    def set_slot_config(
        self,
        index: int,
        *,
        enabled: bool,
        device_guid: str,
        profile: str = PROFILE_AUTO,
        hide_from_fifa: bool | None = None,
    ) -> None:
        """hide_from_fifa=None leaves the slot's current HidHide preference
        untouched (callers that only change enabled/device/profile, e.g.
        the bridge Enabled checkbox or the device combo) -- pass an
        explicit bool to change it (the Hide from FIFA checkbox).

        Only records the new config; the SDL thread picks it up on its next
        tick (woken immediately) and opens/closes/creates/destroys whatever
        that requires -- this never blocks on, or calls into, SDL."""
        if not (0 <= index < SLOT_COUNT):
            return
        slot = self._slots[index]
        with self._lock:
            slot.enabled = enabled
            slot.device_guid = device_guid
            slot.profile = profile
            previous_hide = slot.hide_from_fifa
            if hide_from_fifa is not None:
                slot.hide_from_fifa = hide_from_fifa
        self._persist_slot(index)
        if enabled and device_guid:
            self._ensure_thread()
        self._wake_event.set()
        if hide_from_fifa is not None and hide_from_fifa != previous_hide:
            self._apply_hidhide_preference(index)

    def clear_slot(self, index: int) -> None:
        """Forgets one slot entirely: turns its bridge off (the SDL thread
        releases the virtual pad on its next tick), resets its entry in
        runtime/settings.json to the defaults so no device GUID stays saved
        for a pad that won't be used, and lifts its HidHide cloak.

        The cloak matters because it lives in HidHide's driver, not in
        settings.json -- dropping only the setting would leave the physical
        pad hidden from every app with nothing in this UI left to undo it.
        HidHide hides by model (VID/PID), so it's only lifted when no OTHER
        slot still asking for Hide from FIFA has the same model."""
        if not (0 <= index < SLOT_COUNT):
            return
        slot = self._slots[index]
        with self._lock:
            previous_guid = slot.device_guid
            was_hidden = slot.hide_from_fifa
            slot.enabled = False
            slot.device_guid = ""
            slot.profile = PROFILE_AUTO
            slot.hide_from_fifa = False
            still_hidden_by_another_slot = any(
                other.hide_from_fifa and _same_model(other.device_guid, previous_guid)
                for other_index, other in enumerate(self._slots)
                if other_index != index
            )
        self._persist_slot(index)
        self._wake_event.set()
        if was_hidden and previous_guid and not still_hidden_by_another_slot:
            self._unhide_in_background(index, previous_guid)

    def _unhide_in_background(self, index: int, device_guid: str) -> None:
        hidhide = getattr(self.app, "hidhide", None)
        if hidhide is None:
            return

        def _worker() -> None:
            try:
                hidhide.unhide_device_for_slot(device_guid)
            except Exception as exc:
                self.app.log(f"Gamepad slot {index + 1}: could not lift the HidHide cloak ({exc})")

        threading.Thread(target=_worker, name=f"gamepad-hidhide-clear-slot-{index}", daemon=True).start()

    def _apply_hidhide_preference(self, index: int) -> None:
        """Applies (or removes) the physical-device cloak for one slot via
        HidHide (hidhide_runtime.py), on a background thread -- IOCTL
        round-trips and a possible elevation prompt must never block the Tk
        main thread, same rule the driver install/uninstall buttons already
        follow. No-ops quietly if HidHide isn't wired up or the slot has no
        device selected yet.

        Only ever called from set_slot_config() when hide_from_fifa is
        explicitly toggled by the user this session -- never automatically
        re-applied at app startup for a slot whose preference was already
        True from a previous session (see start()'s own docstring for why:
        a UAC prompt on every single app launch, reported live 2026-09-24)."""
        slot = self._slots[index]
        hidhide = getattr(self.app, "hidhide", None)
        if hidhide is None or not slot.device_guid:
            return
        hide = slot.hide_from_fifa
        device_guid = slot.device_guid

        def _worker() -> None:
            if hide:
                # Hide + cloak-on + app-reg <this app's own exe> + a device
                # restart -- tried unelevated first (usually needs no UAC
                # prompt at all, see hidhide_runtime.hide_device_for_slot()).
                hidhide.hide_device_for_slot(device_guid, own_exe=sys.executable)
            else:
                hidhide.unhide_device_for_slot(device_guid)

        threading.Thread(target=_worker, name=f"gamepad-hidhide-slot-{index}", daemon=True).start()

    def _persist_slot(self, index: int) -> None:
        data = self.app.settings.data.setdefault("gamepad_bridge", {"slots": []})
        slots = data.setdefault("slots", [])
        while len(slots) <= index:
            slots.append(
                {"enabled": False, "device_guid": "", "profile": PROFILE_AUTO, "hide_from_fifa": False}
            )
        slot = self._slots[index]
        slots[index] = {
            "enabled": slot.enabled,
            "device_guid": slot.device_guid,
            "profile": slot.profile,
            "hide_from_fifa": slot.hide_from_fifa,
        }
        self.app.settings.save()

    def start(self) -> None:
        """Loads every slot from settings.json and starts the SDL thread.
        Call once at app startup -- deliberately not gated on FIFA being
        installed/running/detected.

        For every slot whose Hide from FIFA was already checked, makes
        HidHide's real state match it (hidhide_runtime.ensure_hidden_for_
        slot) on a background thread -- NEVER elevated, so still no UAC
        prompt at launch (the reason startup used to skip HidHide entirely,
        reported live 2026-09-24). Skipping it let the checkbox and the real
        state drift apart: reported live 2026-09-23, the box showed checked
        while nothing was hidden, and FIFA listed the physical pad as player
        1 next to the virtual one. Hiding no longer needs elevation (see
        hide_device_for_slot), which is what makes re-applying it safe."""
        data = self.app.settings.data.get("gamepad_bridge", {})
        slots_data = data.get("slots", [])
        with self._lock:
            for index in range(SLOT_COUNT):
                cfg = slots_data[index] if index < len(slots_data) else {}
                slot = self._slots[index]
                slot.enabled = bool(cfg.get("enabled", False))
                slot.device_guid = str(cfg.get("device_guid", ""))
                slot.profile = str(cfg.get("profile", PROFILE_AUTO))
                slot.hide_from_fifa = bool(cfg.get("hide_from_fifa", False))
        self._ensure_thread()
        self._reapply_hidden_slots()

    def _reapply_hidden_slots(self) -> None:
        hidhide = getattr(self.app, "hidhide", None)
        ensure = getattr(hidhide, "ensure_hidden_for_slot", None)
        if ensure is None:
            return
        guids = sorted({s.device_guid for s in self._slots if s.hide_from_fifa and s.device_guid})
        if not guids:
            return

        def _worker() -> None:
            for guid in guids:
                try:
                    ensure(guid, own_exe=sys.executable)
                except Exception as exc:
                    self.app.log(f"HidHide: could not re-apply Hide from FIFA at startup ({exc})")

        threading.Thread(target=_worker, name="gamepad-hidhide-startup", daemon=True).start()

    def stop(self) -> None:
        """Stops the SDL thread, which releases every virtual pad and closes
        every physical device on its way out. A later list_devices()/
        set_slot_config() restarts it."""
        thread = self._thread
        self._stop_event.set()
        self._wake_event.set()
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=3.0)
        self._thread = None

    def _ensure_thread(self) -> bool:
        if not PYGAME_AVAILABLE:
            return False
        thread = self._thread
        if thread is not None and thread.is_alive():
            return True
        self._stop_event = threading.Event()
        self._first_scan_done = threading.Event()
        thread = threading.Thread(target=self._sdl_thread_main, name="gamepad-bridge-sdl", daemon=True)
        self._thread = thread
        thread.start()
        return True

    # ------------------------------------------------------------------
    # SDL thread -- the only place pygame/SDL/vgamepad are ever called
    # ------------------------------------------------------------------

    def _sdl_thread_main(self) -> None:
        stop_event = self._stop_event
        first_scan_done = self._first_scan_done
        # Joystick input must keep flowing while FIFA, not this app, has
        # focus. SDL reads hints from the environment when not set in code.
        os.environ.setdefault("SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS", "1")
        # Map face buttons by POSITION, like an Xbox pad: the bottom button
        # is always A whatever it's labelled. SDL's default for Nintendo
        # pads is by LABEL, which puts the Switch's A (the RIGHT button) on
        # Xbox A -- A/B and X/Y swapped for anyone used to an Xbox layout.
        os.environ.setdefault("SDL_GAMECONTROLLER_USE_BUTTON_LABELS", "0")
        try:
            # SDL's joystick enumeration for a device already connected
            # BEFORE init (not just one hot-plugged afterward) depends on
            # its video subsystem being initialized too -- confirmed live
            # 2026-09-24: pygame.joystick.init() alone left an already-
            # connected Switch Pro Controller invisible to get_count().
            # display.init() only sets up SDL's internal plumbing (a hidden
            # message-only window) -- it never opens a visible window, and
            # it's called on THIS thread so SDL's event pumping below runs
            # on the thread that initialized video, as SDL requires.
            pygame.display.init()
            pygame.joystick.init()
            self._init_controller_api()
        except Exception as exc:
            self.app.log(f"Gamepad bridge: could not initialize SDL joystick input ({exc})")
            first_scan_done.set()
            return
        api = self._api = _SdlDeviceApi.load()
        if api is None:
            self.app.log("Gamepad bridge: SDL2.dll device API unavailable -- listing only pads that open cleanly")
        opened: dict[int, object] = {}
        present: dict[int, DeviceInfo] = {}
        next_rescan = 0.0
        logged_errors: set[str] = set()
        try:
            while not stop_event.is_set():
                self._wake_event.clear()
                try:
                    hotplug = False
                    try:
                        for event in pygame.event.get():
                            if event.type in (pygame.JOYDEVICEADDED, pygame.JOYDEVICEREMOVED):
                                hotplug = True
                    except Exception:
                        hotplug = True
                    now = time.monotonic()
                    if self._reinit_at is not None and now >= self._reinit_at:
                        self._reinit_joysticks(opened)
                        hotplug = True
                    if hotplug or now >= next_rescan or not first_scan_done.is_set():
                        present = self._scan_devices(api, opened)
                        next_rescan = now + RESCAN_INTERVAL_SECONDS
                        first_scan_done.set()
                        self._drop_departed_devices(present, opened)
                    self._sync_devices(present, opened, now)
                    self._drive_slots(opened)
                    self._publish_raw_states(opened, now)
                except Exception as exc:
                    # One bad tick (e.g. a device vanishing mid-read) must
                    # not end bridging for every slot; force a rescan.
                    next_rescan = 0.0
                    message = f"{type(exc).__name__}: {exc}"
                    if message not in logged_errors:
                        logged_errors.add(message)
                        self.app.log(f"Gamepad bridge: recovered from an unexpected error ({message})")
                self._wake_event.wait(POLL_INTERVAL_SECONDS)
        finally:
            self._shutdown_sdl_thread(opened)
            first_scan_done.set()

    def _scan_devices(self, api: "_SdlDeviceApi | None", opened: dict[int, object]) -> dict[int, DeviceInfo]:
        """Returns every present device keyed by instance id, and publishes
        the bridgeable (non-XInput) ones for list_devices()."""
        if api is not None:
            try:
                all_devices = api.scan()
            except Exception:
                all_devices = []
        else:
            all_devices = []
            for index in range(pygame.joystick.get_count()):
                try:
                    joystick = pygame.joystick.Joystick(index)
                    all_devices.append(
                        DeviceInfo(index, joystick.get_name(), joystick.get_guid(), joystick.get_instance_id())
                    )
                    if joystick.get_instance_id() not in opened:
                        joystick.quit()
                except Exception:
                    continue
        present = {d.instance_id: d for d in all_devices}
        for instance_id, device in self._vanished.items():
            if instance_id not in present:
                present[instance_id] = device
        bridgeable = [d for d in present.values() if not is_xinput_device(d.guid)]
        with self._lock:
            self._devices = bridgeable
        return present

    def _drop_departed_devices(self, present: dict[int, DeviceInfo], opened: dict[int, object]) -> None:
        for instance_id in [iid for iid in opened if iid not in present]:
            self._close_device(instance_id, opened)
        for index, slot in enumerate(self._slots):
            if slot.instance_id is not None and slot.instance_id not in present:
                slot.instance_id = None
                self._neutralize_pad(slot)
                with self._lock:
                    slot.status = "disconnected"
                self.app.log(
                    f"Gamepad slot {index + 1}: '{slot.device_name}' disconnected -- waiting for it to "
                    "reconnect (virtual pad kept so FIFA's player assignment doesn't change)"
                )

    def _sync_devices(self, present: dict[int, DeviceInfo], opened: dict[int, object], now: float) -> None:
        with self._lock:
            configs = [(s.enabled, s.device_guid, s.profile) for s in self._slots]
            watched = {k for k, seen in self._raw_watch.items() if now - seen < RAW_WATCH_TIMEOUT_SECONDS}
            self._raw_watch = {k: seen for k, seen in self._raw_watch.items() if k in watched}
        busy: set[str] = set()

        claimed: set[int] = set()
        for index, slot in enumerate(self._slots):
            enabled, guid, profile = configs[index]
            wanted = enabled and bool(guid) and VGAMEPAD_AVAILABLE
            if slot.instance_id is not None:
                device = present.get(slot.instance_id)
                if not wanted or device is None or device.guid != guid:
                    slot.instance_id = None
            if slot.bound_guid != guid:
                # A different physical pad was picked for this slot -- its
                # next activation is a fresh start, not a reconnect.
                slot.bound_guid = guid
                slot.was_connected = False
                slot.busy_logged = False
            if not wanted:
                self._release_pad(index, slot)
                continue
            if slot.instance_id is None:
                candidate = next(
                    (
                        d
                        for d in present.values()
                        if d.guid == guid and d.instance_id not in claimed
                        and not any(s.instance_id == d.instance_id for s in self._slots)
                    ),
                    None,
                )
                if candidate is None:
                    with self._lock:
                        slot.status = "disconnected"
                    continue
                if not self._open_device(candidate, opened, now):
                    busy.add(candidate.guid)
                    if not slot.busy_logged:
                        slot.busy_logged = True
                        self.app.log(
                            f"Gamepad slot {index + 1}: '{candidate.name}' is present but could not be opened "
                            "-- another program (usually Steam) is using it; retrying"
                        )
                    with self._lock:
                        slot.status = "busy"
                    continue
                slot.instance_id = candidate.instance_id
                slot.device_name = candidate.name
                slot.busy_logged = False
                if not self._activate_slot(index, slot, candidate, opened[candidate.instance_id], profile):
                    slot.instance_id = None
                    continue
            claimed.add(slot.instance_id)

        watched_instances: set[int] = set()
        watch_targets: dict[WatchKey, int] = {}
        for key in watched:
            guid = key[0]
            device = self._device_for_watch(key, present, opened, configs)
            if device is None:
                continue
            if self._open_device(device, opened, now):
                watched_instances.add(device.instance_id)
                watch_targets[key] = device.instance_id
            else:
                busy.add(guid)
        self._watch_targets = watch_targets

        needed = claimed | watched_instances
        for instance_id in [iid for iid in opened if iid not in needed]:
            self._close_device(instance_id, opened)
        with self._lock:
            self._busy_guids = busy

    def _device_for_watch(
        self,
        key: WatchKey,
        present: dict[int, DeviceInfo],
        opened: dict[int, object],
        configs: list[tuple[bool, str, str]],
    ) -> DeviceInfo | None:
        """Which physical pad a test-dialog watch means.

        Without a slot index: any pad with that GUID, preferring one that's
        already open. With one, the pad THAT SLOT controls -- a GUID names a
        model, so two identical pads share it and picking "the first match"
        made every slot's Test show slot 1's pad:
        1. the pad the slot is bridging right now (exactly what feeds its
           virtual pad), else
        2. the pad it would get: of the same-model pads no other slot has
           bound, the one at this slot's rank among the lower slots that
           picked the same model and aren't bound yet -- the order the bridge
           itself hands identical pads out in (see the claim loop above).
           Slots that picked the same model but are still disabled count
           too, so two idle slots show two different pads instead of both
           showing the first."""
        guid, slot_index = key
        matches = [d for d in present.values() if d.guid == guid]
        if not matches:
            return None
        if slot_index is None or not (0 <= slot_index < len(self._slots)):
            return next((d for d in matches if d.instance_id in opened), matches[0])

        bound_id = self._slots[slot_index].instance_id
        bound = present.get(bound_id) if bound_id is not None else None
        if bound is not None and bound.guid == guid:
            return bound

        taken = {s.instance_id for i, s in enumerate(self._slots) if i != slot_index and s.instance_id is not None}
        free = [d for d in matches if d.instance_id not in taken]
        if not free:
            # Every pad of this model is bridged by other slots -- show one
            # of them rather than "disconnected" for a pad that's plugged in.
            return next((d for d in matches if d.instance_id in opened), matches[0])
        rank = sum(
            1
            for i in range(slot_index)
            if self._slots[i].instance_id is None and configs[i][1] == guid
        )
        return free[rank] if rank < len(free) else free[0]

    def _open_device(self, device: DeviceInfo, opened: dict[int, object], now: float) -> bool:
        if device.instance_id in opened:
            return True
        if device.instance_id in self._vanished:
            return False
        retry_at = self._open_retry_at.get(device.instance_id, 0.0)
        if now < retry_at:
            return False
        try:
            joystick = pygame.joystick.Joystick(device.index)
            if not joystick.get_init():
                joystick.init()
            if joystick.get_instance_id() != device.instance_id:
                # Device list moved under us since the scan -- try again
                # next tick with fresh indices rather than bridge the
                # wrong pad.
                joystick.quit()
                return False
        except Exception:
            self._open_retry_at[device.instance_id] = now + OPEN_RETRY_SECONDS
            if not self._still_listed(device.instance_id):
                # Confirmed live 2026-09-23: when SDL's Switch driver fails
                # its USB handshake (Steam talking to the same pad), SDL
                # drops the pad from its own list entirely (get_count() goes
                # 1 -> 0) and never re-adds it -- nothing was unplugged, so
                # no hot-plug event ever comes. Only re-initializing the
                # joystick subsystem re-enumerates it (4 of 4 recoveries in
                # the same test). Keep it listed as busy until then.
                self._vanished[device.instance_id] = device
                if self._reinit_at is None:
                    self._reinit_at = now + OPEN_RETRY_SECONDS
            return False
        self._open_retry_at.pop(device.instance_id, None)
        opened[device.instance_id] = joystick
        self._open_controller(device)
        return True

    def _init_controller_api(self) -> None:
        if not SDL_CONTROLLER_AVAILABLE:
            return
        try:
            sdl_controller.init()
        except Exception as exc:
            self.app.log(f"Gamepad bridge: SDL GameController API unavailable ({exc}) -- using raw button maps")

    def _open_controller(self, device: DeviceInfo) -> None:
        """Adds an SDL GameController handle on top of the already-open
        joystick when SDL knows this pad -- that's what gives any
        recognized gamepad the standard Xbox layout. Opening it is
        refcounted by SDL, so it shares the same underlying device."""
        if not SDL_CONTROLLER_AVAILABLE or device.instance_id in self._controllers:
            return
        try:
            if not sdl_controller.is_controller(device.index):
                return
            controller = sdl_controller.Controller(device.index)
            if controller.as_joystick().get_instance_id() != device.instance_id:
                controller.quit()
                return
        except Exception:
            return
        self._controllers[device.instance_id] = controller

    def _close_device(self, instance_id: int, opened: dict[int, object]) -> None:
        controller = self._controllers.pop(instance_id, None)
        if controller is not None:
            try:
                controller.quit()
            except Exception:
                pass
        joystick = opened.pop(instance_id, None)
        self._open_retry_at.pop(instance_id, None)
        if joystick is not None:
            try:
                joystick.quit()
            except Exception:
                pass

    def _still_listed(self, instance_id: int) -> bool:
        if self._api is not None:
            try:
                return any(d.instance_id == instance_id for d in self._api.scan())
            except Exception:
                return True
        return pygame.joystick.get_count() > 0

    def _reinit_joysticks(self, opened: dict[int, object]) -> None:
        """Re-initializes SDL's joystick subsystem so it re-enumerates a pad
        it dropped after a failed open (see _open_device). Closes every open
        pad first -- quitting the subsystem invalidates them -- and lets the
        normal per-tick logic reopen them under their new instance ids;
        virtual pads are kept, only neutralized for that moment."""
        if not self._reinit_logged:
            self._reinit_logged = True
            self.app.log("Gamepad bridge: re-scanning controllers after a failed open (another program is using one)")
        for slot in self._slots:
            if slot.instance_id is not None:
                slot.instance_id = None
                self._neutralize_pad(slot)
        for instance_id in list(opened):
            self._close_device(instance_id, opened)
        self._vanished.clear()
        self._open_retry_at.clear()
        self._reinit_at = None
        try:
            if SDL_CONTROLLER_AVAILABLE:
                sdl_controller.quit()
            pygame.joystick.quit()
            pygame.joystick.init()
            self._init_controller_api()
        except Exception as exc:
            self.app.log(f"Gamepad bridge: joystick re-init failed ({exc})")

    def _activate_slot(
        self, index: int, slot: SlotState, device: DeviceInfo, joystick, profile: str
    ) -> bool:
        if slot.pad is None:
            try:
                slot.pad = vg.VX360Gamepad()
            except Exception as exc:
                self.app.log(
                    f"Gamepad slot {index + 1}: virtual pad unavailable ({exc}) -- is ViGEmBus installed?"
                )
                with self._lock:
                    slot.status = "disconnected"
                return False
        controller = self._controllers.get(device.instance_id)
        if controller is not None and profile == PROFILE_AUTO:
            # Any pad SDL recognizes: standard Xbox layout, analog triggers.
            profile_name = PROFILE_STANDARD
            slot.mapper = lambda _joystick, pad, _c=controller: apply_mapped_state(pad, read_controller_state(_c))
        else:
            profile_name = self.resolve_profile(device.name, device.guid, profile)
            slot.mapper = _switch_pro_mapper if profile_name == PROFILE_SWITCH_PRO else _generic_mapper
        self._reinit_logged = False
        with self._lock:
            slot.status = "active"
        verb = "reconnected, bridging" if slot.was_connected else "bridging"
        slot.was_connected = True
        self.app.log(
            f"Gamepad slot {index + 1}: {verb} '{device.name}' as a virtual Xbox 360 controller "
            f"(profile: {profile_name})"
        )
        return True

    def _drive_slots(self, opened: dict[int, object]) -> None:
        for index, slot in enumerate(self._slots):
            if slot.instance_id is None or slot.pad is None or slot.mapper is None:
                continue
            joystick = opened.get(slot.instance_id)
            if joystick is None:
                continue
            try:
                slot.mapper(joystick, slot.pad)
                slot.pad.update()
            except Exception as exc:
                self.app.log(f"Gamepad slot {index + 1}: translation error: {exc}")

    def _publish_raw_states(self, opened: dict[int, object], now: float) -> None:
        with self._lock:
            watched = [k for k, seen in self._raw_watch.items() if now - seen < RAW_WATCH_TIMEOUT_SECONDS]
        for key in watched:
            # The device _sync_devices() just opened for this watch -- not
            # re-derived here from the GUID, which two identical pads share.
            instance_id = self._watch_targets.get(key)
            joystick = opened.get(instance_id) if instance_id is not None else None
            if joystick is None:
                with self._lock:
                    self._raw_states.pop(key, None)
                continue
            try:
                state = {
                    "buttons": [bool(joystick.get_button(i)) for i in range(joystick.get_numbuttons())],
                    "axes": [joystick.get_axis(i) for i in range(joystick.get_numaxes())],
                    "hats": [joystick.get_hat(i) for i in range(joystick.get_numhats())],
                }
                controller = self._controllers.get(instance_id)
                if controller is not None:
                    # What the bridge actually sends for this pad -- the
                    # test dialog shows it instead of re-deriving it from
                    # the raw indices.
                    state["mapped"] = read_controller_state(controller)
            except Exception:
                continue
            with self._lock:
                self._raw_states[key] = state

    @staticmethod
    def _neutralize_pad(slot: SlotState) -> None:
        if slot.pad is None:
            return
        try:
            slot.pad.reset()
            slot.pad.update()
        except Exception:
            pass

    def _release_pad(self, index: int, slot: SlotState) -> None:
        if slot.pad is None:
            with self._lock:
                slot.status = "disconnected"
            return
        self._neutralize_pad(slot)
        # vgamepad unplugs the virtual device when the VX360Gamepad object
        # is garbage-collected -- it has no explicit close().
        slot.pad = None
        slot.mapper = None
        slot.was_connected = False
        slot.busy_logged = False
        with self._lock:
            slot.status = "disconnected"
        self.app.log(f"Gamepad slot {index + 1}: bridge stopped")

    def _shutdown_sdl_thread(self, opened: dict[int, object]) -> None:
        for index, slot in enumerate(self._slots):
            slot.instance_id = None
            self._release_pad(index, slot)
        for instance_id in list(opened):
            self._close_device(instance_id, opened)
        try:
            if SDL_CONTROLLER_AVAILABLE:
                sdl_controller.quit()
            pygame.joystick.quit()
            pygame.display.quit()
        except Exception:
            pass
        with self._lock:
            self._devices = []
            self._raw_states = {}
            self._watch_targets = {}
            self._busy_guids = set()

def _apply_dpad(pad: "vg.VX360Gamepad", hat_x: int, hat_y: int) -> None:
    dpad_state = {
        vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_UP: hat_y > 0,
        vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_DOWN: hat_y < 0,
        vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_LEFT: hat_x < 0,
        vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_RIGHT: hat_x > 0,
    }
    for button, pressed in dpad_state.items():
        if pressed:
            pad.press_button(button=button)
        else:
            pad.release_button(button=button)


def _apply_sticks(pad: "vg.VX360Gamepad", joystick) -> None:
    axis_count = joystick.get_numaxes()
    lx = joystick.get_axis(0) if axis_count > 0 else 0.0
    ly = joystick.get_axis(1) if axis_count > 1 else 0.0
    rx = joystick.get_axis(2) if axis_count > 2 else 0.0
    ry = joystick.get_axis(3) if axis_count > 3 else 0.0
    # SDL's Y axis reports "up" as negative; XInput's virtual stick wants
    # "up" as positive -- flip Y here rather than baking the sign into the
    # generic clamp helper.
    pad.left_joystick_float(x_value_float=_clamp(lx), y_value_float=_clamp(-ly))
    pad.right_joystick_float(x_value_float=_clamp(rx), y_value_float=_clamp(-ry))


def _apply_buttons(pad: "vg.VX360Gamepad", joystick, button_map: dict[int, str]) -> None:
    button_count = joystick.get_numbuttons()
    for raw_index, xbox_name in button_map.items():
        if raw_index >= button_count:
            continue
        xbox_button = getattr(vg.XUSB_BUTTON, xbox_name)
        if joystick.get_button(raw_index):
            pad.press_button(button=xbox_button)
        else:
            pad.release_button(button=xbox_button)
    if joystick.get_numhats() > 0:
        hat_x, hat_y = joystick.get_hat(0)
        _apply_dpad(pad, hat_x, hat_y)


def _switch_pro_mapper(joystick, pad: "vg.VX360Gamepad") -> None:
    _apply_buttons(pad, joystick, SWITCH_PRO_BUTTON_MAP)
    _apply_sticks(pad, joystick)
    button_count = joystick.get_numbuttons()
    zl = 1.0 if button_count > SWITCH_PRO_ZL_INDEX and joystick.get_button(SWITCH_PRO_ZL_INDEX) else 0.0
    zr = 1.0 if button_count > SWITCH_PRO_ZR_INDEX and joystick.get_button(SWITCH_PRO_ZR_INDEX) else 0.0
    pad.left_trigger_float(value_float=zl)
    pad.right_trigger_float(value_float=zr)


def _generic_mapper(joystick, pad: "vg.VX360Gamepad") -> None:
    _apply_buttons(pad, joystick, GENERIC_BUTTON_MAP)
    _apply_sticks(pad, joystick)
    pad.left_trigger_float(value_float=0.0)
    pad.right_trigger_float(value_float=0.0)


def resolve_mapped_state(raw: dict, profile_name: str) -> dict:
    """Pure function: computes what the translated Xbox output WOULD look
    like for a given raw joystick snapshot (GamepadBridgeRuntime.
    read_raw_state()'s return shape) under a given resolved profile --
    mirrors _switch_pro_mapper/_generic_mapper's own logic exactly, but
    returns plain data instead of driving a real vg.VX360Gamepad(). This
    means GamepadTestDialog can show "what FIFA/Windows would see via the
    virtual pad" without needing ViGEmBus installed/connectable, and
    without contending with a slot's own live bridge thread for the same
    virtual pad handle if that slot happens to already be enabled."""
    buttons = raw.get("buttons", [])
    axes = raw.get("axes", [])
    hats = raw.get("hats", [])
    button_map = SWITCH_PRO_BUTTON_MAP if profile_name == PROFILE_SWITCH_PRO else GENERIC_BUTTON_MAP
    pressed: dict[str, bool] = {name: False for name in _ALL_XUSB_BUTTON_NAMES}
    for raw_index, xbox_name in button_map.items():
        if raw_index < len(buttons):
            pressed[xbox_name] = buttons[raw_index]
    if hats:
        hat_x, hat_y = hats[0]
        pressed["XUSB_GAMEPAD_DPAD_UP"] = hat_y > 0
        pressed["XUSB_GAMEPAD_DPAD_DOWN"] = hat_y < 0
        pressed["XUSB_GAMEPAD_DPAD_LEFT"] = hat_x < 0
        pressed["XUSB_GAMEPAD_DPAD_RIGHT"] = hat_x > 0
    lx = axes[0] if len(axes) > 0 else 0.0
    ly = axes[1] if len(axes) > 1 else 0.0
    rx = axes[2] if len(axes) > 2 else 0.0
    ry = axes[3] if len(axes) > 3 else 0.0
    left_trigger = right_trigger = 0.0
    if profile_name == PROFILE_SWITCH_PRO:
        left_trigger = 1.0 if len(buttons) > SWITCH_PRO_ZL_INDEX and buttons[SWITCH_PRO_ZL_INDEX] else 0.0
        right_trigger = 1.0 if len(buttons) > SWITCH_PRO_ZR_INDEX and buttons[SWITCH_PRO_ZR_INDEX] else 0.0
    return {
        "buttons": pressed,
        "left_stick": (_clamp(lx), _clamp(-ly)),
        "right_stick": (_clamp(rx), _clamp(-ry)),
        "left_trigger": left_trigger,
        "right_trigger": right_trigger,
    }
