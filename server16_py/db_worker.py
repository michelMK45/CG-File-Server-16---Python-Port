"""
32-bit bridge: loads FifaLibrary16.dll and reads the FIFA database.
Must be run with a 32-bit Python interpreter — the DLL is x86-only.

Usage: python db_worker.py <dll_path> <db_path> <xml_path>

Stdout: single JSON object
  {"teams": {"id": "name", ...}, "stadiums": {"id": "name", ...}}
  or {"error": "message"} on failure
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def _pick_field(available: list, candidates: list):
    lower_map = {f.lower(): f for f in available}
    for c in candidates:
        if c in lower_map:
            return lower_map[c]
    return None


def main() -> None:
    if len(sys.argv) < 4:
        print(json.dumps({"error": "Usage: db_worker.py <dll_path> <db_path> <xml_path>"}))
        sys.exit(1)

    dll_path = Path(sys.argv[1])
    db_path  = Path(sys.argv[2])
    xml_path = Path(sys.argv[3])

    for p, label in [(dll_path, "DLL"), (db_path, "db"), (xml_path, "xml")]:
        if not p.exists():
            print(json.dumps({"error": f"{label} not found: {p}"}))
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
        from FifaLibrary import DbFile  # type: ignore[import]
    except Exception as exc:
        print(json.dumps({"error": f"Failed to load FifaLibrary16.dll: {exc}"}))
        sys.exit(1)

    try:
        db = DbFile(str(db_path), str(xml_path))
        if not db.Load():
            print(json.dumps({"error": "DbFile.Load() returned False"}))
            sys.exit(1)
    except Exception as exc:
        print(json.dumps({"error": f"DbFile error: {exc}"}))
        sys.exit(1)

    teams: dict = {}
    stadiums: dict = {}

    try:
        table = db.GetTable("teams")
        if table is not None:
            desc = table.TableDescriptor
            fields = [desc.FieldDescriptors[i].FieldName for i in range(desc.NFields)]
            id_f   = _pick_field(fields, ["teamid", "id"])
            name_f = _pick_field(fields, ["teamname", "name"])
            if id_f and name_f:
                for i in range(table.NValidRecords):
                    rec = table.Records[i]
                    name = rec.GetStringField(name_f)
                    if name:
                        teams[str(rec.GetIntField(id_f))] = name
    except Exception as exc:
        print(json.dumps({"error": f"Error reading teams: {exc}"}))
        sys.exit(1)

    try:
        table = db.GetTable("stadiums")
        if table is not None:
            desc = table.TableDescriptor
            fields = [desc.FieldDescriptors[i].FieldName for i in range(desc.NFields)]
            id_f   = _pick_field(fields, ["stadiumid", "id"])
            name_f = _pick_field(fields, ["stadiumname", "name"])
            if id_f and name_f:
                for i in range(table.NValidRecords):
                    rec = table.Records[i]
                    name = rec.GetStringField(name_f)
                    if name:
                        stadiums[str(rec.GetIntField(id_f))] = name
    except Exception as exc:
        pass  # stadiums are optional

    print(json.dumps({"teams": teams, "stadiums": stadiums}))


if __name__ == "__main__":
    main()
