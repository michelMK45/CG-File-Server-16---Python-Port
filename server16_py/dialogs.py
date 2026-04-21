from __future__ import annotations

import tkinter as tk
import unicodedata
from pathlib import Path
from tkinter import ttk

from PIL import Image, ImageTk


SCOREBOARD_SCOPE_OPTIONS = (
    ("0", "EveryGame in The tournament"),
    ("1", "Specific round"),
    ("2", "Team scoreboard"),
)

MOVIE_SCOPE_OPTIONS = (
    ("0", "EveryGame in The tournament"),
    ("1", "Specific round"),
    ("2", "Derby matchers"),
    ("3", "Team movies"),
)

STADIUM_SCOPE_OPTIONS = (
    ("0", "Home Team"),
    ("1", "Specific Round"),
    ("2", "Multiple Home Team"),
    ("3", "Multiple Specific Round"),
    ("4", "Multiple Full Tournament"),
)

POLICE_PATTERN_OPTIONS = (
    ("1", "English"),
    ("2", "French"),
    ("3", "Italian"),
    ("4", "German"),
    ("6", "Mexican"),
    ("7", "Asiatic"),
    ("8", "African Traits"),
    ("9", "Caucasic Traits"),
    ("10", "Arabic Traits"),
)


class BaseDialog(tk.Toplevel):
    def __init__(self, master: tk.Misc, title: str) -> None:
        owner = master if isinstance(master, tk.Tk) else getattr(master, "ui_root", None) or master
        super().__init__(owner)
        self.app = master
        self.title(title)
        self.resizable(True, True)
        self.grab_set()
        self.result = None
        self._apply_theme(master)
        if hasattr(master, "configure_secondary_window"):
            master.configure_secondary_window(self)

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
        super().__init__(master, "TVLogo/ScoreBoard Assignment")
        self.scope_labels = {key: label for key, label in SCOREBOARD_SCOPE_OPTIONS}
        self.scope_ids = {label: key for key, label in SCOREBOARD_SCOPE_OPTIONS}
        self.scope = tk.StringVar(value=self.scope_labels.get("0", default_scope))
        self.tvlogo = tk.StringVar()
        self.scoreboard = tk.StringVar()
        ttk.Combobox(
            self,
            state="readonly",
            textvariable=self.scope,
            values=tuple(label for _, label in SCOREBOARD_SCOPE_OPTIONS),
            width=40,
            style="Server16.TCombobox",
        ).grid(
            row=0, column=0, columnspan=2, padx=12, pady=12, sticky="ew"
        )
        ttk.Label(self, text="TV Logos").grid(row=1, column=0, padx=12, sticky="w")
        ttk.Label(self, text="Scoreboards").grid(row=1, column=1, padx=12, sticky="w")
        self._build_listbox(2, 0, exedir / "TVLogoGBD", "default", self.tvlogo)
        self._build_listbox(2, 1, exedir / "ScoreBoardGBD", "default", self.scoreboard)
        ttk.Button(
            self,
            text="Select and Assign",
            command=lambda: self.close_ok(
                {
                    "selectedround": self.scope_ids.get(self.scope.get(), "0"),
                    "Selectedtvlogo": self.tvlogo.get(),
                    "Selectedscoreboard": self.scoreboard.get(),
                }
            ),
        ).grid(row=3, column=0, columnspan=2, padx=12, pady=12, sticky="ew")

    def _build_listbox(self, row: int, column: int, base: Path, default: str, target: tk.StringVar) -> None:
        listbox = self._dark_listbox(self, exportselection=False, width=28, height=16)
        listbox.grid(row=row, column=column, padx=12, pady=8)
        listbox.insert("end", default)
        if base.exists():
            for directory in sorted(p for p in base.iterdir() if p.is_dir()):
                listbox.insert("end", directory.name)
        listbox.selection_set(0)
        target.set(default)
        listbox.bind("<<ListboxSelect>>", lambda _event: target.set(listbox.get("active")))


class MovieDialog(BaseDialog):
    def __init__(self, master: tk.Misc, exedir: Path, default_scope: str = "0") -> None:
        super().__init__(master, "Movie Assignment")
        self.scope_labels = {key: label for key, label in MOVIE_SCOPE_OPTIONS}
        self.scope_ids = {label: key for key, label in MOVIE_SCOPE_OPTIONS}
        self.scope = tk.StringVar(value=self.scope_labels.get("0", default_scope))
        self.movie = tk.StringVar()
        ttk.Combobox(
            self,
            state="readonly",
            textvariable=self.scope,
            values=tuple(label for _, label in MOVIE_SCOPE_OPTIONS),
            width=32,
            style="Server16.TCombobox",
        ).pack(fill="x", padx=12, pady=12)
        listbox = self._dark_listbox(self, exportselection=False, width=36, height=16)
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
            text="Select and Assign",
            command=lambda: self.close_ok(
                {"selectedround": self.scope_ids.get(self.scope.get(), "0"), "Selectedmovie": self.movie.get()}
            ),
        ).pack(fill="x", padx=12, pady=12)


class StadiumDialog(BaseDialog):
    def __init__(self, master: tk.Misc, exedir: Path, default_scope: str = "0") -> None:
        super().__init__(master, "Stadium Assign")
        self.geometry("1180x760")
        self.minsize(1060, 700)
        pitch_values = self._file_stems(self._first_existing(exedir / "FSW" / "Images" / "PitchMowPattern", exedir / "FSW" / "PitchMowPattern"))
        net_values = self._file_stems(self._first_existing(exedir / "FSW" / "Images" / "Nets", exedir / "FSW" / "Nets"))
        self.scope_labels = {key: label for key, label in STADIUM_SCOPE_OPTIONS}
        self.scope_ids = {label: key for key, label in STADIUM_SCOPE_OPTIONS}
        self.police_labels = {key: label for key, label in POLICE_PATTERN_OPTIONS}
        self.police_ids = {label: key for key, label in POLICE_PATTERN_OPTIONS}
        self.scope = tk.StringVar(value=self.scope_labels.get(default_scope, STADIUM_SCOPE_OPTIONS[0][1]))
        self.search_var = tk.StringVar()
        self.country_group_var = tk.StringVar()
        self.selectedpitch = tk.StringVar(value=pitch_values[0] if pitch_values else "0")
        self.selectednet = tk.StringVar(value=net_values[0] if net_values else "0")
        self.selectedpolice = tk.StringVar(value=self.police_labels.get("1", "English"))
        self.selectedstadium = tk.StringVar()
        self._ui_ready = False
        self._preview_images: dict[str, ImageTk.PhotoImage] = {}
        self._preview_labels: dict[str, tk.Label] = {}
        self._preview_frames: dict[str, tk.Frame] = {}
        self.stadium_source = exedir / "StadiumGBD"
        self.pitch_source = self._first_existing(exedir / "FSW" / "Images" / "PitchMowPattern", exedir / "FSW" / "PitchMowPattern")
        self.net_source = self._first_existing(exedir / "FSW" / "Images" / "Nets", exedir / "FSW" / "Nets")
        self.police_source = self._first_existing(exedir / "FSW" / "Images" / "Police", exedir / "FSW" / "Police")
        self._all_stadiums = ["None"]
        self._country_group_labels = {"All Countries": "All Countries"}
        if self.stadium_source.exists():
            self._all_stadiums.extend(self._discover_stadium_names())
        self._country_group_values = self._build_country_group_values(self._all_stadiums)
        self.country_group_var.set(self._country_group_values[0] if self._country_group_values else "All Countries")
        self.grid_columnconfigure(0, weight=5)
        self.grid_columnconfigure(1, weight=4)
        self.grid_rowconfigure(1, weight=1)

        topbar = tk.Frame(self, bg=self.bg)
        topbar.grid(row=0, column=0, columnspan=2, sticky="ew", padx=14, pady=(14, 10))
        topbar.grid_columnconfigure(0, weight=1)
        self._dark_label(topbar, "STADIUM ASSIGN", bg=self.bg, font=("Bahnschrift", 18, "bold")).grid(row=0, column=0, sticky="w")
        self._dark_label(
            topbar,
            "Choose the scope, select one or more stadiums, and review separate previews for pitch, net, and police.",
            bg=self.bg,
            muted=True,
            font=("Bahnschrift", 10),
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))

        left_card = self._card(self, "Assignment Scope", "Scope and list of stages for the assignment.")
        left_card.grid(row=1, column=0, sticky="nsew", padx=(14, 8), pady=(0, 14))
        left_card.pack_propagate(False)

        right_card = self._card(self, "Visual Details", "Settings and visual previews of what will be applied.")
        right_card.grid(row=1, column=1, sticky="nsew", padx=(8, 14), pady=(0, 14))
        right_card.pack_propagate(False)

        left_body = tk.Frame(left_card, bg=self.card)
        left_body.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        left_body.grid_columnconfigure(0, weight=1)
        left_body.grid_rowconfigure(7, weight=1)

        self._dark_label(left_body, "Assignment Mode", muted=True, font=("Bahnschrift", 10), anchor="w").grid(row=0, column=0, sticky="w")
        scope_combo = ttk.Combobox(
            left_body,
            state="readonly",
            textvariable=self.scope,
            values=tuple(label for _, label in STADIUM_SCOPE_OPTIONS),
            style="Server16.TCombobox",
        )
        scope_combo.grid(row=1, column=0, sticky="ew", pady=(6, 12))

        self.selection_hint = self._dark_label(left_body, "Single selection", muted=True, font=("Bahnschrift", 10), anchor="w")
        self.selection_hint.grid(row=2, column=0, sticky="w", pady=(0, 8))

        self._dark_label(left_body, "Search Stadium", muted=True, font=("Bahnschrift", 10), anchor="w").grid(row=3, column=0, sticky="w")
        search_entry = ttk.Entry(left_body, textvariable=self.search_var, style="Server16.TEntry")
        search_entry.grid(row=4, column=0, sticky="ew", pady=(6, 10))
        search_entry.bind("<KeyRelease>", self._on_search_changed)
        search_entry.bind("<Return>", self._on_search_changed)

        self._dark_label(left_body, "Country Group", muted=True, font=("Bahnschrift", 10), anchor="w").grid(row=5, column=0, sticky="w")
        self.country_group_combo = ttk.Combobox(
            left_body,
            state="readonly",
            textvariable=self.country_group_var,
            values=self._country_group_values,
            style="Server16.TCombobox",
        )
        self.country_group_combo.grid(row=6, column=0, sticky="ew", pady=(6, 10))

        stadium_list_wrap = tk.Frame(left_body, bg=self.card)
        stadium_list_wrap.grid(row=7, column=0, sticky="nsew")
        stadium_list_wrap.grid_columnconfigure(0, weight=1)
        stadium_list_wrap.grid_rowconfigure(0, weight=1)

        self.stadiums = self._dark_listbox(stadium_list_wrap, exportselection=False, height=22, selectmode="browse", font=("Consolas", 10))
        stadium_scroll = ttk.Scrollbar(
            stadium_list_wrap,
            orient="vertical",
            command=self.stadiums.yview,
            style="Server16.Vertical.TScrollbar",
        )
        self.stadiums.configure(yscrollcommand=stadium_scroll.set)
        self.stadiums.grid(row=0, column=0, sticky="nsew")
        stadium_scroll.grid(row=0, column=1, sticky="ns", padx=(8, 0))
        self._refresh_stadium_list()
        self.stadiums.bind("<<ListboxSelect>>", lambda _event: self._refresh_selection())
        self.stadiums.bind("<ButtonRelease-1>", lambda _event: self._refresh_selection())
        self.stadiums.bind("<KeyRelease-Up>", lambda _event: self._refresh_selection())
        self.stadiums.bind("<KeyRelease-Down>", lambda _event: self._refresh_selection())
        self.scope.trace_add("write", lambda *_args: self._update_mode())
        self.search_var.trace_add("write", lambda *_args: self._refresh_stadium_list())
        self.country_group_combo.bind("<<ComboboxSelected>>", self._on_country_group_changed)

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
        self._bind_mousewheel_target(right_canvas, right_body, scroll_callback=lambda steps: right_canvas.yview_scroll(steps, "units"))

        selected_card = tk.Frame(right_body, bg=self.card_soft, highlightthickness=1, highlightbackground="#243654")
        selected_card.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        selected_card.grid_columnconfigure(0, weight=1)
        self._dark_label(selected_card, "Current Selection", bg=self.card_soft, muted=True, font=("Bahnschrift", 10)).grid(row=0, column=0, sticky="w", padx=12, pady=(10, 2))
        self.selection_value = self._dark_label(selected_card, "None", bg=self.card_soft, font=("Consolas", 11, "bold"), anchor="w", justify="left", wraplength=420)
        self.selection_value.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 10))

        stadium_preview_row = tk.Frame(right_body, bg=self.card)
        stadium_preview_row.grid(row=1, column=0, sticky="nsew", pady=(0, 12))
        stadium_preview_row.grid_columnconfigure(0, weight=1)
        self._preview_frames["stadium"] = stadium_preview_row
        self._build_preview(stadium_preview_row, 0, "Stadium Preview", "stadium", image_size=(520, 420), height=24)

        preview_top = tk.Frame(right_body, bg=self.card)
        preview_top.grid(row=2, column=0, sticky="nsew")
        preview_top.grid_columnconfigure(0, weight=1)
        preview_top.grid_columnconfigure(1, weight=1)
        pitch_wrap = tk.Frame(preview_top, bg=self.card)
        pitch_wrap.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        pitch_wrap.grid_columnconfigure(0, weight=1)
        self._combo(pitch_wrap, 0, "Pitch Mow Pattern", pitch_values, self.selectedpitch, self._on_pitch_changed)
        self._build_preview(pitch_wrap, 0, "Pitch Preview", "pitch", image_size=(420, 360), height=22, row=2)

        net_wrap = tk.Frame(preview_top, bg=self.card)
        net_wrap.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        net_wrap.grid_columnconfigure(0, weight=1)
        self._combo(net_wrap, 0, "Net Pattern", net_values, self.selectednet, self._on_net_changed)
        self._build_preview(net_wrap, 0, "Net Preview", "net", image_size=(420, 360), height=22, row=2)

        preview_bottom = tk.Frame(right_body, bg=self.card)
        preview_bottom.grid(row=3, column=0, sticky="nsew", pady=(12, 0))
        preview_bottom.grid_columnconfigure(0, weight=1)
        self._combo(
            preview_bottom,
            0,
            "Police Pattern",
            [label for _, label in POLICE_PATTERN_OPTIONS],
            self.selectedpolice,
            self._on_police_changed,
        )
        self._build_preview(preview_bottom, 0, "Police Preview", "police", image_size=(520, 420), height=24, row=2)

        action_bar = tk.Frame(self, bg=self.bg)
        action_bar.grid(row=2, column=0, columnspan=2, sticky="ew", padx=14, pady=(0, 14))
        action_bar.grid_columnconfigure(0, weight=1)
        ttk.Button(action_bar, text="Select and Assign", command=self._submit).grid(row=0, column=0, sticky="ew")
        self._ui_ready = True
        self._update_mode()
        self._refresh_stadium_list()
        self._refresh_selection()
        self._update_stadium_preview()
        self._on_pitch_changed()
        self._on_net_changed()
        self._on_police_changed()

    def _discover_stadium_names(self) -> list[str]:
        discovered: dict[str, Path] = {}
        for item in sorted(self.stadium_source.iterdir(), key=lambda path: (not path.is_dir(), path.name.lower())):
            if item.is_dir():
                discovered.setdefault(item.name, item)
                continue
            if item.is_file() and item.suffix.lower() == ".rar":
                stem = item.stem.strip()
                if stem:
                    discovered.setdefault(stem, item)
        return sorted(discovered, key=str.casefold)

    def _combo(self, parent: tk.Misc, row: int, label: str, values: list[str], variable: tk.StringVar, callback=None) -> None:
        self._dark_label(parent, label, muted=True, font=("Bahnschrift", 10), anchor="w").grid(row=row, column=0, sticky="w", pady=(0 if row == 0 else 12, 0))
        combo = ttk.Combobox(parent, state="readonly", textvariable=variable, values=values or ["0"], style="Server16.TCombobox")
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

    def _file_stems(self, folder: Path) -> list[str]:
        if not folder.exists():
            return ["0"]
        return [item.stem for item in sorted(folder.iterdir()) if item.is_file()]

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
        values = [f"All Countries ({sum(counts.values())})"]
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
        if not hasattr(self, "stadiums") or not hasattr(self, "selection_hint"):
            return
        scope_id = self.scope_ids.get(self.scope.get(), "0")
        mode = "extended" if scope_id in {"2", "3", "4"} else "browse"
        self.stadiums.configure(selectmode=mode)
        self.selection_hint.configure(
            text="Multiple selection enabled" if mode == "extended" else "Single selection"
        )
        self._update_selection_summary()

    def _refresh_selection(self) -> None:
        if not self._ui_ready:
            return
        selected = self._selected_stadium_names()
        scope_id = self.scope_ids.get(self.scope.get(), "0")
        if selected and scope_id not in {"2", "3", "4"}:
            self.selectedstadium.set(selected[0])
        self._update_selection_summary()
        self._update_stadium_preview()

    def _update_selection_summary(self) -> None:
        if not self._ui_ready or not hasattr(self, "selection_value"):
            return
        selected = self._selected_stadium_names()
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
        stadium_name = (stadium_name or "").strip()
        if not stadium_name or stadium_name == "None":
            return None
        preview_dir = self.stadium_source / "render" / "thumbnail" / "stadium"
        if not preview_dir.exists():
            return None
        for candidate in sorted(preview_dir.iterdir()):
            if not candidate.is_file():
                continue
            if candidate.suffix.lower() not in {".png", ".jpg", ".jpeg", ".jepg"}:
                continue
            if candidate.stem.casefold() == stadium_name.casefold():
                return candidate
        return None

    def _build_preview(
        self,
        parent: tk.Misc,
        column: int,
        title: str,
        key: str,
        image_size: tuple[int, int] = (280, 220),
        height: int = 13,
        row: int = 0,
    ) -> None:
        frame = tk.Frame(parent, bg=self.card_soft, highlightthickness=1, highlightbackground="#243654")
        frame.grid(row=row, column=column, padx=(0 if column == 0 else 6, 0), sticky="nsew", pady=(12 if row > 0 else 0, 0))
        self._dark_label(frame, title, bg=self.card_soft, muted=True, font=("Bahnschrift", 10)).pack(anchor="w", padx=10, pady=(10, 6))
        preview = tk.Label(
            frame,
            text="No preview",
            bg=self.panel,
            fg=self.muted,
            anchor="center",
            justify="center",
            relief="flat",
            width=31,
            height=height,
        )
        preview.pack(fill="both", expand=True, padx=8, pady=(0, 8), ipadx=8, ipady=24)
        preview.image_size = image_size
        self._preview_labels[key] = preview

    def _update_preview(self, key: str, image_path: Path | None, fallback_text: str) -> None:
        if key not in self._preview_labels:
            return
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
        if not self._ui_ready:
            return
        selected = self._selected_stadium_names()
        stadium_name = next((name for name in selected if name and name != "None"), "")
        image_path = self._resolve_stadium_preview_path(stadium_name)
        preview_frame = self._preview_frames.get("stadium")
        if preview_frame is not None:
            if image_path is None:
                preview_frame.grid_remove()
            else:
                preview_frame.grid()
        fallback = stadium_name if stadium_name else "No stadium preview"
        self._update_preview("stadium", image_path, fallback)

    def _on_pitch_changed(self, _event=None) -> None:
        image_path = self.pitch_source / f"{self.selectedpitch.get()}.png"
        self._update_preview("pitch", image_path, f"Pitch {self.selectedpitch.get() or '-'}")

    def _on_net_changed(self, _event=None) -> None:
        image_path = self.net_source / f"{self.selectednet.get()}.png"
        self._update_preview("net", image_path, f"Net {self.selectednet.get() or '-'}")

    def _on_police_changed(self, _event=None) -> None:
        police_id = self.police_ids.get(self.selectedpolice.get(), "1")
        image_path = self.police_source / f"{police_id}.png"
        self._update_preview("police", image_path, self.selectedpolice.get() or "Police")

    def _submit(self) -> None:
        selected = self._selected_stadium_names()
        police_id = self.police_ids.get(self.selectedpolice.get(), "1")
        payload = {
            "selectedround": self.scope_ids.get(self.scope.get(), "0"),
            "Selectedstadium": selected[0] if selected else "",
            "multistadium": selected,
            "selectedpitch": self.selectedpitch.get(),
            "selectednet": self.selectednet.get(),
            "selectedpolice": police_id,
        }
        self.close_ok(payload)


class ExcludeDialog(BaseDialog):
    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master, "Exclude Competition")
        ttk.Button(self, text="COMP ID", command=lambda: self.close_ok("COMP ID")).pack(fill="x", padx=12, pady=8)
        ttk.Button(self, text="COMP ROUND ID", command=lambda: self.close_ok("COMP ROUND ID")).pack(fill="x", padx=12, pady=(0, 12))
