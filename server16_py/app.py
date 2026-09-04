from __future__ import annotations

import ctypes
import queue
import random
import threading
import tkinter as tk
from time import perf_counter
from ctypes import wintypes

from PIL import Image, ImageTk

from . import __version__ as APP_VERSION
from .asset_runtime import AssetRuntime
from .db_patcher import restore_stadium_names
from .assignment_runtime import AssignmentRuntime
from .camera_runtime import CameraPreset, CameraRuntime
from .chants_runtime import ChantsRuntime, MciAudioPlayer
from .entrance_runtime import TeamEntranceRuntime
from .discord_rpc_runtime import DiscordRPCRuntime, StadiumPreviewUploader
from .fifa_db import FifaDatabase
from .file_tools import checkdirs, checkver, copy, copy_if_exists, extra_setup
from .kit_mixer import KitMixRuntime
from .memory_access import Memory
from .movie_preview_runtime import MoviePreviewRuntime
from .localization import LocalizationManager
from .offsets import Offsets
from .settings_editor import SettingsAreaEditor
from .settings_store import SettingsStore
from .stadium_runtime import StadiumRuntime
from .substitution_runtime import SubstitutionRuntime
from .update_checker import GithubReleaseChecker
from .win32_types import RECT, POINT

from .app_localization import LocalizationMixin
from .app_logging import LogMixin
from .app_ui import UIMixin
from .app_overlay import OverlayMixin
from .app_game import GameMixin
from .app_settings import SettingsMixin


class Server16App(LocalizationMixin, LogMixin, UIMixin, OverlayMixin, GameMixin, SettingsMixin, tk.Tk):
    UPDATE_REPO_OWNER = "michelMK45"
    UPDATE_REPO_NAME = "CG-File-Server-16---Python-Port"

    def __init__(self) -> None:
        super().__init__()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.withdraw()
        self.base_dir = self._resolve_base_dir()
        self.resource_dir = self._resolve_resource_dir()
        self.icon_path = self._resolve_icon_path()
        self._window_icon_image = None
        self.log_path = self.base_dir / "runtime" / "server16.log"
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.settings = SettingsStore(self.base_dir / "runtime" / "settings.json")
        # main() makes this process per-monitor DPI aware so GetCursorPos/
        # ScreenToClient return real screen pixels (see main()'s comment). A
        # side effect: Tk auto-derives its font/widget scaling from the
        # monitor's *real* DPI once it sees this process is DPI aware,
        # enlarging fonts/padding — but every geometry("WxH") call in this
        # app (app_ui.py, dialogs.py, settings_editor.py) is a literal pixel
        # count that doesn't grow to match, so the window box clips its own
        # (now bigger) content, hiding buttons at the top/bottom. Pin Tk's
        # base scaling to the traditional 96-DPI value, independent of the
        # process's real DPI, and layer the user's saved zoom level (see
        # app_ui.py's _apply_ui_zoom / the zoom buttons) on top of that fixed
        # base rather than on whatever the monitor happens to report.
        self._base_tk_scaling = 96 / 72
        self.tk.call("tk", "scaling", self._base_tk_scaling * self.settings.ui_zoom)
        self.show_stadium_loading_var = tk.BooleanVar(value=self.settings.show_stadium_loading_notification)
        self.auto_apply_substitution_var = tk.BooleanVar(value=self.settings.auto_apply_substitution_count)
        self.show_overlay_var = tk.BooleanVar(value=self.settings.show_overlay)
        self.kit_hotkeys_var = tk.BooleanVar(value=self.settings.kit_hotkeys_enabled)
        self.keep_open_var = tk.BooleanVar(value=self.settings.keep_open_on_game_close)
        self.overlay_performance_mode_var = tk.BooleanVar(value=self.settings.overlay_performance_mode)
        self.localization = LocalizationManager(self.resource_dir / "server16_py" / "locales", self.settings.language)
        self.log_backup_path = self.log_path.with_suffix(".previous.log")
        self._prepare_runtime_log()
        self.offsets = Offsets.load()
        self.memory = Memory()
        self.pagechange = False
        self.skillgamechange = False
        self.bumperpagechange = False
        self.matchstarted = False
        self.lastpagename = ""
        self.curstad = ""
        self.StadName = ""
        self.ScoreboardStadName = ""
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
        self._tvlogo_assignment_type = ""
        self._scoreboard_assignment_type = ""
        self._movie_assignment_type = ""
        self._stadium_assignment_type = ""
        self._overlay_scope_phase = False
        self._overlay_selected_scope: str | None = None
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
        self._entrance_sequence = 0
        self._overlay_f12_down = False
        self._overlay_up_down = False
        self._overlay_down_down = False
        self._overlay_left_down = False
        self._overlay_right_down = False
        self._overlay_escape_down = False
        self._overlay_pgup_down = False
        self._overlay_pgdn_down = False
        self._overlay_home_down = False
        self._overlay_end_down = False
        self._overlay_enter_down = False
        self._overlay_mouse_left_down = False
        self._overlay_mouse_wheel_steps = 0
        # Physical left-button state as captured by the WH_MOUSE_LL hook —
        # see _sync_rmlui_menu_mouse_feed for why this is preferred over
        # GetAsyncKeyState(VK_LBUTTON) polling while the menu is open.
        self._overlay_mouse_left_hook_down = False
        # Which hint bar the overlay menu should show — "keyboard" or
        # "gamepad", updated to whichever device was used most recently (see
        # _sync_d3d_menu_input / _sync_rmlui_menu_mouse_feed) and pushed to
        # the DLL via D3DOverlayInjector.set_input_mode().
        self._overlay_input_mode = "keyboard"
        self._overlay_mouse_last_pos: tuple[int, int] | None = None
        self._kit_home_prev_down = False
        self._kit_home_next_down = False
        self._kit_away_prev_down = False
        self._kit_away_next_down = False
        self._kit_type_cycle_down = False
        self._kit_hotkey_ready_at = 0.0
        self._kit_cycle_index: dict[tuple[str, str], int] = {}
        self._kit_cycle_task_running = False
        # F7-F10 (kit-cycle carousel) and F11 (kit-type change) notifications
        # now render as two independent, stackable panels (see CLAUDE.md's
        # kit-cycling carousel section) — each needs its own hide-timer job
        # so showing one doesn't cancel/steal the other's pending auto-hide.
        self._kit_carousel_hide_job = None
        self._kit_carousel_shown_at = 0.0
        self._kit_type_hide_job = None
        self._kit_type_shown_at = 0.0
        # (team_id, kittype_code, index) the kit-cycling carousel notification
        # is currently showing — a prefetched prev/next thumbnail only pushes
        # a live image update (see _kit_cycle_thumb in app_overlay.py) if this
        # still matches by the time it finishes rendering in the background.
        self._kit_carousel_ctx: tuple[str, str, int] | None = None
        # Last-seen menu_event_seq, so _handle_rmlui_menu_event only reacts to
        # a NEW click/scroll event rather than replaying the same one every
        # 80ms tick (see cgfs16_rmlui_menu.cpp's MenuEventListener).
        self._rmlui_menu_event_last_seq = 0
        self._overlay_dblclick_last_time = 0.0
        self._overlay_dblclick_last_index = -1
        self._overlay_blocked_key_down = set()
        self._mouse_hook = None
        self._mouse_hook_proc = None
        self._mouse_hook_thread: threading.Thread | None = None
        self._mouse_hook_thread_id = 0
        self._keyboard_hook = None
        self._keyboard_hook_proc = None
        self._overlay_b_close_pending = False
        self._overlay_toggle_ready_at = 0.0
        self._overlay_tab_ready_at = 0.0
        self._overlay_combo_latched = False
        self._overlay_gp_prev_buttons = 0
        self._overlay_gp_start_pressed_at = 0.0
        self._overlay_gp_back_pressed_at = 0.0
        self._overlay_gp_left_pressed_at = 0.0
        self._overlay_gp_right_pressed_at = 0.0
        self._overlay_gp_start_hold_latched = False
        # Gamepad Y on the Stadiums tab: tap toggles the filter bubble
        # (_toggle_stadium_filter_panel), a 0.6s hold clears the active
        # filter (_clear_stadium_filter) instead — same press/hold-latch
        # pattern as Start above, just resolved on release rather than open.
        self._overlay_gp_y_pressed_at = 0.0
        self._overlay_gp_y_hold_latched = False
        self._overlay_gp_rstick_repeat_at = 0.0
        self._overlay_gp_lstick_repeat_at = 0.0
        self._overlay_gp_lstick_prev_in_zone = False
        self._active_gamepad_index = 0
        self._overlay_tab_names = ["scoreboards", "stadiums", "movies", "tvlogos", "kits"]
        self._overlay_tab_index = 0
        self._overlay_wizard_phase: str | None = None
        self._overlay_wizard_stadium: str | None = None
        self._overlay_wizard_police: str | None = None
        self._overlay_wizard_pitch: str | None = None
        self._overlay_selected_kittype: str | None = None
        self._overlay_kit_sets_cache: list[dict | None] = []
        self._overlay_kit_preview_cache: dict[str, str] = {}
        self._overlay_kit_preview_pending: set[str] = set()
        self._overlay_list_header: str = ""
        # Stadiums-tab country filter panel (Y button) — see
        # _activate_filter_row / _update_menu_content in app_overlay.py.
        # Session-scoped by design: reset whenever the overlay opens/closes
        # or the tab changes, never persisted to settings.
        self._overlay_filter_phase = False
        self._overlay_stadium_country_filter: set[str] = set()
        self._overlay_stadium_sort_desc = False
        self._overlay_filter_rows: list[tuple[str, str]] = []
        self._d3d_menu_visible = False
        self._overlay_items: list[str] = []
        # Parallel to _overlay_items — True marks a row as "checked" (lit up
        # in the RmlUi row via .row-checked). Only populated meaningfully by
        # the Stadiums filter panel branch of _update_menu_content; all-False
        # for every other tab/phase.
        self._overlay_item_checked: list[bool] = []
        # Resolved row-thumbnail path per stadium name, for the Stadiums tab's
        # per-row image (Phase 3 visual redesign) — stadium names/preview
        # images are stable for the lifetime of a session, so this is a
        # plain unbounded dict, unlike the DLL's own bounded LRU texture
        # cache (which holds actual GPU textures, not path strings).
        self._overlay_stadium_thumb_cache: dict[str, str] = {}
        self._overlay_item_count     = 0
        self._overlay_selected_index = 0
        self._overlay_scroll_offset  = 0
        self._overlay_window_base    = 0
        self._overlay_visible_rows   = 20
        # Real Stadiums filter-grid column count, as reported by
        # cgfs16_rmlui_menu.cpp (see get_filter_grid_cols() /
        # menu_filter_grid_cols) — falls back to _FILTER_GRID_COLS_FALLBACK
        # in app_overlay.py until the menu has opened at least once this
        # session and RmlMenu_Sync has had a chance to compute a real value.
        self._overlay_filter_grid_cols = 0
        self._overlay_nav_ready_at   = 0.0
        self._overlay_nav_repeat_at  = 0.0
        self._fifa_hwnd = 0
        self._fifa_hwnd_checked_at = 0.0
        self._worker_queue: queue.Queue[tuple] = queue.Queue()
        self._worker_poll_job = None
        self._stadium_task_running = False
        self._stadium_task_signature = None
        self._stadium_task_request_key = None
        self._last_stadium_applied_signature = None
        self.labels = {}
        self.stat_title_labels = {}
        self.info_labels = {}
        self.module_vars = {}
        self.module_checks = {}
        self.module_states = {}
        self.log_widget = None
        self.logs_frame = None
        self.check_update_button = None
        self.locate_fifa_button = None
        self.launch_fifa_button = None
        self.assign_scoreboard_button = None
        self.assign_movie_button = None
        self.substitution_confirm_button = None
        self.exclude_competition_button = None
        self.log_status_label = None
        self.log_autofollow_checkbox = None
        self._log_autofollow_var: tk.BooleanVar | None = None
        self._log_filter_pointer_trace = False
        self._log_filter_pointer_trace_var: tk.BooleanVar | None = None
        self._log_filter_discord_rpc = False
        self._log_filter_discord_rpc_var: tk.BooleanVar | None = None
        self.log_follow_button = None
        self.language_label = None
        self.language_combo = None
        self.zoom_label = None
        self.zoom_value_label = None
        self.zoom_out_button = None
        self.zoom_in_button = None
        self.zoom_toggle_button = None
        self.zoom_restart_hint_label = None
        self._zoom_popup = None
        self.language_var = tk.StringVar(value=self.settings.language)
        self._log_autofollow = True
        self.ui_root = None
        self.tabview = None
        self.dashboard_tab = None
        self.logs_tab = None
        self.audio_tab = None
        self.camera_tab = None
        self.setup_tab = None
        self.kits_tab = None
        self._setup_canvas = None
        self._setup_canvas_body = None
        self._assets_canvas = None
        self._assets_canvas_body = None
        self._kits_canvas = None
        self._kits_canvas_body = None
        self._kitsimple_canvas = None
        self._kitsimple_canvas_body = None
        self._kits_sub_notebook = None
        self.kits_simple_subtab = None
        self.kits_advanced_subtab = None
        self._setup_status_vars: dict = {}
        self._setup_install_vars: dict = {}
        self._assets_extract_vars: dict = {}
        self.banner_title_label = None
        self.help_label = None
        self.page_banner = None
        self.progress_bar = None
        self.progress_text_label = None
        self.progress_value = None
        self.stadium_loading_modal = None
        self.stadium_loading_title = None
        self.stadium_loading_name = None
        self.stadium_loading_detail = None
        self.stadium_loading_value = None
        self.stadium_loading_bar = None
        self._stadium_loading_hwnd = 0
        self._stadium_loading_visible = False
        self._stadium_loading_restore_fullscreen = False
        self._d3d_injector = None
        self._d3d_overlay_shown_at = 0.0
        self._d3d_overlay_hide_job = None
        self._home_crest_png: str = ""
        self._away_crest_png: str = ""
        self._stadium_loading_hide_job = None
        self.status_pill = None
        self.dashboard_canvas = None
        self.dashboard_scrollbar = None
        self.dashboard_content = None
        self.dashboard_window_id = None
        self._audio_details: dict[str, str] = {}
        self._team_logo_labels: dict[str, tk.Label] = {}
        self._team_logo_images: dict[str, ImageTk.PhotoImage | None] = {}
        self._stadium_preview_label = None
        self._stadium_preview_image: ImageTk.PhotoImage | None = None
        self.stadium_loading_preview = None
        self._stadium_loading_image: ImageTk.PhotoImage | None = None
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
        self.camera_library_card = None
        self.camera_preview_card = None
        self.logs_group = None
        self.app_version = APP_VERSION
        self._update_check_in_progress = False
        self._update_checker = GithubReleaseChecker(self.UPDATE_REPO_OWNER, self.UPDATE_REPO_NAME)
        self.chants_thread_started = False
        self._chants_stop = threading.Event()
        self._chants_reset_requested = False
        self._chants_game_active = False
        self._chants_oneshot_stop = None
        self._chants_last_track = None
        self._chants_last_goal_time = 0.0
        self._chants_player: MciAudioPlayer | None = None
        self._chant_track_index = 0
        self._chants_paused = False
        self._chants_target_volume = 0.0
        self._last_score_snapshot = (0, 0)
        self._last_chants_score_snapshot: tuple[int, int] | None = None
        self._chants_resume_after = 0.0
        self._chants_rng = random.Random()
        self._entrance_active = False
        self._entrance_armed = False
        self._entrance_pre_match_guard = False
        self._last_live_score = (0, 0)
        self._last_live_update = ""
        self.assets_runtime = AssetRuntime(self)
        self.stadium_runtime = StadiumRuntime(self)
        self.chants_runtime = ChantsRuntime(self)
        self.entrance_runtime = TeamEntranceRuntime(self)
        self.movie_preview_runtime = MoviePreviewRuntime(self)
        self.assignment_runtime = AssignmentRuntime(self)
        self.camera_runtime = CameraRuntime(self)
        self.kit_mixer = KitMixRuntime(self)
        self.substitution_runtime = SubstitutionRuntime(self)
        discord_rpc_config = self.settings.data.get("discord_rpc", {})
        client_id = discord_rpc_config.get("client_id", "1495719449700077630")
        self.discord_rpc = DiscordRPCRuntime(client_id, logger=None)
        self._discord_rpc_enabled = discord_rpc_config.get("enabled", False)
        self._discord_rpc_last_presence = None
        _preview_provider = (discord_rpc_config.get("stadium_preview_provider", "discord_webhook") or "discord_webhook").strip().lower()
        _webhook_url = discord_rpc_config.get("stadium_preview_webhook", "")
        _imgur_client_id = (discord_rpc_config.get("stadium_preview_imgur_client_id", "") or "").strip()
        _imgbb_api_key = (discord_rpc_config.get("stadium_preview_imgbb_api_key", "") or "").strip()
        _uploader_enabled = (
            bool(_webhook_url)
            or (_preview_provider == "imgur" and bool(_imgur_client_id))
            or (_preview_provider == "imgbb" and bool(_imgbb_api_key))
        )
        self._stadium_preview_uploader: StadiumPreviewUploader | None = (
            StadiumPreviewUploader(
                _webhook_url,
                provider=_preview_provider,
                imgur_client_id=_imgur_client_id,
                imgbb_api_key=_imgbb_api_key,
            )
            if _uploader_enabled
            else None
        )
        if self._stadium_preview_uploader is not None:
            self._stadium_preview_uploader.add_upload_callback(self._on_stadium_preview_uploaded)
        if self._discord_rpc_enabled:
            self.discord_rpc.connect()
        self.team_db: FifaDatabase | None = None
        self._team_db_load_token = 0
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.user32.GetAsyncKeyState.argtypes = [wintypes.INT]
        self.user32.GetAsyncKeyState.restype = wintypes.SHORT
        self.user32.GetForegroundWindow.restype = wintypes.HWND
        self.user32.GetCursorPos.argtypes = [ctypes.POINTER(POINT)]
        self.user32.GetCursorPos.restype = wintypes.BOOL
        self.user32.ScreenToClient.argtypes = [wintypes.HWND, ctypes.POINTER(POINT)]
        self.user32.ScreenToClient.restype = wintypes.BOOL
        self.user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(POINT)]
        self.user32.ClientToScreen.restype = wintypes.BOOL
        self.user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(RECT)]
        self.user32.GetClientRect.restype = wintypes.BOOL
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
        self.user32.SetWindowsHookExW.argtypes = [ctypes.c_int, ctypes.c_void_p, wintypes.HINSTANCE, wintypes.DWORD]
        self.user32.SetWindowsHookExW.restype = ctypes.c_void_p
        self.user32.CallNextHookEx.argtypes = [ctypes.c_void_p, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
        self.user32.CallNextHookEx.restype = wintypes.LPARAM
        self.user32.UnhookWindowsHookEx.argtypes = [ctypes.c_void_p]
        self.user32.UnhookWindowsHookEx.restype = wintypes.BOOL
        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        self.kernel32.GetModuleHandleW.restype = wintypes.HMODULE
        self._xinput = self._load_xinput_dll()
        self._apply_window_icon(self)
        self._configure_theme()
        self._build_ui()
        self._install_exception_hook()
        self._build_stadium_loading_modal()
        self.setuppaths()
        self._update_setup_notice()
        self.refresh_camera_catalog()
        self.refresh_modules()
        self.log("Bootstrap file writes are deferred until an explicit runtime action")
        self.log("Application started")
        self._poll_job = self.after(500, self.poll_process)
        self._stats_job = self.after(250, self.stats_loop)
        self._overlay_job = self.after(80, self.overlay_loop)
        if self.module_enabled("Chants"):
            self._start_chants_runtime()
        if self._discord_rpc_enabled:
            self.log("DiscordRPC initialized (enabled in settings)")
        else:
            self.log("DiscordRPC initialized (disabled in settings)")

    # ── Core runtime orchestration ─────────────────────────────────────────────

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
            self.targetpath,
            self.TVLogo,
            self.ScoreBoard,
            self.Movies,
        ):
            checkdirs(path)
        extra_setup(self.Psource, self.Pdest, "4", "policeofficer", "4")
        extra_setup(self.Psource, self.Pdest, "9", "policeofficer", "9")
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
            if name == "DiscordRPC":
                var.set(self._discord_rpc_enabled)
            else:
                var.set(self.module_enabled(name))
        self._update_audio_overview()

    def toggle_module(self, module: str) -> None:
        if module in self.module_vars:
            self.module_vars[module].set(self.module_enabled(module))

    def _on_module_toggle(self, name: str, var: tk.BooleanVar) -> None:
        enabled = var.get()
        self.settings_ini.write(name, "1" if enabled else "0", "Modules")
        self.settings_ini.save()
        self.module_states[name] = enabled
        self.log(f"Module '{name}' {'enabled' if enabled else 'disabled'} by user")

    # ── Runtime delegation ─────────────────────────────────────────────────────

    def apply_all_runtime(self) -> None:
        self.log(f"Applying runtime HID={self.HID} AID={self.AID} TOUR={self.TOURNAME} ROUND={self.TOURROUNDID} STAD={self.STADID}")
        self._set_progress(5, "Applying runtime")
        if self.module_enabled("Stadium"):
            self.apply_stadium_runtime()
        else:
            self._set_display("stadium", "Stadium Module Disable")
            self.curstad = ""
            self.ScoreboardStadName = ""
            if self.stadium_runtime.has_assignment():
                self.assets_runtime._show_warning_toast(self.tr("notify.warn.stadium_off"), self.tr("notify.warn.assets_skipped"), icon="stadium")
        try:
            self.apply_scoreboard_runtime()
        except Exception as exc:
            self.log("Scoreboard runtime error", exc, exc_info=True)
        try:
            self.apply_movie_runtime()
        except Exception as exc:
            self.log("Movie runtime error", exc, exc_info=True)
        if not self._stadium_task_running:
            self._set_progress(100, "Runtime ready")

    def apply_stadium_runtime(self) -> None:
        self.stadium_runtime.apply_stadium_runtime()

    def _start_stadium_task(
        self,
        section_id: str,
        section_name: str,
        injid: str,
        stadium_signature: tuple,
        task_request_key: tuple[str, str, str],
        chosen_stadium: str | None = None,
    ) -> None:
        self.stadium_runtime.start_stadium_task(
            section_id, section_name, injid, stadium_signature, task_request_key, chosen_stadium=chosen_stadium,
        )

    def _run_stadium_copy_job(self, hid: str, section: str, injid: str, chosen_stadium: str | None = None) -> dict:
        return self.stadium_runtime.run_stadium_copy_job(hid, section, injid, chosen_stadium=chosen_stadium)

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

    def _start_team_entrance(self) -> bool:
        return self.entrance_runtime.start_for_match()

    def _reset_chants_state(self) -> None:
        self.entrance_runtime.reset()
        self.chants_runtime.reset_chants_state()

    def _fade_player(self, player: MciAudioPlayer, start: float, end: float, duration_ms: int) -> None:
        self.chants_runtime.fade_player(player, start, end, duration_ms)

    def _play_club_song_if_exists(self, team_id: str) -> None:
        self.chants_runtime._play_club_song(team_id)

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

    def apply_substitution_count(self, count: int, first_side_timeout_ms: int | None = None) -> None:
        if first_side_timeout_ms is None:
            self.substitution_runtime.apply_substitution_count(count)
        else:
            self.substitution_runtime.apply_substitution_count(count, first_side_timeout_ms)

    # ── Shutdown ───────────────────────────────────────────────────────────────

    def on_close(self) -> None:
        self._closing = True
        self._chants_stop.set()
        self._reset_chants_state()
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
            self._cancel_stadium_loading_hide()
        except Exception:
            pass
        try:
            self.substitution_runtime.cancel()
        except Exception:
            pass
        try:
            restore_stadium_names(self)
        except Exception:
            pass
        try:
            self.movie_preview_runtime.stop()
        except Exception:
            pass
        try:
            if self._d3d_injector is not None:
                self._d3d_injector.destroy()
        except Exception:
            pass
        try:
            self._uninstall_mouse_wheel_hook()
        except Exception:
            pass
        try:
            self._uninstall_keyboard_hook()
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
    # Per-monitor DPI awareness: without this, GetCursorPos()/ScreenToClient()
    # (used to feed mouse input to the RmlUi menu, e.g.
    # app_overlay.py's _sync_rmlui_menu_mouse_feed) return coordinates in this
    # process's own virtualized 96-DPI space rather than real screen pixels
    # whenever Windows display scaling isn't 100% — silently breaking mouse
    # hit-testing against FIFA's real (unscaled) window/backbuffer
    # coordinates without raising any error.
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
    except Exception:
        pass
    app = Server16App()
    app.mainloop()
