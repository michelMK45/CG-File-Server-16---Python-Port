from __future__ import annotations

import random
import re
import unicodedata
import tempfile
import threading
import traceback
import winsound
from pathlib import Path
from typing import TYPE_CHECKING

from . import file_tools as _ft_mod
from .file_tools import apply_specific_net_color, clear_bcgameplay, clear_goalpost, copy, copy_bcgameplay, copy_glares, copy_goalpost_sources, copy_if_exists, copy_or_clear, extra_setup, inc_count, restore_stadium_inj_files, set_inj_id, is_archive, extract_archive
from .kit_mixer import run_fifalibrary_worker

if TYPE_CHECKING:
    from .app import Server16App

_TRAILING_PAREN_RE = re.compile(r"\s*\([^()]*\)\s*$")


def _clean_db_display_name(raw: str) -> str:
    """Strip modding-DB conventions that never make it onto screen.

    Confirmed live 2026-09-09: `fifa_db.py`'s raw stadium-table lookup for
    injID 176 on a FIP install returned "_Waldstadion (Fussballstadion)", but
    the game only ever rendered "Waldstadion" — a leading "_" (a common
    modding-tool trick to sort an entry to the top of in-game lists) and a
    trailing " (...)" disambiguator (here, literally "football stadium" in
    German — an internal reference note, not player-facing text) are both
    stripped by FIFA's own UI before display. Search text for
    StadiumDbNamePatchCoordinator must match what's actually on screen, not
    the raw DB field, or the isolated-string scan will never find it.
    """
    text = raw.strip()
    if text.startswith("_"):
        text = text[1:]
    text = _TRAILING_PAREN_RE.sub("", text).strip()
    return text


class StadiumRuntime:
    def __init__(self, app: "Server16App") -> None:
        self.app = app

    def resolve_scoreboard_display_name(self, stad_name: str) -> str:
        """Resolve the [scoreboardstdname] display name for a stadium, or
        fall back to the stadium's own on-disk name when no override is
        configured."""
        app = self.app
        if app.settings_ini.key_exists(stad_name, "scoreboardstdname"):
            raw_std = app.settings_ini.read(stad_name, "scoreboardstdname")
            display_name = raw_std.split(",")[0].strip()
            return display_name if display_name else stad_name
        return stad_name

    def write_active_stad_name(self, std_name: str) -> bool:
        """Write the given display name into every known scoreboard
        stadium-name pointer chain (176/261, plus their "B" and "C"
        alternates — see offsets.py).

        The struct layout this leaf offset points into apparently shifts
        with FIFA build/mod, so more than one of these six chains can
        legitimately fail to resolve to a real string buffer on a given
        install — that is expected, not a bug, which is why each write is
        wrapped individually and only logged, never raised. Returns True if
        at least one slot was written and verified.
        """
        app = self.app
        if not app.memory.is_open():
            return False
        written = False
        slots = [
            ("176", app.offsets.STDNAMEOFFSET176),
            ("176B", app.offsets.STDNAMEOFFSET176B),
            ("176C", app.offsets.STDNAMEOFFSET176C),
            ("261", app.offsets.STDNAMEOFFSET261),
            ("261B", app.offsets.STDNAMEOFFSET261B),
            ("261C", app.offsets.STDNAMEOFFSET261C),
        ]
        for label, offsets in slots:
            try:
                safe_value, address = app.memory.write_string_with_offsets_safe(
                    app.offsets.STDNAMEBASE,
                    offsets,
                    std_name,
                    max_bytes=63,
                    validation_size=256,
                    # These buffers' previous contents are not guaranteed to
                    # be printable ASCII: FIFA can store localized text
                    # (UTF-8/Windows-1252) or leave internal bytes before the
                    # struct is fully initialized. Keep the NUL-bound, size
                    # cap and read-back verification, but do not reject the
                    # correct slot only because its old bytes are non-ASCII.
                    require_printable_existing=False,
                )
                if safe_value != std_name:
                    # write_string_safe's max_bytes=63 below is only a floor —
                    # it measures real zero-padding past the buffer's own NUL
                    # and uses that instead when there's more room (see
                    # Memory.write_string_safe's docstring) — so a truncation
                    # here means the buffer genuinely has no more space, not
                    # that a fixed 63-byte cap was hit.
                    app.log(
                        f"Stad name slot {label}: truncated '{std_name}' -> "
                        f"'{safe_value}' (buffer has no more room)"
                    )
                app.log(f"Stad name slot {label} verified at 0x{address:X}")
                written = True
            except Exception as exc:
                app.log(f"Stad name write skipped slot {label}: {exc}")
        return written

    def request_db_name_patch(self, injid: str, new_name: str) -> None:
        """Ask StadiumDbNamePatchCoordinator to rewrite the loaded
        fifa_ng_db.db stadium-name text for this container slot.

        The "old" name to search for is whatever StadiumDbNamePatchCoordinator
        has CONFIRMED (get_current_name -- set only on an actual successful
        read-verify or write-verify, never optimistically) is currently live
        in that slot's buffer, otherwise the slot's vanilla DB name (stadium
        ID == injid; see CLAUDE.md §7 Part 3's live-confirmed "Waldstadion"
        finding for why 176/261 double as real DB stadium IDs). Deliberately
        does NOT cache/assume `new_name` is now live itself -- an earlier
        version of this method did, and a live test (2026-09-09, Part 8)
        showed that broke every retry after the first: each retry recomputed
        old_name as the assumed-already-applied new_name, saw old==new, and
        silently skipped scanning again, even though the patch had never
        actually succeeded. As long as it keeps failing, this keeps resolving
        the same correct original name for every retry. A missing/unavailable
        team_db (32-bit bridge not connected) just means this soft-fails --
        the pointer-chain write in write_active_stad_name still runs
        regardless.
        """
        app = self.app
        old_name = app.stadium_db_name_patcher.get_current_name(injid)
        if not old_name:
            raw_db_name = app._resolve_stadium_name(injid)
            old_name = _clean_db_display_name(raw_db_name) if raw_db_name else None
        if old_name:
            app.stadium_db_name_patcher.request(injid, old_name, new_name)

    def has_assignment(self) -> bool:
        """Return True if there is a stadium assignment for the current match context."""
        app = self.app
        if app.settings_ini.key_exists(app.TOURROUNDID, "exclude") or app.settings_ini.key_exists(app.TOURNAME, "exclude"):
            return False
        return (
            app.settings_ini.key_exists(app.TOURROUNDID, "comp")
            or app.settings_ini.key_exists(app.TOURNAME, "comp")
            or app.settings_ini.key_exists(app.HID, "stadium")
        )

    @staticmethod
    def _parse_stadium_entries(raw_value: str) -> list[tuple[str, str, str, str]]:
        """Parse a [stadium]/[comp] settings.ini value into one (name, police,
        pitch, net) tuple per assigned stadium, transparently handling both
        formats found on disk:
          - legacy shared-triple: name1[,name2,...],police,pitch,net -- every
            name gets the SAME trailing triple. Still written by dialogs.py's
            "Assign Stadium" dialog and by db_worker-free direct edits.
          - per-stadium: name1,police1,pitch1,net1[,name2,police2,pitch2,net2,...]
            -- each stadium carries its own triple. Written by
            settings_editor.py's Stadium Settings editor and by the F12
            overlay wizard's stadium-assign flow once it appends to an
            existing key.
        Disambiguated without a new delimiter: the per-stadium format's total
        field count is always an exact multiple of 4, AND the field right
        after the first name is always numeric (a real stadium folder name is
        never a bare number, and police is always a plain small integer) --
        the legacy format's second field is only ever numeric when there is
        exactly one stadium, in which case both interpretations agree anyway
        so there is nothing to disambiguate.
        """
        parts = [part.strip() for part in raw_value.split(",") if part.strip()]
        if len(parts) < 4:
            return []
        if len(parts) % 4 == 0 and parts[1].isdigit():
            entries = []
            for i in range(0, len(parts), 4):
                name, police, pitch, net = parts[i:i + 4]
                if name and name != "None":
                    entries.append((name, police, pitch, net))
            return entries
        # Legacy shared-triple format: N names, then exactly 3 trailing values.
        police, pitch, net = parts[-3:]
        return [(name, police, pitch, net) for name in parts[:-3] if name and name != "None"]

    @staticmethod
    def _parse_assignment(raw_value: str) -> tuple[list[str], str, str, str]:
        """Legacy shared-triple view over _parse_stadium_entries, kept for
        callers that don't (yet) act on per-stadium police/pitch/net --
        dialogs.py's "Assign Stadium" dialog and apply_stadium_runtime's own
        candidate-name gathering below (which discards police/pitch/net
        entirely). For a genuinely per-stadium value this reports the first
        stadium's own triple as if it were shared -- an accepted, existing
        limitation for those call sites, not a new regression."""
        entries = StadiumRuntime._parse_stadium_entries(raw_value)
        if not entries:
            return [], "", "", ""
        names = [name for name, _police, _pitch, _net in entries]
        _name, police, pitch, net = entries[0]
        return names, police, pitch, net

    @staticmethod
    def _build_task_request_key(section_name: str, section_id: str, raw_value: str) -> tuple[str, str, str]:
        return section_name, section_id, raw_value

    @staticmethod
    def _read_goalpost_override_names(app, stad_name: str) -> tuple[str, str]:
        """The raw [stadiumgoalpost]/[stadiumgoalposttexture] override values for stad_name,
        each empty when unset. Shared by resolve_goalpost_sources (to build the actual source
        paths) and the goalpost-loaded toast notification (to name which specific pack was
        applied, instead of the already-known stadium name)."""
        model = ""
        if app.settings_ini.key_exists(stad_name, "stadiumgoalpost"):
            model = app.settings_ini.read(stad_name, "stadiumgoalpost").strip()
        texture = ""
        if app.settings_ini.key_exists(stad_name, "stadiumgoalposttexture"):
            texture = app.settings_ini.read(stad_name, "stadiumgoalposttexture").strip()
        return model, texture

    @staticmethod
    def resolve_goalpost_sources(app, stad: Path, stad_name: str) -> list[Path]:
        """Resolve where this stadium's goalpost assets come from. Deliberately keyed by
        stad_name (the already-resolved, single stadium folder -- see finish_stadium_apply's
        identical [scoreboardstdname] lookup) rather than any new field on [stadium]/[comp],
        so this never has to touch _parse_stadium_entries' own fragile comma-count heuristics
        for a team with several assigned stadiums.

        Model (the goalpost shape, e.g. specificgoalpost_18_0.rx3) and texture (the net/post
        color, e.g. specificnetsupportpost_0_0_textures.rx3) are independent, separately
        selectable packs -- a real-world pack ships them as sibling FSW/Goalpost/GoalpostModel/
        <name>/ and FSW/Goalpost/GoalpostColor/<name>/ folders, not one combined folder, since
        the same model is commonly paired with several different color variants and vice versa.
        [stadiumgoalpost] holds the model override, [stadiumgoalposttexture] the texture/color
        override -- both keyed by stad_name, independently optional.

        No override of EITHER kind for stad_name keeps the legacy behavior: the stadium pack's
        own bundled GoalpostGBD folder (mixed model+texture+whatever, arbitrary filenames), as
        a single source. The moment either override is set, GoalpostGBD is NOT also mixed in --
        only the explicit override source(s) are used, so there's never an ambiguous case where
        both a legacy file and an override file claim the same destination filename. A category
        left unset while the other IS overridden simply keeps whatever restore_goalnet_defaults
        already restored to vanilla for it (copy_goalpost_sources always clears+restores first)."""
        model, texture = StadiumRuntime._read_goalpost_override_names(app, stad_name)
        if not model and not texture:
            return [stad / "GoalpostGBD"]
        sources: list[Path] = []
        if model:
            sources.append(app.exedir / "FSW" / "Goalpost" / "GoalpostModel" / model)
        if texture:
            sources.append(app.exedir / "FSW" / "Goalpost" / "GoalpostColor" / texture)
        return sources

    def goalpost_texture_preview_dir(self) -> Path:
        return self.app.base_dir / "runtime" / "goalpost_texture_previews"

    def render_goalpost_texture_preview(self, source_rx3: Path, cache_key: str, max_size: int = 220) -> Path:
        """Renders a small PNG preview of a GoalpostColor pack's .rx3 texture
        (there's no dedicated preview-image convention on that side, unlike
        GoalpostModel's preview.<ext> -- see file_tools.
        resolve_goalpost_model_preview_path) via the same 32-bit
        kit_preview_worker.py bridge KitMixRuntime already uses for kit
        textures, role="rx3_texture" (no kit-specific jersey/shorts/crest
        classification -- a goalpost net/post texture has no such roles,
        just its first embedded bitmap). cache_key should be the pack name
        (e.g. "Azul") -- the same pack always renders to the same output
        file, reused across every dialog that previews it. Blocking -- call
        from a background thread when used from the UI, same convention as
        KitMixRuntime.render_preview."""
        output_path = self.goalpost_texture_preview_dir() / f"{cache_key}.png"
        config = {
            "source": str(source_rx3),
            "role": "rx3_texture",
            "output": str(output_path),
            "max_size": max_size,
        }
        result = run_fifalibrary_worker(config, worker_name="kit_preview_worker.py")
        return Path(result["output"])

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

    def _resolve_stadium_source(self, stadium_name: str) -> tuple[str, Path, str]:
        app = self.app
        normalized_name = (stadium_name or "").strip()
        if not normalized_name or normalized_name == "None":
            raise RuntimeError("No stadium name was provided for runtime loading")
        folder_path = app.targetpath / normalized_name
        if folder_path.is_dir():
            return folder_path.name, folder_path, "folder"
        direct_path = app.targetpath / normalized_name
        if direct_path.is_file() and is_archive(direct_path):
            return direct_path.stem, direct_path, "archive"
        for ext in (".zip", ".rar"):
            archive_path = app.targetpath / f"{normalized_name}{ext}"
            if archive_path.is_file() and is_archive(archive_path):
                return archive_path.stem, archive_path, "archive"

        name_nfc = unicodedata.normalize("NFC", normalized_name)
        name_nfd = unicodedata.normalize("NFD", normalized_name)
        try:
            for item in app.targetpath.iterdir():
                item_nfc = unicodedata.normalize("NFC", item.name)
                stem_nfc = unicodedata.normalize("NFC", item.stem)
                if item.is_dir() and item_nfc in {name_nfc, name_nfd}:
                    return item.name, item, "folder"
                if item.is_file() and item.suffix.lower() in {".zip", ".rar"} and stem_nfc in {name_nfc, name_nfd}:
                    if is_archive(item):
                        return item.stem, item, "archive"
        except Exception:
            pass

        raise RuntimeError(f"Assigned stadium source not found: {folder_path} or matching .zip/.rar archive")

    def apply_stadium_runtime(self) -> None:
        app = self.app
        if app.settings_ini.key_exists(app.TOURROUNDID, "exclude") or app.settings_ini.key_exists(app.TOURNAME, "exclude"):
            app.log(f"Stadium excluded for TOUR={app.TOURNAME} ROUND={app.TOURROUNDID}")
            # Clear stadium from previous match when this tournament/round is excluded
            app.curstad = ""
            app.ScoreboardStadName = ""
            clear_goalpost(app.exedir / "data" / "sceneassets" / "goalnet", app.exedir / "FSW" / ".goalpost_manifest", app.exedir / "FSW" / "GoalNet")
            clear_bcgameplay(app.exedir / "data" / "bcdata" / "camera", app.exedir / "FSW" / "bcdata" / "camera")
            extra_setup(app.Nsource, app.Ndest, "0", "netcolor", "0")
            return
        section_id = None
        section_name = None
        app._stadium_assignment_type = ""
        if app.settings_ini.key_exists(app.TOURROUNDID, "comp"):
            section_id, section_name = app.TOURROUNDID, "comp"
            app._stadium_assignment_type = "Round"
        elif app.settings_ini.key_exists(app.TOURNAME, "comp"):
            section_id, section_name = app.TOURNAME, "comp"
            app._stadium_assignment_type = "Tournament"
        elif app.settings_ini.key_exists(app.HID, "stadium"):
            section_id, section_name = app.HID, "stadium"
            app._stadium_assignment_type = "Home Team"
        if section_id:
            raw_value = app.settings_ini.read(section_id, section_name)
            valid_stadiums, _police, _pitch, _net = self._parse_assignment(raw_value)
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
            task_request_key = self._build_task_request_key(section_name, section_id, raw_value)
            stadium_signature = (app._kickoff_generation, section_name, section_id, raw_value, app.HID, app.TOURNAME, app.TOURROUNDID)
            manual_mode = (
                not app.random_stadium_selection_var.get()
                and getattr(app, "_d3d_injector", None) is not None
            )
            if len(valid_stadiums) > 1 and manual_mode:
                # Manual mode: let the player pick via the in-game stadium
                # picker instead of rolling randomly. Only one picker session
                # is ever open at a time — a matching pending signature means
                # this is the same assignment we already popped the picker
                # for; a different one means a new assignment needs a fresh
                # picker session (see _open_stadium_picker). No overlay
                # injector available (not injected yet / DLL missing) falls
                # straight through to random — there's nothing to show.
                # Deliberately independent of show_overlay_var: the picker
                # renders through the same always-on D3D overlay injection
                # and input loop the stadium-loading toast/modal already use
                # (see _sync_d3d_menu_input's own show_overlay_var gate),
                # not the F12 general menu — "Enable in-game overlay" toggles
                # that menu specifically, not this feature.
                if app._stadium_picker_pending and app._stadium_picker_signature == stadium_signature:
                    if not app._stadium_picker_resolved:
                        return  # still waiting on the player; don't re-show, don't re-roll
                    desired_stadium = app._stadium_picker_chosen or self._random_stadium_choice(app.curstad, valid_stadiums)
                    app._stadium_picker_pending = False
                    app._stadium_picker_decided_signature = stadium_signature
                    app._stadium_picker_decided_stadium = desired_stadium
                elif app._stadium_picker_decided_signature == stadium_signature:
                    # Already asked-and-answered for this exact assignment
                    # this match (picker resolved, or closed/cancelled ->
                    # random fallback) -- a later re-entrant call for the
                    # SAME stadium_signature must reuse that decision rather
                    # than popping a brand-new picker on top of one the
                    # player already closed. See _stadium_picker_decided_signature's
                    # own comment (app.py) for the concrete trigger.
                    desired_stadium = app._stadium_picker_decided_stadium
                else:
                    self._open_stadium_picker(valid_stadiums, stadium_signature)
                    return
            else:
                desired_stadium = self._random_stadium_choice(app.curstad, valid_stadiums)
            if stadium_signature == app._last_stadium_applied_signature and app.curstad == desired_stadium:
                app._set_progress(100, f"Stadium already loaded: {desired_stadium}")
                return
            if app._stadium_task_running:
                if task_request_key == app._stadium_task_request_key or stadium_signature == app._stadium_task_signature:
                    app.log(f"Stadium task already running for {desired_stadium}")
                else:
                    app.log(f"Stadium task busy; skipping new request for {desired_stadium}")
                return
            if desired_stadium == app.curstad:
                app.CCount = inc_count(0, app.CCount)
            app.injID, app.PoliceNum = set_inj_id(app.CCount)
            app._set_process_status("Loading Stadium", app.gold)
            self.start_stadium_task(
                section_id,
                section_name,
                app.injID,
                stadium_signature,
                task_request_key,
                chosen_stadium=desired_stadium,
            )
            return
        app._last_stadium_applied_signature = None
        app._hide_stadium_loading_modal()
        app._set_progress(25, "Restoring default stadium")
        copy(app.exedir / "FSW" / "stadium", app.exedir / "data" / "sceneassets")
        clear_goalpost(app.exedir / "data" / "sceneassets" / "goalnet", app.exedir / "FSW" / ".goalpost_manifest", app.exedir / "FSW" / "GoalNet")
        clear_bcgameplay(app.exedir / "data" / "bcdata" / "camera", app.exedir / "FSW" / "bcdata" / "camera")
        extra_setup(app.Nsource, app.Ndest, "0", "netcolor", "0")
        app.curstad = ""
        app.ScoreboardStadName = ""
        app.stadmovie = False
        app._set_display("stadium", "-")
        app._update_audio_overview()
        app._set_progress(100, "Default stadium restored")
        app.log("No stadium assignment found; default stadium restored")

    @staticmethod
    def _random_stadium_choice(current: str, valid_stadiums: list[str]) -> str:
        """Pick a stadium at random from valid_stadiums, excluding the
        currently-loaded one when there's more than one option so back-to-
        back matches against the same team/round/tournament don't repeat the
        same stadium. Shared by both the "random selection" checkbox path
        and the manual picker's "closed without picking" fallback."""
        if len(valid_stadiums) > 1 and current in valid_stadiums:
            candidates = [s for s in valid_stadiums if s != current]
        else:
            candidates = valid_stadiums
        return random.choice(candidates)

    def _open_stadium_picker(self, candidates: list[str], signature: tuple) -> None:
        """Show the in-game stadium-picker overlay panel and mark it pending
        for `signature` — apply_stadium_runtime() returns without loading
        anything until _handle_stadium_picker_event (app_overlay.py) records
        a resolution (a click, a close, or the page-transition safety net in
        app_game.py giving up on it)."""
        app = self.app
        inj = getattr(app, "_d3d_injector", None)
        if inj is None:
            # No overlay available (not injected yet / DLL missing) — there's
            # nothing to show, so don't stall stadium loading waiting for an
            # interaction that can never happen. Deliberately not gated on
            # show_overlay_var ("Enable in-game overlay") — that toggle only
            # controls the F12 general menu; the picker uses the same
            # always-on injection/input loop as the stadium-loading toast.
            app.log("Stadium picker requested but no overlay is available; using random selection instead")
            return
        thumbs = [str(app._resolve_stadium_preview_path_or_default(name) or "") for name in candidates]
        header = app.tr("overlay.stadium_picker.header")
        app._stadium_picker_index = 0
        inj.show_stadium_picker(header, candidates, thumbs, selected=0)
        app._install_keyboard_hook()
        app._install_mouse_wheel_hook()
        app._stadium_picker_pending = True
        app._stadium_picker_signature = signature
        app._stadium_picker_resolved = False
        app._stadium_picker_chosen = None
        app._stadium_picker_candidates = list(candidates)
        # Clear any gamepad A/B release-latch left over from a previous
        # picker session (see app_overlay.py's tick handling) so a stale
        # pending confirm/cancel can never bleed into this fresh one.
        app._stadium_picker_gp_confirm_pending = None
        app._stadium_picker_gp_cancel_pending = False
        app.log(f"Stadium picker opened for [{signature[1]}] {signature[2]} with {len(candidates)} candidates")

    def start_stadium_task(
        self,
        section_id: str,
        section_name: str,
        injid: str,
        stadium_signature: tuple,
        task_request_key: tuple[str, str, str],
        chosen_stadium: str | None = None,
    ) -> None:
        app = self.app
        app._stadium_task_running = True
        app._stadium_task_signature = stadium_signature
        app._stadium_task_request_key = task_request_key
        app._show_stadium_loading_modal(chosen_stadium or section_id, "Preparing stadium assets", progress=4)
        app._set_progress(8, f"Preparing stadium {section_id}")
        app._update_stadium_loading_modal(10, f"Loading stadium from [{section_name}] {section_id}")
        # Write the stadium name to memory immediately — before file copying starts —
        # so it is already in place when FIFA renders the match intro screen.
        # Avoid patching fifa_ng_db.db on disk (db_patcher.py) — that change can
        # survive the match lifecycle and leave the game crashing on the next
        # launch (see CLAUDE.md §7, "Nono's version" on-disk DB corruption bug).
        # Patch FIFA memory only, for the current session, through three
        # independent, best-effort mechanisms that don't depend on each other
        # (see CLAUDE.md §7 Part 3's live findings on which one actually
        # affects the pre-match screen):
        if chosen_stadium:
            std_name = self.resolve_scoreboard_display_name(chosen_stadium)
            if self.write_active_stad_name(std_name):
                app.log(f"Stadium name pre-written to memory: {std_name}")
            # HID/AID aren't resolved yet this early in the flow (this runs
            # before refresh_live_context's own read of them for the new
            # match), so this mostly seeds the coordinator's context for the
            # request from finish_stadium_apply()/the TV-bumper transition to
            # reuse; if HID/AID do happen to already be set (re-roll of the
            # same match) it can patch immediately in the background.
            app.match_string_patcher.request(std_name)
            # The mechanism confirmed live to actually be worth pursuing:
            # rewrite FIFA's own loaded fifa_ng_db.db stadium-name text for
            # this slot. injid is already known here (unlike HID/AID above).
            self.request_db_name_patch(injid, std_name)

        # NOTE: the injection slot ID is intentionally NOT pre-written here.
        # Writing it before the background copy job has cleared/populated the
        # target slot's files created a race: if FIFA read the new injID from
        # memory before the (often archive-extraction-based) file copy finished,
        # it would find an empty/partial slot and silently fall back to the
        # vanilla default stadium for that container (176/261 mismatch bug).
        # finish_stadium_apply() writes+verifies (with readback and retry) the
        # injID only after the copy job has fully completed, which is the only
        # safe time to do so.

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
        raw_value = app.settings_ini.read(hid, section)
        entries = self._parse_stadium_entries(raw_value)
        valid_stadiums = [name for name, _police, _pitch, _net in entries]
        if not valid_stadiums:
            raise RuntimeError(f"No valid stadium names in assignment [{section}] {hid}: {raw_value}")
        # Use the pre-selected stadium if provided (chosen in apply_stadium_runtime),
        # otherwise fall back to random.choice (e.g. when called directly).
        chosen = (chosen_stadium or "").strip()
        if chosen and chosen in valid_stadiums:
            stad_name = chosen
        else:
            stad_name = random.choice(valid_stadiums)
        # Resolve THIS stadium's own police/pitch/net (each stadium can carry its
        # own values now -- see _parse_stadium_entries) before stad_name below gets
        # reassigned to its resolved on-disk form.
        police, pitch, net = next((p, pi, n) for name, p, pi, n in entries if name == stad_name)
        stad_name, source_path, source_kind = self._resolve_stadium_source(stad_name)
        # Support zip/rar archives: extract to a temp folder and work from there
        _temp_dir = None
        if source_kind == "archive":
            runtime_dir = app.base_dir / "runtime"
            runtime_dir.mkdir(parents=True, exist_ok=True)
            _temp_dir = tempfile.mkdtemp(prefix="server16_stad_", dir=runtime_dir)
            try:
                _rarmod_before = _ft_mod._rarmod
                if _rarmod_before is None:
                    app._worker_queue.put(("progress", 3, "Installing rarfile library..."))
                    app.log("rarfile not found — attempting automatic installation")
                app._worker_queue.put(("progress", 5, f"Extracting {source_path.name}..."))
                def _zip_progress(current, total, filename):
                    pct = 5 + int((current / max(1, total)) * 6)
                    short = filename if len(filename) <= 40 else "..." + filename[-37:]
                    app._worker_queue.put(("progress", pct, f"Extracting {short} ({current}/{total})"))
                extract_archive(source_path, Path(_temp_dir), progress_callback=_zip_progress)
                _rarmod_after = _ft_mod._rarmod
                if _rarmod_before is None and _rarmod_after is not None:
                    app.log("rarfile installed successfully — RAR archives now fully supported")
                elif _rarmod_before is not None and _rarmod_after is not _rarmod_before:
                    app.log("rarfile upgraded successfully — RAR5 archives now fully supported")
                elif _rarmod_before is not None and _rarmod_after is None:
                    app.log("rarfile upgrade failed — extracted via system tar fallback")
                elif _rarmod_before is None and _rarmod_after is None:
                    app.log("rarfile installation failed — extracted via system tar fallback")
                stad = self._find_extracted_stadium_root(Path(_temp_dir), source_path.stem)
                app.log(f"Archive extracted to: {stad}")
            except Exception:
                # Cleanup temp dir if extraction fails
                import shutil as _shutil2
                _shutil2.rmtree(_temp_dir, ignore_errors=True)
                _temp_dir = None
                raise
        elif source_path.exists():
            stad = source_path
        else:
            raise RuntimeError(f"Assigned stadium folder or archive not found: {source_path}")
        dest = app.exedir / "data" / "sceneassets"
        other_id = "261" if injid == "176" else "176"
        # Reset the other slot to its vanilla default rather than emptying it, so it's
        # never left in a broken/missing state (see restore_stadium_inj_files docstring).
        restore_stadium_inj_files(dest, app.exedir / "FSW" / "Stadium", other_id)
        # Also reset the slot we're about to write into. copy_if_exists() below only
        # overwrites a file if the new stadium's source actually has it — an
        # incomplete custom pack (missing e.g. one glare or crowd file) would
        # otherwise leave whatever was in this slot before (leftover vanilla
        # content from a "no assignment" match, or a previous custom stadium)
        # mixed in with the new one, which is a real mechanism for the green/blue
        # placeholder-texture mismatch. Restoring to a known-clean vanilla
        # baseline first means any gap in the new pack falls back to vanilla
        # instead of stale/mismatched leftovers.
        restore_stadium_inj_files(dest, app.exedir / "FSW" / "Stadium", injid)
        # These must be calculated AFTER stad is resolved
        glare1 = stad / "1"
        glare3 = stad / "3"
        no_seats = stad / "NoSeats.rx3"
        steps: list[tuple[str, callable]] = [
            ("Copying stadium model", lambda: copy_if_exists(stad / "model.rx3", dest / "stadium" / f"stadium_{injid}.rx3")),
            ("Copying day textures", lambda: copy_if_exists(stad / "texture_day.rx3", dest / "stadium" / f"stadium_{injid}_1_textures.rx3")),
            ("Copying night textures", lambda: copy_if_exists(stad / "texture_night.rx3", dest / "stadium" / f"stadium_{injid}_3_textures.rx3")),
            ("Copying entrance scene", lambda: copy_or_clear(stad / "EntranceScene" / f"bcstadiumcams_{injid}.dat", app.exedir / "data" / "bcdata" / "camera" / f"bcstadiumcams_{injid}.dat")),
            ("Copying gameplay camera", lambda: copy_bcgameplay(stad / "GameplayCamGBD", app.exedir / "data" / "bcdata" / "camera", app.exedir / "FSW" / "bcdata" / "camera")),
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
        def _apply_net_color() -> None:
            # Also write the slot-specific override (specificnetcolor_0_{injid}_...) that
            # goalnet.lua checks before the shared netcolor_0_* fallback below. The shared
            # fallback alone only ever takes effect right after a game restart, because the
            # engine caches netcolor_0_* the first time it loads it and never re-reads it —
            # the slot-specific path gives it a filename it hasn't already cached this session.
            specific = apply_specific_net_color(app.Nsource, app.Ndest, net, injid)
            generic = extra_setup(app.Nsource, app.Ndest, net, "netcolor", "0")
            copied = specific + generic
            if copied:
                app.log(f"Net color applied for {stad_name}: source index [{net}] -> {copied}")
            else:
                app.log(f"Net color NOT applied for {stad_name}: no file matching 'netcolor_{net}_' found in {app.Nsource}")

        steps.extend(
            [
                ("Applying police setup", lambda: extra_setup(app.Psource, app.Pdest, police, "policeofficer", app.PoliceNum)),
                ("Applying net setup", _apply_net_color),
                ("Applying pitch setup", lambda: extra_setup(app.PitchMowsource, app.PitchMowdest, pitch, "pitchmowpattern", "0")),
            ]
        )
        goalpost_model, goalpost_texture = self._read_goalpost_override_names(app, stad_name)
        goalpost_sources = self.resolve_goalpost_sources(app, stad, stad_name)
        _goalpost_overrides_root = app.exedir / "FSW" / "Goalpost"
        for _gp_src in goalpost_sources:
            if _gp_src.parent.parent == _goalpost_overrides_root and not _gp_src.is_dir():
                app.log(f"Goalpost pack not found for {stad_name}: {_gp_src}")
        _goalpost_manifest = app.exedir / "FSW" / ".goalpost_manifest"
        _fsw_goalnet_dir = app.exedir / "FSW" / "GoalNet"
        steps.append(("Applying goalpost models", lambda: copy_goalpost_sources(goalpost_sources, dest / "goalnet", _goalpost_manifest, _fsw_goalnet_dir)))
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

        # Queue toast notifications for custom assets that were applied
        _bcgp_dir = stad / "GameplayCamGBD"
        if _bcgp_dir.is_dir() and any((_bcgp_dir / n).exists() for n in ("bcgameplay_176.dat", "bcgameplay_261.dat")):
            app._worker_queue.put(("toast", app.tr("notify.bcgameplay_loaded"), stad_name, 3500, ""))

        def _goalpost_src_has_files(src: Path) -> bool:
            return src.is_dir() and next((f for f in src.rglob("*") if f.is_file() and f.suffix.lower() != ".png"), None) is not None

        if goalpost_model or goalpost_texture:
            # Independent model/texture overrides -- name the actual pack applied in each
            # toast instead of the stadium name, which the user already knows and which no
            # longer says anything about which goalpost look is active (see
            # resolve_goalpost_sources' docstring). goalpost_sources is built in this same
            # model-then-texture order, only including whichever of the two is set, so it
            # can be consumed positionally here.
            _gp_srcs = iter(goalpost_sources)
            if goalpost_model and _goalpost_src_has_files(next(_gp_srcs)):
                app._worker_queue.put(("toast", app.tr("notify.goalpost_model_loaded"), goalpost_model, 3500, "goalpost"))
            if goalpost_texture and _goalpost_src_has_files(next(_gp_srcs)):
                app._worker_queue.put(("toast", app.tr("notify.goalpost_texture_loaded"), goalpost_texture, 3500, "goalpost"))
        elif any(_goalpost_src_has_files(src) for src in goalpost_sources):
            # Legacy: goalpost assets bundled with the stadium pack's own GoalpostGBD folder --
            # keep the original single notification naming the stadium.
            app._worker_queue.put(("toast", app.tr("notify.goalpost_loaded"), stad_name, 3500, "goalpost"))

        stadmovie = (stad / "StadiumMovie.vp8").exists() and (stad / "StadiumBumper.big").exists()
        if stadmovie:
            copy_if_exists(stad / "StadiumMovie.vp8", app.Movdata)
            copy_if_exists(stad / "StadiumBumper.big", app.MOVBUMP)
        # Verify that at least the stadium model was written — if not, log a warning
        # so users can diagnose archive extraction issues (e.g. unsupported RAR format).
        key_dst = dest / "stadium" / f"stadium_{injid}.rx3"
        if not key_dst.exists():
            present = [
                name
                for name in (
                    f"stadium_{injid}_1_textures.rx3",
                    f"stadium_{injid}_3_textures.rx3",
                )
                if (dest / "stadium" / name).exists()
            ]
            app.log(
                f"Warning: stadium model not found at {key_dst} after copy. "
                + (f"Partial files present: {present}" if present else "No slot files written — check archive format.")
            )
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
            # Extract display name for scoreboardstdname (used in Discord and UI)
            scoreboard_display_name = ""
            if app.settings_ini.key_exists(stad_name, "scoreboardstdname"):
                scoreboard_display_name = app.settings_ini.read(stad_name, "scoreboardstdname").split(",")[0].strip()

            # Write the stadium name through all three independent, best-
            # effort mechanisms -- see StadiumRuntime.write_active_stad_name,
            # MatchStringPatchCoordinator and StadiumDbNamePatchCoordinator
            # (CLAUDE.md §7 Part 3 for which one is actually confirmed live
            # to affect this screen).
            std_name = scoreboard_display_name if scoreboard_display_name else stad_name
            if self.write_active_stad_name(std_name):
                app.log(f"Stadium name written to memory: {std_name}")
            app.match_string_patcher.request(std_name)
            self.request_db_name_patch(payload["injid"], std_name)
            app.CCount = inc_count(0, app.CCount)
            app.injID = payload["injid"]
            app.StadName = stad_name
            app.curstad = stad_name
            app.ScoreboardStadName = scoreboard_display_name  # Save display name for Discord RPC
            app.stadmovie = bool(payload["stadmovie"])
            app._set_display("stadium", stad_name)
            app._set_display("audio_last_action", f"Stadium {stad_name}")
            app._set_progress(100, f"Stadium applied: {stad_name}")
            app._set_process_status("Stadium Ready", app.success)
            self.play_stadium_loaded_sound()
            app._last_stadium_applied_signature = app._stadium_task_signature
            app._update_audio_overview()
            app.log(f"Applied stadium {stad_name} from [{payload['section_name']}] {payload['section_id']} using injID={payload['injid']}")
        finally:
            app._stadium_task_running = False
            app._stadium_task_signature = None
            app._stadium_task_request_key = None
            app._hide_stadium_loading_modal(delay_ms=1200)

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
