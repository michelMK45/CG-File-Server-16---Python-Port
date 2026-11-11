"""The CGFS16 menu inside FIFA 16's own interface (cgfs-ingame project): the app's side of the link.

The menu (Customise > Edit Teams > CGFS16, and R3 on the pre-match KickOffHub) is a FIFA 16 screen of ours,
a clone of FIFA's Game Settings (tabs, rows with < value >, an image). It talks to the app in two ways,
both proven in-game (cgfs-ingame docs/fase3-conexion.md and docs/menu-pestanas.md):

  app -> menu   data/ui/cgfs16/data.big: a one-frame Apt movie the menu loads with loadMovie every time it
                opens. Its data is one text of "KEY=value" lines (row values, the current selection, ACK,
                and optionally the tab/row structure and images), written into a fixed template
                (resources/ingame/data_template.big) by ingame_datafile.render. FIFA re-reads it on every
                visit, so it can be rewritten while FIFA runs.
  menu -> app   when the menu is left with BACK after a change, it leaves
                "CGFS16OUT|v1|<seq>|NAME=<index>:<text>|...|END" in ActionScript memory; when the page
                'game/screens/cgfs16/CGFS16Menu' is left, a worker thread scans FIFA's memory read-only for
                the newest record (ingame_recordscan, ~3.5 s for ~3.7 GB the first time, then the regions
                where records were seen first).

What the rows mean here:
  Marcador / Logo TV   the Default / Friendly assignments, the [Scoreboard]/[TVLogo] key "0" of
                       FSW/settings.ini (the F12 menu's "Default / Friendly" scope); index 0 = no assignment.
  Estadio              with a match context (the menu opened from the KickOffHub) two dependent rows, as the
                       F12 overlay's stadium wizard: "Asignar a" (the scopes this match has: Home Team ->
                       [stadium] <HID>, Round -> [comp] <ROUND>, Tournament -> [comp] <TOUR>) and Estadio (every
                       stadium of StadiumGBD with its preview from ingame_images; per scope the one in use is
                       selected). The pick is appended to that key's stadiums (each "<stadium>,<police>,<pitch>,
                       <net>") and pre-chosen for this match; "Por defecto" removes the key. Below it, the
                       wizard's other steps (STADIUM_OPTIONS): police, pitch pattern, net colour (the entry's
                       triple, per scope) and goalpost model/texture, net mesh, entrance camera (their own
                       sections keyed by the stadium), each showing what that stadium has now. With one scope
                       the "Asignar a" row is left out. Without a context: one value telling to open it from
                       the match hub.
  Vídeos               as the F12's Movies tab: "Asignar a" (Home Team / Derby / Round / Tournament, the ones
                       this match has; left out with one) and the MoviesGBD pack, each previewed by its
                       bootflowoutro.vp8 played muted by FIFA's MoviePlayer in the menu (ingame_images links it
                       under data/ui/cgfs16/mov). Saved to [TeamMovies]/[DerbyMatch]/[movies] as assign_movie.
  Equipaciones         not wired yet: one "Próximamente" value, saves ignored.
After a save that changed settings.ini the runtime is applied again (apply_all_runtime): coming back to the
KickOffHub is a "revisit" that would not reload anything (docs/stadium-slots.md).

ACK=<seq>: the last save the app processed. Until the app has seen a save, the menu keeps its own choice
over the app's selection (a quick re-entry used to show the previous one, prueba 6).
Does nothing unless the menu is installed in the game (data/ui/game/screens/cgfs16/cgfs16menu.big).
"""
from __future__ import annotations

import datetime
import threading
from pathlib import Path
from typing import TYPE_CHECKING

from . import ingame_datafile, ingame_images, ingame_recordscan
from .file_tools import _bundled_resource_path, discover_stadium_names

if TYPE_CHECKING:
    from .app import Server16App

MENU_PAGE = "game/screens/cgfs16/CGFS16Menu"
MENU_MOVIE = Path("data/ui/game/screens/cgfs16/cgfs16menu.big")
DATA_MOVIE = Path("data/ui/cgfs16/data.big")
TEMPLATE = "ingame/data_template.big"
DEFAULT_LABEL = "Por defecto (FIFA 16)"
NOT_YET = "Próximamente"
NO_MATCH = "Ábrelo desde el matchHub (R3)"
# menu row -> (settings.ini section, attribute of the app with the packs' folder); key "0" = Default/Friendly
DEFAULT_ROWS = {
    "SCOREBOARD": ("Scoreboard", "ScoreBoard"),
    "TVLOGO": ("TVLogo", "TVLogo"),
}
OTHER_ROWS = ("KITS",)
DEFAULT_KEY = "0"
STADIUM_SECTION, COMP_SECTION = "stadium", "comp"
# Vídeos, as the F12 overlay's Movies tab (assignment_runtime.assign_movie): Home Team -> [TeamMovies] <HID>,
# Derby -> [DerbyMatch] <HID>vs<AID>, Round -> [movies] <ROUND>, Tournament -> [movies] <TOUR>; the value is a
# MoviesGBD pack. Its preview is the pack's bootflowoutro.vp8 (file_tools.resolve_movie_preview_path), played muted
# by FIFA's own MoviePlayer in the menu from a hard link (else a copy) under data/ui/cgfs16/mov.
MOVIE_SCOPE_ROW, MOVIE_ROW = "MOVIESCOPE", "MOVIES"
TEAM_MOVIES, DERBY_MOVIES, COMP_MOVIES = "TeamMovies", "DerbyMatch", "movies"
SCOPE_ROW, STADIUM_ROW = "STADIUMSCOPE", "STADIUM"
OVERLAY_DEFAULTS = ("4", "0", "0")   # police, pitch, net of a new pick when the F12 wizard skips them
MAX_STADIUMS = 64                    # d3d_injector._MAX_STADIUM_PICKER_ITEMS (the in-game picker's cap)
NONE_LABEL = "Ninguno (el del estadio)"   # a pack row's "None": no override, the stadium keeps its own
# the stadium's options, one row each below Estadio, as the F12 wizard's steps after the stadium
# (app_overlay._STADIUM_WIZARD_PHASES): (row, title, description, kind, where)
#   kind "triple": the n-th of police/pitch/net inside the stadium's entry of the scope's value; where = the
#                  folders whose files are the list (the first that exists, as the overlay), None = police 1..10
#   kind "pack":   [<section>] <stadium name> = <pack folder>; where = (FSW subfolders, section)
STADIUM_OPTIONS = [
    ("STADIUMPOLICE", "Policía", "Nivel de policía del estadio (1-10).", "triple", None),
    ("STADIUMPITCH", "Patrón del césped", "Dibujo del corte del césped (FSW/PitchMowPattern).", "triple",
     (("FSW", "Images", "PitchMowPattern"), ("FSW", "PitchMowPattern"))),
    ("STADIUMNET", "Color de la red", "Color de la red de las porterías (FSW/Nets).", "triple",
     (("FSW", "Images", "Nets"), ("FSW", "Nets"))),
    ("STADIUMGOALPOST", "Portería: modelo", "Modelo de portería (FSW/Goalpost/GoalpostModel).", "pack",
     (("FSW", "Goalpost", "GoalpostModel"), "stadiumgoalpost")),
    ("STADIUMGOALPOSTTEX", "Portería: textura", "Textura de la portería (FSW/Goalpost/GoalpostColor).", "pack",
     (("FSW", "Goalpost", "GoalpostColor"), "stadiumgoalposttexture")),
    ("STADIUMNETMESH", "Malla de la red", "Malla de la red (FSW/NetMesh).", "pack",
     (("FSW", "NetMesh"), "stadiumnetmesh")),
    ("STADIUMENTRANCECAM", "Cámara de entrada", "Cámara de la salida de los equipos (FSW/Camera/EntranceScene).",
     "pack", (("FSW", "Camera", "EntranceScene"), "stadiumentrancecam")),
]
# every option row has a picture per value, the one the F12 wizard previews (_update_d3d_preview_image):
# police/pitch/net FSW/Images/<folder>/<value>.png (else FSW/<folder>/), goalpost model and entrance camera the
# pack's preview.<ext>, net mesh its preview or pattern image, goalpost texture rendered from the pack's .rx3
# (StadiumRuntime.render_goalpost_texture_preview, the 32-bit bridge, seconds each: in the worker thread)
IMAGE_KINDS = {"STADIUMPOLICE": "police", "STADIUMPITCH": "pitch", "STADIUMNET": "net",
               "STADIUMGOALPOST": "goalpost", "STADIUMGOALPOSTTEX": "goalposttex", "STADIUMNETMESH": "netmesh",
               "STADIUMENTRANCECAM": "entrancecam"}
PICTURE_FOLDERS = {"STADIUMPOLICE": "Police", "STADIUMPITCH": "PitchMowPattern", "STADIUMNET": "Nets"}
BAD_CHARS = "|=\n"


class InGameMenuRuntime:
    def __init__(self, app: "Server16App") -> None:
        self.app = app
        self.last_seq = 0        # the newest menu save processed in this FIFA session
        self.hot: list[tuple[int, int]] = []  # memory regions where save records were found
        self.busy = False        # a scan is running in a worker thread
        self._pid: int | None = None
        self._written: str | None = None  # the last data text written (without its STAMP line)
        self._template: bytes | None = None
        self._stadium_scopes: list[tuple[str, str, str]] = []   # the Estadio scopes the data was written with
        self._movie_scopes: list[tuple[str, str, str]] = []     # the Vídeos scopes
        self._images_started = False
        self.images_busy = False   # the previews are being made in a worker thread

    # --- state -------------------------------------------------------------------------------
    def installed(self) -> bool:
        exedir = getattr(self.app, "exedir", None)
        return bool(exedir) and (Path(exedir) / MENU_MOVIE).exists()

    def attached(self, pid: int | None) -> None:
        """FIFA (re)attached or gone: a new FIFA session counts the menu's saves from 1 again."""
        if pid != self._pid:
            self._pid = pid
            self.last_seq = 0
            self.hot = []
            self._written = None

    def rows(self) -> tuple[dict[str, list[str]], dict[str, int]]:
        """(values per row, selected index per row) of the plain rows, from the app's packs and settings.ini."""
        values: dict[str, list[str]] = {}
        selected: dict[str, int] = {}
        for row, (section, folder_attr) in DEFAULT_ROWS.items():
            names = [DEFAULT_LABEL] + _pack_names(getattr(self.app, folder_attr, None))
            values[row] = names
            current = self.app.settings_ini.read(DEFAULT_KEY, section).strip()
            selected[row] = names.index(current) if current in names[1:] else 0
        for row in OTHER_ROWS:
            values[row] = [NOT_YET]
            selected[row] = 0
        return values, selected

    # --- stadiums ------------------------------------------------------------------------------
    def stadium_names(self) -> list[str]:
        root = getattr(self.app, "targetpath", None)
        if not root:
            return []
        try:
            names = discover_stadium_names(root)
        except Exception:  # noqa: BLE001
            return []
        return [n for n in names if n != "None" and not any(c in n for c in BAD_CHARS)]

    def stadium_scopes(self) -> tuple[list[tuple[str, str, str]], int]:
        """([(label, settings.ini section, key)] the F12 overlay offers for stadiums in this match context
        (Home Team -> [stadium] <HID>, Round -> [comp] <ROUND>, Tournament -> [comp] <TOUR>), the index of
        the app's default scope (assignment_runtime.default_scope_for_stadium: round, else tournament, else team)."""
        app = self.app
        scopes: list[tuple[str, str, str]] = []
        default = 0
        hid = _context(app, "HID")
        if hid:
            try:
                name = app._resolve_team_name(hid) or ""
            except Exception:  # noqa: BLE001
                name = ""
            scopes.append((_clean(f"Equipo local ({name or hid})"), STADIUM_SECTION, hid))
        round_id = _context(app, "TOURROUNDID")
        if round_id:
            scopes.append((f"Ronda ({round_id})", COMP_SECTION, round_id))
            default = len(scopes) - 1
        tour = _context(app, "TOURNAME")
        if tour:
            scopes.append((f"Torneo ({tour})", COMP_SECTION, tour))
            if not round_id:
                default = len(scopes) - 1
        return scopes, default

    def stadium_entries(self, section: str, key: str) -> list[tuple[str, str, str, str]]:
        """(name, police, pitch, net) per stadium assigned to this key (both value formats, as the runtime)."""
        from .stadium_runtime import StadiumRuntime
        try:
            return StadiumRuntime._parse_stadium_entries(self.app.settings_ini.read(key, section))
        except Exception:  # noqa: BLE001
            return []

    def stadium_lines(self) -> tuple[list[str], dict[str, list[str]], dict[str, int]]:
        """Extra data lines, values and selection for the Estadio tab (see the module docstring)."""
        scopes, default = self.stadium_scopes()
        self._stadium_scopes = scopes
        if not scopes:
            return [f"DESC_{STADIUM_ROW}=Elige el estadio desde el matchHub, antes del partido (R3)."], \
                   {STADIUM_ROW: [NO_MATCH]}, {STADIUM_ROW: 0}
        names = [DEFAULT_LABEL] + self.stadium_names()
        exedir = Path(self.app.exedir)
        # a stadium without its own preview gets the app's placeholder, as the F12 shows
        # (_resolve_stadium_preview_path_or_default); "Por defecto" and anything else unknown: the menu's logo
        placeholder = ingame_images.PLACEHOLDER_REL if (exedir / "data" / "ui" / ingame_images.PLACEHOLDER_REL).exists() else ""
        images = [""] + [ingame_images.stadium_image_rel(n) if ingame_images.stadium_image_file(exedir, n).exists()
                         else placeholder for n in names[1:]]
        lines = [f"ROWS_{STADIUM_ROW}=" + "|".join([SCOPE_ROW, STADIUM_ROW] + [row for row, *_ in STADIUM_OPTIONS]),
                 f"PARENT_{STADIUM_ROW}={SCOPE_ROW}",
                 f"TITLE_{SCOPE_ROW}=Asignar a", f"TITLE_{STADIUM_ROW}=Estadio",
                 f"DESC_{SCOPE_ROW}=A quién se asigna el estadio, como en el overlay (F12): equipo local, ronda o torneo.",
                 f"DESC_{STADIUM_ROW}=El elegido se añade a los de esa asignación y se usa en este partido."
                 f" Por defecto: quita la asignación (estadio de FIFA)."]
        if any(images):
            lines.append(f"IMG_{STADIUM_ROW}=" + "|".join(images))
        selections = []
        for g, (_label, section, key) in enumerate(scopes):
            entries = self.stadium_entries(section, key)
            current = entries[-1][0] if entries else ""   # the latest added (the F12 appends)
            sel = names.index(current) if current in names[1:] else 0
            selections.append(sel)
            lines.append(f"{STADIUM_ROW}_SEL@{g}={sel}")
        values_out: dict = {}
        lines += self.option_lines(scopes, names, selections, values_out)
        if len(scopes) == 1:
            # one scope (a friendly: only the home team): no "Asignar a" row -- FIFA greys out a row with a
            # single value (prueba 9b) -- its scope goes in the stadium row's title instead; the options'
            # selections are then keyed by the stadium alone ("<g>" instead of "<scope>.<g>")
            lines = [line for line in lines if not line.startswith((f"ROWS_{STADIUM_ROW}=", f"PARENT_{STADIUM_ROW}=",
                                                                    f"TITLE_{SCOPE_ROW}=", f"DESC_{SCOPE_ROW}=",
                                                                    f"TITLE_{STADIUM_ROW}=", f"{STADIUM_ROW}_SEL@"))]
            lines = [line.replace("_SEL@0.", "_SEL@", 1) if "_SEL@0." in line else line for line in lines]
            lines.append(f"TITLE_{STADIUM_ROW}=Estadio · {scopes[0][0]}")
            lines.append(f"ROWS_{STADIUM_ROW}=" + "|".join([STADIUM_ROW] + [row for row, *_ in STADIUM_OPTIONS]))
            return lines, dict(values_out, **{STADIUM_ROW: names}), {STADIUM_ROW: selections[0]}
        return lines, dict(values_out, **{SCOPE_ROW: [label for label, _s, _k in scopes], STADIUM_ROW: names}), \
            {SCOPE_ROW: default, STADIUM_ROW: selections[default]}

    def option_values(self, row: str) -> list[str]:
        """The list of one of the stadium's option rows (STADIUM_OPTIONS), as the F12 wizard offers it."""
        _row, _title, _desc, kind, where = next(o for o in STADIUM_OPTIONS if o[0] == row)
        exedir = Path(self.app.exedir)
        if kind == "triple" and where is None:
            return [str(i) for i in range(1, 11)]
        if kind == "triple":
            for parts in where:
                folder = exedir.joinpath(*parts)
                if folder.is_dir():
                    stems = [f.stem for f in sorted(folder.iterdir()) if f.is_file()]
                    return [t for t in stems if not any(c in t for c in BAD_CHARS)] or ["0"]
            return ["0"]
        folder = exedir.joinpath(*where[0])
        packs = sorted(d.name for d in folder.iterdir() if d.is_dir()) if folder.is_dir() else []
        return [NONE_LABEL] + [n for n in packs if not any(c in n for c in BAD_CHARS)]

    def option_picture(self, row: str, value: str):
        """The picture the F12 wizard previews for this option value (see IMAGE_KINDS), or None."""
        from .file_tools import resolve_goalpost_model_preview_path
        exedir = Path(self.app.exedir)
        if row in PICTURE_FOLDERS:
            for parts in (("FSW", "Images", PICTURE_FOLDERS[row]), ("FSW", PICTURE_FOLDERS[row])):
                candidate = exedir.joinpath(*parts) / f"{value}.png"
                if candidate.is_file():
                    return candidate
            return None
        option = next(o for o in STADIUM_OPTIONS if o[0] == row)
        folder = exedir.joinpath(*option[4][0])
        try:
            if row == "STADIUMNETMESH":
                from .net_mesh import resolve_net_mesh_preview_path
                return resolve_net_mesh_preview_path(folder, value)
            if row in ("STADIUMGOALPOST", "STADIUMENTRANCECAM"):
                return resolve_goalpost_model_preview_path(folder, value)
        except Exception:  # noqa: BLE001
            return None
        return None

    def _texture_renderer(self):
        """A function pack name -> rendered PNG of a GoalpostColor pack (blocking; for the worker), or None
        without the app's stadium runtime."""
        runtime = getattr(self.app, "stadium_runtime", None)
        if runtime is None or not hasattr(runtime, "render_goalpost_texture_preview"):
            return None
        from .file_tools import resolve_goalpost_texture_rx3_path
        folder = Path(self.app.exedir) / "FSW" / "Goalpost" / "GoalpostColor"

        def render(name: str):
            rx3 = resolve_goalpost_texture_rx3_path(folder, name)
            if rx3 is None:
                return None
            try:
                return runtime.render_goalpost_texture_preview(rx3, cache_key=name, reuse_cached=True)
            except Exception:  # noqa: BLE001 - no picture for that pack
                return None
        return render

    def option_images(self, row: str, values: list[str]) -> list[str]:
        kind = IMAGE_KINDS.get(row)
        if not kind:
            return []
        exedir = Path(self.app.exedir)
        return [ingame_images.asset_image_rel(kind, v) if ingame_images.asset_image_file(exedir, kind, v).exists()
                else "" for v in values]

    def option_lines(self, scopes, names, selections, values_out: dict) -> list[str]:
        """Data lines of the stadium's option rows: their lists, titles, defaults and, per path
        "<scope>.<stadium>", what is set now -- police/pitch/net from that stadium's entry in the scope's value,
        the packs from their own sections (same for every scope). Fills values_out with the lists."""
        lines: list[str] = []
        ini = self.app.settings_ini
        entries_by_scope = [{e[0]: e for e in self.stadium_entries(section, key)} for _l, section, key in scopes]
        for n, (row, title, desc, kind, where) in enumerate(STADIUM_OPTIONS):
            values = self.option_values(row)
            values_out[row] = values
            lines += [f"PARENT_{row}={STADIUM_ROW}", f"TITLE_{row}={title}", f"DESC_{row}={desc}"]
            default = OVERLAY_DEFAULTS[n] if kind == "triple" else NONE_LABEL
            lines.append(f"{row}_DEF={values.index(default) if default in values else 0}")
            images = self.option_images(row, values)
            if any(images):
                lines.append(f"IMG_{row}=" + "|".join(images))
            for g, name in enumerate(names):
                if g == 0:
                    continue
                for s, entries in enumerate(entries_by_scope):
                    if kind == "triple":
                        entry = entries.get(name)
                        current = entry[1 + n] if entry else None
                    else:
                        current = ini.read(name, where[1]).strip() or None
                    if current and current != "None" and current in values:
                        lines.append(f"{row}_SEL@{s}.{g}={values.index(current)}")
        return lines

    def movie_names(self) -> list[str]:
        return _pack_names(getattr(self.app, "Movies", None))

    def movie_scopes(self) -> tuple[list[tuple[str, str, str]], int]:
        """As stadium_scopes, for the movies (assignment_runtime.default_scope_for_movie picks the default:
        round, else tournament, else derby, else home team)."""
        app = self.app
        scopes: list[tuple[str, str, str]] = []
        default = None
        hid, aid = _context(app, "HID"), _context(app, "AID")
        names = {}
        for side, team in (("home", hid), ("away", aid)):
            try:
                names[side] = (app._resolve_team_name(team) or "") if team else ""
            except Exception:  # noqa: BLE001
                names[side] = ""
        if hid:
            scopes.append((_clean(f"Equipo local ({names['home'] or hid})"), TEAM_MOVIES, hid))
        if hid and aid:
            scopes.append((_clean(f"Derbi ({names['home'] or hid} - {names['away'] or aid})"), DERBY_MOVIES,
                           f"{hid}vs{aid}"))
        round_id, tour = _context(app, "TOURROUNDID"), _context(app, "TOURNAME")
        if round_id:
            scopes.append((f"Ronda ({round_id})", COMP_MOVIES, round_id))
            default = len(scopes) - 1
        if tour:
            scopes.append((f"Torneo ({tour})", COMP_MOVIES, tour))
            if default is None:
                default = len(scopes) - 1
        if default is None:
            default = 1 if hid and aid else 0
        return scopes, default

    def movie_lines(self) -> tuple[list[str], dict[str, list[str]], dict[str, int]]:
        """Data lines, values and selection for the Vídeos tab: "Asignar a" + Vídeo (left out with one scope,
        as the Estadio tab), each pack with its video, a placeholder picture for packs without one."""
        scopes, default = self.movie_scopes()
        self._movie_scopes = scopes
        if not scopes:
            return [f"DESC_{MOVIE_ROW}=Elige los vídeos desde el matchHub, antes del partido (R3)."], \
                   {MOVIE_ROW: [NO_MATCH]}, {MOVIE_ROW: 0}
        names = [DEFAULT_LABEL] + self.movie_names()
        exedir = Path(self.app.exedir)
        videos = [""] + [ingame_images.movie_video_play_path(n) if ingame_images.movie_video_file(exedir, n).exists()
                         else "" for n in names[1:]]
        placeholder = ingame_images.MOVIE_PLACEHOLDER_REL \
            if (exedir / "data" / "ui" / ingame_images.MOVIE_PLACEHOLDER_REL).exists() else ""
        images = [""] + [placeholder if not v else "" for v in videos[1:]]
        lines = [f"TITLE_{MOVIE_ROW}=Vídeos", f"DESC_{MOVIE_ROW}=Las entradas y salidas de vídeo (MoviesGBD) de esa "
                 f"asignación; la vista previa se reproduce sin sonido. Por defecto: quita la asignación."]
        if any(videos):
            lines.append(f"VID_{MOVIE_ROW}=" + "|".join(videos))
        if any(images):
            lines.append(f"IMG_{MOVIE_ROW}=" + "|".join(images))
        ini = self.app.settings_ini
        selections = []
        for _label, section, key in scopes:
            current = ini.read(key, section).strip()
            selections.append(names.index(current) if current in names[1:] else 0)
        if len(scopes) == 1:
            lines[0] = f"TITLE_{MOVIE_ROW}=Vídeos · {scopes[0][0]}"
            return lines, {MOVIE_ROW: names}, {MOVIE_ROW: selections[0]}
        lines += [f"ROWS_{MOVIE_ROW}={MOVIE_SCOPE_ROW}|{MOVIE_ROW}", f"PARENT_{MOVIE_ROW}={MOVIE_SCOPE_ROW}",
                  f"TITLE_{MOVIE_SCOPE_ROW}=Asignar a",
                  f"DESC_{MOVIE_SCOPE_ROW}=A quién se asignan los vídeos, como en el overlay (F12): equipo local, "
                  f"derbi, ronda o torneo."]
        lines += [f"{MOVIE_ROW}_SEL@{g}={sel}" for g, sel in enumerate(selections)]
        return lines, {MOVIE_SCOPE_ROW: [label for label, _s, _k in scopes], MOVIE_ROW: names}, \
            {MOVIE_SCOPE_ROW: default, MOVIE_ROW: selections[default]}

    def _movie_write(self, fields: dict[str, tuple[int, str]]):
        """The Vídeos tab's save, as assignment_runtime.assign_movie / moviesassign: [section] key = pack;
        "Por defecto" removes the key. Returns (key, value, section) to write, True if a delete was saved, or None."""
        written = self._movie_scopes
        if MOVIE_ROW not in fields or not written:
            return None
        if MOVIE_SCOPE_ROW in fields:
            scope_index, scope_text = fields[MOVIE_SCOPE_ROW]
        elif len(written) == 1:
            scope_index, scope_text = 0, written[0][0]
        else:
            return None
        if not (0 <= scope_index < len(written) and written[scope_index][0] == scope_text):
            self.app.log(f"In-game menu: movie scope '{scope_text}' is not the one written; ignored")
            return None
        _label, section, key = written[scope_index]
        now, _default = self.movie_scopes()
        if (section, key) not in {(s, k) for _l, s, k in now}:
            self.app.log(f"In-game menu: movies for [{section}] {key} ignored (the match context changed)")
            return None
        _index, text = fields[MOVIE_ROW]
        ini = self.app.settings_ini
        if text == DEFAULT_LABEL:
            if ini.key_exists(key, section):
                ini.delete_key(key, section)  # reloads from disk: save before any write
                ini.save()
                self.app.log(f"In-game menu assignment: [{section}] {key} removed")
                return True
            return None
        if text not in self.movie_names():
            self.app.log(f"In-game menu: movie pack '{text}' is not in MoviesGBD; ignored")
            return None
        if ini.read(key, section).strip() == text:
            return None
        return key, text, section

    def start_images(self) -> None:
        """Makes the stadium previews once per app session, in a worker thread; the data is written again
        when they are ready (on_images_done)."""
        if self._images_started or not self.installed():
            return
        self._images_started = True
        self.images_busy = True
        names = self.stadium_names()
        exedir = self.app.exedir
        resolve = getattr(self.app, "_resolve_stadium_preview_path", lambda _n: None)

        assets, textures = [], []
        for row, kind in IMAGE_KINDS.items():
            for value in self.option_values(row):
                if value == NONE_LABEL:
                    continue
                if row == "STADIUMGOALPOSTTEX":
                    textures.append(value)
                    continue
                source = self.option_picture(row, value)
                if source is not None:
                    assets.append((kind, value, source))
        render = self._texture_renderer()
        from .file_tools import asset_placeholder_path, resolve_movie_preview_path, stadium_preview_fallback_path
        placeholder_source = stadium_preview_fallback_path()
        movie_placeholder = asset_placeholder_path("movie")
        movies_root = getattr(self.app, "Movies", None)
        movie_videos = []
        for name in self.movie_names():
            video = resolve_movie_preview_path(Path(movies_root) / name) if movies_root else None
            if video is not None:
                movie_videos.append((name, video))

        def work() -> None:
            try:
                made, available = ingame_images.ensure_stadium_images(exedir, names, resolve)
                if placeholder_source is not None and ingame_images.ensure_placeholder(exedir, placeholder_source):
                    made += 1
                if movie_placeholder is not None and ingame_images.ensure_placeholder(
                        exedir, movie_placeholder, ingame_images.MOVIE_PLACEHOLDER_REL):
                    made += 1
                more, more_available = ingame_images.ensure_movie_videos(exedir, movie_videos)
                made, available = made + more, available + more_available
                for value in textures:   # after the stadiums: these take a subprocess each
                    picture = render(value) if render else None
                    if picture is not None:
                        assets.append(("goalposttex", value, picture))
                more, more_available = ingame_images.ensure_asset_images(exedir, assets)
                made, available = made + more, available + more_available
                self.app._worker_queue.put(("ingame_menu_images", made, available, None))
            except Exception as exc:  # noqa: BLE001
                self.app._worker_queue.put(("ingame_menu_images", 0, 0, str(exc)))

        threading.Thread(target=work, name="ingame-menu-images", daemon=True).start()
        self.app._schedule_worker_poll()

    def on_images_done(self, made: int, available: int, error: str | None) -> None:
        self.images_busy = False
        if error:
            self.app.log(f"In-game menu: stadium previews failed: {error}")
            return
        self.app.log(f"In-game menu: stadium previews ready ({available}, {made} new)")
        if made:
            self.write_data("stadium previews", force=True)

    # --- app -> menu ---------------------------------------------------------------------------
    def write_data(self, reason: str, force: bool = False) -> bool:
        """Writes data.big if the data changed (or force). True if written."""
        if not self.installed():
            return False
        values, selected = self.rows()
        extra, stadium_values, stadium_selected = self.stadium_lines()
        values.update(stadium_values)
        selected.update(stadium_selected)
        movie_extra, movie_values, movie_selected = self.movie_lines()
        extra += movie_extra
        values.update(movie_values)
        selected.update(movie_selected)
        stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        text = ingame_datafile.encode(values, selected, source="CG Server 16", stamp=stamp, ack=self.last_seq)
        text = "\n".join([text] + extra)
        key = "\n".join(line for line in text.split("\n") if not line.startswith("STAMP="))
        if key == self._written and not force:
            return False
        if self._template is None:
            path = _bundled_resource_path(TEMPLATE)
            if path is None:
                self.app.log("In-game menu: data template not found (resources/ingame/data_template.big)")
                return False
            self._template = path.read_bytes()
        target = Path(self.app.exedir) / DATA_MOVIE
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(ingame_datafile.render(self._template, text))
        self._written = key
        shown = ", ".join(f"{row}={values[row][selected[row]]}" for row in DEFAULT_ROWS)
        stadium = f", stadium scopes={len(self._stadium_scopes)}" if self._stadium_scopes else ""
        self.app.log(f"In-game menu: data.big written ({reason}): {shown}{stadium}, ack={self.last_seq}")
        self.start_images()
        return True

    def install_changed(self) -> None:
        """The menu was just installed, updated or removed (Setup tab): its data and previews start over."""
        self._images_started = False
        self._written = None
        self.write_data("install", force=True)

    def context_changed(self) -> None:
        """From the live context reader (HID/AID/... changed): the Estadio rows depend on the home team."""
        if self.installed():
            self.write_data("match context")

    # --- page transitions ------------------------------------------------------------------------
    def on_page(self, previous: str | None, page: str, pid: int | None) -> None:
        """From the page-transition handler (Tk thread)."""
        if not self.installed():
            return
        self.attached(pid)
        if previous == MENU_PAGE and page != MENU_PAGE and pid:
            self._start_scan(pid)
        elif page != MENU_PAGE:
            self.write_data("page " + (page or "?"))

    def _start_scan(self, pid: int) -> None:
        if self.busy:
            return
        self.busy = True
        hot, newer_than = list(self.hot), self.last_seq

        def work() -> None:
            found = list(hot)
            try:
                records, mb, secs = ingame_recordscan.scan(pid, hot, newer_than, found)
                self.app._worker_queue.put(("ingame_menu_scan", pid, records, found, mb, secs, None))
            except Exception as exc:  # noqa: BLE001 - reported on the Tk thread
                self.app._worker_queue.put(("ingame_menu_scan", pid, [], found, 0.0, 0.0, str(exc)))

        threading.Thread(target=work, name="ingame-menu-scan", daemon=True).start()
        self.app._schedule_worker_poll()

    # --- menu -> app ---------------------------------------------------------------------------
    def on_scan_done(self, pid: int, records, found, mb: float, secs: float, error: str | None) -> None:
        """The worker's result, on the Tk thread (_poll_worker_queue); never raises into the queue loop."""
        self.busy = False
        try:
            self._scan_done(pid, records, found, mb, secs, error)
        except Exception as exc:  # noqa: BLE001
            self.app.log(f"In-game menu: applying the menu's save failed: {exc}")

    def _scan_done(self, pid: int, records, found, mb: float, secs: float, error: str | None) -> None:
        if error:
            self.app.log(f"In-game menu: memory scan failed: {error}")
            return
        if pid != self._pid:
            return  # FIFA restarted meanwhile
        self.hot = found
        top = ingame_recordscan.newest(records)
        if not top or top[0] <= self.last_seq:
            self.app.log(f"In-game menu left without a new save ({mb:.0f} MB in {secs:.1f} s)")
            return
        seq, fields = top
        self.app.log(f"In-game menu: save #{seq} read from FIFA ({mb:.0f} MB in {secs:.1f} s)")
        changed = self.apply(dict(fields))
        self.last_seq = seq
        self.write_data(f"after save #{seq}", force=True)
        if changed:
            # back on the KickOffHub the app would not reload anything (a match-preparation revisit)
            self.app.apply_all_runtime()

    def apply(self, fields: dict[str, tuple[int, str]]) -> bool:
        """Writes the menu's choices into settings.ini. The index refers to the lists in data.big; the text
        decides if the lists moved since. True if settings.ini changed."""
        values, _selected = self.rows()
        ini = self.app.settings_ini
        writes: list[tuple[str, str, str]] = []   # (key, value, section)
        changed = False
        for row, (section, _folder) in DEFAULT_ROWS.items():
            if row not in fields:
                continue
            index, text = fields[row]
            names = values[row]
            if not (0 <= index < len(names) and names[index] == text):
                if text in names:
                    index = names.index(text)
                else:
                    self.app.log(f"In-game menu: {row} '{text}' is not one of the app's packs; ignored")
                    continue
            current = ini.read(DEFAULT_KEY, section).strip()
            if index == 0:
                if ini.key_exists(DEFAULT_KEY, section):
                    ini.delete_key(DEFAULT_KEY, section)  # reloads from disk: save before any write
                    ini.save()
                    changed = True
                    self.app.log(f"In-game menu assignment: [{section}] {DEFAULT_KEY} reset to default")
            elif names[index] != current:
                writes.append((DEFAULT_KEY, names[index], section))
        movie = self._movie_write(fields)   # a delete is saved inside: before any write below
        if movie is True:
            changed = True
        elif movie:
            writes.append(movie)
        stadium_write, stadium_changed, preselect = self._stadium_write(fields)  # its own saves come first
        changed = changed or stadium_changed
        if stadium_write:
            writes.append(stadium_write)
        for key, value, section in writes:
            ini.write(key, value, section)
            self.app.log(f"In-game menu assignment: [{section}] {key}={value}")
        if writes:
            ini.save()
        if preselect:
            self._preselect_stadium(*preselect)
        return changed or bool(writes)

    def _stadium_write(self, fields: dict[str, tuple[int, str]]):
        """The Estadio tab's save, as the F12 overlay's stadium wizard (app_overlay._activate_wizard_step's last
        step): the packs (goalpost model/texture, net mesh, entrance camera) first, in their own sections keyed by
        the stadium (assignment_runtime._write_stadium_goalpost_overrides: deletes saved one by one, then the
        writes), then the scope's value with this stadium's entry "<stadium>,<police>,<pitch>,<net>" appended
        (_append_overlay_stadium: a re-picked stadium moves last with the new triple; max 64), pre-chosen for
        the match about to be played. "Por defecto" removes the scope's key.
        Returns (assignment to write (key, value, section) or None, settings.ini changed already, the
        (key, value, section) to pre-choose or None)."""
        written = self._stadium_scopes
        if STADIUM_ROW not in fields or not written:
            return None, False, None
        if SCOPE_ROW in fields:
            scope_index, scope_text = fields[SCOPE_ROW]
        elif len(written) == 1:
            scope_index, scope_text = 0, written[0][0]   # one scope: the menu showed no "Asignar a" row
        else:
            return None, False, None
        if not (0 <= scope_index < len(written) and written[scope_index][0] == scope_text):
            self.app.log(f"In-game menu: stadium scope '{scope_text}' is not the one written; ignored")
            return None, False, None
        _label, section, key = written[scope_index]
        now, _default = self.stadium_scopes()
        if (section, key) not in {(s, k) for _l, s, k in now}:
            self.app.log(f"In-game menu: stadium for [{section}] {key} ignored (the match context changed)")
            return None, False, None
        _index, text = fields[STADIUM_ROW]
        ini = self.app.settings_ini
        if text == DEFAULT_LABEL:
            if ini.key_exists(key, section):
                ini.delete_key(key, section)  # reloads from disk: save before any write
                ini.save()
                self.app.log(f"In-game menu assignment: [{section}] {key} removed (FIFA's stadium)")
                return None, True, None
            return None, False, None
        if text not in self.stadium_names():
            self.app.log(f"In-game menu: stadium '{text}' is not in StadiumGBD; ignored")
            return None, False, None
        entries = self.stadium_entries(section, key)
        old = {name: (police, pitch, net) for name, police, pitch, net in entries}
        triple = list(old.get(text, OVERLAY_DEFAULTS))
        overrides: dict[str, str] = {}
        for n, (row, _title, _desc, kind, where) in enumerate(STADIUM_OPTIONS):
            if row not in fields:
                continue
            chosen = fields[row][1]
            if chosen not in self.option_values(row):
                self.app.log(f"In-game menu: {row} '{chosen}' is not in its list; kept as it was")
                continue
            if kind == "triple":
                triple[n] = chosen
            else:
                overrides[where[1]] = "None" if chosen == NONE_LABEL else chosen
        changed = False
        current_packs = {sec: (ini.read(text, sec).strip() or "None") for sec in overrides}
        if any(current_packs[sec] != value for sec, value in overrides.items()):
            from .assignment_runtime import AssignmentRuntime
            writer = getattr(self.app, "assignment_runtime", None) or AssignmentRuntime(self.app)
            writer._write_stadium_goalpost_overrides([text], overrides)   # saved (before any write below)
            changed = True
            self.app.log(f"In-game menu assignment: packs of {text}: {overrides}")
        new_entries = [entry for entry in entries if entry[0] != text]
        if len(new_entries) >= MAX_STADIUMS:
            new_entries.pop(0)
        new_entries.append((text, *triple))
        value = ",".join(field for entry in new_entries for field in entry)
        old_value = ",".join(field for entry in entries for field in entry)
        write = (key, value, section) if value != old_value else None
        if write is None and not changed:
            return None, False, None   # nothing new for this scope
        return write, changed, (key, value, section)

    def _preselect_stadium(self, key: str, value: str, section: str) -> None:
        """What the overlay leaves after an explicit pick (app_overlay._write_overlay_assignment): the stadium
        picker of this match counts as resolved for the value just written, so apply_stadium_runtime applies
        the chosen one (the last entry) instead of asking among every stadium of that key."""
        app = self.app
        if not hasattr(app, "_stadium_picker_signature"):
            return
        app._stadium_picker_signature = (getattr(app, "_kickoff_generation", 0), section, key, value,
                                         getattr(app, "HID", ""), getattr(app, "TOURNAME", ""),
                                         getattr(app, "TOURROUNDID", ""))
        app._stadium_picker_pending = True
        app._stadium_picker_resolved = True
        app._stadium_picker_chosen = value.split(",")[-4]   # the last entry: the one just picked


def _context(app, attr: str) -> str:
    value = str(getattr(app, attr, "") or "").strip()
    return "" if value in {"", "0"} else value


def _clean(text: str) -> str:
    return text.replace("|", "/").replace("=", "-").replace("\n", " ")


def _pack_names(folder) -> list[str]:
    """Pack folders, as the F12 menu lists them; names the data text cannot carry are left out."""
    if folder is None:
        return []
    p = Path(folder)
    if not p.is_dir():
        return []
    return sorted(d.name for d in p.iterdir() if d.is_dir() and not any(c in d.name for c in BAD_CHARS))
