from __future__ import annotations

import time
import tkinter as tk
from tkinter import ttk

from .dialogs import BaseDialog
from .gamepad_bridge_runtime import GamepadBridgeRuntime, resolve_mapped_state

# ~30Hz -- fast enough that a press/release reads as instant to the eye.
# Each poll only reads the snapshot GamepadBridgeRuntime's SDL thread
# publishes; this dialog never calls pygame/SDL itself (SDL calls from
# several threads crashed the app on pad hot-plug, see that module).
POLL_MS = 33
# The first polls only ask the SDL thread to open the pad -- don't flash
# "not responding" before it has had a chance to.
FIRST_STATE_GRACE_MS = 800

_XBOX_BUTTON_LAYOUT: tuple[tuple[str, str], ...] = (
    ("XUSB_GAMEPAD_A", "A"),
    ("XUSB_GAMEPAD_B", "B"),
    ("XUSB_GAMEPAD_X", "X"),
    ("XUSB_GAMEPAD_Y", "Y"),
    ("XUSB_GAMEPAD_LEFT_SHOULDER", "LB"),
    ("XUSB_GAMEPAD_RIGHT_SHOULDER", "RB"),
    ("XUSB_GAMEPAD_BACK", "Back"),
    ("XUSB_GAMEPAD_START", "Start"),
    ("XUSB_GAMEPAD_LEFT_THUMB", "LS"),
    ("XUSB_GAMEPAD_RIGHT_THUMB", "RS"),
)

_DPAD_LAYOUT: tuple[tuple[str, str], ...] = (
    ("XUSB_GAMEPAD_DPAD_UP", "Up"),
    ("XUSB_GAMEPAD_DPAD_DOWN", "Down"),
    ("XUSB_GAMEPAD_DPAD_LEFT", "Left"),
    ("XUSB_GAMEPAD_DPAD_RIGHT", "Right"),
)

# Only axes 0-3 have an assumed meaning today (_apply_sticks' own
# assumption: 0/1 = left stick X/Y, 2/3 = right stick X/Y). Anything past
# that has no assigned meaning in this codebase -- on some controllers/
# drivers that's exactly where an analog trigger (ZL/ZR) shows up instead
# of as a digital button, which is worth knowing if a button that should
# light up in the raw panel never does.
_AXIS_LABELS = {
    0: "left stick X",
    1: "left stick Y",
    2: "right stick X",
    3: "right stick Y",
}


class GamepadTestDialog(BaseDialog):
    """Live controller-test panel opened from a Gamepads-tab slot's "Test"
    button. Shows two things side by side, both refreshed ~30 times/sec:

    1. Raw physical input -- exactly what this app reads from the device
       via pygame.joystick, independent of any profile/mapping. If a
       button lights up here without the user touching anything, the
       problem is upstream of this app entirely (the physical device/driver
       itself, or another process also reading it) -- not the translation
       logic or FIFA's own input handling.
    2. Translated Xbox output -- what the virtual pad (and therefore FIFA)
       is supposed to see, computed live from the raw input via
       gamepad_bridge_runtime.resolve_mapped_state() using the same
       button-map tables the real bridge thread uses. Deliberately computed
       as plain data rather than driving a real vg.VX360Gamepad(), so this
       works even without ViGEmBus installed and never contends with a
       slot's own live bridge thread for the same virtual-pad handle.

    Added 2026-09-24 after a live report of "buttons pressing themselves in
    FIFA" -- this dialog's job is to let the user (and future debugging)
    tell apart "the raw device itself is glitching" from "translation looks
    fine here, so whatever FIFA is doing is happening outside this app"
    (e.g. FIFA still reading the raw physical device directly -- see
    hidhide_runtime.py and this feature's own plan/CLAUDE.md history)."""

    def __init__(
        self,
        master: tk.Misc,
        gamepad_bridge: GamepadBridgeRuntime,
        device_guid: str,
        device_name: str,
        profile_name: str,
        slot_index: int | None = None,
    ) -> None:
        super().__init__(master, "dialog.gamepad_test.title")
        self.success = getattr(master, "success", "#7ee787")
        self._bridge = gamepad_bridge
        self._device_guid = device_guid
        # Which slot's Test button opened this. The GUID only names the
        # model, so it can't tell two identical pads apart -- the slot is
        # what says which one to show.
        self._slot_index = slot_index
        self._opened_at = time.monotonic()
        self._profile_name = profile_name
        self._poll_job: str | None = None
        self._closed = False

        # "Slot 2 - Pro Controller": with identical pads the model name alone
        # doesn't say which slot's pad this dialog is showing.
        heading = device_name
        if slot_index is not None:
            heading = f'{self.tr("label.gamepads.slot", n=slot_index + 1)} - {device_name}'
        self.title(self.tr("dialog.gamepad_test.title", device=heading))
        # Taller than the driver-button dialogs above -- the raw panel alone
        # stacks up to ~20 button lights (5 rows), the D-pad row, and up to
        # 6-8 lines of per-axis text (one line per raw axis the device
        # reports). Reported live 2026-09-24: 560px cut the axes text off
        # for a 6-axis pad (Switch Pro) at the default size.
        self._set_geometry(760, 700, 660, 620)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        topbar = tk.Frame(self, bg=self.bg)
        topbar.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 8))
        tk.Label(
            topbar,
            text=heading,
            bg=self.bg,
            fg=self.fg,
            font=("Bahnschrift", 14, "bold"),
            anchor="w",
        ).pack(anchor="w")
        self._status_label = tk.Label(
            topbar,
            text="",
            bg=self.bg,
            fg=self.muted,
            font=("Bahnschrift", 9),
            anchor="w",
        )
        self._status_label.pack(anchor="w", pady=(2, 0))

        body = tk.Frame(self, bg=self.bg)
        body.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 8))
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        raw_card = self._card(body, self.tr("dialog.gamepad_test.raw_input"), self.tr("dialog.gamepad_test.raw_input_subtitle"))
        raw_card.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        mapped_card = self._card(
            body,
            self.tr("dialog.gamepad_test.mapped_output"),
            self.tr("dialog.gamepad_test.mapped_output_subtitle", profile=profile_name),
        )
        mapped_card.grid(row=0, column=1, sticky="nsew", padx=(6, 0))

        self._raw_button_lights: list[tk.Label] = []
        raw_buttons_wrap = tk.Frame(raw_card, bg=self.card)
        raw_buttons_wrap.pack(fill="x", padx=12, pady=(0, 8))
        self._raw_buttons_wrap = raw_buttons_wrap

        self._raw_hat_lights: dict[str, tk.Label] = {}
        hat_wrap = tk.Frame(raw_card, bg=self.card)
        hat_wrap.pack(fill="x", padx=12, pady=(4, 8))
        tk.Label(hat_wrap, text=self.tr("dialog.gamepad_test.dpad"), bg=self.card, fg=self.muted, font=("Bahnschrift", 9)).pack(anchor="w")
        hat_row = tk.Frame(hat_wrap, bg=self.card)
        hat_row.pack(anchor="w", pady=(4, 0))
        for label_text in ("Up", "Down", "Left", "Right"):
            light = self._make_light(hat_row, label_text)
            light.pack(side="left", padx=(0, 6))
            self._raw_hat_lights[label_text] = light

        axes_wrap = tk.Frame(raw_card, bg=self.card)
        axes_wrap.pack(fill="x", padx=12, pady=(4, 12))
        tk.Label(axes_wrap, text=self.tr("dialog.gamepad_test.axes"), bg=self.card, fg=self.muted, font=("Bahnschrift", 9)).pack(anchor="w")
        self._axes_label = tk.Label(
            axes_wrap,
            text="",
            bg=self.card,
            fg=self.fg,
            font=("Consolas", 9),
            anchor="w",
            justify="left",
            wraplength=300,
        )
        self._axes_label.pack(anchor="w", pady=(4, 0))
        tk.Label(
            axes_wrap,
            text=self.tr("dialog.gamepad_test.axes_note"),
            bg=self.card,
            fg=self.muted,
            font=("Bahnschrift", 8),
            anchor="w",
            justify="left",
            wraplength=300,
        ).pack(anchor="w", pady=(4, 0))

        # Shown instead of the translated output while this slot's virtual
        # pad is off (see _virtual_pad_enabled).
        self._virtual_disabled_label = tk.Label(
            mapped_card,
            text=self.tr("dialog.gamepad_test.virtual_disabled"),
            bg=self.card,
            fg=self.muted,
            font=("Bahnschrift", 9),
            anchor="w",
            justify="left",
            wraplength=300,
        )
        self._virtual_disabled_shown = False

        self._mapped_button_lights: dict[str, tk.Label] = {}
        mapped_buttons_wrap = tk.Frame(mapped_card, bg=self.card)
        self._mapped_first_widget = mapped_buttons_wrap
        mapped_buttons_wrap.pack(fill="x", padx=12, pady=(0, 8))
        _MAPPED_BUTTONS_PER_ROW = 5
        for i, (xusb_name, label_text) in enumerate(_XBOX_BUTTON_LAYOUT):
            light = self._make_light(mapped_buttons_wrap, label_text)
            light.grid(row=i // _MAPPED_BUTTONS_PER_ROW, column=i % _MAPPED_BUTTONS_PER_ROW, padx=3, pady=3)
            self._mapped_button_lights[xusb_name] = light

        mapped_dpad_wrap = tk.Frame(mapped_card, bg=self.card)
        mapped_dpad_wrap.pack(fill="x", padx=12, pady=(4, 8))
        tk.Label(mapped_dpad_wrap, text=self.tr("dialog.gamepad_test.dpad"), bg=self.card, fg=self.muted, font=("Bahnschrift", 9)).pack(anchor="w")
        mapped_dpad_row = tk.Frame(mapped_dpad_wrap, bg=self.card)
        mapped_dpad_row.pack(anchor="w", pady=(4, 0))
        for xusb_name, label_text in _DPAD_LAYOUT:
            light = self._make_light(mapped_dpad_row, label_text)
            light.pack(side="left", padx=(0, 6))
            self._mapped_button_lights[xusb_name] = light

        sticks_wrap = tk.Frame(mapped_card, bg=self.card)
        sticks_wrap.pack(fill="x", padx=12, pady=(4, 12))
        tk.Label(
            sticks_wrap,
            text=f'{self.tr("dialog.gamepad_test.left_stick")} / {self.tr("dialog.gamepad_test.right_stick")} / {self.tr("dialog.gamepad_test.triggers")}',
            bg=self.card,
            fg=self.muted,
            font=("Bahnschrift", 9),
        ).pack(anchor="w")
        self._sticks_label = tk.Label(
            sticks_wrap,
            text="",
            bg=self.card,
            fg=self.fg,
            font=("Consolas", 9),
            anchor="w",
            justify="left",
        )
        self._sticks_label.pack(anchor="w", pady=(4, 0))

        bottom = tk.Frame(self, bg=self.bg)
        bottom.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 14))
        ttk.Button(bottom, text=self.tr("button.gamepad_test.close"), command=self.destroy).pack(side="right")

        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self._built_raw_lights = False
        self._poll()

    def _make_light(self, parent: tk.Misc, text: str) -> tk.Label:
        return tk.Label(
            parent,
            text=text,
            bg=self.card_soft,
            fg=self.muted,
            font=("Bahnschrift", 9, "bold"),
            width=5,
            height=2,
            relief="flat",
            highlightthickness=1,
            highlightbackground="#243654",
        )

    def _set_light(self, light: tk.Label, pressed: bool) -> None:
        if pressed:
            light.configure(bg=self.success, fg="#0b1220")
        else:
            light.configure(bg=self.card_soft, fg=self.muted)

    _RAW_BUTTONS_PER_ROW = 5

    def _ensure_raw_button_lights(self, count: int) -> None:
        if self._built_raw_lights and len(self._raw_button_lights) == count:
            return
        for widget in self._raw_button_lights:
            widget.destroy()
        self._raw_button_lights = []
        for i in range(count):
            light = self._make_light(self._raw_buttons_wrap, str(i))
            light.grid(row=i // self._RAW_BUTTONS_PER_ROW, column=i % self._RAW_BUTTONS_PER_ROW, padx=3, pady=3)
            self._raw_button_lights.append(light)
        self._built_raw_lights = True

    def _virtual_pad_enabled(self) -> bool:
        """Whether this slot's virtual pad is switched on. Read every poll so
        ticking/unticking the slot's checkbox while the dialog is open takes
        effect at once. Opened without a slot there is nothing to ask."""
        if self._slot_index is None:
            return True
        try:
            return bool(self._bridge.get_slot_snapshot(self._slot_index)["enabled"])
        except Exception:
            return True

    def _show_virtual_disabled(self, disabled: bool) -> None:
        if disabled == self._virtual_disabled_shown:
            return
        self._virtual_disabled_shown = disabled
        if disabled:
            self._virtual_disabled_label.pack(anchor="w", padx=12, pady=(0, 8), before=self._mapped_first_widget)
        else:
            self._virtual_disabled_label.pack_forget()

    def _poll(self) -> None:
        state = self._bridge.read_raw_state(self._device_guid, self._slot_index)
        if state is None:
            if (time.monotonic() - self._opened_at) * 1000 < FIRST_STATE_GRACE_MS:
                status_key = None
            else:
                status_key = (
                    "status.gamepad_test.busy"
                    if self._bridge.is_device_busy(self._device_guid)
                    else "status.gamepad_test.disconnected"
                )
            self._status_label.configure(text=self.tr(status_key) if status_key else "")
        else:
            self._status_label.configure(text="")
            self._ensure_raw_button_lights(len(state["buttons"]))
            for light, pressed in zip(self._raw_button_lights, state["buttons"]):
                self._set_light(light, pressed)
            hat_x, hat_y = state["hats"][0] if state["hats"] else (0, 0)
            self._set_light(self._raw_hat_lights["Up"], hat_y > 0)
            self._set_light(self._raw_hat_lights["Down"], hat_y < 0)
            self._set_light(self._raw_hat_lights["Left"], hat_x < 0)
            self._set_light(self._raw_hat_lights["Right"], hat_x > 0)
            axes_text = "\n".join(
                f"axis {i} ({_AXIS_LABELS.get(i, 'unmapped -- could be an analog trigger')}): {value:+.3f}"
                for i, value in enumerate(state["axes"])
            )
            self._axes_label.configure(text=axes_text or "-")

            if self._virtual_pad_enabled():
                self._show_virtual_disabled(False)
                # Pads SDL recognizes publish the exact standard-Xbox state
                # the bridge sends; only unrecognized ones fall back to the
                # raw map.
                mapped = state.get("mapped") or resolve_mapped_state(state, self._profile_name)
                for xusb_name, light in self._mapped_button_lights.items():
                    self._set_light(light, mapped["buttons"].get(xusb_name, False))
                lx, ly = mapped["left_stick"]
                rx, ry = mapped["right_stick"]
                self._sticks_label.configure(
                    text=(
                        f"LS: {lx:+.2f}, {ly:+.2f}    RS: {rx:+.2f}, {ry:+.2f}\n"
                        f"LT: {mapped['left_trigger']:.2f}    RT: {mapped['right_trigger']:.2f}"
                    )
                )
            else:
                self._show_virtual_disabled(True)
                for light in self._mapped_button_lights.values():
                    self._set_light(light, False)
                self._sticks_label.configure(text="")

        if not self._closed:
            self._poll_job = self.after(POLL_MS, self._poll)

    def destroy(self) -> None:
        self._closed = True
        if self._poll_job is not None:
            try:
                self.after_cancel(self._poll_job)
            except Exception:
                pass
            self._poll_job = None
        super().destroy()
