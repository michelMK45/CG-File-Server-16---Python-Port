"""Keeping this app's Tk windows inside the monitor they open on.

Reported live on a 4K display at 150% scaling (v1.6.1): both the launch
splash and the main window came up far larger than the screen -- their
*content* drawn at the right size in the top-left corner, the window box
running off the bottom-right edge, so the window had to be maximized by
double-clicking its title bar before it was usable.

No geometry() call in this app can produce those sizes (the splash asks for
520x200 logical px, the main window for 1024x680 * ui_zoom), and it does not
reproduce at 125% here, so the cause is environmental -- display scaling, a
DPI-awareness mode Windows refused to change, a third-party window manager.
Rather than guess, every window now goes through this module, which:

* sizes against the *work area* (monitor minus taskbar) of the monitor the
  window will actually appear on, never `winfo_screenwidth()` -- that is the
  primary monitor's width, which is both wrong on multi-monitor setups and
  unbounded by the taskbar;
* clamps the requested size to that work area, so an oversized request can
  never leave the window bigger than the screen;
* verifies, once the window is mapped, that Windows honoured the size, and
  re-applies it once (logging the mismatch) if it did not.

Thread note: every function here takes the Tk window as an argument and
touches nothing else, so it is safe to call from splash.py's own Tk thread
-- but only ever *from that window's own thread*, like any other Tk call.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes

from .win32_types import (
    MDT_EFFECTIVE_DPI,
    MONITOR_DEFAULTTONEAREST,
    MONITORINFO,
    POINT,
    RECT,
)

# A window smaller than this is a bug in the caller, not a small screen --
# clamping is allowed to shrink a window, never to collapse it.
_MIN_SIDE = 200


def _user32():
    return ctypes.windll.user32


def _anchor(window) -> tuple[int, int] | None:
    """The point that decides which monitor a window belongs to: its own
    top-left corner, or None while it is still unmapped.

    Deliberately NOT MonitorFromWindow. That picks the monitor holding the
    largest part of the window rect, and an oversized window -- the whole
    reason this module exists -- spills across monitors, so on a dual-monitor
    desktop it answers with the *neighbouring* screen. Confirmed live here
    (1920x1080 @96dpi next to 2560x1440 @120dpi): a window blown up to
    3840x1417 on the 1080p screen was reported as being on the 1440p one, and
    clamping then moved it to the wrong monitor. The top-left corner is the
    corner clamping shrinks towards, and it is where the title bar is, so it
    stays the right answer however wrong the size is.

    Unmapped windows have no meaningful position yet -- Tk has not placed
    them -- so callers fall back to the monitor under the mouse cursor, which
    on a multi-monitor desktop is the screen the user is looking at."""
    try:
        if not window.winfo_ismapped():
            return None
        return int(window.winfo_rootx()), int(window.winfo_rooty())
    except Exception:
        return None


def _monitor_handle(point: tuple[int, int] | None):
    """The monitor containing (or nearest to) *point*, or the one under the
    mouse cursor when no point is given."""
    user32 = _user32()
    location = POINT()
    if point is None:
        try:
            user32.GetCursorPos(ctypes.byref(location))
        except Exception:
            location.x = location.y = 0
    else:
        location.x, location.y = point
    try:
        return user32.MonitorFromPoint(location, MONITOR_DEFAULTTONEAREST)
    except Exception:
        return None


def work_area(window=None) -> tuple[int, int, int, int]:
    """(left, top, width, height) of the usable desktop area on the monitor
    *window* is on -- the full monitor minus the taskbar. Falls back to the
    primary monitor's metrics if the monitor can't be resolved."""
    handle = _monitor_handle(_anchor(window) if window is not None else None)
    if handle:
        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(MONITORINFO)
        try:
            if _user32().GetMonitorInfoW(handle, ctypes.byref(info)):
                rect = info.rcWork
                width = rect.right - rect.left
                height = rect.bottom - rect.top
                if width > 0 and height > 0:
                    return rect.left, rect.top, width, height
        except Exception:
            pass
    rect = RECT()
    try:
        # SPI_GETWORKAREA (0x0030) -- primary monitor only, but still taskbar-aware.
        if _user32().SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0):
            return rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top
    except Exception:
        pass
    try:
        return 0, 0, _user32().GetSystemMetrics(0), _user32().GetSystemMetrics(1)
    except Exception:
        return 0, 0, 1920, 1080


def display_scale(window=None) -> float:
    """Display scale of that same monitor (1.0 == 96 DPI).

    Per-monitor rather than GetDpiForSystem(), which reports the *primary*
    monitor's DPI -- on a mixed-DPI desktop that is the wrong number for a
    window opening on the other screen. Never below 1.0: this app's layouts
    are authored at 96 DPI and are not readable scaled down."""
    handle = _monitor_handle(_anchor(window) if window is not None else None)
    if handle:
        dpi_x = wintypes.UINT()
        dpi_y = wintypes.UINT()
        try:
            if ctypes.windll.shcore.GetDpiForMonitor(
                handle, MDT_EFFECTIVE_DPI, ctypes.byref(dpi_x), ctypes.byref(dpi_y)
            ) == 0 and dpi_x.value:
                return max(1.0, dpi_x.value / 96.0)
        except Exception:
            pass
    try:
        return max(1.0, _user32().GetDpiForSystem() / 96.0)
    except Exception:
        return 1.0


def frame_overhead(window=None) -> tuple[int, int]:
    """(extra width, extra height) the title bar and borders add around the
    client area.

    Every size in this module -- like every `wm geometry` size -- is a
    *client* size, so a window clamped to exactly the work area would still
    hang its caption and borders off the edge. winfo_x/y give the frame's
    origin and winfo_rootx/y the client's, so the difference is the border
    and caption (0 for an overrideredirect window, and 0 before the window is
    mapped, when there is nothing to measure yet)."""
    if window is None:
        return 0, 0
    try:
        if not window.winfo_ismapped():
            return 0, 0
        border = max(0, int(window.winfo_rootx()) - int(window.winfo_x()))
        caption = max(0, int(window.winfo_rooty()) - int(window.winfo_y()))
    except Exception:
        return 0, 0
    return border * 2, caption + border


def fit(width: int, height: int, window=None) -> tuple[int, int]:
    """*width* x *height* clamped so the whole window -- frame included --
    fits the work area of *window*'s monitor."""
    _, _, area_w, area_h = work_area(window)
    extra_w, extra_h = frame_overhead(window)
    # The cap always wins over the floor: a window wider than the screen is
    # the very thing this module exists to prevent, so _MIN_SIDE only lifts a
    # size the work area still has room for.
    max_w = max(1, area_w - extra_w)
    max_h = max(1, area_h - extra_h)
    return (
        max(min(int(width), max_w), min(_MIN_SIDE, max_w)),
        max(min(int(height), max_h), min(_MIN_SIDE, max_h)),
    )


def centered_geometry(window, width: int, height: int) -> tuple[str, int, int]:
    """A "WxH+X+Y" string centering *width* x *height* (clamped) on the work
    area, plus the clamped client size actually used. The offsets are the work
    area's own origin, so this lands on the right monitor and below the
    taskbar rather than at an absolute screen position; X/Y position the
    *frame*, so the frame is what ends up centered."""
    left, top, area_w, area_h = work_area(window)
    width, height = fit(width, height, window)
    extra_w, extra_h = frame_overhead(window)
    x = left + max(0, (area_w - (width + extra_w)) // 2)
    y = top + max(0, (area_h - (height + extra_h)) // 2)
    return f"{width}x{height}+{x}+{y}", width, height


def apply_centered(window, width: int, height: int) -> tuple[int, int]:
    """Size and center *window*; returns the size asked of Tk."""
    geometry, width, height = centered_geometry(window, width, height)
    window.geometry(geometry)
    return width, height


def clamp_in_place(window, log=None, label: str = "window") -> bool:
    """Pull *window* back inside the work area of the monitor it is on,
    without re-centering it.

    This is the standing guard rather than a one-shot check: whatever inflated
    the windows in the 4K/150% report is environmental and unidentified, so it
    may strike at map time, at a later resize, or when the window is dragged
    to another monitor -- all of which raise <Configure>, which is where this
    is called from. Returns True when it had to change something; a healthy
    window makes it compare four numbers and return False.

    Acts on the *size* only. A window that is merely parked half off the edge
    of the screen is left exactly where it is -- people do that on purpose,
    and a guard that yanked it back 250ms later would be a worse bug than the
    one being fixed. The position is touched only when the window had to be
    shrunk and no longer fits where it sat, and even then it keeps its
    top-left corner rather than being re-centered."""
    try:
        if not window.winfo_exists() or window.wm_state() == "zoomed":
            return False
        current_w = window.winfo_width()
        current_h = window.winfo_height()
        # winfo_x/y, not winfo_rootx/y: geometry()'s +X+Y positions the frame,
        # and re-applying the client origin would walk the window down and to
        # the right by the border/caption size every time this fires.
        current_x = int(window.winfo_x())
        current_y = int(window.winfo_y())
    except Exception:
        return False
    if current_w <= 1 and current_h <= 1:
        return False  # not mapped yet
    left, top, area_w, area_h = work_area(window)
    width, height = fit(current_w, current_h, window)
    if (width, height) == (current_w, current_h):
        return False  # fits: never second-guess where the user put it
    extra_w, extra_h = frame_overhead(window)
    # Keep the top-left corner reachable: a title bar pushed off the top of
    # the screen can't be grabbed again.
    x = min(max(current_x, left), left + max(0, area_w - (width + extra_w)))
    y = min(max(current_y, top), top + max(0, area_h - (height + extra_h)))
    if log is not None:
        try:
            log(
                f"{label} was {current_w}x{current_h}, larger than the "
                f"{area_w}x{area_h} work area ({describe(window)}) -- clamped to {width}x{height}"
            )
        except Exception:
            pass
    try:
        window.geometry(f"{width}x{height}+{x}+{y}")
    except Exception:
        return False
    return True


def verify(window, width: int, height: int, log=None, label: str = "window") -> bool:
    """Once *window* is mapped: did Windows give it the size we asked for?

    Re-applies the geometry once and returns False when it did not, so the
    symptom this module exists for (a window several times its requested
    size) self-corrects instead of reaching the user. *log* is an optional
    callable -- the mismatch is worth recording either way, since nothing
    reproduces it here."""
    try:
        actual_w = window.winfo_width()
        actual_h = window.winfo_height()
    except Exception:
        return True
    # Tk reports 1x1 for a window that has not been mapped yet; that is not a
    # mismatch, just a question asked too early.
    if actual_w <= 1 and actual_h <= 1:
        return True
    if abs(actual_w - width) <= 2 and abs(actual_h - height) <= 2:
        return True
    if log is not None:
        try:
            log(
                f"{label} geometry mismatch: asked {width}x{height}, got {actual_w}x{actual_h} "
                f"({describe(window)}) -- re-applying"
            )
        except Exception:
            pass
    try:
        apply_centered(window, width, height)
    except Exception:
        pass
    return False


def describe(window=None) -> str:
    """One line of display diagnostics for the log -- the missing piece for
    the oversized-window report this module was written for."""
    parts = []
    try:
        awareness = ctypes.c_int(-1)
        ctypes.windll.shcore.GetProcessDpiAwareness(None, ctypes.byref(awareness))
        parts.append(f"dpi_awareness={awareness.value}")
    except Exception:
        parts.append("dpi_awareness=?")
    try:
        parts.append(f"system_dpi={_user32().GetDpiForSystem()}")
    except Exception:
        pass
    left, top, area_w, area_h = work_area(window)
    parts.append(f"work_area={area_w}x{area_h}+{left}+{top}")
    parts.append(f"monitor_scale={display_scale(window):.2f}")
    if window is not None:
        try:
            parts.append(f"screen={window.winfo_screenwidth()}x{window.winfo_screenheight()}")
            parts.append(f"tk_scaling={float(window.tk.call('tk', 'scaling')):.3f}")
        except Exception:
            pass
    return ", ".join(parts)
