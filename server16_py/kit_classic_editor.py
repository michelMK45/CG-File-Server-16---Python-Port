"""One half of the F12 overlay's Team Kits editor (PES 6 style), without Tk or
overlay state: a team playing as the home or the away side, the combination it
uses on that side, the kit being looked at, its three garments and the forced
goalkeeper.

Same rules and same file as the Python Kits > Team tab (kit_classic_tab.py): the
choices come from KitClassicRuntime and every save goes through
KitClassicRuntime.save, so what is made here is exactly what the tab would make.
Like the tab, the side's combination and goalkeeper are saved as soon as they
change, while the garments are only a preview until commit() (the tab's "Add
mix" button). The overlay maps its controls onto cycle()/commit() and draws the
garments from layer_sources().
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Callable, Optional, Union

from .kit_classic import Combination, Mix, TeamCombinations

if TYPE_CHECKING:
    from .kit_classic import KitClassicRuntime

HOME, AWAY = 0, 1

ROW_COMBINATION, ROW_KIT, ROW_SHIRT, ROW_SHORTS, ROW_SOCKS, ROW_GK = range(6)
ROWS = (ROW_COMBINATION, ROW_KIT, ROW_SHIRT, ROW_SHORTS, ROW_SOCKS, ROW_GK)
PART_ROWS = (ROW_SHIRT, ROW_SHORTS, ROW_SOCKS)

# Combination-row entry after the saved combinations: "+ New combination",
# created by commit().
NEW = "new"

Cursor = Union[None, int, str]   # None = original kits, int = combination index, NEW


def load_team(runtime: "KitClassicRuntime", team: int) -> TeamCombinations:
    """The team's combinations (an empty set when its lua has no block yet).

    A home/away pointing past the combinations (a new TeamCombinations starts at
    0) is stored as None: otherwise the first combination one side creates would
    silently become the other side's too. The file doesn't change, both are
    written as the original kits (KM_HOME/KM_AWAY = 0)."""
    tc = runtime.load(team) or TeamCombinations(team)
    tc.home, tc.away = tc.selection_valid(tc.home), tc.selection_valid(tc.away)
    return tc


def open_sides(runtime: "KitClassicRuntime", home_team: int, away_team: int,
               default_name: Optional[Callable[[int], str]] = None) -> tuple["TeamKitSide", "TeamKitSide"]:
    """Both halves for a match. A team playing itself gets one TeamCombinations for
    both, so a save from either half keeps what the other half saved."""
    home_tc = load_team(runtime, home_team)
    away_tc = home_tc if away_team == home_team else load_team(runtime, away_team)
    return (TeamKitSide(runtime, home_team, HOME, home_tc, default_name),
            TeamKitSide(runtime, away_team, AWAY, away_tc, default_name))


def usual_slot(side: int) -> int:
    """The kit a side usually asks for. The one actually chosen in FIFA's kit menu
    can't be read from Python."""
    return 0 if side == HOME else 1


def preview_mix(combo: Optional[Combination], tourn: int, slot: int) -> Optional[Mix]:
    """The mix that shows `combo` best when kit `slot` (of tournament `tourn`) is
    the one looked at: its mix for that kit, else another kit of that tournament
    it mixes (lowest first), else one of another tournament — so a combination
    that only changes another kit doesn't look like the original kits. None for
    the original kits or a combination that mixes nothing."""
    mixes = [m for m in combo.mixes if not m.is_identity] if combo is not None else []
    if not mixes:
        return None
    return min(mixes, key=lambda m: (m.key != (tourn, slot), m.tourn != tourn, m.tourn, m.slot))


def preview_parts(combo: Optional[Combination], tourn: int, slot: int) -> tuple[int, int, int, int]:
    """(tourn, shirt, shorts, socks) that show `combo` in one small drawing (the
    kit hotkeys' carousel, `slot` = the kit the side usually asks for): the
    preview_mix's, else kit `slot` itself."""
    mix = preview_mix(combo, tourn, slot)
    if mix is None:
        return tourn, slot, slot, slot
    return mix.tourn, mix.shirt, mix.shorts, mix.socks


def _step(choices: list, current, direction: int):
    """The choice `direction` steps away from `current`, wrapping around. A value
    that isn't offered (a kit set by hand or by Dinei's tool that isn't loose
    here) is placed among the sorted choices first, so the step starts from it."""
    if current not in choices:
        choices = sorted(set(choices) | {current})
    return choices[(choices.index(current) + direction) % len(choices)]


class TeamKitSide:
    def __init__(self, runtime: "KitClassicRuntime", team: int, side: int,
                 tc: Optional[TeamCombinations] = None,
                 default_name: Optional[Callable[[int], str]] = None) -> None:
        self.runtime = runtime
        self.team = team
        self.side = side
        self.tc = tc if tc is not None else load_team(runtime, team)
        # Name of the n-th combination (the overlay passes tr("kitclassic.default_name")).
        self.default_name = default_name or (lambda n: f"Combination {n}")
        self.tourn = 0
        # The kit looked at: the one the side usually asks for (the kit row lets
        # the user pick another), unless its combination only mixes others.
        self.slot = usual_slot(side)
        self._new = False
        self._follow_combination()
        self.parts: tuple[int, int, int] = self.saved_parts

    # -- state ---------------------------------------------------------------------
    @property
    def editable(self) -> bool:
        return self.runtime.is_supported()

    @property
    def selection(self) -> Optional[int]:
        """The side's saved combination (index), None for the original kits."""
        return self.tc.selection_valid(self.tc.home if self.side == HOME else self.tc.away)

    @property
    def combination_cursor(self) -> Cursor:
        return NEW if self._new else self.selection

    def combination_choices(self) -> list[Cursor]:
        return [None, *range(len(self.tc.items)), NEW]

    @property
    def combination(self) -> Optional[Combination]:
        """The combination the garments belong to: None for the original kits and
        on NEW (nothing saved in it yet)."""
        selection = self.selection
        return None if self._new or selection is None else self.tc.items[selection]

    @property
    def saved_parts(self) -> tuple[int, int, int]:
        combo = self.combination
        return combo.parts_for(self.tourn, self.slot) if combo else (self.slot, self.slot, self.slot)

    @property
    def pending(self) -> bool:
        """Garments changed but not committed yet."""
        return self.parts != self.saved_parts

    @property
    def gk(self) -> Optional[int]:
        return self.tc.gk_home if self.side == HOME else self.tc.gk_away

    def kit_choices(self) -> list[int]:
        return self.runtime.kit_type_choices(self.team, self.tourn)

    def gk_choices(self) -> list[Optional[int]]:
        return self.runtime.gk_choices(self.team, self.gk)

    def conflicts(self) -> list[tuple[int, int]]:
        return self.tc.side_conflicts()

    def layer_sources(self) -> dict[str, Optional[Path]]:
        """Kit file each garment shown is drawn from (None = grey), by layer name
        (kit_classic_art.ART_LAYERS)."""
        shirt, shorts, socks = self.runtime.kit_sources(self.team, self.tourn, *self.parts)
        return {"shirt": shirt, "shorts": shorts, "socks": socks}

    def gk_layer_sources(self) -> Optional[dict[str, Optional[Path]]]:
        """Same for the forced goalkeeper kit; None when it is automatic."""
        gk = self.gk
        if gk is None:
            return None
        path = self.runtime.kit_path(self.team, 0, gk)
        return {"shirt": path, "shorts": path, "socks": path}

    # -- editing -------------------------------------------------------------------
    def cycle(self, row: int, direction: int) -> bool:
        """Move `row` one choice in `direction` (+1/-1). Returns True when this
        saved the team's lua (combination and goalkeeper rows). The kit row only
        changes what is shown and works without editing support; the garment rows
        change the preview, saved by commit()."""
        if row == ROW_KIT:
            self.slot = _step(self.kit_choices(), self.slot, direction)
            self.parts = self.saved_parts
            return False
        if not self.editable:
            return False
        if row == ROW_COMBINATION:
            return self._cycle_combination(direction)
        if row in PART_ROWS:
            index = PART_ROWS.index(row)
            parts = list(self.parts)
            parts[index] = _step(self.kit_choices(), parts[index], direction)
            self.parts = (parts[0], parts[1], parts[2])
            return False
        if row == ROW_GK:
            current = self.gk
            target = _step(self.gk_choices(), current, direction)
            if target == current:
                return False
            if self.side == HOME:
                self.tc.gk_home = target
            else:
                self.tc.gk_away = target
            return self._save()
        raise ValueError(f"unknown row: {row}")

    def _cycle_combination(self, direction: int) -> bool:
        target = _step(self.combination_choices(), self.combination_cursor, direction)
        self._new = target == NEW
        changed = not self._new and target != self.selection
        if changed:
            self._set_selection(target)
        self._follow_combination()
        self.parts = self.saved_parts   # uncommitted garments are dropped
        return self._save() if changed else False

    def step_saved_combination(self, direction: int) -> bool:
        """Moves the side's combination one step through the original kits and the
        saved combinations only (no NEW) and saves it: the F7-F10 kit hotkeys with
        F11 on "Team combination". Returns True when it saved; False without
        editing support or with nothing else to step to."""
        if not self.editable:
            return False
        current = self.selection
        target = _step([None, *range(len(self.tc.items))], current, direction)
        self._new = False
        if target != current:
            self._set_selection(target)
        self._follow_combination()
        self.parts = self.saved_parts
        return self._save() if target != current else False

    def commit(self) -> bool:
        """Saves the garments shown for the current kit into the side's combination
        (the tab's "Add mix"). On NEW, or with changed garments while the side uses
        the original kits, a new combination is created first and becomes the
        side's. Returns True when it saved."""
        if not self.editable:
            return False
        pending = self.pending
        if not self._new and not pending:
            return False
        combo = self.combination
        if combo is None:
            combo = Combination(self.tc.unique_name(self.default_name(len(self.tc.items) + 1)))
            self.tc.items.append(combo)
            self._set_selection(len(self.tc.items) - 1)
            self._new = False
        if pending:
            combo.set_mix(Mix(self.tourn, self.slot, *self.parts))
        return self._save()

    def _follow_combination(self) -> None:
        """Moves the kit row to a kit the side's combination mixes when it doesn't
        mix the one looked at (preview_mix), so the drawing shows the combination:
        one that only mixes kit 3 used to open on kit 0 and show it untouched, the
        original kit, while the tab's cards showed the mix. Kits of the
        tournament looked at only (the editor has no tournament row)."""
        mix = preview_mix(self.combination, self.tourn, self.slot)
        if mix is not None and mix.tourn == self.tourn:
            self.slot = mix.slot

    def _set_selection(self, selection: Optional[int]) -> None:
        if self.side == HOME:
            self.tc.home = selection
        else:
            self.tc.away = selection

    def _save(self) -> bool:
        """Raises like KitClassicRuntime.save; the change stays in memory, so the
        caller can show the error and open the sides again to drop it."""
        self.runtime.save(self.tc)
        return True
