from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from server16_py.image_zoom_dialog import fit_size
from server16_py.kit_art_preview import advanced_mix_sources
from server16_py.kit_mixer import KitMixRuntime


class AdvancedMixSourcesTests(unittest.TestCase):
    CURRENT = Path("live/kit_383_0_0.rx3")

    def test_keep_current_parts_come_from_the_kit_the_mix_starts_from(self):
        keep = {"mode": "keep", "path": None}
        self.assertEqual(advanced_mix_sources(keep, keep, self.CURRENT), (self.CURRENT,) * 3)

    def test_chosen_sources_replace_their_parts_and_socks_follow_the_shorts(self):
        jersey = {"mode": "rx3", "path": "fsw/kit_1041_1_0.rx3"}
        shorts = {"mode": "img", "path": "imports/shorts.png"}
        self.assertEqual(
            advanced_mix_sources(jersey, shorts, self.CURRENT),
            (Path("fsw/kit_1041_1_0.rx3"), Path("imports/shorts.png"), Path("imports/shorts.png")),
        )
        self.assertEqual(advanced_mix_sources(jersey, {"mode": "keep"}, self.CURRENT)[1], self.CURRENT)

    def test_nothing_to_draw(self):
        self.assertIsNone(advanced_mix_sources({"mode": "keep"}, {"mode": "keep"}, None))
        # A source with no path yet counts as "keep".
        self.assertIsNone(advanced_mix_sources({"mode": "rx3", "path": None}, {"mode": "keep"}, None))


class FitSizeTests(unittest.TestCase):
    def test_large_images_shrink_into_the_box_keeping_aspect(self):
        self.assertEqual(fit_size((1024, 512), (560, 560)), (560, 280))

    def test_small_images_grow_but_no_more_than_the_upscale_limit(self):
        self.assertEqual(fit_size((88, 88), (560, 560)), (264, 264))
        self.assertEqual(fit_size((220, 110), (560, 560), max_upscale=10), (560, 280))


class CurrentKitPathTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.exedir = Path(self._tmp.name)
        self.kit_mixer = KitMixRuntime(SimpleNamespace(exedir=self.exedir, settings_ini=None, log=lambda *a: None))

    def tearDown(self):
        self._tmp.cleanup()

    def test_live_kit_is_preferred_and_none_when_there_is_no_kit(self):
        self.assertIsNone(self.kit_mixer.current_kit_path("383", "0"))
        live = self.kit_mixer.live_kit_path("383", "0")
        live.parent.mkdir(parents=True)
        live.write_bytes(b"x")
        self.assertEqual(self.kit_mixer.current_kit_path("383", "0"), live)


if __name__ == "__main__":
    unittest.main()
