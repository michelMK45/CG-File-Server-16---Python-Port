from __future__ import annotations

import unittest
from unittest import mock

from server16_py import window_fit


def _fake_work_area(left=0, top=0, width=3840, height=2100):
    return mock.patch.object(window_fit, "work_area", return_value=(left, top, width, height))


class FitTests(unittest.TestCase):
    def test_a_size_that_fits_is_left_alone(self) -> None:
        with _fake_work_area():
            self.assertEqual(window_fit.fit(1178, 782), (1178, 782))

    def test_an_oversized_request_is_clamped_to_the_work_area(self) -> None:
        # The reported symptom: a window several times the size of the screen,
        # whose title bar controls and right-hand column land offscreen.
        with _fake_work_area():
            self.assertEqual(window_fit.fit(8000, 6000), (3840, 2100))

    def test_clamping_shrinks_but_never_collapses(self) -> None:
        with _fake_work_area(width=400, height=300):
            self.assertEqual(window_fit.fit(1178, 782), (400, 300))
        # A work area smaller than the floor still wins -- a window wider than
        # the screen is exactly what this module exists to prevent.
        with _fake_work_area(width=120, height=90):
            self.assertEqual(window_fit.fit(1178, 782), (120, 90))


class CenteredGeometryTests(unittest.TestCase):
    def test_centers_on_the_work_area_not_the_screen(self) -> None:
        with _fake_work_area(width=3840, height=2100):
            geometry, width, height = window_fit.centered_geometry(None, 1178, 782)
        self.assertEqual((width, height), (1178, 782))
        self.assertEqual(geometry, f"1178x782+{(3840 - 1178) // 2}+{(2100 - 782) // 2}")

    def test_offsets_are_relative_to_the_monitor_origin(self) -> None:
        # A second monitor to the right of the primary one: the window has to
        # land on it, so the origin is added rather than assumed to be 0,0.
        with _fake_work_area(left=3840, top=-120, width=1920, height=1000):
            geometry, _w, _h = window_fit.centered_geometry(None, 1000, 500)
        self.assertEqual(geometry, f"1000x500+{3840 + 460}+{-120 + 250}")

    def test_an_oversized_request_lands_at_the_work_area_origin(self) -> None:
        with _fake_work_area(left=0, top=40, width=2560, height=1390):
            geometry, width, height = window_fit.centered_geometry(None, 9000, 9000)
        self.assertEqual((width, height), (2560, 1390))
        self.assertEqual(geometry, "2560x1390+0+40")


class _FakeWindow:
    """Enough of a Tk top level for the geometry math. border/caption mimic
    a decorated window: winfo_x/y are the frame origin, winfo_rootx/y the
    client one, and wm geometry sizes are client sizes."""

    def __init__(self, width: int, height: int, x: int = 0, y: int = 0,
                 border: int = 0, caption: int = 0, mapped: bool = True) -> None:
        self.width = width
        self.height = height
        self.x = x
        self.y = y
        self.border = border
        self.caption = caption
        self.mapped = mapped
        self.state = "normal"
        self.geometries: list[str] = []

    def winfo_exists(self) -> bool:
        return True

    def winfo_ismapped(self) -> bool:
        return self.mapped

    def wm_state(self) -> str:
        return self.state

    def winfo_width(self) -> int:
        return self.width

    def winfo_height(self) -> int:
        return self.height

    def winfo_x(self) -> int:
        return self.x

    def winfo_y(self) -> int:
        return self.y

    def winfo_rootx(self) -> int:
        return self.x + self.border

    def winfo_rooty(self) -> int:
        return self.y + self.caption

    def geometry(self, spec: str) -> None:
        self.geometries.append(spec)
        size, _, rest = spec.partition("+")
        w, _, h = size.partition("x")
        self.width, self.height = int(w), int(h)
        x, _, y = rest.partition("+")
        self.x, self.y = int(x), int(y)


class FrameOverheadTests(unittest.TestCase):
    def test_an_undecorated_or_unmapped_window_has_none(self) -> None:
        self.assertEqual(window_fit.frame_overhead(None), (0, 0))
        self.assertEqual(window_fit.frame_overhead(_FakeWindow(600, 400)), (0, 0))
        unmapped = _FakeWindow(600, 400, border=9, caption=38, mapped=False)
        self.assertEqual(window_fit.frame_overhead(unmapped), (0, 0))

    def test_border_and_caption_are_measured_from_the_two_origins(self) -> None:
        window = _FakeWindow(600, 400, x=100, y=100, border=9, caption=38)
        # Two borders wide; caption plus the bottom border tall.
        self.assertEqual(window_fit.frame_overhead(window), (18, 47))

    def test_a_clamped_size_leaves_room_for_the_frame(self) -> None:
        window = _FakeWindow(9000, 9000, border=9, caption=38)
        with _fake_work_area(width=2560, height=1390):
            width, height = window_fit.fit(9000, 9000, window)
        self.assertEqual((width + 18, height + 47), (2560, 1390))


class ClampInPlaceTests(unittest.TestCase):
    def test_a_window_that_fits_is_not_touched(self) -> None:
        window = _FakeWindow(1178, 782, x=300, y=200, border=9, caption=38)
        with _fake_work_area(width=2560, height=1390):
            self.assertFalse(window_fit.clamp_in_place(window))
        self.assertEqual(window.geometries, [])

    def test_an_oversized_window_is_shrunk_but_keeps_its_corner(self) -> None:
        window = _FakeWindow(9000, 9000, x=40, y=30, border=9, caption=38)
        logged: list[str] = []
        with _fake_work_area(width=2560, height=1390),                 mock.patch.object(window_fit, "describe", return_value="diag"):
            self.assertTrue(window_fit.clamp_in_place(window, log=logged.append, label="Main window"))
        # Shrunk to the work area minus the frame, and pushed just far enough
        # up/left that the frame fits -- not re-centered.
        self.assertEqual((window.width, window.height), (2542, 1343))
        self.assertEqual((window.x, window.y), (0, 0))
        self.assertEqual(len(logged), 1)
        self.assertIn("Main window", logged[0])
        self.assertIn("larger than the 2560x1390 work area", logged[0])

    def test_clamping_is_idempotent(self) -> None:
        # The guard runs off <Configure>, and its own geometry() call raises
        # one -- a second pass that changed anything would oscillate forever.
        window = _FakeWindow(9000, 9000, x=40, y=30, border=9, caption=38)
        with _fake_work_area(width=2560, height=1390):
            self.assertTrue(window_fit.clamp_in_place(window))
            self.assertFalse(window_fit.clamp_in_place(window))
        self.assertEqual(len(window.geometries), 1)

    def test_a_window_parked_half_off_the_edge_is_left_where_the_user_put_it(self) -> None:
        # Deliberately dragged mostly offscreen: the guard is about size, and
        # snapping this back 250ms later would be worse than the bug it fixes.
        window = _FakeWindow(1000, 600, x=2400, y=1300, border=9, caption=38)
        with _fake_work_area(width=2560, height=1390):
            self.assertFalse(window_fit.clamp_in_place(window))
        self.assertEqual(window.geometries, [])
        self.assertEqual((window.x, window.y), (2400, 1300))

    def test_a_shrunk_window_is_moved_only_as_far_as_it_has_to_be(self) -> None:
        window = _FakeWindow(9000, 9000, x=2400, y=1300, border=9, caption=38)
        with _fake_work_area(width=2560, height=1390):
            self.assertTrue(window_fit.clamp_in_place(window))
        self.assertEqual((window.width, window.height), (2542, 1343))
        self.assertEqual((window.x, window.y), (0, 0))

    def test_the_offsets_of_a_second_monitor_are_respected(self) -> None:
        # A window on the 1080p screen left of the primary one: clamping must
        # keep it there instead of dragging it onto the other monitor.
        window = _FakeWindow(9000, 9000, x=-1920, y=362, border=9, caption=38)
        with _fake_work_area(left=-1920, top=362, width=1920, height=1040):
            self.assertTrue(window_fit.clamp_in_place(window))
        self.assertEqual((window.width, window.height), (1902, 993))
        self.assertEqual((window.x, window.y), (-1920, 362))

    def test_a_maximized_window_is_left_to_windows(self) -> None:
        window = _FakeWindow(9000, 9000, border=9, caption=38)
        window.state = "zoomed"
        with _fake_work_area(width=2560, height=1390):
            self.assertFalse(window_fit.clamp_in_place(window))
        self.assertEqual(window.geometries, [])

    def test_an_unmapped_window_is_left_alone(self) -> None:
        window = _FakeWindow(1, 1, mapped=False)
        with _fake_work_area():
            self.assertFalse(window_fit.clamp_in_place(window))
        self.assertEqual(window.geometries, [])

    def test_clamp_never_raises_when_the_window_is_gone(self) -> None:
        class Dead:
            def winfo_exists(self):
                raise RuntimeError("destroyed")

        self.assertFalse(window_fit.clamp_in_place(Dead()))


class VerifyTests(unittest.TestCase):
    def test_a_window_that_got_what_it_asked_for_is_left_alone(self) -> None:
        window = _FakeWindow(1178, 782)
        logged: list[str] = []
        with _fake_work_area():
            self.assertTrue(window_fit.verify(window, 1178, 782, log=logged.append))
        self.assertEqual(window.geometries, [])
        self.assertEqual(logged, [])

    def test_an_unmapped_window_is_not_a_mismatch(self) -> None:
        # Tk reports 1x1 before the window is mapped; that is a question asked
        # too early, not Windows refusing the size.
        window = _FakeWindow(1, 1)
        logged: list[str] = []
        with _fake_work_area():
            self.assertTrue(window_fit.verify(window, 1178, 782, log=logged.append))
        self.assertEqual(window.geometries, [])
        self.assertEqual(logged, [])

    def test_a_mismatch_is_logged_and_re_applied(self) -> None:
        window = _FakeWindow(3900, 2200)
        logged: list[str] = []
        with _fake_work_area(), mock.patch.object(window_fit, "describe", return_value="diag"):
            self.assertFalse(window_fit.verify(window, 1178, 782, log=logged.append, label="Main window"))
        self.assertEqual(len(window.geometries), 1)
        self.assertTrue(window.geometries[0].startswith("1178x782+"))
        self.assertEqual(len(logged), 1)
        self.assertIn("Main window", logged[0])
        self.assertIn("asked 1178x782", logged[0])
        self.assertIn("got 3900x2200", logged[0])

    def test_rounding_of_a_pixel_or_two_is_tolerated(self) -> None:
        window = _FakeWindow(1180, 783)
        with _fake_work_area():
            self.assertTrue(window_fit.verify(window, 1178, 782))

    def test_verify_never_raises_when_the_window_is_gone(self) -> None:
        class Dead:
            def winfo_width(self):
                raise RuntimeError("destroyed")

            def winfo_height(self):
                raise RuntimeError("destroyed")

        self.assertTrue(window_fit.verify(Dead(), 100, 100))


class WorkAreaTests(unittest.TestCase):
    def test_falls_back_to_a_usable_rectangle_when_every_api_fails(self) -> None:
        with mock.patch.object(window_fit, "_monitor_handle", return_value=None), \
                mock.patch.object(window_fit, "_user32", side_effect=OSError("no user32")):
            left, top, width, height = window_fit.work_area(None)
        self.assertEqual((left, top), (0, 0))
        self.assertGreater(width, 0)
        self.assertGreater(height, 0)

    def test_real_work_area_is_inside_the_screen(self) -> None:
        left, top, width, height = window_fit.work_area(None)
        self.assertGreater(width, 0)
        self.assertGreater(height, 0)

    def test_display_scale_is_never_below_one(self) -> None:
        self.assertGreaterEqual(window_fit.display_scale(None), 1.0)

    def test_describe_mentions_the_work_area(self) -> None:
        self.assertIn("work_area=", window_fit.describe(None))


if __name__ == "__main__":
    unittest.main()
