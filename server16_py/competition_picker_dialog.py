from __future__ import annotations

import queue
import threading
import tkinter as tk
import unicodedata
from collections.abc import Callable
from pathlib import Path
from tkinter import ttk

from .competition_db import CompetitionData, CompetitionLoad, load_competitions, read_names
from .dialogs import BaseDialog

NameLoader = Callable[[Path, CompetitionData], "tuple[dict[str, str], dict[str, str]] | None"]


class CompetitionPickerDialog(BaseDialog):
    """Competition browser for the settings-editor "Key" fields keyed by a
    round id and/or a tournament id (`SectionSpec.key_is_round_id` /
    `key_is_tournament_id`, via `settings_editor.py`'s `_pick_competition_key`).

    Lists the competitions of the game's `compobj.txt` (see `competition_db.py`)
    with their stages underneath; a competition row yields its TOUR id (the
    tournament key), a stage row its ROUND id. A section that only accepts one
    of the two can only pick that kind. Returns the chosen id (str) via
    `self.result` -- same `close_ok(...)` modal convention as TeamPickerDialog/
    StadiumPickerDialog:

        dlg = CompetitionPickerDialog(app, exedir, allow_round=True, allow_tournament=True)
        app.wait_window(dlg)
        if dlg.result:
            ...  # dlg.result is the id string
    """

    NAME_POLL_MS = 120

    def __init__(
        self,
        master: tk.Misc,
        exedir: str | Path,
        *,
        allow_round: bool = True,
        allow_tournament: bool = True,
        name_loader: NameLoader | None = read_names,
    ) -> None:
        super().__init__(master, "dialog.competition_picker.title")
        self._set_geometry(920, 700, 760, 560)

        self._exedir = Path(exedir)
        self._allow_round = allow_round
        self._allow_tournament = allow_tournament
        self._load: CompetitionLoad = load_competitions(self._exedir)
        self._data: CompetitionData | None = self._load.data
        self._names_queue: queue.Queue = queue.Queue()
        self._names_loading = False
        self._selected: tuple[str, str] | None = None  # (kind "tour"|"round", id)

        self._conf_ids: list[int | None] = [None]
        self._nation_ids: list[int | None | str] = [None]  # None = all, "-" = no country, int = nation id

        self.grid_columnconfigure(0, weight=3)
        self.grid_columnconfigure(1, weight=2)
        self.grid_rowconfigure(1, weight=1)

        topbar = tk.Frame(self, bg=self.bg)
        topbar.grid(row=0, column=0, columnspan=2, sticky="ew", padx=14, pady=(14, 10))
        topbar.grid_columnconfigure(0, weight=1)
        self._dark_label(topbar, self.tr("dialog.competition_picker.title"), bg=self.bg, font=("Bahnschrift", 18, "bold")).grid(row=0, column=0, sticky="w")
        self.status_label = self._dark_label(topbar, "", bg=self.bg, muted=True, font=("Bahnschrift", 10), anchor="w", justify="left", wraplength=840)
        self.status_label.grid(row=1, column=0, sticky="w", pady=(2, 0))

        list_card = self._card(self, self.tr("dialog.competition_picker.competitions"))
        list_card.grid(row=1, column=0, sticky="nsew", padx=(14, 6), pady=(0, 14))
        details_card = self._card(self, self.tr("dialog.competition_picker.details"))
        details_card.grid(row=1, column=1, sticky="nsew", padx=(6, 14), pady=(0, 14))

        # --- Filters + tree (left) ---
        list_body = tk.Frame(list_card, bg=self.card)
        list_body.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        list_body.grid_columnconfigure(0, weight=1)
        list_body.grid_columnconfigure(1, weight=1)
        list_body.grid_rowconfigure(4, weight=1)

        self._dark_label(list_body, self.tr("dialog.competition_picker.confederation"), muted=True, font=("Bahnschrift", 10), anchor="w").grid(row=0, column=0, sticky="w")
        self._dark_label(list_body, self.tr("dialog.competition_picker.country"), muted=True, font=("Bahnschrift", 10), anchor="w").grid(row=0, column=1, sticky="w", padx=(8, 0))
        self.conf_combo = ttk.Combobox(list_body, state="readonly", font=("Consolas", 10), style="Server16.TCombobox")
        self.conf_combo.grid(row=1, column=0, sticky="ew", pady=(4, 8))
        self.nation_combo = ttk.Combobox(list_body, state="readonly", font=("Consolas", 10), style="Server16.TCombobox")
        self.nation_combo.grid(row=1, column=1, sticky="ew", pady=(4, 8), padx=(8, 0))
        self.conf_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_conf_change())
        self.nation_combo.bind("<<ComboboxSelected>>", lambda _e: self._refresh_tree())

        self._dark_label(list_body, self.tr("dialog.competition_picker.search"), muted=True, font=("Bahnschrift", 10), anchor="w").grid(row=2, column=0, columnspan=2, sticky="w")
        self.search_var = tk.StringVar()
        search_entry = ttk.Entry(list_body, textvariable=self.search_var, style="Server16.TEntry")
        search_entry.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(4, 8))
        search_entry.bind("<KeyRelease>", lambda _e: self._refresh_tree())

        tree_wrap = tk.Frame(list_body, bg=self.card)
        tree_wrap.grid(row=4, column=0, columnspan=2, sticky="nsew")
        tree_wrap.grid_columnconfigure(0, weight=1)
        tree_wrap.grid_rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(tree_wrap, show="tree", selectmode="browse", style="Server16.Treeview")
        tree_scroll = ttk.Scrollbar(tree_wrap, orient="vertical", command=self.tree.yview, style="Server16.Vertical.TScrollbar")
        self.tree.configure(yscrollcommand=tree_scroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        tree_scroll.grid(row=0, column=1, sticky="ns", padx=(6, 0))
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self._on_select())
        self.tree.bind("<Double-Button-1>", self._on_double_click)

        # --- Details (right) ---
        details_body = tk.Frame(details_card, bg=self.card)
        details_body.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        details_body.grid_columnconfigure(0, weight=1)
        self.selected_label = self._dark_label(
            details_body, self.tr("dialog.competition_picker.no_selection"), muted=True, wraplength=300, justify="left", anchor="w",
        )
        self.selected_label.grid(row=0, column=0, sticky="ew")
        self.hint_label = self._dark_label(details_body, self._hint_text(), muted=True, wraplength=300, justify="left", anchor="w", font=("Bahnschrift", 9))
        self.hint_label.grid(row=1, column=0, sticky="ew", pady=(12, 0))

        # --- Actions ---
        action_bar = tk.Frame(self, bg=self.bg)
        action_bar.grid(row=2, column=0, columnspan=2, sticky="ew", padx=14, pady=(0, 14))
        action_bar.grid_columnconfigure(0, weight=1)
        action_bar.grid_columnconfigure(1, weight=1)
        self.select_button = ttk.Button(action_bar, text=self.tr("button.select_competition"), command=self._confirm, state="disabled")
        self.select_button.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ttk.Button(action_bar, text=self.tr("button.cancel"), command=self.destroy).grid(row=0, column=1, sticky="ew", padx=(6, 0))

        if self._data is None:
            self.status_label.configure(text=self._unavailable_text())
            self.conf_combo.configure(state="disabled")
            self.nation_combo.configure(state="disabled")
            search_entry.configure(state="disabled")
            return

        self._fill_conf_combo()
        self._fill_nation_combo()
        self._refresh_tree()
        self._start_name_loading(name_loader)

    # -- availability ---------------------------------------------------------

    def _unavailable_text(self) -> str:
        key = {
            "packed": "dialog.competition_picker.unavailable_packed",
            "invalid": "dialog.competition_picker.unavailable_invalid",
        }.get(self._load.reason, "dialog.competition_picker.unavailable_missing")
        return self.tr(key, path=str(self._load.expected_path or ""))

    def _hint_text(self) -> str:
        if self._allow_round and self._allow_tournament:
            return self.tr("dialog.competition_picker.hint_both")
        return self.tr("dialog.competition_picker.hint_round" if self._allow_round else "dialog.competition_picker.hint_tournament")

    # -- names (32-bit bridge, off the Tk thread) -------------------------------

    def _start_name_loading(self, name_loader: NameLoader | None) -> None:
        if name_loader is None or self._data is None:
            self._update_status()
            return
        self._names_loading = True
        self._update_status()
        data = self._data

        def worker() -> None:
            try:
                names = name_loader(self._exedir, data)
            except Exception:
                names = None
            self._names_queue.put(names)

        threading.Thread(target=worker, name="competition-names", daemon=True).start()
        self.after(self.NAME_POLL_MS, self._poll_names)

    def _poll_names(self) -> None:
        if not self.winfo_exists():
            return
        try:
            names = self._names_queue.get_nowait()
        except queue.Empty:
            self.after(self.NAME_POLL_MS, self._poll_names)
            return
        self._names_loading = False
        if names and self._data is not None:
            self._data.apply_names(*names)
            self._fill_conf_combo()
            self._fill_nation_combo()
            self._refresh_tree()
        self._update_status()

    def _update_status(self) -> None:
        if self._data is None:
            return
        text = self.tr("dialog.competition_picker.count", count=len(self._data.competitions))
        if self._names_loading:
            text += "  ·  " + self.tr("dialog.competition_picker.loading_names")
        self.status_label.configure(text=text)

    # -- filters --------------------------------------------------------------

    @staticmethod
    def _normalize_text(value: str) -> str:
        normalized = unicodedata.normalize("NFKD", value or "")
        return "".join(char for char in normalized if not unicodedata.combining(char)).lower()

    def _fill_conf_combo(self) -> None:
        assert self._data is not None
        confs = sorted(self._data.confederations, key=lambda conf: (conf.name or conf.code).lower())
        previous = self._current_conf_id()
        self._conf_ids = [None, *[conf.conf_id for conf in confs]]
        self.conf_combo.configure(values=[self.tr("dialog.competition_picker.all_confederations"), *[conf.name or conf.code for conf in confs]])
        self.conf_combo.current(self._conf_ids.index(previous) if previous in self._conf_ids else 0)

    def _fill_nation_combo(self) -> None:
        assert self._data is not None
        conf_id = self._current_conf_id()
        previous = self._current_nation_filter()
        nations = [nation for nation in self._data.nations if conf_id is None or nation.conf_id == conf_id]
        nations.sort(key=lambda nation: self._data.nation_label(nation).lower())
        self._nation_ids = [None, "-", *[nation.nation_id for nation in nations]]
        self.nation_combo.configure(values=[
            self.tr("dialog.competition_picker.all_countries"),
            self.tr("dialog.competition_picker.no_country"),
            *[self._data.nation_label(nation) for nation in nations],
        ])
        self.nation_combo.current(self._nation_ids.index(previous) if previous in self._nation_ids else 0)

    def _current_conf_id(self) -> int | None:
        index = self.conf_combo.current()
        return self._conf_ids[index] if 0 <= index < len(self._conf_ids) else None

    def _current_nation_filter(self) -> int | None | str:
        index = self.nation_combo.current()
        return self._nation_ids[index] if 0 <= index < len(self._nation_ids) else None

    def _on_conf_change(self) -> None:
        self._fill_nation_combo()
        self._refresh_tree()

    # -- tree -------------------------------------------------------------------

    def _competition_title(self, comp) -> str:
        assert self._data is not None
        return self._data.competition_label(comp) or comp.code

    def _refresh_tree(self) -> None:
        data = self._data
        if data is None:
            return
        conf_id = self._current_conf_id()
        nation_filter = self._current_nation_filter()
        query = self._normalize_text(self.search_var.get().strip())
        nations = data.nation_by_id()

        self.tree.delete(*self.tree.get_children())
        self._selected = None
        self._show_selection()

        rows = []
        for comp in data.competitions:
            if conf_id is not None and comp.conf_id != conf_id:
                continue
            if nation_filter == "-" and comp.nation_id is not None:
                continue
            if isinstance(nation_filter, int) and comp.nation_id != nation_filter:
                continue
            nation = nations.get(comp.nation_id) if comp.nation_id is not None else None
            if not query:
                rows.append((comp, comp.stages, False, nation))
                continue
            comp_haystack = [str(comp.tour_id), str(comp.gfx or ""), comp.code, data.competition_label(comp), data.nation_label(nation) if nation else ""]
            if any(query in self._normalize_text(value) for value in comp_haystack):
                rows.append((comp, comp.stages, False, nation))
                continue
            stages = [stage for stage in comp.stages if any(query in self._normalize_text(value) for value in (str(stage.round_id), stage.code, stage.name))]
            if stages:
                rows.append((comp, stages, True, nation))

        rows.sort(key=lambda row: self._competition_title(row[0]).lower())
        for comp, stages, force_open, nation in rows:
            suffix = f"   {data.nation_label(nation)}" if nation else ""
            label = f"{self._competition_title(comp)}  [{comp.tour_id}]{suffix}"
            parent = self.tree.insert("", "end", iid=f"tour:{comp.tour_id}", text=label, open=force_open)
            for stage in stages:
                self.tree.insert(parent, "end", iid=f"round:{stage.round_id}", text=f"{stage.label}  [{stage.round_id}]")

    # -- selection ----------------------------------------------------------------

    def _selectable(self, kind: str) -> bool:
        return self._allow_tournament if kind == "tour" else self._allow_round

    def _on_select(self) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        kind, _, raw_id = selection[0].partition(":")
        self._selected = (kind, raw_id) if self._selectable(kind) else None
        self._show_selection(rejected_kind=None if self._selected else kind)

    def _show_selection(self, rejected_kind: str | None = None) -> None:
        if self._selected is None:
            text = self.tr("dialog.competition_picker.no_selection")
            if rejected_kind == "tour":
                text = self.tr("dialog.competition_picker.pick_a_stage")
            elif rejected_kind == "round":
                text = self.tr("dialog.competition_picker.pick_a_competition")
            self.selected_label.configure(text=text)
            self.select_button.configure(state="disabled")
            return
        kind, raw_id = self._selected
        label = self.tree.item(f"{kind}:{raw_id}", "text").rsplit("  [", 1)[0].strip()
        key = "dialog.competition_picker.selected_tournament" if kind == "tour" else "dialog.competition_picker.selected_round"
        self.selected_label.configure(text=self.tr(key, name=label, id=raw_id))
        self.select_button.configure(state="normal")

    def _on_double_click(self, event) -> None:
        row = self.tree.identify_row(event.y)
        if not row:
            return
        kind = row.partition(":")[0]
        if self._selectable(kind):
            self.tree.selection_set(row)
            self._on_select()
            self._confirm()

    def _confirm(self) -> None:
        if self._selected is None:
            return
        self.close_ok(self._selected[1])
