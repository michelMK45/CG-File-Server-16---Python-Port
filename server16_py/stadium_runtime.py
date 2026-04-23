from __future__ import annotations

import random
import unicodedata
import threading
import traceback
import winsound
from pathlib import Path
from typing import TYPE_CHECKING

from .db_patcher import patch_stadium_names, restore_stadium_names
from .file_tools import copy, copy_glares, copy_if_exists, extra_setup, inc_count, set_inj_id, is_archive, extract_archive
from .match_string_patcher import patch_match_string

if TYPE_CHECKING:
    from .app import Server16App


class StadiumRuntime:
    def __init__(self, app: "Server16App") -> None:
        self.app = app

    def apply_stadium_runtime(self) -> None:
        app = self.app
        if app.settings_ini.key_exists(app.TOURROUNDID, "exclude") or app.settings_ini.key_exists(app.TOURNAME, "exclude"):
            app.log(f"Stadium excluded for TOUR={app.TOURNAME} ROUND={app.TOURROUNDID}")
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
            parts = raw_value.split(",")
            # Last 3 fields are always police, pitch, net — stadiums come before them
            stadiums_in_value = parts[:-3] if len(parts) >= 4 else parts[:1]
            valid_stadiums = [s for s in stadiums_in_value if s and s != "None"]
            if not valid_stadiums:
                app.log(f"No valid stadiums in assignment [{section_name}] {section_id}: {raw_value}")
                return
            # Filter to stadiums that exist as folder OR as archive
            def _stad_exists(name: str) -> bool:
                # Check direct match
                if (app.targetpath / name).exists():
                    return True
                for ext in (".zip", ".rar"):
                    if (app.targetpath / (name + ext)).exists():
                        return True
                # Check with Unicode normalization (NFC vs NFD mismatch)
                name_nfc = unicodedata.normalize("NFC", name)
                name_nfd = unicodedata.normalize("NFD", name)
                try:
                    for item in app.targetpath.iterdir():
                        item_nfc = unicodedata.normalize("NFC", item.name)
                        if item_nfc == name_nfc or item_nfc == name_nfd:
                            return True
                        stem_nfc = unicodedata.normalize("NFC", item.stem)
                        if stem_nfc == name_nfc or stem_nfc == name_nfd:
                            if item.suffix.lower() in (".zip", ".rar"):
                                return True
                except Exception:
                    pass
                return False
            existing_stadiums = [s for s in valid_stadiums if _stad_exists(s)]
            if existing_stadiums:
                valid_stadiums = existing_stadiums
            # Pick the random stadium here, before the dedup check.
            # If there are multiple options, exclude the currently loaded stadium
            # so we always rotate to a different one each kickoff.
            if len(valid_stadiums) > 1 and app.curstad in valid_stadiums:
                candidates = [s for s in valid_stadiums if s != app.curstad]
            else:
                candidates = valid_stadiums
            desired_stadium = random.choice(candidates)
            stadium_signature = (app._kickoff_generation, section_name, section_id, raw_value, app.HID, app.TOURNAME, app.TOURROUNDID)
            if stadium_signature == app._last_stadium_applied_signature and app.curstad == desired_stadium:
                app._set_progress(100, f"Stadium already loaded: {desired_stadium}")
                return
            if app._stadium_task_running:
                if stadium_signature == app._stadium_task_signature:
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
            self.start_stadium_task(section_id, section_name, app.injID, stadium_signature, chosen_stadium=desired_stadium)
            return
        app._last_stadium_applied_signature = None
        app._hide_stadium_loading_modal()
        app._set_progress(25, "Restoring default stadium")
        copy(app.exedir / "FSW" / "stadium", app.exedir / "data" / "sceneassets")
        app.curstad = ""
        app.stadmovie = False
        app._set_display("stadium", "Stadium Module Disable")
        app._update_audio_overview()
        app._set_progress(100, "Default stadium restored")
        app.log("No stadium assignment found; default stadium restored")

    def start_stadium_task(self, section_id: str, section_name: str, injid: str, stadium_signature: tuple, chosen_stadium: str | None = None) -> None:
        app = self.app
        app._stadium_task_running = True
        app._stadium_task_signature = stadium_signature
        app._update_stadium_loading_modal(10, f"Loading stadium from [{section_name}] {section_id}")
        # Write the stadium name to memory immediately — before file copying starts —
        # so it is already in place when FIFA renders the match intro screen.
        if chosen_stadium:
            # Resolve the display name from scoreboardstdname ini key
            if app.settings_ini.key_exists(chosen_stadium, "scoreboardstdname"):
                raw_std = app.settings_ini.read(chosen_stadium, "scoreboardstdname")
                display_name = raw_std.split(",")[0].strip()
                std_name = display_name if display_name else chosen_stadium
            else:
                std_name = chosen_stadium
            # 1) Patch the DB file (in case FIFA re-reads it)
            patch_stadium_names(app, std_name, std_name)
            # 2) Scan FIFA memory and patch the pipe-delimited match string directly
            patch_match_string(app, std_name)
            # 2) Also pre-write to memory for the scoreboard
            if app.memory.is_open():
                try:
                    app.memory.write_string_with_offsets(app.offsets.STDNAMEBASE, app.offsets.STDNAMEOFFSET176, "_" + std_name)
                    app.memory.write_string_with_offsets(app.offsets.STDNAMEBASE, app.offsets.STDNAMEOFFSET261, "_" + std_name)
                    app.log(f"Stadium name pre-written to memory: _{std_name}")
                except Exception as exc:
                    app.log(f"Failed to pre-write stadium name to memory", exc)

        def worker() -> None:
            try:
                payload = self.run_stadium_copy_job(section_id, section_name, injid, chosen_stadium=chosen_stadium)
                app._worker_queue.put(("done", payload))
            except Exception as exc:
                app._worker_queue.put(("error", f"Failed to load stadium assets: {exc}\n{traceback.format_exc().strip()}"))

        threading.Thread(target=worker, daemon=True).start()
        app._schedule_worker_poll()

    def run_stadium_copy_job(self, hid: str, section: str, injid: str, chosen_stadium: str | None = None) -> dict:
        app = self.app
        if not app.settings_ini.key_exists(hid, section):
            raise RuntimeError(f"Missing stadium assignment [{section}] {hid}")
        parts = app.settings_ini.read(hid, section).split(",")
        if len(parts) < 4:
            raise RuntimeError(f"Invalid stadium assignment [{section}] {hid}: {parts}")
        police, pitch, net = parts[-3:]
        stadiums = parts[:-3]
        valid_stadiums = [name for name in stadiums if name and name != "None"]
        if not valid_stadiums:
            raise RuntimeError(f"No valid stadium names in assignment [{section}] {hid}")
        # Use the pre-selected stadium if provided (chosen in apply_stadium_runtime),
        # otherwise fall back to random.choice (e.g. when called directly).
        if chosen_stadium and chosen_stadium in valid_stadiums:
            stad_name = chosen_stadium
        else:
            stad_name = random.choice(valid_stadiums)
        # Support zip/rar archives: extract to a temp folder and work from there
        _temp_dir = None
        # Resolve the actual folder/archive name on disk (handles NFC/NFD mismatch)
        def _resolve_actual_name(name: str) -> str:
            name_nfc = unicodedata.normalize("NFC", name)
            try:
                for item in app.targetpath.iterdir():
                    if unicodedata.normalize("NFC", item.name) == name_nfc:
                        return item.name
                    if unicodedata.normalize("NFC", item.stem) == name_nfc and item.suffix.lower() in (".zip", ".rar"):
                        return item.stem
            except Exception:
                pass
            return name
        resolved_name = _resolve_actual_name(stad_name)
        stad_folder = app.targetpath / resolved_name
        # Also check for archive files: StadiumName.zip or StadiumName.rar
        archive_path = None
        for ext in (".zip", ".rar"):
            candidate = app.targetpath / (resolved_name + ext)
            if candidate.exists() and is_archive(candidate):
                archive_path = candidate
                break
        if archive_path is not None:
            import tempfile as _tempfile
            _temp_dir = _tempfile.mkdtemp(prefix="server16_stad_")
            try:
                app._worker_queue.put(("progress", 5, f"Extracting {archive_path.name}..."))
                def _zip_progress(current, total, filename):
                    pct = 5 + int((current / max(1, total)) * 6)
                    short = filename if len(filename) <= 40 else "..." + filename[-37:]
                    app._worker_queue.put(("progress", pct, f"Extracting {short} ({current}/{total})"))
                extract_archive(archive_path, Path(_temp_dir), progress_callback=_zip_progress)
                # The archive may contain a subfolder with the stadium name or dump files directly
                extracted = Path(_temp_dir)
                # Look for the actual stadium content - could be in root or a subfolder
                subfolders = [p for p in extracted.iterdir() if p.is_dir()]
                files_in_root = [p for p in extracted.iterdir() if p.is_file()]
                if len(subfolders) == 1 and not files_in_root:
                    stad = subfolders[0]
                elif any(f.name.lower() in ("model.rx3", "texture_day.rx3", "texture_night.rx3") for f in files_in_root):
                    stad = extracted
                elif len(subfolders) == 1:
                    stad = subfolders[0]
                else:
                    stad = extracted
                app.log(f"Archive extracted to: {stad}")
            except Exception:
                # Cleanup temp dir if extraction fails
                import shutil as _shutil2
                _shutil2.rmtree(_temp_dir, ignore_errors=True)
                _temp_dir = None
                raise
        elif stad_folder.exists():
            stad = stad_folder
        else:
            raise RuntimeError(f"Assigned stadium folder or archive not found: {stad_folder}")
        dest = app.exedir / "data" / "sceneassets"
        # These must be calculated AFTER stad is resolved
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
        # Clean up temp dir if we extracted an archive
        if _temp_dir is not None:
            try:
                import shutil as _shutil
                _shutil.rmtree(_temp_dir, ignore_errors=True)
            except Exception:
                pass
        return {
            "section_id": hid,
            "section_name": section,
            "injid": injid,
            "stad_name": stad_name,
            "stadmovie": stadmovie,
            "stadium_type": app.Stadiumtype,
        }

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
            stad_name = payload["stad_name"]
            # Write stadium name to memory — same logic as the original legacy C# code.
            # Format in ini: [scoreboardstdname] FolderName=Display Name
            # Both slots (176 and 261) use the same scoreboardstdname key.
            std_offsets_176 = app.offsets.STDNAMEOFFSET176
            std_offsets_261 = app.offsets.STDNAMEOFFSET261
            if app.settings_ini.key_exists(stad_name, "scoreboardstdname"):
                raw_std = app.settings_ini.read(stad_name, "scoreboardstdname")
                # Split by comma and take first part, matching legacy Split(',')[0]
                display_name = raw_std.split(",")[0].strip()
                std_name = "_" + display_name if display_name else "_" + stad_name
            else:
                std_name = "_" + stad_name
            try:
                app.memory.write_string_with_offsets(app.offsets.STDNAMEBASE, std_offsets_176, std_name)
                app.memory.write_string_with_offsets(app.offsets.STDNAMEBASE, std_offsets_261, std_name)
                app.log(f"Stadium name written to memory: {std_name}")
            except Exception as exc:
                app.log(f"Failed to write stadium name to memory", exc)
            app.CCount = inc_count(0, app.CCount)
            app.injID = payload["injid"]
            app.StadName = stad_name
            app.curstad = stad_name
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
