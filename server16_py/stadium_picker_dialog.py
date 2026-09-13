from __future__ import annotations

import tkinter as tk
import unicodedata
from pathlib import Path
from tkinter import ttk

from PIL import Image, ImageTk

from .dialogs import BaseDialog
from .file_tools import discover_stadium_names, resolve_stadium_preview_path, stadium_preview_fallback_path


class StadiumPickerDialog(BaseDialog):
    """Stadium-name browser for any settings-editor "Key" field that's keyed
    by a real StadiumGBD folder name -- [scoreboardstdname], [stadiumnetname],
    [stadiumgoalpost], and [stadiumgoalposttexture] all reuse this via
    `SectionSpec.key_stadium_picker` (`settings_editor.py`'s `_pick_stadium_key`).

    Only lists stadiums that do NOT already have an entry in the calling
    section -- the point of this picker is to help find a stadium that still
    needs this section's setting configured, not to re-browse ones already
    done. Returns the chosen stadium name (str) via `self.result` -- same
    `close_ok(...)` modal convention already used by TeamPickerDialog/
    StadiumDialog:

        dlg = StadiumPickerDialog(app, exedir, configured_names)
        app.wait_window(dlg)
        if dlg.result:
            ...  # dlg.result is the stadium name string
    """

    PREVIEW_IMAGE_SIZE = (260, 260)

    def __init__(self, master: tk.Misc, exedir: str | Path, configured_names: set[str]) -> None:
        super().__init__(master, "dialog.stadium_picker.title")
        self._set_geometry(780, 660, 660, 540)

        self._preview_image: ImageTk.PhotoImage | None = None
        self.stadium_source = Path(exedir) / "StadiumGBD"

        all_names = discover_stadium_names(self.stadium_source)
        configured_normalized = {self._normalize_text(name) for name in configured_names}
        self._available_names = sorted(
            (name for name in all_names if self._normalize_text(name) not in configured_normalized),
            key=lambda name: name.lower(),
        )
        self._filtered_names: list[str] = []
        self._selected_name: str | None = None

        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        topbar = tk.Frame(self, bg=self.bg)
        topbar.grid(row=0, column=0, columnspan=2, sticky="ew", padx=14, pady=(14, 10))
        topbar.grid_columnconfigure(0, weight=1)
        self._dark_label(topbar, self.tr("dialog.stadium_picker.title"), bg=self.bg, font=("Bahnschrift", 18, "bold")).grid(row=0, column=0, sticky="w")
        self.status_label = self._dark_label(
            topbar, self.tr("dialog.stadium_picker.count", count=len(self._available_names)), bg=self.bg, muted=True, font=("Bahnschrift", 10),
        )
        self.status_label.grid(row=1, column=0, sticky="w", pady=(2, 0))

        list_card = self._card(self, self.tr("dialog.stadium_picker.stadiums"))
        list_card.grid(row=1, column=0, sticky="nsew", padx=(14, 6), pady=(0, 14))

        preview_card = self._card(self, self.tr("dialog.stadium_picker.preview"))
        preview_card.grid(row=1, column=1, sticky="nsew", padx=(6, 14), pady=(0, 14))

        # --- Stadium list (left) ---
        list_body = tk.Frame(list_card, bg=self.card)
        list_body.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        list_body.grid_columnconfigure(0, weight=1)
        list_body.grid_rowconfigure(2, weight=1)

        self._dark_label(list_body, self.tr("dialog.stadium_picker.search"), muted=True, font=("Bahnschrift", 10), anchor="w").grid(row=0, column=0, sticky="w")
        self.search_var = tk.StringVar()
        search_entry = ttk.Entry(list_body, textvariable=self.search_var, style="Server16.TEntry")
        search_entry.grid(row=1, column=0, sticky="ew", pady=(4, 8))
        search_entry.bind("<KeyRelease>", lambda _e: self._refresh_list())

        list_wrap = tk.Frame(list_body, bg=self.card)
        list_wrap.grid(row=2, column=0, sticky="nsew")
        list_wrap.grid_columnconfigure(0, weight=1)
        list_wrap.grid_rowconfigure(0, weight=1)
        self.stadium_list = self._dark_listbox(list_wrap, exportselection=False, font=("Consolas", 10))
        list_scroll = ttk.Scrollbar(list_wrap, orient="vertical", command=self.stadium_list.yview, style="Server16.Vertical.TScrollbar")
        self.stadium_list.configure(yscrollcommand=list_scroll.set)
        self.stadium_list.grid(row=0, column=0, sticky="nsew")
        list_scroll.grid(row=0, column=1, sticky="ns", padx=(6, 0))
        self.stadium_list.bind("<<ListboxSelect>>", lambda _e: self._on_select())
        self.stadium_list.bind("<Double-Button-1>", lambda _e: self._confirm())

        # --- Preview (right) ---
        preview_body = tk.Frame(preview_card, bg=self.card)
        preview_body.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        preview_body.grid_columnconfigure(0, weight=1)
        preview_body.grid_rowconfigure(0, weight=1)

        # Same fixed-height, grid_propagate(False) image box as
        # TeamPickerDialog._build_preview_box -- dedicated purely to the
        # image (image_size + 20px padding), independent of any label text,
        # so it can never be clipped by sharing its budget with something
        # else's rendered height.
        image_size = self.PREVIEW_IMAGE_SIZE
        image_wrap = tk.Frame(preview_body, bg=self.panel, highlightthickness=1, highlightbackground="#243654", height=image_size[1] + 20)
        image_wrap.grid(row=0, column=0, sticky="ew")
        image_wrap.grid_propagate(False)
        image_wrap.grid_columnconfigure(0, weight=1)
        image_wrap.grid_rowconfigure(0, weight=1)
        self.preview_label = tk.Label(image_wrap, text=self.tr("dialog.team_picker.no_preview"), bg=self.panel, fg=self.muted, anchor="center", justify="center", relief="flat")
        self.preview_label.grid(row=0, column=0, sticky="nsew")
        self.preview_label.image_size = image_size

        self.selected_label = self._dark_label(preview_body, self.tr("dialog.stadium_picker.no_selection"), muted=True, wraplength=280, justify="left", anchor="w")
        self.selected_label.grid(row=1, column=0, sticky="ew", pady=(8, 0))

        # --- Actions ---
        action_bar = tk.Frame(self, bg=self.bg)
        action_bar.grid(row=2, column=0, columnspan=2, sticky="ew", padx=14, pady=(0, 14))
        action_bar.grid_columnconfigure(0, weight=1)
        action_bar.grid_columnconfigure(1, weight=1)
        self.select_button = ttk.Button(action_bar, text=self.tr("button.select_stadium"), command=self._confirm, state="disabled")
        self.select_button.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ttk.Button(action_bar, text=self.tr("button.cancel"), command=self.destroy).grid(row=0, column=1, sticky="ew", padx=(6, 0))

        self._refresh_list()

    @staticmethod
    def _normalize_text(value: str) -> str:
        normalized = unicodedata.normalize("NFKD", value or "")
        return "".join(char for char in normalized if not unicodedata.combining(char)).lower()

    def _refresh_list(self) -> None:
        query = self._normalize_text(self.search_var.get().strip())
        self.stadium_list.delete(0, "end")
        self._filtered_names = [name for name in self._available_names if not query or query in self._normalize_text(name)]
        for name in self._filtered_names:
            self.stadium_list.insert("end", name)

    def _on_select(self) -> None:
        selection = self.stadium_list.curselection()
        if not selection:
            return
        index = selection[0]
        if index >= len(self._filtered_names):
            return
        name = self._filtered_names[index]
        self._selected_name = name
        self.selected_label.configure(text=self.tr("dialog.stadium_picker.selected_stadium", name=name))
        self.select_button.configure(state="normal")
        image_path = resolve_stadium_preview_path(self.stadium_source, name) or stadium_preview_fallback_path()
        self._update_preview(image_path, name)

    def _update_preview(self, image_path, fallback_text: str) -> None:
        self._preview_image = None
        if image_path is None or not image_path.exists():
            self.preview_label.configure(image="", text=fallback_text, compound="center")
            return
        try:
            image = Image.open(image_path).convert("RGBA")
            image.thumbnail(self.preview_label.image_size)
            photo = ImageTk.PhotoImage(image)
        except Exception:
            self.preview_label.configure(image="", text=fallback_text, compound="center")
            return
        self._preview_image = photo
        self.preview_label.configure(image=photo, text="", compound="center")

    def _confirm(self) -> None:
        if self._selected_name is None:
            return
        self.close_ok(self._selected_name)
