from __future__ import annotations

import sys
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

from .memory_access import Memory

if TYPE_CHECKING:
    from .app import Server16App


class MciAudioPlayer:
    _counter = 0

    def __init__(self) -> None:
        import ctypes

        self._ctypes = ctypes
        self._winmm = ctypes.WinDLL("winmm")
        MciAudioPlayer._counter += 1
        self.alias = f"server16_audio_{MciAudioPlayer._counter}"
        self._open = False

    def _send(self, command: str) -> str:
        buffer = self._ctypes.create_unicode_buffer(255)
        result = self._winmm.mciSendStringW(command, buffer, len(buffer), 0)
        if result != 0:
            raise RuntimeError(f"MCI command failed ({result}): {command}")
        return buffer.value

    def open(self, path: Path) -> None:
        self.close()
        self._send(f'open "{path}" type mpegvideo alias {self.alias}')
        self._open = True

    def play(self) -> None:
        if self._open:
            self._send(f"play {self.alias} from 0")

    def length_ms(self) -> int:
        if not self._open:
            return 0
        try:
            self._send(f"set {self.alias} time format milliseconds")
            raw = self._send(f"status {self.alias} length").strip()
            return max(0, int(raw))
        except Exception:
            return 0

    def pause(self) -> None:
        if self._open:
            self._send(f"pause {self.alias}")

    def resume(self) -> None:
        if self._open:
            self._send(f"resume {self.alias}")

    def stop(self) -> None:
        if self._open:
            try:
                self._send(f"stop {self.alias}")
            except Exception:
                pass

    def close(self) -> None:
        if self._open:
            try:
                self._send(f"close {self.alias}")
            except Exception:
                pass
            self._open = False

    def set_volume(self, volume: float) -> None:
        if self._open:
            level = max(0, min(1000, int(volume * 1000)))
            self._send(f"setaudio {self.alias} volume to {level}")

    def mode(self) -> str:
        if not self._open:
            return "closed"
        try:
            return self._send(f"status {self.alias} mode").strip().lower()
        except Exception:
            return "closed"

    def is_playing(self) -> bool:
        return self.mode() == "playing"

    def is_paused(self) -> bool:
        return self.mode() == "paused"


class ChantsRuntime:
    def __init__(self, app: "Server16App") -> None:
        self.app = app
        self._special_audio_cooldown_until = 0.0

    @staticmethod
    def _safe_float(raw: str, default: float = 0.05) -> float:
        try:
            return float(raw)
        except Exception:
            return default

    def _parse_chants_config(self, raw: str) -> list[str]:
        return [part.strip() for part in raw.split(",")] if raw else []

    def _pick_random_track(self, folder: Path, last_track: Path | None = None) -> Path | None:
        files = sorted(folder.glob("*.mp3"))
        if not files:
            return None
        candidates = [f for f in files if f != last_track] if len(files) > 1 else files
        return self.app._chants_rng.choice(candidates)

    def _player_state(self) -> str:
        app = self.app
        player = app._chants_player
        if player is None:
            return "idle"
        try:
            mode = player.mode()
        except Exception:
            return "busy"
        if mode in {"closed", "stopped"}:
            return "idle"
        if mode == "paused":
            return "paused"
        return "busy"

    def _special_audio_locked(self) -> bool:
        app = self.app
        if time.time() < self._special_audio_cooldown_until:
            return True
        return self._player_state() in {"busy", "paused"}

    def _mark_special_audio(self, cooldown: float = 0.75) -> None:
        self._special_audio_cooldown_until = time.time() + max(0.0, cooldown)

    def start_chants_runtime(self) -> None:
        app = self.app
        if app.chants_thread_started or not app.module_enabled("Chants"):
            return
        app.chants_thread_started = True
        app._chants_stop.clear()
        threading.Thread(target=self.chants_runtime_loop, daemon=True).start()
        app.log("Chants monitor started")

    def reset_chants_state(self) -> None:
        app = self.app
        app.matchstarted = False
        app._chants_paused = False
        app._chant_track_index = 0
        app._chants_resume_after = 0.0
        app._chants_reset_requested = True
        app._chants_target_volume = 0.0
        app._last_chants_score_snapshot = None
        app._set_display_async("audio_current", "No active track")
        app._set_display_async("audio_crowd_mode", "Idle")
        app._set_display_async("audio_crowd_volume", "-")
        app._set_display_async("audio_source", "-")
        app._set_display_async("audio_next", "Waiting for kickoff")

    def fade_player(self, player: MciAudioPlayer, start: float, end: float, duration_ms: int) -> None:
        steps = 20
        if duration_ms <= 0:
            player.set_volume(end)
            return
        sleep_time = max(0.01, duration_ms / 1000 / steps)
        for step in range(steps + 1):
            volume = start + ((end - start) * step / steps)
            try:
                player.set_volume(volume)
            except Exception:
                break
            time.sleep(sleep_time)

    def _open_player(self, path: Path, volume: float, fade_ms: int = 300) -> MciAudioPlayer:
        """Open and start playing a track, returning the player."""
        player = MciAudioPlayer()
        player.open(path)
        player.set_volume(0)
        player.play()
        self.fade_player(player, 0, volume, fade_ms)
        return player

    def _play_goal_track(
        self,
        track: Path,
        volume: float,
        current: str,
        mode: str,
        source: str,
        next_text: str,
        fade_in_ms: int = 300,
        fade_out_ms: int = 500,
        minimum_hold_seconds: float = 8.0,
    ) -> bool:
        app = self.app
        player = MciAudioPlayer()
        try:
            app._chants_player = player
            app._chants_target_volume = volume
            player.open(track)
            duration_ms = player.length_ms()
            player.set_volume(0)
            player.play()
            self.fade_player(player, 0, volume, fade_in_ms)
            duration_seconds = duration_ms / 1000 if duration_ms > 0 else 0.0
            hold_seconds = max(minimum_hold_seconds, duration_seconds)
            hold_until = time.time() + hold_seconds
            app._chants_resume_after = max(app._chants_resume_after, hold_until + 1.0)
            app._set_display_async("audio_current", current)
            app._set_display_async("audio_crowd_mode", mode)
            app._set_display_async("audio_crowd_volume", f"{volume:.2f}")
            app._set_display_async("audio_source", source)
            app._set_display_async("audio_next", next_text)
            app.log(f"Goal audio started: {track.name} duration={duration_ms}ms hold={hold_seconds:.1f}s")
            hard_until = time.time() + max(hold_seconds + 2.0, duration_seconds + 2.0 if duration_seconds > 0 else 180.0)
            while not app._chants_stop.is_set() and not getattr(app, "_chants_reset_requested", False) and app.module_enabled("Chants"):
                mode_state = player.mode()
                if mode_state in {"stopped", "closed"} and time.time() >= hold_until:
                    break
                if time.time() >= hard_until:
                    break
                time.sleep(0.2)
            self.fade_player(player, volume, 0, fade_out_ms)
            app.log(f"Goal audio finished: {track.name}")
            return True
        finally:
            try:
                player.close()
            finally:
                if app._chants_player is player:
                    app._chants_player = None
                    app._chants_target_volume = 0.0

    def chants_runtime_loop(self) -> None:
        app = self.app
        cooldown_until = 0.0
        next_chant_after = 0.0
        non_running_reads = 0
        chants_memory = Memory()
        while not app._chants_stop.is_set():
            try:
                # Handle reset request from Tkinter thread safely
                if getattr(app, "_chants_reset_requested", False):
                    app._chants_reset_requested = False
                    if app._chants_player is not None:
                        try:
                            current_vol = app._chants_target_volume if app._chants_target_volume > 0 else 0.05
                            self.fade_player(app._chants_player, current_vol, 0, 400)
                            app._chants_player.stop()
                            app._chants_player.close()
                        except Exception:
                            pass
                        app._chants_player = None
                    time.sleep(0.1)
                    continue

                if not app.module_enabled("Chants"):
                    self.reset_chants_state()
                    time.sleep(0.5)
                    continue

                if not app.MP or not chants_memory.attack(app.MP) or not chants_memory.is_open():
                    self.reset_chants_state()
                    time.sleep(0.5)
                    continue

                hid = (app.HID or "").split()[0].strip() if app.HID and app.HID.strip() else ""
                aid = (app.AID or "").split()[0].strip() if app.AID and app.AID.strip() else ""
                home_chants = app.settings_ini.read(hid, "chantsid") if hid and app.settings_ini.key_exists(hid, "chantsid") else ""
                away_chants = app.settings_ini.read(aid, "chantsid") if aid and app.settings_ini.key_exists(aid, "chantsid") else ""

                if not app._is_game_running_with(chants_memory):
                    non_running_reads += 1
                    if non_running_reads >= 3:
                        app.matchstarted = False
                        # Only pause if not already paused by a sub-function
                        if app._chants_player is not None and app._chants_player.is_playing() and not app._chants_paused:
                            start_volume = app._chants_target_volume if app._chants_target_volume > 0 else 0.05
                            self.fade_player(app._chants_player, start_volume, 0, 500)
                            app._chants_player.pause()
                            app._chants_paused = True
                            app._set_display_async("audio_crowd_mode", "Paused")
                            app._set_display_async("audio_next", "Resume on return")
                    time.sleep(0.5)
                    continue

                non_running_reads = 0
                app.matchstarted = True

                # Resume paused player when game resumes
                if app._chants_paused and app._chants_player is not None and app._chants_player.is_paused():
                    app._chants_player.resume()
                    self.fade_player(app._chants_player, 0, max(app._chants_target_volume, 0.04), 300)
                    app._chants_paused = False
                    app._set_display_async("audio_crowd_mode", "Resumed")
                    app._set_display_async("audio_next", "Keep crowd running")

                score_home = chants_memory.get_int(app.offsets.GAMESTATSBASE, app.offsets.GAMEHOMEGOALSCORE)
                score_away = chants_memory.get_int(app.offsets.GAMESTATSBASE, app.offsets.GAMEAWAYGOALSCORE)
                if app._last_chants_score_snapshot is None:
                    app._last_chants_score_snapshot = (score_home, score_away)
                previous_home, previous_away = app._last_chants_score_snapshot

                if (score_home, score_away) != (previous_home, previous_away):
                    # Stop current player on goal
                    if app._chants_player is not None:
                        self.fade_player(app._chants_player, 0.05, 0, 500)
                        app._chants_player.stop()
                        app._chants_player.close()
                        app._chants_player = None
                    scorer = hid if score_home > previous_home else aid if score_away > previous_away else ""
                    app._last_chants_score_snapshot = (score_home, score_away)
                    app._chants_resume_after = time.time() + 6.0
                    app._chants_last_goal_time = time.time()
                    app._set_display_async("audio_crowd_mode", "Goal reaction")
                    app._set_display_async("audio_last_action", f"Goal {score_home} x {score_away}")
                    app._set_display_async("audio_next", "Club song, then crowd")
                    if scorer:
                        time.sleep(2.0)
                        club_song_played = self._play_club_song(scorer)
                        if scorer == aid and away_chants and app.module_enabled("AwayChants"):
                            self._play_away_reaction(away_chants, score_home, score_away, skip_random=club_song_played)
                    else:
                        app.log(f"Goal club song skipped: scorer unavailable for score {score_home} x {score_away} (hid={hid or '-'}, aid={aid or '-'})")
                    cooldown_until = time.time() + 4.5
                    next_chant_after = cooldown_until
                    continue

                app._last_chants_score_snapshot = (score_home, score_away)

                if time.time() < cooldown_until or not home_chants:
                    app._set_display_async("audio_crowd_mode", "Cooldown" if time.time() < cooldown_until else "Awaiting home chants")
                    app._set_display_async("audio_next", "Wait until crowd can restart")
                    time.sleep(0.5)
                    continue

                # Clean up stopped player
                if app._chants_player is not None and app._chants_player.mode() == "stopped":
                    try:
                        app._chants_player.close()
                    except Exception:
                        pass
                    app._chants_player = None
                    if app._chants_rng.random() < 0.7:
                        next_chant_after = time.time() + app._chants_rng.uniform(1.5, 4.0)
                    else:
                        next_chant_after = time.time()

                if app._chants_player is not None and app._chants_player.is_playing():
                    app._set_display_async("audio_crowd_mode", "Playing")
                    app._set_display_async("audio_next", "Current chant still active")
                    time.sleep(0.5)
                    continue

                if app._chants_player is not None and app._chants_player.is_paused():
                    app._set_display_async("audio_next", "Waiting resume")
                    time.sleep(0.5)
                    continue

                if time.time() < next_chant_after:
                    remaining = max(0.0, next_chant_after - time.time())
                    # Try away chants during home crowd pause
                    _home_parts = self._parse_chants_config(home_chants) if home_chants else []
                    away_prob = self._safe_float(_home_parts[9], 0.35) if len(_home_parts) > 9 else 0.35
                    if (remaining > 0.5
                            and away_chants
                            and app.module_enabled("AwayChants")
                            and app._chants_rng.random() < away_prob):
                        app.log(f"Away chant triggered: remaining={remaining:.1f}s prob={away_prob:.2f}")
                        self._play_away_chant(away_chants, score_home, score_away)
                    else:
                        app._set_display_async("audio_crowd_mode", "Crowd pause")
                        app._set_display_async("audio_next", f"Next chant in {remaining:.1f}s")
                        time.sleep(0.5)
                    continue

                # Parse home chants config
                parts = self._parse_chants_config(home_chants)
                if len(parts) < 6:
                    app._set_display_async("audio_crowd_mode", "Invalid config")
                    app._set_display_async("audio_next", "Fix chantsid config")
                    time.sleep(0.5)
                    continue

                folder = parts[0].replace("/", "\\").strip("\\")
                chants_root = app.exedir / "FSW" / "Chants" / folder
                score_diff = score_home - score_away
                if score_diff >= -2:
                    subdir = "Support"
                    volume_index = 1 if score_diff == 0 else 2 if score_diff > 0 else 3 if score_diff == -1 else 4
                else:
                    subdir = "Complaint"
                    volume_index = 5

                chants_dir = chants_root / subdir
                if not chants_dir.exists():
                    app._set_display_async("audio_next", f"Missing folder {subdir}")
                    time.sleep(0.5)
                    continue

                last_played = getattr(app, "_chants_last_track", None)
                track = self._pick_random_track(chants_dir, last_track=last_played)
                if track is None:
                    app._set_display_async("audio_next", f"No tracks in {subdir}")
                    time.sleep(0.5)
                    continue
                app._chants_last_track = track

                volume = self._safe_float(parts[volume_index], 0.05)
                if subdir == "Complaint":
                    volume = max(0.03, volume * (0.75 + (app._chants_rng.random() * 0.25)))

                # Configurable silence
                silence_prob = self._safe_float(parts[7], 0.15) if len(parts) > 7 else 0.15
                silence_max = self._safe_float(parts[8], 8.0) if len(parts) > 8 else 8.0
                silence_min = min(3.0, silence_max)
                if app._chants_rng.random() < silence_prob:
                    silence_duration = app._chants_rng.uniform(silence_min, max(silence_min, silence_max))
                    next_chant_after = time.time() + silence_duration
                    app._set_display_async("audio_crowd_mode", "Crowd silence")
                    app._set_display_async("audio_next", f"Silence for {silence_duration:.1f}s")
                    time.sleep(0.5)
                    continue

                # Crowd fatigue after 20 min without goal
                time_since_goal = time.time() - app._chants_last_goal_time if app._chants_last_goal_time > 0 else 0.0
                if time_since_goal > 1200:
                    fatigue_factor = max(0.70, 1.0 - ((time_since_goal - 1200) / 1200) * 0.30)
                else:
                    fatigue_factor = 1.0
                volume = max(0.02, volume * fatigue_factor)

                # Play home chant using app._chants_player
                app._chants_target_volume = volume
                app._chants_player = MciAudioPlayer()
                app._chants_player.open(track)
                app._chants_player.set_volume(0)
                app._chants_player.play()
                self.fade_player(app._chants_player, 0, volume, 300)
                app._set_display_async("audio_current", track.stem)
                app._set_display_async("audio_last_action", f"Chants {subdir}")
                app._set_display_async("audio_clubsong", hid if hid else "-")
                app._set_display_async("audio_crowd_mode", f"{subdir} ({score_home}-{score_away})")
                app._set_display_async("audio_crowd_volume", f"{volume:.2f}")
                app._set_display_async("audio_source", "Home crowd")
                app._set_display_async("audio_next", "Random crowd loop while match runs")

            except Exception as exc:
                app.log("Chants monitor error", exc, exc_info=sys.exc_info())
            time.sleep(0.5)

        chants_memory.close()
        app.chants_thread_started = False
        app.log("Chants monitor stopped")

    def _play_club_song(self, team_id: str) -> bool:
        """Play the goal club song and hold the chants loop until it finishes."""
        app = self.app
        if self._special_audio_locked():
            if app._chants_player is not None:
                try:
                    self.fade_player(app._chants_player, app._chants_target_volume or 0.05, 0, 250)
                    app._chants_player.stop()
                    app._chants_player.close()
                except Exception:
                    pass
                app._chants_player = None
        if not team_id or not app.settings_ini.key_exists(team_id, "chantsid"):
            app.log(f"Goal club song skipped for {team_id or '-'}: chantsid not configured")
            return False
        raw = app.settings_ini.read(team_id, "chantsid")
        parts = [part.strip() for part in raw.split(",")]
        if len(parts) < 7:
            app.log(f"Goal club song skipped for {team_id}: invalid chantsid config")
            return False
        folder = parts[0].replace("/", "\\").strip("\\")
        club_song = app.exedir / "FSW" / "Chants" / folder / "ClubSong.mp3"
        if not club_song.exists():
            app.log(f"Goal club song skipped for {team_id}: missing {club_song}")
            return False
        volume = self._safe_float(parts[6], 0.08)
        try:
            played = self._play_goal_track(
                club_song,
                volume,
                "ClubSong",
                "Club song",
                f"Club anthem {team_id}",
                "Return to crowd after anthem",
                minimum_hold_seconds=12.0,
            )
            app._set_display_async("audio_current", "ClubSong")
            app._set_display_async("audio_clubsong", team_id)
            return played
        except Exception as exc:
            app.log(f"Club song failed for {team_id}", exc, exc_info=sys.exc_info())
            return False

    def _play_away_chant(self, away_chants: str, score_home: int, score_away: int) -> None:
        """Play away chant using app._chants_player and return immediately.
        The main chants loop remains free to handle pause/resume globally.
        """
        app = self.app
        if self._special_audio_locked():
            return
        parts = self._parse_chants_config(away_chants)
        if len(parts) < 6:
            return
        folder = parts[0].replace("/", "\\").strip("\\")
        score_diff = score_away - score_home
        if score_diff >= -2:
            subdir = "Support"
            volume_index = 1 if score_diff == 0 else 2 if score_diff > 0 else 3
        else:
            subdir = "Complaint"
            volume_index = 5
        chants_dir = app.exedir / "FSW" / "Chants" / folder / subdir
        if not chants_dir.exists():
            return
        track = self._pick_random_track(chants_dir)
        if track is None:
            return
        base_volume = self._safe_float(parts[volume_index], 0.05)
        volume = max(0.02, min(base_volume * 0.45, 0.06))
        try:
            app._chants_player = MciAudioPlayer()
            app._chants_target_volume = volume
            app._chants_player.open(track)
            app._chants_player.set_volume(0)
            app._chants_player.play()
            self.fade_player(app._chants_player, 0, volume, 300)
            self._mark_special_audio(1.0)
            app._set_display_async("audio_current", track.stem)
            app._set_display_async("audio_crowd_mode", f"Away crowd ({score_home}-{score_away})")
            app._set_display_async("audio_crowd_volume", f"{volume:.2f}")
            app._set_display_async("audio_source", "Away crowd")
            app._set_display_async("audio_next", "Away chant during home pause")
        except Exception as exc:
            app.log("Away chant failed", exc, exc_info=sys.exc_info())

    def _play_away_reaction(self, away_chants: str, score_home: int, score_away: int, skip_random: bool = False) -> bool:
        """Play away reaction after an away goal and hold the chants loop until it finishes."""
        app = self.app
        if self._special_audio_locked():
            return False
        parts = self._parse_chants_config(away_chants)
        if len(parts) < 6 or (not skip_random and app._chants_rng.random() > 0.45):
            return False
        folder = parts[0].replace("/", "\\").strip("\\")
        support_dir = app.exedir / "FSW" / "Chants" / folder / "Support"
        track = self._pick_random_track(support_dir)
        if track is None:
            return False
        base_volume = self._safe_float(parts[2], 0.04)
        volume = max(0.02, min(0.12, base_volume * 0.6))
        app._set_display_async("audio_last_action", f"Away crowd reaction {score_home} x {score_away}")
        try:
            played = self._play_goal_track(
                track,
                volume,
                track.stem,
                "Away reaction",
                "Away crowd",
                "Return to crowd after reaction",
                fade_in_ms=250,
                fade_out_ms=350,
            )
            return played
        except Exception as exc:
            app.log("Away reaction failed", exc, exc_info=sys.exc_info())
            return False
