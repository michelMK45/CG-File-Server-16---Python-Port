from __future__ import annotations

import tkinter as tk
import unicodedata
from pathlib import Path
from tkinter import ttk

from PIL import Image, ImageTk

from .file_tools import discover_stadium_names, resolve_stadium_preview_path


SCOREBOARD_SCOPE_OPTIONS = (
    ("0", "dialog.scope.every_tournament"),
    ("1", "dialog.scope.specific_round"),
    ("2", "dialog.scope.team_scoreboard"),
    ("3", "Friendly / Default (all matches without tournament)"),
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

POLICE_PATTERN_OPTIONS = (
    ("1", "dialog.police.english"),
    ("2", "dialog.police.french"),
    ("3", "dialog.police.italian"),
    ("4", "dialog.police.german"),
    ("6", "dialog.police.mexican"),
    ("7", "dialog.police.asiatic"),
    ("8", "dialog.police.african_traits"),
    ("9", "dialog.police.caucasic_traits"),
    ("10", "dialog.police.arabic_traits"),
)


class BaseDialog(tk.Toplevel):
    def __init__(self, master: tk.Misc, title: str) -> None:
        owner = master._window() if hasattr(master, "_window") else master
        super().__init__(owner)
        self.app = master
        self.title(title)
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
        super().__init__(master, self.tr("dialog.assignment.title.scoreboard"))
        self.geometry("1100x720")
        self.minsize(900, 620)
        self.scope_labels = {key: (self.tr(label_key) if not label_key.startswith("Friendly") else label_key) for key, label_key in SCOREBOARD_SCOPE_OPTIONS}
        self.scope_ids = {v: k for k, v in self.scope_labels.items()}
        self.scope = tk.StringVar(value=self.scope_labels.get(default_scope, self.scope_labels["0"]))
        self.tvlogo = tk.StringVar(value="default")
        self.scoreboard = tk.StringVar(value="default")
        self._preview_images: dict[str, ImageTk.PhotoImage] = {}
        self._preview_labels: dict[str, tk.Label] = {}
        self._preview_frames: dict[str, tk.Frame] = {}
        self._ui_ready = False
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
        tvlogo_scroll = ttk.Scrollbar(tvlogo_wrap, orient="vertical", command=self._tvlogo_list.yview)
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
        sb_scroll = ttk.Scrollbar(sb_wrap, orient="vertical", command=self._sb_list.yview)
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

        self._build_preview(right_body, 1, "TV Logo Preview", "tvlogo", image_size=(340, 180))
        self._build_preview(right_body, 2, "ScoreBoard Preview", "scoreboard", image_size=(340, 180))

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
        image_path = None
        if folder.exists() and folder.is_dir():
            thumbnail_dir = folder / "render" / "thumbnail"
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
        self._update_preview(key, image_path, f"No preview for {folder.name}")

    def _build_preview(self, parent: tk.Misc, row: int, title: str, key: str, image_size: tuple[int, int] = (340, 180)) -> None:
        frame = tk.Frame(parent, bg=self.card_soft, highlightthickness=1, highlightbackground="#243654")
        frame.grid(row=row, column=0, sticky="ew", pady=(0, 10))
        frame.grid_columnconfigure(0, weight=1)
        self._dark_label(frame, title, bg=self.card_soft, muted=True, font=("Bahnschrift", 10)).pack(anchor="w", padx=10, pady=(8, 4))
        preview = tk.Label(frame, text="No preview", bg=self.panel, fg=self.muted,
            anchor="center", justify="center", relief="flat", width=38, height=10)
        preview.pack(fill="x", padx=10, pady=(0, 10), ipadx=8, ipady=12)
        preview.image_size = image_size
        self._preview_labels[key] = preview

    def _update_preview(self, key: str, image_path: Path | None, fallback_text: str) -> None:
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

    def _build_listbox(self, row: int, column: int, base: Path, default: str, target: tk.StringVar) -> None:
        listbox = tk.Listbox(self, exportselection=False, width=28, height=16)
        listbox.grid(row=row, column=column, padx=12, pady=8)
        listbox.insert("end", default)
        if base.exists():
            for p in sorted(base.iterdir()):
                if p.is_dir():
                    listbox.insert("end", p.name)
                elif p.suffix.lower() in {".zip", ".rar"}:
                    listbox.insert("end", p.name)
        listbox.selection_set(0)
        target.set(default)
        listbox.bind("<<ListboxSelect>>", lambda _event: target.set(listbox.get("active")))


class MovieDialog(BaseDialog):
    def __init__(self, master: tk.Misc, exedir: Path, default_scope: str = "0") -> None:
        super().__init__(master, self.tr("dialog.assignment.title.movie"))
        self.scope_labels = {key: self.tr(label_key) for key, label_key in MOVIE_SCOPE_OPTIONS}
        self.scope_ids = {self.tr(label_key): key for key, label_key in MOVIE_SCOPE_OPTIONS}
        self.scope = tk.StringVar(value=self.scope_labels.get(default_scope, self.scope_labels["0"]))
        self.movie = tk.StringVar()
        ttk.Combobox(
            self,
            state="readonly",
            textvariable=self.scope,
            values=tuple(self.tr(label_key) for _, label_key in MOVIE_SCOPE_OPTIONS),
            style="Server16.TCombobox",
        ).pack(fill="x", padx=12, pady=12)
        listbox = tk.Listbox(self, exportselection=False, width=36, height=16)
        listbox.pack(padx=12, pady=8)
        listbox.insert("end", "None")
        movie_dir = exedir / "MoviesGBD"
        if movie_dir.exists():
            for directory in sorted(p for p in movie_dir.iterdir() if p.is_dir()):
                listbox.insert("end", directory.name)
        listbox.selection_set(0)
        self.movie.set("None")
        listbox.bind("<<ListboxSelect>>", lambda _event: self.movie.set(listbox.get("active")))
        ttk.Button(
            self,
            text=self.tr("button.select_and_assign"),
            command=lambda: self.close_ok(
                {"selectedround": self.scope_ids.get(self.scope.get(), "0"), "Selectedmovie": self.movie.get()}
            ),
        ).pack(fill="x", padx=12, pady=12)


class StadiumDialog(BaseDialog):
    def __init__(self, master: tk.Misc, exedir: Path, default_scope: str = "0") -> None:
        super().__init__(master, self.tr("dialog.assignment.title.stadium"))
        self.geometry("1180x760")
        self.minsize(1060, 700)
        pitch_values = self._file_stems(self._first_existing(exedir / "FSW" / "Images" / "PitchMowPattern", exedir / "FSW" / "PitchMowPattern"))
        net_values = self._file_stems(self._first_existing(exedir / "FSW" / "Images" / "Nets", exedir / "FSW" / "Nets"))
        self.scope_labels = {key: self.tr(label_key) for key, label_key in STADIUM_SCOPE_OPTIONS}
        self.scope_ids = {self.tr(label_key): key for key, label_key in STADIUM_SCOPE_OPTIONS}
        self.police_labels = {key: self.tr(label_key) for key, label_key in POLICE_PATTERN_OPTIONS}
        self.police_ids = {self.tr(label_key): key for key, label_key in POLICE_PATTERN_OPTIONS}
        self.scope = tk.StringVar(value=self.scope_labels.get(default_scope, self.tr(STADIUM_SCOPE_OPTIONS[0][1])))
        self.search_var = tk.StringVar()
        self.country_group_var = tk.StringVar()
        self.selectedpitch = tk.StringVar(value=pitch_values[0] if pitch_values else "0")
        self.selectednet = tk.StringVar(value=net_values[0] if net_values else "0")
        self.selectedpolice = tk.StringVar(value=self.police_labels.get("1", self.tr("dialog.police.english")))
        self.selectedstadium = tk.StringVar()
        self._preview_images: dict[str, ImageTk.PhotoImage] = {}
        self._preview_labels: dict[str, tk.Label] = {}
        self.stadium_source = exedir / "StadiumGBD"
        self.pitch_source = self._first_existing(exedir / "FSW" / "Images" / "PitchMowPattern", exedir / "FSW" / "PitchMowPattern")
        self.net_source = self._first_existing(exedir / "FSW" / "Images" / "Nets", exedir / "FSW" / "Nets")
        self.police_source = self._first_existing(exedir / "FSW" / "Images" / "Police", exedir / "FSW" / "Police")
        pitch_values = self._file_stems(self.pitch_source)
        net_values = self._file_stems(self.net_source)
        self.scope_labels = {key: self.tr(label_key) for key, label_key in STADIUM_SCOPE_OPTIONS}
        self.scope_ids = {self.tr(label_key): key for key, label_key in STADIUM_SCOPE_OPTIONS}
        self.police_labels = {key: self.tr(label_key) for key, label_key in POLICE_PATTERN_OPTIONS if self._has_preview(self.police_source, key)}
        if not self.police_labels:
            self.police_labels = {"1": self.tr("dialog.police.english")}
        self.police_ids = {label: key for key, label in self.police_labels.items()}
        self.scope = tk.StringVar(value=self.scope_labels.get(default_scope, self.tr(STADIUM_SCOPE_OPTIONS[0][1])))
        self.search_var = tk.StringVar()
        self.country_group_var = tk.StringVar()
        self.selectedpitch = tk.StringVar(value=pitch_values[0] if pitch_values else "0")
        self.selectednet = tk.StringVar(value=net_values[0] if net_values else "0")
        self.selectedpolice = tk.StringVar(value=next(iter(self.police_labels.values())))
        self.selectedstadium = tk.StringVar()
        self._preview_images: dict[str, ImageTk.PhotoImage] = {}
        self._preview_labels: dict[str, tk.Label] = {}
        self._preview_frames: dict[str, tk.Frame] = {}
        self._ui_ready = False
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
        right_body.grid_rowconfigure(2, weight=1)
        right_body.grid_rowconfigure(3, weight=1)
        right_body.grid_rowconfigure(4, weight=1)
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
        self._bind_mousewheel_target(right_canvas, right_body, scroll_callback=lambda steps: right_canvas.yview_scroll(steps, "units"))

        controls = tk.Frame(right_body, bg=self.card)
        controls.grid(row=0, column=0, sticky="ew")
        controls.grid_columnconfigure(0, weight=1)

        self._combo(controls, 0, "Pitch Mow Pattern", pitch_values, self.selectedpitch, self._on_pitch_changed)
        self._combo(controls, 2, "Net Pattern", net_values, self.selectednet, self._on_net_changed)
        self._dark_label(controls, "Police Pattern", muted=True, font=("Bahnschrift", 10), anchor="w").grid(row=4, column=0, sticky="w", pady=(12, 0))
        police_combo = ttk.Combobox(
            controls,
            state="readonly",
            textvariable=self.selectedpolice,
            values=tuple(label for _, label in POLICE_PATTERN_OPTIONS),
            style="Server16.TCombobox",
        )
        police_combo.grid(row=5, column=0, sticky="ew", pady=(6, 0))
        police_combo.bind("<<ComboboxSelected>>", self._on_police_changed)

        selected_card = tk.Frame(right_body, bg=self.card_soft, highlightthickness=1, highlightbackground="#243654")
        selected_card.grid(row=1, column=0, sticky="ew", pady=(14, 14))
        selected_card.grid_columnconfigure(0, weight=1)
        self._dark_label(selected_card, self.tr("dialog.stadium.current_selection"), bg=self.card_soft, muted=True, font=("Bahnschrift", 10)).grid(row=0, column=0, sticky="w", padx=12, pady=(10, 2))
        self.selection_value = self._dark_label(selected_card, "None", bg=self.card_soft, font=("Consolas", 11, "bold"), anchor="w", justify="left", wraplength=420)
        self.selection_value.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 10))

        stadium_preview_row = tk.Frame(right_body, bg=self.card)
        stadium_preview_row.grid(row=2, column=0, sticky="nsew", pady=(0, 12))
        stadium_preview_row.grid_columnconfigure(0, weight=1)
        self._preview_frames["stadium"] = stadium_preview_row
        self._build_preview(stadium_preview_row, 0, self.tr("dialog.stadium.preview.stadium"), "stadium", image_size=(520, 420), height=24)

        preview_top = tk.Frame(right_body, bg=self.card)
        preview_top.grid(row=3, column=0, sticky="nsew")
        preview_top.grid_columnconfigure(0, weight=1)
        preview_top.grid_columnconfigure(1, weight=1)
        pitch_wrap = tk.Frame(preview_top, bg=self.card)
        pitch_wrap.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        pitch_wrap.grid_columnconfigure(0, weight=1)
        self._combo(pitch_wrap, 0, self.tr("dialog.stadium.pitch_pattern"), pitch_values, self.selectedpitch, self._on_pitch_changed)
        self._build_preview(pitch_wrap, 0, self.tr("dialog.stadium.preview.pitch"), "pitch", image_size=(420, 360), height=22, row=2)

        net_wrap = tk.Frame(preview_top, bg=self.card)
        net_wrap.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        net_wrap.grid_columnconfigure(0, weight=1)
        self._combo(net_wrap, 0, self.tr("dialog.stadium.net_pattern"), net_values, self.selectednet, self._on_net_changed)
        self._build_preview(net_wrap, 0, self.tr("dialog.stadium.preview.net"), "net", image_size=(420, 360), height=22, row=2)

        preview_bottom = tk.Frame(right_body, bg=self.card)
        preview_bottom.grid(row=4, column=0, sticky="nsew", pady=(12, 0))
        preview_bottom.grid_columnconfigure(0, weight=1)
        self._combo(
            preview_bottom,
            0,
            self.tr("dialog.stadium.police_pattern"),
            [self.tr(label_key) for _, label_key in POLICE_PATTERN_OPTIONS],
            self.selectedpolice,
            self._on_police_changed,
        )
        self._build_preview(preview_bottom, 0, self.tr("dialog.stadium.preview.police"), "police", image_size=(520, 420), height=24, row=2)

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

    def _discover_stadium_names(self) -> list[str]:
        """Return stadium names from StadiumGBD folders and supported archives.

        Supports normal stadium folders plus .zip/.rar archives. File names are
        returned without extension so they match the assignment format expected
        by stadium_runtime.py. Duplicates are removed while preserving a clean
        sorted list.
        """
        if not self.stadium_source.exists():
            return []
        names: list[str] = []
        seen: set[str] = set()
        for item in sorted(self.stadium_source.iterdir(), key=lambda p: p.name.lower()):
            if item.is_dir():
                name = item.name
            elif item.is_file() and item.suffix.lower() in {".zip", ".rar"}:
                name = item.stem
            else:
                continue
            normalized = unicodedata.normalize("NFC", name).strip()
            if not normalized or normalized.lower() == "none":
                continue
            key = normalized.casefold()
            if key in seen:
                continue
            seen.add(key)
            names.append(normalized)
        return names

    def _has_preview(self, folder: Path, stem: str) -> bool:
        if not folder.exists():
            return False
        for suffix in (".png", ".jpg", ".jpeg"):
            if (folder / f"{stem}{suffix}").exists():
                return True
        return False

    def _file_stems(self, folder: Path) -> list[str]:
        if not folder.exists():
            return ["0"]
        values: list[str] = []
        seen: set[str] = set()
        for item in sorted(folder.iterdir(), key=lambda p: p.name.lower()):
            if not item.is_file() or item.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
                continue
            key = item.stem.casefold()
            if key in seen:
                continue
            seen.add(key)
            values.append(item.stem)
        return values or ["0"]

    def _country_code_for_stadium(self, stadium_name: str) -> str:
        stadium_name = (stadium_name or "").strip()
        if stadium_name == "None":
            return "Other"
        if " - " in stadium_name:
            code = stadium_name.split(" - ", 1)[0].strip().upper()
            if len(code) == 3 and code.isalpha():
                return code
        return "Other"

    @staticmethod
    def _normalize_text(value: str) -> str:
        normalized = unicodedata.normalize("NFKD", value or "")
        return "".join(char for char in normalized if not unicodedata.combining(char)).lower()

    def _build_country_group_values(self, stadium_names: list[str]) -> list[str]:
        counts: dict[str, int] = {}
        for name in stadium_names:
            if name == "None":
                continue
            code = self._country_code_for_stadium(name)
            counts[code] = counts.get(code, 0) + 1
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
        self._update_selection_summary()

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
        height: int = 13,
    ) -> None:
        frame = tk.Frame(parent, bg=self.card_soft, highlightthickness=1, highlightbackground="#243654")
        frame.grid(row=0, column=column, padx=(0 if column == 0 else 6, 0), sticky="nsew")
        self._dark_label(frame, title, bg=self.card_soft, muted=True, font=("Bahnschrift", 10)).pack(anchor="w", padx=10, pady=(10, 6))
        preview = tk.Label(
            frame,
            text=self.tr("placeholder.no_preview"),
            bg=self.panel,
            fg=self.muted,
            anchor="center",
            justify="center",
            relief="flat",
            width=31,
            height=height,
        )
        preview.pack(fill="both", expand=True, padx=10, pady=(0, 10), ipadx=12, ipady=16)
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
        preview_frame = self._preview_frames.get("stadium")
        if preview_frame is not None:
            if image_path is None:
                preview_frame.grid_remove()
            else:
                preview_frame.grid()
        fallback = stadium_name if stadium_name else self.tr("placeholder.no_stadium_preview")
        self._update_preview("stadium", image_path, fallback)

    def _preview_path_for_stem(self, folder: Path, stem: str) -> Path | None:
        for suffix in (".png", ".jpg", ".jpeg"):
            candidate = folder / f"{stem}{suffix}"
            if candidate.exists():
                return candidate
        return None

    def _on_pitch_changed(self, _event=None) -> None:
        image_path = self._preview_path_for_stem(self.pitch_source, self.selectedpitch.get())
        self._update_preview("pitch", image_path, self.tr("dialog.stadium.pitch_value", value=self.selectedpitch.get() or "-"))

    def _on_net_changed(self, _event=None) -> None:
        image_path = self._preview_path_for_stem(self.net_source, self.selectednet.get())
        self._update_preview("net", image_path, self.tr("dialog.stadium.net_value", value=self.selectednet.get() or "-"))

    def _on_police_changed(self, _event=None) -> None:
        police_id = self.police_ids.get(self.selectedpolice.get(), "1")
        image_path = self._preview_path_for_stem(self.police_source, police_id)
        self._update_preview("police", image_path, self.selectedpolice.get() or self.tr("dialog.stadium.police_pattern"))

    def _submit(self) -> None:
        selected = [self.stadiums.get(i) for i in self.stadiums.curselection()]
        selected = [name for name in selected if name and name != "None"] or ["None"]
        police_id = self.police_ids.get(self.selectedpolice.get(), "1")
        payload = {
            "selectedround": self.scope_ids.get(self.scope.get(), "0"),
            "Selectedstadium": selected[0] if selected else "None",
            "multistadium": selected,
            "selectedpitch": self.selectedpitch.get(),
            "selectednet": self.selectednet.get(),
            "selectedpolice": police_id,
        }
        self.close_ok(payload)


class ExcludeDialog(BaseDialog):
    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master, self.tr("dialog.assignment.title.exclude"))
        ttk.Button(self, text=self.tr("button.comp_id"), command=lambda: self.close_ok("COMP ID")).pack(fill="x", padx=12, pady=8)
        ttk.Button(self, text=self.tr("button.comp_round_id"), command=lambda: self.close_ok("COMP ROUND ID")).pack(fill="x", padx=12, pady=(0, 12))
