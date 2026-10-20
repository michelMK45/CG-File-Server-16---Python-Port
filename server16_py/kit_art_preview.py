"""Kit drawing previews shared by the Kits subtabs (Classic, Simple, Advanced).

KitArtPreview is a framed kit drawing (kit_classic_art) of three texture sources
-- shirt, shorts, socks -- rendered off the Tk thread; clicking it opens a larger
render in ImageZoomDialog. attach_zoom() gives any other preview the same
click-to-enlarge behaviour. All drawings go through app.kit_classic.art (one disk
cache, one lock).
"""

from __future__ import annotations

import io
import queue
import threading
import tkinter as tk
from pathlib import Path
from typing import Callable, Hashable, Optional

from PIL import Image, ImageTk

from .image_zoom_dialog import ImageZoomDialog
from .kit_classic_art import art_size

ZOOM_ART_SIZE = 380   # art_size() -> 456x547: fits the zoom dialog without enlarging

Sources = tuple[Optional[Path], Optional[Path], Optional[Path]]   # shirt, shorts, socks


class IconLoader:
    """Renders PNGs on one background thread and hands them back to Tk through a
    queue drained by an `after` poll (the thread never touches Tk). A new request()
    supersedes the previous one; stale results are dropped. Each job is
    (key, render) where render() -> PNG bytes runs under `lock`."""

    POLL_MS = 40

    def __init__(self, widget: tk.Misc, lock: threading.Lock,
                 on_ready: Callable[[Hashable, Optional[bytes]], None]) -> None:
        self.widget = widget
        self.lock = lock
        self.on_ready = on_ready
        self.generation = 0
        self._done_generation = 0
        self._results: queue.Queue = queue.Queue()
        self._polling = False

    def request(self, jobs: list[tuple[Hashable, Callable[[], bytes]]]) -> None:
        self.generation += 1
        generation = self.generation
        unique = list({key: render for key, render in jobs}.items())

        def worker() -> None:
            for key, render in unique:
                if generation != self.generation:
                    return
                try:
                    with self.lock:
                        png = render()
                except Exception:  # noqa: BLE001 - shown as an empty / unavailable preview
                    png = None
                self._results.put((generation, key, png))
            self._results.put((generation, None, None))

        threading.Thread(target=worker, daemon=True).start()
        if not self._polling:
            self._polling = True
            self.widget.after(self.POLL_MS, self._poll)

    def _poll(self) -> None:
        try:
            alive = bool(self.widget.winfo_exists())
        except tk.TclError:
            alive = False
        if not alive:
            self._polling = False
            return
        while True:
            try:
                generation, key, png = self._results.get_nowait()
            except queue.Empty:
                break
            if generation != self.generation:
                continue
            if key is None:
                self._done_generation = generation
            else:
                self.on_ready(key, png)
        if self._done_generation == self.generation:
            self._polling = False
            return
        self.widget.after(self.POLL_MS, self._poll)


def render_art_image(app, sources: Sources, size: int) -> Image.Image:
    """Kit drawing of `sources` as a PIL image. Call from a worker thread."""
    runtime = app.kit_classic
    with runtime.art_lock:
        png = runtime.art.render_png(*sources, size=size)
    return Image.open(io.BytesIO(png))


def attach_zoom(app, widget: tk.Widget, open_zoom: Callable[[], None]) -> None:
    """Hand cursor, "click to enlarge" tooltip and the click itself."""
    widget.configure(cursor="hand2")
    widget.bind("<Button-1>", lambda _e: open_zoom())
    app._add_tooltip(widget, "tooltip.preview_zoom")


def open_art_zoom(app, sources: Sources, title: str = "") -> None:
    ImageZoomDialog(app, lambda: render_art_image(app, sources, ZOOM_ART_SIZE), title)


def advanced_mix_sources(jersey: dict, shorts: dict, current: Optional[Path]) -> Optional[Sources]:
    """What the Advanced tab's mix will look like: each part comes from its chosen
    source (an .rx3 or an imported image) or, on "keep current", from the kit the
    mix starts from (`current`). Socks follow the shorts, as in kit_worker.py.
    None when there is nothing to draw at all."""
    def pick(source: dict) -> Optional[Path]:
        if source.get("mode") in ("rx3", "img") and source.get("path"):
            return Path(source["path"])
        return current

    shirt, bottom = pick(jersey), pick(shorts)
    if shirt is None and bottom is None:
        return None
    return shirt, bottom, bottom


class KitArtPreview(tk.Frame):
    """Usage:

        preview = KitArtPreview(parent, app, size=110)
        preview.show((shirt_rx3, shorts_rx3, socks_rx3))   # re-callable; the latest call wins
        preview.show(None, placeholder="(no changes)")

    `framed=False` drops the border/padding (small inline thumbnails)."""

    def __init__(self, parent: tk.Misc, app, size: int, framed: bool = True, bg: Optional[str] = None,
                 zoom_title: str = "") -> None:
        bg = bg or app.card_soft
        super().__init__(parent, bg=bg, highlightthickness=1 if framed else 0, highlightbackground="#243654")
        self.app = app
        self.size = size
        self.zoom_title = zoom_title
        self._sources: Optional[Sources] = None
        self._photo: Optional[ImageTk.PhotoImage] = None
        w, h = art_size(size)
        pad = 8 if framed else 0
        box = tk.Frame(self, bg=bg, width=w + 2 * pad, height=h + 2 * pad)
        box.pack()
        box.pack_propagate(False)
        self.label = tk.Label(box, bg=bg, fg=app.muted, text="", font=("Bahnschrift", 8),
                              wraplength=max(40, w - 8), justify="center")
        self.label.pack(fill="both", expand=True)
        self._loader = IconLoader(self.label, app.kit_classic.art_lock, self._on_ready)
        attach_zoom(app, self.label, self._open_zoom)

    def show(self, sources: Optional[Sources], placeholder: str = "") -> None:
        if sources is not None and sources == self._sources and self._photo is not None:
            return   # already showing it (e.g. re-selecting the same mix)
        self._sources = sources
        self._photo = None
        if sources is None:
            self.label.configure(image="", text=placeholder)
            self._loader.request([])
            return
        self.label.configure(image="", text=self.app.tr("dialog.kitmix.loading"))
        art = self.app.kit_classic.art
        size = self.size
        self._loader.request([(sources, lambda: art.render_png(*sources, size=size))])

    def _on_ready(self, key: Hashable, png: Optional[bytes]) -> None:
        if key != self._sources:
            return
        if png is None:
            self.label.configure(image="", text=self.app.tr("dialog.kitmix.preview_error"))
            return
        try:
            self._photo = ImageTk.PhotoImage(Image.open(io.BytesIO(png)))
        except Exception:  # noqa: BLE001
            self.label.configure(image="", text=self.app.tr("dialog.kitmix.preview_error"))
            return
        self.label.configure(image=self._photo, text="")

    def _open_zoom(self) -> None:
        if self._sources is not None:
            open_art_zoom(self.app, self._sources, self.zoom_title)
