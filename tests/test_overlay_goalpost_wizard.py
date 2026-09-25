from __future__ import annotations

import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

from server16_py.app_overlay import OverlayMixin
from server16_py.assignment_runtime import AssignmentRuntime
from server16_py.ini_file import SessionIniFile
from server16_py.stadium_runtime import StadiumRuntime


class FakeInjector:
    """Records what the overlay pushes into shared memory."""

    def __init__(self) -> None:
        self.header = ""
        self.dashboard: list[str] = []
        self.preview_paths: list[str] = []

    def set_menu_loading(self, _value) -> None:
        pass

    def set_list_header(self, header: str) -> None:
        self.header = header

    def set_menu_content(self, *_args, **_kwargs) -> None:
        pass

    def set_window_info(self, *_args) -> None:
        pass

    def set_dashboard_content(self, items) -> None:
        self.dashboard = list(items)

    def set_match_score_time(self, *_args) -> None:
        pass

    def set_preview_image(self, path: str) -> None:
        self.preview_paths.append(path)


class FakeOverlayApp(OverlayMixin):
    """Real OverlayMixin wizard/list/preview code on a minimal host, wired to
    a REAL SessionIniFile + AssignmentRuntime -- the overrides' delete_key()
    reloads from disk (see tests/test_assignment_runtime.py), so a toy ini
    fake would hide exactly the write-ordering bugs this wizard could have."""

    def __init__(self, exedir: Path, ini_path: Path) -> None:
        self.exedir = exedir
        self.settings_ini = SessionIniFile(ini_path)
        self.assignment_runtime = AssignmentRuntime(self)
        self.assignment_runtime.refresh_context_for_assignment = lambda: None
        self.stadium_runtime = SimpleNamespace(
            _parse_stadium_entries=StadiumRuntime._parse_stadium_entries,
            _read_goalpost_override_names=StadiumRuntime._read_goalpost_override_names,
            render_goalpost_texture_preview=self._render_goalpost_texture_preview,
        )
        self.render_calls: list[str] = []
        self.applied: list[dict] = []
        self.ini_path = ini_path

        self._d3d_injector = FakeInjector()
        self._d3d_menu_visible = True
        self.movie_preview_runtime = SimpleNamespace(stop=lambda: None)
        self.overlay_performance_mode_var = SimpleNamespace(get=lambda: False)
        self.labels: dict = {}
        self.info_labels: dict = {}

        self._overlay_tab_names = ["scoreboards", "stadiums", "movies", "tvlogos", "kits"]
        self._overlay_tab_index = 1
        self._overlay_scope_phase = False
        self._overlay_selected_scope = "0"
        self._overlay_filter_phase = False
        # Leaving the wizard lands back on the Stadiums leaf list, which reads
        # these (the list itself comes from `targetpath`, left unset here).
        self._overlay_stadium_country_filter: set[str] = set()
        self._overlay_stadium_sort_desc = False
        self._overlay_stadium_thumb_cache: dict[str, str] = {}
        self._overlay_visible_rows = 20
        self._overlay_selected_index = 0
        self._overlay_scroll_offset = 0
        self._overlay_items: list[str] = ["Anfield"]
        self._overlay_item_count = 1
        self._overlay_item_checked: list[bool] = [False]
        self._overlay_window_base = 0
        self._overlay_list_header = ""
        self._overlay_kit_preview_cache: dict[str, str] = {}
        self._overlay_kit_preview_pending: set[str] = set()
        self._overlay_goalpost_render_lock = threading.Lock()
        self._stadium_picker_pending = False
        self._stadium_picker_resolved = False
        self._stadium_picker_chosen = None
        self._stadium_picker_signature = None
        self._kickoff_generation = 1
        self.HID = "456"
        self.AID = "10"
        self.TOURNAME = "1"
        self.TOURROUNDID = "2"
        self._clear_overlay_wizard_state()

    # --- stand-ins for the parts of the app this test doesn't exercise ---
    def log(self, *_args, **_kwargs) -> None:
        pass

    def _resolve_stadium_preview_path_or_default(self, _name: str):
        return None

    def _uninstall_mouse_wheel_hook(self) -> None:
        pass

    def _uninstall_keyboard_hook(self) -> None:
        pass

    def _publish_overlay_menu_state(self) -> None:
        pass

    def apply_all_runtime(self) -> None:
        # What the runtime would see the instant the stadium is applied.
        on_disk = SessionIniFile(self.ini_path)
        self.applied.append({
            "stadium": on_disk.read("456", "stadium"),
            "model": on_disk.read("Anfield", "stadiumgoalpost"),
            "texture": on_disk.read("Anfield", "stadiumgoalposttexture"),
        })

    def _render_goalpost_texture_preview(self, source_rx3, cache_key, max_size=220, reuse_cached=False) -> Path:
        self.render_calls.append(cache_key)
        return Path(f"{cache_key}.png")

    # --- test drivers ---
    def pick(self, label: str) -> None:
        """Highlight `label` in the current list and confirm it."""
        self._overlay_selected_index = self._overlay_items.index(label)
        self._activate_overlay_selected_item("test")

    @property
    def inj(self) -> FakeInjector:
        return self._d3d_injector


class OverlayGoalpostWizardTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        self.exedir = root / "fifa"
        fsw = self.exedir / "FSW"
        for name in ("0", "1"):
            for folder in ("PitchMowPattern", "Nets"):
                path = fsw / "Images" / folder / f"{name}.png"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"png")
        for model in ("A", "B"):
            (fsw / "Goalpost" / "GoalpostModel" / model).mkdir(parents=True)
        (fsw / "Goalpost" / "GoalpostModel" / "B" / "preview.png").write_bytes(b"png")
        for color in ("Azul", "Rojo"):
            folder = fsw / "Goalpost" / "GoalpostColor" / color
            folder.mkdir(parents=True)
            (folder / "specificnetsupportpost_0_0_textures.rx3").write_bytes(b"rx3")
        self.ini_path = root / "settings.ini"
        self.app = FakeOverlayApp(self.exedir, self.ini_path)

    def start_wizard(self) -> None:
        self.app.pick("Anfield")
        self.assertEqual(self.app._overlay_wizard_phase, "police")

    def run_to_goalpost_model_step(self) -> None:
        self.start_wizard()
        self.app.pick("4")   # police
        self.app.pick("0")   # pitch
        self.app.pick("1")   # net
        self.assertEqual(self.app._overlay_wizard_phase, "goalpost")

    # ---------------------------------------------------------------- steps
    def test_net_step_now_leads_to_the_goalpost_model_step_instead_of_applying(self) -> None:
        self.run_to_goalpost_model_step()
        self.assertEqual(self.app.applied, [])
        self.assertFalse(self.app.settings_ini.key_exists("456", "stadium"))

    def test_goalpost_steps_list_none_then_every_pack_folder(self) -> None:
        self.run_to_goalpost_model_step()
        self.assertEqual(self.app._overlay_items, ["None", "A", "B"])
        self.app.pick("A")
        self.assertEqual(self.app._overlay_wizard_phase, "goalposttexture")
        self.assertEqual(self.app._overlay_items, ["None", "Azul", "Rojo"])

    def test_step_headers_name_the_previous_pick(self) -> None:
        self.run_to_goalpost_model_step()
        self.assertEqual(self.app.inj.header, "Net: 1  ->  Goalpost Model")
        self.app.pick("B")
        self.assertEqual(self.app.inj.header, "Model: B  ->  Goalpost Texture")

    def test_a_missing_goalpost_folder_still_offers_none(self) -> None:
        for child in (self.exedir / "FSW" / "Goalpost" / "GoalpostColor").iterdir():
            (child / "specificnetsupportpost_0_0_textures.rx3").unlink()
            child.rmdir()
        (self.exedir / "FSW" / "Goalpost" / "GoalpostColor").rmdir()
        self.run_to_goalpost_model_step()
        self.app.pick("A")
        self.assertEqual(self.app._overlay_items, ["None"])

    # ----------------------------------------------------------- applying
    def test_finishing_writes_stadium_and_both_goalpost_overrides_before_applying(self) -> None:
        self.run_to_goalpost_model_step()
        self.app.pick("B")
        self.app.pick("Rojo")

        self.assertIsNone(self.app._overlay_wizard_phase)
        self.assertEqual(len(self.app.applied), 1)
        # The apply is what reads [stadiumgoalpost*] back, so they must already
        # be on disk at that moment -- and the assignment written before it.
        self.assertEqual(self.app.applied[0], {"stadium": "Anfield,4,0,1", "model": "B", "texture": "Rojo"})
        reloaded = SessionIniFile(self.ini_path)
        self.assertEqual(reloaded.read("456", "stadium"), "Anfield,4,0,1")
        self.assertEqual(reloaded.read("Anfield", "stadiumgoalpost"), "B")
        self.assertEqual(reloaded.read("Anfield", "stadiumgoalposttexture"), "Rojo")

    def test_picking_none_clears_an_existing_override_but_keeps_the_other(self) -> None:
        self.app.settings_ini.write("Anfield", "A", "stadiumgoalpost")
        self.app.settings_ini.write("Anfield", "Azul", "stadiumgoalposttexture")
        self.app.settings_ini.save()

        self.run_to_goalpost_model_step()
        self.app.pick("None")   # model: clear
        self.app.pick("Rojo")   # texture: change

        reloaded = SessionIniFile(self.ini_path)
        self.assertFalse(reloaded.key_exists("Anfield", "stadiumgoalpost"))
        self.assertEqual(reloaded.read("Anfield", "stadiumgoalposttexture"), "Rojo")
        self.assertEqual(reloaded.read("456", "stadium"), "Anfield,4,0,1")

    def test_a_failed_override_save_does_not_lose_the_assignment(self) -> None:
        def boom(*_args, **_kwargs):
            raise OSError("disk full")

        self.app.assignment_runtime._write_stadium_goalpost_overrides = boom
        self.run_to_goalpost_model_step()
        self.app.pick("B")
        self.app.pick("Rojo")

        self.assertEqual(SessionIniFile(self.ini_path).read("456", "stadium"), "Anfield,4,0,1")
        self.assertEqual(len(self.app.applied), 1)

    # --------------------------------------------------------------- back
    def test_back_walks_every_step_in_reverse_then_leaves_the_wizard(self) -> None:
        self.run_to_goalpost_model_step()
        self.app.pick("A")
        seen = [self.app._overlay_wizard_phase]
        for _ in range(4):
            self.app._wizard_back()
            seen.append(self.app._overlay_wizard_phase)
        self.assertEqual(seen, ["goalposttexture", "goalpost", "net", "pitch", "police"])
        self.app._wizard_back()
        self.assertIsNone(self.app._overlay_wizard_phase)
        self.assertIsNone(self.app._overlay_wizard_stadium)
        self.assertIsNone(self.app._overlay_wizard_net)
        self.assertIsNone(self.app._overlay_wizard_goalpost)

    def test_restarting_the_wizard_forgets_the_previous_runs_goalpost_picks(self) -> None:
        self.run_to_goalpost_model_step()
        self.app.pick("B")
        self.app._wizard_back()
        self.app._wizard_back()
        self.app._wizard_back()
        self.app._wizard_back()
        self.app._wizard_back()   # out of the wizard, back on the stadium list
        self.app._overlay_items = ["Anfield"]
        self.start_wizard()
        self.assertIsNone(self.app._overlay_wizard_net)
        self.assertIsNone(self.app._overlay_wizard_goalpost)

    # ------------------------------------------------------- preselection
    def test_goalpost_steps_start_on_the_stadiums_current_pack(self) -> None:
        self.app.settings_ini.write("Anfield", "B", "stadiumgoalpost")
        self.app.settings_ini.write("Anfield", "Rojo", "stadiumgoalposttexture")
        self.app.settings_ini.save()

        self.run_to_goalpost_model_step()
        self.assertEqual(self.app._overlay_selected_index, self.app._overlay_items.index("B"))
        self.app.pick("B")
        self.assertEqual(self.app._overlay_selected_index, self.app._overlay_items.index("Rojo"))

    def test_goalpost_steps_start_on_none_when_nothing_is_configured(self) -> None:
        self.run_to_goalpost_model_step()
        self.assertEqual(self.app._overlay_selected_index, 0)

    def test_a_configured_pack_that_no_longer_exists_falls_back_to_none(self) -> None:
        self.app.settings_ini.write("Anfield", "Deleted", "stadiumgoalpost")
        self.app.settings_ini.save()
        self.run_to_goalpost_model_step()
        self.assertEqual(self.app._overlay_selected_index, 0)

    # ---------------------------------------------------------- dashboard
    def test_dashboard_shows_goalpost_picks_as_they_are_made_and_fits_the_overlay(self) -> None:
        from server16_py.d3d_injector import _MAX_DASH_ITEMS

        self.run_to_goalpost_model_step()
        lines = self.app.inj.dashboard
        self.assertLessEqual(len(lines), _MAX_DASH_ITEMS)
        self.assertIn("Net:     1", lines)
        self.assertIn("Goalpost model:   [selecting...]", lines)
        self.assertIn("Goalpost texture: -", lines)

        self.app.pick("B")
        lines = self.app.inj.dashboard
        self.assertLessEqual(len(lines), _MAX_DASH_ITEMS)
        self.assertIn("Goalpost model:   B", lines)
        self.assertIn("Goalpost texture: [selecting...]", lines)
        self.assertIn(">> Select Goalpost Texture <<", lines)

    def test_dashboard_marks_later_steps_as_not_chosen_yet(self) -> None:
        self.start_wizard()
        lines = self.app.inj.dashboard
        self.assertIn("Police:  [selecting...]", lines)
        for label in ("Pitch:   -", "Net:     -", "Goalpost model:   -", "Goalpost texture: -"):
            self.assertIn(label, lines)

    # ------------------------------------------------------------ previews
    def test_goalpost_model_preview_is_the_packs_preview_image(self) -> None:
        self.run_to_goalpost_model_step()
        self.app._overlay_selected_index = self.app._overlay_items.index("B")
        self.app._update_d3d_preview_image()
        self.assertEqual(
            self.app.inj.preview_paths[-1],
            str(self.exedir / "FSW" / "Goalpost" / "GoalpostModel" / "B" / "preview.png"),
        )
        self.app._overlay_selected_index = self.app._overlay_items.index("A")   # no preview image
        self.app._update_d3d_preview_image()
        self.assertEqual(self.app.inj.preview_paths[-1], "")
        self.app._overlay_selected_index = 0                                    # "None"
        self.app._update_d3d_preview_image()
        self.assertEqual(self.app.inj.preview_paths[-1], "")

    def wait_for(self, predicate, timeout: float = 3.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return True
            time.sleep(0.01)
        return predicate()

    def enter_texture_step(self) -> None:
        self.run_to_goalpost_model_step()
        self.app.pick("A")
        self.assertEqual(self.app._overlay_wizard_phase, "goalposttexture")

    def test_texture_preview_never_blocks_and_is_pushed_once_rendered(self) -> None:
        self.enter_texture_step()
        self.app._overlay_selected_index = self.app._overlay_items.index("Azul")

        self.assertEqual(self.app._resolve_goalpost_texture_menu_preview("Azul"), "")   # not ready yet
        self.assertTrue(self.wait_for(lambda: "Azul.png" in self.app.inj.preview_paths))
        self.assertEqual(self.app.render_calls, ["Azul"])
        # Revisiting is answered straight from the cache: no second render.
        self.assertEqual(self.app._resolve_goalpost_texture_menu_preview("Azul"), "Azul.png")
        self.assertEqual(self.app.render_calls, ["Azul"])

    def test_texture_preview_of_none_or_a_pack_without_an_rx3_renders_nothing(self) -> None:
        self.enter_texture_step()
        (self.exedir / "FSW" / "Goalpost" / "GoalpostColor" / "Rojo" / "specificnetsupportpost_0_0_textures.rx3").unlink()
        self.assertEqual(self.app._resolve_goalpost_texture_menu_preview("None"), "")
        self.assertEqual(self.app._resolve_goalpost_texture_menu_preview("Rojo"), "")
        time.sleep(0.05)
        self.assertEqual(self.app.render_calls, [])

    def test_texture_render_is_skipped_when_the_player_scrolled_past_it(self) -> None:
        self.enter_texture_step()
        self.app._overlay_selected_index = self.app._overlay_items.index("Azul")

        with self.app._overlay_goalpost_render_lock:      # a render is already in flight
            self.assertEqual(self.app._resolve_goalpost_texture_menu_preview("Azul"), "")
            self.app._overlay_selected_index = self.app._overlay_items.index("Rojo")   # ...cursor moves on
        # Once the lock frees, Azul's worker sees it is no longer highlighted and
        # gives up without spawning the 32-bit render or leaving itself "pending".
        self.assertTrue(self.wait_for(lambda: "goalposttex_Azul" not in self.app._overlay_kit_preview_pending))
        self.assertEqual(self.app.render_calls, [])
        self.assertNotIn("Azul.png", self.app.inj.preview_paths)
        # ...and coming back later starts a fresh render.
        self.app._overlay_selected_index = self.app._overlay_items.index("Azul")
        self.app._resolve_goalpost_texture_menu_preview("Azul")
        self.assertTrue(self.wait_for(lambda: "Azul.png" in self.app.inj.preview_paths))

    def test_texture_render_result_is_cached_but_not_pushed_if_selection_moved_meanwhile(self) -> None:
        self.enter_texture_step()
        self.app._overlay_selected_index = self.app._overlay_items.index("Azul")
        original = self.app.stadium_runtime.render_goalpost_texture_preview

        def render_then_move(source_rx3, cache_key, **kwargs):
            result = original(source_rx3, cache_key, **kwargs)
            self.app._overlay_selected_index = self.app._overlay_items.index("Rojo")
            return result

        self.app.stadium_runtime.render_goalpost_texture_preview = render_then_move
        self.app._resolve_goalpost_texture_menu_preview("Azul")
        self.assertTrue(self.wait_for(lambda: "goalposttex_Azul" in self.app._overlay_kit_preview_cache))
        time.sleep(0.05)
        self.assertNotIn("Azul.png", self.app.inj.preview_paths)

    def test_texture_preview_is_skipped_in_performance_mode(self) -> None:
        self.enter_texture_step()
        self.app.overlay_performance_mode_var = SimpleNamespace(get=lambda: True)
        self.assertEqual(self.app._resolve_goalpost_texture_menu_preview("Azul"), "")
        time.sleep(0.05)
        self.assertEqual(self.app.render_calls, [])

    def test_a_failed_texture_render_is_retried_on_the_next_visit(self) -> None:
        self.enter_texture_step()
        self.app._overlay_selected_index = self.app._overlay_items.index("Azul")
        calls = []

        def broken(source_rx3, cache_key, **kwargs):
            calls.append(cache_key)
            raise RuntimeError("32-bit bridge unavailable")

        self.app.stadium_runtime.render_goalpost_texture_preview = broken
        self.app._resolve_goalpost_texture_menu_preview("Azul")
        self.assertTrue(self.wait_for(lambda: "goalposttex_Azul" not in self.app._overlay_kit_preview_pending))
        self.assertEqual(calls, ["Azul"])
        self.assertNotIn("goalposttex_Azul", self.app._overlay_kit_preview_cache)
        self.app._resolve_goalpost_texture_menu_preview("Azul")
        self.assertTrue(self.wait_for(lambda: len(calls) == 2))


if __name__ == "__main__":
    unittest.main()
