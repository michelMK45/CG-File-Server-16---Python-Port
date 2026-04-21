"""FIFA 16 Database Reader - Uses FifaLibrary14.dll to read t3db databases directly"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional, Dict

# FifaLibrary14 DLL location
REPO_ROOT = Path(__file__).resolve().parent.parent
FIFA_LIBRARY = REPO_ROOT / "bin" / "FifaLibrary14.dll"

_clr_loaded = False
_loader_error = ""


def _ensure_clr():
    """Load pythonnet and FifaLibrary14.dll once"""
    global _clr_loaded, _loader_error
    if _clr_loaded:
        return True
    try:
        if not FIFA_LIBRARY.exists():
            _loader_error = f"FifaLibrary14.dll not found: {FIFA_LIBRARY}"
            print(f"️  {_loader_error}")
            return False

        # Ensure CLR can resolve dependent assemblies in FIFA Library folder.
        dll_dir = str(FIFA_LIBRARY.parent)
        if dll_dir not in sys.path:
            sys.path.insert(0, dll_dir)
        os.environ["PATH"] = dll_dir + os.pathsep + os.environ.get("PATH", "")

        clr = __import__("clr")
        try:
            clr.AddReference(str(FIFA_LIBRARY))
        except Exception:
            System = __import__("System")
            System.Reflection.Assembly.LoadFrom(str(FIFA_LIBRARY))
            clr.AddReference("FifaLibrary14")

        _clr_loaded = True
        _loader_error = ""
        return True
    except Exception as e:
        _loader_error = f"Cannot load FifaLibrary14.dll: {e}"
        print(f"️  {_loader_error}")
        return False


class FifaDatabase:
    """
    Reads team data directly from FIFA's t3db database using FifaLibrary14.dll.
    No export step needed - reads the same binary format that DB Master uses.
    """

    def __init__(self, fifa_root_path: Path | str) -> None:
        self.fifa_root = Path(fifa_root_path)
        self.db_path = self.fifa_root / "data" / "db" / "fifa_ng_db.db"
        self.xml_path = self.fifa_root / "data" / "db" / "fifa_ng_db-meta.xml"
        self.team_cache: Dict[str, str] = {}
        self.stadium_cache: Dict[str, str] = {}
        self._is_loaded = False
        self.last_error = ""

    def connect(self) -> bool:
        """Load the FIFA database using FifaLibrary14.dll. Returns True on success."""
        if not _ensure_clr():
            self.last_error = _loader_error or "Cannot load pythonnet/FifaLibrary14.dll"
            return False

        if not self.db_path.exists():
            self.last_error = f"Database not found: {self.db_path}"
            print(f"️  {self.last_error}")
            return False
        if not self.xml_path.exists():
            self.last_error = f"Meta XML not found: {self.xml_path}"
            print(f"️  {self.last_error}")
            return False

        try:
            from FifaLibrary import DbFile  # type: ignore[import]

            db = DbFile(str(self.db_path), str(self.xml_path))
            if not db.Load():
                self.last_error = "DbFile.Load() returned False"
                print(f"️  {self.last_error}")
                return False

            table = db.GetTable("teams")
            if table is None:
                self.last_error = "'teams' table not found in database"
                print(f"️  {self.last_error}")
                return False

            # Read field names from table descriptor to find id and name columns
            descriptor = table.TableDescriptor
            field_names = [
                descriptor.FieldDescriptors[i].FieldName
                for i in range(descriptor.NFields)
            ]

            # Determine which fields hold the team id and team name
            id_field = self._pick_field(field_names, ["teamid", "id"])
            name_field = self._pick_field(field_names, ["teamname", "name"])

            if not id_field or not name_field:
                self.last_error = f"Could not find id/name fields. Available: {field_names}"
                print(f"️  {self.last_error}")
                return False

            # Iterate records and cache
            for i in range(table.NValidRecords):
                rec = table.Records[i]
                team_id = str(rec.GetIntField(id_field))
                team_name = rec.GetStringField(name_field)
                if team_name:
                    self.team_cache[team_id] = team_name

                # Load stadiums from stadiums table
                stadium_table = db.GetTable("stadiums")
                if stadium_table is not None:
                    stadium_descriptor = stadium_table.TableDescriptor
                    stadium_field_names = [
                        stadium_descriptor.FieldDescriptors[i].FieldName
                        for i in range(stadium_descriptor.NFields)
                    ]
                    stadium_id_field = self._pick_field(stadium_field_names, ["stadiumid", "id"])
                    stadium_name_field = self._pick_field(stadium_field_names, ["stadiumname", "name"])
                
                    if stadium_id_field and stadium_name_field:
                        for i in range(stadium_table.NValidRecords):
                            rec = stadium_table.Records[i]
                            stadium_id = str(rec.GetIntField(stadium_id_field))
                            stadium_name = rec.GetStringField(stadium_name_field)
                            if stadium_name:
                                self.stadium_cache[stadium_id] = stadium_name
                        print(f" Loaded {len(self.stadium_cache)} stadiums from database")

            self._is_loaded = True
            self.last_error = ""
            print(f" Loaded {len(self.team_cache)} teams from {self.db_path.name}")
            return True

        except Exception as e:
            self.last_error = f"Error reading database: {e}"
            print(f"️  {self.last_error}")
            return False

    # ------------------------------------------------------------------
    @staticmethod
    def _pick_field(available: list[str], candidates: list[str]) -> Optional[str]:
        """Return the first field name that matches any candidate (case-insensitive)."""
        lower_map = {f.lower(): f for f in available}
        for c in candidates:
            if c in lower_map:
                return lower_map[c]
        return None

    # ------------------------------------------------------------------
    def get_team_name(self, team_id: str | int) -> Optional[str]:
        """Get team name by ID from cache"""
        return self.team_cache.get(str(team_id).strip())

    def get_stadium_name(self, stadium_id: str | int) -> Optional[str]:
        """Get stadium name by ID from cache"""
        return self.stadium_cache.get(str(stadium_id).strip())

    def load_all_teams(self) -> int:
        """Return count of loaded teams"""
        return len(self.team_cache)

    def is_connected(self) -> bool:
        return self._is_loaded

    def close(self) -> None:
        """Cleanup."""
        pass
