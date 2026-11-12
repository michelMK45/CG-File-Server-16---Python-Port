"""Page-name reads while FIFA is still starting are logged once per process.

Before the page-name chain is built, every 500 ms poll used to log a full
traceback ("Null pointer at base chain start 0x143809030"), which forum users
quoted as the error. Now: one line per pid until the first real page; failures
after that are logged in full as before.
"""
from __future__ import annotations

import unittest

from server16_py.app_game import GameMixin
from server16_py.memory_access import MemoryAccessError

PID = 4242
NULL_CHAIN = "Null pointer at base chain start 0x143809030"


class FakeMemory:
    def __init__(self) -> None:
        self.process_id = PID
        self.page: str | Exception = MemoryAccessError(NULL_CHAIN)

    def get_string(self, *_args, **_kwargs) -> str:
        if isinstance(self.page, Exception):
            raise self.page
        return self.page


class FakeOffsets:
    ORIPGBASE = 0x143809030
    PG1 = [0]


class FakeApp(GameMixin):
    gold = "gold"

    def __init__(self) -> None:
        self.logs: list[str] = []
        self.memory = FakeMemory()
        self.offsets = FakeOffsets()
        self._fifa_page_ready_pid = 0
        self._page_startup_logged_pid = 0

    def log(self, message, *_args, **_kwargs) -> None:
        self.logs.append(str(message))

    def status_text(self, key) -> str:
        return key

    def _set_process_status(self, *_args) -> None:
        pass

    def _sync_page_banner(self, *_args) -> None:
        pass

    def _handle_page_transition(self, *_args) -> None:
        pass

    def _page_can_have_match_context(self, _page) -> bool:
        return False


def _count(app: FakeApp, text: str) -> int:
    return sum(text in m for m in app.logs)


class PageStartupLoggingTests(unittest.TestCase):
    def test_startup_null_pointer_is_one_line_per_process(self) -> None:
        app = FakeApp()
        for _ in range(10):
            app.update_page_name()
        self.assertEqual(_count(app, "still starting"), 1)
        self.assertEqual(_count(app, "Failed to read page name"), 0)

    def test_errors_after_the_first_page_are_logged_in_full(self) -> None:
        app = FakeApp()
        app.update_page_name()
        app.memory.page = "game/screens/bootflow/Legal"
        app.update_page_name()
        app.memory.page = MemoryAccessError("ReadProcessMemory failed at 0x3809030")
        app.update_page_name()
        self.assertEqual(_count(app, "Failed to read page name"), 1)

    def test_empty_page_does_not_end_startup(self) -> None:
        app = FakeApp()
        app.memory.page = ""
        app.update_page_name()
        app.memory.page = MemoryAccessError(NULL_CHAIN)
        app.update_page_name()
        self.assertEqual(_count(app, "Failed to read page name"), 0)

    def test_a_restarted_fifa_logs_its_startup_again(self) -> None:
        app = FakeApp()
        app.memory.page = "game/screens/bootflow/Legal"
        app.update_page_name()
        app.memory.process_id = PID + 1
        app.memory.page = MemoryAccessError(NULL_CHAIN)
        app.update_page_name()
        app.update_page_name()
        self.assertEqual(_count(app, "still starting"), 1)
        self.assertEqual(_count(app, "Failed to read page name"), 0)


if __name__ == "__main__":
    unittest.main()
