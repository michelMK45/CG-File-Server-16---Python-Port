from __future__ import annotations

import ctypes
import sys
import time
import threading
import webbrowser
import tkinter as tk
from tkinter import filedialog, font as tkfont, messagebox, ttk

from PIL import Image, ImageTk

from .camera_runtime import CameraPreset
from .dialogs import AboutDialog
from .file_tools import (
    gamepad_button_icon_dir,
    keyboard_button_icon_dir,
    kit_ui_placeholder_path,
    resolve_stadium_preview_path,
    rmlui_content_dir,
    stadium_preview_fallback_path,
)
from .kit_mixer import KIT_TYPES, NAME_COLOR_HEX_RE
from .settings_store import UI_ZOOM_DEFAULT, UI_ZOOM_MAX, UI_ZOOM_MIN
from .substitution_runtime import SUBSTITUTION_MAX, SUBSTITUTION_MIN, SUBSTITUTION_VALIDATED_MAX
from .update_checker import UpdateCheckResult
from .win32_types import RECT, SW_SHOWNOACTIVATE, SW_HIDE

try:
    from .d3d_injector import D3DOverlayInjector as _D3DOverlayInjector
except Exception:
    _D3DOverlayInjector = None  # type: ignore[assignment,misc]

# Kit Mixer tab — role keys (display order) and picker "kinds". "image" is used by
# jersey/shorts/crest (list = existing kit .rx3, import = loose PNG); "rx3" by the
# kit-numbers pickers (list and import are both .rx3); "dds" by the kit-UI thumbnail
# picker (list and import are both .dds).
# UI zoom — app_ui.py's zoom popup (opened via the magnifying-glass button in
# the top bar). Only Tk's own *named* fonts (which every ttk widget in this
# app implicitly uses — see _configure_theme, none of its style.configure(...)
# calls set an explicit font) reliably re-render already-displayed widgets
# when reconfigured; that is not guaranteed for a bare "tk scaling" change on
# its own. Raw tk widgets in this file all use literal font tuples instead, so
# they're rescaled individually via _ZOOM_WIDGET_FONTS, captured once after
# _build_ui() finishes building the static tree.
# Step size is kept proportional to UI_ZOOM_DEFAULT so the popup's percentage
# readout still moves in clean 10%-of-default increments now that "100%" no
# longer means the literal 1.0 multiplier (see settings_store.py).
UI_ZOOM_STEP = UI_ZOOM_DEFAULT * 0.1
UI_ZOOM_NAMED_FONTS = (
    "TkDefaultFont", "TkTextFont", "TkFixedFont", "TkMenuFont",
    "TkHeadingFont", "TkCaptionFont", "TkSmallCaptionFont",
    "TkIconFont", "TkTooltipFont",
)

KITMIX_KEEP_LABEL = "-- keep current --"
KITSIMPLE_GK_NONE_LABEL = "-- none --"
KITMIX_IMPORTED_LABEL_PREFIX = "[image] "
KITMIX_IMPORTED_RX3_LABEL_PREFIX = "[file] "
KITMIX_IMPORTED_DDS_LABEL_PREFIX = "[file] "
KITMIX_PICKER_KINDS = {
    "image": ("rx3", "img", KITMIX_IMPORTED_LABEL_PREFIX, [("Images", "*.png *.bmp *.jpg *.jpeg"), ("All files", "*.*")], "dialog.kitmix.import_image"),
    "rx3": ("rx3", "rx3", KITMIX_IMPORTED_RX3_LABEL_PREFIX, [("RX3 files", "*.rx3"), ("All files", "*.*")], "dialog.kitmix.import_rx3"),
    "dds": ("dds", "dds", KITMIX_IMPORTED_DDS_LABEL_PREFIX, [("DDS files", "*.dds"), ("All files", "*.*")], "dialog.kitmix.import_dds"),
}

# Status codes reported by SubstitutionRuntime -> locale keys shown in the Matchup Live card.
# "armed" is special-cased in _on_substitution_status to switch to the "_unverified" variant
# above SUBSTITUTION_VALIDATED_MAX.
_SUBSTITUTION_STATUS_KEYS = {
    "idle": "substitutions.status.idle",
    "invalid": "substitutions.status.invalid",
    "not_attached": "substitutions.status.fifa_not_attached",
    "unsafe_build": "substitutions.status.unsafe_build",
    "already_hooked": "substitutions.status.already_hooked",
    "alloc_failed": "substitutions.status.alloc_failed",
    "patch_failed": "substitutions.status.patch_failed",
    "waiting": "substitutions.status.waiting",
    "armed": "substitutions.status.armed",
    "armed_progress": "substitutions.status.armed_progress",
    "armed_partial": "substitutions.status.armed_partial",
    "timeout": "substitutions.status.timeout",
    "invalid_pointer": "substitutions.status.invalid_pointer",
    "write_failed": "substitutions.status.write_failed",
    "fifa_changed": "substitutions.status.fifa_changed",
}


def _find_python32(extra_dirs: list | None = None) -> list[str] | None:
    """Return a command prefix for a 32-bit Python interpreter, or None if unavailable.

    Checks bundled python32/ first, then the Windows Python Launcher, then common paths.
    Pass extra_dirs (e.g. [resource_dir, base_dir]) to locate a bundled interpreter.
    """
    import subprocess
    import glob as _glob
    import os
    from pathlib import Path as _Path

    # Bundled embeddable Python (bin/python32/python.exe)
    for d in (extra_dirs or []):
        candidate = _Path(d) / "bin" / "python32" / "python.exe"
        if candidate.exists():
            return [str(candidate)]

    # Windows Python Launcher (py -3-32)
    try:
        r = subprocess.run(
            ["py", "-3-32", "-c", "import sys; print(sys.version)"],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0:
            return ["py", "-3-32"]
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Common x86 install paths — verify pointer size to confirm 32-bit
    patterns = [
        r"C:\Python3*-32\python.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Python\Python3*-32\python.exe"),
        r"C:\Program Files (x86)\Python3*\python.exe",
    ]
    for pat in patterns:
        for match in sorted(_glob.glob(pat), reverse=True):
            try:
                r = subprocess.run(
                    [match, "-c", "import struct; print(struct.calcsize('P'))"],
                    capture_output=True, text=True, timeout=10,
                )
                if r.returncode == 0 and r.stdout.strip() == "4":
                    return [match]
            except (FileNotFoundError, subprocess.TimeoutExpired):
                continue

    return None


class UIMixin:
    """Window construction, theming, and all widget interaction — part of Server16App via multiple inheritance."""

    def _window(self) -> tk.Misc:
        return self.ui_root or self

    def _resolve_base_dir(self):
        from pathlib import Path
        if getattr(sys, "frozen", False):
            return Path(sys.executable).resolve().parent
        return Path(__file__).resolve().parent.parent

    def _resolve_resource_dir(self):
        from pathlib import Path
        bundle_dir = getattr(sys, "_MEIPASS", None)
        if bundle_dir:
            return Path(bundle_dir)
        return self.base_dir

    def _resolve_icon_path(self):
        candidates = [
            self.resource_dir / "server16.ico",
            self.base_dir / "server16.ico",
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return None

    def _apply_window_icon(self, window: tk.Misc) -> None:
        if self.icon_path is None:
            return
        icon_value = str(self.icon_path)
        try:
            window.iconbitmap(default=icon_value)
        except Exception:
            pass
        try:
            image = Image.open(self.icon_path)
            self._window_icon_image = ImageTk.PhotoImage(image)
            window.iconphoto(True, self._window_icon_image)
        except Exception:
            pass

    def _configure_theme(self) -> None:
        self.bg = "#0b1220"
        self.panel = "#111a2b"
        self.panel_alt = "#172338"
        self.card = "#0f1727"
        self.card_soft = "#152033"
        self.fg = "#e6edf3"
        self.muted = "#93a1b2"
        self.accent = "#4cc2ff"
        self.success = "#7ee787"
        self.error = "#ff7b72"
        self.gold = "#f6c177"
        self.configure(bg=self.bg)
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure(".", background=self.bg, foreground=self.fg, fieldbackground=self.panel_alt)
        style.configure("TFrame", background=self.bg)
        style.configure("TLabelframe", background=self.bg, foreground=self.fg, borderwidth=1)
        style.configure("TLabelframe.Label", background=self.bg, foreground=self.accent)
        style.configure("TLabel", background=self.bg, foreground=self.fg)
        style.configure("TButton", background=self.panel_alt, foreground=self.fg, padding=8, borderwidth=0)
        style.map("TButton", background=[("active", "#2b3442")])
        style.configure("TCheckbutton", background=self.bg, foreground=self.fg)
        style.configure(
            "Server16.TEntry",
            fieldbackground=self.panel_alt,
            foreground=self.fg,
            insertcolor=self.fg,
            bordercolor="#2a3c59",
            lightcolor=self.panel_alt,
            darkcolor=self.panel_alt,
            padding=4,
        )
        style.map(
            "Server16.TEntry",
            fieldbackground=[("disabled", self.card_soft), ("readonly", self.card_soft)],
            foreground=[("disabled", self.muted), ("!disabled", self.fg)],
        )
        style.configure(
            "Switch.TCheckbutton",
            background=self.card,
            foreground=self.fg,
            padding=(12, 6),
            indicatoron=False,
            relief="flat",
            borderwidth=1,
            focuscolor=self.card,
        )
        style.map(
            "Switch.TCheckbutton",
            background=[("selected", "#19324d"), ("active", "#223753"), ("!selected", self.card_soft)],
            foreground=[("selected", self.accent), ("!selected", self.fg)],
            bordercolor=[("selected", self.accent), ("!selected", "#2a3c59")],
        )
        style.configure(
            "Server16.TNotebook",
            background=self.bg,
            borderwidth=0,
            tabmargins=(0, 0, 0, 0),
        )
        style.configure(
            "Server16.TNotebook.Tab",
            background=self.panel,
            foreground=self.muted,
            padding=(16, 8),
            borderwidth=0,
            lightcolor=self.panel,
            darkcolor=self.panel,
        )
        style.map(
            "Server16.TNotebook.Tab",
            background=[("selected", self.card_soft), ("active", self.panel_alt)],
            foreground=[("selected", self.fg), ("active", self.fg)],
        )
        style.configure(
            "Server16.Vertical.TScrollbar",
            background=self.panel_alt,
            troughcolor=self.card_soft,
            bordercolor="#243654",
            arrowcolor=self.fg,
            darkcolor=self.panel_alt,
            lightcolor=self.panel_alt,
            arrowsize=14,
        )
        style.map(
            "Server16.Vertical.TScrollbar",
            background=[("active", "#223753"), ("pressed", "#1b3453")],
            arrowcolor=[("disabled", self.muted), ("!disabled", self.fg)],
        )
        style.configure(
            "Server16.Horizontal.TScrollbar",
            background=self.panel_alt,
            troughcolor=self.card_soft,
            bordercolor="#243654",
            arrowcolor=self.fg,
            darkcolor=self.panel_alt,
            lightcolor=self.panel_alt,
            arrowsize=14,
        )
        style.map(
            "Server16.Horizontal.TScrollbar",
            background=[("active", "#223753"), ("pressed", "#1b3453")],
            arrowcolor=[("disabled", self.muted), ("!disabled", self.fg)],
        )
        style.configure(
            "Server16.TCombobox",
            fieldbackground=self.panel_alt,
            background=self.panel_alt,
            foreground=self.fg,
            arrowcolor=self.fg,
            bordercolor="#2a3c59",
            lightcolor=self.panel_alt,
            darkcolor=self.panel_alt,
            insertcolor=self.fg,
            selectbackground="#1b3453",
            selectforeground=self.fg,
            padding=2,
        )
        style.map(
            "Server16.TCombobox",
            fieldbackground=[("readonly", self.panel_alt), ("disabled", self.card_soft)],
            background=[("readonly", self.panel_alt), ("active", self.panel_alt)],
            foreground=[("readonly", self.fg), ("disabled", self.muted), ("!disabled", self.fg)],
            arrowcolor=[("disabled", self.muted), ("!disabled", self.fg)],
            selectbackground=[("readonly", "#1b3453")],
            selectforeground=[("readonly", self.fg)],
        )
        style.configure("TCombobox", fieldbackground=self.panel_alt, background=self.panel_alt, foreground=self.fg, arrowcolor=self.fg)
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", self.panel_alt), ("disabled", self.card_soft)],
            foreground=[("readonly", self.fg), ("disabled", self.muted), ("!disabled", self.fg)],
            arrowcolor=[("disabled", self.muted), ("!disabled", self.fg)],
        )
        self.option_add("*TCombobox*Listbox.background", self.panel_alt)
        self.option_add("*TCombobox*Listbox.foreground", self.fg)
        self.option_add("*TCombobox*Listbox.selectBackground", "#1b3453")
        self.option_add("*TCombobox*Listbox.selectForeground", self.fg)
        self.option_add("*TCombobox*Listbox.font", "Consolas 10")
        style.configure("Accent.Horizontal.TProgressbar", troughcolor=self.card_soft, background=self.accent, borderwidth=0, lightcolor=self.accent, darkcolor=self.accent)

    def _build_ui(self) -> None:
        root = tk.Toplevel(self)
        root.title(self.tr("app.title"))
        root.geometry("1024x680")
        root.minsize(980, 640)
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.configure(bg=self.bg)
        self._apply_window_icon(root)
        self.ui_root = root

        top = tk.Frame(root, bg=self.bg, padx=10, pady=10)
        top.pack(fill="x")
        self._top_bar = top
        self.locate_fifa_button = ttk.Button(top, text=self.tr("button.locate_fifa_exe"), command=self.select_fifa_exe)
        self.locate_fifa_button.pack(side="left", padx=6)
        self.launch_fifa_button = ttk.Button(top, text=self.tr("button.launch_fifa"), command=self.launch_fifa)
        self.launch_fifa_button.pack(side="left", padx=6)
        self.assign_scoreboard_button = ttk.Button(top, text=self.tr("button.assign_scoreboard"), command=self.assign_scoreboard)
        self.assign_scoreboard_button.pack(side="left", padx=6)
        self.assign_movie_button = ttk.Button(top, text=self.tr("button.assign_movie"), command=self.assign_movie)
        self.assign_movie_button.pack(side="left", padx=6)
        self.exclude_competition_button = ttk.Button(top, text=self.tr("button.exclude_competition"), command=self.exclude_competition)
        self.exclude_competition_button.pack(side="left", padx=6)
        self.zoom_toggle_button = ttk.Button(top, text="\U0001F50D", width=3, command=self._toggle_zoom_popup)
        self.zoom_toggle_button.pack(side="right", padx=(10, 6))
        language_host = tk.Frame(top, bg=self.bg)
        language_host.pack(side="right", padx=(10, 6))
        self.language_label = tk.Label(language_host, text=self.tr("label.language"), bg=self.bg, fg=self.muted, font=("Bahnschrift", 9, "bold"))
        self.language_label.pack(side="left", padx=(0, 6))
        self.language_combo = ttk.Combobox(
            language_host,
            state="readonly",
            textvariable=self.language_var,
            values=self._language_combo_values(),
            width=16,
            style="Server16.TCombobox",
        )
        self.language_combo.pack(side="left")
        self.language_combo.bind("<<ComboboxSelected>>", self._on_language_selected)
        self.language_var.set(self._language_combo_value())
        self.about_button = ttk.Button(top, text=self.tr("button.about"), command=self._show_about)
        self.about_button.pack(side="right", padx=(0, 6))
        self.check_update_button = ttk.Button(top, text=self.tr("button.check_update"), command=self.check_updates)
        self.check_update_button.pack(side="right", padx=(0, 6))

        header = tk.Frame(root, bg=self.bg, padx=10)
        header.pack(fill="x")
        banner = tk.Frame(header, bg=self.panel, bd=0, highlightthickness=1, highlightbackground="#22314b")
        banner.pack(fill="x")
        self.banner_title_label = tk.Label(
            banner,
            text=self.tr("banner.control_room"),
            bg=self.panel,
            fg=self.gold,
            font=("Bahnschrift", 11, "bold"),
            padx=14,
            pady=8,
        )
        self.banner_title_label.pack(side="left")
        self.page_banner = tk.Label(
            banner,
            text="-",
            bg=self.panel,
            fg=self.fg,
            font=("Consolas", 10),
            padx=10,
            pady=8,
        )
        self.page_banner.pack(side="left")
        self.status_pill = tk.Label(
            banner,
            text=self.status_text("waiting_fifa"),
            bg="#1a2740",
            fg=self.accent,
            font=("Bahnschrift", 9, "bold"),
            padx=10,
            pady=5,
        )
        self.status_pill.pack(side="right", padx=10, pady=6)
        help_bar = tk.Frame(header, bg=self.bg)
        help_bar.pack(fill="x", pady=(8, 0))
        self.help_label = tk.Label(
            help_bar,
            text=self.tr("help.overlay_toggle"),
            bg=self.bg,
            fg=self.muted,
            font=("Bahnschrift", 9),
            anchor="w",
        )
        self.help_label.pack(side="left")

        self.tabview = ttk.Notebook(root, style="Server16.TNotebook")
        self.tabview.pack(fill="both", expand=True, padx=10, pady=10)
        self.dashboard_tab = tk.Frame(self.tabview, bg=self.bg)
        self.logs_tab = tk.Frame(self.tabview, bg=self.bg)
        self.audio_tab = tk.Frame(self.tabview, bg=self.bg)
        self.camera_tab = tk.Frame(self.tabview, bg=self.bg)
        self.setup_tab = tk.Frame(self.tabview, bg=self.bg)
        self.kits_tab = tk.Frame(self.tabview, bg=self.bg)
        self.tabview.add(self.dashboard_tab, text=self.tr("tab.dashboard"))
        self.tabview.add(self.kits_tab, text=self.tr("tab.kits"))
        self.tabview.add(self.audio_tab, text=self.tr("tab.chants"))
        self.tabview.add(self.camera_tab, text=self.tr("tab.camera"))
        self.tabview.add(self.setup_tab, text=self.tr("tab.setup"))
        self.tabview.add(self.logs_tab, text=self.tr("tab.logs"))
        self.tabview.select(self.dashboard_tab)
        self.tabview.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        self._build_setup_notice()

        dashboard_host = tk.Frame(self.dashboard_tab, bg=self.bg)
        self._dashboard_host = dashboard_host
        dashboard_host.pack(fill="both", expand=True, padx=10, pady=10)
        self.dashboard_canvas = tk.Canvas(dashboard_host, bg=self.bg, highlightthickness=0, bd=0)
        self.dashboard_scrollbar = ttk.Scrollbar(
            dashboard_host,
            orient="vertical",
            command=self.dashboard_canvas.yview,
            style="Server16.Vertical.TScrollbar",
        )
        self.dashboard_canvas.configure(yscrollcommand=self.dashboard_scrollbar.set)
        self.dashboard_scrollbar.pack(side="right", fill="y")
        self.dashboard_canvas.pack(side="left", fill="both", expand=True)
        dashboard = tk.Frame(self.dashboard_canvas, bg=self.bg, padx=10, pady=10)
        self.dashboard_content = dashboard
        self.dashboard_window_id = self.dashboard_canvas.create_window((0, 0), window=dashboard, anchor="nw")
        dashboard.bind("<Configure>", self._on_dashboard_configure)
        self.dashboard_canvas.bind("<Configure>", self._on_dashboard_canvas_configure)
        # add="+" — multiple tabs each bind_all their own scoped mousewheel handler
        # (see _on_dashboard_mousewheel / _on_setup_mousewheel); without "+" each new
        # bind_all replaces the previous one on the shared "all" bindtag, leaving only
        # the most-recently-built tab's canvas able to scroll.
        self.dashboard_canvas.bind_all("<MouseWheel>", self._on_dashboard_mousewheel, add="+")
        dashboard.grid_columnconfigure(0, weight=3)
        dashboard.grid_columnconfigure(1, weight=2)
        dashboard.grid_rowconfigure(0, weight=1)

        left = tk.Frame(dashboard, bg=self.bg)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        left.grid_columnconfigure(0, weight=1)

        self._build_matchup_card(left, 0)
        self._build_match_card(left, 1)
        self._build_assets_card(left, 2)

        right = tk.Frame(dashboard, bg=self.bg)
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_columnconfigure(0, weight=1)
        self._build_stadium_card(right, 0)
        self._build_modules_card(right, 1)
        self._build_audio_card()
        self._build_camera_tab()
        self._build_setup_tab()
        self._build_kits_tab()
        self._build_logs_card()
        self._apply_main_localization()

        self._zoom_base_geometry = (1024, 680)
        self._zoom_base_minsize = (980, 640)
        self._capture_zoom_bases()
        self._apply_ui_zoom_fonts()
        zoom = self.settings.ui_zoom
        base_w, base_h = self._zoom_base_geometry
        min_w, min_h = self._zoom_base_minsize
        top_min_w = self._required_top_bar_width()
        # Cache the reqwidth normalized back to a 1.0-equivalent base, so later
        # zoom commits can rescale it with plain multiplication instead of
        # calling _required_top_bar_width() (and its global update_idletasks())
        # again — see that method's docstring for why a repeated call is unsafe.
        self._zoom_base_top_bar_width = top_min_w / zoom if zoom else top_min_w
        root.geometry(f"{max(round(base_w * zoom), top_min_w)}x{round(base_h * zoom)}")
        root.minsize(max(round(min_w * zoom), top_min_w), round(min_h * zoom))
        self._zoom_applied = zoom
        self._zoom_apply_job = None

    def _required_top_bar_width(self) -> int:
        """The narrowest the window can get before the top bar's own buttons
        (locate FIFA .. check for updates) start clipping/going offscreen —
        used as a floor under both the initial geometry and minsize, so e.g.
        the Check Update button on the far right is never hidden until the
        user manually stretches the window wider.

        Only ever safe to call once, during initial _build_ui() — it forces a
        global `update idletasks` flush, which drains every pending geometry
        recalculation in the whole app, not just the top bar's. Confirmed
        live (py-spy dump on a hung process) that calling this again from
        _commit_ui_zoom(), right after _apply_ui_zoom_fonts() has just
        changed every widget's font size, can send that flush into a
        non-terminating <Configure> cascade against a self-referential
        wraplength-follows-own-width label binding (app_ui.py's hint_label,
        ~line 3147) — MainThread parked forever inside update_idletasks(),
        never returning to the Tk mainloop to pump Windows messages, i.e.
        exactly "Not Responding". Later callers must use
        _scaled_top_bar_width(zoom) instead, which reuses the value measured
        here and needs no fresh flush.
        """
        top = getattr(self, "_top_bar", None)
        root = self.ui_root
        if top is None or root is None:
            return 0
        root.update_idletasks()
        return top.winfo_reqwidth() + 24

    def _scaled_top_bar_width(self, zoom: float) -> int:
        base = getattr(self, "_zoom_base_top_bar_width", None)
        if base is None:
            return self._required_top_bar_width()
        return round(base * zoom)

    def _capture_zoom_bases(self) -> None:
        """Record each widget's font size exactly as authored in source
        (e.g. font=("Bahnschrift", 9, "bold") -> base size 9), so later zoom
        changes can always recompute sizes as base_size * zoom instead of
        compounding rounding error onto whatever size is currently displayed.
        Must run before _apply_ui_zoom_fonts() has ever executed once in this
        process — every literal font=(...) tuple in _build_ui()'s static tree
        is a plain hardcoded constant untouched by zoom until that first
        call, so whatever size is on screen right now IS the raw, zoom==1.0
        base value; dividing it by anything here would be wrong.

        Only walks the static tree built by _build_ui() (and its sub-builders,
        all of which run synchronously before this is called) — widgets
        created later at runtime (list rows, kit thumbnails, dialogs) are not
        covered here. ttk widgets are unaffected by this gap since none of
        them set an explicit font (see _configure_theme) — they all inherit
        from the shared named fonts rescaled in _apply_ui_zoom_fonts, which
        covers newly created ttk widgets automatically.
        """
        self._zoom_widget_fonts: list[tuple[tk.Misc, str, int, str, str]] = []

        def walk(widget: tk.Misc) -> None:
            try:
                raw_font = widget.cget("font")
            except Exception:
                raw_font = None
            if raw_font:
                try:
                    actual = tkfont.Font(font=raw_font).actual()
                    base_size = int(actual["size"])
                    if base_size > 0:
                        self._zoom_widget_fonts.append(
                            (widget, actual["family"], base_size, actual["weight"], actual["slant"])
                        )
                except Exception:
                    pass
            try:
                children = widget.winfo_children()
            except Exception:
                children = []
            for child in children:
                walk(child)

        if self.ui_root is not None:
            walk(self.ui_root)

        # Same "whatever's on screen right now is the zoom==1.0 base" logic as
        # above. These are Tk's own built-in fonts (every ttk widget in this
        # app implicitly uses them — see _configure_theme); their size here
        # is whatever Tk/Windows auto-selected at interpreter startup, before
        # _apply_ui_zoom_fonts() has ever run, so it's captured as-is too.
        self._zoom_named_font_bases: dict[str, int] = {}
        for name in UI_ZOOM_NAMED_FONTS:
            try:
                f = tkfont.nametofont(name)
                base_size = abs(int(f.cget("size")))
                if base_size > 0:
                    self._zoom_named_font_bases[name] = base_size
            except Exception:
                pass

    def _apply_ui_zoom_fonts(self) -> None:
        zoom = self.settings.ui_zoom
        try:
            self.tk.call("tk", "scaling", self._base_tk_scaling * zoom)
        except Exception:
            pass
        for name, base_size in self._zoom_named_font_bases.items():
            try:
                tkfont.nametofont(name).configure(size=round(base_size * zoom))
            except Exception:
                pass
        for widget, family, base_size, weight, slant in self._zoom_widget_fonts:
            try:
                if not widget.winfo_exists():
                    continue
            except Exception:
                continue
            font_spec = [family, round(base_size * zoom)]
            if weight == "bold":
                font_spec.append("bold")
            if slant == "italic":
                font_spec.append("italic")
            try:
                widget.configure(font=tuple(font_spec))
            except Exception:
                pass

    def _update_zoom_label(self) -> None:
        pct = round(self.settings.ui_zoom / UI_ZOOM_DEFAULT * 100)
        if self.zoom_value_label is not None:
            self.zoom_value_label.configure(text=f"{pct}%")
        if self.zoom_out_button is not None:
            self.zoom_out_button.configure(state="disabled" if self.settings.ui_zoom <= UI_ZOOM_MIN else "normal")
        if self.zoom_in_button is not None:
            self.zoom_in_button.configure(state="disabled" if self.settings.ui_zoom >= UI_ZOOM_MAX else "normal")

    def _step_ui_zoom(self, direction: int) -> None:
        old_zoom = self.settings.ui_zoom
        new_zoom = round(old_zoom + direction * UI_ZOOM_STEP, 4)
        new_zoom = max(UI_ZOOM_MIN, min(UI_ZOOM_MAX, new_zoom))
        if new_zoom == old_zoom:
            return
        self.settings.ui_zoom = new_zoom
        self._update_zoom_label()
        # Debounced: reconfiguring every literal-font widget in the app plus
        # a native window resize is expensive enough that clicking +/- fast
        # (no debounce) queues up one full pass per click and freezes the UI
        # for several seconds — confirmed live ("Not Responding", ~40s of
        # accumulated CPU time after a rapid-click burst). Same pattern the
        # dashboard canvas already uses for its own Configure storms (see
        # _on_dashboard_configure) — only the LAST zoom level requested
        # within the debounce window actually gets applied.
        if getattr(self, "_zoom_apply_job", None) is not None:
            try:
                self.after_cancel(self._zoom_apply_job)
            except Exception:
                pass
        self._zoom_apply_job = self.after(200, self._commit_ui_zoom)

    def _commit_ui_zoom(self) -> None:
        self._zoom_apply_job = None
        applied_before = getattr(self, "_zoom_applied", self.settings.ui_zoom) or 1.0
        target = self.settings.ui_zoom
        self._apply_ui_zoom_fonts()
        root = self.ui_root
        if root is not None and root.winfo_exists():
            ratio = target / applied_before
            new_w = max(1, round(root.winfo_width() * ratio))
            new_h = max(1, round(root.winfo_height() * ratio))
            top_min_w = self._scaled_top_bar_width(target)
            new_w = max(new_w, top_min_w)
            root.geometry(f"{new_w}x{new_h}")
            min_w, min_h = self._zoom_base_minsize
            root.minsize(max(round(min_w * target), top_min_w), round(min_h * target))
        self._zoom_applied = target
        self._update_zoom_label()

    def _toggle_zoom_popup(self) -> None:
        """Shows/hides the -/percentage/+ zoom controls as a small borderless
        popup anchored under the magnifying-glass button, instead of taking
        up permanent space in the top bar."""
        if self._zoom_popup is not None and self._zoom_popup.winfo_exists():
            self._close_zoom_popup()
            return
        popup = tk.Toplevel(self._window())
        popup.overrideredirect(True)
        popup.attributes("-topmost", True)
        popup.configure(bg=self.panel, highlightthickness=1, highlightbackground="#2a3c59")
        self._zoom_popup = popup

        row = tk.Frame(popup, bg=self.panel, padx=8, pady=6)
        row.pack()
        self.zoom_label = tk.Label(row, text=self.tr("label.zoom"), bg=self.panel, fg=self.muted, font=("Bahnschrift", 9, "bold"))
        self.zoom_label.pack(side="left", padx=(0, 8))
        self.zoom_out_button = ttk.Button(row, text="-", width=2, command=lambda: self._step_ui_zoom(-1))
        self.zoom_out_button.pack(side="left")
        self.zoom_value_label = tk.Label(row, text="100%", bg=self.panel, fg=self.fg, font=("Consolas", 9), width=5, anchor="center")
        self.zoom_value_label.pack(side="left", padx=2)
        self.zoom_in_button = ttk.Button(row, text="+", width=2, command=lambda: self._step_ui_zoom(1))
        self.zoom_in_button.pack(side="left")
        self._update_zoom_label()

        # The window's min/max size floor is only recomputed at startup
        # (_required_top_bar_width, captured once into _zoom_base_top_bar_width
        # — see its docstring) and then merely rescaled on later commits; a
        # live commit still resizes the window itself correctly, but some
        # widgets sized off the window's initial layout don't always settle
        # to the new zoom cleanly without a fresh start. Flagging that here
        # instead of trying to fix live re-layout for every such widget.
        self.zoom_restart_hint_label = tk.Label(
            popup, text=self.tr("label.zoom_restart_hint"), bg=self.panel, fg=self.muted,
            font=("Bahnschrift", 8), justify="left", wraplength=170,
        )
        self.zoom_restart_hint_label.pack(fill="x", padx=8, pady=(0, 6))

        # Position after_idle rather than via an immediate update_idletasks():
        # the latter forces Tk to synchronously drain *every* pending idle
        # task application-wide, not just this popup's — and right after a
        # zoom commit has just rescaled fonts across the whole widget tree,
        # that backlog can be large. Confirmed live (py-spy dump on hung
        # processes, twice) that forcing it here parked the MainThread inside
        # that single Tcl call for a very long time — "Not Responding" —
        # because Tk never returns to the mainloop to pump Windows messages
        # while draining it. after_idle runs once the idle queue empties too,
        # but one event at a time through the normal mainloop, so pending
        # work processes incrementally without blocking message pumping.
        def _position_popup() -> None:
            if not popup.winfo_exists():
                return
            btn = self.zoom_toggle_button
            x = btn.winfo_rootx() + btn.winfo_width() - popup.winfo_reqwidth()
            y = btn.winfo_rooty() + btn.winfo_height() + 4
            popup.geometry(f"+{max(0, x)}+{max(0, y)}")
            popup.focus_force()

        popup.bind("<FocusOut>", lambda _e: self._close_zoom_popup())
        popup.bind("<Escape>", lambda _e: self._close_zoom_popup())
        popup.after_idle(_position_popup)

    def _close_zoom_popup(self) -> None:
        if self._zoom_popup is not None:
            try:
                self._zoom_popup.destroy()
            except Exception:
                pass
            self._zoom_popup = None
        self.zoom_label = None
        self.zoom_value_label = None
        self.zoom_out_button = None
        self.zoom_in_button = None
        self.zoom_restart_hint_label = None

    def _build_stadium_loading_modal(self) -> None:
        modal = tk.Toplevel(self._window())
        modal.withdraw()
        modal.overrideredirect(True)
        modal.attributes("-topmost", True)
        modal.configure(bg=self.card)
        self._apply_window_icon(modal)
        modal_frame = tk.Frame(modal, bg=self.card, highlightthickness=1, highlightbackground="#2a3c59", padx=14, pady=12)
        modal_frame.pack(fill="both", expand=True)
        self.stadium_loading_modal = modal
        self.stadium_loading_title = tk.Label(
            modal_frame,
            text=self.tr("stadium_modal.title"),
            bg=self.card,
            fg=self.gold,
            font=("Bahnschrift", 12, "bold"),
            anchor="w",
        )
        self.stadium_loading_title.pack(fill="x")
        self.stadium_loading_preview = tk.Label(
            modal_frame,
            text=self.tr("stadium_modal.preview"),
            bg=self.card_soft,
            fg=self.muted,
            font=("Bahnschrift", 11, "bold"),
            justify="center",
            anchor="center",
            highlightthickness=1,
            highlightbackground="#243654",
        )
        self.stadium_loading_preview.pack(fill="x", pady=(8, 8), ipady=24)
        self.stadium_loading_name = tk.Label(
            modal_frame,
            text="-",
            bg=self.card,
            fg=self.fg,
            font=("Bahnschrift", 11, "bold"),
            anchor="w",
        )
        self.stadium_loading_name.pack(fill="x", pady=(6, 4))
        self.stadium_loading_detail = tk.Label(
            modal_frame,
            text=self.tr("stadium_modal.preparing"),
            bg=self.card,
            fg=self.muted,
            font=("Bahnschrift", 9),
            anchor="w",
            justify="left",
        )
        self.stadium_loading_detail.pack(fill="x", pady=(0, 8))
        self.stadium_loading_value = tk.DoubleVar(value=0)
        self.stadium_loading_bar = ttk.Progressbar(
            modal_frame,
            maximum=100,
            variable=self.stadium_loading_value,
            style="Accent.Horizontal.TProgressbar",
            mode="determinate",
            length=292,
        )
        self.stadium_loading_bar.pack(fill="x", pady=(2, 0))
        zoom = self.settings.ui_zoom
        modal.geometry(f"{round(340 * zoom)}x{round(274 * zoom)}")

    def _show_stadium_loading_modal(self, stadium_name: str, detail: str = "Preparing stadium assets", progress: float = 0.0) -> None:
        if not self.show_stadium_loading_var.get():
            self._stadium_loading_visible = False
            self._stadium_loading_restore_fullscreen = False
            return
        self._cancel_stadium_loading_hide()
        if self._try_d3d_overlay_show(stadium_name, detail, progress):
            return
        if self.stadium_loading_modal is None:
            return
        self.stadium_loading_modal.configure(cursor="arrow")
        self._update_stadium_loading_preview(stadium_name)
        if self.stadium_loading_name is not None:
            self.stadium_loading_name.configure(text=stadium_name or "-")
        if self.stadium_loading_detail is not None:
            self.stadium_loading_detail.configure(text=detail or self.tr("stadium_modal.preparing"))
        if self.stadium_loading_value is not None:
            self.stadium_loading_value.set(max(0, min(100, progress)))
        self._stadium_loading_restore_fullscreen = self._is_probable_fullscreen_window(self._fifa_hwnd)
        self._stadium_loading_visible = True
        self._position_stadium_loading_modal()
        self.stadium_loading_modal.deiconify()
        self.stadium_loading_modal.update_idletasks()
        self.stadium_loading_modal.update()
        self._stadium_loading_hwnd = self.stadium_loading_modal.winfo_id()
        self._apply_noactivate_window_style(self._stadium_loading_hwnd)
        try:
            self.user32.ShowWindow(self._stadium_loading_hwnd, SW_SHOWNOACTIVATE)
        except Exception:
            pass
        self.after(10, self._focus_fifa_window)

    def _try_d3d_overlay_show(self, stadium_name: str, detail: str, progress: float) -> bool:
        if _D3DOverlayInjector is None:
            self.log("D3D overlay: injector module not available (import failed)")
            return False
        dll_path = self.resource_dir / "bin" / "cgfs16_overlay.dll"
        if not dll_path.exists():
            self.log(f"D3D overlay: DLL not found at {dll_path}")
            return False
        if not self._ensure_d3d_overlay_injected(log_errors=True):
            self.log("D3D overlay unavailable, using modal fallback")
            return False
        inj = self._d3d_injector
        if inj is None:
            return False
        inj.show(stadium_name, detail or self.tr("stadium_modal.preparing"), progress,
                 image_path=str(self._resolve_stadium_preview_path_or_default(stadium_name) or ""))
        self._d3d_overlay_shown_at = time.monotonic()
        self._stadium_loading_visible = True
        self.log(f"Stadium notification via D3D overlay: {stadium_name}")
        return True

    def _ensure_d3d_overlay_injected(self, log_errors: bool = False) -> bool:
        if _D3DOverlayInjector is None:
            if log_errors:
                self.log("D3D overlay: injector module not available (import failed)")
            return False
        dll_path = self.resource_dir / "bin" / "cgfs16_overlay.dll"
        if not dll_path.exists():
            if log_errors:
                self.log(f"D3D overlay: DLL not found at {dll_path}")
            return False
        if self._d3d_injector is None:
            try:
                self._d3d_injector = _D3DOverlayInjector(dll_path)
            except Exception as exc:
                if log_errors:
                    self.log(f"D3D overlay injector init failed: {exc}")
                self._d3d_injector = None
                return False
        inj = self._d3d_injector
        if inj is None or not inj.is_ready():
            if log_errors and inj is not None:
                self.log(f"D3D overlay: not ready (shared_mem={inj._ready}, "
                         f"dll={dll_path.exists()}, "
                         f"exe={inj._find_inject_exe() is not None})")
            return False
        pid = self._resolve_fifa_pid()
        if not pid:
            return False
        if not inj.is_injected(pid):
            if not inj.inject(pid):
                if log_errors:
                    self.log("D3D overlay: injection failed")
                return False
            self.log(f"D3D overlay: DLL injected into FIFA pid {pid}")
            icon_dir = gamepad_button_icon_dir()
            if icon_dir is not None:
                inj.set_gamepad_icon_dir(str(icon_dir))
            key_icon_dir = keyboard_button_icon_dir()
            if key_icon_dir is not None:
                inj.set_keyboard_icon_dir(str(key_icon_dir))
            rml_dir = rmlui_content_dir()
            if rml_dir is not None:
                inj.set_rmlui_content_dir(str(rml_dir))
        return True

    def _show_toast_notification(self, title: str, body: str = "", style: int = 0, icon: str = "") -> int:
        """Show a compact in-game toast (no progress bar, no image). Returns slot index or -1.

        `icon` names a file under resources/rmlui/icons/<icon>.png — leave
        empty to use the default app icon.
        """
        if not self.settings.show_stadium_loading_notification:
            return -1
        if not self._ensure_d3d_overlay_injected(log_errors=False):
            return -1
        inj = self._d3d_injector
        if inj is None:
            return -1
        return inj.show_toast(title, body, style, icon)

    def _hide_toast_notification(self, slot: int = -1) -> None:
        if self._d3d_injector is not None:
            self._d3d_injector.hide_toast(slot)

    def _cancel_stadium_loading_hide(self) -> None:
        if self._stadium_loading_hide_job is not None:
            try:
                self.after_cancel(self._stadium_loading_hide_job)
            except Exception:
                pass
            self._stadium_loading_hide_job = None
        if self._d3d_overlay_hide_job is not None:
            try:
                self.after_cancel(self._d3d_overlay_hide_job)
            except Exception:
                pass
            self._d3d_overlay_hide_job = None

    def _hide_stadium_loading_modal(self, delay_ms: int = 0) -> None:
        if delay_ms > 0:
            self._cancel_stadium_loading_hide()
            self._stadium_loading_hide_job = self.after(delay_ms, self._hide_stadium_loading_modal)
            return
        if self._stadium_loading_hide_job is not None:
            try:
                self.after_cancel(self._stadium_loading_hide_job)
            except Exception:
                pass
        self._stadium_loading_hide_job = None
        if self._d3d_injector is not None and self._d3d_injector.is_injected():
            if self._d3d_overlay_hide_job is not None:
                try:
                    self.after_cancel(self._d3d_overlay_hide_job)
                except Exception:
                    pass
                self._d3d_overlay_hide_job = None
            _MIN_VISIBLE_MS = 2500
            elapsed_ms = int((time.monotonic() - self._d3d_overlay_shown_at) * 1000)
            remaining_ms = max(0, _MIN_VISIBLE_MS - elapsed_ms)
            if remaining_ms > 0:
                self._d3d_overlay_hide_job = self.after(remaining_ms, self._do_hide_d3d_overlay)
            else:
                self._do_hide_d3d_overlay()
            return
        if self._stadium_loading_hwnd:
            try:
                self.user32.ShowWindow(self._stadium_loading_hwnd, SW_HIDE)
            except Exception:
                pass
        if self.stadium_loading_modal is not None:
            self.stadium_loading_modal.withdraw()
        was_visible = self._stadium_loading_visible
        self._stadium_loading_visible = False
        should_restore = self._stadium_loading_restore_fullscreen
        self._stadium_loading_restore_fullscreen = False
        if was_visible and should_restore:
            self.after(140, self._restore_fifa_fullscreen)

    def _do_hide_d3d_overlay(self) -> None:
        self._d3d_overlay_hide_job = None
        if self._d3d_injector is not None:
            self._d3d_injector.hide()
        self._stadium_loading_visible = False
        self.log("Stadium notification hidden via D3D overlay")

    def _update_stadium_loading_modal(self, value: float, detail: str) -> None:
        if not self.show_stadium_loading_var.get():
            return
        if self._d3d_injector is not None and self._d3d_injector.is_injected():
            self._d3d_injector.update(value, detail)
            return
        if self.stadium_loading_modal is None:
            return
        if self.stadium_loading_value is not None:
            self.stadium_loading_value.set(max(0, min(100, value)))
        if self.stadium_loading_detail is not None:
            self.stadium_loading_detail.configure(text=detail)
        if self._stadium_loading_visible:
            self._position_stadium_loading_modal()
            self.stadium_loading_modal.update_idletasks()
            self.stadium_loading_modal.update()

    def _position_stadium_loading_modal(self) -> None:
        if self.stadium_loading_modal is None:
            return
        fifa_hwnd = self._find_fifa_window_handle() if not self._fifa_hwnd else self._fifa_hwnd
        if fifa_hwnd:
            rect = RECT()
            if self.user32.GetWindowRect(fifa_hwnd, ctypes.byref(rect)):
                fifa_width = rect.right - rect.left
                fifa_height = rect.bottom - rect.top
                zoom = self.settings.ui_zoom
                modal_w, modal_h = round(340 * zoom), round(274 * zoom)
                x = rect.left + (fifa_width - modal_w) // 2
                y = rect.top + 40
                self.stadium_loading_modal.geometry(f"{modal_w}x{modal_h}+{x}+{y}")
                return
        window = self._window()
        window.update_idletasks()
        root_x = window.winfo_rootx()
        root_y = window.winfo_rooty()
        zoom = self.settings.ui_zoom
        self.stadium_loading_modal.geometry(f"{round(340 * zoom)}x{round(274 * zoom)}+{root_x + 24}+{root_y + 24}")

    def _card(self, parent: tk.Misc, title_key: str, subtitle_key: str = "") -> tk.Frame:
        card = tk.Frame(parent, bg=self.card, bd=0, highlightthickness=1, highlightbackground="#243654")
        header = tk.Frame(card, bg=self.card)
        header.pack(fill="x", padx=12, pady=(10, 4))
        title_label = tk.Label(header, text=self.tr(title_key), bg=self.card, fg=self.fg, font=("Bahnschrift", 13, "bold"))
        title_label.pack(anchor="w")
        subtitle_label = None
        if subtitle_key:
            subtitle_label = tk.Label(header, text=self.tr(subtitle_key), bg=self.card, fg=self.muted, font=("Bahnschrift", 9))
            subtitle_label.pack(anchor="w", pady=(1, 0))
        if not hasattr(self, "_card_title_bindings"):
            self._card_title_bindings = []
        self._card_title_bindings.append((title_label, title_key, subtitle_label, subtitle_key))
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

    def _register_info_label(self, key: str, widget: tk.Widget) -> None:
        self.info_labels.setdefault(key, []).append(widget)

    def _set_display(self, key: str, text: str) -> None:
        primary = self.labels.get(key)
        if primary is not None:
            primary.configure(text=text)
        for widget in self.info_labels.get(key, []):
            widget.configure(text=text)
        if key == "stadium":
            self._update_stadium_preview(text)

    def _set_display_async(self, key: str, text: str) -> None:
        try:
            self.after(0, lambda: self._set_display(key, text))
        except Exception:
            pass

    def _on_dashboard_configure(self, _event=None) -> None:
        if hasattr(self, "_dashboard_configure_job"):
            self.after_cancel(self._dashboard_configure_job)
        self._dashboard_configure_job = self.after(80, self._apply_dashboard_configure)

    def _apply_dashboard_configure(self) -> None:
        if self.dashboard_canvas is not None and self.dashboard_content is not None:
            self.dashboard_canvas.configure(scrollregion=self.dashboard_canvas.bbox("all"))

    def _on_dashboard_canvas_configure(self, event) -> None:
        if hasattr(self, "_dashboard_canvas_configure_job"):
            self.after_cancel(self._dashboard_canvas_configure_job)
        width = event.width
        self._dashboard_canvas_configure_job = self.after(80, lambda: self._apply_dashboard_canvas_configure(width))

    def _apply_dashboard_canvas_configure(self, width: int) -> None:
        if self.dashboard_canvas is not None and self.dashboard_window_id is not None:
            self.dashboard_canvas.itemconfigure(self.dashboard_window_id, width=width)

    def _event_widget_belongs_to(self, event, *containers) -> bool:
        """True if event's target widget is one of, or nested inside, any of containers.

        bind_all fires for every widget in the app, so callers must check this
        before acting — otherwise a global mousewheel handler bound by one tab
        would also fire while scrolling over unrelated widgets/tabs.
        """
        widget = event.widget
        if isinstance(widget, str):
            try:
                widget = self.nametowidget(widget)
            except Exception:
                return False
        if widget is None:
            return False
        try:
            if widget.winfo_toplevel() is not self._window():
                return False
        except Exception:
            return False
        cursor = widget
        while cursor is not None:
            if cursor in containers:
                return True
            try:
                parent_name = cursor.winfo_parent()
            except Exception:
                break
            if not parent_name:
                break
            try:
                cursor = cursor._nametowidget(parent_name)
            except Exception:
                break
        return False

    def _on_dashboard_mousewheel(self, event) -> None:
        if self.tabview is None or self.dashboard_canvas is None:
            return
        current = self.tabview.nametowidget(self.tabview.select())
        if current is not self.dashboard_tab:
            return
        if not self._event_widget_belongs_to(event, self.dashboard_canvas, self.dashboard_content):
            return
        self.dashboard_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _on_setup_mousewheel(self, event) -> None:
        if self.tabview is None or self._setup_canvas is None:
            return
        current = self.tabview.nametowidget(self.tabview.select())
        if current is not self.setup_tab:
            return
        if not self._event_widget_belongs_to(event, self._setup_canvas, self._setup_canvas_body):
            return
        self._setup_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _on_setup_assets_mousewheel(self, event) -> None:
        if self.tabview is None or self._assets_canvas is None:
            return
        current = self.tabview.nametowidget(self.tabview.select())
        if current is not self.setup_tab:
            return
        if not self._event_widget_belongs_to(event, self._assets_canvas, self._assets_canvas_body):
            return
        self._assets_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _build_placeholder(self, parent: tk.Misc, width: int, height: int, text: str, bg: str | None = None) -> tk.Canvas:
        bg_color = bg or self.card_soft
        canvas = tk.Canvas(parent, width=width, height=height, bg=bg_color, highlightthickness=0)
        canvas.create_rectangle(8, 8, width - 8, height - 8, outline="#314666", width=2)
        canvas.create_text(width / 2, height / 2, text=text, fill=self.muted, font=("Bahnschrift", 12, "bold"))
        return canvas

    def _resolve_stadium_preview_path(self, stadium_name: str):
        from pathlib import Path as _Path
        stadium_name = (stadium_name or "").strip()
        if not stadium_name or stadium_name in {"-", "None", "Stadium Module Disable"}:
            return None
        candidate_roots: list[_Path] = []
        targetpath = getattr(self, "targetpath", None)
        if targetpath is not None:
            candidate_roots.append(_Path(targetpath))
        exedir = getattr(self, "exedir", None)
        if exedir is not None:
            candidate_roots.append(_Path(exedir) / "StadiumGBD")
        seen: set[_Path] = set()
        for root in candidate_roots:
            try:
                root = root.resolve()
            except Exception:
                root = _Path(root)
            if root in seen:
                continue
            seen.add(root)
            candidate = resolve_stadium_preview_path(root, stadium_name)
            if candidate is not None:
                return candidate
        return None

    def _resolve_stadium_preview_path_or_default(self, stadium_name: str):
        """Like `_resolve_stadium_preview_path`, but falls back to the bundled generic
        stadium image (`resources/stadium-placeholder.png`) when a stadium is actually
        assigned but has no preview thumbnail of its own."""
        image_path = self._resolve_stadium_preview_path(stadium_name)
        if image_path is not None:
            return image_path
        stadium_name = (stadium_name or "").strip()
        if not stadium_name or stadium_name in {"-", "None", "Stadium Module Disable"}:
            return None
        return stadium_preview_fallback_path()

    def _load_preview_photo(self, image_path, max_size: tuple[int, int]):
        if image_path is None or not image_path.exists():
            return None
        try:
            image = Image.open(image_path).convert("RGBA")
            image.thumbnail(max_size)
            return ImageTk.PhotoImage(image)
        except Exception:
            return None

    def _update_stadium_preview(self, stadium_name: str) -> None:
        label = self._stadium_preview_label
        if label is None:
            return
        self._stadium_preview_image = None
        image_path = self._resolve_stadium_preview_path_or_default(stadium_name)
        photo = self._load_preview_photo(image_path, (340, 190))
        if photo is None:
            self._stadium_preview_last_value = stadium_name
            label.configure(image="", text=self.tr("placeholder.stadium_preview"), compound="center")
            return
        self._stadium_preview_image = photo
        label.configure(image=photo, text="", compound="center")

    def _update_stadium_loading_preview(self, stadium_name: str) -> None:
        label = self.stadium_loading_preview
        if label is None:
            return
        self._stadium_loading_image = None
        image_path = self._resolve_stadium_preview_path_or_default(stadium_name)
        photo = self._load_preview_photo(image_path, (300, 138))
        if photo is None:
            label.configure(image="", text="STADIUM\nPREVIEW", compound="center")
            return
        self._stadium_loading_image = photo
        label.configure(image=photo, text="", compound="center")

    def prepare_floating_window(self) -> tk.Misc:
        window = self._window()
        window.deiconify()
        window.lift()
        try:
            window.focus_force()
        except Exception:
            pass
        return window

    def configure_secondary_window(self, window: tk.Toplevel) -> None:
        self._apply_window_icon(window)
        try:
            window.overrideredirect(False)
        except Exception:
            pass
        try:
            window.attributes("-topmost", False)
        except Exception:
            pass
        window.deiconify()
        window.lift()
        try:
            window.focus_force()
        except Exception:
            pass

    def _build_logo_placeholder_image(self, width: int = 116, height: int = 72) -> ImageTk.PhotoImage:
        image = Image.new("RGBA", (width, height), self.card_soft)
        return ImageTk.PhotoImage(image)

    def _resolve_team_logo_path(self, team_id: str):
        from pathlib import Path as _Path
        team_id = (team_id or "").strip()
        if not team_id or team_id == "-":
            return None
        crest_dir = self.exedir / "data" / "ui" / "imgAssets" / "crest50x50" / "light"
        candidates = [
            crest_dir / f"l{team_id}.dds",
            crest_dir / f"L{team_id}.dds",
            crest_dir / f"l{int(team_id)}.dds" if team_id.isdigit() else None,
        ]
        for candidate in candidates:
            if candidate is not None and candidate.exists():
                return candidate
        return None

    def _to_overlay_crest_png(self, team_id: str, prefix: str) -> str:
        import tempfile
        import os
        attr = f"_crest_tmp_{prefix}"
        old = getattr(self, attr, "")
        if old:
            try:
                os.unlink(old)
            except OSError:
                pass
        setattr(self, attr, "")
        dds_path = self._resolve_team_logo_path(team_id)
        if not dds_path:
            return ""
        try:
            img = Image.open(dds_path).convert("RGBA")
            tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            img.save(tmp.name, "PNG")
            tmp.close()
            setattr(self, attr, tmp.name)
            return tmp.name
        except Exception:
            return ""

    def _update_team_logo(self, prefix: str, team_id: str) -> None:
        label = self._team_logo_labels.get(prefix)
        if label is None:
            return
        image_ref: ImageTk.PhotoImage | None = None
        logo_path = self._resolve_team_logo_path(team_id)
        if logo_path is not None:
            try:
                image = Image.open(logo_path).convert("RGBA")
                image.thumbnail((116, 72))
                image_ref = ImageTk.PhotoImage(image)
            except Exception as exc:
                self.log(f"Failed to load team crest {logo_path}", exc, exc_info=sys.exc_info())
        if image_ref is None:
            image_ref = self._build_logo_placeholder_image()
            label.configure(text=self.tr("placeholder.logo"), compound="center")
        else:
            label.configure(text="", compound="center")
        label.configure(image=image_ref)
        self._team_logo_images[prefix] = image_ref
        inj = self._d3d_injector
        if inj and inj.is_ready():
            png = self._to_overlay_crest_png(team_id, prefix)
            if prefix == "home":
                self._home_crest_png = png
            else:
                self._away_crest_png = png
            inj.set_team_crests(self._home_crest_png, self._away_crest_png)

    def _build_matchup_card(self, parent: tk.Misc, row: int) -> None:
        card = self._card(parent, "card.matchup.title", "card.matchup.subtitle")
        card.grid(row=row, column=0, sticky="ew", pady=(0, 12))
        card.configure(height=290)
        card.grid_propagate(False)
        body = tk.Frame(card, bg=self.card)
        body.pack(fill="both", expand=True, padx=12, pady=(6, 12))
        body.grid_columnconfigure(0, weight=2)
        body.grid_columnconfigure(1, weight=1)
        body.grid_columnconfigure(2, weight=2)
        body.grid_rowconfigure(0, weight=1)
        body.grid_rowconfigure(1, weight=0)

        self._build_team_panel(body, 0, self.tr("team.a"), "home")
        center = tk.Frame(body, bg=self.card)
        center.grid(row=0, column=1, sticky="nsew", padx=8)
        tk.Label(center, text=self.tr("match.score"), bg=self.card, fg=self.muted, font=("Bahnschrift", 9)).pack(pady=(18, 2))
        score_label = tk.Label(center, text="0 - 0", bg=self.card, fg=self.gold, font=("Bahnschrift", 28, "bold"))
        score_label.pack()
        tk.Label(center, text=self.tr("match.time"), bg=self.card, fg=self.muted, font=("Bahnschrift", 9)).pack(pady=(18, 2))
        timer_label = tk.Label(center, text="00:00", bg=self.card, fg=self.accent, font=("Consolas", 18, "bold"))
        timer_label.pack()
        self._register_info_label("score", score_label)
        self._register_info_label("timer", timer_label)
        self._build_team_panel(body, 2, self.tr("team.b"), "away")
        self._build_substitution_row(body)

    def _build_substitution_row(self, parent: tk.Misc) -> None:
        row = tk.Frame(parent, bg=self.card)
        row.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(10, 0))
        self._dark_label(row, self.tr("substitutions.label"), bg=self.card, muted=True).pack(side="left")
        self.substitution_count_var = tk.StringVar(value=str(self.settings.substitution_count))
        ttk.Entry(row, textvariable=self.substitution_count_var, width=4).pack(side="left", padx=(6, 6))
        self.substitution_confirm_button = ttk.Button(
            row, text=self.tr("button.confirm_substitutions"), command=self._confirm_substitution_count,
        )
        self.substitution_confirm_button.pack(side="left", padx=(0, 10))
        auto_apply_check = ttk.Checkbutton(
            row,
            style="Switch.TCheckbutton",
            text=self.tr("substitutions.auto_apply"),
            variable=self.auto_apply_substitution_var,
            command=self._toggle_auto_apply_substitutions,
        )
        auto_apply_check.pack(side="left", padx=(0, 10))
        status_label = self._dark_label(row, self.tr("substitutions.status.idle"), bg=self.card, muted=True)
        status_label.pack(side="left")
        self._register_info_label("substitution_status", status_label)

    def _confirm_substitution_count(self) -> None:
        raw = self.substitution_count_var.get().strip()
        if not raw.isdigit():
            self._set_display("substitution_status", self.tr("substitutions.status.invalid"))
            return
        count = max(SUBSTITUTION_MIN, min(SUBSTITUTION_MAX, int(raw)))
        self.substitution_count_var.set(str(count))
        self.settings.substitution_count = count
        if count > SUBSTITUTION_VALIDATED_MAX:
            self.log(f"Substitution count {count} exceeds the validated range (<={SUBSTITUTION_VALIDATED_MAX}) — unverified, proceeding at user's request")
        if self.substitution_confirm_button is not None:
            self.substitution_confirm_button.configure(state="disabled")
        self._set_display("substitution_status", self.tr("substitutions.status.installing"))
        self.apply_substitution_count(count)

    def _toggle_auto_apply_substitutions(self) -> None:
        self.settings.auto_apply_substitution_count = self.auto_apply_substitution_var.get()

    def _on_substitution_status(self, code: str, **kwargs) -> None:
        final_codes = {
            "armed", "armed_partial", "timeout", "invalid_pointer", "write_failed", "not_attached",
            "unsafe_build", "already_hooked", "fifa_changed", "patch_failed", "alloc_failed",
        }
        if code == "armed" and kwargs.get("count", 0) > SUBSTITUTION_VALIDATED_MAX:
            key = "substitutions.status.armed_unverified"
        else:
            key = _SUBSTITUTION_STATUS_KEYS.get(code, code)
        text = self.tr(key, **kwargs)
        if code in final_codes and self.substitution_confirm_button is not None:
            self.substitution_confirm_button.configure(state="normal")
        self._set_display("substitution_status", text)
        self.log(f"Substitution count [{code}] {text}")

    def _build_team_panel(self, parent: tk.Misc, column: int, title: str, prefix: str) -> None:
        panel = tk.Frame(parent, bg=self.card_soft, highlightthickness=1, highlightbackground="#243654")
        panel.grid(row=0, column=column, sticky="nsew", padx=(0 if column == 0 else 6, 0 if column == 2 else 6))
        logo = tk.Label(
            panel,
            width=116,
            height=72,
            bg=self.card_soft,
            fg=self.muted,
            text=self.tr("placeholder.logo"),
            font=("Bahnschrift", 12, "bold"),
            compound="center",
        )
        logo.pack(padx=10, pady=(12, 8))
        self._team_logo_labels[prefix] = logo
        self._update_team_logo(prefix, "")
        strips = tk.Frame(panel, bg=self.card_soft)
        strips.pack(padx=10, pady=(0, 8))
        for _ in range(8):
            tk.Frame(strips, bg="#243654", width=7, height=7).pack(side="left", padx=2)
        name_key = f"{prefix}_name"
        id_key = "hid" if prefix == "home" else "aid"
        tk.Label(panel, text=self.tr("team.name"), bg=self.card_soft, fg=self.muted, font=("Bahnschrift", 9)).pack(anchor="w", padx=10)
        name_label = tk.Label(panel, text=title, bg=self.card_soft, fg=self.fg, font=("Bahnschrift", 14, "bold"))
        name_label.pack(anchor="w", padx=10)
        tk.Label(panel, text=self.tr("team.id"), bg=self.card_soft, fg=self.muted, font=("Bahnschrift", 9)).pack(anchor="w", padx=10, pady=(8, 0))
        id_label = tk.Label(panel, text="-", bg=self.card_soft, fg=self.accent, font=("Consolas", 14, "bold"))
        id_label.pack(anchor="w", padx=10, pady=(0, 10))
        self._register_info_label(name_key, name_label)
        self._register_info_label(id_key, id_label)
        self._set_display(name_key, title)

    def _build_match_card(self, parent: tk.Misc, row: int) -> None:
        card = self._card(parent, "card.match.title", "card.match.subtitle")
        card.grid(row=row, column=0, sticky="ew", pady=(0, 12))
        card.configure(height=178)
        card.grid_propagate(False)
        body = tk.Frame(card, bg=self.card)
        body.pack(fill="x", padx=12, pady=(6, 12))
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=1)
        self._build_stat(body, 0, 0, "stat.tournament", "tour", "-")
        self._build_stat(body, 0, 1, "stat.round_id", "round", "-")
        self._build_stat(body, 1, 0, "stat.current_page", "page", "-")
        self._build_stat(body, 1, 1, "stat.derby_key", "derby", "-")
        self._build_stat(body, 2, 0, "stat.minute_second", "match_clock_split", "00 / 00")
        self._build_stat(body, 2, 1, "stat.game_state", "game_state", self.display_value("idle"))
        self._build_stat(body, 3, 0, "stat.goal_status", "goal_active", self.display_value("no"))
        self._build_stat(body, 3, 1, "stat.last_update", "last_update", "-")

    def _build_assets_card(self, parent: tk.Misc, row: int) -> None:
        card = self._card(parent, "card.assets.title", "card.assets.subtitle")
        card.grid(row=row, column=0, sticky="ew")
        card.configure(height=206)
        card.grid_propagate(False)
        body = tk.Frame(card, bg=self.card)
        body.pack(fill="x", padx=12, pady=(6, 12))
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=1)
        self._build_stat(body, 0, 0, "stat.tv_logo", "tvlogo", "default")
        self._build_stat(body, 0, 1, "stat.scoreboard", "scoreboard", "default")
        self._build_stat(body, 1, 0, "stat.movie", "movie", "default")
        self._build_stat(body, 1, 1, "stat.status", "status", self.display_value("idle"))
        ttk.Button(card, text=self.tr("button.edit_asset_settings"), command=self.open_assets_settings_editor).pack(fill="x", padx=12, pady=(0, 6))
        io_row = tk.Frame(card, bg=self.card)
        io_row.pack(fill="x", padx=12, pady=(0, 12))
        io_row.grid_columnconfigure(0, weight=1)
        io_row.grid_columnconfigure(1, weight=1)
        ttk.Button(io_row, text=self.tr("button.export_settings"), command=self.open_export_settings_dialog).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ttk.Button(io_row, text=self.tr("button.import_settings"), command=self.open_import_settings_dialog).grid(row=0, column=1, sticky="ew", padx=(4, 0))

    def _build_kits_tab(self) -> None:
        outer = tk.Frame(self.kits_tab, bg=self.bg)
        outer.pack(fill="both", expand=True, padx=10, pady=10)

        sub_notebook = ttk.Notebook(outer, style="Server16.TNotebook")
        sub_notebook.pack(fill="both", expand=True)
        self._kits_sub_notebook = sub_notebook

        self.kits_simple_subtab = tk.Frame(sub_notebook, bg=self.bg)
        self.kits_advanced_subtab = tk.Frame(sub_notebook, bg=self.bg)
        sub_notebook.add(self.kits_simple_subtab, text=self.tr("tab.kits.simple"))
        sub_notebook.add(self.kits_advanced_subtab, text=self.tr("tab.kits.advanced"))
        sub_notebook.bind("<<NotebookTabChanged>>", self._on_kits_subtab_changed)

        self._build_kits_advanced_tab(self.kits_advanced_subtab)
        self._build_kits_simple_tab(self.kits_simple_subtab)

    def _on_kits_subtab_changed(self, event=None) -> None:
        if self._kits_sub_notebook is None:
            return
        try:
            current = self._kits_sub_notebook.nametowidget(self._kits_sub_notebook.select())
        except Exception:
            return
        if current is self.kits_simple_subtab:
            self._kitsimple_on_tab_shown()
        elif current is self.kits_advanced_subtab:
            self._kitmix_on_tab_shown()

    def _build_kits_advanced_tab(self, parent: tk.Misc) -> None:
        card = self._card(parent, "card.kitmix.title", "card.kitmix.subtitle")
        card.pack(fill="both", expand=True)

        self.kitmix_team_id = tk.StringVar(value="")
        self.kitmix_kittype_labels = {key: key.capitalize() for key in KIT_TYPES}
        self.kitmix_kittype = tk.StringVar(value=self.kitmix_kittype_labels.get("home", "Home"))
        self._kitmix_jersey_source: dict = {"mode": "keep", "path": None}
        self._kitmix_shorts_source: dict = {"mode": "keep", "path": None}
        self._kitmix_crest_source: dict = {"mode": "keep", "path": None}
        self._kitmix_jersey_numbers_source: dict = {"mode": "keep", "path": None}
        self._kitmix_shorts_numbers_source: dict = {"mode": "keep", "path": None}
        self._kitmix_kitui_source: dict = {"mode": "keep", "path": None}
        self.kitmix_namecolor_var = tk.StringVar(value="")
        self._kitmix_preview_images: dict = {}
        self._kitmix_preview_labels: dict = {}
        self._kitmix_preview_generation: dict = {}

        top = tk.Frame(card, bg=self.card)
        top.pack(fill="x", padx=12, pady=(0, 6))
        self._dark_label(top, self.tr("dialog.kitmix.team_id"), bg=self.card, muted=True).pack(side="left")
        ttk.Entry(top, textvariable=self.kitmix_team_id, width=10).pack(side="left", padx=(6, 12))
        self._dark_label(top, self.tr("dialog.kitmix.kit_type"), bg=self.card, muted=True).pack(side="left")
        ttk.Combobox(
            top, state="readonly", textvariable=self.kitmix_kittype,
            values=tuple(self.kitmix_kittype_labels.values()), width=10,
            style="Server16.TCombobox",
        ).pack(side="left", padx=(6, 12))
        ttk.Button(top, text=self.tr("dialog.kitmix.refresh"), command=self._kitmix_refresh_lists).pack(side="left")
        self.kitmix_team_name_label = self._dark_label(top, "", bg=self.card, muted=True)
        self.kitmix_team_name_label.pack(side="left", padx=(12, 0))

        search_row = tk.Frame(card, bg=self.card)
        search_row.pack(fill="x", padx=12, pady=(0, 4))
        self.kitmix_team_search_var = tk.StringVar()
        self._kitmix_team_search_placeholder_active = False
        self._kitmix_team_search_ids: list[str] = []
        search_entry = tk.Entry(
            search_row,
            textvariable=self.kitmix_team_search_var,
            bg=self.panel_alt,
            fg=self.fg,
            insertbackground=self.fg,
            relief="flat",
            font=("Consolas", 10),
        )
        search_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        search_entry.insert(0, self.tr("dialog.kitmix.find_team_by_name"))
        search_entry.configure(fg=self.muted)
        self._kitmix_team_search_placeholder_active = True

        def _clear_team_search_placeholder(_event=None) -> None:
            if self._kitmix_team_search_placeholder_active:
                search_entry.delete(0, "end")
                search_entry.configure(fg=self.fg)
                self._kitmix_team_search_placeholder_active = False

        search_entry.bind("<FocusIn>", _clear_team_search_placeholder)
        search_entry.bind("<KeyRelease>", self._kitmix_on_team_search)
        ttk.Button(search_row, text=self.tr("button.use_home_team"), command=self._kitmix_use_home_team).pack(side="left", padx=(0, 6))
        ttk.Button(search_row, text=self.tr("button.use_away_team"), command=self._kitmix_use_away_team).pack(side="left")

        self.kitmix_team_search_results = self._dark_listbox(card, height=4, exportselection=False, font=("Consolas", 9))
        self.kitmix_team_search_results.bind("<<ListboxSelect>>", self._kitmix_on_team_search_select)

        crest_warning = self._dark_label(
            card, self.tr("dialog.kitmix.crest_warning"), bg=self.card, muted=True, wraplength=1000, justify="left",
        )
        crest_warning.pack(fill="x", padx=12, pady=(0, 6))
        self._kitmix_team_search_results_anchor = crest_warning

        # Fixed footer — packed before the scroll area so it stays visible.
        footer = tk.Frame(card, bg=self.card)
        footer.pack(side="bottom", fill="x", padx=12, pady=(6, 12))
        self.kitmix_status_label = tk.Label(footer, text=self.display_value("idle"), bg=self.card, fg=self.muted, font=("Bahnschrift", 9))
        self.kitmix_status_label.pack(anchor="w", pady=(0, 4))
        btn_row = tk.Frame(footer, bg=self.card)
        btn_row.pack(fill="x")
        btn_row.grid_columnconfigure(0, weight=1)
        btn_row.grid_columnconfigure(1, weight=1)
        btn_row.grid_columnconfigure(2, weight=1)
        ttk.Button(btn_row, text=self.tr("button.select_and_assign"), command=self._kitmix_submit).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ttk.Button(btn_row, text=self.tr("button.restore_kit_original"), command=self.restore_kit_original).grid(row=0, column=1, sticky="ew", padx=(6, 6))
        ttk.Button(btn_row, text=self.tr("button.restore_manager"), command=self._open_kit_restore_manager).grid(row=0, column=2, sticky="ew", padx=(6, 0))

        # Scrollable body: source pickers grid + previews.
        scroll_host = tk.Frame(card, bg=self.card)
        scroll_host.pack(fill="both", expand=True, padx=12, pady=(0, 6))
        canvas = tk.Canvas(scroll_host, bg=self.card, highlightthickness=0, bd=0)
        scrollbar = ttk.Scrollbar(scroll_host, orient="vertical", command=canvas.yview, style="Server16.Vertical.TScrollbar")
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        body = tk.Frame(canvas, bg=self.card)
        canvas_win = canvas.create_window((0, 0), window=body, anchor="nw")

        def _on_body_configure(*_):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _on_canvas_configure(e):
            canvas.itemconfig(canvas_win, width=e.width)

        body.bind("<Configure>", _on_body_configure)
        canvas.bind("<Configure>", _on_canvas_configure)
        self._kits_canvas = canvas
        self._kits_canvas_body = body
        # add="+" — see the comment on the dashboard's bind_all for why this must
        # not replace other tabs' scoped mousewheel handlers.
        canvas.bind_all("<MouseWheel>", self._on_kits_mousewheel, add="+")

        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=1)
        body.grid_columnconfigure(2, weight=1)

        self._kitmix_jersey_list = self._kitmix_build_source_picker(body, 0, 0, self.tr("dialog.kitmix.jersey"), self._kitmix_jersey_source, role_key="jersey")
        self._kitmix_shorts_list = self._kitmix_build_source_picker(body, 1, 0, self.tr("dialog.kitmix.shorts"), self._kitmix_shorts_source, role_key="shorts")
        self._kitmix_crest_list = self._kitmix_build_source_picker(body, 2, 0, self.tr("dialog.kitmix.crest"), self._kitmix_crest_source, role_key="crest")
        self._kitmix_jersey_numbers_list = self._kitmix_build_source_picker(
            body, 0, 1, self.tr("dialog.kitmix.jersey_numbers"), self._kitmix_jersey_numbers_source,
            import_kind="rx3", list_fn=lambda team_id: self.kit_mixer.list_available_kitnumbers(team_id),
            role_key="jersey_numbers",
        )
        self._kitmix_shorts_numbers_list = self._kitmix_build_source_picker(
            body, 1, 1, self.tr("dialog.kitmix.shorts_numbers"), self._kitmix_shorts_numbers_source,
            import_kind="rx3", list_fn=lambda team_id: self.kit_mixer.list_available_kitnumbers(team_id),
            role_key="shorts_numbers",
        )
        self._kitmix_kitui_list = self._kitmix_build_source_picker(
            body, 2, 1, self.tr("dialog.kitmix.kitui"), self._kitmix_kitui_source,
            import_kind="dds", list_fn=lambda team_id: self.kit_mixer.list_available_kitui(team_id),
            role_key="kitui", kitui_image_import=True,
        )
        self._kitmix_build_namecolor_picker(body, 2, 0)

        self._kitmix_refresh_lists()

    def _kitmix_build_namecolor_picker(self, parent: tk.Misc, row: int, column: int) -> None:
        card = self._kitmix_card(parent, self.tr("dialog.kitmix.name_color"))
        card.grid(row=row, column=column, columnspan=3, sticky="ew", pady=(8, 0))
        body_row = tk.Frame(card, bg=self.card)
        body_row.pack(fill="x", padx=12, pady=(0, 12))

        self._kitmix_namecolor_swatch = tk.Label(
            body_row, text="  ", bg=self.card_soft, width=3,
            relief="flat", highlightthickness=1, highlightbackground="#243654",
        )
        self._kitmix_namecolor_swatch.pack(side="left", padx=(0, 8))

        entry = ttk.Entry(body_row, textvariable=self.kitmix_namecolor_var, width=10)
        entry.pack(side="left", padx=(0, 8))
        self.kitmix_namecolor_var.trace_add("write", lambda *_: self._kitmix_update_namecolor_swatch())

        def pick_color() -> None:
            from tkinter import colorchooser

            current = self.kitmix_namecolor_var.get().strip().lstrip("#")
            initial = f"#{current}" if NAME_COLOR_HEX_RE.match(current) else None
            _, hex_value = colorchooser.askcolor(color=initial, title=self.tr("dialog.kitmix.pick_color"))
            if hex_value:
                self.kitmix_namecolor_var.set(hex_value.lstrip("#").upper())

        ttk.Button(body_row, text=self.tr("dialog.kitmix.pick_color"), command=pick_color).pack(side="left", padx=(0, 8))
        self._dark_label(body_row, self.tr("dialog.kitmix.name_color_hint"), bg=self.card, muted=True).pack(side="left", padx=(0, 8))

        self._kitmix_namecolor_combo_var = tk.StringVar(value="")
        self._kitmix_namecolor_combo = ttk.Combobox(
            body_row, state="disabled", textvariable=self._kitmix_namecolor_combo_var,
            values=(), width=24, style="Server16.TCombobox",
        )
        self._kitmix_namecolor_combo.pack(side="left")
        self._kitmix_namecolor_combo.bind("<<ComboboxSelected>>", self._kitmix_on_namecolor_option_select)
        self._kitmix_namecolor_option_values: list[str] = []

        self._kitmix_update_namecolor_swatch()

    def _kitmix_refresh_namecolor_options(self) -> None:
        combo = getattr(self, "_kitmix_namecolor_combo", None)
        if combo is None:
            return
        team_id = self.kitmix_team_id.get().strip()
        self._kitmix_namecolor_option_values = []
        found = self.kit_mixer.list_kit_lua_name_colors(team_id) if team_id else []
        if not found:
            combo.configure(values=(), state="disabled")
            self._kitmix_namecolor_combo_var.set(self.tr("dialog.kitmix.name_color_none_found"))
            return
        code_labels = {code: self.kitmix_kittype_labels.get(name, name) for name, code in KIT_TYPES.items()}
        labels = []
        for kittype, hex_value in found:
            label = code_labels.get(kittype, f"{self.tr('dialog.kitmix.kit_type')} {kittype}")
            labels.append(f"{label}: #{hex_value.upper()}")
            self._kitmix_namecolor_option_values.append(hex_value)
        combo.configure(values=tuple(labels), state="readonly")
        self._kitmix_namecolor_combo_var.set(self.tr("dialog.kitmix.name_color_found"))

    def _kitmix_on_namecolor_option_select(self, _event=None) -> None:
        combo = self._kitmix_namecolor_combo
        values = combo.cget("values")
        current = self._kitmix_namecolor_combo_var.get()
        if current not in values:
            return
        idx = values.index(current)
        if idx >= len(self._kitmix_namecolor_option_values):
            return
        self.kitmix_namecolor_var.set(self._kitmix_namecolor_option_values[idx].upper())

    def _kitmix_update_namecolor_swatch(self) -> None:
        swatch = getattr(self, "_kitmix_namecolor_swatch", None)
        if swatch is None:
            return
        hex_value = self.kitmix_namecolor_var.get().strip().lstrip("#")
        if NAME_COLOR_HEX_RE.match(hex_value):
            swatch.configure(bg=f"#{hex_value}")
        else:
            swatch.configure(bg=self.card_soft)

    def _kitmix_card(self, parent: tk.Misc, title: str) -> tk.Frame:
        card = tk.Frame(parent, bg=self.card, highlightthickness=1, highlightbackground="#243654")
        header = tk.Frame(card, bg=self.card)
        header.pack(fill="x", padx=14, pady=(12, 8))
        tk.Label(header, text=title, bg=self.card, fg=self.fg, font=("Bahnschrift", 13, "bold")).pack(anchor="w")
        return card

    def _kitmix_build_source_picker(
        self, parent: tk.Misc, column: int, row: int, title: str, source: dict,
        import_kind: str = "image", list_fn=None, role_key: str = "", kitui_image_import: bool = False,
    ) -> tk.Listbox:
        from pathlib import Path

        list_mode, imported_mode, imported_prefix, filetypes, button_key = KITMIX_PICKER_KINDS[import_kind]
        card = self._kitmix_card(parent, title)
        card.grid(
            row=row, column=column, sticky="nsew",
            padx=(0 if column == 0 else 6, 0 if column == 2 else 6),
            pady=(0 if row == 0 else 8, 0),
        )
        body_row = tk.Frame(card, bg=self.card)
        body_row.pack(fill="both", expand=True, padx=12, pady=(0, 8))

        listbox = self._dark_listbox(body_row, exportselection=False, height=10, font=("Consolas", 10))
        listbox.pack(side="left", fill="both", expand=True, padx=(0, 8))
        listbox._list_fn = list_fn or (lambda team_id: self.kit_mixer.list_available_kits(team_id))

        if role_key:
            self._kitmix_build_inline_preview(body_row, role_key)

        def on_select(_event=None) -> None:
            sel = listbox.curselection()
            if not sel:
                return
            label = listbox.get(sel[0])
            if label == KITMIX_KEEP_LABEL:
                source["mode"] = "keep"
                source["path"] = None
            elif label.startswith(imported_prefix):
                # path was stashed on the listbox when the file was imported
                source["mode"] = imported_mode
                source["path"] = getattr(listbox, "_imported_path", None)
            else:
                source["mode"] = list_mode
                source["path"] = getattr(listbox, "_kit_paths", {}).get(label)
            if role_key:
                self._kitmix_on_source_changed(role_key, source)

        listbox.bind("<<ListboxSelect>>", on_select)

        def apply_imported_source(actual_path: str, display_name: str) -> None:
            listbox._imported_path = actual_path
            label = f"{imported_prefix}{display_name}"
            listbox.delete(0, "end")
            listbox.insert("end", KITMIX_KEEP_LABEL)
            listbox.insert("end", label)
            for kit_name in getattr(listbox, "_kit_paths", {}):
                listbox.insert("end", kit_name)
            listbox.selection_clear(0, "end")
            listbox.selection_set(1)
            source["mode"] = imported_mode
            source["path"] = actual_path
            if role_key:
                self._kitmix_on_source_changed(role_key, source)

        def import_file() -> None:
            path = filedialog.askopenfilename(title=self.tr(button_key), filetypes=filetypes)
            if not path:
                return
            apply_imported_source(path, Path(path).name)

        if not kitui_image_import:
            ttk.Button(card, text=self.tr(button_key), command=import_file).pack(fill="x", padx=12, pady=(0, 12))
            return listbox

        # Kit UI thumbnails are plain .dds files (see KITMIX_PICKER_KINDS["dds"]),
        # so a loose PNG/JPG can't just be dropped in like jersey/shorts/crest's
        # "image" kind does — it has to be baked into a same-format .dds first
        # via the 32-bit FifaLibrary bridge (KitMixRuntime.convert_image_to_kitui).
        def import_image_file() -> None:
            path = filedialog.askopenfilename(
                title=self.tr("dialog.kitmix.import_image"),
                filetypes=[("Images", "*.png *.bmp *.jpg *.jpeg"), ("All files", "*.*")],
            )
            if not path:
                return
            team_id, kittype_code = self._kitmix_current_team_kittype()
            if not team_id:
                messagebox.showwarning(self.tr("message.kitmix"), self.tr("message.kitmix.missing_team"))
                return

            if role_key:
                self._kitmix_show_preview_placeholder(role_key, self.tr("dialog.kitmix.loading"))

            def worker() -> None:
                try:
                    dds_path = self.kit_mixer.convert_image_to_kitui(team_id, kittype_code, path)
                    error = None
                except Exception as exc:  # noqa: BLE001 - surfaced via messagebox below
                    dds_path, error = None, exc
                self.after(0, lambda: on_converted(dds_path, error))

            def on_converted(dds_path, error) -> None:
                if error is not None or dds_path is None:
                    if role_key:
                        self._kitmix_show_preview_placeholder(role_key, self.tr("dialog.kitmix.preview_error"))
                    self.log("Failed to convert image for kit UI thumbnail", error)
                    messagebox.showerror(self.tr("message.kitmix"), self.tr("message.kitmix.kitui_image_failed", error=error))
                    return
                apply_imported_source(str(dds_path), Path(path).name)

            threading.Thread(target=worker, daemon=True).start()

        btn_row = tk.Frame(card, bg=self.card)
        btn_row.pack(fill="x", padx=12, pady=(0, 12))
        ttk.Button(btn_row, text=self.tr(button_key), command=import_file).pack(side="left", fill="x", expand=True, padx=(0, 6))
        ttk.Button(btn_row, text=self.tr("dialog.kitmix.import_image"), command=import_image_file).pack(side="left", fill="x", expand=True)
        return listbox

    def _kitmix_populate_list(self, listbox: tk.Listbox, source: dict, role_key: str = "") -> None:
        team_id = self.kitmix_team_id.get().strip()
        kits = listbox._list_fn(team_id) if team_id else []
        kit_paths = {p.name: str(p) for p in kits}
        listbox._kit_paths = kit_paths
        listbox.delete(0, "end")
        listbox.insert("end", KITMIX_KEEP_LABEL)
        for name in kit_paths:
            listbox.insert("end", name)
        listbox.selection_clear(0, "end")
        listbox.selection_set(0)
        source["mode"] = "keep"
        source["path"] = None
        if role_key:
            self._kitmix_on_source_changed(role_key, source)

    def _kitmix_refresh_lists(self) -> None:
        team_id = self.kitmix_team_id.get().strip()
        name = self._resolve_team_name(team_id) if team_id else None
        if self.kitmix_team_name_label is not None:
            label_text = name or ""
            if team_id:
                folder_name = self.kit_mixer.kits_folder_name(team_id)
                if folder_name != team_id:
                    label_text = f"{label_text} ({folder_name})" if label_text else folder_name
            self.kitmix_team_name_label.configure(text=label_text)
        self._kitmix_populate_list(self._kitmix_jersey_list, self._kitmix_jersey_source, "jersey")
        self._kitmix_populate_list(self._kitmix_shorts_list, self._kitmix_shorts_source, "shorts")
        self._kitmix_populate_list(self._kitmix_crest_list, self._kitmix_crest_source, "crest")
        self._kitmix_populate_list(self._kitmix_jersey_numbers_list, self._kitmix_jersey_numbers_source, "jersey_numbers")
        self._kitmix_populate_list(self._kitmix_shorts_numbers_list, self._kitmix_shorts_numbers_source, "shorts_numbers")
        self._kitmix_populate_list(self._kitmix_kitui_list, self._kitmix_kitui_source, "kitui")
        self.kitmix_namecolor_var.set("")
        self._kitmix_refresh_namecolor_options()

    def _kitmix_on_tab_shown(self) -> None:
        if not self.kitmix_team_id.get().strip():
            default_team = self.HID or self.AID or ""
            if default_team:
                self.kitmix_team_id.set(default_team)
        self._kitmix_refresh_lists()

    def _kitmix_on_team_search(self, _event=None) -> None:
        query = self.kitmix_team_search_var.get().strip().lower()
        self.kitmix_team_search_results.delete(0, "end")
        self._kitmix_team_search_ids = []
        if not query:
            self.kitmix_team_search_results.pack_forget()
            return
        self.kitmix_team_search_results.pack(
            fill="x", padx=12, pady=(0, 6), before=self._kitmix_team_search_results_anchor,
        )
        team_db = self.team_db
        if team_db is None:
            self.kitmix_team_search_results.insert("end", self.tr("dialog.kitmix.team_db_unavailable"))
            return
        matches = sorted(
            ((team_id, name) for team_id, name in team_db.team_cache.items() if query in name.lower()),
            key=lambda pair: pair[1].lower(),
        )
        if not matches:
            self.kitmix_team_search_results.insert("end", self.tr("dialog.kitmix.no_team_matches"))
            return
        for team_id, name in matches[:30]:
            self.kitmix_team_search_results.insert("end", f"{name}  ({team_id})")
            self._kitmix_team_search_ids.append(team_id)

    def _kitmix_on_team_search_select(self, _event=None) -> None:
        selection = self.kitmix_team_search_results.curselection()
        if not selection or selection[0] >= len(self._kitmix_team_search_ids):
            return
        self._kitmix_select_team(self._kitmix_team_search_ids[selection[0]])

    def _kitmix_use_home_team(self) -> None:
        self._kitmix_use_match_team(self.HID)

    def _kitmix_use_away_team(self) -> None:
        self._kitmix_use_match_team(self.AID)

    def _kitmix_use_match_team(self, team_id: str) -> None:
        team_id = (team_id or "").strip()
        if not team_id:
            messagebox.showwarning(self.tr("message.kitmix"), self.tr("message.kitmix.no_match_team"))
            return
        self._kitmix_select_team(team_id)

    def _kitmix_select_team(self, team_id: str) -> None:
        self.kitmix_team_id.set(team_id)
        self.kitmix_team_search_var.set("")
        self.kitmix_team_search_results.delete(0, "end")
        self.kitmix_team_search_results.pack_forget()
        self._kitmix_team_search_ids = []
        self._kitmix_refresh_lists()

    def _kitmix_build_inline_preview(self, parent: tk.Misc, role_key: str) -> None:
        frame = tk.Frame(parent, bg=self.card_soft, highlightthickness=1, highlightbackground="#243654")
        frame.pack(side="left", fill="y")
        label = tk.Label(
            frame, text=self.tr("dialog.kitmix.no_changes"), bg=self.panel, fg=self.muted,
            anchor="center", justify="center", wraplength=88, font=("Bahnschrift", 8),
        )
        label.pack(padx=6, pady=6, ipadx=2, ipady=2)
        label.image_size = (88, 88)
        self._kitmix_preview_labels[role_key] = label

    def _kitmix_on_source_changed(self, role_key: str, source: dict) -> None:
        from pathlib import Path

        generation = self._kitmix_preview_generation.get(role_key, 0) + 1
        self._kitmix_preview_generation[role_key] = generation
        mode = source.get("mode", "keep")
        path = source.get("path")

        if mode == "keep" or not path:
            self._kitmix_show_preview_placeholder(role_key, self.tr("dialog.kitmix.no_changes"))
            return

        if mode == "img":
            self._kitmix_show_preview_image_path(role_key, Path(path))
            return

        # mode == "rx3" or "dds": needs the 32-bit FifaLibrary bridge — render off the UI thread.
        self._kitmix_show_preview_placeholder(role_key, self.tr("dialog.kitmix.loading"))

        def worker() -> None:
            try:
                png_path = self.kit_mixer.render_preview(path, role_key)
                error = None
            except Exception as exc:  # noqa: BLE001 - surfaced as a preview placeholder
                png_path, error = None, exc
            self.after(0, lambda: self._kitmix_apply_preview_result(role_key, generation, png_path, error))

        threading.Thread(target=worker, daemon=True).start()

    def _kitmix_apply_preview_result(self, role_key: str, generation: int, png_path, error) -> None:
        # A newer selection may have superseded this one while the worker ran.
        if self._kitmix_preview_generation.get(role_key) != generation:
            return
        if error is not None or png_path is None:
            self._kitmix_show_preview_placeholder(role_key, self.tr("dialog.kitmix.preview_error"))
            return
        self._kitmix_show_preview_image_path(role_key, png_path)

    def _kitmix_show_preview_placeholder(self, role_key: str, text: str) -> None:
        label = self._kitmix_preview_labels.get(role_key)
        if not label:
            return
        self._kitmix_preview_images.pop(role_key, None)
        label.configure(image="", text=text, compound="center")

    def _kitmix_show_preview_image_path(self, role_key: str, path) -> None:
        label = self._kitmix_preview_labels.get(role_key)
        if not label:
            return
        try:
            image = Image.open(path).convert("RGBA")
            image.thumbnail(getattr(label, "image_size", (150, 150)))
            photo = ImageTk.PhotoImage(image)
        except Exception:
            self._kitmix_show_preview_placeholder(role_key, self.tr("dialog.kitmix.preview_error"))
            return
        self._kitmix_preview_images[role_key] = photo
        label.configure(image=photo, text="", compound="center")

    def _kitmix_current_team_kittype(self) -> tuple[str, str]:
        team_id = self.kitmix_team_id.get().strip()
        kittype_label = self.kitmix_kittype.get()
        kittype = next((k for k, v in self.kitmix_kittype_labels.items() if v == kittype_label), "home")
        kittype_code = KIT_TYPES.get(kittype, "0")
        return team_id, kittype_code

    def _kitmix_submit(self) -> None:
        if self.fifaEXE == "default":
            messagebox.showwarning(self.tr("message.kitmix"), self.tr("message.warning.select_fifa_first"))
            return
        team_id, kittype_code = self._kitmix_current_team_kittype()
        if not team_id:
            messagebox.showwarning(self.tr("message.kitmix"), self.tr("message.kitmix.missing_team"))
            return
        jersey = dict(self._kitmix_jersey_source)
        shorts = dict(self._kitmix_shorts_source)
        crest = dict(self._kitmix_crest_source)
        jersey_numbers = dict(self._kitmix_jersey_numbers_source)
        shorts_numbers = dict(self._kitmix_shorts_numbers_source)
        kitui = dict(self._kitmix_kitui_source)

        window = self._window()
        window.configure(cursor="watch")
        window.update_idletasks()
        try:
            result = self.kit_mixer.apply_mix(team_id, kittype_code, jersey, shorts, crest)
            self.log(f"Kit mix applied: team={team_id} kittype={kittype_code} -> {result['output']}")
            self.kit_mixer.apply_numbers(team_id, kittype_code, jersey_numbers, shorts_numbers)
            self.kit_mixer.apply_kitui(team_id, kittype_code, kitui)
            namecolor_hex = self.kitmix_namecolor_var.get().strip().lstrip("#") or None
            self.kit_mixer.apply_name_color(team_id, kittype_code, namecolor_hex)
            if self.kitmix_status_label is not None:
                self.kitmix_status_label.configure(text=self.tr("kitmix.applied_prefix", team=team_id))
            messagebox.showinfo(self.tr("message.kitmix"), self.tr("message.kitmix.apply_success", team=team_id))
        except Exception as exc:
            self.log("Failed to apply kit mix", exc, exc_info=sys.exc_info())
            messagebox.showerror(self.tr("message.kitmix"), self.tr("message.kitmix.apply_failed", error=exc))
        finally:
            window.configure(cursor="")

    def _on_kits_mousewheel(self, event) -> None:
        if self.tabview is None or self._kits_canvas is None:
            return
        current = self.tabview.nametowidget(self.tabview.select())
        if current is not self.kits_tab:
            return
        if not self._event_widget_belongs_to(event, self._kits_canvas, self._kits_canvas_body):
            return
        self._kits_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _on_kitsimple_mousewheel(self, event) -> None:
        if self.tabview is None or self._kitsimple_canvas is None:
            return
        current = self.tabview.nametowidget(self.tabview.select())
        if current is not self.kits_tab:
            return
        if not self._event_widget_belongs_to(event, self._kitsimple_canvas, self._kitsimple_canvas_body):
            return
        self._kitsimple_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _restore_team_kit(self, team_id: str) -> None:
        """Reverts every kit asset (jersey/shorts, both number slots, kit UI
        thumbnail, name color) this runtime has ever backed up for team_id,
        across all four kit types. Shared by the single-team "Restore
        Original" button and the bulk restore manager dialog."""
        for kittype in ("0", "1", "2", "3"):
            if self.kit_mixer.has_backup(team_id, kittype):
                self.kit_mixer.restore_original(team_id, kittype)
            for slot in ("jersey", "shorts"):
                if self.kit_mixer.has_backup_numbers(team_id, kittype, slot):
                    self.kit_mixer.restore_numbers_original(team_id, kittype, slot)
            if self.kit_mixer.has_backup_kitui(team_id, kittype):
                self.kit_mixer.restore_kitui_original(team_id, kittype)
        if self.kit_mixer.has_backup_name_color(team_id):
            self.kit_mixer.restore_name_color_original(team_id)

    def restore_kit_original(self) -> None:
        if self.fifaEXE == "default":
            messagebox.showwarning(self.tr("message.kitmix"), self.tr("message.warning.select_fifa_first"))
            return
        team_id = self.kitmix_team_id.get().strip()
        if not team_id:
            messagebox.showwarning(self.tr("message.kitmix"), self.tr("message.kitmix.missing_team"))
            return
        try:
            self._restore_team_kit(team_id)
            self.log(f"Kit restored to original for team {team_id}")
            messagebox.showinfo(self.tr("message.kitmix"), self.tr("message.kitmix.restore_success", team=team_id))
        except Exception as exc:
            self.log("Failed to restore kit", exc, exc_info=sys.exc_info())
            messagebox.showerror(self.tr("message.kitmix"), self.tr("message.kitmix.restore_failed", error=exc))

    def _open_kit_restore_manager(self) -> None:
        if self.fifaEXE == "default":
            messagebox.showwarning(self.tr("message.kitmix"), self.tr("message.warning.select_fifa_first"))
            return

        entries = self.kit_mixer.list_modified_kits()
        code_labels = {code: self.kitmix_kittype_labels.get(name, code) for name, code in KIT_TYPES.items()}
        kind_labels = {
            "kit": f"{self.tr('dialog.kitmix.jersey')}/{self.tr('dialog.kitmix.shorts')}",
            "numbers": self.tr("dialog.kitmix.jersey_numbers"),
            "kitui": self.tr("dialog.kitmix.kitui"),
        }

        win = tk.Toplevel(self._window())
        win.title(self.tr("dialog.kitmix.restore_manager_title"))
        win.configure(bg=self.card)
        zoom = self.settings.ui_zoom
        win.geometry(f"{round(460 * zoom)}x{round(420 * zoom)}")
        win.transient(self._window())
        win.grab_set()

        self._dark_label(
            win, self.tr("dialog.kitmix.restore_manager_hint"), bg=self.card, muted=True,
            wraplength=420, justify="left",
        ).pack(fill="x", padx=12, pady=(12, 6))

        listbox = self._dark_listbox(win, selectmode="extended", exportselection=False, font=("Consolas", 10))
        listbox.pack(fill="both", expand=True, padx=12, pady=(0, 6))

        if not entries:
            listbox.insert("end", self.tr("dialog.kitmix.restore_manager_none"))
            listbox.configure(state="disabled")
        else:
            for entry in entries:
                team_id = entry["team_id"]
                kittype = entry["kittype"]
                name = self._resolve_team_name(team_id) or ""
                team_label = f"{name} ({team_id})" if name else team_id
                if kittype is None:
                    listbox.insert("end", f"{team_label} — {self.tr('dialog.kitmix.name_color_all_kits')}")
                else:
                    kittype_label = code_labels.get(kittype, kittype)
                    kinds = ", ".join(kind_labels.get(k, k) for k in entry["kinds"])
                    listbox.insert("end", f"{team_label} — {kittype_label}: {kinds}")

        btn_row = tk.Frame(win, bg=self.card)
        btn_row.pack(fill="x", padx=12, pady=(0, 12))

        def select_all() -> None:
            listbox.selection_set(0, "end")

        def do_restore() -> None:
            selection = listbox.curselection()
            if not entries or not selection:
                return
            restored_labels: list[str] = []
            failed_labels: list[str] = []
            restored_team_ids: set[str] = set()
            for i in selection:
                entry = entries[i]
                team_id = entry["team_id"]
                kittype = entry["kittype"]
                label = listbox.get(i)
                try:
                    if kittype is None:
                        self.kit_mixer.restore_name_color_original(team_id)
                    else:
                        self.kit_mixer.restore_kit_type(team_id, kittype)
                    restored_labels.append(label)
                    restored_team_ids.add(team_id)
                except Exception as exc:
                    self.log(f"Failed to restore {label}", exc, exc_info=sys.exc_info())
                    failed_labels.append(label)
            if restored_labels:
                self.log(f"Bulk-restored: {', '.join(restored_labels)}")
            if self.kitmix_team_id.get().strip() in restored_team_ids:
                self._kitmix_refresh_lists()
            win.destroy()
            if failed_labels:
                messagebox.showerror(self.tr("message.kitmix"), self.tr("message.kitmix.restore_failed", error=", ".join(failed_labels)))
            elif restored_labels:
                messagebox.showinfo(self.tr("message.kitmix"), self.tr("message.kitmix.restore_success", team=", ".join(restored_labels)))

        ttk.Button(btn_row, text=self.tr("dialog.kitmix.select_all"), command=select_all).pack(side="left")
        ttk.Button(btn_row, text=self.tr("button.restore_kit_original"), command=do_restore).pack(side="right")

    def _build_kits_simple_tab(self, parent: tk.Misc) -> None:
        """Simple Mode: pick one already-bundled "kit set" (a kit_<team>_<kittype>_
        <tourn_id>.rx3 plus whatever companion numbers/kitui files share that same
        tourn_id, see KitMixRuntime.list_kit_sets) and apply it all in one click,
        instead of the advanced tab's 6 independent per-asset pickers. Shares the
        team_id/kittype selection state with the advanced tab (self.kitmix_team_id,
        self.kitmix_kittype) so switching tabs keeps the same team/kit type."""
        outer = tk.Frame(parent, bg=self.bg)
        outer.pack(fill="both", expand=True, padx=10, pady=10)

        card = self._card(outer, "card.kitmix_simple.title", "card.kitmix_simple.subtitle")
        card.pack(fill="both", expand=True)

        self._kitsimple_kit_sets: list[dict] = []
        self._kitsimple_preview_images: dict = {}
        self._kitsimple_preview_generation = 0

        # Fixed footer — packed before the scroll area so "Apply Kit" stays
        # visible even when the window is short (mirrors the advanced tab's
        # pattern, see _build_kits_advanced_tab).
        footer = tk.Frame(card, bg=self.card)
        footer.pack(side="bottom", fill="x", padx=12, pady=(6, 12))
        self._kitsimple_footer_frame = footer
        self.kitsimple_status_label = tk.Label(footer, text=self.display_value("idle"), bg=self.card, fg=self.muted, font=("Bahnschrift", 9))
        self.kitsimple_status_label.pack(anchor="w", pady=(0, 4))
        ttk.Button(footer, text=self.tr("button.apply_kit_set"), command=self._kitsimple_apply).pack(fill="x")

        # Scrollable body: team selector, kit list + preview, GK link row.
        scroll_host = tk.Frame(card, bg=self.card)
        scroll_host.pack(fill="both", expand=True, padx=12, pady=(0, 6))
        canvas = tk.Canvas(scroll_host, bg=self.card, highlightthickness=0, bd=0)
        scrollbar = ttk.Scrollbar(scroll_host, orient="vertical", command=canvas.yview, style="Server16.Vertical.TScrollbar")
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        scroll_body = tk.Frame(canvas, bg=self.card)
        canvas_win = canvas.create_window((0, 0), window=scroll_body, anchor="nw")

        def _on_body_configure(*_):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _on_canvas_configure(e):
            canvas.itemconfig(canvas_win, width=e.width)

        scroll_body.bind("<Configure>", _on_body_configure)
        canvas.bind("<Configure>", _on_canvas_configure)
        self._kitsimple_canvas = canvas
        self._kitsimple_canvas_body = scroll_body
        # add="+" — see the comment on the dashboard's bind_all for why this must
        # not replace other tabs' scoped mousewheel handlers.
        canvas.bind_all("<MouseWheel>", self._on_kitsimple_mousewheel, add="+")

        top = tk.Frame(scroll_body, bg=self.card)
        top.pack(fill="x", pady=(0, 6))
        self._dark_label(top, self.tr("dialog.kitmix.team_id"), bg=self.card, muted=True).pack(side="left")
        ttk.Entry(top, textvariable=self.kitmix_team_id, width=10).pack(side="left", padx=(6, 12))
        self._dark_label(top, self.tr("dialog.kitmix.kit_type"), bg=self.card, muted=True).pack(side="left")
        kittype_combo = ttk.Combobox(
            top, state="readonly", textvariable=self.kitmix_kittype,
            values=tuple(self.kitmix_kittype_labels.values()), width=10,
            style="Server16.TCombobox",
        )
        kittype_combo.pack(side="left", padx=(6, 12))
        kittype_combo.bind("<<ComboboxSelected>>", lambda _e: self._kitsimple_refresh_lists())
        ttk.Button(top, text=self.tr("dialog.kitmix.refresh"), command=self._kitsimple_refresh_lists).pack(side="left")
        self.kitsimple_team_name_label = self._dark_label(top, "", bg=self.card, muted=True)
        self.kitsimple_team_name_label.pack(side="left", padx=(12, 0))

        search_row = tk.Frame(scroll_body, bg=self.card)
        search_row.pack(fill="x", pady=(0, 6))
        ttk.Button(search_row, text=self.tr("button.use_home_team"), command=self._kitsimple_use_home_team).pack(side="left", padx=(0, 6))
        ttk.Button(search_row, text=self.tr("button.use_away_team"), command=self._kitsimple_use_away_team).pack(side="left")

        body = tk.Frame(scroll_body, bg=self.card)
        body.pack(fill="both", expand=True, pady=(0, 6))

        list_frame = tk.Frame(body, bg=self.card)
        list_frame.pack(side="left", fill="both", expand=True, padx=(0, 8))
        self._kitsimple_listbox = self._dark_listbox(list_frame, exportselection=False, height=12, font=("Consolas", 10))
        self._kitsimple_listbox.pack(fill="both", expand=True)
        self._kitsimple_listbox.bind("<<ListboxSelect>>", self._kitsimple_on_select)

        preview_frame = tk.Frame(body, bg=self.card_soft, highlightthickness=1, highlightbackground="#243654")
        preview_frame.pack(side="left", fill="y")
        preview_label = tk.Label(
            preview_frame, text=self.tr("dialog.kitmix.no_changes"), bg=self.panel, fg=self.muted,
            anchor="center", justify="center", wraplength=170, font=("Bahnschrift", 9),
        )
        preview_label.pack(padx=8, pady=8, ipadx=4, ipady=4)
        preview_label.image_size = (170, 170)
        self._kitsimple_preview_label = preview_label

        gk_row = tk.Frame(scroll_body, bg=self.card)
        gk_row.pack(fill="x", pady=(0, 8))
        self.kitsimple_gk_row = gk_row
        self._dark_label(gk_row, self.tr("kitsimple.gk_link_label"), bg=self.card, muted=True).pack(side="left")
        self.kitsimple_gk_var = tk.StringVar(value=KITSIMPLE_GK_NONE_LABEL)
        self._kitsimple_gk_options: dict[str, str] = {}
        gk_combo = ttk.Combobox(
            gk_row, state="readonly", textvariable=self.kitsimple_gk_var,
            values=(KITSIMPLE_GK_NONE_LABEL,), width=24, style="Server16.TCombobox",
        )
        gk_combo.pack(side="left", padx=(6, 0))
        self.kitsimple_gk_combo = gk_combo

        self._kitsimple_refresh_lists()

    def _kitsimple_current_kittype_code(self) -> str:
        kittype_label = self.kitmix_kittype.get()
        kittype = next((k for k, v in self.kitmix_kittype_labels.items() if v == kittype_label), "home")
        return KIT_TYPES.get(kittype, "0")

    def _kitsimple_refresh_lists(self) -> None:
        team_id = self.kitmix_team_id.get().strip()
        name = self._resolve_team_name(team_id) if team_id else None
        if self.kitsimple_team_name_label is not None:
            label_text = name or ""
            if team_id:
                folder_name = self.kit_mixer.kits_folder_name(team_id)
                if folder_name != team_id:
                    label_text = f"{label_text} ({folder_name})" if label_text else folder_name
            self.kitsimple_team_name_label.configure(text=label_text)

        kittype_code = self._kitsimple_current_kittype_code()
        self._kitsimple_kit_sets = self.kit_mixer.list_kit_sets(team_id, kittype_code) if team_id else []

        listbox = self._kitsimple_listbox
        listbox.configure(state="normal")
        listbox.delete(0, "end")
        if not self._kitsimple_kit_sets:
            listbox.insert("end", self.tr("kitsimple.no_sets"))
            listbox.configure(state="disabled")
        else:
            for entry in self._kitsimple_kit_sets:
                status = self.tr("kitsimple.complete") if entry["complete"] else self.tr("kitsimple.partial")
                listbox.insert("end", f"{entry['tourn_id']}  —  {status}")
            listbox.selection_clear(0, "end")
            listbox.selection_set(0)
        self._kitsimple_refresh_gk_options()
        self._kitsimple_on_select()

    def _kitsimple_refresh_gk_options(self) -> None:
        """Populates the "link goalkeeper kit" combobox from this team's own
        keeper kit sets (list_kit_sets(team_id, "2")) — only shown for
        Home/Away, since third-kit linking is out of scope and a keeper kit
        can't sensibly link to another keeper kit."""
        kittype_code = self._kitsimple_current_kittype_code()
        if kittype_code not in ("0", "1"):
            self.kitsimple_gk_row.pack_forget()
            return
        if not self.kitsimple_gk_row.winfo_ismapped():
            self.kitsimple_gk_row.pack(fill="x", pady=(0, 8))

        team_id = self.kitmix_team_id.get().strip()
        gk_sets = self.kit_mixer.list_kit_sets(team_id, "2") if team_id else []
        values = [KITSIMPLE_GK_NONE_LABEL] + [entry["tourn_id"] for entry in gk_sets]
        self.kitsimple_gk_combo.configure(values=tuple(values))
        if self.kitsimple_gk_var.get() not in values:
            self.kitsimple_gk_var.set(KITSIMPLE_GK_NONE_LABEL)

    def _kitsimple_sync_gk_selection(self) -> None:
        """Reflects whatever GK link is already saved (settings.ini [kitgk])
        for the currently-selected outfield kit set — the link is per exact
        (team_id, tourn_id), so this must re-run every time the listbox
        selection changes, not just on tab refresh."""
        kittype_code = self._kitsimple_current_kittype_code()
        if kittype_code not in ("0", "1"):
            return
        listbox = self._kitsimple_listbox
        selection = listbox.curselection()
        if not selection or not self._kitsimple_kit_sets or selection[0] >= len(self._kitsimple_kit_sets):
            self.kitsimple_gk_var.set(KITSIMPLE_GK_NONE_LABEL)
            return
        team_id = self.kitmix_team_id.get().strip()
        tourn_id = self._kitsimple_kit_sets[selection[0]]["tourn_id"]
        linked = self.kit_mixer.get_linked_gk_tourn(team_id, tourn_id) if team_id else None
        available = self.kitsimple_gk_combo.cget("values")
        self.kitsimple_gk_var.set(linked if linked and linked in available else KITSIMPLE_GK_NONE_LABEL)

    def _kitsimple_selected_gk_tourn(self) -> str | None:
        value = self.kitsimple_gk_var.get()
        return value if value and value != KITSIMPLE_GK_NONE_LABEL else None

    def _kitsimple_on_tab_shown(self) -> None:
        if not self.kitmix_team_id.get().strip():
            default_team = self.HID or self.AID or ""
            if default_team:
                self.kitmix_team_id.set(default_team)
        self._kitsimple_refresh_lists()

    def _kitsimple_use_home_team(self) -> None:
        self._kitsimple_use_match_team(self.HID)

    def _kitsimple_use_away_team(self) -> None:
        self._kitsimple_use_match_team(self.AID)

    def _kitsimple_use_match_team(self, team_id: str) -> None:
        team_id = (team_id or "").strip()
        if not team_id:
            messagebox.showwarning(self.tr("message.kitmix"), self.tr("message.kitmix.no_match_team"))
            return
        self.kitmix_team_id.set(team_id)
        self._kitsimple_refresh_lists()

    def _kitsimple_on_select(self, _event=None) -> None:
        listbox = self._kitsimple_listbox
        selection = listbox.curselection()
        self._kitsimple_sync_gk_selection()
        generation = self._kitsimple_preview_generation + 1
        self._kitsimple_preview_generation = generation
        if not selection or not self._kitsimple_kit_sets or selection[0] >= len(self._kitsimple_kit_sets):
            self._kitsimple_show_preview_placeholder(self.tr("dialog.kitmix.no_changes"))
            return

        entry = self._kitsimple_kit_sets[selection[0]]
        if entry["kitui_path"] is None:
            fallback = kit_ui_placeholder_path()
            if fallback is not None:
                self._kitsimple_show_preview_image_path(fallback)
            else:
                self._kitsimple_show_preview_placeholder(self.tr("dialog.kitmix.no_changes"))
            return

        source_path = entry["kitui_path"]
        team_id = self.kitmix_team_id.get().strip()
        kittype_code = self._kitsimple_current_kittype_code()
        cache_key = f"{team_id}_{kittype_code}_{entry['tourn_id']}"

        self._kitsimple_show_preview_placeholder(self.tr("dialog.kitmix.loading"))

        def worker() -> None:
            try:
                png_path = self.kit_mixer.render_preview(str(source_path), "kitui", cache_key=cache_key)
                error = None
            except Exception as exc:  # noqa: BLE001 - surfaced as a preview placeholder
                png_path, error = None, exc
            self.after(0, lambda: self._kitsimple_apply_preview_result(generation, png_path, error))

        threading.Thread(target=worker, daemon=True).start()

    def _kitsimple_apply_preview_result(self, generation: int, png_path, error) -> None:
        # A newer selection may have superseded this one while the worker ran.
        if self._kitsimple_preview_generation != generation:
            return
        if error is not None or png_path is None:
            self._kitsimple_show_preview_placeholder(self.tr("dialog.kitmix.preview_error"))
            return
        self._kitsimple_show_preview_image_path(png_path)

    def _kitsimple_show_preview_placeholder(self, text: str) -> None:
        label = self._kitsimple_preview_label
        if not label:
            return
        self._kitsimple_preview_images.pop("current", None)
        label.configure(image="", text=text, compound="center")

    def _kitsimple_show_preview_image_path(self, path) -> None:
        label = self._kitsimple_preview_label
        if not label:
            return
        try:
            image = Image.open(path).convert("RGBA")
            image.thumbnail(getattr(label, "image_size", (170, 170)))
            photo = ImageTk.PhotoImage(image)
        except Exception:
            self._kitsimple_show_preview_placeholder(self.tr("dialog.kitmix.preview_error"))
            return
        self._kitsimple_preview_images["current"] = photo
        label.configure(image=photo, text="", compound="center")

    def _kitsimple_apply(self) -> None:
        if self.fifaEXE == "default":
            messagebox.showwarning(self.tr("message.kitmix"), self.tr("message.warning.select_fifa_first"))
            return
        team_id = self.kitmix_team_id.get().strip()
        if not team_id:
            messagebox.showwarning(self.tr("message.kitmix"), self.tr("message.kitmix.missing_team"))
            return
        selection = self._kitsimple_listbox.curselection()
        if not selection or not self._kitsimple_kit_sets or selection[0] >= len(self._kitsimple_kit_sets):
            messagebox.showwarning(self.tr("message.kitmix"), self.tr("message.kitsimple.missing_selection"))
            return
        entry = self._kitsimple_kit_sets[selection[0]]
        kittype_code = self._kitsimple_current_kittype_code()

        if kittype_code in ("0", "1"):
            self.kit_mixer.set_linked_gk_tourn(team_id, entry["tourn_id"], self._kitsimple_selected_gk_tourn())

        window = self._window()
        window.configure(cursor="watch")
        window.update_idletasks()
        try:
            self.kit_mixer.apply_kit_set_linked(team_id, kittype_code, entry["tourn_id"])
            if self.kitsimple_status_label is not None:
                self.kitsimple_status_label.configure(text=self.tr("kitmix.applied_prefix", team=team_id))
            messagebox.showinfo(self.tr("message.kitmix"), self.tr("message.kitsimple.apply_success", team=team_id))
        except Exception as exc:
            self.log("Failed to apply kit set", exc, exc_info=sys.exc_info())
            messagebox.showerror(self.tr("message.kitmix"), self.tr("message.kitsimple.apply_failed", error=exc))
        finally:
            window.configure(cursor="")

    def _build_stadium_card(self, parent: tk.Misc, row: int) -> None:
        card = self._card(parent, "card.stadium.title", "card.stadium.subtitle")
        card.grid(row=row, column=0, sticky="nsew", pady=(0, 12))
        card.configure(height=358)
        card.grid_propagate(False)
        preview = tk.Label(
            card,
            text=self.tr("placeholder.stadium_preview"),
            bg=self.card_soft,
            fg=self.muted,
            font=("Bahnschrift", 12, "bold"),
            justify="center",
            anchor="center",
            highlightthickness=1,
            highlightbackground="#243654",
        )
        preview.pack(fill="x", padx=12, pady=(6, 10), ipady=40)
        self._stadium_preview_label = preview
        body = tk.Frame(card, bg=self.card)
        body.pack(fill="x", padx=12, pady=(0, 12))
        body.grid_columnconfigure(0, weight=1)
        self._build_stat(body, 0, 0, "stat.current_stadium", "stadium", "-", value_wraplength=300, block_height=64)
        self._build_stat(body, 1, 0, "stat.stadium_id", "stadid", "-")
        ttk.Button(card, text=self.tr("button.assign_stadium"), command=self.assign_stadium).pack(fill="x", padx=12, pady=(0, 10))
        ttk.Button(card, text=self.tr("button.edit_stadium_settings"), command=self.open_stadium_settings_editor).pack(fill="x", padx=12, pady=(0, 10))
        self.progress_text_label = tk.Label(card, text=self.display_value("idle"), bg=self.card, fg=self.muted, font=("Bahnschrift", 9))
        self.progress_text_label.pack(anchor="w", padx=12, pady=(0, 4))
        self.progress_value = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(card, maximum=100, variable=self.progress_value, style="Accent.Horizontal.TProgressbar")
        self.progress_bar.pack(fill="x", padx=12, pady=(0, 12))
        self._set_progress(0, self.display_value("idle"))
        self._update_stadium_preview(self.labels["stadium"].cget("text"))

    def _build_modules_card(self, parent: tk.Misc, row: int) -> None:
        card = self._card(parent, "card.modules.title", "card.modules.subtitle")
        card.grid(row=row, column=0, sticky="ew")
        card.configure(height=290)
        card.grid_propagate(False)
        modules = tk.Frame(card, bg=self.card)
        modules.pack(fill="x", padx=12, pady=(6, 12))
        module_names = [
            "Stadium", "TvLogo", "ScoreBoard", "Movies", "Autorun",
            "StadiumNet", "Chants", "StadiumName", "AwayChants", "AwayClubSong",
            "DiscordRPC",
        ]
        for idx, name in enumerate(module_names):
            initial = self._discord_rpc_enabled if name == "DiscordRPC" else False
            var = tk.BooleanVar(value=initial)
            self.module_vars[name] = var
            check = ttk.Checkbutton(
                modules,
                style="Switch.TCheckbutton",
                text=name,
                variable=var,
                command=lambda n=name, v=var: self._on_module_toggle(n, v),
            )
            check.grid(row=idx // 2, column=idx % 2, padx=6, pady=4, sticky="w")
            self.module_checks[name] = check

        tk.Label(card, text=self.tr("label.app_options"), bg=self.card, fg=self.muted, font=("Bahnschrift", 9)).pack(anchor="w", padx=12, pady=(4, 2))

        notification_switch = ttk.Checkbutton(
            card,
            style="Switch.TCheckbutton",
            text="Show loading notification",
            variable=self.show_stadium_loading_var,
            command=self._toggle_stadium_loading_visibility,
        )
        notification_switch.pack(anchor="w", padx=12, pady=(0, 4))

        overlay_switch = ttk.Checkbutton(
            card,
            style="Switch.TCheckbutton",
            text=self.tr("toggle.show_overlay"),
            variable=self.show_overlay_var,
            command=self._toggle_overlay_enabled,
        )
        overlay_switch.pack(anchor="w", padx=12, pady=(0, 4))

        kit_hotkeys_switch = ttk.Checkbutton(
            card,
            style="Switch.TCheckbutton",
            text=self.tr("toggle.kit_hotkeys"),
            variable=self.kit_hotkeys_var,
            command=self._toggle_kit_hotkeys,
        )
        kit_hotkeys_switch.pack(anchor="w", padx=12, pady=(0, 4))

        keep_open_switch = ttk.Checkbutton(
            card,
            style="Switch.TCheckbutton",
            text=self.tr("toggle.keep_open"),
            variable=self.keep_open_var,
            command=self._toggle_keep_open,
        )
        keep_open_switch.pack(anchor="w", padx=12, pady=(0, 10))

    def _toggle_discord_rpc(self) -> None:
        new_state = self.module_vars["DiscordRPC"].get()
        self._discord_rpc_enabled = new_state
        discord_config = self.settings.data.get("discord_rpc", {})
        discord_config["enabled"] = new_state
        self.settings.data["discord_rpc"] = discord_config
        self.settings.save()
        self.module_states["DiscordRPC"] = new_state
        self.settings_ini.write("DiscordRPC", "1" if new_state else "0", "Modules")
        self.settings_ini.save()
        try:
            if new_state:
                success = self.discord_rpc.connect()
                if success:
                    self.log("DiscordRPC enabled and connected")
                else:
                    self.log("DiscordRPC enabled but failed to connect (Discord may not be running)")
            else:
                self.discord_rpc.disconnect()
                self.log("DiscordRPC disabled and presence cleared")
        except Exception as exc:
            self.log("Error toggling DiscordRPC", exc, exc_info=sys.exc_info())
            self._discord_rpc_enabled = not new_state
            self.module_states["DiscordRPC"] = not new_state
            self.module_vars["DiscordRPC"].set(not new_state)
            discord_config["enabled"] = not new_state
            self.settings.data["discord_rpc"] = discord_config
            self.settings.save()
            self.settings_ini.write("DiscordRPC", "1" if not new_state else "0", "Modules")
            self.settings_ini.save()

    def _toggle_stadium_loading_visibility(self) -> None:
        self.settings.show_stadium_loading_notification = self.show_stadium_loading_var.get()
        self.settings.save()
        if self.show_stadium_loading_var.get():
            return
        self._hide_stadium_loading_modal()

    def _toggle_kit_mix_sound(self) -> None:
        self.settings.kit_mix_sound_feedback = self.kit_mix_sound_var.get()

    def _toggle_keep_open(self) -> None:
        self.settings.keep_open_on_game_close = self.keep_open_var.get()
        self.settings.save()

    def _toggle_custom_kit_numbers(self) -> None:
        from .file_tools import general_lua_is_foreign, set_kit_number_scheme

        custom = self._setup_install_vars["custom_kit_numbers"].get()
        self.settings.custom_kit_numbers = custom
        general_lua = self.exedir / "data" / "fifarna" / "lua" / "assignments" / "general.lua"
        template = None
        for base in (self.resource_dir, self.base_dir):
            candidate = base / "install_data" / "data" / "fifarna" / "lua" / "assignments" / "general.lua"
            if candidate.exists():
                template = candidate
                break
        if template is not None and general_lua_is_foreign(general_lua, template):
            messagebox.showwarning(
                self.tr("message.kit_numbers"),
                self.tr("message.warning.foreign_general_lua"),
            )
            return
        set_kit_number_scheme(general_lua, custom, template)

    def _toggle_kit_hotkeys(self) -> None:
        self.settings.kit_hotkeys_enabled = self.kit_hotkeys_var.get()
        self.settings.save()

    def _toggle_overlay_enabled(self) -> None:
        self.settings.show_overlay = self.show_overlay_var.get()
        self.settings.save()
        if not self.show_overlay_var.get() and self._d3d_menu_visible:
            self._d3d_menu_visible = False
            self._overlay_wizard_phase = None
            self._overlay_wizard_stadium = None
            self._uninstall_mouse_wheel_hook()
            self._uninstall_keyboard_hook()
            self._publish_overlay_menu_state()

    def _build_audio_card(self) -> None:
        card = self._card(self.audio_tab, "card.chants.title", "card.chants.subtitle")
        card.pack(fill="both", expand=True, padx=10, pady=10)
        body = tk.Frame(card, bg=self.card)
        body.pack(fill="both", expand=True, padx=12, pady=(6, 12))
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=1)
        self._build_stat(body, 0, 0, "stat.chants_module", "audio_module", self.display_value("disabled"))
        self._build_stat(body, 0, 1, "stat.chants_status", "audio_status", self.display_value("idle"))
        self._build_stat(body, 1, 0, "stat.current_chant", "audio_current", "-")
        self._build_stat(body, 1, 1, "stat.club_anthem", "audio_clubsong", "-")
        self._build_stat(body, 2, 0, "stat.chants_folder", "audio_chants_dir", "-")
        self._build_stat(body, 2, 1, "stat.last_action", "audio_last_action", "-")
        self._build_stat(body, 3, 0, "stat.crowd_mode", "audio_crowd_mode", self.display_value("idle"))
        self._build_stat(body, 3, 1, "stat.crowd_volume", "audio_crowd_volume", "-")
        self._build_stat(body, 4, 0, "stat.crowd_source", "audio_source", "-")
        self._build_stat(body, 4, 1, "stat.next_behavior", "audio_next", "-")
        self._build_stat(body, 5, 0, "stat.home_goals", "home_goals", "0")
        self._build_stat(body, 5, 1, "stat.away_goals", "away_goals", "0")
        btn_row = tk.Frame(card, bg=self.card)
        btn_row.pack(fill="x", padx=12, pady=(0, 12))
        self._fix_chants_audio_btn = ttk.Button(btn_row, text=self.tr("button.fix_chants_audio"), command=self._run_fix_chants_audio)
        self._fix_chants_audio_btn.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self._edit_chants_settings_btn = ttk.Button(btn_row, text=self.tr("button.edit_chants_settings"), command=self.open_audio_settings_editor)
        self._edit_chants_settings_btn.pack(side="left", fill="x", expand=True)

    def _set_chants_fix_buttons_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        fix_btn = getattr(self, "_fix_chants_audio_btn", None)
        edit_btn = getattr(self, "_edit_chants_settings_btn", None)
        if fix_btn:
            fix_btn.configure(state=state)
        if edit_btn:
            edit_btn.configure(state=state)

    def _run_fix_chants_audio(self) -> None:
        self._set_chants_fix_buttons_enabled(False)

        def _scan() -> None:
            try:
                paths = self.chants_runtime.scan_chants_audio_files()
            except Exception as exc:
                self.log(f"Scan chants audio failed: {exc}")
                paths = None
            self.after(0, lambda: _after_scan(paths))

        def _after_scan(paths: list | None) -> None:
            self._set_chants_fix_buttons_enabled(True)
            if paths is None:
                messagebox.showerror(self.tr("message.chants"), self.tr("message.chants_fix_error"))
                return
            if not paths:
                messagebox.showinfo(self.tr("message.chants"), self.tr("message.chants_fix_none"))
                return
            self._open_chants_fix_dialog(paths)

        threading.Thread(target=_scan, daemon=True).start()

    def _open_chants_fix_dialog(self, paths: list) -> None:
        root_dir = self.exedir / "FSW" / "Chants"

        win = tk.Toplevel(self._window())
        win.title(self.tr("dialog.chants_fix.title"))
        win.configure(bg=self.card)
        zoom = self.settings.ui_zoom
        win.geometry(f"{round(520 * zoom)}x{round(460 * zoom)}")
        win.transient(self._window())
        win.grab_set()

        self._dark_label(
            win, self.tr("dialog.chants_fix.hint", count=len(paths)), bg=self.card, muted=True,
            wraplength=480, justify="left",
        ).pack(fill="x", padx=12, pady=(12, 6))

        keep_backup_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            win,
            style="Switch.TCheckbutton",
            text=self.tr("dialog.chants_fix.keep_backup"),
            variable=keep_backup_var,
        ).pack(anchor="w", padx=12, pady=(0, 6))

        listbox = self._dark_listbox(win, selectmode="extended", exportselection=False, font=("Consolas", 9))
        listbox.pack(fill="both", expand=True, padx=12, pady=(0, 6))
        for path in paths:
            try:
                label = str(path.relative_to(root_dir))
            except ValueError:
                label = str(path)
            listbox.insert("end", label)
        listbox.selection_set(0, "end")

        btn_row = tk.Frame(win, bg=self.card)
        btn_row.pack(fill="x", padx=12, pady=(0, 12))

        def select_all() -> None:
            listbox.selection_set(0, "end")

        def do_fix() -> None:
            selection = listbox.curselection()
            if not selection:
                return
            selected_paths = [paths[i] for i in selection]
            keep_backup = keep_backup_var.get()
            win.destroy()
            self._run_fix_chants_audio_confirmed(selected_paths, keep_backup)

        ttk.Button(btn_row, text=self.tr("dialog.chants_fix.select_all"), command=select_all).pack(side="left")
        ttk.Button(btn_row, text=self.tr("button.fix_chants_audio"), command=do_fix).pack(side="right")

    def _run_fix_chants_audio_confirmed(self, paths: list, keep_backup: bool) -> None:
        self._set_chants_fix_buttons_enabled(False)

        def _work() -> None:
            try:
                counts = self.chants_runtime.fix_chants_audio_files(paths, keep_backup=keep_backup)
            except Exception as exc:
                self.log(f"Fix chants audio failed: {exc}")
                counts = None
            self.after(0, lambda: _done(counts))

        def _done(counts: dict[str, int] | None) -> None:
            self._set_chants_fix_buttons_enabled(True)
            if counts is None:
                messagebox.showerror(self.tr("message.chants"), self.tr("message.chants_fix_error"))
                return
            self.log(f"Fix chants audio: fixed={counts['fixed']} already_clean={counts['already_clean']} errors={counts['errors']}")
            messagebox.showinfo(
                self.tr("message.chants"),
                self.tr(
                    "message.chants_fix_result",
                    fixed=counts["fixed"],
                    clean=counts["already_clean"],
                    errors=counts["errors"],
                ),
            )

        threading.Thread(target=_work, daemon=True).start()

    def _build_camera_tab(self) -> None:
        card_host = tk.Frame(self.camera_tab, bg=self.bg)
        card_host.pack(fill="both", expand=True, padx=10, pady=10)
        card_host.grid_columnconfigure(0, weight=2)
        card_host.grid_columnconfigure(1, weight=3)
        card_host.grid_rowconfigure(0, weight=1)

        library_card = self._card(card_host, "card.camera_library.title", "card.camera_library.subtitle")
        self.camera_library_card = library_card
        library_card.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        library_body = tk.Frame(library_card, bg=self.card)
        library_body.pack(fill="both", expand=True, padx=12, pady=(6, 12))
        self.camera_select_button = ttk.Button(
            library_body,
            text=self.tr("button.choose_camera_package"),
            command=self.select_camera_package,
        )
        self.camera_select_button.pack(fill="x", pady=(0, 8))
        self.camera_package_label = tk.Label(
            library_body,
            text=self.tr("camera.no_package_selected"),
            bg=self.card,
            fg=self.muted,
            font=("Bahnschrift", 9),
            anchor="w",
            justify="left",
        )
        self.camera_package_label.pack(fill="x", pady=(0, 8))
        list_frame = tk.Frame(library_body, bg=self.card)
        list_frame.pack(fill="both", expand=True)
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", style="Server16.Vertical.TScrollbar")
        self.camera_listbox = tk.Listbox(
            list_frame,
            bg=self.panel_alt,
            fg=self.fg,
            selectbackground="#1b3453",
            selectforeground=self.fg,
            activestyle="none",
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            font=("Bahnschrift", 11),
            yscrollcommand=scrollbar.set,
        )
        scrollbar.configure(command=self.camera_listbox.yview)
        self.camera_listbox.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.camera_listbox.bind("<<ListboxSelect>>", self._on_camera_select)

        detail_card = self._card(card_host, "card.camera_preview.title", "card.camera_preview.subtitle")
        self.camera_preview_card = detail_card
        detail_card.grid(row=0, column=1, sticky="nsew")
        detail_body = tk.Frame(detail_card, bg=self.card)
        detail_body.pack(fill="both", expand=True, padx=12, pady=(6, 12))
        detail_body.grid_columnconfigure(0, weight=1)
        detail_body.grid_rowconfigure(1, weight=1)
        self.camera_name_label = tk.Label(
            detail_body,
            text=self.tr("camera.no_camera_selected"),
            bg=self.card,
            fg=self.gold,
            font=("Bahnschrift", 14, "bold"),
            anchor="w",
        )
        self.camera_name_label.grid(row=0, column=0, sticky="ew")
        preview_shell = tk.Frame(detail_body, bg=self.card_soft, highlightthickness=1, highlightbackground="#243654")
        preview_shell.grid(row=1, column=0, sticky="nsew", pady=(10, 10))
        preview_shell.grid_columnconfigure(0, weight=1)
        preview_shell.grid_rowconfigure(0, weight=1)
        self.camera_preview_canvas = tk.Canvas(
            preview_shell,
            bg=self.card_soft,
            highlightthickness=0,
            bd=0,
        )
        self.camera_preview_canvas.grid(row=0, column=0, sticky="nsew")
        self.camera_preview_frame = tk.Frame(self.camera_preview_canvas, bg=self.card_soft)
        self._camera_preview_canvas_window = self.camera_preview_canvas.create_window((0, 0), window=self.camera_preview_frame, anchor="nw")
        self.camera_preview_canvas.bind("<Configure>", self._on_camera_preview_canvas_configure)
        self.camera_preview_image_label = tk.Label(
            self.camera_preview_frame,
            text=self.tr("placeholder.preview"),
            bg=self.card_soft,
            fg=self.muted,
            font=("Bahnschrift", 12, "bold"),
            bd=0,
            relief="flat",
            compound="center",
            anchor="center",
            justify="center",
            padx=12,
            pady=12,
        )
        self.camera_preview_image_label.pack(anchor="nw")
        self.camera_preview_status = tk.Label(
            detail_body,
            text=self.tr("camera.no_preview"),
            bg=self.card,
            fg=self.muted,
            font=("Bahnschrift", 9),
            anchor="w",
        )
        self.camera_preview_status.grid(row=2, column=0, sticky="ew", pady=(0, 6))
        self.camera_example_combo = ttk.Combobox(detail_body, state="readonly", textvariable=self.camera_example_var)
        self.camera_example_combo.grid(row=3, column=0, sticky="ew", pady=(0, 8))
        self.camera_example_combo.bind("<<ComboboxSelected>>", self._on_camera_example_change)
        instruction_host = tk.Frame(detail_body, bg=self.panel)
        instruction_host.grid(row=4, column=0, sticky="nsew")
        self.camera_instruction_text = tk.Text(
            instruction_host,
            height=5,
            bg=self.panel,
            fg=self.fg,
            insertbackground=self.fg,
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            font=("Consolas", 9),
            wrap="word",
        )
        camera_instruction_scrollbar = ttk.Scrollbar(
            instruction_host,
            orient="vertical",
            command=self.camera_instruction_text.yview,
            style="Server16.Vertical.TScrollbar",
        )
        self.camera_instruction_text.configure(yscrollcommand=camera_instruction_scrollbar.set)
        self.camera_instruction_text.pack(side="left", fill="both", expand=True)
        camera_instruction_scrollbar.pack(side="right", fill="y")
        self.camera_instruction_text.configure(state="disabled")
        self.camera_apply_button = ttk.Button(detail_body, text=self.tr("button.apply_camera"), command=self.apply_selected_camera)
        self.camera_apply_button.grid(row=5, column=0, sticky="ew", pady=(12, 0))

    def _build_setup_tab(self) -> None:
        outer = tk.Frame(self.setup_tab, bg=self.bg)
        outer.pack(fill="both", expand=True, padx=10, pady=10)

        sub_notebook = ttk.Notebook(outer, style="Server16.TNotebook")
        sub_notebook.pack(fill="both", expand=True)
        self._setup_sub_notebook = sub_notebook

        general_tab = tk.Frame(sub_notebook, bg=self.bg)
        assets_tab = tk.Frame(sub_notebook, bg=self.bg)
        sub_notebook.add(general_tab, text=self.tr("tab.setup.general"))
        sub_notebook.add(assets_tab, text=self.tr("tab.setup.assets"))

        self._build_setup_general_tab(general_tab)
        self._build_setup_assets_tab(assets_tab)

        self.refresh_setup_tab()

    def _build_setup_general_tab(self, parent: tk.Frame) -> None:
        card = self._card(parent, "card.setup.title", "card.setup.subtitle")
        card.pack(fill="both", expand=True)

        # Fixed footer — packed before the scroll area so it stays visible
        footer = tk.Frame(card, bg=self.card)
        footer.pack(side="bottom", fill="x", padx=12, pady=(4, 12))
        pb_row = tk.Frame(footer, bg=self.card)
        pb_row.pack(fill="x", pady=(0, 6))
        self._setup_progressbar = ttk.Progressbar(pb_row, mode="determinate", maximum=100, style="Accent.Horizontal.TProgressbar")
        self._setup_progressbar.pack(side="left", fill="x", expand=True)
        self._setup_progress_label = tk.Label(pb_row, text="", bg=self.card, fg=self.muted, font=("Bahnschrift", 9), width=22, anchor="w")
        self._setup_progress_label.pack(side="left", padx=(8, 0))
        btn_row = tk.Frame(footer, bg=self.card)
        btn_row.pack(fill="x")
        ttk.Button(btn_row, text=self.tr("button.refresh"), command=self.refresh_setup_tab).pack(side="left", fill="x", expand=True, padx=(0, 6))
        self._run_setup_btn = ttk.Button(btn_row, text=self.tr("button.run_setup"), command=self._run_setup)
        self._run_setup_btn.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self._regen_bh_btn = ttk.Button(btn_row, text=self.tr("button.regen_bh"), command=self._run_regen_bh, state="disabled")
        self._regen_bh_btn.pack(side="left", fill="x", expand=True)

        # Scrollable two-column content
        scroll_host = tk.Frame(card, bg=self.card)
        scroll_host.pack(fill="both", expand=True, padx=12, pady=(6, 0))

        canvas = tk.Canvas(scroll_host, bg=self.card, highlightthickness=0, bd=0)
        scrollbar = ttk.Scrollbar(scroll_host, orient="vertical", command=canvas.yview, style="Server16.Vertical.TScrollbar")
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        body = tk.Frame(canvas, bg=self.card)
        canvas_win = canvas.create_window((0, 0), window=body, anchor="nw")

        def _on_body_configure(*_):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _on_canvas_configure(e):
            canvas.itemconfig(canvas_win, width=e.width)

        body.bind("<Configure>", _on_body_configure)
        canvas.bind("<Configure>", _on_canvas_configure)
        self._setup_canvas = canvas
        self._setup_canvas_body = body
        # add="+" — see the comment on the dashboard's bind_all for why this must
        # not replace other tabs' scoped mousewheel handlers.
        canvas.bind_all("<MouseWheel>", self._on_setup_mousewheel, add="+")

        body.columnconfigure(0, weight=1, uniform="setupcol")
        body.columnconfigure(1, weight=1, uniform="setupcol")

        left_col = tk.Frame(body, bg=self.card)
        left_col.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        right_col = tk.Frame(body, bg=self.card)
        right_col.grid(row=0, column=1, sticky="nsew", padx=(8, 0))

        def section(parent: tk.Frame, label_key: str) -> None:
            tk.Frame(parent, bg=self.card, height=12).pack(fill="x")
            tk.Label(parent, text=self.tr(label_key), bg=self.card, fg=self.muted, font=("Bahnschrift", 9, "bold")).pack(anchor="w")
            tk.Frame(parent, bg="#243654", height=1).pack(fill="x", pady=(2, 4))

        def status_row(parent: tk.Frame, label_key: str, item_key: str) -> None:
            row = tk.Frame(parent, bg=self.card)
            row.pack(fill="x", pady=2)
            dot = tk.Label(row, text="○", bg=self.card, fg=self.muted, font=("Bahnschrift", 11), width=2)
            dot.pack(side="left")
            tk.Label(row, text=self.tr(label_key), bg=self.card, fg=self.fg, font=("Bahnschrift", 10), anchor="w").pack(side="left", fill="x", expand=True)
            status_lbl = tk.Label(row, text=self.tr("setup.status.not_applicable"), bg=self.card, fg=self.muted, font=("Bahnschrift", 9), anchor="e")
            status_lbl.pack(side="right", padx=(4, 4))
            self._setup_status_vars[item_key] = (dot, status_lbl)

        def source_row(parent: tk.Frame, label_key: str, item_key: str) -> None:
            var = tk.BooleanVar(value=True)
            self._setup_install_vars[item_key] = var
            row = tk.Frame(parent, bg=self.card)
            row.pack(fill="x", pady=2)
            tk.Checkbutton(
                row, variable=var,
                bg=self.card, activebackground=self.card,
                fg=self.fg, selectcolor=self.panel,
                relief="flat", bd=0, cursor="hand2",
                highlightthickness=0,
            ).pack(side="left")
            dot = tk.Label(row, text="○", bg=self.card, fg=self.muted, font=("Bahnschrift", 11), width=2)
            dot.pack(side="left")
            tk.Label(row, text=self.tr(label_key), bg=self.card, fg=self.fg, font=("Bahnschrift", 10), anchor="w").pack(side="left", fill="x", expand=True)
            status_lbl = tk.Label(row, text=self.tr("setup.status.not_applicable"), bg=self.card, fg=self.muted, font=("Bahnschrift", 9), anchor="e")
            status_lbl.pack(side="right", padx=(4, 4))
            self._setup_status_vars[item_key] = (dot, status_lbl)

        # Left column: prerequisites + FSW sources + user folders
        section(left_col, "setup.section.prerequisites")
        status_row(left_col, "setup.item.fifa_exe", "fifa_exe")

        section(left_col, "setup.section.fsw_sources")
        source_row(left_col, "setup.item.settings_ini", "settings_ini")
        source_row(left_col, "setup.item.fsw_police", "fsw_police")
        source_row(left_col, "setup.item.fsw_nets", "fsw_nets")
        source_row(left_col, "setup.item.fsw_pitch", "fsw_pitch")
        source_row(left_col, "setup.item.fsw_stadium", "fsw_stadium")
        source_row(left_col, "setup.item.fsw_goalnet", "fsw_goalnet")
        source_row(left_col, "setup.item.fsw_nav", "fsw_nav")
        source_row(left_col, "setup.item.fsw_scoreboard", "fsw_scoreboard")
        source_row(left_col, "setup.item.fsw_tvlogo", "fsw_tvlogo")

        section(left_col, "setup.section.user_folders")
        status_row(left_col, "setup.item.gbd_stadium", "gbd_stadium")
        status_row(left_col, "setup.item.gbd_tvlogo", "gbd_tvlogo")
        status_row(left_col, "setup.item.gbd_scoreboard", "gbd_scoreboard")
        status_row(left_col, "setup.item.gbd_movies", "gbd_movies")

        # Right column: destination folders
        section(right_col, "setup.section.dest_folders")
        status_row(right_col, "setup.item.dest_slc", "dest_slc")
        status_row(right_col, "setup.item.dest_goalnet", "dest_goalnet")
        status_row(right_col, "setup.item.dest_pitch", "dest_pitch")
        status_row(right_col, "setup.item.dest_stadium", "dest_stadium")
        status_row(right_col, "setup.item.dest_fx", "dest_fx")
        status_row(right_col, "setup.item.dest_crowdplacement", "dest_crowdplacement")
        status_row(right_col, "setup.item.dest_crowdchair", "dest_crowdchair")
        status_row(right_col, "setup.item.dest_overlays", "dest_overlays")
        status_row(right_col, "setup.item.dest_scoreboard_game", "dest_scoreboard_game")
        status_row(right_col, "setup.item.dest_tv", "dest_tv")
        status_row(right_col, "setup.item.dest_nav", "dest_nav")
        status_row(right_col, "setup.item.dest_movies", "dest_movies")
        status_row(right_col, "setup.item.dest_camera", "dest_camera")

        # "Extra" section: everything here is optional and never required for a
        # working install — a clean install loads stadiums fine through CGFS's
        # own injection without any of this. Total-conversion mods (e.g. FIFA
        # Infinity) ship their own data/fifarna/lua and don't need ours, and
        # installing ours over a mod's lua can overwrite a working config — so
        # it's grouped separately and starts unchecked, unlike the source_row
        # items above.
        section(right_col, "setup.section.extra")
        source_row(right_col, "setup.item.revmod_lua", "revmod_lua")
        _revmod_var = self._setup_install_vars.get("revmod_lua")
        if _revmod_var is not None:
            _revmod_var.set(False)

        _kit_numbers_var = tk.BooleanVar(value=self.settings.custom_kit_numbers)
        self._setup_install_vars["custom_kit_numbers"] = _kit_numbers_var
        _kit_numbers_row = tk.Frame(right_col, bg=self.card)
        _kit_numbers_row.pack(fill="x", pady=2)
        tk.Checkbutton(
            _kit_numbers_row, variable=_kit_numbers_var,
            command=self._toggle_custom_kit_numbers,
            bg=self.card, activebackground=self.card,
            fg=self.fg, selectcolor=self.panel,
            relief="flat", bd=0, cursor="hand2",
            highlightthickness=0,
        ).pack(side="left")
        tk.Label(_kit_numbers_row, text="  ", bg=self.card, width=2).pack(side="left")
        tk.Label(_kit_numbers_row, text=self.tr("setup.item.custom_kit_numbers"), bg=self.card, fg=self.fg, font=("Bahnschrift", 10), anchor="w").pack(side="left", fill="x", expand=True)

        status_row(right_col, "setup.item.dest_lua", "dest_lua")

    def _build_setup_assets_tab(self, parent: tk.Frame) -> None:
        card = self._card(parent, "card.setup_assets.title", "card.setup_assets.subtitle")
        card.pack(fill="both", expand=True)

        # Fixed footer — progress bar + action button, same placement pattern as
        # the General sub-tab's footer. The action button is a single toggle:
        # idle it reads "Extract Selected" and starts extraction of whichever
        # kit checkboxes are ticked; while busy it reads "Stop" and cancels
        # whatever is currently running (kits or database) — see
        # _assets_extraction_begin/_end, which swap its text/command.
        footer = tk.Frame(card, bg=self.card)
        footer.pack(side="bottom", fill="x", padx=12, pady=(4, 12))
        pb_row = tk.Frame(footer, bg=self.card)
        pb_row.pack(fill="x")
        self._assets_progressbar = ttk.Progressbar(pb_row, mode="determinate", maximum=100, style="Accent.Horizontal.TProgressbar")
        self._assets_progressbar.pack(side="left", fill="x", expand=True)
        self._assets_progress_label = tk.Label(pb_row, text="", bg=self.card, fg=self.muted, font=("Bahnschrift", 9), width=22, anchor="w")
        self._assets_progress_label.pack(side="left", padx=(8, 0))
        self._assets_action_btn = ttk.Button(
            pb_row, text=self.tr("button.extract_selected_kits"), command=self._run_extract_selected_kits, state="disabled",
        )
        self._assets_action_btn.pack(side="left", padx=(8, 0))

        # Scrollable body — this tab's content can exceed a small window's
        # height, same canvas+scrollbar pattern as the General sub-tab.
        scroll_host = tk.Frame(card, bg=self.card)
        scroll_host.pack(fill="both", expand=True, padx=12, pady=(6, 0))

        canvas = tk.Canvas(scroll_host, bg=self.card, highlightthickness=0, bd=0)
        scrollbar = ttk.Scrollbar(scroll_host, orient="vertical", command=canvas.yview, style="Server16.Vertical.TScrollbar")
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        body = tk.Frame(canvas, bg=self.card)
        canvas_win = canvas.create_window((0, 0), window=body, anchor="nw")

        def _on_body_configure(*_):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _on_canvas_configure(e):
            canvas.itemconfig(canvas_win, width=e.width)

        body.bind("<Configure>", _on_body_configure)
        canvas.bind("<Configure>", _on_canvas_configure)
        self._assets_canvas = canvas
        self._assets_canvas_body = body
        # add="+" — see the comment on the dashboard's bind_all for why this must
        # not replace other tabs' scoped mousewheel handlers.
        canvas.bind_all("<MouseWheel>", self._on_setup_assets_mousewheel, add="+")

        def section(label_key: str) -> None:
            tk.Frame(body, bg=self.card, height=12).pack(fill="x")
            tk.Label(body, text=self.tr(label_key), bg=self.card, fg=self.muted, font=("Bahnschrift", 9, "bold")).pack(anchor="w")
            tk.Frame(body, bg="#243654", height=1).pack(fill="x", pady=(2, 8))

        def hint_label(parent: tk.Misc, text_key: str, **pack_opts) -> tk.Label:
            # wraplength is bound to the label's own allocated width (set via
            # its <Configure> event) instead of a fixed pixel value, so the
            # text re-wraps to use whatever horizontal space is actually
            # available as the window/card is resized, rather than wrapping
            # early at a value tuned for one particular window size.
            lbl = tk.Label(
                parent, text=self.tr(text_key), bg=self.card, fg=self.muted,
                font=("Bahnschrift", 9), anchor="w", justify="left",
            )

            # Debounced, same "Configure storm" pattern as the dashboard canvas
            # (_on_dashboard_configure): reacting to every single <Configure>
            # synchronously — even with a same-value guard — was confirmed
            # live (py-spy dump, repeatedly) to keep re-firing indefinitely
            # under the zoom feature, which resizes dozens of interdependent
            # widgets (including this canvas-embedded scrollable body) in one
            # go. A same-value guard alone doesn't help when e.width itself
            # is genuinely oscillating between two neighboring values each
            # pass (pack-driven rounding while ancestor sizes are still
            # settling) rather than repeating unchanged — MainThread stuck
            # applying wraplength forever, never returning to the mainloop to
            # pump Windows messages ("Not Responding"). Collapsing a burst of
            # rapid-fire Configure events down to one applied width, 80ms
            # after they stop arriving, breaks that tight feedback loop
            # regardless of how many distinct values it was bouncing between.
            def _apply_hint_wrap(width: int, lbl=lbl) -> None:
                lbl._wrap_job = None
                if not lbl.winfo_exists():
                    return
                if int(str(lbl.cget("wraplength")) or 0) != width:
                    lbl.configure(wraplength=width)

            def _on_hint_configure(e, lbl=lbl):
                width = max(int(e.width), 1)
                job = getattr(lbl, "_wrap_job", None)
                if job is not None:
                    try:
                        lbl.after_cancel(job)
                    except Exception:
                        pass
                lbl._wrap_job = lbl.after(80, lambda: _apply_hint_wrap(width))

            lbl.bind("<Configure>", _on_hint_configure)
            lbl.pack(fill="x", **pack_opts)
            return lbl

        section("setup_assets.section.database")
        hint_label(body, "setup_assets.section.database.hint", pady=(0, 6))
        self._extract_db_btn = ttk.Button(body, text=self.tr("button.extract_database"), command=self._run_extract_database, state="disabled")
        self._extract_db_btn.pack(anchor="w")
        self._extract_db_status_label = tk.Label(
            body, text="", bg=self.card, fg=self.muted, font=("Bahnschrift", 9), anchor="w",
        )
        self._extract_db_status_label.pack(anchor="w", pady=(4, 0))

        section("setup_assets.section.kits")
        hint_label(body, "setup_assets.section.kits.hint", pady=(0, 6))

        def check_row(label_key: str, hint_key: str, item_key: str) -> None:
            var = tk.BooleanVar(value=True)
            self._assets_extract_vars[item_key] = var
            row = tk.Frame(body, bg=self.card)
            row.pack(fill="x", pady=(4, 0))
            tk.Checkbutton(
                row, variable=var,
                bg=self.card, activebackground=self.card,
                fg=self.fg, selectcolor=self.panel,
                relief="flat", bd=0, cursor="hand2",
                highlightthickness=0,
            ).pack(side="left", anchor="n")
            label_col = tk.Frame(row, bg=self.card)
            label_col.pack(side="left", fill="x", expand=True)
            tk.Label(label_col, text=self.tr(label_key), bg=self.card, fg=self.fg, font=("Bahnschrift", 10), anchor="w").pack(fill="x")
            hint_label(label_col, hint_key)

        check_row("setup_assets.item.kit_textures", "setup_assets.item.kit_textures.hint", "kit_textures")
        check_row("setup_assets.item.kit_ui", "setup_assets.item.kit_ui.hint", "kit_ui")
        check_row("setup_assets.item.kit_numbers", "setup_assets.item.kit_numbers.hint", "kit_numbers")

        section("setup_assets.section.logos")
        hint_label(body, "setup_assets.section.logos.hint", pady=(0, 6))
        check_row("setup_assets.item.team_logos", "setup_assets.item.team_logos.hint", "team_logos")

    # ── Setup notice (dashboard banner) ───────────────────────────────────────

    def _build_setup_notice(self) -> None:
        amber_bg = "#1c1400"
        notice = tk.Frame(
            self.dashboard_tab,
            bg=amber_bg,
            highlightthickness=1,
            highlightbackground="#f6c177",
        )
        self._setup_notice_frame = notice

        inner = tk.Frame(notice, bg=amber_bg, padx=14, pady=10)
        inner.pack(fill="x")

        header_row = tk.Frame(inner, bg=amber_bg)
        header_row.pack(fill="x", pady=(0, 6))

        self._setup_notice_title = tk.Label(
            header_row,
            text=self.tr("setup_notice.title"),
            bg=amber_bg,
            fg=self.gold,
            font=("Bahnschrift", 11, "bold"),
            anchor="w",
        )
        self._setup_notice_title.pack(side="left")

        self._setup_notice_btn = ttk.Button(
            header_row,
            text=self.tr("setup_notice.go_setup"),
            command=self._go_to_setup_tab,
        )
        self._setup_notice_btn.pack(side="right")

        self._setup_notice_desc = tk.Label(
            inner,
            text=self.tr("setup_notice.description"),
            bg=amber_bg,
            fg=self.fg,
            font=("Bahnschrift", 9),
            anchor="w",
            wraplength=820,
            justify="left",
        )
        self._setup_notice_desc.pack(fill="x", pady=(0, 4))

        steps_frame = tk.Frame(inner, bg=amber_bg)
        steps_frame.pack(fill="x")
        self._setup_notice_step_labels = []
        for key in ("setup_notice.step1", "setup_notice.step2", "setup_notice.step3"):
            lbl = tk.Label(
                steps_frame,
                text=self.tr(key),
                bg=amber_bg,
                fg=self.muted,
                font=("Bahnschrift", 9),
                anchor="w",
            )
            lbl.pack(fill="x")
            self._setup_notice_step_labels.append((key, lbl))

    def _go_to_setup_tab(self) -> None:
        self.tabview.select(self.setup_tab)

    def _on_tab_changed(self, event=None) -> None:
        if self.tabview is None:
            return
        try:
            current = self.tabview.nametowidget(self.tabview.select())
        except Exception:
            return
        if current is self.setup_tab:
            # Re-scan on every visit so users always see live status instead of a
            # possibly stale snapshot from whenever the tab was last built/refreshed.
            self.refresh_setup_tab()
        elif current is self.kits_tab:
            self._on_kits_subtab_changed()

    def _lua_assets_missing_files(self) -> list[str] | None:
        """Compare data/fifarna/lua file-by-file against the bundled install_data source.

        Returns the list of relative paths that are missing or size-mismatched
        (empty list means a complete, verified install), or None if the bundled
        source can't be located — callers should fall back to an existence check
        in that case. This catches partial/interrupted copies (e.g. a single Rev
        Mod lua file missing) that a plain folder-exists check would miss and
        silently report as OK.
        """
        from pathlib import Path as _Path

        src_root = None
        for base in (self.resource_dir, self.base_dir):
            candidate = _Path(base) / "install_data" / "data" / "fifarna" / "lua"
            if candidate.exists():
                src_root = candidate
                break
        if src_root is None:
            return None

        dest_root = self.exedir / "data" / "fifarna" / "lua"
        missing: list[str] = []
        for f in src_root.rglob("*"):
            if not f.is_file():
                continue
            rel = f.relative_to(src_root)
            dest_file = dest_root / rel
            try:
                if not dest_file.exists() or dest_file.stat().st_size != f.stat().st_size:
                    missing.append(str(rel))
            except OSError:
                missing.append(str(rel))
        return missing

    def _is_setup_complete(self) -> bool:
        if not hasattr(self, "fifaEXE") or self.fifaEXE == "default":
            return False
        from pathlib import Path as _Path

        if not _Path(self.fifaEXE).exists():
            return False

        exedir = _Path(self.fifaEXE).parent

        # FSW settings.ini
        if not (exedir / "FSW" / "settings.ini").exists():
            return False

        # FSW source folders must exist and contain at least one file
        for src in (self.Psource, self.Nsource, self.PitchMowsource):
            p = _Path(src)
            if not p.exists() or next((f for f in p.iterdir() if f.is_file()), None) is None:
                return False

        # FSW Stadium, Nav, ScoreBoard and TVLogo folders
        for path in (
            exedir / "FSW" / "Stadium",
            exedir / "FSW" / "Nav",
            exedir / "FSW" / "ScoreBoard",
            exedir / "FSW" / "TVLogo",
        ):
            if not _Path(path).exists():
                return False

        # Destination folders
        dest_paths = [
            self.Pdest, self.Ndest, self.PitchMowdest,
            exedir / "data" / "sceneassets" / "stadium",
            exedir / "data" / "sceneassets" / "fx",
            exedir / "data" / "sceneassets" / "crowdplacement",
            exedir / "data" / "sceneassets" / "crowdchair",
            self.TVdata,
            self.Scoredata / "game",
            exedir / "data" / "ui" / "TV",
            exedir / "data" / "ui" / "nav",
            exedir / "data" / "movies",
            exedir / "data" / "bcdata" / "camera",
        ]
        if not all(_Path(p).exists() for p in dest_paths):
            return False

        # data/fifarna/lua is intentionally not checked here — it's an optional,
        # last-resort extra. A clean install loads stadiums fine through CGFS's
        # own injection without any lua present at all.

        # User GBD folders
        for path in (self.targetpath, self.TVLogo, self.ScoreBoard, self.Movies):
            if not _Path(path).exists():
                return False

        return True

    def _update_setup_notice(self) -> None:
        notice = getattr(self, "_setup_notice_frame", None)
        if notice is None:
            return
        dashboard_host = getattr(self, "_dashboard_host", None)
        if self._is_setup_complete():
            notice.pack_forget()
        elif not notice.winfo_ismapped():
            if dashboard_host:
                notice.pack(fill="x", padx=10, pady=(10, 4), before=dashboard_host)
            else:
                notice.pack(fill="x", padx=10, pady=(10, 4))

    def refresh_setup_tab(self) -> None:
        if not self._setup_status_vars:
            return

        no_exe = not hasattr(self, "fifaEXE") or self.fifaEXE == "default"

        def _set(key: str, ok: bool | None, text: str) -> None:
            pair = self._setup_status_vars.get(key)
            if pair is None:
                return
            dot, lbl = pair
            if ok is None:
                dot.configure(text="○", fg=self.muted)
                lbl.configure(text=text, fg=self.muted)
            elif ok:
                dot.configure(text="●", fg=self.success)
                lbl.configure(text=text, fg=self.success)
            else:
                dot.configure(text="●", fg=self.error)
                lbl.configure(text=text, fg=self.error)

        def _count_files(path) -> int:
            from pathlib import Path
            p = Path(path)
            if not p.exists():
                return -1
            return sum(1 for f in p.iterdir() if f.is_file() and f.suffix.lower() != ".png")

        na = self.tr("setup.status.not_applicable")
        missing = self.tr("setup.status.missing")
        ok_text = self.tr("setup.status.ok")
        empty_text = self.tr("setup.status.empty")

        if no_exe:
            for key in self._setup_status_vars:
                if key == "fifa_exe":
                    _set(key, False, self.tr("setup.status.not_linked"))
                else:
                    _set(key, None, na)
            regen_btn = getattr(self, "_regen_bh_btn", None)
            if regen_btn:
                regen_btn.configure(state="disabled")
            assets_action_btn = getattr(self, "_assets_action_btn", None)
            if assets_action_btn and not getattr(self, "_assets_extraction_running", False):
                assets_action_btn.configure(state="disabled")
            extract_db_btn = getattr(self, "_extract_db_btn", None)
            if extract_db_btn:
                extract_db_btn.configure(state="disabled")
            return

        from pathlib import Path

        # FIFA exe
        exe_path = Path(self.fifaEXE)
        _set("fifa_exe", exe_path.exists(), self.tr("setup.status.linked") if exe_path.exists() else missing)

        exedir = self.exedir

        # FSW sources
        ini_path = exedir / "FSW" / "settings.ini"
        _set("settings_ini", ini_path.exists(), ok_text if ini_path.exists() else missing)

        for key, src in (("fsw_police", self.Psource), ("fsw_nets", self.Nsource), ("fsw_pitch", self.PitchMowsource)):
            count = _count_files(src)
            if count < 0:
                _set(key, False, missing)
            elif count == 0:
                _set(key, None, empty_text)
            else:
                _set(key, True, self.tr("setup.status.files").format(count=count))

        for key, path in (
            ("fsw_stadium", exedir / "FSW" / "Stadium"),
            ("fsw_goalnet", exedir / "FSW" / "GoalNet"),
            ("fsw_nav", exedir / "FSW" / "Nav"),
            ("fsw_scoreboard", exedir / "FSW" / "ScoreBoard"),
            ("fsw_tvlogo", exedir / "FSW" / "TVLogo"),
        ):
            exists = Path(path).exists()
            _set(key, exists, ok_text if exists else missing)

        # Destination folders
        for key, path in (
            ("dest_slc", self.Pdest),
            ("dest_goalnet", self.Ndest),
            ("dest_pitch", self.PitchMowdest),
            ("dest_stadium", exedir / "data" / "sceneassets" / "stadium"),
            ("dest_fx", exedir / "data" / "sceneassets" / "fx"),
            ("dest_crowdplacement", exedir / "data" / "sceneassets" / "crowdplacement"),
            ("dest_crowdchair", exedir / "data" / "sceneassets" / "crowdchair"),
            ("dest_overlays", self.TVdata),
            ("dest_scoreboard_game", self.Scoredata / "game"),
            ("dest_tv", exedir / "data" / "ui" / "TV"),
            ("dest_nav", exedir / "data" / "ui" / "nav"),
            ("dest_movies", exedir / "data" / "movies"),
            ("dest_camera", exedir / "data" / "bcdata" / "camera"),
        ):
            exists = Path(path).exists()
            _set(key, exists, ok_text if exists else missing)

        dest_lua_root = exedir / "data" / "fifarna" / "lua"
        lua_present = dest_lua_root.exists() and any(dest_lua_root.rglob("*.lua"))
        lua_missing = self._lua_assets_missing_files()
        # Lua is optional — a clean install loads stadiums fine through CGFS's own
        # injection without it, so an absent lua is never flagged as an error here.
        if not lua_present:
            _set("dest_lua", None, self.tr("setup.status.lua_optional_not_installed"))
        elif lua_missing is None or not lua_missing:
            _set("dest_lua", True, ok_text)
        else:
            # Something is already there but doesn't match our bundle exactly — could be
            # a total-conversion mod's own lua (e.g. FIFA Infinity) or a prior partial
            # install of ours. Either way, don't imply it's broken; just flag it as custom.
            _set("dest_lua", None, self.tr("setup.status.lua_custom"))

        # User content folders
        for key, path in (
            ("gbd_stadium", self.targetpath),
            ("gbd_tvlogo", self.TVLogo),
            ("gbd_scoreboard", self.ScoreBoard),
            ("gbd_movies", self.Movies),
        ):
            exists = Path(path).exists()
            _set(key, exists, ok_text if exists else missing)

        regen_btn = getattr(self, "_regen_bh_btn", None)
        if regen_btn:
            # Regen BH only needs a valid game directory to glob *.big files from —
            # it doesn't depend on our FSW/lua setup having completed successfully.
            game_dir_ok = Path(self.fifaEXE).exists()
            regen_btn.configure(state="normal" if game_dir_ok else "disabled")

        assets_busy = getattr(self, "_assets_extraction_running", False)
        assets_action_btn = getattr(self, "_assets_action_btn", None)
        if assets_action_btn and not assets_busy:
            # Busy state (text/command already swapped to "Stop") is left alone
            # here — only idle enabled/disabled state is this block's concern;
            # see _assets_extraction_begin/_end for the text/command toggle.
            game_dir_ok = Path(self.fifaEXE).exists()
            assets_action_btn.configure(state="normal" if game_dir_ok else "disabled")

        extract_db_btn = getattr(self, "_extract_db_btn", None)
        db_status_lbl = getattr(self, "_extract_db_status_label", None)
        if extract_db_btn and not assets_busy:
            game_dir_ok = Path(self.fifaEXE).exists()
            # Locked once a database already exists — re-extracting would
            # overwrite a modded install's own data/db/fifa_ng_db.db with the
            # generic vanilla template, corrupting it. Delete the file
            # yourself first if you really need to reset it.
            db_already_extracted = game_dir_ok and (self.exedir / "data" / "db" / "fifa_ng_db.db").exists()
            extract_db_btn.configure(state="normal" if (game_dir_ok and not db_already_extracted) else "disabled")
            if db_status_lbl:
                db_status_lbl.configure(text=self.tr("setup_assets.database_already_extracted") if db_already_extracted else "")

        self._update_setup_notice()

    def _run_setup(self) -> None:
        import shutil
        import threading
        from pathlib import Path as _Path
        from tkinter import messagebox
        from .big4_extractor import extract_fsw_sources

        if not hasattr(self, "fifaEXE") or self.fifaEXE == "default":
            messagebox.showwarning(self.tr("message.fifa16"), self.tr("message.warning.select_fifa_first"))
            return

        install_vars = getattr(self, "_setup_install_vars", {})
        do_settings    = install_vars.get("settings_ini",  tk.BooleanVar(value=True)).get()
        do_police      = install_vars.get("fsw_police",     tk.BooleanVar(value=True)).get()
        do_nets        = install_vars.get("fsw_nets",       tk.BooleanVar(value=True)).get()
        do_pitch       = install_vars.get("fsw_pitch",      tk.BooleanVar(value=True)).get()
        do_stadium     = install_vars.get("fsw_stadium",    tk.BooleanVar(value=True)).get()
        do_goalnet     = install_vars.get("fsw_goalnet",    tk.BooleanVar(value=True)).get()
        do_nav         = install_vars.get("fsw_nav",        tk.BooleanVar(value=True)).get()
        do_scoreboard  = install_vars.get("fsw_scoreboard", tk.BooleanVar(value=True)).get()
        do_tvlogo      = install_vars.get("fsw_tvlogo",     tk.BooleanVar(value=True)).get()
        do_revmod_lua  = install_vars.get("revmod_lua",     tk.BooleanVar(value=True)).get()
        do_custom_kit_numbers = install_vars.get("custom_kit_numbers", tk.BooleanVar(value=False)).get()

        btn = getattr(self, "_run_setup_btn", None)
        if btn:
            btn.configure(state="disabled")

        pb = getattr(self, "_setup_progressbar", None)
        if pb:
            pb["value"] = 0

        def _set_pb(value: float) -> None:
            if pb:
                self.after(0, lambda v=value: pb.configure(value=v))

        _setup_succeeded = [False]

        def _work() -> None:
            try:
                src = self.resource_dir / "install_data"
                if src.exists():
                    self.after(0, self._set_setup_progress, self.tr("progress.setup.copying"))

                    def _ignore(src_dir: str, names: list) -> set:
                        p = _Path(src_dir)
                        skipped: set = set()
                        if not do_settings and p.name == "FSW" and "settings.ini" in names:
                            skipped.add("settings.ini")
                        if not do_nav and p.name == "FSW" and "Nav" in names:
                            skipped.add("Nav")
                        if not do_stadium and p.name == "Stadium" and p.parent.name == "FSW" and "crowdchair" in names:
                            skipped.add("crowdchair")
                        if not do_revmod_lua and p == src / "data" / "fifarna" and "lua" in names:
                            skipped.add("lua")
                        return skipped

                    shutil.copytree(str(src), str(self.exedir), dirs_exist_ok=True, ignore=_ignore)
                    self.log(f"install_data copied to {self.exedir}")
                    if do_revmod_lua:
                        from .file_tools import set_kit_number_scheme
                        set_kit_number_scheme(
                            self.exedir / "data" / "fifarna" / "lua" / "assignments" / "general.lua",
                            do_custom_kit_numbers,
                        )
                else:
                    self.log("install_data folder not found, skipping bundled copy")

                _set_pb(10)
                self.after(0, self._set_setup_progress, self.tr("progress.setup.extracting"))
                self.log("Extracting FSW sources from game archives...")

                skip_categories: set = set()
                if not do_police:
                    skip_categories.add("police")
                if not do_nets:
                    skip_categories.add("nets")
                if not do_pitch:
                    skip_categories.add("pitch")
                if not do_stadium:
                    skip_categories.add("stadium")
                if not do_goalnet:
                    skip_categories.add("goalnet")
                if not do_scoreboard:
                    skip_categories.add("scoreboard")
                if not do_tvlogo:
                    skip_categories.add("tvlogo")

                def _on_extract_progress(step: int, total: int) -> None:
                    _set_pb(10 + 80 * step / total)

                extract_fsw_sources(
                    self.exedir, self.exedir / "FSW",
                    log=self.log, skip=skip_categories,
                    on_progress=_on_extract_progress,
                )

                _set_pb(90)
                self.after(0, self._set_setup_progress, self.tr("progress.setup.bootstrap"))
                self.setuppaths(load_team_database=False)
                self.apply_bootstrap_files()
                _set_pb(100)
                _setup_succeeded[0] = True
            except Exception as exc:
                self.log(f"Setup error: {exc}")
            finally:
                self.after(0, _done)

        def _done() -> None:
            if pb:
                pb["value"] = 0
            self._set_setup_progress("")
            self.refresh_setup_tab()
            if btn:
                btn.configure(state="normal")
            if _setup_succeeded[0]:
                messagebox.showinfo(
                    self.tr("message.setup.complete_title"),
                    self.tr("message.setup.complete_body"),
                )

        threading.Thread(target=_work, daemon=True).start()

    def _run_bh_regen_blocking(self, pb=None) -> tuple[int, int] | None:
        """Runs bh_worker.py against self.exedir and blocks until it's done,
        streaming progress to the log and (if given) a progressbar widget.
        Must be called off the Tk main thread. Returns (ok, failed), or None if
        the worker couldn't even be launched (missing DLL/interpreter/script —
        already logged in that case)."""
        import subprocess
        import json as _json
        from pathlib import Path as _Path

        dll_candidates = [
            self.resource_dir / "bin" / "FifaLibrary16.dll",
            self.base_dir / "bin" / "FifaLibrary16.dll",
        ]
        dll_path = next((c for c in dll_candidates if c.exists()), None)
        if dll_path is None:
            self.log("Regenerate BH: FifaLibrary16.dll not found in bin/")
            return None

        worker_candidates = [
            self.resource_dir / "server16_py" / "bh_worker.py",
            self.base_dir / "server16_py" / "bh_worker.py",
            _Path(__file__).resolve().parent / "bh_worker.py",
        ]
        worker_path = next((c for c in worker_candidates if c.exists()), None)
        if worker_path is None:
            self.log("Regenerate BH: bh_worker.py not found")
            return None

        python32 = _find_python32(extra_dirs=[self.resource_dir, self.base_dir])
        if python32 is None:
            self.log(
                "Regenerate BH: 32-bit Python not found. "
                "Install Python x86 from python.org and retry."
            )
            return None

        self.after(0, self._set_setup_progress, self.tr("progress.setup.regen_bh"))
        self.log(f"Regenerate BH: running for {self.exedir}")
        ok = failed = 0
        cmd = python32 + [str(worker_path), str(dll_path), str(self.exedir)]
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                msg = _json.loads(line)
            except ValueError:
                self.log(f"  [worker] {line}")
                continue
            t = msg.get("t")
            if t == "progress":
                status = "ok" if msg.get("ok") else f"failed: {msg.get('error', '')}"
                self.log(f"  {msg['file']} -> {status}")
                if pb:
                    value = msg["i"] / msg["total"] * 100
                    self.after(0, lambda v=value: pb.configure(value=v))
            elif t == "done":
                ok, failed = msg.get("ok", 0), msg.get("failed", 0)
                self.log(f"Regenerate BH: done ({ok} ok, {failed} failed)")
            elif t == "error":
                self.log(f"Regenerate BH failed: {msg['msg']}")
        proc.wait()
        return ok, failed

    def _run_regen_bh(self) -> None:
        import threading

        btn = getattr(self, "_regen_bh_btn", None)
        if btn:
            btn.configure(state="disabled")
        pb = getattr(self, "_setup_progressbar", None)
        if pb:
            pb["value"] = 0

        def _work() -> None:
            try:
                self._run_bh_regen_blocking(pb)
            except Exception as exc:
                self.log(f"Regenerate BH failed: {exc}")
            finally:
                self.after(0, _done)

        def _done() -> None:
            if pb:
                pb["value"] = 0
            self._set_setup_progress("")
            if btn:
                btn.configure(state="normal")

        threading.Thread(target=_work, daemon=True).start()

    def _find_kit_extractor_exe(self):
        exe_candidates = [
            self.resource_dir / "bin" / "KitExtractorHost.exe",
            self.base_dir / "bin" / "KitExtractorHost.exe",
        ]
        return next((c for c in exe_candidates if c.exists()), None)

    def _assets_extraction_begin(self) -> tuple:
        """Shared setup for Extract Database / Extract Selected (kits): disables
        the database button (only one extraction job can run at a time) and
        flips the shared action button into "Stop" mode — it's a single toggle,
        not two separate buttons, so the same widget that started the job now
        cancels it (see _stop_extraction). Also resets the progress bar.
        Returns the (action_btn, pb) widgets so callers can restore them."""
        db_btn = getattr(self, "_extract_db_btn", None)
        if db_btn:
            db_btn.configure(state="disabled")
        action_btn = getattr(self, "_assets_action_btn", None)
        if action_btn:
            action_btn.configure(text=self.tr("button.stop_extraction"), command=self._stop_extraction, state="normal")
        pb = getattr(self, "_assets_progressbar", None)
        if pb:
            pb["value"] = 0
        self._assets_extraction_running = True
        self._assets_extraction_cancelled = False
        self._assets_extraction_proc = None
        return action_btn, pb

    def _assets_extraction_end(self, action_btn, pb) -> None:
        self._assets_extraction_running = False
        self._assets_extraction_proc = None
        if pb:
            pb["value"] = 0
        self._set_assets_progress("")
        if action_btn:
            # Flip back to "Extract Selected" mode. Disabled here as a safe
            # default; refresh_setup_tab() below re-enables it once it
            # re-checks the game directory (and Extract Database may have just
            # created data/db/fifa_ng_db.db, which must immediately re-lock
            # that separate button too).
            action_btn.configure(text=self.tr("button.extract_selected_kits"), command=self._run_extract_selected_kits, state="disabled")
        self.refresh_setup_tab()

    def _stop_extraction(self) -> None:
        """Stops whichever Extract Database/Extract Kits run is currently in
        progress. Kit extraction runs one KitExtractorHost.exe process per
        batch, so this kills the current batch's process and stops the loop
        from starting another one — already-extracted kits are kept."""
        self._assets_extraction_cancelled = True
        proc = getattr(self, "_assets_extraction_proc", None)
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
            except Exception as exc:
                self.log("Stop extraction: failed to terminate process", exc, exc_info=sys.exc_info())
        self.log("Extraction: stop requested by user")

    def _run_extract_database(self) -> None:
        import os
        import threading
        import subprocess
        import json as _json
        from tkinter import messagebox

        exe_path = self._find_kit_extractor_exe()
        if exe_path is None:
            self.log("Extract Database: KitExtractorHost.exe not found in bin/")
            messagebox.showwarning(self.tr("button.extract_database"), self.tr("message.extract_assets.missing_tool"))
            return

        action_btn, pb = self._assets_extraction_begin()

        def _work() -> None:
            fatal_error: str | None = None
            try:
                self.after(0, self._set_assets_progress, self.tr("progress.setup.extract_database"))
                self.log(f"Extract Database: running for {self.exedir}")

                # Zero teams requested: KitExtractorHost.exe still runs its
                # Initialize/OpenFat/bootstrap-the-db-if-missing/OpenFifaDb
                # sequence, then its team loop does nothing and it exits
                # immediately — see KitExtractorHost.cs. Same quoted-command-line
                # requirement as Extract Kits (see there for why).
                env = os.environ.copy()
                env["KITEXTRACTOR_GAMEDIR"] = str(self.exedir)
                env["KITEXTRACTOR_TEAM_START"] = "0"
                env["KITEXTRACTOR_TEAM_COUNT"] = "0"
                env["KITEXTRACTOR_ALLOW_DB_BOOTSTRAP"] = "1"
                cmdline = f'"{exe_path}"'
                proc = subprocess.Popen(
                    cmdline,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    env=env,
                )
                self._assets_extraction_proc = proc
                for line in proc.stdout:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        msg = _json.loads(line)
                    except ValueError:
                        self.log(f"  [worker] {line}")
                        continue
                    t = msg.get("t")
                    if t == "ready":
                        self.log(f"Extract Database: ready ({msg.get('teams', '?')} teams in database)")
                    elif t == "extracting_db":
                        self.log("Extract Database: copying template database into place...")
                    elif t == "error":
                        fatal_error = msg.get("msg", "unknown error")
                        self.log(f"Extract Database failed: {fatal_error}")
                proc.wait()
                self._assets_extraction_proc = None
            except Exception as exc:
                fatal_error = str(exc)
                self.log(f"Extract Database failed: {exc}")
            finally:
                self.after(0, _done, fatal_error)

        def _done(fatal_error: str | None) -> None:
            self._assets_extraction_end(action_btn, pb)
            if self._assets_extraction_cancelled:
                self.log("Extract Database: cancelled by user")
                return
            if fatal_error:
                messagebox.showerror(self.tr("button.extract_database"), self.tr("message.extract_database.failed", error=fatal_error))
            else:
                messagebox.showinfo(self.tr("message.extract_database.complete_title"), self.tr("message.extract_database.complete_body"))

        threading.Thread(target=_work, daemon=True).start()

    def _run_kit_asset_extraction_blocking(self, asset_mode: str, exe_path, log_label: str, progress_key: str, batch_size: int = 100) -> tuple:
        """Runs KitExtractorHost.exe in batch_size-team batches for the given
        asset_mode ("kit", "kitui", "kitnumbers", or "crest"), streaming
        progress to the log and the Assets Extractor progress bar. Blocking —
        must be called off the Tk main thread (see _run_extract_selected_kits,
        which calls this once per checked asset kind). Returns
        (ok, failed, fatal_error).

        Kit.ExportKitTextures() / the kit-UI / kit-numbers / crest exports all
        spawn an external decompressor per file, and something in that path
        leaks a native OS resource (observed as OutOfMemoryException around
        the ~195th team for the 4-calls/team modes, regardless of which teams
        those are — a hard resource ceiling, not memory pressure a GC can
        reclaim). There's no fix available from outside FifaLibrary16.dll, so
        the roster is processed in small batches, one process per batch, so
        the OS reclaims whatever's leaking each time a batch's process exits.
        100 teams/batch stays well under the observed threshold for the
        4-calls/team modes (and comfortably under it for crest's 1-call/team);
        kitnumbers makes 2x the calls per team (jersey + shorts) so its caller
        passes a proportionally smaller batch_size."""
        import os
        import subprocess
        import json as _json

        BATCH_SIZE = batch_size
        ok = failed = 0
        fatal_error: str | None = None
        pb = getattr(self, "_assets_progressbar", None)

        self.log(f"{log_label}: running for {self.exedir}")
        team_start = 0
        total_teams: int | None = None

        while fatal_error is None and not self._assets_extraction_cancelled:
            # KitExtractorHost.exe must be launched with a command line that is
            # exactly '"<path>"' — see the comment at the top of
            # KitExtractorHost.cs for why a plain argv list corrupts an internal
            # working-directory computation inside FifaLibrary16.dll. The game
            # directory, batch range, and asset mode are passed via env vars
            # instead of argv for the same reason.
            env = os.environ.copy()
            env["KITEXTRACTOR_GAMEDIR"] = str(self.exedir)
            env["KITEXTRACTOR_TEAM_START"] = str(team_start)
            env["KITEXTRACTOR_TEAM_COUNT"] = str(BATCH_SIZE)
            env["KITEXTRACTOR_ASSET"] = asset_mode
            cmdline = f'"{exe_path}"'
            proc = subprocess.Popen(
                cmdline,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=subprocess.CREATE_NO_WINDOW,
                env=env,
            )
            self._assets_extraction_proc = proc
            for line in proc.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = _json.loads(line)
                except ValueError:
                    self.log(f"  [worker] {line}")
                    continue
                t = msg.get("t")
                if t == "ready":
                    total_teams = msg.get("teams")
                    self.log(
                        f"{log_label}: batch teams {msg.get('batch_start')}..{msg.get('batch_end')} of {total_teams}"
                    )
                elif t == "progress":
                    if msg.get("ok"):
                        ok += 1
                    else:
                        failed += 1
                        error = msg.get("error")
                        if error:
                            # "crest" progress messages are per-team only (no
                            # kittype/slot — see the KITEXTRACTOR_ASSET="crest"
                            # branch in KitExtractorHost.cs), so both suffixes
                            # collapse to "" for that mode instead of printing
                            # a misleading "kit None".
                            kittype = msg.get("kittype")
                            kittype_suffix = f" kit {kittype}" if kittype is not None else ""
                            slot = msg.get("slot")
                            slot_suffix = f" ({slot})" if slot else ""
                            self.log(f"  team {msg.get('team')}{kittype_suffix}{slot_suffix} -> failed: {error}")
                    total = msg.get("total") or 1
                    i = msg.get("i", 0)
                    if pb:
                        value = i / total * 100
                        self.after(0, lambda v=value: pb.configure(value=v))
                    text = self.tr(progress_key, current=i, total=total)
                    self.after(0, self._set_assets_progress, text)
                elif t == "error":
                    fatal_error = msg.get("msg", "unknown error")
                    self.log(f"{log_label} failed: {fatal_error}")
            proc.wait()
            self._assets_extraction_proc = None

            team_start += BATCH_SIZE
            if total_teams is None or team_start >= total_teams:
                break

        self.log(f"{log_label}: done ({ok} ok, {failed} failed)")
        return ok, failed, fatal_error

    def _run_extract_selected_kits(self) -> None:
        """Runs whichever asset checkboxes are ticked (kit textures / kit UI /
        kit numbers / team logos) back-to-back in one background thread,
        sharing the Assets Extractor progress bar/action button. Each asset
        kind still runs through its own _run_kit_asset_extraction_blocking
        call (own batch size, own KITEXTRACTOR_ASSET mode) — only the UI is
        consolidated."""
        import threading
        from tkinter import messagebox

        extract_vars = getattr(self, "_assets_extract_vars", {})
        jobs: list[tuple[str, str, str, int]] = []
        if extract_vars.get("kit_textures", tk.BooleanVar(value=True)).get():
            jobs.append(("kit", "Extract Kits", "progress.setup.extract_kits", 100))
        if extract_vars.get("kit_ui", tk.BooleanVar(value=True)).get():
            jobs.append(("kitui", "Extract Kit UI", "progress.setup.extract_kitui", 100))
        if extract_vars.get("kit_numbers", tk.BooleanVar(value=True)).get():
            # kitnumbers makes 2x the calls per team (jersey + shorts) vs.
            # kit/kitui, so it gets half the batch size to keep the same
            # per-batch external-process-spawn ceiling — see
            # _run_kit_asset_extraction_blocking.
            jobs.append(("kitnumbers", "Extract Kit Numbers", "progress.setup.extract_kitnumbers", 50))
        if extract_vars.get("team_logos", tk.BooleanVar(value=True)).get():
            # One export call per team (vs. kit/kitui's four), so it stays
            # well under the same per-batch OOM ceiling at the default size.
            jobs.append(("crest", "Extract Team Logos", "progress.setup.extract_logos", 100))

        if not jobs:
            messagebox.showinfo(self.tr("button.extract_selected_kits"), self.tr("message.extract_assets.none_selected"))
            return

        exe_path = self._find_kit_extractor_exe()
        if exe_path is None:
            self.log("Extract Selected: KitExtractorHost.exe not found in bin/")
            messagebox.showwarning(self.tr("button.extract_selected_kits"), self.tr("message.extract_assets.missing_tool"))
            return

        action_btn, pb = self._assets_extraction_begin()

        def _work() -> None:
            total_ok = total_failed = 0
            fatal_error: str | None = None
            try:
                for asset_mode, log_label, progress_key, batch_size in jobs:
                    if self._assets_extraction_cancelled:
                        break
                    ok, failed, fatal_error = self._run_kit_asset_extraction_blocking(
                        asset_mode, exe_path, log_label, progress_key, batch_size=batch_size
                    )
                    total_ok += ok
                    total_failed += failed
                    if fatal_error:
                        break
            except Exception as exc:
                fatal_error = str(exc)
                self.log(f"Extract Selected failed: {exc}")
            finally:
                self._assets_extraction_proc = None
                self.after(0, _done, total_ok, total_failed, fatal_error)

        def _done(ok: int, failed: int, fatal_error: str | None) -> None:
            cancelled = self._assets_extraction_cancelled
            self._assets_extraction_end(action_btn, pb)
            if cancelled:
                self.log(f"Extract Selected: cancelled by user ({ok} ok, {failed} failed so far)")
                return
            if fatal_error:
                messagebox.showerror(self.tr("button.extract_selected_kits"), self.tr("message.extract_assets.failed", error=fatal_error))
            else:
                messagebox.showinfo(
                    self.tr("message.extract_assets.complete_title"),
                    self.tr("message.extract_assets.complete_body", ok=ok, failed=failed),
                )

        threading.Thread(target=_work, daemon=True).start()

    def _set_assets_progress(self, text: str) -> None:
        lbl = getattr(self, "_assets_progress_label", None)
        if lbl:
            lbl.configure(text=text)

    def _set_setup_progress(self, text: str) -> None:
        lbl = getattr(self, "_setup_progress_label", None)
        if lbl:
            lbl.configure(text=text)

    def _build_logs_card(self) -> None:
        logs = ttk.LabelFrame(self.logs_tab, text=self.tr("logs.group"), padding=10)
        self.logs_frame = logs
        self.logs_group = logs
        logs.pack(fill="both", expand=True, padx=10, pady=10)
        header = tk.Frame(logs, bg=self.bg)
        header.pack(fill="x", pady=(0, 8))
        self._log_autofollow_var = tk.BooleanVar(value=self._log_autofollow)
        self.log_autofollow_checkbox = tk.Checkbutton(
            header,
            text=self.tr("logs.autofollow"),
            variable=self._log_autofollow_var,
            command=self._on_autofollow_toggled,
            bg=self.bg,
            fg=self.fg,
            activebackground=self.bg,
            activeforeground=self.fg,
            selectcolor=self.panel,
            font=("Bahnschrift", 9),
            anchor="w",
            cursor="hand2",
        )
        self.log_autofollow_checkbox.pack(side="left")
        self._log_filter_pointer_trace_var = tk.BooleanVar(value=self._log_filter_pointer_trace)
        self.log_filter_pointer_trace_checkbox = tk.Checkbutton(
            header,
            text=self.tr("logs.filter_pointer_trace"),
            variable=self._log_filter_pointer_trace_var,
            command=self._on_filter_pointer_trace_toggled,
            bg=self.bg,
            fg=self.fg,
            activebackground=self.bg,
            activeforeground=self.fg,
            selectcolor=self.panel,
            font=("Bahnschrift", 9),
            anchor="w",
            cursor="hand2",
        )
        self.log_filter_pointer_trace_checkbox.pack(side="left", padx=(8, 0))
        self._log_filter_discord_rpc_var = tk.BooleanVar(value=self._log_filter_discord_rpc)
        self.log_filter_discord_rpc_checkbox = tk.Checkbutton(
            header,
            text=self.tr("logs.filter_discord_rpc"),
            variable=self._log_filter_discord_rpc_var,
            command=self._on_filter_discord_rpc_toggled,
            bg=self.bg,
            fg=self.fg,
            activebackground=self.bg,
            activeforeground=self.fg,
            selectcolor=self.panel,
            font=("Bahnschrift", 9),
            anchor="w",
            cursor="hand2",
        )
        self.log_filter_discord_rpc_checkbox.pack(side="left", padx=(8, 0))
        self.log_follow_button = ttk.Button(header, text=self.tr("button.jump_latest"), command=self._jump_logs_to_latest)
        self.log_follow_button.pack(side="right")
        logs_body = tk.Frame(logs, bg=self.panel)
        logs_body.pack(fill="both", expand=True)
        self.log_widget = tk.Text(
            logs_body,
            height=18,
            bg=self.panel,
            fg=self.fg,
            insertbackground=self.fg,
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            font=("Consolas", 9),
            wrap="word",
        )
        log_scrollbar = ttk.Scrollbar(
            logs_body,
            orient="vertical",
            command=self.log_widget.yview,
            style="Server16.Vertical.TScrollbar",
        )
        self.log_widget.configure(yscrollcommand=log_scrollbar.set)
        self.log_widget.pack(side="left", fill="both", expand=True)
        log_scrollbar.pack(side="right", fill="y")
        self.log_widget.configure(state="disabled")
        self.log_widget.bind("<ButtonRelease-1>", self._refresh_log_autofollow_state)
        self.log_widget.bind("<ButtonRelease-4>", self._refresh_log_autofollow_state)
        self.log_widget.bind("<ButtonRelease-5>", self._refresh_log_autofollow_state)
        self.log_widget.bind("<MouseWheel>", self._refresh_log_autofollow_state)
        self.log_widget.bind("<KeyRelease>", self._refresh_log_autofollow_state)
        self._update_log_follow_ui()

    def refresh_camera_catalog(self) -> None:
        self._camera_presets = self.camera_runtime.discover_presets()
        self._camera_presets_by_name = {preset.name: preset for preset in self._camera_presets}
        if self.camera_package_label is not None:
            package_dir = self.camera_runtime.package_dir()
            if package_dir is not None and package_dir.exists():
                self.camera_package_label.configure(
                    text=self.tr("camera.cameras_found", count=len(self._camera_presets), path=package_dir),
                    fg=self.muted,
                )
            else:
                self.camera_package_label.configure(
                    text=self.tr("camera.invalid_package_label"),
                    fg=self.error,
                )
        if self.camera_listbox is None:
            return
        self.camera_listbox.delete(0, "end")
        for preset in self._camera_presets:
            self.camera_listbox.insert("end", preset.name)
        if not self._camera_presets:
            self._display_camera_details(None)
            return
        selected_name = self._camera_selected_name if self._camera_selected_name in self._camera_presets_by_name else self._camera_presets[0].name
        index = next((idx for idx, preset in enumerate(self._camera_presets) if preset.name == selected_name), 0)
        self.camera_listbox.selection_clear(0, "end")
        self.camera_listbox.selection_set(index)
        self.camera_listbox.activate(index)
        self.camera_listbox.see(index)
        self._display_camera_details(self._camera_presets[index])

    def _on_camera_select(self, _event=None) -> None:
        if self.camera_listbox is None:
            return
        selection = self.camera_listbox.curselection()
        if not selection:
            return
        name = self.camera_listbox.get(selection[0])
        self._display_camera_details(self._camera_presets_by_name.get(name))

    def _on_camera_example_change(self, _event=None) -> None:
        preset = self._camera_presets_by_name.get(self._camera_selected_name or "")
        if preset is None:
            return
        self._show_camera_example(preset, self.camera_example_var.get())

    def _display_camera_details(self, preset: CameraPreset | None) -> None:
        self._camera_selected_name = preset.name if preset is not None else None
        if self.camera_name_label is not None:
            self.camera_name_label.configure(text=preset.name if preset is not None else self.tr("camera.no_camera_selected"))
        if self.camera_apply_button is not None:
            self.camera_apply_button.configure(state="normal" if preset is not None else "disabled")
        if self.camera_instruction_text is not None:
            self.camera_instruction_text.configure(state="normal")
            self.camera_instruction_text.delete("1.0", "end")
            self.camera_instruction_text.insert("1.0", preset.instructions_text if preset is not None else self.tr("camera.instructions_missing"))
            self.camera_instruction_text.configure(state="disabled")
        if self.camera_example_combo is not None:
            values = [path.name for path in preset.example_paths] if preset is not None else []
            self.camera_example_combo.configure(values=values)
            if values:
                self.camera_example_var.set(values[0])
                self._show_camera_example(preset, values[0])
            else:
                self.camera_example_var.set("")
                self._clear_camera_preview(self.tr("camera.no_preview"))

    def _show_camera_example(self, preset: CameraPreset, image_name: str) -> None:
        target = next((path for path in preset.example_paths if path.name == image_name), None)
        if target is None:
            self._clear_camera_preview(self.tr("camera.no_preview"))
            return
        cache_key = (preset.name, target.name)
        image_obj = self._camera_preview_cache.get(cache_key)
        if image_obj is None:
            try:
                image_obj = Image.open(target).convert("RGBA")
                self._camera_preview_cache[cache_key] = image_obj
            except Exception as exc:
                self.log(f"Failed to load camera preview {target}", exc, exc_info=sys.exc_info())
                self._clear_camera_preview(self.tr("camera.failed_open_preview", name=target.name))
                return
        self._camera_preview_source_key = cache_key
        self._render_camera_preview()
        if self.camera_preview_status is not None:
            self.camera_preview_status.configure(text=self.tr("camera.preview_prefix", name=target.name))

    def _clear_camera_preview(self, text: str) -> None:
        self._camera_preview_source_key = None
        if self.camera_preview_image_label is not None:
            self.camera_preview_image_label.configure(image="", text=self.tr("placeholder.preview"))
            self.camera_preview_image_label.image = None
        if self.camera_preview_status is not None:
            self.camera_preview_status.configure(text=text)

    def _on_camera_preview_canvas_configure(self, _event=None) -> None:
        if hasattr(self, "_camera_preview_configure_job"):
            self.after_cancel(self._camera_preview_configure_job)
        self._camera_preview_configure_job = self.after(80, self._render_camera_preview)

    def _render_camera_preview(self) -> None:
        if self._camera_preview_source_key is None or self.camera_preview_canvas is None or self.camera_preview_image_label is None:
            return
        image_obj = self._camera_preview_cache.get(self._camera_preview_source_key)
        if image_obj is None:
            return
        canvas_width = max(1, self.camera_preview_canvas.winfo_width())
        canvas_height = max(1, self.camera_preview_canvas.winfo_height())
        if canvas_width <= 1 or canvas_height <= 1:
            return
        max_width = max(240, canvas_width - 24)
        max_height = max(180, canvas_height - 24)
        src_width, src_height = image_obj.size
        scale = min(max_width / max(1, src_width), max_height / max(1, src_height), 1.0)
        render_width = max(1, int(src_width * scale))
        render_height = max(1, int(src_height * scale))
        render_key = (*self._camera_preview_source_key, render_width, render_height)
        image_ref = self._camera_preview_render_cache.get(render_key)
        if image_ref is None:
            resampling = getattr(getattr(Image, "Resampling", Image), "LANCZOS", Image.LANCZOS)
            resized = image_obj.resize((render_width, render_height), resampling)
            image_ref = ImageTk.PhotoImage(resized)
            self._camera_preview_render_cache[render_key] = image_ref
        self.camera_preview_image_label.configure(image=image_ref, text="")
        self.camera_preview_image_label.image = image_ref
        self.camera_preview_image_label.update_idletasks()

    def select_camera_package(self) -> None:
        selected = filedialog.askdirectory(title=self.tr("message.camera.select_package_dialog"))
        if not selected:
            return
        if not self.camera_runtime.is_valid_package_dir(selected):
            messagebox.showwarning(
                self.tr("message.camera_package"),
                self.tr("message.camera.invalid_package"),
            )
            return
        self.settings.camera_package = selected
        self._camera_preview_cache.clear()
        self.refresh_camera_catalog()
        self.log(f"Camera package selected: {selected}")

    def apply_selected_camera(self) -> None:
        preset = self._camera_presets_by_name.get(self._camera_selected_name or "")
        if preset is None:
            messagebox.showwarning(self.tr("message.camera"), self.tr("message.camera.select_before_apply"))
            return
        if self.fifaEXE == "default":
            messagebox.showwarning(self.tr("message.camera"), self.tr("message.warning.select_fifa_first"))
            return
        if self.camera_apply_button is not None:
            self.camera_apply_button.configure(state="disabled")
        window = self._window()
        window.configure(cursor="watch")
        window.update_idletasks()
        try:
            result = self.camera_runtime.apply_preset(preset)
            regen = result["regenerator"]
            copied_files = result["copied_files"]
            if isinstance(regen, dict) and regen.get("launched"):
                regen_message = self.tr("message.camera.regen_started", path=regen["path"])
            else:
                regen_message = self.tr("message.camera.regen_failed")
            self.log(f"Camera applied: {preset.name} ({copied_files} files updated)")
            self.log(regen_message)
            if self.camera_preview_status is not None:
                self.camera_preview_status.configure(text=self.tr("camera.applied_prefix", name=preset.name))
            messagebox.showinfo(
                self.tr("message.camera.applied_title"),
                self.tr("message.camera.apply_success", name=preset.name, count=copied_files, regen=regen_message),
            )
        except Exception as exc:
            self.log(f"Failed to apply camera {preset.name}", exc, exc_info=sys.exc_info())
            messagebox.showerror(self.tr("message.camera"), self.tr("message.camera.apply_failed", error=exc))
        finally:
            window.configure(cursor="")
            if self.camera_apply_button is not None:
                self.camera_apply_button.configure(state="normal" if preset is not None else "disabled")

    def _build_stat(
        self,
        parent: tk.Misc,
        row: int,
        column: int,
        title: str,
        key: str,
        default: str,
        value_wraplength: int | None = None,
        block_height: int = 44,
    ) -> None:
        block = tk.Frame(parent, bg=self.card)
        block.grid(row=row, column=column, sticky="ew", padx=(0, 10), pady=4)
        block.configure(width=190, height=block_height)
        block.grid_propagate(False)
        title_label = tk.Label(block, text=self.tr(title), bg=self.card, fg=self.muted, font=("Bahnschrift", 9))
        title_label.pack(anchor="w")
        label = tk.Label(
            block,
            text=default,
            bg=self.card,
            fg=self.fg,
            font=("Consolas", 12, "bold"),
            anchor="w",
            justify="left",
            wraplength=value_wraplength,
        )
        label.pack(anchor="w", pady=(2, 0))
        self.stat_title_labels[key] = title_label
        self.labels[key] = label

    def _show_about(self) -> None:
        AboutDialog(self, self.app_version)

    def _check_update_button_text(self) -> str:
        key = "button.checking_update" if self._update_check_in_progress else "button.check_update"
        return self.tr(key)

    def check_updates(self) -> None:
        if self._update_check_in_progress:
            return
        self._update_check_in_progress = True
        if self.check_update_button is not None:
            self.check_update_button.configure(state="disabled", text=self._check_update_button_text())
        self.log("Checking for updates on GitHub releases")
        threading.Thread(target=self._run_check_updates_worker, daemon=True).start()

    def _run_check_updates_worker(self) -> None:
        result = self._update_checker.check_latest_release(self.app_version)
        window = self._window()
        try:
            window.after(0, lambda: self._handle_check_updates_result(result))
        except Exception:
            pass

    def _handle_check_updates_result(self, result: UpdateCheckResult) -> None:
        self._update_check_in_progress = False
        if self.check_update_button is not None:
            self.check_update_button.configure(state="normal", text=self._check_update_button_text())

        if not result.ok:
            self.log(f"Update check failed: {result.error}")
            messagebox.showerror(
                self.tr("message.update_check_title"),
                self.tr("message.update_check_error", error=result.error),
            )
            return

        if result.update_available:
            self.log(f"Update available: v{result.latest_version} (current v{result.current_version})")
            should_open = messagebox.askyesno(
                self.tr("message.update_check_title"),
                self.tr(
                    "message.update_available",
                    latest=result.latest_version,
                    current=result.current_version,
                ),
            )
            if should_open:
                url = result.release_url or (
                    f"https://github.com/{self.UPDATE_REPO_OWNER}/{self.UPDATE_REPO_NAME}/releases/latest"
                )
                webbrowser.open(url)
            return

        self.log(f"No updates found. Current version is v{result.current_version}")
        messagebox.showinfo(
            self.tr("message.update_check_title"),
            self.tr("message.update_none", current=result.current_version),
        )
