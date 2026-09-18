from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from server16_py.ini_file import SessionIniFile
from server16_py.kit_mixer import KitMixRuntime


def _make_pack_kit_file(exedir: Path, team_id: str, pack_name: str, kittype: str, pack_id: str = "1") -> None:
    kit_dir = exedir / "FSW" / "Kits" / team_id / "packs" / pack_name / "sceneassets" / "kit"
    kit_dir.mkdir(parents=True, exist_ok=True)
    (kit_dir / f"kit_{pack_id}_{kittype}_0.rx3").write_bytes(b"dummy-rx3-bytes")


def _make_pack_numbers_file(exedir: Path, team_id: str, pack_name: str, filename: str) -> Path:
    numbers_dir = exedir / "FSW" / "Kits" / team_id / "packs" / pack_name / "sceneassets" / "kitnumbers"
    numbers_dir.mkdir(parents=True, exist_ok=True)
    path = numbers_dir / filename
    path.write_bytes(b"dummy-numbers-bytes")
    return path


def _make_pack_lua_file(exedir: Path, team_id: str, pack_name: str, lua_filename: str, content: str) -> Path:
    lua_dir = exedir / "FSW" / "Kits" / team_id / "packs" / pack_name / "fifarna" / "lua" / "assignments" / "teams"
    lua_dir.mkdir(parents=True, exist_ok=True)
    path = lua_dir / lua_filename
    path.write_text(content, encoding="utf-8")
    return path


def _make_flat_numbers_file(exedir: Path, team_id: str, filename: str) -> Path:
    numbers_dir = exedir / "FSW" / "Kits" / team_id / "sceneassets" / "kitnumbers"
    numbers_dir.mkdir(parents=True, exist_ok=True)
    path = numbers_dir / filename
    path.write_bytes(b"dummy-numbers-bytes")
    return path


def _make_flat_kit_file(exedir: Path, team_id: str, kittype: str, pack_id: str) -> None:
    kit_dir = exedir / "FSW" / "Kits" / team_id / "sceneassets" / "kit"
    kit_dir.mkdir(parents=True, exist_ok=True)
    (kit_dir / f"kit_{pack_id}_{kittype}_0.rx3").write_bytes(b"dummy-rx3-bytes")


def _make_flat_lua_file(exedir: Path, team_id: str, lua_filename: str, content: str) -> Path:
    lua_dir = exedir / "FSW" / "Kits" / team_id / "fifarna" / "lua" / "assignments" / "teams"
    lua_dir.mkdir(parents=True, exist_ok=True)
    path = lua_dir / lua_filename
    path.write_text(content, encoding="utf-8")
    return path


class GkAutoLinkFlagTests(unittest.TestCase):
    """is_gk_auto_link_enabled backs the "Auto link" checkbox in the Simple
    tab -- it must default to True (checked) when never configured, and
    remember whichever state the user last saved per exact (team_id,
    tourn_id) outfield kit set."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.exedir = Path(self._tmp.name)
        self.ini = SessionIniFile(self.exedir / "FSW" / "settings.ini")
        self.app = SimpleNamespace(exedir=self.exedir, settings_ini=self.ini, log=lambda msg: None)
        self.kit_mixer = KitMixRuntime(self.app)

    def test_defaults_to_enabled_when_never_configured(self) -> None:
        self.assertTrue(self.kit_mixer.is_gk_auto_link_enabled("1", "SeasonA"))

    def test_can_be_explicitly_disabled_and_re_enabled(self) -> None:
        self.kit_mixer.set_gk_auto_link_enabled("1", "SeasonA", False)
        self.assertFalse(self.kit_mixer.is_gk_auto_link_enabled("1", "SeasonA"))
        self.kit_mixer.set_gk_auto_link_enabled("1", "SeasonA", True)
        self.assertTrue(self.kit_mixer.is_gk_auto_link_enabled("1", "SeasonA"))

    def test_flag_is_scoped_per_team_and_pack(self) -> None:
        self.kit_mixer.set_gk_auto_link_enabled("1", "SeasonA", False)
        self.assertTrue(self.kit_mixer.is_gk_auto_link_enabled("1", "SeasonB"))
        self.assertTrue(self.kit_mixer.is_gk_auto_link_enabled("2", "SeasonA"))


class SuggestLinkedGkTournTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.exedir = Path(self._tmp.name)
        self.ini = SessionIniFile(self.exedir / "FSW" / "settings.ini")
        self.app = SimpleNamespace(exedir=self.exedir, settings_ini=self.ini, log=lambda msg: None)
        self.kit_mixer = KitMixRuntime(self.app)
        # "SeasonA" ships both an outfield (home) and a keeper kit together.
        _make_pack_kit_file(self.exedir, "1", "SeasonA", "0")
        _make_pack_kit_file(self.exedir, "1", "SeasonA", "2")
        # "SeasonB" only ships the outfield kit -- no matching keeper pack.
        _make_pack_kit_file(self.exedir, "1", "SeasonB", "0")

    def test_suggests_the_same_named_keeper_pack_when_one_exists(self) -> None:
        self.assertEqual(self.kit_mixer.suggest_linked_gk_tourn("1", "SeasonA"), "SeasonA")

    def test_suggests_nothing_when_no_keeper_pack_shares_the_name(self) -> None:
        self.assertIsNone(self.kit_mixer.suggest_linked_gk_tourn("1", "SeasonB"))

    def test_suggests_nothing_for_missing_team_or_tourn(self) -> None:
        self.assertIsNone(self.kit_mixer.suggest_linked_gk_tourn("", "SeasonA"))
        self.assertIsNone(self.kit_mixer.suggest_linked_gk_tourn("1", ""))


class ResolveGkTournTests(unittest.TestCase):
    """resolve_gk_tourn is the single source of truth apply_kit_set_linked
    and the Simple tab's combo preview both read from: the automatic
    same-pack-name match while "Auto link" is on (the default), or the
    manual [kitgk] value once it's been turned off for that exact kit
    set."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.exedir = Path(self._tmp.name)
        self.ini = SessionIniFile(self.exedir / "FSW" / "settings.ini")
        self.app = SimpleNamespace(exedir=self.exedir, settings_ini=self.ini, log=lambda msg: None)
        self.kit_mixer = KitMixRuntime(self.app)
        _make_pack_kit_file(self.exedir, "1", "SeasonA", "0")
        _make_pack_kit_file(self.exedir, "1", "SeasonA", "2")
        _make_pack_kit_file(self.exedir, "1", "OtherKeeper", "2")

    def test_uses_the_automatic_match_by_default(self) -> None:
        self.assertEqual(self.kit_mixer.resolve_gk_tourn("1", "SeasonA"), "SeasonA")

    def test_manual_link_is_ignored_while_auto_link_is_still_on(self) -> None:
        self.kit_mixer.set_linked_gk_tourn("1", "SeasonA", "OtherKeeper")
        self.assertEqual(self.kit_mixer.resolve_gk_tourn("1", "SeasonA"), "SeasonA")

    def test_manual_link_is_used_once_auto_link_is_turned_off(self) -> None:
        self.kit_mixer.set_gk_auto_link_enabled("1", "SeasonA", False)
        self.kit_mixer.set_linked_gk_tourn("1", "SeasonA", "OtherKeeper")
        self.assertEqual(self.kit_mixer.resolve_gk_tourn("1", "SeasonA"), "OtherKeeper")

    def test_turning_auto_link_off_with_no_manual_link_resolves_to_none(self) -> None:
        self.kit_mixer.set_gk_auto_link_enabled("1", "SeasonA", False)
        self.assertIsNone(self.kit_mixer.resolve_gk_tourn("1", "SeasonA"))


class ApplyKitSetLinkedAutoGkTests(unittest.TestCase):
    """apply_kit_set_linked is what both the overlay's Kits tab and the
    F7-F11 hotkey carousel call -- it must auto-pair a same-named keeper
    pack while "Auto link" is on (the default, requiring zero prior
    configuration), and respect the manual [kitgk] link once the user has
    turned auto off for that exact outfield pack."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.exedir = Path(self._tmp.name)
        self.ini = SessionIniFile(self.exedir / "FSW" / "settings.ini")
        self.logs: list[str] = []
        self.app = SimpleNamespace(exedir=self.exedir, settings_ini=self.ini, log=self.logs.append)
        self.kit_mixer = KitMixRuntime(self.app)
        _make_pack_kit_file(self.exedir, "1", "SeasonA", "0")
        _make_pack_kit_file(self.exedir, "1", "SeasonA", "2")
        _make_pack_kit_file(self.exedir, "1", "SeasonB", "0")

    def test_auto_links_the_matching_keeper_pack_with_no_prior_configuration(self) -> None:
        result = self.kit_mixer.apply_kit_set_linked("1", "0", "SeasonA")
        self.assertIsNotNone(result["gk"])
        self.assertTrue(any("auto-matched" in line for line in self.logs))

    def test_does_not_invent_a_link_when_no_matching_keeper_pack_exists(self) -> None:
        result = self.kit_mixer.apply_kit_set_linked("1", "0", "SeasonB")
        self.assertIsNone(result["gk"])

    def test_turning_auto_link_off_with_no_manual_link_disables_gk_entirely(self) -> None:
        self.kit_mixer.set_gk_auto_link_enabled("1", "SeasonA", False)
        result = self.kit_mixer.apply_kit_set_linked("1", "0", "SeasonA")
        self.assertIsNone(result["gk"])
        self.assertFalse(any("auto-matched" in line for line in self.logs))

    def test_manual_link_is_used_and_not_logged_as_auto_matched(self) -> None:
        _make_pack_kit_file(self.exedir, "1", "OtherKeeper", "2")
        self.kit_mixer.set_gk_auto_link_enabled("1", "SeasonA", False)
        self.kit_mixer.set_linked_gk_tourn("1", "SeasonA", "OtherKeeper")
        result = self.kit_mixer.apply_kit_set_linked("1", "0", "SeasonA")
        self.assertIsNotNone(result["gk"])
        self.assertFalse(any("auto-matched" in line for line in self.logs))


class ResolveSpecificKitnumbersFallbackTests(unittest.TestCase):
    """Regression test for a live-reported bug: real community kit packs
    (confirmed against an actual install, E:\\Fifa\\FIFA 16 test\\fip) ship
    specifickitnumbers files named like "specifickitnumbers_1362_0_0_13.rx3"
    -- shortcode "0" literal, last field a colour/style id -- never the
    "_1_..._<kittype>"/"_2_..._<kittype>" per-kittype shape
    list_kit_sets originally only ever looked for (the shape
    KitExtractorHost.cs's own extractor produces). player.lua's
    GetRMNumberSet confirms this "_0_..." shape is the engine's own
    fallback-by-colour path, read in-game whenever the per-kittype file is
    missing -- so it's a real, valid source, not a malformed file."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.exedir = Path(self._tmp.name)
        self.ini = SessionIniFile(self.exedir / "FSW" / "settings.ini")
        self.logs: list[str] = []
        self.app = SimpleNamespace(exedir=self.exedir, settings_ini=self.ini, log=self.logs.append)
        self.kit_mixer = KitMixRuntime(self.app)

    def test_falls_back_to_the_colour_variant_when_it_is_the_only_candidate(self) -> None:
        _make_pack_kit_file(self.exedir, "1", "Spain 24-25", "0", pack_id="1362")
        _make_pack_numbers_file(self.exedir, "1", "Spain 24-25", "specifickitnumbers_1362_0_0_13.rx3")

        entries = self.kit_mixer.list_kit_sets("1", "0")

        self.assertEqual(len(entries), 1)
        entry = entries[0]
        self.assertIsNotNone(entry["jersey_numbers_path"])
        self.assertIsNotNone(entry["shorts_numbers_path"])
        # Same shared file for both -- nothing in its name distinguishes them.
        self.assertEqual(entry["jersey_numbers_path"], entry["shorts_numbers_path"])
        self.assertEqual(entry["jersey_numbers_path"].name, "specifickitnumbers_1362_0_0_13.rx3")

    def test_ambiguous_colour_candidates_are_left_unresolved_and_logged(self) -> None:
        # The exact live-reported scenario: a real pack shipped 4 colour/
        # style variants (one presumably per kit variant) with no kittype
        # indicator in any of their filenames -- picking one at random
        # (the old alphabetical-first behavior) applied the wrong kit's
        # number style, confirmed live.
        _make_pack_kit_file(self.exedir, "1", "Spain 24-25", "0", pack_id="1362")
        for suffix in ("13", "18", "5", "7"):
            _make_pack_numbers_file(self.exedir, "1", "Spain 24-25", f"specifickitnumbers_1362_0_0_{suffix}.rx3")

        entries = self.kit_mixer.list_kit_sets("1", "0")

        entry = entries[0]
        self.assertIsNone(entry["jersey_numbers_path"])
        self.assertIsNone(entry["shorts_numbers_path"])
        self.assertTrue(any("ambiguous" in line for line in self.logs))

    def test_per_kittype_file_still_wins_over_the_colour_fallback_when_both_exist(self) -> None:
        _make_pack_kit_file(self.exedir, "1", "SeasonA", "0", pack_id="1362")
        _make_pack_numbers_file(self.exedir, "1", "SeasonA", "specifickitnumbers_1362_1_0_0.rx3")
        _make_pack_numbers_file(self.exedir, "1", "SeasonA", "specifickitnumbers_1362_2_0_0.rx3")
        _make_pack_numbers_file(self.exedir, "1", "SeasonA", "specifickitnumbers_1362_0_0_13.rx3")

        entries = self.kit_mixer.list_kit_sets("1", "0")

        entry = entries[0]
        self.assertEqual(entry["jersey_numbers_path"].name, "specifickitnumbers_1362_1_0_0.rx3")
        self.assertEqual(entry["shorts_numbers_path"].name, "specifickitnumbers_1362_2_0_0.rx3")

    def test_no_numbers_files_at_all_still_resolves_to_none(self) -> None:
        _make_pack_kit_file(self.exedir, "1", "SeasonA", "0", pack_id="1362")

        entries = self.kit_mixer.list_kit_sets("1", "0")

        entry = entries[0]
        self.assertIsNone(entry["jersey_numbers_path"])
        self.assertIsNone(entry["shorts_numbers_path"])
        self.assertFalse(entry["complete"])
        self.assertEqual(entry["numbers_missing_reason"], "missing")

    def test_apply_kit_set_surfaces_missing_reason_on_the_result(self) -> None:
        _make_pack_kit_file(self.exedir, "1", "SeasonA", "0", pack_id="1362")

        result = self.kit_mixer.apply_kit_set("1", "0", "SeasonA")

        self.assertEqual(result["numbers_missing_reason"], "missing")
        self.assertNotIn("jersey_numbers", result["applied"])

    def test_apply_kit_set_surfaces_ambiguous_reason_on_the_result(self) -> None:
        _make_pack_kit_file(self.exedir, "1", "Spain 24-25", "0", pack_id="1362")
        for suffix in ("13", "18", "5", "7"):
            _make_pack_numbers_file(self.exedir, "1", "Spain 24-25", f"specifickitnumbers_1362_0_0_{suffix}.rx3")

        result = self.kit_mixer.apply_kit_set("1", "0", "Spain 24-25")

        self.assertEqual(result["numbers_missing_reason"], "ambiguous")
        self.assertNotIn("jersey_numbers", result["applied"])

    def test_apply_kit_set_has_no_missing_reason_once_numbers_resolve(self) -> None:
        _make_pack_kit_file(self.exedir, "1", "Spain 24-25", "0", pack_id="1362")
        _make_pack_numbers_file(self.exedir, "1", "Spain 24-25", "specifickitnumbers_1362_0_0_13.rx3")

        result = self.kit_mixer.apply_kit_set("1", "0", "Spain 24-25")

        self.assertIsNone(result["numbers_missing_reason"])

    def test_apply_kit_set_writes_the_fallback_numbers_to_the_live_path(self) -> None:
        _make_pack_kit_file(self.exedir, "1", "Spain 24-25", "0", pack_id="1362")
        _make_pack_numbers_file(self.exedir, "1", "Spain 24-25", "specifickitnumbers_1362_0_0_13.rx3")

        result = self.kit_mixer.apply_kit_set("1", "0", "Spain 24-25")

        self.assertIn("jersey_numbers", result["applied"])
        self.assertIn("shorts_numbers", result["applied"])
        live_jersey = self.exedir / "data" / "sceneassets" / "kitnumbers" / "specifickitnumbers_1_1_0_0.rx3"
        live_shorts = self.exedir / "data" / "sceneassets" / "kitnumbers" / "specifickitnumbers_1_2_0_0.rx3"
        self.assertTrue(live_jersey.exists())
        self.assertTrue(live_shorts.exists())
        self.assertEqual(live_jersey.read_bytes(), b"dummy-numbers-bytes")


class ResolveSpecificKitnumbersLuaDisambiguationTests(unittest.TestCase):
    """A pack's own bundled team lua (fifarna/lua/assignments/teams/*.lua)
    already tells us, via assignKitDetails' numbercolourshirt/
    numbercolourshort fields, exactly which colour/style file FIFA's own
    player.lua (GetRMNumberSet) would pick for each kit type -- the same
    data confirmed live against a real install (E:\\Fifa\\FIFA 16 test\\fip)
    across several downloaded kit packs, several of which were previously
    reported "ambiguous" and left with no numbers applied at all."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.exedir = Path(self._tmp.name)
        self.ini = SessionIniFile(self.exedir / "FSW" / "settings.ini")
        self.logs: list[str] = []
        self.app = SimpleNamespace(exedir=self.exedir, settings_ini=self.ini, log=self.logs.append)
        self.kit_mixer = KitMixRuntime(self.app)

    def test_disambiguates_four_way_ambiguous_pack_via_bundled_lua(self) -> None:
        # Real pack shape (Racing Santander / "Spain 24-25", team 1362):
        # four colour/style files with no kittype indicator, but the team's
        # own bundled lua assigns a distinct numbercolourshirt/short pair to
        # each of the four kit types, resolving all four unambiguously.
        _make_pack_kit_file(self.exedir, "1", "Spain 24-25", "0", pack_id="1362")
        _make_pack_kit_file(self.exedir, "1", "Spain 24-25", "1", pack_id="1362")
        _make_pack_kit_file(self.exedir, "1", "Spain 24-25", "2", pack_id="1362")
        _make_pack_kit_file(self.exedir, "1", "Spain 24-25", "12", pack_id="1362")
        for suffix in ("5", "18", "13", "7"):
            _make_pack_numbers_file(self.exedir, "1", "Spain 24-25", f"specifickitnumbers_1362_0_0_{suffix}.rx3")
        _make_pack_lua_file(
            self.exedir, "1", "Spain 24-25", "team_1362.lua",
            "assignKitDetails(1362,0,-1,\"e6d728\",-1,-1,5,5,-1,0)\n"
            "assignKitDetails(1362,1,-1,\"d2000f\",-1,-1,18,18,-1,7)\n"
            "assignKitDetails(1362,2,-1,\"2f3e7e\",-1,-1,13,13,-1,7)\n"
            "assignKitDetails(1362,12,-1,\"feba4c\",-1,-1,7,7,-1,7)\n",
        )

        home = next(e for e in self.kit_mixer.list_kit_sets("1", "0") if e["tourn_id"] == "Spain 24-25")
        away = next(e for e in self.kit_mixer.list_kit_sets("1", "1") if e["tourn_id"] == "Spain 24-25")
        keeper = next(e for e in self.kit_mixer.list_kit_sets("1", "2") if e["tourn_id"] == "Spain 24-25")

        self.assertEqual(home["jersey_numbers_path"].name, "specifickitnumbers_1362_0_0_5.rx3")
        self.assertEqual(home["shorts_numbers_path"].name, "specifickitnumbers_1362_0_0_5.rx3")
        self.assertEqual(away["jersey_numbers_path"].name, "specifickitnumbers_1362_0_0_18.rx3")
        self.assertEqual(keeper["jersey_numbers_path"].name, "specifickitnumbers_1362_0_0_13.rx3")
        self.assertFalse(any("ambiguous" in line for line in self.logs))

    def test_resolves_different_files_for_shirt_and_shorts_on_the_same_kit(self) -> None:
        # Real pack shape (Real Sporting / "Germany...", team 1337): the
        # home kit's own assignKitDetails uses numbercolourshirt=2 but
        # numbercolourshort=1 -- genuinely different files for jersey vs
        # shorts digits on the SAME kit type, which the old "one shared file
        # for both" fallback could never have produced correctly.
        _make_pack_kit_file(self.exedir, "1", "GermanyPack", "0", pack_id="1337")
        _make_pack_numbers_file(self.exedir, "1", "GermanyPack", "specifickitnumbers_1337_0_0_1.rx3")
        _make_pack_numbers_file(self.exedir, "1", "GermanyPack", "specifickitnumbers_1337_0_0_2.rx3")
        _make_pack_lua_file(
            self.exedir, "1", "GermanyPack", "team_1337.lua",
            "assignKitDetails(1337,0,-1,\"0c0c0c\",-1,-1,2,1,-1,0)\n",
        )

        entries = self.kit_mixer.list_kit_sets("1", "0")

        entry = entries[0]
        self.assertEqual(entry["jersey_numbers_path"].name, "specifickitnumbers_1337_0_0_2.rx3")
        self.assertEqual(entry["shorts_numbers_path"].name, "specifickitnumbers_1337_0_0_1.rx3")

    def test_falls_back_to_ambiguous_when_lua_names_a_colour_not_present_on_disk(self) -> None:
        _make_pack_kit_file(self.exedir, "1", "Pack", "0", pack_id="1")
        for suffix in ("9", "10"):
            _make_pack_numbers_file(self.exedir, "1", "Pack", f"specifickitnumbers_1_0_0_{suffix}.rx3")
        _make_pack_lua_file(
            self.exedir, "1", "Pack", "team_1.lua",
            "assignKitDetails(1,0,-1,\"e6d728\",-1,-1,99,99,-1,0)\n",
        )

        entries = self.kit_mixer.list_kit_sets("1", "0")

        entry = entries[0]
        self.assertIsNone(entry["jersey_numbers_path"])
        self.assertIsNone(entry["shorts_numbers_path"])
        self.assertEqual(entry["numbers_missing_reason"], "ambiguous")

    def test_falls_back_to_ambiguous_when_no_lua_is_bundled_at_all(self) -> None:
        _make_pack_kit_file(self.exedir, "1", "Pack", "0", pack_id="1")
        for suffix in ("9", "10"):
            _make_pack_numbers_file(self.exedir, "1", "Pack", f"specifickitnumbers_1_0_0_{suffix}.rx3")

        entries = self.kit_mixer.list_kit_sets("1", "0")

        entry = entries[0]
        self.assertEqual(entry["numbers_missing_reason"], "ambiguous")

    def test_still_missing_when_pack_ships_no_kitnumbers_files_at_all(self) -> None:
        # Real pack shape (Real Sporting / "Chile...", team 111459): the
        # bundled lua exists and assigns real colour ids, but the pack
        # simply never shipped any specifickitnumbers_*.rx3 files -- there
        # is nothing to disambiguate, and this must not be mistaken for a
        # resolvable case.
        _make_pack_kit_file(self.exedir, "1", "ChilePack", "0", pack_id="111459")
        _make_pack_lua_file(
            self.exedir, "1", "ChilePack", "team_111459.lua",
            "assignKitDetails(111459,0,-1,\"dcdcdc\",-1,-1,1,1,-1,0)\n",
        )

        entries = self.kit_mixer.list_kit_sets("1", "0")

        entry = entries[0]
        self.assertIsNone(entry["jersey_numbers_path"])
        self.assertIsNone(entry["shorts_numbers_path"])
        self.assertEqual(entry["numbers_missing_reason"], "missing")

    def test_works_for_the_flat_root_kit_folder_too_not_just_packs(self) -> None:
        # Same lua-sibling-of-kitnumbers layout applies to the flat
        # FSW/Kits/<team>/sceneassets root (e.g. Athletic Bilbao's "bk"
        # folder), not just packs/<name>/ subfolders.
        _make_flat_kit_file(self.exedir, "1", "0", pack_id="1345")
        _make_flat_kit_file(self.exedir, "1", "2", pack_id="1345")
        _make_flat_numbers_file(self.exedir, "1", "specifickitnumbers_1345_0_0_1.rx3")
        _make_flat_numbers_file(self.exedir, "1", "specifickitnumbers_1345_0_0_2.rx3")
        _make_flat_lua_file(
            self.exedir, "1", "team_1345.lua",
            "assignKitDetails(1345,0,-1,\"e6e6e6\",-1,-1,1,1,-1,0)\n"
            "assignKitDetails(1345,2,-1,\"0d0d0d\",-1,-1,2,2,-1,9)\n",
        )

        home = next(e for e in self.kit_mixer.list_kit_sets("1", "0") if e["tourn_id"] == "0")
        keeper = next(e for e in self.kit_mixer.list_kit_sets("1", "2") if e["tourn_id"] == "0")

        self.assertEqual(home["jersey_numbers_path"].name, "specifickitnumbers_1345_0_0_1.rx3")
        self.assertEqual(keeper["jersey_numbers_path"].name, "specifickitnumbers_1345_0_0_2.rx3")


class PackNameColorAutoApplyTests(unittest.TestCase):
    """Jersey name colour used to require a separate, manual step in the
    Advanced tab (apply_name_color), and even there it only ever read lua
    files sitting in the flat kits_lua_dir root -- never inside a packs/
    <name>/ subfolder, so a team whose kits only exist as packs (e.g. Racing
    Santander in the real install this was diagnosed against) had no way to
    surface a name colour at all. Packs already bundle the same
    assignKitDetails(...) call kit numbers were fixed to read from -- this
    verifies apply_kit_set now applies that colour automatically, the same
    way it already applies numbers, with no extra manual step or renaming."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.exedir = Path(self._tmp.name)
        self.ini = SessionIniFile(self.exedir / "FSW" / "settings.ini")
        self.logs: list[str] = []
        self.app = SimpleNamespace(exedir=self.exedir, settings_ini=self.ini, log=self.logs.append)
        self.kit_mixer = KitMixRuntime(self.app)

    def test_list_kit_sets_surfaces_the_pack_bundled_name_color(self) -> None:
        _make_pack_kit_file(self.exedir, "1", "Spain 24-25", "0", pack_id="1362")
        _make_pack_lua_file(
            self.exedir, "1", "Spain 24-25", "team_1362.lua",
            "assignKitDetails(1362,0,-1,\"e6d728\",-1,-1,5,5,-1,0)\n",
        )

        entries = self.kit_mixer.list_kit_sets("1", "0")

        self.assertEqual(entries[0]["name_color"], "e6d728")

    def test_apply_kit_set_writes_the_pack_name_color_to_the_live_team_lua(self) -> None:
        _make_pack_kit_file(self.exedir, "1", "Spain 24-25", "0", pack_id="1362")
        _make_pack_lua_file(
            self.exedir, "1", "Spain 24-25", "team_1362.lua",
            "assignKitDetails(1362,0,-1,\"e6d728\",-1,-1,5,5,-1,0)\n",
        )

        result = self.kit_mixer.apply_kit_set("1", "0", "Spain 24-25")

        self.assertIn("name_color", result["applied"])
        live_lua = self.exedir / "data" / "fifarna" / "lua" / "assignments" / "teams" / "team_1.lua"
        self.assertTrue(live_lua.exists())
        text = live_lua.read_text(encoding="utf-8")
        self.assertIn('assignKitDetails(1,0,-1,"e6d728"', text)

    def test_apply_kit_set_backs_up_the_live_team_lua_before_first_write(self) -> None:
        live_lua = self.exedir / "data" / "fifarna" / "lua" / "assignments" / "teams" / "team_1.lua"
        live_lua.parent.mkdir(parents=True, exist_ok=True)
        live_lua.write_text("assignKitDetails(1,0,-1,\"original\",-1,-1,-1,-1,-1,0)\n", encoding="utf-8")
        _make_pack_kit_file(self.exedir, "1", "Spain 24-25", "0", pack_id="1362")
        _make_pack_lua_file(
            self.exedir, "1", "Spain 24-25", "team_1362.lua",
            "assignKitDetails(1362,0,-1,\"e6d728\",-1,-1,5,5,-1,0)\n",
        )

        self.kit_mixer.apply_kit_set("1", "0", "Spain 24-25")

        backup = live_lua.with_name("team_1.original.lua")
        self.assertTrue(backup.exists())
        self.assertIn("original", backup.read_text(encoding="utf-8"))

    def test_no_name_color_applied_when_pack_leaves_it_at_dont_override(self) -> None:
        _make_pack_kit_file(self.exedir, "1", "Pack", "0", pack_id="1")
        _make_pack_lua_file(
            self.exedir, "1", "Pack", "team_1.lua",
            "assignKitDetails(1,0,-1,-1,-1,-1,5,5,-1,0)\n",
        )

        entries = self.kit_mixer.list_kit_sets("1", "0")
        result = self.kit_mixer.apply_kit_set("1", "0", "Pack")

        self.assertIsNone(entries[0]["name_color"])
        self.assertNotIn("name_color", result["applied"])

    def test_no_name_color_applied_when_pack_has_no_bundled_lua_at_all(self) -> None:
        _make_pack_kit_file(self.exedir, "1", "Pack", "0", pack_id="1")

        entries = self.kit_mixer.list_kit_sets("1", "0")
        result = self.kit_mixer.apply_kit_set("1", "0", "Pack")

        self.assertIsNone(entries[0]["name_color"])
        self.assertNotIn("name_color", result["applied"])

    def test_works_for_the_flat_root_kit_folder_too_not_just_packs(self) -> None:
        _make_flat_kit_file(self.exedir, "1", "0", pack_id="1345")
        _make_flat_lua_file(
            self.exedir, "1", "team_1345.lua",
            "assignKitDetails(1345,0,-1,\"e6e6e6\",-1,-1,1,1,-1,0)\n",
        )

        entries = self.kit_mixer.list_kit_sets("1", "0")

        home = next(e for e in entries if e["tourn_id"] == "0")
        self.assertEqual(home["name_color"], "e6e6e6")

    def test_a_failed_name_color_patch_does_not_block_the_rest_of_the_kit_apply(self) -> None:
        # An existing live team lua with a malformed assignKitDetails call
        # (fewer than 8 args) makes _patch_assign_kit_details raise -- the
        # kit texture itself must still apply successfully.
        live_lua = self.exedir / "data" / "fifarna" / "lua" / "assignments" / "teams" / "team_1.lua"
        live_lua.parent.mkdir(parents=True, exist_ok=True)
        live_lua.write_text("assignKitDetails(1,0,-1,-1)\n", encoding="utf-8")
        _make_pack_kit_file(self.exedir, "1", "Spain 24-25", "0", pack_id="1362")
        _make_pack_lua_file(
            self.exedir, "1", "Spain 24-25", "team_1362.lua",
            "assignKitDetails(1362,0,-1,\"e6d728\",-1,-1,5,5,-1,0)\n",
        )

        result = self.kit_mixer.apply_kit_set("1", "0", "Spain 24-25")

        self.assertIn("kit", result["applied"])
        self.assertNotIn("name_color", result["applied"])
        self.assertTrue(any("name color apply failed" in line for line in self.logs))


if __name__ == "__main__":
    unittest.main()
