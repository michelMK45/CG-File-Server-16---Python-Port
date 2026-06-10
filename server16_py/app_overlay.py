from __future__ import annotations

import ctypes
import sys
import time
import threading
from ctypes import wintypes
from pathlib import Path
from time import perf_counter

import psutil

from .win32_types import (
    RECT, POINT, MSG, MSLLHOOKSTRUCT, KBDLLHOOKSTRUCT, XINPUT_STATE, XINPUT_GAMEPAD,
    GWL_EXSTYLE, WS_EX_TOOLWINDOW, WS_EX_NOACTIVATE, HWND_TOPMOST,
    SW_RESTORE, SWP_NOMOVE, SWP_NOSIZE, SWP_NOACTIVATE, SWP_SHOWWINDOW,
    VK_F12, VK_ESCAPE, VK_LEFT, VK_UP, VK_RIGHT, VK_DOWN,
    VK_PRIOR, VK_NEXT, VK_HOME, VK_END, VK_MENU, VK_RETURN,
    KEYEVENTF_KEYUP,
    WH_MOUSE_LL, WH_KEYBOARD_LL, HC_ACTION,
    WM_LBUTTONDOWN, WM_LBUTTONUP, WM_RBUTTONDOWN, WM_RBUTTONUP,
    WM_MBUTTONDOWN, WM_MBUTTONUP, WM_MOUSEWHEEL,
    WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP, WM_QUIT,
    XINPUT_GAMEPAD_START, XINPUT_GAMEPAD_BACK,
    XINPUT_GAMEPAD_LEFT_SHOULDER, XINPUT_GAMEPAD_RIGHT_SHOULDER,
    XINPUT_GAMEPAD_A, XINPUT_GAMEPAD_B, XINPUT_SUCCESS,
    XINPUT_GAMEPAD_DPAD_UP, XINPUT_GAMEPAD_DPAD_DOWN,
    _D3D_MENU_RATIO_W, _D3D_MENU_RATIO_H, _D3D_MENU_MIN_W, _D3D_MENU_MIN_H,
    _D3D_MENU_VIEW_MARGIN, _D3D_MENU_TAB_H, _D3D_MENU_DASH_MIN_H,
    _D3D_MENU_DASH_MAX_H, _D3D_MENU_ITEM_H,
)
from .file_tools import discover_stadium_names


class OverlayMixin:
    """D3D in-game overlay menu, input hooks, and FIFA window tracking — part of Server16App via multiple inheritance."""

    def overlay_loop(self) -> None:
        self._overlay_job = None
        if self._closing:
            return
        try:
            self._sync_d3d_menu_input()
        except Exception as exc:
            self.log("Overlay loop error", exc, exc_info=sys.exc_info())
        if not self._closing:
            self._overlay_job = self.after(80, self.overlay_loop)

    def _refresh_fifa_hwnd_if_needed(self, now: float) -> None:
        hwnd = self._fifa_hwnd
        if hwnd and not self.user32.IsWindow(hwnd):
            self._fifa_hwnd = 0
            self._fifa_hwnd_checked_at = 0.0
            hwnd = 0
        if not hwnd and now - self._fifa_hwnd_checked_at >= 1.0:
            self._fifa_hwnd_checked_at = now
            self._fifa_hwnd = self._find_fifa_window_handle()

    def _sync_d3d_menu_input(self) -> None:
        """Manages the D3D in-game menu (F12 / Hold Start for 0.6s)."""
        if not self._ensure_d3d_overlay_injected(log_errors=False):
            return
        inj = self._d3d_injector
        if inj is None:
            return
        if not self.show_overlay_var.get():
            if self._d3d_menu_visible:
                self._d3d_menu_visible = False
                self._overlay_wizard_phase = None
                self._overlay_wizard_stadium = None
                self._uninstall_mouse_wheel_hook()
                self._uninstall_keyboard_hook()
                self._publish_overlay_menu_state()
            return
        now = perf_counter()
        self._refresh_fifa_hwnd_if_needed(now)
        foreground = int(self.user32.GetForegroundWindow() or 0)
        overlay_hwnd = 0
        overlay_vw = 0
        overlay_vh = 0
        try:
            overlay_hwnd, overlay_vw, overlay_vh = inj.get_menu_metrics()
        except Exception:
            overlay_hwnd = 0
        fifa_fg = (foreground == self._fifa_hwnd and self._fifa_hwnd != 0)
        overlay_fg = (foreground == int(overlay_hwnd) and int(overlay_hwnd) != 0)
        menu_input_fg = fifa_fg or overlay_fg

        if not self._d3d_menu_visible:
            self._overlay_blocked_key_down.clear()

        if overlay_vw > 0 and overlay_vh > 0:
            self._overlay_visible_rows = self._compute_overlay_visible_rows(float(overlay_vw), float(overlay_vh))

        f12_down = self._is_overlay_key_down(VK_F12, menu_input_fg)
        key_up_down = self._is_overlay_key_down(VK_UP, menu_input_fg)
        key_down_down = self._is_overlay_key_down(VK_DOWN, menu_input_fg)
        key_left_down = self._is_overlay_key_down(VK_LEFT, menu_input_fg)
        key_right_down = self._is_overlay_key_down(VK_RIGHT, menu_input_fg)
        key_escape_down = self._is_overlay_key_down(VK_ESCAPE, menu_input_fg)
        key_pgup_down = self._is_overlay_key_down(VK_PRIOR, menu_input_fg)
        key_pgdn_down = self._is_overlay_key_down(VK_NEXT, menu_input_fg)
        key_home_down = self._is_overlay_key_down(VK_HOME, menu_input_fg)
        key_end_down = self._is_overlay_key_down(VK_END, menu_input_fg)
        key_enter_down = self._is_overlay_key_down(VK_RETURN, menu_input_fg)
        gamepad_buttons, _stick_rx, stick_ry = self._get_gamepad_snapshot()
        start_down = bool(gamepad_buttons & XINPUT_GAMEPAD_START)
        back_down = bool(gamepad_buttons & XINPUT_GAMEPAD_BACK)
        left_shoulder_down = bool(gamepad_buttons & XINPUT_GAMEPAD_LEFT_SHOULDER)
        right_shoulder_down = bool(gamepad_buttons & XINPUT_GAMEPAD_RIGHT_SHOULDER)
        a_down = bool(gamepad_buttons & XINPUT_GAMEPAD_A)
        b_down = bool(gamepad_buttons & XINPUT_GAMEPAD_B)

        prev_buttons = self._overlay_gp_prev_buttons
        start_edge = start_down and not bool(prev_buttons & XINPUT_GAMEPAD_START)
        back_edge = back_down and not bool(prev_buttons & XINPUT_GAMEPAD_BACK)
        left_shoulder_edge = left_shoulder_down and not bool(prev_buttons & XINPUT_GAMEPAD_LEFT_SHOULDER)
        right_shoulder_edge = right_shoulder_down and not bool(prev_buttons & XINPUT_GAMEPAD_RIGHT_SHOULDER)

        if start_edge:
            self._overlay_gp_start_pressed_at = now
            self._overlay_gp_start_hold_latched = False
        if back_edge:
            self._overlay_gp_back_pressed_at = now
        if left_shoulder_edge:
            self._overlay_gp_left_pressed_at = now
        if right_shoulder_edge:
            self._overlay_gp_right_pressed_at = now
        if not start_down:
            self._overlay_gp_start_hold_latched = False

        # Toggle: allowed if FIFA in foreground OR menu already open
        can_toggle = (self._fifa_hwnd != 0 or self._d3d_menu_visible) and now >= self._overlay_toggle_ready_at

        f12_toggle = f12_down and not self._overlay_f12_down
        key_escape_edge = key_escape_down and not self._overlay_escape_down
        key_left_edge = key_left_down and not self._overlay_left_down
        key_right_edge = key_right_down and not self._overlay_right_down
        key_up_edge = key_up_down and not self._overlay_up_down
        key_down_edge = key_down_down and not self._overlay_down_down
        key_pgup_edge = key_pgup_down and not self._overlay_pgup_down
        key_pgdn_edge = key_pgdn_down and not self._overlay_pgdn_down
        key_home_edge = key_home_down and not self._overlay_home_down
        key_end_edge = key_end_down and not self._overlay_end_down
        key_enter_edge = key_enter_down and not getattr(self, "_overlay_enter_down", False)
        a_edge = a_down and not bool(prev_buttons & XINPUT_GAMEPAD_A)
        b_edge = b_down and not bool(prev_buttons & XINPUT_GAMEPAD_B)
        start_hold_toggle = False

        if start_down and not back_down and self._overlay_gp_start_pressed_at > 0.0:
            if (now - self._overlay_gp_start_pressed_at) >= 0.60 and not self._overlay_gp_start_hold_latched:
                start_hold_toggle = True
                self._overlay_gp_start_hold_latched = True

        if (f12_toggle or start_hold_toggle) and can_toggle:
            self._d3d_menu_visible = not self._d3d_menu_visible
            self._overlay_toggle_ready_at = now + 0.22
            self.log(f"D3D menu {'opened' if self._d3d_menu_visible else 'closed'}")
            self._publish_overlay_menu_state()
            if self._d3d_menu_visible:
                self._install_mouse_wheel_hook()
                self._install_keyboard_hook()
                self._overlay_wizard_phase = None
                self._overlay_wizard_stadium = None
                self._overlay_wizard_police = None
                self._overlay_wizard_pitch = None
                self._overlay_selected_scope = None
                self._overlay_scope_phase = True
                self._update_menu_content()
            else:
                self._overlay_wizard_phase = None
                self._overlay_wizard_stadium = None
                self._overlay_wizard_police = None
                self._overlay_wizard_pitch = None
                self._overlay_selected_scope = None
                self._overlay_scope_phase = False
                self._uninstall_mouse_wheel_hook()
                self._uninstall_keyboard_hook()

        if self._d3d_menu_visible and inj is not None:
            try:
                inj.set_dashboard_content(self._build_overlay_dashboard_lines())
            except Exception:
                pass

        if self._d3d_menu_visible and key_escape_edge and now >= self._overlay_toggle_ready_at:
            if self._overlay_wizard_phase is not None:
                self._wizard_back()
                self._overlay_toggle_ready_at = now + 0.22
            elif not self._overlay_scope_phase:
                self._overlay_scope_phase = True
                self._overlay_selected_scope = None
                self._overlay_toggle_ready_at = now + 0.22
                self._update_menu_content()
            else:
                self._d3d_menu_visible = False
                self._overlay_toggle_ready_at = now + 0.22
                self.log("D3D menu closed via keyboard")
                self._uninstall_mouse_wheel_hook()
                self._uninstall_keyboard_hook()
                self._publish_overlay_menu_state()

        if self._d3d_menu_visible and b_edge and now >= self._overlay_toggle_ready_at:
            if self._overlay_wizard_phase is not None:
                self._wizard_back()
                self._overlay_toggle_ready_at = now + 0.22
            elif not self._overlay_scope_phase:
                self._overlay_scope_phase = True
                self._overlay_selected_scope = None
                self._overlay_toggle_ready_at = now + 0.22
                self._update_menu_content()
            else:
                # Latch the close intent; execute only after B is released so
                # XInputEnable(TRUE) fires when B is already up — preventing the
                # game from seeing the same B press that closed the overlay.
                self._overlay_b_close_pending = True

        if self._overlay_b_close_pending and not b_down:
            self._overlay_b_close_pending = False
            if self._d3d_menu_visible:
                self._d3d_menu_visible = False
                self._overlay_toggle_ready_at = now + 0.22
                self.log("D3D menu closed via gamepad B")
                self._uninstall_mouse_wheel_hook()
                self._uninstall_keyboard_hook()
                self._publish_overlay_menu_state()

        if self._d3d_menu_visible and now >= self._overlay_tab_ready_at:
            if left_shoulder_edge or key_left_edge:
                self._set_overlay_tab(self._overlay_tab_index - 1, "gamepad-l")
                self._overlay_tab_ready_at = now + 0.14
            elif right_shoulder_edge or key_right_edge:
                self._set_overlay_tab(self._overlay_tab_index + 1, "gamepad-r")
                self._overlay_tab_ready_at = now + 0.14

        # DPAD up/down: navigate list items (with initial delay + repeat)
        if self._d3d_menu_visible and self._overlay_item_count > 0:
            dpad_up   = bool(gamepad_buttons & XINPUT_GAMEPAD_DPAD_UP)
            dpad_down = bool(gamepad_buttons & XINPUT_GAMEPAD_DPAD_DOWN)
            dpad_up_edge   = dpad_up   and not bool(prev_buttons & XINPUT_GAMEPAD_DPAD_UP)
            dpad_down_edge = dpad_down and not bool(prev_buttons & XINPUT_GAMEPAD_DPAD_DOWN)
            nav_up = dpad_up or key_up_down
            nav_down = dpad_down or key_down_down
            if dpad_up_edge or key_up_edge:
                self._navigate_menu_items(-1)
                self._overlay_nav_repeat_at = now + 0.40
            elif dpad_down_edge or key_down_edge:
                self._navigate_menu_items(1)
                self._overlay_nav_repeat_at = now + 0.40
            elif (nav_up or nav_down) and now >= self._overlay_nav_repeat_at:
                self._navigate_menu_items(-1 if nav_up else 1)
                self._overlay_nav_repeat_at = now + 0.10
            if key_pgup_edge:
                self._navigate_menu_items(-self._overlay_visible_rows)
            elif key_pgdn_edge:
                self._navigate_menu_items(self._overlay_visible_rows)
            elif key_home_edge:
                self._set_menu_selection(0)
            elif key_end_edge:
                self._set_menu_selection(self._overlay_item_count - 1)
            wheel_steps = self._overlay_mouse_wheel_steps
            if wheel_steps:
                self._overlay_mouse_wheel_steps = 0
                self._navigate_menu_items(-wheel_steps * 3)

            abs_ry = abs(int(stick_ry))
            deadzone = 9000
            if abs_ry > deadzone:
                norm = min(1.0, float(abs_ry - deadzone) / float(32767 - deadzone))
                step = max(1, int(round(1.0 + norm * 5.0)))
                interval = max(0.04, 0.18 - (norm * 0.12))
                if now >= self._overlay_gp_rstick_repeat_at:
                    self._navigate_menu_items(-step if stick_ry > 0 else step)
                    self._overlay_gp_rstick_repeat_at = now + interval
            else:
                self._overlay_gp_rstick_repeat_at = now

        if self._d3d_menu_visible and (key_enter_edge or a_edge):
            self._activate_overlay_selected_item("confirm")

        self._overlay_f12_down = f12_down
        self._overlay_up_down = key_up_down
        self._overlay_down_down = key_down_down
        self._overlay_left_down = key_left_down
        self._overlay_right_down = key_right_down
        self._overlay_escape_down = key_escape_down
        self._overlay_pgup_down = key_pgup_down
        self._overlay_pgdn_down = key_pgdn_down
        self._overlay_home_down = key_home_down
        self._overlay_end_down = key_end_down
        self._overlay_enter_down = key_enter_down
        self._overlay_gp_prev_buttons = gamepad_buttons

        self._sync_d3d_menu_mouse_input(menu_input_fg)
        if self._d3d_menu_visible:
            self._best_effort_neutralize_game_keys()

        # Auto-close if FIFA exits
        if self._d3d_menu_visible and not self._fifa_hwnd:
            self._d3d_menu_visible = False
            self._overlay_wizard_phase = None
            self._overlay_wizard_stadium = None
            self._uninstall_mouse_wheel_hook()
            self._uninstall_keyboard_hook()
            self._publish_overlay_menu_state()

    def _load_xinput_dll(self):
        for dll_name in ("xinput1_4", "xinput1_3", "xinput9_1_0"):
            try:
                dll = ctypes.WinDLL(dll_name, use_last_error=True)
                dll.XInputGetState.argtypes = [wintypes.DWORD, ctypes.POINTER(XINPUT_STATE)]
                dll.XInputGetState.restype = wintypes.DWORD
                self.log(f"XInput initialized from {dll_name}.dll")
                return dll
            except Exception:
                continue
        self.log("XInput unavailable; gamepad overlay controls disabled")
        return None

    def _get_gamepad_snapshot(self) -> tuple[int, int, int]:
        if self._xinput is None:
            return 0, 0, 0
        indices = [self._active_gamepad_index] + [i for i in range(4) if i != self._active_gamepad_index]
        for index in indices:
            state = XINPUT_STATE()
            try:
                result = int(self._xinput.XInputGetState(index, ctypes.byref(state)))
            except Exception:
                continue
            if result == XINPUT_SUCCESS:
                self._active_gamepad_index = index
                return int(state.Gamepad.wButtons), int(state.Gamepad.sThumbRX), int(state.Gamepad.sThumbRY)
        self._active_gamepad_index = 0
        return 0, 0, 0

    def _get_gamepad_buttons(self) -> int:
        buttons, _rx, _ry = self._get_gamepad_snapshot()
        return buttons

    def _set_overlay_tab(self, index: int, source: str) -> None:
        if not self._overlay_tab_names:
            return
        normalized = index % len(self._overlay_tab_names)
        if normalized == self._overlay_tab_index:
            return
        self._overlay_tab_index = normalized
        tab_name = self._overlay_tab_names[self._overlay_tab_index]
        self.log(f"Overlay menu tab changed to {tab_name} via {source}")
        self._overlay_wizard_phase = None
        self._overlay_wizard_stadium = None
        self._overlay_wizard_police = None
        self._overlay_wizard_pitch = None
        self._overlay_selected_scope = None
        self._overlay_scope_phase = True
        self._publish_overlay_menu_state()
        if self._d3d_injector is not None:
            try:
                self._d3d_injector.push_menu_event(100 + self._overlay_tab_index)
            except Exception:
                pass
            if self._d3d_menu_visible:
                self._update_menu_content()

    def _publish_overlay_menu_state(self) -> None:
        if self._d3d_injector is None:
            return
        try:
            self._d3d_injector.set_menu_state(self._d3d_menu_visible, self._overlay_tab_index)
        except Exception:
            pass

    def _update_menu_content(self) -> None:
        """Populate the D3D menu content list for the active tab (or current wizard step)."""
        inj = self._d3d_injector
        if inj is None:
            return
        try:
            inj.set_dashboard_content(self._build_overlay_dashboard_lines())
        except Exception:
            pass
        items: list[str] = []
        try:
            def _list_dirs(base) -> list[str]:
                if base is None:
                    return []
                p = Path(base)
                if not p.exists():
                    return []
                return sorted(d.name for d in p.iterdir() if d.is_dir())

            def _list_file_stems(base) -> list[str]:
                if base is None:
                    return []
                p = Path(base)
                if not p.exists():
                    return []
                return [f.stem for f in sorted(p.iterdir()) if f.is_file()]

            def _first_img_dir(*paths) -> Path | None:
                for p in paths:
                    if Path(p).exists():
                        return Path(p)
                return None

            if self._overlay_scope_phase:
                tab_name = self._overlay_tab_names[self._overlay_tab_index]
                scope_options = self._get_scope_options_for_tab(tab_name)
                items = [label for label, _code in scope_options]
            elif self._overlay_wizard_phase == "police":
                items = [str(i) for i in range(1, 11)]
            elif self._overlay_wizard_phase == "pitch":
                exedir = getattr(self, "exedir", None)
                img_dir = _first_img_dir(
                    Path(exedir) / "FSW" / "Images" / "PitchMowPattern",
                    Path(exedir) / "FSW" / "PitchMowPattern",
                ) if exedir else None
                items = _list_file_stems(img_dir) or ["0"]
            elif self._overlay_wizard_phase == "net":
                exedir = getattr(self, "exedir", None)
                img_dir = _first_img_dir(
                    Path(exedir) / "FSW" / "Images" / "Nets",
                    Path(exedir) / "FSW" / "Nets",
                ) if exedir else None
                items = _list_file_stems(img_dir) or ["0"]
            else:
                tab_name = self._overlay_tab_names[self._overlay_tab_index]
                if tab_name == "scoreboards":
                    items = _list_dirs(getattr(self, "ScoreBoard", None))
                elif tab_name == "stadiums":
                    stadium_root = getattr(self, "targetpath", None)
                    items = discover_stadium_names(stadium_root) if stadium_root else []
                elif tab_name == "movies":
                    items = _list_dirs(getattr(self, "Movies", None))
                elif tab_name == "tvlogos":
                    items = _list_dirs(getattr(self, "TVLogo", None))
                elif tab_name == "chants":
                    exedir = getattr(self, "exedir", None)
                    if exedir:
                        items = _list_dirs(Path(exedir) / "FSV")
        except Exception as exc:
            self.log(f"Menu content error (wizard={self._overlay_wizard_phase}): {exc}")
        self._overlay_items = items
        self._overlay_selected_index = 0
        self._overlay_scroll_offset  = 0
        self._overlay_item_count     = len(items)
        self._overlay_window_base    = 0

        # Wizard step header shown above the item list
        phase = self._overlay_wizard_phase
        if self._overlay_scope_phase:
            tab_name = self._overlay_tab_names[self._overlay_tab_index]
            header = f"Select scope  →  {tab_name.rstrip('s').title()}"
        elif phase == "police":
            header = f"Stadium: {self._overlay_wizard_stadium or '?'}  →  Police Pattern"
        elif phase == "pitch":
            header = f"Police: {self._overlay_wizard_police or '?'}  →  Pitch Mow Pattern"
        elif phase == "net":
            header = f"Pitch: {self._overlay_wizard_pitch or '?'}  →  Net Pattern"
        else:
            scope_label = ""
            if self._overlay_selected_scope is not None:
                tab_name = self._overlay_tab_names[self._overlay_tab_index]
                for label, code in self._get_scope_options_for_tab(tab_name):
                    if code == self._overlay_selected_scope:
                        scope_label = label
                        break
            header = f"[{scope_label}]" if scope_label else ""
        self._overlay_list_header = header
        try:
            inj.set_list_header(header)
        except Exception:
            pass

        self._refresh_d3d_window()
        self._update_d3d_preview_image()

    def _refresh_d3d_window(self) -> None:
        """Write a sliding window of the current tab's items to shared memory."""
        inj = self._d3d_injector
        if inj is None:
            return
        items = self._overlay_items
        total = len(items)
        scroll = self._overlay_scroll_offset
        sel = self._overlay_selected_index

        from .d3d_injector import _MAX_MENU_ITEMS as _WIN
        # Align window so that the scroll position sits in the lower quarter.
        base = max(0, scroll - _WIN // 4)
        base = min(base, max(0, total - _WIN))
        # Ensure the selection is always inside the window.
        if sel < base:
            base = max(0, sel)
        elif sel >= base + _WIN:
            base = max(0, sel - _WIN + 1)

        self._overlay_window_base = base
        window_items = items[base : base + _WIN]
        window_scroll = max(0, scroll - base)
        window_sel = max(0, sel - base)
        try:
            inj.set_menu_content(window_items, window_sel, window_scroll)
            inj.set_window_info(total, base)
        except Exception:
            pass

    def _compute_d3d_menu_layout(self, vp_w: float, vp_h: float) -> dict[str, float]:
        margin = _D3D_MENU_VIEW_MARGIN
        avail_w = max(320.0, vp_w - (2.0 * margin))
        avail_h = max(240.0, vp_h - (2.0 * margin))
        menu_w = min(avail_w, max(_D3D_MENU_MIN_W, float(int(vp_w * _D3D_MENU_RATIO_W))))
        menu_h = min(avail_h, max(_D3D_MENU_MIN_H, float(int(vp_h * _D3D_MENU_RATIO_H))))
        tab_h = _D3D_MENU_TAB_H
        dash_h = max(_D3D_MENU_DASH_MIN_H, min(_D3D_MENU_DASH_MAX_H, float(int(menu_h * 0.28))))
        menu_x = float(int((vp_w - menu_w) // 2))
        menu_y = float(int((vp_h - menu_h) // 2))
        content_y = menu_y + tab_h
        list_x = menu_x + 4.0
        list_y = content_y + 4.0
        scroll_w = 12.0
        scroll_gap = 6.0
        base_content_w = menu_w - 8.0
        list_ymax = menu_y + menu_h - dash_h - 14.0
        tab_w = float(int(menu_w // max(1, len(self._overlay_tab_names))))

        show_split = (self._overlay_tab_index == 1)
        header_h = 30.0
        show_header = bool(self._overlay_list_header)
        if show_split:
            list_side_w = float(int(base_content_w * 0.60))
            adj_list_w = list_side_w - scroll_w - scroll_gap
        else:
            adj_list_w = base_content_w - scroll_w - scroll_gap
        adj_list_y = list_y + (header_h + 4.0 if show_header else 0.0)
        adj_scroll_x = list_x + adj_list_w + scroll_gap

        return {
            "menu_x": menu_x,
            "menu_y": menu_y,
            "menu_w": menu_w,
            "menu_h": menu_h,
            "tab_h": tab_h,
            "tab_w": tab_w,
            "dash_h": dash_h,
            "list_x": list_x,
            "list_y": adj_list_y,
            "list_w": adj_list_w,
            "list_ymax": list_ymax,
            "scroll_x": adj_scroll_x,
            "scroll_y": adj_list_y,
            "scroll_w": scroll_w,
            "scroll_h": max(1.0, list_ymax - adj_list_y),
            "item_h": _D3D_MENU_ITEM_H,
        }

    def _compute_overlay_visible_rows(self, viewport_w: float, viewport_h: float) -> int:
        layout = self._compute_d3d_menu_layout(viewport_w, viewport_h)
        usable = max(1.0, layout["list_ymax"] - layout["list_y"])
        return max(1, int(usable // layout["item_h"]))

    def _get_scope_options_for_tab(self, tab_name: str) -> list[tuple[str, str]]:
        """Return [(display_label, scope_code)] for all valid scopes of the tab."""
        if tab_name in {"scoreboards", "tvlogos"}:
            return [
                ("Home Team", "2"),
                ("Default / Friendly", "3"),
                ("Round", "1"),
                ("Tournament", "0"),
            ]
        if tab_name == "movies":
            return [
                ("Home Team", "3"),
                ("Derby", "2"),
                ("Round", "1"),
                ("Tournament", "0"),
            ]
        if tab_name == "stadiums":
            return [
                ("Home Team", "0"),
                ("Round", "1"),
                ("Tournament", "4"),
            ]
        return []

    def _resolve_overlay_assignment_target(self, tab_name: str, scope_override: str | None = None) -> tuple[str | None, str | None]:
        if tab_name in {"scoreboards", "tvlogos"}:
            scope = scope_override if scope_override is not None else self.assignment_runtime.default_scope_for_scoreboard()
            return self.assignment_runtime.resolve_assignment_target(
                scope,
                {
                    "0": (self.TOURNAME, "Tournament"),
                    "1": (self.TOURROUNDID, "Round"),
                    "2": (self.HID, "Home Team"),
                    "3": ("0", "Default"),
                },
            )
        if tab_name == "movies":
            scope = scope_override if scope_override is not None else self.assignment_runtime.default_scope_for_movie()
            return self.assignment_runtime.resolve_assignment_target(
                scope,
                {
                    "0": (self.TOURNAME, "Tournament"),
                    "1": (self.TOURROUNDID, "Round"),
                    "2": (self.derby if self.HID and self.AID else "", "Derby"),
                    "3": (self.HID, "Home Team"),
                },
            )
        if tab_name == "stadiums":
            scope = scope_override if scope_override is not None else self.assignment_runtime.default_scope_for_stadium()
            return self.assignment_runtime.resolve_assignment_target(
                scope,
                {
                    "0": (self.HID, "Home Team"),
                    "1": (self.TOURROUNDID, "Round"),
                    "4": (self.TOURNAME, "Tournament"),
                },
            )
        return None, None

    def _write_overlay_assignment(self, key: str, comp: str, value: str, source: str) -> bool:
        if not comp or not key:
            return False
        try:
            self.settings_ini.write(comp, value, key)
            self.settings_ini.save()
            self.log(f"Overlay assignment ({source}): [{key}] {comp}={value}")
            if self._d3d_menu_visible:
                self._d3d_menu_visible = False
                self._overlay_scope_phase = False
                self._overlay_selected_scope = None
                self._uninstall_mouse_wheel_hook()
                self._uninstall_keyboard_hook()
                self._publish_overlay_menu_state()
            # Stadium assignments need the full runtime (may trigger loading modal).
            # Movie/scoreboard assignments skip apply_stadium_runtime to avoid
            # triggering a stadium reload as a side effect.
            if key in {"stadium", "comp"}:
                self.apply_all_runtime()
            else:
                self.apply_scoreboard_runtime()
                self.apply_movie_runtime()
            return True
        except Exception as exc:
            self.log(f"Overlay assignment failed ({source})", exc, exc_info=sys.exc_info())
            return False

    def _build_overlay_stadium_payload(self, selected_item: str, comp: str, key: str) -> str:
        police = self.PoliceNum or "4"
        pitch = "0"
        net = "0"
        try:
            if comp and key and self.settings_ini.key_exists(comp, key):
                existing = self.settings_ini.read(comp, key)
                _stadiums, ex_police, ex_pitch, ex_net = self.stadium_runtime._parse_assignment(existing)
                if ex_police:
                    police = ex_police
                if ex_pitch:
                    pitch = ex_pitch
                if ex_net:
                    net = ex_net
        except Exception:
            pass
        return ",".join([selected_item, police, pitch, net])

    def _wizard_back(self) -> None:
        if self._overlay_wizard_phase == "net":
            self._overlay_wizard_phase = "pitch"
        elif self._overlay_wizard_phase == "pitch":
            self._overlay_wizard_phase = "police"
        else:
            self._overlay_wizard_phase = None
            self._overlay_wizard_stadium = None
            self._overlay_wizard_police = None
            self._overlay_wizard_pitch = None
        self._update_menu_content()

    def _activate_overlay_selected_item(self, source: str) -> None:
        if self._overlay_scope_phase:
            tab_name = self._overlay_tab_names[self._overlay_tab_index]
            scope_options = self._get_scope_options_for_tab(tab_name)
            if not scope_options:
                return
            sel = max(0, min(self._overlay_selected_index, len(scope_options) - 1))
            _label, code = scope_options[sel]
            self._overlay_selected_scope = code
            self._overlay_scope_phase = False
            self._update_menu_content()
            return

        if self._overlay_wizard_phase is not None:
            self._activate_wizard_step(source)
            return

        tab_name = self._overlay_tab_names[self._overlay_tab_index]
        if not self._overlay_items:
            return
        sel = max(0, min(self._overlay_selected_index, len(self._overlay_items) - 1))
        selected_item = (self._overlay_items[sel] or "").strip()
        if not selected_item:
            return

        self.assignment_runtime.refresh_context_for_assignment()
        comp, resolved = self._resolve_overlay_assignment_target(tab_name, scope_override=self._overlay_selected_scope)
        if not comp:
            self.log(f"Overlay assign skipped ({source}): no usable context for tab={tab_name}")
            return

        if tab_name == "scoreboards":
            key = "HomeTeamScoreBoard" if resolved == "Home Team" else "Scoreboard"
            self._write_overlay_assignment(key, comp, selected_item, source)
            return
        if tab_name == "tvlogos":
            key = "HomeTeamTvLogo" if resolved == "Home Team" else "TVLogo"
            self._write_overlay_assignment(key, comp, selected_item, source)
            return
        if tab_name == "movies":
            if resolved == "Home Team":
                key = "TeamMovies"
            elif resolved == "Derby":
                key = "DerbyMatch"
            else:
                key = "movies"
            self._write_overlay_assignment(key, comp, selected_item, source)
            return
        if tab_name == "stadiums":
            self._overlay_wizard_stadium = selected_item
            self._overlay_wizard_phase = "police"
            self._overlay_wizard_police = None
            self._overlay_wizard_pitch = None
            self._update_menu_content()
            return

    def _activate_wizard_step(self, source: str) -> None:
        if not self._overlay_items:
            return
        sel = max(0, min(self._overlay_selected_index, len(self._overlay_items) - 1))
        selected_item = (self._overlay_items[sel] or "").strip()
        if not selected_item:
            return
        if self._overlay_wizard_phase == "police":
            self._overlay_wizard_police = selected_item
            self._overlay_wizard_phase = "pitch"
            self._update_menu_content()
        elif self._overlay_wizard_phase == "pitch":
            self._overlay_wizard_pitch = selected_item
            self._overlay_wizard_phase = "net"
            self._update_menu_content()
        elif self._overlay_wizard_phase == "net":
            police = self._overlay_wizard_police or "4"
            pitch = self._overlay_wizard_pitch or "0"
            net = selected_item
            stadium = self._overlay_wizard_stadium or ""
            self._overlay_wizard_phase = None
            self._overlay_wizard_stadium = None
            self._overlay_wizard_police = None
            self._overlay_wizard_pitch = None
            if stadium:
                self.assignment_runtime.refresh_context_for_assignment()
                comp, resolved = self._resolve_overlay_assignment_target("stadiums", scope_override=self._overlay_selected_scope)
                if comp:
                    key = "stadium" if resolved == "Home Team" else "comp"
                    payload = ",".join([stadium, police, pitch, net])
                    self._write_overlay_assignment(key, comp, payload, source)
                else:
                    self.log(f"Overlay wizard apply skipped ({source}): no match context")
            self._update_menu_content()

    def _build_overlay_dashboard_lines(self) -> list[str]:
        def _label_text(key: str, fallback: str = "-") -> str:
            label = self.labels.get(key)
            if label is None:
                return fallback
            text = str(label.cget("text") or "").strip()
            return text or fallback

        if self._overlay_wizard_phase is not None:
            phase = self._overlay_wizard_phase
            phase_labels = {"police": "Police", "pitch": "Pitch Pattern", "net": "Net Pattern"}
            police_val = "[selecting...]" if phase == "police" else (self._overlay_wizard_police or "-")
            pitch_val = "-" if phase == "police" else "[selecting...]" if phase == "pitch" else (self._overlay_wizard_pitch or "-")
            net_val = "[selecting...]" if phase == "net" else "-"
            return [
                "-- STADIUM CONFIG --",
                f"Stadium: {self._overlay_wizard_stadium or '-'}",
                f"Police:  {police_val}",
                f"Pitch:   {pitch_val}",
                f"Net:     {net_val}",
                f">> Select {phase_labels.get(phase, phase)} <<",
                "",
                "B / Esc = back",
            ]

        def _with_type(value: str, atype: str) -> str:
            return f"{value} [{atype}]" if atype else value

        return [
            self.tr("card.assets.title"),
            f"{self.tr('stat.current_stadium')}: {_with_type(_label_text('stadium'), self._stadium_assignment_type)}",
            f"{self.tr('stat.scoreboard')}: {_with_type(_label_text('scoreboard', 'default'), self._scoreboard_assignment_type)}",
            f"{self.tr('stat.tv_logo')}: {_with_type(_label_text('tvlogo', 'default'), self._tvlogo_assignment_type)}",
            f"{self.tr('stat.movie')}: {_with_type(_label_text('movie', 'default'), self._movie_assignment_type)}",
            self.tr("card.match.title"),
            f"{self.tr('stat.current_page')}: {_label_text('page')}",
            f"{self.tr('stat.minute_second')}: {_label_text('match_clock_split', '00 / 00')}",
            f"{self.tr('stat.tournament')}: {_label_text('tour')}",
            f"{self.tr('stat.round_id')}: {_label_text('round')}",
            f"{self.tr('stat.status')}: {_label_text('status', self.display_value('idle'))}",
        ]

    def _update_d3d_preview_image(self) -> None:
        """Update shared memory image_path to the preview of the currently highlighted item."""
        inj = self._d3d_injector
        if inj is None:
            return
        sel = self._overlay_selected_index
        selected_item = self._overlay_items[sel] if 0 <= sel < len(self._overlay_items) else ""
        preview_path = ""
        phase = self._overlay_wizard_phase
        tab_name = self._overlay_tab_names[self._overlay_tab_index]
        if phase is not None and selected_item:
            exedir = getattr(self, "exedir", None)
            if exedir:
                _exedir = Path(exedir)
                if phase == "police":
                    for subdir in ("FSW/Images/Police", "FSW/Police"):
                        p = _exedir / subdir / f"{selected_item}.png"
                        if p.exists():
                            preview_path = str(p)
                            break
                elif phase == "pitch":
                    for subdir in ("FSW/Images/PitchMowPattern", "FSW/PitchMowPattern"):
                        p = _exedir / subdir / f"{selected_item}.png"
                        if p.exists():
                            preview_path = str(p)
                            break
                elif phase == "net":
                    for subdir in ("FSW/Images/Nets", "FSW/Nets"):
                        p = _exedir / subdir / f"{selected_item}.png"
                        if p.exists():
                            preview_path = str(p)
                            break
        elif tab_name == "stadiums" and selected_item:
            try:
                path = self._resolve_stadium_preview_path(selected_item)
                preview_path = str(path) if path else ""
            except Exception:
                pass
        try:
            inj.set_preview_image(preview_path)
        except Exception:
            pass

    def _navigate_menu_items(self, delta: int) -> None:
        """Move selection up/down in the current tab list."""
        count = self._overlay_item_count
        if count == 0:
            return
        sel = (self._overlay_selected_index + delta) % count
        self._overlay_selected_index = sel
        scroll = self._overlay_scroll_offset
        visible_rows = max(1, int(self._overlay_visible_rows))
        if sel < scroll:
            scroll = sel
        elif sel >= scroll + visible_rows:
            scroll = sel - visible_rows + 1
        self._overlay_scroll_offset = scroll
        self._refresh_d3d_window()
        self._update_d3d_preview_image()

    def _set_menu_selection(self, index: int) -> None:
        count = self._overlay_item_count
        if count <= 0:
            return
        sel = max(0, min(int(index), count - 1))
        self._overlay_selected_index = sel
        scroll = self._overlay_scroll_offset
        visible_rows = max(1, int(self._overlay_visible_rows))
        if sel < scroll:
            scroll = sel
        elif sel >= scroll + visible_rows:
            scroll = sel - visible_rows + 1
        self._overlay_scroll_offset = scroll
        self._refresh_d3d_window()
        self._update_d3d_preview_image()

    def _sync_d3d_menu_mouse_input(self, menu_input_fg: bool) -> None:
        left_edge = self._overlay_mouse_click_pending
        self._overlay_mouse_click_pending = False

        if not self._d3d_menu_visible:
            return

        input_hwnd = int(self._fifa_hwnd)
        vp_w = 0
        vp_h = 0
        inj = self._d3d_injector
        if inj is not None:
            try:
                overlay_hwnd, overlay_vw, overlay_vh = inj.get_menu_metrics()
                if overlay_hwnd:
                    input_hwnd = int(overlay_hwnd)
                if overlay_vw > 0 and overlay_vh > 0:
                    vp_w = int(overlay_vw)
                    vp_h = int(overlay_vh)
            except Exception:
                pass

        if not input_hwnd:
            return

        client_rect = RECT()
        cursor = POINT()
        if not self.user32.GetClientRect(input_hwnd, ctypes.byref(client_rect)):
            return

        if self._overlay_mouse_screen_x is not None and self._overlay_mouse_screen_y is not None:
            cursor.x = int(self._overlay_mouse_screen_x)
            cursor.y = int(self._overlay_mouse_screen_y)
        elif not self.user32.GetCursorPos(ctypes.byref(cursor)):
            return
        if not self.user32.ScreenToClient(input_hwnd, ctypes.byref(cursor)):
            return

        if vp_w <= 0:
            vp_w = max(1, int(client_rect.right - client_rect.left))
        if vp_h <= 0:
            vp_h = max(1, int(client_rect.bottom - client_rect.top))
        self._overlay_visible_rows = self._compute_overlay_visible_rows(float(vp_w), float(vp_h))
        local_x = float(cursor.x)
        local_y = float(cursor.y)
        if local_x < 0 or local_y < 0 or local_x >= vp_w or local_y >= vp_h:
            return

        layout = self._compute_d3d_menu_layout(float(vp_w), float(vp_h))
        menu_x = layout["menu_x"]
        menu_y = layout["menu_y"]
        tab_h = layout["tab_h"]
        tab_w = layout["tab_w"]
        list_x = layout["list_x"]
        list_y = layout["list_y"]
        list_w = layout["list_w"]
        list_ymax = layout["list_ymax"]
        scroll_x = layout["scroll_x"]
        scroll_y = layout["scroll_y"]
        scroll_w = layout["scroll_w"]
        scroll_h = layout["scroll_h"]
        item_h = layout["item_h"]

        tab_strip_x = menu_x + 2.0
        tab_strip_y = menu_y + 2.0
        tab_strip_h = tab_h - 2.0
        if left_edge and tab_strip_x <= local_x < (tab_strip_x + tab_w * len(self._overlay_tab_names)) and tab_strip_y <= local_y < (tab_strip_y + tab_strip_h):
            tab_index = int((local_x - tab_strip_x) // tab_w)
            if 0 <= tab_index < len(self._overlay_tab_names):
                self._set_overlay_tab(tab_index, "mouse")
                return

        if left_edge and list_x <= local_x < (list_x + list_w) and list_y <= local_y < list_ymax and self._overlay_item_count > 0:
            row = int((local_y - list_y) // item_h)
            item_index = self._overlay_scroll_offset + row
            if 0 <= item_index < self._overlay_item_count:
                now = time.monotonic()
                if (item_index == self._overlay_dblclick_last_index
                        and now - self._overlay_dblclick_last_time < 0.5):
                    self._activate_overlay_selected_item("dblclick")
                    self._overlay_dblclick_last_time = 0.0
                    self._overlay_dblclick_last_index = -1
                else:
                    self._set_menu_selection(item_index)
                    self._overlay_dblclick_last_time = now
                    self._overlay_dblclick_last_index = item_index

        if left_edge and scroll_x <= local_x < (scroll_x + scroll_w) and scroll_y <= local_y < (scroll_y + scroll_h) and self._overlay_item_count > 0:
            visible_rows = max(1, int(self._overlay_visible_rows))
            max_scroll = max(0, self._overlay_item_count - visible_rows)
            if max_scroll <= 0:
                return

            track_h = max(1.0, scroll_h)
            thumb_h = max(22.0, (track_h * float(visible_rows)) / float(self._overlay_item_count))
            thumb_h = min(track_h, thumb_h)
            thumb_range = max(1.0, track_h - thumb_h)
            cur_scroll = max(0, min(self._overlay_scroll_offset, max_scroll))
            thumb_top = scroll_y + (float(cur_scroll) / float(max_scroll)) * thumb_range

            if local_y < thumb_top:
                new_scroll = max(0, cur_scroll - visible_rows)
            elif local_y > (thumb_top + thumb_h):
                new_scroll = min(max_scroll, cur_scroll + visible_rows)
            else:
                rel = (local_y - scroll_y - (thumb_h * 0.5)) / thumb_range
                rel = max(0.0, min(1.0, rel))
                new_scroll = int(round(rel * max_scroll))

            self._overlay_scroll_offset = new_scroll
            sel = max(0, min(self._overlay_selected_index, self._overlay_item_count - 1))
            if sel < new_scroll:
                sel = new_scroll
            elif sel >= (new_scroll + visible_rows):
                sel = max(new_scroll, min(self._overlay_item_count - 1, new_scroll + visible_rows - 1))
            self._overlay_selected_index = sel
            self._refresh_d3d_window()

    def _is_overlay_input_foreground(self) -> bool:
        fg = int(self.user32.GetForegroundWindow() or 0)
        if fg == 0:
            return False
        if fg == int(self._fifa_hwnd or 0):
            return True
        inj = self._d3d_injector
        if inj is not None:
            try:
                overlay_hwnd, _vw, _vh = inj.get_menu_metrics()
                if overlay_hwnd and fg == int(overlay_hwnd):
                    return True
            except Exception:
                pass
        return False

    def _install_mouse_wheel_hook(self) -> None:
        if self._mouse_hook_thread is not None and self._mouse_hook_thread.is_alive():
            return
        t = threading.Thread(target=self._mouse_hook_thread_func, name="mouse-hook", daemon=True)
        t.start()
        self._mouse_hook_thread = t

    def _mouse_hook_thread_func(self) -> None:
        """Dedicated Win32 message-pump thread for WH_MOUSE_LL."""
        hook_type = ctypes.WINFUNCTYPE(ctypes.c_longlong, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
        block_mouse_messages = {
            WM_LBUTTONDOWN,
            WM_LBUTTONUP,
            WM_RBUTTONDOWN,
            WM_RBUTTONUP,
            WM_MBUTTONDOWN,
            WM_MBUTTONUP,
            WM_MOUSEWHEEL,
        }

        def _mouse_proc(n_code: int, w_param: int, l_param: int) -> int:
            if n_code == HC_ACTION and self._d3d_menu_visible:
                msg = int(w_param)
                mouse_x = mouse_y = -1
                try:
                    info = ctypes.cast(l_param, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
                    mouse_x = int(info.pt.x)
                    mouse_y = int(info.pt.y)
                    self._overlay_mouse_screen_x = mouse_x
                    self._overlay_mouse_screen_y = mouse_y
                except Exception:
                    pass
                over_fifa = False
                try:
                    fifa_hwnd = int(self._fifa_hwnd or 0)
                    if fifa_hwnd and mouse_x >= 0:
                        pt = POINT()
                        pt.x = mouse_x
                        pt.y = mouse_y
                        hwnd_at = self.user32.WindowFromPoint(pt)
                        if hwnd_at:
                            root = self.user32.GetAncestor(hwnd_at, 2)  # GA_ROOT
                            over_fifa = (int(root or hwnd_at) == fifa_hwnd)
                except Exception:
                    pass
                if msg == WM_MOUSEWHEEL and over_fifa:
                    try:
                        info = ctypes.cast(l_param, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
                        delta = ctypes.c_short((int(info.mouseData) >> 16) & 0xFFFF).value
                        if delta:
                            self._overlay_mouse_wheel_steps += int(delta / 120)
                    except Exception:
                        pass
                if msg in block_mouse_messages and over_fifa:
                    if msg == WM_LBUTTONDOWN:
                        self._overlay_mouse_click_pending = True
                    return 1
            return int(self.user32.CallNextHookEx(self._mouse_hook or 0, n_code, w_param, l_param))

        proc = hook_type(_mouse_proc)
        self._mouse_hook_proc = proc
        module_handle = self.kernel32.GetModuleHandleW(None)
        hook = self.user32.SetWindowsHookExW(WH_MOUSE_LL, proc, module_handle, 0)
        self._mouse_hook = hook
        self._mouse_hook_thread_id = self.kernel32.GetCurrentThreadId()

        win_msg = MSG()
        while self.user32.GetMessageW(ctypes.byref(win_msg), None, 0, 0) > 0:
            self.user32.TranslateMessage(ctypes.byref(win_msg))
            self.user32.DispatchMessageW(ctypes.byref(win_msg))

        if hook:
            try:
                self.user32.UnhookWindowsHookEx(hook)
            except Exception:
                pass
        self._mouse_hook = None
        self._mouse_hook_proc = None
        self._mouse_hook_thread_id = 0

    def _uninstall_mouse_wheel_hook(self) -> None:
        tid = self._mouse_hook_thread_id
        if tid:
            self.user32.PostThreadMessageW(tid, WM_QUIT, 0, 0)
        t = self._mouse_hook_thread
        if t is not None:
            t.join(timeout=1.0)
            self._mouse_hook_thread = None

    def _install_keyboard_hook(self) -> None:
        if self._keyboard_hook is not None:
            return

        hook_type = ctypes.WINFUNCTYPE(ctypes.c_longlong, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
        blocked_keys = {
            VK_F12,
            VK_ESCAPE,
            VK_RETURN,
            VK_LEFT,
            VK_RIGHT,
            VK_UP,
            VK_DOWN,
            VK_PRIOR,
            VK_NEXT,
            VK_HOME,
            VK_END,
        }
        key_messages = {WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP}

        def _keyboard_proc(n_code: int, w_param: int, l_param: int) -> int:
            if n_code == HC_ACTION and self._d3d_menu_visible:
                msg = int(w_param)
                if msg in key_messages:
                    try:
                        info = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                        vk = int(info.vkCode)
                        if vk in blocked_keys:
                            if msg in (WM_KEYDOWN, WM_SYSKEYDOWN):
                                self._overlay_blocked_key_down.add(vk)
                            elif msg in (WM_KEYUP, WM_SYSKEYUP):
                                self._overlay_blocked_key_down.discard(vk)
                            return 1
                    except Exception:
                        pass
            return int(self.user32.CallNextHookEx(self._keyboard_hook, n_code, w_param, l_param))

        self._keyboard_hook_proc = hook_type(_keyboard_proc)
        module_handle = self.kernel32.GetModuleHandleW(None)
        try:
            self._keyboard_hook = self.user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._keyboard_hook_proc, module_handle, 0)
        except Exception:
            self._keyboard_hook = None
        # Seed state for keys already held when the hook is installed.
        for vk in blocked_keys:
            if bool(self.user32.GetAsyncKeyState(vk) & 0x8000):
                self._overlay_blocked_key_down.add(vk)

    def _uninstall_keyboard_hook(self) -> None:
        if self._keyboard_hook is not None:
            try:
                self.user32.UnhookWindowsHookEx(self._keyboard_hook)
            except Exception:
                pass
            self._keyboard_hook = None
        self._keyboard_hook_proc = None
        self._overlay_blocked_key_down.clear()

    def _is_overlay_key_down(self, vk: int, menu_input_fg: bool) -> bool:
        if self._d3d_menu_visible and self._keyboard_hook is not None:
            return vk in self._overlay_blocked_key_down
        return bool(self.user32.GetAsyncKeyState(vk) & 0x8000)

    def _best_effort_neutralize_game_keys(self) -> None:
        """Release common UI keys so FIFA is less likely to consume held inputs while menu is open."""
        for vk in (VK_UP, VK_DOWN, VK_LEFT, VK_RIGHT, VK_RETURN, VK_PRIOR, VK_NEXT, VK_HOME, VK_END):
            if self.user32.GetAsyncKeyState(vk) & 0x8000:
                self.user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)

    def _apply_noactivate_window_style(self, hwnd: int) -> None:
        if not hwnd:
            return
        try:
            ex_style = int(self.user32.GetWindowLongW(hwnd, GWL_EXSTYLE))
            ex_style |= WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
            self.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style)
            self.user32.SetWindowPos(
                hwnd,
                HWND_TOPMOST,
                0, 0, 0, 0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW,
            )
        except Exception:
            pass

    def _focus_fifa_window(self) -> None:
        if not self._fifa_hwnd:
            return
        try:
            self.user32.ShowWindow(self._fifa_hwnd, SW_RESTORE)
        except Exception:
            pass
        try:
            self.user32.SetForegroundWindow(self._fifa_hwnd)
        except Exception:
            pass

    def _is_probable_fullscreen_window(self, hwnd: int) -> bool:
        if not hwnd:
            return False
        rect = RECT()
        if not self.user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return False
        width = max(1, rect.right - rect.left)
        height = max(1, rect.bottom - rect.top)
        screen_width = max(1, int(self.user32.GetSystemMetrics(0)))
        screen_height = max(1, int(self.user32.GetSystemMetrics(1)))
        tolerance = 8
        return abs(width - screen_width) <= tolerance and abs(height - screen_height) <= tolerance

    def _restore_fifa_fullscreen(self) -> None:
        if not self._fifa_hwnd:
            return
        self._focus_fifa_window()
        try:
            self.user32.keybd_event(VK_MENU, 0, 0, 0)
            self.user32.keybd_event(VK_RETURN, 0, 0, 0)
            self.user32.keybd_event(VK_RETURN, 0, KEYEVENTF_KEYUP, 0)
            self.user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)
            self.log("Attempted fullscreen restore with Alt+Enter")
        except Exception as exc:
            self.log("Failed to restore FIFA fullscreen", exc, exc_info=sys.exc_info())
        finally:
            self.after(180, self._focus_fifa_window)

    def _find_fifa_window_handle(self) -> int:
        pid = self._resolve_fifa_pid()
        if not pid:
            return 0
        matches: list[int] = []
        callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        @callback_type
        def enum_proc(hwnd, _lparam):
            if not self.user32.IsWindowVisible(hwnd):
                return True
            owner_pid = wintypes.DWORD()
            self.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner_pid))
            if owner_pid.value == pid:
                rect = RECT()
                if self.user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                    if rect.right > rect.left and rect.bottom > rect.top:
                        matches.append(int(hwnd))
                        return False
            return True

        self.user32.EnumWindows(enum_proc, 0)
        return matches[0] if matches else 0

    def _resolve_fifa_pid(self) -> int:
        if self.memory.process_id and self.memory.is_open():
            return int(self.memory.process_id)
        if not self.MP:
            return 0
        try:
            for proc in psutil.process_iter(["pid", "name"]):
                if Path((proc.info.get("name") or "")).stem.lower() == self.MP.lower():
                    return int(proc.info["pid"])
        except Exception:
            return 0
        return 0
