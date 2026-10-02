from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from server16_py.app_overlay import OverlayMixin
from server16_py.file_tools import asset_placeholder_path


class AssetPlaceholderPathTests(unittest.TestCase):
    def test_resolves_the_bundled_placeholder_in_resources_not_the_toast_icon_set(self) -> None:
        for kind in ("scoreboard", "tv", "movie"):
            with self.subTest(kind=kind):
                path = asset_placeholder_path(kind)
                self.assertIsNotNone(path)
                self.assertEqual(path.name, f"{kind}-placeholder.png")
                self.assertEqual(path.parent.name, "resources")

    def test_unknown_kind_resolves_to_none(self) -> None:
        self.assertIsNone(asset_placeholder_path("nonexistent"))


class FakeOverlayApp(OverlayMixin):
    """Real OverlayMixin preview resolvers on a minimal host -- only what
    _resolve_scoreboard_or_tvlogo_preview/_resolve_movies_menu_preview touch."""

    def __init__(self, performance_mode: bool = False) -> None:
        self.overlay_performance_mode_var = SimpleNamespace(get=lambda: performance_mode)
        self.movie_preview_runtime = SimpleNamespace(stop=lambda: None, is_muted=False)
        self._d3d_injector = None
        self.Movies = None
        self.log = lambda *_a, **_k: None


class OverlayPlaceholderTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        (self.root / "PackWithoutThumb").mkdir()
        thumb_dir = self.root / "PackWithThumb" / "render" / "thumbnail"
        thumb_dir.mkdir(parents=True)
        self.thumb = thumb_dir / "scoreboard.png"
        self.thumb.write_bytes(b"png")

    def test_scoreboard_without_its_own_thumbnail_shows_the_scoreboard_placeholder(self) -> None:
        result = FakeOverlayApp()._resolve_scoreboard_or_tvlogo_preview("scoreboard", "scoreboard", self.root, "PackWithoutThumb")
        self.assertEqual(Path(result), asset_placeholder_path("scoreboard"))

    def test_tvlogo_without_its_own_thumbnail_shows_the_tv_placeholder(self) -> None:
        result = FakeOverlayApp()._resolve_scoreboard_or_tvlogo_preview("tvlogo", "tv", self.root, "PackWithoutThumb")
        self.assertEqual(Path(result), asset_placeholder_path("tv"))

    def test_the_pack_s_own_thumbnail_still_wins_over_the_placeholder(self) -> None:
        result = FakeOverlayApp()._resolve_scoreboard_or_tvlogo_preview("scoreboard", "scoreboard", self.root, "PackWithThumb")
        self.assertEqual(Path(result), self.thumb)

    def test_performance_mode_skips_the_thumbnail_and_shows_the_placeholder(self) -> None:
        result = FakeOverlayApp(performance_mode=True)._resolve_scoreboard_or_tvlogo_preview("scoreboard", "scoreboard", self.root, "PackWithThumb")
        self.assertEqual(Path(result), asset_placeholder_path("scoreboard"))

    def test_movies_with_nothing_playable_shows_the_movie_placeholder(self) -> None:
        result = FakeOverlayApp()._resolve_movies_menu_preview("SomeMovie")
        self.assertEqual(Path(result), asset_placeholder_path("movie"))


if __name__ == "__main__":
    unittest.main()
