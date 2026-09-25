from __future__ import annotations

import sys
import time
from datetime import datetime
from pathlib import Path

import psutil
import tkinter as tk

from .memory_access import Memory, MemoryAccessError
from .substitution_runtime import POLL_TIMEOUT_SECOND_SIDE_MS

# How long, in wall-clock seconds after the "TV/bumper" transition, to keep
# re-requesting StadiumDbNamePatchCoordinator every ~900ms. See
# _schedule_db_name_patch_retry's docstring for why this must be a time
# budget, not a fixed tick count -- one real scan attempt can take 1.5-2.5s+,
# so a short window can run out of wall-clock time well before the
# coordinator's own MAX_SCAN_ATTEMPTS is reached.
DB_NAME_PATCH_RETRY_WINDOW_SECONDS = 60.0

# Reported live 2026-09-14: the "Applying scoreboard name..." loading bar can
# stay on screen for the full 60s window above regardless of whether the
# match has already kicked off -- the retry chain is only ever stopped by a
# confirmed patch or the wall-clock deadline, never by the pre-match
# presentation screen itself having already come and gone. Once real
# gameplay is running the screen this patch targets is no longer even
# visible, so continuing to show a loading notification over live play (for
# up to a minute) is just noise, not a useful "still working" signal.
# Mirrors the exact kick-off heuristic already proven live elsewhere in this
# codebase (ChantsRuntime._play_goal_track, TeamEntranceRuntime's own
# kick-off detection, CLAUDE.md §5.5): sustained match-clock movement
# (timer delta >= 1 at >= 6x real-time speed, 3 consecutive ~900ms-spaced
# hits) rather than trusting GAMESTARTEDBINARY/matchstarted alone, which can
# read true well before kick-off (confirmed live -- "matchstarted=True" logs
# within ~6s of the bumper starting, long before the pre-match screen with
# the stadium name has even finished showing).
DB_NAME_PATCH_KICKOFF_SPEED_THRESHOLD = 6.0
DB_NAME_PATCH_KICKOFF_HITS_REQUIRED = 3
# Same 6s grace period ChantsRuntime uses before trusting clock-speed reads
# at all -- the pre-match presentation/walkout can itself show brief, non-
# representative clock jitter right after the bumper starts.
DB_NAME_PATCH_KICKOFF_PROTECTION_SECONDS = 6.0


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
        # Kept deliberately lightweight (real transitions only, thanks to the
        # dedupe above) — this is the trail needed to diagnose why a given
        # page path did or didn't arm/start Team Entrance (see CLAUDE.md §7,
        # "entrance anthem does not restart when the match is restarted").
        self.log(f"Page transition: {page_name!r} (entrance_armed={self._entrance_armed} matchstarted={self.matchstarted})")
        # Safety net for the manual stadium picker (see _open_stadium_picker
        # in stadium_runtime.py): it only ever opens while sitting at
        # KickOffHub, so the first genuine transition away from it — the
        # player backing out, switching teams, or the match progressing
        # toward TV/bumper — means it's never coming back for this session.
        # Force-resolve to random rather than leaving the match without a
        # stadium because nobody ever clicked the popup. Same page-name-
        # driven "the only available signal can't distinguish two
        # situations" safety-net pattern as the Team Entrance saga (CLAUDE.md
        # §7) — deliberately checked before any early return below so it
        # fires no matter what the new page turns out to be.
        # stadium_picker_awaiting_selection(), not _stadium_picker_pending:
        # pending stays True after a resolution until apply_stadium_runtime
        # consumes it, and _resolve_stadium_picker is a no-op once resolved —
        # so the raw flag logged "abandoned" on EVERY later transition while
        # actually abandoning nothing (2026-09-25 log: nine of them in 40s).
        if self.stadium_picker_awaiting_selection() and page_name != "game/screens/playNow/KickOffHub":
            self.log(f"Stadium picker abandoned (left KickOffHub for {page_name!r}); falling back to random")
            self._resolve_stadium_picker(None)
        if self._page_blocks_team_entrance(page_name):
            # `self.matchstarted` is normally only flipped False by
            # ChantsRuntime's own poll loop, after 3 consecutive 0.5s-spaced
            # memory reads report the match not running -- up to ~1.5s of
            # lag behind the page transition that actually caused it. A
            # Restart chosen quickly after opening the pause menu can reach
            # a fresh blank/walkout page before that lag clears, so the
            # blank-page arm fallback below (guarded by `not
            # self.matchstarted`) can silently skip re-arming Team Entrance
            # for the restarted match -- leaving the *previous* attempt's
            # worker as the only one that ever ran, with nothing to replace
            # or stop it (reported live 2026-08-30, still unconfirmed by a
            # captured Restart log -- see CLAUDE.md §7 Part 7). Reaching a
            # pause/setup menu page is itself proof the match isn't
            # currently live, so reflect that immediately instead of
            # waiting on Chants' independently-clocked poll to catch up.
            self.matchstarted = False
        if self._page_is_outside_match(page_name):
            self._reset_for_leaving_match(page_name)
        if page_name == "game/screens/playNow/KickOffHub":
            self._left_match_reset_done = False
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

        # TV/bumper is FIFA's competition intro.  The club entrance anthem
        # belongs to the following 3D walkout presentation, so only start it
        # on the first page transition *after* the bumper has gone away.
        entrance_just_started = False
        if self._entrance_armed and "TV/bumper" not in page_name:
            self._entrance_armed = False
            if self._page_blocks_team_entrance(page_name):
                # The blank-page fallback below arms Team Entrance on *any*
                # blank page while matchstarted/skillgamechange are both
                # False -- including a blank page reached mid-Abandon, since
                # FIFA's own started/ran_time flags can read stale/reset
                # values while bouncing through the pause menu (see
                # CLAUDE.md §7). Confirmed live 2026-08-29/30
                # (runtime/server16.log): that false arm gets "consumed" by
                # whatever page comes next -- sometimes FluxHub reasserting
                # itself, sometimes landing on playNow/SelectTeam -- and
                # without this guard that next transition was treated as a
                # genuine new match, restarting the anthem from scratch
                # audibly inside the menu. A page that is itself a pause
                # menu or playNow setup menu can never be the real walkout,
                # so just drop the arm here instead of starting.
                self.log(f"Team entrance disarmed: next page was a menu ({page_name!r})")
            else:
                entrance_just_started = self._start_team_entrance()

        if not page_name.strip() and not self.matchstarted and not self.skillgamechange:
            if not entrance_just_started:
                # Mirror Chants' own restart resilience: this blank-page
                # transition is Chants' second, independent trigger besides
                # TV/bumper (see just below) for exactly this reason — FIFA's
                # "Restart Match" (chosen mid-match from the pause menu)
                # does not reliably re-show the TV/bumper competition intro
                # the way a fresh match from the main menu does, so
                # TV/bumper-only arming left Team Entrance silently unarmed
                # for a restarted match while Chants kept working via this
                # same fallback (reported live 2026-08-28). Arming here is
                # safe for the ordinary first-match case too: the very next
                # transition is normally "TV/bumper" itself, which the check
                # above ignores (it contains the substring "TV/bumper"), so
                # entrance still only actually starts once the bumper ends —
                # `entrance_just_started` above only prevents re-arming a
                # worker that this same call just handed off to a thread.
                self._entrance_sequence += 1
                self._entrance_armed = True
                self._entrance_pre_match_guard = True
            # The blank page right after KickOffHub is when FIFA starts
            # LOADING the match -- and, in every captured log, exactly when
            # the stadium-name buffer first gets allocated (the priority
            # window reads 0MB until then). Start polling for it now rather
            # than waiting for the slower scan attempts to stumble on it
            # (see StadiumDbNamePatchCoordinator.fast_watch). No-op unless a
            # stadium is applied for this match.
            self._start_scoreboard_name_fast_watch()
            self._start_chants_runtime()
            return
        if "TV/bumper" in page_name or "skillGames/SkillGa" in page_name:
            if "TV/bumper" in page_name:
                # Arm here, but do not play over FIFA's competition bumper.
                self._entrance_sequence += 1
                self._entrance_armed = True
                # FIFA exposes the match as "running" during parts of the 3D
                # intro.  Hold Support chants until actual clock movement
                # confirms kick-off.
                self._entrance_pre_match_guard = True
                self._start_chants_runtime()
            if not self.bumperpagechange and not self.skillgamechange:
                self.pagechange = False
                self.bumperpagechange = True
                self.skillgamechange = True
                self.tv_bumper_page()
                # Re-request the stadium-name patch now that the bumper is
                # loading — the last moment before FIFA renders the stadium
                # name, and by now HID/AID are reliably resolved (unlike the
                # earlier request from start_stadium_task, which can fire
                # before refresh_live_context has captured them for a brand
                # new match). This re-arms the same background coordinator;
                # it no-ops instantly if the earlier request already patched
                # this exact match's string.
                if self.curstad:
                    std_name = self.stadium_runtime.resolve_scoreboard_display_name(self.curstad)
                    self.stadium_runtime.write_active_stad_name(std_name)
                    self.match_string_patcher.request(std_name)
                    self.stadium_runtime.request_db_name_patch(self.injID, std_name)
                    # Backstop for a blank-page transition that never fired
                    # (or fired before the stadium was applied) -- same fast
                    # watch, just started later. Harmless if already running.
                    self._start_scoreboard_name_fast_watch()
                    self._start_scoreboard_name_progress(self.injID, std_name)
            return
        self.pagechange = False
        self.bumperpagechange = False
        self.skillgamechange = False

    @staticmethod
    def _page_is_outside_match(page_name: str) -> bool:
        """True for pages that can only be reached after the previous match
        is over: the training hub / skill games / practice arena.

        Deliberately NOT the same vocabulary as `_page_blocks_team_entrance`:
        FluxHub is both the in-match pause menu and the main menu, and
        Settings/Profile can be opened from the pause menu, so none of those
        prove the match is gone. Training screens are only reachable from the
        main menu. FIFA leaves the abandoned match's started/clock/HID/AID
        memory untouched there (only KickOffHub used to clear it), so without
        this the practice arena looked like a live match to CGFS and played
        the abandoned match's chants (reported live 2026-09-23).
        """
        lowered = (page_name or "").lower()
        return any(token in lowered for token in ("training/", "skillgames/", "misc/arenaplayer"))

    def _reset_for_leaving_match(self, page_name: str) -> None:
        """Forget the previous match once, on the first out-of-match page.

        Same teardown a KickOffHub visit does (context, chants, entrance,
        substitution addresses) minus arming anything for a new match. Runs
        once per departure: `_left_match_reset_done` is re-armed at the next
        KickOffHub so moving between training pages does not re-clear.
        """
        if getattr(self, "_left_match_reset_done", False):
            return
        self._left_match_reset_done = True
        self.log(f"Left match for {page_name!r}: resetting chants, entrance and live context")
        # Bumped like a KickOffHub visit so stale chains keyed on the
        # generation (scoreboard-name progress, entrance match key) stop.
        self._kickoff_generation += 1
        self._last_stadium_applied_signature = None
        self.pagechange = False
        self.bumperpagechange = False
        self._entrance_armed = False
        self._entrance_pre_match_guard = False
        self._clear_live_context()
        self.substitution_runtime.reset_for_new_match()
        self._reset_chants_state()

    def _start_scoreboard_name_progress(self, injid: str, std_name: str) -> None:
        """Show a loading bar for the scoreboardstdname patch and drive it
        to completion once StadiumDbNamePatchCoordinator actually confirms
        the name is live -- so the user can SEE the attempt happening
        instead of only finding out (or not) from the log.

        Reuses the same D3D-overlay loading bar StadiumRuntime's own
        file-copy job shows (StadiumRuntime.start_stadium_task /
        _show_stadium_loading_modal) -- it's the only progress-bar widget
        this app has, and by the time "TV/bumper" fires (well after the
        match's own menus/team-select, not during stadium loading) that
        earlier instance is long since closed, so this opens a fresh one
        rather than fighting over an already-visible one.

        Ticks are tagged with the current `_kickoff_generation` (bumped only
        on a genuine new KickOffHub visit -- the same "advances exactly once
        per real new match" signal TeamEntranceRuntime already relies on for
        this exact class of bug, CLAUDE.md §5.5 Part 9) so a stale chain from
        an abandoned/superseded match can never fight a newer match's own
        chain over this one shared bar -- e.g. by hiding it right after the
        new chain just showed it.
        """
        self._show_stadium_loading_modal(std_name, "Applying scoreboard name...", progress=0)
        started_at = time.monotonic()
        # Captured BEFORE the first request of this cycle so a later tick can
        # tell "the coordinator actually wrote something new" apart from
        # "still showing whatever was already there" -- see
        # _db_name_patch_retry_tick's own success check for why an exact
        # match to `std_name` alone isn't enough (a real, expected buffer-
        # capacity limit can mean only a TRUNCATED name ever lands, e.g.
        # CLAUDE.md §7 Part 10's "Campos de Sport de El Sardinero" -> "Campos
        # de S" for FIFA's 12-byte slot-176 name buffer -- confirmed live
        # again 2026-09-10 for the same team/stadium).
        baseline_name = self.stadium_db_name_patcher.get_current_name(injid)
        # Mutable, per-cycle kick-off clock-speed tracking state (see
        # _db_name_patch_kickoff_detected) -- threaded through every tick of
        # this one cycle so the loading bar stops itself the moment real
        # gameplay starts, instead of sitting on screen for the full
        # DB_NAME_PATCH_RETRY_WINDOW_SECONDS regardless of match state
        # (reported live 2026-09-14: "Applying scoreboard name..." still
        # showing well into an already-live match).
        speed_state: dict = {}
        self._scoreboard_name_progress_active = True
        self._scoreboard_name_progress_std_name = std_name
        self._scoreboard_name_progress_injid = injid
        self._schedule_db_name_patch_retry(
            injid, std_name, baseline_name, self._kickoff_generation,
            started_at, started_at + DB_NAME_PATCH_RETRY_WINDOW_SECONDS, speed_state,
        )

    def _loading_has_started(self) -> bool:
        """True once FIFA is past KickOffHub and loading the match: the blank
        page (or the bumper) is showing. Used by finish_stadium_apply so a
        stadium that finishes applying AFTER the user already pressed start --
        i.e. after the blank-page transition that normally starts the fast
        watch has come and gone -- still starts it."""
        page = self.lastpagename or ""
        return not page.strip() or "TV/bumper" in page

    def _start_scoreboard_name_fast_watch(self) -> None:
        """Start StadiumDbNamePatchCoordinator's fast priority-window watch for
        the stadium applied to this match, if any.

        Called at the blank page that follows KickOffHub (FIFA starts loading
        the match; the name buffer only gets allocated from here on) and again
        at "TV/bumper" as a backstop. Reported live 2026-09-21: the second
        match of a session displayed "Sanderson Park" -- the patch landed in
        the same second as the bumper, after the one before it had landed a
        second EARLIER, because the slow scan attempts (1.5-6s each) only
        happen to catch the freshly allocated buffer in time some of the
        time. See StadiumDbNamePatchCoordinator.fast_watch for the details.

        Deliberately NOT started earlier (e.g. from finish_stadium_apply): an
        earlier prewarm of ordinary scan attempts was tried, but the buffer
        does not exist during the menus, so those attempts could never
        succeed and only consumed the coordinator's per-slot scan budget
        (MAX_SCAN_ATTEMPTS lasts the whole FIFA process) -- a long pause on
        KickOffHub could exhaust it before the buffer even existed.
        """
        if not self.curstad or self._closing:
            return
        try:
            std_name = self.stadium_runtime.resolve_scoreboard_display_name(self.curstad)
            self.stadium_runtime.start_db_name_fast_watch(self.injID, std_name)
        except Exception as exc:
            self.log("Stadium DB name fast watch start error", exc)

    def _hide_scoreboard_name_progress_for_stadium_scene(self) -> None:
        """Hide the scoreboardstdname loading notification the instant Team
        Entrance's own trigger fires (see _start_team_entrance in app.py,
        called from here and from ChantsRuntime._resolve_pending_entrance_arm).

        Requested live 2026-09-14: reaching that trigger means we're already
        past the pre-match presentation screen this notification exists to
        report on -- we're in the stadium/walkout scene -- so there is
        nothing left worth showing it for, independent of whether the patch
        itself ever gets confirmed within its own retry window. This only
        touches the shared UI widget; StadiumDbNamePatchCoordinator's own
        background retries are untouched (same as the kick-off-detection
        stop above) -- the very next scheduled tick, if any, will also see
        `_scoreboard_name_progress_active` already False and simply return.
        """
        if not self._scoreboard_name_progress_active:
            return
        std_name = self._scoreboard_name_progress_std_name
        injid = self._scoreboard_name_progress_injid
        current = self.stadium_db_name_patcher.get_current_name(injid) if injid is not None else None
        self.log(
            f"Scoreboard name progress hidden: Team entrance trigger fired "
            f"(already in the stadium scene) for slot {injid!r}"
        )
        self._finish_scoreboard_name_progress(std_name or "", current)

    def _finish_scoreboard_name_progress(self, std_name: str, actual_name: str | None) -> None:
        self._scoreboard_name_progress_active = False
        if actual_name is None:
            text = "Scoreboard name not confirmed"
        elif actual_name == std_name:
            text = f"Scoreboard name applied: {actual_name}"
        else:
            # A real, expected limit of FIFA's own buffer for this slot (not
            # a bug in this write path) -- see the note in
            # _start_scoreboard_name_progress above. Surfacing the actually-
            # applied text here, instead of always echoing back the full
            # requested name, is what makes this honest instead of silently
            # claiming a success the screen doesn't actually show.
            text = f"Scoreboard name applied (shortened): {actual_name}"
        self._update_stadium_loading_modal(100, text)
        self._hide_stadium_loading_modal(delay_ms=1200)

    def _db_name_patch_kickoff_detected(self, speed_state: dict, started_at: float) -> bool:
        """True once real, sustained match-clock movement is observed --
        i.e. the pre-match presentation screen this patch targets has
        already been shown (or missed) and actual gameplay is underway.

        Mirrors the exact heuristic already proven live elsewhere in this
        codebase for telling "genuinely kicked off" apart from FIFA's own
        started/ran_time flags reading true too early (ChantsRuntime.
        _play_goal_track, TeamEntranceRuntime -- CLAUDE.md §5.5): sustained
        timer movement (delta >= 1 at >= 6x real-time speed) across
        DB_NAME_PATCH_KICKOFF_HITS_REQUIRED consecutive ticks, only trusted
        after DB_NAME_PATCH_KICKOFF_PROTECTION_SECONDS have passed since the
        bumper (matching ChantsRuntime's own 6s protection window) so brief
        clock jitter during the walkout itself can't trigger a false
        positive. `speed_state` is a plain dict the caller owns for the
        whole retry cycle -- mutated in place each call, never reset except
        by starting a brand new cycle.
        """
        now = time.monotonic()
        try:
            game_time = self.memory.get_int(self.offsets.GAMESTATSBASE, self.offsets.GAMERANTIME)
        except Exception:
            game_time = None
        if now - started_at < DB_NAME_PATCH_KICKOFF_PROTECTION_SECONDS or game_time is None:
            speed_state["last_game_time"] = game_time
            speed_state["last_real_time"] = now
            speed_state["hits"] = 0
            return False
        last_game_time = speed_state.get("last_game_time")
        last_real_time = speed_state.get("last_real_time")
        speed_state["last_game_time"] = game_time
        speed_state["last_real_time"] = now
        if last_game_time is None or last_real_time is None:
            speed_state["hits"] = 0
            return False
        real_delta = max(0.001, now - last_real_time)
        timer_delta = abs(game_time - last_game_time)
        speed = timer_delta / real_delta
        if timer_delta >= 1 and speed >= DB_NAME_PATCH_KICKOFF_SPEED_THRESHOLD:
            speed_state["hits"] = speed_state.get("hits", 0) + 1
        else:
            speed_state["hits"] = 0
        return speed_state["hits"] >= DB_NAME_PATCH_KICKOFF_HITS_REQUIRED

    def _schedule_db_name_patch_retry(
        self, injid: str, std_name: str, baseline_name: str | None, generation: int, started_at: float, deadline: float,
        speed_state: dict | None = None,
    ) -> None:
        """Re-request StadiumDbNamePatchCoordinator every ~900ms until
        `deadline` (a time.monotonic() timestamp) or an earlier confirmed
        success, after the bumper starts -- covering the pre-match
        presentation screen's actual display window (see the "TV/bumper"
        handler above for why the very first request there can easily fire
        too early). Also drives the loading bar opened by
        _start_scoreboard_name_progress, proportionally to how far into the
        window this retry chain has gotten.

        A fixed *tick count* (this used to be attempts_left=19, one fewer per
        call) is the wrong unit here: it silently assumes each tick
        corresponds to roughly one real scan. That was true when the
        coordinator could skip scanning once something was already cached,
        but not since StadiumDbNamePatchCoordinator was changed (2026-09-10)
        to keep searching for MORE copies on every attempt instead of
        stopping at the first success -- each real scan now reliably takes
        1.5-2.5s+ (three search modes every time), so a 19-tick/~17s budget
        only ever bought room for ~9-10 real scans, well short of
        MAX_SCAN_ATTEMPTS=20, and the retry chain would simply run out of
        ticks with no error and no log line, looking exactly like a silent
        failure. A wall-clock deadline decouples "how long to keep trying"
        from "how fast a single scan happens to be" -- ticks past the point
        the coordinator has already exhausted its own MAX_SCAN_ATTEMPTS are
        cheap no-op cache reverifications, not wasted full scans, so a
        generous window costs little.
        """
        if self._closing:
            return
        # A newer match has since started (a real KickOffHub visit) -- this
        # chain's own bar may already have been overwritten by that match's
        # own fresh _start_scoreboard_name_progress call. Stop touching the
        # shared widget entirely rather than racing it (e.g. hiding it right
        # after the new chain just showed it).
        if self._kickoff_generation != generation:
            return
        # Already finished by something else this generation (a confirmed
        # patch, the deadline, kick-off detection, or the Team Entrance
        # trigger hiding it early -- see
        # _hide_scoreboard_name_progress_for_stadium_scene) since the last
        # tick was scheduled. Nothing left to do.
        if not self._scoreboard_name_progress_active:
            return
        if speed_state is None:
            speed_state = {}
        if time.monotonic() >= deadline:
            self._finish_scoreboard_name_progress(std_name, None)
            return
        self.after(
            900,
            lambda: self._db_name_patch_retry_tick(
                injid, std_name, baseline_name, generation, started_at, deadline, speed_state
            ),
        )

    def _db_name_patch_retry_tick(
        self, injid: str, std_name: str, baseline_name: str | None, generation: int, started_at: float, deadline: float,
        speed_state: dict | None = None,
    ) -> None:
        if self._closing or self._kickoff_generation != generation:
            return
        if not self._scoreboard_name_progress_active:
            return
        if speed_state is None:
            speed_state = {}
        # Stop early if a different stadium has since taken over this slot --
        # a stale retry for an old match would just be a wasted scan. Kept
        # alongside the generation check above (which catches the common
        # case) as a second guard for the "no assignment" match branch,
        # which intentionally never writes injID (see StadiumRuntime /
        # CLAUDE.md §5.1) -- injID could otherwise coincidentally still
        # match a genuinely different match attempt.
        if self.injID != injid:
            self.log(
                f"Stadium DB name patch retry stopped early: injID changed "
                f"from {injid!r} to {self.injID!r}"
            )
            self._finish_scoreboard_name_progress(std_name, None)
            return
        # get_current_name() only ever reports a name this coordinator
        # itself write-verified or read-confirmed live -- never optimistic
        # (see StadiumDbNamePatchCoordinator's own docstring) -- so a change
        # here is a real completion signal, not just "a request was sent".
        # Deliberately NOT requiring an exact match to `std_name`: FIFA's own
        # buffer for a slot can be too small to hold the full requested text
        # (a real, expected limit, not a bug -- CLAUDE.md §7 Part 10), in
        # which case the coordinator still confirms a TRUNCATED value that
        # will never equal `std_name`. Treating that as "never confirmed"
        # used to burn the entire retry window and then falsely report
        # failure, even though the coordinator succeeded (with a shortened
        # name) on its very first attempt. `current != baseline_name` is
        # what actually proves something changed as a result of THIS
        # request; the exact-match check alongside it covers the case where
        # the slot was already showing the right name before this cycle
        # even started (nothing to change, so nothing would ever differ from
        # the baseline).
        current = self.stadium_db_name_patcher.get_current_name(injid)
        if current is not None and (current == std_name or current != baseline_name):
            self._finish_scoreboard_name_progress(std_name, current)
            return
        # Stop showing the loading bar once real gameplay is confirmed
        # running, whether or not a patch ever landed -- the pre-match
        # presentation screen this patch targets is no longer even visible
        # once actual kick-off has happened, so a loading notification still
        # sitting on screen at that point is just noise (reported live
        # 2026-09-14: it stayed up "during the match"). The coordinator
        # itself is untouched by this -- StadiumDbNamePatchCoordinator keeps
        # whatever it's doing in the background regardless; this only stops
        # re-showing the modal.
        if self._db_name_patch_kickoff_detected(speed_state, started_at):
            self.log(
                f"Stadium DB name patch retry stopped: real kick-off detected "
                f"for slot {injid} before a patch was confirmed"
            )
            self._finish_scoreboard_name_progress(std_name, None)
            return
        # A retry chain silently dying from an unexpected exception here
        # would look identical to the injID-mismatch case above (no further
        # log lines, ever) -- catch and log instead of letting Tkinter's
        # default callback-exception handling swallow it and kill the rest
        # of the scheduled window.
        try:
            self.stadium_runtime.request_db_name_patch(injid, std_name)
        except Exception as exc:
            self.log("Stadium DB name patch retry tick error", exc)
        elapsed = time.monotonic() - started_at
        total = max(1.0, deadline - started_at)
        # Capped short of 100 -- only an actual confirmed success (above) is
        # allowed to show a full bar; a bar that reaches 100% on its own
        # while still just guessing would misreport an unresolved patch as
        # done.
        progress = min(95.0, (elapsed / total) * 100.0)
        self._update_stadium_loading_modal(progress, "Applying scoreboard name...")
        self._schedule_db_name_patch_retry(
            injid, std_name, baseline_name, generation, started_at, deadline, speed_state
        )

    def _clear_live_context(self) -> None:
        self._kit_cycle_index = {}
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
        self._set_display("score", "0 - 0")
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

    @staticmethod
    def _page_blocks_team_entrance(page_name: str) -> bool:
        """True for a pause menu or any other non-match setup menu -- never
        the walkout.

        Same page-name vocabulary already used by TeamEntranceRuntime's own
        loop ("playnow") and by the Discord presence pause detection
        ("fluxhub"/"stadiumpan") to recognize these pages, plus the mode-
        select/career/save-load families ("tournamentmode", "career",
        "saveload") added 2026-09-15 after a live report + log capture
        (runtime/server16.log) showed the same "blank page arms, next page
        consumes it" mechanism (CLAUDE.md §5.5 Part 6) misfiring on
        Tournament Mode: after a friendly match, going FluxHub -> blank ->
        "tournamentMode/SelectTournament" was not recognized as a menu, so
        the blank-page arm from the previous match got consumed as if the
        new page were the walkout, replaying that team's Entrance.mp3 for
        ~16 seconds while just browsing the Tournament Mode / Career setup
        screens, until the unresolved-state timeout finally stopped it.
        "instantreplay" added 2026-09-18 for the same reason: FluxHub's own
        "Instant Replay" option routes through `game/screens/instantReplay/
        ReplayScreen`, which is never the walkout either -- see
        TeamEntranceRuntime._run_worker's own `pause_menu_tokens`, which
        needed the identical addition for the live-worker resume-debounce
        case (a paused anthem incorrectly resuming while just reviewing a
        replay from the pause menu). Used to stop the blank-page arm
        fallback from being consumed as "the walkout started" when the very
        next transition is actually just menu/mode-select/replay churn.
        """
        lowered = (page_name or "").lower()
        return any(
            token in lowered
            for token in (
                "playnow", "fluxhub", "stadiumpan", "tournamentmode", "career", "saveload", "instantreplay",
            )
        )

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
        """Try an alternate (shorter, 5-hop) HID/AID pointer chain that
        apparently resolves on some FIFA builds/mods where the newer 6-hop
        chain _try_read_context_int falls back to below does not -- same
        "try more than one chain shape, let whichever resolves win" pattern
        already used for STDNAMEOFFSET176/176B/176C (CLAUDE.md §7 Part 3).

        Reused ``self.memory`` (not a fresh Memory() instance) as of
        2026-09-21: this used to open and close a SECOND, independent
        process handle -- a full psutil.process_iter() system-wide scan plus
        OpenProcess plus a Toolhelp32 module snapshot -- on every single
        call. Called every ~500ms poll tick throughout ALL pre-match menu
        navigation (poll_process -> update_page_name -> refresh_live_context
        whenever the page name contains "team"/"squad"/"stadium"/etc.), this
        chain very commonly hasn't resolved yet (HID/AID aren't meaningful
        until a match is actually starting) -- so this was paying that full
        re-attach cost AND logging a full exception traceback, with no
        de-duplication, on nearly every tick for as long as the user stayed
        in those menus. Reported live as "memory read errors during
        runtime". self.memory is already open and freshly re-attacked this
        same poll tick (poll_process's own self.memory.attack(self.MP) call,
        just before update_page_name runs) -- there is nothing this
        alternate chain gains from a second, independent handle to the same
        process. Failures here are expected and silent (like
        _try_read_optional_int's own pattern below) -- the caller's own
        _try_read_context_int calls right after already report a genuinely
        unresolved context exactly once per distinct state, not once per
        tick (see that method's own _last_context_error de-duplication).
        """
        if not self.MP or not self.memory.is_open():
            return None, None
        try:
            hid = str(self.memory.get_int(self.offsets.ORIHTIDBASE, self.offsets.HT[:5]))
            aid = str(self.memory.get_int(self.offsets.ORIHTIDBASE, self.offsets.HT[:4] + [self.offsets.HT[5]]))
            if hid == "0":
                friendly_hid = str(self.memory.get_int(self.offsets.ORIFRIHTIDBASE, self.offsets.HT2[:5]))
                friendly_aid = str(self.memory.get_int(self.offsets.ORIFRIHTIDBASE, self.offsets.HT2[:4] + [self.offsets.HT2[5]]))
                if friendly_hid != "0":
                    hid = friendly_hid
                if friendly_aid != "0":
                    aid = friendly_aid
            return hid, aid
        except Exception:
            return None, None

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
            self._last_context_error.pop(trace_name, None)
            return value
        except MemoryAccessError as exc:
            message = f"Context not ready for page '{page_name}' [{trace_name}]: {exc}"
            if message != self._last_context_error.get(trace_name):
                self._last_context_error[trace_name] = message
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
            return started == 1 and ran_time >= 1 and not self._page_is_outside_match(self.lastpagename)
        except Exception:
            return False

    def _is_game_running_with(self, memory: Memory) -> bool:
        try:
            started = memory.get_int(self.offsets.GAMESTARTEDBINARYBASE, self.offsets.GAMESTARTEDBINARY)
            ran_time = memory.get_int(self.offsets.GAMESTATSBASE, self.offsets.GAMERANTIME)
            return started == 1 and ran_time >= 1 and not self._page_is_outside_match(self.lastpagename)
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
        self._set_display("score", f"{score_home_display} - {score_away_display}")
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
