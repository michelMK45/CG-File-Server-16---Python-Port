from __future__ import annotations

import json
import struct
import tempfile
import unittest
import unittest.mock
from pathlib import Path

from server16_py import ingame_hubpatch, ingame_menu_install, ingame_modinstall

KICKOFF = "data/ui/game/screens/playnow/kickoffhub.big"
NAV = "data/ui/nav/kickoffhubflow.nav"
FLOW = "data/ui/nav/cgfs16menuflow.nav"
VANILLA_KICKOFF_SHA1 = "e1d6cb580f9f4d82cae36a6819cc83d4f4284021"   # FIFA 16's own kickoffhub.big
REAL_PACKAGE_DIR = ingame_menu_install.package_dir
REAL_PATCHES = ingame_hubpatch.PATCHES


def big4(files: list[tuple[str, bytes]]) -> bytes:
    """A small uncompressed BIG4 archive (entry offsets from the start of the file)."""
    names = b"".join(struct.pack(">II", 0, 0) + n.encode() + b"\0" for n, _ in files)
    pos = 16 + len(names)
    table, body = b"", b""
    for name, blob in files:
        table += struct.pack(">II", pos, len(blob)) + name.encode() + b"\0"
        body += blob
        pos += len(blob)
    return b"BIG4" + struct.pack("<I", pos) + struct.pack(">II", len(files), len(table)) + table + body


def bh(count: int) -> bytes:
    return b"ViV4" + bytes(4) + struct.pack(">I", count) + bytes(4) + b"".join(
        bytes(12) + bytes([i + 1]) * 8 for i in range(count))


def fake_patch(text: str) -> str:
    return text if "CGFS16-INGAME" in text else text + "/* CGFS16-INGAME BEGIN */,{}/* CGFS16-INGAME END */\n"


def fake_unpatch(text: str) -> str:
    return text.replace("/* CGFS16-INGAME BEGIN */,{}/* CGFS16-INGAME END */\n", "")


class InGameMenuInstallTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        self.game = self.base / "game"
        self.game.mkdir()
        (self.game / "fifa16.exe").write_bytes(b"")
        self.kickoff = b"FIFA's own kickoffhub"
        entries = [(KICKOFF, self.kickoff), (NAV, b'{"states":[]}\n')]
        (self.game / "data_front_end.big").write_bytes(big4(entries))
        (self.game / "data_front_end.bh").write_bytes(bh(len(entries)))
        self.package = self.base / "mod"
        ingame_modinstall.write_package(
            str(self.package), {"version": "fase4-pestanas", "installed": "2026-11-11 12:53", "screen": "menu"},
            {FLOW: b"our flow", "data/ui/cgfs16/data.big": b"data"},
            {KICKOFF: {ingame_modinstall.sha1(self.kickoff): b"hooked kickoffhub"}})
        self._patch(ingame_menu_install, "package_dir", lambda: self.package)
        self._patch(ingame_modinstall, "game_running", lambda: False)
        self._patch(ingame_hubpatch, "PATCHES", {NAV: (fake_patch, fake_unpatch)})
        self._patch(ingame_hubpatch, "check_patched", lambda rel, text: None)
        self.logs: list[str] = []

    def _patch(self, target, name, value) -> None:
        patcher = unittest.mock.patch.object(target, name, value)
        patcher.start()
        self.addCleanup(patcher.stop)

    def snapshot(self) -> dict[str, bytes]:
        return {p.relative_to(self.game).as_posix(): p.read_bytes() for p in self.game.rglob("*") if p.is_file()}

    def test_bundled_package_is_complete(self) -> None:
        folder = REAL_PACKAGE_DIR()
        self.assertIsNotNone(folder, "resources/ingame/mod missing: cgfs-ingame `ingame.py release`")
        info, files = ingame_modinstall.load_package(str(folder))
        self.assertEqual(info["screen"], "menu")
        for rel in ("data/ui/game/screens/cgfs16/cgfs16menu.big", "data/ui/cgfs16/menudata.big",
                    "data/ui/cgfs16/img/logo.dds", FLOW):
            self.assertIn(rel, files)
        self.assertTrue(callable(files[KICKOFF]))
        index = json.loads((folder / ingame_modinstall.PACKAGE_INFO).read_text(encoding="utf-8"))
        self.assertIn(VANILLA_KICKOFF_SHA1, index["variants"][KICKOFF])
        self.assertEqual(set(REAL_PATCHES), {   # R3 on the match hub; no hub tile any more
            NAV, "data/ui/nav/careermode/playmatchflow.nav", "data/ui/nav/fut/quicksettingsflow.nav"})
        self.assertNotIn("data/ui/imgassets/tiles/mainhub/cgfs16menu.dds", files)
        self.assertEqual(set(ingame_hubpatch.RETIRED), {"data/ui/layout/mainhubcfg.xml", "data/ui/nav/mainfeflow.nav"})

    def test_install_status_uninstall(self) -> None:
        before = self.snapshot()
        self.assertEqual(ingame_menu_install.status(self.game).installed, None)
        st = ingame_menu_install.install(self.game, self.logs.append)
        self.assertTrue(st.up_to_date and not st.without_r3)
        self.assertEqual((self.game / KICKOFF).read_bytes(), b"hooked kickoffhub")
        self.assertEqual((self.game / FLOW).read_bytes(), b"our flow")
        self.assertIn("CGFS16-INGAME", (self.game / NAV).read_text())
        game = ingame_modinstall.GameFiles(str(self.game))
        self.assertTrue(game.hash_zeroed(KICKOFF) and game.hash_zeroed(NAV))   # FIFA reads the loose files
        man = ingame_modinstall.load_manifest(game)
        self.assertEqual(man["source"], "CG Server 16")
        ingame_menu_install.install(self.game, self.logs.append)   # again: an update over itself
        (self.game / "data/ui/cgfs16/img").mkdir(parents=True)
        (self.game / "data/ui/cgfs16/img/preview.dds").write_bytes(b"made by the app")
        self.assertTrue(ingame_menu_install.uninstall(self.game, self.logs.append))
        self.assertEqual(self.snapshot(), before | {"_bh_original/data_front_end.bh": before["data_front_end.bh"]})
        self.assertFalse(ingame_menu_install.uninstall(self.game, self.logs.append))

    def test_older_build_shows_an_update(self) -> None:
        ingame_menu_install.install(self.game, self.logs.append)
        path = Path(ingame_modinstall.manifest_path(ingame_modinstall.GameFiles(str(self.game))))
        man = json.loads(path.read_text(encoding="utf-8"))
        man["installed"] = "2026-11-10 21:48"
        path.write_text(json.dumps(man), encoding="utf-8")
        st = ingame_menu_install.status(self.game)
        self.assertEqual((st.installed, st.bundled, st.up_to_date), ("2026-11-10 21:48", "2026-11-11 12:53", False))

    def test_unknown_kickoffhub_installs_without_r3(self) -> None:
        (self.game / KICKOFF).parent.mkdir(parents=True)
        (self.game / KICKOFF).write_bytes(b"another mod's kickoffhub")
        st = ingame_menu_install.install(self.game, self.logs.append)
        self.assertTrue(st.without_r3)
        self.assertEqual((self.game / KICKOFF).read_bytes(), b"another mod's kickoffhub")
        self.assertTrue((self.game / FLOW).exists())

    def test_refused_while_fifa_runs(self) -> None:
        self._patch(ingame_modinstall, "game_running", lambda: True)
        with self.assertRaises(ingame_menu_install.FifaRunning):
            ingame_menu_install.install(self.game, self.logs.append)
        with self.assertRaises(ingame_menu_install.FifaRunning):
            ingame_menu_install.uninstall(self.game, self.logs.append)
        self.assertFalse((self.game / FLOW).exists())


if __name__ == "__main__":
    unittest.main()
