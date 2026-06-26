from __future__ import annotations

from .localization import LANGUAGE_LABELS, SUPPORTED_LANGUAGES


class LocalizationMixin:
    """Language switching and text translation — part of Server16App via multiple inheritance."""

    def tr(self, key: str, **kwargs) -> str:
        return self.localization.translate(key, **kwargs)

    def display_value(self, key: str, fallback: str | None = None, **kwargs) -> str:
        text = self.tr(f"display.{key}", **kwargs)
        if text == f"display.{key}" and fallback is not None:
            return fallback.format(**kwargs) if kwargs else fallback
        return text

    def progress_text(self, key: str, **kwargs) -> str:
        return self.tr(f"progress.{key}", **kwargs)

    def status_text(self, key: str, **kwargs) -> str:
        return self.tr(f"status.{key}", **kwargs)

    def _language_combo_values(self) -> list[str]:
        return [f"{code.upper()} - {LANGUAGE_LABELS[code]}" for code in SUPPORTED_LANGUAGES]

    def _language_combo_value(self, language: str | None = None) -> str:
        code = (language or self.localization.language).strip().lower()
        return f"{code.upper()} - {LANGUAGE_LABELS.get(code, LANGUAGE_LABELS['en'])}"

    def _selected_language_code(self) -> str:
        raw = (self.language_var.get() or "").split(" - ", 1)[0].strip().lower()
        return raw if raw in SUPPORTED_LANGUAGES else "en"

    def _on_language_selected(self, _event=None) -> None:
        self._set_language(self._selected_language_code())

    def _set_language(self, language: str) -> None:
        normalized = self.localization.set_language(language)
        if self.settings.language != normalized:
            self.settings.language = normalized
        self.language_var.set(self._language_combo_value(normalized))
        self._apply_main_localization()

    def _apply_main_localization(self) -> None:
        window = self._window()
        try:
            window.title(self.tr("app.title"))
        except Exception:
            pass
        if self.locate_fifa_button is not None:
            self.locate_fifa_button.configure(text=self.tr("button.locate_fifa_exe"))
        if self.launch_fifa_button is not None:
            self.launch_fifa_button.configure(text=self.tr("button.launch_fifa"))
        if self.assign_scoreboard_button is not None:
            self.assign_scoreboard_button.configure(text=self.tr("button.assign_scoreboard"))
        if self.assign_movie_button is not None:
            self.assign_movie_button.configure(text=self.tr("button.assign_movie"))
        if self.exclude_competition_button is not None:
            self.exclude_competition_button.configure(text=self.tr("button.exclude_competition"))
        if self.check_update_button is not None:
            self.check_update_button.configure(text=self._check_update_button_text())
        if self.language_label is not None:
            self.language_label.configure(text=self.tr("label.language"))
        if self.language_combo is not None:
            self.language_combo.configure(values=self._language_combo_values())
        if self.banner_title_label is not None:
            self.banner_title_label.configure(text=self.tr("banner.control_room"))
        if self.help_label is not None:
            self.help_label.configure(text=self.tr("help.overlay_toggle"))
        if self.tabview is not None:
            self.tabview.tab(self.dashboard_tab, text=self.tr("tab.dashboard"))
            self.tabview.tab(self.audio_tab, text=self.tr("tab.chants"))
            self.tabview.tab(self.camera_tab, text=self.tr("tab.camera"))
            self.tabview.tab(self.logs_tab, text=self.tr("tab.logs"))
        if self.logs_group is not None:
            self.logs_group.configure(text=self.tr("logs.group"))
        if self.log_follow_button is not None:
            self.log_follow_button.configure(text=self.tr("button.jump_latest"))
        self._update_log_follow_ui()
        self._apply_stat_titles()
        self._apply_module_labels()
        self._apply_camera_localization()
        self._refresh_card_titles()
        self._apply_setup_notice_localization()

    def _refresh_card_titles(self) -> None:
        if hasattr(self, "_card_title_bindings"):
            for title_label, title_key, subtitle_label, subtitle_key in self._card_title_bindings:
                if title_label.winfo_exists():
                    title_label.configure(text=self.tr(title_key))
                if subtitle_label is not None and subtitle_label.winfo_exists():
                    subtitle_label.configure(text=self.tr(subtitle_key))

    def _apply_stat_titles(self) -> None:
        title_map = {
            "tour": "stat.tournament",
            "round": "stat.round_id",
            "page": "stat.current_page",
            "derby": "stat.derby_key",
            "match_clock_split": "stat.minute_second",
            "game_state": "stat.game_state",
            "goal_active": "stat.goal_status",
            "last_update": "stat.last_update",
            "tvlogo": "stat.tv_logo",
            "scoreboard": "stat.scoreboard",
            "movie": "stat.movie",
            "status": "stat.status",
            "stadium": "stat.current_stadium",
            "stadid": "stat.stadium_id",
            "audio_module": "stat.chants_module",
            "audio_status": "stat.chants_status",
            "audio_current": "stat.current_chant",
            "audio_clubsong": "stat.club_anthem",
            "audio_chants_dir": "stat.chants_folder",
            "audio_last_action": "stat.last_action",
            "audio_crowd_mode": "stat.crowd_mode",
            "audio_crowd_volume": "stat.crowd_volume",
            "audio_source": "stat.crowd_source",
            "audio_next": "stat.next_behavior",
            "home_goals": "stat.home_goals",
            "away_goals": "stat.away_goals",
        }
        for key, label in self.stat_title_labels.items():
            label.configure(text=self.tr(title_map.get(key, key)))

    def _apply_module_labels(self) -> None:
        module_map = {
            "Stadium": "module.stadium",
            "TvLogo": "module.tvlogo",
            "ScoreBoard": "module.scoreboard",
            "Movies": "module.movies",
            "Autorun": "module.autorun",
            "StadiumNet": "module.stadiumnet",
            "Chants": "module.chants",
            "DiscordRPC": "module.discord_rpc",
        }
        for name, check in self.module_checks.items():
            check.configure(text=self.tr(module_map.get(name, name)))

    def _apply_camera_localization(self) -> None:
        if self.camera_select_button is not None:
            self.camera_select_button.configure(text=self.tr("button.choose_camera_package"))
        if self.camera_apply_button is not None:
            self.camera_apply_button.configure(text=self.tr("button.apply_camera"))
        if self.camera_name_label is not None and self._camera_selected_name is None:
            self.camera_name_label.configure(text=self.tr("camera.no_camera_selected"))
        if self.camera_preview_status is not None and not self._camera_preview_source_key:
            self.camera_preview_status.configure(text=self.tr("camera.no_preview"))
        if self.camera_preview_image_label is not None and not getattr(self.camera_preview_image_label, "image", None):
            self.camera_preview_image_label.configure(text=self.tr("placeholder.preview"))
        if hasattr(self, "settings_ini"):
            self.refresh_camera_catalog()

    def _apply_setup_notice_localization(self) -> None:
        title_lbl = getattr(self, "_setup_notice_title", None)
        if title_lbl is not None and title_lbl.winfo_exists():
            title_lbl.configure(text=self.tr("setup_notice.title"))
        desc_lbl = getattr(self, "_setup_notice_desc", None)
        if desc_lbl is not None and desc_lbl.winfo_exists():
            desc_lbl.configure(text=self.tr("setup_notice.description"))
        btn = getattr(self, "_setup_notice_btn", None)
        if btn is not None and btn.winfo_exists():
            btn.configure(text=self.tr("setup_notice.go_setup"))
        for key, lbl in getattr(self, "_setup_notice_step_labels", []):
            if lbl.winfo_exists():
                lbl.configure(text=self.tr(key))
