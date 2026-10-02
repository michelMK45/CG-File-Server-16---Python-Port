from __future__ import annotations

import tempfile
import unittest
import unittest.mock
from pathlib import Path

from server16_py.asset_runtime import AssetRuntime


class FakeIni:
    def __init__(self, data: dict[str, dict[str, str]]) -> None:
        self._data = data

    def read(self, key: str, section: str) -> str:
        return self._data.get(section, {}).get(key, "")


class FakeWipeApp:
    """Enough of Server16App for AssetRuntime.apply_wipe_runtime to run against
    a real on-disk install: FSW/wipe/<pack>/ sources, data/sceneassets/wipe3d/."""

    def __init__(self, base: Path) -> None:
        self.exedir = base
        self.TOURROUNDID = "103"
        self.settings_ini = FakeIni({"wipe": {"103": "OFC Qualifiers", "14": "CNB Qualifiers"}})
        self.wipe_enabled = True
        self.logs: list[str] = []

    def module_enabled(self, name: str) -> bool:
        return self.wipe_enabled if name == "Wipe" else False

    def tr(self, key: str) -> str:
        return key

    def log(self, *parts) -> None:
        self.logs.append(" ".join(str(p) for p in parts))


class ApplyWipeRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.app = FakeWipeApp(Path(self._tmp.name))
        self.wipe3d = self.app.exedir / "data" / "sceneassets" / "wipe3d"
        self.wipe3d.mkdir(parents=True)
        self.write(self.wipe3d / "specificwipe_0_996_0.rx3", b"vanilla 996")
        self.write(self.wipe3d / "specificwipe_0_992_0.rx3", b"vanilla 992")
        self.write(self.app.exedir / "FSW" / "wipe" / "OFC Qualifiers" / "specificwipe_0_996_0.rx3", b"ofc")
        self.write(self.app.exedir / "FSW" / "wipe" / "CNB Qualifiers" / "specificwipe_0_992_0.rx3", b"cnb")
        self.runtime = AssetRuntime(self.app)
        self.runtime._show_asset_toast = unittest.mock.Mock()
        self.runtime._show_warning_toast = unittest.mock.Mock()

    def write(self, path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def read(self, name: str) -> bytes:
        return (self.wipe3d / name).read_bytes()

    def test_assigned_round_overwrites_the_slot(self) -> None:
        self.runtime.apply_wipe_runtime()
        self.assertEqual(self.read("specificwipe_0_996_0.rx3"), b"ofc")
        self.assertEqual(self.read("specificwipe_0_992_0.rx3"), b"vanilla 992")
        self.runtime._show_asset_toast.assert_called_once()

    def test_switching_to_a_round_with_another_pack_puts_the_first_slot_back(self) -> None:
        self.runtime.apply_wipe_runtime()
        self.app.TOURROUNDID = "14"
        self.runtime.apply_wipe_runtime()
        self.assertEqual(self.read("specificwipe_0_996_0.rx3"), b"vanilla 996")
        self.assertEqual(self.read("specificwipe_0_992_0.rx3"), b"cnb")

    def test_a_round_without_a_wipe_gets_the_vanilla_files_back(self) -> None:
        self.runtime.apply_wipe_runtime()
        self.app.TOURROUNDID = "999"
        self.runtime.apply_wipe_runtime()
        self.assertEqual(self.read("specificwipe_0_996_0.rx3"), b"vanilla 996")
        self.assertIn("restored", "\n".join(self.app.logs))

    def test_a_missing_pack_folder_gets_the_vanilla_files_back(self) -> None:
        self.runtime.apply_wipe_runtime()
        self.app.settings_ini = FakeIni({"wipe": {"103": "Deleted Pack"}})
        self.runtime.apply_wipe_runtime()
        self.assertEqual(self.read("specificwipe_0_996_0.rx3"), b"vanilla 996")

    def test_turning_the_module_off_gets_the_vanilla_files_back_and_warns(self) -> None:
        self.runtime.apply_wipe_runtime()
        self.app.wipe_enabled = False
        self.runtime.apply_wipe_runtime()
        self.assertEqual(self.read("specificwipe_0_996_0.rx3"), b"vanilla 996")
        self.runtime._show_warning_toast.assert_called_once()

    def test_no_round_read_yet_leaves_an_installed_wipe_alone(self) -> None:
        self.runtime.apply_wipe_runtime()
        self.app.TOURROUNDID = ""
        self.runtime.apply_wipe_runtime()
        self.assertEqual(self.read("specificwipe_0_996_0.rx3"), b"ofc")

    def test_applying_the_same_round_twice_keeps_the_original_backed_up(self) -> None:
        self.runtime.apply_wipe_runtime()
        self.runtime.apply_wipe_runtime()
        self.app.TOURROUNDID = "999"
        self.runtime.apply_wipe_runtime()
        self.assertEqual(self.read("specificwipe_0_996_0.rx3"), b"vanilla 996")


if __name__ == "__main__":
    unittest.main()
