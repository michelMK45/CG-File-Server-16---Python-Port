from __future__ import annotations

import sys
import time
from datetime import datetime
from pathlib import Path

import psutil
import tkinter as tk

from .memory_access import Memory, MemoryAccessError
from .substitution_runtime import POLL_TIMEOUT_SECOND_SIDE_MS


class GameMixin:
    """Game process polling, live context reading, and stats loop — part of Server16App via multiple inheritance."""

    def poll_process(self) -> None:
        if self._closing:
            return
        try:
            if not self.offsets.is_configured():
                self._sync_page_banner("Offsets nao configurados na classe Offsets")
                self._set_process_status(self.status_text("offsets_missing"), self.error)
                self.log("Offsets are not configured")
                self._poll_job = self.after(500, self.poll_process)
                return
            running = bool(self.MP) and any(Path((p.info.get("name") or "")).stem.lower() == self.MP.lower() for p in psutil.process_iter(["name"]))
            if running and self.memory.attack(self.MP):
                if not self._attached_once:
                    self._attached_once = True
                    self._show_attach_notification()
                self._set_process_status(self.status_text("fifa_attached"), self.success)
                self.update_page_name()
            else:
                self._sync_page_banner("Process not running")
                self._set_process_status(self.status_text("waiting_fifa"), self.accent)
                if self._attached_once:
                    if self.keep_open_var.get():
                        self.log("Game process ended; keeping server open")
                        self.memory.close()
                        self._attached_once = False
                        self._reset_chants_state()
                    else:
                        self.log("Game process ended; closing server automatically")
                        self.on_close()
                        return
                self._reset_chants_state()
        except Exception as exc:
            self._sync_page_banner(f"Polling error: {exc}")
            self._set_process_status(self.status_text("polling_error"), self.error)
            self.log("Polling error", exc, exc_info=sys.exc_info())
        if not self._closing:
            self._poll_job = self.after(500, self.poll_process)

    def _show_attach_notification(self) -> None:
        try:
            slot = self._show_toast_notification(
                self.tr("notify.fifa_attached"),
                self.tr("notify.fifa_attached_detail"),
            )
            if slot == -1:
                return
            self.after(11000, lambda: self._hide_toast_notification(slot))
        except Exception as exc:
            self.log("Attach notification error", exc, exc_info=sys.exc_info())

    def stats_loop(self) -> None:
        if self._closing:
            return
        try:
            if self.memory.is_open():
                page_name = self.labels["page"].cget("text") if "page" in self.labels else self.lastpagename
                self._update_live_match_stats(page_name)
                # Only refresh context when HID/AID are missing or context was
                # never captured. Once we have both IDs, avoid calling
                # refresh_live_context from the stats loop — it would re-trigger
                # apply_all_runtime and re-roll the random stadium every 250ms.
                missing_ids = not self.HID or not self.AID
                no_signature = self._last_runtime_signature is None
                if (missing_ids or no_signature) and self._page_can_have_match_context(page_name):
                    self.refresh_live_context(page_name)
            # Update DiscordRPC presence
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
            self._set_process_status(self.status_text("reading_page"), self.gold)
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
            self.substitution_runtime.reset_for_new_match()
            if self.settings.auto_apply_substitution_count:
                # KickOffHub is reached well before kickoff (menus, formation, etc.), so the
                # FIRST side's own first substitution could be a long way off — use the same
                # generous window normally reserved for the second side, rather than the short
                # timeout meant for a manual Confirm click made shortly before subbing.
                self.log(f"Auto-applying substitution count ({self.settings.substitution_count}) for new match")
                self.apply_substitution_count(self.settings.substitution_count, first_side_timeout_ms=POLL_TIMEOUT_SECOND_SIDE_MS)
            self._kickoff_retry_remaining = 12
            self._schedule_kickoff_retry()
            # Stop any audio still playing from the previous match
            self._reset_chants_state()
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
                # Patch the match string in memory now that the bumper is loading
                # — this is the last moment before FIFA renders the stadium name
                if self.curstad:
                    if self.settings_ini.key_exists(self.curstad, "scoreboardstdname"):
                        raw = self.settings_ini.read(self.curstad, "scoreboardstdname")
                        std_name = raw.split(",")[0].strip() or self.curstad
                    else:
                        std_name = self.curstad
                    from .match_string_patcher import patch_match_string
                    patch_match_string(self, std_name)
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
        self.StadName = ""
        self._last_runtime_signature = None
        self._last_live_score = (0, 0)
        self._last_score_snapshot = (0, 0)
        self._last_chants_score_snapshot = None
        self._chants_resume_after = 0.0
        self._chants_last_track = None
        self._chants_last_goal_time = 0.0
        self._last_live_update = ""
        self._set_display("hid", "-")
        self._set_display("aid", "-")
        self._set_display("tour", "-")
        self._set_display("round", "-")
        self._set_display("derby", "-")
        self._set_display("stadid", "-")
        self._set_display("stadium", "-")
        self._set_display("home_name", self.tr("team.a"))
        self._set_display("away_name", self.tr("team.b"))
        self._update_team_logo("home", "")
        self._update_team_logo("away", "")
        self._set_display("score", "0 x 0")
        self._set_display("timer", "00:00")
        self._set_display("home_goals", "0")
        self._set_display("away_goals", "0")
        self._set_display("match_clock_split", "00 / 00")
        self._set_display("game_state", self.display_value("idle"))
        self._set_display("goal_active", self.display_value("no"))
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
        self._set_display("home_name", home_name or (f"{self.tr('team.a')} ({self.HID})" if self.HID else self.tr("team.a")))
        self._set_display("away_name", away_name or (f"{self.tr('team.b')} ({self.AID})" if self.AID else self.tr("team.b")))
        self._update_live_match_stats(page_name)
        # STADID is intentionally excluded from the signature: it reflects the
        # stadium currently loaded in FIFA memory and fluctuates while the game
        # boots, which would otherwise re-trigger apply_all_runtime on every
        # memory read and cause the random stadium to keep re-rolling.
        signature = (self.HID, self.AID, self.TOURNAME, self.TOURROUNDID)
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
            game_state = self.display_value("running")
        elif self.matchstarted or self._chants_paused:
            game_state = self.display_value("paused")
        else:
            game_state = self.display_value("idle")
        self._set_display("game_state", game_state)
        self._set_display("goal_active", self.display_value("yes") if goal_active else self.display_value("no"))
        self._last_live_update = datetime.now().strftime("%H:%M:%S")
        self._set_display("last_update", self._last_live_update)
        if "TV/bumper" in page_name:
            self._set_display("audio_last_action", self.display_value("tv_bumper_active"))

    def _on_stadium_preview_uploaded(self, stadium_name: str, url: str) -> None:
        self.log(f"Discord stadium preview uploaded: {stadium_name} -> {url}")
        self._discord_rpc_last_presence = None

    def _update_discord_presence(self) -> None:
        if not self._discord_rpc_enabled:
            return

        try:
            if not self.discord_rpc.is_connected():
                self.discord_rpc.connect()

            page_name = self.labels.get("page", tk.Label()).cget("text") if "page" in self.labels else self.lastpagename

            score_home = self.labels.get("home_goals", tk.Label()).cget("text") if "home_goals" in self.labels else "0"
            score_away = self.labels.get("away_goals", tk.Label()).cget("text") if "away_goals" in self.labels else "0"
            match_time = "00:00"
            raw_time = self._try_read_optional_int(self.offsets.GAMESTATSBASE, self.offsets.GAMERANTIME)
            if raw_time is not None:
                total_seconds = raw_time // 100 if raw_time > 6000 else raw_time
                minutes, seconds = divmod(max(0, total_seconds), 60)
                match_time = f"{minutes:02d}:{seconds:02d}"
            elif "timer" in self.labels:
                match_time = self.labels.get("timer", tk.Label()).cget("text")
            game_state = self.labels.get("game_state", tk.Label()).cget("text") if "game_state" in self.labels else "Idle"
            pause_menu_tokens = ("fluxhub", "stadiumpan")
            if any(token in (page_name or "").lower() for token in pause_menu_tokens):
                game_state = "paused"
            custom_stadium_display = ""
            if self._has_active_custom_stadium_assignment():
                custom_stadium_display = (
                    self.ScoreboardStadName
                    or self.curstad
                    or getattr(self, "StadName", "")
                )
            stadium_display = custom_stadium_display or self._resolve_stadium_name(self.STADID) or ""

            stadium_image_url: str | None = None
            if self._stadium_preview_uploader is not None:
                candidate_names = []
                for name in [self.curstad, custom_stadium_display, stadium_display]:
                    norm = (name or "").strip()
                    if norm and norm not in candidate_names:
                        candidate_names.append(norm)

                resolved_name = ""
                preview_path = None
                for candidate_name in candidate_names:
                    preview_path = self._resolve_stadium_preview_path(candidate_name)
                    if preview_path is not None:
                        resolved_name = candidate_name
                        break

                if preview_path is not None and resolved_name:
                    cached = self._stadium_preview_uploader.get_cached_url(resolved_name)
                    if cached:
                        stadium_image_url = cached
                    else:
                        self._stadium_preview_uploader.get_or_upload(resolved_name, preview_path)

            discord_rpc_config = self.settings.data.get("discord_rpc", {})
            stadium_preview_mode = discord_rpc_config.get("stadium_preview_mode", "button_fallback")
            stadium_preview_override_url = (discord_rpc_config.get("stadium_preview_override_url", "") or "").strip()
            if stadium_preview_override_url:
                stadium_image_url = stadium_preview_override_url

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
                stadium_image_url=stadium_image_url,
                external_image_mode=stadium_preview_mode,
            )

            if presence != self._discord_rpc_last_presence:
                sent = self.discord_rpc.update_presence(**presence)
                self._discord_rpc_last_presence = presence
                self.log(f"DiscordRPC updated: {presence.get('state', 'N/A')}")
                self.log(f"DiscordRPC image key: {presence.get('large_image', '')}")
                self.log(f"DiscordRPC external image mode: {stadium_preview_mode}")
                if stadium_preview_override_url:
                    self.log(f"DiscordRPC external image override URL: {stadium_preview_override_url}")
                if sent:
                    self.log("DiscordRPC update_presence result: ok")
                else:
                    self.log("DiscordRPC update_presence result: failed")
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
