"""Bigger view of a small preview: clicking a preview in the Kits tab opens this
dialog with a large version of it.

`load()` produces the image on a worker thread -- a fresh large render (kit
drawings) or the full-size source (kit UI thumbnails, textures) -- and hands it back
through a queue drained by the dialog's own `after` poll, so the thread never
touches Tk and closing the dialog mid-load is harmless.
"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from typing import Callable, Optional

from PIL import Image, ImageTk

from .dialogs import BaseDialog

ZOOM_BOX = (560, 560)   # the image is fitted inside this box (times the UI zoom)
MAX_UPSCALE = 3.0       # small sources are enlarged at most this much


def fit_size(size: tuple[int, int], box: tuple[int, int], max_upscale: float = MAX_UPSCALE) -> tuple[int, int]:
    """`size` scaled to fit inside `box`, keeping its aspect ratio; enlarged by no
    more than `max_upscale`."""
    w, h = size
    scale = min(box[0] / w, box[1] / h, max_upscale)
    return max(1, round(w * scale)), max(1, round(h * scale))


class ImageZoomDialog(BaseDialog):
    POLL_MS = 40

    def __init__(self, master: tk.Misc, load: Callable[[], Optional[Image.Image]], title: str = "") -> None:
        super().__init__(master, "dialog.zoom.title")
        if title:
            self.title(title)
        self.resizable(False, False)
        settings = getattr(master, "settings", None)
        zoom = getattr(settings, "ui_zoom", 1.0) if settings is not None else 1.0
        self._box = (round(ZOOM_BOX[0] * zoom), round(ZOOM_BOX[1] * zoom))
        self._photo: Optional[ImageTk.PhotoImage] = None
        self._closed = False
        self._result: queue.Queue = queue.Queue()

        frame = tk.Frame(self, bg=self.card_soft, highlightthickness=1, highlightbackground="#243654")
        frame.pack(padx=14, pady=(14, 6))
        self.image_label = tk.Label(
            frame, bg=self.card_soft, fg=self.muted, text=self.tr("dialog.kitmix.loading"),
            font=("Bahnschrift", 9), width=40, height=12, cursor="hand2",
        )
        self.image_label.pack(padx=10, pady=10)
        tk.Label(self, text=self.tr("dialog.zoom.hint"), bg=self.bg, fg=self.muted,
                 font=("Bahnschrift", 8)).pack(pady=(0, 10))
        self.image_label.bind("<Button-1>", lambda _e: self.destroy())
        self.bind("<Escape>", lambda _e: self.destroy())

        def worker() -> None:
            try:
                image = load()
                if image is not None:
                    image = image.convert("RGBA")   # decode here, off the Tk thread
                    size = fit_size(image.size, self._box)
                    if size != image.size:
                        image = image.resize(size, Image.LANCZOS)
            except Exception:  # noqa: BLE001 - shown as "preview unavailable"
                image = None
            self._result.put(image)

        threading.Thread(target=worker, daemon=True).start()
        self._center()
        self.after(self.POLL_MS, self._poll)

    def _poll(self) -> None:
        if self._closed:
            return
        try:
            image = self._result.get_nowait()
        except queue.Empty:
            self.after(self.POLL_MS, self._poll)
            return
        if image is None:
            self.image_label.configure(text=self.tr("dialog.kitmix.preview_error"))
            return
        self._photo = ImageTk.PhotoImage(image)
        self.image_label.configure(image=self._photo, text="", width=image.width, height=image.height)
        self._center()

    def _center(self) -> None:
        """Center over the main window (BaseDialog leaves placement to Windows)."""
        try:
            self.update_idletasks()
            owner = self.master
            w, h = self.winfo_reqwidth(), self.winfo_reqheight()
            x = owner.winfo_rootx() + max(0, (owner.winfo_width() - w) // 2)
            y = owner.winfo_rooty() + max(0, (owner.winfo_height() - h) // 2)
            self.geometry(f"+{x}+{y}")
        except tk.TclError:
            pass

    def destroy(self) -> None:
        self._closed = True
        super().destroy()
