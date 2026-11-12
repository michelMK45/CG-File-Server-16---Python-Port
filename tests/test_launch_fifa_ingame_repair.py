from __future__ import annotations

import inspect
import unittest
import unittest.mock
from types import SimpleNamespace

from server16_py import app_settings, ingame_menu_install
from server16_py.app import Server16App
from server16_py.app_settings import SettingsMixin
from server16_py.app_ui import UIMixin


class SyncThread:
    """threading.Thread that runs its target on start() (the worker's order is what is tested)."""

    def __init__(self, target, args=(), daemon=None) -> None:
        self.target, self.args = target, args

    def start(self) -> None:
        self.target(*self.args)


class LaunchFifaRepairsTheInGameMenuTests(unittest.TestCase):
    """Launch FIFA 16 puts the in-game menu back first when a FIFA theme replaced its files (R3 gone)."""

    def make_app(self, *, installed: bool, running: bool = False) -> SimpleNamespace:
        app = SimpleNamespace(fifaEXE="C:/FIFA/fifa16.exe", exedir="C:/FIFA", events=[], logs=[])
        app.setuppaths = app.apply_bootstrap_files = app.refresh_modules = lambda: None
        app._is_target_process_running = lambda: running
        app.after = lambda _ms, fn: fn()
        app.log = lambda message, *a, **k: app.logs.append(message)
        app._repair_ingame_menu_blocking = lambda why: app.events.append(("repair", why))
        app._start_fifa_process = lambda: app.events.append(("launch",))
        status = ingame_menu_install.MenuStatus("2026-11-12 18:00" if installed else None, "2026-11-12 18:00")
        patcher = unittest.mock.patch.object(ingame_menu_install, "status", lambda exedir: status)
        patcher.start()
        self.addCleanup(patcher.stop)
        return app

    def launch(self, app: SimpleNamespace) -> None:
        with unittest.mock.patch.object(app_settings.threading, "Thread", SyncThread):
            SettingsMixin.launch_fifa(app)

    def test_repairs_before_launching_when_the_menu_is_installed(self) -> None:
        app = self.make_app(installed=True)
        self.launch(app)
        self.assertEqual(app.events, [("repair", "before launching FIFA"), ("launch",)])

    def test_launches_straight_away_without_the_menu(self) -> None:
        app = self.make_app(installed=False)
        self.launch(app)
        self.assertEqual(app.events, [("launch",)])

    def test_a_second_click_while_the_check_runs_launches_nothing(self) -> None:
        app = self.make_app(installed=True)
        app._fifa_launch_pending = True
        self.launch(app)
        self.assertEqual(app.events, [])

    def test_nothing_while_fifa_runs(self) -> None:
        app = self.make_app(installed=True, running=True)
        self.launch(app)
        self.assertEqual(app.events, [])

    def test_start_fifa_process_clears_the_pending_flag_and_logs_a_failed_launch(self) -> None:
        app = SimpleNamespace(fifaEXE="C:/nowhere/fifa16.exe", _fifa_launch_pending=True, logs=[])
        app._is_target_process_running = lambda: False
        app.log = lambda message, *a, **k: app.logs.append(message)
        with unittest.mock.patch.object(app_settings.subprocess, "Popen", side_effect=OSError("not found")):
            SettingsMixin._start_fifa_process(app)
        self.assertFalse(app._fifa_launch_pending)
        self.assertIn("Could not launch FIFA executable", app.logs[-1])

    def test_app_start_runs_the_repair(self) -> None:
        self.assertIn("self._start_ingame_menu_repair()", inspect.getsource(Server16App.__init__))


class RepairBlockingTests(unittest.TestCase):
    def make_app(self) -> SimpleNamespace:
        app = SimpleNamespace(exedir="C:/FIFA", logs=[], scheduled=[], ingame_menu=SimpleNamespace(install_changed=None))
        app.log = lambda message, *a, **k: app.logs.append(message)
        app.after = lambda _ms, fn: app.scheduled.append(fn)
        return app

    def test_repaired_tells_the_runtime(self) -> None:
        app = self.make_app()
        with unittest.mock.patch.object(ingame_menu_install, "repair", lambda exedir, log: True):
            self.assertTrue(UIMixin._repair_ingame_menu_blocking(app, "app start"))
        self.assertEqual(app.scheduled, [app.ingame_menu.install_changed])
        self.assertIn("In-game menu: repaired (app start)", app.logs)

    def test_nothing_to_do_is_silent(self) -> None:
        app = self.make_app()
        with unittest.mock.patch.object(ingame_menu_install, "repair", lambda exedir, log: False):
            self.assertFalse(UIMixin._repair_ingame_menu_blocking(app, "app start"))
        self.assertEqual((app.logs, app.scheduled), ([], []))

    def test_fifa_running_or_a_failure_is_logged_not_raised(self) -> None:
        app = self.make_app()

        def running(exedir, log):
            raise ingame_menu_install.FifaRunning("FIFA 16 is running")

        def broken(exedir, log):
            raise ValueError("a patch anchor is missing")

        for repair in (running, broken):
            with unittest.mock.patch.object(ingame_menu_install, "repair", repair):
                self.assertFalse(UIMixin._repair_ingame_menu_blocking(app, "before launching FIFA"))
        self.assertIn("FIFA 16 is running", app.logs[0])
        self.assertIn("repair failed (before launching FIFA): a patch anchor is missing", app.logs[1])
        self.assertEqual(app.scheduled, [])


if __name__ == "__main__":
    unittest.main()
