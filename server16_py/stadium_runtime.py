from __future__ import annotations

import random
import subprocess
import tempfile
import threading
import traceback
import winsound
from pathlib import Path
from typing import TYPE_CHECKING

from .file_tools import copy, copy_glares, copy_if_exists, extra_setup, inc_count, set_inj_id

if TYPE_CHECKING:
    from .app import Server16App


class StadiumRuntime:
    def __init__(self, app: "Server16App") -> None:
        self.app = app

    @staticmethod
    def _parse_assignment(raw_value: str) -> tuple[list[str], str, str, str]:
        parts = [part.strip() for part in raw_value.split(",") if part.strip()]
        if len(parts) < 4:
            return [], "", "", ""
        police, pitch, net = parts[-3:]
        stadiums = [name for name in parts[:-3] if name and name != "None"]
        return stadiums, police, pitch, net

    @staticmethod
    def _build_task_request_key(section_name: str, section_id: str, raw_value: str) -> tuple[str, str, str]:
        return section_name, section_id, raw_value

    def apply_stadium_runtime(self) -> None:
        app = self.app
        if app.settings_ini.key_exists(app.TOURROUNDID, "exclude") or app.settings_ini.key_exists(app.TOURNAME, "exclude"):
            app.log(f"Stadium excluded for TOUR={app.TOURNAME} ROUND={app.TOURROUNDID}")
            # Clear stadium from previous match when this tournament/round is excluded
            app.curstad = ""
            app.ScoreboardStadName = ""
            return
        section_id = None
        section_name = None
        if app.settings_ini.key_exists(app.TOURROUNDID, "comp"):
            section_id, section_name = app.TOURROUNDID, "comp"
        elif app.settings_ini.key_exists(app.TOURNAME, "comp"):
            section_id, section_name = app.TOURNAME, "comp"
        elif app.settings_ini.key_exists(app.HID, "stadium"):
            section_id, section_name = app.HID, "stadium"
        if section_id:
            raw_value = app.settings_ini.read(section_id, section_name)
            valid_stadiums, _police, _pitch, _net = self._parse_assignment(raw_value)
            desired_stadium = valid_stadiums[0] if valid_stadiums else raw_value.split(",")[0]
            task_request_key = self._build_task_request_key(section_name, section_id, raw_value)
            stadium_signature = (app._kickoff_generation, section_name, section_id, raw_value, app.HID, app.TOURNAME, app.TOURROUNDID)
            if stadium_signature == app._last_stadium_applied_signature and app.curstad in valid_stadiums:
                app._set_progress(100, f"Stadium already loaded: {desired_stadium}")
                return
            if app._stadium_task_running:
                if task_request_key == app._stadium_task_request_key:
                    app.log(f"Stadium task already running for {desired_stadium}")
                else:
                    app.log(f"Stadium task busy; skipping new request for {desired_stadium}")
                return
            if desired_stadium == app.curstad:
                app.CCount = inc_count(0, app.CCount)
            app.injID, app.PoliceNum = set_inj_id(app.CCount)
            app._show_stadium_loading_modal(desired_stadium, "Preparing stadium assets", progress=4)
            app._set_process_status("Loading Stadium", app.gold)
            app._set_progress(8, f"Preparing stadium {section_id}")
            self.start_stadium_task(section_id, section_name, app.injID, stadium_signature, task_request_key)
            return
        app._last_stadium_applied_signature = None
        app._hide_stadium_loading_modal()
        app._set_progress(25, "Restoring default stadium")
        copy(app.exedir / "FSW" / "stadium", app.exedir / "data" / "sceneassets")
        app.curstad = ""
        app.ScoreboardStadName = ""
        app.stadmovie = False
        app._set_display("stadium", "Stadium Module Disable")
        app._update_audio_overview()
        app._set_progress(100, "Default stadium restored")
        app.log("No stadium assignment found; default stadium restored")

    def start_stadium_task(
        self,
        section_id: str,
        section_name: str,
        injid: str,
        stadium_signature: tuple,
        task_request_key: tuple[str, str, str],
    ) -> None:
        app = self.app
        app._stadium_task_running = True
        app._stadium_task_signature = stadium_signature
        app._stadium_task_request_key = task_request_key
        app._update_stadium_loading_modal(10, f"Loading stadium from [{section_name}] {section_id}")

        def worker() -> None:
            try:
                payload = self.run_stadium_copy_job(section_id, section_name, injid)
                app._worker_queue.put(("done", payload))
            except Exception as exc:
                app._worker_queue.put(("error", f"Failed to load stadium assets: {exc}\n{traceback.format_exc().strip()}"))

        threading.Thread(target=worker, daemon=True).start()
        app._schedule_worker_poll()

    def _resolve_stadium_source(self, stadium_name: str) -> tuple[str, Path, str]:
        app = self.app
        normalized_name = (stadium_name or "").strip()
        if not normalized_name or normalized_name == "None":
            raise RuntimeError("No stadium name was provided for runtime loading")
        folder_path = app.targetpath / normalized_name
        if folder_path.is_dir():
            return folder_path.name, folder_path, "folder"
        direct_path = app.targetpath / normalized_name
        if direct_path.is_file() and direct_path.suffix.lower() == ".rar":
            return direct_path.stem, direct_path, "rar"
        rar_path = app.targetpath / f"{normalized_name}.rar"
        if rar_path.is_file():
            return rar_path.stem, rar_path, "rar"
        raise RuntimeError(f"Assigned stadium source not found: {folder_path} or {rar_path}")

    @staticmethod
    def _looks_like_stadium_dir(path: Path) -> bool:
        required_markers = ("model.rx3", "texture_day.rx3", "texture_night.rx3", "crowd_day.dat", "crowd_night.dat")
        return any((path / marker).exists() for marker in required_markers)

    def _find_extracted_stadium_root(self, extracted_root: Path, preferred_name: str) -> Path:
        preferred_path = extracted_root / preferred_name
        if preferred_path.is_dir() and self._looks_like_stadium_dir(preferred_path):
            return preferred_path
        if self._looks_like_stadium_dir(extracted_root):
            return extracted_root
        matches: list[Path] = []
        for candidate in extracted_root.rglob("*"):
            if not candidate.is_dir():
                continue
            if candidate.name.startswith(".") or candidate.name.upper() == "__MACOSX":
                continue
            if candidate.name.casefold() == preferred_name.casefold() and self._looks_like_stadium_dir(candidate):
                return candidate
            if self._looks_like_stadium_dir(candidate):
                matches.append(candidate)
        if not matches:
            raise RuntimeError(f"Could not find a valid stadium folder inside extracted archive {preferred_name}")
        matches.sort(key=lambda path: (len(path.relative_to(extracted_root).parts), str(path).lower()))
        return matches[0]

    def _extract_rar_archive(self, archive_path: Path) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        app = self.app
        runtime_dir = app.base_dir / "runtime"
        runtime_dir.mkdir(parents=True, exist_ok=True)
        temp_dir = tempfile.TemporaryDirectory(prefix="stadium_rar_", dir=runtime_dir)
        extract_root = Path(temp_dir.name)
        startupinfo = None
        creationflags = 0
        if hasattr(subprocess, "STARTUPINFO") and hasattr(subprocess, "STARTF_USESHOWWINDOW"):
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            result = subprocess.run(
                ["tar", "-xf", str(archive_path), "-C", str(extract_root)],
                capture_output=True,
                text=True,
                check=False,
                startupinfo=startupinfo,
                creationflags=creationflags,
            )
        except FileNotFoundError as exc:
            temp_dir.cleanup()
            raise RuntimeError("The system tar extractor is not available for RAR support") from exc
        if result.returncode != 0:
            temp_dir.cleanup()
            details = (result.stderr or result.stdout or "").strip()
            raise RuntimeError(f"Failed to extract RAR archive {archive_path.name}: {details or 'unknown error'}")
        return temp_dir, self._find_extracted_stadium_root(extract_root, archive_path.stem)

    def run_stadium_copy_job(self, hid: str, section: str, injid: str) -> dict:
        app = self.app
        if not app.settings_ini.key_exists(hid, section):
            raise RuntimeError(f"Missing stadium assignment [{section}] {hid}")
        raw_value = app.settings_ini.read(hid, section)
        valid_stadiums, police, pitch, net = self._parse_assignment(raw_value)
        if len(valid_stadiums) == 0 and not all([police, pitch, net]):
            raise RuntimeError(f"Invalid stadium assignment [{section}] {hid}: {raw_value}")
        if not valid_stadiums:
            raise RuntimeError(f"No valid stadium names in assignment [{section}] {hid}")
        assigned_name = random.choice(valid_stadiums)
        stad_name, source_path, source_kind = self._resolve_stadium_source(assigned_name)
        dest = app.exedir / "data" / "sceneassets"
        extracted_dir: tempfile.TemporaryDirectory[str] | None = None
        try:
            if source_kind == "rar":
                app._worker_queue.put(("progress", 11, f"Extracting stadium archive {source_path.name}"))
                extracted_dir, stad = self._extract_rar_archive(source_path)
            else:
                stad = source_path
            glare1 = stad / "1"
            glare3 = stad / "3"
            no_seats = stad / "NoSeats.rx3"
            steps: list[tuple[str, callable]] = [
                ("Copying stadium model", lambda: copy_if_exists(stad / "model.rx3", dest / "stadium" / f"stadium_{injid}.rx3")),
                ("Copying day textures", lambda: copy_if_exists(stad / "texture_day.rx3", dest / "stadium" / f"stadium_{injid}_1_textures.rx3")),
                ("Copying night textures", lambda: copy_if_exists(stad / "texture_night.rx3", dest / "stadium" / f"stadium_{injid}_3_textures.rx3")),
                ("Copying entrance scene", lambda: copy_if_exists(stad / "EntranceScene" / f"bcstadiumcams_{injid}.dat", app.exedir / "data" / "bcdata" / "camera" / f"bcstadiumcams_{injid}.dat")),
                ("Copying crowd day", lambda: copy_if_exists(stad / "crowd_day.dat", dest / "crowdplacement" / f"crowd_{injid}_1.dat")),
                ("Copying crowd night", lambda: copy_if_exists(stad / "crowd_night.dat", dest / "crowdplacement" / f"crowd_{injid}_3.dat")),
            ]
            for suffix in range(4):
                steps.extend(
                    [
                        (f"Day glare {suffix}", lambda s=suffix: copy_glares(glare1 / f"glare1_{s}.lnx", "1", str(s), injid, app.exedir)),
                        (f"Day glare texture {suffix}", lambda s=suffix: copy_if_exists(glare1 / f"glare1_{s}.rx3", dest / "fx" / f"glares_{injid}_1_{s}.rx3")),
                        (f"Night glare {suffix}", lambda s=suffix: copy_glares(glare3 / f"glare3_{s}.lnx", "3", str(s), injid, app.exedir)),
                        (f"Night glare texture {suffix}", lambda s=suffix: copy_if_exists(glare3 / f"glare3_{s}.rx3", dest / "fx" / f"glares_{injid}_3_{s}.rx3")),
                    ]
                )
            steps.extend(
                [
                    ("Applying police setup", lambda: extra_setup(app.Psource, app.Pdest, police, "policeofficer", app.PoliceNum)),
                    ("Applying net setup", lambda: extra_setup(app.Nsource, app.Ndest, net, "netcolor", "0")),
                    ("Applying pitch setup", lambda: extra_setup(app.PitchMowsource, app.PitchMowdest, pitch, "pitchmowpattern", "0")),
                ]
            )
            if no_seats.exists():
                steps.append(("Applying crowd chairs", lambda: copy_if_exists(no_seats, app.exedir / "data" / "sceneassets" / "crowdchair" / f"specificchair_0_{injid}.rx3")))
            else:
                steps.extend(
                    [
                        ("Restoring crowd chair 176", lambda: copy_if_exists(app.exedir / "FSW" / "Stadium" / "crowdchair" / "specificchair_0_176.rx3", app.exedir / "data" / "sceneassets" / "crowdchair" / "specificchair_0_176.rx3")),
                        ("Restoring crowd chair 261", lambda: copy_if_exists(app.exedir / "FSW" / "Stadium" / "crowdchair" / "specificchair_0_261.rx3", app.exedir / "data" / "sceneassets" / "crowdchair" / "specificchair_0_261.rx3")),
                    ]
                )
            total_steps = max(1, len(steps))
            for index, (message, action) in enumerate(steps, start=1):
                progress = 12 + (index / total_steps) * 72
                app._worker_queue.put(("progress", progress, message))
                action()

            stadmovie = (stad / "StadiumMovie.vp8").exists() and (stad / "StadiumBumper.big").exists()
            if stadmovie:
                copy_if_exists(stad / "StadiumMovie.vp8", app.Movdata)
                copy_if_exists(stad / "StadiumBumper.big", app.MOVBUMP)
            return {
                "section_id": hid,
                "section_name": section,
                "injid": injid,
                "stad_name": stad_name,
                "stadmovie": stadmovie,
                "stadium_type": app.Stadiumtype,
            }
        finally:
            if extracted_dir is not None:
                extracted_dir.cleanup()

    def finish_stadium_apply(self, payload: dict) -> None:
        app = self.app
        try:
            offsets = self.stadium_offsets(payload.get("stadium_type", "first"))
            app._set_progress(90, "Writing stadium memory")
            app.memory.write_int(app.offsets.ORISTADIDBASE, offsets, payload["injid"])
            try:
                readback = str(app.memory.get_int(app.offsets.ORISTADIDBASE, offsets))
            except Exception:
                readback = ""
            if readback != str(payload["injid"]):
                fallback_type = "alter" if payload.get("stadium_type", "first") == "first" else "first"
                fallback_offsets = self.stadium_offsets(fallback_type)
                app.log(
                    f"Primary stadium write did not stick for {payload['stad_name']} "
                    f"(expected {payload['injid']}, got {readback or 'unknown'}). Retrying with {fallback_type} chain."
                )
                app.memory.write_int(app.offsets.ORISTADIDBASE, fallback_offsets, payload["injid"])
            std_offsets = app.offsets.STDNAMEOFFSET176 if payload["injid"] == "176" else app.offsets.STDNAMEOFFSET261
            stad_name = payload["stad_name"]
            # Extract display name for scoreboardstdname (used in Discord and UI)
            scoreboard_display_name = ""
            if app.settings_ini.key_exists(stad_name, "scoreboardstdname"):
                scoreboard_display_name = app.settings_ini.read(stad_name, "scoreboardstdname").split(",")[0]
            std_name = "_" + (scoreboard_display_name if scoreboard_display_name else stad_name)
            app.memory.write_string_with_offsets(app.offsets.STDNAMEBASE, std_offsets, std_name)
            app.CCount = inc_count(0, app.CCount)
            app.injID = payload["injid"]
            app.StadName = stad_name
            app.curstad = stad_name
            app.ScoreboardStadName = scoreboard_display_name  # Save display name for Discord RPC
            app.stadmovie = bool(payload["stadmovie"])
            app._set_display("stadium", stad_name)
            app._set_display("audio_last_action", f"Stadium {stad_name}")
            self.play_stadium_loaded_sound()
            app._set_progress(100, f"Stadium applied: {stad_name}")
            app._set_process_status("Stadium Ready", app.success)
            app._last_stadium_applied_signature = app._stadium_task_signature
            app._update_audio_overview()
            app.log(f"Applied stadium {stad_name} from [{payload['section_name']}] {payload['section_id']} using injID={payload['injid']}")
        finally:
            app._stadium_task_running = False
            app._stadium_task_signature = None
            app._stadium_task_request_key = None
            app._hide_stadium_loading_modal()

    def stadium_offsets(self, stadium_type: str) -> list[int]:
        app = self.app
        if stadium_type == "alter":
            return [app.offsets.S[0], app.offsets.S[1], app.offsets.S[3], app.offsets.S[4], app.offsets.S[5]]
        return [app.offsets.S[0], app.offsets.S[1], app.offsets.S[2], app.offsets.S[4], app.offsets.S[5]]

    def play_stadium_loaded_sound(self) -> None:
        try:
            winsound.MessageBeep(winsound.MB_OK)
        except Exception:
            try:
                winsound.Beep(1100, 180)
            except Exception:
                pass
