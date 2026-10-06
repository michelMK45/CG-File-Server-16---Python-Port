"""Ids inside Ball / Referee / Wipe / Adboard packs vs. the id the game asks for.

The RM Mod Lua builds every one of these paths from a *league graphics id* it
reads off the match (wvWipe.leagueID, see Offsets.TLEAGUE):

    data/sceneassets/ball/specificball_0_<id>_0.rx3
    data/sceneassets/wipe3d/specificwipe_0_<id>_0.rx3
    data/sceneassets/adboard/specificadboard_0_<id>_0_0.rx3
    data/sceneassets/kit/kit_600x_5_<id>.rx3              (referee)

A pack is authored for ONE id, but it is assigned in settings.ini to a ROUND
(TOURROUNDID) -- a different number space -- so a pack only ever showed up when
its author's id happened to be the one the game asked for in that round. This
module renames the id inside a pack's file names to the one the game will ask
for, so "assign pack X to round R" does what it says.

Which id the game asks for is not always the raw league id: the Lua pipes it
through getTournamentGraphics (swapTournamentID pairs, optional global
override) and, for referee kits, getCloneTournamentRefereeKits
(copyTournamentRefereeKitAssets). Those are plain top-level calls in the
install's own data/fifarna/lua/assignments/*.lua, read here so a league that is
swapped/cloned (e.g. 54 -> 53 for referee kits) resolves to what the engine
really requests.

Only a pack that carries exactly ONE non-zero id is renamed: a pack holding
several ids (one set of files per competition) is already addressed by id and is
installed untouched. Id 0 is the generic fallback and is never touched.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Callable, Iterable, Mapping

KINDS = ("ball", "wipe", "adboard", "cornerflag", "referee")

_LUA_CALL_RE = re.compile(
    r"^\s*(swapTournamentID|copyTournamentRefereeKitAssets|useGlobalTournamentGraphics)"
    r"\s*\(\s*(-?\d+)\s*(?:,\s*(-?\d+)\s*)?\)"
)


@dataclass(frozen=True)
class LuaIdMaps:
    """What the install's Lua does to a league id before building asset paths."""

    swaps: Mapping[int, int] = field(default_factory=dict)  # swapTournamentID(a, b): both directions
    referee_clone: Mapping[int, int] = field(default_factory=dict)  # copyTournamentRefereeKitAssets(old, new)
    forced: int | None = None  # useGlobalTournamentGraphics(id): every league resolves to it


_EMPTY_MAPS = LuaIdMaps()
_maps_cache: dict[str, tuple[tuple, LuaIdMaps]] = {}


def read_lua_id_maps(exedir: str | Path) -> LuaIdMaps:
    """Parse the swap / clone / global-override calls out of the install's
    data/fifarna/lua/assignments/*.lua (top level only: the teams/ and players/
    sub-folders hold thousands of per-team files that never declare these).
    Commented-out calls are ignored. Missing folder or unreadable file -> no
    mapping, i.e. the league id is used as it is."""
    folder = Path(exedir) / "data" / "fifarna" / "lua" / "assignments"
    try:
        files = sorted(path for path in folder.glob("*.lua") if path.is_file())
        signature = tuple((path.name, path.stat().st_mtime_ns, path.stat().st_size) for path in files)
    except OSError:
        return _EMPTY_MAPS
    if not files:
        return _EMPTY_MAPS
    cached = _maps_cache.get(str(folder))
    if cached is not None and cached[0] == signature:
        return cached[1]

    swaps: dict[int, int] = {}
    clones: dict[int, int] = {}
    forced: int | None = None
    for path in files:
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        for line in lines:
            match = _LUA_CALL_RE.match(line)
            if match is None:
                continue
            name, first, second = match.group(1), int(match.group(2)), match.group(3)
            if name == "swapTournamentID" and second is not None:
                # rm_common.lua: swapIDTournamentList[ida] = idb; swapIDTournamentList[idb] = ida
                swaps[first] = int(second)
                swaps[int(second)] = first
            elif name == "copyTournamentRefereeKitAssets" and second is not None:
                clones[first] = int(second)
            elif name == "useGlobalTournamentGraphics":
                forced = first if first != -1 else None  # -1 is the Lua's "unset"
    maps = LuaIdMaps(swaps=swaps, referee_clone=clones, forced=forced)
    _maps_cache[str(folder)] = (signature, maps)
    return maps


def engine_id(kind: str, league_id: int, maps: LuaIdMaps = _EMPTY_MAPS) -> int:
    """The id the Lua puts in the file names it asks for, for this kind of asset.

    ball / wipe / adboard / cornerflag: getTournamentGraphics(leagueID).
    referee: getCloneTournamentRefereeKits(getTournamentGraphics(leagueID))."""
    base = maps.forced if maps.forced is not None else maps.swaps.get(league_id, league_id)
    if kind == "referee":
        return maps.referee_clone.get(base, base)
    return base


# ── where the tournament id sits in each kind of file name ──────────────────────
# Each extractor returns (start, end) of the id inside the BASE name, or None when
# the name is not an id-addressed asset of that kind (or its id is the generic 0).

def _span(match: re.Match[str], group: str) -> tuple[int, int] | None:
    if int(match.group(group)) <= 0:
        return None
    return match.start(group), match.end(group)


_BALL_RE = re.compile(
    r"^specificball_(?P<team>\d+)_(?P<tourn>\d+)_(?P<variant>-?\d+)(?:_(?P<stad>\d+))?(?:_textures)?\.rx3$", re.I
)
_WIPE_RE = re.compile(r"^specificwipe_(?P<wipe>\d+)_(?P<tourn>\d+)(?:_(?P<default>\d+))?(?:_textures)?\.rx3$", re.I)
_ADBOARD_RE = re.compile(
    r"^specificadboard_(?P<team>\d+)_(?P<tourn>\d+)_(?P<stad>\d+)_(?P<last>\d+)\.rx3$", re.I
)
_CORNERFLAG_RE = re.compile(r"^cornerflag_(?P<team>\d+)_(?P<tourn>\d+)_(?P<stad>\d+)\.rx3$", re.I)
_REFEREE_KIT_RE = re.compile(r"^kit_(?P<kit>6[01]\d\d)_(?P<type>\d+)_(?P<tourn>\d+)\.rx3$", re.I)
_REFEREE_SPECIFIC_RE = re.compile(
    r"^specifickit_(?P<kit>6[01]\d\d)_(?P<type>\d+)_(?P<tourn>\d+)_(?P<home>\d+)_(?P<away>\d+)\.rx3$", re.I
)


def _ball_span(name: str) -> tuple[int, int] | None:
    match = _BALL_RE.match(name)
    return _span(match, "tourn") if match else None


def _wipe_span(name: str) -> tuple[int, int] | None:
    match = _WIPE_RE.match(name)
    return _span(match, "tourn") if match else None


def _cornerflag_span(name: str) -> tuple[int, int] | None:
    match = _CORNERFLAG_RE.match(name)
    return _span(match, "tourn") if match else None


def _adboard_span(name: str) -> tuple[int, int] | None:
    match = _ADBOARD_RE.match(name)
    if match is None:
        return None
    if int(match.group("tourn")) > 0:
        return _span(match, "tourn")
    # Older naming: specificadboard_0_0_0_<tourn>.rx3 (id in the last slot). Only when the
    # team and stadium slots are both 0 -- otherwise the last slot is a per-team random pick.
    if int(match.group("team")) == 0 and int(match.group("stad")) == 0:
        return _span(match, "last")
    return None


def _referee_span(name: str) -> tuple[int, int] | None:
    match = _REFEREE_KIT_RE.match(name) or _REFEREE_SPECIFIC_RE.match(name)
    return _span(match, "tourn") if match else None


_SPAN_FINDERS: dict[str, Callable[[str], tuple[int, int] | None]] = {
    "ball": _ball_span,
    "wipe": _wipe_span,
    "adboard": _adboard_span,
    # Corner flags travel inside an Adboard folder but are addressed (and renamed) on their own:
    # a pack can pair boards of one id with flags of another.
    "cornerflag": _cornerflag_span,
    "referee": _referee_span,
}


def pack_ids(kind: str, names: Iterable[str]) -> set[int]:
    """Every non-zero id the pack's file names carry (for logging / the editor)."""
    find = _SPAN_FINDERS[kind]
    found: set[int] = set()
    for rel in names:
        base = PurePosixPath(rel).name
        span = find(base)
        if span is not None:
            found.add(int(base[span[0]:span[1]]))
    return found


@dataclass(frozen=True)
class PackRemap:
    rename: dict[str, str] = field(default_factory=dict)  # pack-relative name -> installed name (changed ones only)
    source_ids: tuple[int, ...] = ()  # the id(s) the pack carries
    target_id: int | None = None
    reason: str = ""  # "remapped" | "no-id" | "multiple-ids" | "same-id" | "invalid-target"


def plan_pack_remap(kind: str, names: Iterable[str], target_id: int) -> PackRemap:
    """Work out which file names to change so a single-id pack answers to target_id.
    `names` are pack-relative POSIX paths; only the file's base name is rewritten."""
    if target_id <= 0:
        return PackRemap(reason="invalid-target", target_id=target_id)
    find = _SPAN_FINDERS[kind]
    spans: dict[str, tuple[int, int]] = {}
    for rel in names:
        span = find(PurePosixPath(rel).name)
        if span is not None:
            spans[rel] = span
    ids = sorted({int(PurePosixPath(rel).name[s:e]) for rel, (s, e) in spans.items()})
    if not ids:
        return PackRemap(reason="no-id", target_id=target_id)
    if len(ids) > 1:
        return PackRemap(source_ids=tuple(ids), target_id=target_id, reason="multiple-ids")
    if ids[0] == target_id:
        return PackRemap(source_ids=tuple(ids), target_id=target_id, reason="same-id")

    rename: dict[str, str] = {}
    for rel, (start, end) in spans.items():
        path = PurePosixPath(rel)
        new_name = path.name[:start] + str(target_id) + path.name[end:]
        rename[rel] = str(path.with_name(new_name))
    return PackRemap(rename=rename, source_ids=tuple(ids), target_id=target_id, reason="remapped")
