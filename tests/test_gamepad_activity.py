from __future__ import annotations

import ctypes
import threading
import unittest
from types import SimpleNamespace
from unittest import mock

from server16_py import app_ui
from server16_py import gamepad_bridge_runtime as gbr
from server16_py import xinput_players
from server16_py.win32_types import XINPUT_CAPABILITIES_EX, XINPUT_GAMEPAD, XINPUT_STATE

GUID = "030056fb7e0500000920000010026803"


def _mapped(buttons=(), left_stick=(0.0, 0.0), right_stick=(0.0, 0.0), left_trigger=0.0, right_trigger=0.0) -> dict:
    return {
        "buttons": {name: name in buttons for name in gbr._ALL_XUSB_BUTTON_NAMES},
        "left_stick": left_stick,
        "right_stick": right_stick,
        "left_trigger": left_trigger,
        "right_trigger": right_trigger,
    }


class StateHasInputTests(unittest.TestCase):
    """What lights a slot's activity indicator: any deliberate input, but
    never an idle pad -- stick drift and resting triggers must stay dark."""

    def test_idle_raw_pad_is_dark(self) -> None:
        self.assertFalse(gbr.state_has_input({"buttons": [False] * 12, "axes": [0.0] * 4, "hats": [(0, 0)]}))

    def test_raw_button_lights_it(self) -> None:
        self.assertTrue(gbr.state_has_input({"buttons": [False, True], "axes": [], "hats": []}))

    def test_raw_dpad_hat_lights_it(self) -> None:
        self.assertTrue(gbr.state_has_input({"buttons": [], "axes": [], "hats": [(0, -1)]}))

    def test_raw_stick_lights_it_only_past_the_deadzone(self) -> None:
        self.assertFalse(gbr.state_has_input({"buttons": [], "axes": [0.2, -0.2, 0.1, 0.0], "hats": []}))
        self.assertTrue(gbr.state_has_input({"buttons": [], "axes": [0.0, -0.9, 0.0, 0.0], "hats": []}))

    def test_raw_trigger_axes_resting_at_minus_one_stay_dark(self) -> None:
        # Axes past the two sticks are analog triggers on many pads, and
        # those rest at -1.0 with nothing touched.
        self.assertFalse(gbr.state_has_input({"buttons": [], "axes": [0.0, 0.0, 0.0, 0.0, -1.0, -1.0], "hats": []}))

    def test_translated_state_wins_over_the_raw_one(self) -> None:
        # SDL-recognized pad: the raw trigger axes rest at -1.0, the
        # translated state says nothing is pressed.
        state = {"buttons": [], "axes": [0.0, 0.0, -1.0, -1.0], "hats": [], "mapped": _mapped()}
        self.assertFalse(gbr.state_has_input(state))

    def test_translated_button_stick_and_trigger_each_light_it(self) -> None:
        for mapped in (
            _mapped(buttons={"XUSB_GAMEPAD_A"}),
            _mapped(buttons={"XUSB_GAMEPAD_DPAD_LEFT"}),
            _mapped(left_stick=(0.0, -0.8)),
            _mapped(right_stick=(0.7, 0.0)),
            _mapped(right_trigger=0.6),
        ):
            with self.subTest(mapped=mapped):
                self.assertTrue(gbr.state_has_input({"buttons": [], "axes": [], "hats": [], "mapped": mapped}))

    def test_translated_drift_stays_dark(self) -> None:
        mapped = _mapped(left_stick=(0.12, -0.2), right_stick=(0.05, 0.0), left_trigger=0.05)
        self.assertFalse(gbr.state_has_input({"buttons": [], "axes": [], "hats": [], "mapped": mapped}))


class XInputGamepadHasInputTests(unittest.TestCase):
    def test_idle_pad_is_dark(self) -> None:
        self.assertFalse(gbr.xinput_gamepad_has_input(XINPUT_GAMEPAD()))

    def test_button_lights_it(self) -> None:
        self.assertTrue(gbr.xinput_gamepad_has_input(XINPUT_GAMEPAD(wButtons=0x1000)))

    def test_stick_lights_it_only_past_the_deadzone(self) -> None:
        self.assertFalse(gbr.xinput_gamepad_has_input(XINPUT_GAMEPAD(sThumbLX=4000, sThumbRY=-5000)))
        self.assertTrue(gbr.xinput_gamepad_has_input(XINPUT_GAMEPAD(sThumbLY=-32768)))
        self.assertTrue(gbr.xinput_gamepad_has_input(XINPUT_GAMEPAD(sThumbRX=20000)))

    def test_trigger_lights_it_only_past_the_threshold(self) -> None:
        self.assertFalse(gbr.xinput_gamepad_has_input(XINPUT_GAMEPAD(bLeftTrigger=20)))
        self.assertTrue(gbr.xinput_gamepad_has_input(XINPUT_GAMEPAD(bRightTrigger=200)))


class SlotInputActiveTests(unittest.TestCase):
    """slot_input_active() is read ~20 times a second by the Tk thread; the
    SDL thread samples at ~125Hz and latches the last time it saw input, so a
    tap shorter than the Tk poll interval still lights the indicator."""

    def _runtime(self, guid: str = GUID) -> gbr.GamepadBridgeRuntime:
        runtime = gbr.GamepadBridgeRuntime.__new__(gbr.GamepadBridgeRuntime)
        runtime._lock = threading.Lock()
        runtime._slots = [gbr.SlotState() for _ in range(gbr.SLOT_COUNT)]
        runtime._slots[1].device_guid = guid
        runtime._raw_states = {}
        runtime._raw_watch = {}
        runtime._watch_targets = {}
        runtime._input_seen = {}
        runtime._controllers = {}
        runtime._ensure_thread = lambda: True
        return runtime

    def test_dark_until_the_sdl_thread_reports_input(self) -> None:
        self.assertFalse(self._runtime().slot_input_active(1))

    def test_lit_right_after_input_and_dark_again_once_the_hold_expires(self) -> None:
        runtime = self._runtime()
        with mock.patch.object(gbr.time, "monotonic", return_value=50.0):
            runtime._input_seen[(GUID, 1)] = 50.0 - gbr.INPUT_ACTIVITY_HOLD_SECONDS / 2
            self.assertTrue(runtime.slot_input_active(1))
            runtime._input_seen[(GUID, 1)] = 50.0 - gbr.INPUT_ACTIVITY_HOLD_SECONDS * 2
            self.assertFalse(runtime.slot_input_active(1))

    def test_asks_the_sdl_thread_to_keep_the_slots_own_pad_open(self) -> None:
        # Also for a slot whose bridge is off -- that's how the light can
        # show which physical pad a slot means before enabling it.
        runtime = self._runtime()
        runtime.slot_input_active(1)
        self.assertIn((GUID, 1), runtime._raw_watch)

    def test_slot_without_a_device_never_watches_anything(self) -> None:
        runtime = self._runtime()
        self.assertFalse(runtime.slot_input_active(0))
        self.assertEqual(runtime._raw_watch, {})

    def test_out_of_range_slot_is_dark(self) -> None:
        self.assertFalse(self._runtime().slot_input_active(99))

    def test_dark_without_pygame(self) -> None:
        runtime = self._runtime()
        runtime._ensure_thread = lambda: False
        self.assertFalse(runtime.slot_input_active(1))

    def test_publish_latches_input_and_keeps_it_through_a_released_sample(self) -> None:
        runtime = self._runtime()
        key = (GUID, 1)
        runtime._watch_targets = {key: 7}
        pressed = SimpleNamespace(
            get_numbuttons=lambda: 1, get_button=lambda i: True,
            get_numaxes=lambda: 0, get_numhats=lambda: 0,
        )
        released = SimpleNamespace(
            get_numbuttons=lambda: 1, get_button=lambda i: False,
            get_numaxes=lambda: 0, get_numhats=lambda: 0,
        )
        runtime._raw_watch = {key: 100.0}
        runtime._publish_raw_states({7: pressed}, 100.0)
        self.assertEqual(runtime._input_seen[key], 100.0)
        # Button released one tick later: the latch must still say 100.0, so
        # the light stays on for the hold time instead of vanishing at once.
        runtime._publish_raw_states({7: released}, 100.008)
        self.assertEqual(runtime._input_seen[key], 100.0)

    def test_publish_forgets_the_latch_when_the_pad_goes_away(self) -> None:
        runtime = self._runtime()
        key = (GUID, 1)
        runtime._raw_watch = {key: 100.0}
        runtime._input_seen[key] = 99.99
        runtime._publish_raw_states({}, 100.0)
        self.assertNotIn(key, runtime._input_seen)


class VirtualPadDriverIndexTests(unittest.TestCase):
    """What the bridge publishes about its virtual pads for the Xbox
    controllers card: ViGEmBus's own index (a ranking hint only -- it is NOT
    the XInput player) and the buttons each pad is showing."""

    _PAD = SimpleNamespace(_busp=0x1111, _devicep=0x2222)

    def _client(self, error: int, player: int):
        calls = []

        def get_user_index(busp, devicep, index_ref):
            calls.append((busp, devicep))
            ctypes.cast(index_ref, ctypes.POINTER(ctypes.c_ulong)).contents.value = player
            return error

        return SimpleNamespace(vigem_target_x360_get_user_index=get_user_index), calls

    def _lookup(self, client):
        with mock.patch.dict(gbr.sys.modules, {gbr._VIGEM_CLIENT_MODULE: client}):
            return gbr._virtual_pad_driver_index(self._PAD)

    def test_returns_the_index_the_driver_reports_for_this_pads_own_handles(self) -> None:
        client, calls = self._client(gbr._VIGEM_ERROR_NONE, 2)
        self.assertEqual(self._lookup(client), 2)
        self.assertEqual(calls, [(0x1111, 0x2222)])

    def test_unknown_while_the_driver_reports_an_error(self) -> None:
        client, _calls = self._client(0xE0000008, 0)
        self.assertIsNone(self._lookup(client))

    def test_unknown_for_an_out_of_range_index(self) -> None:
        client, _calls = self._client(gbr._VIGEM_ERROR_NONE, 9)
        self.assertIsNone(self._lookup(client))

    def test_unknown_when_the_call_itself_fails(self) -> None:
        def boom(*_args):
            raise OSError("access violation")

        self.assertIsNone(self._lookup(SimpleNamespace(vigem_target_x360_get_user_index=boom)))

    def test_unknown_without_vgamepad_loaded(self) -> None:
        with mock.patch.dict(gbr.sys.modules):
            gbr.sys.modules.pop(gbr._VIGEM_CLIENT_MODULE, None)
            self.assertIsNone(gbr._virtual_pad_driver_index(self._PAD))

    def test_publishes_every_slot_that_has_a_virtual_pad_with_what_it_is_showing(self) -> None:
        runtime = gbr.GamepadBridgeRuntime.__new__(gbr.GamepadBridgeRuntime)
        runtime._lock = threading.Lock()
        runtime._slots = [gbr.SlotState() for _ in range(gbr.SLOT_COUNT)]
        runtime._virtual_sent = [None] * gbr.SLOT_COUNT
        runtime._slots[0].pad = SimpleNamespace(report=SimpleNamespace(wButtons=0x1000))
        # A pad the driver hasn't indexed yet is still a virtual pad.
        runtime._slots[2].pad = SimpleNamespace(report=SimpleNamespace(wButtons=0))
        runtime._slots[3].driver_index = 1  # stale: this slot's pad is gone
        indices = {id(runtime._slots[0].pad): 1, id(runtime._slots[2].pad): None}
        with mock.patch.object(gbr, "_virtual_pad_driver_index", side_effect=lambda pad: indices[id(pad)]):
            runtime._refresh_virtual_driver_indices()
        runtime._publish_virtual_pads()
        self.assertEqual(runtime.virtual_pads(), {0: (1, 0x1000), 2: (None, 0)})


class _FakeDot:
    def __init__(self) -> None:
        self.lit = False

    def set_lit(self, lit: bool) -> None:
        self.lit = bool(lit)


class _FakeLabel:
    def __init__(self) -> None:
        self.text = ""

    def configure(self, **kwargs) -> None:
        self.text = kwargs.get("text", self.text)


class _FakeXInput:
    """XInputGetState over a {player: XINPUT_GAMEPAD} table; records which
    players were asked about."""

    def __init__(self, pads: dict[int, XINPUT_GAMEPAD]) -> None:
        self.pads = pads
        self.asked: list[int] = []

    def XInputGetState(self, index, state_ref) -> int:
        self.asked.append(index)
        pad = self.pads.get(index)
        if pad is None:
            return 1167  # ERROR_DEVICE_NOT_CONNECTED
        ctypes.cast(state_ref, ctypes.POINTER(XINPUT_STATE)).contents.Gamepad = pad
        return 0


XBOX_SERIES = (0x045E, 0x0B12)
VIRTUAL = (0x045E, 0x028E)  # also what a real wired Xbox 360 pad reports


def _fake_capabilities_ex(identities: dict[int, tuple[int, int]]):
    def capabilities_ex(_one, index, _flags, caps_ref) -> int:
        if index not in identities:
            return 1167
        caps = ctypes.cast(caps_ref, ctypes.POINTER(XINPUT_CAPABILITIES_EX)).contents
        caps.VendorId, caps.ProductId = identities[index]
        return 0

    return capabilities_ex


class XInputRowsTests(unittest.TestCase):
    """The read-only Xbox controllers card: which XInput players are taken,
    and which of them are really this app's own virtual pads."""

    def _app(
        self,
        pads: dict[int, XINPUT_GAMEPAD],
        virtual: "dict[int, tuple[int | None, int]] | None" = None,
        identities: "dict[int, tuple[int, int]] | None" = None,
    ) -> SimpleNamespace:
        """`virtual` is the bridge's virtual_pads(); `identities` what each
        player reports through XInputGetCapabilitiesEx (None: no xinput1_4)."""
        app = SimpleNamespace(
            _xinput=_FakeXInput(pads),
            _xinput_capabilities_ex=None if identities is None else _fake_capabilities_ex(identities),
            _xinput_connected=set(),
            _xinput_virtual_candidates=set(),
            _xinput_matcher=xinput_players.VirtualPadMatcher(),
            _gamepad_slot_device_names={},
            gamepad_bridge=SimpleNamespace(
                virtual_pads=lambda: dict(virtual or {}),
                slot_input_active=lambda idx: idx == 1,
            ),
            gamepad_xinput_rows={
                i: {"activity": _FakeDot(), "label": _FakeLabel(), "status": _FakeLabel()}
                for i in range(gbr.XINPUT_USER_COUNT)
            },
            gamepad_slot_widgets={i: {"activity": _FakeDot()} for i in range(gbr.SLOT_COUNT)},
            gamepads_tab=SimpleNamespace(winfo_viewable=lambda: True),
            tr=lambda key, **kw: key + "".join(f"|{k}={v}" for k, v in sorted(kw.items())),
            fg="fg",
            muted="muted",
            after=lambda delay, callback: delay,
        )
        app._read_xinput_gamepad = lambda index: app_ui.UIMixin._read_xinput_gamepad(app, index)
        app._relabel_xinput_rows = lambda: app_ui.UIMixin._relabel_xinput_rows(app)
        app._gamepad_activity_tick = lambda: None
        return app

    def _statuses(self, app) -> list[str]:
        return [app.gamepad_xinput_rows[i]["status"].text for i in range(gbr.XINPUT_USER_COUNT)]

    def test_lists_real_pads_virtual_pads_and_empty_players(self) -> None:
        app = self._app(
            {0: XINPUT_GAMEPAD(), 2: XINPUT_GAMEPAD(), 3: XINPUT_GAMEPAD()},
            virtual={1: (0, 0), 3: (1, 0)},
            identities={0: XBOX_SERIES, 2: VIRTUAL, 3: VIRTUAL},
        )
        app_ui.UIMixin._refresh_xinput_rows(app, {1: "Pro Controller"})
        self.assertEqual(
            self._statuses(app),
            [
                "status.gamepads.xinput_connected",
                "status.gamepads.xinput_empty",
                "status.gamepads.xinput_virtual|n=2 (Pro Controller)",
                # Slot 4's physical pad is unplugged (no name), its virtual
                # pad is kept alive -- still labelled as that slot's.
                "status.gamepads.xinput_virtual|n=4",
            ],
        )
        self.assertEqual(app._xinput_connected, {0, 2, 3})

    def test_xbox_series_pad_plus_one_bridged_slot_is_labelled_by_what_xinput_says(self) -> None:
        # Reported live 2026-10-05, with the players exactly as probed on
        # that PC: the real Xbox Series pad is player 1, the Switch pad's
        # virtual pad player 2 -- while ViGEmBus calls that virtual pad
        # index 0, which used to put its label on the real pad's row.
        app = self._app(
            {0: XINPUT_GAMEPAD(), 1: XINPUT_GAMEPAD()},
            virtual={0: (0, 0)},
            identities={0: XBOX_SERIES, 1: VIRTUAL},
        )
        app_ui.UIMixin._refresh_xinput_rows(app, {0: "Nintendo Switch Pro Controller"})
        self.assertEqual(
            self._statuses(app)[:2],
            ["status.gamepads.xinput_connected", "status.gamepads.xinput_virtual|n=1 (Nintendo Switch Pro Controller)"],
        )

    def test_the_real_pad_keeps_its_row_whether_or_not_the_slot_is_bridged(self) -> None:
        app = self._app({0: XINPUT_GAMEPAD()}, virtual={}, identities={0: XBOX_SERIES})
        app_ui.UIMixin._refresh_xinput_rows(app, {})
        self.assertEqual(self._statuses(app)[0], "status.gamepads.xinput_connected")
        # Slot 1 gets bridged: its pad exists but XInput doesn't list it yet.
        app.gamepad_bridge.virtual_pads = lambda: {0: (0, 0)}
        app_ui.UIMixin._refresh_xinput_rows(app, {})
        self.assertEqual(self._statuses(app)[0], "status.gamepads.xinput_connected")

    def test_a_real_360_pad_is_not_guessed_at_until_a_button_settles_it(self) -> None:
        # A real wired Xbox 360 pad (player 1) reports the same identity as
        # the virtual pad (player 2): neither row may claim to be the slot's.
        pads = {0: XINPUT_GAMEPAD(), 1: XINPUT_GAMEPAD()}
        sent = {0: (0, 0)}
        app = self._app(pads, virtual=sent, identities={0: VIRTUAL, 1: VIRTUAL})
        app_ui.UIMixin._refresh_xinput_rows(app, {})
        self.assertEqual(self._statuses(app)[:2], ["status.gamepads.xinput_connected"] * 2)
        # A is held on the slot's physical pad: the bridge sends it, and
        # player 2 is the one that shows it.
        sent[0] = (0, 0x1000)
        pads[1] = XINPUT_GAMEPAD(wButtons=0x1000)
        for _ in range(xinput_players.SIGHTINGS_TO_CONFIRM):
            app_ui.UIMixin._gamepad_activity_tick(app)
        self.assertEqual(
            self._statuses(app)[:2], ["status.gamepads.xinput_connected", "status.gamepads.xinput_virtual|n=1"]
        )

    def test_without_xinput1_4_every_pad_may_be_virtual(self) -> None:
        # No identities at all (xinput1_3 / xinput9_1_0): one virtual pad and
        # two connected players can't be told apart without input.
        app = self._app({0: XINPUT_GAMEPAD(), 1: XINPUT_GAMEPAD()}, virtual={0: (0, 0)})
        app_ui.UIMixin._refresh_xinput_rows(app, {})
        self.assertEqual(self._statuses(app)[:2], ["status.gamepads.xinput_connected"] * 2)
        self.assertEqual(app._xinput_virtual_candidates, {0, 1})

    def test_everything_reads_empty_without_xinput(self) -> None:
        app = self._app({})
        app._xinput = None
        app_ui.UIMixin._refresh_xinput_rows(app, {})
        self.assertEqual(self._statuses(app), ["status.gamepads.xinput_empty"] * 4)

    def test_a_pad_that_was_unplugged_goes_dark(self) -> None:
        app = self._app({})
        app.gamepad_xinput_rows[0]["activity"].lit = True
        app_ui.UIMixin._refresh_xinput_rows(app, {})
        self.assertFalse(app.gamepad_xinput_rows[0]["activity"].lit)

    def test_activity_tick_lights_the_pads_in_use_and_only_polls_connected_players(self) -> None:
        app = self._app({0: XINPUT_GAMEPAD(), 2: XINPUT_GAMEPAD(wButtons=0x1000)})
        app._xinput_connected = {0, 2}
        app_ui.UIMixin._gamepad_activity_tick(app)
        self.assertEqual([app.gamepad_xinput_rows[i]["activity"].lit for i in range(4)], [False, False, True, False])
        self.assertEqual([app.gamepad_slot_widgets[i]["activity"].lit for i in range(4)], [False, True, False, False])
        # Empty players are slow to query -- left to the 1Hz refresh.
        self.assertEqual(sorted(app._xinput.asked), [0, 2])
        self.assertEqual(app._gamepad_activity_job, app_ui.GAMEPAD_ACTIVITY_POLL_MS)

    def test_activity_tick_polls_nothing_while_the_tab_is_not_on_screen(self) -> None:
        app = self._app({0: XINPUT_GAMEPAD(wButtons=0x1000)})
        app._xinput_connected = {0}
        app.gamepads_tab = SimpleNamespace(winfo_viewable=lambda: False)
        watched: list[int] = []
        app.gamepad_bridge.slot_input_active = lambda idx: watched.append(idx) or True
        app_ui.UIMixin._gamepad_activity_tick(app)
        self.assertEqual(watched, [])
        self.assertEqual(app._xinput.asked, [])
        self.assertEqual(app._gamepad_activity_job, app_ui.GAMEPAD_ACTIVITY_IDLE_MS)


if __name__ == "__main__":
    unittest.main()
