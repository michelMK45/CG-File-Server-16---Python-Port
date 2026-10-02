from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from server16_py.app_logging import LogMixin


class FakeLoggerApp(LogMixin):
    """Minimal host for LogMixin.log(), matching the pattern used elsewhere
    in this test suite for mixin classes that expect to live on Server16App."""

    def __init__(self, log_path: Path) -> None:
        self.log_path = log_path
        self.log_widget = None


class LogExcInfoContractTests(unittest.TestCase):
    """LogMixin.log()'s `exc_info` parameter only ever accepts None or a real
    sys.exc_info()-shaped 3-tuple -- it is passed straight to
    traceback.format_exception(*exc_info). Every call site in this codebase
    must use `exc_info=sys.exc_info()`, never the bare `exc_info=True` that
    Python's stdlib `logging` module accepts as a "capture the current
    exception" shortcut; `log()` does not implement that shortcut. Passing
    `True` used to raise `TypeError: traceback.format_exception() argument
    after * must be an iterable, not bool` from INSIDE the except block that
    was trying to log the original failure -- confirmed live 2026-09-27 in a
    user-supplied runtime/server16.log, where it fired from
    substitution_runtime.py's poll tick and masked the real read failure
    behind a second, unrelated exception. Found to also affect six call
    sites in app.py's apply_all_runtime() (Ball/Referee/Wipe/Scoreboard/
    Movie/Adboard runtime error handlers) -- the higher-risk set, since that
    method runs at the start of every single match, not just occasionally
    during a substitution.
    """

    def test_log_accepts_a_real_exc_info_tuple(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = FakeLoggerApp(Path(tmp) / "test.log")
            try:
                raise RuntimeError("boom")
            except RuntimeError as exc:
                # Must not raise -- this is exactly how every fixed call site
                # in server16_py now calls log().
                app.log("Something failed", exc, exc_info=sys.exc_info())
            self.assertIn("Something failed: boom", app.log_path.read_text(encoding="utf-8"))

    def test_no_source_file_passes_the_bare_exc_info_true_shortcut(self) -> None:
        # Regression guard for the whole class of bug, not just the two
        # files fixed live: LogMixin.log() has no support for a bare `True`
        # (unlike stdlib logging), so any future call site written that way
        # would carry the exact same latent crash. Cheaper to catch here than
        # to wait for it to fire in a live session again.
        repo_root = Path(__file__).resolve().parent.parent
        offenders = []
        for path in (repo_root / "server16_py").rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            if "exc_info=True" in text:
                offenders.append(str(path.relative_to(repo_root)))
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
