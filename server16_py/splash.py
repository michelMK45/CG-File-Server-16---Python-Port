from __future__ import annotations

import base64
import ctypes
import io
import struct
import sys
import threading
import time
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path

from . import __version__

BG = "#0b1220"
PANEL = "#111a2b"
BORDER = "#22314b"
TRACK = "#1c2a44"
ACCENT = "#4cc2ff"
FG = "#e6edf3"
MUTED = "#93a1b2"

TITLE = "CG SERVER 16"

# Logical (96-DPI) sizes; compute_layout() scales them to the real display.
_WIDTH = 520
_HEIGHT = 200
_MARGIN = 28
_ICON = 128
_ICON_GAP = 30
_SEGMENTS = 28
_TAIL_SEGMENTS = 12.0
_REVOLUTION_SECONDS = 1.2
_FADE_OUT_SECONDS = 0.12
_FRAME_MS = 15
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


@dataclass(frozen=True)
class Layout:
    width: int
    height: int
    icon_px: int
    icon_x: int
    icon_y: int
    text_x: int
    title_y: int
    subtitle_y: int
    spin_cx: int
    spin_cy: int
    spin_r: int
    ring_width: int
    message_x: int
    message_y: int
    title_px: int
    subtitle_px: int
    message_px: int


def compute_layout(scale: float) -> Layout:
    """All pixel positions for the splash at a given display scale. Shared by
    the Tk window below and by scripts/make_boot_splash.py, which draws the
    static PyInstaller bootloader splash with the same geometry so the
    handoff between the two looks like one window."""

    def px(value: float) -> int:
        return round(value * scale)

    icon_px = px(_ICON)
    margin = px(_MARGIN)
    width = px(_WIDTH)
    height = max(px(_HEIGHT), icon_px + 2 * margin)
    center_y = height // 2
    text_x = margin + icon_px + px(_ICON_GAP)
    spin_r = px(17)
    spin_cy = center_y + px(28)
    return Layout(
        width=width,
        height=height,
        icon_px=icon_px,
        icon_x=margin,
        icon_y=(height - icon_px) // 2,
        text_x=text_x,
        title_y=center_y - px(44),
        subtitle_y=center_y - px(16),
        spin_cx=text_x + spin_r,
        spin_cy=spin_cy,
        spin_r=spin_r,
        ring_width=max(2, px(4)),
        message_x=text_x + 2 * spin_r + px(14),
        message_y=spin_cy,
        title_px=px(24),
        subtitle_px=px(12),
        message_px=px(14),
    )


def enable_dpi_awareness() -> None:
    """Must run before the first Tk window of the process is created -- a
    process that is not DPI aware gets bitmap-stretched (blurry) windows and
    virtualized coordinates on scaled displays. Calling it a second time is a
    harmless no-op (Windows refuses to change the mode once set)."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
    except Exception:
        pass


def dpi_scale() -> float:
    try:
        return max(1.0, ctypes.windll.user32.GetDpiForSystem() / 96.0)
    except Exception:
        return 1.0


def find_icon_path() -> Path | None:
    candidates = (
        Path(__file__).resolve().parent.parent / "server16.ico",  # source tree, or PyInstaller's _MEIPASS
        Path(sys.executable).resolve().parent / "server16.ico",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _ico_png_entries(path: Path) -> list[tuple[int, bytes]]:
    """(size, PNG bytes) for every PNG-compressed image in an .ico. Reading
    the directory by hand keeps PIL out of the path to the first frame: Tk
    decodes PNG natively, and server16.ico stores every size as PNG."""
    data = path.read_bytes()
    _reserved, kind, count = struct.unpack_from("<HHH", data, 0)
    if kind != 1:
        return []
    entries: list[tuple[int, bytes]] = []
    for index in range(count):
        width, _h, _colors, _r, _planes, _bpp, size, offset = struct.unpack_from("<BBBBHHII", data, 6 + 16 * index)
        chunk = data[offset:offset + size]
        if chunk[:8] == _PNG_MAGIC:
            entries.append((width or 256, chunk))
    return entries


def icon_png(path: Path | None, target_px: int) -> bytes | None:
    """PNG bytes of the icon at exactly target_px when possible. An exact
    entry in the .ico is used as-is; otherwise the nearest larger one is
    resampled with PIL (imported only in that case), falling back to the
    largest entry that fits if PIL is unavailable."""
    if path is None:
        return None
    try:
        entries = sorted(_ico_png_entries(path))
    except Exception:
        return None
    if not entries:
        return None
    for size, chunk in entries:
        if size == target_px:
            return chunk
    larger = [entry for entry in entries if entry[0] > target_px]
    try:
        from PIL import Image

        source = Image.open(io.BytesIO((larger[0] if larger else entries[-1])[1])).convert("RGBA")
        buffer = io.BytesIO()
        source.resize((target_px, target_px), Image.LANCZOS).save(buffer, "PNG")
        return buffer.getvalue()
    except Exception:
        fitting = [entry for entry in entries if entry[0] <= target_px]
        return (fitting[-1] if fitting else entries[0])[1]


def _blend(low: str, high: str, amount: float) -> str:
    amount = 0.0 if amount < 0.0 else 1.0 if amount > 1.0 else amount
    low_rgb = [int(low[i:i + 2], 16) for i in (1, 3, 5)]
    high_rgb = [int(high[i:i + 2], 16) for i in (1, 3, 5)]
    mixed = [round(a + (b - a) * amount) for a, b in zip(low_rgb, high_rgb)]
    return "#%02x%02x%02x" % tuple(mixed)


class SplashScreen:
    """Borderless "loading" window: app icon on the left, name/version and a
    spinning circle with a status message on the right.

    Runs its own Tk interpreter on a dedicated thread, which is the whole
    point: startup imports and shutdown cleanup block the main thread for
    seconds at a time (imports, subprocess calls, thread joins), and the
    spinner must keep turning through all of it. Two rules keep that safe:

    * Nothing outside this thread ever touches the splash's Tk objects --
      other threads only set plain attributes/events that its own tick loop
      polls.
    * The interpreter is destroyed, and every reference to it dropped, on
      this same thread. A Tk interpreter freed from another thread aborts the
      process ("Tcl_AsyncDelete: async handler deleted by the wrong
      thread"), so no reference cycle may outlive the thread -- hence a class
      with bound methods rather than self-referencing closures.

    The constructor returns once the window is on screen (or gave up), so
    callers can rely on it being visible before they start slow work. It
    appears immediately, with no fade-in: the point is to be seen as early
    as possible."""

    def __init__(self, message: str = "") -> None:
        self._message = message
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._shown_at = 0.0
        self._thread = threading.Thread(target=self._run, name="splash-screen", daemon=True)
        self._thread.start()
        self._ready.wait(timeout=3.0)

    def set_message(self, message: str) -> None:
        self._message = message

    def close(self, *, wait: bool = True, min_visible: float = 0.0) -> None:
        """Fades the window out and tears it down. `min_visible` keeps it up
        for at least that many seconds after it appeared, so a fast shutdown
        doesn't flash a spinner that never had time to turn. `wait=False`
        returns immediately and lets the fade finish in the background --
        only safe while the process is going to keep running afterwards."""
        if self._shown_at and min_visible > 0:
            remaining = min_visible - (time.perf_counter() - self._shown_at)
            if remaining > 0:
                time.sleep(remaining)
        self._stop.set()
        if wait and self._thread is not threading.current_thread():
            self._thread.join(timeout=2.0)

    def _run(self) -> None:
        window = None
        try:
            window = _SplashWindow(self)
            window.show()
        except Exception:
            window = None
        finally:
            self._ready.set()
        if window is None:
            return
        try:
            window.run()
        except Exception:
            pass
        finally:
            window.teardown()
            window = None


class _SplashWindow:
    def __init__(self, owner: SplashScreen) -> None:
        self.owner = owner
        self.root: tk.Tk | None = tk.Tk()
        # Tk() registers itself as tkinter's process-wide default root when
        # none exists yet. This one lives on its own thread, so it must never
        # be picked up by a Variable()/PhotoImage() elsewhere that passes no
        # master -- the app creates dozens of those on the main thread.
        if getattr(tk, "_default_root", None) is self.root:
            tk._default_root = None
        self.scale = dpi_scale()
        self.layout = compute_layout(self.scale)
        self.canvas: tk.Canvas | None = None
        self.icon: tk.PhotoImage | None = None
        self.segment_ids: list[int] = []
        self.message_id = 0
        self.shown_message = ""
        self.started_at = 0.0
        self.fade_out_at: float | None = None
        self._build()

    def _build(self) -> None:
        root = self.root
        assert root is not None
        layout = self.layout
        root.withdraw()
        root.overrideredirect(True)
        root.configure(bg=PANEL)
        x = (root.winfo_screenwidth() - layout.width) // 2
        y = (root.winfo_screenheight() - layout.height) // 2
        root.geometry(f"{layout.width}x{layout.height}+{x}+{y}")
        try:
            root.attributes("-topmost", True)
        except Exception:
            pass
        canvas = tk.Canvas(root, width=layout.width, height=layout.height, bg=PANEL, highlightthickness=0, bd=0)
        canvas.place(x=0, y=0)
        self.canvas = canvas
        canvas.create_rectangle(0, 0, layout.width - 1, layout.height - 1, outline=BORDER)

        png = icon_png(find_icon_path(), layout.icon_px)
        if png is not None:
            try:
                self.icon = tk.PhotoImage(master=root, data=base64.b64encode(png).decode("ascii"))
                canvas.create_image(layout.icon_x, layout.icon_y, image=self.icon, anchor="nw")
            except Exception:
                self.icon = None

        canvas.create_text(
            layout.text_x, layout.title_y, text=TITLE, fill=FG, anchor="w",
            font=("Bahnschrift", -layout.title_px, "bold"),
        )
        canvas.create_text(
            layout.text_x, layout.subtitle_y, text=f"v{__version__}", fill=MUTED, anchor="w",
            font=("Bahnschrift", -layout.subtitle_px),
        )

        radius = layout.spin_r
        box = (
            layout.spin_cx - radius, layout.spin_cy - radius,
            layout.spin_cx + radius, layout.spin_cy + radius,
        )
        step = 360.0 / _SEGMENTS
        for index in range(_SEGMENTS):
            # Segment 0 sits at 12 o'clock and the index grows clockwise;
            # Tk measures arc angles counter-clockwise from 3 o'clock.
            start = 90.0 - (index + 1) * step
            self.segment_ids.append(
                canvas.create_arc(
                    *box, start=start, extent=step + 1.0, style="arc", outline=TRACK, width=layout.ring_width,
                )
            )
        self.message_id = canvas.create_text(
            layout.message_x, layout.message_y, text="", fill=MUTED, anchor="w",
            font=("Bahnschrift", -layout.message_px),
        )

    def show(self) -> None:
        root = self.root
        assert root is not None
        self._apply_message()
        root.deiconify()
        root.update()
        self.started_at = time.perf_counter()
        self.owner._shown_at = self.started_at

    def run(self) -> None:
        root = self.root
        assert root is not None
        root.after(0, self._tick)
        root.mainloop()

    def _apply_message(self) -> None:
        message = self.owner._message
        if message != self.shown_message and self.canvas is not None:
            self.shown_message = message
            self.canvas.itemconfigure(self.message_id, text=message)

    def _tick(self) -> None:
        root = self.root
        if root is None:
            return
        now = time.perf_counter()
        self._apply_message()

        head = ((now - self.started_at) / _REVOLUTION_SECONDS * _SEGMENTS) % _SEGMENTS
        canvas = self.canvas
        if canvas is not None:
            for index, item in enumerate(self.segment_ids):
                behind = (head - index) % _SEGMENTS
                strength = 0.0
                if behind < _TAIL_SEGMENTS:
                    strength = (1.0 - behind / _TAIL_SEGMENTS) ** 1.6
                canvas.itemconfigure(item, outline=_blend(TRACK, ACCENT, strength))

        if self.owner._stop.is_set():
            if self.fade_out_at is None:
                self.fade_out_at = now
            alpha = 1.0 - (now - self.fade_out_at) / _FADE_OUT_SECONDS
            if alpha <= 0.0:
                root.quit()
                return
            try:
                root.attributes("-alpha", alpha)
            except Exception:
                pass
        root.after(_FRAME_MS, self._tick)

    def teardown(self) -> None:
        root, self.root = self.root, None
        self.canvas = None
        self.icon = None
        if root is not None:
            try:
                root.destroy()
            except Exception:
                pass
