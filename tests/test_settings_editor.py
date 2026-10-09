from __future__ import annotations

import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from tkinter import ttk
from types import SimpleNamespace
from unittest import mock

from PIL import Image

from server16_py.ini_file import SessionIniFile
from server16_py.settings_editor import (
    SectionSpec,
    SettingsAreaEditor,
    SettingsSectionFrame,
    asset_specs,
    asset_tab_groups,
    audio_specs,
    stadium_specs,
    stadium_tab_groups,
)


def _tk_available() -> bool:
    try:
        root = tk.Tk()
        root.destroy()
        return True
    except tk.TclError:
        return False


_TK_AVAILABLE = _tk_available()


class FakeApp:
    """Minimal stand-in for Server16App -- just enough attributes for
    SettingsSectionFrame's kind="stadium" UI to construct and for
    save_entry() to run to completion."""

    def __init__(self, exedir: Path, ini: SessionIniFile) -> None:
        self.card = "#111111"
        self.card_soft = "#222222"
        self.bg = "#000000"
        self.fg = "#ffffff"
        self.muted = "#888888"
        self.accent = "#00ff00"
        self.gold = "#ffff00"
        self.error = "#ff0000"
        self.panel = "#333333"
        self.panel_alt = "#444444"
        self.exedir = exedir
        self.settings_ini = ini
        self.PitchMowsource = exedir / "FSW" / "PitchMowPattern"
        self.Nsource = exedir / "FSW" / "Nets"
        self.stadium_runtime = SimpleNamespace()

    def tr(self, translation_key: str, **kwargs) -> str:
        # Deliberately not named "key" -- save_entry() calls
        # self.tr("dialog.editor.saved", section=..., key=key), which would
        # collide with a same-named positional parameter here.
        return translation_key

    def wait_window(self, _dialog) -> None:
        pass

    def apply_all_runtime(self) -> None:
        pass

    def refresh_modules(self) -> None:
        pass

    def log(self, *args, **kwargs) -> None:
        pass


@unittest.skipUnless(_TK_AVAILABLE, "requires a Tk display")
class StadiumEditorSaveGoalpostOverridesTests(unittest.TestCase):
    """Regression tests for the 2026-09-11 bug reported live: saving a
    stadium's Police/Pitch/Net/Goalpost from the "Stadium Settings" editor
    (Edit Stadium Assets) silently never wrote [stadiumgoalpost]/
    [stadiumgoalposttexture] -- and, worse, could silently drop the
    [stadium]/[comp] assignment itself. Root cause: SessionIniFile.
    delete_key() unconditionally reloads from disk before deleting (see
    ini_file.py), which discards any write() made earlier in the same save
    cycle that hasn't reached disk yet. save_entry() used to write() the
    [stadium] value, then call _save_stadium_goalpost_overrides(), which
    interleaved write()/delete_key() across two dicts -- whichever category
    happened to be "None" (the common case) triggered a delete_key() that
    wiped out everything written earlier in the very same save_entry() call.
    Fixed by splitting into a delete-only pass (_clear_stale_stadium_
    goalpost_overrides, called BEFORE the [stadium] write) and a write-only
    pass (_write_stadium_goalpost_overrides, called after), so no delete_key()
    call in this cycle ever has anything pending to discard.

    These tests build a REAL SettingsSectionFrame (kind="stadium") against a
    REAL SessionIniFile -- a lightweight fake ini (plain dict, no reload
    semantics) would hide this exact bug, which is how it shipped unnoticed
    the first time."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.exedir = Path(self._tmp.name)
        (self.exedir / "FSW").mkdir(parents=True)
        self.ini = SessionIniFile(self.exedir / "FSW" / "settings.ini")
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.app = FakeApp(self.exedir, self.ini)

    def make_stadium_frame(self) -> SettingsSectionFrame:
        spec = SectionSpec("stadium", "Team Stadiums", kind="stadium", directory="StadiumGBD")
        return SettingsSectionFrame(self.root, self.app, spec)

    def test_model_only_override_and_the_stadium_assignment_both_persist(self) -> None:
        frame = self.make_stadium_frame()
        frame.key_var.set("176")
        frame.assigned_stadium_list.insert("end", "Anfield")
        frame._stadium_params["Anfield"] = ("4", "0", "0")
        frame._stadium_goalpost["Anfield"] = "1"
        frame._stadium_goalpost_texture["Anfield"] = "None"
        frame.save_entry()

        reloaded = SessionIniFile(self.ini.path)
        self.assertEqual(reloaded.read("176", "stadium"), "Anfield,4,0,0")
        self.assertEqual(reloaded.read("Anfield", "stadiumgoalpost"), "1")
        self.assertFalse(reloaded.key_exists("Anfield", "stadiumgoalposttexture"))

    def test_texture_only_override_and_the_stadium_assignment_both_persist(self) -> None:
        frame = self.make_stadium_frame()
        frame.key_var.set("176")
        frame.assigned_stadium_list.insert("end", "Anfield")
        frame._stadium_params["Anfield"] = ("4", "0", "0")
        frame._stadium_goalpost["Anfield"] = "None"
        frame._stadium_goalpost_texture["Anfield"] = "Azul"
        frame.save_entry()

        reloaded = SessionIniFile(self.ini.path)
        self.assertEqual(reloaded.read("176", "stadium"), "Anfield,4,0,0")
        self.assertFalse(reloaded.key_exists("Anfield", "stadiumgoalpost"))
        self.assertEqual(reloaded.read("Anfield", "stadiumgoalposttexture"), "Azul")

    def test_neither_override_set_still_persists_the_stadium_assignment(self) -> None:
        # Both categories "None" -- two delete_key() calls in a row, right
        # after the [stadium] write, was the original reported failure mode.
        frame = self.make_stadium_frame()
        frame.key_var.set("176")
        frame.assigned_stadium_list.insert("end", "Anfield")
        frame._stadium_params["Anfield"] = ("4", "0", "0")
        frame._stadium_goalpost["Anfield"] = "None"
        frame._stadium_goalpost_texture["Anfield"] = "None"
        frame.save_entry()

        reloaded = SessionIniFile(self.ini.path)
        self.assertEqual(reloaded.read("176", "stadium"), "Anfield,4,0,0")

    def test_entrance_camera_override_persists_alongside_everything_else(self) -> None:
        frame = self.make_stadium_frame()
        frame.key_var.set("176")
        frame.assigned_stadium_list.insert("end", "Anfield")
        frame._stadium_params["Anfield"] = ("4", "0", "0")
        frame._stadium_goalpost["Anfield"] = "1"
        frame._stadium_goalpost_texture["Anfield"] = "None"
        frame._stadium_entrance_cam["Anfield"] = "Aerial"
        frame.save_entry()

        reloaded = SessionIniFile(self.ini.path)
        self.assertEqual(reloaded.read("176", "stadium"), "Anfield,4,0,0")
        self.assertEqual(reloaded.read("Anfield", "stadiumgoalpost"), "1")
        self.assertEqual(reloaded.read("Anfield", "stadiumentrancecam"), "Aerial")

    def test_entrance_camera_set_to_none_deletes_the_existing_override(self) -> None:
        self.ini.write("Anfield", "Aerial", "stadiumentrancecam")
        self.ini.save()
        frame = self.make_stadium_frame()
        frame.key_var.set("176")
        frame.assigned_stadium_list.insert("end", "Anfield")
        frame._stadium_params["Anfield"] = ("4", "0", "0")
        frame._stadium_goalpost["Anfield"] = "1"
        frame._stadium_goalpost_texture["Anfield"] = "None"
        frame._stadium_entrance_cam["Anfield"] = "None"
        frame.save_entry()

        reloaded = SessionIniFile(self.ini.path)
        self.assertEqual(reloaded.read("176", "stadium"), "Anfield,4,0,0")
        self.assertEqual(reloaded.read("Anfield", "stadiumgoalpost"), "1")
        self.assertFalse(reloaded.key_exists("Anfield", "stadiumentrancecam"))

    def test_loading_an_entry_reads_the_existing_entrance_camera(self) -> None:
        self.ini.write("176", "Anfield,4,0,0", "stadium")
        self.ini.write("Anfield", "Aerial", "stadiumentrancecam")
        self.ini.save()
        frame = self.make_stadium_frame()
        frame.load_entry("176")
        self.assertEqual(frame._stadium_entrance_cam, {"Anfield": "Aerial"})
        self.assertEqual(frame.entrance_cam_var.get(), "Aerial")


@unittest.skipUnless(_TK_AVAILABLE, "requires a Tk display")
class CurrentRoundIdKeyButtonTests(unittest.TestCase):
    """Ball/Referee/Wipe/Adboard are keyed by the round id, so their editors get a
    "Use Current Round ID" button next to Key (like Use Home/Away Team for team keys)."""

    ROUND_KEYED = ("ball", "referee", "wipe", "adboard")

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        exedir = Path(self._tmp.name)
        (exedir / "FSW").mkdir(parents=True)
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.app = FakeApp(exedir, SessionIniFile(exedir / "FSW" / "settings.ini"))
        self.app.TOURROUNDID = "103"

    def make_frame(self, section: str) -> SettingsSectionFrame:
        spec = next(spec for spec in asset_specs() if spec.section == section)
        return SettingsSectionFrame(self.root, self.app, spec)

    def button_texts(self, widget) -> list[str]:
        found: list[str] = []
        for child in widget.winfo_children():
            if child.winfo_class() == "TButton":
                found.append(str(child.cget("text")))
            found.extend(self.button_texts(child))
        return found

    def test_round_keyed_modules_get_the_button_and_it_fills_the_key(self) -> None:
        for section in self.ROUND_KEYED:
            with self.subTest(section=section):
                frame = self.make_frame(section)
                self.assertIn("button.use_current_round_id", self.button_texts(frame))
                frame.key_var.set("")
                frame._use_current_round_key()
                self.assertEqual(frame.key_var.get(), "103")

    def test_no_round_read_yet_clears_the_key_instead_of_failing(self) -> None:
        self.app.TOURROUNDID = ""
        frame = self.make_frame("ball")
        frame.key_var.set("old")
        frame._use_current_round_key()
        self.assertEqual(frame.key_var.get(), "")

    def test_team_keyed_sections_do_not_get_the_button(self) -> None:
        for section in ("HomeTeamScoreBoard", "HomeTeamTvLogo", "TeamMovies", "kitsid"):
            with self.subTest(section=section):
                self.assertNotIn("button.use_current_round_id", self.button_texts(self.make_frame(section)))


@unittest.skipUnless(_TK_AVAILABLE, "requires a Tk display")
class CompetitionEntranceEditorTests(unittest.TestCase):
    """[tournamententrance] / [roundentrance]: `folder,volume,delay` keyed by the
    current tournament / round id (see TeamEntranceRuntime._parse_competition_values).
    Real SessionIniFile, like the stadium save tests above."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.exedir = Path(self._tmp.name)
        for folder in ("Teams/Arsenal", "Cups/Champions"):
            track = self.exedir / "FSW" / "Chants" / folder / "Entrance.mp3"
            track.parent.mkdir(parents=True)
            track.write_bytes(b"test")
        # A chants folder with no Entrance.mp3 must not be offered.
        (self.exedir / "FSW" / "Chants" / "Teams" / "NoEntrance").mkdir()
        self.ini = SessionIniFile(self.exedir / "FSW" / "settings.ini")
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.app = FakeApp(self.exedir, self.ini)
        self.app.TOURNAME = "78"
        self.app.TOURROUNDID = "103"

    def make_frame(self, section: str) -> SettingsSectionFrame:
        spec = next(spec for spec in audio_specs() if spec.section == section)
        return SettingsSectionFrame(self.root, self.app, spec)

    def button_texts(self, widget) -> list[str]:
        found: list[str] = []
        for child in widget.winfo_children():
            if child.winfo_class() == "TButton":
                found.append(str(child.cget("text")))
            found.extend(self.button_texts(child))
        return found

    def test_sections_are_offered_next_to_the_team_chants_editor(self) -> None:
        self.assertEqual(
            [spec.section for spec in audio_specs()],
            ["chantsid", "tournamententrance", "roundentrance"],
        )

    def test_each_section_gets_its_own_use_current_id_button(self) -> None:
        tournament = self.make_frame("tournamententrance")
        self.assertIn("button.use_current_tournament_id", self.button_texts(tournament))
        self.assertNotIn("button.use_current_round_id", self.button_texts(tournament))
        tournament._use_current_tournament_key()
        self.assertEqual(tournament.key_var.get(), "78")

        round_frame = self.make_frame("roundentrance")
        self.assertIn("button.use_current_round_id", self.button_texts(round_frame))
        self.assertNotIn("button.use_current_tournament_id", self.button_texts(round_frame))
        round_frame._use_current_round_key()
        self.assertEqual(round_frame.key_var.get(), "103")

    def test_no_tournament_read_yet_clears_the_key_instead_of_failing(self) -> None:
        self.app.TOURNAME = ""
        frame = self.make_frame("tournamententrance")
        frame.key_var.set("old")
        frame._use_current_tournament_key()
        self.assertEqual(frame.key_var.get(), "")

    def test_only_folders_with_an_entrance_track_are_offered(self) -> None:
        frame = self.make_frame("tournamententrance")
        self.assertEqual(frame._available_entrance_choices(), ["Cups/Champions", "Teams/Arsenal"])

    def test_a_folder_with_only_a_numbered_entrance_is_offered_too(self) -> None:
        chants = self.exedir / "FSW" / "Chants"
        (chants / "Teams" / "NoEntrance" / "Entrance2.mp3").write_bytes(b"test")
        # Not a variant: name + number only (see chants_runtime.numbered_tracks).
        (chants / "Teams" / "Other").mkdir()
        (chants / "Teams" / "Other" / "Entrance_old.mp3").write_bytes(b"test")
        frame = self.make_frame("tournamententrance")
        self.assertEqual(frame._available_entrance_choices(), ["Cups/Champions", "Teams/Arsenal", "Teams/NoEntrance"])

    def test_save_writes_folder_volume_and_delay_under_the_key(self) -> None:
        frame = self.make_frame("tournamententrance")
        frame.key_var.set("78")
        frame.chants_folder_var.set("Cups/Champions")
        frame.entrance_volume_var.set("0.30")
        frame.entrance_delay_var.set("5.5")
        frame.save_entry()
        self.assertEqual(SessionIniFile(self.ini.path).read("78", "tournamententrance"), "Cups/Champions,0.30,5.5")

    def test_blank_volume_and_delay_are_saved_as_the_defaults(self) -> None:
        frame = self.make_frame("roundentrance")
        frame.key_var.set("103")
        frame.chants_folder_var.set("Cups/Champions")
        frame.entrance_volume_var.set("")
        frame.entrance_delay_var.set("  ")
        frame.save_entry()
        self.assertEqual(SessionIniFile(self.ini.path).read("103", "roundentrance"), "Cups/Champions,0.16,7.0")

    def test_empty_folder_is_not_saved(self) -> None:
        frame = self.make_frame("tournamententrance")
        frame.key_var.set("78")
        frame.chants_folder_var.set("")
        with mock.patch("server16_py.settings_editor.messagebox") as box:
            frame.save_entry()
        box.showwarning.assert_called_once()
        self.assertFalse(SessionIniFile(self.ini.path).key_exists("78", "tournamententrance"))

    def test_loading_an_entry_fills_the_form_and_tolerates_a_folder_only_value(self) -> None:
        self.ini.write("78", "Cups/Champions,0.25,3", "tournamententrance")
        self.ini.write("79", "Teams/Arsenal", "tournamententrance")
        self.ini.save()
        frame = self.make_frame("tournamententrance")
        frame.load_entry("78")
        self.assertEqual(
            (frame.chants_folder_var.get(), frame.entrance_volume_var.get(), frame.entrance_delay_var.get()),
            ("Cups/Champions", "0.25", "3"),
        )
        frame.load_entry("79")
        self.assertEqual(
            (frame.chants_folder_var.get(), frame.entrance_volume_var.get(), frame.entrance_delay_var.get()),
            ("Teams/Arsenal", "0.16", "7.0"),
        )

    def test_new_entry_resets_to_the_defaults(self) -> None:
        frame = self.make_frame("roundentrance")
        frame.entrance_volume_var.set("0.9")
        frame.entrance_delay_var.set("30")
        frame.new_entry()
        self.assertEqual(frame.key_var.get(), "")
        self.assertEqual(frame.entrance_volume_var.get(), "0.16")
        self.assertEqual(frame.entrance_delay_var.get(), "7.0")
        self.assertEqual(frame.chants_folder_var.get(), "Cups/Champions")


@unittest.skipUnless(_TK_AVAILABLE, "requires a Tk display")
class ChantsPreviewMouseWheelTests(unittest.TestCase):
    """The track list of the chants preview panel scrolls with the wheel. It
    used to be bound, with the rest of the panel, to the editor body's scroll,
    and the rows rebuilt on a folder change were not bound to anything."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.exedir = Path(self._tmp.name)
        for folder, count in (("Long", 40), ("Short", 1)):
            support = self.exedir / "FSW" / "Chants" / folder / "Support"
            support.mkdir(parents=True)
            for index in range(count):
                (support / f"chant{index:02d}.mp3").write_bytes(b"test")
        self.root = tk.Tk()
        self.root.geometry("1000x600")
        self.addCleanup(self.root.destroy)
        app = FakeApp(self.exedir, SessionIniFile(self.exedir / "FSW" / "settings.ini"))
        spec = next(spec for spec in audio_specs() if spec.section == "chantsid")
        self.frame = SettingsSectionFrame(self.root, app, spec)
        self.frame.pack(fill="both", expand=True)

    def show(self, folder: str) -> None:
        self.frame.chants_folder_var.set(folder)
        self.root.update()

    def wheel(self, delta: int) -> None:
        self.frame._on_chants_preview_mousewheel(SimpleNamespace(delta=delta))
        self.root.update()

    def descendants(self, widget) -> list:
        found = [widget]
        for child in widget.winfo_children():
            found.extend(self.descendants(child))
        return found

    def test_wheel_scrolls_the_track_list_and_not_the_editor_body(self) -> None:
        self.show("Long")
        canvas = self.frame._preview_canvas
        body_before = self.frame._body_canvas.yview()
        self.assertEqual(canvas.yview()[0], 0.0)
        self.wheel(-120)
        down = canvas.yview()[0]
        self.assertGreater(down, 0.0)
        self.assertEqual(self.frame._body_canvas.yview(), body_before)
        self.wheel(120)
        self.assertLess(canvas.yview()[0], down)

    def test_rows_rebuilt_on_a_folder_change_are_bound_too(self) -> None:
        self.show("Short")
        self.show("Long")
        widgets = self.descendants(self.frame._preview_canvas)
        self.assertGreater(len(widgets), 40)
        for widget in widgets:
            self.assertIn("_on_chants_preview_mousewheel", widget.bind("<MouseWheel>"))

    def test_a_list_that_fits_hands_the_wheel_to_the_editor_body(self) -> None:
        self.show("Short")
        self.assertEqual(self.frame._preview_canvas.yview(), (0.0, 1.0))
        with mock.patch.object(self.frame._body_canvas, "yview_scroll") as body_scroll:
            self.wheel(-120)
        body_scroll.assert_called_once_with(1, "units")

    def test_changing_folder_returns_the_list_to_the_top(self) -> None:
        self.show("Long")
        self.wheel(-360)
        self.assertGreater(self.frame._preview_canvas.yview()[0], 0.0)
        self.show("Short")
        self.show("Long")
        self.assertEqual(self.frame._preview_canvas.yview()[0], 0.0)


@unittest.skipUnless(_TK_AVAILABLE, "requires a Tk display")
class StadiumEditorAssetPickerTests(unittest.TestCase):
    """The small button beside each preview-bearing combo of the stadium
    editor (Police/Pitch/Net/Goalpost Model/Goalpost Texture) opens
    AssetGridPickerDialog. The dialog itself is covered by
    test_asset_grid_picker_dialog.py -- here it's replaced by a recorder, so
    these tests only pin what the EDITOR feeds it (option lists, preview
    locations, current value) and what it does with the answer."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.exedir = Path(self._tmp.name)
        fsw = self.exedir / "FSW"
        # Preview dirs are resolved once when the frame is built, so the
        # files have to exist before make_frame().
        for rel in (
            "Images/Police/3.png",
            "Images/PitchMowPattern/2.png",
            "PitchMowPattern/pitchmowpattern_2_textures.rx3",
            "PitchMowPattern/pitchmowpattern_10_textures.rx3",
            "Images/Nets/1.png",
            "Nets/netcolor_1_textures.rx3",
            "Goalpost/GoalpostModel/1/preview.png",
            "Goalpost/GoalpostModel/2/specificgoalpost_0_0.rx3",
            "Goalpost/GoalpostColor/Azul/specificnetsupportpost_0_0_textures.rx3",
            "Camera/EntranceScene/Aerial/preview.png",
            "Camera/EntranceScene/Plain/bcstadiumcams_176.dat",
        ):
            path = fsw / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"x")
        (fsw / "Goalpost" / "GoalpostColor" / "Rojo").mkdir()  # a colour pack with no .rx3
        self.ini = SessionIniFile(fsw / "settings.ini")
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.addCleanup(self.root.update_idletasks)
        self.app = FakeApp(self.exedir, self.ini)

    def make_frame(self) -> SettingsSectionFrame:
        spec = SectionSpec("stadium", "Team Stadiums", kind="stadium", directory="StadiumGBD")
        return SettingsSectionFrame(self.root, self.app, spec)

    def select_stadium(self, frame: SettingsSectionFrame, name: str = "Anfield") -> None:
        frame.assigned_stadium_list.insert("end", name)
        frame.assigned_stadium_list.selection_set("end")
        frame._refresh_stadium_assigned_state()

    def run_picker(self, frame: SettingsSectionFrame, field: str, result: str | None) -> SimpleNamespace:
        """Runs _pick_stadium_asset with the dialog replaced by a recorder that
        answers `result`; returns the recorded call."""
        calls = []

        def fake_dialog(master, field_label, items, current="", **_kwargs):
            call = SimpleNamespace(master=master, field_label=field_label, items=items, current=current, result=result)
            calls.append(call)
            return call

        with mock.patch("server16_py.settings_editor.AssetGridPickerDialog", fake_dialog):
            frame._pick_stadium_asset(field)
        self.assertEqual(len(calls), 1)
        return calls[0]

    # ------------------------------------------------------------ option lists

    def test_police_offers_every_pattern_with_its_png(self) -> None:
        frame = self.make_frame()
        variable, label_key, items = frame._stadium_picker_setup("police")
        self.assertIs(variable, frame.police_var)
        self.assertEqual(label_key, "dialog.editor.field.police")
        self.assertEqual([item.value for item in items], [str(n) for n in range(1, 11)])
        self.assertEqual(items[2].image_path, self.exedir / "FSW" / "Images" / "Police" / "3.png")

    def test_pitch_and_net_offer_the_variant_index_the_combo_stores(self) -> None:
        frame = self.make_frame()
        _, _, pitch_items = frame._stadium_picker_setup("pitch")
        # "pitchmowpattern_10_textures.rx3" -> "10", sorted numerically (2 before 10).
        self.assertEqual([item.value for item in pitch_items], ["2", "10"])
        self.assertEqual(pitch_items[0].image_path, self.exedir / "FSW" / "Images" / "PitchMowPattern" / "2.png")
        _, _, net_items = frame._stadium_picker_setup("net")
        self.assertEqual([item.value for item in net_items], ["1"])
        self.assertEqual(net_items[0].image_path, self.exedir / "FSW" / "Images" / "Nets" / "1.png")

    def test_goalpost_model_offers_none_first_and_previews_only_where_a_preview_file_exists(self) -> None:
        frame = self.make_frame()
        variable, _, items = frame._stadium_picker_setup("goalpost")
        self.assertIs(variable, frame.goalpost_var)
        self.assertEqual([item.value for item in items], ["None", "1", "2"])
        by_value = {item.value: item for item in items}
        self.assertIsNone(by_value["None"].image_path)
        self.assertEqual(by_value["1"].image_path, self.exedir / "FSW" / "Goalpost" / "GoalpostModel" / "1" / "preview.png")
        self.assertIsNone(by_value["2"].image_path)  # no preview.<ext> in that pack

    def test_entrance_camera_offers_none_first_and_the_pack_preview_file(self) -> None:
        frame = self.make_frame()
        variable, label_key, items = frame._stadium_picker_setup("entrancecam")
        self.assertIs(variable, frame.entrance_cam_var)
        self.assertEqual(label_key, "dialog.editor.field.entrance_cam")
        self.assertEqual([item.value for item in items], ["None", "Aerial", "Plain"])
        by_value = {item.value: item for item in items}
        self.assertEqual(by_value["Aerial"].image_path, self.exedir / "FSW" / "Camera" / "EntranceScene" / "Aerial" / "preview.png")
        self.assertIsNone(by_value["Plain"].image_path)

    def test_goalpost_texture_previews_are_rendered_from_the_rx3_reusing_the_cache(self) -> None:
        rendered = self.exedir / "azul.png"
        calls = []
        self.app.stadium_runtime.render_goalpost_texture_preview = (
            lambda rx3, cache_key, **kwargs: calls.append((rx3, cache_key, kwargs)) or rendered
        )
        frame = self.make_frame()
        variable, _, items = frame._stadium_picker_setup("goalposttexture")
        self.assertIs(variable, frame.goalpost_texture_var)
        by_value = {item.value: item for item in items}
        self.assertEqual(list(by_value), ["None", "Azul", "Rojo"])
        self.assertIsNone(by_value["None"].render)
        self.assertIsNone(by_value["Rojo"].render)  # pack without an .rx3: nothing to render
        self.assertIsNone(by_value["Azul"].image_path)
        self.assertEqual(by_value["Azul"].render(), rendered)
        source = self.exedir / "FSW" / "Goalpost" / "GoalpostColor" / "Azul" / "specificnetsupportpost_0_0_textures.rx3"
        self.assertEqual(calls, [(source, "Azul", {"reuse_cached": True})])

    def test_an_unknown_field_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.make_frame()._stadium_picker_setup("shape")

    # ------------------------------------------------------------------ result

    def test_choosing_sets_the_field_and_writes_through_to_the_selected_stadium(self) -> None:
        frame = self.make_frame()
        self.select_stadium(frame)
        call = self.run_picker(frame, "police", "7")
        self.assertEqual(call.current, "4")  # the police default the row started with
        self.assertEqual(call.field_label, "dialog.editor.field.police")
        self.assertEqual(frame.police_var.get(), "7")
        self.assertEqual(frame._stadium_params["Anfield"], ("7", "0", "0"))

    def test_choosing_a_goalpost_lands_in_that_stadiums_goalpost_dicts(self) -> None:
        frame = self.make_frame()
        self.select_stadium(frame)
        # Setting a real texture pack also kicks off the editor's own async
        # preview render (a thread that reports back through after(), which
        # needs a running mainloop) -- irrelevant to what's asserted here.
        with mock.patch.object(frame, "_update_goalpost_texture_preview"):
            self.run_picker(frame, "goalposttexture", "Azul")
        self.assertEqual(frame._stadium_goalpost_texture["Anfield"], "Azul")
        self.run_picker(frame, "goalpost", "1")
        self.assertEqual(frame._stadium_goalpost["Anfield"], "1")
        self.run_picker(frame, "entrancecam", "Plain")
        self.assertEqual(frame._stadium_entrance_cam["Anfield"], "Plain")

    def test_the_current_value_is_passed_so_the_grid_can_highlight_it(self) -> None:
        frame = self.make_frame()
        self.select_stadium(frame)
        frame.goalpost_var.set("2")
        call = self.run_picker(frame, "goalpost", None)
        self.assertEqual(call.current, "2")

    def test_cancelling_leaves_the_field_and_the_stadium_untouched(self) -> None:
        frame = self.make_frame()
        self.select_stadium(frame)
        before = dict(frame._stadium_params)
        self.run_picker(frame, "net", None)
        self.assertEqual(frame.net_var.get(), "0")
        self.assertEqual(frame._stadium_params, before)

    # ----------------------------------------------------------------- buttons

    def test_every_preview_combo_has_a_picker_button_that_follows_the_combo_state(self) -> None:
        frame = self.make_frame()
        combos = (frame.police_combo, frame.pitch_combo, frame.net_combo, frame.goalpost_combo, frame.goalpost_texture_combo, frame.entrance_cam_combo)
        for combo in combos:
            self.assertTrue(combo.picker_button.instate(["disabled"]), "no stadium row selected yet")
        self.select_stadium(frame)
        for combo in combos:
            self.assertTrue(combo.picker_button.instate(["!disabled"]))
        frame.assigned_stadium_list.selection_clear(0, "end")
        frame._on_assigned_selection_changed()
        for combo in combos:
            self.assertTrue(combo.picker_button.instate(["disabled"]))

    def test_combos_outside_the_stadium_editor_get_no_picker_button(self) -> None:
        # Only the stadium editor's preview-bearing fields opt in; the shared
        # _add_combo_row leaves every other editor's combos exactly as they were.
        spec = SectionSpec("scoreboard", "Scoreboards", kind="simple", directory="ScoreBoardGBD")
        frame = SettingsSectionFrame(self.root, self.app, spec)
        self.assertFalse(hasattr(frame.value_combo, "picker_button"))


@unittest.skipUnless(_TK_AVAILABLE, "requires a Tk display")
class EntranceCamPriorityHintTests(unittest.TestCase):
    """Every editor tab where an Entrance Camera pack can be picked explains that the
    pack wins over the stadium's own EntranceScene folder."""

    HINT_KEY = "dialog.stadium.entrance_cam_hint"

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        exedir = Path(self._tmp.name)
        (exedir / "FSW").mkdir(parents=True)
        self.app = FakeApp(exedir, SessionIniFile(exedir / "FSW" / "settings.ini"))
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)

    def hint_labels(self, spec: SectionSpec) -> list[tk.Label]:
        frame = SettingsSectionFrame(self.root, self.app, spec)
        return [w for w in frame.body.winfo_children() if isinstance(w, tk.Label) and w.cget("text") == self.HINT_KEY]

    def test_stadium_settings_tab_shows_the_hint(self) -> None:
        spec = SectionSpec("stadium", "Team Stadiums", kind="stadium", directory="StadiumGBD")
        self.assertEqual(len(self.hint_labels(spec)), 1)

    def test_entrance_cameras_by_stadium_name_tab_shows_the_hint(self) -> None:
        spec = SectionSpec("stadiumentrancecam", "Entrance Cameras By Stadium Name", kind="simple", directory="FSW\\Camera\\EntranceScene", key_stadium_picker=True)
        self.assertEqual(len(self.hint_labels(spec)), 1)

    def test_other_simple_tabs_do_not_show_it(self) -> None:
        spec = SectionSpec("stadiumgoalpost", "Goalpost Models By Stadium Name", kind="simple", directory="FSW\\Goalpost\\GoalpostModel", key_stadium_picker=True)
        self.assertEqual(self.hint_labels(spec), [])


@unittest.skipUnless(_TK_AVAILABLE, "requires a Tk display")
class PackByStadiumNamePreviewTests(unittest.TestCase):
    """The "Goalpost Models / Entrance Cameras By Stadium Name" tabs show the selected pack's
    static preview image, like the Stadium Settings editor does."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        exedir = Path(self._tmp.name)
        for rel in ("FSW/Camera/EntranceScene/Aerial/preview.png", "FSW/Goalpost/GoalpostModel/1/preview.png"):
            path = exedir / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGBA", (40, 30), "red").save(path)
        (exedir / "FSW" / "Camera" / "EntranceScene" / "Bare").mkdir()
        self.app = FakeApp(exedir, SessionIniFile(exedir / "FSW" / "settings.ini"))
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)

    def make_frame(self, section: str, directory: str) -> SettingsSectionFrame:
        spec = SectionSpec(section, section, kind="simple", directory=directory, key_stadium_picker=True)
        return SettingsSectionFrame(self.root, self.app, spec)

    def assert_preview_follows_value(self, frame: SettingsSectionFrame, key: str, value: str) -> None:
        label = frame._preview_labels[key]
        self.assertEqual(str(label.cget("image")), "")
        frame.value_var.set(value)
        self.assertNotEqual(str(label.cget("image")), "")
        frame.value_var.set("Bare")
        self.assertEqual(str(label.cget("image")), "")

    def test_entrance_camera_tab_shows_the_packs_preview(self) -> None:
        frame = self.make_frame("stadiumentrancecam", "FSW\\Camera\\EntranceScene")
        self.assert_preview_follows_value(frame, "entrance_cam", "Aerial")

    def test_goalpost_model_tab_shows_the_packs_preview(self) -> None:
        frame = self.make_frame("stadiumgoalpost", "FSW\\Goalpost\\GoalpostModel")
        self.assert_preview_follows_value(frame, "goalpost_model", "1")

    def test_goalpost_texture_tab_renders_through_the_shared_texture_preview(self) -> None:
        frame = self.make_frame("stadiumgoalposttexture", "FSW\\Goalpost\\GoalpostColor")
        self.assertIn("goalpost_texture", frame._preview_labels)
        with mock.patch.object(frame, "_show_goalpost_texture_preview") as show:
            frame.value_var.set("Azul")
        show.assert_called_with("Azul")


@unittest.skipUnless(_TK_AVAILABLE, "requires a Tk display")
class LiveContextKeyButtonTests(unittest.TestCase):
    """Sections whose key the runtimes read from the live game context get a button
    next to Key that fills it from that context: round and/or tournament id for the
    competition-keyed ones (the runtimes try the round id, then the tournament id),
    "{home}vs{away}" for derbies, the engine stadium id for [stadiumnetid]."""

    COMPETITION_KEYED = ("Scoreboard", "TVLogo", "movies", "comp", "exclude")

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        exedir = Path(self._tmp.name)
        (exedir / "FSW").mkdir(parents=True)
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.app = FakeApp(exedir, SessionIniFile(exedir / "FSW" / "settings.ini"))
        self.app.HID = "241"
        self.app.AID = "243"
        self.app.derby = "241vs243"
        self.app.TOURNAME = "78"
        self.app.TOURROUNDID = "103"
        self.app.STADID = "5"

    def make_frame(self, section: str) -> SettingsSectionFrame:
        spec = next(spec for spec in (*asset_specs(), *stadium_specs()) if spec.section == section)
        return SettingsSectionFrame(self.root, self.app, spec)

    def button_texts(self, widget) -> list[str]:
        found: list[str] = []
        for child in widget.winfo_children():
            if child.winfo_class() == "TButton":
                found.append(str(child.cget("text")))
            found.extend(self.button_texts(child))
        return found

    def test_competition_keyed_sections_offer_round_and_tournament(self) -> None:
        for section in self.COMPETITION_KEYED:
            with self.subTest(section=section):
                frame = self.make_frame(section)
                texts = self.button_texts(frame)
                self.assertIn("button.use_current_round_id", texts)
                self.assertIn("button.use_current_tournament_id", texts)
                frame._use_current_round_key()
                self.assertEqual(frame.key_var.get(), "103")
                frame._use_current_tournament_key()
                self.assertEqual(frame.key_var.get(), "78")

    def test_competition_keyed_sections_get_the_competition_picker_button(self) -> None:
        for section in self.COMPETITION_KEYED:
            with self.subTest(section=section):
                self.assertIn("button.pick_competition", self.button_texts(self.make_frame(section)))
        for section in ("HomeTeamScoreBoard", "TeamMovies", "DerbyMatch", "stadiumnetid"):
            with self.subTest(section=section):
                self.assertNotIn("button.pick_competition", self.button_texts(self.make_frame(section)))

    def test_competition_picker_is_limited_to_what_the_section_accepts(self) -> None:
        for section, (round_ok, tournament_ok) in {"Scoreboard": (True, True), "ball": (True, False)}.items():
            with self.subTest(section=section):
                frame = self.make_frame(section)
                with mock.patch("server16_py.settings_editor.CompetitionPickerDialog") as picker:
                    picker.return_value.result = "103"
                    frame._pick_competition_key()
                self.assertEqual(picker.call_args.kwargs, {"allow_round": round_ok, "allow_tournament": tournament_ok})
                self.assertEqual(frame.key_var.get(), "103")

    def test_cancelling_the_competition_picker_keeps_the_key(self) -> None:
        frame = self.make_frame("Scoreboard")
        frame.key_var.set("old")
        with mock.patch("server16_py.settings_editor.CompetitionPickerDialog") as picker:
            picker.return_value.result = None
            frame._pick_competition_key()
        self.assertEqual(frame.key_var.get(), "old")

    def test_team_keyed_sections_keep_their_team_buttons_only(self) -> None:
        for section in ("HomeTeamScoreBoard", "TeamMovies", "stadium"):
            with self.subTest(section=section):
                key_buttons = [t for t in self.button_texts(self.make_frame(section)) if t.startswith(("button.use_", "button.pick_"))]
                self.assertEqual(key_buttons, ["button.use_home_team", "button.use_away_team", "button.pick_team"])

    def test_derby_button_fills_home_vs_away(self) -> None:
        for section in ("DerbyMatch", "DerbyScoreBoard", "DerbyTvLogo"):
            with self.subTest(section=section):
                frame = self.make_frame(section)
                self.assertIn("button.use_current_derby", self.button_texts(frame))
                frame._use_current_derby_key()
                self.assertEqual(frame.key_var.get(), "241vs243")

    def test_derby_button_clears_the_key_until_both_teams_are_known(self) -> None:
        # app.derby degrades to "vs" when nothing was read; the runtimes never
        # look a derby up in that state, so never write it as a key.
        self.app.AID = ""
        self.app.derby = "241vs"
        frame = self.make_frame("DerbyMatch")
        frame.key_var.set("old")
        frame._use_current_derby_key()
        self.assertEqual(frame.key_var.get(), "")
        self.app.HID = ""
        self.app.derby = "vs"
        frame._use_current_derby_key()
        self.assertEqual(frame.key_var.get(), "")

    def test_only_the_derby_section_gets_the_derby_button(self) -> None:
        for section in ("movies", "TeamMovies", "Scoreboard", "HomeTeamScoreBoard", "TVLogo", "HomeTeamTvLogo"):
            with self.subTest(section=section):
                self.assertNotIn("button.use_current_derby", self.button_texts(self.make_frame(section)))

    def test_net_by_stadium_id_gets_the_current_stadium_id_button(self) -> None:
        frame = self.make_frame("stadiumnetid")
        self.assertIn("button.use_current_stadium_id", self.button_texts(frame))
        frame._use_current_stadium_id_key()
        self.assertEqual(frame.key_var.get(), "5")
        # Keyed by stadium NAME instead: picks from the stadium list, not an id.
        by_name = self.button_texts(self.make_frame("stadiumnetname"))
        self.assertNotIn("button.use_current_stadium_id", by_name)
        self.assertIn("button.pick_stadium", by_name)

    def test_no_context_read_yet_clears_the_key_instead_of_failing(self) -> None:
        self.app.STADID = ""
        frame = self.make_frame("stadiumnetid")
        frame.key_var.set("old")
        frame._use_current_stadium_id_key()
        self.assertEqual(frame.key_var.get(), "")


class TabLayoutTests(unittest.TestCase):
    """stadium_tab_groups()/asset_tab_groups() only re-arrange stadium_specs()/
    asset_specs(): a spec left out of the layout would silently vanish from its editor."""

    def test_every_spec_lands_in_exactly_one_group(self) -> None:
        for name, specs, groups in (
            ("stadium", stadium_specs(), stadium_tab_groups()),
            ("asset", asset_specs(), asset_tab_groups()),
        ):
            with self.subTest(editor=name):
                self.assertCountEqual(
                    [spec.section for group in groups for spec in group.specs],
                    [spec.section for spec in specs],
                )

    def test_groups_with_several_specs_are_titled_and_lone_specs_use_their_own_title(self) -> None:
        for groups in (stadium_tab_groups(), asset_tab_groups()):
            for group in groups:
                with self.subTest(first=group.specs[0].section):
                    if len(group.specs) > 1:
                        self.assertTrue(group.title.startswith("dialog.editor.group."))
                        self.assertEqual(group.tab_title, group.title)
                    else:
                        self.assertEqual(group.tab_title, group.specs[0].title)

    def test_the_scoreboard_tab_holds_the_competition_home_team_and_derby_scoreboards(self) -> None:
        group = next(group for group in asset_tab_groups() if group.specs[0].section == "Scoreboard")
        self.assertEqual([spec.section for spec in group.specs], ["Scoreboard", "HomeTeamScoreBoard", "DerbyScoreBoard"])

    def test_every_tab_title_is_a_locale_key_present_in_every_language(self) -> None:
        import json

        locales = Path(__file__).resolve().parent.parent / "server16_py" / "locales"
        catalogs = {lang: json.loads((locales / f"{lang}.json").read_text(encoding="utf-8")) for lang in ("en", "es", "pt")}
        groups = (*stadium_tab_groups(), *asset_tab_groups())
        titles = {group.tab_title for group in groups} | {spec.title for group in groups for spec in group.specs}
        for title in titles:
            for lang, catalog in catalogs.items():
                with self.subTest(title=title, lang=lang):
                    self.assertIn(title, catalog)


@unittest.skipUnless(_TK_AVAILABLE, "requires a Tk display")
class GroupedSettingsEditorTests(unittest.TestCase):
    """SettingsAreaEditor: a multi-spec group is one top-level tab holding a
    sub-notebook; everything that used to work on the flat notebook (active
    frame, initial section, reload on tab change, preview stop) goes through it."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        exedir = Path(self._tmp.name)
        (exedir / "FSW").mkdir(parents=True)
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.app = FakeApp(exedir, SessionIniFile(exedir / "FSW" / "settings.ini"))
        self.app._window = lambda: self.root

    def make_editor(self, groups, initial_section: str | None = None) -> SettingsAreaEditor:
        editor = SettingsAreaEditor(self.app, "Editor", groups, initial_section=initial_section)
        self.addCleanup(editor.destroy)
        return editor

    @staticmethod
    def tab_texts(notebook: ttk.Notebook) -> list[str]:
        return [notebook.tab(tab, "text") for tab in notebook.tabs()]

    def sub_notebook(self, editor: SettingsAreaEditor, index: int) -> ttk.Notebook:
        return editor._sub_notebooks[editor.notebook.nametowidget(editor.notebook.tabs()[index])]

    def test_asset_editor_top_level_tabs_and_sub_tabs(self) -> None:
        editor = self.make_editor(asset_tab_groups())
        self.assertEqual(
            self.tab_texts(editor.notebook),
            [
                "dialog.editor.group.scoreboards",
                "dialog.editor.group.tvlogos",
                "dialog.editor.group.movies",
                "dialog.editor.choice.kits_ids",
                "dialog.editor.group.match_assets",
            ],
        )
        self.assertEqual(
            self.tab_texts(self.sub_notebook(editor, 0)),
            [
                "dialog.editor.choice.competition_scoreboards",
                "dialog.editor.choice.home_team_scoreboards",
                "dialog.editor.choice.derby_scoreboards",
            ],
        )
        self.assertEqual(len(self.sub_notebook(editor, 2).tabs()), 3)
        self.assertEqual(len(self.sub_notebook(editor, 4).tabs()), 4)

    def test_stadium_editor_top_level_tabs(self) -> None:
        editor = self.make_editor(stadium_tab_groups())
        self.assertEqual(
            self.tab_texts(editor.notebook),
            [
                "dialog.editor.group.stadiums",
                "dialog.editor.group.nets",
                "dialog.editor.group.goalposts",
                "dialog.editor.choice.scoreboard_stadium_name",
                "dialog.editor.choice.entrance_cams_by_stadium_name",
                "dialog.editor.choice.excluded_competitions",
            ],
        )
        self.assertEqual(
            self.tab_texts(self.sub_notebook(editor, 0)),
            ["dialog.editor.choice.team_stadiums", "dialog.editor.choice.competition_stadiums"],
        )

    def test_a_lone_spec_is_a_plain_tab_without_a_sub_notebook(self) -> None:
        editor = self.make_editor(asset_tab_groups())
        kits = editor.notebook.nametowidget(editor.notebook.tabs()[3])
        self.assertIsInstance(kits, SettingsSectionFrame)
        self.assertNotIn(kits, editor._sub_notebooks)

    def test_flat_spec_list_still_builds_one_plain_tab_per_spec(self) -> None:
        editor = self.make_editor(audio_specs())
        self.assertEqual(len(editor.notebook.tabs()), len(audio_specs()))
        self.assertEqual(editor._sub_notebooks, {})
        self.assertEqual(set(editor.frames), {spec.section.lower() for spec in audio_specs()})

    def test_every_section_has_a_frame(self) -> None:
        for groups, specs in ((stadium_tab_groups(), stadium_specs()), (asset_tab_groups(), asset_specs())):
            editor = self.make_editor(groups)
            self.assertEqual(set(editor.frames), {spec.section.lower() for spec in specs})

    def test_initial_section_inside_a_group_selects_the_group_and_the_sub_tab(self) -> None:
        editor = self.make_editor(asset_tab_groups(), initial_section="HomeTeamTvLogo")
        self.assertIs(editor._active_frame(), editor.frames["hometeamtvlogo"])
        self.assertEqual(editor.notebook.index(editor.notebook.select()), 1)

    def test_initial_section_is_case_insensitive_and_reaches_lone_tabs(self) -> None:
        editor = self.make_editor(asset_tab_groups(), initial_section="KITSID")
        self.assertIs(editor._active_frame(), editor.frames["kitsid"])

    def test_unknown_initial_section_is_ignored(self) -> None:
        editor = self.make_editor(asset_tab_groups(), initial_section="nope")
        self.assertIs(editor._active_frame(), editor.frames["scoreboard"])

    def test_active_frame_follows_the_sub_tab_selection(self) -> None:
        editor = self.make_editor(asset_tab_groups())
        self.assertIs(editor._active_frame(), editor.frames["scoreboard"])
        self.sub_notebook(editor, 0).select(editor.frames["hometeamscoreboard"])
        self.assertIs(editor._active_frame(), editor.frames["hometeamscoreboard"])

    def test_switching_sub_tab_reloads_the_frame_that_becomes_visible(self) -> None:
        editor = self.make_editor(asset_tab_groups())
        editor.update()
        target = editor.frames["hometeamscoreboard"]
        with mock.patch.object(target, "reload_entries") as reload:
            self.sub_notebook(editor, 0).select(target)
            editor.update()
        reload.assert_called()

    def test_switching_top_level_tab_reloads_the_sub_tab_shown_inside_it(self) -> None:
        editor = self.make_editor(asset_tab_groups())
        editor.update()
        self.sub_notebook(editor, 1).select(editor.frames["hometeamtvlogo"])
        editor.notebook.select(0)
        editor.update()
        target = editor.frames["hometeamtvlogo"]
        with mock.patch.object(target, "reload_entries") as reload:
            editor.notebook.select(1)
            editor.update()
        reload.assert_called()

    def test_any_tab_change_stops_every_frames_preview(self) -> None:
        editor = self.make_editor(asset_tab_groups())
        stoppers = {name: mock.patch.object(frame, "_stop_preview").start() for name, frame in editor.frames.items()}
        self.addCleanup(mock.patch.stopall)
        editor._on_tab_changed()
        for name, stop in stoppers.items():
            with self.subTest(section=name):
                stop.assert_called_once()


MATCH_ASSET_SECTIONS = ("ball", "referee", "wipe", "adboard")


@unittest.skipUnless(_TK_AVAILABLE, "requires a Tk display")
class MatchAssetsTabTests(unittest.TestCase):
    """The Ball / Referee / Wipe / Adboard tabs of the Match Assets group: a
    texture preview with arrows below the Value combo, and the grid picker
    button beside it. The 32-bit render itself is replaced by a recorder (it is
    covered by test_asset_runtime_rx3.py); these tests pin what the TAB asks
    for and what it does with the answers."""

    FOLDERS = {"ball": "balls", "referee": "referee", "wipe": "wipe", "adboard": "adboards"}

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.exedir = Path(self._tmp.name)
        fsw = self.exedir / "FSW"
        for rel in (
            "balls/Adidas/ball.rx3",
            "balls/Plain/readme.txt",  # a pack folder with no .rx3
            "wipe/Pack8/specificwipe_0_996_0.rx3",
            "wipe/Pack8/specificwipe_0_996_1.rx3",
            "referee/Orange/kit_0.rx3",
            "adboards/Banners/specificadboard_0_1_0_0.rx3",
        ):
            path = fsw / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"x")
        self.ini = SessionIniFile(fsw / "settings.ini")
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.addCleanup(self.root.update_idletasks)
        self.app = FakeApp(self.exedir, self.ini)
        self.render_calls: list[tuple[str, Path, Path]] = []
        self.textures_per_file = 2

        def render(kind: str, pack_dir: Path, rx3: Path) -> list[Path]:
            self.render_calls.append((kind, pack_dir, rx3))
            return [self.make_png(f"{kind}_{pack_dir.name}_{rx3.stem}_{i}.png") for i in range(self.textures_per_file)]

        self.app.assets_runtime = SimpleNamespace(render_match_asset_textures=render)

    def make_png(self, name: str) -> Path:
        from PIL import Image

        path = self.exedir / name
        Image.new("RGBA", (16, 16), (10, 120, 200, 255)).save(path)
        return path

    def make_frame(self, section: str) -> SettingsSectionFrame:
        spec = next(spec for spec in asset_specs() if spec.section == section)
        frame = SettingsSectionFrame(self.root, self.app, spec)
        self.addCleanup(frame.destroy)
        return frame

    def pump(self, until, timeout: float = 5.0) -> None:
        import time

        deadline = time.monotonic() + timeout
        while not until():
            self.assertLess(time.monotonic(), deadline, "timed out waiting for the preview")
            self.root.update()
            time.sleep(0.005)

    def run_picker(self, frame: SettingsSectionFrame, result: str | None) -> SimpleNamespace:
        calls = []

        def fake_dialog(master, field_label, items, current="", **_kwargs):
            call = SimpleNamespace(master=master, field_label=field_label, items=items, current=current, result=result)
            calls.append(call)
            return call

        with mock.patch("server16_py.settings_editor.AssetGridPickerDialog", fake_dialog):
            frame._pick_match_asset()
        self.assertEqual(len(calls), 1)
        return calls[0]

    # ------------------------------------------------------------------ layout

    def test_exactly_the_four_match_asset_specs_ask_for_the_preview(self) -> None:
        flagged = {spec.section for spec in asset_specs() if spec.rx3_preview}
        self.assertEqual(flagged, set(MATCH_ASSET_SECTIONS))
        group = next(group for group in asset_tab_groups() if group.title == "dialog.editor.group.match_assets")
        self.assertEqual({spec.section for spec in group.specs}, flagged)

    def test_each_match_asset_tab_has_the_texture_preview_and_a_picker_button(self) -> None:
        for section in MATCH_ASSET_SECTIONS:
            with self.subTest(section=section):
                frame = self.make_frame(section)
                self.assertIsNotNone(frame._rx3_preview)
                self.assertTrue(hasattr(frame.value_combo, "picker_button"))
                self.assertEqual(frame.value_combo.picker_button.cget("text"), "▦")

    def test_other_asset_tabs_are_left_exactly_as_they_were(self) -> None:
        for section in ("Scoreboard", "TVLogo", "movies", "kitsid"):
            with self.subTest(section=section):
                frame = self.make_frame(section)
                self.assertIsNone(frame._rx3_preview)
                self.assertFalse(hasattr(frame.value_combo, "picker_button"))

    def test_the_preview_starts_with_no_pack(self) -> None:
        frame = self.make_frame("wipe")
        self.assertEqual(frame._rx3_preview.frames, [])
        self.assertEqual(self.render_calls, [])

    # --------------------------------------------------------------- preview

    def test_choosing_a_pack_previews_every_texture_of_every_rx3_in_it(self) -> None:
        frame = self.make_frame("wipe")
        frame.value_var.set("Pack8")
        self.pump(lambda: len(frame._rx3_preview.frames) == 4)  # 2 files x 2 textures
        pack = self.exedir / "FSW" / "wipe" / "Pack8"
        self.assertEqual(
            self.render_calls,
            [("wipe", pack, pack / "specificwipe_0_996_0.rx3"), ("wipe", pack, pack / "specificwipe_0_996_1.rx3")],
        )
        self.assertEqual([f.rx3 for f in frame._rx3_preview.frames],
                         ["specificwipe_0_996_0.rx3"] * 2 + ["specificwipe_0_996_1.rx3"] * 2)

    def test_each_tab_looks_in_its_own_folder_with_its_own_kind(self) -> None:
        for section, pack in (("ball", "Adidas"), ("referee", "Orange"), ("adboard", "Banners")):
            with self.subTest(section=section):
                self.render_calls.clear()
                frame = self.make_frame(section)
                frame.value_var.set(pack)
                self.pump(lambda: len(frame._rx3_preview.frames) == 2)
                (kind, pack_dir, _rx3), = self.render_calls
                self.assertEqual(kind, section)
                self.assertEqual(pack_dir, self.exedir / "FSW" / self.FOLDERS[section] / pack)

    def test_a_pack_without_rx3_or_an_unknown_value_never_renders(self) -> None:
        frame = self.make_frame("ball")
        for value in ("Plain", "NoSuchPack", "   "):
            frame.value_var.set(value)
            self.root.update()
            self.pump(lambda: frame._rx3_preview_job is None)
        self.assertEqual(self.render_calls, [])
        self.assertEqual(frame._rx3_preview.frames, [])

    def test_a_burst_of_changes_renders_only_the_value_it_settles_on(self) -> None:
        # Stepping through the combo with the arrow keys must not launch a
        # 32-bit render per press.
        frame = self.make_frame("ball")
        with mock.patch.object(frame._rx3_preview, "show_pack") as show:
            for value in ("A", "Ad", "Adi", "Adidas"):
                frame.value_var.set(value)
            self.pump(lambda: show.called)
        show.assert_called_once()
        self.assertEqual(show.call_args.args[0], self.exedir / "FSW" / "balls" / "Adidas")

    def test_loading_an_entry_refreshes_the_preview(self) -> None:
        # key 12 -> pack Adidas, like a saved [ball] entry. Saved to disk because
        # load_entry() reloads the file first, which drops unsaved writes.
        self.ini.write("12", "Adidas", "ball")
        self.ini.save()
        frame = self.make_frame("ball")
        frame.load_entry("12")
        self.pump(lambda: len(frame._rx3_preview.frames) == 2)
        self.assertEqual(frame.value_var.get(), "Adidas")

    def test_destroying_the_tab_with_a_refresh_pending_is_safe(self) -> None:
        frame = self.make_frame("ball")
        frame.value_var.set("Adidas")
        self.assertIsNotNone(frame._rx3_preview_job)
        frame.destroy()
        self.assertIsNone(frame._rx3_preview_job)
        for _ in range(30):
            self.root.update()

    # ---------------------------------------------------------------- picker

    def test_the_grid_offers_every_pack_folder_with_a_texture_render_where_there_is_an_rx3(self) -> None:
        frame = self.make_frame("ball")
        call = self.run_picker(frame, None)
        by_value = {item.value: item for item in call.items}
        self.assertEqual(list(by_value), ["Adidas", "Plain"])
        self.assertIsNone(by_value["Plain"].render)  # no .rx3: placeholder
        first_texture = by_value["Adidas"].render()
        self.assertEqual(first_texture.name, "ball_Adidas_ball_0.png")  # the FIRST texture of the pack
        self.assertEqual(self.render_calls, [("ball", self.exedir / "FSW" / "balls" / "Adidas", self.exedir / "FSW" / "balls" / "Adidas" / "ball.rx3")])

    def test_the_grid_is_titled_for_the_tab_and_highlights_the_current_value(self) -> None:
        for section, key in (("ball", "ball"), ("referee", "referee"), ("wipe", "wipe"), ("adboard", "adboard")):
            with self.subTest(section=section):
                frame = self.make_frame(section)
                frame.value_var.set("  Chosen ")
                call = self.run_picker(frame, None)
                self.assertEqual(call.field_label, f"dialog.editor.field.{key}")
                self.assertEqual(call.current, "Chosen")

    def test_choosing_in_the_grid_sets_the_value_and_previews_that_pack(self) -> None:
        frame = self.make_frame("wipe")
        self.run_picker(frame, "Pack8")
        self.assertEqual(frame.value_var.get(), "Pack8")
        self.pump(lambda: len(frame._rx3_preview.frames) == 4)

    def test_cancelling_the_grid_leaves_the_value_untouched(self) -> None:
        frame = self.make_frame("wipe")
        frame.value_var.set("Pack8")
        self.run_picker(frame, None)
        self.assertEqual(frame.value_var.get(), "Pack8")

    def test_the_grid_rereads_the_folder_so_a_new_pack_shows_up(self) -> None:
        frame = self.make_frame("ball")
        (self.exedir / "FSW" / "balls" / "Added").mkdir()
        call = self.run_picker(frame, None)
        self.assertIn("Added", [item.value for item in call.items])

    def test_the_picker_button_opens_the_grid(self) -> None:
        frame = self.make_frame("ball")
        calls = []
        with mock.patch("server16_py.settings_editor.AssetGridPickerDialog",
                        lambda *a, **k: calls.append((a, k)) or SimpleNamespace(result=None)):
            frame.value_combo.picker_button.invoke()
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
