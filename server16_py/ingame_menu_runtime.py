"""The CGFS16 menu inside FIFA 16's own interface (cgfs-ingame project): the app's side of the link.

The menu (Customise > Edit Teams > CGFS16) is a FIFA 16 screen of ours. It talks to the app in two ways,
both proven in-game with a stand-in (cgfs-ingame docs/fase3-conexion.md, pruebas 4-6b):

  app -> menu   data/ui/cgfs16/data.big: a one-frame Apt movie the menu loads with loadMovie every time it
                opens. Its data is one text of "KEY=value" lines (row values, the current selection, ACK),
                written into a fixed template (resources/ingame/data_template.big) by ingame_datafile.render.
                FIFA re-reads it on every visit, so it can be rewritten while FIFA runs.
  menu -> app   on "Guardar y salir" the menu leaves "CGFS16OUT|v1|<seq>|NAME=<index>:<text>|...|END" in
                ActionScript memory; when the page 'game/screens/cgfs16/CGFS16Menu' is left, a worker thread
                scans FIFA's memory read-only for the newest record (ingame_recordscan, ~3.5 s for ~3.7 GB the
                first time, then the regions where records were seen first).

What the rows mean here (first version): Marcador and Logo TV are the Default / Friendly assignments, the
same [Scoreboard]/[TVLogo] key "0" of FSW/settings.ini as the F12 menu's "Default / Friendly" scope; index 0
is "default" (no assignment). Estadio, Vídeos and Equipaciones depend on a match or a team and are not
wired yet: they show one "Próximamente" value and their saves are ignored.

ACK=<seq>: the last save the app processed. Until the app has seen a save, the menu keeps its own choice
over the app's selection (a quick re-entry used to show the previous one, prueba 6).
Does nothing unless the menu is installed in the game (data/ui/game/screens/cgfs16/cgfs16menu.big).
"""
from __future__ import annotations

import datetime
import threading
from pathlib import Path
from typing import TYPE_CHECKING

from . import ingame_datafile, ingame_recordscan
from .file_tools import _bundled_resource_path

if TYPE_CHECKING:
    from .app import Server16App

MENU_PAGE = "game/screens/cgfs16/CGFS16Menu"
MENU_MOVIE = Path("data/ui/game/screens/cgfs16/cgfs16menu.big")
DATA_MOVIE = Path("data/ui/cgfs16/data.big")
TEMPLATE = "ingame/data_template.big"
DEFAULT_LABEL = "Por defecto (FIFA 16)"
NOT_YET = "Próximamente"
# menu row -> (settings.ini section, attribute of the app with the packs' folder); key "0" = Default/Friendly
DEFAULT_ROWS = {
    "SCOREBOARD": ("Scoreboard", "ScoreBoard"),
    "TVLOGO": ("TVLogo", "TVLogo"),
}
OTHER_ROWS = ("STADIUM", "MOVIES", "KITS")
DEFAULT_KEY = "0"


class InGameMenuRuntime:
    def __init__(self, app: "Server16App") -> None:
        self.app = app
        self.last_seq = 0        # the newest menu save processed in this FIFA session
        self.hot: list[tuple[int, int]] = []  # memory regions where save records were found
        self.busy = False        # a scan is running in a worker thread
        self._pid: int | None = None
        self._written: str | None = None  # the last data text written (without its STAMP line)
        self._template: bytes | None = None

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
        """(values per row, selected index per row) from the app's packs and settings.ini."""
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

    # --- app -> menu ---------------------------------------------------------------------------
    def write_data(self, reason: str, force: bool = False) -> bool:
        """Writes data.big if the data changed (or force). True if written."""
        if not self.installed():
            return False
        values, selected = self.rows()
        stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        text = ingame_datafile.encode(values, selected, source="CG Server 16", stamp=stamp, ack=self.last_seq)
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
        self.app.log(f"In-game menu: data.big written ({reason}): {shown}, ack={self.last_seq}")
        return True

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
        self.apply(dict(fields))
        self.last_seq = seq
        self.write_data(f"after save #{seq}", force=True)

    def apply(self, fields: dict[str, tuple[int, str]]) -> None:
        """Writes the menu's choices for the wired rows into settings.ini (Default/Friendly key "0").
        The index refers to the lists in data.big; the text decides if the lists moved since."""
        values, _selected = self.rows()
        ini = self.app.settings_ini
        writes: list[tuple[str, str]] = []
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
                    self.app.log(f"In-game menu assignment: [{section}] {DEFAULT_KEY} reset to default")
            elif names[index] != current:
                writes.append((section, names[index]))
        for section, value in writes:
            ini.write(DEFAULT_KEY, value, section)
            self.app.log(f"In-game menu assignment: [{section}] {DEFAULT_KEY}={value}")
        if writes:
            ini.save()


def _pack_names(folder) -> list[str]:
    """Pack folders, as the F12 menu lists them; names the data text cannot carry are left out."""
    if folder is None:
        return []
    p = Path(folder)
    if not p.is_dir():
        return []
    return sorted(d.name for d in p.iterdir() if d.is_dir() and not any(c in d.name for c in "|=\n"))
