from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace

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


if __name__ == "__main__":
    unittest.main()
