from __future__ import annotations

import ctypes
import tempfile
import unittest
import unittest.mock
from pathlib import Path
from types import SimpleNamespace

from server16_py import net_ropes
from server16_py.app_ui import UIMixin
from server16_py.net_ropes import RopesBridge, compose_net_value, rope_level, split_net_value


class RopeLevelParsingTests(unittest.TestCase):
    def test_classic_five_field_value_has_no_level(self) -> None:
        self.assertIsNone(rope_level("1089199011,1087199011,2,0,0"))
        self.assertIsNone(rope_level(""))
        self.assertIsNone(rope_level(None))

    def test_sixth_field_is_the_level(self) -> None:
        for level in (0, 1, 2, 3):
            with self.subTest(level=level):
                self.assertEqual(rope_level(f"1,2,3,0,0,{level}"), level)

    def test_invalid_sixth_field_is_no_level(self) -> None:
        self.assertIsNone(rope_level("1,2,3,0,0,7"))
        self.assertIsNone(rope_level("1,2,3,0,0,"))

    def test_author_seven_field_value_with_physics(self) -> None:
        # down,high,rig,shape,tension,ropes,physics (forum author's build)
        self.assertEqual(rope_level("1,2,4,0,0,2,3"), 2)

    def test_author_legacy_eight_field_flags(self) -> None:
        # down,high,rig,shape,tension,hide_centre,hide_top,hide_all
        self.assertEqual(rope_level("1,2,4,0,0,0,0,0"), 0)
        self.assertEqual(rope_level("1,2,4,0,0,1,0,0"), 1)
        self.assertEqual(rope_level("1,2,4,0,0,1,1,0"), 2)
        self.assertEqual(rope_level("1,2,4,0,0,0,0,1"), 3)


class ComposeTests(unittest.TestCase):
    FIVE = ["1089199011", "1087199011", "2", "0", "0"]

    def test_level_zero_keeps_the_classic_five_fields(self) -> None:
        self.assertEqual(compose_net_value(self.FIVE, 0), "1089199011,1087199011,2,0,0")

    def test_other_levels_add_the_sixth_field(self) -> None:
        self.assertEqual(compose_net_value(self.FIVE, 3), "1089199011,1087199011,2,0,0,3")

    def test_fields_after_the_level_are_kept_even_at_level_zero(self) -> None:
        level, extra = split_net_value("1,2,4,0,0,0,3")
        self.assertEqual((level, extra), (0, ["3"]))
        self.assertEqual(compose_net_value(["1", "2", "4", "0", "0"], level, extra), "1,2,4,0,0,0,3")

    def test_legacy_flags_are_converted_not_kept(self) -> None:
        level, extra = split_net_value("1,2,4,0,0,1,1,0")
        self.assertEqual((level, extra), (2, []))
        self.assertEqual(compose_net_value(["1", "2", "4", "0", "0"], level, extra), "1,2,4,0,0,2")

    def test_round_trip_of_every_level(self) -> None:
        for level in (0, 1, 2, 3):
            with self.subTest(level=level):
                value = compose_net_value(self.FIVE, level)
                self.assertEqual(rope_level(value), None if level == 0 else level)
                self.assertEqual(split_net_value(value)[0], level)


def _make_game(root: Path, loader: bool = True) -> Path:
    game = root / "game"
    game.mkdir()
    if loader:
        (game / "winmm.dll").write_bytes(b"MZ..." + "FIFA Plugin Loader".encode("utf-16-le") + b"...")
    return game


def _make_bundle(root: Path, payload: bytes = b"MZ ropes v2") -> Path:
    (root / "res" / "bin").mkdir(parents=True)
    (root / "res" / "bin" / net_ropes.PLUGIN_FILE).write_bytes(payload)
    return root / "res"


class PluginFileTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def test_states(self) -> None:
        resource = _make_bundle(self.root)
        bundled = net_ropes.bundled_plugin(resource)
        (self.root / "bare").mkdir()
        no_loader_game = _make_game(self.root / "bare", loader=False)
        self.assertEqual(net_ropes.plugin_state(no_loader_game, bundled), net_ropes.STATE_NO_LOADER)
        game = _make_game(self.root)
        self.assertEqual(net_ropes.plugin_state(game, bundled), net_ropes.STATE_MISSING)
        (game / "plugins").mkdir()
        (game / "plugins" / "SERVER16_Ropes.asi.disabled").write_bytes(b"MZ ropes v2")
        self.assertEqual(net_ropes.plugin_state(game, bundled), net_ropes.STATE_DISABLED)
        (game / "plugins" / "SERVER16_Ropes.asi").write_bytes(b"MZ ropes v1")
        self.assertEqual(net_ropes.plugin_state(game, bundled), net_ropes.STATE_OUTDATED)
        (game / "plugins" / "SERVER16_Ropes.asi").write_bytes(b"MZ ropes v2")
        self.assertEqual(net_ropes.plugin_state(game, bundled), net_ropes.STATE_INSTALLED)
        # A build without the bundled file cannot call anything outdated.
        self.assertIsNone(net_ropes.bundled_plugin(self.root / "nowhere"))
        (game / "plugins" / "SERVER16_Ropes.asi").write_bytes(b"other")
        self.assertEqual(net_ropes.plugin_state(game, None), net_ropes.STATE_INSTALLED)

    def test_install_creates_the_plugins_folder(self) -> None:
        bundled = net_ropes.bundled_plugin(_make_bundle(self.root))
        game = _make_game(self.root)
        target = net_ropes.install_plugin(game, bundled)
        self.assertEqual(target, game / "plugins" / "SERVER16_Ropes.asi")
        self.assertEqual(target.read_bytes(), b"MZ ropes v2")
        self.assertEqual(net_ropes.plugin_state(game, bundled), net_ropes.STATE_INSTALLED)

    def test_install_keeps_a_switched_off_plugin_off(self) -> None:
        bundled = net_ropes.bundled_plugin(_make_bundle(self.root))
        game = _make_game(self.root)
        (game / "plugins").mkdir()
        disabled = game / "plugins" / "SERVER16_Ropes.asi.disabled"
        disabled.write_bytes(b"MZ ropes v1")
        self.assertEqual(net_ropes.install_plugin(game, bundled), disabled)
        self.assertEqual(disabled.read_bytes(), b"MZ ropes v2")
        self.assertFalse((game / "plugins" / "SERVER16_Ropes.asi").exists())


class LegacyNameTests(unittest.TestCase):
    """The first builds were called cgfs16_ropes.asi: Setup replaces them (two loaded copies would
    both hook D3D11) and keeps the user's ini."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        self.bundled = net_ropes.bundled_plugin(_make_bundle(root))
        self.game = _make_game(root)
        self.plugins = self.game / "plugins"
        self.plugins.mkdir()

    def test_old_name_alone_reads_as_outdated(self) -> None:
        (self.plugins / "cgfs16_ropes.asi").write_bytes(b"MZ ropes v2")
        self.assertEqual(net_ropes.plugin_state(self.game, self.bundled), net_ropes.STATE_OUTDATED)

    def test_old_copy_next_to_the_new_one_is_outdated_too(self) -> None:
        (self.plugins / "SERVER16_Ropes.asi").write_bytes(b"MZ ropes v2")
        (self.plugins / "cgfs16_ropes.asi").write_bytes(b"MZ ropes v1")
        self.assertEqual(net_ropes.plugin_state(self.game, self.bundled), net_ropes.STATE_OUTDATED)

    def test_install_replaces_the_old_name_and_carries_the_ini_over(self) -> None:
        (self.plugins / "cgfs16_ropes.asi").write_bytes(b"MZ ropes v1")
        (self.plugins / "cgfs16_ropes.ini").write_text("[ROPES]\r\nLevel=3\r\n", encoding="utf-8")
        (self.plugins / "cgfs16_ropes.log").write_text("old", encoding="utf-8")
        target = net_ropes.install_plugin(self.game, self.bundled)
        self.assertEqual(target, self.plugins / "SERVER16_Ropes.asi")
        self.assertEqual(sorted(p.name for p in self.plugins.iterdir()), ["SERVER16_Ropes.asi", "SERVER16_Ropes.ini"])
        self.assertIn("Level=3", (self.plugins / "SERVER16_Ropes.ini").read_text(encoding="utf-8"))
        self.assertEqual(net_ropes.plugin_state(self.game, self.bundled), net_ropes.STATE_INSTALLED)

    def test_new_ini_wins_over_the_old_one(self) -> None:
        (self.plugins / "cgfs16_ropes.asi").write_bytes(b"MZ ropes v1")
        (self.plugins / "cgfs16_ropes.ini").write_text("Level=3", encoding="utf-8")
        (self.plugins / "SERVER16_Ropes.ini").write_text("Level=1", encoding="utf-8")
        net_ropes.install_plugin(self.game, self.bundled)
        self.assertEqual((self.plugins / "SERVER16_Ropes.ini").read_text(encoding="utf-8"), "Level=1")

    def test_a_switched_off_old_copy_stays_off_under_the_new_name(self) -> None:
        (self.plugins / "cgfs16_ropes.asi.disabled").write_bytes(b"MZ ropes v1")
        target = net_ropes.install_plugin(self.game, self.bundled)
        self.assertEqual(target, self.plugins / "SERVER16_Ropes.asi.disabled")
        self.assertFalse((self.plugins / "cgfs16_ropes.asi.disabled").exists())
        self.assertEqual(net_ropes.plugin_state(self.game, self.bundled), net_ropes.STATE_DISABLED)


class SetupInstallTests(unittest.TestCase):
    """UIMixin._install_ropes_plugin_blocking (Run Setup worker) on a stand-in app."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.logs: list[str] = []
        self.after_calls: list = []
        self.app = SimpleNamespace(
            resource_dir=_make_bundle(self.root),
            exedir=_make_game(self.root),
            log=self.logs.append,
            after=lambda delay, fn: self.after_calls.append(fn),
        )
        self.app._ropes_plugin_fifa_running = lambda: None

    def run_install(self) -> bool:
        return UIMixin._install_ropes_plugin_blocking(self.app)

    def test_installs_the_bundled_plugin(self) -> None:
        self.assertTrue(self.run_install())
        self.assertTrue((self.app.exedir / "plugins" / "SERVER16_Ropes.asi").is_file())
        self.assertIn("Ropes plugin: installed", self.logs[-1])

    def test_loaded_plugin_while_fifa_runs_asks_to_close_fifa(self) -> None:
        with unittest.mock.patch.object(net_ropes, "install_plugin", side_effect=PermissionError("in use")):
            self.assertFalse(self.run_install())
        self.assertEqual(len(self.after_calls), 1)
        self.assertIn("FIFA 16 has it loaded", self.logs[-1])

    def test_build_without_the_plugin_installs_nothing(self) -> None:
        self.app.resource_dir = self.root / "empty"
        self.assertFalse(self.run_install())
        self.assertFalse((self.app.exedir / "plugins").exists())


class SharedLayoutTests(unittest.TestCase):
    def test_struct_matches_the_plugin_layout(self) -> None:
        # RopesShared in server16_py/ropes_plugin/SERVER16_Ropes.cpp: 64 bytes, pack 4.
        cls = net_ropes._RopesShared
        self.assertEqual(ctypes.sizeof(cls), 64)
        offsets = {name: getattr(cls, name).offset for name, _ in cls._fields_}
        self.assertEqual(
            offsets,
            {"magic": 0, "version": 4, "level": 8, "plugin_flags": 12, "rope_draws": 16,
             "rope_draws_cut": 20, "effective_level": 24, "reserved": 28},
        )


class RopesBridgeTests(unittest.TestCase):
    """Against a real named mapping (a test-only name, so a running FIFA is never touched)."""

    def setUp(self) -> None:
        patcher = unittest.mock.patch.object(net_ropes, "SHARED_NAME", f"Local\\CGFS16_Ropes_test_{id(self)}")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_creating_side_initialises_the_header_and_not_set_level(self) -> None:
        bridge = RopesBridge()
        self.addCleanup(bridge.close)
        self.assertTrue(bridge.set_level(None))
        shared = bridge._shared
        self.assertEqual((shared.magic, shared.version, shared.level), (net_ropes.MAGIC, 1, net_ropes.NOT_SET))
        self.assertFalse(bridge.plugin_active())

    def test_levels_are_visible_to_a_second_view_like_the_plugin(self) -> None:
        server = RopesBridge()
        plugin = RopesBridge()
        self.addCleanup(server.close)
        self.addCleanup(plugin.close)
        server.set_level(2)
        plugin._open()
        self.assertEqual(plugin._shared.level, 2)
        server.set_level(9)  # not a level -> "not set"
        self.assertEqual(plugin._shared.level, net_ropes.NOT_SET)
        plugin._shared.plugin_flags = net_ropes.FLAG_DEVICE_HOOKED | 1
        self.assertTrue(server.plugin_active())


if __name__ == "__main__":
    unittest.main()
