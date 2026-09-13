from __future__ import annotations

import queue
import tempfile
import unittest
from pathlib import Path

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


class FakeAdboardApp:
    """Enough of Server16App for AssetRuntime._apply_adboard_runtime_impl to
    run against a real, on-disk FSW/adboards/<stadium>/ folder."""

    def __init__(self, base: Path, awaiting: bool) -> None:
        self.exedir = base
        self.curstad = "Anfield"
        self.TOURROUNDID = ""
        self._active_adboard_injected_files: list[str] = []
        self._worker_queue: "queue.Queue" = queue.Queue()
        self._awaiting = awaiting
        self.logs: list[str] = []

    def stadium_picker_awaiting_selection(self) -> bool:
        return self._awaiting

    def tr(self, key: str) -> str:
        return key

    def log(self, *parts) -> None:
        self.logs.append(" ".join(str(p) for p in parts))


class AdboardQueuedToastGatingTests(unittest.TestCase):
    def _make_app(self, awaiting: bool) -> FakeAdboardApp:
        tmp = Path(tempfile.mkdtemp())
        stadium_dir = tmp / "FSW" / "adboards" / "Anfield"
        stadium_dir.mkdir(parents=True)
        (stadium_dir / "board1.rx3").write_bytes(b"data")
        return FakeAdboardApp(tmp, awaiting)

    def test_adboard_toast_not_queued_while_stadium_picker_awaits_selection(self) -> None:
        app = self._make_app(awaiting=True)
        AssetRuntime(app)._apply_adboard_runtime_impl()
        # The asset itself still applies -- only the notification is held back.
        self.assertEqual(app._active_adboard_injected_files, ["board1.rx3"])
        self.assertTrue(app._worker_queue.empty())

    def test_adboard_toast_queued_once_stadium_is_selected(self) -> None:
        app = self._make_app(awaiting=False)
        AssetRuntime(app)._apply_adboard_runtime_impl()
        self.assertFalse(app._worker_queue.empty())
        kind, title, body, duration_ms, icon = app._worker_queue.get_nowait()
        self.assertEqual(kind, "toast")
        self.assertEqual(body, "Anfield")


if __name__ == "__main__":
    unittest.main()
