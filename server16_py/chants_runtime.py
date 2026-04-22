from __future__ import annotations

import ctypes
import itertools
import sys
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

from .memory_access import Memory

if TYPE_CHECKING:
    from .app import Server16App


def _ensure_pygame_mixer() -> None:
    """Initialize pygame mixer once, shared across all players."""
    import pygame

    if not pygame.mixer.get_init():
        pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=2048)


class MciAudioPlayer:
    """
    Player that prefers the native Windows MCI backend so chants show up as
    their own app session in the Windows volume mixer, while still falling
    back to pygame if the native path is unavailable.
    """

    _alias_counter = itertools.count(1)
    _owner: "MciAudioPlayer | None" = None

    def __init__(self) -> None:
        self._backend = "mci"
        self._pygame = None
        self._winmm = None
        self.alias = f"server16_audio_{next(self._alias_counter)}"
        try:
            self._winmm = ctypes.WinDLL("winmm")
            self._winmm.mciSendStringW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_void_p]
            self._winmm.mciSendStringW.restype = ctypes.c_uint
        except Exception:
            self._backend = "pygame"
            import pygame

            self._pygame = pygame
            _ensure_pygame_mixer()
        self._open = False
        self._paused = False
        self._volume: float = 1.0

    def _send_mci(self, command: str) -> str:
        if self._winmm is None:
            raise RuntimeError("MCI backend is not available")
        buffer = ctypes.create_unicode_buffer(255)
        result = self._winmm.mciSendStringW(command, buffer, len(buffer), None)
        if result != 0:
            raise RuntimeError(f"MCI command failed ({result}): {command}")
        return buffer.value.strip()

    def open(self, path: Path) -> None:
        self.close()
        if self._backend == "pygame":
            self._pygame.mixer.music.load(str(path))
            MciAudioPlayer._owner = self
        else:
            escaped = str(path).replace('"', '""')
            self._send_mci(f'open "{escaped}" type mpegvideo alias {self.alias}')
        self._open = True
        self._paused = False
        self.set_volume(self._volume)

    def play(self) -> None:
        if not self._open:
            return
        if self._backend == "pygame":
            if not self._is_owner():
                return
            self._pygame.mixer.music.play(start=0.0)
        else:
            self._send_mci(f"play {self.alias} from 0")
        self._paused = False

    def pause(self) -> None:
        if not self._open or self._paused:
            return
        if self._backend == "pygame":
            if not self._is_owner():
                return
            self._pygame.mixer.music.pause()
        else:
            self._send_mci(f"pause {self.alias}")
        self._paused = True

    def resume(self) -> None:
        if not self._open or not self._paused:
            return
        if self._backend == "pygame":
            if not self._is_owner():
                return
            self._pygame.mixer.music.unpause()
        else:
            self._send_mci(f"resume {self.alias}")
        self._paused = False

    def stop(self) -> None:
        if not self._open:
            return
        try:
            if self._backend == "pygame":
                if not self._is_owner():
                    return
                self._pygame.mixer.music.stop()
            else:
                self._send_mci(f"stop {self.alias}")
        except Exception:
            pass

    def close(self) -> None:
        if not self._open:
            return
        if self._backend == "pygame":
            if self._is_owner():
                try:
                    self._pygame.mixer.music.stop()
                    self._pygame.mixer.music.unload()
                except Exception:
                    pass
                MciAudioPlayer._owner = None
        else:
            try:
                self._send_mci(f"close {self.alias}")
            except Exception:
                pass
        self._open = False
        self._paused = False

    def set_volume(self, volume: float) -> None:
        self._volume = max(0.0, min(1.0, volume))
        if not self._open:
            return
        if self._backend == "pygame":
            if not self._is_owner():
                return
            self._pygame.mixer.music.set_volume(self._volume)
        else:
            try:
                self._send_mci(f"setaudio {self.alias} volume to {int(self._volume * 1000)}")
            except Exception:
                pass

    def mode(self) -> str:
        if not self._open:
            return "closed"
        if self._backend == "pygame":
            if not self._is_owner():
                return "closed"
            if self._paused:
                return "paused"
            if self._pygame.mixer.music.get_busy():
                return "playing"
            return "stopped"
        if self._paused:
            return "paused"
        try:
            return self._send_mci(f"status {self.alias} mode").lower()
        except Exception:
            return "stopped"

    def is_playing(self) -> bool:
        return self.mode() == "playing"

    def is_paused(self) -> bool:
        return self.mode() == "paused"

    def _is_owner(self) -> bool:
        return MciAudioPlayer._owner is self


class ChantsRuntime:
    def __init__(self, app: "Server16App") -> None:
        self.app = app

    @staticmethod
    def _safe_float(raw: str, default: float = 0.05) -> float:
        try:
            return float(raw)
        except Exception:
            return default

    def _parse_chants_config(self, raw: str) -> list[str]:
        return [part.strip() for part in raw.split(",")] if raw else []

    def _pick_random_track(self, folder: Path) -> Path | None:
        files = sorted(folder.glob("*.mp3"))
        if not files:
            return None
        return self.app._chants_rng.choice(files)

    def _play_one_shot_track(self, track: Path, volume: float, mode: str, source: str) -> None:
        app = self.app
        player = MciAudioPlayer()
        try:
            player.open(track)
            player.set_volume(0)
            player.play()
            self.fade_player(player, 0, volume, 250)
            app._set_display_async("audio_current", track.stem)
            app._set_display_async("audio_crowd_mode", mode)
            app._set_display_async("audio_crowd_volume", f"{volume:.2f}")
            app._set_display_async("audio_source", source)
            while not app._chants_stop.is_set() and player.mode() not in {"stopped", "closed"}:
                time.sleep(0.2)
            self.fade_player(player, volume, 0, 350)
        finally:
            player.close()

    def _play_away_reaction_if_needed(self, away_chants: str, score_home: int, score_away: int) -> None:
        app = self.app
        parts = self._parse_chants_config(away_chants)
        if len(parts) < 6 or app._chants_rng.random() > 0.45:
            return
        folder = parts[0].replace("/", "\\").strip("\\")
        track = self._pick_random_track(app.exedir / "FSW" / "Chants" / folder / "Support")
        if track is None:
            return
        base_volume = self._safe_float(parts[2], 0.04)
        volume = max(0.02, min(0.12, base_volume * 0.6))
        app._set_display_async("audio_last_action", f"Away crowd reaction {score_home} x {score_away}")
        self._play_one_shot_track(track, volume, "Away reaction", "Away crowd")

    def start_chants_runtime(self) -> None:
        app = self.app
        if app.chants_thread_started or not app.module_enabled("Chants"):
            return
        app.chants_thread_started = True
        app._chants_stop.clear()
        app._set_display_async("audio_status", "Starting chants monitor")
        threading.Thread(target=self.chants_runtime_loop, daemon=True).start()
        app.log("Chants monitor started")

    def reset_chants_state(self) -> None:
        app = self.app
        app.matchstarted = False
        app._chants_paused = False
        app._chant_track_index = 0
        app._chants_target_volume = 0.0
        app._chants_resume_after = 0.0
        if app._chants_player is not None:
            try:
                app._chants_player.stop()
                app._chants_player.close()
            except Exception:
                pass
            app._chants_player = None
        app._last_chants_score_snapshot = None
        app._set_display_async("audio_status", "Waiting for FIFA / kickoff")
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

    def play_club_song_if_exists(self, team_id: str) -> None:
        app = self.app
        if not team_id or not app.settings_ini.key_exists(team_id, "chantsid"):
            return
        raw = app.settings_ini.read(team_id, "chantsid")
        parts = [part.strip() for part in raw.split(",")]
        if len(parts) < 7:
            return
        folder = parts[0].replace("/", "\\").strip("\\")
        club_song = app.exedir / "FSW" / "Chants" / folder / "ClubSong.mp3"
        if not club_song.exists():
            return
        volume = self._safe_float(parts[6], 0.08)
        player = MciAudioPlayer()
        try:
            player.open(club_song)
            player.set_volume(0)
            player.play()
            self.fade_player(player, 0, volume, 300)
            app._set_display_async("audio_clubsong", team_id)
            app._set_display_async("audio_crowd_mode", "Club song")
            app._set_display_async("audio_crowd_volume", f"{volume:.2f}")
            app._set_display_async("audio_source", f"Club anthem {team_id}")
            app._set_display_async("audio_next", "Return to crowd after anthem")
            while not app._chants_stop.is_set() and player.mode() not in {"stopped", "closed"}:
                time.sleep(0.2)
            self.fade_player(player, volume, 0, 500)
        except Exception as exc:
            app.log(f"Club song failed for {team_id}", exc, exc_info=sys.exc_info())
        finally:
            player.close()

    def chants_runtime_loop(self) -> None:
        app = self.app
        cooldown_until = 0.0
        next_chant_after = 0.0
        non_running_reads = 0
        chants_memory = Memory()
        while not app._chants_stop.is_set():
            try:
                if not app.module_enabled("Chants"):
                    self.reset_chants_state()
                    app._set_display_async("audio_status", "Chants disabled")
                    time.sleep(0.5)
                    continue
                if not app.MP or not chants_memory.attack(app.MP) or not chants_memory.is_open():
                    self.reset_chants_state()
                    app._set_display_async("audio_status", "Waiting for FIFA process")
                    time.sleep(0.5)
                    continue
                hid = (app.HID or "").split()[0].strip()
                aid = (app.AID or "").split()[0].strip()
                home_chants = app.settings_ini.read(hid, "chantsid") if hid and app.settings_ini.key_exists(hid, "chantsid") else ""
                away_chants = app.settings_ini.read(aid, "chantsid") if aid and app.settings_ini.key_exists(aid, "chantsid") else ""
                if not app._is_game_running_with(chants_memory):
                    non_running_reads += 1
                    app._set_display_async("audio_status", "Waiting for live match")
                    if non_running_reads >= 3:
                        app.matchstarted = False
                        if app._chants_player is not None and app._chants_player.is_playing():
                            start_volume = app._chants_target_volume if app._chants_target_volume > 0 else 0.05
                            self.fade_player(app._chants_player, start_volume, 0, 500)
                            app._chants_player.pause()
                            app._chants_paused = True
                            app._set_display_async("audio_crowd_mode", "Paused")
                            app._set_display_async("audio_next", "Resume same crowd loop")
                    time.sleep(0.5)
                    continue
                non_running_reads = 0
                app.matchstarted = True
                app._set_display_async("audio_status", "Live match monitor")
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
                    if app._chants_player is not None:
                        self.fade_player(app._chants_player, 0.05, 0, 500)
                        app._chants_player.stop()
                        app._chants_player.close()
                        app._chants_player = None
                    scorer = hid if score_home > previous_home else aid if score_away > previous_away else ""
                    app._last_chants_score_snapshot = (score_home, score_away)
                    app._chants_resume_after = time.time() + 6.0
                    app._set_display_async("audio_crowd_mode", "Goal reaction")
                    app._set_display_async("audio_last_action", f"Goal {score_home} x {score_away}")
                    app._set_display_async("audio_next", "Anthem, cooldown, then crowd")
                    if scorer:
                        time.sleep(2.0)
                        self.play_club_song_if_exists(scorer)
                        if scorer == aid and away_chants:
                            self._play_away_reaction_if_needed(away_chants, score_home, score_away)
                    cooldown_until = time.time() + 4.5
                    next_chant_after = cooldown_until
                    continue
                app._last_chants_score_snapshot = (score_home, score_away)
                if time.time() < cooldown_until or not home_chants:
                    app._set_display_async("audio_crowd_mode", "Cooldown" if time.time() < cooldown_until else "Awaiting home chants")
                    app._set_display_async("audio_next", "Wait until crowd can restart")
                    if not home_chants:
                        app._set_display_async("audio_status", "Missing home chants configuration")
                    time.sleep(0.5)
                    continue
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
                    app._set_display_async("audio_crowd_mode", "Crowd pause")
                    app._set_display_async("audio_next", f"Next chant in {remaining:.1f}s")
                    time.sleep(0.5)
                    continue
                parts = self._parse_chants_config(home_chants)
                if len(parts) < 6:
                    app._set_display_async("audio_status", "Invalid chants configuration")
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
                    app._set_display_async("audio_status", f"Missing chants folder: {subdir}")
                    app._set_display_async("audio_next", f"Missing folder {subdir}")
                    time.sleep(0.5)
                    continue
                track = self._pick_random_track(chants_dir)
                if track is None:
                    app._set_display_async("audio_status", f"No chants found in {subdir}")
                    app._set_display_async("audio_next", f"No tracks in {subdir}")
                    time.sleep(0.5)
                    continue
                volume = self._safe_float(parts[volume_index], 0.05)
                if subdir == "Complaint":
                    volume = max(0.03, volume * (0.75 + (app._chants_rng.random() * 0.25)))
                app._chants_target_volume = volume
                app._chants_player = MciAudioPlayer()
                app._chants_player.open(track)
                app._chants_player.set_volume(0)
                app._chants_player.play()
                self.fade_player(app._chants_player, 0, volume, 300)
                app._set_display_async("audio_status", "Playing chants")
                app._set_display_async("audio_current", track.stem)
                app._set_display_async("audio_last_action", f"Chants {subdir}")
                app._set_display_async("audio_clubsong", hid if hid else "-")
                app._set_display_async("audio_crowd_mode", f"{subdir} ({score_home}-{score_away})")
                app._set_display_async("audio_crowd_volume", f"{volume:.2f}")
                app._set_display_async("audio_source", "Home crowd")
                app._set_display_async("audio_next", "Random crowd loop while match runs")
            except Exception as exc:
                app._set_display_async("audio_status", "Chants error")
                app.log("Chants monitor error", exc, exc_info=sys.exc_info())
            time.sleep(0.5)
        chants_memory.close()
