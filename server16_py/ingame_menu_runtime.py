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
  Marcador / Logo TV   as the F12's ScoreBoards / TV Logos tabs: "Asignar a" (Home Team -> [HomeTeamScoreBoard] /
                       [HomeTeamTvLogo] <HID>, Derby -> [DerbyScoreBoard] / [DerbyTvLogo] <HID>vs<AID>, Default /
                       Friendly -> [Scoreboard] / [TVLogo] key "0", Round / Tournament -> the same sections <id>; the
                       ones there are, default as default_scope_for_scoreboard; left out with only Default /
                       Friendly, e.g. opened from the hub tile) and the pack, previewed by its
                       render/thumbnail/<scoreboard|tvlogo> picture (else the app's placeholder); "Por defecto"
                       removes the key.
  Estadio              with a match context (the menu opened from the KickOffHub) a list tab of the menu
                       (menudata LIST_<tab>, prueba 14a): "Asignar a" (the scopes this match has: Home Team ->
                       [stadium] <HID>, Round -> [comp] <ROUND>, Tournament -> [comp] <TOUR>; left out with one),
                       "+ Agregar estadio", one row per stadium assigned to that scope (each entry
                       "<stadium>,<police>,<pitch>,<net>" of the key) and "Estadio del partido" (Selector/Al azar or one of
                       them, saved in settings.ini [FixedStadium] <section>_<key>: StadiumRuntime uses it for every
                       match of that assignment, before random or the picker, until Selector/Al azar again). A on "+ Agregar" or a stadium opens its assets, as the F12 overlay's stadium
                       wizard: the stadium (every one of StadiumGBD, with its preview from ingame_images; locked
                       when editing one), then STADIUM_OPTIONS: police, pitch pattern, net colour (the entry's
                       triple, per scope) and goalpost model/texture, net mesh, entrance camera (their own
                       sections keyed by the stadium), each showing what that stadium has now. "Guardar" adds it
                       to the list (an assigned one keeps its place), "Quitar" takes an assigned one out (the key
                       goes with the last); the menu sends every save / removal (SV<n>_<row>) and
                       every changed match row (M<scope>_STADIUMMATCH). Without a context: one value telling to
                       open it from the match hub.
  Vídeos               as the F12's Movies tab: "Asignar a" (Home Team / Derby / Round / Tournament, the ones
                       this match has; left out with one) and the MoviesGBD pack, each previewed by its
                       bootflowoutro.vp8 played muted by FIFA's MoviePlayer in the menu (ingame_images links it
                       under data/ui/cgfs16/mov). Saved to [TeamMovies]/[DerbyMatch]/[movies] as assign_movie.
  Equipaciones         not wired yet: one "Próximamente" value, saves ignored.
After a save that changed settings.ini the runtime is applied again (apply_all_runtime): coming back to the
KickOffHub is a "revisit" that would not reload anything (docs/stadium-slots.md).

Texts: keys, not texts ("{{home~team:FC Barcelona}}", ingame_menu_texts.token): the menu puts them in FIFA's
language of the moment (it can be chosen in the game, USE_LANGUAGE_SELECT = 1), with the same table
(ingame_menu_texts, a copy of cgfs-ingame's menutexts.py). Its record says that language (LANG) and what comes
back is compared with the keys rendered in it (say).

ACK=<seq>: the last save the app processed. Until the app has seen a save, the menu keeps its own choice
over the app's selection (a quick re-entry used to show the previous one, prueba 6).
Does nothing unless the menu is installed in the game (data/ui/game/screens/cgfs16/cgfs16menu.big).
"""
from __future__ import annotations

import datetime
import re
import threading
from pathlib import Path
from typing import TYPE_CHECKING

from . import ingame_datafile, ingame_images, ingame_menu_texts, ingame_recordscan
from .file_tools import _bundled_resource_path, discover_stadium_names

if TYPE_CHECKING:
    from .app import Server16App

MENU_PAGE = "game/screens/cgfs16/CGFS16Menu"
MENU_MOVIE = Path("data/ui/game/screens/cgfs16/cgfs16menu.big")
DATA_MOVIE = Path("data/ui/cgfs16/data.big")
TEMPLATE = "ingame/data_template.big"
# the texts in Spanish (tests, docs); the menu gets them in the game's language (InGameMenuRuntime.t)
DEFAULT_LABEL = "Por defecto (FIFA 16)"
NOT_YET = "Próximamente"
NO_MATCH = "Ábrelo desde el matchHub (R3)"
# the Marcador / Logo TV tabs, as the F12's scoreboards / tvlogos tabs (app_overlay._get_scope_options_for_tab,
# _resolve_overlay_assignment_target, the assign step): menu row -> (its scope row, title, attribute of the app with
# the packs' folder, sections (home team, derby, the rest), thumbnail key, placeholder kind, image kind); the
# title is an ingame_menu_texts key
PACK_TABS = {
    "SCOREBOARD": ("SCOREBOARDSCOPE", "tab_scoreboard", "ScoreBoard", ("HomeTeamScoreBoard", "DerbyScoreBoard", "Scoreboard"),
                   "scoreboard", "scoreboard", "scoreboard"),
    "TVLOGO": ("TVLOGOSCOPE", "tab_tvlogo", "TVLogo", ("HomeTeamTvLogo", "DerbyTvLogo", "TVLogo"),
               "tvlogo", "tv", "tvlogo"),
}
DEFAULT_ROWS = tuple(PACK_TABS)   # the rows the log line shows
DEFAULT_SCOPE_LABEL = "Por defecto / Amistoso"   # Spanish (tests)
PACK_PLACEHOLDERS = {"SCOREBOARD": ingame_images.SCOREBOARD_PLACEHOLDER_REL, "TVLOGO": ingame_images.TVLOGO_PLACEHOLDER_REL}
OTHER_ROWS = ("KITS",)
DEFAULT_KEY = "0"
STADIUM_SECTION, COMP_SECTION = "stadium", "comp"
# "Estadio del partido" (the match row of the Estadio tab): the stadium fixed for one assignment, kept across
# matches and restarts in settings.ini [FixedStadium] "<section>_<key>" = <stadium> (stadium_241, comp_12);
# no key = Selector/Al azar. StadiumRuntime._ingame_menu_choice reads it.
FIXED_STADIUM_SECTION = "FixedStadium"
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
RANDOM_LABEL = "Selector/Al azar"   # the match row's first value (STADIUMMATCH_FIRST, Spanish)
# tab -> its label (ingame_menu_texts key): the menu's tabs (menudata.TABS, model.TOGGLES)
STAMP_SLOT = "@STAMP@"   # the time in the INFO key, filled in when the data is written
TAB_TEXTS = {"STADIUM": "tab_stadium", "SCOREBOARD": "tab_scoreboard", "TVLOGO": "tab_tvlogo",
             "MOVIES": "tab_movies", "KITS": "tab_kits"}
SAVE_FIELD = re.compile(r"SV(\d+)_([A-Z][A-Z0-9_]*)$")          # the n-th "Guardar" of a list tab
MATCH_FIELD = re.compile(r"M(\d*)_" + STADIUM_ROW + r"MATCH$")   # the match row of a scope ("" with one scope)


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
        self._pack_scopes: dict[str, list[tuple[str, str, str]]] = {}   # the Marcador / Logo TV scopes
        self.record_lang: str | None = None   # the language of the menu's last record (its LANG): FIFA's
        self._images_started = False
        self.images_busy = False   # the previews are being made in a worker thread

    # --- language ----------------------------------------------------------------------------
    def language(self) -> str:
        """FIFA's language as last seen: the menu's record, else the app's guess (ingame_menu_texts.detect)."""
        if self.record_lang:
            return self.record_lang
        localization = getattr(self.app, "localization", None)
        return ingame_menu_texts.detect(getattr(self.app, "exedir", None), getattr(localization, "language", None))

    def t(self, key: str, **fields) -> str:
        """A text for the menu: its key, which the menu puts in FIFA's language when it opens."""
        return _clean(ingame_menu_texts.token(key, **{k: _clean(str(v)) for k, v in fields.items()}))

    def say(self, value: str) -> str:
        """A value written with keys, as the menu showed it: in the language of its record (else the app's guess)."""
        return ingame_menu_texts.render(value, self.language())

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
        for row in OTHER_ROWS:
            values[row] = [self.t("not_yet")]
            selected[row] = 0
        return values, selected

    # --- Marcador / Logo TV ------------------------------------------------------------------------
    def pack_names(self, row: str) -> list[str]:
        return _pack_names(getattr(self.app, PACK_TABS[row][2], None))

    def pack_scopes(self, row: str) -> tuple[list[tuple[str, str, str]], int]:
        """([(label, section, key)] the F12 overlay offers for scoreboards / TV logos in this match context, in its
        order (Home Team, Derby, Default / Friendly, Round, Tournament), the index of the app's default scope
        (assignment_runtime.default_scope_for_scoreboard: round, else tournament, else home team, else default)."""
        app = self.app
        home_section, derby_section, section = PACK_TABS[row][3]
        hid, aid = _context(app, "HID"), _context(app, "AID")
        names = {}
        for side, team in (("home", hid), ("away", aid)):
            try:
                names[side] = (app._resolve_team_name(team) or "") if team else ""
            except Exception:  # noqa: BLE001
                names[side] = ""
        scopes: list[tuple[str, str, str]] = []
        home = None
        if hid:
            home = len(scopes)
            scopes.append((self.t("home", team=names['home'] or hid), home_section, hid))
        if hid and aid:
            scopes.append((self.t("derby", home=names['home'] or hid, away=names['away'] or aid), derby_section,
                           f"{hid}vs{aid}"))
        default = len(scopes)
        scopes.append((self.t("default_scope"), section, DEFAULT_KEY))
        round_id, tour = _context(app, "TOURROUNDID"), _context(app, "TOURNAME")
        chosen = None
        if round_id:
            chosen = len(scopes)
            scopes.append((self.t("round", id=round_id), section, round_id))
        if tour:
            if chosen is None:
                chosen = len(scopes)
            scopes.append((self.t("tour", id=tour), section, tour))
        if chosen is None:
            chosen = home if home is not None else default
        return scopes, chosen

    def pack_lines(self, row: str) -> tuple[list[str], dict[str, list[str]], dict[str, int]]:
        """Data lines, values and selection for the Marcador / Logo TV tab (see the module docstring)."""
        scope_row, title_key, _attr, _sections, _thumb, _placeholder, kind = PACK_TABS[row]
        title = self.t(title_key)
        scopes, default = self.pack_scopes(row)
        self._pack_scopes[row] = scopes
        names = [self.t("default")] + self.pack_names(row)
        exedir = Path(self.app.exedir)
        placeholder_rel = PACK_PLACEHOLDERS[row]
        placeholder = placeholder_rel if (exedir / "data" / "ui" / placeholder_rel).exists() else ""
        images = [""] + [ingame_images.asset_image_rel(kind, n) if ingame_images.asset_image_file(exedir, kind, n).exists()
                         else placeholder for n in names[1:]]
        lines = [f"TITLE_{row}={title}", f"DESC_{row}=" + self.t(f"{title_key[4:]}_desc")]
        if any(images):
            lines.append(f"IMG_{row}=" + "|".join(images))
        ini = self.app.settings_ini
        selections = []
        for _label, section, key in scopes:
            current = ini.read(key, section).strip()
            selections.append(names.index(current) if current in names[1:] else 0)
        if len(scopes) == 1:
            lines[0] = f"TITLE_{row}={title} · {scopes[0][0]}"
            return lines, {row: names}, {row: selections[0]}
        lines += [f"ROWS_{row}={scope_row}|{row}", f"PARENT_{row}={scope_row}",
                  f"TITLE_{scope_row}=" + self.t("scope"), f"DESC_{scope_row}=" + self.t("scope_desc_pack")]
        lines += [f"{row}_SEL@{g}={sel}" for g, sel in enumerate(selections)]
        return lines, {scope_row: [label for label, _s, _k in scopes], row: names}, \
            {scope_row: default, row: selections[default]}

    def _pack_write(self, row: str, fields: dict[str, tuple[int, str]]):
        """The Marcador / Logo TV tab's save, as the F12 overlay's: [section] key = pack; "Por defecto" removes
        the key. Returns (key, value, section) to write, True if a delete was saved, or None."""
        if row not in fields:
            return None
        scope_row = PACK_TABS[row][0]
        written = self._pack_scopes.get(row) or self.pack_scopes(row)[0]
        if scope_row in fields:
            scope_index, scope_text = fields[scope_row]
        elif len(written) == 1:
            scope_index, scope_text = 0, self.say(written[0][0])
        else:
            return None
        if not (0 <= scope_index < len(written) and self.say(written[scope_index][0]) == scope_text):
            self.app.log(f"In-game menu: {row} scope '{scope_text}' is not the one written; ignored")
            return None
        _label, section, key = written[scope_index]
        now, _default = self.pack_scopes(row)
        if (section, key) not in {(s, k) for _l, s, k in now}:
            self.app.log(f"In-game menu: {row} for [{section}] {key} ignored (the match context changed)")
            return None
        index, text = fields[row]
        names = [self.say(self.t("default"))] + self.pack_names(row)
        if not (0 <= index < len(names) and names[index] == text):
            if text in names:
                index = names.index(text)
            else:
                self.app.log(f"In-game menu: {row} '{text}' is not one of the app's packs; ignored")
                return None
        ini = self.app.settings_ini
        if index == 0:
            if ini.key_exists(key, section):
                ini.delete_key(key, section)  # reloads from disk: save before any write
                ini.save()
                self.app.log(f"In-game menu assignment: [{section}] {key} reset to default")
                return True
            return None
        if ini.read(key, section).strip() == names[index]:
            return None
        return key, names[index], section

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
            scopes.append((self.t("home", team=name or hid), STADIUM_SECTION, hid))
        round_id = _context(app, "TOURROUNDID")
        if round_id:
            scopes.append((self.t("round", id=round_id), COMP_SECTION, round_id))
            default = len(scopes) - 1
        tour = _context(app, "TOURNAME")
        if tour:
            scopes.append((self.t("tour", id=tour), COMP_SECTION, tour))
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
            return [f"TITLE_{STADIUM_ROW}=" + self.t("tab_stadium"), f"DESC_{STADIUM_ROW}=" + self.t("stadium_open_hub")], \
                   {STADIUM_ROW: [self.t("no_match")]}, {STADIUM_ROW: 0}
        names = self.stadium_names()
        if not names:
            return [f"TITLE_{STADIUM_ROW}=" + self.t("tab_stadium"), f"DESC_{STADIUM_ROW}=" + self.t("no_stadiums")], \
                   {STADIUM_ROW: ["-"]}, {STADIUM_ROW: 0}
        exedir = Path(self.app.exedir)
        # a stadium without its own preview gets the app's placeholder, as the F12 shows
        # (_resolve_stadium_preview_path_or_default); anything else unknown: the menu's logo
        placeholder = ingame_images.PLACEHOLDER_REL if (exedir / "data" / "ui" / ingame_images.PLACEHOLDER_REL).exists() else ""
        images = [ingame_images.stadium_image_rel(n) if ingame_images.stadium_image_file(exedir, n).exists()
                  else placeholder for n in names]
        options = [row for row, *_ in STADIUM_OPTIONS]
        r = STADIUM_ROW
        lines = [f"ROWS_{r}=" + "|".join([SCOPE_ROW, r] + options), f"PARENT_{r}={SCOPE_ROW}", f"LIST_{r}={r}",
                 f"TITLE_{SCOPE_ROW}=" + self.t("scope"), f"DESC_{SCOPE_ROW}=" + self.t("scope_desc_stadium"),
                 f"TITLE_{r}=" + self.t("tab_stadium"), f"DESC_{r}=" + self.t("stadium_desc"),
                 f"TITLE_{r}ADD=" + self.t("add"), f"DESC_{r}ADD=" + self.t("add_desc"),
                 f"DESC_{r}ENTRY=" + self.t("entry_desc"),
                 f"TITLE_{r}SAVE=" + self.t("save"), f"DESC_{r}SAVE=" + self.t("save_desc"),
                 f"TITLE_{r}DEL=" + self.t("remove"), f"DESC_{r}DEL=" + self.t("remove_desc"),
                 f"TITLE_{r}MATCH=" + self.t("match"), f"DESC_{r}MATCH=" + self.t("match_desc"),
                 f"{r}MATCH_FIRST=" + self.t("random")]
        if any(images):
            lines.append(f"IMG_{r}=" + "|".join(images))
        for g, (_label, section, key) in enumerate(scopes):
            assigned = self.listed_stadiums(section, key, names)
            lines.append(f"{r}_LIST@{g}=" + "|".join(str(names.index(n)) for n in assigned))
            chosen = self.match_choice(section, key)
            if chosen in assigned:
                lines.append(f"{r}MATCH_SEL@{g}={assigned.index(chosen) + 1}")
        values_out: dict = {}
        lines += self.option_lines(scopes, names, values_out)
        if len(scopes) == 1:
            # one scope (a friendly: only the home team): no "Asignar a" row -- FIFA greys out a row with a
            # single value (prueba 9b) -- its scope goes in the stadium row's title instead; the lists and
            # selections are then keyed without it ("<g>" instead of "<scope>.<g>", "_LIST" instead of "_LIST@0")
            drop = (f"ROWS_{r}=", f"PARENT_{r}=", f"TITLE_{SCOPE_ROW}=", f"DESC_{SCOPE_ROW}=", f"TITLE_{r}=")
            lines = [line for line in lines if not line.startswith(drop)]
            lines = [line.replace("_SEL@0.", "_SEL@", 1) if "_SEL@0." in line
                     else line.replace(f"{r}_LIST@0=", f"{r}_LIST=", 1).replace(f"{r}MATCH_SEL@0=", f"{r}MATCH_SEL=", 1)
                     for line in lines]
            lines.append(f"TITLE_{r}=" + self.t("tab_stadium") + f" · {scopes[0][0]}")
            lines.append(f"ROWS_{r}=" + "|".join([r] + options))
            return lines, dict(values_out, **{r: names}), {r: 0}
        return lines, dict(values_out, **{SCOPE_ROW: [label for label, _s, _k in scopes], r: names}), \
            {SCOPE_ROW: default, r: 0}

    def listed_stadiums(self, section: str, key: str, names: list[str]) -> list[str]:
        """The stadiums assigned to this key that the menu can show (in StadiumGBD), in order, once each."""
        out: list[str] = []
        for name, *_rest in self.stadium_entries(section, key):
            if name in names and name not in out:
                out.append(name)
        return out

    def match_choice(self, section: str, key: str) -> str | None:
        """The stadium "Estadio del partido" fixed for this key, or None (random / the picker)."""
        return read_fixed_stadium(self.app.settings_ini, section, key)

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
        return [self.t("none")] + [n for n in packs if not any(c in n for c in BAD_CHARS)]

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

    def option_lines(self, scopes, names, values_out: dict) -> list[str]:
        """Data lines of the stadium's option rows: their lists, titles, defaults and, per path
        "<scope>.<stadium>", what is set now -- police/pitch/net from that stadium's entry in the scope's value,
        the packs from their own sections (same for every scope). Fills values_out with the lists."""
        lines: list[str] = []
        ini = self.app.settings_ini
        entries_by_scope = [{e[0]: e for e in self.stadium_entries(section, key)} for _l, section, key in scopes]
        for n, (row, _title, _desc, kind, where) in enumerate(STADIUM_OPTIONS):
            values = self.option_values(row)
            values_out[row] = values
            lines += [f"PARENT_{row}={STADIUM_ROW}", f"TITLE_{row}=" + self.t(IMAGE_KINDS[row]),
                      f"DESC_{row}=" + self.t(IMAGE_KINDS[row] + "_desc")]
            default = OVERLAY_DEFAULTS[n] if kind == "triple" else self.t("none")
            lines.append(f"{row}_DEF={values.index(default) if default in values else 0}")
            images = self.option_images(row, values)
            if any(images):
                lines.append(f"IMG_{row}=" + "|".join(images))
            for g, name in enumerate(names):
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
            scopes.append((self.t("home", team=names['home'] or hid), TEAM_MOVIES, hid))
        if hid and aid:
            scopes.append((self.t("derby", home=names['home'] or hid, away=names['away'] or aid), DERBY_MOVIES,
                           f"{hid}vs{aid}"))
        round_id, tour = _context(app, "TOURROUNDID"), _context(app, "TOURNAME")
        if round_id:
            scopes.append((self.t("round", id=round_id), COMP_MOVIES, round_id))
            default = len(scopes) - 1
        if tour:
            scopes.append((self.t("tour", id=tour), COMP_MOVIES, tour))
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
            return [f"TITLE_{MOVIE_ROW}=" + self.t("tab_movies"), f"DESC_{MOVIE_ROW}=" + self.t("movies_open_hub")], \
                   {MOVIE_ROW: [self.t("no_match")]}, {MOVIE_ROW: 0}
        names = [self.t("default")] + self.movie_names()
        exedir = Path(self.app.exedir)
        videos = [""] + [ingame_images.movie_video_play_path(n) if ingame_images.movie_video_file(exedir, n).exists()
                         else "" for n in names[1:]]
        placeholder = ingame_images.MOVIE_PLACEHOLDER_REL \
            if (exedir / "data" / "ui" / ingame_images.MOVIE_PLACEHOLDER_REL).exists() else ""
        images = [""] + [placeholder if not v else "" for v in videos[1:]]
        lines = [f"TITLE_{MOVIE_ROW}=" + self.t("tab_movies"), f"DESC_{MOVIE_ROW}=" + self.t("movies_desc")]
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
            lines[0] = f"TITLE_{MOVIE_ROW}=" + self.t("tab_movies") + f" · {scopes[0][0]}"
            return lines, {MOVIE_ROW: names}, {MOVIE_ROW: selections[0]}
        lines += [f"ROWS_{MOVIE_ROW}={MOVIE_SCOPE_ROW}|{MOVIE_ROW}", f"PARENT_{MOVIE_ROW}={MOVIE_SCOPE_ROW}",
                  f"TITLE_{MOVIE_SCOPE_ROW}=" + self.t("scope"), f"DESC_{MOVIE_SCOPE_ROW}=" + self.t("scope_desc_movies")]
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
            scope_index, scope_text = 0, self.say(written[0][0])
        else:
            return None
        if not (0 <= scope_index < len(written) and self.say(written[scope_index][0]) == scope_text):
            self.app.log(f"In-game menu: movie scope '{scope_text}' is not the one written; ignored")
            return None
        _label, section, key = written[scope_index]
        now, _default = self.movie_scopes()
        if (section, key) not in {(s, k) for _l, s, k in now}:
            self.app.log(f"In-game menu: movies for [{section}] {key} ignored (the match context changed)")
            return None
        index, text = fields[MOVIE_ROW]
        ini = self.app.settings_ini
        if index == 0 or text == self.say(self.t("default")):
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
                if value == self.t("none"):
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
        from .file_tools import resolve_asset_thumbnail_path
        for row, (_scope, _title, attr, _sections, thumb, placeholder_kind, kind) in PACK_TABS.items():
            root = getattr(self.app, attr, None)
            for pack in self.pack_names(row) if root else []:
                try:
                    source = resolve_asset_thumbnail_path(Path(root) / pack, thumb)
                except Exception:  # noqa: BLE001
                    source = None
                if source is not None:
                    assets.append((kind, pack, source))
        pack_placeholders = [(asset_placeholder_path(PACK_TABS[row][5]), rel) for row, rel in PACK_PLACEHOLDERS.items()]
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
                for source, rel in pack_placeholders:
                    if source is not None and ingame_images.ensure_placeholder(exedir, source, rel):
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
        extra: list[str] = [f"LANG={self.language()}",   # the app's guess, for the log / diagnosis only
                            "INFO=" + self.t("info", source="CG Server 16", stamp=STAMP_SLOT),
                            "BEHIND=" + self.t("behind"), "TITLE_KITS=" + self.t("tab_kits"),
                            "DESC_KITS=" + self.t("kits_desc")]
        extra += [f"TAB_{tab}=" + self.t(key) for tab, key in TAB_TEXTS.items()]
        for row in PACK_TABS:
            pack_extra, pack_values, pack_selected = self.pack_lines(row)
            extra += pack_extra
            values.update(pack_values)
            selected.update(pack_selected)
        stadium_extra, stadium_values, stadium_selected = self.stadium_lines()
        extra += stadium_extra
        values.update(stadium_values)
        selected.update(stadium_selected)
        movie_extra, movie_values, movie_selected = self.movie_lines()
        extra += movie_extra
        values.update(movie_values)
        selected.update(movie_selected)
        stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        text = ingame_datafile.encode(values, selected, source="CG Server 16", stamp=stamp, ack=self.last_seq)
        text = "\n".join([text] + [line.replace(STAMP_SLOT, stamp) if line.startswith("INFO=") else line
                                   for line in extra])
        key = "\n".join(line for line in text.split("\n") if not line.startswith(("STAMP=", "INFO=")))
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
        shown = ", ".join(f"{row}={self.say(values[row][selected[row]])}" for row in DEFAULT_ROWS)
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
        fields = dict(fields)
        reported = ingame_menu_texts.normalize(fields.pop("LANG", (0, ""))[1])
        if reported and reported != self.record_lang:
            self.app.log(f"In-game menu: FIFA is in '{reported}'")
        if reported:
            self.record_lang = reported   # what follows was shown in it
        changed = self.apply(fields)
        self.last_seq = seq
        self.write_data(f"after save #{seq}", force=True)
        if changed:
            # back on the KickOffHub the app would not reload anything (a match-preparation revisit)
            self.app.apply_all_runtime()

    def apply(self, fields: dict[str, tuple[int, str]]) -> bool:
        """Writes the menu's choices into settings.ini. The index refers to the lists in data.big; the text
        decides if the lists moved since. True if settings.ini changed."""
        ini = self.app.settings_ini
        writes: list[tuple[str, str, str]] = []   # (key, value, section)
        changed = False
        for row in PACK_TABS:
            pack = self._pack_write(row, fields)   # a delete is saved inside: before any write below
            if pack is True:
                changed = True
            elif pack:
                writes.append(pack)
        movie = self._movie_write(fields)   # a delete is saved inside: before any write below
        if movie is True:
            changed = True
        elif movie:
            writes.append(movie)
        changed = self._stadium_saves(fields) or changed   # saved inside: before the writes below
        for key, value, section in writes:
            ini.write(key, value, section)
            self.app.log(f"In-game menu assignment: [{section}] {key}={value}")
        if writes:
            ini.save()
        return changed or bool(writes)

    def _stadium_scope(self, index: int | None, text: str | None):
        """(section, key) of a scope the menu sent (index and label into the scopes the data was written with;
        None with one scope: the menu showed no "Asignar a" row), or None (logged) if it is not one of them or
        the match context changed since."""
        written = self._stadium_scopes
        if index is None:
            if len(written) != 1:
                return None
            index, text = 0, self.say(written[0][0])
        if not (0 <= index < len(written) and self.say(written[index][0]) == text):
            self.app.log(f"In-game menu: stadium scope '{text}' is not the one written; ignored")
            return None
        _label, section, key = written[index]
        now, _default = self.stadium_scopes()
        if (section, key) not in {(s, k) for _l, s, k in now}:
            self.app.log(f"In-game menu: stadium for [{section}] {key} ignored (the match context changed)")
            return None
        return section, key

    def _stadium_saves(self, fields: dict[str, tuple[int, str]]) -> bool:
        """The Estadio tab's "Guardar"s (SV<n>_<row>, in order) and its match rows. True if anything changed."""
        saves: dict[int, dict[str, tuple[int, str]]] = {}
        for name, value in fields.items():
            m = SAVE_FIELD.match(name)
            if m:
                saves.setdefault(int(m.group(1)), {})[m.group(2)] = value
        changed = False
        for n in sorted(saves):
            changed = self._stadium_save(saves[n]) or changed
        return self._match_choices(fields) or changed

    def _stadium_remove(self, section: str, key: str, text: str) -> bool:
        """"Quitar": the stadium's entry goes from the key's value (the key goes with the last one; its packs stay,
        they belong to the stadium) and so does a match choice of it. Saved here. True if settings.ini changed."""
        ini = self.app.settings_ini
        entries = self.stadium_entries(section, key)
        rest = [entry for entry in entries if entry[0] != text]
        fixed_changed = False
        if read_fixed_stadium(ini, section, key) == text:
            write_fixed_stadium(ini, section, key, None)   # saved
            fixed_changed = True
            self.app.log(f"In-game menu: fixed stadium on [{section}] {key} removed ({text} removed)")
        if len(rest) == len(entries):
            return fixed_changed
        if rest:
            value = ",".join(field for entry in rest for field in entry)
            ini.write(key, value, section)
            ini.save()
            self.app.log(f"In-game menu assignment: [{section}] {key}={value} ({text} removed)")
        else:
            ini.delete_key(key, section)   # reloads from disk: nothing pending here
            ini.save()
            self.app.log(f"In-game menu assignment: [{section}] {key} removed ({text} was the last)")
        return True

    def _stadium_save(self, fields: dict[str, tuple[int, str]]) -> bool:
        """One "Guardar", as the F12 overlay's stadium wizard (app_overlay._activate_wizard_step's last step): the
        packs (goalpost model/texture, net mesh, entrance camera) first, in their own sections keyed by the stadium
        (assignment_runtime._write_stadium_goalpost_overrides: deletes saved one by one, then the writes), then
        the scope's value with this stadium's entry "<stadium>,<police>,<pitch>,<net>": in its place if it was
        assigned already, else appended (max 64, the oldest goes). Saved here. True if settings.ini changed."""
        if STADIUM_ROW not in fields:
            return False
        scope = self._stadium_scope(*fields[SCOPE_ROW]) if SCOPE_ROW in fields else self._stadium_scope(None, None)
        if scope is None:
            return False
        section, key = scope
        text = fields[STADIUM_ROW][1]
        if f"{STADIUM_ROW}DEL" in fields:
            return self._stadium_remove(section, key, text)
        if text not in self.stadium_names():
            self.app.log(f"In-game menu: stadium '{text}' is not in StadiumGBD; ignored")
            return False
        ini = self.app.settings_ini
        entries = self.stadium_entries(section, key)
        old = {name: (police, pitch, net) for name, police, pitch, net in entries}
        triple = list(old.get(text, OVERLAY_DEFAULTS))
        overrides: dict[str, str] = {}
        for n, (row, _title, _desc, kind, where) in enumerate(STADIUM_OPTIONS):
            if row not in fields:
                continue
            chosen = fields[row][1]
            if chosen not in [self.say(v) for v in self.option_values(row)]:
                self.app.log(f"In-game menu: {row} '{chosen}' is not in its list; kept as it was")
                continue
            if kind == "triple":
                triple[n] = chosen
            else:
                overrides[where[1]] = "None" if chosen == self.say(self.t("none")) else chosen
        changed = False
        current_packs = {sec: (ini.read(text, sec).strip() or "None") for sec in overrides}
        if any(current_packs[sec] != value for sec, value in overrides.items()):
            from .assignment_runtime import AssignmentRuntime
            writer = getattr(self.app, "assignment_runtime", None) or AssignmentRuntime(self.app)
            writer._write_stadium_goalpost_overrides([text], overrides)   # saved (before the write below)
            changed = True
            self.app.log(f"In-game menu assignment: packs of {text}: {overrides}")
            entries = self.stadium_entries(section, key)
        entry = (text, *triple)
        if text in old:
            new_entries = [entry if name == text else (name, *rest) for name, *rest in entries]
        else:
            new_entries = list(entries)
            if len(new_entries) >= MAX_STADIUMS:
                new_entries.pop(0)
            new_entries.append(entry)
        value = ",".join(field for e in new_entries for field in e)
        old_value = ",".join(field for e in entries for field in e)
        if value != old_value:
            ini.write(key, value, section)
            ini.save()
            changed = True
            self.app.log(f"In-game menu assignment: [{section}] {key}={value}")
        return changed

    def _match_choices(self, fields: dict[str, tuple[int, str]]) -> bool:
        """"Estadio del partido" per scope: saved in settings.ini [FixedStadium] (write_fixed_stadium), kept for
        every match of that assignment; "Selector/Al azar" removes it. True if a choice changed."""
        ini = self.app.settings_ini
        changed = False
        for field, (index, text) in fields.items():
            m = MATCH_FIELD.match(field)
            if not m:
                continue
            if m.group(1):   # the scope's index in the data (the record carries no scope label here)
                g = int(m.group(1))
                if g >= len(self._stadium_scopes):
                    continue
                scope = self._stadium_scope(g, self.say(self._stadium_scopes[g][0]))
            else:
                scope = self._stadium_scope(None, None)
            if scope is None:
                continue
            section, key = scope
            before = self.match_choice(section, key)
            assigned = [entry[0] for entry in self.stadium_entries(section, key)]
            if index == 0 or text == self.say(self.t("random")):
                after = None
            elif text in assigned:
                after = text
            else:
                self.app.log(f"In-game menu: match stadium '{text}' is not assigned to [{section}] {key}; ignored")
                continue
            if after != before:
                write_fixed_stadium(ini, section, key, after)   # saved
                changed = True
                self.app.log(f"In-game menu: fixed stadium on [{section}] {key}: {after or self.say(self.t('random'))}")
        return changed


def fixed_stadium_key(section: str, key: str) -> str:
    """The [FixedStadium] key of one stadium assignment: "<section>_<key>" (stadium_241, comp_12)."""
    return f"{str(section).strip().lower()}_{str(key).strip()}"


def read_fixed_stadium(ini, section: str, key: str) -> str | None:
    """The stadium "Estadio del partido" fixed for [section] key, or None (Selector/Al azar)."""
    try:
        return ini.read(fixed_stadium_key(section, key), FIXED_STADIUM_SECTION).strip() or None
    except Exception:  # noqa: BLE001
        return None


def write_fixed_stadium(ini, section: str, key: str, stadium: str | None) -> None:
    """Fix (or with None, unfix) the stadium of [section] key in [FixedStadium]; saved here. The delete is saved on
    its own (SessionIniFile.delete_key reloads from disk and would drop pending writes)."""
    name = fixed_stadium_key(section, key)
    if stadium:
        ini.write(name, stadium, FIXED_STADIUM_SECTION)
    else:
        ini.delete_key(name, FIXED_STADIUM_SECTION)
    ini.save()


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
