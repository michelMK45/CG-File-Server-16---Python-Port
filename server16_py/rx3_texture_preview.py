"""Preview box for the textures inside a Match Asset pack (ball / referee /
wipe / adboard), with left/right arrows to step through them.

A pack is a folder of one or more .rx3 files, and each .rx3 embeds several
textures (a wipe carries about eight), so a single static thumbnail says
little. Every texture of every .rx3 in the pack is rendered -- by the 32-bit
FifaLibrary bridge, see AssetRuntime.render_rx3_textures -- and the arrows walk
through them as one flat sequence, the caption naming the file each one comes
from.
"""
from __future__ import annotations

import queue
import threading
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import ttk
from typing import Callable

from PIL import Image, ImageTk

from .file_tools import match_asset_rx3_files

PREV_ICON = "◀"
NEXT_ICON = "▶"


@dataclass(frozen=True)
class TextureFrame:
    """One texture of the pack: texture `index` (0-based) of `count` inside `rx3`."""

    rx3: str  # shown in the caption: the .rx3's path relative to the pack folder
    index: int
    count: int
    png: Path


class Rx3TexturePreview(tk.Frame):
    """Usage:

        preview = Rx3TexturePreview(parent, app, "Textures", image_size=(420, 280))
        preview.show_pack(pack_dir, render_file)   # re-callable; the latest call wins

    `render_file(rx3_path) -> list[Path]` returns the PNG of each texture of one
    .rx3 in order (AssetRuntime.render_match_asset_textures, bound to the pack's
    kind). It runs on ONE background thread, a file at a time, so a slow 32-bit
    render never blocks Tk, and each file's textures join the sequence as soon as
    that render ends. The thread never touches Tk: it only fills a queue that
    this widget drains from its own `after` poll, so closing the dialog
    mid-render can't leave a callback aimed at a dead widget (the same hand-off
    AssetGridPickerDialog uses).
    """

    POLL_MS = 50

    def __init__(self, parent: tk.Misc, app, title: str, image_size: tuple[int, int] = (420, 280)) -> None:
        super().__init__(
            parent,
            bg=app.card_soft,
            highlightthickness=1,
            highlightbackground="#243654",
        )
        self.app = app
        self.image_size = image_size
        self._closed = False
        self._generation = 0
        self._frames: list[TextureFrame] = []
        self._index = 0
        self._photo: ImageTk.PhotoImage | None = None
        self._results: queue.Queue[tuple[int, str, list[Path] | None]] = queue.Queue()
        self._outstanding = 0
        self._poll_job: str | None = None

        self.grid_columnconfigure(0, weight=1)
        tk.Label(self, text=title, bg=app.card_soft, fg=app.muted, font=("Bahnschrift", 9)).grid(
            row=0, column=0, sticky="w", padx=8, pady=(8, 4),
        )
        # Fixed-pixel image box + grid_propagate(False), for the reason spelled out
        # in SettingsSectionFrame._build_stadium_preview_box: a Label's own
        # width/height count characters while it shows text and stop reserving
        # room once it shows an image, which clipped previews.
        image_box = tk.Frame(self, bg=app.panel, width=image_size[0], height=image_size[1])
        image_box.grid(row=1, column=0, padx=8)
        image_box.grid_propagate(False)
        image_box.grid_columnconfigure(0, weight=1)
        image_box.grid_rowconfigure(0, weight=1)
        self._image_label = tk.Label(
            image_box, text=app.tr("placeholder.no_preview"), bg=app.panel, fg=app.muted,
            anchor="center", justify="center", wraplength=image_size[0] - 16,
        )
        self._image_label.grid(row=0, column=0, sticky="nsew")

        nav = tk.Frame(self, bg=app.card_soft)
        nav.grid(row=2, column=0, pady=(6, 0))
        self._prev_button = ttk.Button(nav, text=PREV_ICON, width=3, command=lambda: self.step(-1), state="disabled")
        self._prev_button.grid(row=0, column=0)
        self._counter_label = tk.Label(
            nav, text="", bg=app.card_soft, fg=app.fg, font=("Bahnschrift", 10, "bold"), width=9,
        )
        self._counter_label.grid(row=0, column=1, padx=8)
        self._next_button = ttk.Button(nav, text=NEXT_ICON, width=3, command=lambda: self.step(1), state="disabled")
        self._next_button.grid(row=0, column=2)

        self._caption_label = tk.Label(
            self, text="", bg=app.card_soft, fg=app.muted, font=("Consolas", 9), wraplength=image_size[0],
        )
        self._caption_label.grid(row=3, column=0, padx=8, pady=(4, 8))

        # Arrow keys work once the image has been clicked (a Label only takes
        # focus on click, so it never steals Tab focus from the form).
        self._image_label.bind("<Left>", lambda _e: self.step(-1))
        self._image_label.bind("<Right>", lambda _e: self.step(1))
        self._image_label.bind("<Button-1>", lambda _e: self._image_label.focus_set())

    # ------------------------------------------------------------------ public

    @property
    def frames(self) -> list[TextureFrame]:
        return list(self._frames)

    @property
    def index(self) -> int:
        return self._index

    def show_pack(self, pack_dir: Path | None, render_file: Callable[[Path], list[Path]]) -> None:
        """Shows the textures of `pack_dir`'s .rx3 files, replacing whatever was
        shown. A newer call supersedes an older one still rendering."""
        self._generation += 1
        generation = self._generation
        self._frames = []
        self._index = 0
        self._outstanding = 0
        self._drain_stale()
        rx3_files = match_asset_rx3_files(pack_dir) if pack_dir is not None else []
        if not rx3_files:
            self._show_message(self.app.tr("placeholder.no_preview" if pack_dir is None else "dialog.editor.preview.rx3_empty"))
            return
        self._show_message(self.app.tr("dialog.kitmix.loading"))
        self._outstanding = len(rx3_files)

        def worker() -> None:
            for rx3 in rx3_files:
                if self._closed or self._generation != generation:
                    return
                name = rx3.relative_to(pack_dir).as_posix()
                try:
                    pngs: list[Path] | None = render_file(rx3)
                except Exception:  # noqa: BLE001 - this one file just contributes no textures
                    pngs = None
                self._results.put((generation, name, pngs))

        threading.Thread(target=worker, daemon=True).start()
        self._schedule_poll()

    def step(self, delta: int) -> None:
        """Moves `delta` textures through the sequence, wrapping around."""
        if len(self._frames) < 2:
            return
        self._index = (self._index + delta) % len(self._frames)
        self._show_current()

    def destroy(self) -> None:
        # _closed is also read by the render thread, which can outlive the widget.
        self._closed = True
        if self._poll_job is not None:
            try:
                self.after_cancel(self._poll_job)
            except tk.TclError:
                pass
            self._poll_job = None
        super().destroy()

    # ---------------------------------------------------------------- internals

    def _drain_stale(self) -> None:
        while True:
            try:
                self._results.get_nowait()
            except queue.Empty:
                return

    def _schedule_poll(self) -> None:
        if self._poll_job is None and not self._closed:
            self._poll_job = self.after(self.POLL_MS, self._poll)

    def _poll(self) -> None:
        self._poll_job = None
        if self._closed:
            return
        had_frames = bool(self._frames)
        while True:
            try:
                generation, name, pngs = self._results.get_nowait()
            except queue.Empty:
                break
            if generation != self._generation:
                continue  # a newer show_pack superseded the render that produced this
            self._outstanding -= 1
            if pngs:
                self._frames += [TextureFrame(name, index, len(pngs), png) for index, png in enumerate(pngs)]
        if self._frames and not had_frames:
            self._show_current()  # the first texture just arrived: replace "Loading..."
        elif not self._frames and self._outstanding <= 0:
            self._show_message(self.app.tr("dialog.kitmix.preview_error"))
        else:
            # Later files only grow the sequence; leave the texture being looked at alone.
            self._update_nav()
        if self._outstanding > 0:
            self._schedule_poll()

    def _show_message(self, text: str) -> None:
        self._photo = None
        self._image_label.configure(image="", text=text)
        self._caption_label.configure(text="")
        self._update_nav()

    def _show_current(self) -> None:
        if not self._frames:
            self._update_nav()
            return
        frame = self._frames[self._index]
        photo = self._load_photo(frame.png)
        if photo is None:
            self._photo = None
            self._image_label.configure(image="", text=self.app.tr("dialog.kitmix.preview_error"))
        else:
            self._photo = photo  # keep a reference or Tk drops the image
            self._image_label.configure(image=photo, text="")
        self._caption_label.configure(
            text=self.app.tr("dialog.editor.preview.rx3_caption", file=frame.rx3, index=frame.index + 1, count=frame.count),
        )
        self._update_nav()

    def _update_nav(self) -> None:
        total = len(self._frames)
        if total:
            # Still rendering the rest of the pack: the total can grow, so mark it.
            suffix = "+" if self._outstanding > 0 else ""
            self._counter_label.configure(text=f"{self._index + 1} / {total}{suffix}")
        else:
            self._counter_label.configure(text="")
        state = "normal" if total > 1 else "disabled"
        self._prev_button.configure(state=state)
        self._next_button.configure(state=state)

    def _load_photo(self, path: Path) -> ImageTk.PhotoImage | None:
        try:
            with Image.open(path) as source:
                image = source.convert("RGBA")
            # Textures often keep a gloss/spec mask in the alpha channel; one that
            # is entirely ~0 would render as an empty box, so show its colour alone.
            if image.getchannel("A").getextrema()[1] < 8:
                image = image.convert("RGB")
            image.thumbnail(self.image_size)
            return ImageTk.PhotoImage(image)
        except Exception:  # noqa: BLE001 - an unreadable PNG just shows the error placeholder
            return None
