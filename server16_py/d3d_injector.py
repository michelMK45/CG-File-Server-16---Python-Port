"""
d3d_injector.py
───────────────
Manages the D3D overlay DLL injection into FIFA 16 and the shared-memory
channel used to control what the overlay displays.

Usage (from app.py):
    injector = D3DOverlayInjector(dll_path="runtime/cgfs16_overlay.dll")
    injector.inject(fifa_pid)       # call once when FIFA is detected
    injector.show("Bernabéu", "Copying files...", 0.0)
    injector.update(42.0, "Copying files...")
    injector.hide()
    injector.destroy()              # call on app exit
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import logging
import os
import threading
from pathlib import Path

log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Shared memory layout — MUST match OverlayShared in cgfs16_overlay.cpp
# ─────────────────────────────────────────────────────────────────────────────
_SHMEM_NAME = "Local\\CGFS16_Overlay_v2"
_MAX_STR    = 256
_MAX_IMG    = 512
_MAX_MENU_ITEM_LEN = 80
_MAX_MENU_ITEMS    = 256  # must match MAX_MENU_ITEMS in the compiled DLL
_MAX_DASH_ITEMS    = 10
_MAX_TOASTS        = 6    # must match MAX_TOASTS in the compiled DLL
_MAX_ICON          = 32   # must match MAX_ICON in the compiled DLL


class _ToastEntry(ctypes.Structure):
    _fields_ = [
        ("visible", ctypes.c_long),
        ("title",   ctypes.c_wchar * _MAX_STR),
        ("body",    ctypes.c_wchar * _MAX_STR),
        ("style",   ctypes.c_long),   # 0 = info (blue), 1 = warning (amber)
        # Lowercase key naming a file under resources/rmlui/icons/<icon>.png
        # ("tv", "scoreboard", "movie", "goalpost", ...) — empty (the
        # default) or a name with no matching file falls back to the app
        # icon, see ResolveToastIconPath in cgfs16_rmlui.cpp.
        ("icon",    ctypes.c_wchar * _MAX_ICON),
    ]


class _OverlayShared(ctypes.Structure):
    _fields_ = [
        ("visible",       ctypes.c_long),           # 0 = hide, 1 = show
        ("progress_x100", ctypes.c_long),           # progress * 100  (0–10000)
        ("stadium_name",  ctypes.c_wchar * _MAX_STR),
        ("detail_text",   ctypes.c_wchar * _MAX_STR),
        ("image_path",    ctypes.c_wchar * _MAX_IMG),  # abs path to preview image
        ("menu_visible",  ctypes.c_long),           # 0 = menu hidden, 1 = menu shown
        ("active_tab",    ctypes.c_long),           # overlay tab index
        ("last_input_event", ctypes.c_long),        # app-defined input event id
        ("reserved0",     ctypes.c_long),           # menu viewport width telemetry
            ("menu_item_count",     ctypes.c_long),    # 0..MAX_MENU_ITEMS valid items
            ("menu_selected_index", ctypes.c_long),    # highlighted row
            ("menu_scroll_offset",  ctypes.c_long),    # first visible row
            ("reserved1",           ctypes.c_long),    # menu viewport height telemetry
            ("dashboard_item_count", ctypes.c_long),
            ("reserved2",            ctypes.c_long),    # menu swapchain output hwnd telemetry
            ("dashboard_items",      (ctypes.c_wchar * _MAX_MENU_ITEM_LEN) * _MAX_DASH_ITEMS),
            ("menu_items",          (ctypes.c_wchar * _MAX_MENU_ITEM_LEN) * _MAX_MENU_ITEMS),
            # Virtual-scroll telemetry: written by Python, read by C++ for scrollbar.
            ("menu_total_count",    ctypes.c_long),    # real list size (may exceed MAX_MENU_ITEMS)
            ("menu_window_base",    ctypes.c_long),    # real index of menu_items[0]
            # Team crest image paths (PNG) for dashboard panel — written by Python
            ("home_crest_path",     ctypes.c_wchar * _MAX_IMG),
            ("away_crest_path",     ctypes.c_wchar * _MAX_IMG),
            # Wizard step header text shown above the item list (empty = hidden)
            ("list_header",         ctypes.c_wchar * _MAX_STR),
        # Toast notification stack — each slot is independently shown/hidden
        ("toasts",              _ToastEntry * _MAX_TOASTS),
        # Overrides DrawOverlay11's hardcoded "Loading Stadium" header line —
        # empty (the default) keeps that exact text, so existing stadium-
        # loading callers of show() need no changes.
        ("panel_title",          ctypes.c_wchar * _MAX_STR),
        # Absolute directory holding the bundled gamepad button icon PNGs
        # (a.png/b.png/dpad.png/lb.png/rb.png/rs.png) — written once after
        # injection so the gamepad hint bar can render real button glyphs.
        ("gamepad_icon_dir",     ctypes.c_wchar * _MAX_IMG),
        # Absolute directory holding the bundled keyboard key icon PNGs
        # (up.png/down.png/left.png/right.png/enter.png/esc.png/mouse.png) —
        # written once after injection so the keyboard hint bar can render
        # real key glyphs instead of text badges.
        ("keyboard_icon_dir",    ctypes.c_wchar * _MAX_IMG),
        # Absolute directory holding the loose .rml documents rendered by
        # cgfs16_rmlui.cpp (resources/rmlui/toast.rml, stadium_panel.rml) —
        # written once after injection so those documents can be edited on
        # disk without recompiling the DLL.
        ("rmlui_content_dir",    ctypes.c_wchar * _MAX_IMG),
        # DLL -> Python: item rows that fit in the RmlUi menu's list area at
        # the current viewport size, computed once per frame by
        # cgfs16_rmlui_menu.cpp's RmlMenu_Sync from its own RCSS-derived
        # layout — replaces the old DrawMenuOverlay11/_compute_d3d_menu_layout
        # duplication (see get_menu_metrics()).
        ("menu_visible_rows", ctypes.c_long),
        # Live mouse feed into the RmlUi Context — written every ~80ms from
        # _sync_d3d_menu_input (see set_rmlui_menu_mouse()), window-coordinate
        # space (0,0 = top-left client area), same space as the viewport
        # telemetry above. left_down is the raw continuous button state; the
        # DLL does its own down/up edge detection. Only acted on while the
        # menu is visible — zero effect on the game otherwise.
        ("rmlui_menu_mouse_x", ctypes.c_long),
        ("rmlui_menu_mouse_y", ctypes.c_long),
        ("rmlui_menu_mouse_left_down", ctypes.c_long),
        # DLL -> Python "last event wins" click/scroll signal — see
        # get_menu_event(). kind: 0=none, 1=tab_click, 2=item_click,
        # 3=scroll_to, 4=hero_activate, 5=close_click; index is a tab index /
        # absolute item index / absolute scroll target / unused(0) depending
        # on kind.
        # Written by cgfs16_rmlui_menu.cpp's
        # MenuEventListener in kind/index-then-seq order (seq last), so a
        # torn read here can only see a fully-old or fully-new event.
        ("menu_event_seq", ctypes.c_long),
        ("menu_event_kind", ctypes.c_long),
        ("menu_event_index", ctypes.c_long),
        # Phase 3 (visual redesign): per-item row thumbnail image paths,
        # parallel to menu_items[] and windowed identically (index i is the
        # same logical item in both arrays, same menu_window_base applies) —
        # only populated by Python while the active tab is Stadiums, left
        # blank otherwise. See set_menu_content()'s thumb_paths parameter.
        ("menu_item_thumb_paths", (ctypes.c_wchar * _MAX_IMG) * _MAX_MENU_ITEMS),
        # Which hint bar the DLL should show: 0 = keyboard/mouse, 1 = gamepad.
        # See set_input_mode().
        ("input_mode", ctypes.c_long),
        # 1 while _update_menu_content() is synchronously computing a new
        # item list (e.g. the Stadiums tab's filesystem scan) — see
        # set_menu_loading().
        ("menu_loading", ctypes.c_long),
        # Compact scoreboard widget (dashboard, right side, next to the team
        # crests) — "2 x 1" / "23:45", independent of dashboard_items[] (the
        # generic stat-line list) since these render as their own large text
        # beside the crests rather than one more line in that list. See
        # set_match_score_time().
        ("score_text",      ctypes.c_wchar * _MAX_STR),
        ("match_time_text", ctypes.c_wchar * _MAX_STR),
        # 1 while the keyboard/gamepad "activate" input (Enter / A) is
        # currently held — drives #hero-btn.hero-pressed's press-shrink in
        # menu.rml for those two input methods, which (unlike a real mouse
        # click) never touch RmlUi's own :active pseudo-class. See
        # set_menu_activate_down().
        ("menu_activate_down", ctypes.c_long),
        # 1 to show the "Filter" button beside the wizard-header band
        # (Stadiums tab) — clickable with the mouse, shows the Y glyph in
        # gamepad mode. See set_stadium_filter_hint_visible().
        ("stadium_filter_hint_visible", ctypes.c_long),
        # 1 while the Stadiums country-filter bubble is open — tells the DLL
        # to render #list-area as a small bordered popover instead of the
        # normal full-height list. See set_stadium_filter_panel_open().
        ("stadium_filter_panel_open", ctypes.c_long),
        # Parallel to menu_items[]/menu_item_thumb_paths[], windowed
        # identically — 1 marks a row as "checked" (lit up via .row-checked)
        # instead of encoding that into the row's own text. Only meaningful
        # while the Stadiums filter bubble is open. See set_menu_content()'s
        # checked parameter.
        ("menu_item_checked", ctypes.c_long * _MAX_MENU_ITEMS),
        # DLL -> Python: real number of columns the Stadiums country-filter
        # grid is actually rendering this frame, computed by RmlMenu_Sync
        # from the same box-model math (fixed item width + column-gap)
        # #list-area.bubble's RCSS uses — see get_filter_grid_cols() and
        # menu_filter_grid_cols' field comment in cgfs16_overlay.cpp for why
        # a hardcoded column count on this side couldn't reliably match
        # RmlUi's actual flex-wrap column count at every panel width. Only
        # meaningful while stadium_filter_panel_open is set.
        ("menu_filter_grid_cols", ctypes.c_long),
        # Kit-cycling carousel notification (F7-F10) — a fully independent
        # panel/doc from the stadium-loading one above (own visible flag),
        # unlike the old approach of reusing show()/visible/image_path for
        # it, which meant a kit-cycle notification had to be skipped outright
        # whenever a stadium load happened to be in progress. See
        # show_kit_carousel()/kit_carousel.rml/SyncKitCarousel in
        # cgfs16_rmlui.cpp.
        ("kit_carousel_visible",       ctypes.c_long),
        ("kit_carousel_title",         ctypes.c_wchar * _MAX_STR),
        ("kit_carousel_detail",        ctypes.c_wchar * _MAX_STR),
        ("kit_carousel_hint",          ctypes.c_wchar * _MAX_STR),
        ("kit_carousel_image_prev",    ctypes.c_wchar * _MAX_IMG),
        ("kit_carousel_image_current", ctypes.c_wchar * _MAX_IMG),
        ("kit_carousel_image_next",    ctypes.c_wchar * _MAX_IMG),
        # "Last event wins" signal for a genuine F7-F10 cycle step (mirrors
        # menu_event_seq's shape) — bumped by show_kit_carousel() every call,
        # never touched by update_kit_carousel_images()'s background-prefetch
        # pop-ins, so cgfs16_rmlui.cpp can tell a real cycle (slide the
        # changed slots in `direction`) apart from a late thumbnail arriving
        # (crossfade only, no motion). Single-writer (Python only), so a
        # plain += is fine — no InterlockedIncrement needed on this side.
        ("kit_carousel_cycle_seq",  ctypes.c_long),
        ("kit_carousel_direction",  ctypes.c_long),  # -1 (prev) / +1 (next)
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Win32 constants & kernel32 setup
# ─────────────────────────────────────────────────────────────────────────────
_PROCESS_CREATE_THREAD    = 0x0002
_PROCESS_VM_OPERATION     = 0x0008
_PROCESS_VM_WRITE         = 0x0020
_PROCESS_VM_READ          = 0x0010
_PROCESS_QUERY_INFORMATION = 0x0400
_MEM_COMMIT               = 0x1000
_MEM_RESERVE              = 0x2000
_MEM_RELEASE              = 0x8000
_PAGE_READWRITE           = 0x04
_FILE_MAP_ALL_ACCESS      = 0xF001F
_INVALID_HANDLE_VALUE     = ctypes.c_void_p(-1).value


def _configure_kernel32() -> ctypes.WinDLL:
    k = ctypes.WinDLL("kernel32", use_last_error=True)

    HANDLE  = wintypes.HANDLE
    BOOL    = wintypes.BOOL
    DWORD   = wintypes.DWORD
    LPCWSTR = wintypes.LPCWSTR
    LPVOID  = ctypes.c_void_p
    SIZE_T  = ctypes.c_size_t

    k.OpenProcess.argtypes  = [DWORD, BOOL, DWORD]
    k.OpenProcess.restype   = HANDLE

    k.VirtualAllocEx.argtypes = [HANDLE, LPVOID, SIZE_T, DWORD, DWORD]
    k.VirtualAllocEx.restype  = LPVOID

    k.WriteProcessMemory.argtypes = [
        HANDLE, LPVOID, LPVOID, SIZE_T, ctypes.POINTER(SIZE_T)]
    k.WriteProcessMemory.restype  = BOOL

    k.VirtualFreeEx.argtypes  = [HANDLE, LPVOID, SIZE_T, DWORD]
    k.VirtualFreeEx.restype   = BOOL

    k.CreateRemoteThread.argtypes = [
        HANDLE, LPVOID, SIZE_T, LPVOID, LPVOID, DWORD, ctypes.POINTER(DWORD)]
    k.CreateRemoteThread.restype  = HANDLE

    k.WaitForSingleObject.argtypes = [HANDLE, DWORD]
    k.WaitForSingleObject.restype  = DWORD

    k.CloseHandle.argtypes  = [HANDLE]
    k.CloseHandle.restype   = BOOL

    k.GetModuleHandleW.argtypes = [LPCWSTR]
    k.GetModuleHandleW.restype  = wintypes.HMODULE

    k.GetProcAddress.argtypes = [wintypes.HMODULE, ctypes.c_char_p]
    k.GetProcAddress.restype  = LPVOID

    k.CreateFileMappingW.argtypes = [
        HANDLE, LPVOID, DWORD, DWORD, DWORD, LPCWSTR]
    k.CreateFileMappingW.restype  = HANDLE

    k.MapViewOfFile.argtypes = [HANDLE, DWORD, DWORD, DWORD, SIZE_T]
    k.MapViewOfFile.restype  = LPVOID

    k.UnmapViewOfFile.argtypes = [LPVOID]
    k.UnmapViewOfFile.restype  = BOOL

    return k


_k32 = _configure_kernel32()


# ─────────────────────────────────────────────────────────────────────────────
# D3DOverlayInjector
# ─────────────────────────────────────────────────────────────────────────────
class D3DOverlayInjector:
    """Injects cgfs16_overlay.dll into FIFA 16 and drives it via shared memory."""

    def __init__(self, dll_path: str | Path) -> None:
        self._dll_path     = str(Path(dll_path).resolve())
        self._hmap: int    = 0
        self._shared_ptr   = 0          # raw address returned by MapViewOfFile
        self._shared: _OverlayShared | None = None
        self._injected_pid = 0
        self._lock         = threading.Lock()
        self._ready        = False

        self._open_shared_memory()

    # ── Public ────────────────────────────────────────────────────────────────

    def is_ready(self) -> bool:
        """True if shared memory is mapped, the DLL exists, and the injector exe exists."""
        return (self._ready
                and os.path.isfile(self._dll_path)
                and self._find_inject_exe() is not None)

    def is_injected(self, pid: int = 0) -> bool:
        if pid:
            return self._injected_pid == pid
        return self._injected_pid != 0

    def inject(self, pid: int) -> bool:
        """Inject the DLL into *pid*.  Safe to call multiple times for the same pid."""
        if not self._ready:
            log.error("D3DOverlay: shared memory not ready")
            return False
        if not os.path.isfile(self._dll_path):
            log.error("D3DOverlay: DLL not found: %s", self._dll_path)
            return False
        with self._lock:
            if self._injected_pid == pid:
                return True
            ok = self._do_inject(pid)
            if ok:
                self._injected_pid = pid
            return ok

    def show(self, stadium_name: str, detail: str = "", progress: float = 0.0,
             image_path: str = "", panel_title: str = "") -> None:
        if not self._ready or self._shared is None:
            return
        self._shared.stadium_name  = stadium_name[:_MAX_STR - 1]
        self._shared.detail_text   = detail[:_MAX_STR - 1]
        self._shared.image_path    = image_path[:_MAX_IMG - 1]
        self._shared.panel_title   = panel_title[:_MAX_STR - 1]
        self._shared.progress_x100 = int(max(0.0, min(100.0, progress)) * 100)
        # Write visible LAST so the DLL sees consistent data
        self._shared.visible = 1

    def update(self, progress: float, detail: str = "") -> None:
        if not self._ready or self._shared is None:
            return
        if detail:
            self._shared.detail_text = detail[:_MAX_STR - 1]
        self._shared.progress_x100 = int(max(0.0, min(100.0, progress)) * 100)

    def hide(self) -> None:
        if self._shared is not None:
            self._shared.visible = 0

    def set_menu_state(self, visible: bool, active_tab: int) -> None:
        if not self._ready or self._shared is None:
            return
        self._shared.active_tab = max(0, int(active_tab))
        self._shared.menu_visible = 1 if visible else 0

    def push_menu_event(self, event_id: int) -> None:
        if not self._ready or self._shared is None:
            return
        self._shared.last_input_event = int(event_id)

    def set_menu_content(
        self,
        items: list,
        selected: int = 0,
        scroll: int = 0,
        thumb_paths: list | None = None,
        checked: list | None = None,
    ) -> None:
        """thumb_paths, if given, must be the same length/order as items —
        one row-thumbnail path per item (empty string = no thumbnail for
        that row). Only meaningful for the Stadiums tab today; pass None
        (the default) for every other tab so stale thumbnails don't linger
        in shared memory after switching tabs.

        checked, if given, must be the same length/order as items — True
        marks a row as "checked" (lit up via .row-checked in menu.rml)
        instead of encoding that into the row's own text. Only meaningful
        while the Stadiums country filter bubble is open; pass None (the
        default) otherwise so stale highlights don't linger."""
        if not self._ready or self._shared is None:
            return
        count = min(len(items), _MAX_MENU_ITEMS)
        for i in range(count):
            text = str(items[i])[:_MAX_MENU_ITEM_LEN - 1]
            self._shared.menu_items[i].value = text
            thumb = ""
            if thumb_paths and i < len(thumb_paths) and thumb_paths[i]:
                thumb = str(thumb_paths[i])[:_MAX_IMG - 1]
            self._shared.menu_item_thumb_paths[i].value = thumb
            self._shared.menu_item_checked[i] = 1 if (checked and i < len(checked) and checked[i]) else 0
        for i in range(count, _MAX_MENU_ITEMS):
            self._shared.menu_items[i].value = ""
            self._shared.menu_item_thumb_paths[i].value = ""
            self._shared.menu_item_checked[i] = 0
        self._shared.menu_item_count = count
        if count <= 0:
            self._shared.menu_selected_index = 0
            self._shared.menu_scroll_offset = 0
            return
        max_selected = count - 1
        safe_selected = max(0, min(int(selected), max_selected))
        safe_scroll = max(0, min(int(scroll), safe_selected))
        self._shared.menu_selected_index = safe_selected
        self._shared.menu_scroll_offset = safe_scroll

    def set_window_info(self, total_count: int, window_base: int) -> None:
        """Write virtual-scroll metadata so the C++ scrollbar reflects the real list size."""
        if not self._ready or self._shared is None:
            return
        self._shared.menu_total_count = int(total_count)
        self._shared.menu_window_base = int(window_base)

    def set_team_crests(self, home_path: str = "", away_path: str = "") -> None:
        """Write team crest PNG paths so the C++ dashboard panel can render them."""
        if not self._ready or self._shared is None:
            return
        self._shared.home_crest_path = home_path[:_MAX_IMG - 1]
        self._shared.away_crest_path = away_path[:_MAX_IMG - 1]

    def set_match_score_time(self, score_text: str = "", time_text: str = "") -> None:
        """Write the compact score ("2 x 1") and match clock ("23:45") text
        shown next to the crests in the dashboard's #dash-score widget —
        independent of set_dashboard_content()'s generic stat-line list."""
        if not self._ready or self._shared is None:
            return
        self._shared.score_text = score_text[:_MAX_STR - 1]
        self._shared.match_time_text = time_text[:_MAX_STR - 1]

    def set_preview_image(self, path: str) -> None:
        """Update the preview image path in shared memory without changing visible state."""
        if not self._ready or self._shared is None:
            return
        self._shared.image_path = (path or "")[:_MAX_IMG - 1]

    def show_toast(self, title: str, body: str = "", style: int = 0, icon: str = "") -> int:
        """Occupy the first free slot. Returns slot index (0-3) or -1 if all full.

        `icon` names a file under resources/rmlui/icons/<icon>.png (e.g.
        "tv", "scoreboard", "movie", "goalpost") — leave empty to use the
        default app icon, or if the asset type has no dedicated icon.
        """
        if not self._ready or self._shared is None:
            return -1
        for i in range(_MAX_TOASTS):
            if self._shared.toasts[i].visible == 0:
                self._shared.toasts[i].title   = title[:_MAX_STR - 1]
                self._shared.toasts[i].body    = body[:_MAX_STR - 1]
                self._shared.toasts[i].style   = style
                self._shared.toasts[i].icon    = (icon or "")[:_MAX_ICON - 1]
                self._shared.toasts[i].visible = 1
                return i
        return -1

    def hide_toast(self, slot: int = -1) -> None:
        """Hide a specific slot (0-3) or all slots when slot=-1."""
        if self._shared is None:
            return
        if slot == -1:
            for i in range(_MAX_TOASTS):
                self._shared.toasts[i].visible = 0
                self._shared.toasts[i].style   = 0
        elif 0 <= slot < _MAX_TOASTS:
            self._shared.toasts[slot].visible = 0
            self._shared.toasts[slot].style   = 0

    def show_kit_carousel(self, title: str, detail: str, hint: str,
                          image_prev: str, image_current: str, image_next: str,
                          direction: int = 0) -> None:
        """Show the kit-cycling carousel notification (F7-F10) — a dedicated
        panel/doc, independent of the stadium-loading show()/update()/hide()
        above, so the two never fight over one shared visible flag.

        `direction` (-1 = prev, +1 = next, 0 = no directional slide, e.g. the
        very first reveal) drives which way cgfs16_rmlui.cpp slides the
        changed slots in — see kit_carousel_cycle_seq's field comment."""
        if not self._ready or self._shared is None:
            return
        self._shared.kit_carousel_title         = title[:_MAX_STR - 1]
        self._shared.kit_carousel_detail        = detail[:_MAX_STR - 1]
        self._shared.kit_carousel_hint          = hint[:_MAX_STR - 1]
        self._shared.kit_carousel_image_prev    = (image_prev or "")[:_MAX_IMG - 1]
        self._shared.kit_carousel_image_current = (image_current or "")[:_MAX_IMG - 1]
        self._shared.kit_carousel_image_next    = (image_next or "")[:_MAX_IMG - 1]
        self._shared.kit_carousel_direction = int(direction)
        self._shared.kit_carousel_cycle_seq += 1
        # Write visible LAST so the DLL sees consistent data
        self._shared.kit_carousel_visible = 1

    def update_kit_carousel_images(self, image_prev: str, image_current: str, image_next: str) -> None:
        """Refresh the carousel's thumbnails in place (no re-trigger of the
        open animation) — used once a prefetched neighbor thumbnail finishes
        rendering in the background, after the panel is already showing."""
        if not self._ready or self._shared is None:
            return
        self._shared.kit_carousel_image_prev    = (image_prev or "")[:_MAX_IMG - 1]
        self._shared.kit_carousel_image_current = (image_current or "")[:_MAX_IMG - 1]
        self._shared.kit_carousel_image_next    = (image_next or "")[:_MAX_IMG - 1]

    def hide_kit_carousel(self) -> None:
        if self._shared is not None:
            self._shared.kit_carousel_visible = 0

    def set_gamepad_icon_dir(self, path: str) -> None:
        """Write the bundled gamepad button-icon directory (call once after inject)."""
        if not self._ready or self._shared is None:
            return
        self._shared.gamepad_icon_dir = (path or "")[:_MAX_IMG - 1]

    def set_keyboard_icon_dir(self, path: str) -> None:
        """Write the bundled keyboard key-icon directory (call once after inject)."""
        if not self._ready or self._shared is None:
            return
        self._shared.keyboard_icon_dir = (path or "")[:_MAX_IMG - 1]

    def set_rmlui_content_dir(self, path: str) -> None:
        """Write the resources/rmlui/ directory holding the loose .rml documents
        (call once after inject)."""
        if not self._ready or self._shared is None:
            return
        self._shared.rmlui_content_dir = (path or "")[:_MAX_IMG - 1]

    def set_rmlui_menu_mouse(self, x: int, y: int, left_down: bool) -> None:
        """Live mouse feed for the RmlUi menu's Context — x/y in the
        same window-coordinate space as get_menu_metrics()' viewport telemetry
        (0,0 = top-left client area). left_down is the raw continuous button
        state, not a click edge — cgfs16_rmlui_menu.cpp does its own down/up
        edge detection. Only consumed while the menu is visible."""
        if not self._ready or self._shared is None:
            return
        self._shared.rmlui_menu_mouse_x = int(x)
        self._shared.rmlui_menu_mouse_y = int(y)
        self._shared.rmlui_menu_mouse_left_down = 1 if left_down else 0

    def set_input_mode(self, gamepad: bool) -> None:
        """Tell cgfs16_rmlui_menu.cpp which hint bar to show: gamepad=True
        shows the gamepad hint row, gamepad=False shows the keyboard/mouse
        one. Never both at once — see OverlayShared::input_mode."""
        if not self._ready or self._shared is None:
            return
        self._shared.input_mode = 1 if gamepad else 0

    def set_menu_activate_down(self, down: bool) -> None:
        """Tell cgfs16_rmlui_menu.cpp whether the keyboard/gamepad "activate"
        input (Enter / A) is currently held, so #hero-btn can show the same
        press-shrink feedback a real mouse click already gets for free from
        RmlUi's own :active pseudo-class. See OverlayShared::menu_activate_down."""
        if not self._ready or self._shared is None:
            return
        self._shared.menu_activate_down = 1 if down else 0

    def set_stadium_filter_hint_visible(self, visible: bool) -> None:
        """Tell cgfs16_rmlui_menu.cpp whether to show the "Y: Filter" gamepad
        hint pill beside the wizard-header band — call with the full gating
        condition already resolved (Stadiums tab, past the scope step, not
        mid-wizard, filter panel not already open); the DLL only ANDs in
        gamepad-mode on top. See OverlayShared::stadium_filter_hint_visible."""
        if not self._ready or self._shared is None:
            return
        self._shared.stadium_filter_hint_visible = 1 if visible else 0

    def set_stadium_filter_panel_open(self, open_: bool) -> None:
        """Tell cgfs16_rmlui_menu.cpp whether the Stadiums country filter
        bubble is currently open, so #list-area renders as a small bordered
        popover instead of the normal full-height list. See
        OverlayShared::stadium_filter_panel_open."""
        if not self._ready or self._shared is None:
            return
        self._shared.stadium_filter_panel_open = 1 if open_ else 0

    def set_menu_loading(self, loading: bool) -> None:
        """Tell cgfs16_rmlui_menu.cpp to show a loading spinner in place of
        the item list — call with True immediately before a (synchronous)
        item-list scan that might take a moment (e.g. the Stadiums tab's
        discover_stadium_names()), and False right after. See
        OverlayShared::menu_loading."""
        if not self._ready or self._shared is None:
            return
        self._shared.menu_loading = 1 if loading else 0

    def set_list_header(self, text: str) -> None:
        """Set the wizard step header text shown above the menu item list (empty = hidden)."""
        if not self._ready or self._shared is None:
            return
        self._shared.list_header = (text or "")[:_MAX_STR - 1]

    def set_menu_selection(self, selected: int, scroll: int) -> None:
        if not self._ready or self._shared is None:
            return
        count = int(self._shared.menu_item_count)
        if count <= 0:
            self._shared.menu_selected_index = 0
            self._shared.menu_scroll_offset = 0
            return
        max_selected = count - 1
        safe_selected = max(0, min(int(selected), max_selected))
        safe_scroll = max(0, min(int(scroll), safe_selected))
        self._shared.menu_selected_index = safe_selected
        self._shared.menu_scroll_offset = safe_scroll

    def set_dashboard_content(self, items: list[str]) -> None:
        if not self._ready or self._shared is None:
            return
        count = min(len(items), _MAX_DASH_ITEMS)
        for i in range(count):
            text = str(items[i])[:_MAX_MENU_ITEM_LEN - 1]
            self._shared.dashboard_items[i].value = text
        for i in range(count, _MAX_DASH_ITEMS):
            self._shared.dashboard_items[i].value = ""
        self._shared.dashboard_item_count = count

    def get_menu_metrics(self) -> tuple[int, int, int, int]:
        """Return runtime menu telemetry as
        (output_hwnd, viewport_w, viewport_h, visible_rows). visible_rows is
        0 whenever cgfs16_rmlui_menu.cpp's RmlMenu_Sync hasn't run yet this
        session (neither the real F12 menu nor the F6 dev preview has ever
        opened) — callers should fall back to their own row estimate in
        that case."""
        if not self._ready or self._shared is None:
            return (0, 0, 0, 0)
        vw = int(self._shared.reserved0)
        vh = int(self._shared.reserved1)
        # Shared from x86 DLL as LONG; normalize into an unsigned handle value.
        hwnd = int(ctypes.c_uint32(int(self._shared.reserved2)).value)
        rows = int(self._shared.menu_visible_rows)
        if vw < 0:
            vw = 0
        if vh < 0:
            vh = 0
        if rows < 0:
            rows = 0
        return (hwnd, vw, vh, rows)

    def get_filter_grid_cols(self) -> int:
        """Real column count of the Stadiums country-filter grid this frame,
        computed by cgfs16_rmlui_menu.cpp's RmlMenu_Sync from the same
        box-model math #list-area.bubble's RCSS uses (see
        menu_filter_grid_cols' field comment). 0 before the menu has ever
        opened this session (RmlMenu_Sync hasn't run yet) — callers should
        fall back to their own default in that case, same as
        get_menu_metrics()'s visible_rows."""
        if not self._ready or self._shared is None:
            return 0
        cols = int(self._shared.menu_filter_grid_cols)
        return cols if cols > 0 else 0

    def get_menu_event(self) -> tuple[int, int, int]:
        """Return (seq, kind, index) from the DLL's "last event wins"
        click/scroll signal — see MenuEventListener in cgfs16_rmlui_menu.cpp.
        kind: 0=none, 1=tab_click, 2=item_click, 3=scroll_to, 4=hero_activate,
        5=close_click, 6=filter_toggle, 7=filter_clear. Callers should compare seq against their own
        last-seen value and only act when it changed (a single slot, not a
        queue)."""
        if not self._ready or self._shared is None:
            return (0, 0, 0)
        return (int(self._shared.menu_event_seq), int(self._shared.menu_event_kind),
                int(self._shared.menu_event_index))

    def reset_injected(self) -> None:
        """Call when FIFA exits so we re-inject on the next launch."""
        with self._lock:
            self._injected_pid = 0

    def destroy(self) -> None:
        self.hide()
        if self._shared_ptr:
            try:
                _k32.UnmapViewOfFile(self._shared_ptr)
            except Exception:
                pass
            self._shared_ptr = 0
            self._shared     = None
        if self._hmap:
            try:
                _k32.CloseHandle(self._hmap)
            except Exception:
                pass
            self._hmap = 0
        self._ready = False

    # ── Private ───────────────────────────────────────────────────────────────

    def _open_shared_memory(self) -> None:
        hmap = _k32.CreateFileMappingW(
            _INVALID_HANDLE_VALUE, None, _PAGE_READWRITE,
            0, ctypes.sizeof(_OverlayShared),
            _SHMEM_NAME)
        if not hmap:
            log.error("D3DOverlay: CreateFileMappingW failed (err=%d)",
                      ctypes.get_last_error())
            return

        ptr = _k32.MapViewOfFile(
            hmap, _FILE_MAP_ALL_ACCESS, 0, 0,
            ctypes.sizeof(_OverlayShared))
        if not ptr:
            log.error("D3DOverlay: MapViewOfFile failed (err=%d)",
                      ctypes.get_last_error())
            _k32.CloseHandle(hmap)
            return

        self._hmap       = hmap
        self._shared_ptr = ptr
        self._shared     = _OverlayShared.from_address(ptr)
        # Reset to hidden on startup
        self._shared.visible          = 0
        self._shared.progress_x100    = 0
        self._shared.stadium_name     = ""
        self._shared.detail_text      = ""
        self._shared.image_path       = ""
        self._shared.menu_visible     = 0
        self._shared.active_tab       = 0
        self._shared.last_input_event = 0
        self._shared.reserved0        = 0
        self._shared.menu_item_count = 0
        self._shared.menu_selected_index = 0
        self._shared.menu_scroll_offset = 0
        self._shared.reserved1 = 0
        self._shared.dashboard_item_count = 0
        self._shared.reserved2 = 0
        for i in range(_MAX_DASH_ITEMS):
            self._shared.dashboard_items[i].value = ""
        for i in range(_MAX_MENU_ITEMS):
            self._shared.menu_items[i].value = ""
            self._shared.menu_item_thumb_paths[i].value = ""
        for i in range(_MAX_TOASTS):
            self._shared.toasts[i].visible = 0
            self._shared.toasts[i].title   = ""
            self._shared.toasts[i].body    = ""
            self._shared.toasts[i].icon    = ""
        self._shared.gamepad_icon_dir = ""
        self._shared.keyboard_icon_dir = ""
        self._shared.rmlui_content_dir = ""
        self._shared.menu_visible_rows = 0
        self._shared.rmlui_menu_mouse_x = 0
        self._shared.rmlui_menu_mouse_y = 0
        self._shared.rmlui_menu_mouse_left_down = 0
        self._shared.menu_event_seq = 0
        self._shared.menu_event_kind = 0
        self._shared.menu_event_index = 0
        self._shared.kit_carousel_visible = 0
        self._shared.kit_carousel_title = ""
        self._shared.kit_carousel_detail = ""
        self._shared.kit_carousel_hint = ""
        self._shared.kit_carousel_image_prev = ""
        self._shared.kit_carousel_image_current = ""
        self._shared.kit_carousel_image_next = ""
        self._shared.kit_carousel_cycle_seq = 0
        self._shared.kit_carousel_direction = 0
        self._ready = True
        log.debug("D3DOverlay: shared memory opened at 0x%X, size=%d",
                  ptr, ctypes.sizeof(_OverlayShared))

    def _find_inject_exe(self) -> str | None:
        """Locate the x86 injector helper exe (next to DLL or in runtime/)."""
        dll_p = Path(self._dll_path)
        candidates = [
            dll_p.parent / "cgfs16_inject.exe",           # e.g. bin/
            dll_p.parent.parent / "runtime" / "cgfs16_inject.exe",
        ]
        for c in candidates:
            if c.exists():
                return str(c)
        return None

    def _do_inject(self, pid: int) -> bool:
        """Inject via the x86 cgfs16_inject.exe helper.

        FIFA 16 is a 32-bit process.  Our Python host is 64-bit, so any
        GetProcAddress(LoadLibraryW) we obtain here is a 64-bit address
        that is invalid inside the 32-bit target.  The x86 helper exe
        solves this: being 32-bit itself, it holds the correct 32-bit
        LoadLibraryW address for the WOW64 target.
        """
        import subprocess

        injector = self._find_inject_exe()
        if not injector:
            log.error("D3DOverlay: cgfs16_inject.exe not found "
                      "(run build.bat to compile it)")
            return False

        log.debug("D3DOverlay: running injector: %s %s %s",
                  injector, pid, self._dll_path)
        try:
            result = subprocess.run(
                [injector, str(pid), self._dll_path],
                capture_output=True,
                timeout=12,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except subprocess.TimeoutExpired:
            log.error("D3DOverlay: cgfs16_inject.exe timed out")
            return False
        except Exception as exc:
            log.error("D3DOverlay: failed to run injector: %s", exc)
            return False

        # The C exe writes narrow (ANSI) text to stderr/stdout even though
        # it uses fwprintf — on Windows pipes the CRT converts wide chars
        # to the ANSI codepage, so decode with 'mbcs' (system ANSI codepage).
        def _decode(b: bytes) -> str:
            for enc in ('mbcs', 'latin-1', 'utf-8'):
                try:
                    return b.decode(enc, errors='replace').strip()
                except Exception:
                    continue
            return repr(b)

        stdout = _decode(result.stdout)
        stderr = _decode(result.stderr)
        log.debug("D3DOverlay: inject helper stdout=%r stderr=%r rc=%d",
                  stdout, stderr, result.returncode)
        if result.returncode != 0:
            log.error("D3DOverlay: inject helper failed (rc=%d): %s",
                      result.returncode, stderr or stdout)
            return False

        log.info("D3DOverlay: DLL injected into pid %d (%s)", pid, stdout)
        return True
