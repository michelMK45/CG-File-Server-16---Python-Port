"""The in-game CGFS16 menu's Equipaciones tab (docs/ingame-menu.md): which saved Team Kits combination each side
of the match uses.

Two plain rows, one per side, both always in the menu's record (a scope row + a dependent row would only send the
side on screen): KITS = the home team (HID), KITSAWAY = the away team (AID). Values: the original kits, then the
team's combinations in file order (KitClassicRuntime, team_<id>.lua); selected = the side's KM_HOME / KM_AWAY.
Each value has a picture: the drawing the F7-F10 kit hotkeys' carousel makes (kit_classic_editor.preview_parts),
contained in the menu's 320x180 image as a DDS under data/ui/cgfs16/img/kit/, named after the drawing's cache PNG
(new kit files -> new name). Pictures are made in a worker; until then a value shows the kit placeholder.

BACK saves both sides through KitClassicRuntime.save, as the hotkeys do, when the record still matches what was
written (same teams, same combinations in the same order). Not settings.ini: no apply_all_runtime(); Rev Mod
reads the team file when the match loads.
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Optional

from . import ingame_images
from .kit_classic_editor import AWAY, HOME, load_team, preview_parts, usual_slot

if TYPE_CHECKING:
    from .ingame_menu_runtime import InGameMenuRuntime

HOME_ROW, AWAY_ROW = "KITS", "KITSAWAY"    # KITS: the tab's own row name (menudata's default row of a tab)
ROWS = ((HOME_ROW, HOME, "HID", "kits_home"), (AWAY_ROW, AWAY, "AID", "kits_away"))
ART_SIZE = 170                              # the drawing's size, inside the menu's 320x180 picture
IMAGE_KIND = "kit"                          # data/ui/cgfs16/img/kit/
PLACEHOLDER_REL = "cgfs16/img/kit/placeholder.dds"

Sources = tuple[Optional[Path], Optional[Path], Optional[Path]]


class InGameKits:
    def __init__(self, menu: "InGameMenuRuntime") -> None:
        self.menu = menu
        self.app = menu.app
        self.written: dict[str, tuple[int, list[str]]] = {}   # row -> (team, its labels as written)
        self._jobs: list[Sources] = []                         # the drawings the last data asked for
        self.pictures_busy = False
        self.applying = False   # a menu save is being applied: its own saves don't rewrite the data
        # team -> every list of combinations written since the menu last opened (_identity): the record only
        # says index + name and names can repeat, so a list that changed meanwhile is not trusted
        self._seen: dict[int, set[str]] = {}
        self._current: dict[int, str] = {}   # team -> its list in the last data

    def _runtime(self):
        return getattr(self.app, "kit_classic", None)

    # --- app -> menu ---------------------------------------------------------------------------
    def lines(self) -> tuple[list[str], dict[str, list[str]], dict[str, int]]:
        """Data lines, values and selection of the Equipaciones tab."""
        from .ingame_menu_runtime import _clean, _context
        t = self.menu.t
        self.written = {}
        self._jobs = []
        teams = {row: _context(self.app, attr) for row, _side, attr, _title in ROWS}
        if not (teams[HOME_ROW] and teams[AWAY_ROW]):
            return [f"TITLE_{HOME_ROW}=" + t("tab_kits"), f"DESC_{HOME_ROW}=" + t("kits_desc")], \
                {HOME_ROW: [t("no_match")]}, {HOME_ROW: 0}
        runtime = self._runtime()
        lines = [f"ROWS_{HOME_ROW}={HOME_ROW}|{AWAY_ROW}"]
        values: dict[str, list[str]] = {}
        selected: dict[str, int] = {}
        supported = runtime is not None and runtime.is_supported()
        loaded = {}
        missing = False
        for row, side, _attr, title in ROWS:
            team = teams[row]
            try:
                name = self.app._resolve_team_name(team) or ""
            except Exception:  # noqa: BLE001
                name = ""
            lines.append(f"TITLE_{row}=" + t(title, team=name or team))
            if not supported:
                lines.append(f"DESC_{row}=" + t("kits_desc"))
                values[row], selected[row] = [t("kits_unsupported")], 0
                continue
            number = int(team)
            if number not in loaded:
                loaded[number] = load_team(runtime, number)
                self._current[number] = _identity(loaded[number])
                self._seen.setdefault(number, set()).add(self._current[number])
            tc = loaded[number]
            labels = [t("kits_original")] + [_clean(c.name) for c in tc.items]
            choice = tc.selection_valid(tc.home if side == HOME else tc.away)
            lines.append(f"DESC_{row}=" + t("kits_desc" if tc.items else "kits_none"))
            images = []
            for combo in [None, *tc.items]:
                sources = runtime.kit_sources(number, *preview_parts(combo, 0, usual_slot(side)))
                rel = self._picture_rel(runtime, sources)
                if rel is None:
                    missing = True
                    rel = self._placeholder_rel()
                if sources not in self._jobs:
                    self._jobs.append(sources)
                images.append(rel)
            lines.append(f"IMG_{row}=" + "|".join(images))
            values[row], selected[row] = labels, 0 if choice is None else choice + 1
            self.written[row] = (number, labels)
        if missing and not self.pictures_busy:
            self.start_pictures()
        return lines, values, selected

    def menu_opened(self) -> None:
        """FIFA has just read data.big (the menu page came up): only the lists in it count from now on."""
        self._seen = {team: {identity} for team, identity in self._current.items()}

    def jobs(self) -> list[Sources]:
        """The sources of every value's drawing in the last data (deduped)."""
        return list(self._jobs)

    def _picture_rel(self, runtime, sources: Sources) -> Optional[str]:
        """The menu's path of a drawing's picture when it exists, else None."""
        png = self._png(runtime, sources)
        if png is None:
            return None
        rel = ingame_images.asset_image_rel(IMAGE_KIND, png.name)
        return rel if (Path(self.app.exedir) / "data" / "ui" / rel).exists() else None

    @staticmethod
    def _png(runtime, sources: Sources) -> Optional[Path]:
        with runtime.art_lock:
            return runtime.art.drawing_path(*sources, size=ART_SIZE)

    def _placeholder_rel(self) -> str:
        return PLACEHOLDER_REL if (Path(self.app.exedir) / "data" / "ui" / PLACEHOLDER_REL).exists() else ""

    # --- menu -> app ---------------------------------------------------------------------------
    def apply(self, fields: dict[str, tuple[int, str]]) -> list[int]:
        """The record's KITS / KITSAWAY into the teams' files (Tk thread). A side is ignored (logged) unless its
        index and text are what the data offered, its team is still the side's and the team's combinations are
        still those. A team playing itself is saved once with both sides. Returns the teams saved."""
        runtime = self._runtime()
        if runtime is None:
            return []
        self.applying = True
        try:
            return self._apply(runtime, fields)
        finally:
            self.applying = False
            self._seen = {}   # the data written after the save starts the next visit's lists

    def _apply(self, runtime, fields: dict[str, tuple[int, str]]) -> list[int]:
        from .ingame_menu_runtime import _clean, _context
        wanted: dict[int, list[tuple[int, str, Optional[int], str]]] = {}   # team -> [(side, side name, sel, label)]
        for row, side, attr, _title in ROWS:
            if row not in fields or row not in self.written:
                continue
            team, labels = self.written[row]
            index, text = fields[row]
            side_name = "home" if side == HOME else "away"
            if not (0 <= index < len(labels) and self.menu.say(labels[index]) == text):
                self.app.log(f"In-game menu: kits '{text}' for team {team} ({side_name}) is not the one written; ignored")
                continue
            if _context(self.app, attr) != str(team):
                self.app.log(f"In-game menu: kits for team {team} ({side_name}) ignored (the match context changed)")
                continue
            wanted.setdefault(team, []).append((side, side_name, None if index == 0 else index - 1, text))
        saved = []
        for team, choices in wanted.items():
            tc = load_team(runtime, team)
            now = [self.menu.t("kits_original")] + [_clean(c.name) for c in tc.items]
            changed_meanwhile = bool(self._seen.get(team, set()) - {_identity(tc)})
            if changed_meanwhile or any(now != self.written[row][1] for row, _s, _a, _t in ROWS
                                        if row in self.written and self.written[row][0] == team):
                self.app.log(f"In-game menu: kits for team {team} ignored (its combinations changed in the app)")
                continue
            changed = []
            for side, side_name, selection, text in choices:
                if tc.selection_valid(tc.home if side == HOME else tc.away) == selection:
                    continue
                if side == HOME:
                    tc.home = selection
                else:
                    tc.away = selection
                changed.append((side_name, text))
            if not changed:
                continue
            try:
                runtime.save(tc)
            except Exception as exc:  # noqa: BLE001 - the menu's other choices still apply
                self.app.log(f"In-game menu: could not save team {team}'s kits: {exc}")
                continue
            for side_name, text in changed:
                self.app.log(f"In-game menu: team {team} ({side_name}) now uses {text}")
            saved.append(team)
            view = getattr(self.app, "kit_classic_view", None)
            if view is not None:
                try:
                    view.invalidate(team)
                except Exception as exc:  # noqa: BLE001
                    self.app.log(f"In-game menu: could not refresh the Kits > Team tab: {exc}")
        return saved

    # --- pictures ------------------------------------------------------------------------------
    def make_pictures(self, jobs: list[Sources], failures: Optional[list[str]] = None) -> int:
        """Draws every job missing its picture (and the placeholder) under data/ui/cgfs16/img/kit/; returns how
        many files were made. A drawing that fails is skipped (its value keeps the placeholder) and reported
        in `failures` (from the worker: app.log touches Tk), else logged."""
        from .file_tools import kit_ui_placeholder_path
        exedir = Path(self.app.exedir)
        made = 0
        source = kit_ui_placeholder_path()
        if source is not None and ingame_images.ensure_placeholder(exedir, source, PLACEHOLDER_REL):
            made += 1
        runtime = self._runtime()
        if runtime is None:
            return made
        for sources in jobs:
            try:
                png = self._png(runtime, sources)
                if png is None:
                    continue
                target = ingame_images.asset_image_file(exedir, IMAGE_KIND, png.name)
                if target.exists():
                    continue
                with runtime.art_lock:
                    png = runtime.art.render_path(*sources, size=ART_SIZE)
                if png is None:
                    continue
                ingame_images.make_contained(png, target)
                made += 1
            except Exception as exc:  # noqa: BLE001 - the other kits still get theirs
                message = f"In-game menu: kit preview failed ({sources[0]}): {exc}"
                if failures is None:
                    self.app.log(message)
                else:
                    failures.append(message)
        return made

    def start_pictures(self) -> None:
        """make_pictures for the last data's jobs in a worker thread (one at a time); the result reaches
        on_pictures_done through the app's worker queue ("ingame_menu_kit_images")."""
        import threading
        if self.pictures_busy:
            return
        self.pictures_busy = True
        jobs = self.jobs()

        def work() -> None:
            failures: list[str] = []
            try:
                made = self.make_pictures(jobs, failures)
                self.app._worker_queue.put(("ingame_menu_kit_images", made, None, failures))
            except Exception as exc:  # noqa: BLE001 - reported on the Tk thread
                self.app._worker_queue.put(("ingame_menu_kit_images", 0, str(exc), failures))

        threading.Thread(target=work, name="ingame-menu-kits", daemon=True).start()
        self.app._schedule_worker_poll()

    def on_pictures_done(self, made: int, error: Optional[str], failures: tuple[str, ...] | list[str] = ()) -> None:
        """Tk thread: the worker's failures are logged; the data is written again when new pictures are there."""
        self.pictures_busy = False
        for message in failures:
            self.app.log(message)
        if error:
            self.app.log(f"In-game menu: kit previews failed: {error}")
            return
        if made:
            self.app.log(f"In-game menu: kit previews ready ({made} new)")
            self.menu.write_data("kit previews", force=True)


def _identity(tc) -> str:
    """A team's list of combinations (names and mixes, in order), to tell whether it changed."""
    return repr([(c.name, c.mixes) for c in tc.items])
