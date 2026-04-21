from __future__ import annotations

import ctypes
import queue
import random
import subprocess
import sys
import threading
import time
import traceback
import tkinter as tk
from datetime import datetime
from time import perf_counter
from pathlib import Path
from ctypes import wintypes
from tkinter import filedialog, messagebox, scrolledtext, ttk

import psutil
from PIL import Image, ImageTk

from .asset_runtime import AssetRuntime
from .assignment_runtime import AssignmentRuntime
from .camera_runtime import CameraPreset, CameraRuntime
from .chants_runtime import ChantsRuntime, MciAudioPlayer
from .discord_rpc_runtime import DiscordRPCRuntime
from .fifa_db import FifaDatabase
from .file_tools import checkdirs, checkver, copy, copy_if_exists, extra_setup
from .ini_file import SessionIniFile
from .memory_access import Memory, MemoryAccessError
from .offsets import Offsets
from .settings_editor import SettingsAreaEditor, asset_specs, audio_specs, stadium_specs
from .settings_store import SettingsStore
from .stadium_runtime import StadiumRuntime


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
HWND_TOPMOST = -1
SW_SHOWNOACTIVATE = 4
SW_HIDE = 0
SW_RESTORE = 9
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040
VK_MENU = 0x12
VK_RETURN = 0x0D
KEYEVENTF_KEYUP = 0x0002


class Server16App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.withdraw()
        self.base_dir = self._resolve_base_dir()
        self.log_path = self.base_dir / "runtime" / "server16.log"
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.settings = SettingsStore(self.base_dir / "runtime" / "settings.json")
        self.offsets = Offsets.load()
        self.memory = Memory()
        self.pagechange = False
        self.skillgamechange = False
        self.bumperpagechange = False
        self.matchstarted = False
        self.lastpagename = ""
        self.curstad = ""
        self.ScoreboardStadName = ""  # Display name from scoreboardstdname setting
        self.stadmovie = False
        self.CCount = "0"
        self.injID = "176"
        self.PoliceNum = "4"
        self.HID = ""
        self.AID = ""
        self.STADID = ""
        self.TOURNAME = ""
        self.TOURROUNDID = ""
        self.derby = ""
        self.tvlogoscoreboardtype = "default"
        self._last_runtime_signature = None
        self._last_context_error = None
        self._closing = False
        self._poll_job = None
        self._stats_job = None
        self._kickoff_retry_job = None
        self._overlay_job = None
        self._kickoff_retry_remaining = 0
        self._attached_once = False
        self._logs_visible = False
        self._kickoff_generation = 0
        self._overlay_enabled = False
        self._overlay_visible = False
        self._overlay_space_down = False
        self._overlay_toggle_ready_at = 0.0
        self._overlay_hwnd = 0
        self._fifa_hwnd = 0
        self._restore_fullscreen_on_hide = False
        self._launcher_mode = True
        self._worker_queue: queue.Queue[tuple] = queue.Queue()
        self._worker_poll_job = None
        self._stadium_task_running = False
        self._stadium_task_signature = None
        self._stadium_task_request_key = None
        self._last_stadium_applied_signature = None
        self.labels = {}
        self.info_labels = {}
        self.module_vars = {}
        self.module_checks = {}
        self.module_states = {}
        self.log_widget = None
        self.logs_frame = None
        self.toggle_logs_button = None
        self.start_overlay_button = None
        self.log_status_label = None
        self.log_follow_button = None
        self._log_autofollow = True
        self.ui_root = None
        self.tabview = None
        self.dashboard_tab = None
        self.logs_tab = None
        self.audio_tab = None
        self.camera_tab = None
        self.page_banner = None
        self.progress_bar = None
        self.progress_text = None
        self.progress_value = None
        self.stadium_loading_modal = None
        self.stadium_loading_title = None
        self.stadium_loading_info = None
        self.stadium_loading_name = None
        self.stadium_loading_detail = None
        self.stadium_loading_progress_text = None
        self.stadium_loading_value = None
        self.stadium_loading_bar = None
        self._stadium_loading_hwnd = 0
        self._stadium_loading_visible = False
        self._stadium_loading_restore_fullscreen = False
        self.show_stadium_loading_var = tk.BooleanVar(value=self.settings.show_stadium_loading_notification)
        self.status_pill = None
        self.dashboard_canvas = None
        self.dashboard_scrollbar = None
        self.dashboard_content = None
        self.dashboard_window_id = None
        self._audio_details: dict[str, str] = {}
        self._team_logo_labels: dict[str, tk.Label] = {}
        self._team_logo_images: dict[str, ImageTk.PhotoImage | None] = {}
        self._stadium_preview_frame = None
        self._stadium_preview_body_anchor = None
        self._stadium_preview_label = None
        self._stadium_preview_image: ImageTk.PhotoImage | None = None
        self.stadium_loading_preview = None
        self._stadium_loading_image: ImageTk.PhotoImage | None = None
        self._stadium_loading_preview_visible = True
        self._settings_editors: dict[str, SettingsAreaEditor] = {}
        self._camera_presets: list[CameraPreset] = []
        self._camera_presets_by_name: dict[str, CameraPreset] = {}
        self._camera_preview_cache: dict[tuple[str, str], Image.Image] = {}
        self._camera_preview_render_cache: dict[tuple[str, str, int, int], ImageTk.PhotoImage] = {}
        self._camera_selected_name: str | None = None
        self._camera_preview_source_key: tuple[str, str] | None = None
        self._camera_preview_canvas_window = None
        self.camera_listbox = None
        self.camera_name_label = None
        self.camera_preview_canvas = None
        self.camera_preview_frame = None
        self.camera_preview_image_label = None
        self.camera_preview_status = None
        self.camera_package_label = None
        self.camera_select_button = None
        self.camera_example_var = tk.StringVar(value="")
        self.camera_example_combo = None
        self.camera_instruction_text = None
        self.camera_apply_button = None
        self.chants_thread_started = False
        self._chants_stop = threading.Event()
        self._chants_player: MciAudioPlayer | None = None
        self._chant_track_index = 0
        self._chants_paused = False
        self._chants_target_volume = 0.0
        self._last_score_snapshot = (0, 0)
        self._last_chants_score_snapshot: tuple[int, int] | None = None
        self._chants_resume_after = 0.0
        self._chants_rng = random.Random()
        self._last_live_score = (0, 0)
        self._last_live_update = ""
        self.assets_runtime = AssetRuntime(self)
        self.stadium_runtime = StadiumRuntime(self)
        self.chants_runtime = ChantsRuntime(self)
        self.assignment_runtime = AssignmentRuntime(self)
        self.camera_runtime = CameraRuntime(self)
        # Initialize Discord RPC (loads from settings.json)
        discord_rpc_config = self.settings.data.get("discord_rpc", {})
        client_id = discord_rpc_config.get("client_id", "1495719449700077630")
        self.discord_rpc = DiscordRPCRuntime(client_id, logger=None)
        self._discord_rpc_enabled = discord_rpc_config.get("enabled", False)
        self._discord_rpc_last_presence = None
        if self._discord_rpc_enabled:
            self.discord_rpc.connect()
        # Initialize team database (will be loaded when FIFA EXE is selected)
        self.team_db: FifaDatabase | None = None
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.user32.GetAsyncKeyState.argtypes = [wintypes.INT]
        self.user32.GetAsyncKeyState.restype = wintypes.SHORT
        self.user32.GetForegroundWindow.restype = wintypes.HWND
        self.user32.IsWindowVisible.argtypes = [wintypes.HWND]
        self.user32.IsWindowVisible.restype = wintypes.BOOL
        self.user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(RECT)]
        self.user32.GetWindowRect.restype = wintypes.BOOL
        self.user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        self.user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
        self.user32.GetWindowLongW.restype = ctypes.c_long
        self.user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
        self.user32.SetWindowLongW.restype = ctypes.c_long
        self.user32.SetWindowPos.argtypes = [
            wintypes.HWND,
            wintypes.HWND,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_uint,
        ]
        self.user32.SetWindowPos.restype = wintypes.BOOL
        self.user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        self.user32.ShowWindow.restype = wintypes.BOOL
        self.user32.SetForegroundWindow.argtypes = [wintypes.HWND]
        self.user32.SetForegroundWindow.restype = wintypes.BOOL
        self.user32.GetSystemMetrics.argtypes = [ctypes.c_int]
        self.user32.GetSystemMetrics.restype = ctypes.c_int
        self.user32.keybd_event.argtypes = [ctypes.c_ubyte, ctypes.c_ubyte, ctypes.c_uint, ctypes.c_ulong]
        self.user32.keybd_event.restype = None
        self.user32.EnumWindows.argtypes = [ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM), wintypes.LPARAM]
        self.user32.EnumWindows.restype = wintypes.BOOL
        self._configure_theme()
        self._build_ui()
        self._install_exception_hook()
        self._build_stadium_loading_modal()
        self.setuppaths()
        self.refresh_camera_catalog()
        self.apply_bootstrap_files()
        self.refresh_modules()
        self.log("Application started")
        self._poll_job = self.after(500, self.poll_process)
        self._stats_job = self.after(250, self.stats_loop)
        self._overlay_job = self.after(80, self.overlay_loop)
        if self.module_enabled("Chants"):
            self._start_chants_runtime()
        # Log Discord RPC initialization status
        if self._discord_rpc_enabled:
            self.log("Discord RPC initialized (enabled in settings)")
        else:
            self.log("Discord RPC initialized (disabled in settings)")

    def _resolve_base_dir(self) -> Path:
        if getattr(sys, "frozen", False):
            return Path(sys.executable).resolve().parent
        return Path(__file__).resolve().parent.parent

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
        style.configure("TCombobox", fieldbackground=self.panel_alt, background=self.panel_alt, foreground=self.fg, arrowcolor=self.fg)
        style.configure(
            "Accent.Horizontal.TProgressbar",
            troughcolor=self.card_soft,
            background=self.accent,
            borderwidth=0,
            lightcolor=self.accent,
            darkcolor=self.accent,
        )
        style.configure(
            "LoadingStadium.Horizontal.TProgressbar",
            troughcolor=self.card_soft,
            background=self.accent,
            borderwidth=0,
            lightcolor=self.accent,
            darkcolor=self.accent,
            thickness=14,
        )

    def _install_exception_hook(self) -> None:
        def report(exc_type, exc_value, exc_tb):
            self.log("Unhandled exception", exc_value, exc_info=(exc_type, exc_value, exc_tb))

        self.report_callback_exception = report

    def log(self, message: str, error: Exception | None = None, exc_info=None) -> None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{timestamp}] {message}"
        if error is not None:
            line = f"{line}: {error}"
        if exc_info is not None:
            line = f"{line}\n{''.join(traceback.format_exception(*exc_info)).strip()}"
        elif error is not None:
            line = f"{line}\n{traceback.format_exc().strip()}" if traceback.format_exc().strip() != "NoneType: None" else line
        try:
            with self.log_path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        except Exception:
            pass
        if self.log_widget is not None:
            if self._log_widget_is_near_bottom():
                self._log_autofollow = True
            self.log_widget.configure(state="normal")
            self.log_widget.insert("end", line + "\n")
            if self._log_autofollow:
                self.log_widget.see("end")
            self.log_widget.configure(state="disabled")
            self._update_log_follow_ui()

    def _log_widget_is_near_bottom(self) -> bool:
        if self.log_widget is None:
            return True
        _first, last = self.log_widget.yview()
        return last >= 0.995

    def _refresh_log_autofollow_state(self, _event=None) -> None:
        self._log_autofollow = self._log_widget_is_near_bottom()
        self._update_log_follow_ui()

    def _jump_logs_to_latest(self) -> None:
        if self.log_widget is None:
            return
        self._log_autofollow = True
        self.log_widget.see("end")
        self._update_log_follow_ui()

    def _update_log_follow_ui(self) -> None:
        if self.log_status_label is not None:
            if self._log_autofollow:
                self.log_status_label.configure(text="Following latest logs", fg=self.success)
            else:
                self.log_status_label.configure(text="Browsing history", fg=self.gold)
        if self.log_follow_button is not None:
            self.log_follow_button.configure(state="disabled" if self._log_autofollow else "normal")

    def _window(self) -> tk.Misc:
        return self.ui_root or self

    def _build_ui(self) -> None:
        root = tk.Toplevel(self)
        root.title("CG Server 16 Python")
        root.geometry("1024x680")
        root.minsize(980, 640)
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.configure(bg=self.bg)
        self.ui_root = root

        top = tk.Frame(root, bg=self.bg, padx=10, pady=10)
        top.pack(fill="x")
        self.start_overlay_button = ttk.Button(top, text="Start Overlay", command=self.start_overlay_session)
        self.start_overlay_button.pack(side="left")
        ttk.Button(top, text="Locate FIFA 16 EXE", command=self.select_fifa_exe).pack(side="left", padx=6)
        ttk.Button(top, text="Launch FIFA 16", command=self.launch_fifa).pack(side="left", padx=6)
        ttk.Button(top, text="Assign Scoreboard", command=self.assign_scoreboard).pack(side="left", padx=6)
        ttk.Button(top, text="Assign Movie", command=self.assign_movie).pack(side="left", padx=6)
        ttk.Button(top, text="Exclude Competition", command=self.exclude_competition).pack(side="left", padx=6)
        self.toggle_logs_button = ttk.Button(top, text="Open Logs", command=self.toggle_logs)
        self.toggle_logs_button.pack(side="right")

        header = tk.Frame(root, bg=self.bg, padx=10)
        header.pack(fill="x")
        banner = tk.Frame(header, bg=self.panel, bd=0, highlightthickness=1, highlightbackground="#22314b")
        banner.pack(fill="x")
        tk.Label(
            banner,
            text="SERVER16 CONTROL ROOM",
            bg=self.panel,
            fg=self.gold,
            font=("Bahnschrift", 11, "bold"),
            padx=14,
            pady=8,
        ).pack(side="left")
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
            text="Waiting FIFA",
            bg="#1a2740",
            fg=self.accent,
            font=("Bahnschrift", 9, "bold"),
            padx=10,
            pady=5,
        )
        self.status_pill.pack(side="right", padx=10, pady=6)
        help_bar = tk.Frame(header, bg=self.bg)
        help_bar.pack(fill="x", pady=(8, 0))
        tk.Label(
            help_bar,
            text="Space toggles the overlay while FIFA is active ",
            bg=self.bg,
            fg=self.muted,
            font=("Bahnschrift", 9),
            anchor="w",
        ).pack(side="left")

        self.tabview = ttk.Notebook(root, style="Server16.TNotebook")
        self.tabview.pack(fill="both", expand=True, padx=10, pady=10)
        self.dashboard_tab = tk.Frame(self.tabview, bg=self.bg)
        self.logs_tab = tk.Frame(self.tabview, bg=self.bg)
        self.audio_tab = tk.Frame(self.tabview, bg=self.bg)
        self.camera_tab = tk.Frame(self.tabview, bg=self.bg)
        self.tabview.add(self.dashboard_tab, text="Dashboard")
        self.tabview.add(self.audio_tab, text="Chants")
        self.tabview.add(self.camera_tab, text="Camera")
        self.tabview.add(self.logs_tab, text="Logs")

        dashboard_host = tk.Frame(self.dashboard_tab, bg=self.bg)
        dashboard_host.pack(fill="both", expand=True, padx=10, pady=10)
        self.dashboard_canvas = tk.Canvas(dashboard_host, bg=self.bg, highlightthickness=0, bd=0)
        self.dashboard_scrollbar = ttk.Scrollbar(dashboard_host, orient="vertical", command=self.dashboard_canvas.yview)
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
        self._build_logs_card()

    def _build_stadium_loading_modal(self) -> None:
        modal = tk.Toplevel(self._window())
        modal.withdraw()
        modal.overrideredirect(True)
        modal.attributes("-topmost", True)
        modal.configure(bg=self.card)
        modal_frame = tk.Frame(modal, bg=self.card, highlightthickness=1, highlightbackground="#2a3c59", padx=12, pady=10)
        modal_frame.pack(fill="both", expand=True)
        self.stadium_loading_modal = modal
        self.stadium_loading_title = tk.Label(
            modal_frame,
            text="Loading Stadium",
            bg=self.card,
            fg=self.gold,
            font=("Bahnschrift", 12, "bold"),
            anchor="w",
        )
        self.stadium_loading_title.pack(fill="x")
        self.stadium_loading_preview = tk.Label(
            modal_frame,
            text="STADIUM\nPREVIEW",
            bg=self.card_soft,
            fg=self.muted,
            font=("Bahnschrift", 11, "bold"),
            justify="center",
            anchor="center",
            highlightthickness=1,
            highlightbackground="#243654",
        )
        self.stadium_loading_preview.pack(fill="x", pady=(6, 8), ipady=8)
        info_frame = tk.Frame(modal_frame, bg=self.card)
        info_frame.pack(fill="x")
        self.stadium_loading_info = info_frame
        self.stadium_loading_name = tk.Label(
            info_frame,
            text="-",
            bg=self.card,
            fg=self.fg,
            font=("Bahnschrift", 11, "bold"),
            anchor="w",
        )
        self.stadium_loading_name.pack(fill="x")
        self.stadium_loading_detail = tk.Label(
            info_frame,
            text="Preparing stadium assets",
            bg=self.card,
            fg=self.muted,
            font=("Bahnschrift", 9),
            anchor="w",
            justify="left",
            wraplength=312,
        )
        self.stadium_loading_detail.pack(fill="x", pady=(2, 6))
        self.stadium_loading_value = tk.DoubleVar(value=0)
        self.stadium_loading_bar = ttk.Progressbar(
            info_frame,
            maximum=100,
            variable=self.stadium_loading_value,
            style="LoadingStadium.Horizontal.TProgressbar",
            mode="determinate",
            length=292,
        )
        self.stadium_loading_bar.pack(fill="x", pady=(4, 3))
        self.stadium_loading_progress_text = tk.Label(
            info_frame,
            text="0%",
            bg=self.card,
            fg=self.accent,
            font=("Consolas", 10, "bold"),
            anchor="w",
        )
        self.stadium_loading_progress_text.pack(fill="x")
        modal.geometry("340x252")

    def _show_stadium_loading_modal(self, stadium_name: str, detail: str = "Preparing stadium assets", progress: float = 0.0) -> None:
        if self.stadium_loading_modal is None:
            return
        if not self.show_stadium_loading_var.get():
            self._stadium_loading_visible = False
            self._stadium_loading_restore_fullscreen = False
            return
        self.stadium_loading_modal.configure(cursor="arrow")
        self._update_stadium_loading_preview(stadium_name)
        if self.stadium_loading_name is not None:
            self.stadium_loading_name.configure(text=stadium_name or "-")
        if self.stadium_loading_detail is not None:
            self.stadium_loading_detail.configure(text=detail)
        if self.stadium_loading_value is not None:
            self.stadium_loading_value.set(max(0, min(100, progress)))
        if self.stadium_loading_progress_text is not None:
            self.stadium_loading_progress_text.configure(text=f"{int(max(0, min(100, progress)))}%")
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

    def _hide_stadium_loading_modal(self) -> None:
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

    def _update_stadium_loading_modal(self, value: float, detail: str) -> None:
        if self.stadium_loading_modal is None:
            return
        if self.stadium_loading_value is not None:
            self.stadium_loading_value.set(max(0, min(100, value)))
        if self.stadium_loading_detail is not None:
            self.stadium_loading_detail.configure(text=detail)
        if self.stadium_loading_progress_text is not None:
            self.stadium_loading_progress_text.configure(text=f"{int(max(0, min(100, value)))}%")
        if not self.show_stadium_loading_var.get():
            return
        if self._stadium_loading_visible:
            self._position_stadium_loading_modal()
            self.stadium_loading_modal.update_idletasks()
            self.stadium_loading_modal.update()

    def _position_stadium_loading_modal(self) -> None:
        if self.stadium_loading_modal is None:
            return
        window = self._window()
        window.update_idletasks()
        modal_height = 252 if self._stadium_loading_preview_visible else 148
        if self._overlay_visible and self._fifa_hwnd:
            rect = RECT()
            if self.user32.GetWindowRect(self._fifa_hwnd, ctypes.byref(rect)):
                x = rect.left + 24
                y = rect.top + 24
                self.stadium_loading_modal.geometry(f"340x{modal_height}+{x}+{y}")
                return
        root_x = window.winfo_rootx()
        root_y = window.winfo_rooty()
        self.stadium_loading_modal.geometry(f"340x{modal_height}+{root_x + 24}+{root_y + 24}")

    def _card(self, parent: tk.Misc, title: str, subtitle: str = "") -> tk.Frame:
        card = tk.Frame(parent, bg=self.card, bd=0, highlightthickness=1, highlightbackground="#243654")
        header = tk.Frame(card, bg=self.card)
        header.pack(fill="x", padx=12, pady=(10, 4))
        tk.Label(header, text=title, bg=self.card, fg=self.fg, font=("Bahnschrift", 13, "bold")).pack(anchor="w")
        if subtitle:
            tk.Label(header, text=subtitle, bg=self.card, fg=self.muted, font=("Bahnschrift", 9)).pack(anchor="w", pady=(1, 0))
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
        if self.dashboard_canvas is not None and self.dashboard_content is not None:
            self.dashboard_canvas.configure(scrollregion=self.dashboard_canvas.bbox("all"))

    def _on_dashboard_canvas_configure(self, event) -> None:
        if self.dashboard_canvas is not None and self.dashboard_window_id is not None:
            self.dashboard_canvas.itemconfigure(self.dashboard_window_id, width=event.width)

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

    def _resolve_stadium_preview_path(self, stadium_name: str) -> Path | None:
        stadium_name = (stadium_name or "").strip()
        if not stadium_name or stadium_name in {"-", "None", "Stadium Module Disable"}:
            return None
        candidate_roots: list[Path] = []
        targetpath = getattr(self, "targetpath", None)
        if targetpath is not None:
            candidate_roots.append(Path(targetpath))
        exedir = getattr(self, "exedir", None)
        if exedir is not None:
            candidate_roots.append(Path(exedir) / "StadiumGBD")
        seen: set[Path] = set()
        for root in candidate_roots:
            try:
                root = root.resolve()
            except Exception:
                root = Path(root)
            if root in seen:
                continue
            seen.add(root)
            preview_dir = root / "render" / "thumbnail" / "stadium"
            if not preview_dir.exists():
                continue
            for candidate in sorted(preview_dir.iterdir()):
                if not candidate.is_file():
                    continue
                if candidate.suffix.lower() not in {".png", ".jpg", ".jpeg", ".jepg"}:
                    continue
                if candidate.stem.casefold() == stadium_name.casefold():
                    return candidate
        return None

    def _load_preview_photo(self, image_path: Path | None, max_size: tuple[int, int]) -> ImageTk.PhotoImage | None:
        if image_path is None or not image_path.exists():
            return None
        try:
            image = Image.open(image_path).convert("RGBA")
            image.thumbnail(max_size)
            return ImageTk.PhotoImage(image)
        except Exception:
            return None

    def _update_stadium_preview(self, stadium_name: str) -> None:
        frame = self._stadium_preview_frame
        label = self._stadium_preview_label
        if label is None:
            return
        self._stadium_preview_image = None
        image_path = self._resolve_stadium_preview_path(stadium_name)
        photo = self._load_preview_photo(image_path, (520, 340))
        if photo is None:
            if frame is not None:
                frame.pack_forget()
            label.configure(image="", text="STADIUM\nPREVIEW", compound="center")
            return
        if frame is not None and not frame.winfo_manager():
            pack_kwargs = {"fill": "x", "padx": 10, "pady": (4, 8)}
            if self._stadium_preview_body_anchor is not None:
                frame.pack(before=self._stadium_preview_body_anchor, **pack_kwargs)
            else:
                frame.pack(**pack_kwargs)
        self._stadium_preview_image = photo
        label.configure(image=photo, text="", compound="center")

    def _update_stadium_loading_preview(self, stadium_name: str) -> None:
        label = self.stadium_loading_preview
        if label is None:
            return
        self._stadium_loading_image = None
        image_path = self._resolve_stadium_preview_path(stadium_name)
        photo = self._load_preview_photo(image_path, (250, 110))
        if photo is None:
            if self._stadium_loading_preview_visible:
                label.pack_forget()
                self._stadium_loading_preview_visible = False
                self._position_stadium_loading_modal()
            label.configure(image="", text="", compound="center")
            return
        if not self._stadium_loading_preview_visible:
            pack_target = self.stadium_loading_info if self.stadium_loading_info is not None else self.stadium_loading_name
            label.pack(fill="x", pady=(6, 8), ipady=8, before=pack_target)
            self._stadium_loading_preview_visible = True
            self._position_stadium_loading_modal()
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
        try:
            window.overrideredirect(False)
        except Exception:
            pass
        try:
            window.transient(None)
        except Exception:
            pass
        try:
            window.attributes("-topmost", True)
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

    def _resolve_team_logo_path(self, team_id: str) -> Path | None:
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
            label.configure(text="LOGO", compound="center")
        else:
            label.configure(text="", compound="center")
        label.configure(image=image_ref)
        self._team_logo_images[prefix] = image_ref

    def _build_matchup_card(self, parent: tk.Misc, row: int) -> None:
        card = self._card(parent, "MATCHUP", "Teams, score and match clock")
        card.grid(row=row, column=0, sticky="ew", pady=(0, 12))
        card.configure(height=230)
        card.grid_propagate(False)
        body = tk.Frame(card, bg=self.card)
        body.pack(fill="both", expand=True, padx=12, pady=(6, 12))
        body.grid_columnconfigure(0, weight=2)
        body.grid_columnconfigure(1, weight=1)
        body.grid_columnconfigure(2, weight=2)

        self._build_team_panel(body, 0, "TEAM A", "home")
        center = tk.Frame(body, bg=self.card)
        center.grid(row=0, column=1, sticky="nsew", padx=8)
        tk.Label(center, text="SCORE", bg=self.card, fg=self.muted, font=("Bahnschrift", 9)).pack(pady=(18, 2))
        score_label = tk.Label(center, text="0 x 0", bg=self.card, fg=self.gold, font=("Bahnschrift", 28, "bold"))
        score_label.pack()
        tk.Label(center, text="TIME", bg=self.card, fg=self.muted, font=("Bahnschrift", 9)).pack(pady=(18, 2))
        timer_label = tk.Label(center, text="00:00", bg=self.card, fg=self.accent, font=("Consolas", 18, "bold"))
        timer_label.pack()
        self._register_info_label("score", score_label)
        self._register_info_label("timer", timer_label)
        self._build_team_panel(body, 2, "TEAM B", "away")

    def _build_team_panel(self, parent: tk.Misc, column: int, title: str, prefix: str) -> None:
        panel = tk.Frame(parent, bg=self.card_soft, highlightthickness=1, highlightbackground="#243654")
        panel.grid(row=0, column=column, sticky="nsew", padx=(0 if column == 0 else 6, 0 if column == 2 else 6))
        logo = tk.Label(
            panel,
            width=116,
            height=72,
            bg=self.card_soft,
            fg=self.muted,
            text="LOGO",
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
        tk.Label(panel, text="Name", bg=self.card_soft, fg=self.muted, font=("Bahnschrift", 9)).pack(anchor="w", padx=10)
        name_label = tk.Label(panel, text=title, bg=self.card_soft, fg=self.fg, font=("Bahnschrift", 14, "bold"))
        name_label.pack(anchor="w", padx=10)
        tk.Label(panel, text="ID", bg=self.card_soft, fg=self.muted, font=("Bahnschrift", 9)).pack(anchor="w", padx=10, pady=(8, 0))
        id_label = tk.Label(panel, text="-", bg=self.card_soft, fg=self.accent, font=("Consolas", 14, "bold"))
        id_label.pack(anchor="w", padx=10, pady=(0, 10))
        self._register_info_label(name_key, name_label)
        self._register_info_label(id_key, id_label)
        self._set_display(name_key, title)

    def _build_match_card(self, parent: tk.Misc, row: int) -> None:
        card = self._card(parent, "MATCH HUB", "Tournament, round, page and match state")
        card.grid(row=row, column=0, sticky="ew", pady=(0, 12))
        card.configure(height=178)
        card.grid_propagate(False)
        body = tk.Frame(card, bg=self.card)
        body.pack(fill="x", padx=12, pady=(6, 12))
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=1)
        self._build_stat(body, 0, 0, "Tournament", "tour", "-")
        self._build_stat(body, 0, 1, "Round ID", "round", "-")
        self._build_stat(body, 1, 0, "Current Page", "page", "-")
        self._build_stat(body, 1, 1, "Derby Key", "derby", "-")
        self._build_stat(body, 2, 0, "Minute / Second", "match_clock_split", "00 / 00")
        self._build_stat(body, 2, 1, "Game State", "game_state", "Idle")
        self._build_stat(body, 3, 0, "Goal Status", "goal_active", "No")
        self._build_stat(body, 3, 1, "Last Update", "last_update", "-")

    def _build_assets_card(self, parent: tk.Misc, row: int) -> None:
        card = self._card(parent, "ASSET ROUTING", "Active TV logo, scoreboard and movie")
        card.grid(row=row, column=0, sticky="ew")
        card.configure(height=164)
        card.grid_propagate(False)
        body = tk.Frame(card, bg=self.card)
        body.pack(fill="x", padx=12, pady=(6, 12))
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=1)
        self._build_stat(body, 0, 0, "TV Logo", "tvlogo", "default")
        self._build_stat(body, 0, 1, "Scoreboard", "scoreboard", "default")
        self._build_stat(body, 1, 0, "Movie", "movie", "default")
        self._build_stat(body, 1, 1, "Status", "status", "Idle")
        ttk.Button(card, text="Edit Asset Settings", command=self.open_assets_settings_editor).pack(fill="x", padx=12, pady=(0, 12))

    def _build_stadium_card(self, parent: tk.Misc, row: int) -> None:
        card = self._card(parent, "STADIUM BAY", "Preview and loaded stadium details")
        card.grid(row=row, column=0, sticky="nsew", pady=(0, 12))
        card.configure(height=464)
        card.grid_propagate(False)
        preview_frame = tk.Frame(card, bg=self.card)
        preview_frame.pack(fill="x", padx=10, pady=(4, 8))
        preview = tk.Label(
            preview_frame,
            text="STADIUM\nPREVIEW",
            bg=self.card_soft,
            fg=self.muted,
            font=("Bahnschrift", 12, "bold"),
            justify="center",
            anchor="center",
            highlightthickness=1,
            highlightbackground="#243654",
        )
        preview.pack(fill="x", ipady=80)
        self._stadium_preview_frame = preview_frame
        self._stadium_preview_label = preview
        body = tk.Frame(card, bg=self.card)
        body.pack(fill="x", padx=12, pady=(0, 12))
        self._stadium_preview_body_anchor = body
        body.grid_columnconfigure(0, weight=1)
        self._build_stat(body, 0, 0, "Current Stadium", "stadium", "-", value_wraplength=300, block_height=64)
        self._build_stat(body, 1, 0, "Stadium ID", "stadid", "-")
        notification_switch = ttk.Checkbutton(
            card,
            style="Switch.TCheckbutton",
            text="Show loading notification",
            variable=self.show_stadium_loading_var,
            command=self._toggle_stadium_loading_visibility,
        )
        notification_switch.pack(anchor="w", padx=12, pady=(0, 10))
        ttk.Button(card, text="Assign Stadium", command=self.assign_stadium).pack(fill="x", padx=12, pady=(0, 10))
        ttk.Button(card, text="Edit Stadium Settings", command=self.open_stadium_settings_editor).pack(fill="x", padx=12, pady=(0, 10))
        self.progress_text = tk.Label(card, text="Idle", bg=self.card, fg=self.muted, font=("Bahnschrift", 9))
        self.progress_text.pack(anchor="w", padx=12, pady=(0, 4))
        self.progress_value = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(card, maximum=100, variable=self.progress_value, style="Accent.Horizontal.TProgressbar")
        self.progress_bar.pack(fill="x", padx=12, pady=(0, 12))
        self._set_progress(0, "Idle")
        self._update_stadium_preview(self.labels["stadium"].cget("text"))

    def _toggle_stadium_loading_visibility(self) -> None:
        self.settings.show_stadium_loading_notification = self.show_stadium_loading_var.get()
        if self.show_stadium_loading_var.get():
            return
        self._hide_stadium_loading_modal()

    def _build_modules_card(self, parent: tk.Misc, row: int) -> None:
        card = self._card(parent, "MODULES", "Loaded from settings.ini at startup")
        card.grid(row=row, column=0, sticky="ew")
        card.configure(height=200)
        card.grid_propagate(False)
        modules = tk.Frame(card, bg=self.card)
        modules.pack(fill="x", padx=12, pady=(6, 12))
        module_names = ["Stadium", "TvLogo", "ScoreBoard", "Movies", "Autorun", "StadiumNet", "Chants", "Discord RPC"]
        for idx, name in enumerate(module_names):
            initial = self._discord_rpc_enabled if name == "Discord RPC" else False
            var = tk.BooleanVar(value=initial)
            self.module_vars[name] = var
            check = ttk.Checkbutton(modules, style="Switch.TCheckbutton", text=name, variable=var)
            check.state(["disabled"])
            check.grid(row=idx // 2, column=idx % 2, padx=6, pady=4, sticky="w")
            self.module_checks[name] = check

    def _toggle_discord_rpc(self) -> None:
        """Toggle Discord RPC on/off and save to settings."""
        new_state = self.module_vars["Discord RPC"].get()
        
        # Update internal state first
        self._discord_rpc_enabled = new_state
        
        # Update settings.json
        discord_config = self.settings.data.get("discord_rpc", {})
        discord_config["enabled"] = new_state
        self.settings.data["discord_rpc"] = discord_config
        self.settings.save()
        self.module_states["Discord RPC"] = new_state
        if self._has_selected_fifa_exe():
            self.settings_ini.write("discordRP", "1" if new_state else "0", "Modules")
            self.settings_ini.save()
        else:
            self.log("Discord RPC state kept only in runtime/settings.json until FIFA EXE is selected")
        
        # Connect or disconnect based on new state
        try:
            if new_state:
                # Enable Discord RPC
                success = self.discord_rpc.connect()
                if success:
                    self.log("Discord RPC enabled and connected")
                else:
                    self.log("Discord RPC enabled but failed to connect (Discord may not be running)")
            else:
                # Disable Discord RPC - disconnect and clear presence
                self.discord_rpc.disconnect()
                self.log("Discord RPC disabled and presence cleared")
        except Exception as exc:
            self.log("Error toggling Discord RPC", exc, exc_info=sys.exc_info())
            # Revert checkbox if there was an error
            self._discord_rpc_enabled = not new_state
            self.module_states["Discord RPC"] = not new_state
            self.module_vars["Discord RPC"].set(not new_state)
            discord_config["enabled"] = not new_state
            self.settings.data["discord_rpc"] = discord_config
            self.settings.save()
            if self._has_selected_fifa_exe():
                self.settings_ini.write("discordRP", "1" if not new_state else "0", "Modules")
                self.settings_ini.save()

    def _build_audio_card(self) -> None:
        card = self._card(self.audio_tab, "CHANTS CONTROL", "Crowd audio, club anthem and detailed playback state")
        card.pack(fill="both", expand=True, padx=10, pady=10)
        body = tk.Frame(card, bg=self.card)
        body.pack(fill="both", expand=True, padx=12, pady=(6, 12))
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=1)
        self._build_stat(body, 0, 0, "Chants Module", "audio_module", "Disabled")
        self._build_stat(body, 0, 1, "Chants Status", "audio_status", "Idle")
        self._build_stat(body, 1, 0, "Current Chant", "audio_current", "-")
        self._build_stat(body, 1, 1, "Club Anthem", "audio_clubsong", "-")
        self._build_stat(body, 2, 0, "Chants Folder", "audio_chants_dir", "-")
        self._build_stat(body, 2, 1, "Last Action", "audio_last_action", "-")
        self._build_stat(body, 3, 0, "Crowd Mode", "audio_crowd_mode", "Idle")
        self._build_stat(body, 3, 1, "Crowd Volume", "audio_crowd_volume", "-")
        self._build_stat(body, 4, 0, "Crowd Source", "audio_source", "-")
        self._build_stat(body, 4, 1, "Next Behavior", "audio_next", "-")
        self._build_stat(body, 5, 0, "Home Goals", "home_goals", "0")
        self._build_stat(body, 5, 1, "Away Goals", "away_goals", "0")
        ttk.Button(card, text="Edit Chants Settings", command=self.open_audio_settings_editor).pack(fill="x", padx=12, pady=(0, 12))

    def _build_camera_tab(self) -> None:
        card_host = tk.Frame(self.camera_tab, bg=self.bg)
        card_host.pack(fill="both", expand=True, padx=10, pady=10)
        card_host.grid_columnconfigure(0, weight=2)
        card_host.grid_columnconfigure(1, weight=3)
        card_host.grid_rowconfigure(0, weight=1)

        library_card = self._card(card_host, "CAMERA LIBRARY", "Select the Anth package folder / Selecione a pasta do pacote Anth")
        library_card.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        library_body = tk.Frame(library_card, bg=self.card)
        library_body.pack(fill="both", expand=True, padx=12, pady=(6, 12))
        self.camera_select_button = ttk.Button(
            library_body,
            text="Choose Camera Package / Escolher pacote de camera",
            command=self.select_camera_package,
        )
        self.camera_select_button.pack(fill="x", pady=(0, 8))
        self.camera_package_label = tk.Label(
            library_body,
            text="No camera package selected / Nenhum pacote de camera selecionado",
            bg=self.card,
            fg=self.muted,
            font=("Bahnschrift", 9),
            anchor="w",
            justify="left",
        )
        self.camera_package_label.pack(fill="x", pady=(0, 8))
        list_frame = tk.Frame(library_body, bg=self.card)
        list_frame.pack(fill="both", expand=True)
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical")
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

        detail_card = self._card(card_host, "CAMERA PREVIEW", "Adaptive full preview / Preview completo adaptavel")
        detail_card.grid(row=0, column=1, sticky="nsew")
        detail_body = tk.Frame(detail_card, bg=self.card)
        detail_body.pack(fill="both", expand=True, padx=12, pady=(6, 12))
        detail_body.grid_columnconfigure(0, weight=1)
        detail_body.grid_rowconfigure(1, weight=1)
        self.camera_name_label = tk.Label(
            detail_body,
            text="No camera selected / Nenhuma camera selecionada",
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
            text="PREVIEW",
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
            text="No preview / Sem preview",
            bg=self.card,
            fg=self.muted,
            font=("Bahnschrift", 9),
            anchor="w",
        )
        self.camera_preview_status.grid(row=2, column=0, sticky="ew", pady=(0, 6))
        self.camera_example_combo = ttk.Combobox(detail_body, state="readonly", textvariable=self.camera_example_var)
        self.camera_example_combo.grid(row=3, column=0, sticky="ew", pady=(0, 8))
        self.camera_example_combo.bind("<<ComboboxSelected>>", self._on_camera_example_change)
        self.camera_instruction_text = scrolledtext.ScrolledText(
            detail_body,
            height=5,
            bg=self.panel,
            fg=self.fg,
            insertbackground=self.fg,
            relief="flat",
            borderwidth=0,
            font=("Consolas", 9),
            wrap="word",
        )
        self.camera_instruction_text.grid(row=4, column=0, sticky="nsew")
        self.camera_instruction_text.configure(state="disabled")
        self.camera_apply_button = ttk.Button(detail_body, text="Apply Camera", command=self.apply_selected_camera)
        self.camera_apply_button.grid(row=5, column=0, sticky="ew", pady=(12, 0))

    def _build_logs_card(self) -> None:
        logs = ttk.LabelFrame(self.logs_tab, text="Logs", padding=10)
        self.logs_frame = logs
        logs.pack(fill="both", expand=True, padx=10, pady=10)
        header = tk.Frame(logs, bg=self.bg)
        header.pack(fill="x", pady=(0, 8))
        self.log_status_label = tk.Label(
            header,
            text="Following latest logs",
            bg=self.bg,
            fg=self.success,
            font=("Bahnschrift", 9, "bold"),
            anchor="w",
        )
        self.log_status_label.pack(side="left")
        self.log_follow_button = ttk.Button(header, text="Jump To Latest / Ir para o fim", command=self._jump_logs_to_latest)
        self.log_follow_button.pack(side="right")
        self.log_widget = scrolledtext.ScrolledText(
            logs,
            height=18,
            bg=self.panel,
            fg=self.fg,
            insertbackground=self.fg,
            relief="flat",
            borderwidth=0,
            font=("Consolas", 9),
        )
        self.log_widget.pack(fill="both", expand=True)
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
                    text=f"{len(self._camera_presets)} cameras found / encontradas em {package_dir}",
                    fg=self.muted,
                )
            else:
                self.camera_package_label.configure(
                    text="Choose a valid 'Anth's FIFA 16 AIO Camera Mod Package' folder / Escolha uma pasta valida do pacote",
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
            self.camera_name_label.configure(text=preset.name if preset is not None else "No camera selected / Nenhuma camera selecionada")
        if self.camera_apply_button is not None:
            self.camera_apply_button.configure(state="normal" if preset is not None else "disabled")
        if self.camera_instruction_text is not None:
            self.camera_instruction_text.configure(state="normal")
            self.camera_instruction_text.delete("1.0", "end")
            self.camera_instruction_text.insert("1.0", preset.instructions_text if preset is not None else "No camera selected.\nNenhuma camera selecionada.")
            self.camera_instruction_text.configure(state="disabled")
        if self.camera_example_combo is not None:
            values = [path.name for path in preset.example_paths] if preset is not None else []
            self.camera_example_combo.configure(values=values)
            if values:
                self.camera_example_var.set(values[0])
                self._show_camera_example(preset, values[0])
            else:
                self.camera_example_var.set("")
                self._clear_camera_preview("No preview / Sem preview")

    def _show_camera_example(self, preset: CameraPreset, image_name: str) -> None:
        target = next((path for path in preset.example_paths if path.name == image_name), None)
        if target is None:
            self._clear_camera_preview("No preview / Sem preview")
            return
        cache_key = (preset.name, target.name)
        image_obj = self._camera_preview_cache.get(cache_key)
        if image_obj is None:
            try:
                image_obj = Image.open(target).convert("RGBA")
                self._camera_preview_cache[cache_key] = image_obj
            except Exception as exc:
                self.log(f"Failed to load camera preview {target}", exc, exc_info=sys.exc_info())
                self._clear_camera_preview(f"Failed to open  {target.name}")
                return
        self._camera_preview_source_key = cache_key
        self._render_camera_preview()
        if self.camera_preview_status is not None:
            self.camera_preview_status.configure(text=f"Preview: {target.name}")

    def _clear_camera_preview(self, text: str) -> None:
        self._camera_preview_source_key = None
        if self.camera_preview_image_label is not None:
            self.camera_preview_image_label.configure(image="", text="PREVIEW")
            self.camera_preview_image_label.image = None
        if self.camera_preview_status is not None:
            self.camera_preview_status.configure(text=text)

    def _on_camera_preview_canvas_configure(self, _event=None) -> None:
        self._render_camera_preview()

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
        selected = filedialog.askdirectory(title="Select Anth's FIFA 16 AIO Camera Mod Package")
        if not selected:
            return
        if not self.camera_runtime.is_valid_package_dir(selected):
            messagebox.showwarning(
                "Camera Package / Pacote de camera",
                "Select the exact folder named 'Anth's FIFA 16 AIO Camera Mod Package'.\nSelecione exatamente a pasta com esse nome.",
            )
            return
        self.settings.camera_package = selected
        self._camera_preview_cache.clear()
        self.refresh_camera_catalog()
        self.log(f"Camera package selected: {selected}")

    def apply_selected_camera(self) -> None:
        preset = self._camera_presets_by_name.get(self._camera_selected_name or "")
        if preset is None:
            messagebox.showwarning("Camera", "Select a camera before applying.\nSelecione uma camera antes de aplicar.")
            return
        if self.fifaEXE == "default":
            messagebox.showwarning("Camera", "Select the FIFA 16 executable first.\nSelecione o executavel do FIFA 16 primeiro.")
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
                regen_message = f"REGENERATOR iniciado em {regen['path']}."
            else:
                regen_message = regen.get("message", "Nao foi possivel iniciar o REGENERATOR.") if isinstance(regen, dict) else "Nao foi possivel iniciar o REGENERATOR."
            self.log(f"Camera applied: {preset.name} ({copied_files} arquivos atualizados)")
            self.log(regen_message)
            if self.camera_preview_status is not None:
                self.camera_preview_status.configure(text=f"Applied / Aplicada: {preset.name}")
            messagebox.showinfo(
                "Camera applied / Camera aplicada",
                f"{preset.name} applied successfully.\n{preset.name} aplicada com sucesso.\n\nUpdated files / Arquivos atualizados: {copied_files}\n{regen_message}",
            )
        except Exception as exc:
            self.log(f"Failed to apply camera {preset.name}", exc, exc_info=sys.exc_info())
            messagebox.showerror("Camera", f"Failed to apply camera:\n{exc}")
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
        tk.Label(block, text=title, bg=self.card, fg=self.muted, font=("Bahnschrift", 9)).pack(anchor="w")
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
        self.labels[key] = label

    def toggle_logs(self) -> None:
        if self.tabview is None or self.toggle_logs_button is None:
            return
        current = self.tabview.index(self.tabview.select())
        logs_index = self.tabview.index(self.logs_tab)
        if current == logs_index:
            self.tabview.select(0)
            self.toggle_logs_button.configure(text="Open Logs")
        else:
            self.tabview.select(logs_index)
            self.toggle_logs_button.configure(text="Back To Dashboard")

    def _set_progress(self, value: float, text: str) -> None:
        if self.progress_value is not None:
            self.progress_value.set(max(0, min(100, value)))
        if self.progress_text is not None:
            self.progress_text.configure(text=text)
        self._set_display("status", text)
        if self._stadium_task_running:
            self._update_stadium_loading_modal(value, text)
        self.update_idletasks()

    def _set_process_status(self, text: str, color: str | None = None) -> None:
        if self.status_pill is not None:
            self.status_pill.configure(text=text, fg=color or self.accent)

    def _sync_page_banner(self, page_name: str) -> None:
        self._set_display("page", page_name or "-")
        if self.page_banner is not None:
            self.page_banner.configure(text=page_name or "-")

    def _should_auto_apply_runtime(self, page_name: str) -> bool:
        return page_name == "game/screens/playNow/KickOffHub"

    def _schedule_worker_poll(self) -> None:
        if self._closing or self._worker_poll_job is not None:
            return
        self._worker_poll_job = self.after(50, self._poll_worker_queue)

    def _poll_worker_queue(self) -> None:
        self._worker_poll_job = None
        while not self._worker_queue.empty():
            event = self._worker_queue.get()
            kind = event[0]
            if kind == "progress":
                _, value, text = event
                self._set_progress(value, text)
            elif kind == "done":
                _, payload = event
                self._finish_stadium_apply(payload)
            elif kind == "error":
                _, message = event
                self._stadium_task_running = False
                self._stadium_task_signature = None
                self._stadium_task_request_key = None
                self._set_process_status("Stadium Error", self.error)
                self._hide_stadium_loading_modal()
                self.log(message)
        if self._stadium_task_running or not self._worker_queue.empty():
            self._schedule_worker_poll()

    def setuppaths(self, load_team_database: bool = True) -> None:
        self.fifaEXE = self.settings.fifa_exe
        self.MP = Path(self.fifaEXE).stem if self.fifaEXE != "default" else ""
        self.exedir = Path(self.fifaEXE).parent if self.fifaEXE != "default" else self.base_dir
        self.TVLogo = self.exedir / "TVLogoGBD"
        self.TVdata = self.exedir / "data" / "ui" / "game" / "overlays"
        self.Scoredata = self.exedir / "data" / "ui"
        self.MOVBUMP = self.exedir / "data" / "ui" / "TV" / "bumper.big"
        self.ScoreBoard = self.exedir / "ScoreBoardGBD"
        self.Movies = self.exedir / "MoviesGBD"
        self.Movdata = self.exedir / "data" / "movies" / "bootflowoutro.vp8"
        self.targetpath = self.exedir / "StadiumGBD"
        self.Psource = self._first_existing(self.exedir / "FSW" / "Police", self.exedir / "FSW" / "Images" / "Police")
        self.Nsource = self._first_existing(self.exedir / "FSW" / "Nets", self.exedir / "FSW" / "Images" / "Nets")
        self.PitchMowsource = self._first_existing(self.exedir / "FSW" / "PitchMowPattern", self.exedir / "FSW" / "Images" / "PitchMowPattern")
        self.Pdest = self.exedir / "data" / "sceneassets" / "slc"
        self.Ndest = self.exedir / "data" / "sceneassets" / "goalnet"
        self.PitchMowdest = self.exedir / "data" / "sceneassets" / "pitch"
        self.settings_ini = SessionIniFile(self.exedir / "FSW" / "settings.ini")
        self._load_module_states()
        self._update_audio_overview()
        if load_team_database:
            self._load_team_database()

    def _first_existing(self, *paths: Path) -> Path:
        for path in paths:
            if path.exists():
                return path
        return paths[0]

    def _load_module_states(self) -> None:
        module_names = ["Stadium", "TvLogo", "ScoreBoard", "Movies", "Autorun", "StadiumNet", "Chants"]
        self.module_states = {name: self.settings_ini.read(name, "Modules") == "1" for name in module_names}
        previous_rpc_state = self._discord_rpc_enabled
        discord_ini_value = self.settings_ini.read("discordRP", "Modules")
        if discord_ini_value in {"0", "1"}:
            self._discord_rpc_enabled = discord_ini_value == "1"
        elif self._has_selected_fifa_exe():
            self.settings_ini.write("discordRP", "1" if self._discord_rpc_enabled else "0", "Modules")
            self.settings_ini.save()
        else:
            self.log("Skipping Modules bootstrap in settings.ini until FIFA EXE is selected")
        self.module_states["Discord RPC"] = self._discord_rpc_enabled
        loaded = ", ".join(
            f"{name}={'1' if enabled else '0'}"
            for name, enabled in self.module_states.items()
        )
        self.log(f"Modules loaded from {self.exedir / 'FSW' / 'settings.ini'}: {loaded}")

        if self._discord_rpc_enabled:
            if not self.discord_rpc.is_connected():
                self.discord_rpc.connect()
        elif previous_rpc_state or self.discord_rpc.is_connected():
            self.discord_rpc.disconnect()

        discord_var = self.module_vars.get("Discord RPC")
        if discord_var is not None:
            discord_var.set(self._discord_rpc_enabled)

    def module_enabled(self, name: str) -> bool:
        if name == "Discord RPC":
            return self._discord_rpc_enabled
        enabled = self.settings_ini.read(name, "Modules") == "1"
        self.module_states[name] = enabled
        return enabled

    def _has_selected_fifa_exe(self) -> bool:
        return bool(self.fifaEXE and self.fifaEXE != "default")

    def _open_settings_editor(self, editor_key: str, title: str, specs, initial_section: str | None = None) -> None:
        existing = self._settings_editors.get(editor_key)
        if existing is not None and existing.winfo_exists():
            existing.deiconify()
            existing.lift()
            existing.focus_force()
            existing._refresh_active_frame()
            return
        editor = SettingsAreaEditor(self, title, specs, initial_section=initial_section)
        self._settings_editors[editor_key] = editor
        editor.bind("<Destroy>", lambda _event, key=editor_key: self._settings_editors.pop(key, None))

    def open_stadium_settings_editor(self) -> None:
        self._open_settings_editor("stadium", "Stadium Settings", stadium_specs())

    def open_assets_settings_editor(self) -> None:
        self._open_settings_editor("assets", "Asset Settings", asset_specs())

    def open_audio_settings_editor(self) -> None:
        self._open_settings_editor("audio", "Chants Settings", audio_specs())

    def select_fifa_exe(self) -> None:
        filename = filedialog.askopenfilename(filetypes=[("Executable", "*.exe")], title="Select FIFA 16 EXE")
        if not filename:
            return
        window = self._window()
        window.configure(cursor="watch")
        window.update_idletasks()
        try:
            self._set_process_status("Loading FIFA Data", self.accent)
            self._set_progress(8, "Saving selected executable")
            self.settings.fifa_exe = filename
            self._set_progress(24, "Configuring runtime paths")
            self.setuppaths(load_team_database=False)
            self._load_team_database(lambda value, text: self._set_progress(value, text))
            self._set_progress(82, "Applying bootstrap files")
            self.apply_bootstrap_files()
            self._set_progress(94, "Refreshing modules")
            self.refresh_modules()
            self._set_progress(100, "FIFA data ready")
            self._set_process_status("FIFA Ready", self.success)
            self.log(f"Selected FIFA executable: {filename}")
        except Exception as exc:
            self._set_process_status("FIFA Load Error", self.error)
            self.log("Failed while loading FIFA data after selecting executable", exc, exc_info=sys.exc_info())
            messagebox.showerror("FIFA 16", "Could not finish loading FIFA data. Check logs for details.")
        finally:
            window.configure(cursor="")
            window.update_idletasks()

    def _auto_detect_fifa_exe(self) -> Path | None:
        for name in ("fifa16.exe", "FIFA16.exe", "FIFA 16.exe", "fifa 16.exe"):
            candidate = self.base_dir / name
            if candidate.exists():
                return candidate
        if self.settings.fifa_exe and self.settings.fifa_exe != "default":
            candidate = Path(self.settings.fifa_exe)
            if candidate.exists():
                return candidate
        return None

    def _load_team_database(self, progress_callback=None) -> None:
        """Load FIFA team database for the selected installation"""
        if not self.fifaEXE or self.fifaEXE == "default":
            self.team_db = None
            self.discord_rpc.set_team_name_resolver(None)
            return
        
        try:
            fifa_root = Path(self.fifaEXE).parent
            self.team_db = FifaDatabase(fifa_root)
            if progress_callback is not None:
                progress_callback(50, "Connecting to FIFA database")
            if self.team_db.connect():
                if progress_callback is not None:
                    progress_callback(72, "Loading teams and stadiums")
                team_count = self.team_db.load_all_teams()
                # Connect resolver to Discord RPC
                self.discord_rpc.set_team_name_resolver(self.team_db.get_team_name)
                self.log(f" Team database loaded for {fifa_root.name} ({team_count} teams)")
                if progress_callback is not None:
                    progress_callback(78, "Team database ready")
            else:
                reason = self.team_db.last_error if self.team_db else "unknown reason"
                self.log(f"️  Could not connect to team database: {reason}")
                self.team_db = None
                if progress_callback is not None:
                    progress_callback(78, "Database unavailable, continuing")
        except Exception as e:
            self.log(f"❌ Error loading team database: {e}")
            self.team_db = None
            if progress_callback is not None:
                progress_callback(78, "Database load failed, continuing")

    def _resolve_team_name(self, team_id: str) -> str | None:
        """Resolve a team id to its display name using the loaded team database."""
        if not team_id or team_id in {"-", "0"} or self.team_db is None:
            return None
        try:
            return self.team_db.get_team_name(team_id)
        except Exception:
            return None

    def _resolve_stadium_name(self, stadium_id: str) -> str | None:
        """Resolve a stadium id to its display name using the loaded database."""
        if not stadium_id or stadium_id in {"-", "0"} or self.team_db is None:
            return None
        try:
            return self.team_db.get_stadium_name(stadium_id)
        except Exception:
            return None

    def _has_active_custom_stadium_assignment(self) -> bool:
        """Return True when current context resolves to a custom stadium assignment in settings.ini."""
        if not hasattr(self, "settings_ini") or self.settings_ini is None:
            return False
        try:
            if self.TOURROUNDID and self.settings_ini.key_exists(self.TOURROUNDID, "comp"):
                return True
            if self.TOURNAME and self.settings_ini.key_exists(self.TOURNAME, "comp"):
                return True
            if self.HID and self.settings_ini.key_exists(self.HID, "stadium"):
                return True
        except Exception:
            return False
        return False

    def _is_target_process_running(self) -> bool:
        if not self.MP:
            return False
        try:
            return any(Path((p.info.get("name") or "")).stem.lower() == self.MP.lower() for p in psutil.process_iter(["name"]))
        except Exception:
            return False

    def start_overlay_session(self) -> None:
        fifa_path = self._auto_detect_fifa_exe()
        if fifa_path is None:
            messagebox.showwarning(
                "FIFA 16",
                "Could not find FIFA 16 in the same folder as this app.\nNao encontrei o FIFA 16 na mesma pasta deste app.",
            )
            self.select_fifa_exe()
            fifa_path = self._auto_detect_fifa_exe()
            if fifa_path is None:
                return
        self.settings.fifa_exe = str(fifa_path)
        self.setuppaths()
        self.apply_bootstrap_files()
        self.refresh_modules()
        self._overlay_enabled = True
        self._launcher_mode = False
        self._set_process_status("Overlay Armed", self.accent)
        self.log(f"Overlay session armed for FIFA executable: {fifa_path}")
        if not self._is_target_process_running():
            self.launch_fifa()
        self._hide_overlay()

    def launch_fifa(self) -> None:
        if self.fifaEXE == "default":
            messagebox.showwarning("FIFA 16", "Selecione o executável do FIFA 16 primeiro.")
            return
        if self._is_target_process_running():
            self.log(f"FIFA process already running: {self.fifaEXE}")
            return
        subprocess.Popen([self.fifaEXE], shell=False)
        self.log(f"Launched FIFA executable: {self.fifaEXE}")

    def overlay_loop(self) -> None:
        self._overlay_job = None
        if self._closing:
            return
        try:
            self._sync_overlay_hotkey()
            if self._overlay_visible:
                self._position_overlay()
        except Exception as exc:
            self.log("Overlay loop error", exc, exc_info=sys.exc_info())
        if not self._closing:
            self._overlay_job = self.after(80, self.overlay_loop)

    def _sync_overlay_hotkey(self) -> None:
        if not self._overlay_enabled:
            return
        now = perf_counter()
        foreground = int(self.user32.GetForegroundWindow() or 0)
        self._fifa_hwnd = self._find_fifa_window_handle()
        key_down = bool(self.user32.GetAsyncKeyState(0x20) & 0x8000)
        if self._overlay_visible:
            can_toggle = bool(self._fifa_hwnd or self._overlay_hwnd)
        else:
            can_toggle = foreground in {self._fifa_hwnd, self._overlay_hwnd} and foreground != 0
        if key_down and not self._overlay_space_down and can_toggle and now >= self._overlay_toggle_ready_at:
            if self._overlay_visible:
                self._hide_overlay()
            else:
                self._show_overlay()
            self._overlay_toggle_ready_at = now + 0.22
        self._overlay_space_down = key_down
        if self._overlay_visible and not self._fifa_hwnd:
            self._hide_overlay()

    def _apply_noactivate_window_style(self, hwnd: int) -> None:
        if not hwnd:
            return
        try:
            ex_style = int(self.user32.GetWindowLongW(hwnd, GWL_EXSTYLE))
            ex_style |= WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
            self.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style)
            self.user32.SetWindowPos(
                hwnd,
                HWND_TOPMOST,
                0,
                0,
                0,
                0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW,
            )
        except Exception:
            pass

    def _apply_overlay_window_style(self) -> None:
        self._apply_noactivate_window_style(self._overlay_hwnd)

    def _focus_fifa_window(self) -> None:
        if not self._fifa_hwnd:
            return
        try:
            self.user32.ShowWindow(self._fifa_hwnd, SW_RESTORE)
        except Exception:
            pass
        try:
            self.user32.SetForegroundWindow(self._fifa_hwnd)
        except Exception:
            pass

    def _show_overlay(self) -> None:
        if not self._fifa_hwnd:
            return
        window = self._window()
        self._launcher_mode = False
        self._restore_fullscreen_on_hide = self._is_probable_fullscreen_window(self._fifa_hwnd)
        window.overrideredirect(True)
        window.attributes("-topmost", True)
        window.deiconify()
        window.update_idletasks()
        self._overlay_hwnd = window.winfo_id()
        self._apply_overlay_window_style()
        self._position_overlay()
        try:
            self.user32.ShowWindow(self._overlay_hwnd, SW_SHOWNOACTIVATE)
        except Exception:
            pass
        self.after(10, self._focus_fifa_window)
        self._overlay_visible = True
        self._set_process_status("Overlay Visible", self.success)

    def _hide_overlay(self) -> None:
        window = self._window()
        self._overlay_visible = False
        if self._overlay_hwnd:
            try:
                self.user32.ShowWindow(self._overlay_hwnd, SW_HIDE)
            except Exception:
                pass
        window.withdraw()
        self._set_process_status("Overlay Hidden", self.gold if self._overlay_enabled else self.accent)
        self.after(10, self._focus_fifa_window)
        if self._restore_fullscreen_on_hide:
            self.after(120, self._restore_fifa_fullscreen)

    def _position_overlay(self) -> None:
        if not self._fifa_hwnd:
            return
        window = self._window()
        rect = RECT()
        if not self.user32.GetWindowRect(self._fifa_hwnd, ctypes.byref(rect)):
            return
        game_width = max(1, rect.right - rect.left)
        game_height = max(1, rect.bottom - rect.top)
        overlay_width = min(game_width - 24, max(980, int(game_width * 0.86)))
        overlay_height = min(max(360, int(game_height * 0.58)), game_height - 24)
        x = rect.left + max(0, (game_width - overlay_width) // 2)
        y = rect.top + 8
        window.geometry(f"{overlay_width}x{overlay_height}+{x}+{y}")
        if self._overlay_hwnd:
            try:
                self.user32.SetWindowPos(
                    self._overlay_hwnd,
                    HWND_TOPMOST,
                    x,
                    y,
                    overlay_width,
                    overlay_height,
                    SWP_NOACTIVATE | SWP_SHOWWINDOW,
                )
            except Exception:
                pass

    def _is_probable_fullscreen_window(self, hwnd: int) -> bool:
        if not hwnd:
            return False
        rect = RECT()
        if not self.user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return False
        width = max(1, rect.right - rect.left)
        height = max(1, rect.bottom - rect.top)
        screen_width = max(1, int(self.user32.GetSystemMetrics(0)))
        screen_height = max(1, int(self.user32.GetSystemMetrics(1)))
        tolerance = 8
        return abs(width - screen_width) <= tolerance and abs(height - screen_height) <= tolerance

    def _restore_fifa_fullscreen(self) -> None:
        if not self._fifa_hwnd:
            return
        self._focus_fifa_window()
        try:
            self.user32.keybd_event(VK_MENU, 0, 0, 0)
            self.user32.keybd_event(VK_RETURN, 0, 0, 0)
            self.user32.keybd_event(VK_RETURN, 0, KEYEVENTF_KEYUP, 0)
            self.user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)
            self.log("Attempted fullscreen restore with Alt+Enter")
        except Exception as exc:
            self.log("Failed to restore FIFA fullscreen", exc, exc_info=sys.exc_info())
        finally:
            self._restore_fullscreen_on_hide = False
            self.after(180, self._focus_fifa_window)

    def _find_fifa_window_handle(self) -> int:
        pid = self._resolve_fifa_pid()
        if not pid:
            return 0
        matches: list[int] = []
        callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        @callback_type
        def enum_proc(hwnd, _lparam):
            if not self.user32.IsWindowVisible(hwnd):
                return True
            owner_pid = wintypes.DWORD()
            self.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner_pid))
            if owner_pid.value == pid:
                rect = RECT()
                if self.user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                    if rect.right > rect.left and rect.bottom > rect.top:
                        matches.append(int(hwnd))
                        return False
            return True

        self.user32.EnumWindows(enum_proc, 0)
        return matches[0] if matches else 0

    def _resolve_fifa_pid(self) -> int:
        if self.memory.process_id and self.memory.is_open():
            return int(self.memory.process_id)
        if not self.MP:
            return 0
        try:
            for proc in psutil.process_iter(["pid", "name"]):
                if Path((proc.info.get("name") or "")).stem.lower() == self.MP.lower():
                    return int(proc.info["pid"])
        except Exception:
            return 0
        return 0

    def apply_bootstrap_files(self) -> None:
        if self.fifaEXE == "default":
            return
        started_at = perf_counter()
        self.version = checkver(self.fifaEXE)
        self.log(f"Applying bootstrap files for version: {self.version}")
        for path in (
            self.Pdest,
            self.Ndest,
            self.PitchMowdest,
            self.TVdata,
            self.Scoredata / "game",
            self.exedir / "data" / "sceneassets" / "stadium",
            self.exedir / "data" / "sceneassets" / "fx",
            self.exedir / "data" / "sceneassets" / "crowdplacement",
            self.exedir / "data" / "sceneassets" / "crowdchair",
            self.exedir / "data" / "bcdata" / "camera",
            self.exedir / "data" / "ui" / "nav",
            self.exedir / "data" / "ui" / "TV",
            self.exedir / "data" / "movies",
        ):
            checkdirs(path)
        extra_setup(self.Psource, self.Pdest, "4", "4", "4")
        extra_setup(self.Psource, self.Pdest, "9", "9", "9")
        extra_setup(self.Nsource, self.Ndest, "0", "netcolor", "0")
        extra_setup(self.PitchMowsource, self.PitchMowdest, "0", "pitchmowpattern", "0")
        copy(self.exedir / "FSW" / "stadium", self.exedir / "data" / "sceneassets")
        copy(self.exedir / "FSW" / "TVLogo", self.TVdata)
        copy(self.exedir / "FSW" / "ScoreBoard", self.Scoredata / "game")
        if self.module_enabled("Movies"):
            copy_if_exists(self.exedir / "FSW" / "Nav" / "pausemenuflow.nav_new", self.exedir / "data" / "ui" / "nav" / "pausemenuflow.nav")
            copy_if_exists(self.exedir / "FSW" / "Nav" / "bootflowoutro.vp8", self.Movdata)
            copy_if_exists(self.exedir / "FSW" / "Nav" / "bumper.big", self.MOVBUMP)
        else:
            copy_if_exists(self.exedir / "FSW" / "Nav" / "pausemenuflow.nav_Original", self.exedir / "data" / "ui" / "nav" / "pausemenuflow.nav")
            copy_if_exists(self.exedir / "FSW" / "Nav" / "Fbootflowoutro.vp8", self.Movdata)
            copy_if_exists(self.exedir / "FSW" / "Nav" / "bumper.big", self.MOVBUMP)
        self._update_audio_overview()
        self.log(f"Bootstrap files ready in {perf_counter() - started_at:.2f}s")

    def refresh_modules(self) -> None:
        self._load_module_states()
        for name, var in self.module_vars.items():
            if name == "Discord RPC":
                var.set(self._discord_rpc_enabled)
            else:
                var.set(self.module_enabled(name))
        self._update_audio_overview()

    def toggle_module(self, module: str) -> None:
        if module in self.module_vars:
            self.module_vars[module].set(self.module_enabled(module))

    def poll_process(self) -> None:
        if self._closing:
            return
        try:
            if not self.offsets.is_configured():
                self._sync_page_banner("Offsets nao configurados na classe Offsets")
                self._set_process_status("Offsets Missing", self.error)
                self.log("Offsets are not configured")
                self._poll_job = self.after(500, self.poll_process)
                return
            running = bool(self.MP) and any(Path((p.info.get("name") or "")).stem.lower() == self.MP.lower() for p in psutil.process_iter(["name"]))
            if running and self.memory.attack(self.MP):
                self._attached_once = True
                self._set_process_status("FIFA Attached", self.success)
                self.update_page_name()
            else:
                self._sync_page_banner("Process not running")
                self._set_process_status("Waiting FIFA", self.accent)
                if self._attached_once:
                    self.log("Game process ended; closing server automatically")
                    self.on_close()
                    return
                self._reset_chants_state()
        except Exception as exc:
            self._sync_page_banner(f"Polling error: {exc}")
            self._set_process_status("Polling Error", self.error)
            self.log("Polling error", exc, exc_info=sys.exc_info())
        if not self._closing:
            self._poll_job = self.after(500, self.poll_process)

    def stats_loop(self) -> None:
        if self._closing:
            return
        try:
            if self.memory.is_open():
                page_name = self.labels["page"].cget("text") if "page" in self.labels else self.lastpagename
                self._update_live_match_stats(page_name)
                if (not self.HID or not self.AID) and self._page_can_have_match_context(page_name):
                    self.refresh_live_context(page_name)
            # Update Discord RPC presence
            if self._discord_rpc_enabled:
                self._update_discord_presence()
        except Exception as exc:
            self.log("Stats loop error", exc, exc_info=sys.exc_info())
        if not self._closing:
            self._stats_job = self.after(250, self.stats_loop)

    def update_page_name(self) -> None:
        try:
            page_name = self.memory.get_string(self.offsets.ORIPGBASE, self.offsets.PG1, size=64)
            self._sync_page_banner(page_name)
            self._handle_page_transition(page_name)
            if self._page_can_have_match_context(page_name):
                self.refresh_live_context(page_name)
        except Exception as exc:
            self._sync_page_banner(f"Offset pending: {exc}")
            self._set_process_status("Reading Page", self.gold)
            self.log("Failed to read page name", exc, exc_info=sys.exc_info())

    def _handle_page_transition(self, page_name: str) -> None:
        if page_name == self.lastpagename:
            return
        self.lastpagename = page_name
        if page_name == "game/screens/playNow/KickOffHub":
            self._kickoff_generation += 1
            self._last_stadium_applied_signature = None
            self.pagechange = True
            self.skillgamechange = False
            self.bumperpagechange = False
            self._clear_live_context()
            self._kickoff_retry_remaining = 12
            self._schedule_kickoff_retry()
            return
        if "training/SkillGame" in page_name:
            self.skillgamechange = True
            return
        if not page_name.strip() and not self.matchstarted and not self.skillgamechange:
            self._start_chants_runtime()
            return
        if "TV/bumper" in page_name or "skillGames/SkillGa" in page_name:
            if not self.bumperpagechange and not self.skillgamechange:
                self.pagechange = False
                self.bumperpagechange = True
                self.skillgamechange = True
                self.tv_bumper_page()
            return
        self.pagechange = False
        self.bumperpagechange = False
        self.skillgamechange = False

    def _clear_live_context(self) -> None:
        self.HID = ""
        self.AID = ""
        self.STADID = ""
        self.TOURNAME = ""
        self.TOURROUNDID = ""
        self.derby = ""
        self._last_runtime_signature = None
        self._last_live_score = (0, 0)
        self._last_score_snapshot = (0, 0)
        self._last_chants_score_snapshot = None
        self._chants_resume_after = 0.0
        self._last_live_update = ""
        self._set_display("hid", "-")
        self._set_display("aid", "-")
        self._set_display("tour", "-")
        self._set_display("round", "-")
        self._set_display("derby", "-")
        self._set_display("stadid", "-")
        self._set_display("stadium", "-")
        self._set_display("home_name", "TEAM A")
        self._set_display("away_name", "TEAM B")
        self._update_team_logo("home", "")
        self._update_team_logo("away", "")
        self._set_display("score", "0 x 0")
        self._set_display("timer", "00:00")
        self._set_display("home_goals", "0")
        self._set_display("away_goals", "0")
        self._set_display("match_clock_split", "00 / 00")
        self._set_display("game_state", "Idle")
        self._set_display("goal_active", "No")
        self._set_display("last_update", "-")

    def _schedule_kickoff_retry(self) -> None:
        if self._closing or self._kickoff_retry_job is not None:
            return
        self._kickoff_retry_job = self.after(250, self._kickoff_retry_tick)

    def _kickoff_retry_tick(self) -> None:
        self._kickoff_retry_job = None
        if self._closing:
            return
        page_name = self.labels["page"].cget("text")
        if page_name != "game/screens/playNow/KickOffHub":
            self._kickoff_retry_remaining = 0
            return
        self.refresh_live_context(page_name)
        if self.HID not in {"", "0"} and self.AID not in {"", "0"}:
            self._kickoff_retry_remaining = 0
            self.log(f"KickOffHub context captured HID={self.HID} AID={self.AID}")
            return
        if self._kickoff_retry_remaining > 0:
            self._kickoff_retry_remaining -= 1
            self._schedule_kickoff_retry()

    def _page_can_have_match_context(self, page_name: str) -> bool:
        if not page_name:
            return False
        candidates = (
            "KickOffHub",
            "playNow",
            "team",
            "squad",
            "stadium",
            "TV/bumper",
        )
        lowered = page_name.lower()
        return any(token.lower() in lowered for token in candidates)

    def _read_legacy_team_context(self) -> tuple[str | None, str | None]:
        if not self.MP:
            return None, None
        legacy_memory = Memory()
        try:
            if not legacy_memory.attack(self.MP) or not legacy_memory.is_open():
                return None, None
            hid = str(legacy_memory.get_int(self.offsets.ORIHTIDBASE, self.offsets.HT[:5]))
            aid = str(legacy_memory.get_int(self.offsets.ORIHTIDBASE, self.offsets.HT[:4] + [self.offsets.HT[5]]))
            if hid == "0":
                friendly_hid = str(legacy_memory.get_int(self.offsets.ORIFRIHTIDBASE, self.offsets.HT2[:5]))
                friendly_aid = str(legacy_memory.get_int(self.offsets.ORIFRIHTIDBASE, self.offsets.HT2[:4] + [self.offsets.HT2[5]]))
                if friendly_hid != "0":
                    hid = friendly_hid
                if friendly_aid != "0":
                    aid = friendly_aid
            return hid, aid
        except Exception as exc:
            self.log("Legacy team context read failed", exc, exc_info=sys.exc_info())
            return None, None
        finally:
            legacy_memory.close()

    def refresh_live_context(self, page_name: str) -> None:
        hid, aid = self._read_legacy_team_context()
        if hid is None:
            hid = self._try_read_context_int("HT-HID", self.offsets.ORIHTIDBASE, self.offsets.HT, page_name)
        if aid is None:
            aid = self._try_read_context_int("HT-AID", self.offsets.ORIHTIDBASE, self.offsets.HT[:4] + [self.offsets.HT[5]], page_name)
        dashboard_hid = self._read_dashboard_pointer("DASHBOARDHOMEIDBASE", "DASHBOARDHOMEID")
        dashboard_aid = self._read_dashboard_pointer("DASHBOARDAWAYIDBASE", "DASHBOARDAWAYID")
        if hid in {"0", None} or aid in {"0", None}:
            friendly_hid = self._try_read_context_int("HT2-HID", self.offsets.ORIFRIHTIDBASE, self.offsets.HT2[:5], page_name)
            friendly_aid = self._try_read_context_int("HT2-AID", self.offsets.ORIFRIHTIDBASE, self.offsets.HT2[:4] + [self.offsets.HT2[5]], page_name)
            if hid in {"0", None} and friendly_hid not in {None, "0"}:
                hid = friendly_hid
            if aid in {"0", None} and friendly_aid not in {None, "0"}:
                aid = friendly_aid
        if hid in {"0", None} and dashboard_hid not in {None, 0}:
            hid = str(dashboard_hid)
        if aid in {"0", None} and dashboard_aid not in {None, 0}:
            aid = str(dashboard_aid)
        self.Stadiumtype = "first"
        stadid = self._try_read_context_int(
            "S-FIRST",
            self.offsets.ORISTADIDBASE,
            [self.offsets.S[0], self.offsets.S[1], self.offsets.S[2], self.offsets.S[4], self.offsets.S[5]],
            page_name,
        )
        if stadid == "0" or stadid is None:
            alter = self._try_read_context_int(
                "S-ALTER",
                self.offsets.ORISTADIDBASE,
                [self.offsets.S[0], self.offsets.S[1], self.offsets.S[3], self.offsets.S[4], self.offsets.S[5]],
                page_name,
            )
            if alter is not None:
                stadid = alter
                self.Stadiumtype = "alter"
        tour = self._try_read_context_int("T-TOUR", self.offsets.ORITOURIDBASE, self.offsets.T[:5], page_name)
        round_id = self._try_read_context_int("T-ROUND", self.offsets.ORITOURIDBASE, self.offsets.T[:4] + [self.offsets.T[5]], page_name)
        if hid not in {None, "0"}:
            self.HID = hid
        if aid not in {None, "0"}:
            self.AID = aid
        if stadid not in {None, "0"}:
            self.STADID = stadid
        if tour not in {None, "0"}:
            self.TOURNAME = tour
        if round_id not in {None, "0"}:
            self.TOURROUNDID = round_id
        if not any(value for value in (self.HID, self.AID, self.STADID, self.TOURNAME, self.TOURROUNDID)):
            return
        self.derby = f"{self.HID}vs{self.AID}"
        self._set_display("hid", self.HID or "-")
        self._set_display("aid", self.AID or "-")
        self._update_team_logo("home", self.HID or "")
        self._update_team_logo("away", self.AID or "")
        self._set_display("tour", self.TOURNAME or "-")
        self._set_display("round", self.TOURROUNDID or "-")
        self._set_display("derby", self.derby or "-")
        self._set_display("stadid", self.STADID or "-")
        home_name = self._resolve_team_name(self.HID or "")
        away_name = self._resolve_team_name(self.AID or "")
        self._set_display("home_name", home_name or (f"Team A ({self.HID})" if self.HID else "TEAM A"))
        self._set_display("away_name", away_name or (f"Team B ({self.AID})" if self.AID else "TEAM B"))
        self._update_live_match_stats(page_name)
        signature = (self.HID, self.AID, self.TOURNAME, self.TOURROUNDID, self.STADID)
        if signature != self._last_runtime_signature:
            self._last_runtime_signature = signature
            self.log(
                f"Live context updated page={page_name} HID={self.HID or '-'} AID={self.AID or '-'} "
                f"TOUR={self.TOURNAME or '-'} ROUND={self.TOURROUNDID or '-'} STAD={self.STADID or '-'}"
            )
            if self._should_auto_apply_runtime(page_name):
                self.apply_all_runtime()

    def _try_read_context_int(self, trace_name: str, static_ptr: int, offsets: list[int], page_name: str) -> str | None:
        try:
            value = str(self.memory.get_int(static_ptr, offsets))
            self._last_context_error = None
            return value
        except MemoryAccessError as exc:
            message = f"Context not ready for page '{page_name}' [{trace_name}]: {exc}"
            if message != self._last_context_error:
                self._last_context_error = message
                self.log(message)
                self._log_pointer_debug()
            return None
        except Exception as exc:
            self.log(f"Failed to read context {trace_name}", exc, exc_info=sys.exc_info())
            return None

    def _try_read_optional_int(self, static_ptr: int, offsets: list[int]) -> int | None:
        try:
            if not static_ptr or not offsets or not any(offsets):
                return None
            return self.memory.get_int(static_ptr, offsets)
        except Exception:
            return None

    def _read_dashboard_pointer(self, base_attr: str, offsets_attr: str) -> int | None:
        static_ptr = getattr(self.offsets, base_attr, 0)
        offsets = getattr(self.offsets, offsets_attr, [])
        if not static_ptr or not offsets or not any(offsets):
            return None
        return self._try_read_optional_int(static_ptr, offsets)

    def _is_game_running(self) -> bool:
        try:
            started = self.memory.get_int(self.offsets.GAMESTARTEDBINARYBASE, self.offsets.GAMESTARTEDBINARY)
            ran_time = self.memory.get_int(self.offsets.GAMESTATSBASE, self.offsets.GAMERANTIME)
            return started == 1 and ran_time >= 1 and "training/SkillGame" not in self.lastpagename
        except Exception:
            return False

    def _is_game_running_with(self, memory: Memory) -> bool:
        try:
            started = memory.get_int(self.offsets.GAMESTARTEDBINARYBASE, self.offsets.GAMESTARTEDBINARY)
            ran_time = memory.get_int(self.offsets.GAMESTATSBASE, self.offsets.GAMERANTIME)
            return started == 1 and ran_time >= 1 and "training/SkillGame" not in self.lastpagename
        except Exception:
            return False

    def _update_live_match_stats(self, page_name: str) -> None:
        score_home = self._try_read_optional_int(self.offsets.GAMESTATSBASE, self.offsets.GAMEHOMEGOALSCORE)
        score_away = self._try_read_optional_int(self.offsets.GAMESTATSBASE, self.offsets.GAMEAWAYGOALSCORE)
        raw_time = self._try_read_optional_int(self.offsets.GAMESTATSBASE, self.offsets.GAMERANTIME)
        started = self._try_read_optional_int(self.offsets.GAMESTARTEDBINARYBASE, self.offsets.GAMESTARTEDBINARY)
        if score_home is not None and score_away is not None:
            if (score_home, score_away) != self._last_live_score:
                self._chants_resume_after = max(self._chants_resume_after, time.time() + 6.0)
                self._last_live_score = (score_home, score_away)
        score_home_display = score_home if score_home is not None else 0
        score_away_display = score_away if score_away is not None else 0
        self._set_display("home_goals", str(score_home_display))
        self._set_display("away_goals", str(score_away_display))
        self._set_display("score", f"{score_home_display} x {score_away_display}")
        if raw_time is None:
            minutes = 0
            seconds = 0
        else:
            total_seconds = raw_time // 100 if raw_time > 6000 else raw_time
            minutes, seconds = divmod(max(0, total_seconds), 60)
        self._set_display("timer", f"{max(0, minutes):02d}:{max(0, seconds):02d}")
        self._set_display("match_clock_split", f"{max(0, minutes):02d} / {max(0, seconds):02d}")
        goal_active = time.time() < self._chants_resume_after
        if started == 1 and raw_time and raw_time >= 1:
            game_state = "Running"
        elif self.matchstarted or self._chants_paused:
            game_state = "Paused"
        else:
            game_state = "Idle"
        self._set_display("game_state", game_state)
        self._set_display("goal_active", "Yes" if goal_active else "No")
        self._last_live_update = datetime.now().strftime("%H:%M:%S")
        self._set_display("last_update", self._last_live_update)
        if "TV/bumper" in page_name:
            self._set_display("audio_last_action", "TV bumper active")

    def _update_discord_presence(self) -> None:
        """Update Discord Rich Presence with current match state."""
        # Only update if Discord RPC is enabled
        if not self._discord_rpc_enabled:
            return
        
        try:
            if not self.discord_rpc.is_connected():
                # Try to reconnect if not connected
                self.discord_rpc.connect()
            
            page_name = self.labels.get("page", tk.Label()).cget("text") if "page" in self.labels else self.lastpagename
            
            # Get current match state
            score_home = self.labels.get("home_goals", tk.Label()).cget("text") if "home_goals" in self.labels else "0"
            score_away = self.labels.get("away_goals", tk.Label()).cget("text") if "away_goals" in self.labels else "0"
            # Read match time directly from memory to avoid stale UI label values.
            match_time = "00:00"
            raw_time = self._try_read_optional_int(self.offsets.GAMESTATSBASE, self.offsets.GAMERANTIME)
            if raw_time is not None:
                total_seconds = raw_time // 100 if raw_time > 6000 else raw_time
                minutes, seconds = divmod(max(0, total_seconds), 60)
                match_time = f"{minutes:02d}:{seconds:02d}"
            elif "timer" in self.labels:
                match_time = self.labels.get("timer", tk.Label()).cget("text")
            game_state = self.labels.get("game_state", tk.Label()).cget("text") if "game_state" in self.labels else "Idle"
            custom_stadium_display = ""
            if self._has_active_custom_stadium_assignment():
                custom_stadium_display = (
                    self.ScoreboardStadName
                    or self.curstad
                    or getattr(self, "StadName", "")
                )
            stadium_display = custom_stadium_display or self._resolve_stadium_name(self.STADID) or ""
            
            # Build presence using helper
            presence = self.discord_rpc.build_match_presence(
                home_team=self.HID or "",
                away_team=self.AID or "",
                home_score=int(score_home) if score_home.isdigit() else 0,
                away_score=int(score_away) if score_away.isdigit() else 0,
                match_time=match_time,
                tournament=self.TOURNAME or "",
                round_name=self.TOURROUNDID or "",
                stadium=stadium_display,
                game_state=game_state,
            )
            
            # Only update if presence changed (reduce API calls)
            if presence != self._discord_rpc_last_presence:
                self.discord_rpc.update_presence(**presence)
                self._discord_rpc_last_presence = presence
                # Log Discord RPC updates for debugging
                self.log(f"Discord RPC updated: {presence.get('state', 'N/A')}")
        except Exception as exc:
            self.log("Discord RPC update error", exc, exc_info=sys.exc_info())

    def _log_pointer_debug(self) -> None:
        traces = [
            ("HT-HID", self.offsets.ORIHTIDBASE, self.offsets.HT),
            ("HT-AID", self.offsets.ORIHTIDBASE, self.offsets.HT[:4] + [self.offsets.HT[5]]),
            ("HT2-HID", self.offsets.ORIFRIHTIDBASE, self.offsets.HT2[:5]),
            ("HT2-AID", self.offsets.ORIFRIHTIDBASE, self.offsets.HT2[:4] + [self.offsets.HT2[5]]),
            ("S-FIRST", self.offsets.ORISTADIDBASE, [self.offsets.S[0], self.offsets.S[1], self.offsets.S[2], self.offsets.S[4], self.offsets.S[5]]),
            ("S-ALTER", self.offsets.ORISTADIDBASE, [self.offsets.S[0], self.offsets.S[1], self.offsets.S[3], self.offsets.S[4], self.offsets.S[5]]),
            ("T-TOUR", self.offsets.ORITOURIDBASE, self.offsets.T[:5]),
            ("T-ROUND", self.offsets.ORITOURIDBASE, self.offsets.T[:4] + [self.offsets.T[5]]),
        ]
        for name, static_ptr, offsets in traces:
            try:
                chain = self.memory.trace_pointer_chain(static_ptr, offsets)
                self.log(f"Pointer trace {name}\n" + "\n".join(chain))
            except Exception as exc:
                self.log(f"Pointer trace {name} failed", exc, exc_info=sys.exc_info())

    def apply_all_runtime(self) -> None:
        self.log(f"Applying runtime HID={self.HID} AID={self.AID} TOUR={self.TOURNAME} ROUND={self.TOURROUNDID} STAD={self.STADID}")
        self._set_progress(5, "Applying runtime")
        if self.module_enabled("Stadium"):
            self.apply_stadium_runtime()
        else:
            self._set_display("stadium", "Stadium Module Disable")
            # Clear stadium from previous match when module is disabled
            self.curstad = ""
            self.ScoreboardStadName = ""
        self.apply_scoreboard_runtime()
        self.apply_movie_runtime()
        if not self._stadium_task_running:
            self._set_progress(100, "Runtime ready")

    def apply_stadium_runtime(self) -> None:
        self.stadium_runtime.apply_stadium_runtime()

    def _start_stadium_task(self, section_id: str, section_name: str, injid: str, stadium_signature: tuple) -> None:
        self.stadium_runtime.start_stadium_task(section_id, section_name, injid, stadium_signature)

    def _run_stadium_copy_job(self, hid: str, section: str, injid: str) -> dict:
        return self.stadium_runtime.run_stadium_copy_job(hid, section, injid)

    def _finish_stadium_apply(self, payload: dict) -> None:
        self.stadium_runtime.finish_stadium_apply(payload)

    def _stadium_offsets(self, stadium_type: str) -> list[int]:
        return self.stadium_runtime.stadium_offsets(stadium_type)

    def _play_stadium_loaded_sound(self) -> None:
        self.stadium_runtime.play_stadium_loaded_sound()

    def _update_audio_overview(self) -> None:
        self.assets_runtime.update_audio_overview()

    def apply_scoreboard_runtime(self) -> None:
        self.assets_runtime.apply_scoreboard_runtime()

    def apply_movie_runtime(self) -> None:
        self.assets_runtime.apply_movie_runtime()

    def tv_bumper_page(self) -> None:
        self.assets_runtime.tv_bumper_page()

    def _start_chants_runtime(self) -> None:
        self.chants_runtime.start_chants_runtime()

    def _reset_chants_state(self) -> None:
        self.chants_runtime.reset_chants_state()

    def _fade_player(self, player: MciAudioPlayer, start: float, end: float, duration_ms: int) -> None:
        self.chants_runtime.fade_player(player, start, end, duration_ms)

    def _play_club_song_if_exists(self, team_id: str) -> None:
        self.chants_runtime.play_club_song_if_exists(team_id)

    def _chants_runtime_loop(self) -> None:
        self.chants_runtime.chants_runtime_loop()

    def _refresh_context_for_assignment(self) -> None:
        self.assignment_runtime.refresh_context_for_assignment()

    def _default_scope_for_scoreboard(self) -> str:
        return self.assignment_runtime.default_scope_for_scoreboard()

    def _default_scope_for_movie(self) -> str:
        return self.assignment_runtime.default_scope_for_movie()

    def _default_scope_for_stadium(self) -> str:
        return self.assignment_runtime.default_scope_for_stadium()

    def _resolve_assignment_target(self, scope: str, mapping: dict[str, tuple[str, str]]) -> tuple[str, str] | tuple[None, None]:
        return self.assignment_runtime.resolve_assignment_target(scope, mapping)

    def assign_scoreboard(self) -> None:
        self.assignment_runtime.assign_scoreboard()

    def assign_movie(self) -> None:
        self.assignment_runtime.assign_movie()

    def assign_stadium(self) -> None:
        self.assignment_runtime.assign_stadium()

    def exclude_competition(self) -> None:
        self.assignment_runtime.exclude_competition()

    def scoreboards(self, comp: str, tvlogo: str, scoreboard: str) -> None:
        self.assignment_runtime.scoreboards(comp, tvlogo, scoreboard)

    def teamscoreboards(self, comp: str, tvlogo: str, scoreboard: str) -> None:
        self.assignment_runtime.teamscoreboards(comp, tvlogo, scoreboard)

    def moviesassign(self, comp: str, movie: str, section: str) -> None:
        self.assignment_runtime.moviesassign(comp, movie, section)

    def assignstadium_value(self, comp: str, value: str, section: str) -> None:
        self.assignment_runtime.assignstadium_value(comp, value, section)

    def assigncompstadium(self, comp: str, value: str, section: str) -> None:
        self.assignment_runtime.assigncompstadium(comp, value, section)

    def _assign_with_delete(self, comp: str, key: str, value: str, default_value: str, success_message: str) -> None:
        self.assignment_runtime.assign_with_delete(comp, key, value, default_value, success_message)

    def on_close(self) -> None:
        self._closing = True
        self._chants_stop.set()
        self._reset_chants_state()
        # Disconnect Discord RPC and clear presence
        try:
            self.discord_rpc.disconnect()
        except Exception:
            pass
        try:
            if self._poll_job is not None:
                self.after_cancel(self._poll_job)
        except Exception:
            pass
        try:
            if self._stats_job is not None:
                self.after_cancel(self._stats_job)
        except Exception:
            pass
        try:
            if self._overlay_job is not None:
                self.after_cancel(self._overlay_job)
        except Exception:
            pass
        try:
            if self._kickoff_retry_job is not None:
                self.after_cancel(self._kickoff_retry_job)
        except Exception:
            pass
        try:
            if self._worker_poll_job is not None:
                self.after_cancel(self._worker_poll_job)
        except Exception:
            pass
        try:
            self.memory.close()
        except Exception:
            pass
        try:
            self.quit()
        except Exception:
            pass
        self.destroy()


def main() -> None:
    app = Server16App()
    app.mainloop()
