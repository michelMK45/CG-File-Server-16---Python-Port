"""FIFA 16 Database Reader - Uses FifaLibrary16.dll via a 32-bit subprocess bridge"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Optional, Dict

REPO_ROOT = Path(__file__).resolve().parent.parent


def _resource_root() -> Path:
    """Return the directory where bundled assets live (MEIPASS when frozen, repo root otherwise)."""
    bundle = getattr(sys, "_MEIPASS", None)
    return Path(bundle) if bundle else REPO_ROOT


def _find_dll() -> Optional[Path]:
    for base in (_resource_root(), REPO_ROOT):
        p = base / "bin" / "FifaLibrary16.dll"
        if p.exists():
            return p
    return None


def _find_python32() -> Optional[Path]:
    for base in (_resource_root(), REPO_ROOT):
        p = base / "bin" / "python32" / "python.exe"
        if p.exists():
            return p
    return None


def _find_worker(name: str) -> Optional[Path]:
    for candidate in (
        _resource_root() / "server16_py" / name,
        Path(__file__).resolve().parent / name,
    ):
        if candidate.exists():
            return candidate
    return None


class FifaDatabase:
    """
    Reads team/stadium data from FIFA's t3db database using FifaLibrary16.dll.
    The DLL is x86-only, so it is loaded inside a dedicated 32-bit subprocess.
    """

    def __init__(self, fifa_root_path: Path | str) -> None:
        self.fifa_root = Path(fifa_root_path)
        self.db_path   = self.fifa_root / "data" / "db" / "fifa_ng_db.db"
        self.xml_path  = self.fifa_root / "data" / "db" / "fifa_ng_db-meta.xml"
        self.team_cache: Dict[str, str]    = {}
        self.stadium_cache: Dict[str, str] = {}
        self._is_loaded = False
        self.last_error = ""

    def connect(self) -> bool:
        """Read the FIFA database via the 32-bit db_worker subprocess. Returns True on success."""
        dll = _find_dll()
        if dll is None:
            self.last_error = "FifaLibrary16.dll not found in bin/"
            print(f"  {self.last_error}")
            return False

        python32 = _find_python32()
        if python32 is None:
            self.last_error = (
                "32-bit Python not found in bin/python32/. "
                "Run scripts/setup_python32.bat to set it up."
            )
            print(f"  {self.last_error}")
            return False

        worker = _find_worker("db_worker.py")
        if worker is None:
            self.last_error = "db_worker.py not found"
            print(f"  {self.last_error}")
            return False

        if not self.db_path.exists():
            self.last_error = f"Database not found: {self.db_path}"
            print(f"  {self.last_error}")
            return False
        if not self.xml_path.exists():
            self.last_error = f"Meta XML not found: {self.xml_path}"
            print(f"  {self.last_error}")
            return False

        try:
            result = subprocess.run(
                [str(python32), str(worker), str(dll), str(self.db_path), str(self.xml_path)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except Exception as exc:
            self.last_error = f"Failed to launch db_worker: {exc}"
            print(f"  {self.last_error}")
            return False

        raw = (result.stdout or "").strip()
        if not raw:
            self.last_error = f"db_worker produced no output. stderr: {result.stderr[:300]}"
            print(f"  {self.last_error}")
            return False

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            self.last_error = f"db_worker returned invalid JSON: {exc}"
            print(f"  {self.last_error}")
            return False

        if "error" in data:
            self.last_error = data["error"]
            print(f"  {self.last_error}")
            return False

        self.team_cache    = data.get("teams", {})
        self.stadium_cache = data.get("stadiums", {})
        self._is_loaded    = True
        self.last_error    = ""
        print(f" Loaded {len(self.team_cache)} teams, {len(self.stadium_cache)} stadiums from {self.db_path.name}")
        return True

    @staticmethod
    def _pick_field(available: list[str], candidates: list[str]) -> Optional[str]:
        lower_map = {f.lower(): f for f in available}
        for c in candidates:
            if c in lower_map:
                return lower_map[c]
        return None

    def get_team_name(self, team_id: str | int) -> Optional[str]:
        return self.team_cache.get(str(team_id).strip())

    def get_stadium_name(self, stadium_id: str | int) -> Optional[str]:
        return self.stadium_cache.get(str(stadium_id).strip())

    def load_all_teams(self) -> int:
        return len(self.team_cache)

    def is_connected(self) -> bool:
        return self._is_loaded

    def close(self) -> None:
        pass
