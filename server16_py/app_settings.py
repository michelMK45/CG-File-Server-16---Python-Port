from __future__ import annotations

import subprocess
import sys
import threading
from pathlib import Path
from tkinter import filedialog, messagebox

import psutil

from .dialogs import SectionPickerDialog
from .fifa_db import FifaDatabase
from .ini_file import SessionIniFile, export_sections
from .settings_editor import SettingsAreaEditor, asset_specs, audio_specs, stadium_specs


class SettingsMixin:
    """FIFA path setup, module management, and settings UI — part of Server16App via multiple inheritance."""

    def _set_progress(self, value: float, text: str) -> None:
        if self.progress_value is not None:
            self.progress_value.set(max(0, min(100, value)))
        if self.progress_text_label is not None:
            self.progress_text_label.configure(text=text)
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
            elif kind == "toast":
                _, title, body, duration_ms = event
                slot = self._show_toast_notification(title, body)
                if slot != -1:
                    self.after(duration_ms, lambda s=slot: self._hide_toast_notification(s))
            elif kind == "error":
                _, message = event
                short_message = str(message).splitlines()[0] if message else self.status_text("stadium_error")
                self._set_progress(100, short_message)
                self._stadium_task_running = False
                self._stadium_task_signature = None
                self._stadium_task_request_key = None
                self._set_process_status(self.status_text("stadium_error"), self.error)
                self._hide_stadium_loading_modal(delay_ms=5000)
                self.log(message)
            elif kind == "kit_cycled":
                _, side, team_id, tourn_id, result, png_path = event
                self._kit_cycle_task_running = False
                self._show_kit_hotkey_notification(side, team_id, tourn_id, result, png_path)
            elif kind == "kit_cycle_error":
                _, side, team_id, message = event
                self._kit_cycle_task_running = False
                self.log(f"Kit hotkey: failed to cycle kit for team {team_id} ({side}): {message}")
        if self._stadium_task_running or self._kit_cycle_task_running or not self._worker_queue.empty():
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
        if not self.settings_ini.path.exists() and self.fifaEXE != "default":
            import shutil as _shutil
            src_ini = self.resource_dir / "install_data" / "FSW" / "settings.ini"
            if src_ini.exists():
                self.settings_ini.path.parent.mkdir(parents=True, exist_ok=True)
                _shutil.copy2(str(src_ini), str(self.settings_ini.path))
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
        module_names = ["Stadium", "TvLogo", "ScoreBoard", "Movies", "Autorun", "StadiumNet", "Chants", "StadiumName", "AwayChants", "AwayClubSong"]
        self.module_states = {name: self.settings_ini.read(name, "Modules") == "1" for name in module_names}
        previous_rpc_state = self._discord_rpc_enabled
        discord_ini_value = self.settings_ini.read("DiscordRPC", "Modules")
        if discord_ini_value in {"0", "1"}:
            self._discord_rpc_enabled = discord_ini_value == "1"
        else:
            # Avoid creating FSW/settings.ini on first app start when FIFA is not linked yet.
            if self.fifaEXE != "default" or self.settings_ini.path.exists():
                self.settings_ini.write("DiscordRPC", "1" if self._discord_rpc_enabled else "0", "Modules")
                self.settings_ini.save()
        self.module_states["DiscordRPC"] = self._discord_rpc_enabled
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

        discord_var = self.module_vars.get("DiscordRPC")
        if discord_var is not None:
            discord_var.set(self._discord_rpc_enabled)

    def module_enabled(self, name: str) -> bool:
        if name == "DiscordRPC":
            return self._discord_rpc_enabled
        if not hasattr(self, "settings_ini") or self.settings_ini is None:
            return self.module_states.get(name, False)
        enabled = self.settings_ini.read(name, "Modules") == "1"
        self.module_states[name] = enabled
        return enabled

    def _open_settings_editor(self, editor_key: str, title: str, specs, initial_section: str | None = None) -> None:
        self.prepare_floating_window()
        existing = self._settings_editors.get(editor_key)
        if existing is not None and existing.winfo_exists():
            existing.deiconify()
            existing.lift()
            existing.focus_force()
            existing._refresh_active_frame()
            return
        editor = SettingsAreaEditor(self, self.tr(title), specs, initial_section=initial_section)
        self._settings_editors[editor_key] = editor
        editor.bind("<Destroy>", lambda _event, key=editor_key: self._settings_editors.pop(key, None))

    def open_stadium_settings_editor(self) -> None:
        self._open_settings_editor("stadium", "dialog.editor.section.stadium_settings", stadium_specs())

    def open_assets_settings_editor(self) -> None:
        self._open_settings_editor("assets", "dialog.editor.section.asset_settings", asset_specs())

    def open_audio_settings_editor(self) -> None:
        self._open_settings_editor("audio", "dialog.editor.section.chants_settings", audio_specs())

    def open_export_settings_dialog(self) -> None:
        self.prepare_floating_window()
        self.settings_ini.reload()
        sections = self.settings_ini.sections()
        if not sections:
            messagebox.showinfo(self.tr("message.settings_io"), self.tr("message.settings_io.no_sections"))
            return
        section_counts = {section: len(self.settings_ini.items(section)) for section in sections}
        dialog = SectionPickerDialog(
            self,
            "dialog.settings_io.export_title",
            "dialog.settings_io.export_subtitle",
            sections,
            section_counts,
            "button.export",
        )
        self.wait_window(dialog)
        if not dialog.result:
            return
        selected_sections = dialog.result
        dest = filedialog.asksaveasfilename(
            title=self.tr("filedialog.export_settings"),
            defaultextension=".ini",
            filetypes=[("INI files", "*.ini"), ("All files", "*.*")],
        )
        if not dest:
            return
        try:
            count = export_sections(self.settings_ini, selected_sections, Path(dest))
        except Exception as exc:
            self.log("Failed to export settings sections", exc)
            messagebox.showerror(self.tr("message.settings_io"), self.tr("message.settings_io.export_failed", error=exc))
            return
        self.log(f"Exported settings sections {selected_sections} ({count} keys) to {dest}")
        messagebox.showinfo(
            self.tr("message.settings_io"),
            self.tr("message.settings_io.export_done", count=count, sections=len(selected_sections), path=dest),
        )

    def open_import_settings_dialog(self) -> None:
        self.prepare_floating_window()
        source = filedialog.askopenfilename(
            title=self.tr("filedialog.import_settings"),
            filetypes=[("INI files", "*.ini"), ("All files", "*.*")],
        )
        if not source:
            return
        try:
            imported = SessionIniFile(Path(source))
        except Exception as exc:
            self.log("Failed to read settings file for import", exc)
            messagebox.showerror(self.tr("message.settings_io"), self.tr("message.settings_io.invalid_file", error=exc))
            return
        sections = imported.sections()
        if not sections:
            messagebox.showwarning(self.tr("message.settings_io"), self.tr("message.settings_io.no_sections_found"))
            return
        section_counts = {section: len(imported.items(section)) for section in sections}
        dialog = SectionPickerDialog(
            self,
            "dialog.settings_io.import_title",
            "dialog.settings_io.import_subtitle",
            sections,
            section_counts,
            "button.import",
        )
        self.wait_window(dialog)
        if not dialog.result:
            return
        selected_sections = dialog.result

        self.settings_ini.reload()
        conflicts: list[tuple[str, str, str, str]] = []
        additions = 0
        for section in selected_sections:
            existing = self.settings_ini.as_dict(section)
            for key, value in imported.items(section):
                if key in existing and existing[key] != value:
                    conflicts.append((section, key, existing[key], value))
                elif key not in existing:
                    additions += 1

        if conflicts:
            preview_lines = [f"[{section}] {key}: {old} -> {new}" for section, key, old, new in conflicts[:15]]
            if len(conflicts) > 15:
                preview_lines.append(f"... (+{len(conflicts) - 15})")
            proceed = messagebox.askyesno(
                self.tr("message.settings_io"),
                self.tr("message.settings_io.conflicts_confirm", count=len(conflicts), preview="\n".join(preview_lines)),
            )
            if not proceed:
                self.log("Settings import cancelled by user due to key conflicts")
                return

        for section in selected_sections:
            for key, value in imported.items(section):
                self.settings_ini.write(key, value, section)
        self.settings_ini.save()
        self._load_module_states()
        try:
            self.refresh_modules()
            self.apply_all_runtime()
        except Exception as exc:
            self.log("Failed to apply runtime after settings import", exc)

        self.log(f"Imported settings sections {selected_sections} from {source} ({additions} new, {len(conflicts)} overwritten)")
        messagebox.showinfo(
            self.tr("message.settings_io"),
            self.tr("message.settings_io.import_done", added=additions, overwritten=len(conflicts), sections=len(selected_sections)),
        )

    def select_fifa_exe(self) -> None:
        filename = filedialog.askopenfilename(filetypes=[("Executable", "*.exe")], title=self.tr("filedialog.select_fifa_exe"))
        if not filename:
            return
        window = self._window()
        window.configure(cursor="watch")
        window.update_idletasks()
        try:
            self._set_process_status(self.status_text("loading_fifa_data"), self.accent)
            self._set_progress(8, self.progress_text("saving_executable"))
            self.settings.fifa_exe = filename
            self._set_progress(24, self.progress_text("configuring_paths"))
            self.setuppaths(load_team_database=False)
            self._load_team_database(lambda value, text: self._set_progress(value, text))
            self._set_progress(82, self.progress_text("applying_bootstrap"))
            self.apply_bootstrap_files()
            if getattr(self, "_setup_status_vars", None):
                self.refresh_setup_tab()
            self._set_progress(94, self.progress_text("refreshing_modules"))
            self.refresh_modules()
            self._set_progress(100, self.progress_text("fifa_data_ready"))
            self._set_process_status(self.status_text("fifa_ready"), self.success)
            self.log(f"Selected FIFA executable: {filename}")
        except Exception as exc:
            self._set_process_status(self.status_text("fifa_load_error"), self.error)
            self.log("Failed while loading FIFA data after selecting executable", exc, exc_info=sys.exc_info())
            messagebox.showerror(self.tr("message.fifa16"), self.tr("message.error.load_fifa_data"))
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
        if not self.fifaEXE or self.fifaEXE == "default":
            self._team_db_load_token += 1
            self.team_db = None
            self.discord_rpc.set_team_name_resolver(None)
            if progress_callback is not None:
                progress_callback(0, "Team database idle")
            else:
                self._set_progress(0, "Team database idle")
            return

        def _report_progress(value: float, text: str) -> None:
            if progress_callback is not None:
                progress_callback(value, text)
            else:
                self._set_progress(value, text)

        self._team_db_load_token += 1
        load_token = self._team_db_load_token
        fifa_root = Path(self.fifaEXE).parent
        self.team_db = None
        self.discord_rpc.set_team_name_resolver(None)
        self._set_process_status("Loading Team DB", self.gold)
        _report_progress(10, self.progress_text("connecting_database"))

        def _apply_success(db: FifaDatabase, team_count: int) -> None:
            if load_token != self._team_db_load_token or self._closing:
                return
            self.team_db = db
            self.discord_rpc.set_team_name_resolver(self.team_db.get_team_name)
            self.log(f" Team database loaded for {fifa_root.name} ({team_count} teams)")
            _report_progress(100, f"{self.progress_text('database_ready')} ({team_count} teams)")
            if not self.memory.is_open():
                self._set_process_status(self.status_text("waiting_fifa"), self.accent)

        def _apply_failure(reason: str) -> None:
            if load_token != self._team_db_load_token or self._closing:
                return
            self.team_db = None
            self.log(f"️  Could not connect to team database: {reason}")
            _report_progress(0, self.progress_text("database_unavailable"))
            if not self.memory.is_open():
                self._set_process_status(self.status_text("waiting_fifa"), self.accent)

        def _apply_error(message: str) -> None:
            if load_token != self._team_db_load_token or self._closing:
                return
            self.team_db = None
            self.log(f"❌ Error loading team database: {message}")
            _report_progress(0, self.progress_text("database_failed"))
            if not self.memory.is_open():
                self._set_process_status(self.status_text("waiting_fifa"), self.accent)

        def _worker() -> None:
            try:
                db = FifaDatabase(fifa_root)
                self.after(0, lambda: _report_progress(40, self.progress_text("connecting_database")))
                if not db.connect():
                    reason = db.last_error or "unknown reason"
                    self.after(0, lambda: _apply_failure(reason))
                    return
                self.after(0, lambda: _report_progress(80, self.progress_text("loading_teams")))
                team_count = db.load_all_teams()
                self.after(0, lambda: _apply_success(db, team_count))
            except Exception as exc:
                self.after(0, lambda: _apply_error(str(exc)))

        threading.Thread(target=_worker, daemon=True).start()

    def _resolve_team_name(self, team_id: str) -> str | None:
        if not team_id or team_id in {"-", "0"} or self.team_db is None:
            return None
        try:
            return self.team_db.get_team_name(team_id)
        except Exception:
            return None

    def _resolve_stadium_name(self, stadium_id: str) -> str | None:
        if not stadium_id or stadium_id in {"-", "0"} or self.team_db is None:
            return None
        try:
            return self.team_db.get_stadium_name(stadium_id)
        except Exception:
            return None

    def _has_active_custom_stadium_assignment(self) -> bool:
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

    def launch_fifa(self) -> None:
        if self.fifaEXE == "default":
            messagebox.showwarning(self.tr("message.fifa16"), self.tr("message.warning.select_fifa_first"))
            return
        self.setuppaths()
        self.apply_bootstrap_files()
        if getattr(self, "_setup_status_vars", None):
            self.refresh_setup_tab()
        self.refresh_modules()
        if self._is_target_process_running():
            self.log(f"FIFA process already running: {self.fifaEXE}")
            return
        subprocess.Popen([self.fifaEXE], shell=False)
        self.log(f"Launched FIFA executable: {self.fifaEXE}")
