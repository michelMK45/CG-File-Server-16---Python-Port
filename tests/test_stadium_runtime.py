from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from server16_py.stadium_runtime import StadiumRuntime, _clean_db_display_name


class CleanDbDisplayNameTests(unittest.TestCase):
    def test_strips_leading_underscore_and_trailing_parenthetical(self) -> None:
        # The exact case confirmed live 2026-09-09 (CLAUDE.md §7 Part 4/5):
        # fifa_db.py returned this raw DB field but FIFA only ever rendered
        # "Waldstadion" on screen.
        self.assertEqual(
            _clean_db_display_name("_Waldstadion (Fussballstadion)"),
            "Waldstadion",
        )

    def test_leaves_plain_name_untouched(self) -> None:
        self.assertEqual(_clean_db_display_name("Anfield"), "Anfield")

    def test_strips_only_leading_underscore_without_parenthetical(self) -> None:
        self.assertEqual(_clean_db_display_name("_Sanderson Park"), "Sanderson Park")

    def test_strips_only_trailing_parenthetical_without_underscore(self) -> None:
        self.assertEqual(_clean_db_display_name("Camp Nou (Barcelona)"), "Camp Nou")

    def test_does_not_strip_a_parenthetical_in_the_middle(self) -> None:
        # Only a *trailing* parenthetical is a disambiguator suffix; one in
        # the middle of the name is presumably part of the real name itself.
        self.assertEqual(_clean_db_display_name("Estadio (Viejo) Nuevo"), "Estadio (Viejo) Nuevo")


class FakeDbNamePatcher:
    """Stands in for StadiumDbNamePatchCoordinator: get_current_name only
    ever reports a name once a caller explicitly marks it confirmed, mirroring
    the real coordinator only updating it on an actual successful write/read-
    verify in _patch_one -- never just because a request was made."""

    def __init__(self) -> None:
        self.requests: list[tuple[str, str, str]] = []
        self._confirmed: dict[str, str] = {}

    def get_current_name(self, injid: str) -> str | None:
        return self._confirmed.get(injid)

    def request(self, injid: str, old: str, new: str) -> None:
        self.requests.append((injid, old, new))

    def mark_confirmed(self, injid: str, name: str) -> None:
        self._confirmed[injid] = name


class RequestDbNamePatchTests(unittest.TestCase):
    def make_app(self, raw_db_name: str | None) -> SimpleNamespace:
        app = SimpleNamespace()
        app._resolve_stadium_name = lambda injid: raw_db_name
        app.stadium_db_name_patcher = FakeDbNamePatcher()
        return app

    def test_requests_patch_with_cleaned_vanilla_name_on_first_call(self) -> None:
        app = self.make_app("_Waldstadion (Fussballstadion)")
        runtime = StadiumRuntime(app)
        runtime.request_db_name_patch("176", "Campos de Sport de El Sardinero")
        self.assertEqual(
            app.stadium_db_name_patcher.requests,
            [("176", "Waldstadion", "Campos de Sport de El Sardinero")],
        )

    def test_repeated_calls_before_any_confirmed_success_keep_resolving_the_same_vanilla_name(self) -> None:
        # The exact bug fixed 2026-09-09 (Part 8): request_db_name_patch used
        # to assume its own request had already succeeded and cache the *new*
        # name immediately, so every retry after the first computed
        # old_name == new_name and silently stopped scanning -- confirmed
        # live via "scan attempt 1/6" never being followed by "2/6". As long
        # as nothing ever confirms success, every retry must keep searching
        # for the same original vanilla name, not the name it's trying (and
        # failing) to write.
        app = self.make_app("_Waldstadion (Fussballstadion)")
        runtime = StadiumRuntime(app)
        for _ in range(5):
            runtime.request_db_name_patch("176", "Campos de Sport de El Sardinero")
        self.assertEqual(
            app.stadium_db_name_patcher.requests,
            [("176", "Waldstadion", "Campos de Sport de El Sardinero")] * 5,
        )

    def test_uses_confirmed_name_instead_of_db_lookup_once_a_patch_actually_succeeded(self) -> None:
        app = self.make_app("_Waldstadion (Fussballstadion)")
        runtime = StadiumRuntime(app)
        runtime.request_db_name_patch("176", "First Custom Stadium")
        app.stadium_db_name_patcher.mark_confirmed("176", "First Custom Stadium")
        app._resolve_stadium_name = lambda injid: (_ for _ in ()).throw(AssertionError("should not re-query DB"))
        runtime.request_db_name_patch("176", "Second Custom Stadium")
        self.assertEqual(
            app.stadium_db_name_patcher.requests[-1],
            ("176", "First Custom Stadium", "Second Custom Stadium"),
        )

    def test_no_request_when_db_name_unavailable(self) -> None:
        app = self.make_app(None)
        runtime = StadiumRuntime(app)
        runtime.request_db_name_patch("176", "Custom Stadium")
        self.assertEqual(app.stadium_db_name_patcher.requests, [])


class FakeSettingsIni:
    """Minimal stand-in for IniFile/SessionIniFile: same (key, section) argument
    order, backed by a plain dict of {section: {key: value}}."""

    def __init__(self, data: dict[str, dict[str, str]] | None = None) -> None:
        self._data = data or {}

    def key_exists(self, key: str, section: str) -> bool:
        return bool(self._data.get(section, {}).get(key))

    def read(self, key: str, section: str) -> str:
        return self._data.get(section, {}).get(key, "")


class ResolveGoalpostSourcesTests(unittest.TestCase):
    """Model (specificgoalpost_*.rx3, [stadiumgoalpost]) and texture/color
    (specificnetsupportpost_*_textures.rx3, [stadiumgoalposttexture]) are
    independent, separately selectable packs -- a real-world pack ships them
    as sibling FSW/Goalpost/GoalpostModel/<name>/ and
    FSW/Goalpost/GoalpostColor/<name>/ folders, confirmed against a real
    contributor-supplied pack (2026-09-11)."""

    def make_app(self, ini_data: dict[str, dict[str, str]] | None = None) -> SimpleNamespace:
        return SimpleNamespace(
            settings_ini=FakeSettingsIni(ini_data),
            exedir=Path("C:/FIFA16"),
        )

    def test_no_override_falls_back_to_the_stadium_pack_s_own_goalpostgbd_folder(self) -> None:
        app = self.make_app()
        stad = Path("C:/FIFA16/FSW/Stadium/Anfield")
        result = StadiumRuntime.resolve_goalpost_sources(app, stad, "Anfield")
        self.assertEqual(result, [stad / "GoalpostGBD"])

    def test_model_only_override_resolves_under_goalpostmodel_with_no_legacy_fallback_mixed_in(self) -> None:
        # Keyed by stad_name -- the one already-resolved stadium -- not by any
        # new field on [stadium]/[comp], so a team with several assigned
        # stadiums (comma-separated) never needs its own per-stadium goalpost
        # to be threaded through _parse_stadium_entries.
        app = self.make_app({"stadiumgoalpost": {"Anfield": "1"}})
        stad = Path("C:/FIFA16/FSW/Stadium/Anfield")
        result = StadiumRuntime.resolve_goalpost_sources(app, stad, "Anfield")
        # GoalpostGBD is NOT also included -- see the module docstring on why
        # mixing a legacy source with an explicit override is deliberately
        # avoided (ambiguous filename collisions).
        self.assertEqual(result, [Path("C:/FIFA16/FSW/Goalpost/GoalpostModel/1")])

    def test_texture_only_override_resolves_under_goalpostcolor(self) -> None:
        app = self.make_app({"stadiumgoalposttexture": {"Anfield": "Azul"}})
        stad = Path("C:/FIFA16/FSW/Stadium/Anfield")
        result = StadiumRuntime.resolve_goalpost_sources(app, stad, "Anfield")
        self.assertEqual(result, [Path("C:/FIFA16/FSW/Goalpost/GoalpostColor/Azul")])

    def test_both_overrides_resolve_to_both_sources_model_first(self) -> None:
        app = self.make_app({
            "stadiumgoalpost": {"Anfield": "1"},
            "stadiumgoalposttexture": {"Anfield": "Azul"},
        })
        stad = Path("C:/FIFA16/FSW/Stadium/Anfield")
        result = StadiumRuntime.resolve_goalpost_sources(app, stad, "Anfield")
        self.assertEqual(
            result,
            [
                Path("C:/FIFA16/FSW/Goalpost/GoalpostModel/1"),
                Path("C:/FIFA16/FSW/Goalpost/GoalpostColor/Azul"),
            ],
        )

    def test_override_is_looked_up_by_the_chosen_stadium_not_other_stadiums_sharing_the_same_team(self) -> None:
        app = self.make_app({"stadiumgoalpost": {"Anfield": "1"}})
        stad = Path("C:/FIFA16/FSW/Stadium/OldTrafford")
        result = StadiumRuntime.resolve_goalpost_sources(app, stad, "OldTrafford")
        # No entry for THIS stadium -- falls back to its own GoalpostGBD,
        # unaffected by a sibling stadium's override.
        self.assertEqual(result, [stad / "GoalpostGBD"])

    def test_resolution_does_not_require_the_override_folder_to_exist_on_disk(self) -> None:
        # copy_goalpost_sources() already no-ops safely on a missing src_dir
        # -- resolution and existence are deliberately kept separate here too.
        app = self.make_app({"stadiumgoalpost": {"Anfield": "TypoedFolderName"}})
        stad = Path("C:/FIFA16/FSW/Stadium/Anfield")
        result = StadiumRuntime.resolve_goalpost_sources(app, stad, "Anfield")
        self.assertEqual(result, [Path("C:/FIFA16/FSW/Goalpost/GoalpostModel/TypoedFolderName")])
        self.assertFalse(result[0].exists())


class ApplyStadiumRuntimePickerReentryTests(unittest.TestCase):
    """Regression coverage for the manual in-game stadium picker reopening
    itself right after the player closed it (reported live 2026-09-15).

    Root cause: app_game.py's KickOffHub retry loop
    (_kickoff_retry_tick/_schedule_kickoff_retry) calls refresh_live_context
    repeatedly while HID/AID are still resolving, and refresh_live_context
    calls apply_all_runtime() any time its own (HID, AID, TOUR, ROUND)
    signature changes -- which it does every time AID resolves a tick after
    HID already has. apply_stadium_runtime's own stadium_signature excludes
    AID, so that later call re-enters apply_stadium_runtime for the EXACT
    SAME stadium_signature the player already resolved (by picking, or by
    closing/cancelling -> random fallback) a moment earlier. The picker's
    own pending/resolved flags are one-shot -- cleared the instant the first
    call consumes them -- so without a longer-lived memory of "already
    decided", this second call saw pending=False and treated it as a brand
    new assignment, popping the picker again on top of the one the player
    just closed."""

    class FakeVar:
        def __init__(self, value: bool) -> None:
            self._value = value

        def get(self) -> bool:
            return self._value

    def make_app(self, tmp_path: Path) -> SimpleNamespace:
        (tmp_path / "StadiumA").mkdir()
        (tmp_path / "StadiumB").mkdir()
        app = SimpleNamespace(
            settings_ini=FakeSettingsIni({"stadium": {"Team123": "StadiumA,StadiumB,4,1,1"}}),
            targetpath=tmp_path,
            HID="Team123",
            TOURNAME="",
            TOURROUNDID="",
            AID="",
            curstad="",
            CCount="0",
            injID=None,
            PoliceNum=None,
            gold=None,
            _kickoff_generation=1,
            _d3d_injector=object(),  # only needs to be non-None; _open_stadium_picker itself is stubbed below
            random_stadium_selection_var=self.FakeVar(False),
            _stadium_picker_pending=False,
            _stadium_picker_signature=None,
            _stadium_picker_resolved=False,
            _stadium_picker_chosen=None,
            _stadium_picker_decided_signature=None,
            _stadium_picker_decided_stadium=None,
            _stadium_task_running=False,
            _stadium_task_signature=None,
            _last_stadium_applied_signature=None,
            log=lambda *a, **k: None,
            _set_progress=lambda *a, **k: None,
            _set_process_status=lambda *a, **k: None,
        )
        return app

    def test_reentrant_call_after_close_reuses_the_decision_instead_of_reopening(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            app = self.make_app(Path(tmp))
            runtime = StadiumRuntime(app)

            opened: list[tuple] = []

            def fake_open_stadium_picker(candidates: list[str], signature: tuple) -> None:
                opened.append(signature)
                # Mirrors the real _open_stadium_picker's own bookkeeping,
                # minus the actual D3D-overlay calls.
                app._stadium_picker_pending = True
                app._stadium_picker_signature = signature
                app._stadium_picker_resolved = False
                app._stadium_picker_chosen = None

            started: list[str] = []

            def fake_start_stadium_task(section_id, section_name, injid, signature, request_key, chosen_stadium):
                started.append(chosen_stadium)

            runtime._open_stadium_picker = fake_open_stadium_picker
            runtime.start_stadium_task = fake_start_stadium_task

            # 1) First entry (e.g. KickOffHub retry tick #1, HID just resolved):
            # no picker session yet for this signature -> opens one and returns
            # without loading anything.
            runtime.apply_stadium_runtime()
            self.assertEqual(len(opened), 1)
            self.assertEqual(len(started), 0)

            # 2) Player closes the picker (Escape / the Close button) without
            # picking -- mirrors _resolve_stadium_picker(None) marking it
            # resolved with no chosen stadium, then forcing a fresh
            # apply_all_runtime() call to consume that resolution.
            app._stadium_picker_resolved = True
            runtime.apply_stadium_runtime()
            self.assertEqual(len(opened), 1, "must not reopen a second picker on this consuming call")
            self.assertEqual(len(started), 1)
            self.assertFalse(app._stadium_picker_pending)

            # 3) A later re-entrant call for the SAME stadium_signature (e.g.
            # the KickOffHub retry loop's next tick, once AID has also
            # resolved) must reuse the already-decided stadium instead of
            # popping a brand-new picker on top of the one just closed.
            runtime.apply_stadium_runtime()
            self.assertEqual(len(opened), 1, "picker must not reopen after already being resolved this match")
            self.assertEqual(len(started), 2)
            self.assertEqual(started[0], started[1], "must not re-roll a different stadium on the re-entrant call")


class ApplyStadiumRuntimeStuckPickerFlagTests(unittest.TestCase):
    """Regression coverage for the F12 overlay refusing to open again for the
    rest of the session after a stadium was assigned through it (reported live
    2026-09-25).

    _write_overlay_assignment (app_overlay.py) pre-resolves the manual picker
    for the assignment it just wrote -- pending=True, resolved=True,
    chosen=<the stadium the player picked in the wizard> -- and relies on the
    next apply_stadium_runtime() to consume that session and clear pending.
    But the only code that cleared pending lived inside the
    `len(valid_stadiums) > 1 and manual_mode` branch, and the wizard writes a
    SINGLE stadium, so the flag stayed True forever. app_overlay.py's
    can_toggle refuses F12/Start-hold while a picker is pending, so the
    overlay went permanently dead (and every page transition logged "Stadium
    picker abandoned" without abandoning anything). Same stuck flag with
    "random stadium selection" checked, which drops manual_mode entirely.
    """

    class FakeVar:
        def __init__(self, value: bool) -> None:
            self._value = value

        def get(self) -> bool:
            return self._value

    def make_app(self, tmp_path: Path, raw_value: str, random_mode: bool) -> SimpleNamespace:
        for name in ("StadiumA", "StadiumB"):
            (tmp_path / name).mkdir()
        app = SimpleNamespace(
            settings_ini=FakeSettingsIni({"stadium": {"Team123": raw_value}}),
            targetpath=tmp_path,
            HID="Team123",
            TOURNAME="",
            TOURROUNDID="",
            AID="",
            curstad="",
            CCount="0",
            injID=None,
            PoliceNum=None,
            gold=None,
            _kickoff_generation=1,
            _d3d_injector=object(),
            random_stadium_selection_var=self.FakeVar(random_mode),
            _stadium_picker_pending=False,
            _stadium_picker_signature=None,
            _stadium_picker_resolved=False,
            _stadium_picker_chosen=None,
            _stadium_picker_decided_signature=None,
            _stadium_picker_decided_stadium=None,
            _stadium_task_running=False,
            _stadium_task_signature=None,
            _last_stadium_applied_signature=None,
            log=lambda *a, **k: None,
            _set_progress=lambda *a, **k: None,
            _set_process_status=lambda *a, **k: None,
        )
        app.hide_calls = []
        app._hide_stadium_picker = lambda: app.hide_calls.append(True)
        return app

    def _run(self, raw_value: str, random_mode: bool, chosen: str) -> SimpleNamespace:
        with tempfile.TemporaryDirectory() as tmp:
            app = self.make_app(Path(tmp), raw_value, random_mode)
            runtime = StadiumRuntime(app)

            opened: list[tuple] = []
            runtime._open_stadium_picker = lambda candidates, signature: opened.append(signature)
            started: list[str] = []
            runtime.start_stadium_task = (
                lambda section_id, section_name, injid, signature, request_key, chosen_stadium:
                    started.append(chosen_stadium)
            )

            # Exactly the state _write_overlay_assignment leaves behind for the
            # signature apply_stadium_runtime is about to recompute.
            app._stadium_picker_signature = (
                app._kickoff_generation, "stadium", "Team123", raw_value,
                app.HID, app.TOURNAME, app.TOURROUNDID,
            )
            app._stadium_picker_pending = True
            app._stadium_picker_resolved = True
            app._stadium_picker_chosen = chosen

            runtime.apply_stadium_runtime()
            app.opened = opened
            app.started = started
            return app

    def test_single_stadium_assignment_does_not_leave_the_picker_pending(self) -> None:
        app = self._run("StadiumA,4,1,1", random_mode=False, chosen="StadiumA")
        self.assertFalse(
            app._stadium_picker_pending,
            "a stuck pending flag kills the F12/Start overlay toggle for the whole session",
        )
        self.assertEqual(app.opened, [], "one candidate must never pop the picker")
        self.assertEqual(app.started, ["StadiumA"])
        self.assertEqual(app.hide_calls, [True], "any panel left over for that session must be dropped")

    def test_random_selection_mode_does_not_leave_the_picker_pending(self) -> None:
        app = self._run("StadiumA,4,1,1;StadiumB,4,1,1", random_mode=True, chosen="StadiumB")
        self.assertFalse(app._stadium_picker_pending)
        self.assertEqual(app.opened, [], "random mode must never pop the picker")
        self.assertEqual(len(app.started), 1)


class RenderGoalpostTexturePreviewCacheTests(unittest.TestCase):
    """reuse_cached=True lets the asset grid preview every GoalpostColor pack
    at once without re-running the ~seconds-long 32-bit subprocess for packs
    whose PNG is still current."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        base = Path(self._tmp.name)
        self.runtime = StadiumRuntime(SimpleNamespace(base_dir=base))
        self.rx3 = base / "pack.rx3"
        self.rx3.write_bytes(b"rx3")
        self.worker_calls: list[dict] = []

    def fake_worker(self, config: dict, worker_name: str = "kit_worker.py") -> dict:
        self.worker_calls.append(config)
        output = Path(config["output"])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"png")
        return {"ok": True, "output": str(output)}

    def render(self, **kwargs) -> Path:
        with mock.patch("server16_py.stadium_runtime.run_fifalibrary_worker", self.fake_worker):
            return self.runtime.render_goalpost_texture_preview(self.rx3, cache_key="Azul", **kwargs)

    def test_default_always_re_renders(self) -> None:
        self.render()
        self.render()
        self.assertEqual(len(self.worker_calls), 2)

    def test_reuse_cached_renders_when_there_is_no_png_yet(self) -> None:
        output = self.render(reuse_cached=True)
        self.assertEqual(len(self.worker_calls), 1)
        self.assertTrue(output.is_file())

    def test_reuse_cached_skips_the_subprocess_when_the_png_is_current(self) -> None:
        first = self.render(reuse_cached=True)
        second = self.render(reuse_cached=True)
        self.assertEqual(len(self.worker_calls), 1)
        self.assertEqual(second, first)

    def test_a_png_rendered_by_the_default_path_is_reusable_too(self) -> None:
        self.render()
        self.render(reuse_cached=True)
        self.assertEqual(len(self.worker_calls), 1)

    def test_a_replaced_rx3_is_re_rendered_even_when_it_is_older_than_the_png(self) -> None:
        # The case a plain "PNG newer than source" check gets wrong: a pack
        # swapped for a file that keeps an OLDER modification date.
        self.render(reuse_cached=True)
        older = self.rx3.stat().st_mtime_ns - 10_000_000_000
        os.utime(self.rx3, ns=(older, older))
        self.render(reuse_cached=True)
        self.assertEqual(len(self.worker_calls), 2)
        self.render(reuse_cached=True)  # ...and that render is cached in turn
        self.assertEqual(len(self.worker_calls), 2)

    def test_a_missing_source_is_never_treated_as_cached(self) -> None:
        self.render()
        self.rx3.unlink()
        self.render(reuse_cached=True)
        self.assertEqual(len(self.worker_calls), 2)


if __name__ == "__main__":
    unittest.main()
