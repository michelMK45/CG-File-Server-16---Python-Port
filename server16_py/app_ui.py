from __future__ import annotations

import ctypes
import sys
import time
import threading
import webbrowser
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk

from .camera_runtime import CameraPreset
from .dialogs import AboutDialog
from .file_tools import resolve_stadium_preview_path
from .update_checker import UpdateCheckResult
from .win32_types import RECT, SW_SHOWNOACTIVATE, SW_HIDE

try:
    from .d3d_injector import D3DOverlayInjector as _D3DOverlayInjector
except Exception:
    _D3DOverlayInjector = None  # type: ignore[assignment,misc]


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
        self.tabview.add(self.dashboard_tab, text=self.tr("tab.dashboard"))
        self.tabview.add(self.audio_tab, text=self.tr("tab.chants"))
        self.tabview.add(self.camera_tab, text=self.tr("tab.camera"))
        self.tabview.add(self.setup_tab, text=self.tr("tab.setup"))
        self.tabview.add(self.logs_tab, text=self.tr("tab.logs"))

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
        self.dashboard_canvas.bind_all("<MouseWheel>", self._on_dashboard_mousewheel)
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
        self._build_logs_card()
        self._apply_main_localization()

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
        modal.geometry("340x274")

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
                 image_path=str(self._resolve_stadium_preview_path(stadium_name) or ""))
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
        return True

    def _show_toast_notification(self, title: str, body: str = "", style: int = 0) -> int:
        """Show a compact in-game toast (no progress bar, no image). Returns slot index or -1."""
        if not self.settings.show_stadium_loading_notification:
            return -1
        if not self._ensure_d3d_overlay_injected(log_errors=False):
            return -1
        inj = self._d3d_injector
        if inj is None:
            return -1
        return inj.show_toast(title, body, style)

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
                modal_w, modal_h = 340, 274
                x = rect.left + (fifa_width - modal_w) // 2
                y = rect.top + 40
                self.stadium_loading_modal.geometry(f"{modal_w}x{modal_h}+{x}+{y}")
                return
        window = self._window()
        window.update_idletasks()
        root_x = window.winfo_rootx()
        root_y = window.winfo_rooty()
        self.stadium_loading_modal.geometry(f"340x274+{root_x + 24}+{root_y + 24}")

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

    def _on_dashboard_mousewheel(self, event) -> None:
        if self.tabview is None or self.dashboard_canvas is None:
            return
        current = self.tabview.nametowidget(self.tabview.select())
        if current is not self.dashboard_tab:
            return
        widget = event.widget
        if isinstance(widget, str):
            try:
                widget = self.nametowidget(widget)
            except Exception:
                widget = None
        if widget is None:
            return
        try:
            if widget.winfo_toplevel() is not self._window():
                return
        except Exception:
            return
        cursor = widget
        belongs_to_dashboard = False
        while cursor is not None:
            if cursor is self.dashboard_canvas or cursor is self.dashboard_content:
                belongs_to_dashboard = True
                break
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
        if not belongs_to_dashboard:
            return
        self.dashboard_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

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
        image_path = self._resolve_stadium_preview_path(stadium_name)
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
        image_path = self._resolve_stadium_preview_path(stadium_name)
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
        card.configure(height=230)
        card.grid_propagate(False)
        body = tk.Frame(card, bg=self.card)
        body.pack(fill="both", expand=True, padx=12, pady=(6, 12))
        body.grid_columnconfigure(0, weight=2)
        body.grid_columnconfigure(1, weight=1)
        body.grid_columnconfigure(2, weight=2)

        self._build_team_panel(body, 0, self.tr("team.a"), "home")
        center = tk.Frame(body, bg=self.card)
        center.grid(row=0, column=1, sticky="nsew", padx=8)
        tk.Label(center, text=self.tr("match.score"), bg=self.card, fg=self.muted, font=("Bahnschrift", 9)).pack(pady=(18, 2))
        score_label = tk.Label(center, text="0 x 0", bg=self.card, fg=self.gold, font=("Bahnschrift", 28, "bold"))
        score_label.pack()
        tk.Label(center, text=self.tr("match.time"), bg=self.card, fg=self.muted, font=("Bahnschrift", 9)).pack(pady=(18, 2))
        timer_label = tk.Label(center, text="00:00", bg=self.card, fg=self.accent, font=("Consolas", 18, "bold"))
        timer_label.pack()
        self._register_info_label("score", score_label)
        self._register_info_label("timer", timer_label)
        self._build_team_panel(body, 2, self.tr("team.b"), "away")

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
        card.configure(height=164)
        card.grid_propagate(False)
        body = tk.Frame(card, bg=self.card)
        body.pack(fill="x", padx=12, pady=(6, 12))
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=1)
        self._build_stat(body, 0, 0, "stat.tv_logo", "tvlogo", "default")
        self._build_stat(body, 0, 1, "stat.scoreboard", "scoreboard", "default")
        self._build_stat(body, 1, 0, "stat.movie", "movie", "default")
        self._build_stat(body, 1, 1, "stat.status", "status", self.display_value("idle"))
        ttk.Button(card, text=self.tr("button.edit_asset_settings"), command=self.open_assets_settings_editor).pack(fill="x", padx=12, pady=(0, 12))

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

    def _toggle_keep_open(self) -> None:
        self.settings.keep_open_on_game_close = self.keep_open_var.get()
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
        ttk.Button(card, text=self.tr("button.edit_chants_settings"), command=self.open_audio_settings_editor).pack(fill="x", padx=12, pady=(0, 12))

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

        card = self._card(outer, "card.setup.title", "card.setup.subtitle")
        card.pack(fill="both", expand=True)

        # Fixed footer — packed before the scroll area so it stays visible
        footer = tk.Frame(card, bg=self.card)
        footer.pack(side="bottom", fill="x", padx=12, pady=(4, 12))
        pb_row = tk.Frame(footer, bg=self.card)
        pb_row.pack(fill="x", pady=(0, 6))
        self._setup_progressbar = ttk.Progressbar(pb_row, mode="indeterminate", style="Accent.Horizontal.TProgressbar")
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
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))

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

        # Left column: prerequisites + FSW sources + user folders
        section(left_col, "setup.section.prerequisites")
        status_row(left_col, "setup.item.fifa_exe", "fifa_exe")

        section(left_col, "setup.section.fsw_sources")
        status_row(left_col, "setup.item.settings_ini", "settings_ini")
        status_row(left_col, "setup.item.fsw_police", "fsw_police")
        status_row(left_col, "setup.item.fsw_nets", "fsw_nets")
        status_row(left_col, "setup.item.fsw_pitch", "fsw_pitch")
        status_row(left_col, "setup.item.fsw_stadium", "fsw_stadium")
        status_row(left_col, "setup.item.fsw_nav", "fsw_nav")

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
        status_row(right_col, "setup.item.dest_lua", "dest_lua")

        self.refresh_setup_tab()

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

        # FSW Stadium and Nav folders
        for path in (exedir / "FSW" / "Stadium", exedir / "FSW" / "Nav"):
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
            exedir / "data" / "fifarna" / "lua" / "assets",
        ]
        if not all(_Path(p).exists() for p in dest_paths):
            return False

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
            return sum(1 for f in p.iterdir() if f.is_file())

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

        for key, path in (("fsw_stadium", exedir / "FSW" / "Stadium"), ("fsw_nav", exedir / "FSW" / "Nav")):
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
            ("dest_lua", exedir / "data" / "fifarna" / "lua" / "assets"),
        ):
            exists = Path(path).exists()
            _set(key, exists, ok_text if exists else missing)

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
                exedir / "data" / "fifarna" / "lua" / "assets",
            ]
            setup_ok = Path(self.fifaEXE).exists() and all(Path(p).exists() for p in dest_paths)
            regen_btn.configure(state="normal" if setup_ok else "disabled")

        self._update_setup_notice()

    def _run_setup(self) -> None:
        import shutil
        import threading
        from tkinter import messagebox
        from .big4_extractor import extract_fsw_sources

        if not hasattr(self, "fifaEXE") or self.fifaEXE == "default":
            messagebox.showwarning(self.tr("message.fifa16"), self.tr("message.warning.select_fifa_first"))
            return

        btn = getattr(self, "_run_setup_btn", None)
        if btn:
            btn.configure(state="disabled")

        pb = getattr(self, "_setup_progressbar", None)
        if pb:
            pb.start(12)

        def _work() -> None:
            try:
                src = self.resource_dir / "install_data"
                if src.exists():
                    self.after(0, self._set_setup_progress, self.tr("progress.setup.copying"))
                    shutil.copytree(str(src), str(self.exedir), dirs_exist_ok=True)
                    self.log(f"install_data copied to {self.exedir}")
                else:
                    self.log("install_data folder not found, skipping bundled copy")

                self.after(0, self._set_setup_progress, self.tr("progress.setup.extracting"))
                self.log("Extracting FSW sources from game archives...")
                extract_fsw_sources(self.exedir, self.exedir / "FSW", log=self.log)

                self.after(0, self._set_setup_progress, self.tr("progress.setup.bootstrap"))
                self.setuppaths(load_team_database=False)
                self.apply_bootstrap_files()
            except Exception as exc:
                self.log(f"Setup error: {exc}")
            finally:
                self.after(0, _done)

        def _done() -> None:
            if pb:
                pb.stop()
                pb["value"] = 0
            self._set_setup_progress("")
            self.refresh_setup_tab()
            if btn:
                btn.configure(state="normal")

        threading.Thread(target=_work, daemon=True).start()

    def _run_regen_bh(self) -> None:
        import subprocess
        import threading

        candidates = [
            self.resource_dir / "bin" / "regen-cli.exe",
            self.base_dir / "bin" / "regen-cli.exe",
        ]
        regen_exe = next((c for c in candidates if c.exists()), None)
        if regen_exe is None:
            self.log("Regenerate BH: regen-cli.exe not found in bin/")
            return

        btn = getattr(self, "_regen_bh_btn", None)
        if btn:
            btn.configure(state="disabled")

        pb = getattr(self, "_setup_progressbar", None)
        if pb:
            pb.start(12)

        def _work() -> None:
            try:
                self.after(0, self._set_setup_progress, self.tr("progress.setup.regen_bh"))
                self.log(f"Regenerate BH: running for {self.exedir}")
                result = subprocess.run(
                    [str(regen_exe), "--gamedir", str(self.exedir)],
                    capture_output=True, text=True, timeout=120,
                )
                for line in result.stdout.splitlines():
                    if line.strip():
                        self.log(f"  {line.strip()}")
                if result.returncode == 0:
                    self.log("Regenerate BH: done")
                else:
                    self.log(f"Regenerate BH: exit code {result.returncode}")
                    if result.stderr:
                        self.log(result.stderr.strip())
            except subprocess.TimeoutExpired:
                self.log("Regenerate BH: timed out after 120s")
            except Exception as exc:
                self.log(f"Regenerate BH failed: {exc}")
            finally:
                self.after(0, _done)

        def _done() -> None:
            if pb:
                pb.stop()
                pb["value"] = 0
            self._set_setup_progress("")
            if btn:
                btn.configure(state="normal")

        threading.Thread(target=_work, daemon=True).start()

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
