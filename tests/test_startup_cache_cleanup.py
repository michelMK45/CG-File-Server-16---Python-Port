from __future__ import annotations

import os
import tempfile
import time
import tkinter as tk
import unittest
from pathlib import Path
from types import SimpleNamespace

from server16_py.app_ui import UIMixin


class _App:
    """Just what UIMixin._start_previous_session_cache_cleanup touches."""

    _start_previous_session_cache_cleanup = UIMixin._start_previous_session_cache_cleanup
    _format_freed_size = staticmethod(UIMixin._format_freed_size)

    def __init__(self, root: tk.Tk, base_dir: Path, enabled: bool) -> None:
        self.root = root
        self.base_dir = base_dir
        self._closing = False
        self._session_started_at = time.time()
        self.settings = SimpleNamespace(auto_clean_cache_on_startup=enabled)
        self.logs: list[str] = []

    def after(self, ms, func):
        return self.root.after(ms, func)

    def log(self, message, error=None):
        self.logs.append(message)


class StartupCacheCleanupTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base_dir = Path(self._tmp.name)
        self.old = self.base_dir / "runtime" / "kit_art_cache" / "kit_v3_46_old.png"
        self.old.parent.mkdir(parents=True)
        self.old.write_bytes(b"x" * 8)
        stamp = time.time() - 3600
        os.utime(self.old, (stamp, stamp))
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)

    def _pump(self, app: _App, seconds: float) -> None:
        deadline = time.time() + seconds
        while time.time() < deadline and not app.logs:
            self.root.update()
            time.sleep(0.02)

    def test_enabled_deletes_the_previous_sessions_files_and_logs_from_the_tk_thread(self) -> None:
        app = _App(self.root, self.base_dir, enabled=True)
        app._start_previous_session_cache_cleanup()
        self._pump(app, 5)
        self.assertFalse(self.old.exists())
        self.assertEqual(len(app.logs), 1)
        self.assertIn("removed 1 file(s)", app.logs[0])

    def test_disabled_leaves_everything_alone(self) -> None:
        app = _App(self.root, self.base_dir, enabled=False)
        app._start_previous_session_cache_cleanup()
        self._pump(app, 1)
        self.assertTrue(self.old.exists())
        self.assertEqual(app.logs, [])


if __name__ == "__main__":
    unittest.main()
