"""Which XInput player is which, for the Gamepads tab's Xbox controllers card.

The card lists the four XInput players and has to tell a real Xbox pad from
one of this app's own virtual pads (gamepad_bridge_runtime.py). Nothing hands
that over directly: the index ViGEmBus reports for a virtual pad is the LED
number the Xbox 360 driver gave it, and that driver only counts Xbox 360-class
devices. An Xbox One/Series pad sits on a different driver, so with one of
those connected the virtual pad is "0" for ViGEmBus while XInput has it as
player 2 (reported live 2026-10-05: the card labelled the real Xbox pad as the
Switch pad's virtual one, and the other way round).

So the card works it out from what XInput itself says:
- identity: a virtual pad always reports ViGEm's Xbox 360 VID/PID, which rules
  out every player that reports something else (read_player_identity);
- input: a virtual pad's buttons are whatever its slot just sent, so a player
  that keeps showing exactly those buttons is that slot's pad
  (VirtualPadMatcher.observe) -- the only thing that separates a virtual pad
  from a real wired Xbox 360 pad, or two virtual pads from each other.

Everything here runs on the Tk thread.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
from typing import Iterable

from .gamepad_bridge_runtime import _VIGEM_X360_VID_PID
from .win32_types import XINPUT_CAPABILITIES_EX, XINPUT_SUCCESS

_CAPABILITIES_EX_ORDINAL = 108
# XInputGetState never reports the Guide button, so a virtual pad that has it
# held still reads back without it.
_GUIDE_BUTTON = 0x0400
# Sightings of "this player shows exactly the buttons this slot sent" before
# the pair is trusted. One could be two people pressing the same button in the
# very instant the virtual pad's own state hadn't caught up yet.
SIGHTINGS_TO_CONFIRM = 2
# Consecutive looks at a confirmed pair where the player did NOT show the
# slot's buttons before it is dropped (Windows moved the pad to another
# player). Well above the one-look lag around a press or release.
MISSES_TO_FORGET = 10


def bind_capabilities_ex(dll):
    """XInputGetCapabilitiesEx from an already-loaded xinput1_4.dll, or None.
    It has no name, only export ordinal 108, and exists in xinput1_4 alone --
    don't call this for xinput1_3/xinput9_1_0. It is XInputGetCapabilities
    plus the device's USB vendor/product id (SDL identifies XInput pads with
    it the same way)."""
    try:
        function = dll[_CAPABILITIES_EX_ORDINAL]
        function.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(XINPUT_CAPABILITIES_EX)]
        function.restype = wintypes.DWORD
    except Exception:
        return None
    return function


def read_player_identity(capabilities_ex, index: int) -> tuple[int, int] | None:
    """(vendor id, product id) of the pad holding an XInput player, or None
    when it can't be told (no xinput1_4, or the call failed)."""
    if capabilities_ex is None:
        return None
    capabilities = XINPUT_CAPABILITIES_EX()
    try:
        if int(capabilities_ex(1, index, 0, ctypes.byref(capabilities))) != XINPUT_SUCCESS:
            return None
    except Exception:
        return None
    return int(capabilities.VendorId), int(capabilities.ProductId)


def may_be_virtual_pad(identity: tuple[int, int] | None) -> bool:
    """False only for a pad that is certainly real. A real wired Xbox 360 pad
    (and the many pads that clone its ids) reports the same identity as a
    virtual one, and an unknown identity could be anything."""
    return identity is None or identity == _VIGEM_X360_VID_PID


class VirtualPadMatcher:
    """Works out which XInput player each slot's virtual pad is."""

    def __init__(self) -> None:
        self._confirmed: dict[int, int] = {}  # slot -> player
        self._sightings: dict[int, tuple[int, int]] = {}  # slot -> (player, how many)
        self._misses: dict[int, int] = {}

    def observe(self, sent: dict[int, int], players: dict[int, int]) -> bool:
        """One look at the pads. `sent` is {slot: buttons last sent to its
        virtual pad}, one entry per slot that has a virtual pad; `players` is
        {player: buttons XInput reports}, for the players that may be a
        virtual pad. Returns True when a pair was confirmed or dropped.

        Only buttons are compared: they read back exactly, whereas a moving
        stick differs between the two samples. A slot with nothing pressed
        says nothing, and neither does one sending the same buttons as
        another slot."""
        before = dict(self._confirmed)
        self._confirmed = {s: p for s, p in self._confirmed.items() if s in sent and p in players}
        self._sightings = {s: v for s, v in self._sightings.items() if s in sent and v[0] in players}
        self._misses = {s: n for s, n in self._misses.items() if s in self._confirmed}
        pressed = {slot: buttons & ~_GUIDE_BUTTON for slot, buttons in sent.items()}
        for slot, buttons in pressed.items():
            if not buttons or sum(1 for other in pressed.values() if other == buttons) > 1:
                continue
            showing = [player for player, shown in players.items() if shown == buttons]
            confirmed = self._confirmed.get(slot)
            if confirmed is not None:
                if confirmed in showing:
                    self._misses[slot] = 0
                else:
                    self._misses[slot] = self._misses.get(slot, 0) + 1
                    if self._misses[slot] >= MISSES_TO_FORGET:
                        del self._confirmed[slot]
                        del self._misses[slot]
                continue
            taken = set(self._confirmed.values())
            showing = [player for player in showing if player not in taken]
            if len(showing) != 1:
                continue
            player = showing[0]
            seen_player, count = self._sightings.get(slot, (player, 0))
            count = count + 1 if seen_player == player else 1
            if count >= SIGHTINGS_TO_CONFIRM:
                self._confirmed[slot] = player
                self._sightings.pop(slot, None)
            else:
                self._sightings[slot] = (player, count)
        return self._confirmed != before

    def resolve(self, slots: dict[int, int | None], candidates: Iterable[int]) -> dict[int, int]:
        """{player: slot} as far as it can be told right now. `slots` is
        {slot: driver index} for the slots that have a virtual pad,
        `candidates` the players that may be one.

        Pairs confirmed by input come first. The rest are only paired when
        there are exactly as many candidates left as virtual pads -- then
        every one of them IS a virtual pad, and with a single one (by far the
        common case) there is nothing left to guess. Several are handed out
        in driver-index order: that index is not the XInput player (see the
        module docstring) but both are given out in connection order, so it
        usually ranks them right, and input corrects it when it doesn't.
        Otherwise a real pad that looks like a virtual one is among them, and
        which is which stays open until input settles it."""
        candidates = sorted(candidates)
        resolved = {player: slot for slot, player in self._confirmed.items() if slot in slots and player in candidates}
        open_players = [player for player in candidates if player not in resolved]
        claimed = set(resolved.values())
        open_slots = sorted(
            (slot for slot in slots if slot not in claimed),
            key=lambda slot: (slots[slot] is None, slots[slot] or 0, slot),
        )
        if len(open_players) == len(open_slots):
            resolved.update(zip(open_players, open_slots))
        return resolved
