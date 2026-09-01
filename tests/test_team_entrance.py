from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from server16_py.entrance_runtime import TeamEntranceConfig, TeamEntranceRuntime


class FakeIni:
    def __init__(self, values: dict[tuple[str, str], str] | None = None) -> None:
        self.values = values or {}

    def key_exists(self, key: str, section: str) -> bool:
        return (key, section) in self.values

    def read(self, key: str, section: str) -> str:
        return self.values.get((key, section), "")


class FakePlayer:
    def __init__(self) -> None:
        self.opened: Path | None = None
        self.played = False
        self.stopped = False
        self.closed = False
        self.volumes: list[float] = []
        self.pause_calls = 0
        self.resume_calls = 0
        self._mode = "closed"

    def open(self, path: Path) -> None:
        self.opened = path
        self._mode = "closed"

    def length_ms(self) -> int:
        return 60_000

    def set_volume(self, volume: float) -> None:
        self.volumes.append(volume)

    def play(self) -> None:
        self.played = True
        self._mode = "playing"

    def mode(self) -> str:
        return self._mode

    def is_playing(self) -> bool:
        return self._mode == "playing"

    def is_paused(self) -> bool:
        return self._mode == "paused"

    def pause(self) -> None:
        self.pause_calls += 1
        self._mode = "paused"

    def resume(self) -> None:
        self.resume_calls += 1
        self._mode = "playing"

    def stop(self) -> None:
        self.stopped = True
        self._mode = "stopped"

    def close(self) -> None:
        self.closed = True
        self._mode = "closed"


class FakeMemory:
    """A ``None`` entry simulates the match's pointer chain no longer
    resolving (e.g. after Abandon/Restart unloads the match): both get_int
    calls raise, and the index does not advance past it, matching how a real
    dangling pointer keeps failing on every subsequent read."""

    def __init__(self, states: list[tuple[int, int] | None]) -> None:
        self.states = list(states)
        self.state_index = 0
        self.closed = False

    def attack(self, _process: str) -> bool:
        return True

    def is_open(self) -> bool:
        return True

    def get_int(self, base, offsets) -> int:
        state = self.states[min(self.state_index, len(self.states) - 1)]
        if base == "stats" and offsets == "time":
            if state is None:
                raise RuntimeError("match memory unresolvable")
            self.state_index += 1
            return state[1]
        if state is None:
            raise RuntimeError("match memory unresolvable")
        return state[0]

    def close(self) -> None:
        self.closed = True


class FakeChantsRuntime:
    def __init__(self) -> None:
        self.fades: list[tuple[float, float, int]] = []

    def fade_player(self, _player, start: float, end: float, duration_ms: int) -> None:
        self.fades.append((start, end, duration_ms))


class FakeApp:
    def __init__(self, root: Path, ini: FakeIni | None = None) -> None:
        self.exedir = root
        self.settings_ini = ini or FakeIni()
        self.HID = "1"
        self.AID = "2"
        self.TOURNAME = "0"
        self.TOURROUNDID = "0"
        self.MP = "fifa16"
        self._kickoff_generation = 4
        self._entrance_sequence = 2
        self._entrance_active = False
        self._entrance_armed = False
        self._entrance_pre_match_guard = True
        self.lastpagename = ""
        self.offsets = SimpleNamespace(
            GAMESTARTEDBINARYBASE="started",
            GAMESTARTEDBINARY="flag",
            GAMESTATSBASE="stats",
            GAMERANTIME="time",
        )
        self.chants_runtime = FakeChantsRuntime()
        self.displays: dict[str, str] = {}
        self.logs: list[str] = []
        self.enabled = True

    def module_enabled(self, name: str) -> bool:
        return name == "TeamEntrance" and self.enabled

    def _set_display_async(self, key: str, value: str) -> None:
        self.displays[key] = value

    def log(self, message: str, *_args, **_kwargs) -> None:
        self.logs.append(message)


class TeamEntranceRuntimeTests(unittest.TestCase):
    def test_old_chantsid_uses_entrance_defaults(self) -> None:
        parsed = TeamEntranceRuntime._parse_values(
            "Arsenal,0.12,0.15,0.10,0.05,0.15,0.13,0.15,8.0,0.35"
        )
        self.assertEqual(parsed, ("Arsenal", 0.16, 7.0))

    def test_extended_chantsid_is_clamped(self) -> None:
        parsed = TeamEntranceRuntime._parse_values(
            "Club,0,0,0,0,0,0,0,0,0,4.5,-3"
        )
        self.assertEqual(parsed, ("Club", 1.0, 0.0))

    def test_resolve_config_requires_exact_entrance_filename(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            track = root / "FSW" / "Chants" / "Arsenal" / "Entrance.mp3"
            track.parent.mkdir(parents=True)
            track.write_bytes(b"test")
            ini = FakeIni({("1", "chantsid"): "Arsenal,0,0,0,0,0,0,0,0,0,0.25,5.5"})
            runtime = TeamEntranceRuntime(FakeApp(root, ini))
            config = runtime._resolve_config("1")
            self.assertEqual(config, TeamEntranceConfig(track, 0.25, 5.5))
            self.assertIsNone(runtime._resolve_config("2"))

    def test_start_for_match_noops_when_only_entrance_sequence_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            track = root / "FSW" / "Chants" / "Arsenal" / "Entrance.mp3"
            track.parent.mkdir(parents=True)
            track.write_bytes(b"test")
            ini = FakeIni({("1", "chantsid"): "Arsenal,0,0,0,0,0,0,0,0,0,0.2,0"})
            app = FakeApp(root, ini)
            stale_player = FakePlayer()
            stale_player.play()
            memory = FakeMemory([(1, 1)])
            runtime = TeamEntranceRuntime(
                app,
                player_factory=lambda: FakePlayer(),
                memory_factory=lambda: memory,
            )

            # Simulate the previous match's worker still alive (e.g. paused
            # mid-walkout in FluxHub) when Restart is chosen *without* going
            # through KickOffHub -- e.g. Restart selected during the walkout,
            # before kick-off, which FIFA can resolve by skipping the intro
            # animation entirely and dropping straight back into the same
            # blank page the walkout was already on. That page re-triggers
            # app_game.py's blank-page arm fallback, bumping
            # `_entrance_sequence` even though `_kickoff_generation` (only
            # bumped by a real KickOffHub visit) is unchanged and the home
            # team is unchanged. _match_key() deliberately ignores
            # `_entrance_sequence` for exactly this reason (see its
            # docstring), so this must resolve to the SAME match and be a
            # no-op -- confirmed live 2026-08-30 (runtime/server16.log,
            # 13:45:42-13:46:05): before this fix, this exact sequence
            # replayed the entrance anthem from scratch deep into an
            # already-live match. See CLAUDE.md §7.
            runtime._worker_running = True
            runtime._started_match_key = runtime._match_key("1")
            runtime._player = stale_player
            runtime._target_volume = 0.2
            app._entrance_active = True
            app._entrance_sequence += 1

            with patch("server16_py.entrance_runtime.threading.Thread") as thread_cls:
                started = runtime.start_for_match()

            self.assertFalse(started)
            thread_cls.assert_not_called()
            self.assertFalse(stale_player.stopped)
            self.assertFalse(stale_player.closed)
            self.assertFalse(any("cancelling previous match" in line for line in app.logs))

    def test_start_for_match_noops_for_same_match_after_worker_already_finished(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            track = root / "FSW" / "Chants" / "Arsenal" / "Entrance.mp3"
            track.parent.mkdir(parents=True)
            track.write_bytes(b"test")
            ini = FakeIni({("1", "chantsid"): "Arsenal,0,0,0,0,0,0,0,0,0,0.2,0"})
            app = FakeApp(root, ini)
            memory = FakeMemory([(1, 1)])
            runtime = TeamEntranceRuntime(
                app,
                player_factory=lambda: FakePlayer(),
                memory_factory=lambda: memory,
            )

            # The worker for this match already played the anthem in full and
            # exited on its own (real kick-off detected, `_worker_running`
            # back to False) -- unlike the previous test, there is no worker
            # left alive to guard against a spurious re-arm. A later
            # re-arm for the SAME match (e.g. the blank-page arm fallback in
            # app_game.py firing again because `matchstarted` hadn't yet
            # caught up to a routine, brief pause-menu open/close -- no
            # `_kickoff_generation` change, so still the same match_key) must
            # still be a no-op, or it replays Entrance.mp3 from scratch for
            # an instant before its own kick-off detection fades it right
            # back out. Confirmed live 2026-08-30 (runtime/server16.log,
            # 14:09:02-14:09:42): several one-second replays of the anthem,
            # none of them an actual Restart. See CLAUDE.md §7.
            runtime._worker_running = False
            runtime._started_match_key = runtime._match_key("1")

            with patch("server16_py.entrance_runtime.threading.Thread") as thread_cls:
                started = runtime.start_for_match()

            self.assertFalse(started)
            thread_cls.assert_not_called()
            self.assertFalse(any("cancelling previous match" in line for line in app.logs))

    def test_start_for_match_cancels_stale_worker_for_new_kickoff_generation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            track = root / "FSW" / "Chants" / "Arsenal" / "Entrance.mp3"
            track.parent.mkdir(parents=True)
            track.write_bytes(b"test")
            ini = FakeIni({("1", "chantsid"): "Arsenal,0,0,0,0,0,0,0,0,0,0.2,0"})
            app = FakeApp(root, ini)
            stale_player = FakePlayer()
            stale_player.play()
            memory = FakeMemory([(1, 1)])
            runtime = TeamEntranceRuntime(
                app,
                player_factory=lambda: FakePlayer(),
                memory_factory=lambda: memory,
            )

            # A genuinely new match -- e.g. Abandon/Restart routed back
            # through KickOffHub, or a fresh match from the main menu --
            # bumps `_kickoff_generation` (app_game.py, only on a real
            # KickOffHub visit). This must still cancel the stale worker and
            # start a new one.
            runtime._worker_running = True
            runtime._started_match_key = runtime._match_key("1")
            runtime._player = stale_player
            runtime._target_volume = 0.2
            app._entrance_active = True
            app._kickoff_generation += 1

            with patch("server16_py.entrance_runtime.threading.Thread") as thread_cls:
                started = runtime.start_for_match()

            self.assertTrue(started)
            thread_cls.assert_called_once()
            thread_cls.return_value.start.assert_called_once()
            self.assertTrue(stale_player.stopped)
            self.assertTrue(stale_player.closed)
            self.assertTrue(any("cancelling previous match" in line for line in app.logs))

    def test_worker_plays_then_fades_when_kickoff_starts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            track = root / "Entrance.mp3"
            track.write_bytes(b"test")
            app = FakeApp(root)
            player = FakePlayer()
            # FIFA may already report started=1 during the walkout.  A static
            # clock must be accepted, then sustained clock movement fades the
            # anthem at real kick-off.
            memory = FakeMemory([(1, 1), (1, 1), (1, 2), (1, 3), (1, 4), (1, 5)])
            runtime = TeamEntranceRuntime(
                app,
                player_factory=lambda: player,
                memory_factory=lambda: memory,
            )
            config = TeamEntranceConfig(track, 0.2, 0.0)

            with patch("server16_py.entrance_runtime.time.sleep", return_value=None):
                runtime._run_worker(0, "1", config)

            self.assertEqual(player.opened, track)
            self.assertTrue(player.played)
            self.assertTrue(player.stopped)
            self.assertTrue(player.closed)
            self.assertTrue(memory.closed)
            self.assertFalse(app._entrance_active)
            self.assertFalse(app._entrance_pre_match_guard)
            self.assertIn((0, 0.2, 500), app.chants_runtime.fades)
            self.assertIn((0.2, 0, 700), app.chants_runtime.fades)
            self.assertTrue(any("kick-off clock detected" in line for line in app.logs))

    def test_worker_never_opens_track_when_match_already_live_before_delay_elapses(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            track = root / "Entrance.mp3"
            track.write_bytes(b"test")
            app = FakeApp(root)
            player = FakePlayer()
            # Skipping the pre-kickoff presentation (formations/walkout) can
            # drop the player into a genuinely live match before this
            # worker's configured delay (3s here) elapses. Ported-fork
            # ("Walkout") report: its equivalent wait was a bare
            # time.sleep(10.0) with no state check at all, so the track
            # always opened and played regardless -- exactly the bug being
            # fixed here. The same "timer_delta >= 1 and speed >= 6.0, three
            # consecutive hits" signal the playback loop already trusts for
            # kick-off detection must also apply *during* the delay wait, so
            # Entrance.mp3 is never opened at all once the match is already
            # running at live-gameplay speed.
            memory = FakeMemory(
                [
                    (1, 100),  # consumed by _wait_for_presentation
                    (1, 100),  # delay iter1: baseline
                    (1, 108),  # delay iter2: speed hit 1
                    (1, 116),  # delay iter3: speed hit 2
                    (1, 124),  # delay iter4: speed hit 3 -> abort before playing
                ]
            )
            runtime = TeamEntranceRuntime(
                app,
                player_factory=lambda: player,
                memory_factory=lambda: memory,
            )
            config = TeamEntranceConfig(track, 0.2, 3.0)

            fake_now = [1_000_000.0]

            def fake_time() -> float:
                return fake_now[0]

            def fake_sleep(_seconds: float) -> None:
                fake_now[0] += 0.2

            with patch("server16_py.entrance_runtime.time.sleep", side_effect=fake_sleep), \
                 patch("server16_py.entrance_runtime.time.time", side_effect=fake_time):
                runtime._run_worker(0, "1", config)

            self.assertIsNone(player.opened)
            self.assertFalse(player.played)
            self.assertFalse(app._entrance_active)
            self.assertTrue(memory.closed)
            self.assertTrue(any("match already live" in line for line in app.logs))

    def test_worker_plays_normally_when_delay_elapses_with_static_clock(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            track = root / "Entrance.mp3"
            track.write_bytes(b"test")
            app = FakeApp(root)
            player = FakePlayer()
            player.length_ms = lambda: 1000  # keep hard_deadline short below
            # The ordinary, non-skipped path: the clock stays static/frozen
            # throughout the whole delay window (exactly what the walkout
            # looks like). Once past `deadline`, every further read clamps to
            # this same last entry (see FakeMemory), so the new pre-play
            # kick-off check must never false-positive on a frozen clock and
            # must let playback start normally once the delay elapses.
            memory = FakeMemory(
                [
                    (1, 1),  # consumed by _wait_for_presentation
                    (1, 1),  # delay: repeats (clamped) until the deadline passes
                ]
            )
            runtime = TeamEntranceRuntime(
                app,
                player_factory=lambda: player,
                memory_factory=lambda: memory,
            )
            config = TeamEntranceConfig(track, 0.2, 0.8)

            fake_now = [1_000_000.0]

            def fake_time() -> float:
                return fake_now[0]

            def fake_sleep(_seconds: float) -> None:
                fake_now[0] += 0.2

            with patch("server16_py.entrance_runtime.time.sleep", side_effect=fake_sleep), \
                 patch("server16_py.entrance_runtime.time.time", side_effect=fake_time):
                runtime._run_worker(0, "1", config)

            self.assertEqual(player.opened, track)
            self.assertTrue(player.played)
            self.assertFalse(any("match already live" in line for line in app.logs))

    def test_worker_pauses_on_pause_menu_and_resumes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            track = root / "Entrance.mp3"
            track.write_bytes(b"test")
            app = FakeApp(root)
            player = FakePlayer()
            # The clock keeps reading as static/low the whole time (exactly
            # what a real pre-kickoff walkout looks like) so that a state-based
            # pause check would misfire; only the page-name pause-menu tokens
            # below should ever pause the anthem. The match state is read
            # every loop tick (even while paused, to catch Abandon/Restart —
            # see the tests below), so one entry is consumed per iteration:
            # presentation-wait, then iter1..iter10. Resume trusts the same
            # page-name signal pausing uses, with a 3-tick debounce (iter5-7,
            # symmetric with the 3-tick pause-entry debounce) instead of the
            # clock-speed heuristic reserved for kick-off detection below
            # (iter8-10) — that heuristic can only ever be satisfied once real
            # kick-off has already happened, so requiring it to *resume* used
            # to leave the anthem muted for the rest of the walkout every time
            # it was paused (confirmed live 2026-08-28; see CLAUDE.md §7).
            memory = FakeMemory(
                [
                    (1, 1),  # consumed by _wait_for_presentation
                    (1, 1),  # iter1: warm up (kick-off baseline set)
                    (1, 1),  # iter2: paused (fluxhub, count=1) -> baseline cleared
                    (1, 1),  # iter3: paused (fluxhub, count=2)
                    (1, 1),  # iter4: paused (fluxhub, count=3 -> pause fires)
                    (1, 1),  # iter5: fluxhub gone, resume debounce tick 1 -> stays muted
                    (1, 1),  # iter6: resume debounce tick 2 -> stays muted
                    (1, 1),  # iter7: resume debounce tick 3 -> resume fires, kickoff baseline reset
                    (1, 2),  # iter8: kickoff speed hit 1
                    (1, 3),  # iter9: kickoff speed hit 2
                    (1, 4),  # iter10: kickoff speed hit 3 -> fade-out
                ]
            )
            runtime = TeamEntranceRuntime(
                app,
                player_factory=lambda: player,
                memory_factory=lambda: memory,
            )
            config = TeamEntranceConfig(track, 0.2, 0.0)

            # FluxHub (FIFA's own pause menu) shows for three consecutive
            # polls, matching ChantsRuntime's debounce, then closes again.
            # Each entry is consumed by the loop's time.sleep(0.2) call, i.e.
            # it's the page name in effect for the *next* iteration.
            page_sequence = iter(
                [
                    "game/screens/fluxHub/FluxHub",
                    "game/screens/fluxHub/FluxHub",
                    "game/screens/fluxHub/FluxHub",
                    "",
                ]
            )

            def fake_sleep(_seconds: float) -> None:
                app.lastpagename = next(page_sequence, app.lastpagename)

            with patch("server16_py.entrance_runtime.time.sleep", side_effect=fake_sleep):
                runtime._run_worker(0, "1", config)

            self.assertEqual(player.pause_calls, 1)
            self.assertEqual(player.resume_calls, 1)
            self.assertIn((0.2, 0, 400), app.chants_runtime.fades)
            self.assertIn((0, 0.2, 300), app.chants_runtime.fades)
            self.assertTrue(any("kick-off clock detected" in line for line in app.logs))

    def test_worker_stops_completely_when_match_ends_while_paused(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            track = root / "Entrance.mp3"
            track.write_bytes(b"test")
            app = FakeApp(root)
            player = FakePlayer()
            # FluxHub opens (pause fires), then the match's own memory stops
            # resolving entirely — simulating Abandon/Restart chosen from the
            # pause menu, which doesn't reliably route back through the exact
            # "KickOffHub" page that would normally cancel this worker via
            # app_game.py. It must stop for good instead of resuming once
            # FluxHub happens to disappear, or looping forever waiting for a
            # kick-off that will never come.
            memory = FakeMemory(
                [
                    (1, 1),  # consumed by _wait_for_presentation
                    (1, 1),  # iter1: warm up
                    (1, 1),  # iter2: paused (fluxhub, count=1)
                    (1, 1),  # iter3: paused (fluxhub, count=2)
                    (1, 1),  # iter4: paused (fluxhub, count=3 -> pause fires)
                    None,    # iter5-7: unresolvable (index doesn't advance
                             # past a None entry) -> stop for good at count=3
                ]
            )
            runtime = TeamEntranceRuntime(
                app,
                player_factory=lambda: player,
                memory_factory=lambda: memory,
            )
            config = TeamEntranceConfig(track, 0.2, 0.0)

            # The page name never has to change for this scenario to
            # reproduce the bug: the match state itself is what disappears
            # while the Abandon confirmation is still showing over FluxHub.
            def fake_sleep(_seconds: float) -> None:
                app.lastpagename = "game/screens/fluxHub/FluxHub"

            with patch("server16_py.entrance_runtime.time.sleep", side_effect=fake_sleep):
                runtime._run_worker(0, "1", config)

            self.assertEqual(player.pause_calls, 1)
            self.assertEqual(player.resume_calls, 0)
            self.assertTrue(player.stopped)
            self.assertTrue(player.closed)
            self.assertTrue(memory.closed)
            self.assertFalse(app._entrance_active)
            self.assertTrue(any("Team entrance stopped: match ended" in line for line in app.logs))

    def test_worker_gives_up_when_fluxhub_never_closes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            track = root / "Entrance.mp3"
            track.write_bytes(b"test")
            app = FakeApp(root)
            player = FakePlayer()
            # FluxHub debounces open (pause fires) and then simply never
            # closes again (e.g. the user leaves the console idle on the
            # pause menu). Resume is page-name-driven now, so the only thing
            # that can end this is the PAUSE_GIVEUP_SECONDS safety net —
            # verify it still fires and the worker doesn't wait forever.
            memory = FakeMemory([(1, 1)])
            runtime = TeamEntranceRuntime(
                app,
                player_factory=lambda: player,
                memory_factory=lambda: memory,
            )
            runtime.PAUSE_GIVEUP_SECONDS = 5.0
            config = TeamEntranceConfig(track, 0.2, 0.0)

            # A fake clock that advances by 1s per tick, driven off the same
            # time.sleep call the loop already uses to pace itself, so the
            # test doesn't actually wait PAUSE_GIVEUP_SECONDS in real time.
            fake_now = [1_000_000.0]

            def fake_time() -> float:
                return fake_now[0]

            def fake_sleep(_seconds: float) -> None:
                fake_now[0] += 1.0
                app.lastpagename = "game/screens/fluxHub/FluxHub"

            with patch("server16_py.entrance_runtime.time.sleep", side_effect=fake_sleep), \
                 patch("server16_py.entrance_runtime.time.time", side_effect=fake_time):
                runtime._run_worker(0, "1", config)

            self.assertEqual(player.pause_calls, 1)
            self.assertEqual(player.resume_calls, 0)
            self.assertTrue(player.stopped)
            self.assertTrue(player.closed)
            self.assertFalse(app._entrance_active)
            self.assertTrue(any("did not resume" in line for line in app.logs))

    def test_worker_resume_via_page_name_still_stops_if_match_then_ends(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            track = root / "Entrance.mp3"
            track.write_bytes(b"test")
            app = FakeApp(root)
            player = FakePlayer()
            # Resume no longer waits on clock-speed confirmation (see the
            # test above and CLAUDE.md §7) — it trusts the same page-name
            # signal pausing does, debounced over 3 consecutive ticks. That
            # reopens a narrow window during an Abandon transition where
            # FluxHub closes just before the match is actually torn down:
            # this test checks the *other* safety net — the unresolved-state
            # counter — still stops playback for good once the pointer chain
            # dies, rather than resuming and then looping forever.
            memory = FakeMemory(
                [
                    (1, 1),  # consumed by _wait_for_presentation
                    (1, 1),  # iter1: warm up
                    (1, 1),  # iter2: paused (fluxhub, count=1)
                    (1, 1),  # iter3: paused (fluxhub, count=2)
                    (1, 1),  # iter4: paused (fluxhub, count=3 -> pause fires)
                    (1, 1),  # iter5: fluxhub gone, resume debounce tick 1
                    (1, 1),  # iter6: resume debounce tick 2
                    (1, 1),  # iter7: resume debounce tick 3 -> resume fires
                    None,    # iter8: match pointer chain now dead -> unresolved count=1
                    None,    # iter9: unresolved count=2
                    None,    # iter10: unresolved count=3 -> stop for good
                ]
            )
            runtime = TeamEntranceRuntime(
                app,
                player_factory=lambda: player,
                memory_factory=lambda: memory,
            )
            config = TeamEntranceConfig(track, 0.2, 0.0)

            page_sequence = iter(
                [
                    "game/screens/fluxHub/FluxHub",
                    "game/screens/fluxHub/FluxHub",
                    "game/screens/fluxHub/FluxHub",
                    "",
                ]
            )

            def fake_sleep(_seconds: float) -> None:
                app.lastpagename = next(page_sequence, app.lastpagename)

            with patch("server16_py.entrance_runtime.time.sleep", side_effect=fake_sleep):
                runtime._run_worker(0, "1", config)

            self.assertEqual(player.pause_calls, 1)
            self.assertEqual(player.resume_calls, 1)
            self.assertTrue(player.stopped)
            self.assertTrue(player.closed)
            self.assertTrue(memory.closed)
            self.assertFalse(app._entrance_active)
            self.assertTrue(any("Team entrance stopped: match ended" in line for line in app.logs))

    def test_worker_stops_outright_on_abandon_to_select_team_menu(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            track = root / "Entrance.mp3"
            track.write_bytes(b"test")
            app = FakeApp(root)
            player = FakePlayer()
            # Regression test for the real bug report (2026-08-29,
            # server16.log): abandoning mid-walkout routed FluxHub -> blank
            # -> FluxHub -> blank -> game/screens/playNow/SelectTeam. Each
            # blank tick satisfied the resume debounce (3 ticks without a
            # pause-menu token), so the anthem kept fading back in every time
            # -- and once SelectTeam appeared, nothing on the page-name path
            # ever paused it again, while the match's own pointer chain
            # stayed resolvable (stale) for many seconds instead of going
            # unreadable, so the unresolved-state safety net didn't fire
            # either. The anthem must stop for good the instant a playNow
            # menu page is seen, regardless of pause state.
            memory = FakeMemory([(1, 1)])
            runtime = TeamEntranceRuntime(
                app,
                player_factory=lambda: player,
                memory_factory=lambda: memory,
            )
            config = TeamEntranceConfig(track, 0.2, 0.0)

            page_sequence = iter(
                [
                    "game/screens/fluxHub/FluxHub",  # iter1: paused count=1
                    "game/screens/fluxHub/FluxHub",  # iter2: paused count=2
                    "game/screens/fluxHub/FluxHub",  # iter3: paused count=3 -> pause fires
                    "",                              # iter4: resume debounce tick 1
                    "",                              # iter5: resume debounce tick 2
                    "",                              # iter6: resume debounce tick 3 -> false resume
                    "game/screens/playNow/SelectTeam",  # iter7: menu reached -> stop outright
                ]
            )

            def fake_sleep(_seconds: float) -> None:
                app.lastpagename = next(page_sequence, app.lastpagename)

            with patch("server16_py.entrance_runtime.time.sleep", side_effect=fake_sleep):
                runtime._run_worker(0, "1", config)

            self.assertEqual(player.pause_calls, 1)
            self.assertTrue(player.stopped)
            self.assertTrue(player.closed)
            self.assertFalse(app._entrance_active)
            self.assertTrue(any("returned to menu" in line for line in app.logs))

    def test_worker_ignores_isolated_page_glitch_while_paused(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            track = root / "Entrance.mp3"
            track.write_bytes(b"test")
            app = FakeApp(root)
            player = FakePlayer()
            # Regression test for the real bug report: resume_pending_count
            # used to only get reset to 0 at the moment pause first fires, not
            # every time a pause-menu page is confirmed again afterward. That
            # let a single isolated non-consecutive misread of the page name
            # while still genuinely sitting in FluxHub (iter5) survive all the
            # way to the next non-consecutive misread (iter7-8) and combine
            # with it to reach the resume threshold — resuming playback while
            # the player never actually left the pause menu. Fixed by
            # resetting the counter on every confirmed pause-menu tick, so
            # only *consecutive* non-pause ticks count. Here FluxHub reasserts
            # itself at iter6, so iter7-8 (2 ticks) must not be enough to
            # resume; only 3 *fresh* consecutive ticks may.
            memory = FakeMemory([(1, 1)])
            runtime = TeamEntranceRuntime(
                app,
                player_factory=lambda: player,
                memory_factory=lambda: memory,
            )
            runtime.PAUSE_GIVEUP_SECONDS = 5.0
            config = TeamEntranceConfig(track, 0.2, 0.0)

            page_sequence = iter(
                [
                    "game/screens/fluxHub/FluxHub",  # -> iter2: paused count=1
                    "game/screens/fluxHub/FluxHub",  # -> iter3: paused count=2
                    "game/screens/fluxHub/FluxHub",  # -> iter4: paused count=3 -> pause fires
                    "",                              # -> iter5: isolated glitch (resume_pending=1)
                    "game/screens/fluxHub/FluxHub",  # -> iter6: FluxHub reasserts -> resets to 0
                    "",                              # -> iter7: fresh tick 1 (resume_pending=1)
                    "",                              # -> iter8: fresh tick 2 (resume_pending=2, NOT 3)
                ]
            )

            fake_now = [1_000_000.0]

            def fake_time() -> float:
                return fake_now[0]

            def fake_sleep(_seconds: float) -> None:
                fake_now[0] += 1.0
                app.lastpagename = next(page_sequence, app.lastpagename)

            with patch("server16_py.entrance_runtime.time.sleep", side_effect=fake_sleep), \
                 patch("server16_py.entrance_runtime.time.time", side_effect=fake_time):
                runtime._run_worker(0, "1", config)

            # Only 2 fresh consecutive ticks were ever observed (iter7-8), so
            # the worker must still be paused when PAUSE_GIVEUP_SECONDS fires
            # at iter9 — never resumed, despite 2 non-consecutive misreads
            # (iter5 and iter7) having occurred over the session.
            self.assertEqual(player.pause_calls, 1)
            self.assertEqual(player.resume_calls, 0)
            self.assertTrue(player.stopped)
            self.assertTrue(player.closed)
            self.assertTrue(any("did not resume" in line for line in app.logs))


if __name__ == "__main__":
    unittest.main()
