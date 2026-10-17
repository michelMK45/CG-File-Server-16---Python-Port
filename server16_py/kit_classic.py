"""Kits > Team ("Team Kits"; "Classic" in the code, its name until 2026-10-17):
per-team kit combinations built only from a team's OWN kits.

Ported from Dinei's standalone Kit Mixer (FIFA 16 Revolution Mod). Unlike the
Advanced tab (KitMixRuntime), nothing here touches a .rx3: each team's
data/fifarna/lua/assignments/teams/team_<id>.lua gets one marker-delimited block
that registers

    swapTeamKit(team, slot, 4000000 + shirt*10000 + shorts*100 + socks)

for every requested kit slot a combination changes. Rev Mod V1.3.5+'s player.lua
reads it back through getSwapKit and splits the number again with
getIndividualKitPart, so the engine draws shirt, shorts and socks from three
different kits of the same team. A team can hold several named combinations; the
block carries all of them plus a small Lua snippet that checks, when the file
runs, whether the team is the home side (wvPlayer 9) or the away side (wvPlayer
20) and registers combination KM_HOME or KM_AWAY -- or both, when the team plays
itself (see the comment above _GK_APPLY).

The lines both tools parse (markers, KM_HOME/KM_AWAY and KM_GKH/KM_GKA, the
`if KM_SEL == n then -- name` branches, swap lines and the kitmixer:reset lines)
keep Dinei's format, so a team_<id>.lua written by either one is read correctly by
the other. Differences: his tool writes the same KM_HOME/KM_AWAY into every team,
while here each team keeps its own choice; his snippet applies only the home
combination when a team plays itself; and this block also undoes what an earlier
version of it left in the game (_CLEANUP).

V1.0 player.lua (the one CGFS bundled before 2026-10-16) has swapTeamKit but no
getIndividualKitPart: it would hand the raw 4000100-style code to the engine as a
kit type. KitClassicRuntime.missing_player_lua_functions() is the gate the UI uses
to refuse saving in that case.
"""

from __future__ import annotations

import os
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Iterable, Optional

from .kit_classic_art import IconFactory

if TYPE_CHECKING:
    from .app import Server16App

BLOCK_PREFIX = "-- KITMIXER:BEGIN"
BLOCK_BEGIN = BLOCK_PREFIX + " (CGFS16 Kits > Team - do not edit between the markers)"
BLOCK_END = "-- KITMIXER:END"
# Dinei's tool can also append a kit-details block (assignKitDetails from
# teamkits.txt). Classic never writes it, but whole-file restores of a team lua
# must carry it over just like the combinations block (see replace_generated_blocks).
DETAILS_PREFIX = "-- KITDETAILS:BEGIN"
DETAILS_END = "-- KITDETAILS:END"
RESET_MARK = "kitmixer:reset"

PART_BASE = 4000000
PART_MAX = 99

# Rev Mod functions the block relies on. swapTeamKit alone is not enough: V1.0
# has it too but feeds the stored number straight to the engine as a kit type.
REQUIRED_PLAYER_LUA_FUNCTIONS = ("getIndividualKitPart", "getSwapKit", "swapTeamKit", "swapTeamKitTournament")

BACKUP_DIR_NAME = "kitmixer_backups"   # same folder Dinei's tool uses, so both share one pristine backup

_RE_SWAP = re.compile(r"^\s*swapTeamKit\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)")
_RE_SWAP_T = re.compile(r"^\s*swapTeamKitTournament\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)")
_RE_BRANCH = re.compile(r"^\s*(?:else)?if\s+KM_SEL\s*==\s*(\d+)\s+then\s*(?:--\s*(.*))?$")
_RE_SEL = re.compile(r"^\s*local\s+KM_HOME\s*,\s*KM_AWAY\s*=\s*(-?\d+)\s*,\s*(-?\d+)", re.M)
_RE_GK = re.compile(r"^\s*local\s+KM_GKH\s*,\s*KM_GKA\s*=\s*(-?\d+)\s*,\s*(-?\d+)", re.M)
_RE_OLD_NAME = re.compile(r"^--\s*combinacao:\s*(.*)$", re.M)
_RE_KIT_FILE = re.compile(r"^kit_(\d+)_(\d+)_(\d+)\.rx3$", re.I)

# Goalkeeper kit types (Rev Mod), the ones offered as a forced goalkeeper kit.
GK_KITS = (2, 12, 13, 30, 31)

# How the side is chosen: like Dinei's tool, when the team file runs, from
# wvPlayer 9 (home) / wvPlayer 20 (away) -- confirmed working in matches by the
# user with his tool. Rev Mod re-runs the file on every player update and decides
# both sides' kits in the first match PlayerUpdate (idx > 7), right after the
# file of that player's team ran with the match's players in 9/20. The kit menu
# keeps stale 9/20 and doesn't re-run the file on ◀ ▶, so its preview can differ
# (the tab says so). Tried and dropped on 2026-10-17: registering every
# combination for both sides (ignores "Home uses"/"Away uses") and wrapping
# getSwapKit to read the side at lookup time (failed live for a home team, cause
# not found).

# Forced goalkeeper. Rev Mod's getGKKitColour looks up the team's precedence list
# by the kit the outfield SHIRT comes from, and a one-entry list is returned as-is,
# skipping its colour-clash check (getAltKitColour still runs afterwards). So the
# detected side's choice is registered for every outfield kit type a part code
# can name, which makes it independent of the combination being worn; a team
# playing itself (KM_BOTH) gives the away choice to the kit the away shirt comes
# from (KM_GKAK). The lists are noted in KM_GKMINE so the next run can drop them
# (see _CLEANUP). KM_GKH/KM_GKA keep Dinei's names and meaning (-1 = automatic),
# so his tool still reads the choice back.
_GK_APPLY = [
    "local KM_GK, KM_GKAK = -1, -1",
    "if km_home then KM_GK = KM_GKH elseif km_away then KM_GK = KM_GKA end",
    "if KM_BOTH then pcall(function() KM_GKAK = getIndividualKitPart(getSwapKit(%(team)d, km_ak, 0), 1) end) end",
    "KM_GKMINE = KM_GKMINE or {}",
    "KM_GKMINE[%(team)d] = {}",
    "pcall(function()",
    "local KM_GKNUM = {%(gk_set)s}",
    "for k = 0, %(max)d do",
    "if not KM_GKNUM[k] then",
    "local g = KM_GK",
    "if k == KM_GKAK then g = KM_GKA end",
    "if g >= 0 then local t = {g} assignGKKitPrecedence(%(team)d, k, 0, t) KM_GKMINE[%(team)d][k] = t end",
    "end",
    "end",
    "end)",
]

# The game keeps every swapTeamKit / assignGKKitPrecedence until the next stadium
# load (importTeamStatements), while the team file runs again on every player
# update. So whatever an earlier save registered stays in the game after it is
# removed, unless the block undoes it. Mixes: any part code (>= 4000000, only kit
# mixers write those) on a kit neither this block nor the rest of the file swaps
# goes back to the original -- value-based, so it also undoes older versions of
# this block and Dinei's tool. Keepers: the lists the previous run created
# (KM_GKMINE, compared by identity, so a list the file set again in this run is
# left alone) are dropped. KM_RES / KM_GKRES belong to the short-lived lookup
# version (getSwapKit wrapper); clearing them makes a wrapper still installed in
# the running game pass straight through.
_CLEANUP = [
    "-- Undoes what an earlier version of this block left in the game (kept until the next stadium load).",
    "if KM_RES then KM_RES[%(team)d] = nil end",
    "if KM_GKRES then KM_GKRES[%(team)d] = nil end",
    "pcall(function()",
    "local keep = {%(keep)s}",
    "for s, c in pairs(swapKit[%(team)d] or {}) do",
    "if type(c) == \"number\" and c >= %(base)d and not keep[s] then swapKit[%(team)d][s] = s end",
    "end",
    "for r, t in pairs(swapKitTourn[%(team)d] or {}) do",
    "for s, c in pairs(t) do",
    "if type(c) == \"number\" and c >= %(base)d and not keep[r * 100 + s] then t[s] = s end",
    "end",
    "end",
    "end)",
    "pcall(function()",
    "local o, old = gkKitOrder[%(team)d], KM_GKMINE and KM_GKMINE[%(team)d]",
    "if o and old then for k, t in pairs(old) do if o[k] == t then o[k] = nil end end end",
    "if KM_GKMINE then KM_GKMINE[%(team)d] = nil end",
    "end)",
]


def encode_parts(shirt: int, shorts: int, socks: int) -> int:
    """Mirror of getIndividualKitPart in Rev Mod's player.lua."""
    for value in (shirt, shorts, socks):
        if not 0 <= value <= PART_MAX:
            raise ValueError(f"kit part out of range 0..{PART_MAX}: {value}")
    return PART_BASE + shirt * 10000 + shorts * 100 + socks


def decode_parts(code: int) -> tuple[int, int, int]:
    """(shirt, shorts, socks). Numbers below PART_BASE are a plain kit type."""
    if code < PART_BASE:
        return code, code, code
    socks = code % 100
    shorts = ((code - socks) % 10000) // 100
    shirt = ((code - shorts * 100 - socks) % 1000000) // 10000
    return shirt, shorts, socks


@dataclass(frozen=True)
class Mix:
    """When the game asks for kit `slot` (in tournament `tourn`, 0 = any), draw the
    shirt, shorts and socks from these kit types of the same team."""

    tourn: int
    slot: int
    shirt: int
    shorts: int
    socks: int

    @property
    def key(self) -> tuple[int, int]:
        return self.tourn, self.slot

    @property
    def is_identity(self) -> bool:
        return self.shirt == self.shorts == self.socks == self.slot

    @property
    def code(self) -> int:
        # "original kit" (all three parts from the slot itself) is written as the
        # slot number, which every player.lua version understands.
        return self.slot if self.is_identity else encode_parts(self.shirt, self.shorts, self.socks)


@dataclass
class Combination:
    name: str
    mixes: list[Mix] = field(default_factory=list)

    def set_mix(self, mix: Mix) -> None:
        """Add `mix`, replacing any mix for the same (tourn, slot)."""
        self.mixes = [m for m in self.mixes if m.key != mix.key] + [mix]

    def remove_mix(self, key: tuple[int, int]) -> None:
        self.mixes = [m for m in self.mixes if m.key != key]


@dataclass
class TeamCombinations:
    """Every combination of one team plus which one it uses at home / away.

    `home`/`away` are 0-based indexes into `items`, or None for "original kits".
    `gk_home`/`gk_away` are the goalkeeper kit type forced when the team is the home
    / away side, or None to let the game choose (its usual colour-clash logic)."""

    team: int
    items: list[Combination] = field(default_factory=list)
    home: Optional[int] = 0
    away: Optional[int] = 0
    gk_home: Optional[int] = None
    gk_away: Optional[int] = None

    def has_mixes(self) -> bool:
        return any(c.mixes for c in self.items)

    @property
    def has_gk(self) -> bool:
        return self.gk_home is not None or self.gk_away is not None

    def unique_name(self, base: str) -> str:
        names = {c.name for c in self.items}
        if base not in names:
            return base
        n = 2
        while f"{base} ({n})" in names:
            n += 1
        return f"{base} ({n})"

    def remove(self, index: int) -> None:
        """Delete combination `index`, keeping home/away pointing at the same
        combinations (or "original kits" if theirs was the one removed)."""
        del self.items[index]

        def shift(sel: Optional[int]) -> Optional[int]:
            if sel is None or sel == index:
                return None
            return sel - 1 if sel > index else sel

        self.home = shift(self.home)
        self.away = shift(self.away)

    def selection_valid(self, sel: Optional[int]) -> Optional[int]:
        return sel if sel is not None and 0 <= sel < len(self.items) else None

    def side_conflicts(self) -> list[tuple[int, int]]:
        """(tourn, slot) keys the home and the away combination both mix, differently.
        Rev Mod keeps one swap per team and kit with no side, so only one of the two
        can be active at a time: the detected side's in a match against another team
        (the kit menu may preview the other), and the home one when the team plays
        itself with that kit on both sides."""
        home, away = self.selection_valid(self.home), self.selection_valid(self.away)
        if home is None or away is None or home == away:
            return []
        away_codes = {m.key: m.code for m in self.items[away].mixes}
        return sorted(m.key for m in self.items[home].mixes if m.key in away_codes and away_codes[m.key] != m.code)


# ---------------------------------------------------------------------------
# team_<id>.lua text
# ---------------------------------------------------------------------------

def split_marked(text: str, prefix: str, end: str) -> tuple[str, Optional[str], str]:
    """(before, block, after); block is None when the markers aren't both there.
    The block includes the line break right after its end marker."""
    b = text.find(prefix)
    if b < 0:
        return text, None, ""
    e = text.find(end, b)
    if e < 0:
        return text, None, ""
    start = text.rfind("\n", 0, b) + 1
    stop = e + len(end)
    if text.startswith("\r\n", stop):
        stop += 2
    elif text.startswith("\n", stop):
        stop += 1
    return text[:start], text[start:stop], text[stop:]


def _parse_swap_line(line: str, team: int) -> Optional[Mix]:
    m = _RE_SWAP_T.match(line)
    if m and int(m.group(1)) == team:
        return Mix(int(m.group(2)), int(m.group(3)), *decode_parts(int(m.group(4))))
    m = _RE_SWAP.match(line)
    if m and int(m.group(1)) == team:
        return Mix(0, int(m.group(2)), *decode_parts(int(m.group(3))))
    return None


def parse_team_block(text: str, team: int) -> Optional[TeamCombinations]:
    """The team's combinations as stored in its Classic block, or None when the
    file has no block. Also reads blocks written by Dinei's tool, including his
    first format (a single unnamed combination, no KM_SEL branches)."""
    _, block, _ = split_marked(text, BLOCK_PREFIX, BLOCK_END)
    if block is None:
        return None
    items: list[Combination] = []
    current: Optional[Combination] = None
    loose: list[Mix] = []
    for line in block.splitlines():
        m = _RE_BRANCH.match(line)
        if m:
            current = Combination((m.group(2) or "").strip() or f"Combination {m.group(1)}")
            items.append(current)
            continue
        if RESET_MARK in line:
            continue
        mix = _parse_swap_line(line, team)
        if mix is None:
            continue
        if current is not None:
            current.set_mix(mix)
        else:
            loose.append(mix)
    if not items and loose:
        nm = _RE_OLD_NAME.search(block)
        items = [Combination(nm.group(1).strip() if nm else "Combination 1", loose)]

    tc = TeamCombinations(team, items)
    sel = _RE_SEL.search(block)
    if sel:
        tc.home = tc.selection_valid(int(sel.group(1)) - 1)
        tc.away = tc.selection_valid(int(sel.group(2)) - 1)
    gk = _RE_GK.search(block)
    if gk:
        tc.gk_home, tc.gk_away = (v if v >= 0 else None for v in (int(gk.group(1)), int(gk.group(2))))
    return tc


def _clean_name(name: str) -> str:
    return re.sub(r"[\r\n]+", " ", name or "").strip()


def render_team_block(tc: TeamCombinations, nl: str = "\n", keep: Iterable[tuple[int, int]] = (),
                      cleanup: bool = False) -> str:
    """The Classic block for `tc`. `keep`: (tourn, slot) keys the rest of the file
    swaps, which the cleanup of earlier versions must not touch.

    With nothing to write (no mixes and no forced goalkeeper) it returns "", which
    removes the block -- unless `cleanup` (the block being replaced had mixes or a
    keeper): then a cleanup-only block stays, so whatever the old one registered
    is undone without waiting for the next stadium load. Saving again once that
    block is the old one removes it."""
    team = tc.team
    keys = sorted({m.key for c in tc.items for m in c.mixes})
    gk = tc.has_gk
    cleanup_values = {
        "team": team,
        "base": PART_BASE,
        "keep": ",".join(f"[{tourn * 100 + slot}]=true" for tourn, slot in sorted(set(keys) | set(keep))),
    }
    cleanup_lines = [ln % cleanup_values for ln in _CLEANUP]
    if not keys and not gk:
        if not cleanup:
            return ""
        lines = [
            BLOCK_BEGIN,
            "-- No combinations left: this block only undoes what an earlier version registered.",
            "local KM_HOME, KM_AWAY = 0, 0",
            *cleanup_lines,
            BLOCK_END,
        ]
        return nl.join(lines) + nl

    def swap(tourn: int, slot: int, code: int, info: str) -> str:
        if tourn == 0:
            return f"swapTeamKit({team}, {slot}, {code}) {info}"
        return f"swapTeamKitTournament({team}, {tourn}, {slot}, {code}) {info}"

    def lua_sel(sel: Optional[int]) -> int:
        sel = tc.selection_valid(sel)
        return 0 if sel is None else sel + 1

    lines = [
        BLOCK_BEGIN,
        "-- Picked per match: home uses combination KM_HOME, away KM_AWAY (1 = first, 0 = original kits).",
        f"local KM_HOME, KM_AWAY = {lua_sel(tc.home)}, {lua_sel(tc.away)}",
    ]
    if gk:
        lines.append(f"local KM_GKH, KM_GKA = {_lua_gk(tc.gk_home)}, {_lua_gk(tc.gk_away)}")
    # The game keeps the last registered swap in memory, so every slot any
    # combination touches goes back to the original kit first.
    for tourn, slot in keys:
        lines.append(swap(tourn, slot, slot, f"-- {RESET_MARK} (back to the original kit)"))
    lines += cleanup_lines
    # Side, read when the file runs (see the comment above _GK_APPLY); km_hk /
    # km_ak are the kits the home / away side asks for.
    lines += [
        "local km_home, km_away, km_hk, km_ak = false, false, -1, -1",
        "pcall(function()",
        "local as = gSportsRNA",
        'local h = as:GetTable("wvPlayer", 9)',
        'local a = as:GetTable("wvPlayer", 20)',
        f'km_home = as:GetInt(h, "teamid") == {team} or as:GetInt(h, "kit") == {team}',
        f'km_away = as:GetInt(a, "teamid") == {team} or as:GetInt(a, "kit") == {team}',
        'km_hk, km_ak = as:GetInt(h, "kitType") % 20, as:GetInt(a, "kitType") % 20',
        "end)",
    ]
    # Rev Mod picks both sides' kits at once from swapKit[team], so a team playing
    # itself (KM_BOTH) needs both combinations registered together: the away one
    # only for the kit the away side asks for, the home one for every other kit.
    # Otherwise exactly Dinei's: the detected side's combination, home first.
    lines += [
        "local KM_BOTH = km_home and km_away and km_ak >= 0 and km_hk ~= km_ak",
        "local km_swap, km_swapt = swapTeamKit, swapTeamKitTournament",
        "local function KM_APPLY(KM_SEL, km_only, km_skip)",
        "-- Inside KM_APPLY these two only register the kits this pass may change.",
        "local function swapTeamKit(t, s, c) if s ~= km_skip and (km_only < 0 or s == km_only) then km_swap(t, s, c) end end",
        "local function swapTeamKitTournament(t, r, s, c) if s ~= km_skip and (km_only < 0 or s == km_only) then km_swapt(t, r, s, c) end end",
    ]
    for i, combo in enumerate(tc.items):
        name = _clean_name(combo.name) or f"Combination {i + 1}"
        lines.append(f"{'if' if i == 0 else 'elseif'} KM_SEL == {i + 1} then -- {name}")
        if not combo.mixes:
            lines.append("-- (no mixes: original kits)")
        for m in sorted(combo.mixes, key=lambda x: x.key):
            if m.is_identity:
                info = f"-- original kit (shirt, shorts and socks of kit {m.slot})"
            else:
                info = f"-- shirt={m.shirt} shorts={m.shorts} socks={m.socks}"
            lines.append(swap(m.tourn, m.slot, m.code, info))
    if tc.items:
        lines.append("end")
    lines += [
        "end",
        "if KM_BOTH then",
        "KM_APPLY(KM_HOME, -1, km_ak)",
        "KM_APPLY(KM_AWAY, km_ak, -1)",
        "elseif km_home then",
        "KM_APPLY(KM_HOME, -1, -1)",
        "elseif km_away then",
        "KM_APPLY(KM_AWAY, -1, -1)",
        "end",
    ]
    if gk:
        values = {"team": team, "max": PART_MAX, "gk_set": ",".join(f"[{k}]=true" for k in GK_KITS)}
        lines += [ln % values for ln in _GK_APPLY]
    lines.append(BLOCK_END)
    return nl.join(lines) + nl


def _lua_gk(kit: Optional[int]) -> int:
    return -1 if kit is None else kit


def apply_team_block(text: str, tc: TeamCombinations) -> str:
    """`text` with the Classic block replaced, appended at the end, or removed.
    Everything outside the block is kept byte for byte, including CRLF endings."""
    nl = "\r\n" if "\r\n" in text else "\n"
    old = parse_team_block(text, tc.team)
    cleanup = old is not None and (old.has_mixes() or old.has_gk)
    new_block = render_team_block(tc, nl, keep=external_swap_slots(text, tc.team), cleanup=cleanup)
    before, block, after = split_marked(text, BLOCK_PREFIX, BLOCK_END)
    if block is None:
        if not new_block:
            return text
        if before and not before.endswith("\n"):
            before += nl
        return before + new_block
    return before + new_block + after


def external_swap_slots(text: str, team: int) -> set[tuple[int, int]]:
    """(tourn, slot) pairs that the file already swaps OUTSIDE the Classic block.
    The block sits at the end and runs last, so it wins, but the user should know."""
    before, _, after = split_marked(text, BLOCK_PREFIX, BLOCK_END)
    found: set[tuple[int, int]] = set()
    for chunk in (before, after):
        for line in chunk.splitlines():
            if line.lstrip().startswith("--"):
                continue
            mix = _parse_swap_line(line, team)
            if mix is not None:
                found.add(mix.key)
    return found


def _generated_blocks(text: str) -> list[str]:
    blocks = []
    for prefix, end in ((BLOCK_PREFIX, BLOCK_END), (DETAILS_PREFIX, DETAILS_END)):
        _, block, _ = split_marked(text, prefix, end)
        if block is not None:
            blocks.append(block)
    return blocks


def strip_generated_blocks(text: str) -> str:
    for prefix, end in ((BLOCK_PREFIX, BLOCK_END), (DETAILS_PREFIX, DETAILS_END)):
        before, block, after = split_marked(text, prefix, end)
        if block is not None:
            text = before + after
    return text


def replace_generated_blocks(restored: str, current: str) -> str:
    """`restored` (a whole-file backup being put back) with its Classic / kit-details
    blocks swapped for the ones `current` (the live file) has right now.

    KitMixRuntime restores team_<id>.lua as a whole file from its own
    team_<id>.original.lua backup when the jersey name colour is reverted. Without
    this the restore would wipe the team's Classic combinations, or bring back a
    stale copy of them if the backup was taken after they were first saved."""
    text = strip_generated_blocks(restored)
    blocks = _generated_blocks(current)
    if not blocks:
        return text
    nl = "\r\n" if "\r\n" in (text or current) else "\n"
    if text and not text.endswith("\n"):
        text += nl
    return text + "".join(blocks)


# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------

def read_lua_text(path: Path) -> str:
    """newline="" keeps CRLF; surrogateescape round-trips non-UTF-8 bytes (some
    patches ship cp1252 team files) instead of failing or mangling them."""
    with open(path, "r", encoding="utf-8", errors="surrogateescape", newline="") as fh:
        return fh.read()


def write_lua_text_atomic(path: Path, text: str, attempts: int = 5) -> None:
    """Write via a temp file + os.replace so the game, which re-reads team files on
    every match load, never sees a half-written file. Retries briefly when the
    file is momentarily locked."""
    tmp = path.with_name(path.name + ".classic.tmp")
    with open(tmp, "w", encoding="utf-8", errors="surrogateescape", newline="") as fh:
        fh.write(text)
    for attempt in range(attempts):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if attempt == attempts - 1:
                try:
                    tmp.unlink()
                except OSError:
                    pass
                raise
            time.sleep(0.1)


def scan_kit_folder(folder: Path) -> dict[int, dict[int, dict[int, Path]]]:
    """team -> tournament -> kit type -> path for every loose kit_<team>_<type>_<tourn>.rx3.
    Kit types >= 100 are skipped (they don't fit a part code)."""
    kits: dict[int, dict[int, dict[int, Path]]] = {}
    try:
        entries = list(os.scandir(folder))
    except OSError:
        return kits
    for entry in entries:
        m = _RE_KIT_FILE.match(entry.name)
        if not m or not entry.is_file():
            continue
        team, ktype, tourn = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if ktype > PART_MAX:
            continue
        kits.setdefault(team, {}).setdefault(tourn, {})[ktype] = Path(entry.path)
    return kits


def missing_functions(player_lua_text: str) -> list[str]:
    return [
        name for name in REQUIRED_PLAYER_LUA_FUNCTIONS
        if not re.search(r"^\s*function\s+%s\s*\(" % name, player_lua_text, re.M)
    ]


class KitClassicRuntime:
    """File side of the Classic subtab: team_<id>.lua blocks, the loose kit index
    and the player.lua capability check. Holds no Tk state."""

    def __init__(self, app: "Server16App") -> None:
        self.app = app
        self._kits: Optional[dict[int, dict[int, dict[int, Path]]]] = None
        self._kits_folder: Optional[Path] = None
        self._player_lua_cache: tuple[Optional[Path], float, Optional[list[str]]] = (None, 0.0, None)
        # Kit drawings for the whole Kits tab (Classic, Simple, Advanced): one disk
        # cache, and one lock because IconFactory isn't thread-safe and each preview
        # renders on its own worker thread.
        base_dir = getattr(app, "base_dir", None)
        self.art = IconFactory(self.kit_path, Path(base_dir) / "runtime" / "kit_art_cache" if base_dir else None)
        self.art_lock = threading.Lock()

    # -- paths ---------------------------------------------------------------
    def team_lua_dir(self) -> Path:
        return Path(self.app.exedir) / "data" / "fifarna" / "lua" / "assignments" / "teams"

    def team_lua_path(self, team: int) -> Path:
        return self.team_lua_dir() / f"team_{team}.lua"

    def backup_path(self, team: int) -> Path:
        return self.team_lua_dir() / BACKUP_DIR_NAME / f"team_{team}.lua.bak"

    def kit_dir(self) -> Path:
        return Path(self.app.exedir) / "data" / "sceneassets" / "kit"

    def player_lua_path(self) -> Path:
        return Path(self.app.exedir) / "data" / "fifarna" / "lua" / "assets" / "player.lua"

    # -- player.lua ------------------------------------------------------------
    def missing_player_lua_functions(self) -> Optional[list[str]]:
        """Required Rev Mod functions the installed player.lua lacks ([] = supported),
        or None when there is no player.lua at all. Cached by path + mtime."""
        path = self.player_lua_path()
        try:
            mtime = path.stat().st_mtime
        except OSError:
            return None
        cached_path, cached_mtime, cached = self._player_lua_cache
        if cached_path == path and cached_mtime == mtime and cached is not None:
            return cached
        try:
            missing = missing_functions(read_lua_text(path))
        except OSError:
            return None
        self._player_lua_cache = (path, mtime, missing)
        return missing

    def is_supported(self) -> bool:
        return self.missing_player_lua_functions() == []

    # -- kits --------------------------------------------------------------------
    def kits(self, refresh: bool = False) -> dict[int, dict[int, dict[int, Path]]]:
        folder = self.kit_dir()
        if refresh or self._kits is None or self._kits_folder != folder:
            self._kits = scan_kit_folder(folder)
            self._kits_folder = folder
        return self._kits

    def team_kits(self, team: int, refresh: bool = False) -> dict[int, dict[int, Path]]:
        return self.kits(refresh).get(team, {})

    def gk_kit_options(self, team: int) -> list[int]:
        """Goalkeeper kit types offered for `team`: the GK_KITS it has as loose files,
        or just 2 (every team has one) when none of them are loose."""
        have = self.team_kits(team).get(0) or {}
        return [k for k in GK_KITS if k in have] or [GK_KITS[0]]

    def kit_path(self, team: int, tourn: int, ktype: int) -> Optional[Path]:
        by_tourn = self.team_kits(team)
        return (by_tourn.get(tourn) or {}).get(ktype) or (by_tourn.get(0) or {}).get(ktype)

    # -- combinations --------------------------------------------------------------
    def load(self, team: int) -> Optional[TeamCombinations]:
        """The team's saved combinations, or None when its lua has no Classic block."""
        path = self.team_lua_path(team)
        if not path.is_file():
            return None
        return parse_team_block(read_lua_text(path), team)

    def save(self, tc: TeamCombinations) -> tuple[Path, list[tuple[int, int]]]:
        """Write `tc` into team_<id>.lua (block replaced, appended, or removed when
        empty). Backs the file up once, before Classic first changes it. Returns
        (path, slots also swapped outside the block). Raises RuntimeError when the
        installed player.lua can't decode part codes."""
        if not self.is_supported():
            raise RuntimeError("Installed player.lua does not support kit part combinations")
        path = self.team_lua_path(tc.team)
        exists = path.is_file()
        text = read_lua_text(path) if exists else ""
        new_text = apply_team_block(text, tc)
        external = external_swap_slots(text, tc.team)
        clashes = sorted({m.key for c in tc.items for m in c.mixes} & external)
        if new_text == text:
            return path, clashes
        if exists:
            backup = self.backup_path(tc.team)
            if not backup.exists():
                backup.parent.mkdir(parents=True, exist_ok=True)
                with open(backup, "w", encoding="utf-8", errors="surrogateescape", newline="") as fh:
                    fh.write(text)
        elif not new_text.strip():
            return path, clashes
        path.parent.mkdir(parents=True, exist_ok=True)
        write_lua_text_atomic(path, new_text)
        self.app.log(f"Kits Classic: saved {len(tc.items)} combination(s) for team {tc.team} -> {path}")
        return path, clashes
