"""Plugins tab: the FIFA Plugin Loader's ``plugins\\*.asi`` with ON/OFF, a ⚙ ini editor and a
"loaded" icon while FIFA runs. Logic lives in plugin_loader.py / plugin_ini.py; this mixin only
builds the widgets and wires the buttons. Spec: docs/superpowers/specs/2026-11-20-plugins-tab-design.md.

All of it runs on the Tk thread (small file I/O only). The loaded icons come from the OS module list
of the FIFA process (``Memory.list_module_paths``), never from FIFA's memory.
"""
from __future__ import annotations

import os
import sys
import tkinter as tk
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path
from tkinter import messagebox, ttk

from . import plugin_loader

# The loader loads every plugin while FIFA starts; check a while after FIFA is detected. Tune live.
PLUGINS_LOADED_CHECK_DELAY_MS = 10000

_ICON_LOADED = "✔"      # ✔
_ICON_NOT_LOADED = "✖"  # ✖
_ICON_SETTINGS = "⚙"    # ⚙


@dataclass(frozen=True)
class PluginRow:
    name: str
    file_name: str
    enabled: bool
    conflict: bool
    has_ini: bool
    loaded: bool | None
    ini_path: Path | None = None


@dataclass(frozen=True)
class PluginsView:
    state: str                  # "no_game_dir" | "ok"
    loader_installed: bool
    folder: Path | None
    rows: list[PluginRow] = field(default_factory=list)


class PluginsTabMixin:
    # ---- state (no Tk) ---------------------------------------------------------------------
    def _plugins_entries(self) -> list[plugin_loader.PluginEntry]:
        game_dir = self._extender_game_dir()
        return plugin_loader.scan(game_dir) if game_dir is not None else []

    def _plugins_entry(self, name: str) -> plugin_loader.PluginEntry | None:
        return next((entry for entry in self._plugins_entries() if entry.name == name), None)

    def _plugins_view_model(self) -> PluginsView:
        game_dir = self._extender_game_dir()
        if game_dir is None:
            return PluginsView(state="no_game_dir", loader_installed=False, folder=None)
        entries = plugin_loader.scan(game_dir)
        states: dict[str, bool | None] = {}
        memory = getattr(self, "memory", None)
        # Icons only once the post-start delay has passed: before that the loader may still be
        # loading plugins and a not-yet-loaded one would show a false ✖.
        if (self._plugins_game_running and self._plugins_icons_ready
                and memory is not None and memory.is_open()):
            states = plugin_loader.loaded_states(entries, memory.list_module_paths(), self._plugins_toggled)
        rows = [
            PluginRow(
                name=entry.name,
                file_name=entry.path.name,
                enabled=entry.enabled,
                conflict=entry.conflict,
                has_ini=entry.ini_path is not None,
                loaded=states.get(entry.name),
                ini_path=entry.ini_path,
            )
            for entry in entries
        ]
        return PluginsView(
            state="ok",
            loader_installed=plugin_loader.is_loader_installed(game_dir),
            folder=plugin_loader.plugins_dir(game_dir),
            rows=rows,
        )

    def on_plugins_game_running(self, running: bool) -> None:
        """poll_process, every tick: on FIFA start forget this session's toggles and check the
        loaded icons once the loader has had time to load everything; on FIFA exit drop the icons."""
        if running == self._plugins_game_running:
            return
        self._plugins_game_running = running
        self._plugins_icons_ready = False
        # A delayed check from an earlier FIFA session must not enable this session's icons.
        self._plugins_session = getattr(self, "_plugins_session", 0) + 1
        if running:
            self._plugins_toggled.clear()
            session = self._plugins_session
            self.after(PLUGINS_LOADED_CHECK_DELAY_MS, lambda: self._on_plugins_icons_ready(session))
        else:
            self.refresh_plugins_tab()

    def _on_plugins_icons_ready(self, session: int) -> None:
        if session != getattr(self, "_plugins_session", 0) or not self._plugins_game_running:
            return
        self._plugins_icons_ready = True
        self.refresh_plugins_tab()

    # ---- actions ---------------------------------------------------------------------------
    def _toggle_plugin(self, name: str) -> None:
        entry = self._plugins_entry(name)
        if entry is None:
            self.refresh_plugins_tab()
            return
        try:
            new_path = plugin_loader.set_enabled(entry, not entry.enabled)
        except OSError as exc:
            self.log(f"Plugins: could not rename {entry.path.name}", exc, exc_info=sys.exc_info())
            messagebox.showerror(self.tr("tab.plugins"), self.tr("error.plugins.toggle", error=exc), parent=self._window())
        else:
            self.log(f"Plugins: {entry.path.name} -> {new_path.name}")
            if self._plugins_game_running:
                self._plugins_toggled.add(entry.name)
        self.refresh_plugins_tab()

    def _open_plugin_ini(self, name: str) -> None:
        from .dialogs import PluginIniDialog

        entry = self._plugins_entry(name)
        if entry is None or entry.ini_path is None:
            self.refresh_plugins_tab()
            return
        try:
            dialog = PluginIniDialog(self, entry.name, entry.ini_path)
        except OSError as exc:
            self.log(f"Plugins: could not open {entry.ini_path}", exc, exc_info=sys.exc_info())
            messagebox.showerror(self.tr("tab.plugins"), self.tr("dialog.plugins.ini.error_save", error=exc),
                                 parent=self._window())
            return
        self.wait_window(dialog)
        self.refresh_plugins_tab()

    def _open_plugins_folder(self) -> None:
        game_dir = self._extender_game_dir()
        if game_dir is None:
            return
        folder = plugin_loader.plugins_dir(game_dir)
        try:
            folder.mkdir(exist_ok=True)
            os.startfile(folder)  # type: ignore[attr-defined]
        except OSError as exc:
            self.log(f"Plugins: could not open {folder}", exc, exc_info=sys.exc_info())

    def _open_loader_thread(self) -> None:
        webbrowser.open(plugin_loader.LOADER_THREAD_URL)

    # ---- widgets ---------------------------------------------------------------------------
    def _build_plugins_tab(self) -> None:
        from .app_ui import _ToolTip

        self._plugins_tooltip_cls = _ToolTip
        style = ttk.Style(self)
        style.configure("Server16.PluginAccent.TButton", background=self.accent, foreground="#0b1220")
        style.map("Server16.PluginAccent.TButton", background=[("active", "#7fd3ff")])
        style.configure("Server16.PluginOn.TButton", background="#1f4d33", foreground=self.success, padding=(12, 4))
        style.map("Server16.PluginOn.TButton", background=[("active", "#27613f")],
                  foreground=[("disabled", self.muted)])
        style.configure("Server16.PluginOff.TButton", padding=(12, 4))
        style.map("Server16.PluginOff.TButton", foreground=[("disabled", self.muted)])

        # Buttons and notes stay fixed at the top; only the plugin list inside the card scrolls.
        outer = tk.Frame(self.plugins_tab, bg=self.bg)
        outer.pack(fill="both", expand=True, padx=10, pady=10)

        top = tk.Frame(outer, bg=self.bg)
        top.pack(fill="x", pady=(0, 8))
        self._plugins_download_button = ttk.Button(
            top, text=self.tr("button.plugins.download_loader"), command=self._open_loader_thread)
        self._plugins_download_button.pack(side="left")
        self._plugins_folder_button = ttk.Button(
            top, text=self.tr("button.plugins.open_folder"), command=self._open_plugins_folder)
        self._plugins_folder_button.pack(side="left", padx=(6, 0))

        self._plugins_status_label = tk.Label(outer, text="", bg=self.bg, fg=self.gold, font=("Bahnschrift", 10, "bold"),
                                              anchor="w", justify="left", wraplength=760)
        self._plugins_note_label = tk.Label(outer, text=self.tr("label.plugins.persistent_note"), bg=self.bg,
                                            fg=self.muted, font=("Bahnschrift", 9), anchor="w", justify="left",
                                            wraplength=760)
        self._plugins_note_label.pack(fill="x", pady=(0, 10))

        card = self._card(outer, "card.plugins.title", "card.plugins.subtitle")
        card.pack(fill="both", expand=True)
        self._plugins_card = card
        list_host = tk.Frame(card, bg=self.card)
        list_host.pack(fill="both", expand=True, padx=12, pady=(6, 12))
        canvas = tk.Canvas(list_host, bg=self.card, highlightthickness=0, bd=0)
        scrollbar = ttk.Scrollbar(list_host, orient="vertical", command=canvas.yview,
                                  style="Server16.Vertical.TScrollbar")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        self._plugins_canvas = canvas
        self._plugins_scrollbar = scrollbar
        self._plugins_rows_frame = tk.Frame(canvas, bg=self.card)
        # Columns: 0 toggle, 1 settings, 2 loaded icon, 3 name. Controls lead the row so they stay in a
        # fixed column (easy to scan in a long list) and the name takes the remaining width.
        self._plugins_rows_frame.grid_columnconfigure(3, weight=1)
        window = canvas.create_window((0, 0), window=self._plugins_rows_frame, anchor="nw")
        self._plugins_rows_frame.bind("<Configure>", lambda _e: self._update_plugins_scroll())
        canvas.bind("<Configure>", lambda e: (canvas.itemconfig(window, width=e.width),
                                              self._update_plugins_scroll()))
        canvas.bind_all("<MouseWheel>", self._on_plugins_mousewheel, add="+")
        self.refresh_plugins_tab()

    def _plugins_list_overflows(self) -> bool:
        canvas = self._plugins_canvas
        return self._plugins_rows_frame.winfo_reqheight() > canvas.winfo_height() > 1

    def _update_plugins_scroll(self) -> None:
        """Scroll region follows the rows; the scrollbar is shown only while the list doesn't fit."""
        canvas = self._plugins_canvas
        canvas.configure(scrollregion=canvas.bbox("all"))
        if self._plugins_list_overflows():
            if not self._plugins_scrollbar.winfo_manager():
                self._plugins_scrollbar.pack(side="right", fill="y", before=canvas)
        else:
            if self._plugins_scrollbar.winfo_manager():
                self._plugins_scrollbar.pack_forget()
            canvas.yview_moveto(0)

    def _on_plugins_mousewheel(self, event) -> None:
        if self.tabview is None or getattr(self, "_plugins_canvas", None) is None:
            return
        try:
            current = self.tabview.nametowidget(self.tabview.select())
        except Exception:
            return
        if current is not self.plugins_tab:
            return
        if not self._event_widget_belongs_to(event, self._plugins_canvas, self._plugins_rows_frame):
            return
        if self._plugins_list_overflows():
            self._plugins_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def refresh_plugins_tab(self) -> None:
        rows_frame = getattr(self, "_plugins_rows_frame", None)
        if rows_frame is None:
            return
        try:
            view = self._plugins_view_model()
        except Exception as exc:
            self.log("Plugins: could not read the plugins folder", exc, exc_info=sys.exc_info())
            return
        for child in rows_frame.winfo_children():
            child.destroy()

        status = ""
        if view.state == "no_game_dir":
            status = self.tr("status.plugins.no_game_dir")
        elif not view.loader_installed:
            status = self.tr("status.plugins.loader_missing")
        if status:
            self._plugins_status_label.configure(text=status)
            self._plugins_status_label.pack(fill="x", pady=(0, 6), before=self._plugins_note_label)
        else:
            self._plugins_status_label.pack_forget()
        accent = view.state == "ok" and not view.loader_installed
        self._plugins_download_button.configure(style="Server16.PluginAccent.TButton" if accent else "TButton")
        self._plugins_folder_button.state(["disabled"] if view.state == "no_game_dir" else ["!disabled"])

        if view.state == "no_game_dir":
            self._plugins_card.pack_forget()
            return
        if not self._plugins_card.winfo_manager():
            self._plugins_card.pack(fill="both", expand=True)
        if not view.rows:
            tk.Label(rows_frame, text=self.tr("status.plugins.empty", path=view.folder), bg=self.card, fg=self.muted,
                     font=("Bahnschrift", 10), anchor="w").grid(row=0, column=0, columnspan=4, sticky="w")
            return
        tooltip = self._plugins_tooltip_cls
        for index, row in enumerate(view.rows):
            icon, colour = "", self.muted
            if row.loaded is True:
                icon, colour = _ICON_LOADED, self.success
            elif row.loaded is False:
                icon, colour = _ICON_NOT_LOADED, self.error
            tk.Label(rows_frame, text=icon, width=2, bg=self.card, fg=colour,
                     font=("Segoe UI Symbol", 11, "bold")).grid(row=index, column=2, padx=(10, 4), pady=3)
            name_label = tk.Label(rows_frame, text=row.name, bg=self.card, fg=self.fg if row.enabled else self.muted,
                                  font=("Bahnschrift", 11), anchor="w")
            name_label.grid(row=index, column=3, sticky="w", pady=3)
            tooltip(name_label, lambda f=row.file_name: f, self.card, self.fg, "#243654")

            toggle = ttk.Button(
                rows_frame,
                text=self.tr("button.plugins.on" if row.enabled else "button.plugins.off"),
                style="Server16.PluginOn.TButton" if row.enabled else "Server16.PluginOff.TButton",
                command=lambda n=row.name: self._toggle_plugin(n),
                width=6,
            )
            toggle.grid(row=index, column=0, padx=(0, 6), pady=3)
            if row.conflict:
                toggle.state(["disabled"])
                tooltip(toggle, lambda n=row.name: self.tr("tooltip.plugins.conflict", name=n),
                        self.card, self.fg, "#243654")

            gear = ttk.Button(rows_frame, text=_ICON_SETTINGS, style="Server16.Picker.TButton", width=3,
                              command=lambda n=row.name: self._open_plugin_ini(n))
            gear.grid(row=index, column=1, pady=3)
            if row.has_ini:
                tooltip(gear, lambda p=row.ini_path: f"{self.tr('tooltip.plugins.settings')}\n{p}",
                        self.card, self.fg, "#243654")
            else:
                gear.state(["disabled"])

    def _apply_plugins_tab_localization(self) -> None:
        if getattr(self, "_plugins_rows_frame", None) is None:
            return
        self._plugins_download_button.configure(text=self.tr("button.plugins.download_loader"))
        self._plugins_folder_button.configure(text=self.tr("button.plugins.open_folder"))
        self._plugins_note_label.configure(text=self.tr("label.plugins.persistent_note"))
        self.refresh_plugins_tab()
