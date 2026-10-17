from __future__ import annotations

import io
import struct
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from server16_py import kit_classic as kc
from server16_py import kit_classic_art as art
from server16_py.kit_mixer import KitMixRuntime

SUPPORTED_PLAYER_LUA = "\n".join(
    f"function {name}(a,b,c)\nend" for name in kc.REQUIRED_PLAYER_LUA_FUNCTIONS
) + "\n"

# Block exactly as Dinei's standalone Kit Mixer wrote it into a real team_383.lua
# (Portuguese comments, global KM_HOME past the last combination, goalkeeper code).
DINEI_BLOCK = """--Sociedade Esportiva Palmeiras
identifyTeamKitColours(383,0,"006030","005a30","e7e8e7","006030")
-- KITMIXER:BEGIN (gerado pelo Kit Mixer - nao edite entre os marcadores)
-- O jogo escolhe a cada partida: mandante usa a combinacao KM_HOME, visitante a KM_AWAY (1 = primeira).
local KM_HOME, KM_AWAY = 9, 1
local KM_GKH, KM_GKA = 13, -1
swapTeamKit(383, 0, 0) -- kitmixer:reset (volta ao kit original)
swapTeamKit(383, 1, 1) -- kitmixer:reset (volta ao kit original)
local KM_SEL = 0
local KM_GK = -1
do
local km_ok, km_side = pcall(function()
local as = gSportsRNA
local h = as:GetTable("wvPlayer", 9)
local a = as:GetTable("wvPlayer", 20)
if as:GetInt(h, "teamid") == 383 or as:GetInt(h, "kit") == 383 then return 0 end
if as:GetInt(a, "teamid") == 383 or as:GetInt(a, "kit") == 383 then return 1 end
return -1
end)
if km_ok then
if km_side == 0 then KM_SEL = KM_HOME KM_GK = KM_GKH elseif km_side == 1 then KM_SEL = KM_AWAY KM_GK = KM_GKA end
end
end
if KM_SEL == 1 then -- Home 1
swapTeamKit(383, 0, 4000100) -- camisa=0 shorts=1 meias=0
elseif KM_SEL == 2 then -- Home 3
swapTeamKit(383, 0, 0) -- kit original (camisa, shorts e meias do kit 0)
elseif KM_SEL == 3 then -- Away 1
swapTeamKit(383, 1, 4010001) -- camisa=1 shorts=0 meias=1
end
pcall(function()
assignGKKitPrecedence(383, 0, 1, {13})
end)
-- KITMIXER:END
"""

DINEI_OLD_BLOCK = """-- team
-- KITMIXER:BEGIN (gerado pelo Kit Mixer - nao edite entre os marcadores)
-- combinacao: Camisa branca
swapTeamKit(383, 3, 4040303) -- camisa=4 shorts=3 meias=3
swapTeamKitTournament(383, 7, 3, 4040403) -- camisa=4 shorts=4 meias=3
swapTeamKit(383, 4, 4) -- kitmixer:reset (volta ao kit original)
-- KITMIXER:END
"""


def _sample() -> kc.TeamCombinations:
    return kc.TeamCombinations(
        383,
        [
            kc.Combination("Home green socks", [kc.Mix(0, 0, 0, 0, 1)]),
            kc.Combination("Away mixed", [kc.Mix(0, 1, 1, 0, 1), kc.Mix(223, 0, 0, 1, 1)]),
            kc.Combination("Empty"),
        ],
        home=0,
        away=1,
    )


class PartCodeTests(unittest.TestCase):
    def test_round_trip_matches_rev_mod_decoder(self):
        for parts in [(0, 0, 0), (3, 4, 4), (12, 7, 99), (99, 99, 99), (1, 0, 5)]:
            self.assertEqual(kc.decode_parts(kc.encode_parts(*parts)), parts)
        self.assertEqual(kc.encode_parts(3, 4, 4), 4030404)
        self.assertEqual(kc.decode_parts(3), (3, 3, 3))

    def test_out_of_range_part_is_rejected(self):
        with self.assertRaises(ValueError):
            kc.encode_parts(100, 0, 0)

    def test_identity_mix_is_written_as_the_plain_slot(self):
        self.assertEqual(kc.Mix(0, 1, 1, 1, 1).code, 1)
        self.assertEqual(kc.Mix(0, 1, 1, 0, 1).code, 4010001)


class BlockRoundTripTests(unittest.TestCase):
    def test_render_then_parse_gives_back_the_same_combinations(self):
        tc = _sample()
        parsed = kc.parse_team_block(kc.render_team_block(tc), 383)
        self.assertEqual([c.name for c in parsed.items], ["Home green socks", "Away mixed", "Empty"])
        self.assertEqual(parsed.items[0].mixes, [kc.Mix(0, 0, 0, 0, 1)])
        self.assertEqual(sorted(parsed.items[1].mixes, key=lambda m: m.key),
                         [kc.Mix(0, 1, 1, 0, 1), kc.Mix(223, 0, 0, 1, 1)])
        self.assertEqual(parsed.items[2].mixes, [])
        self.assertEqual((parsed.home, parsed.away), (0, 1))
        self.assertFalse(parsed.has_gk)

    def test_original_kits_selection_is_written_as_zero(self):
        tc = _sample()
        tc.home = None
        text = kc.render_team_block(tc)
        self.assertIn("local KM_HOME, KM_AWAY = 0, 2", text)
        self.assertIsNone(kc.parse_team_block(text, 383).home)

    def test_every_touched_slot_is_reset_before_the_branches(self):
        text = kc.render_team_block(_sample())
        self.assertIn("swapTeamKit(383, 0, 0) -- kitmixer:reset", text)
        self.assertIn("swapTeamKit(383, 1, 1) -- kitmixer:reset", text)
        self.assertIn("swapTeamKitTournament(383, 223, 0, 0) -- kitmixer:reset", text)
        self.assertLess(text.index("kitmixer:reset"), text.index("if KM_SEL == 1"))

    def test_nothing_to_write_renders_no_block(self):
        self.assertEqual(kc.render_team_block(kc.TeamCombinations(383, [kc.Combination("Empty")])), "")

    def test_reads_dineis_block_and_keeps_his_goalkeeper_choice(self):
        tc = kc.parse_team_block(DINEI_BLOCK, 383)
        self.assertEqual([c.name for c in tc.items], ["Home 1", "Home 3", "Away 1"])
        self.assertEqual(tc.items[0].mixes, [kc.Mix(0, 0, 0, 1, 0)])
        self.assertEqual(tc.items[1].mixes, [kc.Mix(0, 0, 0, 0, 0)])
        self.assertIsNone(tc.home)   # his KM_HOME = 9 points past the last combination
        self.assertEqual(tc.away, 0)
        self.assertEqual((tc.gk_home, tc.gk_away), (13, None))
        rendered = kc.render_team_block(tc)
        self.assertIn("local KM_GKH, KM_GKA = 13, -1", rendered)
        self.assertIn("assignGKKitPrecedence(383, k, 0, t)", rendered)

    def test_automatic_goalkeepers_write_no_goalkeeper_code(self):
        text = kc.render_team_block(_sample())
        self.assertNotIn("KM_GKH", text)
        self.assertNotIn("assignGKKitPrecedence", text)

    def test_goalkeeper_only_block_round_trips(self):
        tc = kc.TeamCombinations(383, [kc.Combination("Empty")], gk_away=12)
        text = kc.render_team_block(tc)
        self.assertIn("local KM_GKH, KM_GKA = -1, 12", text)
        parsed = kc.parse_team_block(text, 383)
        self.assertEqual((parsed.gk_home, parsed.gk_away), (None, 12))
        self.assertFalse(parsed.has_mixes())
        parsed.gk_away = None
        self.assertEqual(kc.render_team_block(parsed), "")

    def test_reads_dineis_first_single_combination_format(self):
        tc = kc.parse_team_block(DINEI_OLD_BLOCK, 383)
        self.assertEqual(len(tc.items), 1)
        self.assertEqual(tc.items[0].name, "Camisa branca")
        self.assertEqual(sorted(tc.items[0].mixes, key=lambda m: m.key),
                         [kc.Mix(0, 3, 4, 3, 3), kc.Mix(7, 3, 4, 4, 3)])

    def test_file_without_block_parses_as_none(self):
        self.assertIsNone(kc.parse_team_block("assignTeamTournament(383,7)\n", 383))


class ApplyBlockTests(unittest.TestCase):
    ORIGINAL = "--Palmeiras\r\nassignTeamTournament(383,7)\r\nswapTeamKit(383, 0, 5)\r\n"

    def test_block_is_appended_keeping_crlf_and_the_rest_of_the_file(self):
        text = kc.apply_team_block(self.ORIGINAL, _sample())
        self.assertTrue(text.startswith(self.ORIGINAL))
        self.assertNotIn("\n", text.replace("\r\n", ""))

    def test_saving_again_replaces_instead_of_duplicating(self):
        tc = _sample()
        once = kc.apply_team_block(self.ORIGINAL, tc)
        tc.items[0].name = "Renamed"
        twice = kc.apply_team_block(once, tc)
        self.assertEqual(twice.count(kc.BLOCK_PREFIX), 1)
        self.assertIn("-- Renamed", twice)

    def test_removing_every_mix_leaves_a_cleanup_block_until_the_next_save(self):
        tc = _sample()
        text = kc.apply_team_block(self.ORIGINAL, tc)
        for combo in tc.items:
            combo.mixes = []
        cleaned = kc.apply_team_block(text, tc)
        self.assertTrue(cleaned.startswith(self.ORIGINAL))
        self.assertIn("No combinations left", cleaned)
        self.assertIn("local keep = {[0]=true}", cleaned)   # the file's own swapTeamKit(383, 0, 5)
        parsed = kc.parse_team_block(cleaned, 383)
        self.assertFalse(parsed.has_mixes() or parsed.has_gk)
        self.assertEqual((parsed.home, parsed.away), (None, None))
        self.assertEqual(kc.apply_team_block(cleaned, tc), self.ORIGINAL)

    def test_cleanup_keeps_the_kits_this_block_and_the_file_swap(self):
        text = kc.apply_team_block(self.ORIGINAL, _sample())
        self.assertIn("local keep = {[0]=true,[1]=true,[22300]=true}", text)

    def test_swaps_outside_the_block_are_reported(self):
        text = kc.apply_team_block(self.ORIGINAL, _sample())
        self.assertEqual(kc.external_swap_slots(text, 383), {(0, 0)})


class TeamCombinationsTests(unittest.TestCase):
    def test_removing_a_combination_keeps_selections_on_the_same_items(self):
        tc = _sample()
        tc.home, tc.away = 2, 1
        tc.remove(0)
        self.assertEqual((tc.home, tc.away), (1, 0))
        tc.remove(0)
        self.assertEqual((tc.home, tc.away), (0, None))

    def test_unique_name(self):
        tc = _sample()
        self.assertEqual(tc.unique_name("Empty"), "Empty (2)")
        self.assertEqual(tc.unique_name("New"), "New")

    def test_side_conflicts_are_kits_both_sides_mix_differently(self):
        tc = kc.TeamCombinations(1860, [
            kc.Combination("Home", [kc.Mix(0, 0, 1, 0, 0), kc.Mix(0, 1, 1, 0, 1), kc.Mix(0, 3, 3, 1, 3)]),
            kc.Combination("Away", [kc.Mix(0, 0, 0, 1, 0), kc.Mix(0, 1, 1, 0, 1), kc.Mix(0, 2, 2, 0, 2)]),
        ], home=0, away=1)
        self.assertEqual(tc.side_conflicts(), [(0, 0)])   # kit 1 is the same mix on both
        tc.away = 0
        self.assertEqual(tc.side_conflicts(), [])
        tc.away = None
        self.assertEqual(tc.side_conflicts(), [])


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.exedir = Path(self._tmp.name)
        self.logs: list[str] = []
        self.runtime = kc.KitClassicRuntime(SimpleNamespace(exedir=self.exedir, log=self.logs.append))
        self.teams = self.runtime.team_lua_dir()
        self.teams.mkdir(parents=True)

    def tearDown(self):
        self._tmp.cleanup()

    def _install_player_lua(self, text: str = SUPPORTED_PLAYER_LUA) -> None:
        path = self.runtime.player_lua_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def test_old_player_lua_is_detected_and_refuses_to_save(self):
        self.assertIsNone(self.runtime.missing_player_lua_functions())
        self._install_player_lua("function swapTeamKit(team,type1,type2)\nend\n")
        self.assertIn("getIndividualKitPart", self.runtime.missing_player_lua_functions())
        with self.assertRaises(RuntimeError):
            self.runtime.save(_sample())
        self.assertFalse(self.runtime.team_lua_path(383).exists())

    def test_save_writes_block_and_backs_up_the_untouched_file_once(self):
        self._install_player_lua()
        original = b"--Palmeiras \xe9\r\nswapTeamKit(383, 1, 3)\r\n"   # cp1252 byte must survive
        self.runtime.team_lua_path(383).write_bytes(original)
        path, clashes = self.runtime.save(_sample())
        data = path.read_bytes()
        self.assertTrue(data.startswith(original))
        self.assertIn(b"KITMIXER:BEGIN", data)
        self.assertEqual(clashes, [(0, 1)])
        self.assertEqual(self.runtime.backup_path(383).read_bytes(), original)
        tc = self.runtime.load(383)
        tc.items[0].name = "Changed"
        self.runtime.save(tc)
        self.assertEqual(self.runtime.backup_path(383).read_bytes(), original)
        self.assertEqual(self.runtime.load(383).items[0].name, "Changed")
        self.assertEqual(list(self.teams.glob("*.tmp")), [])

    def test_empty_combinations_never_create_a_new_file(self):
        self._install_player_lua()
        self.runtime.save(kc.TeamCombinations(999, [kc.Combination("Empty")]))
        self.assertFalse(self.runtime.team_lua_path(999).exists())

    def test_goalkeeper_options_come_from_the_loose_kits(self):
        kit_dir = self.runtime.kit_dir()
        kit_dir.mkdir(parents=True)
        for name in ("kit_383_0_0.rx3", "kit_383_2_0.rx3", "kit_383_12_0.rx3", "kit_383_31_0.rx3", "kit_383_14_0.rx3"):
            (kit_dir / name).write_bytes(b"x")
        self.runtime.kits(refresh=True)
        self.assertEqual(self.runtime.gk_kit_options(383), [2, 12, 31])
        self.assertEqual(self.runtime.gk_kit_options(999), [2])

    def test_scan_kit_folder_indexes_loose_kits(self):
        kit_dir = self.runtime.kit_dir()
        kit_dir.mkdir(parents=True)
        for name in ("kit_383_0_0.rx3", "kit_383_1_0.rx3", "kit_383_1_223.rx3", "kit_383_150_0.rx3", "other.rx3"):
            (kit_dir / name).write_bytes(b"x")
        kits = self.runtime.kits(refresh=True)
        self.assertEqual({t: sorted(v) for t, v in kits[383].items()}, {0: [0, 1], 223: [1]})
        self.assertEqual(self.runtime.kit_path(383, 223, 0), kit_dir / "kit_383_0_0.rx3")


class GeneratedBlocksAcrossRestoreTests(unittest.TestCase):
    """KitMixRuntime restores team_<id>.lua as a whole file when the jersey name
    colour is reverted; that must not wipe (or roll back) Classic combinations."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.exedir = Path(self._tmp.name)
        app = SimpleNamespace(exedir=self.exedir, settings_ini=None, log=lambda *a, **k: None)
        self.kit_mixer = KitMixRuntime(app)
        self.classic = kc.KitClassicRuntime(app)
        path = self.classic.player_lua_path()
        path.parent.mkdir(parents=True)
        path.write_text(SUPPORTED_PLAYER_LUA, encoding="utf-8")
        self.lua = self.kit_mixer.team_lua_path("383")
        self.lua.parent.mkdir(parents=True)
        self.lua.write_text('identifyTeamKitColours(383,0,"006030","005a30","e7e8e7","006030")\n', encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def test_whole_file_restore_keeps_the_current_combinations(self):
        self.kit_mixer.apply_name_color("383", "0", "FF0000")
        tc = _sample()
        self.classic.save(tc)
        tc.items[0].name = "Saved after the backup"
        self.classic.save(tc)
        self.kit_mixer.restore_name_color_original("383")
        text = self.lua.read_text(encoding="utf-8")
        self.assertNotIn("FF0000", text)
        self.assertEqual(text.count(kc.BLOCK_PREFIX), 1)
        self.assertEqual(self.classic.load(383).items[0].name, "Saved after the backup")

    def test_restore_with_a_stale_block_in_the_backup_uses_the_live_one(self):
        self.classic.save(_sample())
        self.kit_mixer.apply_name_color("383", "0", "FF0000")   # backup now holds the first block
        tc = self.classic.load(383)
        tc.items[1].mixes = []
        self.classic.save(tc)
        self.kit_mixer.restore_name_color_original("383")
        self.assertEqual(self.classic.load(383).items[1].mixes, [])
        self.assertEqual(self.lua.read_text(encoding="utf-8").count(kc.BLOCK_PREFIX), 1)

    def test_per_kittype_reset_counts_as_fully_reverted_despite_the_block(self):
        # The original already has the call, so resetting the colour gives back
        # the original text -- apart from the Classic block, which must not count.
        self.lua.write_text("assignKitDetails(383,0,-1,-1,-1,-1,-1,-1,-1,-1)\n", encoding="utf-8")
        self.kit_mixer.apply_name_color("383", "0", "FF0000")
        self.classic.save(_sample())
        self.kit_mixer.restore_name_color_for_kittype("383", "0")
        self.assertFalse(self.kit_mixer.has_backup_name_color("383"))
        self.assertIsNotNone(self.classic.load(383))

    def test_restore_of_a_file_that_did_not_exist_keeps_only_the_block(self):
        self.lua.unlink()
        self.kit_mixer.apply_name_color("383", "0", "FF0000")   # empty-marker backup
        self.classic.save(_sample())
        self.kit_mixer.restore_name_color_original("383")
        text = self.lua.read_text(encoding="utf-8")
        self.assertTrue(text.startswith(kc.BLOCK_PREFIX))
        self.assertNotIn("assignKitDetails", text)


def _rx3(textures: list[tuple[int, int, int, bytes]]) -> bytes:
    """Minimal RX3: one texture table + texture sections. textures = (fmt, w, h, data)."""
    count = 1 + len(textures)
    header_size = 16 + 16 * count
    table = struct.pack("<I", len(textures)) + b"\0" * 12
    for fmt, w, h, _data in textures:
        entry = bytearray(16)
        entry[5] = fmt
        struct.pack_into("<HH", entry, 8, w, h)
        entry[14] = 1
        table += bytes(entry)
    entries = [(art.RX3_TYPE_TABLE, header_size, len(table))]
    body = table
    for _fmt, _w, _h, data in textures:
        entries.append((art.RX3_TYPE_TEXTURE, header_size + len(body), len(data)))
        body += data
    head = art.RX3_MAGIC + b"\0" * 8 + struct.pack("<I", count)
    return head + b"".join(struct.pack("<IIII", t, o, s, 0) for t, o, s in entries) + body


def _solid_dxt1(w: int, h: int, color565: int) -> bytes:
    return struct.pack("<HHI", color565, color565, 0) * ((w // 4) * (h // 4))


class ArtTests(unittest.TestCase):
    RED, BLUE = 0xF800, 0x001F

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.kit = self.dir / "kit_383_0_0.rx3"
        self.kit.write_bytes(_rx3([(0, 32, 32, _solid_dxt1(32, 32, self.RED)),
                                   (0, 32, 16, _solid_dxt1(32, 16, self.BLUE)),
                                   (2, 16, 16, b"\0" * 256)]))

    def tearDown(self):
        self._tmp.cleanup()

    def test_picks_the_square_shirt_and_the_wide_atlas(self):
        shirt, atlas = art.pick_textures(art.parse_rx3(self.kit))
        self.assertEqual((shirt.w, shirt.h, atlas.w, atlas.h), (32, 32, 32, 16))

    def test_icon_is_painted_with_the_kit_textures_and_cached(self):
        cache = self.dir / "cache"
        factory = art.IconFactory(lambda team, tourn, k: self.kit if k == 0 else None, cache)
        png = factory.icon_png(383, 0, 0, 0, 0, size=56)
        image = Image.open(io.BytesIO(png)).convert("RGBA")
        w, h = art.art_size(56)
        self.assertEqual(image.size, (w, h))
        r, g, b, a = image.getpixel((w // 2, int(h * 0.3)))     # shirt body
        self.assertTrue(a > 200 and r > 150 and b < 80)
        r, g, b, a = image.getpixel((int(w * 0.39), int(h * 0.95)))   # left sock
        self.assertTrue(a > 200 and b > 150 and r < 80)
        self.assertEqual(len(list(cache.glob("*.png"))), 1)

    def test_render_from_paths_mixes_rx3_and_imported_image_sources(self):
        # An imported image is the texture itself: a solid green image as the shorts+socks texture.
        image_path = self.dir / "shorts.png"
        Image.new("RGB", (32, 16), (0, 200, 0)).save(image_path)
        factory = art.IconFactory(lambda *a: None, None)
        image = Image.open(io.BytesIO(factory.render_png(self.kit, image_path, image_path, size=56))).convert("RGBA")
        w, h = art.art_size(56)
        r, g, b, a = image.getpixel((w // 2, int(h * 0.3)))       # shirt from the rx3: red
        self.assertTrue(a > 200 and r > 150 and g < 80)
        r, g, b, a = image.getpixel((int(w * 0.39), int(h * 0.95)))   # sock from the image: green
        self.assertTrue(a > 200 and g > 150 and r < 80)

    def test_large_render_uses_full_resolution_textures(self):
        factory = art.IconFactory(lambda *a: None, None)
        factory.render_png(self.kit, self.kit, self.kit, size=art.FULL_TEXTURE_SIZE)
        reduces = {key[3] for key in factory._textures}
        self.assertEqual(reduces, {1})
        factory.render_png(self.kit, self.kit, self.kit, size=56)
        self.assertEqual({key[3] for key in factory._textures}, {1, art.TEXTURE_REDUCE})

    def test_missing_kit_draws_grey(self):
        factory = art.IconFactory(lambda team, tourn, k: None, None)
        image = Image.open(io.BytesIO(factory.icon_png(1, 0, 0, 0, 0, size=56))).convert("RGBA")
        w, h = art.art_size(56)
        r, g, b, a = image.getpixel((w // 2, int(h * 0.3)))
        self.assertTrue(a > 200 and abs(r - g) < 10 and abs(g - b) < 10)


try:
    from lupa import lua54 as _lua54
except ImportError:  # optional: only this class needs it
    _lua54 = None

PLAYER_LUA = Path(__file__).resolve().parent.parent / "install_data" / "data" / "fifarna" / "lua" / "assets" / "player.lua"


@unittest.skipUnless(_lua54 is not None and PLAYER_LUA.exists(), "lupa not installed")
class BlockRunsInRevModLuaTests(unittest.TestCase):
    """Runs a rendered block in Lua 5.4 against the real Rev Mod functions copied
    out of the bundled player.lua, with the engine (gSportsRNA, kit colours)
    stubbed. Optional: `pip install lupa` to run it."""

    FUNCTIONS = ("getIndividualKitPart", "swapTeamKit", "swapTeamKitTournament", "getSwapKit",
                 "assignGKKitPrecedence", "getGKKitPrecedenceList", "getGKKitPrecedenceRand", "getGKKitColour")

    def setUp(self):
        import re
        source = PLAYER_LUA.read_text(encoding="utf-8", errors="replace")
        self.lua = _lua54.LuaRuntime()
        for name in self.FUNCTIONS:
            # player.lua isn't indented, so a function runs up to the next one.
            m = re.search(r"^function %s\(.*?(?=^function |\Z)" % name, source, re.S | re.M)
            self.assertIsNotNone(m, name)
            self.lua.execute(m.group(0))
        # wvPlayer 9 = home and 20 = away outfield player, what the block reads.
        self.lua.execute("""
            function getShirt1Colour() return -1 end
            function getShirt2Colour() return -1 end
            function getSockColour() return -1 end
            function getColourDistance() return 999 end
            HOME, AWAY, HOMEKIT, AWAYKIT = 0, 0, 0, 1
            gSportsRNA = {
              GetTable = function(self, name, idx) return {idx = idx} end,
              GetInt = function(self, t, field)
                if field == "teamid" or field == "kit" then
                  if t.idx == 9 then return HOME end
                  if t.idx == 20 then return AWAY end
                elseif field == "kitType" then
                  if t.idx == 9 then return HOMEKIT end
                  if t.idx == 20 then return AWAYKIT end
                end
                return 0
              end,
            }
        """)
        tc = kc.TeamCombinations(383, [kc.Combination("Home", [kc.Mix(0, 0, 0, 1, 0)]),
                                       kc.Combination("Away", [kc.Mix(0, 1, 1, 0, 1)])],
                                 home=0, away=1, gk_home=12)
        self.block = kc.render_team_block(tc)

    def _set(self, home: int, away: int, home_kit: int = 0, away_kit: int = 1) -> None:
        self.lua.execute(f"HOME, AWAY, HOMEKIT, AWAYKIT = {home}, {away}, {home_kit}, {away_kit}")

    def _load_match(self, home: int, away: int, home_kit: int = 0, away_kit: int = 1) -> None:
        # What V1.3.5's importTeamStatements does before loading the two team files.
        self.lua.execute("swapKit, swapKitTourn = {}, {} "
                         "gkKitOrder, gkKitOrderRand, gkKitOrderTourn, gkKitOrderRandTourn = {}, {}, {}, {}")
        self._set(home, away, home_kit, away_kit)
        self.lua.execute(self.block)

    def _run(self, block: str, prelude: str = "") -> None:
        # The team file running again WITHOUT a stadium load in between: the
        # game's swap and keeper tables still hold what the last run registered.
        self.lua.execute(prelude + "\n" + block)

    def test_home_side_gets_its_combination_and_forced_goalkeeper(self):
        self._load_match(383, 1041)
        get = self.lua.globals()
        self.assertEqual(get.getSwapKit(383, 0, 0), 4000100)
        self.assertEqual(get.getSwapKit(383, 1, 0), 1)   # only the away combination changes kit 1
        # The forced keeper doesn't depend on which outfield kit is worn.
        for outfield in (4000100, 0, 1, 3):
            self.assertEqual(get.getGKKitColour(383, 1041, outfield, 1, 0, 0, 0, 0, outfield, 1, -1), 12)

    def test_away_side_gets_its_combination_and_an_automatic_goalkeeper(self):
        self._load_match(1041, 383)
        get = self.lua.globals()
        self.assertEqual(get.getSwapKit(383, 1, 0), 4010001)
        self.assertEqual(get.getSwapKit(383, 0, 0), 0)
        self.assertEqual(get.getGKKitPrecedenceList(383, 1, 0, 0), -1)

    def test_original_kits_for_one_side_ignore_the_other_sides_mixes(self):
        tc = kc.TeamCombinations(1860, [kc.Combination("Away", [kc.Mix(0, 0, 0, 1, 3), kc.Mix(0, 3, 3, 1, 0)])],
                                 home=None, away=0)
        self.block = kc.render_team_block(tc)
        get = self.lua.globals()
        self._load_match(1860, 1041)
        self.assertEqual(get.getSwapKit(1860, 0, 0), 0)
        self.assertEqual(get.getSwapKit(1860, 3, 0), 3)
        self._load_match(1041, 1860)
        self.assertEqual(get.getSwapKit(1860, 0, 0), 4000103)
        self.assertEqual(get.getSwapKit(1860, 3, 0), 4030100)

    def test_block_without_goalkeeper_and_with_a_tournament_mix(self):
        self.block = kc.render_team_block(_sample())
        get = self.lua.globals()
        self._load_match(1041, 383)   # away: "Away mixed"
        self.assertEqual(get.getSwapKit(383, 1, 0), 4010001)
        self.assertEqual(get.getSwapKit(383, 0, 223), 4000101)
        self.assertEqual(get.getSwapKit(383, 0, 0), 0)
        self._load_match(383, 1041)   # home: "Home green socks"; the tournament slot is reset
        self.assertEqual(get.getSwapKit(383, 0, 0), 4000001)
        self.assertEqual(get.getSwapKit(383, 0, 223), 0)
        self.assertEqual(get.getSwapKit(383, 1, 0), 1)

    def test_a_kit_both_combinations_change_goes_to_the_detected_side(self):
        tc = kc.TeamCombinations(383, [kc.Combination("Home", [kc.Mix(0, 0, 0, 1, 0)]),
                                       kc.Combination("Away", [kc.Mix(0, 0, 0, 0, 1)])],
                                 home=0, away=1)
        self.block = kc.render_team_block(tc)
        get = self.lua.globals()
        self._load_match(383, 1041)
        self.assertEqual(get.getSwapKit(383, 0, 0), 4000100)
        self._load_match(1041, 383)
        self.assertEqual(get.getSwapKit(383, 0, 0), 4000001)

    def test_side_comes_from_players_9_and_20_when_the_file_runs(self):
        # Dinei's approach: Rev Mod runs the file again right before it decides the
        # match kits. Until it runs again (kit menu arrows), the last reading holds.
        tc = kc.TeamCombinations(1860, [kc.Combination("Away", [kc.Mix(0, 0, 0, 1, 3)])], home=None, away=0)
        self.block = kc.render_team_block(tc)
        get = self.lua.globals()
        self._load_match(1041, 1860)
        self.assertEqual(get.getSwapKit(1860, 0, 0), 4000103)
        self._set(1860, 1041)
        self.assertEqual(get.getSwapKit(1860, 0, 0), 4000103)
        self._run(self.block)
        self.assertEqual(get.getSwapKit(1860, 0, 0), 0)

    def test_team_against_itself_gets_both_combinations(self):
        # Rev Mod picks both sides' kits in one PlayerUpdate from the single
        # swapKit[team] table; Dinei's block only registers the home combination.
        tc = kc.TeamCombinations(1860, [kc.Combination("Home", [kc.Mix(0, 0, 1, 2, 4)]),
                                        kc.Combination("Away", [kc.Mix(0, 1, 0, 1, 0)])],
                                 home=0, away=1)
        self.block = kc.render_team_block(tc)
        self._load_match(1860, 1860)
        get = self.lua.globals()
        self.assertEqual(get.getSwapKit(1860, 0, 0), 4010204)
        self.assertEqual(get.getSwapKit(1860, 1, 0), 4000100)

    def test_team_against_itself_resolves_each_kit_by_the_side_that_asks_for_it(self):
        tc = kc.TeamCombinations(1860, [kc.Combination("Home", [kc.Mix(0, 0, 1, 1, 0), kc.Mix(0, 1, 0, 0, 1)]),
                                        kc.Combination("Away", [kc.Mix(0, 0, 3, 3, 0)])],
                                 home=0, away=1)
        self.block = kc.render_team_block(tc)
        get = self.lua.globals()
        # Away side asks for kit 1, which the away combination leaves original.
        self._load_match(1860, 1860, home_kit=0, away_kit=1)
        self.assertEqual(get.getSwapKit(1860, 0, 0), 4010100)
        self.assertEqual(get.getSwapKit(1860, 1, 0), 1)
        self._load_match(1860, 1860, home_kit=1, away_kit=0)
        self.assertEqual(get.getSwapKit(1860, 1, 0), 4000001)
        self.assertEqual(get.getSwapKit(1860, 0, 0), 4030300)
        # Same kit on both sides: one swap per team and kit, the home one.
        self._load_match(1860, 1860, home_kit=0, away_kit=0)
        self.assertEqual(get.getSwapKit(1860, 0, 0), 4010100)

    def test_team_against_itself_gives_each_keeper_its_sides_choice(self):
        tc = kc.TeamCombinations(1860, [kc.Combination("Home", [kc.Mix(0, 0, 1, 2, 4)]),
                                        kc.Combination("Away", [kc.Mix(0, 1, 0, 1, 0)])],
                                 home=0, away=1, gk_home=12, gk_away=13)
        self.block = kc.render_team_block(tc)
        self._load_match(1860, 1860)
        get = self.lua.globals()
        # getGKKitColour looks the list up by the outfield shirt's kit: home shirt is
        # kit 1 (4010204), away shirt kit 0 (4000100).
        self.assertEqual(get.getGKKitColour(1860, 1860, 4010204, 4000100, 0, 0, 0, 0, 4010204, 4000100, -1), 12)
        self.assertEqual(get.getGKKitColour(1860, 1860, 4000100, 4010204, 0, 0, 0, 0, 4000100, 4010204, 12), 13)

    def test_a_removed_mix_does_not_stay_in_the_game_until_the_next_stadium_load(self):
        # Reported 2026-10-17: the kit 3 mix was deleted while FIFA sat in the kit
        # menu and kit 3 kept showing it.
        old = kc.TeamCombinations(1860, [kc.Combination("Home", [kc.Mix(0, 0, 1, 0, 3)]),
                                         kc.Combination("Away", [kc.Mix(0, 3, 3, 1, 0), kc.Mix(223, 1, 0, 1, 1)])],
                                  home=0, away=1)
        self._load_match(1041, 1860)
        self.lua.execute(kc.render_team_block(old))
        get = self.lua.globals()
        self.assertEqual(get.getSwapKit(1860, 3, 0), 4030100)
        self.assertEqual(get.getSwapKit(1860, 1, 223), 4000101)
        new = kc.TeamCombinations(1860, [kc.Combination("Home", [kc.Mix(0, 0, 1, 0, 3)]), kc.Combination("Away")],
                                  home=0, away=1)
        # Plus a mix some other writer (Dinei's tool) registered as a plain swap.
        self._run(kc.render_team_block(new), prelude="swapTeamKit(1860, 5, 4050505)")
        self.assertEqual(get.getSwapKit(1860, 3, 0), 3)
        self.assertEqual(get.getSwapKit(1860, 1, 223), 1)
        self.assertEqual(get.getSwapKit(1860, 5, 0), 5)
        self._set(1860, 1041)
        self._run(kc.render_team_block(new))
        self.assertEqual(get.getSwapKit(1860, 0, 0), 4010003)
        # Nothing left at all: the cleanup-only block undoes the rest.
        text = kc.apply_team_block("--Getafe\n" + kc.render_team_block(new), kc.TeamCombinations(1860))
        _, cleanup_block, _ = kc.split_marked(text, kc.BLOCK_PREFIX, kc.BLOCK_END)
        self._run(cleanup_block)
        self.assertEqual(get.getSwapKit(1860, 0, 0), 0)

    def test_cleanup_leaves_part_codes_the_rest_of_the_file_sets(self):
        tc = kc.TeamCombinations(1860, [kc.Combination("Home", [kc.Mix(0, 0, 1, 0, 3)])], home=0, away=None)
        self._load_match(1860, 1041)
        self._run(kc.render_team_block(tc, keep=[(0, 1)]), prelude="swapTeamKit(1860, 1, 4020202)")
        self.assertEqual(self.lua.globals().getSwapKit(1860, 1, 0), 4020202)

    def test_a_keeper_set_back_to_automatic_is_dropped_but_the_files_own_list_stays(self):
        mixes = [kc.Combination("Home", [kc.Mix(0, 0, 1, 0, 3)])]
        self._load_match(1860, 1041)
        self.lua.execute(kc.render_team_block(kc.TeamCombinations(1860, mixes, home=0, away=None, gk_home=12)))
        get = self.lua.globals()
        self.assertEqual(get.getGKKitPrecedenceList(1860, 0, 0, 0)[1], 12)
        self._run(kc.render_team_block(kc.TeamCombinations(1860, mixes, home=0, away=None)),
                  prelude="assignGKKitPrecedence(1860, 1, 0, {31})")
        self.assertEqual(get.getGKKitPrecedenceList(1860, 0, 0, 0), -1)
        self.assertEqual(get.getGKKitPrecedenceList(1860, 1, 0, 0)[1], 31)

    def test_team_not_in_the_match_keeps_its_original_kits(self):
        self._load_match(1, 2)
        get = self.lua.globals()
        self.assertEqual(get.getSwapKit(383, 0, 0), 0)
        self.assertEqual(get.getSwapKit(383, 1, 0), 1)
        self.assertEqual(get.getGKKitPrecedenceList(383, 0, 0, 0), -1)


if __name__ == "__main__":
    unittest.main()
