"""Competition list (TOUR / ROUND ids) read from the game's `compobj.txt`.

The ids the settings.ini sections are keyed by (`TOURNAME` / `TOURROUNDID`, see
`app_game.py`) are the row ids of the FootballCompEng DLC's competition tree,
and they differ between installations -- so they are always read from the
user's own files. Same source and row layout as the standalone CGFS settings
editor (`electron/compobj-reader.cjs`).

`compobj.txt` row: `id,type,code,nameKey,parentId`
    types: 0 root, 1 confederation, 2 nation, 3 competition (TOUR),
           4 stage (ROUND), 5 group

Mods ship the file loose; a vanilla install keeps it packed inside
`FootballCompEngzf.dll`, which this module cannot unpack -- `load_competitions`
reports that case as `reason == "packed"` so the UI can say so.

Localized competition/country names live in the game's language DB and need
`FifaLibrary16.dll`, so they come from the 32-bit `comp_names_worker.py`
(never load that DLL in-process). They are cosmetic: without them the list
still works, labelled by `C###` code.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .fifa_db import _find_dll, _find_python32, _find_worker

FCE_DIR = ("dlc", "dlc_FootballCompEng", "dlc", "FootballCompEng")
COMPOBJ_REL = (*FCE_DIR, "data", "compdata", "compobj.txt")
PACKED_DLL_REL = (*FCE_DIR, "FootballCompEngzf.dll")

TYPE_CONFEDERATION = 1
TYPE_NATION = 2
TYPE_COMPETITION = 3
TYPE_STAGE = 4


@dataclass(frozen=True)
class Stage:
    round_id: int
    code: str
    name_key: str

    @property
    def name(self) -> str:
        # FCE_Round_of_16 -> "Round of 16"
        return re.sub(r"^FCE_", "", self.name_key).replace("_", " ").strip()

    @property
    def label(self) -> str:
        name = self.name
        return f"{self.code} · {name}" if name else self.code


@dataclass
class Competition:
    tour_id: int
    code: str
    gfx: int | None
    name_key: str
    nation_id: int | None
    conf_id: int | None
    stages: list[Stage] = field(default_factory=list)


@dataclass(frozen=True)
class Nation:
    nation_id: int
    code: str
    name_key: str
    conf_id: int | None

    @property
    def number(self) -> str | None:
        match = re.search(r"(\d+)$", self.name_key)
        return match.group(1) if match else None


@dataclass(frozen=True)
class Confederation:
    conf_id: int
    code: str
    name: str


@dataclass
class CompetitionData:
    path: Path
    confederations: list[Confederation]
    nations: list[Nation]
    competitions: list[Competition]
    # Filled in by `apply_names`: C### graphics id -> name, nation number -> name.
    competition_names: dict[int, str] = field(default_factory=dict)
    country_names: dict[str, str] = field(default_factory=dict)

    def competition_label(self, comp: Competition) -> str:
        return self.competition_names.get(comp.gfx, "") if comp.gfx is not None else ""

    def nation_label(self, nation: Nation) -> str:
        return self.country_names.get(nation.number or "", "") or nation.code

    def nation_by_id(self) -> dict[int, Nation]:
        return {nation.nation_id: nation for nation in self.nations}

    def apply_names(self, competitions: dict[str, str], countries: dict[str, str]) -> None:
        self.competition_names = {int(key): value for key, value in competitions.items() if str(key).isdigit()}
        self.country_names = {str(key): value for key, value in countries.items()}


@dataclass(frozen=True)
class CompetitionLoad:
    ok: bool
    data: CompetitionData | None = None
    # "missing" (no file), "packed" (vanilla install, only the DLL exists),
    # "invalid" (file without competitions).
    reason: str = ""
    expected_path: Path | None = None


def parse_compobj(text: str, path: Path | None = None) -> CompetitionData:
    nodes: dict[int, tuple[int, str, str, int]] = {}  # id -> (type, code, nameKey, parent)
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = line.split(",")
        if len(parts) < 5:
            continue
        try:
            node_id, node_type, parent = int(parts[0]), int(parts[1]), int(parts[-1])
        except ValueError:
            continue
        nodes[node_id] = (node_type, parts[2].strip(), ",".join(parts[3:-1]).strip(), parent)

    def ancestor_of(parent_id: int, wanted_type: int) -> int | None:
        current = nodes.get(parent_id)
        current_id = parent_id
        for _ in range(8):  # the tree is shallow; the bound only guards a cyclic file
            if current is None:
                return None
            if current[0] == wanted_type:
                return current_id
            current_id = current[3]
            current = nodes.get(current_id)
        return None

    confederations: list[Confederation] = []
    nations: list[Nation] = []
    competitions: dict[int, Competition] = {}
    for node_id, (node_type, code, name_key, parent) in nodes.items():
        if node_type == TYPE_CONFEDERATION:
            confederations.append(Confederation(node_id, code, name_key))
        elif node_type == TYPE_NATION:
            nations.append(Nation(node_id, code, name_key, ancestor_of(parent, TYPE_CONFEDERATION)))
        elif node_type == TYPE_COMPETITION:
            gfx = re.fullmatch(r"C(\d+)", code, re.IGNORECASE)
            competitions[node_id] = Competition(
                tour_id=node_id,
                code=code,
                gfx=int(gfx.group(1)) if gfx else None,
                name_key=name_key,
                nation_id=ancestor_of(parent, TYPE_NATION),
                conf_id=ancestor_of(parent, TYPE_CONFEDERATION),
            )
    for node_id, (node_type, code, name_key, parent) in nodes.items():
        if node_type == TYPE_STAGE and parent in competitions:
            competitions[parent].stages.append(Stage(node_id, code, name_key))

    return CompetitionData(
        path=path or Path("compobj.txt"),
        confederations=confederations,
        nations=nations,
        competitions=list(competitions.values()),
    )


def load_competitions(exedir: Path | str) -> CompetitionLoad:
    root = Path(exedir)
    loose = root.joinpath(*COMPOBJ_REL)
    if not loose.exists():
        reason = "packed" if root.joinpath(*PACKED_DLL_REL).exists() else "missing"
        return CompetitionLoad(ok=False, reason=reason, expected_path=loose)
    try:
        text = loose.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return CompetitionLoad(ok=False, reason="missing", expected_path=loose)
    data = parse_compobj(text, loose)
    if not data.competitions:
        return CompetitionLoad(ok=False, reason="invalid", expected_path=loose)
    return CompetitionLoad(ok=True, data=data, expected_path=loose)


def find_language_db(exedir: Path | str) -> tuple[Path, Path] | None:
    """(db, meta xml) of the game's language DB: English if present, otherwise
    the first full one that has its meta XML (skipping the `_N_` copies and the
    `_upd` patch files)."""
    loc_dir = Path(exedir) / "data" / "loc"
    try:
        files = {entry.name for entry in loc_dir.iterdir()}
    except OSError:
        return None
    names = sorted(
        name[:-3]
        for name in files
        if name.lower().endswith(".db")
        and not re.match(r"^_\d+_", name)
        and not name.lower().endswith("_upd.db")
        and f"{name[:-3]}-meta.xml" in files
    )
    if not names:
        return None
    pick = next((name for name in names if name.lower() == "eng_us"), names[0])
    return loc_dir / f"{pick}.db", loc_dir / f"{pick}-meta.xml"


def read_names(exedir: Path | str, data: CompetitionData) -> tuple[dict[str, str], dict[str, str]] | None:
    """Localized (competition names by C### id, country names by nation
    number) through the 32-bit bridge. Blocking -- call from a worker thread.
    Returns None when the bridge or the language DB is unavailable."""
    dll, python32, worker = _find_dll(), _find_python32(), _find_worker("comp_names_worker.py")
    language_db = find_language_db(exedir)
    if dll is None or python32 is None or worker is None or language_db is None:
        return None
    trophy_ids = sorted({comp.gfx for comp in data.competitions if comp.gfx is not None})
    country_ids = sorted({nation.number for nation in data.nations if nation.number}, key=int)
    try:
        result = subprocess.run(
            [
                str(python32), str(worker), str(dll), str(language_db[0]), str(language_db[1]),
                ",".join(str(value) for value in trophy_ids), ",".join(country_ids),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        payload = json.loads((result.stdout or "").strip() or "{}")
    except Exception:
        return None
    if not isinstance(payload, dict) or "error" in payload:
        return None
    return payload.get("competitions", {}), payload.get("countries", {})
