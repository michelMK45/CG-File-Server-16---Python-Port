from __future__ import annotations

import shutil
import struct
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


class OpenPlayDetector:
    """Kick-off signal that does not depend on how fast the match clock runs.

    The older check -- "the clock gained >= 6 units/s on three consecutive
    ~0.2s ticks" -- reads an integer clock over a window so short that it can
    only compute 0, ~4.8 or ~9.5 units/s: it really asks for two clock units
    per tick. A 4-minute half runs at 11.25 units/s and passes at once; a
    10-minute half runs at 4.5 units/s (one unit per tick) and practically
    never does, which left Support chants on "Waiting for kick-off"
    (docs/bugs-entrance.md Parts 14-18).

    This one asks FIFA instead: GAMEPLAYSTATE reads OPEN_PLAY while the ball
    is in play, and GAMEPERIODSECONDS must have gained REQUIRED_GAIN while it
    stayed that way. The gain is what keeps a stale "in play" value over a
    frozen clock (the practice arena after Abandon, see
    GameMixin._page_is_outside_match) from ever passing, and it is counted in
    period seconds because GAMERANTIME itself stands still at 2700 during
    first-half added time. Every tick that is not open play starts over.
    """

    OPEN_PLAY = 15
    REQUIRED_GAIN = 2

    def __init__(self) -> None:
        self._baseline: int | None = None

    def reset(self) -> None:
        self._baseline = None

    def update(self, play_state: int | None, period_seconds: int | None) -> bool:
        if play_state != self.OPEN_PLAY or period_seconds is None:
            self._baseline = None
            return False
        if self._baseline is None or period_seconds < self._baseline:
            self._baseline = period_seconds
            return False
        return period_seconds - self._baseline >= self.REQUIRED_GAIN


class LiveMatchTracker:
    """Whether the thing in FIFA's memory is a real match that has kicked off.

    OpenPlayDetector alone cannot tell: the practice arena also reads "ball in
    play" over a running clock (~7 units/s, confirmed live 2026-10-05), so
    releasing the pre-match guard on it played chants and goal songs there
    (docs/bugs-entrance.md Part 20). What the arena never shows is a kick-off.

    A match goes live when GAMEPLAYSTATE read KICKOFF_PENDING (pre-match
    scene, after a goal, before the second half) and open play followed. It
    stays live through pauses, stoppages and half-time, and is forgotten when
    the match leaves memory: the clock goes backwards (FIFA zeroes it on the
    way back to the main menu), the state reads LOADING, or it reads
    NO_LIVE_PLAY while the "started" flag is down -- half-time is the one
    NO_LIVE_PLAY inside a match and keeps the flag up. Feed it every tick,
    not only while a match looks running: the kick-off-pending stretch has the
    flag down and the clock at 0.
    """

    KICKOFF_PENDING = 2
    NO_LIVE_PLAY = 1
    LOADING = 13

    def __init__(self) -> None:
        self.live = False
        self._kickoff_pending = False
        self._last_clock: int | None = None
        self._open_play = OpenPlayDetector()

    def forget(self) -> None:
        self.live = False
        self._kickoff_pending = False
        self._open_play.reset()

    def update(
        self, started: int | None, play_state: int | None, clock: int | None, period_seconds: int | None
    ) -> bool:
        if clock is not None:
            if self._last_clock is not None and clock < self._last_clock:
                self.forget()
            self._last_clock = clock
        if play_state == self.LOADING or (play_state == self.NO_LIVE_PLAY and started != 1):
            self.forget()
        elif play_state == self.KICKOFF_PENDING:
            self._kickoff_pending = True
        if self._kickoff_pending:
            if started != 1:
                # Same rule as every other debounced counter here: a tick that
                # disqualifies (the pause menu drops the flag while the period
                # clock stays put) must not leave a stale baseline behind.
                self._open_play.reset()
            elif self._open_play.update(play_state, period_seconds):
                self.live = True
                self._kickoff_pending = False
        return self.live


def read_open_play_inputs(memory: Memory, offsets) -> tuple[int | None, int | None]:
    """(GAMEPLAYSTATE, GAMEPERIODSECONDS) for OpenPlayDetector.update, None for
    whatever cannot be read."""
    values: list[int | None] = []
    for name in ("GAMEPLAYSTATE", "GAMEPERIODSECONDS"):
        try:
            values.append(memory.get_int(offsets.GAMESTATSBASE, getattr(offsets, name)))
        except Exception:
            values.append(None)
    return values[0], values[1]


class ChantsRuntime:
    # Sampling period of the "Chants clock" diagnostic line (see
    # _log_clock_diagnostic): tighter while the pre-match guard is waiting,
    # which is the window the open "Waiting for kick-off" reports are about.
    CLOCK_DIAG_GUARD_INTERVAL = 2.0
    CLOCK_DIAG_INTERVAL = 5.0
    # Read-only window of 32-bit values around the fields already used in the
    # GAMESTATSBASE struct (score +5484/+5488, clock +5500), dumped by the
    # same diagnostic to look for a "period"/"match state" field.
    CLOCK_DIAG_STATS_START = 5436
    CLOCK_DIAG_STATS_COUNT = 32

    def __init__(self, app: "Server16App") -> None:
        self.app = app
        self._special_audio_cooldown_until = 0.0
        self._clock_diag_last: tuple[float, int | None] | None = None
        self._clock_diag_frozen_key: tuple | None = None
        self._clock_diag_stats_last: tuple[int, ...] | None = None
        self._live_match = LiveMatchTracker()

    @staticmethod
    def _safe_float(raw: str, default: float = 0.05) -> float:
        try:
            return float(raw)
        except Exception:
            return default

    # Windows' legacy MCI "mpegvideo" driver (the backend MciAudioPlayer uses)
    # can refuse to open an otherwise perfectly valid MP3 purely because of
    # ID3v2 tag content -- confirmed live 2026-08-21 on two unrelated failing
    # tracks, one with an oversized tag (~76% of file size) and one with an
    # ordinary-looking tag (~0.8%). Tag size is not a reliable predictor;
    # stripping the tag outright is the only fix that held up in both cases.

    @staticmethod
    def _id3v2_tag_total(header: bytes) -> int | None:
        """Given the first 10 bytes of a file, return the total byte length
        of a leading ID3v2 tag (header + body + optional footer), or None if
        there's no ID3v2 tag here."""
        if len(header) < 10 or header[:3] != b"ID3":
            return None
        flags = header[5]
        size = 0
        for b in header[6:10]:
            size = (size << 7) | (b & 0x7F)
        has_footer = bool(flags & 0x10)
        tag_total = 10 + size + (10 if has_footer else 0)
        return tag_total if tag_total > 0 else None

    def _strip_leading_id3v2(self, data: bytes) -> bytes | None:
        """Return `data` with a leading ID3v2 tag removed, or None if there's
        nothing to strip (no tag, or the bytes after it don't look like a
        valid MPEG frame, in which case the file is left untouched)."""
        tag_total = self._id3v2_tag_total(data[:10])
        if tag_total is None or tag_total >= len(data):
            return None
        remainder = data[tag_total:]
        if len(remainder) < 2 or remainder[0] != 0xFF or (remainder[1] & 0xE0) != 0xE0:
            return None
        return remainder

    def _needs_fix(self, path: Path) -> bool:
        """Lightweight check (a handful of bytes, not the whole file) for
        whether `path` has a leading ID3v2 tag that _strip_leading_id3v2
        would actually remove."""
        try:
            size = path.stat().st_size
            with path.open("rb") as handle:
                header = handle.read(10)
                tag_total = self._id3v2_tag_total(header)
                if tag_total is None or tag_total >= size:
                    return False
                handle.seek(tag_total)
                probe = handle.read(2)
        except Exception:
            return False
        return len(probe) == 2 and probe[0] == 0xFF and (probe[1] & 0xE0) == 0xE0

    def scan_chants_audio_files(self) -> list[Path]:
        """List every MP3 under FSW/Chants that fix_chants_audio_files would
        actually touch, without loading full file contents -- cheap enough to
        run before showing the user a confirmation dialog."""
        root = self.app.exedir / "FSW" / "Chants"
        if not root.exists():
            return []
        return [
            path
            for path in sorted(root.rglob("*.mp3"))
            if not path.name.endswith(".original.mp3") and self._needs_fix(path)
        ]

    def fix_chants_audio_files(self, paths: list[Path] | None = None, keep_backup: bool = True) -> dict[str, int]:
        """Strip ID3v2 tags from `paths` (or every MP3 under FSW/Chants when
        `paths` is None) so MCI stops silently refusing to open them. When
        `keep_backup` is set, keeps a `<name>.original.mp3` backup of anything
        it touches, matching the restore-sidecar convention used elsewhere in
        this codebase; when unset, overwrites in place with no backup."""
        app = self.app
        if paths is None:
            root = app.exedir / "FSW" / "Chants"
            paths = (
                [p for p in sorted(root.rglob("*.mp3")) if not p.name.endswith(".original.mp3")]
                if root.exists()
                else []
            )
        counts = {"fixed": 0, "already_clean": 0, "errors": 0}
        for path in paths:
            try:
                data = path.read_bytes()
            except Exception as exc:
                app.log(f"Fix chants audio: failed to read {path}", exc, exc_info=sys.exc_info())
                counts["errors"] += 1
                continue
            try:
                stripped = self._strip_leading_id3v2(data)
            except Exception as exc:
                app.log(f"Fix chants audio: failed to parse {path}", exc, exc_info=sys.exc_info())
                counts["errors"] += 1
                continue
            if stripped is None:
                counts["already_clean"] += 1
                continue
            try:
                if keep_backup:
                    backup = path.with_name(path.stem + ".original" + path.suffix)
                    if not backup.exists():
                        shutil.copy2(path, backup)
                path.write_bytes(stripped)
                counts["fixed"] += 1
                app.log(f"Fix chants audio: stripped ID3v2 tag from {path}")
            except Exception as exc:
                app.log(f"Fix chants audio: failed to rewrite {path}", exc, exc_info=sys.exc_info())
                counts["errors"] += 1
        return counts

    def _track_live_match(self, memory: Memory) -> None:
        """Feed LiveMatchTracker one reading and log when its verdict flips."""
        app = self.app
        try:
            started = memory.get_int(app.offsets.GAMESTARTEDBINARYBASE, app.offsets.GAMESTARTEDBINARY)
        except Exception:
            started = None
        try:
            clock = memory.get_int(app.offsets.GAMESTATSBASE, app.offsets.GAMERANTIME)
        except Exception:
            clock = None
        play_state, period_seconds = read_open_play_inputs(memory, app.offsets)
        was_live = self._live_match.live
        live = self._live_match.update(started, play_state, clock, period_seconds)
        if live != was_live:
            verdict = "kick-off confirmed" if live else "no longer in memory"
            app.log(f"Chants live match: {verdict} (started={started} state={play_state} clock={clock})")

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

    def _resolve_pending_entrance_arm(self) -> None:
        """Consume a still-armed Team Entrance the moment a match is
        confirmed live again, instead of waiting on a page-name transition
        that may never come.

        `_handle_page_transition` (app_game.py) normally consumes an armed
        Team Entrance on whatever DIFFERENT page name shows up next. That
        only works if a different page name actually arrives. Confirmed
        live 2026-08-30 (runtime/server16.log, 13:22:27-13:23:01): FIFA can
        keep reporting the exact same blank page name for 30+ seconds while
        the player simply sits in the pause menu deciding -- so a fixed
        timeout can't safely distinguish "genuinely stuck, nothing else is
        coming" from "still mid-pause, a menu transition is coming eventually".
        A follow-up capture (13:23:36-13:23:57) showed a mid-match Restart
        can *also* resume gameplay while still reading that exact same blank
        page it paused on, with no further transition at all for the rest of
        the session -- so `_handle_page_transition` never got a second
        chance to consume the arm either.

        `app.matchstarted` flipping back to True here (this method is only
        called on that exact transition, see chants_runtime_loop) is itself
        proof a real match -- the same one resumed, or a freshly restarted
        one -- is live again, independent of whether the page name ever
        changes. That makes it a reliable, event-driven point to resolve
        whatever arm is still pending, using the page name that's current
        right now. See CLAUDE.md §7 Part 8 before changing this.
        """
        app = self.app
        if not getattr(app, "_entrance_armed", False):
            return
        page_name = getattr(app, "lastpagename", "") or ""
        if "TV/bumper" in page_name:
            # Bumper hasn't ended yet -- its own eventual transition to a
            # different page name is a reliable, distinctly-named event, so
            # leave it to _handle_page_transition rather than risk starting
            # over FIFA's own competition intro audio.
            return
        app._entrance_armed = False
        if app._page_blocks_team_entrance(page_name):
            app.log(f"Team entrance disarmed (match resumed on a menu page): {page_name!r}")
            return
        app.log(f"Team entrance armed via match-resumed signal (no further page transition): {page_name!r}")
        app._start_team_entrance()

    def _log_clock_diagnostic(self, memory: Memory, now: float | None = None) -> None:
        """Log what the match clock (GAMERANTIME) is actually doing, averaged
        over a few seconds, together with everything the pre-match guard
        decides on.

        Diagnostic only -- it changes no behaviour. The open "Support chants
        stuck on Waiting for kick-off" reports (docs/bugs-entrance.md Parts
        14-18) could never be settled from a log because nothing recorded
        the clock while the guard waited: not its rate during the walkout,
        not whether it restarts at kick-off, not its rate in play for each
        Half Length. The guard's own check samples an integer clock every
        ~0.2s, where it can only ever compute 0, ~4.8 or ~9.5 units/s, so
        its "speed" says little; this line uses a 2-5s window instead.

        A clock that stops moving is logged once ("+0") and then stays quiet
        until something changes, so sitting in a menu does not flood the
        log. No line is written while a goal song holds the loop -- the
        next one just covers a longer window.

        Two more read-only candidates for a real kick-off signal ride on the
        same line: `dash=` is the DASHBOARDMINUTES/DASHBOARDSECONDS pair
        (inherited offsets nothing else reads, validity on this build
        unknown), and `stats[...]` is the window of values around the score
        and clock (see CLOCK_DIAG_STATS_START) -- dumped in full the first
        time, afterwards only the ones that changed, as `+offset:old>new`.
        """
        app = self.app
        now = time.time() if now is None else now
        guard = bool(getattr(app, "_entrance_pre_match_guard", False))
        interval = self.CLOCK_DIAG_GUARD_INTERVAL if guard else self.CLOCK_DIAG_INTERVAL
        last = self._clock_diag_last
        if last is not None and now - last[0] < interval:
            return
        try:
            started = memory.get_int(app.offsets.GAMESTARTEDBINARYBASE, app.offsets.GAMESTARTEDBINARY)
        except Exception:
            started = None
        try:
            clock = memory.get_int(app.offsets.GAMESTATSBASE, app.offsets.GAMERANTIME)
        except Exception:
            clock = None
        self._clock_diag_last = (now, clock)
        entrance = bool(getattr(app, "_entrance_active", False))
        page_name = getattr(app, "lastpagename", "") or ""
        if last is None:
            movement = "first sample"
            frozen = False
        elif clock is None or last[1] is None:
            movement = "no previous reading" if clock is not None else "unreadable"
            frozen = clock is None and last[1] is None
        else:
            elapsed = max(0.001, now - last[0])
            delta = clock - last[1]
            movement = f"{delta:+d} in {elapsed:.1f}s = {delta / elapsed:.1f}/s"
            frozen = delta == 0
        dash_minutes = self._read_clock_diag_int(memory, "DASHBOARDMINUTESBASE", "DASHBOARDMINUTES")
        dash_seconds = self._read_clock_diag_int(memory, "DASHBOARDSECONDSBASE", "DASHBOARDSECONDS")
        stats = self._read_clock_diag_stats(memory)
        previous_stats = self._clock_diag_stats_last
        self._clock_diag_stats_last = stats
        key = (started, clock, guard, entrance, page_name, dash_minutes, dash_seconds, stats)
        if frozen:
            if key == self._clock_diag_frozen_key:
                return
            self._clock_diag_frozen_key = key
        else:
            self._clock_diag_frozen_key = None
        app.log(
            f"Chants clock: started={started} clock={clock} ({movement}) "
            f"guard={guard} entrance={entrance} page={page_name!r} "
            f"dash={dash_minutes}:{dash_seconds} stats[{self._format_clock_diag_stats(previous_stats, stats)}]"
        )

    def _read_clock_diag_int(self, memory: Memory, base_attr: str, offsets_attr: str) -> int | None:
        try:
            return memory.get_int(getattr(self.app.offsets, base_attr), getattr(self.app.offsets, offsets_attr))
        except Exception:
            return None

    def _read_clock_diag_stats(self, memory: Memory) -> tuple[int, ...] | None:
        try:
            address = memory.resolve_pointer(self.app.offsets.GAMESTATSBASE, [self.CLOCK_DIAG_STATS_START])
            raw = memory.read_process_memory(address, self.CLOCK_DIAG_STATS_COUNT * 4)
            return struct.unpack(f"<{self.CLOCK_DIAG_STATS_COUNT}I", raw)
        except Exception:
            return None

    def _format_clock_diag_stats(self, previous: tuple[int, ...] | None, current: tuple[int, ...] | None) -> str:
        if current is None:
            return "unreadable"
        offsets = range(self.CLOCK_DIAG_STATS_START, self.CLOCK_DIAG_STATS_START + len(current) * 4, 4)
        if previous is None:
            return " ".join(f"+{offset}={value}" for offset, value in zip(offsets, current))
        changed = [
            f"+{offset}:{old}>{new}"
            for offset, old, new in zip(offsets, previous, current)
            if old != new
        ]
        return " ".join(changed) if changed else "="

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
        chants_memory: "Memory | None" = None,
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
            non_running_count = 0
            player_paused = False
            speed_hits = 0
            last_game_time: int | None = None
            last_real_time: float | None = None
            started_at = time.time()
            while not app._chants_stop.is_set() and not getattr(app, "_chants_reset_requested", False) and app.module_enabled("Chants"):
                if chants_memory is not None:
                    # This loop holds chants_runtime_loop for the whole song.
                    self._track_live_match(chants_memory)
                mode_state = player.mode()
                if mode_state in {"stopped", "closed"} and time.time() >= hold_until:
                    break
                if time.time() >= hard_until:
                    break
                if chants_memory is not None:
                    is_running = app._is_game_running_with(chants_memory)
                    if not is_running:
                        # Pause menu: game stopped — pause and reset timer tracking
                        non_running_count += 1
                        last_game_time = None
                        last_real_time = None
                        speed_hits = 0
                        if non_running_count >= 3 and not player_paused and player.is_playing():
                            self.fade_player(player, volume, 0, 400)
                            player.pause()
                            player_paused = True
                            app._set_display_async("audio_crowd_mode", "Paused")
                            app._set_display_async("audio_next", "Resume on return")
                    else:
                        non_running_count = 0
                        if player_paused and player.is_paused():
                            player.resume()
                            self.fade_player(player, 0, volume, 300)
                            player_paused = False
                            app._set_display_async("audio_crowd_mode", mode)
                            app._set_display_async("audio_next", next_text)
                        # Kick-off detection via timer speed (same logic as v1.1.0)
                        # After 6s protection window, normal gameplay runs at ~8-10 timer units/sec
                        # while celebration runs at ~1 timer unit/sec
                        now = time.time()
                        elapsed = now - started_at
                        if elapsed >= 6.0:
                            try:
                                game_time = chants_memory.get_int(app.offsets.GAMESTATSBASE, app.offsets.GAMERANTIME)
                            except Exception:
                                game_time = None
                            if game_time is not None and last_game_time is not None and last_real_time is not None:
                                real_delta = max(0.001, now - last_real_time)
                                timer_delta = abs(game_time - last_game_time)
                                speed = timer_delta / real_delta
                                if speed >= 6.0 and timer_delta >= 1:
                                    speed_hits += 1
                                else:
                                    speed_hits = 0
                                if speed_hits >= 3:
                                    app.log(f"Goal audio cut: kick-off detected speed={speed:.1f} hits={speed_hits}")
                                    time.sleep(0.5)
                                    break
                            last_game_time = game_time
                            last_real_time = now
                        else:
                            # Within protection window — record baseline but don't cut
                            try:
                                last_game_time = chants_memory.get_int(app.offsets.GAMESTATSBASE, app.offsets.GAMERANTIME)
                            except Exception:
                                last_game_time = None
                            last_real_time = now
                            speed_hits = 0
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
        pre_match_last_time: int | None = None
        pre_match_last_real: float | None = None
        pre_match_speed_hits = 0
        pre_match_open_play = OpenPlayDetector()
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
                    self._live_match.forget()
                    time.sleep(0.5)
                    continue

                self._track_live_match(chants_memory)
                self._log_clock_diagnostic(chants_memory)

                hid = (app.HID or "").split()[0].strip() if app.HID and app.HID.strip() else ""
                aid = (app.AID or "").split()[0].strip() if app.AID and app.AID.strip() else ""
                home_chants = app.settings_ini.read(hid, "chantsid") if hid and app.settings_ini.key_exists(hid, "chantsid") else ""
                away_chants = app.settings_ini.read(aid, "chantsid") if aid and app.settings_ini.key_exists(aid, "chantsid") else ""

                if not app._is_game_running_with(chants_memory):
                    non_running_reads += 1
                    pre_match_last_time = None
                    pre_match_last_real = None
                    pre_match_speed_hits = 0
                    pre_match_open_play.reset()
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
                was_matchstarted = app.matchstarted
                app.matchstarted = True
                if not was_matchstarted:
                    self._resolve_pending_entrance_arm()

                # The FIFA "game started" flag becomes true during the 3D
                # walkout, before actual kick-off.  Do not let a Support track
                # cover the entrance anthem or the league presentation.  Real
                # play is confirmed by FIFA's own play state -- the ball in
                # play (OpenPlayDetector) in a match whose kick-off was seen
                # (LiveMatchTracker; the practice arena has none) -- or, as
                # before, by sustained fast match-clock movement, which alone
                # never fired on a long Half Length.
                if getattr(app, "_entrance_pre_match_guard", False):
                    now = time.time()
                    try:
                        game_time = chants_memory.get_int(app.offsets.GAMESTATSBASE, app.offsets.GAMERANTIME)
                    except Exception:
                        game_time = None
                    play_state, period_seconds = read_open_play_inputs(chants_memory, app.offsets)
                    ball_in_play = pre_match_open_play.update(play_state, period_seconds)
                    if ball_in_play and self._live_match.live:
                        app._entrance_pre_match_guard = False
                        next_chant_after = time.time() + 1.0
                        app.log(f"Pre-match Support guard released: ball in play (period clock={period_seconds})")
                    elif game_time is not None and pre_match_last_time is not None and pre_match_last_real is not None:
                        real_delta = max(0.001, now - pre_match_last_real)
                        timer_delta = abs(game_time - pre_match_last_time)
                        speed = timer_delta / real_delta
                        if timer_delta >= 1 and speed >= 6.0:
                            pre_match_speed_hits += 1
                        else:
                            pre_match_speed_hits = 0
                        if pre_match_speed_hits >= 3:
                            app._entrance_pre_match_guard = False
                            next_chant_after = time.time() + 1.0
                            app.log(f"Pre-match Support guard released at clock speed={speed:.1f}")
                    pre_match_last_time = game_time
                    pre_match_last_real = now
                    if getattr(app, "_entrance_pre_match_guard", False):
                        app._set_display_async("audio_crowd_mode", "Waiting for kick-off")
                        app._set_display_async("audio_next", "Support chants after actual kick-off")
                        time.sleep(0.2)
                        continue
                # Whoever released the guard (here or the entrance worker), the
                # next wait must measure its own gain from scratch.
                pre_match_open_play.reset()

                # The entrance anthem owns the pre-kickoff audio window.  If
                # FIFA starts its clock while the anthem is fading, hold the
                # regular crowd loop briefly so the two MCI players do not
                # overlap at full volume.
                if getattr(app, "_entrance_active", False):
                    app._set_display_async("audio_crowd_mode", "Waiting for entrance")
                    app._set_display_async("audio_next", "Crowd audio after entrance")
                    time.sleep(0.2)
                    continue

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
                        club_song_played = False
                        if scorer == hid or app.module_enabled("AwayClubSong"):
                            club_song_played = self._play_club_song(scorer, chants_memory=chants_memory)
                        if scorer == aid and away_chants and app.module_enabled("AwayChants"):
                            self._play_away_reaction(away_chants, score_home, score_away, skip_random=club_song_played, chants_memory=chants_memory)
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

    def _play_club_song(self, team_id: str, chants_memory: "Memory | None" = None) -> bool:
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
                chants_memory=chants_memory,
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

    def _play_away_reaction(self, away_chants: str, score_home: int, score_away: int, skip_random: bool = False, chants_memory: "Memory | None" = None) -> bool:
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
                chants_memory=chants_memory,
            )
            return played
        except Exception as exc:
            app.log("Away reaction failed", exc, exc_info=sys.exc_info())
            return False
