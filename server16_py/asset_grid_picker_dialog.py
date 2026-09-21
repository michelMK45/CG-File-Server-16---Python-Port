from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk

from PIL import Image, ImageTk

from .asset_grid_items import AssetGridItem
from .dialogs import BaseDialog


class AssetGridPickerDialog(BaseDialog):
    """Visual alternative to a Combobox for any settings.ini value that has a
    preview: shows every option as a thumbnail + name in a scrollable grid so
    the user can see what they're choosing instead of stepping through a
    dropdown one value at a time. Returns the chosen item's `value` via
    `self.result` (None if cancelled) -- same `close_ok(...)` modal convention
    as TeamPickerDialog/StadiumPickerDialog:

        dlg = AssetGridPickerDialog(app, "Police", items, current="4")
        app.wait_window(dlg)
        if dlg.result is not None:
            ...  # dlg.result is the chosen AssetGridItem.value

    Static previews (`image_path`) are decoded a few per event-loop tick so a
    big grid opens instantly instead of freezing on the first paint;
    generated ones (`render`) run sequentially on one background thread and
    each cell fills in as its render finishes. The render thread never calls
    into Tk: it only puts results on a queue that the dialog drains from its
    own `after` poll (the codebase's usual worker -> Tk hand-off), so closing
    the dialog mid-render can't leave a callback aimed at a dead widget.
    """

    # Same size the stadium editor's own single-preview boxes use for these
    # assets, so a thumbnail here is as legible as the one beside the combo.
    THUMB_SIZE = (170, 140)
    # Static images decoded per event-loop tick (see _load_static_previews).
    LOAD_BATCH = 6
    # How often the Tk side drains finished renders while any are outstanding.
    RENDER_POLL_MS = 50
    BORDER = "#243654"
    # Horizontal room one cell needs beyond its thumbnail: the image box's own
    # 8px padx (x2) + the cell's 2px highlight border (x2) + the 3px grid gap (x2).
    CELL_EXTRA_WIDTH = 26

    def __init__(
        self,
        master: tk.Misc,
        field_label: str,
        items: list[AssetGridItem],
        current: str = "",
        thumb_size: tuple[int, int] = THUMB_SIZE,
    ) -> None:
        super().__init__(master, "dialog.asset_grid.title")
        self._closed = False
        # Pending `after` jobs, cancelled in destroy() -- an after callback
        # that fires once its widget is gone is a Tcl "invalid command name".
        self._load_job: str | None = None
        self._render_poll_job: str | None = None
        self._visible_job: str | None = None
        self._render_results: queue.Queue[tuple[int, Path | None]] = queue.Queue()
        self._render_outstanding = 0
        self._laid_out = False
        self._items = list(items)
        self._thumb_size = thumb_size
        self._cells: list[tk.Frame] = []
        self._thumbs: list[tk.Label] = []
        self._photos: dict[int, ImageTk.PhotoImage] = {}
        self._selected: int | None = None
        self._columns = 0

        heading = self.tr("dialog.asset_grid.title", field=field_label)
        self.title(heading)
        self._set_geometry(940, 700, 560, 460)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        topbar = tk.Frame(self, bg=self.bg)
        topbar.grid(row=0, column=0, sticky="ew", padx=14, pady=(14, 10))
        topbar.grid_columnconfigure(0, weight=1)
        self._dark_label(topbar, heading, bg=self.bg, font=("Bahnschrift", 18, "bold")).grid(row=0, column=0, sticky="w")
        self._dark_label(
            topbar, self.tr("dialog.asset_grid.hint"), bg=self.bg, muted=True, font=("Bahnschrift", 10),
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))

        card = tk.Frame(self, bg=self.card, highlightthickness=1, highlightbackground=self.BORDER)
        card.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 10))
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(0, weight=1)
        self._canvas = tk.Canvas(card, bg=self.card, highlightthickness=0, bd=0)
        scrollbar = ttk.Scrollbar(card, orient="vertical", command=self._canvas.yview, style="Server16.Vertical.TScrollbar")
        self._canvas.configure(yscrollcommand=scrollbar.set)
        self._canvas.grid(row=0, column=0, sticky="nsew", padx=(8, 0), pady=8)
        scrollbar.grid(row=0, column=1, sticky="ns", padx=4, pady=8)
        self._grid_frame = tk.Frame(self._canvas, bg=self.card)
        self._grid_window = self._canvas.create_window((0, 0), window=self._grid_frame, anchor="nw")
        self._grid_frame.bind("<Configure>", lambda _e: self._canvas.configure(scrollregion=self._canvas.bbox("all")))
        self._canvas.bind("<Configure>", self._on_canvas_configure)
        self._bind_mousewheel(self._canvas, self._grid_frame)

        bar = tk.Frame(self, bg=self.bg)
        bar.grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 14))
        bar.grid_columnconfigure(0, weight=1)
        self._selected_label = self._dark_label(
            bar, self.tr("dialog.asset_grid.no_selection"), bg=self.bg, muted=True, font=("Bahnschrift", 10), anchor="w",
        )
        self._selected_label.grid(row=0, column=0, sticky="w")
        self._select_button = ttk.Button(bar, text=self.tr("dialog.asset_grid.select"), command=self._confirm, state="disabled")
        self._select_button.grid(row=0, column=1, padx=(8, 0))
        ttk.Button(bar, text=self.tr("button.cancel"), command=self.destroy).grid(row=0, column=2, padx=(8, 0))

        self.bind("<Return>", lambda _e: self._confirm())
        self.bind("<Escape>", lambda _e: self.destroy())
        self.bind("<Left>", lambda _e: self._move_selection(-1))
        self.bind("<Right>", lambda _e: self._move_selection(1))
        self.bind("<Up>", lambda _e: self._move_selection(-max(1, self._columns)))
        self.bind("<Down>", lambda _e: self._move_selection(max(1, self._columns)))

        if not self._items:
            self._dark_label(
                self._grid_frame, self.tr("dialog.asset_grid.empty"), muted=True, font=("Bahnschrift", 11),
            ).grid(row=0, column=0, padx=20, pady=20)
            return

        for index, item in enumerate(self._items):
            self._build_cell(index, item)
        # Provisional layout so cells exist in the grid from the start; the
        # first <Configure> of the canvas re-flows to however many columns
        # actually fit the real window width.
        self._relayout(3)

        static_pending = [i for i, item in enumerate(self._items) if item.image_path is not None]
        render_pending = [i for i, item in enumerate(self._items) if item.image_path is None and item.render is not None]
        self._load_static_previews(static_pending)
        if render_pending:
            self._start_render_worker(render_pending)

        wanted = (current or "").strip()
        for index, item in enumerate(self._items):
            if item.value == wanted:
                self._select(index)
                self._schedule_selection_visible()
                break

    def destroy(self) -> None:
        # _closed is also read by the render thread, which can easily outlive
        # the dialog (the 32-bit render subprocess takes seconds).
        self._closed = True
        for job in (self._load_job, self._render_poll_job, self._visible_job):
            if job is not None:
                try:
                    self.after_cancel(job)
                except tk.TclError:
                    pass
        super().destroy()

    # ------------------------------------------------------------------ cells

    def _build_cell(self, index: int, item: AssetGridItem) -> None:
        width, height = self._thumb_size
        cell = tk.Frame(self._grid_frame, bg=self.card_soft, highlightthickness=2, highlightbackground=self.BORDER)
        cell.grid_columnconfigure(0, weight=1)
        cell.grid_rowconfigure(1, weight=1)

        # Fixed-pixel image box + grid_propagate(False): a tk.Label's own
        # width/height are character counts while it shows text and stop
        # reserving room once an image is set, which is what used to clip
        # previews elsewhere (see the same box in settings_editor.py's
        # _build_stadium_preview_box). The frame keeps its size regardless.
        image_box = tk.Frame(cell, bg=self.panel, width=width, height=height)
        image_box.grid(row=0, column=0, padx=8, pady=(8, 4))
        image_box.grid_propagate(False)
        image_box.grid_columnconfigure(0, weight=1)
        image_box.grid_rowconfigure(0, weight=1)
        will_have_image = item.image_path is not None or item.render is not None
        thumb = tk.Label(
            image_box,
            text=self.tr("dialog.kitmix.loading" if will_have_image else "placeholder.no_preview"),
            bg=self.panel,
            fg=self.muted,
            anchor="center",
            justify="center",
            wraplength=width - 12,
        )
        thumb.grid(row=0, column=0, sticky="nsew")
        name = tk.Label(
            cell, text=item.label, bg=self.card_soft, fg=self.fg, font=("Bahnschrift", 10), wraplength=width, justify="center",
        )
        name.grid(row=1, column=0, sticky="n", padx=8, pady=(0, 8))

        for widget in (cell, image_box, thumb, name):
            widget.bind("<Button-1>", lambda _e, i=index: self._select(i))
            widget.bind("<Double-Button-1>", lambda _e, i=index: self._activate(i))
        self._bind_mousewheel(cell, image_box, thumb, name)
        self._cells.append(cell)
        self._thumbs.append(thumb)

    def _columns_for_width(self, width: int) -> int:
        return max(1, width // (self._thumb_size[0] + self.CELL_EXTRA_WIDTH))

    def _on_canvas_configure(self, event) -> None:
        self._canvas.itemconfigure(self._grid_window, width=event.width)
        if not self._cells:
            return
        columns = self._columns_for_width(event.width)
        reflowed = columns != self._columns
        if reflowed:
            self._relayout(columns)
        # The pre-selected cell can only be scrolled to once the window has its
        # real size, and a reflow moves every cell -- so (re)bring the selection
        # into view on the first real layout and after any column-count change,
        # not just once at construction (when the canvas is still unsized).
        if (reflowed or not self._laid_out) and self._selected is not None:
            self._schedule_selection_visible()
        self._laid_out = True

    def _relayout(self, columns: int) -> None:
        for column in range(max(self._columns, columns)):
            active = column < columns
            self._grid_frame.grid_columnconfigure(column, weight=1 if active else 0, uniform="cell" if active else "")
        for index, cell in enumerate(self._cells):
            cell.grid(row=index // columns, column=index % columns, sticky="nsew", padx=3, pady=3)
        self._columns = columns

    # -------------------------------------------------------------- selection

    def _select(self, index: int) -> None:
        if not 0 <= index < len(self._items):
            return
        if self._selected is not None:
            self._cells[self._selected].configure(highlightbackground=self.BORDER)
        self._selected = index
        self._cells[index].configure(highlightbackground=self.accent)
        self._selected_label.configure(text=self.tr("dialog.asset_grid.selected", name=self._items[index].label))
        self._select_button.configure(state="normal")

    def _activate(self, index: int) -> None:
        self._select(index)
        self._confirm()

    def _move_selection(self, delta: int) -> None:
        if not self._items:
            return
        target = 0 if self._selected is None else self._selected + delta
        if not 0 <= target < len(self._items):
            return
        self._select(target)
        self._ensure_visible(target)

    def _confirm(self) -> None:
        if self._selected is None:
            return
        self.close_ok(self._items[self._selected].value)

    def _schedule_selection_visible(self) -> None:
        if self._visible_job is not None:
            self.after_cancel(self._visible_job)
        self._visible_job = self.after_idle(self._ensure_selection_visible)

    def _ensure_selection_visible(self) -> None:
        self._visible_job = None
        if self._selected is not None:
            self._ensure_visible(self._selected)

    def _ensure_visible(self, index: int) -> None:
        """Scrolls the grid just enough to bring cell `index` fully into view."""
        if self._closed or not 0 <= index < len(self._cells):
            return
        if self._canvas.winfo_height() <= 1:
            return  # not mapped/sized yet; the first real <Configure> schedules this again
        # Flush pending geometry, then refresh the scroll region ourselves: its
        # <Configure> binding may not have run yet, and fractions passed to
        # yview_moveto are relative to whatever the region currently is.
        self.update_idletasks()
        bounds = self._canvas.bbox("all")
        if not bounds:
            return
        self._canvas.configure(scrollregion=bounds)
        total = max(1, bounds[3] - bounds[1])
        cell = self._cells[index]
        top = cell.winfo_y()
        bottom = top + cell.winfo_height()
        view_top = self._canvas.canvasy(0)
        view_bottom = view_top + self._canvas.winfo_height()
        margin = 6  # keep a sliver of the neighbouring row visible
        if top < view_top:
            self._canvas.yview_moveto(max(0, top - margin) / total)
        elif bottom > view_bottom:
            self._canvas.yview_moveto((bottom + margin - self._canvas.winfo_height()) / total)

    # ------------------------------------------------------------ mouse wheel

    def _bind_mousewheel(self, *widgets: tk.Misc) -> None:
        # <MouseWheel> only fires on the exact widget under the cursor, so every
        # widget that can sit under it (canvas, frame, each cell and its
        # children) needs its own binding.
        def on_mousewheel(event):
            if event.delta:
                self._canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            return "break"

        for widget in widgets:
            widget.bind("<MouseWheel>", on_mousewheel)

    # ---------------------------------------------------------------- previews

    def _show_image(self, index: int, path: Path | None, fallback_key: str) -> None:
        thumb = self._thumbs[index]
        self._photos.pop(index, None)
        if path is None or not Path(path).is_file():
            thumb.configure(image="", text=self.tr(fallback_key))
            return
        try:
            with Image.open(path) as source:
                image = source.convert("RGBA")
            image.thumbnail(self._thumb_size)
            photo = ImageTk.PhotoImage(image)
        except Exception:  # noqa: BLE001 - a corrupt/unreadable image just shows the placeholder
            thumb.configure(image="", text=self.tr("dialog.kitmix.preview_error"))
            return
        self._photos[index] = photo  # keep a reference or Tk drops the image
        thumb.configure(image=photo, text="")

    def _load_static_previews(self, pending: list[int]) -> None:
        self._load_job = None
        if self._closed:
            return
        for index in pending[: self.LOAD_BATCH]:
            self._show_image(index, self._items[index].image_path, "placeholder.no_preview")
        remaining = pending[self.LOAD_BATCH:]
        if remaining:
            self._load_job = self.after(1, lambda: self._load_static_previews(remaining))

    def _start_render_worker(self, pending: list[int]) -> None:
        def worker() -> None:
            for index in pending:
                if self._closed:
                    return
                try:
                    path = self._items[index].render()
                except Exception:  # noqa: BLE001 - surfaced as a placeholder on that cell
                    path = None
                self._render_results.put((index, path))

        self._render_outstanding = len(pending)
        threading.Thread(target=worker, daemon=True).start()
        self._render_poll_job = self.after(self.RENDER_POLL_MS, self._poll_render_results)

    def _poll_render_results(self) -> None:
        self._render_poll_job = None
        if self._closed:
            return
        while True:
            try:
                index, path = self._render_results.get_nowait()
            except queue.Empty:
                break
            self._render_outstanding -= 1
            self._show_image(index, path, "dialog.kitmix.preview_error")
        if self._render_outstanding > 0:
            self._render_poll_job = self.after(self.RENDER_POLL_MS, self._poll_render_results)
