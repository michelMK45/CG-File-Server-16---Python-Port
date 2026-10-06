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


class FakeApp:
    """Enough of Server16App for AssetRuntime.apply_ball_runtime /
    apply_referee_runtime to run against a real on-disk install."""

    def __init__(self, base: Path) -> None:
        self.exedir = base
        self.TOURROUNDID = "103"
        self.settings_ini = FakeIni({
            "ball": {"103": "Ball A", "14": "Ball B"},
            "referee": {"103": "Ref A", "14": "Ref B"},
        })
        self.enabled = {"Ball": True, "Referee": True}
        self._kickoff_generation = 1
        self._active_ball_runtime = None
        self.logs: list[str] = []

    def module_enabled(self, name: str) -> bool:
        return self.enabled.get(name, False)

    def tr(self, key: str) -> str:
        return key

    def log(self, *parts) -> None:
        self.logs.append(" ".join(str(p) for p in parts))


class _Base:
    """Shared cases; subclasses set module/section/src_root/target/apply."""

    module = ""
    src_root = ""
    target = ""
    apply_name = ""
    icon = ""  # resources/rmlui/icons/<icon>.png shown on the module's toasts
    file_a = "specific_a.rx3"
    file_b = "specific_b.rx3"

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.app = FakeApp(Path(self._tmp.name))
        self.dst = self.app.exedir / "data" / "sceneassets" / self.target
        self.dst.mkdir(parents=True)
        self.write(self.dst / self.file_a, b"vanilla a")
        self.write(self.dst / self.file_b, b"vanilla b")
        fsw = self.app.exedir / "FSW" / self.src_root
        self.write(fsw / self.pack("A") / self.file_a, b"pack A")
        self.write(fsw / self.pack("B") / self.file_b, b"pack B")
        self.write(fsw / self.pack("A") / "extra_new.rx3", b"new in A")
        self.runtime = AssetRuntime(self.app)
        self.runtime._show_asset_toast = unittest.mock.Mock()
        self.runtime._show_warning_toast = unittest.mock.Mock()

    def pack(self, letter: str) -> str:
        return f"{'Ball' if self.module == 'Ball' else 'Ref'} {letter}"

    def write(self, path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def read(self, name: str) -> bytes:
        return (self.dst / name).read_bytes()

    def apply(self) -> None:
        getattr(self.runtime, self.apply_name)()

    def test_assigned_round_overwrites_the_slot(self) -> None:
        self.apply()
        self.assertEqual(self.read(self.file_a), b"pack A")
        self.assertEqual(self.read(self.file_b), b"vanilla b")
        self.runtime._show_asset_toast.assert_called_once()
        self.assertEqual(self.runtime._show_asset_toast.call_args.kwargs["icon"], self.icon)

    def test_switching_round_puts_the_first_pack_back(self) -> None:
        self.apply()
        self.app.TOURROUNDID = "14"
        self.apply()
        self.assertEqual(self.read(self.file_a), b"vanilla a")
        self.assertEqual(self.read(self.file_b), b"pack B")
        self.assertFalse((self.dst / "extra_new.rx3").exists())

    def test_a_round_without_an_assignment_gets_the_vanilla_files_back(self) -> None:
        self.apply()
        self.app.TOURROUNDID = "999"
        self.apply()
        self.assertEqual(self.read(self.file_a), b"vanilla a")
        self.assertFalse((self.dst / "extra_new.rx3").exists())
        self.assertIn("restored", "\n".join(self.app.logs))

    def test_a_missing_pack_folder_gets_the_vanilla_files_back(self) -> None:
        self.apply()
        self.app.settings_ini = FakeIni({self.module.lower(): {"103": "Deleted Pack"}})
        self.apply()
        self.assertEqual(self.read(self.file_a), b"vanilla a")

    def test_turning_the_module_off_restores_and_warns(self) -> None:
        self.apply()
        self.app.enabled[self.module] = False
        self.apply()
        self.assertEqual(self.read(self.file_a), b"vanilla a")
        self.runtime._show_warning_toast.assert_called_once()
        self.assertEqual(self.runtime._show_warning_toast.call_args.kwargs["icon"], self.icon)

    def test_a_match_with_no_round_gets_the_vanilla_files_back(self) -> None:
        # A friendly after a competition match: Kick-Off never has a round, so
        # an empty one cannot mean "leave the last pack in place" (changed
        # 2026-10-05; the pack used to stay installed).
        self.apply()
        self.app.TOURROUNDID = ""
        self.apply()
        self.assertEqual(self.read(self.file_a), b"vanilla a")
        self.assertFalse((self.dst / "extra_new.rx3").exists())
        self.assertIn("no competition round in this match", " | ".join(self.app.logs))

    def test_no_round_and_nothing_installed_does_nothing(self) -> None:
        self.app.TOURROUNDID = ""
        self.apply()
        self.assertEqual(self.read(self.file_a), b"vanilla a")
        self.assertEqual(self.read(self.file_b), b"vanilla b")
        self.assertEqual(self.app.logs, [])

    def test_applying_twice_keeps_the_original_backed_up(self) -> None:
        self.apply()
        self.apply()
        self.app.TOURROUNDID = "999"
        self.apply()
        self.assertEqual(self.read(self.file_a), b"vanilla a")

    def test_unrelated_files_in_the_target_are_never_touched(self) -> None:
        self.write(self.dst / "someone_elses.rx3", b"keep me")
        self.apply()
        self.app.TOURROUNDID = "999"
        self.apply()
        self.assertEqual(self.read("someone_elses.rx3"), b"keep me")


class ApplyBallRuntimeTests(_Base, unittest.TestCase):
    module = "Ball"
    src_root = "balls"
    target = "ball"
    apply_name = "apply_ball_runtime"
    icon = "ball"

    def test_active_profile_is_remembered_and_reapply_reinstalls(self) -> None:
        self.apply()
        self.assertEqual(self.app._active_ball_runtime["folder"], "Ball A")
        self.write(self.dst / self.file_a, b"overwritten by someone")
        self.assertTrue(self.runtime.reapply_active_ball_runtime(reason="test"))
        self.assertEqual(self.read(self.file_a), b"pack A")
        self.app.TOURROUNDID = "999"
        self.apply()
        self.assertEqual(self.read(self.file_a), b"vanilla a")

    def test_reapply_is_skipped_once_a_new_match_started(self) -> None:
        self.apply()
        self.app._kickoff_generation += 1
        self.assertFalse(self.runtime.reapply_active_ball_runtime(reason="test"))

    def test_module_off_clears_the_active_profile(self) -> None:
        self.apply()
        self.app.enabled["Ball"] = False
        self.apply()
        self.assertIsNone(self.app._active_ball_runtime)


class ApplyRefereeRuntimeTests(_Base, unittest.TestCase):
    module = "Referee"
    src_root = "referee"
    target = "kit"
    apply_name = "apply_referee_runtime"
    icon = "referee"


if __name__ == "__main__":
    unittest.main()
