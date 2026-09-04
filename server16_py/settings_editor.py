from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

from PIL import Image, ImageTk

from .chants_runtime import MciAudioPlayer
from .file_tools import discover_stadium_names, resolve_stadium_preview_path, stadium_preview_fallback_path
from .video_preview import MoviePreviewPanel


@dataclass(frozen=True)
class SectionSpec:
    section: str
    title: str
    kind: str = "simple"
    value_label: str = "Value"
    directory: str | None = None
    recursive: bool = False


class SettingsAreaEditor(tk.Toplevel):
    def __init__(self, app, title: str, specs: list[SectionSpec], initial_section: str | None = None) -> None:
        owner = app._window() if hasattr(app, "_window") else app
        super().__init__(owner)
        self.app = app
        self.specs = specs
        self.configure(bg=app.bg)
        self.title(title)
        zoom = getattr(getattr(app, "settings", None), "ui_zoom", 1.0)
        self.geometry(f"{round(1120 * zoom)}x{round(700 * zoom)}")
        self.minsize(round(1000 * zoom), round(640 * zoom))
        self.transient(owner)
        self.deiconify()
        self.lift()
        try:
            self.focus_force()
        except Exception:
            pass
        self.notebook = ttk.Notebook(self, style="Server16.TNotebook")
        self.notebook.pack(fill="both", expand=True, padx=10, pady=10)
        self.frames: dict[str, SettingsSectionFrame] = {}
        for spec in specs:
            frame = SettingsSectionFrame(self.notebook, app, spec)
            self.notebook.add(frame, text=app.tr(spec.title) if hasattr(app, "tr") else spec.title)
            self.frames[spec.section.lower()] = frame
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)
        if initial_section:
            for index, spec in enumerate(specs):
                if spec.section.lower() == initial_section.lower():
                    self.notebook.select(index)
                    break
        self._refresh_active_frame()

    def _on_tab_changed(self, _event=None) -> None:
        for frame in self.frames.values():
            stop_preview = getattr(frame, "_stop_preview", None)
            if stop_preview is not None:
                stop_preview()
        self._refresh_active_frame()

    def _refresh_active_frame(self) -> None:
        current_tab = self.notebook.nametowidget(self.notebook.select())
        if isinstance(current_tab, SettingsSectionFrame):
            current_tab.reload_entries()


class SettingsSectionFrame(tk.Frame):
    STADIUM_DEFAULTS = {"police": "4", "pitch": "0", "net": "0"}
    NET_DEFAULTS = {"down": "1086199011", "high": "1087199011", "rig": "4", "shape": "0"}
    STADIUM_NAME_DEFAULTS = {"name": "", "active": "1"}
    CHANTS_DEFAULTS = {
        "folder": "",
        "default": "0.12",
        "winning": "0.15",
        "lose1": "0.10",
        "lose2": "0.05",
        "lose3": "0.15",
        "goal": "0.13",
        "silence_prob": "0.15",
        "silence_max": "8.0",
        "away_prob": "0.35",
        "entrance_volume": "0.16",
        "entrance_delay": "7.0",
    }
    PLAY_ICON = "▶"
    STOP_ICON = "■"

    def __init__(self, parent: tk.Misc, app, spec: SectionSpec) -> None:
        super().__init__(parent, bg=app.bg)
        self.app = app
        self.spec = spec
        self.selected_key: str | None = None
        self._refresh_job = None
        self._display_keys: list[str] = []
        self._preview_player: MciAudioPlayer | None = None
        self._preview_playing_path: Path | None = None
        self._preview_poll_job = None
        self._preview_buttons: dict[Path, ttk.Button] = {}
        self._preview_images: dict[str, ImageTk.PhotoImage] = {}
        self._preview_labels: dict[str, tk.Label] = {}
        self._setup_ui()
        self.bind("<Destroy>", self._on_destroy)

    def tr(self, translation_key: str, **kwargs) -> str:
        if hasattr(self.app, "tr"):
            return self.app.tr(translation_key, **kwargs)
        return translation_key.format(**kwargs) if kwargs else translation_key

    def _setup_ui(self) -> None:
        self.grid_columnconfigure(0, weight=2)
        self.grid_columnconfigure(1, weight=3)
        self.grid_rowconfigure(1, weight=1)

        header = tk.Frame(self, bg=self.app.bg)
        header.grid(row=0, column=0, columnspan=2, sticky="ew", padx=12, pady=(12, 8))
        header.grid_columnconfigure(0, weight=1)
        tk.Label(
            header,
            text=f"[{self.spec.section}]",
            bg=self.app.bg,
            fg=self.app.gold,
            font=("Bahnschrift", 15, "bold"),
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            header,
            text=self.tr("dialog.editor.active_file", path=self.app.settings_ini.path),
            bg=self.app.bg,
            fg=self.app.muted,
            font=("Bahnschrift", 9),
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))
        ttk.Button(header, text=self.tr("button.refresh"), command=self.reload_entries).grid(row=0, column=1, rowspan=2, sticky="e")

        left_card = tk.Frame(self, bg=self.app.card, highlightthickness=1, highlightbackground="#243654")
        left_card.grid(row=1, column=0, sticky="nsew", padx=(12, 6), pady=(0, 12))
        left_card.grid_rowconfigure(1, weight=1)
        left_card.grid_columnconfigure(0, weight=1)

        left_top = tk.Frame(left_card, bg=self.app.card)
        left_top.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 8))
        left_top.grid_columnconfigure(0, weight=1)
        self.search_var = tk.StringVar()
        search = tk.Entry(
            left_top,
            textvariable=self.search_var,
            bg=self.app.panel_alt,
            fg=self.app.fg,
            insertbackground=self.app.fg,
            relief="flat",
            font=("Consolas", 10),
        )
        search.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        search.bind("<KeyRelease>", lambda _event: self.reload_entries(preserve=False))
        ttk.Button(left_top, text=self.tr("button.new"), command=self.new_entry).grid(row=0, column=1)

        self.entries_list = tk.Listbox(
            left_card,
            exportselection=False,
            bg=self.app.panel,
            fg=self.app.fg,
            selectbackground="#19324d",
            selectforeground=self.app.fg,
            relief="flat",
            font=("Consolas", 10),
        )
        entries_scroll = ttk.Scrollbar(
            left_card,
            orient="vertical",
            command=self.entries_list.yview,
            style="Server16.Vertical.TScrollbar",
        )
        self.entries_list.configure(yscrollcommand=entries_scroll.set)
        self.entries_list.grid(row=1, column=0, sticky="nsew", padx=(12, 0), pady=(0, 8))
        entries_scroll.grid(row=1, column=1, sticky="ns", padx=(8, 12), pady=(0, 8))
        self.entries_list.bind("<<ListboxSelect>>", self._on_entry_selected)

        self.count_label = tk.Label(left_card, text=self.tr("dialog.editor.entries_count", count=0), bg=self.app.card, fg=self.app.muted, font=("Bahnschrift", 9))
        self.count_label.grid(row=2, column=0, sticky="w", padx=12, pady=(0, 10))

        right_card = tk.Frame(self, bg=self.app.card, highlightthickness=1, highlightbackground="#243654")
        right_card.grid(row=1, column=1, sticky="nsew", padx=(6, 12), pady=(0, 12))
        right_card.grid_rowconfigure(1, weight=1)
        right_card.grid_columnconfigure(0, weight=1)

        form = tk.Frame(right_card, bg=self.app.card)
        form.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 8))
        form.grid_columnconfigure(1, weight=1)

        tk.Label(form, text=self.tr("dialog.editor.key"), bg=self.app.card, fg=self.app.muted, font=("Bahnschrift", 10)).grid(row=0, column=0, sticky="w", pady=(0, 6))
        self.key_var = tk.StringVar()
        self.key_entry = tk.Entry(
            form,
            textvariable=self.key_var,
            bg=self.app.panel_alt,
            fg=self.app.fg,
            insertbackground=self.app.fg,
            relief="flat",
            font=("Consolas", 11),
        )
        self.key_entry.grid(row=0, column=1, sticky="ew", pady=(0, 6))

        # The editor body (and, for chants/stadium, the preview panel below it)
        # can be taller than the window -- e.g. the stadium preview images only
        # fully fit at a much larger window height than this dialog opens at.
        # Wrap that middle section in its own scroll region so it's reachable
        # by scrollbar/mousewheel instead of being cut off, while Key/actions/
        # status stay pinned in view.
        scroll_wrap = tk.Frame(right_card, bg=self.app.card)
        scroll_wrap.grid(row=1, column=0, sticky="nsew")
        scroll_wrap.grid_columnconfigure(0, weight=1)
        scroll_wrap.grid_rowconfigure(0, weight=1)

        body_canvas = tk.Canvas(scroll_wrap, bg=self.app.card, highlightthickness=0, bd=0)
        body_canvas.grid(row=0, column=0, sticky="nsew")
        body_scroll = ttk.Scrollbar(scroll_wrap, orient="vertical", command=body_canvas.yview, style="Server16.Vertical.TScrollbar")
        body_scroll.grid(row=0, column=1, sticky="ns")
        body_canvas.configure(yscrollcommand=body_scroll.set)

        scroll_content = tk.Frame(body_canvas, bg=self.app.card)
        scroll_content.grid_columnconfigure(0, weight=1)
        content_window = body_canvas.create_window((0, 0), window=scroll_content, anchor="nw")
        scroll_content.bind("<Configure>", lambda _e: body_canvas.configure(scrollregion=body_canvas.bbox("all")))
        body_canvas.bind("<Configure>", lambda e: body_canvas.itemconfigure(content_window, width=e.width))

        def _on_body_mousewheel(event):
            if event.delta == 0:
                return "break"
            body_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            return "break"

        body_canvas.bind("<MouseWheel>", _on_body_mousewheel)
        scroll_content.bind("<MouseWheel>", _on_body_mousewheel)

        self.body = tk.Frame(scroll_content, bg=self.app.card)
        self.body.grid(row=0, column=0, sticky="nsew", padx=12, pady=(0, 8))
        self.body.grid_columnconfigure(0, weight=1)

        self._build_editor_body()

        if self.spec.kind == "chants":
            self._build_chants_preview_panel(scroll_content)
        elif self.spec.kind == "stadium":
            self._build_stadium_preview_panel(scroll_content)
        elif self.spec.directory == "MoviesGBD":
            self._build_movie_preview_panel(scroll_content)
        elif self.spec.directory in ("ScoreBoardGBD", "TVLogoGBD"):
            self._build_asset_preview_panel(scroll_content)

        actions = tk.Frame(right_card, bg=self.app.card)
        actions.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 12))
        actions.grid_columnconfigure(0, weight=1)
        ttk.Button(actions, text=self.tr("button.save_settings"), command=self.save_entry).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.reveal_button = ttk.Button(actions, text=self.tr("button.reveal_in_explorer"), command=self._reveal_in_explorer)
        self.reveal_button.grid(row=0, column=1, sticky="ew", padx=6)
        if not self.spec.directory:
            self.reveal_button.configure(state="disabled")
        ttk.Button(actions, text=self.tr("button.delete_entry"), command=self.delete_entry).grid(row=0, column=2, sticky="ew", padx=6)
        ttk.Button(actions, text=self.tr("button.apply_runtime"), command=self._apply_runtime).grid(row=0, column=3, sticky="ew", padx=(6, 0))

        self.status_var = tk.StringVar(value=self.tr("dialog.editor.no_selection"))
        tk.Label(
            right_card,
            textvariable=self.status_var,
            bg=self.app.card,
            fg=self.app.muted,
            font=("Bahnschrift", 9),
            anchor="w",
            justify="left",
        ).grid(row=3, column=0, sticky="ew", padx=12, pady=(0, 12))

    def _build_editor_body(self) -> None:
        if self.spec.kind == "simple":
            self.value_var = tk.StringVar()
            self.value_combo = self._add_combo_row(self.body, 0, self.spec.value_label, self.value_var, self._available_choices())
        elif self.spec.kind == "stadium":
            self._build_stadium_editor()
        elif self.spec.kind == "net":
            self._build_net_editor()
        elif self.spec.kind == "scoreboardstdname":
            self._build_scoreboard_name_editor()
        elif self.spec.kind == "chants":
            self._build_chants_editor()
        elif self.spec.kind == "exclude":
            self.exclude_var = tk.StringVar(value="excluded from stadium server")
            self.exclude_entry = self._add_entry_row(self.body, 0, "Reason", self.exclude_var, readonly=True)

    def _build_stadium_editor(self) -> None:
        self.stadium_list = tk.Listbox(
            self.body,
            selectmode="extended",
            exportselection=False,
            height=14,
            bg=self.app.panel,
            fg=self.app.fg,
            selectbackground="#19324d",
            selectforeground=self.app.fg,
            relief="flat",
            font=("Consolas", 10),
        )
        stadium_scroll = ttk.Scrollbar(
            self.body,
            orient="vertical",
            command=self.stadium_list.yview,
            style="Server16.Vertical.TScrollbar",
        )
        self.stadium_list.configure(yscrollcommand=stadium_scroll.set)
        self.stadium_list.grid(row=0, column=0, sticky="nsew", pady=(0, 10))
        stadium_scroll.grid(row=0, column=1, sticky="ns", padx=(8, 0), pady=(0, 10))
        self.body.grid_columnconfigure(0, weight=1)
        self.body.grid_columnconfigure(1, weight=0)
        for entry in self._available_choices():
            self.stadium_list.insert("end", entry)
        # selection_set() (used by _load_stadium_value/new_entry) doesn't fire
        # this virtual event, so those two call _update_stadium_preview() directly;
        # this binding only covers the user clicking in the list themselves.
        self.stadium_list.bind("<<ListboxSelect>>", lambda _e: self._update_stadium_preview())
        self.police_var = tk.StringVar(value=self.STADIUM_DEFAULTS["police"])
        self.pitch_var = tk.StringVar(value=self.STADIUM_DEFAULTS["pitch"])
        self.net_var = tk.StringVar(value=self.STADIUM_DEFAULTS["net"])
        self.police_var.trace_add("write", lambda *_: self._update_police_preview())
        self.pitch_var.trace_add("write", lambda *_: self._update_pitch_preview())
        self.net_var.trace_add("write", lambda *_: self._update_net_preview())
        self._add_combo_row(self.body, 1, "Police", self.police_var, [str(i) for i in range(1, 11)])
        self._add_combo_row(self.body, 2, "Pitch", self.pitch_var, self._asset_indices(self.app.PitchMowsource))
        self._add_combo_row(self.body, 3, "Net", self.net_var, self._asset_indices(self.app.Nsource))

    def _build_stadium_preview_panel(self, scroll_content: tk.Misc) -> None:
        # Same slot _build_chants_preview_panel uses (row 1 of the scrollable
        # content area, directly below self.body) -- the two kinds are mutually
        # exclusive so there's no conflict.
        self._pitch_preview_dir = self._first_existing_dir(
            self.app.exedir / "FSW" / "Images" / "PitchMowPattern", self.app.exedir / "FSW" / "PitchMowPattern"
        )
        self._net_preview_dir = self._first_existing_dir(
            self.app.exedir / "FSW" / "Images" / "Nets", self.app.exedir / "FSW" / "Nets"
        )
        self._police_preview_dir = self._first_existing_dir(
            self.app.exedir / "FSW" / "Images" / "Police", self.app.exedir / "FSW" / "Police"
        )

        container = tk.Frame(scroll_content, bg=self.app.card)
        container.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 8))
        container.grid_columnconfigure(0, weight=1)
        container.grid_rowconfigure(1, weight=1)

        small_row = tk.Frame(container, bg=self.app.card)
        small_row.grid(row=0, column=0, sticky="nsew", pady=(0, 8))
        small_row.grid_columnconfigure(0, weight=1)
        small_row.grid_columnconfigure(1, weight=1)
        small_row.grid_columnconfigure(2, weight=1)
        self._build_stadium_preview_box(small_row, 0, self.tr("dialog.stadium.preview.pitch"), "pitch", image_size=(170, 140))
        self._build_stadium_preview_box(small_row, 1, self.tr("dialog.stadium.preview.net"), "net", image_size=(170, 140))
        self._build_stadium_preview_box(small_row, 2, self.tr("dialog.stadium.preview.police"), "police", image_size=(170, 140))

        stadium_wrap = tk.Frame(container, bg=self.app.card)
        stadium_wrap.grid(row=1, column=0, sticky="nsew")
        stadium_wrap.grid_columnconfigure(0, weight=1)
        self._build_stadium_preview_box(stadium_wrap, 0, self.tr("dialog.stadium.preview.stadium"), "stadium", image_size=(520, 300))

        self._update_stadium_preview()
        self._update_pitch_preview()
        self._update_net_preview()
        self._update_police_preview()

    def _build_stadium_preview_box(
        self,
        parent: tk.Misc,
        column: int,
        title: str,
        key: str,
        image_size: tuple[int, int] = (280, 220),
    ) -> None:
        # A tk.Label's -width/-height are interpreted as character/line counts
        # while it's showing text (the initial "No preview" placeholder), but
        # once an image is configured onto the same label those same numbers
        # stop reserving enough room and the image renders clipped -- that was
        # the "previews look tiny and cropped" bug. Sidestepping it entirely:
        # give the wrapping frame a fixed pixel size (image_size plus room for
        # the title + padding) and grid_propagate(False) it, then let the
        # preview label fill that fixed cell via sticky="nsew" instead of its
        # own width/height. The frame's size is then guaranteed to be big
        # enough for image_size, whether showing the fallback text or the
        # actual thumbnail (PIL's .thumbnail() only ever shrinks to fit, never
        # upscales, so the rendered image can never exceed image_size).
        box_width = image_size[0] + 16
        box_height = image_size[1] + 46
        frame = tk.Frame(
            parent,
            bg=self.app.card_soft,
            highlightthickness=1,
            highlightbackground="#243654",
            width=box_width,
            height=box_height,
        )
        frame.grid(row=0, column=column, padx=(0 if column == 0 else 6, 0), sticky="nsew")
        frame.grid_propagate(False)
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(1, weight=1)
        tk.Label(frame, text=title, bg=self.app.card_soft, fg=self.app.muted, font=("Bahnschrift", 9)).grid(row=0, column=0, sticky="w", padx=8, pady=(8, 4))
        preview = tk.Label(
            frame,
            text=self.tr("placeholder.no_preview"),
            bg=self.app.panel,
            fg=self.app.muted,
            anchor="center",
            justify="center",
            relief="flat",
        )
        preview.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        preview.image_size = image_size
        self._preview_labels[key] = preview

    @staticmethod
    def _first_existing_dir(*paths: Path) -> Path:
        for path in paths:
            if path.exists():
                return path
        return paths[0]

    def _set_preview_image(self, key: str, image_path: Path | None, fallback_text: str) -> None:
        label = self._preview_labels.get(key)
        if label is None:
            return
        self._preview_images.pop(key, None)
        if image_path is None or not image_path.exists():
            label.configure(image="", text=fallback_text, compound="center")
            return
        try:
            image = Image.open(image_path).convert("RGBA")
            image.thumbnail(getattr(label, "image_size", (280, 220)))
            photo = ImageTk.PhotoImage(image)
        except Exception:
            label.configure(image="", text=fallback_text, compound="center")
            return
        self._preview_images[key] = photo
        label.configure(image=photo, text="", compound="center")

    def _update_stadium_preview(self) -> None:
        if "stadium" not in self._preview_labels:
            return
        selection = self.stadium_list.curselection()
        stadium_name = self.stadium_list.get(selection[0]) if selection else ""
        image_path = resolve_stadium_preview_path(self.app.exedir / self.spec.directory, stadium_name) if stadium_name else None
        if image_path is None and stadium_name:
            image_path = stadium_preview_fallback_path()
        fallback = stadium_name if stadium_name else self.tr("placeholder.no_stadium_preview")
        self._set_preview_image("stadium", image_path, fallback)

    def _update_pitch_preview(self) -> None:
        if "pitch" not in self._preview_labels:
            return
        value = self.pitch_var.get().strip()
        image_path = self._pitch_preview_dir / f"{value}.png"
        self._set_preview_image("pitch", image_path, self.tr("dialog.stadium.pitch_value", value=value or "-"))

    def _update_net_preview(self) -> None:
        if "net" not in self._preview_labels:
            return
        value = self.net_var.get().strip()
        image_path = self._net_preview_dir / f"{value}.png"
        self._set_preview_image("net", image_path, self.tr("dialog.stadium.net_value", value=value or "-"))

    def _update_police_preview(self) -> None:
        if "police" not in self._preview_labels:
            return
        value = self.police_var.get().strip()
        image_path = self._police_preview_dir / f"{value}.png"
        self._set_preview_image("police", image_path, value or self.tr("dialog.stadium.police_pattern"))

    def _build_net_editor(self) -> None:
        self.down_var = tk.StringVar(value=self.NET_DEFAULTS["down"])
        self.high_var = tk.StringVar(value=self.NET_DEFAULTS["high"])
        self.rig_var = tk.StringVar(value=self.NET_DEFAULTS["rig"])
        self.shape_var = tk.StringVar(value=self.NET_DEFAULTS["shape"])
        self._add_entry_row(self.body, 0, "Down Deep", self.down_var)
        self._add_entry_row(self.body, 1, "High Deep", self.high_var)
        self._add_combo_row(self.body, 2, "Rig", self.rig_var, [str(i) for i in range(0, 11)])
        self._add_combo_row(self.body, 3, "Shape", self.shape_var, ["0", "1", "2", "3", "4"])

    def _build_scoreboard_name_editor(self) -> None:
        self.display_name_var = tk.StringVar()
        self._add_entry_row(self.body, 0, "Displayed Name", self.display_name_var)

    def _build_chants_editor(self) -> None:
        self.chants_folder_var = tk.StringVar(value=self.CHANTS_DEFAULTS["folder"])
        self.default_var = tk.StringVar(value=self.CHANTS_DEFAULTS["default"])
        self.winning_var = tk.StringVar(value=self.CHANTS_DEFAULTS["winning"])
        self.lose1_var = tk.StringVar(value=self.CHANTS_DEFAULTS["lose1"])
        self.lose2_var = tk.StringVar(value=self.CHANTS_DEFAULTS["lose2"])
        self.lose3_var = tk.StringVar(value=self.CHANTS_DEFAULTS["lose3"])
        self.goal_var = tk.StringVar(value=self.CHANTS_DEFAULTS["goal"])
        self.silence_prob_var = tk.StringVar(value=self.CHANTS_DEFAULTS["silence_prob"])
        self.silence_max_var = tk.StringVar(value=self.CHANTS_DEFAULTS["silence_max"])
        self.away_prob_var = tk.StringVar(value=self.CHANTS_DEFAULTS["away_prob"])
        self.entrance_volume_var = tk.StringVar(value=self.CHANTS_DEFAULTS["entrance_volume"])
        self.entrance_delay_var = tk.StringVar(value=self.CHANTS_DEFAULTS["entrance_delay"])

        self.body.grid_columnconfigure(0, weight=0)
        self.body.grid_columnconfigure(1, weight=0)
        self.body.grid_columnconfigure(2, weight=1)

        folder_choices = self._available_choices()
        tk.Label(self.body, text=self.tr("dialog.editor.field.chants_folder"), bg=self.app.card, fg=self.app.muted, font=("Bahnschrift", 10)).grid(row=0, column=0, sticky="w", pady=4, padx=(0, 8))
        ttk.Combobox(self.body, textvariable=self.chants_folder_var, values=folder_choices or [""], font=("Consolas", 10), style="Server16.TCombobox").grid(row=0, column=1, columnspan=2, sticky="ew", pady=4)

        self._add_chants_field_row(self.body, 1, self.tr("dialog.editor.field.vol_draw"), self.default_var)
        self._add_chants_field_row(self.body, 2, self.tr("dialog.editor.field.vol_winning"), self.winning_var)
        self._add_chants_field_row(self.body, 3, self.tr("dialog.editor.field.vol_losing1"), self.lose1_var)
        self._add_chants_field_row(self.body, 4, self.tr("dialog.editor.field.vol_losing2"), self.lose2_var)
        self._add_chants_field_row(self.body, 5, self.tr("dialog.editor.field.vol_complaint"), self.lose3_var)
        self._add_chants_field_row(self.body, 6, self.tr("dialog.editor.field.vol_goal"), self.goal_var)
        self._add_chants_field_row(self.body, 7, self.tr("dialog.editor.field.prob_silence"), self.silence_prob_var)
        self._add_chants_field_row(self.body, 8, self.tr("dialog.editor.field.max_silence"), self.silence_max_var, to=30.0, resolution=0.5)
        self._add_chants_field_row(self.body, 9, self.tr("dialog.editor.field.prob_away_crowd"), self.away_prob_var)
        self._add_chants_field_row(self.body, 10, self.tr("dialog.editor.field.vol_entrance"), self.entrance_volume_var)
        self._add_chants_field_row(self.body, 11, self.tr("dialog.editor.field.entrance_delay"), self.entrance_delay_var, to=45.0, resolution=0.5)

    def _add_chants_field_row(self, parent: tk.Misc, row: int, label: str, variable: tk.StringVar, from_: float = 0.0, to: float = 1.0, resolution: float = 0.01) -> tk.Entry:
        tk.Label(parent, text=label, bg=self.app.card, fg=self.app.muted, font=("Bahnschrift", 10)).grid(row=row, column=0, sticky="w", pady=2, padx=(0, 8))

        entry = tk.Entry(
            parent,
            textvariable=variable,
            bg=self.app.panel_alt,
            fg=self.app.fg,
            insertbackground=self.app.fg,
            relief="flat",
            bd=0,
            highlightthickness=0,
            font=("Consolas", 11),
            width=7,
        )
        entry.grid(row=row, column=1, sticky="ew", pady=2, padx=(0, 8))

        _guard = [False]

        def _parse(s: str) -> float | None:
            try:
                return float(s)
            except ValueError:
                return None

        initial = _parse(variable.get())
        initial = max(from_, min(to, initial)) if initial is not None else from_
        scale_var = tk.DoubleVar(value=initial)

        def on_scale(val: str) -> None:
            if _guard[0]:
                return
            _guard[0] = True
            try:
                fmt = f"{float(val):.2f}" if resolution < 1.0 else f"{float(val):.1f}"
                if variable.get() != fmt:
                    variable.set(fmt)
            finally:
                _guard[0] = False

        def on_entry(*_) -> None:
            if _guard[0]:
                return
            _guard[0] = True
            try:
                v = _parse(variable.get())
                if v is not None:
                    scale_var.set(max(from_, min(to, v)))
            finally:
                _guard[0] = False

        scale = tk.Scale(
            parent,
            from_=from_,
            to=to,
            resolution=resolution,
            orient="horizontal",
            variable=scale_var,
            command=on_scale,
            bg=self.app.card,
            fg=self.app.fg,
            troughcolor=self.app.panel_alt,
            activebackground=self.app.accent,
            highlightthickness=0,
            bd=0,
            showvalue=False,
            sliderlength=16,
        )
        scale.grid(row=row, column=2, sticky="ew", pady=2)
        variable.trace_add("write", on_entry)
        return entry

    def _build_chants_preview_panel(self, scroll_content: tk.Misc) -> None:
        # Placed at row 1 of the scrollable content area, directly below
        # self.body (row 0) -- that whole area scrolls together now, so this
        # panel is reachable even when the form above it already fills the
        # window (see the scroll_wrap/body_canvas setup in _setup_ui).
        container = tk.Frame(scroll_content, bg=self.app.card)
        container.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 8))
        container.grid_columnconfigure(0, weight=1)
        container.grid_rowconfigure(1, weight=1)

        tk.Label(
            container,
            text=self.tr("dialog.editor.chants_preview.title"),
            bg=self.app.card,
            fg=self.app.muted,
            font=("Bahnschrift", 9),
        ).grid(row=0, column=0, sticky="w", pady=(0, 4))

        list_wrap = tk.Frame(container, bg=self.app.panel, highlightthickness=1, highlightbackground="#243654")
        list_wrap.grid(row=1, column=0, sticky="nsew")
        list_wrap.grid_columnconfigure(0, weight=1)
        list_wrap.grid_rowconfigure(0, weight=1)

        canvas = tk.Canvas(list_wrap, bg=self.app.panel, highlightthickness=0, height=110)
        canvas.grid(row=0, column=0, sticky="nsew")
        preview_scroll = ttk.Scrollbar(list_wrap, orient="vertical", command=canvas.yview, style="Server16.Vertical.TScrollbar")
        preview_scroll.grid(row=0, column=1, sticky="ns")
        canvas.configure(yscrollcommand=preview_scroll.set)

        self._preview_rows_frame = tk.Frame(canvas, bg=self.app.panel)
        preview_window = canvas.create_window((0, 0), window=self._preview_rows_frame, anchor="nw")
        self._preview_canvas = canvas

        self._preview_rows_frame.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(preview_window, width=e.width))

        # Rebuild the list whenever the folder changes, whether the user typed
        # it directly or picked it from the combobox -- both go through the
        # same StringVar.
        self.chants_folder_var.trace_add("write", lambda *_: self._refresh_chants_preview())
        self._refresh_chants_preview()

    def _refresh_chants_preview(self) -> None:
        if not hasattr(self, "_preview_rows_frame"):
            return
        self._stop_preview()
        for child in self._preview_rows_frame.winfo_children():
            child.destroy()
        self._preview_buttons = {}

        folder = self.chants_folder_var.get().strip()
        base: Path | None = None
        files: list[Path] = []
        if folder:
            base = self.app.exedir / "FSW" / "Chants" / folder
            if base.exists():
                # rglob so tracks organized into subfolders (e.g. a "Goal" or
                # "Extra" subfolder some packs use) show up too, not just the
                # ones sitting directly in the mapped folder.
                files = sorted(p for p in base.rglob("*.mp3") if not p.name.endswith(".original.mp3"))

        if not files or base is None:
            tk.Label(
                self._preview_rows_frame,
                text=self.tr("dialog.editor.chants_preview.empty"),
                bg=self.app.panel,
                fg=self.app.muted,
                font=("Bahnschrift", 9),
            ).pack(anchor="w", padx=8, pady=6)
            return

        for path in files:
            self._add_chants_preview_row(path, path.relative_to(base).as_posix())

    def _add_chants_preview_row(self, path: Path, display_name: str) -> None:
        row = tk.Frame(self._preview_rows_frame, bg=self.app.panel)
        row.pack(fill="x", padx=6, pady=2)
        tk.Label(
            row,
            text=display_name,
            bg=self.app.panel,
            fg=self.app.fg,
            font=("Consolas", 9),
            anchor="w",
        ).pack(side="left", fill="x", expand=True)
        button = ttk.Button(row, text=self.PLAY_ICON, width=3, command=lambda p=path: self._toggle_chants_preview(p))
        button.pack(side="right")
        self._preview_buttons[path] = button

    def _toggle_chants_preview(self, path: Path) -> None:
        if self._preview_playing_path == path:
            self._stop_preview()
            return
        self._stop_preview()
        try:
            player = MciAudioPlayer()
            player.open(path)
            player.play()
        except Exception as exc:
            self.app.log(f"Chants preview playback failed for {path}", exc)
            self.status_var.set(self.tr("dialog.editor.chants_preview.play_failed", file=path.name))
            return
        self._preview_player = player
        self._preview_playing_path = path
        button = self._preview_buttons.get(path)
        if button is not None:
            button.configure(text=self.STOP_ICON)
        self._schedule_preview_poll()

    def _schedule_preview_poll(self) -> None:
        self._preview_poll_job = self.after(400, self._poll_preview_state)

    def _poll_preview_state(self) -> None:
        self._preview_poll_job = None
        if self._preview_player is None:
            return
        try:
            still_playing = self._preview_player.is_playing()
        except Exception:
            still_playing = False
        if still_playing:
            self._schedule_preview_poll()
        else:
            self._stop_preview()

    def _build_movie_preview_panel(self, scroll_content: tk.Misc) -> None:
        # Same slot _build_chants_preview_panel/_build_stadium_preview_panel use
        # (row 1 of the scrollable content area, directly below self.body) --
        # movies/TeamMovies/DerbyMatch are the only "simple"-kind specs pointed
        # at MoviesGBD, so this is mutually exclusive with those two panels.
        container = tk.Frame(scroll_content, bg=self.app.card)
        container.grid(row=1, column=0, sticky="w", padx=12, pady=(0, 8))

        tk.Label(
            container,
            text=self.tr("dialog.movie_preview.title"),
            bg=self.app.card,
            fg=self.app.muted,
            font=("Bahnschrift", 9),
        ).pack(anchor="w", pady=(0, 4))

        # Bigger than MovieDialog's inline preview (dialogs.py, 340x191) --
        # the right card is roughly 600px wide at this editor's default
        # window size (1120x700, see SettingsAreaEditor.__init__), and
        # scroll_content's width always tracks the canvas exactly (no
        # horizontal scrollbar), so this needs to stay comfortably under
        # that or it gets clipped. The fullscreen button covers the rest.
        self._movie_preview_panel = MoviePreviewPanel(container, self.app, width=560, height=315)
        self._movie_preview_panel.pack(anchor="w")

        # Rebuild whenever the folder value changes, whether typed directly or
        # picked from the combobox -- both go through the same StringVar (see
        # _build_editor_body's "simple" branch).
        self.value_var.trace_add("write", lambda *_: self._refresh_movie_preview())
        self._refresh_movie_preview()

    def _refresh_movie_preview(self) -> None:
        panel = getattr(self, "_movie_preview_panel", None)
        if panel is None:
            return
        value = self.value_var.get().strip()
        path = None
        if value and self.spec.directory:
            candidate = self.app.exedir / self.spec.directory / value / "bootflowoutro.vp8"
            if candidate.exists():
                path = candidate
        panel.set_movie(path)

    def _build_asset_preview_panel(self, scroll_content: tk.Misc) -> None:
        # Same slot _build_chants_preview_panel/_build_stadium_preview_panel/
        # _build_movie_preview_panel use (row 1 of the scrollable content area,
        # directly below self.body) -- Scoreboard/TVLogo/HomeTeamScoreBoard/
        # HomeTeamTvLogo are the only "simple"-kind specs pointed at
        # ScoreBoardGBD/TVLogoGBD, so this is mutually exclusive with the
        # other panels. Looks for the same thumbnail ScoreboardDialog
        # (dialogs.py) shows: <folder>/render/thumbnail/<key>.<ext>, falling
        # back to the first image in that thumbnail folder.
        container = tk.Frame(scroll_content, bg=self.app.card)
        container.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 8))
        container.grid_columnconfigure(0, weight=1)

        self._asset_preview_key = "tvlogo" if self.spec.directory == "TVLogoGBD" else "scoreboard"
        title_key = "dialog.editor.preview.tvlogo" if self._asset_preview_key == "tvlogo" else "dialog.editor.preview.scoreboard"
        self._build_stadium_preview_box(container, 0, self.tr(title_key), self._asset_preview_key, image_size=(340, 180))

        # Rebuild whenever the value changes, whether typed directly or picked
        # from the combobox -- both go through the same StringVar (see
        # _build_editor_body's "simple" branch).
        self.value_var.trace_add("write", lambda *_: self._refresh_asset_preview())
        self._refresh_asset_preview()

    def _refresh_asset_preview(self) -> None:
        key = getattr(self, "_asset_preview_key", None)
        if key is None or key not in self._preview_labels:
            return
        value = self.value_var.get().strip()
        image_path = None
        if value and self.spec.directory:
            thumbnail_dir = self.app.exedir / self.spec.directory / value / "render" / "thumbnail"
            if thumbnail_dir.exists():
                for ext in (".png", ".jpg", ".jpeg"):
                    candidate = thumbnail_dir / f"{key}{ext}"
                    if candidate.exists():
                        image_path = candidate
                        break
                if image_path is None:
                    for candidate in sorted(thumbnail_dir.iterdir()):
                        if candidate.is_file() and candidate.suffix.lower() in {".png", ".jpg", ".jpeg"}:
                            image_path = candidate
                            break
        fallback = value if value else self.tr("placeholder.no_preview")
        self._set_preview_image(key, image_path, fallback)

    def _stop_preview(self) -> None:
        movie_panel = getattr(self, "_movie_preview_panel", None)
        if movie_panel is not None:
            movie_panel.stop()
        if self._preview_poll_job is not None:
            try:
                self.after_cancel(self._preview_poll_job)
            except Exception:
                pass
            self._preview_poll_job = None
        if self._preview_playing_path is not None:
            button = self._preview_buttons.get(self._preview_playing_path)
            if button is not None:
                try:
                    button.configure(text=self.PLAY_ICON)
                except Exception:
                    pass
        if self._preview_player is not None:
            try:
                self._preview_player.close()
            except Exception:
                pass
            self._preview_player = None
        self._preview_playing_path = None

    def _add_entry_row(self, parent: tk.Misc, row: int, label: str, variable: tk.StringVar, readonly: bool = False):
        tk.Label(parent, text=label, bg=self.app.card, fg=self.app.muted, font=("Bahnschrift", 10)).grid(row=row, column=0, sticky="w", pady=4, padx=(0, 10))
        entry = tk.Entry(
            parent,
            textvariable=variable,
            bg=self.app.panel_alt,
            fg=self.app.fg,
            insertbackground=self.app.fg,
            relief="flat",
            bd=0,
            highlightthickness=0,
            font=("Consolas", 11),
        )
        if readonly:
            entry.configure(
                readonlybackground=self.app.panel_alt,
                disabledbackground=self.app.card_soft,
                disabledforeground=self.app.muted,
                state="readonly",
            )
        entry.grid(row=row, column=1, sticky="ew", pady=4)
        parent.grid_columnconfigure(1, weight=1)
        return entry

    def _add_combo_row(self, parent: tk.Misc, row: int, label: str, variable: tk.StringVar, values: list[str]):
        tk.Label(parent, text=label, bg=self.app.card, fg=self.app.muted, font=("Bahnschrift", 10)).grid(row=row, column=0, sticky="w", pady=4, padx=(0, 10))
        combo = ttk.Combobox(parent, textvariable=variable, values=values, font=("Consolas", 10), style="Server16.TCombobox")
        combo.grid(row=row, column=1, sticky="ew", pady=4)
        parent.grid_columnconfigure(1, weight=1)
        return combo

    def _on_destroy(self, _event=None) -> None:
        if self._refresh_job is not None:
            try:
                self.after_cancel(self._refresh_job)
            except Exception:
                pass
            self._refresh_job = None
        self._stop_preview()

    def _available_choices(self) -> list[str]:
        directory = self.spec.directory
        if not directory:
            return []
        base = self.app.exedir / directory
        if self.spec.recursive:
            entries = []
            if base.exists():
                for path in sorted(p for p in base.rglob("*") if p.is_dir()):
                    try:
                        entries.append(path.relative_to(base).as_posix())
                    except ValueError:
                        continue
            return entries
        if not base.exists():
            return []
        if directory.replace("/", "\\").casefold() == "stadiumgbd":
            return discover_stadium_names(base)
        return sorted(path.name for path in base.iterdir() if path.is_dir())

    def _asset_indices(self, folder: Path) -> list[str]:
        """Return the variant index token (e.g. "5" from "netcolor_5_textures.rx3")
        for files in folder, matching the "{prefix}_{index}_..." naming convention
        that extra_setup()/legacy ExtraSetup() actually match against. Showing raw
        file stems here would save a value the backend can never match (see
        extra_setup's check = f"{{asset_prefix}}_{{source_index}}_")."""
        if not folder.exists():
            return ["0"]
        indices: set[str] = set()
        for item in folder.iterdir():
            if not item.is_file():
                continue
            parts = item.stem.split("_")
            if len(parts) >= 2:
                indices.add(parts[1])
        if not indices:
            return ["0"]
        return sorted(indices, key=lambda v: (0, int(v)) if v.isdigit() else (1, v))

    def _on_entry_selected(self, _event=None) -> None:
        selection = self.entries_list.curselection()
        if not selection:
            return
        key = self._display_keys[selection[0]]
        self.load_entry(key)

    def reload_entries(self, preserve: bool = True) -> None:
        current_selection = self.selected_key if preserve else None
        # Use reload_if_needed instead of force-reload to avoid re-reading the
        # file right after a save (which already updated _last_mtime_ns).
        self.app.settings_ini._reload_if_needed()
        items = self.app.settings_ini.items(self.spec.section)
        query = self.search_var.get().strip().lower()
        if query:
            items = [(key, value) for key, value in items if query in key.lower() or query in value.lower()]
        self.entries_list.delete(0, "end")
        self._display_keys = []
        for key, value in items:
            preview = value if len(value) <= 58 else value[:55] + "..."
            self.entries_list.insert("end", f"{key}  ->  {preview}")
            self._display_keys.append(key)
        self.count_label.configure(text=self.tr("dialog.editor.entries_count", count=len(items)))
        if current_selection:
            for index, (key, _value) in enumerate(items):
                if key == current_selection:
                    self.entries_list.selection_clear(0, "end")
                    self.entries_list.selection_set(index)
                    self.entries_list.activate(index)
                    break
        self._schedule_refresh()

    def _schedule_refresh(self) -> None:
        # Do not schedule auto-refresh while the user is actively editing an entry
        # — it would overwrite what they typed in the form fields before they save.
        if self.selected_key is not None:
            return
        if self._refresh_job is not None:
            try:
                self.after_cancel(self._refresh_job)
            except Exception:
                pass
        self._refresh_job = self.after(3000, self.reload_entries)

    def new_entry(self) -> None:
        self.selected_key = None
        self.key_var.set("")
        if self.spec.kind == "simple":
            choices = self._available_choices()
            self.value_var.set(choices[0] if choices else "")
        elif self.spec.kind == "stadium":
            self.stadium_list.selection_clear(0, "end")
            self.police_var.set(self.STADIUM_DEFAULTS["police"])
            self.pitch_var.set(self.STADIUM_DEFAULTS["pitch"])
            self.net_var.set(self.STADIUM_DEFAULTS["net"])
            self._update_stadium_preview()
        elif self.spec.kind == "net":
            self.down_var.set(self.NET_DEFAULTS["down"])
            self.high_var.set(self.NET_DEFAULTS["high"])
            self.rig_var.set(self.NET_DEFAULTS["rig"])
            self.shape_var.set(self.NET_DEFAULTS["shape"])
        elif self.spec.kind == "scoreboardstdname":
            self.display_name_var.set("")
        elif self.spec.kind == "chants":
            choices = self._available_choices()
            self.chants_folder_var.set(choices[0] if choices else self.CHANTS_DEFAULTS["folder"])
            self.default_var.set(self.CHANTS_DEFAULTS["default"])
            self.winning_var.set(self.CHANTS_DEFAULTS["winning"])
            self.lose1_var.set(self.CHANTS_DEFAULTS["lose1"])
            self.lose2_var.set(self.CHANTS_DEFAULTS["lose2"])
            self.lose3_var.set(self.CHANTS_DEFAULTS["lose3"])
            self.goal_var.set(self.CHANTS_DEFAULTS["goal"])
            self.silence_prob_var.set(self.CHANTS_DEFAULTS["silence_prob"])
            self.silence_max_var.set(self.CHANTS_DEFAULTS["silence_max"])
            self.away_prob_var.set(self.CHANTS_DEFAULTS["away_prob"])
            self.entrance_volume_var.set(self.CHANTS_DEFAULTS["entrance_volume"])
            self.entrance_delay_var.set(self.CHANTS_DEFAULTS["entrance_delay"])
        elif self.spec.kind == "exclude":
            self.exclude_var.set("excluded from stadium server")
        self.status_var.set(self.tr("dialog.editor.new_ready"))

    def load_entry(self, key: str) -> None:
        self.app.settings_ini.reload()
        value = self.app.settings_ini.read(key, self.spec.section)
        self.selected_key = key
        self.key_var.set(key)
        if self.spec.kind == "simple":
            self.value_var.set(value)
        elif self.spec.kind == "stadium":
            self._load_stadium_value(value)
        elif self.spec.kind == "net":
            self._load_net_value(value)
        elif self.spec.kind == "scoreboardstdname":
            self._load_scoreboard_name_value(key, value)
        elif self.spec.kind == "chants":
            self._load_chants_value(value)
        elif self.spec.kind == "exclude":
            self.exclude_var.set(value or "excluded from stadium server")
        self.status_var.set(self.tr("dialog.editor.editing", section=self.spec.section, key=key))

    def _load_stadium_value(self, value: str) -> None:
        self.stadium_list.selection_clear(0, "end")
        if not value or value == "None":
            self.police_var.set(self.STADIUM_DEFAULTS["police"])
            self.pitch_var.set(self.STADIUM_DEFAULTS["pitch"])
            self.net_var.set(self.STADIUM_DEFAULTS["net"])
            self._update_stadium_preview()
            return
        parts = [part.strip() for part in value.split(",") if part.strip()]
        if len(parts) >= 4:
            stadiums, police, pitch, net = parts[:-3], parts[-3], parts[-2], parts[-1]
        else:
            stadiums, police, pitch, net = parts[:1], self.STADIUM_DEFAULTS["police"], self.STADIUM_DEFAULTS["pitch"], self.STADIUM_DEFAULTS["net"]
        choices = self._available_choices()
        for stadium in stadiums:
            if stadium in choices:
                index = choices.index(stadium)
                self.stadium_list.selection_set(index)
        self.police_var.set(police)
        self.pitch_var.set(pitch)
        self.net_var.set(net)
        self._update_stadium_preview()

    def _load_net_value(self, value: str) -> None:
        parts = [part.strip() for part in value.split(",")]
        while len(parts) < 4:
            parts.append("")
        self.down_var.set(parts[0] or self.NET_DEFAULTS["down"])
        self.high_var.set(parts[1] or self.NET_DEFAULTS["high"])
        self.rig_var.set(parts[2] or self.NET_DEFAULTS["rig"])
        self.shape_var.set(parts[3] or self.NET_DEFAULTS["shape"])

    def _load_scoreboard_name_value(self, key: str, value: str) -> None:
        # Format: DisplayName  (comma-separated values are supported, we take first part)
        display_name = value.split(",")[0].strip() if value else key
        self.display_name_var.set(display_name)

    def _load_chants_value(self, value: str) -> None:
        parts = [part.strip() for part in value.split(",")]
        # Backward compatibility:
        # old format (7): folder,default,winning,lose1,lose2,lose3,goal
        # current format (12): folder,default,winning,lose1,lose2,lose3,goal,
        # silence_prob,silence_max,away_prob,entrance_volume,entrance_delay
        if len(parts) >= 7:
            folder = parts[0]
            default = parts[1] if len(parts) > 1 else ""
            winning = parts[2] if len(parts) > 2 else ""
            lose1 = parts[3] if len(parts) > 3 else ""
            lose2 = parts[4] if len(parts) > 4 else ""
            lose3 = parts[5] if len(parts) > 5 else ""
            goal = parts[6] if len(parts) > 6 else ""
            silence_prob = parts[7] if len(parts) > 7 else ""
            silence_max = parts[8] if len(parts) > 8 else ""
            away_prob = parts[9] if len(parts) > 9 else ""
            entrance_volume = parts[10] if len(parts) > 10 else ""
            entrance_delay = parts[11] if len(parts) > 11 else ""
        else:
            # Very old/invalid payload: keep best effort with defaults.
            while len(parts) < 12:
                parts.append("")
            (
                folder, default, winning, lose1, lose2, lose3, goal,
                silence_prob, silence_max, away_prob, entrance_volume,
                entrance_delay,
            ) = parts[:12]
        self.chants_folder_var.set(folder or self.CHANTS_DEFAULTS["folder"])
        self.default_var.set(default or self.CHANTS_DEFAULTS["default"])
        self.winning_var.set(winning or self.CHANTS_DEFAULTS["winning"])
        self.lose1_var.set(lose1 or self.CHANTS_DEFAULTS["lose1"])
        self.lose2_var.set(lose2 or self.CHANTS_DEFAULTS["lose2"])
        self.lose3_var.set(lose3 or self.CHANTS_DEFAULTS["lose3"])
        self.goal_var.set(goal or self.CHANTS_DEFAULTS["goal"])
        self.silence_prob_var.set(silence_prob or self.CHANTS_DEFAULTS["silence_prob"])
        self.silence_max_var.set(silence_max or self.CHANTS_DEFAULTS["silence_max"])
        self.away_prob_var.set(away_prob or self.CHANTS_DEFAULTS["away_prob"])
        self.entrance_volume_var.set(entrance_volume or self.CHANTS_DEFAULTS["entrance_volume"])
        self.entrance_delay_var.set(entrance_delay or self.CHANTS_DEFAULTS["entrance_delay"])

    def _compose_value(self) -> str:
        if self.spec.kind == "simple":
            return self.value_var.get().strip()
        if self.spec.kind == "stadium":
            selected = [self.stadium_list.get(index) for index in self.stadium_list.curselection()]
            if not selected:
                return "None"
            return ",".join(selected + [self.police_var.get().strip(), self.pitch_var.get().strip(), self.net_var.get().strip()])
        if self.spec.kind == "net":
            return ",".join(
                [
                    self.down_var.get().strip(),
                    self.high_var.get().strip(),
                    self.rig_var.get().strip(),
                    self.shape_var.get().strip(),
                ]
            )
        if self.spec.kind == "scoreboardstdname":
            return self.display_name_var.get().strip() or self.key_var.get().strip()
        if self.spec.kind == "chants":
            return ",".join(
                [
                    self.chants_folder_var.get().strip(),
                    self.default_var.get().strip(),
                    self.winning_var.get().strip(),
                    self.lose1_var.get().strip(),
                    self.lose2_var.get().strip(),
                    self.lose3_var.get().strip(),
                    self.goal_var.get().strip(),
                    self.silence_prob_var.get().strip(),
                    self.silence_max_var.get().strip(),
                    self.away_prob_var.get().strip(),
                    self.entrance_volume_var.get().strip(),
                    self.entrance_delay_var.get().strip(),
                ]
            )
        if self.spec.kind == "exclude":
            return self.exclude_var.get().strip() or "excluded from stadium server"
        return ""

    def save_entry(self) -> None:
        key = self.key_var.get().strip()
        if not key:
            messagebox.showwarning(self.tr("message.settings"), self.tr("message.settings.enter_key"))
            return
        if self.spec.section.lower() == "modules":
            messagebox.showwarning(self.tr("message.settings"), self.tr("message.settings.modules_locked"))
            return
        value = self._compose_value()
        if not value:
            messagebox.showwarning(self.tr("message.settings"), self.tr("message.settings.enter_valid_value"))
            return
        original_key = self.selected_key
        if original_key and original_key != key:
            self.app.settings_ini.delete_key(original_key, self.spec.section)
        self.app.settings_ini.write(key, value, self.spec.section)
        self.app.settings_ini.save()
        self.selected_key = key
        self.status_var.set(self.tr("dialog.editor.saved", section=self.spec.section, key=key))
        self.reload_entries()
        self._apply_runtime()

    def delete_entry(self) -> None:
        key = self.key_var.get().strip() or self.selected_key
        if not key:
            return
        if not messagebox.askyesno(self.tr("message.settings"), self.tr("message.settings.remove_entry", section=self.spec.section, key=key)):
            return
        self.app.settings_ini.delete_key(key, self.spec.section)
        self.app.settings_ini.save()
        self.status_var.set(self.tr("dialog.editor.removed", section=self.spec.section, key=key))
        self.new_entry()
        self.reload_entries(preserve=False)
        self._apply_runtime()

    def _apply_runtime(self) -> None:
        try:
            self.app.refresh_modules()
            self.app.apply_all_runtime()
            self.status_var.set(self.status_var.get() + self.tr("dialog.editor.runtime_updated"))
        except Exception as exc:
            self.app.log("Failed to apply runtime after settings edit", exc)

    def _asset_reveal_target(self) -> Path | None:
        """Resolve the on-disk name (folder or archive stem) currently
        selected/entered for this section, so the Reveal button knows what to
        point Explorer at. Returns None when this section has no directory
        (e.g. 'exclude', or 'stadiumnetid' which is keyed by numeric ID, not a
        folder name) or nothing is currently selected/typed."""
        directory = self.spec.directory
        if not directory:
            return None
        base = self.app.exedir / directory
        if self.spec.kind == "chants":
            folder = self.chants_folder_var.get().strip()
            return base / folder if folder else None
        if self.spec.kind == "simple":
            value = self.value_var.get().strip()
            return base / value if value else None
        if self.spec.kind == "stadium":
            selection = self.stadium_list.curselection()
            return base / self.stadium_list.get(selection[0]) if selection else None
        if self.spec.kind in ("net", "scoreboardstdname"):
            key = self.key_var.get().strip()
            return base / key if key else None
        return None

    @staticmethod
    def _resolve_existing_asset_path(target: Path) -> Path | None:
        if target.is_dir():
            return target
        for suffix in (".zip", ".rar"):
            candidate = target.with_suffix(suffix)
            if candidate.exists():
                return candidate
        return target if target.exists() else None

    def _reveal_in_explorer(self) -> None:
        target = self._asset_reveal_target()
        if target is None:
            messagebox.showinfo(self.tr("message.settings"), self.tr("message.settings.nothing_to_reveal"))
            return
        resolved = self._resolve_existing_asset_path(target)
        if resolved is None:
            messagebox.showwarning(self.tr("message.settings"), self.tr("message.settings.asset_not_found", path=str(target)))
            return
        try:
            if resolved.is_dir():
                os.startfile(str(resolved))
            else:
                subprocess.Popen(["explorer", "/select,", str(resolved)])
        except Exception as exc:
            self.app.log(f"Failed to reveal {resolved} in Explorer", exc)


def stadium_specs() -> list[SectionSpec]:
    return [
        SectionSpec("stadium", "Team Stadiums", kind="stadium", directory="StadiumGBD"),
        SectionSpec("comp", "Competition Stadiums", kind="stadium", directory="StadiumGBD"),
        SectionSpec("stadiumnetname", "Net By Stadium Name", kind="net", directory="StadiumGBD"),
        SectionSpec("stadiumnetid", "Net By Stadium ID", kind="net"),
        SectionSpec("scoreboardstdname", "Scoreboard Stadium Name (slot 176)", kind="scoreboardstdname", directory="StadiumGBD"),
        SectionSpec("scoreboardstdnamem", "Scoreboard Stadium Name (slot 261)", kind="scoreboardstdname", directory="StadiumGBD"),
        SectionSpec("exclude", "Excluded Competitions", kind="exclude"),
    ]


def asset_specs() -> list[SectionSpec]:
    return [
        SectionSpec("Scoreboard", "dialog.editor.choice.competition_scoreboards", kind="simple", directory="ScoreBoardGBD"),
        SectionSpec("TVLogo", "dialog.editor.choice.competition_tvlogos", kind="simple", directory="TVLogoGBD"),
        SectionSpec("HomeTeamScoreBoard", "dialog.editor.choice.home_team_scoreboards", kind="simple", directory="ScoreBoardGBD"),
        SectionSpec("HomeTeamTvLogo", "dialog.editor.choice.home_team_tvlogos", kind="simple", directory="TVLogoGBD"),
        SectionSpec("movies", "dialog.editor.choice.competition_movies", kind="simple", directory="MoviesGBD"),
        SectionSpec("TeamMovies", "dialog.editor.choice.team_movies", kind="simple", directory="MoviesGBD"),
        SectionSpec("DerbyMatch", "dialog.editor.choice.derby_movies", kind="simple", directory="MoviesGBD"),
        SectionSpec("kitsid", "dialog.editor.choice.kits_ids", kind="simple", directory="FSW\\Kits"),
    ]


def audio_specs() -> list[SectionSpec]:
    return [
        SectionSpec("chantsid", "dialog.editor.choice.chants_ids", kind="chants", directory="FSW\\Chants", recursive=True),
    ]
