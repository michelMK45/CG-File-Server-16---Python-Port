from __future__ import annotations

import queue
import tempfile
import unittest
import unittest.mock
from pathlib import Path

from PIL import Image

from server16_py import ingame_datafile, ingame_images, ingame_menu_runtime, ingame_menu_texts
from server16_py.ingame_menu_runtime import DEFAULT_LABEL, NO_MATCH, NOT_YET, InGameMenuRuntime
from server16_py.ini_file import SessionIniFile


class FakeApp:
    """Enough of Server16App for InGameMenuRuntime: a game folder with the menu installed (or not), the
    packs' folders and the real SessionIniFile."""

    def __init__(self, base: Path, installed: bool = True) -> None:
        self.exedir = base
        self.ScoreBoard = base / "ScoreBoardGBD"
        self.TVLogo = base / "TVLogoGBD"
        for folder, packs in ((self.ScoreBoard, ("LaLiga", "Bundesliga", "UCL")), (self.TVLogo, ("ESPN", "DAZN"))):
            for pack in packs:
                (folder / pack).mkdir(parents=True)
        (self.TVLogo / "bad=name").mkdir()  # "=" cannot travel in the data text ("|" is not a valid folder name)
        (base / "FSW").mkdir()
        (base / "locale.ini").write_text("[LOCALE]\nUSE_LANGUAGE_SELECT = 0\nDEFAULT_LANGUAGE = spa,es\n",
                                         encoding="latin-1")   # FIP's: the game in Spanish
        self.targetpath = base / "StadiumGBD"
        for name in ("ARG - Bombonera", "ARG - Monumental", "ESP - Camp Nou", "Wembley"):
            (self.targetpath / name).mkdir(parents=True)
        thumbs = self.targetpath / "render" / "thumbnail" / "stadium"
        thumbs.mkdir(parents=True)
        Image.new("RGB", (640, 360), (10, 120, 30)).save(thumbs / "ESP - Camp Nou.jpg")
        for sub_dir in ("Images/PitchMowPattern", "Images/Nets"):
            folder = base / "FSW" / sub_dir
            folder.mkdir(parents=True)
            for stem in ("0", "1", "10"):
                Image.new("RGBA", (64, 128), (200, 200, 200, 255)).save(folder / f"{stem}.png")
        police = base / "FSW" / "Images" / "Police"
        police.mkdir(parents=True)
        Image.new("RGBA", (100, 100), (0, 0, 200, 255)).save(police / "4.png")
        for sub_dir, packs in (("Goalpost/GoalpostModel", ("1", "2")), ("Goalpost/GoalpostColor", ("Grey", "Black")),
                               ("NetMesh", ("Hex 1",)), ("Camera/EntranceScene", ("Aerial", "Classic"))):
            for pack in packs:
                (base / "FSW" / sub_dir / pack).mkdir(parents=True)
        Image.new("RGB", (200, 100)).save(base / "FSW" / "Goalpost" / "GoalpostModel" / "2" / "preview.png")
        Image.new("RGB", (200, 100)).save(base / "FSW" / "Camera" / "EntranceScene" / "Aerial" / "preview.png")
        Image.new("RGBA", (64, 64)).save(base / "FSW" / "NetMesh" / "Hex 1" / "net.png")
        (base / "FSW" / "Goalpost" / "GoalpostColor" / "Grey" / "post_textures.rx3").write_bytes(b"rx3")
        rendered = base / "rendered_grey.png"
        Image.new("RGB", (220, 220), (128, 128, 128)).save(rendered)
        self.stadium_runtime = type("FakeStadiumRuntime", (), {
            "render_goalpost_texture_preview": lambda _self, rx3, cache_key, reuse_cached=False:
                rendered if cache_key == "Grey" else None})()
        self.Movies = base / "MoviesGBD"
        for pack in ("LaLiga", "UCL", "Copa"):
            (self.Movies / pack).mkdir(parents=True)
        (self.Movies / "UCL" / "bootflowoutro.vp8").write_bytes(b"vp8 movie bytes")
        self.HID = ""
        self.AID = ""
        self.runtime_applied = 0
        self.settings_ini = SessionIniFile(base / "FSW" / "settings.ini")
        if installed:
            menu = base / ingame_menu_runtime.MENU_MOVIE
            menu.parent.mkdir(parents=True)
            menu.write_bytes(b"BIG4")
        self._worker_queue: queue.Queue = queue.Queue()
        self.logs: list[str] = []
        self.polls = 0

    def log(self, *parts, **_kwargs) -> None:
        self.logs.append(" ".join(str(p) for p in parts))

    def _schedule_worker_poll(self) -> None:
        self.polls += 1

    def _resolve_team_name(self, hid: str) -> str:
        return {"241": "FC Barcelona"}.get(hid, "")

    def _resolve_stadium_preview_path(self, name: str):
        p = self.targetpath / "render" / "thumbnail" / "stadium" / f"{name}.jpg"
        return p if p.exists() else None

    def apply_all_runtime(self) -> None:
        self.runtime_applied += 1


def read_data(app: FakeApp, lang: str | None = "spa") -> dict[str, str]:
    """The key=value lines of the data.big the runtime wrote, its keys in `lang` as the menu shows them with FIFA
    in that language (None: as written)."""
    data = (app.exedir / ingame_menu_runtime.DATA_MOVIE).read_bytes()
    _entry, items = ingame_datafile.read_const(dict(ingame_datafile.big_entries(data))["1"])
    text = next(v for t, v in items if t == 1 and v.startswith(b"SOURCE=")).decode("utf-8")
    lines = dict(line.split("=", 1) for line in text.split("\n"))
    if lang is None:
        return lines
    return {k: ingame_menu_texts.render(v, lang) for k, v in lines.items()}


class InGameMenuRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.app = FakeApp(Path(self._tmp.name))
        self.rt = InGameMenuRuntime(self.app)
        self.rt._images_started = True  # no preview thread in the tests (tested directly, it would race the cleanup)

    def test_not_installed_does_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as other:
            app = FakeApp(Path(other), installed=False)
            rt = InGameMenuRuntime(app)
            self.assertFalse(rt.write_data("test"))
            rt.on_page("game/screens/cgfs16/CGFS16Menu", "game/screens/fluxHub/FluxHub", 123)
            self.assertFalse((Path(other) / ingame_menu_runtime.DATA_MOVIE).exists())
            self.assertEqual(app.polls, 0)

    def test_data_carries_the_packs_and_the_default_assignment(self) -> None:
        self.app.settings_ini.write("0", "UCL", "Scoreboard")
        self.app.settings_ini.save()
        self.assertTrue(self.rt.write_data("test"))
        d = read_data(self.app)
        self.assertEqual(d["SCOREBOARD"].split("|"), [DEFAULT_LABEL, "Bundesliga", "LaLiga", "UCL"])
        self.assertEqual(d["SCOREBOARD_SEL"], "3")
        self.assertEqual(d["TVLOGO"].split("|"), [DEFAULT_LABEL, "DAZN", "ESPN"])  # "bad=name" left out
        self.assertEqual(d["TVLOGO_SEL"], "0")
        self.assertEqual(d["STADIUM"], NO_MATCH)        # no match context: the Estadio tab says where to open it
        self.assertEqual(d["MOVIES"], NO_MATCH)
        self.assertEqual(d["KITS"], NOT_YET)
        self.assertEqual(d["ACK"], "0")
        self.assertFalse(self.rt.write_data("again"))            # nothing changed
        self.assertTrue(self.rt.write_data("again", force=True))

    def test_leaving_the_menu_scans_in_a_worker_and_applies_the_save(self) -> None:
        record = (1, (("SCOREBOARD", (1, "Bundesliga")), ("TVLOGO", (2, "ESPN")), ("STADIUM", (0, NOT_YET))))
        with unittest.mock.patch.object(ingame_menu_runtime.ingame_recordscan, "scan",
                                        return_value=([record], 3700.0, 3.4)) as scan:
            self.rt.on_page("game/screens/fluxHub/FluxHub", ingame_menu_runtime.MENU_PAGE, 77)
            self.rt.on_page(ingame_menu_runtime.MENU_PAGE, "game/screens/fluxHub/FluxHub", 77)
            event = self.app._worker_queue.get(timeout=5)
        self.assertEqual(scan.call_args.args[:3], (77, [], 0))
        self.assertTrue(self.rt.busy)
        self.assertEqual(event[0], "ingame_menu_scan")
        self.rt.on_scan_done(*event[1:])
        self.assertFalse(self.rt.busy)
        self.assertEqual(self.app.settings_ini.read("0", "Scoreboard"), "Bundesliga")
        self.assertEqual(self.app.settings_ini.read("0", "TVLogo"), "ESPN")
        self.assertEqual(self.rt.last_seq, 1)
        d = read_data(self.app)                                   # written again for the menu, with the ack
        self.assertEqual((d["ACK"], d["SCOREBOARD_SEL"], d["TVLOGO_SEL"]), ("1", "1", "2"))

    def test_same_or_older_save_is_not_applied_again(self) -> None:
        self.rt.attached(5)
        self.rt.last_seq = 3
        self.rt.on_scan_done(5, [(3, (("TVLOGO", (1, "DAZN")),))], [], 1.0, 0.1, None)
        self.assertEqual(self.app.settings_ini.read("0", "TVLogo"), "")
        self.assertIn("without a new save", self.app.logs[-1])
        self.rt.on_scan_done(6, [(4, (("TVLOGO", (1, "DAZN")),))], [], 1.0, 0.1, None)  # another FIFA
        self.assertEqual(self.app.settings_ini.read("0", "TVLogo"), "")

    def test_default_resets_and_texts_win_over_moved_indices(self) -> None:
        ini = self.app.settings_ini
        ini.write("0", "LaLiga", "Scoreboard")
        ini.write("0", "DAZN", "TVLogo")
        ini.save()
        # the scoreboard back to default (index 0), the TV logo by text (its index is stale)
        self.rt.apply({"SCOREBOARD": (0, DEFAULT_LABEL), "TVLOGO": (1, "ESPN"), "KITS": (0, NOT_YET)})
        reloaded = SessionIniFile(self.app.exedir / "FSW" / "settings.ini")
        self.assertFalse(reloaded.key_exists("0", "Scoreboard"))
        self.assertEqual(reloaded.read("0", "TVLogo"), "ESPN")
        self.rt.apply({"TVLOGO": (9, "Gone")})                    # not a pack any more: ignored
        self.assertEqual(SessionIniFile(self.app.exedir / "FSW" / "settings.ini").read("0", "TVLogo"), "ESPN")

    def test_new_fifa_session_resets_the_sequence(self) -> None:
        self.rt.attached(10)
        self.rt.last_seq, self.rt.hot = 4, [(1, 2)]
        self.rt.attached(10)
        self.assertEqual(self.rt.last_seq, 4)
        self.rt.attached(11)
        self.assertEqual((self.rt.last_seq, self.rt.hot), (0, []))

    def test_scoreboard_and_tvlogo_scopes_like_the_overlay(self) -> None:
        ini = self.app.settings_ini
        ini.write("241", "UCL", "HomeTeamScoreBoard")
        ini.write("241vs73", "DAZN", "DerbyTvLogo")
        ini.write("0", "LaLiga", "Scoreboard")
        ini.write("12", "Bundesliga", "Scoreboard")
        ini.save()
        self.app.HID, self.app.AID, self.app.TOURNAME = "241", "73", "12"
        self.rt.context_changed()
        d = read_data(self.app)
        self.assertEqual((d["ROWS_SCOREBOARD"], d["PARENT_SCOREBOARD"]), ("SCOREBOARDSCOPE|SCOREBOARD", "SCOREBOARDSCOPE"))
        self.assertEqual(d["SCOREBOARDSCOPE"].split("|"), ["Equipo local (FC Barcelona)", "Derbi (FC Barcelona - 73)",
                                                            "Por defecto / Amistoso", "Torneo (12)"])
        self.assertEqual(d["SCOREBOARDSCOPE_SEL"], "3")                  # default_scope_for_scoreboard: tournament
        names = d["SCOREBOARD"].split("|")
        self.assertEqual([names[int(d[f"SCOREBOARD_SEL@{g}"])] for g in range(4)],
                         ["UCL", DEFAULT_LABEL, "LaLiga", "Bundesliga"])
        tv = d["TVLOGO"].split("|")
        self.assertEqual(tv[int(d["TVLOGO_SEL@1"])], "DAZN")
        self.assertEqual(d["TVLOGOSCOPE_SEL"], "3")
        # saved per scope: the derby's scoreboard, the home team's TV logo back to default
        self.rt.attached(5)
        record = (1, (("SCOREBOARDSCOPE", (1, "Derbi (FC Barcelona - 73)")), ("SCOREBOARD", (3, "UCL")),
                      ("TVLOGOSCOPE", (1, "Derbi (FC Barcelona - 73)")), ("TVLOGO", (0, DEFAULT_LABEL))))
        self.rt.on_scan_done(5, [record], [], 1.0, 0.1, None)
        saved = SessionIniFile(self.app.exedir / "FSW" / "settings.ini")
        self.assertEqual(saved.read("241vs73", "DerbyScoreBoard"), "UCL")
        self.assertFalse(saved.key_exists("241vs73", "DerbyTvLogo"))
        self.assertEqual(saved.read("0", "Scoreboard"), "LaLiga")       # the others as they were
        self.assertEqual(self.app.runtime_applied, 1)

    def test_scoreboard_one_scope_without_a_match(self) -> None:
        self.rt.write_data("test")                                       # opened from the hub tile: no match
        d = read_data(self.app)
        self.assertNotIn("ROWS_SCOREBOARD", d)
        self.assertEqual(d["TITLE_SCOREBOARD"], "Marcador · Por defecto / Amistoso")
        self.assertEqual(d["TITLE_TVLOGO"], "Logo TV · Por defecto / Amistoso")
        self.app.HID = "241"                                             # a friendly: home team is the default
        self.rt.write_data("test")
        d = read_data(self.app)
        self.assertEqual(d["SCOREBOARDSCOPE"].split("|"), ["Equipo local (FC Barcelona)", "Por defecto / Amistoso"])
        self.assertEqual(d["SCOREBOARDSCOPE_SEL"], "0")

    def test_scoreboard_and_tvlogo_previews(self) -> None:
        thumbs = self.app.ScoreBoard / "UCL" / "render" / "thumbnail"
        thumbs.mkdir(parents=True)
        Image.new("RGB", (600, 120), (0, 0, 90)).save(thumbs / "Preview.jpg")   # any picture there, as the F12
        self.rt._images_started = False
        self.rt.start_images()
        event = self.app._worker_queue.get(timeout=30)
        self.rt.on_images_done(*event[1:])
        dds = ingame_images.asset_image_file(self.app.exedir, "scoreboard", "UCL")
        self.assertEqual(len(dds.read_bytes()), 128 + 320 * 180 * 4)
        self.rt.write_data("test", force=True)
        d = read_data(self.app)
        self.assertEqual(d["IMG_SCOREBOARD"].split("|"), ["", ingame_images.SCOREBOARD_PLACEHOLDER_REL,
                                                          ingame_images.SCOREBOARD_PLACEHOLDER_REL,
                                                          ingame_images.asset_image_rel("scoreboard", "UCL")])
        self.assertEqual(d["IMG_TVLOGO"].split("|"), ["", ingame_images.TVLOGO_PLACEHOLDER_REL,
                                                      ingame_images.TVLOGO_PLACEHOLDER_REL])

    def test_stadium_list_per_scope(self) -> None:
        ini = self.app.settings_ini
        ini.write("241", "ESP - Camp Nou,4,0,0", "stadium")             # home team: one stadium
        ini.write("12", "Wembley,ARG - Bombonera,1,2,3", "comp")         # tournament: legacy shared-triple
        ini.save()
        self.app.HID, self.app.TOURNAME = "241", "12"
        self.rt.context_changed()
        d = read_data(self.app)
        self.assertEqual(d["ROWS_STADIUM"], "STADIUMSCOPE|STADIUM|STADIUMPOLICE|STADIUMPITCH|STADIUMNET|STADIUMGOALPOST|STADIUMGOALPOSTTEX|STADIUMNETMESH|STADIUMENTRANCECAM")
        self.assertEqual((d["PARENT_STADIUM"], d["LIST_STADIUM"]), ("STADIUMSCOPE", "STADIUM"))   # a list tab
        self.assertEqual(d["STADIUMSCOPE"].split("|"), ["Equipo local (FC Barcelona)", "Torneo (12)"])
        self.assertEqual(d["STADIUMSCOPE_SEL"], "1")                     # the app's default scope: tournament
        names = d["STADIUM"].split("|")
        self.assertEqual(names, ["ARG - Bombonera", "ARG - Monumental", "ESP - Camp Nou", "Wembley"])  # no "Por defecto"
        self.assertEqual([names[int(i)] for i in d["STADIUM_LIST@0"].split("|")], ["ESP - Camp Nou"])
        self.assertEqual([names[int(i)] for i in d["STADIUM_LIST@1"].split("|")], ["Wembley", "ARG - Bombonera"])
        self.assertEqual(d["TITLE_STADIUMADD"], "+ Agregar estadio")
        self.assertNotIn("STADIUMMATCH_SEL@1", d)                        # nothing chosen: "Selector/Al azar"
        self.app._ingame_stadium_choice = {("comp", "12"): (0, "ARG - Bombonera")}
        self.rt.write_data("test", force=True)
        self.assertEqual(read_data(self.app)["STADIUMMATCH_SEL@1"], "2")
        self.app._kickoff_generation = 1                                 # another match: that choice is gone
        self.rt.write_data("test", force=True)
        self.assertNotIn("STADIUMMATCH_SEL@1", read_data(self.app))

    def test_one_scope_has_no_scope_row(self) -> None:
        self.app.HID = "241"                                             # a friendly: only the home team
        self.rt.context_changed()
        d = read_data(self.app)
        self.assertEqual(d["ROWS_STADIUM"], "STADIUM|STADIUMPOLICE|STADIUMPITCH|STADIUMNET|STADIUMGOALPOST|STADIUMGOALPOSTTEX|STADIUMNETMESH|STADIUMENTRANCECAM")
        for key in ("PARENT_STADIUM", "STADIUMSCOPE", "TITLE_STADIUMSCOPE", "STADIUM_LIST@0"):
            self.assertNotIn(key, d)                                     # FIFA greys out a one-value row
        self.assertEqual((d["TITLE_STADIUM"], d["STADIUM_LIST"]), ("Estadio · Equipo local (FC Barcelona)", ""))
        self.rt.attached(5)
        self.rt.on_scan_done(5, [(1, (("SV1_STADIUM", (3, "Wembley")),))], [], 1.0, 0.1, None)
        self.assertEqual(SessionIniFile(self.app.exedir / "FSW" / "settings.ini").read("241", "stadium"),
                         "Wembley,4,0,0")
        self.assertEqual(self.app.runtime_applied, 1)
        self.assertEqual(read_data(self.app)["STADIUM_LIST"], "3")      # the list the menu shows next time

    def test_stadium_options_rows_and_current_values(self) -> None:
        ini = self.app.settings_ini
        ini.write("241", "ESP - Camp Nou,7,10,1", "stadium")
        ini.write("12", "Wembley,2,0,0", "comp")
        ini.write("ESP - Camp Nou", "2", "stadiumgoalpost")
        ini.save()
        self.app.HID, self.app.TOURNAME = "241", "12"
        self.rt.context_changed()
        d = read_data(self.app)
        self.assertEqual(d["STADIUMPOLICE"], "1|2|3|4|5|6|7|8|9|10")
        self.assertEqual(d["STADIUMPOLICE_DEF"], "3")                      # police 4, as the F12 wizard
        self.assertEqual(d["STADIUMPITCH"], "0|1|10")
        self.assertEqual(d["STADIUMGOALPOST"].split("|"), ["Ninguno (el del estadio)", "1", "2"])
        self.assertEqual(d["PARENT_STADIUMNET"], "STADIUM")
        names = d["STADIUM"].split("|")
        camp, wembley = names.index("ESP - Camp Nou"), names.index("Wembley")
        self.assertEqual(d[f"STADIUMPOLICE_SEL@0.{camp}"], "6")             # police 7 in the home team's entry
        self.assertEqual(d[f"STADIUMPITCH_SEL@0.{camp}"], "2")              # pitch "10"
        self.assertEqual(d[f"STADIUMPOLICE_SEL@1.{wembley}"], "1")          # police 2 in the tournament's entry
        self.assertNotIn(f"STADIUMPOLICE_SEL@1.{camp}", d)                  # not in that scope: the default
        self.assertEqual(d[f"STADIUMGOALPOST_SEL@0.{camp}"], "2")           # packs: by stadium, every scope
        self.assertEqual(d[f"STADIUMGOALPOST_SEL@1.{camp}"], "2")

    def test_stadium_options_saved_like_the_wizard(self) -> None:
        ini = self.app.settings_ini
        ini.write("241", "ESP - Camp Nou,7,10,1", "stadium")
        ini.write("ESP - Camp Nou", "1", "stadiumgoalpost")
        ini.save()
        self.app.HID = "241"
        self.rt.write_data("test")
        self.rt.attached(5)
        fields = (("SV1_STADIUM", (2, "ESP - Camp Nou")), ("SV1_STADIUMPOLICE", (8, "9")), ("SV1_STADIUMPITCH", (0, "0")),
                  ("SV1_STADIUMNET", (1, "1")), ("SV1_STADIUMGOALPOST", (0, "Ninguno (el del estadio)")),
                  ("SV1_STADIUMGOALPOSTTEX", (2, "Black")), ("SV1_STADIUMNETMESH", (0, "Ninguno (el del estadio)")),
                  ("SV1_STADIUMENTRANCECAM", (1, "Aerial")))
        self.rt.on_scan_done(5, [(1, fields)], [], 1.0, 0.1, None)
        saved = SessionIniFile(self.app.exedir / "FSW" / "settings.ini")
        self.assertEqual(saved.read("241", "stadium"), "ESP - Camp Nou,9,0,1")      # same stadium, new triple
        self.assertFalse(saved.key_exists("ESP - Camp Nou", "stadiumgoalpost"))    # "Ninguno": no override
        self.assertEqual(saved.read("ESP - Camp Nou", "stadiumgoalposttexture"), "Black")
        self.assertEqual(saved.read("ESP - Camp Nou", "stadiumentrancecam"), "Aerial")
        self.assertFalse(getattr(self.app, "_ingame_stadium_choice", None))        # saving chooses nothing
        self.assertEqual(self.app.runtime_applied, 1)
        # only a pack changes: the packs are written, the entry stays, the runtime is applied again
        fields2 = fields[:6] + (("SV1_STADIUMENTRANCECAM", (2, "Classic")),)
        self.rt.on_scan_done(5, [(2, fields2)], [], 1.0, 0.1, None)
        saved = SessionIniFile(self.app.exedir / "FSW" / "settings.ini")
        self.assertEqual(saved.read("ESP - Camp Nou", "stadiumentrancecam"), "Classic")
        self.assertEqual(saved.read("241", "stadium"), "ESP - Camp Nou,9,0,1")
        self.assertEqual(self.app.runtime_applied, 2)

    def test_option_pictures_become_dds(self) -> None:
        self.app.HID = "241"
        self.rt._images_started = False
        self.rt.start_images()
        event = self.app._worker_queue.get(timeout=20)
        self.assertEqual(event[0], "ingame_menu_images")
        self.rt.on_images_done(*event[1:])
        net = ingame_images.asset_image_file(self.app.exedir, "net", "10")
        self.assertEqual(len(net.read_bytes()), 128 + 320 * 180 * 4)
        self.rt.write_data("test", force=True)
        d = read_data(self.app)
        self.assertEqual(d["IMG_STADIUMNET"].split("|")[2], ingame_images.asset_image_rel("net", "10"))
        # every option has its picture where the F12 wizard has one
        self.assertEqual(d["IMG_STADIUMPOLICE"].split("|")[3], ingame_images.asset_image_rel("police", "4"))
        self.assertEqual(d["IMG_STADIUMGOALPOST"].split("|"), ["", "", ingame_images.asset_image_rel("goalpost", "2")])
        self.assertEqual(d["IMG_STADIUMENTRANCECAM"].split("|")[1], ingame_images.asset_image_rel("entrancecam", "Aerial"))
        self.assertEqual(d["IMG_STADIUMNETMESH"].split("|")[1], ingame_images.asset_image_rel("netmesh", "Hex 1"))
        tex = d["IMG_STADIUMGOALPOSTTEX"].split("|")   # None, Black (no .rx3), Grey (rendered)
        self.assertEqual(tex, ["", "", ingame_images.asset_image_rel("goalposttex", "Grey")])

    def tmp_placeholder(self) -> str:
        path = Path(self._tmp.name) / "stadium-placeholder.png"
        Image.new("RGB", (400, 225), (40, 40, 40)).save(path)
        return str(path)

    def test_movie_scopes_values_and_videos(self) -> None:
        ini = self.app.settings_ini
        ini.write("241vs73", "Copa", "DerbyMatch")
        ini.write("12", "UCL", "movies")
        ini.save()
        self.app.HID, self.app.AID, self.app.TOURNAME = "241", "73", "12"
        movies = [("UCL", self.app.Movies / "UCL" / "bootflowoutro.vp8")]
        self.assertEqual(ingame_images.ensure_movie_videos(self.app.exedir, movies), (1, 1))
        linked = ingame_images.movie_video_file(self.app.exedir, "UCL")
        self.assertEqual(linked.read_bytes(), b"vp8 movie bytes")
        self.assertEqual(ingame_images.ensure_movie_videos(self.app.exedir, movies), (0, 1))   # kept
        self.rt.context_changed()
        d = read_data(self.app)
        self.assertEqual(d["ROWS_MOVIES"], "MOVIESCOPE|MOVIES")
        self.assertEqual(d["MOVIESCOPE"].split("|"),
                         ["Equipo local (FC Barcelona)", "Derbi (FC Barcelona - 73)", "Torneo (12)"])
        self.assertEqual(d["MOVIESCOPE_SEL"], "2")                  # default_scope_for_movie: the tournament
        names = d["MOVIES"].split("|")
        self.assertEqual(names, [DEFAULT_LABEL, "Copa", "LaLiga", "UCL"])
        self.assertEqual([names[int(d[f"MOVIES_SEL@{g}"])] for g in range(3)], [DEFAULT_LABEL, "Copa", "UCL"])
        self.assertEqual(d["VID_MOVIES"].split("|"), ["", "", "", ingame_images.movie_video_play_path("UCL")])
        self.assertTrue(ingame_images.movie_video_play_path("UCL").startswith("data\\ui\\cgfs16\\mov\\"))

    def test_movie_saved_per_scope(self) -> None:
        self.app.HID, self.app.AID = "241", "73"
        self.rt.write_data("test")
        self.rt.attached(5)
        record = (1, (("MOVIESCOPE", (1, "Derbi (FC Barcelona - 73)")), ("MOVIES", (2, "LaLiga"))))
        self.rt.on_scan_done(5, [record], [], 1.0, 0.1, None)
        saved = SessionIniFile(self.app.exedir / "FSW" / "settings.ini")
        self.assertEqual(saved.read("241vs73", "DerbyMatch"), "LaLiga")
        self.assertEqual(self.app.runtime_applied, 1)
        self.rt.on_scan_done(5, [(2, (("MOVIESCOPE", (1, "Derbi (FC Barcelona - 73)")),
                                      ("MOVIES", (0, DEFAULT_LABEL))))], [], 1.0, 0.1, None)
        self.assertFalse(SessionIniFile(self.app.exedir / "FSW" / "settings.ini").key_exists("241vs73", "DerbyMatch"))
        self.assertEqual(self.app.runtime_applied, 2)

    def test_install_changed_writes_the_data_again(self) -> None:
        started = []
        self.rt.start_images = lambda: started.append(self.rt._images_started)
        self.rt.write_data("test")
        target = self.app.exedir / ingame_menu_runtime.DATA_MOVIE
        target.unlink()
        self.rt.write_data("test")
        self.assertFalse(target.exists())          # same data: not written again
        self.rt.install_changed()                  # Setup installed / updated the menu
        self.assertTrue(target.exists())
        self.assertEqual(started[-1], False)       # the previews are made again too

    def test_one_movie_scope_has_no_scope_row(self) -> None:
        self.app.HID = "241"
        self.rt.context_changed()
        d = read_data(self.app)
        self.assertNotIn("ROWS_MOVIES", d)
        self.assertEqual(d["TITLE_MOVIES"], "Vídeos · Equipo local (FC Barcelona)")
        self.rt.attached(5)
        self.rt.on_scan_done(5, [(1, (("MOVIES", (3, "UCL")),))], [], 1.0, 0.1, None)
        self.assertEqual(SessionIniFile(self.app.exedir / "FSW" / "settings.ini").read("241", "TeamMovies"), "UCL")

    def test_stadium_previews_become_dds_and_go_in_the_data(self) -> None:
        self.app.HID = "241"
        made, available = ingame_images.ensure_stadium_images(
            self.app.exedir, self.rt.stadium_names(), self.app._resolve_stadium_preview_path)
        self.assertEqual((made, available), (1, 1))
        dds = ingame_images.stadium_image_file(self.app.exedir, "ESP - Camp Nou")
        self.assertEqual(dds.read_bytes()[:4], b"DDS ")
        self.assertEqual(len(dds.read_bytes()), 128 + 320 * 180 * 4)
        self.rt.write_data("test", force=True)
        images = read_data(self.app)["IMG_STADIUM"].split("|")
        self.assertEqual(images[2], ingame_images.stadium_image_rel("ESP - Camp Nou"))
        self.assertEqual(images[:2], ["", ""])
        # the placeholder (made by the images worker): stadiums without a preview get it
        ingame_images.ensure_placeholder(self.app.exedir, Path(self.tmp_placeholder()))
        self.rt.write_data("test", force=True)
        images = read_data(self.app)["IMG_STADIUM"].split("|")
        self.assertEqual(images[0], ingame_images.PLACEHOLDER_REL)
        self.assertEqual(images[2], ingame_images.stadium_image_rel("ESP - Camp Nou"))
        self.assertEqual(ingame_images.ensure_stadium_images(
            self.app.exedir, self.rt.stadium_names(), self.app._resolve_stadium_preview_path), (0, 1))  # cached

    def test_saves_append_or_update_in_place_and_the_match_choice(self) -> None:
        ini = self.app.settings_ini
        ini.write("241", "ESP - Camp Nou,1,2,3", "stadium")
        ini.save()
        self.app.HID, self.app._kickoff_generation = "241", 4
        self.rt.write_data("test")
        self.rt.attached(5)
        record = (1, (("SV1_STADIUM", (1, "ARG - Monumental")),                 # + Agregar: appended
                      ("SV2_STADIUM", (2, "ESP - Camp Nou")), ("SV2_STADIUMPOLICE", (6, "7")),   # edited: in place
                      ("M_STADIUMMATCH", (2, "ARG - Monumental"))))
        self.rt.on_scan_done(5, [record], [], 1.0, 0.1, None)
        value = SessionIniFile(self.app.exedir / "FSW" / "settings.ini").read("241", "stadium")
        self.assertEqual(value, "ESP - Camp Nou,7,2,3,ARG - Monumental,4,0,0")
        self.assertEqual(self.app._ingame_stadium_choice, {("stadium", "241"): (4, "ARG - Monumental")})
        self.assertEqual(self.app.runtime_applied, 1)
        d = read_data(self.app)
        self.assertEqual((d["STADIUM_LIST"], d["STADIUMMATCH_SEL"]), ("2|1", "2"))
        # only the match row changes: still applied again (another stadium)
        self.rt.on_scan_done(5, [(2, (("M_STADIUMMATCH", (0, "Selector/Al azar")),))], [], 1.0, 0.1, None)
        self.assertEqual(self.app._ingame_stadium_choice, {})
        self.assertEqual(self.app.runtime_applied, 2)
        self.rt.on_scan_done(5, [(3, (("M_STADIUMMATCH", (1, "Wembley")),))], [], 1.0, 0.1, None)   # not assigned
        self.assertEqual(self.app._ingame_stadium_choice, {})

    def test_quitar_removes_the_entry_and_its_match_choice(self) -> None:
        ini = self.app.settings_ini
        ini.write("241", "ESP - Camp Nou,1,2,3,Wembley,4,0,0", "stadium")
        ini.write("ESP - Camp Nou", "2", "stadiumgoalpost")
        ini.save()
        self.app.HID = "241"
        self.app._ingame_stadium_choice = {("stadium", "241"): (0, "ESP - Camp Nou")}
        self.rt.write_data("test")
        self.rt.attached(5)
        record = (1, (("SV1_STADIUM", (2, "ESP - Camp Nou")), ("SV1_STADIUMDEL", (0, ""))))
        self.rt.on_scan_done(5, [record], [], 1.0, 0.1, None)
        saved = SessionIniFile(self.app.exedir / "FSW" / "settings.ini")
        self.assertEqual(saved.read("241", "stadium"), "Wembley,4,0,0")
        self.assertEqual(saved.read("ESP - Camp Nou", "stadiumgoalpost"), "2")      # its packs stay
        self.assertEqual(self.app._ingame_stadium_choice, {})
        self.assertEqual(self.app.runtime_applied, 1)
        self.rt.on_scan_done(5, [(2, (("SV1_STADIUM", (3, "Wembley")), ("SV1_STADIUMDEL", (0, ""))))],
                             [], 1.0, 0.1, None)
        self.assertFalse(SessionIniFile(self.app.exedir / "FSW" / "settings.ini").key_exists("241", "stadium"))
        self.assertEqual(read_data(self.app)["STADIUM_LIST"], "")
        self.assertEqual(self.app.runtime_applied, 2)

    def test_match_choice_per_scope_and_stadium_runtime_uses_it(self) -> None:
        from server16_py.stadium_runtime import StadiumRuntime
        ini = self.app.settings_ini
        ini.write("12", "Wembley,2,0,0,ARG - Bombonera,1,0,0", "comp")
        ini.save()
        self.app.HID, self.app.TOURNAME = "241", "12"
        self.rt.write_data("test")
        self.rt.attached(5)
        self.rt.on_scan_done(5, [(1, (("M1_STADIUMMATCH", (2, "ARG - Bombonera")),))], [], 1.0, 0.1, None)
        self.assertEqual(self.app._ingame_stadium_choice, {("comp", "12"): (0, "ARG - Bombonera")})
        runtime = StadiumRuntime(self.app)
        self.assertEqual(runtime._ingame_menu_choice("comp", "12", ["Wembley", "ARG - Bombonera"]), "ARG - Bombonera")
        self.assertIsNone(runtime._ingame_menu_choice("stadium", "241", ["Wembley"]))      # another assignment
        self.assertIsNone(runtime._ingame_menu_choice("comp", "12", ["Wembley"]))          # no longer one of them
        self.app._kickoff_generation = 1
        self.assertIsNone(runtime._ingame_menu_choice("comp", "12", ["Wembley", "ARG - Bombonera"]))  # next match

    def test_stadium_of_another_match_is_ignored(self) -> None:
        self.app.HID = "241"
        self.rt.write_data("test")
        self.app.HID = "73"   # a new match meanwhile
        self.assertFalse(self.rt.apply({"SV1_STADIUMSCOPE": (0, "Equipo local (FC Barcelona)"),
                                        "SV1_STADIUM": (2, "ESP - Camp Nou")}))
        self.assertFalse(self.app.settings_ini.key_exists("241", "stadium"))
        self.assertEqual(self.app.runtime_applied, 0)

    def test_scan_error_is_logged(self) -> None:
        self.rt.busy = True
        self.rt.on_scan_done(1, [], [], 0.0, 0.0, "OpenProcess failed (5)")
        self.assertFalse(self.rt.busy)
        self.assertIn("scan failed", self.app.logs[-1])


if __name__ == "__main__":
    unittest.main()


class InGameMenuLanguageTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.app = FakeApp(Path(self._tmp.name))
        self.rt = InGameMenuRuntime(self.app)
        self.rt._images_started = True

    def test_every_language_has_every_text_with_the_same_fields(self) -> None:
        import string
        from server16_py import ingame_menu_texts as texts
        self.assertEqual(set(texts.TEXTS), set(texts.LANGUAGES))
        fields = lambda s: {f for _l, f, _s, _c in string.Formatter().parse(s) if f}  # noqa: E731
        for lang, table in texts.TEXTS.items():
            self.assertEqual(set(table), set(texts.TEXTS["eng"]), lang)
            for key, value in table.items():
                self.assertEqual(fields(value), fields(texts.TEXTS["eng"][key]), (lang, key))
                self.assertFalse(any(c in value for c in "|=\n"), (lang, key))   # the data text cannot carry them

    def test_language_codes(self) -> None:
        from server16_py import ingame_menu_texts as texts
        for code, lang in (("spa,es", "spa"), ("spa,mx", "spa"), ("es_ES", "spa"), ("en-US", "eng"),
                           ("por,br", "por"), ("cze", "cze"), ("nb_NO", "nor"), ("xx", None), ("", None)):
            self.assertEqual(texts.normalize(code), lang, code)
        self.assertEqual(texts.from_locale_ini(self.app.exedir), "spa")
        self.assertEqual(texts.detect(Path(self._tmp.name) / "nowhere", "pt"), texts.from_registry() or "por")

    def test_the_data_carries_keys_the_menu_puts_in_fifas_language(self) -> None:
        self.app.HID, self.app.TOURNAME = "241", "12"
        self.rt.write_data("test")
        raw = read_data(self.app, None)
        self.assertEqual(raw["STADIUMSCOPE"].split("|")[0], "{{home~team:FC Barcelona}}")
        self.assertEqual(raw["LANG"], "spa")                             # the app's guess (locale.ini), informative
        d = read_data(self.app, "eng")                                    # FIFA in English
        self.assertEqual(d["SCOREBOARD"].split("|")[0], "Default (FIFA 16)")
        self.assertEqual(d["STADIUMSCOPE"].split("|"), ["Home team (FC Barcelona)", "Tournament (12)"])
        self.assertEqual((d["TAB_STADIUM"], d["TITLE_STADIUMADD"], d["STADIUMMATCH_FIRST"]),
                         ("Stadium", "+ Add stadium", "Picker/Random"))
        self.assertTrue(d["INFO"].startswith("App data (CG Server 16, 20"))
        self.assertEqual(read_data(self.app, "ger")["TAB_SCOREBOARD"], "Anzeigetafel")

    def test_a_save_is_read_in_the_language_of_its_record(self) -> None:
        self.app.HID, self.app.TOURNAME = "241", "12"
        self.rt.write_data("test")
        self.rt.attached(5)
        record = (1, (("LANG", (0, "eng")), ("SCOREBOARDSCOPE", (1, "Default / Friendly")),
                      ("SCOREBOARD", (3, "UCL")), ("TVLOGOSCOPE", (1, "Default / Friendly")),
                      ("TVLOGO", (0, "Default (FIFA 16)"))))
        self.rt.on_scan_done(5, [record], [], 1.0, 0.1, None)
        saved = SessionIniFile(self.app.exedir / "FSW" / "settings.ini")
        self.assertEqual(saved.read("0", "Scoreboard"), "UCL")
        self.assertEqual(self.rt.record_lang, "eng")
        self.assertTrue(any("FIFA is in 'eng'" in line for line in self.app.logs))
        # FIFA switched to German in the game: the next save is read in German
        self.rt.on_scan_done(5, [(2, (("LANG", (0, "ger")), ("SCOREBOARDSCOPE", (1, "Standard / Freundschaftsspiel")),
                                      ("SCOREBOARD", (2, "LaLiga"))))], [], 1.0, 0.1, None)
        self.assertEqual(SessionIniFile(self.app.exedir / "FSW" / "settings.ini").read("0", "Scoreboard"), "LaLiga")
        # a scope label in another language than the record's is not this scope: ignored
        self.rt.on_scan_done(5, [(3, (("LANG", (0, "ger")), ("SCOREBOARDSCOPE", (1, "Default / Friendly")),
                                      ("SCOREBOARD", (1, "Bundesliga"))))], [], 1.0, 0.1, None)
        self.assertEqual(SessionIniFile(self.app.exedir / "FSW" / "settings.ini").read("0", "Scoreboard"), "LaLiga")

    def test_rna_ini_language(self) -> None:
        from server16_py import ingame_menu_texts as texts
        (self.app.exedir / "rna.ini").write_text("[LOCALE]\nUSE_LANGUAGE_SELECT = 1\nDEFAULT_LANGUAGE = it,IT\n",
                                                encoding="latin-1")
        self.assertEqual(texts.from_locale_ini(self.app.exedir), "ita")   # RNA's first
        self.assertEqual(self.rt.language(), "ita")
