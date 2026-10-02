from __future__ import annotations

import inspect
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from server16_py.app import Server16App
from server16_py.app_settings import SettingsMixin


class AutorunLaunchTests(unittest.TestCase):
    """[Modules] Autorun launches FIFA once when CGFS16 starts (same as Launch FIFA). The
    switch used to be read by nothing."""

    def make_app(self, exe: str, *, module_on: bool = True, running: bool = False, closing: bool = False) -> SimpleNamespace:
        app = SimpleNamespace(
            _closing=closing,
            fifaEXE=exe,
            module_enabled=lambda name: module_on if name == "Autorun" else False,
            _is_target_process_running=lambda: running,
            launches=0,
            logs=[],
        )

        def launch_fifa() -> None:
            app.launches += 1

        app.launch_fifa = launch_fifa
        app.log = lambda message, *args, **kwargs: app.logs.append(message)
        return app

    def run_autorun(self, **kwargs) -> SimpleNamespace:
        with tempfile.TemporaryDirectory() as tmp:
            exe = Path(tmp) / "fifa16.exe"
            exe.write_bytes(b"MZ")
            app = self.make_app(kwargs.pop("exe", str(exe)), **kwargs)
            SettingsMixin._autorun_launch_fifa(app)
        return app

    def test_launches_fifa_once_when_the_module_is_on(self) -> None:
        self.assertEqual(self.run_autorun().launches, 1)

    def test_does_nothing_while_the_module_is_off(self) -> None:
        app = self.run_autorun(module_on=False)
        self.assertEqual(app.launches, 0)
        self.assertEqual(app.logs, [])

    def test_does_nothing_while_the_app_is_closing(self) -> None:
        self.assertEqual(self.run_autorun(closing=True).launches, 0)

    def test_does_not_launch_when_no_fifa_exe_is_linked(self) -> None:
        # launch_fifa() would pop a warning dialog here -- Autorun must stay silent.
        app = self.run_autorun(exe="default")
        self.assertEqual(app.launches, 0)
        self.assertTrue(any("no valid FIFA executable" in line for line in app.logs))

    def test_does_not_launch_when_the_linked_exe_no_longer_exists(self) -> None:
        app = self.run_autorun(exe=str(Path(tempfile.gettempdir()) / "definitely_missing_fifa16.exe"))
        self.assertEqual(app.launches, 0)

    def test_does_not_launch_a_second_fifa_when_it_is_already_running(self) -> None:
        app = self.run_autorun(running=True)
        self.assertEqual(app.launches, 0)
        self.assertTrue(any("already running" in line for line in app.logs))

    def test_a_failing_launch_is_logged_not_raised(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            exe = Path(tmp) / "fifa16.exe"
            exe.write_bytes(b"MZ")
            app = self.make_app(str(exe))

            def boom() -> None:
                raise OSError("blocked by antivirus")

            app.launch_fifa = boom
            SettingsMixin._autorun_launch_fifa(app)
        self.assertTrue(any("failed to launch FIFA" in line for line in app.logs))

    def test_startup_schedules_it(self) -> None:
        # Server16App.__init__ is too heavy to run here; guard the wiring instead.
        self.assertIn("self._autorun_launch_fifa", inspect.getsource(Server16App.__init__))


if __name__ == "__main__":
    unittest.main()
