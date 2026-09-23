from __future__ import annotations

import json
import sys
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from server16_py import gamepad_bridge_runtime as gbr
from server16_py.settings_store import SettingsStore


# The XUSB_BUTTON names referenced by SWITCH_PRO_BUTTON_MAP / GENERIC_BUTTON_MAP
# / _apply_dpad, as a flat name->name namespace -- enough to exercise the
# mapping logic without requiring the real (Windows-driver-backed) vgamepad
# package to be installed in the test environment.
_XUSB_BUTTON_NAMES = (
    "XUSB_GAMEPAD_DPAD_UP",
    "XUSB_GAMEPAD_DPAD_DOWN",
    "XUSB_GAMEPAD_DPAD_LEFT",
    "XUSB_GAMEPAD_DPAD_RIGHT",
    "XUSB_GAMEPAD_START",
    "XUSB_GAMEPAD_BACK",
    "XUSB_GAMEPAD_LEFT_THUMB",
    "XUSB_GAMEPAD_RIGHT_THUMB",
    "XUSB_GAMEPAD_LEFT_SHOULDER",
    "XUSB_GAMEPAD_RIGHT_SHOULDER",
    "XUSB_GAMEPAD_A",
    "XUSB_GAMEPAD_B",
    "XUSB_GAMEPAD_X",
    "XUSB_GAMEPAD_Y",
)


class FakeJoystick:
    def __init__(self, buttons=(), axes=(), hats=(), name="Fake Pad", guid="fake-guid"):
        self._buttons = list(buttons)
        self._axes = list(axes)
        self._hats = list(hats)
        self._name = name
        self._guid = guid

    def get_numbuttons(self) -> int:
        return len(self._buttons)

    def get_button(self, index: int) -> bool:
        return bool(self._buttons[index])

    def get_numaxes(self) -> int:
        return len(self._axes)

    def get_axis(self, index: int) -> float:
        return self._axes[index]

    def get_numhats(self) -> int:
        return len(self._hats)

    def get_hat(self, index: int):
        return self._hats[index]

    def get_name(self) -> str:
        return self._name

    def get_guid(self) -> str:
        return self._guid

    def get_init(self) -> bool:
        return True

    def init(self) -> None:
        pass


class FakePad:
    def __init__(self) -> None:
        self.pressed: set[str] = set()
        self.left_stick = (0.0, 0.0)
        self.right_stick = (0.0, 0.0)
        self.left_trigger_value = 0.0
        self.right_trigger_value = 0.0

    def press_button(self, button: str) -> None:
        self.pressed.add(button)

    def release_button(self, button: str) -> None:
        self.pressed.discard(button)

    def left_joystick_float(self, x_value_float: float, y_value_float: float) -> None:
        self.left_stick = (x_value_float, y_value_float)

    def right_joystick_float(self, x_value_float: float, y_value_float: float) -> None:
        self.right_stick = (x_value_float, y_value_float)

    def left_trigger_float(self, value_float: float) -> None:
        self.left_trigger_value = value_float

    def right_trigger_float(self, value_float: float) -> None:
        self.right_trigger_value = value_float


class GamepadBridgeMapperTests(unittest.TestCase):
    """Exercises the pure button/axis/hat translation logic with fake
    joystick/pad objects, monkeypatching module-level `vg` so this runs
    without the real (Windows-driver-backed) vgamepad package installed --
    see FakePad/_XUSB_BUTTON_NAMES above."""

    def setUp(self) -> None:
        self._original_vg = getattr(gbr, "vg", None)
        gbr.vg = SimpleNamespace(XUSB_BUTTON=SimpleNamespace(**{n: n for n in _XUSB_BUTTON_NAMES}))

    def tearDown(self) -> None:
        gbr.vg = self._original_vg

    def test_switch_pro_mapper_swaps_face_buttons_by_position(self) -> None:
        # raw index 0 = physical B (bottom) -> Xbox A (bottom)
        joystick = FakeJoystick(buttons=[True, False, False, False])
        pad = FakePad()
        gbr._switch_pro_mapper(joystick, pad)
        self.assertIn("XUSB_GAMEPAD_A", pad.pressed)
        self.assertNotIn("XUSB_GAMEPAD_B", pad.pressed)

        # raw index 1 = physical A (right) -> Xbox B (right)
        joystick = FakeJoystick(buttons=[False, True, False, False])
        pad = FakePad()
        gbr._switch_pro_mapper(joystick, pad)
        self.assertIn("XUSB_GAMEPAD_B", pad.pressed)
        self.assertNotIn("XUSB_GAMEPAD_A", pad.pressed)

        # raw index 2 = physical Y (left) -> Xbox X (left)
        joystick = FakeJoystick(buttons=[False, False, True, False])
        pad = FakePad()
        gbr._switch_pro_mapper(joystick, pad)
        self.assertIn("XUSB_GAMEPAD_X", pad.pressed)

        # raw index 3 = physical X (top) -> Xbox Y (top)
        joystick = FakeJoystick(buttons=[False, False, False, True])
        pad = FakePad()
        gbr._switch_pro_mapper(joystick, pad)
        self.assertIn("XUSB_GAMEPAD_Y", pad.pressed)

    def test_switch_pro_mapper_zl_zr_drive_triggers_not_buttons(self) -> None:
        buttons = [False] * 8
        buttons[gbr.SWITCH_PRO_ZL_INDEX] = True
        buttons[gbr.SWITCH_PRO_ZR_INDEX] = True
        joystick = FakeJoystick(buttons=buttons)
        pad = FakePad()
        gbr._switch_pro_mapper(joystick, pad)
        self.assertEqual(pad.left_trigger_value, 1.0)
        self.assertEqual(pad.right_trigger_value, 1.0)
        self.assertFalse(pad.pressed)  # ZL/ZR must never show up as a button press

    def test_dpad_hat_maps_to_dpad_buttons(self) -> None:
        joystick = FakeJoystick(buttons=[], hats=[(0, 1)])  # up
        pad = FakePad()
        gbr._apply_buttons(pad, joystick, gbr.SWITCH_PRO_BUTTON_MAP)
        self.assertIn("XUSB_GAMEPAD_DPAD_UP", pad.pressed)
        self.assertNotIn("XUSB_GAMEPAD_DPAD_DOWN", pad.pressed)

        joystick = FakeJoystick(buttons=[], hats=[(-1, 0)])  # left
        pad = FakePad()
        gbr._apply_buttons(pad, joystick, gbr.SWITCH_PRO_BUTTON_MAP)
        self.assertIn("XUSB_GAMEPAD_DPAD_LEFT", pad.pressed)

    def test_sticks_invert_sdl_y_axis_for_xinput_convention(self) -> None:
        # SDL reports "up" as -1.0 on the Y axis; XInput's virtual stick
        # wants "up" as +1.0.
        joystick = FakeJoystick(axes=[0.5, -1.0, -0.25, 1.0])
        pad = FakePad()
        gbr._apply_sticks(pad, joystick)
        self.assertEqual(pad.left_stick, (0.5, 1.0))
        self.assertEqual(pad.right_stick, (-0.25, -1.0))

    def test_sticks_are_clamped_to_valid_range(self) -> None:
        joystick = FakeJoystick(axes=[1.5, -1.5])
        pad = FakePad()
        gbr._apply_sticks(pad, joystick)
        self.assertEqual(pad.left_stick, (1.0, 1.0))

    def test_generic_mapper_is_a_straight_positional_passthrough(self) -> None:
        # No position swap for an unrecognized pad -- raw index 0 -> Xbox A directly.
        joystick = FakeJoystick(buttons=[True, False])
        pad = FakePad()
        gbr._generic_mapper(joystick, pad)
        self.assertIn("XUSB_GAMEPAD_A", pad.pressed)
        self.assertEqual(pad.left_trigger_value, 0.0)
        self.assertEqual(pad.right_trigger_value, 0.0)


class ResolveMappedStateTests(unittest.TestCase):
    """resolve_mapped_state() is the pure-data twin of _switch_pro_mapper/
    _generic_mapper used by GamepadTestDialog to show "what FIFA would see
    via the virtual pad" without needing a real vg.VX360Gamepad() -- must
    stay in lockstep with the real mappers' own logic."""

    def test_switch_pro_face_button_swap_matches_the_real_mapper(self) -> None:
        raw = {"buttons": [True, False, False, False], "axes": [], "hats": []}
        mapped = gbr.resolve_mapped_state(raw, gbr.PROFILE_SWITCH_PRO)
        self.assertTrue(mapped["buttons"]["XUSB_GAMEPAD_A"])
        self.assertFalse(mapped["buttons"]["XUSB_GAMEPAD_B"])

    def test_switch_pro_zl_zr_drive_triggers_not_buttons(self) -> None:
        buttons = [False] * 8
        buttons[gbr.SWITCH_PRO_ZL_INDEX] = True
        buttons[gbr.SWITCH_PRO_ZR_INDEX] = True
        mapped = gbr.resolve_mapped_state({"buttons": buttons, "axes": [], "hats": []}, gbr.PROFILE_SWITCH_PRO)
        self.assertEqual(mapped["left_trigger"], 1.0)
        self.assertEqual(mapped["right_trigger"], 1.0)
        self.assertFalse(any(mapped["buttons"].values()))

    def test_generic_profile_never_drives_triggers(self) -> None:
        buttons = [False] * 8
        buttons[gbr.SWITCH_PRO_ZL_INDEX] = True
        mapped = gbr.resolve_mapped_state({"buttons": buttons, "axes": [], "hats": []}, gbr.PROFILE_GENERIC)
        self.assertEqual(mapped["left_trigger"], 0.0)
        self.assertEqual(mapped["right_trigger"], 0.0)

    def test_dpad_hat_maps_to_dpad_directions(self) -> None:
        mapped = gbr.resolve_mapped_state({"buttons": [], "axes": [], "hats": [(0, 1)]}, gbr.PROFILE_GENERIC)
        self.assertTrue(mapped["buttons"]["XUSB_GAMEPAD_DPAD_UP"])
        self.assertFalse(mapped["buttons"]["XUSB_GAMEPAD_DPAD_DOWN"])

    def test_sticks_invert_sdl_y_axis_and_clamp(self) -> None:
        mapped = gbr.resolve_mapped_state({"buttons": [], "axes": [1.5, -1.0, -0.25, 1.0], "hats": []}, gbr.PROFILE_GENERIC)
        self.assertEqual(mapped["left_stick"], (1.0, 1.0))
        self.assertEqual(mapped["right_stick"], (-0.25, -1.0))

    def test_missing_axes_and_hats_default_to_neutral(self) -> None:
        mapped = gbr.resolve_mapped_state({"buttons": [], "axes": [], "hats": []}, gbr.PROFILE_GENERIC)
        self.assertEqual(mapped["left_stick"], (0.0, 0.0))
        self.assertEqual(mapped["right_stick"], (0.0, 0.0))
        self.assertFalse(any(mapped["buttons"].values()))



class StandardControllerMappingTests(unittest.TestCase):
    """Any pad SDL's GameController database recognizes is translated
    through read_controller_state()/apply_mapped_state() -- SDL already
    reports the Xbox layout (A = bottom face button), so this must be a
    1:1 pass-through with analog triggers and Y flipped to XInput's
    up-positive convention."""

    _CONSTANTS = SimpleNamespace(
        **{name: name for name, _x in gbr._CONTROLLER_BUTTON_MAP},
        CONTROLLER_AXIS_LEFTX="LX",
        CONTROLLER_AXIS_LEFTY="LY",
        CONTROLLER_AXIS_RIGHTX="RX",
        CONTROLLER_AXIS_RIGHTY="RY",
        CONTROLLER_AXIS_TRIGGERLEFT="LT",
        CONTROLLER_AXIS_TRIGGERRIGHT="RT",
    )

    class FakeController:
        def __init__(self, pressed=(), axes=None):
            self.pressed = set(pressed)
            self.axes = axes or {}

        def get_button(self, name):
            return name in self.pressed

        def get_axis(self, name):
            return self.axes.get(name, 0)

    def test_buttons_pass_through_one_to_one(self) -> None:
        ctrl = self.FakeController(pressed={"CONTROLLER_BUTTON_A", "CONTROLLER_BUTTON_GUIDE", "CONTROLLER_BUTTON_DPAD_UP"})
        state = gbr.read_controller_state(ctrl, self._CONSTANTS)
        self.assertTrue(state["buttons"]["XUSB_GAMEPAD_A"])
        self.assertTrue(state["buttons"]["XUSB_GAMEPAD_GUIDE"])
        self.assertTrue(state["buttons"]["XUSB_GAMEPAD_DPAD_UP"])
        self.assertFalse(state["buttons"]["XUSB_GAMEPAD_B"])

    def test_sticks_are_normalized_and_y_flipped(self) -> None:
        ctrl = self.FakeController(axes={"LX": 32767, "LY": -32768, "RX": -16384, "RY": 32767})
        state = gbr.read_controller_state(ctrl, self._CONSTANTS)
        self.assertEqual(state["left_stick"], (1.0, 1.0))
        self.assertAlmostEqual(state["right_stick"][0], -0.5, places=3)
        self.assertEqual(state["right_stick"][1], -1.0)

    def test_triggers_are_analog_zero_to_one(self) -> None:
        ctrl = self.FakeController(axes={"LT": 16384, "RT": 32767})
        state = gbr.read_controller_state(ctrl, self._CONSTANTS)
        self.assertAlmostEqual(state["left_trigger"], 0.5, places=3)
        self.assertEqual(state["right_trigger"], 1.0)

    def test_apply_mapped_state_drives_the_virtual_pad(self) -> None:
        original_vg = getattr(gbr, "vg", None)
        gbr.vg = SimpleNamespace(XUSB_BUTTON=SimpleNamespace(**{n: n for n in _XUSB_BUTTON_NAMES}, XUSB_GAMEPAD_GUIDE="XUSB_GAMEPAD_GUIDE"))
        try:
            pad = FakePad()
            state = {
                "buttons": {"XUSB_GAMEPAD_A": True, "XUSB_GAMEPAD_B": False},
                "left_stick": (0.5, -0.5),
                "right_stick": (0.0, 1.0),
                "left_trigger": 0.25,
                "right_trigger": 1.0,
            }
            gbr.apply_mapped_state(pad, state)
        finally:
            gbr.vg = original_vg
        self.assertEqual(pad.pressed, {"XUSB_GAMEPAD_A"})
        self.assertEqual(pad.left_stick, (0.5, -0.5))
        self.assertEqual(pad.right_stick, (0.0, 1.0))
        self.assertEqual(pad.left_trigger_value, 0.25)
        self.assertEqual(pad.right_trigger_value, 1.0)

    def test_every_mapped_xbox_button_exists_in_vgamepad(self) -> None:
        if not gbr.VGAMEPAD_AVAILABLE:
            self.skipTest("vgamepad not importable here")
        for _sdl, xusb in gbr._CONTROLLER_BUTTON_MAP:
            self.assertTrue(hasattr(gbr.vg.XUSB_BUTTON, xusb), xusb)

class ReadRawStateTests(unittest.TestCase):
    """read_raw_state()/is_device_busy() no longer touch pygame/SDL
    directly -- all SDL access moved onto one dedicated thread
    (_sdl_thread_main) after several pygame calls from multiple threads
    around a device hot-plug crashed the whole app natively (no traceback,
    just the process ending -- see gamepad_bridge_runtime.py's class
    docstring). The Tk thread only reads/writes the snapshots that thread
    publishes under self._lock, and is keyed by (device GUID, slot index)
    rather than SDL instance id, since instance ids change on every
    reconnect -- and by slot on top of the GUID, since a GUID names a model
    and two identical pads share it."""

    def _runtime(self) -> gbr.GamepadBridgeRuntime:
        runtime = gbr.GamepadBridgeRuntime.__new__(gbr.GamepadBridgeRuntime)
        runtime._lock = threading.Lock()
        runtime._raw_states = {}
        runtime._raw_watch = {}
        runtime._watch_targets = {}
        runtime._busy_guids = set()
        return runtime

    def test_returns_none_when_sdl_thread_unavailable(self) -> None:
        runtime = self._runtime()
        runtime._ensure_thread = lambda: False
        self.assertIsNone(runtime.read_raw_state("guid-1"))

    def test_returns_the_sdl_threads_published_snapshot(self) -> None:
        runtime = self._runtime()
        runtime._ensure_thread = lambda: True
        runtime._raw_states[("guid-1", None)] = {"buttons": [True, False], "axes": [0.5], "hats": [(1, 0)]}
        state = runtime.read_raw_state("guid-1")
        self.assertEqual(state, {"buttons": [True, False], "axes": [0.5], "hats": [(1, 0)]})

    def test_asks_the_sdl_thread_to_keep_watching_the_device(self) -> None:
        # No enabled slot may be using this device -- read_raw_state()
        # (called by GamepadTestDialog) is what tells the SDL thread to
        # open/keep-open and sample it anyway.
        runtime = self._runtime()
        runtime._ensure_thread = lambda: True
        runtime.read_raw_state("guid-1")
        self.assertIn(("guid-1", None), runtime._raw_watch)

    def test_snapshots_are_kept_per_slot_for_the_same_guid(self) -> None:
        runtime = self._runtime()
        runtime._ensure_thread = lambda: True
        runtime._raw_states[("guid-1", 0)] = {"buttons": [True], "axes": [], "hats": []}
        runtime._raw_states[("guid-1", 1)] = {"buttons": [False], "axes": [], "hats": []}
        self.assertEqual(runtime.read_raw_state("guid-1", 0)["buttons"], [True])
        self.assertEqual(runtime.read_raw_state("guid-1", 1)["buttons"], [False])
        self.assertIn(("guid-1", 0), runtime._raw_watch)
        self.assertIn(("guid-1", 1), runtime._raw_watch)

    def test_returns_none_for_a_device_not_yet_published(self) -> None:
        runtime = self._runtime()
        runtime._ensure_thread = lambda: True
        self.assertIsNone(runtime.read_raw_state("guid-unknown"))

    def test_is_device_busy_reads_the_published_busy_set(self) -> None:
        runtime = self._runtime()
        runtime._busy_guids = {"guid-1"}
        self.assertTrue(runtime.is_device_busy("guid-1"))
        self.assertFalse(runtime.is_device_busy("guid-2"))

    def test_describe_raw_state_falls_back_when_read_raw_state_returns_none(self) -> None:
        runtime = gbr.GamepadBridgeRuntime.__new__(gbr.GamepadBridgeRuntime)
        runtime.read_raw_state = lambda device_guid: None
        self.assertEqual(runtime.describe_raw_state("guid-1"), "pygame joystick subsystem unavailable")


class IdenticalPadsWatchTests(unittest.TestCase):
    """Two pads of the same model share one SDL GUID. Every slot's Test
    button used to resolve "the pad with this GUID" to the first one, so all
    the dialogs showed slot 1's controller (reported live 2026-09-24). A
    slot's watch now resolves to the pad THAT slot controls."""

    GUID = "030056fb7e0500000920000010026803"

    def _runtime(self, slots: list[gbr.SlotState]) -> gbr.GamepadBridgeRuntime:
        runtime = gbr.GamepadBridgeRuntime.__new__(gbr.GamepadBridgeRuntime)
        runtime._lock = threading.Lock()
        runtime._slots = slots
        runtime._raw_states = {}
        runtime._raw_watch = {}
        runtime._watch_targets = {}
        runtime._busy_guids = set()
        runtime._controllers = {}
        return runtime

    @staticmethod
    def _slot(guid: str = "", instance_id: int | None = None, enabled: bool = True) -> gbr.SlotState:
        return gbr.SlotState(enabled=enabled, device_guid=guid, instance_id=instance_id)

    @staticmethod
    def _configs(slots: list[gbr.SlotState]) -> list[tuple[bool, str, str]]:
        return [(s.enabled, s.device_guid, s.profile) for s in slots]

    def _pads(self, *instance_ids: int) -> dict[int, gbr.DeviceInfo]:
        return {
            iid: gbr.DeviceInfo(index=n, name="Pro Controller", guid=self.GUID, instance_id=iid)
            for n, iid in enumerate(instance_ids)
        }

    def _resolve(self, runtime, slot_index, present, opened=None):
        key = (self.GUID, slot_index)
        return runtime._device_for_watch(key, present, opened or {}, self._configs(runtime._slots))

    def test_each_bridged_slot_resolves_to_its_own_pad(self) -> None:
        runtime = self._runtime([self._slot(self.GUID, 11), self._slot(self.GUID, 12)])
        present = self._pads(11, 12)
        self.assertEqual(self._resolve(runtime, 0, present).instance_id, 11)
        self.assertEqual(self._resolve(runtime, 1, present).instance_id, 12)

    def test_slot_binding_wins_even_when_the_other_pad_is_the_one_already_open(self) -> None:
        runtime = self._runtime([self._slot(self.GUID, 11), self._slot(self.GUID, 12)])
        present = self._pads(11, 12)
        # Only pad 11 is open (e.g. slot 2's pad is mid-reconnect) -- slot 2
        # must still mean pad 12, not fall back to the open one.
        self.assertEqual(self._resolve(runtime, 1, present, opened={11: object()}).instance_id, 12)

    def test_unbound_slot_gets_a_pad_no_other_slot_has(self) -> None:
        runtime = self._runtime([self._slot(self.GUID, 11), self._slot(self.GUID, None, enabled=False)])
        present = self._pads(11, 12)
        self.assertEqual(self._resolve(runtime, 1, present).instance_id, 12)

    def test_idle_slots_sharing_a_model_show_different_pads_in_slot_order(self) -> None:
        runtime = self._runtime(
            [self._slot(self.GUID, None, enabled=False), self._slot(self.GUID, None, enabled=False)]
        )
        present = self._pads(11, 12)
        self.assertEqual(self._resolve(runtime, 0, present).instance_id, 11)
        self.assertEqual(self._resolve(runtime, 1, present).instance_id, 12)

    def test_falls_back_to_the_pad_in_use_when_there_is_only_one(self) -> None:
        # Slot 2 picked the same (single) pad slot 1 already bridges -- Test
        # still shows that pad instead of a false "disconnected".
        runtime = self._runtime([self._slot(self.GUID, 11), self._slot(self.GUID, None, enabled=False)])
        present = self._pads(11)
        self.assertEqual(self._resolve(runtime, 1, present).instance_id, 11)

    def test_unplugged_pad_resolves_to_nothing(self) -> None:
        runtime = self._runtime([self._slot(self.GUID, None)])
        self.assertIsNone(self._resolve(runtime, 0, {}))

    def test_without_a_slot_index_prefers_an_already_open_pad(self) -> None:
        runtime = self._runtime([self._slot(), self._slot()])
        present = self._pads(11, 12)
        self.assertEqual(self._resolve(runtime, None, present, opened={12: object()}).instance_id, 12)
        self.assertEqual(self._resolve(runtime, None, present).instance_id, 11)

    def test_sync_and_publish_show_each_slots_own_pad_end_to_end(self) -> None:
        slots = [self._slot(self.GUID, 11), self._slot(self.GUID, 12)]
        runtime = self._runtime(slots)
        present = self._pads(11, 12)
        joysticks = {
            11: FakeJoystick(buttons=[True, False], axes=[0.0], hats=[(0, 0)]),
            12: FakeJoystick(buttons=[False, True], axes=[0.0], hats=[(0, 0)]),
        }
        runtime._open_device = lambda device, opened, now: opened.setdefault(
            device.instance_id, joysticks[device.instance_id]
        ) is not None
        runtime._release_pad = lambda index, slot: None
        now = 100.0
        runtime._raw_watch = {(self.GUID, 0): now, (self.GUID, 1): now}
        opened: dict[int, object] = {}

        runtime._sync_devices(present, opened, now)
        runtime._publish_raw_states(opened, now)

        self.assertEqual(runtime._raw_states[(self.GUID, 0)]["buttons"], [True, False])
        self.assertEqual(runtime._raw_states[(self.GUID, 1)]["buttons"], [False, True])


class ResolveProfileTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runtime = gbr.GamepadBridgeRuntime.__new__(gbr.GamepadBridgeRuntime)

    def test_detects_switch_pro_controller_by_name(self) -> None:
        self.assertEqual(
            self.runtime.resolve_profile("Nintendo Switch Pro Controller", "guid"), gbr.PROFILE_SWITCH_PRO
        )
        self.assertEqual(self.runtime.resolve_profile("pro controller", "guid"), gbr.PROFILE_SWITCH_PRO)

    def test_unrecognized_name_falls_back_to_generic(self) -> None:
        self.assertEqual(self.runtime.resolve_profile("Some Random USB Gamepad", "guid"), gbr.PROFILE_GENERIC)

    def test_explicit_override_wins_over_name_detection(self) -> None:
        self.assertEqual(
            self.runtime.resolve_profile("Nintendo Switch Pro Controller", "guid", override=gbr.PROFILE_GENERIC),
            gbr.PROFILE_GENERIC,
        )


class IsVigembusInstalledTests(unittest.TestCase):
    """Regression coverage for a real live bug: an earlier version of this
    method constructed (and immediately destroyed) a real vg.VX360Gamepad()
    on every call, which plugs and unplugs an actual virtual USB/XInput
    device on the bus each time -- audibly triggering Windows' device
    connected/disconnected sound repeatedly, including on every Gamepads tab
    visit and language switch. It must be a pure registry read instead."""

    def setUp(self) -> None:
        self.runtime = gbr.GamepadBridgeRuntime.__new__(gbr.GamepadBridgeRuntime)

    def test_never_constructs_a_virtual_pad(self) -> None:
        original_vg = getattr(gbr, "vg", None)

        class ExplodingVX360Gamepad:
            def __init__(self):
                raise AssertionError("is_vigembus_installed() must not construct a VX360Gamepad")

        gbr.vg = SimpleNamespace(VX360Gamepad=ExplodingVX360Gamepad)
        try:
            # Must not raise, regardless of the real result on this machine.
            self.runtime.is_vigembus_installed()
        finally:
            gbr.vg = original_vg


class FindVigembusInstallerTests(unittest.TestCase):
    """Regression coverage for the exact bug a live placement of the real,
    current ViGEmBus download (a combined *.exe* bootstrapper, not the older
    per-arch *.msi*) exposed: discovery must match by extension, not a
    hardcoded legacy filename."""

    @staticmethod
    def _make_runtime(base_dir: Path) -> gbr.GamepadBridgeRuntime:
        runtime = gbr.GamepadBridgeRuntime.__new__(gbr.GamepadBridgeRuntime)
        runtime.app = SimpleNamespace(base_dir=base_dir)
        return runtime

    def test_finds_the_current_combined_exe_bootstrapper(self) -> None:
        with TemporaryDirectory() as tmp:
            base = Path(tmp)
            vigembus_dir = base / "bin" / "ViGEmBus"
            vigembus_dir.mkdir(parents=True)
            exe_path = vigembus_dir / "ViGEmBus_1.22.0_x64_x86_arm64.exe"
            exe_path.write_bytes(b"")
            self.assertEqual(self._make_runtime(base).find_vigembus_installer(), exe_path)

    def test_finds_a_legacy_msi(self) -> None:
        with TemporaryDirectory() as tmp:
            base = Path(tmp)
            vigembus_dir = base / "bin" / "ViGEmBus"
            vigembus_dir.mkdir(parents=True)
            msi_path = vigembus_dir / "ViGEmBusSetup_x64.msi"
            msi_path.write_bytes(b"")
            self.assertEqual(self._make_runtime(base).find_vigembus_installer(), msi_path)

    def test_prefers_exe_over_msi_when_both_present(self) -> None:
        with TemporaryDirectory() as tmp:
            base = Path(tmp)
            vigembus_dir = base / "bin" / "ViGEmBus"
            vigembus_dir.mkdir(parents=True)
            (vigembus_dir / "ViGEmBusSetup_x64.msi").write_bytes(b"")
            exe_path = vigembus_dir / "ViGEmBus_1.22.0_x64_x86_arm64.exe"
            exe_path.write_bytes(b"")
            self.assertEqual(self._make_runtime(base).find_vigembus_installer(), exe_path)

    @unittest.skipUnless(gbr.VGAMEPAD_PACKAGE_PRESENT, "vgamepad package not installed")
    def test_falls_back_to_vgamepads_own_bundled_installer_when_bin_is_empty(self) -> None:
        # vgamepad vendors ViGEmBusSetup_x64.msi/_x86.msi inside its own
        # package (win/vigem/install/<arch>/) -- bin/ViGEmBus/ is only an
        # override, so an empty/missing bin/ViGEmBus/ must still resolve to
        # something real, not None, whenever the vgamepad *package* is
        # installed -- gated on VGAMEPAD_PACKAGE_PRESENT, not
        # VGAMEPAD_AVAILABLE: this must keep working even when vgamepad
        # fails to fully import (ViGEmBus missing/not connectable), since
        # that's exactly the state a real machine was in when this was
        # written (see IsVigembusInstalledTests' docstring) -- the one
        # moment the Install Driver button most needs this to work.
        with TemporaryDirectory() as tmp:
            runtime = self._make_runtime(Path(tmp))
            found = runtime.find_vigembus_installer()
            self.assertIsNotNone(found)
            self.assertTrue(found.exists())
            self.assertEqual(found.suffix.lower(), ".msi")

    @unittest.skipUnless(gbr.VGAMEPAD_PACKAGE_PRESENT, "vgamepad package not installed")
    def test_bundled_installer_lookup_never_touches_vg_when_import_failed(self) -> None:
        """Regression test for the actual live crash: right after ViGEmBus
        is uninstalled, `import vgamepad` itself raises (module-level
        VBus-connect side effect -- see the import guard docstring at the
        top of gamepad_bridge_runtime.py), so VGAMEPAD_AVAILABLE is False
        and `vg` was never bound. _vgamepad_package_dir() must locate the
        package via import metadata only (importlib.util.find_spec) in that
        state, never by touching the (possibly-unbound) `vg` name."""
        original_available = gbr.VGAMEPAD_AVAILABLE
        gbr.VGAMEPAD_AVAILABLE = False
        try:
            with TemporaryDirectory() as tmp:
                runtime = self._make_runtime(Path(tmp))
                found = runtime.find_vigembus_installer()
                self.assertIsNotNone(found)
                self.assertTrue(found.exists())
        finally:
            gbr.VGAMEPAD_AVAILABLE = original_available

    def test_returns_none_when_nothing_available_anywhere(self) -> None:
        with TemporaryDirectory() as tmp:
            base = Path(tmp)
            runtime = self._make_runtime(base)
            (base / "bin" / "ViGEmBus").mkdir(parents=True)
            original_helper = runtime._vgamepad_bundled_installer
            runtime._vgamepad_bundled_installer = lambda: None
            try:
                self.assertIsNone(runtime.find_vigembus_installer())
            finally:
                runtime._vgamepad_bundled_installer = original_helper

    def test_falls_back_to_resource_dir_when_base_dir_has_nothing(self) -> None:
        # Regression test for a real, live-reported bug: in a frozen onefile
        # build, an installer placed under the source repo's bin/ViGEmBus/
        # at build time is bundled by Server16Python.spec's datas entry, but
        # extracts to sys._MEIPASS at runtime (app.resource_dir) -- NOT to
        # the folder holding the deployed .exe (app.base_dir). Looking only
        # at base_dir means the button silently finds nothing unless a
        # contributor *also* manually copies the installer next to the
        # deployed exe after building.
        with TemporaryDirectory() as tmp:
            base = Path(tmp) / "deployed"
            resource = Path(tmp) / "_MEIxxxxxx"
            base.mkdir(parents=True)
            resource_vigembus_dir = resource / "bin" / "ViGEmBus"
            resource_vigembus_dir.mkdir(parents=True)
            exe_path = resource_vigembus_dir / "ViGEmBus_1.22.0_x64_x86_arm64.exe"
            exe_path.write_bytes(b"")
            runtime = gbr.GamepadBridgeRuntime.__new__(gbr.GamepadBridgeRuntime)
            runtime.app = SimpleNamespace(base_dir=base, resource_dir=resource)
            self.assertEqual(runtime.find_vigembus_installer(), exe_path)

    def test_prefers_base_dir_override_over_resource_dir(self) -> None:
        with TemporaryDirectory() as tmp:
            base = Path(tmp) / "deployed"
            resource = Path(tmp) / "_MEIxxxxxx"
            base_vigembus_dir = base / "bin" / "ViGEmBus"
            base_vigembus_dir.mkdir(parents=True)
            resource_vigembus_dir = resource / "bin" / "ViGEmBus"
            resource_vigembus_dir.mkdir(parents=True)
            override_exe = base_vigembus_dir / "ViGEmBus_override.exe"
            override_exe.write_bytes(b"")
            (resource_vigembus_dir / "ViGEmBus_bundled.exe").write_bytes(b"")
            runtime = gbr.GamepadBridgeRuntime.__new__(gbr.GamepadBridgeRuntime)
            runtime.app = SimpleNamespace(base_dir=base, resource_dir=resource)
            self.assertEqual(runtime.find_vigembus_installer(), override_exe)


class SettingsStoreGamepadBridgeTests(unittest.TestCase):
    def test_defaults_have_four_slots(self) -> None:
        with TemporaryDirectory() as tmp:
            store = SettingsStore(Path(tmp) / "settings.json")
            slots = store.data["gamepad_bridge"]["slots"]
            self.assertEqual(len(slots), 4)
            self.assertTrue(
                all(
                    slot == {"enabled": False, "device_guid": "", "profile": "auto", "hide_from_fifa": False}
                    for slot in slots
                )
            )

    def test_partial_user_file_is_deep_merged_not_replaced(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            path.write_text(json.dumps({"gamepad_bridge": {"slots": [{"enabled": True, "device_guid": "abc", "profile": "switch_pro"}]}}), encoding="utf-8")
            store = SettingsStore(path)
            slots = store.data["gamepad_bridge"]["slots"]
            self.assertEqual(slots[0], {"enabled": True, "device_guid": "abc", "profile": "switch_pro"})

    def test_missing_key_entirely_still_yields_four_default_slots(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            path.write_text(json.dumps({"LANGUAGE": "es"}), encoding="utf-8")
            store = SettingsStore(path)
            self.assertEqual(len(store.data["gamepad_bridge"]["slots"]), 4)


class FakeHidHide:
    """Records calls instead of touching a real HidHideCLI.exe/driver --
    GamepadBridgeRuntime only ever calls these two methods (see
    _apply_hidhide_preference), never anything else on hidhide_runtime.py's
    real HidHideRuntime. hide_device_for_slot's own_exe param is the
    self-exclusion request folded into the same call (see hidhide_runtime.py
    -- this used to be a separate ensure_own_process_excluded() call, merged
    to cut elevation/UAC prompts from up to three down to one per toggle)."""

    def __init__(self) -> None:
        self.hidden: list[str] = []
        self.hidden_own_exe: list[str | None] = []
        self.unhidden: list[str] = []
        self.done = threading.Event()

    def hide_device_for_slot(self, guid: str, own_exe: str | None = None) -> bool:
        self.hidden.append(guid)
        self.hidden_own_exe.append(own_exe)
        self.done.set()
        return True

    def unhide_device_for_slot(self, guid: str) -> bool:
        self.unhidden.append(guid)
        self.done.set()
        return True


class SetSlotConfigHideFromFifaTests(unittest.TestCase):
    """set_slot_config(index, hide_from_fifa=...) is the only entry point
    that should ever touch HidHide -- confirms it dispatches correctly
    (hide+self-exclude on True, unhide on False, nothing at all when the
    parameter is left at its None default) without needing a real pygame
    joystick or vgamepad/ViGEmBus, and without ever calling into the real
    hidhide_runtime.HidHideRuntime (a fake standing in via app.hidhide)."""

    def _make_runtime(self, hidhide: "FakeHidHide") -> gbr.GamepadBridgeRuntime:
        # A plain in-memory fake -- no real SettingsStore/filesystem needed,
        # these tests only care that set_slot_config() writes the right
        # dict shape into app.settings.data and dispatches to app.hidhide
        # correctly, not that it round-trips through a real file.
        settings = SimpleNamespace(data={"gamepad_bridge": {"slots": []}}, save=lambda: None)
        runtime = gbr.GamepadBridgeRuntime.__new__(gbr.GamepadBridgeRuntime)
        runtime.app = SimpleNamespace(settings=settings, hidhide=hidhide, log=lambda *a, **k: None)
        runtime._lock = threading.Lock()
        runtime._slots = [gbr.SlotState() for _ in range(gbr.SLOT_COUNT)]
        runtime._wake_event = threading.Event()
        runtime._ensure_thread = lambda: True
        return runtime

    def test_enabling_hide_from_fifa_hides_the_device_and_self_excludes(self) -> None:
        hidhide = FakeHidHide()
        runtime = self._make_runtime(hidhide)
        runtime.set_slot_config(0, enabled=False, device_guid="guid-1", hide_from_fifa=True)
        self.assertTrue(hidhide.done.wait(timeout=2.0), "background HidHide worker never ran")
        self.assertEqual(hidhide.hidden, ["guid-1"])
        # own_exe must be sys.executable -- this app's own process, not FIFA's.
        self.assertEqual(hidhide.hidden_own_exe, [sys.executable])
        self.assertEqual(hidhide.unhidden, [])

    def test_disabling_hide_from_fifa_unhides_without_whitelisting(self) -> None:
        hidhide = FakeHidHide()
        runtime = self._make_runtime(hidhide)
        # First arm it hidden (mirrors a real prior session), then flip off.
        runtime._slots[0].hide_from_fifa = True
        hidhide.done.clear()
        runtime.set_slot_config(0, enabled=False, device_guid="guid-1", hide_from_fifa=False)
        self.assertTrue(hidhide.done.wait(timeout=2.0), "background HidHide worker never ran")
        self.assertEqual(hidhide.unhidden, ["guid-1"])
        self.assertEqual(hidhide.hidden, [])

    def test_leaving_hide_from_fifa_as_none_never_touches_hidhide(self) -> None:
        hidhide = FakeHidHide()
        runtime = self._make_runtime(hidhide)
        # Only enabled/device/profile change -- the Enabled checkbox/device
        # combo path, which must never call into HidHide on its own.
        runtime.set_slot_config(0, enabled=False, device_guid="guid-1")
        self.assertFalse(hidhide.done.wait(timeout=0.3))
        self.assertEqual(hidhide.hidden, [])
        self.assertEqual(hidhide.unhidden, [])

    def test_persists_hide_from_fifa_to_settings(self) -> None:
        hidhide = FakeHidHide()
        runtime = self._make_runtime(hidhide)
        runtime.set_slot_config(2, enabled=False, device_guid="guid-2", hide_from_fifa=True)
        hidhide.done.wait(timeout=2.0)
        saved_slot = runtime.app.settings.data["gamepad_bridge"]["slots"][2]
        self.assertEqual(saved_slot["hide_from_fifa"], True)
        self.assertEqual(saved_slot["device_guid"], "guid-2")


class ClearSlotTests(unittest.TestCase):
    """clear_slot() is the per-slot Remove button: bridge off, saved device
    dropped from runtime/settings.json, HidHide cloak lifted -- so a pad that
    won't be used again isn't kept around (and stays hidden) forever."""

    # Two SDL GUIDs of the same model (same VID/PID bytes) and one of another.
    PRO_A = "030056fb7e0500000920000010026803"
    PRO_B = "030056fb7e0500000920000011026803"
    OTHER = "03000000c82d00000160000000000000"

    def _make_runtime(self, settings, hidhide: "FakeHidHide | None" = None) -> gbr.GamepadBridgeRuntime:
        runtime = gbr.GamepadBridgeRuntime.__new__(gbr.GamepadBridgeRuntime)
        runtime.app = SimpleNamespace(settings=settings, hidhide=hidhide, log=lambda *a, **k: None)
        runtime._lock = threading.Lock()
        runtime._slots = [gbr.SlotState() for _ in range(gbr.SLOT_COUNT)]
        runtime._wake_event = threading.Event()
        runtime._ensure_thread = lambda: True
        return runtime

    @staticmethod
    def _memory_settings():
        return SimpleNamespace(data={"gamepad_bridge": {"slots": []}}, save=lambda: None)

    @staticmethod
    def _configure(runtime, index: int, guid: str, *, enabled=True, hide=False, profile=gbr.PROFILE_AUTO) -> None:
        slot = runtime._slots[index]
        slot.enabled, slot.device_guid, slot.hide_from_fifa, slot.profile = enabled, guid, hide, profile

    def test_resets_the_slot_and_its_saved_entry_to_defaults(self) -> None:
        runtime = self._make_runtime(self._memory_settings())
        self._configure(runtime, 1, self.PRO_A, hide=True, profile=gbr.PROFILE_GENERIC)
        runtime.clear_slot(1)
        self.assertEqual(
            runtime.get_slot_snapshot(1),
            {"enabled": False, "device_guid": "", "profile": gbr.PROFILE_AUTO, "status": "disconnected",
             "hide_from_fifa": False},
        )
        saved = runtime.app.settings.data["gamepad_bridge"]["slots"][1]
        self.assertEqual(
            saved, {"enabled": False, "device_guid": "", "profile": gbr.PROFILE_AUTO, "hide_from_fifa": False}
        )

    def test_wakes_the_sdl_thread_so_the_virtual_pad_is_released(self) -> None:
        runtime = self._make_runtime(self._memory_settings())
        self._configure(runtime, 0, self.PRO_A)
        runtime.clear_slot(0)
        self.assertTrue(runtime._wake_event.is_set())

    def test_only_touches_the_requested_slot(self) -> None:
        runtime = self._make_runtime(self._memory_settings())
        self._configure(runtime, 0, self.PRO_A)
        self._configure(runtime, 1, self.OTHER)
        runtime.clear_slot(0)
        self.assertEqual(runtime.get_slot_snapshot(1)["device_guid"], self.OTHER)
        self.assertTrue(runtime.get_slot_snapshot(1)["enabled"])

    def test_lifts_the_hidhide_cloak_when_the_slot_had_hidden_its_pad(self) -> None:
        hidhide = FakeHidHide()
        runtime = self._make_runtime(self._memory_settings(), hidhide)
        self._configure(runtime, 0, self.PRO_A, hide=True)
        runtime.clear_slot(0)
        self.assertTrue(hidhide.done.wait(timeout=2.0), "background HidHide worker never ran")
        self.assertEqual(hidhide.unhidden, [self.PRO_A])

    def test_keeps_the_cloak_while_another_slot_still_hides_the_same_model(self) -> None:
        # HidHide hides by VID/PID, so unhiding here would expose the other
        # slot's pad too -- even though its GUID string differs.
        hidhide = FakeHidHide()
        runtime = self._make_runtime(self._memory_settings(), hidhide)
        self._configure(runtime, 0, self.PRO_A, hide=True)
        self._configure(runtime, 1, self.PRO_B, hide=True)
        runtime.clear_slot(0)
        self.assertFalse(hidhide.done.wait(timeout=0.3))
        self.assertEqual(hidhide.unhidden, [])

    def test_lifts_the_cloak_when_the_other_hiding_slot_is_a_different_model(self) -> None:
        hidhide = FakeHidHide()
        runtime = self._make_runtime(self._memory_settings(), hidhide)
        self._configure(runtime, 0, self.PRO_A, hide=True)
        self._configure(runtime, 1, self.OTHER, hide=True)
        runtime.clear_slot(0)
        self.assertTrue(hidhide.done.wait(timeout=2.0))
        self.assertEqual(hidhide.unhidden, [self.PRO_A])

    def test_never_touches_hidhide_for_a_slot_that_was_not_hiding(self) -> None:
        hidhide = FakeHidHide()
        runtime = self._make_runtime(self._memory_settings(), hidhide)
        self._configure(runtime, 0, self.PRO_A, hide=False)
        runtime.clear_slot(0)
        self.assertFalse(hidhide.done.wait(timeout=0.3))
        self.assertEqual(hidhide.unhidden, [])

    def test_works_without_hidhide_installed_or_wired_up(self) -> None:
        runtime = self._make_runtime(self._memory_settings(), hidhide=None)
        self._configure(runtime, 0, self.PRO_A, hide=True)
        runtime.clear_slot(0)
        self.assertEqual(runtime.get_slot_snapshot(0)["device_guid"], "")

    def test_out_of_range_index_is_ignored(self) -> None:
        runtime = self._make_runtime(self._memory_settings())
        runtime.clear_slot(-1)
        runtime.clear_slot(gbr.SLOT_COUNT)
        self.assertEqual(runtime.app.settings.data["gamepad_bridge"]["slots"], [])

    def test_the_saved_guid_is_really_gone_from_the_json_file(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            store = SettingsStore(path)
            runtime = self._make_runtime(store)
            self._configure(runtime, 2, self.PRO_A, hide=False)
            runtime._persist_slot(2)
            self.assertIn(self.PRO_A, path.read_text(encoding="utf-8"))

            runtime.clear_slot(2)

            on_disk = json.loads(path.read_text(encoding="utf-8"))
            self.assertNotIn(self.PRO_A, path.read_text(encoding="utf-8"))
            self.assertEqual(on_disk["gamepad_bridge"]["slots"][2]["device_guid"], "")
            self.assertFalse(on_disk["gamepad_bridge"]["slots"][2]["enabled"])
            self.assertEqual(len(on_disk["gamepad_bridge"]["slots"]), gbr.SLOT_COUNT)


class SameModelTests(unittest.TestCase):
    def test_same_model_matches_on_vid_pid_not_the_whole_guid(self) -> None:
        self.assertTrue(gbr._same_model("030056fb7e0500000920000010026803", "030056fb7e0500000920000011026803"))

    def test_different_models_and_empty_guids_never_match(self) -> None:
        self.assertFalse(gbr._same_model("030056fb7e0500000920000010026803", "03000000c82d00000160000000000000"))
        self.assertFalse(gbr._same_model("", ""))
        self.assertFalse(gbr._same_model("030056fb7e0500000920000010026803", ""))

    def test_unparseable_guids_only_match_when_identical(self) -> None:
        self.assertTrue(gbr._same_model("not-hex", "not-hex"))
        self.assertFalse(gbr._same_model("not-hex", "also-not-hex"))


class StartDoesNotTouchHidhideTests(unittest.TestCase):
    """Regression test for a real, live-reported bug: start() used to call
    _apply_hidhide_preference() for any slot whose hide_from_fifa was
    already True in settings.json -- which fires HidHide's *elevated* CLI
    commands (a UAC prompt) on every single app launch forever. Reported
    live 2026-09-24 as "now it asks for admin permissions every time I open
    the app". HidHide's own driver persists the hide/cloak/whitelist state
    across app restarts, so nothing needs to be redone at startup."""

    def test_start_never_calls_hidhide_even_when_a_slot_has_hide_from_fifa_true(self) -> None:
        hidhide = FakeHidHide()
        settings = SimpleNamespace(
            data={
                "gamepad_bridge": {
                    "slots": [
                        {"enabled": False, "device_guid": "guid-1", "profile": "auto", "hide_from_fifa": True},
                        {"enabled": False, "device_guid": "", "profile": "auto", "hide_from_fifa": False},
                        {"enabled": False, "device_guid": "", "profile": "auto", "hide_from_fifa": False},
                        {"enabled": False, "device_guid": "", "profile": "auto", "hide_from_fifa": False},
                    ]
                }
            },
            save=lambda: None,
        )
        runtime = gbr.GamepadBridgeRuntime.__new__(gbr.GamepadBridgeRuntime)
        runtime.app = SimpleNamespace(settings=settings, hidhide=hidhide, log=lambda *a, **k: None)
        runtime._lock = threading.Lock()
        runtime._slots = [gbr.SlotState() for _ in range(gbr.SLOT_COUNT)]
        runtime._ensure_thread = lambda: True
        runtime.start()
        self.assertTrue(runtime._slots[0].hide_from_fifa)  # loaded from settings correctly
        self.assertFalse(hidhide.done.wait(timeout=0.3))
        self.assertEqual(hidhide.hidden, [])
        self.assertEqual(hidhide.unhidden, [])



class StartReappliesHideFromFifaTests(unittest.TestCase):
    """Reported live 2026-09-23: Hide from FIFA showed checked while HidHide
    had nothing hidden, so FIFA listed the physical pad as player 1 next to
    the virtual one. start() now re-applies the checkbox's state -- through
    ensure_hidden_for_slot(), which never elevates (no UAC prompt at app
    launch)."""

    def _runtime(self, hidhide, slots):
        settings = SimpleNamespace(data={"gamepad_bridge": {"slots": slots}}, save=lambda: None)
        runtime = gbr.GamepadBridgeRuntime.__new__(gbr.GamepadBridgeRuntime)
        runtime.app = SimpleNamespace(settings=settings, hidhide=hidhide, log=lambda *a, **k: None)
        runtime._lock = threading.Lock()
        runtime._slots = [gbr.SlotState() for _ in range(gbr.SLOT_COUNT)]
        runtime._ensure_thread = lambda: True
        return runtime

    def test_start_ensures_every_hidden_slot_without_the_elevating_entry_point(self) -> None:
        ensured: list[tuple[str, str | None]] = []
        done = threading.Event()

        def ensure(guid, own_exe=None):
            ensured.append((guid, own_exe))
            done.set()
            return True

        hidhide = SimpleNamespace(
            ensure_hidden_for_slot=ensure,
            hide_device_for_slot=lambda *a, **k: self.fail("start() must never use the elevating entry point"),
        )
        runtime = self._runtime(
            hidhide,
            [
                {"enabled": True, "device_guid": "guid-1", "profile": "auto", "hide_from_fifa": True},
                {"enabled": True, "device_guid": "guid-2", "profile": "auto", "hide_from_fifa": False},
            ],
        )
        runtime.start()
        self.assertTrue(done.wait(timeout=2.0))
        self.assertEqual(ensured, [("guid-1", sys.executable)])

    def test_start_does_nothing_when_no_slot_hides(self) -> None:
        hidhide = SimpleNamespace(ensure_hidden_for_slot=lambda *a, **k: self.fail("must not be called"))
        runtime = self._runtime(
            hidhide, [{"enabled": True, "device_guid": "guid-1", "profile": "auto", "hide_from_fifa": False}]
        )
        runtime.start()


if __name__ == "__main__":
    unittest.main()
