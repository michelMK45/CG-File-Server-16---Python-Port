"""Kit Mixer runtime - builds a mixed kit .rx3 (jersey from one source, shorts+socks
from another) using FifaLibrary16.dll via the 32-bit kit_worker.py bridge.

Mirrors the bridge-location pattern in fifa_db.py (_find_dll/_find_python32/_find_worker)
and the subprocess invocation in FifaDatabase.connect().
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .app import Server16App

REPO_ROOT = Path(__file__).resolve().parent.parent

# EKitType values confirmed via reflection against FifaLibrary16.dll.
KIT_TYPES: dict[str, str] = {
    "home": "0",
    "away": "1",
    "keeper": "2",
    "third": "3",
}


def _resource_root() -> Path:
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


def _find_worker(name: str = "kit_worker.py") -> Optional[Path]:
    for candidate in (
        _resource_root() / "server16_py" / name,
        Path(__file__).resolve().parent / name,
    ):
        if candidate.exists():
            return candidate
    return None


def kit_filename(team_id: str, kittype: str, tourn_id: str = "0") -> str:
    return f"kit_{team_id}_{kittype}_{tourn_id}.rx3"


# short=0 -> jersey numbers, short=1 -> shorts numbers (see GetRMNumberSet in
# install_data/data/fifarna/lua/assets/player.lua). tourn_id "0" is the
# tournament-agnostic slot the engine falls back to, and takes priority over
# the generic per-colour kitnumbers set assigned in each team's Lua file.
NUMBERS_SHORT_CODE: dict[str, str] = {"jersey": "1", "shorts": "2"}


def kitnumbers_filename(team_id: str, kittype: str, slot: str, tourn_id: str = "0") -> str:
    return f"specifickitnumbers_{team_id}_{NUMBERS_SHORT_CODE[slot]}_{tourn_id}_{kittype}.rx3"


def kitui_filename(team_id: str, kittype: str) -> str:
    return f"j0_{team_id}_{kittype}.dds"


class KitMixRuntime:
    """Runtime for mixing jersey/shorts+socks textures across kit .rx3 files."""

    def __init__(self, app: "Server16App") -> None:
        self.app = app

    def kits_folder_name(self, team_id: str) -> str:
        """The FSW/Kits subfolder to browse for a team: a friendly name from the
        settings.ini [kitsid] section (team_id -> name, edited via the asset
        settings editor — same mechanism as [chantsid]), or the raw team_id
        when no mapping is configured, so existing <team_id>-named folders
        keep working unchanged."""
        settings_ini = getattr(self.app, "settings_ini", None)
        if team_id and settings_ini is not None:
            name = settings_ini.read(team_id, "kitsid")
            if name:
                return name
        return team_id

    def kits_dir(self, team_id: str) -> Path:
        return self.app.exedir / "FSW" / "Kits" / self.kits_folder_name(team_id) / "sceneassets" / "kit"

    def live_kit_dir(self) -> Path:
        return self.app.exedir / "data" / "sceneassets" / "kit"

    def list_available_kits(self, team_id: str) -> list[Path]:
        folder = self.kits_dir(team_id)
        if not folder.exists():
            return []
        return sorted(folder.glob("*.rx3"), key=lambda p: p.name.lower())

    def live_kit_path(self, team_id: str, kittype: str) -> Path:
        return self.live_kit_dir() / kit_filename(team_id, kittype)

    def kitnumbers_dir(self, team_id: str) -> Path:
        return self.app.exedir / "FSW" / "Kits" / self.kits_folder_name(team_id) / "sceneassets" / "kitnumbers"

    def live_kitnumbers_dir(self) -> Path:
        return self.app.exedir / "data" / "sceneassets" / "kitnumbers"

    def list_available_kitnumbers(self, team_id: str) -> list[Path]:
        folder = self.kitnumbers_dir(team_id)
        if not folder.exists():
            return []
        return sorted(folder.glob("*.rx3"), key=lambda p: p.name.lower())

    def live_kitnumbers_path(self, team_id: str, kittype: str, slot: str) -> Path:
        return self.live_kitnumbers_dir() / kitnumbers_filename(team_id, kittype, slot)

    def kitui_dir(self, team_id: str) -> Path:
        return self.app.exedir / "FSW" / "Kits" / self.kits_folder_name(team_id) / "ui" / "imgAssets" / "kits"

    def live_kitui_dir(self) -> Path:
        return self.app.exedir / "data" / "ui" / "imgAssets" / "kits"

    def list_available_kitui(self, team_id: str) -> list[Path]:
        folder = self.kitui_dir(team_id)
        if not folder.exists():
            return []
        return sorted(folder.glob("*.dds"), key=lambda p: p.name.lower())

    def live_kitui_path(self, team_id: str, kittype: str) -> Path:
        return self.live_kitui_dir() / kitui_filename(team_id, kittype)

    def backup_path(self, live_path: Path) -> Path:
        return live_path.with_name(f"{live_path.stem}.original{live_path.suffix}")

    def has_backup(self, team_id: str, kittype: str) -> bool:
        return self.backup_path(self.live_kit_path(team_id, kittype)).exists()

    def has_backup_numbers(self, team_id: str, kittype: str, slot: str) -> bool:
        return self.backup_path(self.live_kitnumbers_path(team_id, kittype, slot)).exists()

    def has_backup_kitui(self, team_id: str, kittype: str) -> bool:
        return self.backup_path(self.live_kitui_path(team_id, kittype)).exists()

    def _backup_if_needed(self, live_path: Path) -> None:
        backup = self.backup_path(live_path)
        if backup.exists():
            return
        backup.parent.mkdir(parents=True, exist_ok=True)
        if live_path.exists():
            backup.write_bytes(live_path.read_bytes())
        else:
            # Marker for "nothing lived here before our first write" — a real
            # .rx3 backup is never zero bytes, so _restore() below treats an
            # empty marker as "delete the file we created" instead of trying
            # to write empty bytes back.
            backup.write_bytes(b"")

    def _restore(self, live_path: Path) -> None:
        backup = self.backup_path(live_path)
        if not backup.exists():
            raise FileNotFoundError(f"No backup available for {live_path.name}")
        if backup.stat().st_size == 0:
            live_path.unlink(missing_ok=True)
        else:
            live_path.parent.mkdir(parents=True, exist_ok=True)
            live_path.write_bytes(backup.read_bytes())

    def _resolve_template(self, team_id: str, kittype: str) -> Path:
        live = self.live_kit_path(team_id, kittype)
        if live.exists():
            return live
        candidates = [
            p for p in self.list_available_kits(team_id)
            if p.name.startswith(f"kit_{team_id}_{kittype}_")
        ]
        if candidates:
            return candidates[0]
        available = self.list_available_kits(team_id)
        if available:
            return available[0]
        raise FileNotFoundError(
            f"No template kit found for team {team_id} (kit type {kittype}). "
            f"Place at least one .rx3 under {self.kits_dir(team_id)}"
        )

    def _run_worker(self, config: dict, worker_name: str = "kit_worker.py") -> dict:
        dll = _find_dll()
        if dll is None:
            raise FileNotFoundError("FifaLibrary16.dll not found in bin/")
        python32 = _find_python32()
        if python32 is None:
            raise FileNotFoundError(
                "32-bit Python not found in bin/python32/. Run scripts/setup_python32.bat to set it up."
            )
        worker = _find_worker(worker_name)
        if worker is None:
            raise FileNotFoundError(f"{worker_name} not found")

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as fh:
            json.dump(config, fh)
            config_path = fh.name

        try:
            result = subprocess.run(
                [str(python32), str(worker), str(dll), config_path],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        finally:
            Path(config_path).unlink(missing_ok=True)

        raw = (result.stdout or "").strip()
        if not raw:
            raise RuntimeError(f"{worker_name} produced no output. stderr: {(result.stderr or '')[:300]}")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"{worker_name} returned invalid JSON: {exc}. stdout: {raw[:300]}") from exc

        if not data.get("ok"):
            raise RuntimeError(data.get("error", f"{worker_name} failed with no error message"))
        return data

    def apply_mix(self, team_id: str, kittype: str, jersey: dict, shorts: dict, crest: dict | None = None) -> dict:
        """jersey/shorts/crest are {"mode": "keep"|"rx3"|"img", "path": "..."} dicts.

        crest targets the "crest_cm" badge decal the engine overlays on the
        jersey at runtime (see kit_worker.py). Mixing a jersey from a
        different team without also picking a matching crest source is what
        causes two badges to render on top of each other in-game.
        """
        app = self.app
        if not team_id:
            raise ValueError("A team ID is required to mix a kit")

        template_path = self._resolve_template(team_id, kittype)
        live_path = self.live_kit_path(team_id, kittype)
        tmp_output = live_path.with_name(f"{live_path.stem}.tmp{live_path.suffix}")

        config = {
            "template": str(template_path),
            "output": str(tmp_output),
            "jersey": jersey,
            "shorts": shorts,
            "crest": crest or {"mode": "keep"},
        }
        result = self._run_worker(config)

        self._backup_if_needed(live_path)

        live_path.parent.mkdir(parents=True, exist_ok=True)
        Path(tmp_output).replace(live_path)

        app.log(f"Kit mix applied for team {team_id} ({kittype}): {live_path}")
        return {
            "team_id": team_id,
            "kittype": kittype,
            "template": str(template_path),
            "output": str(live_path),
            "roles": result.get("roles", {}),
        }

    def restore_original(self, team_id: str, kittype: str) -> dict:
        live_path = self.live_kit_path(team_id, kittype)
        self._restore(live_path)
        self.app.log(f"Kit restored to original for team {team_id} ({kittype}): {live_path}")
        return {"team_id": team_id, "kittype": kittype, "output": str(live_path)}

    def apply_numbers(self, team_id: str, kittype: str, jersey_numbers: dict | None, shorts_numbers: dict | None) -> dict:
        """jersey_numbers/shorts_numbers are {"mode": "keep"|"rx3", "path": "..."} dicts.

        Unlike the kit texture, a specifickitnumbers_*.rx3 file is a
        self-contained set of ten uniform digit textures (0-9) with the font
        and colour already baked in, so "mixing" it is a plain file copy —
        no FifaLibrary/kit_worker involvement needed. Writing to the
        tournament-agnostic "specific" path makes it take priority over the
        generic per-colour numbers set assigned in the team's Lua file.
        """
        app = self.app
        if not team_id:
            raise ValueError("A team ID is required to change kit numbers")

        applied: dict[str, str] = {}
        for slot, cfg in (("jersey", jersey_numbers), ("shorts", shorts_numbers)):
            if not cfg or cfg.get("mode", "keep") == "keep":
                continue
            source_path = cfg.get("path")
            if not source_path or not Path(source_path).exists():
                raise FileNotFoundError(f"Numbers source not found for {slot}: {source_path}")
            live_path = self.live_kitnumbers_path(team_id, kittype, slot)
            self._backup_if_needed(live_path)
            live_path.parent.mkdir(parents=True, exist_ok=True)
            live_path.write_bytes(Path(source_path).read_bytes())
            applied[slot] = str(live_path)
            app.log(f"Kit numbers ({slot}) applied for team {team_id} ({kittype}): {live_path}")

        return {"team_id": team_id, "kittype": kittype, "applied": applied}

    def restore_numbers_original(self, team_id: str, kittype: str, slot: str) -> dict:
        live_path = self.live_kitnumbers_path(team_id, kittype, slot)
        self._restore(live_path)
        self.app.log(f"Kit numbers ({slot}) restored to original for team {team_id} ({kittype}): {live_path}")
        return {"team_id": team_id, "kittype": kittype, "slot": slot, "output": str(live_path)}

    def apply_kitui(self, team_id: str, kittype: str, cfg: dict | None) -> dict:
        """cfg is a {"mode": "keep"|"dds", "path": "..."} dict for the kit
        selection screen thumbnail (j0_<team>_<kittype>.dds). Same-format
        plain file copy, like apply_numbers — no FifaLibrary involvement
        needed unless dimensions/compression differ from the target slot."""
        app = self.app
        if not team_id:
            raise ValueError("A team ID is required to change the kit UI thumbnail")
        if not cfg or cfg.get("mode", "keep") == "keep":
            return {"team_id": team_id, "kittype": kittype, "applied": False}

        source_path = cfg.get("path")
        if not source_path or not Path(source_path).exists():
            raise FileNotFoundError(f"Kit UI thumbnail source not found: {source_path}")

        live_path = self.live_kitui_path(team_id, kittype)
        self._backup_if_needed(live_path)
        live_path.parent.mkdir(parents=True, exist_ok=True)
        live_path.write_bytes(Path(source_path).read_bytes())

        app.log(f"Kit UI thumbnail applied for team {team_id} ({kittype}): {live_path}")
        return {"team_id": team_id, "kittype": kittype, "applied": True, "output": str(live_path)}

    def restore_kitui_original(self, team_id: str, kittype: str) -> dict:
        live_path = self.live_kitui_path(team_id, kittype)
        self._restore(live_path)
        self.app.log(f"Kit UI thumbnail restored to original for team {team_id} ({kittype}): {live_path}")
        return {"team_id": team_id, "kittype": kittype, "output": str(live_path)}

    def preview_dir(self) -> Path:
        return self.app.base_dir / "runtime" / "kitmix_previews"

    def render_preview(self, source_path: str, role: str, max_size: int = 220) -> Path:
        """Render a small PNG preview of one kit asset ("jersey"/"shorts"/"crest"/
        "jersey_numbers"/"shorts_numbers") extracted from source_path, via the
        32-bit kit_preview_worker.py bridge. Blocking — call from a background
        thread when used from the UI."""
        output_path = self.preview_dir() / f"{role}.png"
        config = {
            "source": source_path,
            "role": role,
            "output": str(output_path),
            "max_size": max_size,
        }
        result = self._run_worker(config, worker_name="kit_preview_worker.py")
        return Path(result["output"])
