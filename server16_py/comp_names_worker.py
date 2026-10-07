"""
32-bit bridge: localized competition / country names from the game's language DB.
Must be run with a 32-bit Python interpreter -- FifaLibrary16.dll is x86-only.

Usage: python comp_names_worker.py <dll_path> <lang_db> <lang_xml> <trophy_ids> <country_ids>
  trophy_ids / country_ids: comma-separated ids (the C### number of a competition,
  the number a nation's name key ends with). Either may be empty.

Stdout: single JSON object
  {"competitions": {"id": "name", ...}, "countries": {"id": "name", ...}}
  or {"error": "message"} on failure

The language DB addresses a string by a hash of its asset id (FifaLibrary's
`Language.GetTournamentHash` / `GetCountryHash`). Hashes are unsigned 32-bit in
FifaLibrary and signed in the DB, so both sides are masked before comparing.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_MASK = 0xFFFFFFFF


def _ids(arg: str) -> list[int]:
    return [int(token) for token in arg.split(",") if token.strip().isdigit()]


def main() -> None:
    if len(sys.argv) < 6:
        print(json.dumps({"error": "Usage: comp_names_worker.py <dll_path> <lang_db> <lang_xml> <trophy_ids> <country_ids>"}))
        sys.exit(1)

    dll_path, lang_db, lang_xml = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    for path, label in [(dll_path, "DLL"), (lang_db, "language db"), (lang_xml, "language xml")]:
        if not path.exists():
            print(json.dumps({"error": f"{label} not found: {path}"}))
            sys.exit(1)

    dll_dir = str(dll_path.parent)
    if dll_dir not in sys.path:
        sys.path.insert(0, dll_dir)
    os.environ["PATH"] = dll_dir + os.pathsep + os.environ.get("PATH", "")

    try:
        clr = __import__("clr")
        try:
            clr.AddReference(str(dll_path))
        except Exception:
            System = __import__("System")
            System.Reflection.Assembly.LoadFrom(str(dll_path))
            clr.AddReference("FifaLibrary16")
        clr.AddReference("System.Data")
        from FifaLibrary import DbFile, Language  # type: ignore[import]
    except Exception as exc:
        print(json.dumps({"error": f"Failed to load FifaLibrary16.dll: {exc}"}))
        sys.exit(1)

    try:
        db = DbFile(str(lang_db), str(lang_xml))
        if not db.Load():
            print(json.dumps({"error": "DbFile.Load() returned False"}))
            sys.exit(1)
        language = Language(db.Table[0])
        strings: dict[int, str] = {}
        for row in db.ConvertToDataSet().Tables["LanguageStrings"].Rows:
            strings[int(row["hashid"]) & _MASK] = str(row["sourcetext"])

        tournament_types = Language.ETournamentStringType
        competitions: dict[str, str] = {}
        for comp_id in _ids(sys.argv[4]):
            name = strings.get(int(language.GetTournamentHash(comp_id, tournament_types.Full)) & _MASK)
            if not name:
                name = strings.get(int(language.GetTournamentHash(comp_id, tournament_types.Abbr15)) & _MASK)
            if name:
                competitions[str(comp_id)] = name

        # FifaLibrary16's GetCountryHash takes a string type too (the FifaLibrary14
        # the reference editor targets does not).
        country_full = Language.ECountryStringType.Full
        countries: dict[str, str] = {}
        for country_id in _ids(sys.argv[5]):
            name = strings.get(int(language.GetCountryHash(country_id, country_full)) & _MASK)
            if name:
                countries[str(country_id)] = name
    except Exception as exc:
        print(json.dumps({"error": f"Error reading language names: {exc}"}))
        sys.exit(1)

    print(json.dumps({"competitions": competitions, "countries": countries}))


if __name__ == "__main__":
    main()
