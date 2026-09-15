from __future__ import annotations

import unittest

from server16_py.app_ui import UIMixin


class FakeLabel:
    def __init__(self) -> None:
        self.configure_calls: list[dict] = []

    def configure(self, **kwargs) -> None:
        self.configure_calls.append(kwargs)


class FakeInjector:
    def __init__(self, ready: bool = True) -> None:
        self._ready = ready
        self.set_team_crests_calls = 0

    def is_ready(self) -> bool:
        return self._ready

    def set_team_crests(self, home_path: str, away_path: str) -> None:
        self.set_team_crests_calls += 1


class FakeApp(UIMixin):
    """Minimal host for _update_team_logo -- exercises the real caching
    logic in UIMixin without needing a real Tk root or real crest files.
    See CLAUDE.md's "overlay input reliability" history: this method used
    to redo a full disk-read/PIL-decode/PhotoImage-build, plus a
    delete+open+re-encode+disk-write PNG round-trip x2 (small/large), on
    EVERY stats_loop tick (250ms) once HID/AID were known -- i.e.
    continuously from team-select onward -- even when the team_id hadn't
    actually changed. That's real, repeated work on the Tk main thread,
    which also drives window resize and the overlay's own poll tick."""

    def __init__(self) -> None:
        self._team_logo_labels = {"home": FakeLabel(), "away": FakeLabel()}
        self._team_logo_images: dict[str, object] = {}
        self._team_logo_last_id: dict[str, str] = {}
        self._team_crest_pushed_id: dict[str, str] = {}
        self._d3d_injector = FakeInjector()
        self._home_crest_png = ""
        self._away_crest_png = ""
        self._home_crest_png_large = ""
        self._away_crest_png_large = ""
        self.resolve_calls = 0
        self.png_calls = 0

    # Stubbed out so the test never touches real files/Tk PhotoImage —
    # only the caching logic in _update_team_logo itself is under test.
    def _resolve_team_logo_path(self, team_id: str):
        self.resolve_calls += 1
        return None

    def _build_logo_placeholder_image(self, width: int = 116, height: int = 72):
        return object()

    def _to_overlay_crest_png(self, team_id: str, prefix: str, large: bool = False) -> str:
        self.png_calls += 1
        return f"{prefix}-{team_id}.png"

    def tr(self, key: str) -> str:
        return key

    def log(self, *args, **kwargs) -> None:
        pass


class UpdateTeamLogoCacheTests(unittest.TestCase):
    def test_repeated_calls_with_same_team_id_do_no_redundant_work(self) -> None:
        app = FakeApp()
        app._update_team_logo("home", "123")
        self.assertEqual(app.resolve_calls, 1)
        self.assertEqual(app.png_calls, 2)  # small + large variant
        self.assertEqual(app._d3d_injector.set_team_crests_calls, 1)

        for _ in range(10):
            app._update_team_logo("home", "123")

        self.assertEqual(app.resolve_calls, 1, "unchanged team_id must not re-resolve/redecode the crest")
        self.assertEqual(app.png_calls, 2, "unchanged team_id must not regenerate the overlay PNGs")
        # set_team_crests is cheap (a plain shared-memory field write) and is
        # fine to keep calling every tick.
        self.assertEqual(app._d3d_injector.set_team_crests_calls, 11)

    def test_team_id_change_triggers_a_fresh_update(self) -> None:
        app = FakeApp()
        app._update_team_logo("home", "123")
        app._update_team_logo("home", "456")
        self.assertEqual(app.resolve_calls, 2)
        self.assertEqual(app.png_calls, 4)

    def test_injector_becoming_ready_later_still_pushes_crests_once(self) -> None:
        app = FakeApp()
        app._d3d_injector = FakeInjector(ready=False)
        app._update_team_logo("home", "123")
        self.assertEqual(app.png_calls, 0)

        app._d3d_injector = FakeInjector(ready=True)
        app._update_team_logo("home", "123")
        self.assertEqual(app.png_calls, 2, "first tick the injector is ready must still push crests even though team_id is unchanged")

        app._update_team_logo("home", "123")
        self.assertEqual(app.png_calls, 2, "a second ready tick with the same team_id must not regenerate again")

    def test_home_and_away_are_cached_independently(self) -> None:
        app = FakeApp()
        app._update_team_logo("home", "123")
        app._update_team_logo("away", "456")
        self.assertEqual(app.png_calls, 4)
        app._update_team_logo("home", "123")
        app._update_team_logo("away", "456")
        self.assertEqual(app.png_calls, 4, "each side's cache must be keyed independently by its own prefix")


if __name__ == "__main__":
    unittest.main()
