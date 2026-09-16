from __future__ import annotations

import threading
import tkinter as tk
import unicodedata
import webbrowser
from pathlib import Path
from tkinter import messagebox, ttk

from PIL import Image, ImageTk

from .file_tools import (
    discover_stadium_names,
    resolve_asset_thumbnail_path,
    resolve_goalpost_model_preview_path,
    resolve_goalpost_texture_rx3_path,
    resolve_stadium_preview_path,
    stadium_country_code,
    stadium_country_counts,
    stadium_preview_fallback_path,
)
from .stadium_runtime import StadiumRuntime
from .video_preview import MoviePreviewPanel


SCOREBOARD_SCOPE_OPTIONS = (
    ("0", "dialog.scope.every_tournament"),
    ("1", "dialog.scope.specific_round"),
    ("2", "dialog.scope.team_scoreboard"),
    ("3", "dialog.scope.friendly_default"),
)

MOVIE_SCOPE_OPTIONS = (
    ("0", "dialog.scope.every_tournament"),
    ("1", "dialog.scope.specific_round"),
    ("2", "dialog.scope.derby_matchers"),
    ("3", "dialog.scope.team_movies"),
)

STADIUM_SCOPE_OPTIONS = (
    ("0", "dialog.scope.home_team"),
    ("1", "dialog.scope.specific_round"),
    ("2", "dialog.scope.multiple_home_team"),
    ("3", "dialog.scope.multiple_specific_round"),
    ("4", "dialog.scope.multiple_full_tournament"),
)


class BaseDialog(tk.Toplevel):
    def __init__(self, master: tk.Misc, title: str) -> None:
        owner = master._window() if hasattr(master, "_window") else master
        super().__init__(owner)
        self.app = master
        self.title(self.tr(title))
        self.resizable(True, True)
        self.transient(owner)
        self.grab_set()
        self.result = None
        self._apply_theme(master)
        self.deiconify()
        self.lift()
        try:
            self.focus_force()
        except Exception:
            pass

    def tr(self, key: str, **kwargs) -> str:
        app = getattr(self, "app", None)
        if app is not None and hasattr(app, "tr"):
            return app.tr(key, **kwargs)
        return key.format(**kwargs) if kwargs else key

    def _set_geometry(self, width: int, height: int, min_width: int, min_height: int) -> None:
        """Applies the app's current UI zoom (app_ui.py's zoom buttons) to a
        literal pixel window size, so a zoomed-in dialog doesn't clip its own
        (now bigger) fonts the same way the main window used to."""
        settings = getattr(getattr(self, "app", None), "settings", None)
        zoom = getattr(settings, "ui_zoom", 1.0) if settings is not None else 1.0
        self.geometry(f"{round(width * zoom)}x{round(height * zoom)}")
        self.minsize(round(min_width * zoom), round(min_height * zoom))

    def close_ok(self, value) -> None:
        self.result = value
        self.destroy()

    def _apply_theme(self, master: tk.Misc) -> None:
        self.bg = getattr(master, "bg", "#0b1220")
        self.panel = getattr(master, "panel", "#111a2b")
        self.panel_alt = getattr(master, "panel_alt", "#172338")
        self.card = getattr(master, "card", "#0f1727")
        self.card_soft = getattr(master, "card_soft", "#152033")
        self.fg = getattr(master, "fg", "#e6edf3")
        self.muted = getattr(master, "muted", "#93a1b2")
        self.accent = getattr(master, "accent", "#4cc2ff")
        self.gold = getattr(master, "gold", "#f6c177")
        self.configure(bg=self.bg)

    def _card(self, parent: tk.Misc, title: str, subtitle: str = "") -> tk.Frame:
        card = tk.Frame(parent, bg=self.card, highlightthickness=1, highlightbackground="#243654")
        header = tk.Frame(card, bg=self.card)
        header.pack(fill="x", padx=14, pady=(12, 8))
        tk.Label(header, text=title, bg=self.card, fg=self.fg, font=("Bahnschrift", 13, "bold")).pack(anchor="w")
        if subtitle:
            tk.Label(header, text=subtitle, bg=self.card, fg=self.muted, font=("Bahnschrift", 9)).pack(anchor="w", pady=(2, 0))
        return card

    def _dark_listbox(self, parent: tk.Misc, **kwargs) -> tk.Listbox:
        return tk.Listbox(
            parent,
            bg=self.panel,
            fg=self.fg,
            selectbackground="#19324d",
            selectforeground=self.fg,
            relief="flat",
            highlightthickness=1,
            highlightbackground="#243654",
            activestyle="none",
            **kwargs,
        )

    def _dark_label(self, parent: tk.Misc, text: str, muted: bool = False, **kwargs) -> tk.Label:
        return tk.Label(
            parent,
            text=text,
            bg=kwargs.pop("bg", self.card),
            fg=self.muted if muted else self.fg,
            **kwargs,
        )


class ScoreboardDialog(BaseDialog):
    def __init__(self, master: tk.Misc, exedir: Path, default_scope: str = "0") -> None:
        super().__init__(master, "dialog.assignment.title.scoreboard")
        self._set_geometry(1100, 720, 900, 620)
        self.scope_labels = {key: self.tr(label_key) for key, label_key in SCOREBOARD_SCOPE_OPTIONS}
        self.scope_ids = {v: k for k, v in self.scope_labels.items()}
        self.scope = tk.StringVar(value=self.scope_labels.get(default_scope, self.scope_labels["0"]))
        self.tvlogo = tk.StringVar(value="default")
        self.scoreboard = tk.StringVar(value="default")
        self._preview_images: dict[str, ImageTk.PhotoImage] = {}
        self._preview_labels: dict[str, tk.Label] = {}
        self._tvlogo_source = exedir / "TVLogoGBD"
        self._scoreboard_source = exedir / "ScoreBoardGBD"

        self.grid_columnconfigure(0, weight=3)
        self.grid_columnconfigure(1, weight=3)
        self.grid_columnconfigure(2, weight=4)
        self.grid_rowconfigure(1, weight=1)

        topbar = tk.Frame(self, bg=self.bg)
        topbar.grid(row=0, column=0, columnspan=3, sticky="ew", padx=14, pady=(14, 10))
        topbar.grid_columnconfigure(0, weight=1)
        self._dark_label(topbar, "TVLOGO / SCOREBOARD ASSIGN", bg=self.bg, font=("Bahnschrift", 18, "bold")).grid(row=0, column=0, sticky="w")
        self._dark_label(topbar, "Choose the assignment scope, select a TV logo and a scoreboard.", bg=self.bg, muted=True, font=("Bahnschrift", 10)).grid(row=1, column=0, sticky="w", pady=(2, 0))

        tvlogo_card = self._card(self, "TV Logo", "Select a TV logo pack.")
        tvlogo_card.grid(row=1, column=0, sticky="nsew", padx=(14, 6), pady=(0, 14))
        tvlogo_card.pack_propagate(False)
        tvlogo_body = tk.Frame(tvlogo_card, bg=self.card)
        tvlogo_body.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        tvlogo_body.grid_columnconfigure(0, weight=1)
        tvlogo_body.grid_rowconfigure(3, weight=1)
        self._dark_label(tvlogo_body, "Assignment Mode", muted=True, font=("Bahnschrift", 10), anchor="w").grid(row=0, column=0, sticky="w")
        ttk.Combobox(tvlogo_body, state="readonly", textvariable=self.scope,
            values=tuple(self.scope_labels[k] for k, _ in SCOREBOARD_SCOPE_OPTIONS),
            style="Server16.TCombobox",
        ).grid(row=1, column=0, sticky="ew", pady=(6, 12))
        self._dark_label(tvlogo_body, "TV Logo", muted=True, font=("Bahnschrift", 10), anchor="w").grid(row=2, column=0, sticky="w")
        tvlogo_wrap = tk.Frame(tvlogo_body, bg=self.card)
        tvlogo_wrap.grid(row=3, column=0, sticky="nsew")
        tvlogo_wrap.grid_columnconfigure(0, weight=1)
        tvlogo_wrap.grid_rowconfigure(0, weight=1)
        self._tvlogo_list = self._dark_listbox(tvlogo_wrap, exportselection=False, height=18, font=("Consolas", 10))
        tvlogo_scroll = ttk.Scrollbar(tvlogo_wrap, orient="vertical", command=self._tvlogo_list.yview, style="Server16.Vertical.TScrollbar")
        self._tvlogo_list.configure(yscrollcommand=tvlogo_scroll.set)
        self._tvlogo_list.grid(row=0, column=0, sticky="nsew")
        tvlogo_scroll.grid(row=0, column=1, sticky="ns", padx=(6, 0))
        self._populate_listbox(self._tvlogo_list, self._tvlogo_source, self.tvlogo)
        self._tvlogo_list.bind("<<ListboxSelect>>", lambda _e: self._on_tvlogo_select())

        sb_card = self._card(self, "ScoreBoard", "Select a scoreboard pack.")
        sb_card.grid(row=1, column=1, sticky="nsew", padx=(6, 6), pady=(0, 14))
        sb_card.pack_propagate(False)
        sb_body = tk.Frame(sb_card, bg=self.card)
        sb_body.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        sb_body.grid_columnconfigure(0, weight=1)
        sb_body.grid_rowconfigure(1, weight=1)
        self._dark_label(sb_body, "ScoreBoard", muted=True, font=("Bahnschrift", 10), anchor="w").grid(row=0, column=0, sticky="w")
        sb_wrap = tk.Frame(sb_body, bg=self.card)
        sb_wrap.grid(row=1, column=0, sticky="nsew")
        sb_wrap.grid_columnconfigure(0, weight=1)
        sb_wrap.grid_rowconfigure(0, weight=1)
        self._sb_list = self._dark_listbox(sb_wrap, exportselection=False, height=18, font=("Consolas", 10))
        sb_scroll = ttk.Scrollbar(sb_wrap, orient="vertical", command=self._sb_list.yview, style="Server16.Vertical.TScrollbar")
        self._sb_list.configure(yscrollcommand=sb_scroll.set)
        self._sb_list.grid(row=0, column=0, sticky="nsew")
        sb_scroll.grid(row=0, column=1, sticky="ns", padx=(6, 0))
        self._populate_listbox(self._sb_list, self._scoreboard_source, self.scoreboard)
        self._sb_list.bind("<<ListboxSelect>>", lambda _e: self._on_sb_select())

        right_card = self._card(self, "Preview", "Current selection and visual preview.")
        right_card.grid(row=1, column=2, sticky="nsew", padx=(6, 14), pady=(0, 14))
        right_card.pack_propagate(False)
        right_body = tk.Frame(right_card, bg=self.card)
        right_body.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        right_body.grid_columnconfigure(0, weight=1)

        sel_frame = tk.Frame(right_body, bg=self.card_soft, highlightthickness=1, highlightbackground="#243654")
        sel_frame.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        sel_frame.grid_columnconfigure(0, weight=1)
        self._dark_label(sel_frame, "Current Selection", bg=self.card_soft, muted=True, font=("Bahnschrift", 10)).grid(row=0, column=0, sticky="w", padx=12, pady=(10, 2))
        self._sel_tvlogo_lbl = self._dark_label(sel_frame, "TV Logo: default", bg=self.card_soft, font=("Consolas", 10, "bold"), anchor="w")
        self._sel_tvlogo_lbl.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 2))
        self._sel_sb_lbl = self._dark_label(sel_frame, "ScoreBoard: default", bg=self.card_soft, font=("Consolas", 10, "bold"), anchor="w")
        self._sel_sb_lbl.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 10))

        self._build_preview_sb(right_body, 1, "TV Logo Preview", "tvlogo", image_size=(340, 180))
        self._build_preview_sb(right_body, 2, "ScoreBoard Preview", "scoreboard", image_size=(340, 180))

        action_bar = tk.Frame(self, bg=self.bg)
        action_bar.grid(row=2, column=0, columnspan=3, sticky="ew", padx=14, pady=(0, 14))
        action_bar.grid_columnconfigure(0, weight=1)
        ttk.Button(action_bar, text=self.tr("button.select_and_assign"),
            command=lambda: self.close_ok({
                "selectedround": self.scope_ids.get(self.scope.get(), "0"),
                "Selectedtvlogo": self.tvlogo.get(),
                "Selectedscoreboard": self.scoreboard.get(),
            }),
        ).grid(row=0, column=0, sticky="ew")

    def _populate_listbox(self, listbox: tk.Listbox, base: Path, target: tk.StringVar) -> None:
        listbox.insert("end", "default")
        if base.exists():
            for p in sorted(base.iterdir()):
                if p.is_dir():
                    listbox.insert("end", p.name)
                elif p.suffix.lower() in {".zip", ".rar"}:
                    listbox.insert("end", p.name)
        listbox.selection_set(0)
        target.set("default")

    def _on_tvlogo_select(self) -> None:
        sel = self._tvlogo_list.curselection()
        if sel:
            val = self._tvlogo_list.get(sel[0])
            self.tvlogo.set(val)
            self._sel_tvlogo_lbl.configure(text=f"TV Logo: {val}")
            self._update_preview_for("tvlogo", self._tvlogo_source / val)

    def _on_sb_select(self) -> None:
        sel = self._sb_list.curselection()
        if sel:
            val = self._sb_list.get(sel[0])
            self.scoreboard.set(val)
            self._sel_sb_lbl.configure(text=f"ScoreBoard: {val}")
            self._update_preview_for("scoreboard", self._scoreboard_source / val)

    def _update_preview_for(self, key: str, folder: Path) -> None:
        image_path = resolve_asset_thumbnail_path(folder, key)
        self._update_preview_sb(key, image_path, f"No preview for {folder.name}")

    def _build_preview_sb(self, parent: tk.Misc, row: int, title: str, key: str, image_size: tuple[int, int] = (340, 180)) -> None:
        # tk.Label's -width/-height are character/line counts while showing
        # text (the "No preview" placeholder) but stop reserving enough room
        # once an image is configured on the same label, clipping it -- same
        # bug already fixed for the stadium preview in settings_editor.py's
        # _build_stadium_preview_box. Fix: give the wrapping frame a fixed
        # pixel height and grid_propagate(False) it, then let the preview
        # label fill that cell via sticky="nsew" instead of its own width/height.
        box_height = image_size[1] + 46
        frame = tk.Frame(parent, bg=self.card_soft, highlightthickness=1, highlightbackground="#243654", height=box_height)
        frame.grid(row=row, column=0, sticky="ew", pady=(0, 10))
        frame.grid_propagate(False)
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(1, weight=1)
        self._dark_label(frame, title, bg=self.card_soft, muted=True, font=("Bahnschrift", 10)).grid(row=0, column=0, sticky="w", padx=10, pady=(8, 4))
        preview = tk.Label(frame, text="No preview", bg=self.panel, fg=self.muted,
            anchor="center", justify="center", relief="flat")
        preview.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        preview.image_size = image_size
        self._preview_labels[key] = preview

    def _update_preview_sb(self, key: str, image_path: "Path | None", fallback_text: str) -> None:
        label = self._preview_labels.get(key)
        if not label:
            return
        self._preview_images.pop(key, None)
        if image_path is None or not image_path.exists():
            label.configure(image="", text=fallback_text, compound="center")
            return
        try:
            image = Image.open(image_path).convert("RGBA")
            image.thumbnail(getattr(label, "image_size", (340, 180)))
            photo = ImageTk.PhotoImage(image)
        except Exception:
            label.configure(image="", text=fallback_text, compound="center")
            return
        self._preview_images[key] = photo
        label.configure(image=photo, text="", compound="center")


class MovieDialog(BaseDialog):
    def __init__(self, master: tk.Misc, exedir: Path, default_scope: str = "0") -> None:
        super().__init__(master, "dialog.assignment.title.movie")
        self._set_geometry(640, 620, 560, 520)
        self.scope_labels = {key: self.tr(label_key) for key, label_key in MOVIE_SCOPE_OPTIONS}
        self.scope_ids = {self.tr(label_key): key for key, label_key in MOVIE_SCOPE_OPTIONS}
        self.scope = tk.StringVar(value=self.scope_labels.get(default_scope, self.scope_labels["0"]))
        self.movie = tk.StringVar()
        self.movie_dir = exedir / "MoviesGBD"

        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        ttk.Combobox(
            self,
            state="readonly",
            textvariable=self.scope,
            values=tuple(self.tr(label_key) for _, label_key in MOVIE_SCOPE_OPTIONS),
            style="Server16.TCombobox",
        ).grid(row=0, column=0, columnspan=2, sticky="ew", padx=12, pady=12)

        listbox = self._dark_listbox(self, exportselection=False, width=36, height=16, font=("Consolas", 10))
        listbox.grid(row=1, column=0, sticky="nsew", padx=(12, 6), pady=(0, 8))
        listbox.insert("end", "None")
        if self.movie_dir.exists():
            for directory in sorted(p for p in self.movie_dir.iterdir() if p.is_dir()):
                listbox.insert("end", directory.name)
        listbox.selection_set(0)
        self.movie.set("None")

        preview_wrap = tk.Frame(self, bg=self.card, highlightthickness=1, highlightbackground="#243654")
        preview_wrap.grid(row=1, column=1, sticky="nsew", padx=(6, 12), pady=(0, 8))
        self._dark_label(
            preview_wrap, self.tr("dialog.movie_preview.title"), bg=self.card, font=("Bahnschrift", 11, "bold")
        ).pack(anchor="w", padx=12, pady=(12, 6))
        self.preview_panel = MoviePreviewPanel(preview_wrap, self.app)
        self.preview_panel.pack(padx=12, pady=(0, 12))

        def _on_select(_event=None) -> None:
            selection = listbox.curselection()
            if not selection:
                return
            value = listbox.get(selection[0])
            self.movie.set(value)
            self._update_movie_preview(value)

        listbox.bind("<<ListboxSelect>>", _on_select)

        ttk.Button(
            self,
            text=self.tr("button.select_and_assign"),
            command=lambda: self.close_ok(
                {"selectedround": self.scope_ids.get(self.scope.get(), "0"), "Selectedmovie": self.movie.get()}
            ),
        ).grid(row=2, column=0, columnspan=2, sticky="ew", padx=12, pady=12)

    def _update_movie_preview(self, value: str) -> None:
        path = None
        if value and value != "None":
            candidate = self.movie_dir / value / "bootflowoutro.vp8"
            if candidate.exists():
                path = candidate
        self.preview_panel.set_movie(path)


class StadiumDialog(BaseDialog):
    def __init__(self, master: tk.Misc, exedir: Path, default_scope: str = "0") -> None:
        super().__init__(master, "dialog.assignment.title.stadium")
        self._set_geometry(1180, 760, 1060, 700)
        pitch_values = self._file_stems(self._first_existing(exedir / "FSW" / "Images" / "PitchMowPattern", exedir / "FSW" / "PitchMowPattern"))
        net_values = self._file_stems(self._first_existing(exedir / "FSW" / "Images" / "Nets", exedir / "FSW" / "Nets"))
        self.scope_labels = {key: self.tr(label_key) for key, label_key in STADIUM_SCOPE_OPTIONS}
        self.scope_ids = {self.tr(label_key): key for key, label_key in STADIUM_SCOPE_OPTIONS}
        self.scope = tk.StringVar(value=self.scope_labels.get(default_scope, self.tr(STADIUM_SCOPE_OPTIONS[0][1])))
        self.search_var = tk.StringVar()
        self.country_group_var = tk.StringVar()
        self.selectedpitch = tk.StringVar(value=pitch_values[0] if pitch_values else "0")
        self.selectednet = tk.StringVar(value=net_values[0] if net_values else "0")
        # Numeric ID, same convention as the settings.ini editor's Police combo
        # (settings_editor.py's SettingsSectionFrame._build_stadium_editor) --
        # previously this held the translated pattern name (e.g. "German"),
        # which looked inconsistent next to that editor showing plain "4".
        self.selectedpolice = tk.StringVar(value="1")
        # Model (shape, e.g. specificgoalpost_18_0.rx3) and texture/color
        # (e.g. specificnetsupportpost_0_0_textures.rx3) are independent,
        # separately selectable packs -- see StadiumRuntime.resolve_goalpost_sources.
        self.selectedgoalpost = tk.StringVar(value="None")
        self.selectedgoalposttexture = tk.StringVar(value="None")
        self.selectedstadium = tk.StringVar()
        # Which (comp, section) assignment targets this dialog session has
        # already pre-loaded the existing selection for (see
        # _reload_existing_selection_for_scope) -- seeded once per target so
        # switching scope back and forth doesn't clobber a selection the
        # user is actively editing, while still fixing the underlying bug
        # this exists for: reopening "Assign Stadium" to add one more
        # stadium to an already-multi-assigned team used to start from an
        # empty list, so Save silently replaced the whole existing
        # multi-stadium assignment with just whatever was freshly clicked.
        self._preloaded_targets: set[tuple[str, str]] = set()
        self._preview_images: dict[str, ImageTk.PhotoImage] = {}
        self._preview_labels: dict[str, tk.Label] = {}
        self._preview_frames: dict[str, tk.Frame] = {}
        self.stadium_source = exedir / "StadiumGBD"
        self.pitch_source = self._first_existing(exedir / "FSW" / "Images" / "PitchMowPattern", exedir / "FSW" / "PitchMowPattern")
        self.net_source = self._first_existing(exedir / "FSW" / "Images" / "Nets", exedir / "FSW" / "Nets")
        self.police_source = self._first_existing(exedir / "FSW" / "Images" / "Police", exedir / "FSW" / "Police")
        self.goalpost_model_source = exedir / "FSW" / "Goalpost" / "GoalpostModel"
        self.goalpost_texture_source = exedir / "FSW" / "Goalpost" / "GoalpostColor"
        self._all_stadiums = ["None"]
        self._country_group_labels = {"All Countries": self.tr("dialog.stadium.all_countries")}
        self._all_stadiums.extend(discover_stadium_names(self.stadium_source))
        self._country_group_values = self._build_country_group_values(self._all_stadiums)
        self.country_group_var.set(self._country_group_values[0] if self._country_group_values else self.tr("dialog.stadium.all_countries"))
        self.grid_columnconfigure(0, weight=5)
        self.grid_columnconfigure(1, weight=4)
        self.grid_rowconfigure(1, weight=1)

        topbar = tk.Frame(self, bg=self.bg)
        topbar.grid(row=0, column=0, columnspan=2, sticky="ew", padx=14, pady=(14, 10))
        topbar.grid_columnconfigure(0, weight=1)
        self._dark_label(topbar, self.tr("dialog.stadium.top_title"), bg=self.bg, font=("Bahnschrift", 18, "bold")).grid(row=0, column=0, sticky="w")
        self._dark_label(
            topbar,
            self.tr("dialog.stadium.top_subtitle"),
            bg=self.bg,
            muted=True,
            font=("Bahnschrift", 10),
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))

        left_card = self._card(self, self.tr("dialog.stadium.scope_card"), self.tr("dialog.stadium.scope_card_subtitle"))
        left_card.grid(row=1, column=0, sticky="nsew", padx=(14, 8), pady=(0, 14))
        left_card.pack_propagate(False)

        right_card = self._card(self, self.tr("dialog.stadium.visual_card"), self.tr("dialog.stadium.visual_card_subtitle"))
        right_card.grid(row=1, column=1, sticky="nsew", padx=(8, 14), pady=(0, 14))
        right_card.pack_propagate(False)

        left_body = tk.Frame(left_card, bg=self.card)
        left_body.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        left_body.grid_columnconfigure(0, weight=1)
        left_body.grid_rowconfigure(3, weight=1)

        self._dark_label(left_body, self.tr("dialog.stadium.assignment_mode"), muted=True, font=("Bahnschrift", 10), anchor="w").grid(row=0, column=0, sticky="w")
        scope_combo = ttk.Combobox(
            left_body,
            state="readonly",
            textvariable=self.scope,
            values=tuple(self.tr(label_key) for _, label_key in STADIUM_SCOPE_OPTIONS),
            style="Server16.TCombobox",
        )
        scope_combo.grid(row=1, column=0, sticky="ew", pady=(6, 12))

        self.selection_hint = self._dark_label(left_body, self.tr("dialog.stadium.single_selection"), muted=True, font=("Bahnschrift", 10), anchor="w")
        self.selection_hint.grid(row=2, column=0, sticky="w", pady=(0, 8))

        self._dark_label(left_body, self.tr("dialog.stadium.search"), muted=True, font=("Bahnschrift", 10), anchor="w").grid(row=3, column=0, sticky="w")
        search_entry = ttk.Entry(left_body, textvariable=self.search_var, style="Server16.TEntry")
        search_entry.grid(row=4, column=0, sticky="ew", pady=(6, 10))
        search_entry.bind("<KeyRelease>", self._on_search_changed)
        search_entry.bind("<Return>", self._on_search_changed)

        self._dark_label(left_body, self.tr("dialog.stadium.country_group"), muted=True, font=("Bahnschrift", 10), anchor="w").grid(row=5, column=0, sticky="w")
        self.country_group_combo = ttk.Combobox(
            left_body,
            state="readonly",
            textvariable=self.country_group_var,
            values=self._country_group_values,
            style="Server16.TCombobox",
        )
        self.country_group_combo.grid(row=6, column=0, sticky="ew", pady=(6, 10))
        self.country_group_combo.bind("<<ComboboxSelected>>", self._on_country_group_changed)

        stadium_list_wrap = tk.Frame(left_body, bg=self.card)
        stadium_list_wrap.grid(row=3, column=0, sticky="nsew")
        stadium_list_wrap.grid_columnconfigure(0, weight=1)
        stadium_list_wrap.grid_rowconfigure(0, weight=1)

        self.stadiums = self._dark_listbox(stadium_list_wrap, exportselection=False, height=22, selectmode="browse", font=("Consolas", 10))
        for stadium_name in self._all_stadiums:
            self.stadiums.insert("end", stadium_name)
        stadium_scroll = ttk.Scrollbar(
            stadium_list_wrap,
            orient="vertical",
            command=self.stadiums.yview,
            style="Server16.Vertical.TScrollbar",
        )
        self.stadiums.configure(yscrollcommand=stadium_scroll.set)
        self.stadiums.grid(row=0, column=0, sticky="nsew")
        stadium_scroll.grid(row=0, column=1, sticky="ns", padx=(8, 0))
        self.stadiums.selection_set(0)
        self.selectedstadium.set("None")
        self.stadiums.bind("<<ListboxSelect>>", lambda _event: self._refresh_selection())
        self.scope.trace_add("write", lambda *_args: self._update_mode())

        right_wrap = tk.Frame(right_card, bg=self.card)
        right_wrap.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        right_wrap.grid_columnconfigure(0, weight=1)
        right_wrap.grid_rowconfigure(0, weight=1)

        right_canvas = tk.Canvas(right_wrap, bg=self.card, highlightthickness=0, bd=0)
        right_scroll = ttk.Scrollbar(
            right_wrap,
            orient="vertical",
            command=right_canvas.yview,
            style="Server16.Vertical.TScrollbar",
        )
        right_body = tk.Frame(right_canvas, bg=self.card)
        right_body.grid_columnconfigure(0, weight=1)
        right_body.grid_rowconfigure(1, weight=1)
        right_body.grid_rowconfigure(2, weight=1)
        right_body.grid_rowconfigure(3, weight=1)
        right_body.bind(
            "<Configure>",
            lambda _event: right_canvas.configure(scrollregion=right_canvas.bbox("all")),
        )
        right_window = right_canvas.create_window((0, 0), window=right_body, anchor="nw")
        right_canvas.configure(yscrollcommand=right_scroll.set)
        right_canvas.grid(row=0, column=0, sticky="nsew")
        right_scroll.grid(row=0, column=1, sticky="ns", padx=(8, 0))
        right_canvas.bind(
            "<Configure>",
            lambda event: right_canvas.itemconfigure(right_window, width=event.width),
        )
        self._right_canvas = right_canvas
        self._right_body = right_body

        selected_card = tk.Frame(right_body, bg=self.card_soft, highlightthickness=1, highlightbackground="#243654")
        selected_card.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        selected_card.grid_columnconfigure(0, weight=1)
        self._dark_label(selected_card, self.tr("dialog.stadium.current_selection"), bg=self.card_soft, muted=True, font=("Bahnschrift", 10)).grid(row=0, column=0, sticky="w", padx=12, pady=(10, 2))
        self.selection_value = self._dark_label(selected_card, "None", bg=self.card_soft, font=("Consolas", 11, "bold"), anchor="w", justify="left", wraplength=420)
        self.selection_value.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 10))

        stadium_preview_row = tk.Frame(right_body, bg=self.card)
        stadium_preview_row.grid(row=1, column=0, sticky="nsew", pady=(0, 12))
        stadium_preview_row.grid_columnconfigure(0, weight=1)
        self._preview_frames["stadium"] = stadium_preview_row
        self._build_preview(stadium_preview_row, 0, self.tr("dialog.stadium.preview.stadium"), "stadium", image_size=(360, 220))

        preview_top = tk.Frame(right_body, bg=self.card)
        preview_top.grid(row=2, column=0, sticky="nsew")
        preview_top.grid_columnconfigure(0, weight=1)
        preview_top.grid_columnconfigure(1, weight=1)
        pitch_wrap = tk.Frame(preview_top, bg=self.card)
        pitch_wrap.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        pitch_wrap.grid_columnconfigure(0, weight=1)
        self._combo(pitch_wrap, 0, self.tr("dialog.stadium.pitch_pattern"), pitch_values, self.selectedpitch, self._on_pitch_changed)
        self._build_preview(pitch_wrap, 0, self.tr("dialog.stadium.preview.pitch"), "pitch", image_size=(155, 135), row=2)

        net_wrap = tk.Frame(preview_top, bg=self.card)
        net_wrap.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        net_wrap.grid_columnconfigure(0, weight=1)
        self._combo(net_wrap, 0, self.tr("dialog.stadium.net_pattern"), net_values, self.selectednet, self._on_net_changed)
        self._build_preview(net_wrap, 0, self.tr("dialog.stadium.preview.net"), "net", image_size=(155, 135), row=2)

        preview_bottom = tk.Frame(right_body, bg=self.card)
        preview_bottom.grid(row=3, column=0, sticky="nsew", pady=(12, 0))
        preview_bottom.grid_columnconfigure(0, weight=1)
        self._combo(
            preview_bottom,
            0,
            self.tr("dialog.stadium.police_pattern"),
            [str(i) for i in range(1, 11)],
            self.selectedpolice,
            self._on_police_changed,
        )
        self._build_preview(preview_bottom, 0, self.tr("dialog.stadium.preview.police"), "police", image_size=(360, 220), row=2)

        # Optional overrides, separate from GoalpostGBD/the police/pitch/net
        # triple above: [stadiumgoalpost] (model) and [stadiumgoalposttexture]
        # (net/post color), each keyed by stadium name (see
        # StadiumRuntime.resolve_goalpost_sources). "None" means no override
        # for that category -- vanilla for it, or (if BOTH stay "None") the
        # stadium keeps using its own bundled GoalpostGBD folder as a whole.
        # Side-by-side (like pitch_wrap/net_wrap above), not stacked, so both
        # previews sit at the same height.
        goalpost_row = tk.Frame(preview_bottom, bg=self.card)
        goalpost_row.grid(row=3, column=0, sticky="nsew", pady=(12, 0))
        goalpost_row.grid_columnconfigure(0, weight=1)
        goalpost_row.grid_columnconfigure(1, weight=1)

        goalpost_model_wrap = tk.Frame(goalpost_row, bg=self.card)
        goalpost_model_wrap.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        goalpost_model_wrap.grid_columnconfigure(0, weight=1)
        self._combo(
            goalpost_model_wrap,
            0,
            self.tr("dialog.stadium.goalpost_model"),
            self._folder_names(self.goalpost_model_source),
            self.selectedgoalpost,
            self._on_goalpost_model_changed,
        )
        self._build_preview(goalpost_model_wrap, 0, self.tr("dialog.stadium.preview.goalpost_model"), "goalpost_model", image_size=(155, 135), row=2)

        goalpost_texture_wrap = tk.Frame(goalpost_row, bg=self.card)
        goalpost_texture_wrap.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        goalpost_texture_wrap.grid_columnconfigure(0, weight=1)
        self._combo(
            goalpost_texture_wrap,
            0,
            self.tr("dialog.stadium.goalpost_texture"),
            self._folder_names(self.goalpost_texture_source),
            self.selectedgoalposttexture,
            self._on_goalpost_texture_changed,
        )
        self._build_preview(goalpost_texture_wrap, 0, self.tr("dialog.stadium.preview.goalpost_texture"), "goalpost_texture", image_size=(155, 135), row=2)

        # <MouseWheel> only fires on the exact widget under the cursor, not
        # its ancestors -- binding just right_canvas/right_body (as before)
        # left the wheel dead over almost the whole panel, since that's
        # covered by descendant labels/combos/frames. Bind every descendant
        # too, now that the full subtree exists (Listbox instances are
        # skipped so the left-panel stadium list, if ever nested in here,
        # keeps its own native per-widget wheel scrolling instead of being
        # hijacked into scrolling this canvas).
        self._bind_mousewheel_recursive(self._right_canvas, scroll_callback=lambda steps: self._right_canvas.yview_scroll(steps, "units"))

        action_bar = tk.Frame(self, bg=self.bg)
        action_bar.grid(row=2, column=0, columnspan=2, sticky="ew", padx=14, pady=(0, 14))
        action_bar.grid_columnconfigure(0, weight=1)
        ttk.Button(action_bar, text=self.tr("button.select_and_assign"), command=self._submit).grid(row=0, column=0, sticky="ew")
        self._ui_ready = True
        self._update_mode()
        self._update_stadium_preview()
        self._on_pitch_changed()
        self._on_net_changed()
        self._on_police_changed()
        self._on_goalpost_model_changed()
        self._on_goalpost_texture_changed()

    def _combo(self, parent: tk.Misc, row: int, label: str, values: list[str], variable: tk.StringVar, callback=None) -> None:
        self._dark_label(parent, label, muted=True, font=("Bahnschrift", 10), anchor="w").grid(row=row, column=0, sticky="w", pady=(0 if row == 0 else 12, 0))
        combo = ttk.Combobox(
            parent,
            state="readonly",
            textvariable=variable,
            values=values or ["0"],
            style="Server16.TCombobox",
        )
        combo.grid(row=row + 1, column=0, sticky="ew", pady=(6, 0))
        if callback is not None:
            combo.bind("<<ComboboxSelected>>", callback)

    def _bind_mousewheel_target(self, *widgets: tk.Misc, scroll_callback) -> None:
        def on_mousewheel(event):
            if event.delta == 0:
                return "break"
            scroll_callback(int(-1 * (event.delta / 120)))
            return "break"

        for widget in widgets:
            widget.bind("<MouseWheel>", on_mousewheel)

    def _bind_mousewheel_recursive(self, widget: tk.Misc, scroll_callback) -> None:
        """Like _bind_mousewheel_target, but walks the whole already-built
        subtree instead of a fixed widget list -- <MouseWheel> only ever
        fires on the exact widget directly under the cursor, so binding just
        a scrollable canvas/body leaves the wheel dead over any of its many
        descendant labels/combos/frames, which is most of the visible area.
        Skips tk.Listbox so a listbox with its own many rows (e.g. this
        dialog's own stadium picker) keeps its native per-widget wheel
        scrolling instead of being hijacked into scrolling this canvas.
        Call once, after the full subtree already exists -- widgets added
        later won't be covered."""
        if isinstance(widget, tk.Listbox):
            return
        self._bind_mousewheel_target(widget, scroll_callback=scroll_callback)
        for child in widget.winfo_children():
            self._bind_mousewheel_recursive(child, scroll_callback)

    def _file_stems(self, folder: Path) -> list[str]:
        if not folder.exists():
            return ["0"]
        return [item.stem for item in sorted(folder.iterdir()) if item.is_file()]

    def _folder_names(self, folder: Path) -> list[str]:
        names = ["None"]
        if folder.exists():
            names.extend(sorted(item.name for item in folder.iterdir() if item.is_dir()))
        return names

    def _country_code_for_stadium(self, stadium_name: str) -> str:
        return stadium_country_code(stadium_name)

    @staticmethod
    def _normalize_text(value: str) -> str:
        normalized = unicodedata.normalize("NFKD", value or "")
        return "".join(char for char in normalized if not unicodedata.combining(char)).lower()

    def _build_country_group_values(self, stadium_names: list[str]) -> list[str]:
        counts = stadium_country_counts(stadium_names)
        values = [f"{self.tr('dialog.stadium.all_countries')} ({sum(counts.values())})"]
        self._country_group_labels = {"All Countries": values[0]}
        for code in sorted(counts):
            label = f"{code} ({counts[code]})"
            self._country_group_labels[code] = label
            values.append(label)
        return values

    def _selected_country_group(self) -> str:
        current = self.country_group_var.get().strip()
        if not current:
            self.country_group_var.set(self._country_group_labels["All Countries"])
            return "All Countries"
        for code, label in self._country_group_labels.items():
            if current == label:
                return code
        if current == "All Countries":
            return "All Countries"
        self.country_group_var.set(self._country_group_labels["All Countries"])
        return "All Countries"

    def _on_search_changed(self, _event=None) -> str | None:
        self._refresh_stadium_list()
        return None

    def _on_country_group_changed(self, _event=None) -> str | None:
        if self.search_var.get():
            self.search_var.set("")
        self._refresh_stadium_list()
        return None

    def _refresh_stadium_list(self) -> None:
        if not self._ui_ready or not hasattr(self, "stadiums"):
            return
        previous_selection = self._selected_stadium_names()
        selected_name = previous_selection[0] if previous_selection else self.selectedstadium.get() or "None"
        query = self._normalize_text(self.search_var.get().strip())
        selected_group = self._selected_country_group()
        filtered = []
        for name in self._all_stadiums:
            if name == "None":
                if selected_group == "All Countries" and not query:
                    filtered.append(name)
                continue
            if selected_group != "All Countries" and self._country_code_for_stadium(name) != selected_group:
                continue
            if query and query not in self._normalize_text(name):
                continue
            filtered.append(name)
        if not filtered:
            filtered = ["None"]
        self.stadiums.delete(0, "end")
        for name in filtered:
            self.stadiums.insert("end", name)
        target_name = selected_name if selected_name in filtered else filtered[0]
        index = filtered.index(target_name)
        self.stadiums.selection_set(index)
        self.stadiums.activate(index)
        self.stadiums.see(index)
        self.selectedstadium.set(target_name)
        self._update_selection_summary()
        self._update_stadium_preview()

    def _selected_stadium_names(self) -> list[str]:
        if not hasattr(self, "stadiums"):
            return []
        selected = [self.stadiums.get(i) for i in self.stadiums.curselection()]
        if selected:
            return selected
        try:
            active_name = self.stadiums.get("active")
        except Exception:
            active_name = ""
        fallback = self.selectedstadium.get().strip()
        if active_name:
            return [active_name]
        if fallback:
            return [fallback]
        return []

    def _first_existing(self, *paths: Path) -> Path:
        for path in paths:
            if path.exists():
                return path
        return paths[0]

    def _update_mode(self) -> None:
        scope_id = self.scope_ids.get(self.scope.get(), "0")
        mode = "extended" if scope_id in {"2", "3", "4"} else "browse"
        self.stadiums.configure(selectmode=mode)
        self.selection_hint.configure(text=self.tr("dialog.stadium.multiple_selection") if mode == "extended" else self.tr("dialog.stadium.single_selection"))
        self._reload_existing_selection_for_scope(scope_id)
        self._update_selection_summary()

    def _resolve_existing_assignment_target(self, scope_id: str) -> tuple[str, str] | tuple[None, None]:
        """Same scope -> (comp id, ini section) mapping assign_stadium() uses
        to decide where to write (assignment_runtime.py) -- scopes 0/2 both
        target the Home Team's [stadium] key, 1/3 both target the Round's
        [comp] key, so "Home Team" and "Multiple Home Team" (etc.) are really
        two different UIs over the SAME underlying entry, not separate data."""
        app = self.app
        mapping = {
            "0": (getattr(app, "HID", "") or "", "stadium"),
            "1": (getattr(app, "TOURROUNDID", "") or "", "comp"),
            "2": (getattr(app, "HID", "") or "", "stadium"),
            "3": (getattr(app, "TOURROUNDID", "") or "", "comp"),
            "4": (getattr(app, "TOURNAME", "") or "", "comp"),
        }
        comp, section = mapping.get(scope_id, ("", ""))
        return (comp, section) if comp else (None, None)

    def _reload_existing_selection_for_scope(self, scope_id: str) -> None:
        comp, section = self._resolve_existing_assignment_target(scope_id)
        if not comp or not section:
            return
        target = (comp, section)
        if target in self._preloaded_targets:
            return  # already seeded this dialog session -- don't stomp an in-progress edit
        self._preloaded_targets.add(target)
        if not self.app.settings_ini.key_exists(comp, section):
            return
        raw_value = self.app.settings_ini.read(comp, section)
        stadiums, police, pitch, net = StadiumRuntime._parse_assignment(raw_value)
        if not stadiums:
            return
        self.stadiums.selection_clear(0, "end")
        names_in_list = [self.stadiums.get(i) for i in range(self.stadiums.size())]
        first_index = None
        for name in stadiums:
            if name in names_in_list:
                index = names_in_list.index(name)
                self.stadiums.selection_set(index)
                if first_index is None:
                    first_index = index
        if first_index is not None:
            self.stadiums.activate(first_index)
            self.stadiums.see(first_index)
        self.selectedstadium.set(stadiums[0])
        if police:
            self.selectedpolice.set(police)
        if pitch:
            self.selectedpitch.set(pitch)
        if net:
            self.selectednet.set(net)
        # [stadiumgoalpost]/[stadiumgoalposttexture] are separate sections
        # keyed by stadium name (see StadiumRuntime.resolve_goalpost_sources),
        # not part of this comma-joined value -- same "first assigned
        # stadium's own values" accepted limitation _parse_assignment's own
        # docstring already notes for police/pitch/net above.
        if self.app.settings_ini.key_exists(stadiums[0], "stadiumgoalpost"):
            existing_goalpost = self.app.settings_ini.read(stadiums[0], "stadiumgoalpost").strip()
            self.selectedgoalpost.set(existing_goalpost or "None")
        if self.app.settings_ini.key_exists(stadiums[0], "stadiumgoalposttexture"):
            existing_texture = self.app.settings_ini.read(stadiums[0], "stadiumgoalposttexture").strip()
            self.selectedgoalposttexture.set(existing_texture or "None")
        # .set() alone doesn't fire <<ComboboxSelected>> -- refresh both
        # goalpost previews explicitly, same as pitch/net/police already
        # need to right after this same preload elsewhere in this class.
        if getattr(self, "_ui_ready", False):
            self._on_goalpost_model_changed()
            self._on_goalpost_texture_changed()
        self._update_stadium_preview()

    def _refresh_selection(self) -> None:
        selected = [self.stadiums.get(i) for i in self.stadiums.curselection()]
        scope_id = self.scope_ids.get(self.scope.get(), "0")
        if selected and scope_id not in {"2", "3", "4"}:
            self.selectedstadium.set(selected[0])
        self._update_selection_summary()
        self._update_stadium_preview()

    def _update_selection_summary(self) -> None:
        selected = [self.stadiums.get(i) for i in self.stadiums.curselection()]
        if not selected:
            text = "None"
        elif len(selected) == 1:
            text = selected[0]
        else:
            text = ", ".join(selected[:6])
            if len(selected) > 6:
                text += f" ... (+{len(selected) - 6})"
        self.selection_value.configure(text=text)

    def _resolve_stadium_preview_path(self, stadium_name: str) -> Path | None:
        return resolve_stadium_preview_path(self.stadium_source, stadium_name)

    def _build_preview(
        self,
        parent: tk.Misc,
        column: int,
        title: str,
        key: str,
        image_size: tuple[int, int] = (280, 220),
        row: int = 0,
    ) -> None:
        # A tk.Label's -width/-height are character/line counts while it's
        # showing the "No preview" placeholder text, but once an image is
        # configured onto the same label those same numbers stop reserving
        # enough room and the image renders clipped -- confirmed live, this
        # was cropping every preview in this dialog down to ~60px tall.
        # Sidestep it: give the wrapping frame a fixed pixel size (image_size
        # plus room for the title + padding) and grid_propagate(False) it, so
        # the frame's size is guaranteed independent of whether the label is
        # currently showing placeholder text or the real thumbnail.
        box_width = image_size[0] + 24
        box_height = image_size[1] + 60
        frame = tk.Frame(
            parent,
            bg=self.card_soft,
            highlightthickness=1,
            highlightbackground="#243654",
            width=box_width,
            height=box_height,
        )
        frame.grid(row=row, column=column, padx=(0 if column == 0 else 6, 0), sticky="nsew")
        frame.grid_propagate(False)
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(1, weight=1)
        self._dark_label(frame, title, bg=self.card_soft, muted=True, font=("Bahnschrift", 10)).grid(row=0, column=0, sticky="w", padx=10, pady=(10, 6))
        preview = tk.Label(
            frame,
            text=self.tr("placeholder.no_preview"),
            bg=self.panel,
            fg=self.muted,
            anchor="center",
            justify="center",
            relief="flat",
        )
        preview.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        preview.image_size = image_size
        self._preview_labels[key] = preview

    def _update_preview(self, key: str, image_path: Path | None, fallback_text: str) -> None:
        label = self._preview_labels[key]
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
        selected = [self.stadiums.get(i) for i in self.stadiums.curselection()]
        stadium_name = next((name for name in selected if name and name != "None"), "")
        image_path = self._resolve_stadium_preview_path(stadium_name)
        if image_path is None and stadium_name:
            image_path = stadium_preview_fallback_path()
        preview_frame = self._preview_frames.get("stadium")
        if preview_frame is not None:
            if image_path is None:
                preview_frame.grid_remove()
            else:
                preview_frame.grid()
        fallback = stadium_name if stadium_name else self.tr("placeholder.no_stadium_preview")
        self._update_preview("stadium", image_path, fallback)

    def _on_pitch_changed(self, _event=None) -> None:
        image_path = self.pitch_source / f"{self.selectedpitch.get()}.png"
        self._update_preview("pitch", image_path, self.tr("dialog.stadium.pitch_value", value=self.selectedpitch.get() or "-"))

    def _on_net_changed(self, _event=None) -> None:
        image_path = self.net_source / f"{self.selectednet.get()}.png"
        self._update_preview("net", image_path, self.tr("dialog.stadium.net_value", value=self.selectednet.get() or "-"))

    def _on_police_changed(self, _event=None) -> None:
        police_id = self.selectedpolice.get().strip() or "1"
        image_path = self.police_source / f"{police_id}.png"
        self._update_preview("police", image_path, police_id)

    def _on_goalpost_model_changed(self, _event=None) -> None:
        # Static image, unlike the texture side below -- see the "preview"
        # convention documented on resolve_goalpost_model_preview_path.
        name = self.selectedgoalpost.get().strip()
        image_path = resolve_goalpost_model_preview_path(self.goalpost_model_source, name) if name and name != "None" else None
        self._update_preview("goalpost_model", image_path, self.tr("placeholder.no_preview"))

    def _on_goalpost_texture_changed(self, _event=None) -> None:
        # Unlike every other preview in this dialog (all plain image files),
        # a GoalpostColor pack has no preview image convention -- the
        # preview is rendered from the pack's own .rx3 texture via the
        # 32-bit FifaLibrary bridge (StadiumRuntime.
        # render_goalpost_texture_preview), so this has to run off the UI
        # thread and guard against a newer selection superseding a still-
        # running render, same pattern app_ui.py's Kit Mixer preview uses.
        name = self.selectedgoalposttexture.get().strip()
        self._goalpost_texture_preview_generation = getattr(self, "_goalpost_texture_preview_generation", 0) + 1
        generation = self._goalpost_texture_preview_generation
        if not name or name == "None":
            self._update_preview("goalpost_texture", None, self.tr("placeholder.no_preview"))
            return
        source_rx3 = resolve_goalpost_texture_rx3_path(self.goalpost_texture_source, name)
        if source_rx3 is None:
            self._update_preview("goalpost_texture", None, self.tr("placeholder.no_preview"))
            return
        self._update_preview("goalpost_texture", None, self.tr("dialog.kitmix.loading"))

        def worker() -> None:
            try:
                png_path = self.app.stadium_runtime.render_goalpost_texture_preview(source_rx3, cache_key=name)
                error = None
            except Exception as exc:  # noqa: BLE001 - surfaced as a preview placeholder
                png_path, error = None, exc
            self.after(0, lambda: self._apply_goalpost_texture_preview_result(generation, png_path, error))

        threading.Thread(target=worker, daemon=True).start()

    def _apply_goalpost_texture_preview_result(self, generation: int, png_path, error) -> None:
        if getattr(self, "_goalpost_texture_preview_generation", 0) != generation:
            return  # a newer selection superseded this one while the worker ran
        if error is not None or png_path is None:
            self._update_preview("goalpost_texture", None, self.tr("dialog.kitmix.preview_error"))
            return
        self._update_preview("goalpost_texture", png_path, self.tr("dialog.kitmix.preview_error"))

    def _submit(self) -> None:
        selected = [self.stadiums.get(i) for i in self.stadiums.curselection()]
        police_id = self.selectedpolice.get().strip() or "1"
        payload = {
            "selectedround": self.scope_ids.get(self.scope.get(), "0"),
            "Selectedstadium": selected[0] if selected else "",
            "multistadium": selected,
            "selectedpitch": self.selectedpitch.get(),
            "selectednet": self.selectednet.get(),
            "selectedpolice": police_id,
            "selectedgoalpost": self.selectedgoalpost.get(),
            "selectedgoalposttexture": self.selectedgoalposttexture.get(),
        }
        self.close_ok(payload)


class ExcludeDialog(BaseDialog):
    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master, "dialog.assignment.title.exclude")
        ttk.Button(self, text=self.tr("button.comp_id"), command=lambda: self.close_ok("COMP ID")).pack(fill="x", padx=12, pady=8)
        ttk.Button(self, text=self.tr("button.comp_round_id"), command=lambda: self.close_ok("COMP ROUND ID")).pack(fill="x", padx=12, pady=(0, 12))


class SectionPickerDialog(BaseDialog):
    """Checkbox list of settings.ini sections ('blocks'), shared by the export and import
    settings flows. `confirm_key` closes the dialog with the list of checked section names."""

    def __init__(
        self,
        master: tk.Misc,
        title_key: str,
        subtitle_key: str,
        sections: list[str],
        section_counts: dict[str, int],
        confirm_key: str,
    ) -> None:
        super().__init__(master, title_key)
        self._set_geometry(460, 560, 400, 420)
        self.section_vars: dict[str, tk.BooleanVar] = {}
        self._suspend_sync = False

        self._dark_label(
            self,
            self.tr(subtitle_key),
            bg=self.bg,
            muted=True,
            font=("Bahnschrift", 10),
            wraplength=420,
            justify="left",
            anchor="w",
        ).pack(fill="x", padx=16, pady=(16, 8))

        self.all_var = tk.BooleanVar(value=True)
        self._themed_checkbutton(
            self,
            text=self.tr("dialog.settings_io.all"),
            variable=self.all_var,
            bg=self.bg,
            command=self._toggle_all,
        ).pack(anchor="w", padx=16, pady=(0, 6))

        tk.Frame(self, bg="#22314b", height=1).pack(fill="x", padx=16, pady=(0, 8))

        list_card = tk.Frame(self, bg=self.card, highlightthickness=1, highlightbackground="#243654")
        list_card.pack(fill="both", expand=True, padx=16, pady=(0, 12))

        canvas = tk.Canvas(list_card, bg=self.card, highlightthickness=0, bd=0)
        scroll = ttk.Scrollbar(list_card, orient="vertical", command=canvas.yview, style="Server16.Vertical.TScrollbar")
        body = tk.Frame(canvas, bg=self.card)
        body.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        window = canvas.create_window((0, 0), window=body, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=8)
        scroll.pack(side="right", fill="y", padx=(0, 8), pady=8)
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(window, width=e.width))

        for section in sections:
            var = tk.BooleanVar(value=True)
            self.section_vars[section] = var
            var.trace_add("write", self._sync_all_checkbox)
            row = tk.Frame(body, bg=self.card)
            row.pack(fill="x", padx=8, pady=3)
            self._themed_checkbutton(row, text=f"[{section}]", variable=var, bg=self.card).pack(side="left")
            count = section_counts.get(section, 0)
            self._dark_label(
                row,
                self.tr("dialog.editor.entries_count", count=count),
                bg=self.card,
                muted=True,
                font=("Bahnschrift", 9),
            ).pack(side="right")

        # A plain widget-level bind("<MouseWheel>") only fires when the cursor is
        # directly over that widget — since the checkbox rows fill nearly all of
        # `body`'s visible area, binding just canvas/body left almost nowhere for
        # the event to land on. Bind every descendant instead so the wheel works
        # no matter which row/checkbox/label is under the cursor.
        self._bind_mousewheel_recursive(canvas, canvas)
        self._bind_mousewheel_recursive(body, canvas)

        action_bar = tk.Frame(self, bg=self.bg)
        action_bar.pack(fill="x", padx=16, pady=(0, 16))
        ttk.Button(action_bar, text=self.tr(confirm_key), command=self._confirm).pack(fill="x")

    def _themed_checkbutton(self, parent: tk.Misc, text: str, variable: tk.BooleanVar, bg: str, command=None) -> tk.Checkbutton:
        return tk.Checkbutton(
            parent,
            text=text,
            variable=variable,
            command=command,
            bg=bg,
            activebackground=bg,
            fg=self.fg,
            selectcolor=self.panel,
            activeforeground=self.fg,
            relief="flat",
            bd=0,
            cursor="hand2",
            highlightthickness=0,
            font=("Bahnschrift", 10),
        )

    def _bind_mousewheel_recursive(self, widget: tk.Misc, canvas: tk.Canvas) -> None:
        def on_mousewheel(event):
            if event.delta == 0:
                return "break"
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            return "break"

        widget.bind("<MouseWheel>", on_mousewheel)
        for child in widget.winfo_children():
            self._bind_mousewheel_recursive(child, canvas)

    def _toggle_all(self) -> None:
        value = self.all_var.get()
        self._suspend_sync = True
        try:
            for var in self.section_vars.values():
                var.set(value)
        finally:
            self._suspend_sync = False

    def _sync_all_checkbox(self, *_args) -> None:
        if self._suspend_sync or not self.section_vars:
            return
        self.all_var.set(all(var.get() for var in self.section_vars.values()))

    def _confirm(self) -> None:
        selected = [section for section, var in self.section_vars.items() if var.get()]
        if not selected:
            messagebox.showwarning(self.tr("message.settings_io"), self.tr("message.settings_io.select_one"))
            return
        self.close_ok(selected)


class ImportModeDialog(BaseDialog):
    """Shown right after SectionPickerDialog in the settings-import flow, once the user has
    picked which sections to import. Asks whether each selected section should be replaced
    wholesale (old keys the import doesn't mention are removed) or merged (only keys currently
    missing are added; existing values are never touched). `close_ok` receives "replace" or
    "merge"."""

    def __init__(self, master: tk.Misc, section_count: int) -> None:
        super().__init__(master, "dialog.settings_io.mode_title")
        self._set_geometry(420, 300, 380, 280)

        self._dark_label(
            self,
            self.tr("dialog.settings_io.mode_subtitle", count=section_count),
            bg=self.bg,
            muted=True,
            font=("Bahnschrift", 10),
            wraplength=380,
            justify="left",
            anchor="w",
        ).pack(fill="x", padx=16, pady=(16, 12))

        def _option(button_key: str, desc_key: str, mode: str) -> None:
            frame = tk.Frame(self, bg=self.card, highlightthickness=1, highlightbackground="#243654")
            frame.pack(fill="x", padx=16, pady=(0, 10))
            ttk.Button(frame, text=self.tr(button_key), command=lambda: self.close_ok(mode)).pack(fill="x", padx=10, pady=(10, 4))
            self._dark_label(
                frame,
                self.tr(desc_key),
                bg=self.card,
                muted=True,
                font=("Bahnschrift", 9),
                wraplength=350,
                justify="left",
                anchor="w",
            ).pack(fill="x", padx=10, pady=(0, 10))

        _option("dialog.settings_io.mode_replace", "dialog.settings_io.mode_replace_desc", "replace")
        _option("dialog.settings_io.mode_merge", "dialog.settings_io.mode_merge_desc", "merge")


class AboutDialog(BaseDialog):
    _GITHUB = "https://github.com/michelMK45/CG-File-Server-16---Python-Port"
    _FORUM = "https://soccergaming.com/forums/threads/cg-file-server-16-python-port.6475909/"
    _TRELLO = "https://trello.com/b/Y5Akq5is/cg-file-server-16-python-port"
    _GITHUB_LEGACY = "https://github.com/igor1043/CG-File-Server-16---Python-Port"
    _DONATE = "https://paypal.me/michellmk"

    def __init__(self, master: tk.Misc, version: str) -> None:
        super().__init__(master, "dialog.about.title")
        self.resizable(False, False)
        self._build(version)
        # Sized from actual packed content rather than a hardcoded WxH —
        # credits/library rows wrap and grow over time, and a fixed guess
        # silently clips whatever doesn't fit instead of adapting.
        self.update_idletasks()
        self.geometry(f"{self.winfo_reqwidth()}x{self.winfo_reqheight()}")

    def _build(self, version: str) -> None:
        header = tk.Frame(self, bg=self.panel, pady=18)
        header.pack(fill="x")
        tk.Label(header, text="CG SERVER 16", bg=self.panel, fg=self.gold,
                 font=("Bahnschrift", 17, "bold")).pack()
        tk.Label(header, text="Python Port", bg=self.panel, fg=self.muted,
                 font=("Bahnschrift", 10)).pack()
        tk.Label(header, text=f"v{version}", bg=self.panel, fg=self.accent,
                 font=("Bahnschrift", 9)).pack(pady=(4, 0))

        tk.Frame(self, bg="#22314b", height=1).pack(fill="x")

        body = tk.Frame(self, bg=self.bg, padx=22, pady=16)
        body.pack(fill="both", expand=True)

        tk.Label(body, text=self.tr("dialog.about.links"), bg=self.bg, fg=self.muted,
                 font=("Bahnschrift", 8, "bold")).pack(anchor="w")

        links_row = tk.Frame(body, bg=self.bg)
        links_row.pack(anchor="w", pady=(7, 16))
        for key, url in (
            ("dialog.about.github", self._GITHUB),
            ("dialog.about.forum", self._FORUM),
            ("dialog.about.trello", self._TRELLO),
            ("dialog.about.github.legacy", self._GITHUB_LEGACY),
            ("dialog.about.donate", self._DONATE),
        ):
            lbl = tk.Label(links_row, text=self.tr(key), bg=self.bg, fg=self.accent,
                           font=("Bahnschrift", 10, "underline"), cursor="hand2")
            lbl.pack(side="left", padx=(0, 16))
            lbl.bind("<Button-1>", lambda _, u=url: webbrowser.open(u))

        tk.Frame(body, bg="#22314b", height=1).pack(fill="x", pady=(0, 14))

        def credit_row(parent: tk.Misc, label_key: str, names: str) -> None:
            row = tk.Frame(parent, bg=self.bg)
            row.pack(fill="x", pady=(9, 0))
            tk.Label(row, text=self.tr(label_key), bg=self.bg, fg=self.muted,
                     font=("Bahnschrift", 8)).pack(anchor="w")
            tk.Label(row, text=names, bg=self.bg, fg=self.fg, font=("Bahnschrift", 10, "bold"),
                     wraplength=360, justify="left", anchor="w").pack(anchor="w", fill="x")

        tk.Label(body, text=self.tr("dialog.about.credits"), bg=self.bg, fg=self.muted,
                 font=("Bahnschrift", 8, "bold")).pack(anchor="w")

        credit_row(body, "dialog.about.developer", "igorVin")
        credit_row(body, "dialog.about.developer_continuing", "MichelMK")
        credit_row(body, "dialog.about.collaborators", "NonoLoko, hoondori34")
        credit_row(body, "dialog.about.special_thanks", "Robson Mambrini, RHZhang, Guiiro, dinei, FIFA 16 COMUNITY")

        tk.Frame(body, bg="#22314b", height=1).pack(fill="x", pady=(14, 0))
        tk.Label(body, text=self.tr("dialog.about.libraries"), bg=self.bg, fg=self.muted,
                 font=("Bahnschrift", 8, "bold")).pack(anchor="w", pady=(14, 0))

        credit_row(body, "dialog.about.libraries_fifalib", "FifaLibrary16 (rzocc)")
        credit_row(body, "dialog.about.libraries_rmlui", "RmlUi (MIT License)")
        credit_row(body, "dialog.about.libraries_freetype", "FreeType (FreeType License)")

        tk.Frame(self, bg="#22314b", height=1).pack(fill="x")
        foot = tk.Frame(self, bg=self.panel, pady=10)
        foot.pack(fill="x")
        ttk.Button(foot, text=self.tr("dialog.about.close"),
                   command=self.destroy).pack(side="right", padx=14)


class FifaLocationWarningDialog(BaseDialog):
    """Shown by app_settings.py's _check_fifa_location -- both at startup (app.py's __init__,
    right after setuppaths()) and right after a user manually links a FIFA exe via
    select_fifa_exe() -- whenever this program ends up running from a different folder than
    the linked fifa16.exe. Launch FIFA and every file operation that assumes co-location
    (exedir is always derived from the linked FIFA exe's own parent, never from where this
    program itself lives) will misbehave. `close_ok(True)` means "continue anyway";
    `close_ok(False)`, wired to the window's own X button too, means "close the application"
    -- deliberately the same, cautious default, since dismissing an unresolved warning should
    never be read as consent to proceed."""

    def __init__(self, master: tk.Misc, fifa_dir: Path, app_dir: Path) -> None:
        super().__init__(master, "dialog.fifa_location.title")
        self._set_geometry(520, 300, 460, 260)
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", lambda: self.close_ok(False))

        body = tk.Frame(self, bg=self.bg, padx=18, pady=16)
        body.pack(fill="both", expand=True)

        tk.Label(
            body,
            text=self.tr("dialog.fifa_location.heading"),
            bg=self.bg,
            fg=self.gold,
            font=("Bahnschrift", 12, "bold"),
            wraplength=460,
            justify="left",
            anchor="w",
        ).pack(fill="x")

        self._dark_label(
            body,
            self.tr("dialog.fifa_location.body"),
            bg=self.bg,
            font=("Bahnschrift", 10),
            wraplength=460,
            justify="left",
            anchor="w",
        ).pack(fill="x", pady=(10, 10))

        paths = tk.Frame(body, bg=self.card, highlightthickness=1, highlightbackground="#243654")
        paths.pack(fill="x", pady=(0, 14))
        self._dark_label(
            paths,
            self.tr("dialog.fifa_location.app_path", path=str(app_dir)),
            bg=self.card,
            muted=True,
            font=("Consolas", 9),
            wraplength=430,
            justify="left",
            anchor="w",
        ).pack(fill="x", padx=10, pady=(8, 2))
        self._dark_label(
            paths,
            self.tr("dialog.fifa_location.fifa_path", path=str(fifa_dir)),
            bg=self.card,
            muted=True,
            font=("Consolas", 9),
            wraplength=430,
            justify="left",
            anchor="w",
        ).pack(fill="x", padx=10, pady=(0, 8))

        actions = tk.Frame(body, bg=self.bg)
        actions.pack(fill="x", side="bottom")
        ttk.Button(actions, text=self.tr("dialog.fifa_location.close"), command=lambda: self.close_ok(False)).pack(side="left", fill="x", expand=True, padx=(0, 6))
        ttk.Button(actions, text=self.tr("dialog.fifa_location.continue"), command=lambda: self.close_ok(True)).pack(side="right", fill="x", expand=True, padx=(6, 0))
