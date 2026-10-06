from __future__ import annotations

import os
import subprocess
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

from PIL import Image, ImageTk

from .asset_grid_items import (
    AssetGridItem,
    goalpost_model_items,
    goalpost_texture_items,
    make_picker_button,
    match_asset_items,
    png_items,
)
from .asset_grid_picker_dialog import AssetGridPickerDialog
from .chants_runtime import MciAudioPlayer
from .file_tools import (
    discover_stadium_names,
    resolve_goalpost_model_preview_path,
    resolve_goalpost_texture_rx3_path,
    resolve_stadium_preview_path,
    stadium_preview_fallback_path,
)
from .rx3_texture_preview import Rx3TexturePreview
from .stadium_picker_dialog import StadiumPickerDialog
from .stadium_runtime import StadiumRuntime
from .team_picker_dialog import TeamPickerDialog
from .video_preview import MoviePreviewPanel


@dataclass(frozen=True)
class SectionSpec:
    section: str
    title: str
    kind: str = "simple"
    value_label: str = "Value"
    directory: str | None = None
    recursive: bool = False
    key_is_team_id: bool = False
    key_is_round_id: bool = False
    key_is_tournament_id: bool = False
    key_is_derby: bool = False
    key_is_stadium_id: bool = False
    key_stadium_picker: bool = False
    # Match Assets (ball/referee/wipe/adboard): the value is a pack folder of
    # .rx3 files, so the tab shows a texture preview with arrows and the combo
    # gets the grid picker. `section` doubles as the preview's cache "kind".
    rx3_preview: bool = False


@dataclass(frozen=True)
class SpecGroup:
    """One top-level tab of SettingsAreaEditor. Two or more specs become
    sub-tabs of that tab; a single spec is shown as a plain tab (no nested
    notebook with one lonely sub-tab). `title` is only used for the
    multi-spec case -- a lone spec's tab is labelled with the spec's own title."""

    specs: tuple[SectionSpec, ...]
    title: str = ""

    @property
    def tab_title(self) -> str:
        return self.title if len(self.specs) > 1 and self.title else self.specs[0].title


class SettingsAreaEditor(tk.Toplevel):
    def __init__(self, app, title: str, specs: list[SectionSpec | SpecGroup], initial_section: str | None = None) -> None:
        owner = app._window() if hasattr(app, "_window") else app
        super().__init__(owner)
        self.app = app
        # A bare SectionSpec is a group of one, so flat spec lists (the chants
        # editor) and grouped layouts (stadium/asset editors) share one code path.
        self.groups = [spec if isinstance(spec, SpecGroup) else SpecGroup((spec,)) for spec in specs]
        self.specs = [spec for group in self.groups for spec in group.specs]
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
        # Top-level tab widget of a multi-spec group -> the sub-notebook inside
        # it, and section (lowercase) -> that sub-notebook, so the active frame
        # and initial_section can be resolved through the extra level.
        self._sub_notebooks: dict[tk.Misc, ttk.Notebook] = {}
        self._section_notebook: dict[str, ttk.Notebook] = {}
        self._section_tab: dict[str, tk.Misc] = {}
        for group in self.groups:
            if len(group.specs) == 1:
                spec = group.specs[0]
                frame = SettingsSectionFrame(self.notebook, app, spec)
                self.notebook.add(frame, text=self._tab_text(group.tab_title))
                self.frames[spec.section.lower()] = frame
                self._section_tab[spec.section.lower()] = frame
                continue
            host = tk.Frame(self.notebook, bg=app.bg)
            sub_notebook = ttk.Notebook(host, style="Server16.Sub.TNotebook")
            sub_notebook.pack(fill="both", expand=True, pady=(6, 0))
            self.notebook.add(host, text=self._tab_text(group.tab_title))
            self._sub_notebooks[host] = sub_notebook
            for spec in group.specs:
                frame = SettingsSectionFrame(sub_notebook, app, spec)
                sub_notebook.add(frame, text=self._tab_text(spec.title))
                self.frames[spec.section.lower()] = frame
                self._section_notebook[spec.section.lower()] = sub_notebook
                self._section_tab[spec.section.lower()] = host
        for notebook in (self.notebook, *self._sub_notebooks.values()):
            notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)
        if initial_section:
            self.select_section(initial_section)
        self._refresh_active_frame()

    def _tab_text(self, title: str) -> str:
        return self.app.tr(title) if hasattr(self.app, "tr") else title

    def select_section(self, section: str) -> None:
        """Shows the tab (and, inside a group, the sub-tab) holding `section`."""
        key = section.lower()
        frame = self.frames.get(key)
        if frame is None:
            return
        sub_notebook = self._section_notebook.get(key)
        if sub_notebook is not None:
            sub_notebook.select(frame)
        self.notebook.select(self._section_tab[key])

    def _active_frame(self) -> SettingsSectionFrame | None:
        try:
            current = self.notebook.nametowidget(self.notebook.select())
            sub_notebook = self._sub_notebooks.get(current)
            if sub_notebook is not None:
                current = sub_notebook.nametowidget(sub_notebook.select())
        except tk.TclError:
            return None
        return current if isinstance(current, SettingsSectionFrame) else None

    def _on_tab_changed(self, _event=None) -> None:
        for frame in self.frames.values():
            stop_preview = getattr(frame, "_stop_preview", None)
            if stop_preview is not None:
                stop_preview()
        self._refresh_active_frame()

    def _refresh_active_frame(self) -> None:
        frame = self._active_frame()
        if frame is not None:
            frame.reload_entries()


class SettingsSectionFrame(tk.Frame):
    # Must match _MAX_STADIUM_PICKER_ITEMS (d3d_injector.py) / MAX_STADIUM_PICKER_ITEMS
    # (cgfs16_overlay.cpp) -- the in-game F12 stadium picker's shared-memory
    # buffer holds at most this many candidates (it can now scroll through all
    # of them, so this is a generous technical ceiling, not a "fits on screen"
    # limit), so there is no point letting a key be assigned more than this here.
    MAX_ASSIGNED_STADIUMS = 64
    STADIUM_DEFAULTS = {"police": "4", "pitch": "0", "net": "0"}
    POLICE_VALUES = tuple(str(i) for i in range(1, 11))
    NET_DEFAULTS = {"down": "1089199011", "high": "1087199011", "rig": "2", "shape": "0", "tension": "0"}
    # Net shape is a 0/1 flag in-engine -- only these two values are valid.
    # shape_var holds the human-readable label; raw "0"/"1" is what actually
    # gets read/written to settings.ini (see _load_net_value/_compose_value).
    SHAPE_VALUE_TO_LABEL = {"0": "square(0)", "1": "triangle(1)"}
    SHAPE_LABEL_TO_VALUE = {label: value for value, label in SHAPE_VALUE_TO_LABEL.items()}
    SHAPE_CHOICES = list(SHAPE_VALUE_TO_LABEL.values())
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
    # Heading of the grid picker for each Match Asset section ("Choose Ball").
    MATCH_ASSET_FIELD_KEYS = {
        "ball": "dialog.editor.field.ball",
        "referee": "dialog.editor.field.referee",
        "wipe": "dialog.editor.field.wipe",
        "adboard": "dialog.editor.field.adboard",
    }
    # Pause before a changed Match Asset value starts rendering its textures
    # (each pack costs a seconds-long 32-bit subprocess), so stepping through
    # the combo with the arrow keys doesn't launch one per press.
    RX3_PREVIEW_DELAY_MS = 250

    def __init__(self, parent: tk.Misc, app, spec: SectionSpec) -> None:
        super().__init__(parent, bg=app.bg)
        self.app = app
        self.spec = spec
        self.selected_key: str | None = None
        self._refresh_job = None
        self._rx3_preview: Rx3TexturePreview | None = None
        self._rx3_preview_job = None
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

        key_button_specs = self._key_button_specs()
        if key_button_specs:
            key_buttons = tk.Frame(form, bg=self.app.card)
            key_buttons.grid(row=0, column=2, sticky="e", padx=(8, 0), pady=(0, 6))
            for index, (label_key, command) in enumerate(key_button_specs):
                last = index == len(key_button_specs) - 1
                ttk.Button(key_buttons, text=self.tr(label_key), command=command).pack(side="left", padx=(0, 0 if last else 4))

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

        self.body = tk.Frame(scroll_content, bg=self.app.card)
        self.body.grid(row=0, column=0, sticky="nsew", padx=12, pady=(0, 8))
        self.body.grid_columnconfigure(0, weight=1)

        self._build_editor_body()

        if self.spec.kind in ("chants", "entrance"):
            self._build_chants_preview_panel(scroll_content)
        elif self.spec.kind == "stadium":
            self._build_stadium_preview_panel(scroll_content)
        elif self.spec.rx3_preview:
            self._build_rx3_preview_panel(scroll_content)
        elif self.spec.directory == "MoviesGBD":
            self._build_movie_preview_panel(scroll_content)
        elif self.spec.directory in ("ScoreBoardGBD", "TVLogoGBD"):
            self._build_asset_preview_panel(scroll_content)

        # <MouseWheel> only fires on the exact widget under the cursor, not
        # its ancestors -- binding just body_canvas/scroll_content (as
        # before) left the wheel dead over almost the whole panel, since
        # that's covered by self.body's/the preview panel's own descendant
        # labels/combos/frames. Bind every descendant too, now that the full
        # subtree (body + whichever preview panel this kind built) exists.
        self._bind_mousewheel_recursive(body_canvas, scroll_callback=lambda steps: body_canvas.yview_scroll(steps, "units"))

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

    def _key_button_specs(self) -> list[tuple[str, Callable[[], None]]]:
        """(locale key, command) of every button shown next to Key. A key can
        be valid in several ways (Scoreboard/TV Logo/Movies/Competition
        stadiums accept a round id OR a tournament id, see the runtimes'
        round-then-tournament lookups), so the helpers add up instead of
        excluding each other."""
        spec = self.spec
        buttons: list[tuple[str, Callable[[], None]]] = []
        if spec.key_is_team_id:
            buttons += [
                ("button.use_home_team", self._use_home_team_key),
                ("button.use_away_team", self._use_away_team_key),
                ("button.pick_team", self._pick_team_key),
            ]
        if spec.key_is_round_id:
            buttons.append(("button.use_current_round_id", self._use_current_round_key))
        if spec.key_is_tournament_id:
            buttons.append(("button.use_current_tournament_id", self._use_current_tournament_key))
        if spec.key_is_derby:
            buttons.append(("button.use_current_derby", self._use_current_derby_key))
        if spec.key_is_stadium_id:
            buttons.append(("button.use_current_stadium_id", self._use_current_stadium_id_key))
        if spec.key_stadium_picker:
            buttons.append(("button.pick_stadium", self._pick_stadium_key))
        return buttons

    def _use_home_team_key(self) -> None:
        self.key_var.set(getattr(self.app, "HID", "") or "")

    def _use_away_team_key(self) -> None:
        self.key_var.set(getattr(self.app, "AID", "") or "")

    def _use_current_round_key(self) -> None:
        self.key_var.set(getattr(self.app, "TOURROUNDID", "") or "")

    def _use_current_tournament_key(self) -> None:
        self.key_var.set(getattr(self.app, "TOURNAME", "") or "")

    def _use_current_derby_key(self) -> None:
        # The runtimes only look a derby up when BOTH teams are known (app.derby
        # is "{HID}vs{AID}", which degrades to "vs" with no teams read yet).
        app = self.app
        derby = getattr(app, "derby", "") if getattr(app, "HID", "") and getattr(app, "AID", "") else ""
        self.key_var.set(derby or "")

    def _use_current_stadium_id_key(self) -> None:
        self.key_var.set(getattr(self.app, "STADID", "") or "")

    def _pick_team_key(self) -> None:
        dialog = TeamPickerDialog(self.app)
        self.app.wait_window(dialog)
        if dialog.result:
            self.key_var.set(dialog.result)

    def _pick_stadium_key(self) -> None:
        exedir = getattr(self.app, "exedir", None)
        if not exedir:
            return
        configured_names = {key for key, _value in self.app.settings_ini.items(self.spec.section)}
        dialog = StadiumPickerDialog(self.app, exedir, configured_names)
        self.app.wait_window(dialog)
        if dialog.result:
            self.key_var.set(dialog.result)

    def _build_editor_body(self) -> None:
        if self.spec.kind == "simple":
            self.value_var = tk.StringVar()
            self.value_combo = self._add_combo_row(
                self.body, 0, self.spec.value_label, self.value_var, self._available_choices(),
                picker=self._pick_match_asset if self.spec.rx3_preview else None,
            )
            if self.spec.section == "stadiumentrancecam":
                self._add_entrance_cam_hint(1)
        elif self.spec.kind == "stadium":
            self._build_stadium_editor()
        elif self.spec.kind == "net":
            self._build_net_editor()
        elif self.spec.kind == "scoreboardstdname":
            self._build_scoreboard_name_editor()
        elif self.spec.kind == "chants":
            self._build_chants_editor()
        elif self.spec.kind == "entrance":
            self._build_entrance_editor()
        elif self.spec.kind == "exclude":
            self.exclude_var = tk.StringVar(value="excluded from stadium server")
            self.exclude_entry = self._add_entry_row(self.body, 0, "Reason", self.exclude_var, readonly=True)

    def _build_stadium_editor(self) -> None:
        # Per-stadium Police/Pitch/Net -- name -> (police, pitch, net), keyed
        # by stadium name (unique within Assigned, see _stadium_add_selected)
        # so it survives reordering without tracking Listbox indices. Whichever
        # single row is selected in Assigned is the "active" one the three
        # combos below read from and write into (see _on_assigned_selection_changed).
        self._stadium_params: dict[str, tuple[str, str, str]] = {}
        # Goalpost model/texture are deliberately NOT part of _stadium_params'
        # comma-joined tuple -- they're persisted separately, to
        # [stadiumgoalpost]/[stadiumgoalposttexture], keyed by stadium name,
        # exactly like StadiumRuntime.resolve_goalpost_sources reads them
        # (see save_entry -> _save_stadium_goalpost_overrides). Kept in their
        # own dicts here purely so this UI can show/edit them alongside
        # Police/Pitch/Net without touching _parse_stadium_entries' own
        # fragile comma-count heuristic for [stadium]/[comp] itself. Split
        # into two independent dicts/combos (not one) because a real pack
        # ships model and texture/color as separate, independently
        # mix-and-matchable folders (FSW/Goalpost/GoalpostModel/<name>/,
        # FSW/Goalpost/GoalpostColor/<name>/), not one combined folder.
        self._stadium_goalpost: dict[str, str] = {}
        self._stadium_goalpost_texture: dict[str, str] = {}
        # [stadiumentrancecam] (FSW/Camera/EntranceScene/<name>/ packs, see
        # StadiumRuntime.resolve_entrance_cam_sources) -- same name-keyed,
        # separately-persisted convention as the two goalpost dicts above.
        self._stadium_entrance_cam: dict[str, str] = {}
        self._active_stadium_name: str | None = None
        self.body.grid_columnconfigure(0, weight=1)
        self.body.grid_columnconfigure(1, weight=1)

        # Assigned <-> Available layout: the left list is exactly the (ordered)
        # set of stadiums saved for this key -- order matters, since it's the
        # same order the in-game F12 stadium picker lists them in
        # (stadium_runtime._open_stadium_picker -> stadium_picker.rml). The
        # right list is every stadium folder that exists on disk, filterable
        # by the search box above it. Add/Remove/Replace/Move act between them
        # instead of one big ctrl+click multi-select list.
        lists_row = tk.Frame(self.body, bg=self.app.card)
        lists_row.grid(row=0, column=0, columnspan=2, sticky="nsew", pady=(0, 10))
        lists_row.grid_columnconfigure(0, weight=1)
        lists_row.grid_columnconfigure(2, weight=1)
        lists_row.grid_rowconfigure(0, weight=1)

        assigned_col = tk.Frame(lists_row, bg=self.app.card)
        assigned_col.grid(row=0, column=2, sticky="nsew", padx=(8, 0))
        assigned_col.grid_columnconfigure(0, weight=1)
        assigned_col.grid_rowconfigure(1, weight=1)

        assigned_header = tk.Frame(assigned_col, bg=self.app.card)
        assigned_header.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        assigned_header.grid_columnconfigure(0, weight=1)
        tk.Label(
            assigned_header,
            text=self.tr("dialog.editor.stadium_multi.assigned_title"),
            bg=self.app.card,
            fg=self.app.muted,
            font=("Bahnschrift", 9, "bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="w")
        self.assigned_count_label = tk.Label(
            assigned_header, text="", bg=self.app.card, font=("Bahnschrift", 9, "bold"), anchor="e",
        )
        self.assigned_count_label.grid(row=0, column=1, sticky="e")

        assigned_list_wrap = tk.Frame(assigned_col, bg=self.app.card)
        assigned_list_wrap.grid(row=1, column=0, sticky="nsew")
        assigned_list_wrap.grid_columnconfigure(0, weight=1)
        assigned_list_wrap.grid_rowconfigure(0, weight=1)
        self.assigned_stadium_list = tk.Listbox(
            assigned_list_wrap,
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
        assigned_scroll = ttk.Scrollbar(
            assigned_list_wrap, orient="vertical", command=self.assigned_stadium_list.yview, style="Server16.Vertical.TScrollbar",
        )
        self.assigned_stadium_list.configure(yscrollcommand=assigned_scroll.set)
        self.assigned_stadium_list.grid(row=0, column=0, sticky="nsew")
        assigned_scroll.grid(row=0, column=1, sticky="ns", padx=(4, 0))
        # selection_set() (used by _load_stadium_value/new_entry/add/remove/
        # replace/move) doesn't fire this virtual event, so those call
        # _on_assigned_selection_changed() directly; this binding only covers
        # the user clicking in the list themselves.
        self.assigned_stadium_list.bind("<<ListboxSelect>>", lambda _e: self._on_assigned_selection_changed())
        self.assigned_stadium_list.bind("<Double-Button-1>", lambda _e: self._stadium_remove_selected())

        tk.Label(
            assigned_col,
            text=self.tr("dialog.editor.stadium_multi.hint"),
            bg=self.app.card,
            fg=self.app.muted,
            font=("Bahnschrift", 8),
            anchor="w",
            wraplength=220,
            justify="left",
        ).grid(row=2, column=0, sticky="w", pady=(4, 0))

        toolbar = tk.Frame(lists_row, bg=self.app.card)
        toolbar.grid(row=0, column=1, sticky="ns", padx=4)
        self._stadium_add_btn = ttk.Button(
            toolbar, text=self.tr("dialog.editor.stadium_multi.add") + " →", command=self._stadium_add_selected,
        )
        self._stadium_add_btn.pack(fill="x", pady=(28, 4))
        ttk.Button(
            toolbar, text="← " + self.tr("dialog.editor.stadium_multi.remove"), command=self._stadium_remove_selected,
        ).pack(fill="x", pady=4)
        ttk.Button(
            toolbar, text=self.tr("dialog.editor.stadium_multi.replace"), command=self._stadium_replace_selected,
        ).pack(fill="x", pady=4)
        move_row = tk.Frame(toolbar, bg=self.app.card)
        move_row.pack(fill="x", pady=(16, 4))
        ttk.Button(move_row, text="▲", width=3, command=lambda: self._stadium_move_selected(-1)).pack(side="left", expand=True, fill="x")
        ttk.Button(move_row, text="▼", width=3, command=lambda: self._stadium_move_selected(1)).pack(side="left", expand=True, fill="x")

        available_col = tk.Frame(lists_row, bg=self.app.card)
        available_col.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        available_col.grid_columnconfigure(0, weight=1)
        available_col.grid_rowconfigure(2, weight=1)
        tk.Label(
            available_col,
            text=self.tr("dialog.editor.stadium_multi.available_title"),
            bg=self.app.card,
            fg=self.app.muted,
            font=("Bahnschrift", 9, "bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="w", pady=(0, 4))
        self.available_search_var = tk.StringVar()
        search_entry = tk.Entry(
            available_col,
            textvariable=self.available_search_var,
            bg=self.app.panel_alt,
            fg=self.app.fg,
            insertbackground=self.app.fg,
            relief="flat",
            font=("Consolas", 10),
        )
        search_entry.grid(row=1, column=0, sticky="ew", pady=(0, 4))
        search_entry.bind("<KeyRelease>", lambda _e: self._filter_available_stadiums())

        available_list_wrap = tk.Frame(available_col, bg=self.app.card)
        available_list_wrap.grid(row=2, column=0, sticky="nsew")
        available_list_wrap.grid_columnconfigure(0, weight=1)
        available_list_wrap.grid_rowconfigure(0, weight=1)
        self.available_stadium_list = tk.Listbox(
            available_list_wrap,
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
        available_scroll = ttk.Scrollbar(
            available_list_wrap, orient="vertical", command=self.available_stadium_list.yview, style="Server16.Vertical.TScrollbar",
        )
        self.available_stadium_list.configure(yscrollcommand=available_scroll.set)
        self.available_stadium_list.grid(row=0, column=0, sticky="nsew")
        available_scroll.grid(row=0, column=1, sticky="ns", padx=(4, 0))
        self.available_stadium_list.bind("<Double-Button-1>", lambda _e: self._stadium_add_selected())
        self._all_available_stadiums = self._available_choices()
        for entry in self._all_available_stadiums:
            self.available_stadium_list.insert("end", entry)

        self.stadium_params_label = tk.Label(
            self.body, text="", bg=self.app.card, fg=self.app.accent, font=("Bahnschrift", 9, "bold"), anchor="w",
        )
        self.stadium_params_label.grid(row=1, column=0, columnspan=2, sticky="w", pady=(2, 4))

        self.police_var = tk.StringVar(value=self.STADIUM_DEFAULTS["police"])
        self.pitch_var = tk.StringVar(value=self.STADIUM_DEFAULTS["pitch"])
        self.net_var = tk.StringVar(value=self.STADIUM_DEFAULTS["net"])
        # Each StringVar write both refreshes that field's preview image AND
        # (when a single Assigned row is selected) writes the new value back
        # into that stadium's own entry in self._stadium_params -- see
        # _on_stadium_param_changed. Re-applying the same value back to
        # itself (e.g. right after _on_assigned_selection_changed loads a
        # freshly-selected row's values into these vars) is a harmless no-op.
        self.police_var.trace_add("write", lambda *_: self._on_stadium_param_changed("police"))
        self.pitch_var.trace_add("write", lambda *_: self._on_stadium_param_changed("pitch"))
        self.net_var.trace_add("write", lambda *_: self._on_stadium_param_changed("net"))
        # Each combo also gets a small button beside it that opens the preview
        # grid for that field (see _pick_stadium_asset) -- picking there just
        # sets the same StringVar the combo is bound to, so everything above
        # (preview refresh, write-back into _stadium_params/_stadium_goalpost*)
        # runs exactly as if the value had been chosen from the dropdown.
        self.police_combo = self._add_combo_row(self.body, 2, self.tr("dialog.editor.field.police"), self.police_var, list(self.POLICE_VALUES), picker=lambda: self._pick_stadium_asset("police"))
        self.pitch_combo = self._add_combo_row(self.body, 3, self.tr("dialog.editor.field.pitch"), self.pitch_var, self._asset_indices(self.app.PitchMowsource), picker=lambda: self._pick_stadium_asset("pitch"))
        self.net_combo = self._add_combo_row(self.body, 4, self.tr("dialog.editor.field.net"), self.net_var, self._asset_indices(self.app.Nsource), picker=lambda: self._pick_stadium_asset("net"))
        self.goalpost_var = tk.StringVar(value="None")
        self.goalpost_var.trace_add("write", lambda *_: self._on_stadium_param_changed("goalpost"))
        self.goalpost_combo = self._add_combo_row(self.body, 5, self.tr("dialog.editor.field.goalpost_model"), self.goalpost_var, self._available_goalpost_choices("GoalpostModel"), picker=lambda: self._pick_stadium_asset("goalpost"))
        self.goalpost_texture_var = tk.StringVar(value="None")
        self.goalpost_texture_var.trace_add("write", lambda *_: self._on_stadium_param_changed("goalposttexture"))
        self.goalpost_texture_combo = self._add_combo_row(self.body, 6, self.tr("dialog.editor.field.goalpost_texture"), self.goalpost_texture_var, self._available_goalpost_choices("GoalpostColor"), picker=lambda: self._pick_stadium_asset("goalposttexture"))
        self.entrance_cam_var = tk.StringVar(value="None")
        self.entrance_cam_var.trace_add("write", lambda *_: self._on_stadium_param_changed("entrancecam"))
        self.entrance_cam_combo = self._add_combo_row(self.body, 7, self.tr("dialog.editor.field.entrance_cam"), self.entrance_cam_var, self._available_entrance_cam_choices(), picker=lambda: self._pick_stadium_asset("entrancecam"))
        self._add_entrance_cam_hint(8)
        self._refresh_stadium_assigned_state()

    def _add_entrance_cam_hint(self, row: int) -> None:
        """Pack-vs-stadium-camera priority note (see StadiumRuntime.resolve_entrance_cam_sources),
        shown wherever an Entrance Camera pack can be picked in this editor."""
        tk.Label(
            self.body,
            text=self.tr("dialog.stadium.entrance_cam_hint"),
            bg=self.app.card,
            fg=self.app.muted,
            font=("Bahnschrift", 8),
            anchor="w",
            wraplength=420,
            justify="left",
        ).grid(row=row, column=0, columnspan=2, sticky="w", pady=(4, 4))

    def _stadium_default_triple(self) -> tuple[str, str, str]:
        return (self.STADIUM_DEFAULTS["police"], self.STADIUM_DEFAULTS["pitch"], self.STADIUM_DEFAULTS["net"])

    def _available_goalpost_choices(self, category: str) -> list[str]:
        base = self.app.exedir / "FSW" / "Goalpost" / category
        choices = ["None"]
        if base.exists():
            choices.extend(sorted(path.name for path in base.iterdir() if path.is_dir()))
        return choices

    def _lookup_existing_goalpost_overrides(self, name: str) -> tuple[str, str]:
        """Reads name's CURRENT [stadiumgoalpost]/[stadiumgoalposttexture]
        values directly from settings.ini -- used whenever a stadium enters
        this UI's in-memory dicts for the first time this session (a fresh
        Add, or the new occupant of a Replace), so an existing global
        override for that name (e.g. set while it was assigned to a
        different team) is reflected accurately here instead of defaulting
        to "None" and then silently deleting it the moment this key is
        saved (see _save_stadium_goalpost_overrides)."""
        model = self.app.settings_ini.read(name, "stadiumgoalpost").strip() if self.app.settings_ini.key_exists(name, "stadiumgoalpost") else ""
        texture = self.app.settings_ini.read(name, "stadiumgoalposttexture").strip() if self.app.settings_ini.key_exists(name, "stadiumgoalposttexture") else ""
        return model or "None", texture or "None"

    def _entrance_cam_dir(self) -> Path:
        return self.app.exedir / "FSW" / "Camera" / "EntranceScene"

    def _available_entrance_cam_choices(self) -> list[str]:
        base = self._entrance_cam_dir()
        choices = ["None"]
        if base.exists():
            choices.extend(sorted(path.name for path in base.iterdir() if path.is_dir()))
        return choices

    def _lookup_existing_entrance_cam(self, name: str) -> str:
        """name's CURRENT [stadiumentrancecam] value from settings.ini, for the
        same reason as _lookup_existing_goalpost_overrides (kept separate so
        that one's 2-tuple stays as it is)."""
        if self.app.settings_ini.key_exists(name, "stadiumentrancecam"):
            return self.app.settings_ini.read(name, "stadiumentrancecam").strip() or "None"
        return "None"

    def _set_stadium_param_controls_state(self, state: str) -> None:
        for combo in (self.police_combo, self.pitch_combo, self.net_combo, self.goalpost_combo, self.goalpost_texture_combo, self.entrance_cam_combo):
            combo.configure(state=state)
            # The picker button (see _add_combo_row) follows its combo: with no
            # single Assigned row selected there's nothing for a pick to write into.
            picker_button = getattr(combo, "picker_button", None)
            if picker_button is not None:
                picker_button.configure(state=state)

    def _pick_stadium_asset(self, field: str) -> None:
        """Opens the preview grid for one of the stadium editor's
        preview-bearing fields and writes the choice back into that field's
        StringVar (which then flows through _on_stadium_param_changed like any
        dropdown change). Cancelling leaves the field untouched."""
        variable, label_key, items = self._stadium_picker_setup(field)
        dialog = AssetGridPickerDialog(self.app, self.tr(label_key), items, current=variable.get().strip())
        self.app.wait_window(dialog)
        if dialog.result is not None:
            variable.set(dialog.result)

    def _stadium_picker_setup(self, field: str) -> tuple[tk.StringVar, str, list[AssetGridItem]]:
        """(variable, label translation key, grid items) for `field` -- the
        same option lists and preview locations the combos and preview boxes
        above already use, re-read from disk so a pack added while this editor
        was open still shows up."""
        if field == "police":
            return self.police_var, "dialog.editor.field.police", png_items(self.POLICE_VALUES, self._police_preview_dir)
        if field == "pitch":
            items = png_items(self._asset_indices(self.app.PitchMowsource), self._pitch_preview_dir)
            return self.pitch_var, "dialog.editor.field.pitch", items
        if field == "net":
            items = png_items(self._asset_indices(self.app.Nsource), self._net_preview_dir)
            return self.net_var, "dialog.editor.field.net", items
        if field == "goalpost":
            model_dir = self.app.exedir / "FSW" / "Goalpost" / "GoalpostModel"
            items = goalpost_model_items(model_dir, self._available_goalpost_choices("GoalpostModel"))
            return self.goalpost_var, "dialog.editor.field.goalpost_model", items
        if field == "goalposttexture":
            color_dir = self.app.exedir / "FSW" / "Goalpost" / "GoalpostColor"
            items = goalpost_texture_items(color_dir, self._available_goalpost_choices("GoalpostColor"), self.app.stadium_runtime)
            return self.goalpost_texture_var, "dialog.editor.field.goalpost_texture", items
        if field == "entrancecam":
            # Same preview.<ext>-inside-the-pack convention as GoalpostModel.
            items = goalpost_model_items(self._entrance_cam_dir(), self._available_entrance_cam_choices())
            return self.entrance_cam_var, "dialog.editor.field.entrance_cam", items
        raise ValueError(f"no asset picker for stadium field {field!r}")

    def _on_assigned_selection_changed(self) -> None:
        """Loads the single selected Assigned row's own Police/Pitch/Net into
        the three combos below (or disables them when 0 or >1 rows are
        selected, to avoid ambiguously bulk-editing). Called after every
        mutation (add/remove/replace/move) as well as on <<ListboxSelect>>."""
        selection = self.assigned_stadium_list.curselection()
        if len(selection) == 1:
            name = self.assigned_stadium_list.get(selection[0])
            self._active_stadium_name = name
            police, pitch, net = self._stadium_params.get(name, self._stadium_default_triple())
            self.police_var.set(police)
            self.pitch_var.set(pitch)
            self.net_var.set(net)
            self.goalpost_var.set(self._stadium_goalpost.get(name, "None"))
            self.goalpost_texture_var.set(self._stadium_goalpost_texture.get(name, "None"))
            self.entrance_cam_var.set(self._stadium_entrance_cam.get(name, "None"))
            self._set_stadium_param_controls_state("normal")
            self.stadium_params_label.configure(text=self.tr("dialog.editor.stadium_multi.editing_params", name=name))
        else:
            self._active_stadium_name = None
            self._set_stadium_param_controls_state("disabled")
            self.stadium_params_label.configure(text=self.tr("dialog.editor.stadium_multi.select_to_edit_params"))
        self._update_stadium_preview()

    def _on_stadium_param_changed(self, field: str) -> None:
        if field == "police":
            self._update_police_preview()
        elif field == "pitch":
            self._update_pitch_preview()
        elif field == "net":
            self._update_net_preview()
        elif field == "goalpost":
            self._update_goalpost_model_preview()
        elif field == "goalposttexture":
            self._update_goalpost_texture_preview()
        elif field == "entrancecam":
            self._update_entrance_cam_preview()
        if self._active_stadium_name is None:
            return
        if field == "goalpost":
            self._stadium_goalpost[self._active_stadium_name] = self.goalpost_var.get().strip() or "None"
        elif field == "goalposttexture":
            self._stadium_goalpost_texture[self._active_stadium_name] = self.goalpost_texture_var.get().strip() or "None"
        elif field == "entrancecam":
            self._stadium_entrance_cam[self._active_stadium_name] = self.entrance_cam_var.get().strip() or "None"
        else:
            self._stadium_params[self._active_stadium_name] = (
                self.police_var.get().strip(), self.pitch_var.get().strip(), self.net_var.get().strip(),
            )

    def _refresh_stadium_assigned_state(self) -> None:
        count = self.assigned_stadium_list.size()
        over_max = count > self.MAX_ASSIGNED_STADIUMS
        self.assigned_count_label.configure(
            text=self.tr("dialog.editor.stadium_multi.count", count=count, max=self.MAX_ASSIGNED_STADIUMS),
            fg=self.app.error if over_max else self.app.gold,
        )
        self._stadium_add_btn.configure(state="disabled" if count >= self.MAX_ASSIGNED_STADIUMS else "normal")
        self._on_assigned_selection_changed()

    def _filter_available_stadiums(self) -> None:
        query = self.available_search_var.get().strip().lower()
        self.available_stadium_list.delete(0, "end")
        for name in self._all_available_stadiums:
            if not query or query in name.lower():
                self.available_stadium_list.insert("end", name)

    def _stadium_add_selected(self) -> None:
        to_add = [self.available_stadium_list.get(index) for index in self.available_stadium_list.curselection()]
        if not to_add:
            return
        existing = set(self.assigned_stadium_list.get(0, "end"))
        last_added_index = None
        for name in to_add:
            if name in existing:
                continue
            if self.assigned_stadium_list.size() >= self.MAX_ASSIGNED_STADIUMS:
                self.status_var.set(self.tr("dialog.editor.stadium_multi.max_reached", max=self.MAX_ASSIGNED_STADIUMS))
                break
            self.assigned_stadium_list.insert("end", name)
            # A stadium not yet in _stadium_params (the common case) starts at
            # the defaults; one already there (e.g. re-added after Remove)
            # keeps whatever it had rather than resetting it.
            self._stadium_params.setdefault(name, self._stadium_default_triple())
            if name not in self._stadium_goalpost:
                model, texture = self._lookup_existing_goalpost_overrides(name)
                self._stadium_goalpost[name] = model
                self._stadium_goalpost_texture[name] = texture
            if name not in self._stadium_entrance_cam:
                self._stadium_entrance_cam[name] = self._lookup_existing_entrance_cam(name)
            existing.add(name)
            last_added_index = self.assigned_stadium_list.size() - 1
        if last_added_index is not None:
            self.assigned_stadium_list.selection_clear(0, "end")
            self.assigned_stadium_list.selection_set(last_added_index)
            self.assigned_stadium_list.activate(last_added_index)
            self._refresh_stadium_assigned_state()

    def _stadium_remove_selected(self) -> None:
        selection = self.assigned_stadium_list.curselection()
        if not selection:
            return
        for index in reversed(selection):
            name = self.assigned_stadium_list.get(index)
            self.assigned_stadium_list.delete(index)
            self._stadium_params.pop(name, None)
        self._refresh_stadium_assigned_state()

    def _stadium_replace_selected(self) -> None:
        assigned_selection = self.assigned_stadium_list.curselection()
        available_selection = self.available_stadium_list.curselection()
        if len(assigned_selection) != 1 or len(available_selection) != 1:
            self.status_var.set(self.tr("dialog.editor.stadium_multi.select_to_replace"))
            return
        index = assigned_selection[0]
        new_name = self.available_stadium_list.get(available_selection[0])
        current_name = self.assigned_stadium_list.get(index)
        if new_name != current_name and new_name in set(self.assigned_stadium_list.get(0, "end")):
            self.status_var.set(self.tr("dialog.editor.stadium_multi.already_assigned", name=new_name))
            return
        # Replace in place (same index) so it doesn't reshuffle in-game picker
        # order. The new occupant inherits the outgoing one's Police/Pitch/Net
        # (replacing preserves "this slot's configuration", it just swaps which
        # stadium fills it) unless the new name already has its own saved
        # values from earlier (e.g. it was assigned before and removed).
        if new_name != current_name:
            inherited = self._stadium_params.get(new_name, self._stadium_params.get(current_name, self._stadium_default_triple()))
            self._stadium_params[new_name] = inherited
            self._stadium_params.pop(current_name, None)
            # Goalpost model/texture are global-by-name (see
            # _lookup_existing_goalpost_overrides), so the new occupant does
            # NOT inherit the outgoing stadium's goalpost the way Police/
            # Pitch/Net does above -- it gets its own already-in-memory value
            # if this session already touched it, else whatever's currently
            # configured for it globally.
            if new_name in self._stadium_goalpost:
                goalpost_model = self._stadium_goalpost[new_name]
                goalpost_texture = self._stadium_goalpost_texture.get(new_name, "None")
            else:
                goalpost_model, goalpost_texture = self._lookup_existing_goalpost_overrides(new_name)
            self._stadium_goalpost[new_name] = goalpost_model
            self._stadium_goalpost_texture[new_name] = goalpost_texture
            self._stadium_goalpost.pop(current_name, None)
            self._stadium_goalpost_texture.pop(current_name, None)
            # Global-by-name too, same as the goalpost picks above.
            if new_name not in self._stadium_entrance_cam:
                self._stadium_entrance_cam[new_name] = self._lookup_existing_entrance_cam(new_name)
            self._stadium_entrance_cam.pop(current_name, None)
        self.assigned_stadium_list.delete(index)
        self.assigned_stadium_list.insert(index, new_name)
        self.assigned_stadium_list.selection_set(index)
        self._refresh_stadium_assigned_state()

    def _stadium_move_selected(self, direction: int) -> None:
        selection = self.assigned_stadium_list.curselection()
        if len(selection) != 1:
            return
        index = selection[0]
        target = index + direction
        items = list(self.assigned_stadium_list.get(0, "end"))
        if target < 0 or target >= len(items):
            return
        items[index], items[target] = items[target], items[index]
        self.assigned_stadium_list.delete(0, "end")
        for name in items:
            self.assigned_stadium_list.insert("end", name)
        self.assigned_stadium_list.selection_set(target)
        self.assigned_stadium_list.activate(target)
        self._on_assigned_selection_changed()

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
        container.grid_rowconfigure(2, weight=1)

        small_row = tk.Frame(container, bg=self.app.card)
        small_row.grid(row=0, column=0, sticky="nsew", pady=(0, 8))
        small_row.grid_columnconfigure(0, weight=1)
        small_row.grid_columnconfigure(1, weight=1)
        small_row.grid_columnconfigure(2, weight=1)
        self._build_stadium_preview_box(small_row, 0, self.tr("dialog.stadium.preview.police"), "police", image_size=(170, 140))
        self._build_stadium_preview_box(small_row, 1, self.tr("dialog.stadium.preview.pitch"), "pitch", image_size=(170, 140))
        self._build_stadium_preview_box(small_row, 2, self.tr("dialog.stadium.preview.net"), "net", image_size=(170, 140))

        goalpost_row = tk.Frame(container, bg=self.app.card)
        goalpost_row.grid(row=1, column=0, sticky="nsew", pady=(0, 8))
        goalpost_row.grid_columnconfigure(0, weight=1)
        goalpost_row.grid_columnconfigure(1, weight=1)
        goalpost_row.grid_columnconfigure(2, weight=1)
        self._build_stadium_preview_box(goalpost_row, 0, self.tr("dialog.stadium.preview.goalpost_model"), "goalpost_model", image_size=(170, 140))
        self._build_stadium_preview_box(goalpost_row, 1, self.tr("dialog.stadium.preview.goalpost_texture"), "goalpost_texture", image_size=(170, 140))
        self._build_stadium_preview_box(goalpost_row, 2, self.tr("dialog.stadium.preview.entrance_cam"), "entrance_cam", image_size=(170, 140))

        stadium_wrap = tk.Frame(container, bg=self.app.card)
        stadium_wrap.grid(row=2, column=0, sticky="nsew")
        stadium_wrap.grid_columnconfigure(0, weight=1)
        self._build_stadium_preview_box(stadium_wrap, 0, self.tr("dialog.stadium.preview.stadium"), "stadium", image_size=(520, 300))

        self._update_stadium_preview()
        self._update_pitch_preview()
        self._update_net_preview()
        self._update_police_preview()
        self._update_goalpost_model_preview()
        self._update_goalpost_texture_preview()
        self._update_entrance_cam_preview()

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
        selection = self.assigned_stadium_list.curselection()
        if selection:
            stadium_name = self.assigned_stadium_list.get(selection[0])
        elif self.assigned_stadium_list.size() > 0:
            stadium_name = self.assigned_stadium_list.get(0)
        else:
            stadium_name = ""
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

    def _update_goalpost_model_preview(self) -> None:
        # Static image, unlike the texture side below -- see the "preview"
        # convention documented on resolve_goalpost_model_preview_path.
        if "goalpost_model" not in self._preview_labels:
            return
        name = self.goalpost_var.get().strip()
        image_path = None
        if name and name != "None":
            image_path = resolve_goalpost_model_preview_path(self.app.exedir / "FSW" / "Goalpost" / "GoalpostModel", name)
        self._set_preview_image("goalpost_model", image_path, self.tr("placeholder.no_preview"))

    def _update_entrance_cam_preview(self) -> None:
        if "entrance_cam" not in self._preview_labels:
            return
        name = self.entrance_cam_var.get().strip()
        image_path = None
        if name and name != "None":
            image_path = resolve_goalpost_model_preview_path(self._entrance_cam_dir(), name)
        self._set_preview_image("entrance_cam", image_path, self.tr("placeholder.no_preview"))

    def _update_goalpost_texture_preview(self) -> None:
        # Unlike every other preview in this panel (all plain image files), a
        # GoalpostColor pack has no preview image convention -- the preview
        # is rendered from the pack's own .rx3 texture via the 32-bit
        # FifaLibrary bridge (StadiumRuntime.render_goalpost_texture_preview),
        # so this has to run off the UI thread and guard against a newer
        # selection superseding a still-running render (same pattern
        # app_ui.py's Kit Mixer preview uses, and dialogs.py's StadiumDialog
        # goalpost texture preview).
        if "goalpost_texture" not in self._preview_labels:
            return
        name = self.goalpost_texture_var.get().strip()
        self._goalpost_texture_preview_generation = getattr(self, "_goalpost_texture_preview_generation", 0) + 1
        generation = self._goalpost_texture_preview_generation
        if not name or name == "None":
            self._set_preview_image("goalpost_texture", None, self.tr("placeholder.no_preview"))
            return
        source_rx3 = resolve_goalpost_texture_rx3_path(self.app.exedir / "FSW" / "Goalpost" / "GoalpostColor", name)
        if source_rx3 is None:
            self._set_preview_image("goalpost_texture", None, self.tr("placeholder.no_preview"))
            return
        self._set_preview_image("goalpost_texture", None, self.tr("dialog.kitmix.loading"))

        def worker() -> None:
            try:
                png_path = self.app.stadium_runtime.render_goalpost_texture_preview(source_rx3, cache_key=name)
                error = None
            except Exception as exc:  # noqa: BLE001 - surfaced as a preview placeholder
                png_path, error = None, exc
            self.after(0, lambda: self._apply_goalpost_texture_preview_result(generation, png_path, error))

        threading.Thread(target=worker, daemon=True).start()

    def _apply_goalpost_texture_preview_result(self, generation: int, png_path, error) -> None:
        if getattr(self, "_destroyed", False):
            return  # this tab/dialog was closed while the render subprocess was still running
        if getattr(self, "_goalpost_texture_preview_generation", 0) != generation:
            return  # a newer selection superseded this one while the worker ran
        if error is not None or png_path is None:
            self._set_preview_image("goalpost_texture", None, self.tr("dialog.kitmix.preview_error"))
            return
        self._set_preview_image("goalpost_texture", png_path, self.tr("dialog.kitmix.preview_error"))

    def _build_net_editor(self) -> None:
        self.down_var = tk.StringVar(value=self.NET_DEFAULTS["down"])
        self.high_var = tk.StringVar(value=self.NET_DEFAULTS["high"])
        self.rig_var = tk.StringVar(value=self.NET_DEFAULTS["rig"])
        self.shape_var = tk.StringVar(value=self.SHAPE_VALUE_TO_LABEL[self.NET_DEFAULTS["shape"]])
        self.tension_var = tk.StringVar(value=self.NET_DEFAULTS["tension"])
        self._add_entry_row(self.body, 0, "Down Deep", self.down_var)
        self._add_entry_row(self.body, 1, "High Deep", self.high_var)
        self._add_combo_row(self.body, 2, "Rig", self.rig_var, [str(i) for i in range(0, 11)])
        shape_combo = self._add_combo_row(self.body, 3, "Shape", self.shape_var, self.SHAPE_CHOICES)
        shape_combo.configure(state="readonly")  # only square(0)/triangle(1) are valid in-engine
        self._add_combo_row(self.body, 4, "Tension", self.tension_var, ["0", "1", "2"])

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

    def _available_entrance_choices(self) -> list[str]:
        """Chants folders that hold the exact `Entrance.mp3` the entrance
        runtime plays -- the other folders could never produce a track here.
        (The combobox stays editable, so a folder still being set up can be typed.)"""
        base = self.app.exedir / (self.spec.directory or "")
        return [name for name in self._available_choices() if (base / name / "Entrance.mp3").is_file()]

    def _build_entrance_editor(self) -> None:
        """[tournamententrance]/[roundentrance]: `folder,volume,delay`, the same
        folder/volume/delay a team's [chantsid] line carries for its entrance
        (see TeamEntranceRuntime._parse_competition_values). Reuses the chants
        folder variable so the chants audio preview panel works unchanged."""
        self.chants_folder_var = tk.StringVar(value=self.CHANTS_DEFAULTS["folder"])
        self.entrance_volume_var = tk.StringVar(value=self.CHANTS_DEFAULTS["entrance_volume"])
        self.entrance_delay_var = tk.StringVar(value=self.CHANTS_DEFAULTS["entrance_delay"])

        self.body.grid_columnconfigure(0, weight=0)
        self.body.grid_columnconfigure(1, weight=0)
        self.body.grid_columnconfigure(2, weight=1)

        tk.Label(self.body, text=self.tr("dialog.editor.field.chants_folder"), bg=self.app.card, fg=self.app.muted, font=("Bahnschrift", 10)).grid(row=0, column=0, sticky="w", pady=4, padx=(0, 8))
        ttk.Combobox(self.body, textvariable=self.chants_folder_var, values=self._available_entrance_choices() or [""], font=("Consolas", 10), style="Server16.TCombobox").grid(row=0, column=1, columnspan=2, sticky="ew", pady=4)
        self._add_chants_field_row(self.body, 1, self.tr("dialog.editor.field.vol_entrance"), self.entrance_volume_var)
        self._add_chants_field_row(self.body, 2, self.tr("dialog.editor.field.entrance_delay"), self.entrance_delay_var, to=45.0, resolution=0.5)
        tk.Label(
            self.body,
            text=self.tr("dialog.editor.entrance_hint"),
            bg=self.app.card,
            fg=self.app.muted,
            font=("Bahnschrift", 8),
            anchor="w",
            wraplength=420,
            justify="left",
        ).grid(row=3, column=0, columnspan=3, sticky="w", pady=(6, 4))

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

    def _build_rx3_preview_panel(self, scroll_content: tk.Misc) -> None:
        # Same slot as the other preview panels (row 1 of the scrollable
        # content, below self.body). Ball/Referee/Wipe/Adboard are the only
        # specs with rx3_preview, so it is mutually exclusive with them.
        container = tk.Frame(scroll_content, bg=self.app.card)
        container.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 8))
        container.grid_columnconfigure(0, weight=1)
        self._rx3_preview = Rx3TexturePreview(container, self.app, self.tr("dialog.editor.preview.rx3_title"))
        self._rx3_preview.grid(row=0, column=0)
        # Whether the value is typed or picked from the combo/grid, it goes
        # through the same StringVar (see _build_editor_body's "simple" branch).
        self.value_var.trace_add("write", lambda *_: self._schedule_rx3_preview())
        self._refresh_rx3_preview()

    def _schedule_rx3_preview(self) -> None:
        if self._rx3_preview_job is not None:
            try:
                self.after_cancel(self._rx3_preview_job)
            except Exception:
                pass
        self._rx3_preview_job = self.after(self.RX3_PREVIEW_DELAY_MS, self._refresh_rx3_preview)

    def _match_asset_pack_dir(self, name: str) -> Path | None:
        name = (name or "").strip()
        return self.app.exedir / self.spec.directory / name if name and self.spec.directory else None

    def _refresh_rx3_preview(self) -> None:
        self._rx3_preview_job = None
        preview = self._rx3_preview
        if preview is None or getattr(self, "_destroyed", False):
            return
        pack_dir = self._match_asset_pack_dir(self.value_var.get())
        kind = self.spec.section.lower()

        def render_file(rx3: Path) -> list[Path]:
            return self.app.assets_runtime.render_match_asset_textures(kind, pack_dir, rx3)

        preview.show_pack(pack_dir, render_file)

    def _pick_match_asset(self) -> None:
        """Opens the preview grid for this Match Assets tab and writes the choice
        into the Value combo (which then refreshes the texture preview like any
        dropdown change). Re-reads the folders so a pack added while this editor
        was open still shows up. Cancelling leaves the value untouched."""
        base = self.app.exedir / (self.spec.directory or "")
        section = self.spec.section.lower()
        items = match_asset_items(section, base, self._available_choices(), self.app.assets_runtime)
        label = self.tr(self.MATCH_ASSET_FIELD_KEYS.get(section, self.spec.title))
        dialog = AssetGridPickerDialog(self.app, label, items, current=self.value_var.get().strip())
        self.app.wait_window(dialog)
        if dialog.result is not None:
            self.value_var.set(dialog.result)

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

    def _add_combo_row(self, parent: tk.Misc, row: int, label: str, variable: tk.StringVar, values: list[str], picker=None):
        """`picker`, when given, adds a small button right of the combo that
        calls it (used to open AssetGridPickerDialog). The button is reachable
        as `combo.picker_button` so callers can enable/disable it with the combo."""
        tk.Label(parent, text=label, bg=self.app.card, fg=self.app.muted, font=("Bahnschrift", 10)).grid(row=row, column=0, sticky="w", pady=4, padx=(0, 10))
        if picker is None:
            combo = ttk.Combobox(parent, textvariable=variable, values=values, font=("Consolas", 10), style="Server16.TCombobox")
            combo.grid(row=row, column=1, sticky="ew", pady=4)
        else:
            # Combo + button share column 1 through a wrapper frame so the
            # form's column layout stays identical to the rows without a picker.
            field = tk.Frame(parent, bg=self.app.card)
            field.grid(row=row, column=1, sticky="ew", pady=4)
            field.grid_columnconfigure(0, weight=1)
            combo = ttk.Combobox(field, textvariable=variable, values=values, font=("Consolas", 10), style="Server16.TCombobox")
            combo.grid(row=0, column=0, sticky="ew")
            combo.picker_button = make_picker_button(field, self.app, picker)
            combo.picker_button.grid(row=0, column=1, padx=(6, 0))
        parent.grid_columnconfigure(1, weight=1)
        return combo

    def _on_destroy(self, _event=None) -> None:
        # Guards _apply_goalpost_texture_preview_result's self.after(0, ...)
        # callback -- the 32-bit render subprocess it's waiting on can easily
        # still be running after this tab/dialog is closed.
        self._destroyed = True
        if self._refresh_job is not None:
            try:
                self.after_cancel(self._refresh_job)
            except Exception:
                pass
            self._refresh_job = None
        if self._rx3_preview_job is not None:
            try:
                self.after_cancel(self._rx3_preview_job)
            except Exception:
                pass
            self._rx3_preview_job = None
        self._stop_preview()

    def _bind_mousewheel_recursive(self, widget: tk.Misc, scroll_callback) -> None:
        """<MouseWheel> only fires on the exact widget directly under the
        cursor, so binding just the scrollable canvas/body leaves the wheel
        dead over any of its many descendant labels/combos/frames, which is
        most of the visible area. Walks the whole already-built subtree and
        binds each one, skipping tk.Listbox so a listbox with its own many
        rows (the Assigned/Available stadium lists) keeps its native
        per-widget wheel scrolling instead of being hijacked into scrolling
        this outer canvas. Call once, after the full subtree already exists
        -- widgets added later won't be covered."""
        if isinstance(widget, tk.Listbox):
            return

        def on_mousewheel(event):
            if event.delta == 0:
                return "break"
            scroll_callback(int(-1 * (event.delta / 120)))
            return "break"

        widget.bind("<MouseWheel>", on_mousewheel)
        for child in widget.winfo_children():
            self._bind_mousewheel_recursive(child, scroll_callback)

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
            self.assigned_stadium_list.delete(0, "end")
            self._stadium_params = {}
            self._stadium_goalpost = {}
            self._stadium_goalpost_texture = {}
            self._stadium_entrance_cam = {}
            self._refresh_stadium_assigned_state()
        elif self.spec.kind == "net":
            self.down_var.set(self.NET_DEFAULTS["down"])
            self.high_var.set(self.NET_DEFAULTS["high"])
            self.rig_var.set(self.NET_DEFAULTS["rig"])
            self.shape_var.set(self.SHAPE_VALUE_TO_LABEL[self.NET_DEFAULTS["shape"]])
            self.tension_var.set(self.NET_DEFAULTS["tension"])
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
        elif self.spec.kind == "entrance":
            choices = self._available_entrance_choices()
            self.chants_folder_var.set(choices[0] if choices else self.CHANTS_DEFAULTS["folder"])
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
        elif self.spec.kind == "entrance":
            self._load_entrance_value(value)
        elif self.spec.kind == "exclude":
            self.exclude_var.set(value or "excluded from stadium server")
        self.status_var.set(self.tr("dialog.editor.editing", section=self.spec.section, key=key))

    def _load_stadium_value(self, value: str) -> None:
        self.assigned_stadium_list.delete(0, "end")
        self._stadium_params = {}
        self._stadium_goalpost = {}
        self._stadium_goalpost_texture = {}
        self._stadium_entrance_cam = {}
        if value and value != "None":
            entries = StadiumRuntime._parse_stadium_entries(value)
            if not entries:
                # Malformed/too-short legacy value (fewer than 4 comma fields)
                # -- fall back to a lone stadium name with default params,
                # same graceful degradation as before this per-stadium rework.
                parts = [part.strip() for part in value.split(",") if part.strip()]
                if parts:
                    entries = [(parts[0], *self._stadium_default_triple())]
            # Keep every assigned name in its saved order, even one whose
            # folder no longer exists on disk (renamed/removed pack) --
            # dropping it here would silently lose it the moment this key is
            # opened and re-saved. The Available list on the right stays
            # limited to real, discoverable folders, since you can only *add*
            # ones that actually exist.
            for name, police, pitch, net in entries:
                self.assigned_stadium_list.insert("end", name)
                self._stadium_params[name] = (police, pitch, net)
                # [stadiumgoalpost]/[stadiumgoalposttexture] are separate
                # sections keyed by stadium name (see
                # StadiumRuntime.resolve_goalpost_sources), not part of this
                # comma-joined value -- read them independently here.
                model, texture = self._lookup_existing_goalpost_overrides(name)
                self._stadium_goalpost[name] = model
                self._stadium_goalpost_texture[name] = texture
                self._stadium_entrance_cam[name] = self._lookup_existing_entrance_cam(name)
        if self.assigned_stadium_list.size() > 0:
            self.assigned_stadium_list.selection_set(0)
            self.assigned_stadium_list.activate(0)
        self._refresh_stadium_assigned_state()

    def _load_net_value(self, value: str) -> None:
        parts = [part.strip() for part in value.split(",")]
        while len(parts) < 5:
            parts.append("")
        self.down_var.set(parts[0] or self.NET_DEFAULTS["down"])
        self.high_var.set(parts[1] or self.NET_DEFAULTS["high"])
        self.rig_var.set(parts[2] or self.NET_DEFAULTS["rig"])
        shape_raw = (parts[3] or self.NET_DEFAULTS["shape"]).strip()
        self.shape_var.set(self.SHAPE_VALUE_TO_LABEL.get(shape_raw, self.SHAPE_VALUE_TO_LABEL[self.NET_DEFAULTS["shape"]]))
        self.tension_var.set(parts[4] or self.NET_DEFAULTS["tension"])

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

    def _load_entrance_value(self, value: str) -> None:
        parts = [part.strip() for part in value.split(",")]
        parts += [""] * (3 - len(parts))
        folder, volume, delay = parts[:3]
        self.chants_folder_var.set(folder or self.CHANTS_DEFAULTS["folder"])
        self.entrance_volume_var.set(volume or self.CHANTS_DEFAULTS["entrance_volume"])
        self.entrance_delay_var.set(delay or self.CHANTS_DEFAULTS["entrance_delay"])

    def _compose_value(self) -> str:
        if self.spec.kind == "simple":
            return self.value_var.get().strip()
        if self.spec.kind == "entrance":
            folder = self.chants_folder_var.get().strip()
            if not folder:
                # An empty folder would save ",0.16,7.0": nothing to play.
                # Returning "" makes save_entry() warn instead of writing it.
                return ""
            return ",".join(
                [
                    folder,
                    self.entrance_volume_var.get().strip() or self.CHANTS_DEFAULTS["entrance_volume"],
                    self.entrance_delay_var.get().strip() or self.CHANTS_DEFAULTS["entrance_delay"],
                ]
            )
        if self.spec.kind == "stadium":
            names = list(self.assigned_stadium_list.get(0, "end"))
            if not names:
                return "None"
            fields: list[str] = []
            for name in names:
                police, pitch, net = self._stadium_params.get(name, self._stadium_default_triple())
                fields.extend([name, police, pitch, net])
            return ",".join(fields)
        if self.spec.kind == "net":
            return ",".join(
                [
                    self.down_var.get().strip(),
                    self.high_var.get().strip(),
                    self.rig_var.get().strip(),
                    self.SHAPE_LABEL_TO_VALUE.get(self.shape_var.get().strip(), self.NET_DEFAULTS["shape"]),
                    self.tension_var.get().strip(),
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
        # All delete_key() calls for this save cycle MUST run before ANY
        # write() -- IniFile/SessionIniFile.delete_key() unconditionally
        # reloads from disk first (see ini_file.py's own "Force reload from
        # disk" comment), which silently discards any not-yet-saved write()
        # made earlier in this same cycle. Confirmed live 2026-09-11: saving
        # a stadium whose goalpost model/texture combo was left at "None"
        # (the common case -- most stadiums only override one of the two)
        # triggered delete_key() for that category, which wiped out the
        # [stadium]/[comp] write two lines below and/or the OTHER category's
        # own write, all silently -- nothing in this section ever actually
        # reached disk. Splitting into a delete-only pass (here, before
        # anything is written) and a write-only pass (below, after) fixes it
        # regardless of which categories happen to be set/unset.
        if self.spec.kind == "stadium":
            self._clear_stale_stadium_goalpost_overrides()
        self.app.settings_ini.write(key, value, self.spec.section)
        if self.spec.kind == "stadium":
            self._write_stadium_goalpost_overrides()
        self.app.settings_ini.save()
        self.selected_key = key
        self.status_var.set(self.tr("dialog.editor.saved", section=self.spec.section, key=key))
        self.reload_entries()
        self._apply_runtime()

    def _clear_stale_stadium_goalpost_overrides(self) -> None:
        """The delete_key() half of persisting self._stadium_goalpost/
        _stadium_goalpost_texture into [stadiumgoalpost]/
        [stadiumgoalposttexture] (see StadiumRuntime.resolve_goalpost_sources)
        -- kept as its own pass, called before the main [stadium]/[comp]
        write and before _write_stadium_goalpost_overrides, so its forced
        disk reloads never discard a write not yet saved this cycle (see the
        ordering comment in save_entry). Deliberately never deletes an
        override for a name no longer in this key's assigned list -- the
        same stadium could still be referenced by another team's own
        [stadium] assignment, and these sections are shared by name, not
        owned by any single team's entry (same convention already used by
        [stadiumnetname]/[scoreboardstdname], which also aren't cleaned up
        when a team stops referencing a stadium name). _stadium_add_selected/
        _stadium_replace_selected already seed both dicts from the current
        on-disk value for any name entering them for the first time this
        session (_lookup_existing_goalpost_overrides), so a plain "None"
        reaching this loop for an untouched entry reflects a real absence,
        not a stale default about to clobber someone else's override."""
        for name, goalpost in self._stadium_goalpost.items():
            if not goalpost or goalpost == "None":
                self.app.settings_ini.delete_key(name, "stadiumgoalpost")
        for name, texture in self._stadium_goalpost_texture.items():
            if not texture or texture == "None":
                self.app.settings_ini.delete_key(name, "stadiumgoalposttexture")
        for name, entrance_cam in self._stadium_entrance_cam.items():
            if not entrance_cam or entrance_cam == "None":
                self.app.settings_ini.delete_key(name, "stadiumentrancecam")

    def _write_stadium_goalpost_overrides(self) -> None:
        """The write() half -- see _clear_stale_stadium_goalpost_overrides,
        which must run first in the same save cycle (before this call and
        before the main [stadium]/[comp] write)."""
        for name, goalpost in self._stadium_goalpost.items():
            if goalpost and goalpost != "None":
                self.app.settings_ini.write(name, goalpost, "stadiumgoalpost")
        for name, texture in self._stadium_goalpost_texture.items():
            if texture and texture != "None":
                self.app.settings_ini.write(name, texture, "stadiumgoalposttexture")
        for name, entrance_cam in self._stadium_entrance_cam.items():
            if entrance_cam and entrance_cam != "None":
                self.app.settings_ini.write(name, entrance_cam, "stadiumentrancecam")

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
        if self.spec.kind in ("chants", "entrance"):
            folder = self.chants_folder_var.get().strip()
            return base / folder if folder else None
        if self.spec.kind == "simple":
            value = self.value_var.get().strip()
            return base / value if value else None
        if self.spec.kind == "stadium":
            selection = self.assigned_stadium_list.curselection()
            if selection:
                return base / self.assigned_stadium_list.get(selection[0])
            if self.assigned_stadium_list.size() > 0:
                return base / self.assigned_stadium_list.get(0)
            return None
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
        SectionSpec("stadium", "dialog.editor.choice.team_stadiums", kind="stadium", directory="StadiumGBD", key_is_team_id=True),
        SectionSpec("comp", "dialog.editor.choice.competition_stadiums", kind="stadium", directory="StadiumGBD", key_is_round_id=True, key_is_tournament_id=True),
        SectionSpec("stadiumnetname", "dialog.editor.choice.net_by_stadium_name", kind="net", directory="StadiumGBD", key_stadium_picker=True),
        SectionSpec("stadiumnetid", "dialog.editor.choice.net_by_stadium_id", kind="net", key_is_stadium_id=True),
        SectionSpec("scoreboardstdname", "dialog.editor.choice.scoreboard_stadium_name", kind="scoreboardstdname", directory="StadiumGBD", key_stadium_picker=True),
        SectionSpec("stadiumgoalpost", "dialog.editor.choice.goalpost_models_by_stadium_name", kind="simple", directory="FSW\\Goalpost\\GoalpostModel", key_stadium_picker=True),
        SectionSpec("stadiumgoalposttexture", "dialog.editor.choice.goalpost_textures_by_stadium_name", kind="simple", directory="FSW\\Goalpost\\GoalpostColor", key_stadium_picker=True),
        SectionSpec("stadiumentrancecam", "dialog.editor.choice.entrance_cams_by_stadium_name", kind="simple", directory="FSW\\Camera\\EntranceScene", key_stadium_picker=True),
        SectionSpec("exclude", "dialog.editor.choice.excluded_competitions", kind="exclude", key_is_round_id=True, key_is_tournament_id=True),
    ]


def asset_specs() -> list[SectionSpec]:
    return [
        SectionSpec("Scoreboard", "dialog.editor.choice.competition_scoreboards", kind="simple", directory="ScoreBoardGBD", key_is_round_id=True, key_is_tournament_id=True),
        SectionSpec("TVLogo", "dialog.editor.choice.competition_tvlogos", kind="simple", directory="TVLogoGBD", key_is_round_id=True, key_is_tournament_id=True),
        SectionSpec("HomeTeamScoreBoard", "dialog.editor.choice.home_team_scoreboards", kind="simple", directory="ScoreBoardGBD", key_is_team_id=True),
        SectionSpec("HomeTeamTvLogo", "dialog.editor.choice.home_team_tvlogos", kind="simple", directory="TVLogoGBD", key_is_team_id=True),
        SectionSpec("movies", "dialog.editor.choice.competition_movies", kind="simple", directory="MoviesGBD", key_is_round_id=True, key_is_tournament_id=True),
        SectionSpec("TeamMovies", "dialog.editor.choice.team_movies", kind="simple", directory="MoviesGBD", key_is_team_id=True),
        SectionSpec("DerbyMatch", "dialog.editor.choice.derby_movies", kind="simple", directory="MoviesGBD", key_is_derby=True),
        SectionSpec("kitsid", "dialog.editor.choice.kits_ids", kind="simple", directory="FSW\\Kits", key_is_team_id=True),
        SectionSpec("ball", "dialog.editor.choice.competition_balls", kind="simple", directory="FSW\\balls", key_is_round_id=True, rx3_preview=True),
        SectionSpec("referee", "dialog.editor.choice.competition_referees", kind="simple", directory="FSW\\referee", key_is_round_id=True, rx3_preview=True),
        SectionSpec("wipe", "dialog.editor.choice.competition_wipes", kind="simple", directory="FSW\\wipe", key_is_round_id=True, rx3_preview=True),
        SectionSpec("adboard", "dialog.editor.choice.competition_adboards", kind="simple", directory="FSW\\adboards", key_is_round_id=True, rx3_preview=True),
    ]


def audio_specs() -> list[SectionSpec]:
    return [
        SectionSpec("chantsid", "dialog.editor.choice.chants_ids", kind="chants", directory="FSW\\Chants", recursive=True),
        SectionSpec("tournamententrance", "dialog.editor.choice.tournament_entrance", kind="entrance", directory="FSW\\Chants", recursive=True, key_is_tournament_id=True),
        SectionSpec("roundentrance", "dialog.editor.choice.round_entrance", kind="entrance", directory="FSW\\Chants", recursive=True, key_is_round_id=True),
    ]


def _grouped(specs: list[SectionSpec], layout: list[tuple[str, tuple[str, ...]]]) -> list[SpecGroup]:
    """Arranges `specs` into the top-level tabs described by `layout`
    ((group title, section names)). A section missing from `specs` raises
    KeyError right away; one missing from `layout` would silently vanish from
    the editor, which tests/test_settings_editor.py guards against."""
    by_section = {spec.section: spec for spec in specs}
    return [SpecGroup(tuple(by_section[name] for name in sections), title) for title, sections in layout]


def stadium_tab_groups() -> list[SpecGroup]:
    return _grouped(
        stadium_specs(),
        [
            ("dialog.editor.group.stadiums", ("stadium", "comp")),
            ("dialog.editor.group.nets", ("stadiumnetname", "stadiumnetid")),
            ("dialog.editor.group.goalposts", ("stadiumgoalpost", "stadiumgoalposttexture")),
            ("", ("scoreboardstdname",)),
            ("", ("stadiumentrancecam",)),
            ("", ("exclude",)),
        ],
    )


def asset_tab_groups() -> list[SpecGroup]:
    return _grouped(
        asset_specs(),
        [
            ("dialog.editor.group.scoreboards", ("Scoreboard", "HomeTeamScoreBoard")),
            ("dialog.editor.group.tvlogos", ("TVLogo", "HomeTeamTvLogo")),
            ("dialog.editor.group.movies", ("movies", "TeamMovies", "DerbyMatch")),
            ("", ("kitsid",)),
            ("dialog.editor.group.match_assets", ("ball", "referee", "wipe", "adboard")),
        ],
    )
