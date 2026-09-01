from __future__ import annotations

import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from .chants_runtime import MciAudioPlayer
from .memory_access import Memory

if TYPE_CHECKING:
    from .app import Server16App


@dataclass(frozen=True)
class TeamEntranceConfig:
    track: Path
    volume: float
    delay_seconds: float


class TeamEntranceRuntime:
    """Play one home-team entrance track during the pre-kickoff presentation.

    The existing chants player is intentionally not reused.  FIFA's normal
    crowd loop pauses whenever the match clock is not running, which is the
    exact window in which an entrance anthem must play.  A dedicated MCI
    player keeps both state machines independent and lets the entrance track
    fade out as soon as kick-off is detected.
    """

    DEFAULT_VOLUME = 0.16
    # Start after FIFA's short league intro sting that follows the TV bumper.
    DEFAULT_DELAY_SECONDS = 7.0
    MAX_DELAY_SECONDS = 45.0
    PRESENTATION_WAIT_SECONDS = 30.0
    MAX_PLAY_SECONDS = 180.0
    # How long the anthem may stay paused before this worker gives up and
    # closes for good instead of waiting for a resume that may never come.
    PAUSE_GIVEUP_SECONDS = 20.0

    def __init__(
        self,
        app: "Server16App",
        *,
        player_factory: Callable[[], MciAudioPlayer] = MciAudioPlayer,
        memory_factory: Callable[[], Memory] = Memory,
    ) -> None:
        self.app = app
        self._player_factory = player_factory
        self._memory_factory = memory_factory
        self._lock = threading.RLock()
        self._worker_generation = 0
        self._worker_running = False
        self._started_match_key: tuple[object, ...] | None = None
        self._player: MciAudioPlayer | None = None
        self._target_volume = 0.0

    @staticmethod
    def _safe_float(raw: str, default: float) -> float:
        try:
            return float(raw)
        except (TypeError, ValueError):
            return default

    @classmethod
    def _parse_values(cls, raw: str) -> tuple[str, float, float] | None:
        parts = [part.strip() for part in raw.split(",")] if raw else []
        if not parts or not parts[0]:
            return None
        folder = parts[0].replace("/", "\\").strip("\\")
        volume = cls._safe_float(parts[10], cls.DEFAULT_VOLUME) if len(parts) > 10 else cls.DEFAULT_VOLUME
        delay = cls._safe_float(parts[11], cls.DEFAULT_DELAY_SECONDS) if len(parts) > 11 else cls.DEFAULT_DELAY_SECONDS
        volume = max(0.01, min(1.0, volume))
        delay = max(0.0, min(cls.MAX_DELAY_SECONDS, delay))
        return folder, volume, delay

    def _resolve_config(self, team_id: str) -> TeamEntranceConfig | None:
        app = self.app
        if not team_id or not app.settings_ini.key_exists(team_id, "chantsid"):
            return None
        parsed = self._parse_values(app.settings_ini.read(team_id, "chantsid"))
        if parsed is None:
            return None
        folder, volume, delay = parsed
        track = app.exedir / "FSW" / "Chants" / folder / "Entrance.mp3"
        if not track.is_file():
            return None
        return TeamEntranceConfig(track=track, volume=volume, delay_seconds=delay)

    def _match_key(self, home_team_id: str) -> tuple[object, ...]:
        # Deliberately excludes `_entrance_sequence`: that counter bumps on
        # every blank-page arm fallback in app_game.py, including a redundant
        # one fired by a mid-walkout Restart that skips the intro animation
        # and lands back on the same blank page it paused on. `_kickoff_generation`
        # only advances on a genuine visit to game/screens/playNow/KickOffHub,
        # which such a restart does not go through -- so it correctly still
        # identifies this as the SAME match, letting start_for_match() no-op
        # instead of cancelling the live worker and replaying the anthem from
        # scratch deep into an already-live match. Confirmed live 2026-08-30
        # (runtime/server16.log, 13:45:42-13:46:05) -- see CLAUDE.md §7.
        app = self.app
        return (
            getattr(app, "_kickoff_generation", 0),
            home_team_id,
            (getattr(app, "AID", "") or "").strip(),
            (getattr(app, "TOURNAME", "") or "").strip(),
            (getattr(app, "TOURROUNDID", "") or "").strip(),
        )

    def start_for_match(self) -> bool:
        """Schedule the current home team's entrance track once.

        Returns ``True`` only when a worker was scheduled.  The worker itself
        waits for FIFA's pre-kickoff memory state, so returning ``True`` does
        not necessarily mean audio has already begun.
        """

        app = self.app
        if not app.module_enabled("TeamEntrance"):
            return False
        home_team_id = (getattr(app, "HID", "") or "").split()[0].strip()
        config = self._resolve_config(home_team_id)
        if config is None:
            if home_team_id:
                app.log(f"Team entrance skipped for {home_team_id}: Entrance.mp3 or chantsid mapping missing")
            return False

        match_key = self._match_key(home_team_id)
        stale_player: MciAudioPlayer | None = None
        stale_volume = 0.0
        with self._lock:
            # Checked unconditionally, BEFORE the worker_running branch below
            # -- not only while a worker for this match is still alive. A
            # worker that already played and exited naturally (real kick-off
            # detected, `_worker_running` back to False) leaves
            # `_started_match_key` pointing at the match it just finished; a
            # spurious re-arm for that same match (e.g. the blank-page arm
            # fallback in app_game.py firing again because `matchstarted`
            # hadn't yet caught up to a quick pause-menu open/close, with no
            # `_kickoff_generation` change) must still no-op here, or it
            # replays the anthem from scratch for an instant before its own
            # kick-off detection catches up and fades it right back out.
            # Confirmed live 2026-08-30 (runtime/server16.log, 14:09:02-
            # 14:09:42): several one-second replays, none of them an actual
            # Restart. See CLAUDE.md §7 before changing this.
            if self._started_match_key == match_key:
                return False
            if self._worker_running:
                # A different match wants the anthem while the previous
                # match's worker is still alive -- most commonly Restart
                # chosen from the pause menu during the walkout, which
                # never routes through KickOffHub (the usual trigger for
                # entrance_runtime.reset()) the way Abandon eventually does.
                # Cut the stale worker loose here instead of silently
                # refusing to start the new one. Mirrors reset()'s own
                # immediate-close pattern, but must NOT touch the guard
                # flags reset() clears -- app_game.py has already set them
                # for the *new* match before calling start_for_match().
                app.log(f"Team entrance: cancelling previous match's anthem for HID={home_team_id}")
                stale_player = self._player
                stale_volume = self._target_volume
                self._player = None
                self._target_volume = 0.0
                self.app._entrance_active = False
            self._started_match_key = match_key
            self._worker_generation += 1
            worker_generation = self._worker_generation
            self._worker_running = True

        if stale_player is not None:
            self._close_player(stale_player, stale_volume, fade_ms=300)

        threading.Thread(
            target=self._run_worker,
            args=(worker_generation, home_team_id, config),
            daemon=True,
            name=f"TeamEntrance-{home_team_id}",
        ).start()
        app.log(
            f"Team entrance armed: HID={home_team_id} track={config.track.name} "
            f"delay={config.delay_seconds:.1f}s volume={config.volume:.2f}"
        )
        return True

    def reset(self, *, clear_match: bool = True) -> None:
        """Cancel pending/playing entrance audio and optionally allow a new match."""

        with self._lock:
            self._worker_generation += 1
            self._worker_running = False
            if clear_match:
                self._started_match_key = None
            player = self._player
            self._player = None
            target_volume = self._target_volume
            self._target_volume = 0.0
            self.app._entrance_active = False
            self.app._entrance_armed = False
            self.app._entrance_pre_match_guard = False
        if player is not None:
            self._close_player(player, target_volume, fade_ms=300)

    def _is_current(self, generation: int) -> bool:
        with self._lock:
            return generation == self._worker_generation

    def _wait_for_kickoff_or_delay(self, seconds: float, generation: int, memory: Memory) -> bool:
        """Wait out the configured pre-play delay -- unless the match clock
        is already running at live-gameplay speed by the time this worker
        gets there, in which case bail out WITHOUT ever opening the track.

        Skipping the pre-kickoff presentation (formations/walkout) can drop
        the player straight into a genuinely live match before this worker's
        delay (7s by default) even elapses. The kick-off detector inside the
        playback loop below (`timer_delta >= 1 and speed >= 6.0`, three
        consecutive ~0.2s hits -- the same "normal gameplay runs at ~8-10
        timer units/sec while celebration/walkout runs far slower" heuristic
        ChantsRuntime's goal-song cut already relies on, see
        chants_runtime.py's `_play_goal_track`) is proven live to catch this
        correctly, but it previously only ever ran *after* `player.play()`,
        so a skip could still make the anthem audibly start for up to ~1s
        before fading back out. Running the identical check here, before the
        track is ever opened, closes that gap -- reusing a signal already
        validated live rather than inventing a new one. Ported from a report
        by the original author of this feature (as "Walkout" in an earlier,
        pre-refactor fork): that implementation's equivalent wait was a bare
        `time.sleep(10.0)` with no state check at all, and a `_walkout_cancelled`
        flag that was set but never read anywhere -- an abandoned attempt at
        exactly this fix. See CLAUDE.md §5.5/§7 before changing this.
        """
        app = self.app
        deadline = time.time() + max(0.0, seconds)
        kickoff_hits = 0
        last_game_time: int | None = None
        last_real_time: float | None = None
        while True:
            now = time.time()
            if now >= deadline:
                return self._is_current(generation)
            if not self._is_current(generation) or not app.module_enabled("TeamEntrance"):
                return False
            state = self._read_match_state(memory)
            if state is not None:
                game_time = state[1]
                if last_game_time is not None and last_real_time is not None:
                    real_delta = max(0.001, now - last_real_time)
                    timer_delta = abs(game_time - last_game_time)
                    speed = timer_delta / real_delta
                    if timer_delta >= 1 and speed >= 6.0:
                        kickoff_hits += 1
                    else:
                        kickoff_hits = 0
                    if kickoff_hits >= 3:
                        app.log(
                            f"Team entrance skipped: match already live before playback "
                            f"started (speed={speed:.1f})"
                        )
                        return False
                last_game_time = game_time
                last_real_time = now
            time.sleep(0.2)

    def _read_match_state(self, memory: Memory) -> tuple[int, int] | None:
        app = self.app
        try:
            started = memory.get_int(app.offsets.GAMESTARTEDBINARYBASE, app.offsets.GAMESTARTEDBINARY)
            game_time = memory.get_int(app.offsets.GAMESTATSBASE, app.offsets.GAMERANTIME)
            return started, game_time
        except Exception:
            return None

    def _wait_for_presentation(self, memory: Memory, generation: int) -> bool:
        """Wait until FIFA's match memory is readable.

        Page transition logic already proves that the TV bumper has ended.
        FIFA 16 may report ``started=1`` and a non-zero runtime while the
        players are still walking out, so those values must not reject the
        entrance anthem here.
        """
        app = self.app
        deadline = time.time() + self.PRESENTATION_WAIT_SECONDS
        while time.time() < deadline and self._is_current(generation):
            if not app.module_enabled("TeamEntrance"):
                return False
            if not app.MP or not memory.attack(app.MP) or not memory.is_open():
                time.sleep(0.2)
                continue
            state = self._read_match_state(memory)
            if state is not None:
                return True
            time.sleep(0.2)
        app.log("Team entrance skipped: 3D presentation memory was not detected")
        return False

    def _kickoff_started(self, memory: Memory) -> bool:
        state = self._read_match_state(memory)
        return bool(state and state[0] == 1 and state[1] >= 1)

    def _run_worker(self, generation: int, team_id: str, config: TeamEntranceConfig) -> None:
        app = self.app
        memory = self._memory_factory()
        player: MciAudioPlayer | None = None
        try:
            if not self._wait_for_presentation(memory, generation):
                return
            if not self._wait_for_kickoff_or_delay(config.delay_seconds, generation, memory):
                return
            player = self._player_factory()
            player.open(config.track)
            duration_ms = player.length_ms()
            player.set_volume(0)
            player.play()
            with self._lock:
                if not self._is_current(generation):
                    return
                self._player = player
                self._target_volume = config.volume
                app._entrance_active = True

            app.chants_runtime.fade_player(player, 0, config.volume, 500)
            app._set_display_async("audio_status", "Team entrance")
            app._set_display_async("audio_current", config.track.stem)
            app._set_display_async("audio_clubsong", team_id)
            app._set_display_async("audio_crowd_mode", "Entrance anthem")
            app._set_display_async("audio_crowd_volume", f"{config.volume:.2f}")
            app._set_display_async("audio_source", "Home team entrance")
            app._set_display_async("audio_next", "Fade at kick-off")
            app._set_display_async("audio_last_action", f"Entrance anthem {team_id}")
            app.log(f"Team entrance started: HID={team_id} track={config.track}")

            duration_seconds = duration_ms / 1000 if duration_ms > 0 else self.MAX_PLAY_SECONDS
            hard_deadline = time.time() + min(self.MAX_PLAY_SECONDS, max(5.0, duration_seconds + 2.0))
            kickoff_hits = 0
            last_game_time: int | None = None
            last_real_time: float | None = None
            non_paused_count = 0
            unresolved_state_count = 0
            player_paused = False
            paused_since: float | None = None
            resume_pending_count = 0
            # Same page-name tokens app_game.py's Discord presence already uses
            # to detect FIFA's own pause menu (FluxHub) / stadium free-cam pause
            # view.  The started/ran_time memory flags can't be used here: they
            # are known to read as "not running" throughout the normal, unpaused
            # walkout too (see the class docstring), so they would mistake the
            # pre-kickoff presentation itself for a pause.
            pause_menu_tokens = ("fluxhub", "stadiumpan")
            while time.time() < hard_deadline and self._is_current(generation):
                if not app.module_enabled("TeamEntrance"):
                    break
                mode = player.mode()
                if mode in {"stopped", "closed"}:
                    break

                # Read match state every tick, even while paused, to catch
                # Abandon/Restart chosen from the pause menu: once the match's
                # own pointer chain stops resolving entirely, the session is
                # gone for good, so stop instead of pausing forever.
                now = time.time()
                state = self._read_match_state(memory)
                if state is None:
                    unresolved_state_count += 1
                    if unresolved_state_count >= 3:
                        app.log(f"Team entrance stopped: match ended for HID={team_id}")
                        break
                    time.sleep(0.2)
                    continue
                unresolved_state_count = 0
                game_time = state[1]

                # Abandon/Restart more commonly leaves the pointer chain
                # resolvable but the clock frozen/reset instead of making it
                # unreadable, and FIFA doesn't reliably route every
                # abandon/restart destination through the exact "KickOffHub"
                # page string that normally cancels this worker
                # (app_game.py's _handle_page_transition). So: give up for
                # good if we've been paused too long without confirmed
                # progress, rather than waiting indefinitely for a resume
                # that may never come.
                if player_paused and paused_since is not None and now - paused_since >= self.PAUSE_GIVEUP_SECONDS:
                    app.log(f"Team entrance stopped: match did not resume for HID={team_id}")
                    break

                page_name = (getattr(app, "lastpagename", "") or "").lower()
                if "playnow" in page_name:
                    # game/screens/playNow/SideSelect, SelectTeam and
                    # KickOffHub are pre-match SETUP menus, never part of an
                    # in-progress presentation/walkout. Reaching one while
                    # this worker is still alive is decisive proof the match
                    # it was armed for is over -- most commonly Abandon
                    # chosen from the FluxHub pause menu during the walkout,
                    # before kick-off (the only window this worker is even
                    # active in). The page-name resume debounce below cannot
                    # tell "FluxHub closed, walkout resumed" apart from
                    # "FluxHub closed, now navigating out to a menu" -- both
                    # look identical (fluxhub token gone) for several ticks.
                    # Confirmed live 2026-08-29 (server16.log): after such an
                    # Abandon the anthem stayed audible through SelectTeam for
                    # 8s, well past the 3-tick resume debounce, because the
                    # match's own pointer chain kept reading back a stale but
                    # resolvable value instead of going unreadable. Stop
                    # outright here rather than waiting on that unresolved-
                    # state counter. See CLAUDE.md §7 before changing this.
                    app.log(f"Team entrance stopped: returned to menu for HID={team_id}")
                    break

                if any(token in page_name for token in pause_menu_tokens):
                    # Pause menu open — pause the anthem, same debounce/pause
                    # pattern as ChantsRuntime's crowd loop. Every confirmed
                    # pause-menu tick also resets resume_pending_count: without
                    # this, an isolated non-consecutive misread of the page
                    # name while still genuinely paused (a single stray tick,
                    # possibly minutes apart from another one) would slowly
                    # accumulate toward the resume threshold below instead of
                    # requiring truly consecutive ticks — confirmed live
                    # 2026-08-28 as the cause of the anthem audibly resuming
                    # while still sitting in the pause menu.
                    non_paused_count += 1
                    last_game_time = None
                    last_real_time = None
                    kickoff_hits = 0
                    resume_pending_count = 0
                    if non_paused_count >= 3 and not player_paused and player.is_playing():
                        app.chants_runtime.fade_player(player, config.volume, 0, 400)
                        player.pause()
                        player_paused = True
                        paused_since = now
                        app._set_display_async("audio_crowd_mode", "Paused")
                        app._set_display_async("audio_next", "Resume on return")
                    time.sleep(0.2)
                    continue
                non_paused_count = 0

                if player_paused:
                    # FluxHub/stadium-pan is gone. A 2026-08-27 fix required
                    # *sustained* clock-speed progress here (the same
                    # kick-off heuristic used below) to stop a stale-memory
                    # false resume after Abandon/Restart. That condition can
                    # only ever be satisfied once real kick-off has *already*
                    # happened — the walkout clock never runs at match speed
                    # before then — so it also silently blocked every genuine
                    # pause/resume during the walkout, the anthem's entire
                    # active window (confirmed live 2026-08-28: pausing and
                    # returning never brought the anthem back). Trust the
                    # page-name signal instead, the same way pausing does,
                    # with a short debounce rather than a single sample. The
                    # unresolved-state check above and the KickOffHub reset
                    # in app_game.py still bound how long a stale Abandon
                    # transition could stay audible if one ever slips past
                    # this. See CLAUDE.md §7 before changing this again.
                    resume_pending_count += 1
                    if resume_pending_count < 3:
                        time.sleep(0.2)
                        continue
                    player.resume()
                    app.chants_runtime.fade_player(player, 0, config.volume, 300)
                    player_paused = False
                    paused_since = None
                    resume_pending_count = 0
                    app._set_display_async("audio_crowd_mode", "Entrance anthem")
                    app._set_display_async("audio_next", "Fade at kick-off")

                if last_game_time is not None and last_real_time is not None:
                    real_delta = max(0.001, now - last_real_time)
                    timer_delta = abs(game_time - last_game_time)
                    speed = timer_delta / real_delta
                    if timer_delta >= 1 and speed >= 6.0:
                        kickoff_hits += 1
                    else:
                        kickoff_hits = 0
                    if kickoff_hits >= 3:
                        app._entrance_pre_match_guard = False
                        app.log(f"Team entrance fade-out: actual kick-off clock detected for HID={team_id}")
                        break
                last_game_time = game_time
                last_real_time = now
                time.sleep(0.2)
        except Exception as exc:
            app.log(f"Team entrance failed for {team_id}", exc, exc_info=sys.exc_info())
        finally:
            if player is not None:
                self._close_player(player, config.volume, fade_ms=700)
            try:
                memory.close()
            except Exception:
                pass
            with self._lock:
                if self._player is player:
                    self._player = None
                self._target_volume = 0.0
                app._entrance_active = False
                if generation == self._worker_generation:
                    self._worker_running = False
            app._set_display_async("audio_next", "Crowd audio resumes")

    def _close_player(self, player: MciAudioPlayer, start_volume: float, *, fade_ms: int) -> None:
        try:
            self.app.chants_runtime.fade_player(player, max(0.0, start_volume), 0, fade_ms)
        except Exception:
            pass
        try:
            player.stop()
        except Exception:
            pass
        try:
            player.close()
        except Exception:
            pass
