"""Custom keys and gamepad buttons for the in-game overlay shortcuts and the
kit hotkeys (Settings tab > Controls card, app_ui._build_controls_card).

Only the shortcuts that work while the overlay menu is CLOSED are bindable:
open/close the menu, go straight to Kits > Team Kits, and the five
kit-cycling hotkeys. Navigation inside the open menu (arrows/Enter/Esc/...,
A/B/X/Y/LB/RB/D-pad) stays fixed: its button legend is drawn by the DLL
(cgfs16_rmlui_menu.cpp's kKeyHints/kGpHints), so rebinding it would mean a
new DLL and shared-memory layout.

Every binding, keyboard or gamepad, has its own Hold setting, so one key or
combination can serve two actions: one on the press, the other held
HOLD_SECONDS (F12 opens the overlay, F12 held goes to Team Kits — the
defaults). See TAP for how the press then behaves.

An InputBindings is never changed in place: the app swaps the whole object
(Server16App.input_bindings) on every change, so the hotkey poll thread and
the keyboard hook, which read it from their own threads, always see one
consistent set. Stored in runtime/settings.json under INPUT_BINDINGS
(settings_store.py)."""

from __future__ import annotations

import ctypes
from dataclasses import dataclass
from typing import Callable, Mapping

from .win32_types import (
    VK_DOWN, VK_END, VK_ESCAPE, VK_F7, VK_F8, VK_F9, VK_F10, VK_F11, VK_F12, VK_HOME, VK_LEFT, VK_NEXT,
    VK_PRIOR, VK_RETURN, VK_RIGHT, VK_SPACE, VK_UP,
    XINPUT_GAMEPAD_A, XINPUT_GAMEPAD_B, XINPUT_GAMEPAD_BACK, XINPUT_GAMEPAD_DPAD_DOWN,
    XINPUT_GAMEPAD_DPAD_LEFT, XINPUT_GAMEPAD_DPAD_RIGHT, XINPUT_GAMEPAD_DPAD_UP,
    XINPUT_GAMEPAD_LEFT_SHOULDER, XINPUT_GAMEPAD_LEFT_THUMB, XINPUT_GAMEPAD_RIGHT_SHOULDER,
    XINPUT_GAMEPAD_RIGHT_THUMB, XINPUT_GAMEPAD_START, XINPUT_GAMEPAD_X, XINPUT_GAMEPAD_Y,
)

Translate = Callable[..., str]

# How long a "hold" binding (Start/Select-hold style, F12 held) has to be held.
HOLD_SECONDS = 0.60

OVERLAY_MENU = "overlay_menu"
TEAM_KITS = "team_kits"
KIT_HOME_PREV = "kit_home_prev"
KIT_HOME_NEXT = "kit_home_next"
KIT_AWAY_PREV = "kit_away_prev"
KIT_AWAY_NEXT = "kit_away_next"
KIT_TYPE = "kit_type"

MENU_ACTIONS = (OVERLAY_MENU, TEAM_KITS)
KIT_ACTIONS = (KIT_HOME_PREV, KIT_HOME_NEXT, KIT_AWAY_PREV, KIT_AWAY_NEXT, KIT_TYPE)
ACTIONS = MENU_ACTIONS + KIT_ACTIONS

# What the open overlay menu navigates with; the WH_KEYBOARD_LL hook eats
# them while it is open (app_overlay._keyboard_hook_thread_func). Never
# bindable: the overlay key would also move the selection or close a step.
MENU_NAV_VKS = frozenset({
    VK_ESCAPE, VK_RETURN, VK_LEFT, VK_RIGHT, VK_UP, VK_DOWN, VK_PRIOR, VK_NEXT, VK_HOME, VK_END,
})

_VK_BACKSPACE = 0x08
_VK_TAB = 0x09
_VK_PAUSE = 0x13
_VK_INSERT = 0x2D
_VK_DELETE = 0x2E
_VK_SCROLL_LOCK = 0x91

# Keys a binding may use. Left out on purpose: Alt and the Windows keys (the
# shell acts on them), Caps/Num Lock (pressing them toggles a lock), the
# mouse buttons, and Print Screen (GetAsyncKeyState only sees its release).
BINDABLE_VKS = frozenset(
    (_VK_BACKSPACE, _VK_TAB, _VK_PAUSE, VK_SPACE, _VK_INSERT, _VK_DELETE, _VK_SCROLL_LOCK)
    + tuple(range(0x30, 0x3A))      # 0-9
    + tuple(range(0x41, 0x5B))      # A-Z
    + tuple(range(0x60, 0x70))      # numpad digits and operators
    + tuple(range(0x70, 0x88))      # F1-F24
    + tuple(range(0xA0, 0xA4))      # Left/Right Shift, Left/Right Ctrl
    + tuple(range(0xBA, 0xC1))      # OEM keys (punctuation; layout-dependent)
    + tuple(range(0xDB, 0xE0))
    + (0xE2,)
)

# What the capture dialog listens for: every bindable key, plus the reserved
# ones so pressing one says why it can't be used. Esc is the dialog's cancel.
CAPTURE_VKS = tuple(sorted(BINDABLE_VKS | (MENU_NAV_VKS - {VK_ESCAPE})))

_WORD_KEYS = {
    _VK_BACKSPACE: "key.backspace",
    _VK_TAB: "key.tab",
    _VK_PAUSE: "key.pause",
    VK_SPACE: "key.space",
    _VK_INSERT: "key.insert",
    _VK_DELETE: "key.delete",
    _VK_SCROLL_LOCK: "key.scroll_lock",
    0xA0: "key.left_shift",
    0xA1: "key.right_shift",
    0xA2: "key.left_ctrl",
    0xA3: "key.right_ctrl",
}
_NUMPAD_SYMBOLS = {0x6A: "*", 0x6B: "+", 0x6C: ",", 0x6D: "-", 0x6E: ".", 0x6F: "/"}

# Every button a binding may use, in the order a combination is named.
# (bit, fixed label, locale key when the name is a description)
_PAD_BUTTONS = (
    (XINPUT_GAMEPAD_LEFT_SHOULDER, "LB", ""),
    (XINPUT_GAMEPAD_RIGHT_SHOULDER, "RB", ""),
    (XINPUT_GAMEPAD_LEFT_THUMB, "LS", ""),
    (XINPUT_GAMEPAD_RIGHT_THUMB, "RS", ""),
    (XINPUT_GAMEPAD_BACK, "Select", ""),
    (XINPUT_GAMEPAD_START, "Start", ""),
    (XINPUT_GAMEPAD_A, "A", ""),
    (XINPUT_GAMEPAD_B, "B", ""),
    (XINPUT_GAMEPAD_X, "X", ""),
    (XINPUT_GAMEPAD_Y, "Y", ""),
    (XINPUT_GAMEPAD_DPAD_UP, "", "pad.dpad_up"),
    (XINPUT_GAMEPAD_DPAD_DOWN, "", "pad.dpad_down"),
    (XINPUT_GAMEPAD_DPAD_LEFT, "", "pad.dpad_left"),
    (XINPUT_GAMEPAD_DPAD_RIGHT, "", "pad.dpad_right"),
)
PAD_ALL_BUTTONS = 0
for _bit, _label, _key in _PAD_BUTTONS:
    PAD_ALL_BUTTONS |= _bit

# Buttons the open menu doesn't use. A menu shortcut must include one, or
# pressing it inside the menu would also confirm/go back/switch tab.
PAD_MENU_FREE_BUTTONS = (
    XINPUT_GAMEPAD_START | XINPUT_GAMEPAD_BACK | XINPUT_GAMEPAD_LEFT_THUMB | XINPUT_GAMEPAD_RIGHT_THUMB
)

# Problems key_problem()/pad_problem() report.
RESERVED = "reserved"
UNSUPPORTED = "unsupported"
NEEDS_FREE_BUTTON = "needs_free_button"

# When a binding fires (InputBindings.key_mode()/pad_mode(), BindingTracker).
PRESS = "press"     # as soon as it goes down
HOLD = "hold"       # once it has been held HOLD_SECONDS
# A press binding whose key/combination another action uses held: it fires
# on the release, and only when let go before HOLD_SECONDS — firing on the
# press would make every hold do both actions.
TAP = "tap"

# The exception to TAP: the overlay's press, when the action held on the
# same key/combination is Team Kits, still opens the menu at once (a tap
# must not wait for its release) and the hold then moves the open menu to
# Team Kits — opening the menu is the first half of going there anyway.
_PRESS_THEN_HOLD = {OVERLAY_MENU: TEAM_KITS}


@dataclass(frozen=True)
class KeyBinding:
    """A keyboard key (virtual-key code, 0 = not set) and whether it has to
    be held HOLD_SECONDS before it fires."""

    vk: int = 0
    hold: bool = False


@dataclass(frozen=True)
class PadBinding:
    """A gamepad button combination (XInput wButtons bits, 0 = not set) and
    whether it has to be held HOLD_SECONDS before it fires."""

    buttons: int = 0
    hold: bool = False


_NO_KEY = KeyBinding()
_NO_PAD = PadBinding()

DEFAULT_KEYS = {
    OVERLAY_MENU: KeyBinding(VK_F12),
    TEAM_KITS: KeyBinding(VK_F12, True),
    KIT_HOME_PREV: KeyBinding(VK_F7),
    KIT_HOME_NEXT: KeyBinding(VK_F8),
    KIT_AWAY_PREV: KeyBinding(VK_F9),
    KIT_AWAY_NEXT: KeyBinding(VK_F10),
    KIT_TYPE: KeyBinding(VK_F11),
}
DEFAULT_PADS = {
    OVERLAY_MENU: PadBinding(XINPUT_GAMEPAD_START, True),
    TEAM_KITS: PadBinding(XINPUT_GAMEPAD_BACK, True),
}


def key_problem(vk: int) -> str | None:
    if vk in MENU_NAV_VKS:
        return RESERVED
    if vk not in BINDABLE_VKS:
        return UNSUPPORTED
    return None


def pad_problem(action: str, buttons: int) -> str | None:
    if not buttons or buttons & ~PAD_ALL_BUTTONS:
        return UNSUPPORTED
    if action in MENU_ACTIONS and not buttons & PAD_MENU_FREE_BUTTONS:
        return NEEDS_FREE_BUTTON
    return None


class InputBindings:
    """One KeyBinding and one PadBinding per action. No two actions share a
    key (or a combination) with the same Hold setting; with different ones
    they can (see TAP). Treat as immutable: with_key()/with_pad() return a
    new object."""

    def __init__(
        self, keys: Mapping[str, KeyBinding] | None = None, pads: Mapping[str, PadBinding] | None = None,
    ) -> None:
        keys = DEFAULT_KEYS if keys is None else keys
        pads = DEFAULT_PADS if pads is None else pads
        self._keys = {action: keys.get(action, _NO_KEY) for action in ACTIONS}
        self._pads = {action: pads.get(action, _NO_PAD) for action in ACTIONS}
        # Read every ~10ms by app_overlay's hotkey poll thread: every bound
        # key, once even when two actions share it.
        self.hotkey_poll_vks = tuple(dict.fromkeys(b.vk for b in self._keys.values() if b.vk))
        # Read by the keyboard hook while the menu is open: the menu's own
        # keys, which it eats and tracks like the navigation keys.
        self.menu_hook_vks = frozenset(self._keys[action].vk for action in MENU_ACTIONS if self._keys[action].vk)
        self.kit_vks = frozenset(self._keys[action].vk for action in KIT_ACTIONS if self._keys[action].vk)
        self.kit_keys_bound = bool(self.kit_vks)
        self.kit_pads_bound = any(self._pads[action].buttons for action in KIT_ACTIONS)
        self._key_modes = _modes({action: (b.vk, b.hold) for action, b in self._keys.items()})
        self._pad_modes = _modes({action: (b.buttons, b.hold) for action, b in self._pads.items()})
        self._pad_others = {
            action: tuple(
                self._pads[other].buttons for other in ACTIONS if other != action and self._pads[other].buttons
            )
            for action in ACTIONS
        }

    @classmethod
    def defaults(cls) -> InputBindings:
        return cls()

    def key(self, action: str) -> KeyBinding:
        return self._keys[action]

    def pad(self, action: str) -> PadBinding:
        return self._pads[action]

    def key_mode(self, action: str) -> str:
        """PRESS, TAP or HOLD: when `action`'s key fires."""
        return self._key_modes[action]

    def pad_mode(self, action: str) -> str:
        return self._pad_modes[action]

    def pad_state(self, action: str, seen_buttons: int, raw_buttons: int) -> tuple[bool, bool]:
        """(seen, held) of `action`'s combination for BindingTracker.update:
        down at some point since the last tick (`seen_buttons`, the gamepad
        poll thread's latch) and down right now (`raw_buttons`) — each as
        combo_held decides, against every other action's combination."""
        buttons, others = self._pads[action].buttons, self._pad_others[action]
        return combo_held(buttons, seen_buttons | raw_buttons, others), combo_held(buttons, raw_buttons, others)

    def with_key(self, action: str, binding: KeyBinding) -> InputBindings:
        return InputBindings({**self._keys, action: binding}, self._pads)

    def with_pad(self, action: str, binding: PadBinding) -> InputBindings:
        return InputBindings(self._keys, {**self._pads, action: binding})

    def key_owner(self, binding: KeyBinding, exclude: str = "") -> str | None:
        """The action already bound to `binding` (same key, same Hold),
        other than `exclude`."""
        if not binding.vk:
            return None
        return next((a for a in ACTIONS if a != exclude and self._keys[a] == binding), None)

    def pad_owner(self, binding: PadBinding, exclude: str = "") -> str | None:
        if not binding.buttons:
            return None
        return next((a for a in ACTIONS if a != exclude and self._pads[a] == binding), None)

    def overlay_reachable(self) -> bool:
        return bool(self._keys[OVERLAY_MENU].vk or self._pads[OVERLAY_MENU].buttons)

    def to_dict(self) -> dict:
        return {
            "keyboard": {action: {"vk": k.vk, "hold": k.hold} for action, k in self._keys.items()},
            "gamepad": {action: {"buttons": p.buttons, "hold": p.hold} for action, p in self._pads.items()},
        }

    @classmethod
    def from_dict(cls, data) -> InputBindings:
        """Reads settings.json's INPUT_BINDINGS. A missing action gets its
        default; a hand-edited value that isn't a usable binding, or repeats
        one an earlier action already has (same key/combination, same Hold),
        falls back to the default too (or to not set, when another action
        holds the default)."""
        data = data if isinstance(data, dict) else {}
        keys = _read_bindings(
            data.get("keyboard"), DEFAULT_KEYS, _NO_KEY, "vk", lambda _action, vk: not key_problem(vk),
        )
        pads = _read_bindings(
            data.get("gamepad"), DEFAULT_PADS, _NO_PAD, "buttons",
            lambda action, buttons: not pad_problem(action, buttons),
        )
        bindings = cls(keys, pads)
        if not bindings.overlay_reachable():
            if bindings.key_owner(DEFAULT_KEYS[OVERLAY_MENU]) is None:
                bindings = bindings.with_key(OVERLAY_MENU, DEFAULT_KEYS[OVERLAY_MENU])
            else:
                bindings = bindings.with_pad(OVERLAY_MENU, DEFAULT_PADS[OVERLAY_MENU])
        return bindings

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, InputBindings):
            return NotImplemented
        return self._keys == other._keys and self._pads == other._pads

    def __hash__(self) -> int:
        return hash((tuple(self._keys.items()), tuple(self._pads.items())))


def _modes(bindings: Mapping[str, tuple[int, bool]]) -> dict[str, str]:
    """Each action's PRESS/TAP/HOLD from its (key or combination, hold)."""
    held_by = {code: action for action, (code, hold) in bindings.items() if code and hold}
    modes = {}
    for action, (code, hold) in bindings.items():
        if hold:
            modes[action] = HOLD
        elif code in held_by and held_by[code] != _PRESS_THEN_HOLD.get(action):
            modes[action] = TAP
        else:
            modes[action] = PRESS
    return modes


def _read_bindings(raw, defaults: Mapping, empty, field: str, usable) -> dict:
    """One section ("keyboard"/"gamepad") of from_dict: {action: {field:
    int, "hold": bool}} -> {action: KeyBinding/PadBinding}."""
    raw = raw if isinstance(raw, dict) else {}
    make = type(empty)
    result = {}
    used: set[tuple[int, bool]] = set()
    for action in ACTIONS:
        binding = defaults.get(action, empty)
        entry = raw.get(action)
        if isinstance(entry, dict):
            code, hold = _as_int(entry.get(field)), entry.get("hold")
            if code is not None and isinstance(hold, bool):
                if not code:
                    binding = empty
                elif usable(action, code) and (code, hold) not in used:
                    binding = make(code, hold)
        code = getattr(binding, field)
        if (code, binding.hold) in used:
            binding = empty
        elif code:
            used.add((code, binding.hold))
        result[action] = binding
    return result


def _as_int(value) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0 or value > 0xFFFF:
        return None
    return value


def combo_held(buttons: int, state: int, others: tuple[int, ...] = ()) -> bool:
    """True while every button of `buttons` is down in `state` and no other
    binding's combination that isn't part of this one is fully down too.

    That second rule is what keeps Start-hold (open the menu) and Select-hold
    (Team Kits) from both firing when Start and Select are held together, and
    lets a bigger combination win over the smaller one inside it (with Start
    and Start+Select bound, holding Start+Select is only Start+Select)."""
    if not buttons or state & buttons != buttons:
        return False
    for other in others:
        if other and state & other == other and other & ~buttons:
            return False
    return True


class BindingTracker:
    """Turns one binding, key or gamepad combination, into "fire once per
    press", fed once per input tick the way its mode says: PRESS on the
    press itself, HOLD once held HOLD_SECONDS (once per hold, not again
    until it's released), TAP on a release that came before HOLD_SECONDS.

    `seen` says it went down at some point since the last tick — from the
    poll threads' latches, so a press whose whole down+up cycle fell between
    two ticks still counts — and `held` that it is down right now. Only a
    held -> released -> held change starts a new press, so the keyboard's
    auto-repeat (the hook latches every repeated WM_KEYDOWN) never does."""

    def __init__(self) -> None:
        self.down = False
        self.pressed_at = 0.0
        # This press already did its one thing, or may not do anything more.
        self.spent = False

    def prime(self, held: bool, now: float) -> None:
        """Takes the current state as already seen: what is held right now
        only fires once it's released and pressed again."""
        self.down = held
        self.pressed_at = now
        self.spent = held

    def spend(self) -> None:
        """The press going on now may not fire this binding any more (its
        key/combination's other action used it up)."""
        if self.down:
            self.spent = True

    def update(self, mode: str, seen: bool, held: bool, now: float) -> bool:
        was_down = self.down
        if held and not was_down:
            self.pressed_at = now
            self.spent = False
        self.down = held
        if mode == PRESS:
            return seen and not was_down
        timed_out = held and not self.spent and now - self.pressed_at >= HOLD_SECONDS
        if mode == HOLD:
            if timed_out:
                self.spent = True
            return timed_out
        # TAP: held too long is the hold binding's turn.
        if timed_out:
            self.spent = True
        if held:
            return False
        if was_down:
            return not self.spent
        return seen


def key_name(vk: int, tr: Translate) -> str:
    if 0x70 <= vk <= 0x87:
        return f"F{vk - 0x6F}"
    if 0x30 <= vk <= 0x39 or 0x41 <= vk <= 0x5A:
        return chr(vk)
    if 0x60 <= vk <= 0x69:
        return f"Num {vk - 0x60}"
    if vk in _NUMPAD_SYMBOLS:
        return f"Num {_NUMPAD_SYMBOLS[vk]}"
    if vk in _WORD_KEYS:
        return tr(_WORD_KEYS[vk])
    return _layout_char(vk) or f"0x{vk:02X}"


def _layout_char(vk: int) -> str:
    """What an OEM key types on the current keyboard layout (Ñ, ´, ...)."""
    try:
        code = int(ctypes.windll.user32.MapVirtualKeyW(vk, 2)) & 0x7FFFFFFF  # MAPVK_VK_TO_CHAR; dead keys set the top bit
    except Exception:
        return ""
    if code < 0x21 or code > 0x10FFFF:
        return ""
    return chr(code).upper()


def pad_name(buttons: int, tr: Translate) -> str:
    return "+".join(label or tr(key) for bit, label, key in _PAD_BUTTONS if buttons & bit)


def key_binding_name(binding: KeyBinding, tr: Translate) -> str:
    name = key_name(binding.vk, tr)
    return tr("controls.hold", name=name) if binding.hold else name


def pad_binding_name(binding: PadBinding, tr: Translate) -> str:
    name = pad_name(binding.buttons, tr)
    return tr("controls.hold", name=name) if binding.hold else name


def action_shortcut_name(bindings: InputBindings, action: str, tr: Translate) -> str:
    """The key for `action`, or its gamepad combination without one, or a dash
    — for the short in-game legends (the kit carousel's hint line)."""
    if bindings.key(action).vk:
        return key_binding_name(bindings.key(action), tr)
    if bindings.pad(action).buttons:
        return pad_binding_name(bindings.pad(action), tr)
    return "—"


def _action_ways(bindings: InputBindings, action: str, tr: Translate) -> str:
    ways = []
    if bindings.key(action).vk:
        ways.append(key_binding_name(bindings.key(action), tr))
    if bindings.pad(action).buttons:
        ways.append(pad_binding_name(bindings.pad(action), tr))
    return " / ".join(ways) or "—"


def overlay_help_text(bindings: InputBindings, tr: Translate) -> str:
    """The main window's help line (help.overlay_toggle): every way to open
    the overlay and to get to Team Kits with the current bindings."""
    return tr(
        "help.overlay_toggle",
        open=_action_ways(bindings, OVERLAY_MENU, tr),
        team_kits=_action_ways(bindings, TEAM_KITS, tr),
    )


def kit_hotkey_hint(bindings: InputBindings, tr: Translate) -> str:
    """The kit carousel's control legend (kitsimple.hotkey_hint)."""
    return tr("kitsimple.hotkey_hint", **{action: action_shortcut_name(bindings, action, tr) for action in KIT_ACTIONS})
