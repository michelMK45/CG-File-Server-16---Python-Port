from __future__ import annotations

import queue
import tempfile
import unittest
import unittest.mock
from pathlib import Path

from server16_py.app_settings import SettingsMixin
from server16_py.asset_runtime import AssetRuntime


class FakeApp:
    """Minimal double for the toast helpers in AssetRuntime -- only the
    surface _show_asset_toast/_show_warning_toast actually touch."""

    def __init__(self, awaiting: bool) -> None:
        self._awaiting = awaiting
        self.toast_calls: list[tuple] = []
        self.after_calls: list[tuple] = []
        self.hide_calls: list[int] = []

    def stadium_picker_awaiting_selection(self) -> bool:
        return self._awaiting

    def _show_toast_notification(self, title, body="", style=0, icon="") -> int:
        self.toast_calls.append((title, body, style, icon))
        return len(self.toast_calls)

    def _hide_toast_notification(self, slot: int = -1) -> None:
        self.hide_calls.append(slot)

    def after(self, delay_ms, callback):
        self.after_calls.append((delay_ms, callback))
        return len(self.after_calls)


class AssetToastGatingTests(unittest.TestCase):
    def test_asset_toast_suppressed_while_stadium_picker_awaits_selection(self) -> None:
        app = FakeApp(awaiting=True)
        AssetRuntime(app)._show_asset_toast("Scoreboard", "Anfield Board", icon="scoreboard")
        self.assertEqual(app.toast_calls, [])
        self.assertEqual(app.after_calls, [])

    def test_warning_toast_suppressed_while_stadium_picker_awaits_selection(self) -> None:
        app = FakeApp(awaiting=True)
        AssetRuntime(app)._show_warning_toast("TV Logo (OFF)", "Assets skipped", icon="tv")
        self.assertEqual(app.toast_calls, [])

    def test_asset_toast_shows_normally_once_stadium_is_selected(self) -> None:
        app = FakeApp(awaiting=False)
        AssetRuntime(app)._show_asset_toast("Scoreboard", "Anfield Board", icon="scoreboard")
        self.assertEqual(app.toast_calls, [("Scoreboard", "Anfield Board", 0, "scoreboard")])
        self.assertEqual(len(app.after_calls), 1)

    def test_warning_toast_shows_normally_once_stadium_is_selected(self) -> None:
        app = FakeApp(awaiting=False)
        AssetRuntime(app)._show_warning_toast("TV Logo (OFF)", "Assets skipped", icon="tv")
        self.assertEqual(app.toast_calls, [("TV Logo (OFF)", "Assets skipped", 1, "tv")])


class FakeIni:
    def __init__(self, data: dict[str, dict[str, str]]) -> None:
        self._data = data

    def key_exists(self, key: str, section: str) -> bool:
        return bool(self._data.get(section, {}).get(key))

    def read(self, key: str, section: str) -> str:
        return self._data.get(section, {}).get(key, "")


class FakeAdboardApp(FakeApp):
    """Enough of Server16App for AssetRuntime._apply_adboard_runtime_impl to
    run against a real, on-disk FSW/adboards/<folder>/ pack assigned to round R1."""

    def __init__(self, base: Path, awaiting: bool) -> None:
        super().__init__(awaiting)
        self.exedir = base
        self.TOURROUNDID = "R1"
        self.settings_ini = FakeIni({"adboard": {"R1": "Banners"}})
        self._active_adboard_injected_files: list[str] = []
        self.logs: list[str] = []

    def tr(self, key: str) -> str:
        return key

    def log(self, *parts) -> None:
        self.logs.append(" ".join(str(p) for p in parts))


class AdboardToastGatingTests(unittest.TestCase):
    def _make_app(self, awaiting: bool) -> FakeAdboardApp:
        tmp = Path(tempfile.mkdtemp())
        pack_dir = tmp / "FSW" / "adboards" / "Banners"
        pack_dir.mkdir(parents=True)
        (pack_dir / "board1.rx3").write_bytes(b"data")
        return FakeAdboardApp(tmp, awaiting)

    def test_adboard_toast_not_shown_while_stadium_picker_awaits_selection(self) -> None:
        app = self._make_app(awaiting=True)
        AssetRuntime(app)._apply_adboard_runtime_impl()
        # The asset itself still applies -- only the notification is held back.
        self.assertEqual(app._active_adboard_injected_files, ["board1.rx3"])
        self.assertEqual(app.toast_calls, [])

    def test_adboard_toast_shown_once_stadium_is_selected(self) -> None:
        app = self._make_app(awaiting=False)
        AssetRuntime(app)._apply_adboard_runtime_impl()
        self.assertEqual(app.toast_calls, [("notify.adboard_loaded", "Banners", 0, "adboard")])


class StadiumNetOffToastTests(unittest.TestCase):
    """tv_bumper_page warns when the StadiumNet module is off but net values are assigned to
    the stadium (or its id) -- and nothing else changes while it is on."""

    def make_app(self, ini: dict[str, dict[str, str]], module_on: bool, curstad: str = "Anfield") -> FakeApp:
        app = FakeApp(awaiting=False)
        app.module_enabled = lambda name: module_on if name == "StadiumNet" else False
        app.curstad = curstad
        app.StadName = curstad
        app.STADID = "12"
        app.TOURROUNDID = "R1"
        app.settings_ini = FakeIni(ini)
        app.tr = lambda key, **_kw: key
        app.memory = unittest.mock.MagicMock()
        app.offsets = unittest.mock.MagicMock()
        app._set_display = lambda *_a, **_k: None
        app.display_value = lambda *_a, **_k: ""
        app.log = lambda *_a, **_k: None
        return app

    def run_bumper(self, app: FakeApp) -> None:
        runtime = AssetRuntime(app)
        with unittest.mock.patch.object(AssetRuntime, "reapply_active_ball_runtime"):
            runtime.tv_bumper_page()

    WARNING = ("notify.warn.stadiumnet_off", "notify.warn.assets_skipped", 1, "")

    def test_module_off_with_stadium_net_values_warns_and_writes_nothing(self) -> None:
        app = self.make_app({"stadiumnetname": {"Anfield": "1,2,3,4,5"}}, module_on=False)
        self.run_bumper(app)
        self.assertEqual(app.toast_calls, [self.WARNING])
        app.memory.write_int.assert_not_called()

    def test_module_off_with_net_values_by_stadium_id_warns(self) -> None:
        app = self.make_app({"stadiumnetid": {"12": "1,2,3,4,5"}}, module_on=False, curstad="")
        self.run_bumper(app)
        self.assertEqual(app.toast_calls, [self.WARNING])

    def test_module_off_without_net_values_does_not_warn(self) -> None:
        app = self.make_app({}, module_on=False)
        self.run_bumper(app)
        self.assertEqual(app.toast_calls, [])

    def test_module_off_for_an_excluded_round_does_not_warn(self) -> None:
        app = self.make_app({"stadiumnetname": {"Anfield": "1,2,3,4,5"}, "exclude": {"R1": "1"}}, module_on=False)
        self.run_bumper(app)
        self.assertEqual(app.toast_calls, [])

    def test_module_on_writes_the_five_net_values_without_a_warning(self) -> None:
        app = self.make_app({"stadiumnetname": {"Anfield": "1,2,3,4,5"}}, module_on=True)
        self.run_bumper(app)
        self.assertEqual(app.toast_calls, [])
        self.assertEqual(app.memory.write_int.call_count, 5)



class WorkerQueueToastStyleTests(unittest.TestCase):
    """SettingsMixin._poll_worker_queue shows the ("toast", ...) events the stadium copy job
    queues from its worker thread: 5 elements = normal toast, an optional 6th = its style."""

    def poll(self, *events: tuple) -> FakeApp:
        app = FakeApp(awaiting=False)
        app._worker_queue = queue.Queue()
        for event in events:
            app._worker_queue.put(event)
        app._stadium_task_running = False
        app._kit_cycle_task_running = False
        SettingsMixin._poll_worker_queue(app)
        return app

    def test_five_element_toast_keeps_the_default_style(self) -> None:
        app = self.poll(("toast", "Goalposts", "Anfield", 3500, "goalpost"))
        self.assertEqual(app.toast_calls, [("Goalposts", "Anfield", 0, "goalpost")])
        self.assertEqual([delay for delay, _cb in app.after_calls], [3500])

    def test_sixth_element_sets_the_warning_style_and_duration(self) -> None:
        app = self.poll(("toast", "Goalposts (OFF)", "Assets detected, module is OFF", 5000, "goalpost", 1))
        self.assertEqual(app.toast_calls, [("Goalposts (OFF)", "Assets detected, module is OFF", 1, "goalpost")])
        self.assertEqual([delay for delay, _cb in app.after_calls], [5000])


if __name__ == "__main__":
    unittest.main()
