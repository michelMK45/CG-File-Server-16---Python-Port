from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import unicodedata
import tkinter as tk
from tkinter import messagebox, ttk


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
        owner = app if isinstance(app, tk.Tk) else getattr(app, "ui_root", None) or app
        super().__init__(owner)
        self.app = app
        self.specs = specs
        self.configure(bg=app.bg)
        self.title(title)
        self.geometry("1120x700")
        self.minsize(1000, 640)
        if hasattr(app, "configure_secondary_window"):
            app.configure_secondary_window(self)
        self.notebook = ttk.Notebook(self, style="Server16.TNotebook")
        self.notebook.pack(fill="both", expand=True, padx=10, pady=10)
        self.frames: dict[str, SettingsSectionFrame] = {}
        for spec in specs:
            frame = SettingsSectionFrame(self.notebook, app, spec)
            self.notebook.add(frame, text=spec.title)
            self.frames[spec.section.lower()] = frame
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)
        if initial_section:
            for index, spec in enumerate(specs):
                if spec.section.lower() == initial_section.lower():
                    self.notebook.select(index)
                    break
        self._refresh_active_frame()

    def _on_tab_changed(self, _event=None) -> None:
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
        "default": "0.30",
        "winning": "0.35",
        "lose1": "0.25",
        "lose2": "0.30",
        "lose3": "0.30",
        "clubsong": "0.18",
    }

    def __init__(self, parent: tk.Misc, app, spec: SectionSpec) -> None:
        super().__init__(parent, bg=app.bg)
        self.app = app
        self.spec = spec
        self.selected_key: str | None = None
        self._refresh_job = None
        self._display_keys: list[str] = []
        self._setup_ui()
        self.bind("<Destroy>", self._on_destroy)

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
            text=f"Arquivo ativo: {self.app.settings_ini.path}",
            bg=self.app.bg,
            fg=self.app.muted,
            font=("Bahnschrift", 9),
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))
        ttk.Button(header, text="Refresh", command=self.reload_entries).grid(row=0, column=1, rowspan=2, sticky="e")

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
        ttk.Button(left_top, text="New", command=self.new_entry).grid(row=0, column=1)

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
        self.entries_list.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 8))
        self.entries_list.bind("<<ListboxSelect>>", self._on_entry_selected)

        self.count_label = tk.Label(left_card, text="0 entries", bg=self.app.card, fg=self.app.muted, font=("Bahnschrift", 9))
        self.count_label.grid(row=2, column=0, sticky="w", padx=12, pady=(0, 10))

        right_card = tk.Frame(self, bg=self.app.card, highlightthickness=1, highlightbackground="#243654")
        right_card.grid(row=1, column=1, sticky="nsew", padx=(6, 12), pady=(0, 12))
        right_card.grid_rowconfigure(2, weight=1)
        right_card.grid_columnconfigure(0, weight=1)

        form = tk.Frame(right_card, bg=self.app.card)
        form.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 8))
        form.grid_columnconfigure(1, weight=1)

        tk.Label(form, text="Key", bg=self.app.card, fg=self.app.muted, font=("Bahnschrift", 10)).grid(row=0, column=0, sticky="w", pady=(0, 6))
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

        self.body = tk.Frame(right_card, bg=self.app.card)
        self.body.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 8))
        self.body.grid_columnconfigure(0, weight=1)

        self._build_editor_body()

        actions = tk.Frame(right_card, bg=self.app.card)
        actions.grid(row=3, column=0, sticky="ew", padx=12, pady=(0, 12))
        actions.grid_columnconfigure(0, weight=1)
        ttk.Button(actions, text="Save To settings.ini", command=self.save_entry).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ttk.Button(actions, text="Delete Entry", command=self.delete_entry).grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(actions, text="Apply Runtime", command=self._apply_runtime).grid(row=0, column=2, sticky="ew", padx=(6, 0))

        self.status_var = tk.StringVar(value="Selecione ou crie um item para editar.")
        tk.Label(
            right_card,
            textvariable=self.status_var,
            bg=self.app.card,
            fg=self.app.muted,
            font=("Bahnschrift", 9),
            anchor="w",
            justify="left",
        ).grid(row=4, column=0, sticky="ew", padx=12, pady=(0, 12))

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
        self.stadium_list.grid(row=0, column=0, columnspan=2, sticky="nsew", pady=(0, 10))
        for entry in self._available_choices():
            self.stadium_list.insert("end", entry)
        self.police_var = tk.StringVar(value=self.STADIUM_DEFAULTS["police"])
        self.pitch_var = tk.StringVar(value=self.STADIUM_DEFAULTS["pitch"])
        self.net_var = tk.StringVar(value=self.STADIUM_DEFAULTS["net"])
        self._add_combo_row(self.body, 1, "Police", self.police_var, [str(i) for i in range(1, 11)])
        self._add_combo_row(self.body, 2, "Pitch", self.pitch_var, self._file_stems(self.app.PitchMowsource))
        self._add_combo_row(self.body, 3, "Net", self.net_var, self._file_stems(self.app.Nsource))

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
        self.active_var = tk.StringVar(value=self.STADIUM_NAME_DEFAULTS["active"])
        self._add_entry_row(self.body, 0, "Displayed Name", self.display_name_var)
        self._add_combo_row(self.body, 1, "Active", self.active_var, ["0", "1"])

    def _build_chants_editor(self) -> None:
        self.chants_folder_var = tk.StringVar(value=self.CHANTS_DEFAULTS["folder"])
        self.default_var = tk.StringVar(value=self.CHANTS_DEFAULTS["default"])
        self.winning_var = tk.StringVar(value=self.CHANTS_DEFAULTS["winning"])
        self.lose1_var = tk.StringVar(value=self.CHANTS_DEFAULTS["lose1"])
        self.lose2_var = tk.StringVar(value=self.CHANTS_DEFAULTS["lose2"])
        self.lose3_var = tk.StringVar(value=self.CHANTS_DEFAULTS["lose3"])
        self.clubsong_var = tk.StringVar(value=self.CHANTS_DEFAULTS["clubsong"])
        self._add_combo_row(self.body, 0, "Chants Folder", self.chants_folder_var, self._available_choices())
        self._add_entry_row(self.body, 1, "Default", self.default_var)
        self._add_entry_row(self.body, 2, "Winning", self.winning_var)
        self._add_entry_row(self.body, 3, "Lose 1", self.lose1_var)
        self._add_entry_row(self.body, 4, "Lose 2", self.lose2_var)
        self._add_entry_row(self.body, 5, "Lose 3", self.lose3_var)
        self._add_entry_row(self.body, 6, "Club Song", self.clubsong_var)

    @staticmethod
    def _normalize_text(value: str) -> str:
        normalized = unicodedata.normalize("NFKD", value or "")
        return "".join(char for char in normalized if not unicodedata.combining(char)).lower()

    def _add_entry_row(self, parent: tk.Misc, row: int, label: str, variable: tk.StringVar, readonly: bool = False):
        tk.Label(parent, text=label, bg=self.app.card, fg=self.app.muted, font=("Bahnschrift", 10)).grid(row=row, column=0, sticky="w", pady=4, padx=(0, 10))
        entry = tk.Entry(
            parent,
            textvariable=variable,
            bg=self.app.panel_alt,
            fg=self.app.fg,
            insertbackground=self.app.fg,
            relief="flat",
            font=("Consolas", 11),
        )
        if readonly:
            entry.configure(state="readonly")
        entry.grid(row=row, column=1, sticky="ew", pady=4)
        parent.grid_columnconfigure(1, weight=1)
        return entry

    def _add_combo_row(self, parent: tk.Misc, row: int, label: str, variable: tk.StringVar, values: list[str]):
        tk.Label(parent, text=label, bg=self.app.card, fg=self.app.muted, font=("Bahnschrift", 10)).grid(row=row, column=0, sticky="w", pady=4, padx=(0, 10))
        combo = ttk.Combobox(parent, textvariable=variable, values=values, font=("Consolas", 10))
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
        return sorted(path.name for path in base.iterdir() if path.is_dir())

    def _file_stems(self, folder: Path) -> list[str]:
        if not folder.exists():
            return ["0"]
        values = [item.stem for item in sorted(folder.iterdir()) if item.is_file()]
        return values or ["0"]

    def _on_entry_selected(self, _event=None) -> None:
        selection = self.entries_list.curselection()
        if not selection:
            return
        key = self._display_keys[selection[0]]
        self.load_entry(key)

    def reload_entries(self, preserve: bool = True) -> None:
        current_selection = self.selected_key if preserve else None
        self.app.settings_ini.reload()
        items = self.app.settings_ini.items(self.spec.section)
        query = self._normalize_text(self.search_var.get().strip())
        if query:
            items = [
                (key, value)
                for key, value in items
                if query in self._normalize_text(key) or query in self._normalize_text(value)
            ]
        self.entries_list.delete(0, "end")
        self._display_keys = []
        for key, value in items:
            preview = value if len(value) <= 58 else value[:55] + "..."
            self.entries_list.insert("end", f"{key}  ->  {preview}")
            self._display_keys.append(key)
        self.count_label.configure(text=f"{len(items)} entries")
        if current_selection:
            for index, (key, _value) in enumerate(items):
                if key == current_selection:
                    self.entries_list.selection_clear(0, "end")
                    self.entries_list.selection_set(index)
                    self.entries_list.activate(index)
                    break
        self._schedule_refresh()

    def _schedule_refresh(self) -> None:
        if self._refresh_job is not None:
            try:
                self.after_cancel(self._refresh_job)
            except Exception:
                pass
        self._refresh_job = self.after(1500, self.reload_entries)

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
        elif self.spec.kind == "net":
            self.down_var.set(self.NET_DEFAULTS["down"])
            self.high_var.set(self.NET_DEFAULTS["high"])
            self.rig_var.set(self.NET_DEFAULTS["rig"])
            self.shape_var.set(self.NET_DEFAULTS["shape"])
        elif self.spec.kind == "scoreboardstdname":
            self.display_name_var.set("")
            self.active_var.set(self.STADIUM_NAME_DEFAULTS["active"])
        elif self.spec.kind == "chants":
            choices = self._available_choices()
            self.chants_folder_var.set(choices[0] if choices else self.CHANTS_DEFAULTS["folder"])
            self.default_var.set(self.CHANTS_DEFAULTS["default"])
            self.winning_var.set(self.CHANTS_DEFAULTS["winning"])
            self.lose1_var.set(self.CHANTS_DEFAULTS["lose1"])
            self.lose2_var.set(self.CHANTS_DEFAULTS["lose2"])
            self.lose3_var.set(self.CHANTS_DEFAULTS["lose3"])
            self.clubsong_var.set(self.CHANTS_DEFAULTS["clubsong"])
        elif self.spec.kind == "exclude":
            self.exclude_var.set("excluded from stadium server")
        self.status_var.set("Novo item pronto. Salvar grava imediatamente no settings.ini.")

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
        self.status_var.set(f"Editando [{self.spec.section}] {key}")

    def _load_stadium_value(self, value: str) -> None:
        self.stadium_list.selection_clear(0, "end")
        if not value or value == "None":
            self.police_var.set(self.STADIUM_DEFAULTS["police"])
            self.pitch_var.set(self.STADIUM_DEFAULTS["pitch"])
            self.net_var.set(self.STADIUM_DEFAULTS["net"])
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

    def _load_net_value(self, value: str) -> None:
        parts = [part.strip() for part in value.split(",")]
        while len(parts) < 4:
            parts.append("")
        self.down_var.set(parts[0] or self.NET_DEFAULTS["down"])
        self.high_var.set(parts[1] or self.NET_DEFAULTS["high"])
        self.rig_var.set(parts[2] or self.NET_DEFAULTS["rig"])
        self.shape_var.set(parts[3] or self.NET_DEFAULTS["shape"])

    def _load_scoreboard_name_value(self, key: str, value: str) -> None:
        if "," in value:
            display_name, active = value.rsplit(",", 1)
        else:
            display_name, active = value or key, self.STADIUM_NAME_DEFAULTS["active"]
        self.display_name_var.set(display_name)
        self.active_var.set(active or self.STADIUM_NAME_DEFAULTS["active"])

    def _load_chants_value(self, value: str) -> None:
        parts = [part.strip() for part in value.split(",")]
        while len(parts) < 7:
            parts.append("")
        self.chants_folder_var.set(parts[0] or self.CHANTS_DEFAULTS["folder"])
        self.default_var.set(parts[1] or self.CHANTS_DEFAULTS["default"])
        self.winning_var.set(parts[2] or self.CHANTS_DEFAULTS["winning"])
        self.lose1_var.set(parts[3] or self.CHANTS_DEFAULTS["lose1"])
        self.lose2_var.set(parts[4] or self.CHANTS_DEFAULTS["lose2"])
        self.lose3_var.set(parts[5] or self.CHANTS_DEFAULTS["lose3"])
        self.clubsong_var.set(parts[6] or self.CHANTS_DEFAULTS["clubsong"])

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
            display_name = self.display_name_var.get().strip() or self.key_var.get().strip()
            return f"{display_name},{self.active_var.get().strip() or '1'}"
        if self.spec.kind == "chants":
            return ",".join(
                [
                    self.chants_folder_var.get().strip(),
                    self.default_var.get().strip(),
                    self.winning_var.get().strip(),
                    self.lose1_var.get().strip(),
                    self.lose2_var.get().strip(),
                    self.lose3_var.get().strip(),
                    self.clubsong_var.get().strip(),
                ]
            )
        if self.spec.kind == "exclude":
            return self.exclude_var.get().strip() or "excluded from stadium server"
        return ""

    def save_entry(self) -> None:
        key = self.key_var.get().strip()
        if not key:
            messagebox.showwarning("Settings", "Informe a chave da entrada.")
            return
        if self.spec.section.lower() == "modules":
            messagebox.showwarning("Settings", "A seção Modules está bloqueada nesta interface.")
            return
        value = self._compose_value()
        if not value:
            messagebox.showwarning("Settings", "Informe um valor válido para salvar.")
            return
        original_key = self.selected_key
        if original_key and original_key != key:
            self.app.settings_ini.delete_key(original_key, self.spec.section)
        self.app.settings_ini.write(key, value, self.spec.section)
        self.app.settings_ini.save()
        self.selected_key = key
        self.status_var.set(f"[{self.spec.section}] {key} salvo em tempo real.")
        self.reload_entries()
        self._apply_runtime()

    def delete_entry(self) -> None:
        key = self.key_var.get().strip() or self.selected_key
        if not key:
            return
        if not messagebox.askyesno("Settings", f"Remover [{self.spec.section}] {key}?"):
            return
        self.app.settings_ini.delete_key(key, self.spec.section)
        self.app.settings_ini.save()
        self.status_var.set(f"[{self.spec.section}] {key} removido.")
        self.new_entry()
        self.reload_entries(preserve=False)
        self._apply_runtime()

    def _apply_runtime(self) -> None:
        try:
            self.app.refresh_modules()
            self.app.apply_all_runtime()
            self.status_var.set(self.status_var.get() + " Runtime atualizado.")
        except Exception as exc:
            self.app.log("Failed to apply runtime after settings edit", exc)


def stadium_specs() -> list[SectionSpec]:
    return [
        SectionSpec("stadium", "Team Stadiums", kind="stadium", directory="StadiumGBD"),
        SectionSpec("comp", "Competition Stadiums", kind="stadium", directory="StadiumGBD"),
        SectionSpec("stadiumnetname", "Net By Stadium Name", kind="net", directory="StadiumGBD"),
        SectionSpec("stadiumnetid", "Net By Stadium ID", kind="net"),
        SectionSpec("scoreboardstdname", "Scoreboard Stadium Name", kind="scoreboardstdname", directory="StadiumGBD"),
        SectionSpec("exclude", "Excluded Competitions", kind="exclude"),
    ]


def asset_specs() -> list[SectionSpec]:
    return [
        SectionSpec("Scoreboard", "Competition Scoreboards", kind="simple", directory="ScoreBoardGBD"),
        SectionSpec("TVLogo", "Competition TV Logos", kind="simple", directory="TVLogoGBD"),
        SectionSpec("HomeTeamScoreBoard", "Home Team Scoreboards", kind="simple", directory="ScoreBoardGBD"),
        SectionSpec("HomeTeamTvLogo", "Home Team TV Logos", kind="simple", directory="TVLogoGBD"),
        SectionSpec("movies", "Competition Movies", kind="simple", directory="MoviesGBD"),
        SectionSpec("TeamMovies", "Team Movies", kind="simple", directory="MoviesGBD"),
        SectionSpec("DerbyMatch", "Derby Movies", kind="simple", directory="MoviesGBD"),
    ]


def audio_specs() -> list[SectionSpec]:
    return [
        SectionSpec("chantsid", "Chants IDs", kind="chants", directory="FSW\\Chants", recursive=True),
    ]
