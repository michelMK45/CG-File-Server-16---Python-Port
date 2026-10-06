from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import TYPE_CHECKING

from .file_tools import (
    copy,
    copy_if_exists,
    copy_tvlogo,
    install_tracked_files,
    install_tracked_selection,
    list_pack_files,
    restore_tracked_files,
)
from .kit_mixer import run_fifalibrary_worker
from .match_asset_ids import engine_id, plan_pack_remap, read_lua_id_maps

if TYPE_CHECKING:
    from .app import Server16App


class AssetRuntime:
    # Longest side of a rendered texture PNG. The Match Assets preview box is
    # ~420px wide and the grid picker downscales further, so 512 covers both
    # (the PNGs are cached, so a bigger one would only cost disk).
    RX3_PREVIEW_MAX_SIZE = 512

    def __init__(self, app: "Server16App") -> None:
        self.app = app
        # One lock per cache folder: the preview panel and the grid picker both
        # render packs on their own threads and can ask for the same .rx3 at once.
        self._rx3_render_locks: dict[str, threading.Lock] = {}
        self._rx3_render_locks_guard = threading.Lock()

    def match_asset_preview_dir(self) -> Path:
        return self.app.base_dir / "runtime" / "match_asset_previews"

    def render_rx3_textures(self, source_rx3: Path, cache_key: str, reuse_cached: bool = True) -> list[Path]:
        """Renders EVERY texture embedded in `source_rx3` to PNGs (the Match
        Assets preview: a wipe pack carries about eight per file) through the
        32-bit kit_preview_worker.py bridge, role="rx3_all_textures". Returns
        the PNG paths in the file's own texture order. `cache_key` (a relative
        path such as "wipe/MyPack/specificwipe_0_996_0") names the cache folder
        under runtime/match_asset_previews/. Blocking and seconds-long on a
        miss -- call from a background thread.

        The cache is trusted only while a manifest next to the PNGs records this
        exact source mtime (equal, not merely older, so swapping in an older
        file is noticed too -- same rule as StadiumRuntime.
        render_goalpost_texture_preview) and the same size, and every PNG is
        still on disk. Raises when the bridge fails."""
        source_rx3 = Path(source_rx3)
        out_dir = self.match_asset_preview_dir() / cache_key
        max_size = self.RX3_PREVIEW_MAX_SIZE
        with self._rx3_render_lock(str(out_dir)):
            try:
                source_mtime_ns = source_rx3.stat().st_mtime_ns
            except OSError:
                source_mtime_ns = None
            if reuse_cached and source_mtime_ns is not None:
                cached = self._cached_rx3_textures(out_dir, source_mtime_ns, max_size)
                if cached:
                    return cached
            # Textures of an earlier, longer version of the file must not linger.
            for stale in out_dir.glob("*.png") if out_dir.is_dir() else ():
                try:
                    stale.unlink()
                except OSError:
                    pass
            result = run_fifalibrary_worker(
                {"source": str(source_rx3), "role": "rx3_all_textures", "output_dir": str(out_dir), "max_size": max_size},
                worker_name="kit_preview_worker.py",
            )
            rendered = [Path(path) for path in result["outputs"]]
            if source_mtime_ns is not None:
                manifest = {"mtime_ns": source_mtime_ns, "max_size": max_size, "textures": [path.name for path in rendered]}
                try:
                    (out_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
                except OSError:
                    pass  # only costs a re-render next time
            return rendered

    def render_match_asset_textures(self, kind: str, pack_dir: Path, source_rx3: Path) -> list[Path]:
        """render_rx3_textures for one .rx3 of a Match Asset pack. `kind` is the
        settings section ("ball", "referee", "wipe", "adboard"); the cache folder
        is <kind>/<pack>/<.rx3 path inside the pack, without extension>, so
        packs and files never share one."""
        relative = Path(source_rx3).relative_to(pack_dir).with_suffix("").as_posix()
        return self.render_rx3_textures(source_rx3, f"{kind}/{Path(pack_dir).name}/{relative}")

    def _rx3_render_lock(self, key: str) -> threading.Lock:
        with self._rx3_render_locks_guard:
            return self._rx3_render_locks.setdefault(key, threading.Lock())

    @staticmethod
    def _cached_rx3_textures(out_dir: Path, source_mtime_ns: int, max_size: int) -> list[Path]:
        """The PNGs of a still-valid cache, or [] (see render_rx3_textures)."""
        try:
            manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
            if manifest["mtime_ns"] != source_mtime_ns or manifest["max_size"] != max_size:
                return []
            paths = [out_dir / name for name in manifest["textures"]]
        except (OSError, ValueError, KeyError, TypeError):
            return []
        return paths if paths and all(path.is_file() for path in paths) else []

    def _show_asset_toast(self, title: str, body: str, duration_ms: int = 3500, icon: str = "") -> None:
        app = self.app
        if app.stadium_picker_awaiting_selection():
            return
        slot = app._show_toast_notification(title, body, icon=icon)
        if slot != -1:
            app.after(duration_ms, lambda s=slot: app._hide_toast_notification(s))

    def _show_warning_toast(self, title: str, body: str, duration_ms: int = 5000, icon: str = "") -> None:
        app = self.app
        if app.stadium_picker_awaiting_selection():
            return
        slot = app._show_toast_notification(title, body, style=1, icon=icon)
        if slot != -1:
            app.after(duration_ms, lambda s=slot: app._hide_toast_notification(s))

    def _resolve_assignment_value(self, candidates: list[tuple[str, str]], fallback: tuple[str, str] | None = None) -> str:
        app = self.app
        for key, section in candidates:
            if key and app.settings_ini.key_exists(key, section):
                return app.settings_ini.read(key, section)
        if fallback is not None:
            key, section = fallback
            if key and app.settings_ini.key_exists(key, section):
                return app.settings_ini.read(key, section)
        return ""

    def _resolve_assignment_type_label(self, candidates: list[tuple[str, str, str]], fallback: tuple[str, str, str] | None = None) -> str:
        """Returns the display label of the first matching assignment candidate."""
        app = self.app
        for key, section, label in candidates:
            if key and app.settings_ini.key_exists(key, section):
                return label
        if fallback is not None:
            key, section, label = fallback
            if key and app.settings_ini.key_exists(key, section):
                return label
        return ""

    def update_audio_overview(self) -> None:
        app = self.app
        chants_enabled = app.module_enabled("Chants") if hasattr(app, "module_states") else False
        app._set_display("audio_module", app.display_value("enabled") if chants_enabled else app.display_value("disabled"))
        current_audio = app.labels.get("audio_current").cget("text") if app.labels.get("audio_current") else "-"
        current_mode = app.labels.get("audio_crowd_mode").cget("text") if app.labels.get("audio_crowd_mode") else "-"
        current_status = app.labels.get("audio_status").cget("text") if app.labels.get("audio_status") else "-"
        current_source = app.labels.get("audio_source").cget("text") if app.labels.get("audio_source") else "-"
        current_next = app.labels.get("audio_next").cget("text") if app.labels.get("audio_next") else "-"
        current_clubsong = app.labels.get("audio_clubsong").cget("text") if app.labels.get("audio_clubsong") else "-"
        if not chants_enabled:
            app._set_display("audio_status", app.display_value("idle"))
            if current_audio in {"", "-", app.display_value("no_active_track"), app.display_value("no_active_chant")}:
                app._set_display("audio_current", app.display_value("no_active_chant"))
            app._set_display("audio_clubsong", app.HID or "-")
            app._set_display("audio_crowd_mode", app.display_value("idle"))
            app._set_display("audio_crowd_volume", "-")
            app._set_display("audio_source", "-")
            app._set_display("audio_next", "-")
        else:
            if current_status in {"", "-", app.display_value("idle")}:
                app._set_display("audio_status", app.display_value("live_match_monitor"))
            if current_audio in {"", "-"}:
                app._set_display("audio_current", app.display_value("no_active_chant"))
            if current_clubsong in {"", "-"}:
                app._set_display("audio_clubsong", app.HID or "-")
            if current_mode in {"", "-"}:
                app._set_display("audio_crowd_mode", app.display_value("monitoring"))
            if current_source in {"", "-"}:
                app._set_display("audio_source", app.display_value("home_crowd"))
            if current_next in {"", "-"}:
                app._set_display("audio_next", app.display_value("wait_for_action"))
            if app.labels.get("audio_crowd_volume") and app.labels["audio_crowd_volume"].cget("text") in {"", "-"}:
                app._set_display("audio_crowd_volume", app.display_value("managed_by_chants"))
        if current_audio in {"", "-", app.display_value("no_active_track")}:
            app._set_display("audio_current", app.display_value("no_active_chant"))
        app._set_display("audio_chants_dir", str(app.exedir / "FSW" / "Chants") if hasattr(app, "exedir") else "-")
        status_label = app.labels.get("status")
        last_action = app.labels.get("audio_last_action").cget("text") if app.labels.get("audio_last_action") else "-"
        if last_action in {"", "-"}:
            app._set_display("audio_last_action", status_label.cget("text") if status_label is not None else "-")

    def apply_scoreboard_runtime(self) -> None:
        app = self.app
        app._set_display("tvlogo", "default")
        app._set_display("scoreboard", "default")
        app.tvlogoscoreboardtype = "default"
        app._tvlogo_assignment_type = ""
        app._scoreboard_assignment_type = ""
        if app.module_enabled("TvLogo"):
            default_source = app.exedir / "FSW" / "TVLogo"
            source = default_source
            tvlogo = self._resolve_assignment_value(
                [
                    (app.TOURROUNDID, "TVLogo"),
                    (app.TOURNAME, "TVLogo"),
                    (app.derby, "DerbyTvLogo"),
                    (app.HID, "HomeTeamTvLogo"),
                ],
                fallback=("0", "TVLogo"),
            )
            app._tvlogo_assignment_type = self._resolve_assignment_type_label(
                [
                    (app.TOURROUNDID, "TVLogo", "Round"),
                    (app.TOURNAME, "TVLogo", "Tournament"),
                    (app.derby, "DerbyTvLogo", "Derby"),
                    (app.HID, "HomeTeamTvLogo", "Home Team"),
                ],
                fallback=("0", "TVLogo", "Default"),
            )
            if tvlogo:
                source = app.TVLogo / tvlogo
            if not Path(source).exists():
                app.log(f"TV logo source not found, falling back to default: {source}")
                source = default_source
            app.tvlogoscoreboardtype = copy_tvlogo(source, app.TVdata)
            app._set_display("tvlogo", Path(source).name)
            app.log(f"Applied TV logo source: {source}")
            if source != default_source:
                self._show_asset_toast(app.tr("notify.tvlogo_loaded"), Path(source).name, icon="tv")
        else:
            app._set_display("tvlogo", app.display_value("tvlogo_module_disable"))
            tvlogo_check = self._resolve_assignment_value(
                [
                    (app.TOURROUNDID, "TVLogo"),
                    (app.TOURNAME, "TVLogo"),
                    (app.derby, "DerbyTvLogo"),
                    (app.HID, "HomeTeamTvLogo"),
                ],
                fallback=("0", "TVLogo"),
            )
            if tvlogo_check and (app.TVLogo / tvlogo_check).exists():
                self._show_warning_toast(app.tr("notify.warn.tvlogo_off"), app.tr("notify.warn.assets_skipped"), icon="tv")
        if app.module_enabled("ScoreBoard"):
            copy(app.exedir / "FSW" / "ScoreBoard", app.Scoredata / "game")
            scoreboard = self._resolve_assignment_value(
                [
                    (app.TOURROUNDID, "Scoreboard"),
                    (app.TOURNAME, "Scoreboard"),
                    (app.derby, "DerbyScoreBoard"),
                    (app.HID, "HomeTeamScoreBoard"),
                ],
                fallback=("0", "Scoreboard"),
            )
            app._scoreboard_assignment_type = self._resolve_assignment_type_label(
                [
                    (app.TOURROUNDID, "Scoreboard", "Round"),
                    (app.TOURNAME, "Scoreboard", "Tournament"),
                    (app.derby, "DerbyScoreBoard", "Derby"),
                    (app.HID, "HomeTeamScoreBoard", "Home Team"),
                ],
                fallback=("0", "Scoreboard", "Default"),
            )
            if scoreboard:
                from .file_tools import is_archive, extract_archive
                import tempfile, shutil

                scoreboard_path = app.ScoreBoard / scoreboard
                scoreboard_dir = scoreboard_path

                if not scoreboard_path.exists():
                    for ext in (".zip", ".rar"):
                        candidate = app.ScoreBoard / (scoreboard + ext)
                        if candidate.exists():
                            scoreboard_path = candidate
                            break

                if scoreboard_path.exists() and is_archive(scoreboard_path):
                    tmp_dir = Path(tempfile.mkdtemp())
                    try:
                        app.log(f"Extracting scoreboard archive: {scoreboard_path.name}")
                        extract_archive(scoreboard_path, tmp_dir)
                        extracted = list(tmp_dir.iterdir())
                        if len(extracted) == 1 and extracted[0].is_dir():
                            scoreboard_dir = extracted[0]
                        else:
                            scoreboard_dir = tmp_dir
                        variant = scoreboard_dir / app.tvlogoscoreboardtype
                        if app.tvlogoscoreboardtype != "default" and variant.exists():
                            copy(variant, app.Scoredata)
                        else:
                            copy(scoreboard_dir, app.Scoredata)
                    except Exception as exc:
                        app.log(f"Failed to apply scoreboard archive '{scoreboard_path.name}': {exc}")
                        scoreboard = ""
                    finally:
                        shutil.rmtree(tmp_dir, ignore_errors=True)
                elif scoreboard_dir.exists() and scoreboard_dir.is_dir():
                    variant = scoreboard_dir / app.tvlogoscoreboardtype
                    if app.tvlogoscoreboardtype != "default" and variant.exists():
                        copy(variant, app.Scoredata)
                    else:
                        copy(scoreboard_dir, app.Scoredata)
                else:
                    app.log(f"Scoreboard not found, keeping default: {scoreboard_path}")
                    scoreboard = ""
                if scoreboard:
                    app._set_display("scoreboard", scoreboard)
                    app.log(f"Applied scoreboard: {scoreboard}")
                    self._show_asset_toast(app.tr("notify.scoreboard_loaded"), scoreboard, icon="scoreboard")
            else:
                app.log("No scoreboard assignment found; default scoreboard active")
        else:
            app._set_display("scoreboard", app.display_value("scoreboard_module_disable"))
            scoreboard_check = self._resolve_assignment_value(
                [
                    (app.TOURROUNDID, "Scoreboard"),
                    (app.TOURNAME, "Scoreboard"),
                    (app.derby, "DerbyScoreBoard"),
                    (app.HID, "HomeTeamScoreBoard"),
                ],
                fallback=("0", "Scoreboard"),
            )
            if scoreboard_check:
                from .file_tools import is_archive
                sb_path = app.ScoreBoard / scoreboard_check
                sb_exists = sb_path.exists() and sb_path.is_dir()
                if not sb_exists:
                    for ext in (".zip", ".rar"):
                        if (app.ScoreBoard / (scoreboard_check + ext)).exists():
                            sb_exists = True
                            break
                if sb_exists:
                    self._show_warning_toast(app.tr("notify.warn.scoreboard_off"), app.tr("notify.warn.assets_skipped"), icon="scoreboard")
        self.update_audio_overview()

    def apply_movie_runtime(self) -> None:
        app = self.app
        app._set_display("movie", "default")
        app._movie_assignment_type = ""
        if not app.module_enabled("Movies"):
            app._set_display("movie", app.display_value("movie_module_disable"))
            movie_check = self._resolve_assignment_value(
                [
                    (app.TOURROUNDID, "movies"),
                    (app.TOURNAME, "movies"),
                    (app.derby, "DerbyMatch"),
                    (app.HID, "TeamMovies"),
                ],
                fallback=("0", "movies"),
            )
            if movie_check and (app.Movies / movie_check).exists():
                self._show_warning_toast(app.tr("notify.warn.movie_off"), app.tr("notify.warn.assets_skipped"), icon="movie")
            self.update_audio_overview()
            return
        movie = self._resolve_assignment_value(
            [
                (app.TOURROUNDID, "movies"),
                (app.TOURNAME, "movies"),
                (app.derby, "DerbyMatch"),
                (app.HID, "TeamMovies"),
            ],
            fallback=("0", "movies"),
        )
        app._movie_assignment_type = self._resolve_assignment_type_label(
            [
                (app.TOURROUNDID, "movies", "Round"),
                (app.TOURNAME, "movies", "Tournament"),
                (app.derby, "DerbyMatch", "Derby"),
                (app.HID, "TeamMovies", "Home Team"),
            ],
            fallback=("0", "movies", "Default"),
        )
        if movie:
            movie_dir = app.Movies / movie
            if movie_dir.exists():
                copy_if_exists(movie_dir / "bootflowoutro.vp8", app.Movdata)
                copy_if_exists(movie_dir / "bumper.big", app.MOVBUMP)
                app._set_display("movie", movie)
                app._set_display("audio_current", movie)
                app._set_display("audio_last_action", app.display_value("movie_prefix", fallback="Movie {name}", name=movie))
                app.log(f"Applied movie: {movie}")
                self._show_asset_toast(app.tr("notify.movie_loaded"), movie, icon="movie")
            else:
                app.log(f"Movie directory not found, falling back to default movie: {movie_dir}")
                movie = ""
        elif app.stadmovie:
            app._set_display("movie", app.display_value("stadium_movie_title"))
            app._set_display("audio_current", app.display_value("stadium_movie_current", fallback="{name} Stadium Movie", name=app.curstad))
            app._set_display("audio_last_action", app.display_value("stadium_movie"))
            app.log("Applied stadium movie")
        if not movie and not app.stadmovie:
            copy_if_exists(app.exedir / "FSW" / "Nav" / "bootflowoutro.vp8", app.Movdata)
            copy_if_exists(app.exedir / "FSW" / "Nav" / "bumper.big", app.MOVBUMP)
            app._set_display("movie", "default")
            app._set_display("audio_current", app.display_value("default_navigation_audio"))
            app._set_display("audio_last_action", app.display_value("default_movie_restored"))
            app.log("Default movie restored")
        self.update_audio_overview()

    def _restore_tracked_originals(self, label: str, target_dir: Path, backup_name: str, reason: str) -> None:
        """Puts back the game's own files that an earlier <label> pack
        overwrote (and deletes the ones the pack added), from the backup
        install_tracked_files took in FSW/<backup_name>. No-op when nothing is
        tracked."""
        app = self.app
        restored, failed = restore_tracked_files(target_dir, app.exedir / "FSW" / backup_name)
        if restored:
            app.log(f"{label} runtime: {restored} original file(s) restored ({reason})")
        if failed:
            app.log(f"{label} runtime: could not restore {', '.join(failed)} ({reason})")

    def _pack_id_rename(self, kind: str, label: str, names: list[str]) -> dict[str, str]:
        """{pack file name: installed name} for a pack whose single id differs from
        the one the game will ask for in this match, {} when nothing needs to change.

        The packs are assigned to a ROUND but addressed by an id inside their file
        names; the id the Lua asks for is the match's league graphics id (read live,
        Offsets.TLEAGUE) after its own swap/clone tables -- see match_asset_ids.
        No league id yet (no competition, or the read failed) leaves the pack as it
        is, exactly as before."""
        app = self.app
        league = str(getattr(app, "LEAGUEID", "") or "").strip()
        if not league.isdigit() or int(league) <= 0:
            return {}
        target = engine_id(kind, int(league), read_lua_id_maps(app.exedir))
        plan = plan_pack_remap(kind, names, target)
        if plan.reason == "remapped":
            sources = "/".join(str(item) for item in plan.source_ids)
            app.log(
                f"{label} runtime: pack id {sources} -> {target} (match league {league}), "
                f"{len(plan.rename)} file(s) renamed on install"
            )
            return plan.rename
        if plan.reason == "multiple-ids":
            sources = ", ".join(str(item) for item in plan.source_ids)
            app.log(f"{label} runtime: pack carries several ids ({sources}); installed as-is (match asks for {target})")
        return {}

    def apply_ball_runtime(self) -> None:
        """Installs FSW/balls/<folder>/ for the current round to
        data/sceneassets/ball/, ported from Nono's fork (see CLAUDE.md).
        Ini-only: assign by hand under settings.ini's [ball] section,
        key=TOURROUNDID value=<folder> (same section/key shape Nono's server
        reads).

        Tracked like Wipe: the game's own ball files a pack overwrites are
        backed up (FSW/.ball_backup) and put back as soon as a later apply no
        longer wants them -- module off, a round with no ball assigned, a
        missing pack folder, or a different pack. Without it the last custom
        ball stayed in its slot for good.

        Applied before Stadium/Scoreboard in apply_all_runtime (Nono found the
        ball arriving 7-11s late when it went after the scoreboard copy), and
        remembered per kickoff generation so tv_bumper_page() can reapply it
        if anything overwrites data/sceneassets/ball/ later in the same match.
        """
        app = self.app
        app._active_ball_runtime = None
        key = app.TOURROUNDID
        ball_folder = app.settings_ini.read(key, "ball") if key else ""
        target_dir = app.exedir / "data" / "sceneassets" / "ball"
        if not app.module_enabled("Ball"):
            self._restore_tracked_originals("Ball", target_dir, ".ball_backup", "module off")
            if ball_folder and (app.exedir / "FSW" / "balls" / ball_folder).exists():
                self._show_warning_toast(app.tr("notify.warn.ball_off"), app.tr("notify.warn.assets_skipped"), icon="ball")
            return
        if not key or not ball_folder:
            # No round at all is a friendly (Kick-Off never has one), not a
            # round still to be read: the last competition's ball must not
            # carry over into it.
            self._restore_tracked_originals(
                "Ball", target_dir, ".ball_backup",
                "no ball assigned to this round" if key else "no competition round in this match",
            )
            return
        src_dir = app.exedir / "FSW" / "balls" / ball_folder
        if not src_dir.exists():
            app.log(f"Ball folder not found: {src_dir}")
            self._restore_tracked_originals("Ball", target_dir, ".ball_backup", "assigned ball folder not found")
            return
        rename = self._pack_id_rename("ball", "Ball", list_pack_files(src_dir))
        # Remembered before the copy so tv_bumper_page() retries a partial failure
        # (with the same renaming: the league id was read once, for this match).
        app._active_ball_runtime = {
            "generation": app._kickoff_generation,
            "key": key,
            "folder": ball_folder,
            "src_dir": str(src_dir),
            "rename": rename,
        }
        install_tracked_files(src_dir, target_dir, app.exedir / "FSW" / ".ball_backup", rename=rename)
        app.log(f"Ball runtime: [{key}] {ball_folder} applied")
        self._show_asset_toast(app.tr("notify.ball_loaded"), ball_folder, icon="ball")

    def reapply_active_ball_runtime(self, *, reason: str) -> bool:
        """Re-installs the currently active Ball profile, if any, as long as no
        newer match (kickoff generation) has started since it was applied."""
        app = self.app
        profile = app._active_ball_runtime
        if not profile or profile.get("generation") != app._kickoff_generation:
            return False
        src_dir = Path(str(profile["src_dir"]))
        if not src_dir.exists():
            return False
        target_dir = app.exedir / "data" / "sceneassets" / "ball"
        install_tracked_files(
            src_dir, target_dir, app.exedir / "FSW" / ".ball_backup", rename=profile.get("rename") or None
        )
        app.log(f"Ball priority preserved ({reason}): [{profile['key']}] {profile['folder']}")
        return True

    def apply_referee_runtime(self) -> None:
        """Installs FSW/referee/<folder>/ for the current round to
        data/sceneassets/kit/ (same destination team kits use), ported from
        Nono's fork. Ini-only: settings.ini [referee], key=TOURROUNDID.
        No stadium dependency, so -- like Ball -- this runs early in
        apply_all_runtime, before Stadium/Scoreboard.

        Tracked like Wipe (backup in FSW/.referee_backup): only the files the
        referee pack itself installed are ever restored or deleted, so team
        kits sharing data/sceneassets/kit are left alone."""
        app = self.app
        key = app.TOURROUNDID
        referee_folder = app.settings_ini.read(key, "referee") if key else ""
        target_dir = app.exedir / "data" / "sceneassets" / "kit"
        if not app.module_enabled("Referee"):
            self._restore_tracked_originals("Referee", target_dir, ".referee_backup", "module off")
            if referee_folder and (app.exedir / "FSW" / "referee" / referee_folder).exists():
                self._show_warning_toast(app.tr("notify.warn.referee_off"), app.tr("notify.warn.assets_skipped"), icon="referee")
            return
        if not key or not referee_folder:
            # Same as Ball: a match with no round is a friendly.
            self._restore_tracked_originals(
                "Referee", target_dir, ".referee_backup",
                "no referee assigned to this round" if key else "no competition round in this match",
            )
            return
        src_dir = app.exedir / "FSW" / "referee" / referee_folder
        if not src_dir.exists():
            app.log(f"Referee folder not found: {src_dir}")
            self._restore_tracked_originals("Referee", target_dir, ".referee_backup", "assigned referee folder not found")
            return
        rename = self._pack_id_rename("referee", "Referee", list_pack_files(src_dir))
        install_tracked_files(src_dir, target_dir, app.exedir / "FSW" / ".referee_backup", rename=rename)
        app.log(f"Referee runtime: [{key}] {referee_folder} applied")
        self._show_asset_toast(app.tr("notify.referee_loaded"), referee_folder, icon="referee")

    def _restore_wipe_originals(self, reason: str) -> None:
        self._restore_tracked_originals("Wipe", self.app.exedir / "data" / "sceneassets" / "wipe3d", ".wipe_backup", reason)

    def apply_wipe_runtime(self) -> None:
        """Copies FSW/wipe/<folder>/ for the current round to
        data/sceneassets/wipe3d/ (the 3D scene-transition wipe), ported from
        Nono's fork. Ini-only: settings.ini [wipe], key=TOURROUNDID.

        Unlike Nono's fork, the game's own wipe files a pack overwrites are
        backed up (FSW/.wipe_backup) and put back as soon as a later apply no
        longer wants them -- module off, a round with no wipe assigned, a
        missing pack folder, or a different pack. Without it the last custom
        wipe stayed in its slot for good. Copies are temp-file + os.replace,
        as in Nono's fork, so FIFA never reads a half-written .rx3."""
        app = self.app
        key = app.TOURROUNDID
        wipe_folder = app.settings_ini.read(key, "wipe") if key else ""
        if not app.module_enabled("Wipe"):
            self._restore_wipe_originals("module off")
            if wipe_folder and (app.exedir / "FSW" / "wipe" / wipe_folder).exists():
                self._show_warning_toast(app.tr("notify.warn.wipe_off"), app.tr("notify.warn.assets_skipped"), icon="wipe")
            return
        if not key:
            return
        if not wipe_folder:
            self._restore_wipe_originals("no wipe assigned to this round")
            return
        src_dir = app.exedir / "FSW" / "wipe" / wipe_folder
        if not src_dir.exists():
            app.log(f"Wipe folder not found: {src_dir}")
            self._restore_wipe_originals("assigned wipe folder not found")
            return
        target_dir = app.exedir / "data" / "sceneassets" / "wipe3d"
        rename = self._pack_id_rename("wipe", "Wipe", list_pack_files(src_dir))
        install_tracked_files(src_dir, target_dir, app.exedir / "FSW" / ".wipe_backup", rename=rename)
        app.log(f"Wipe runtime: [{key}] {wipe_folder} applied")
        self._show_asset_toast(app.tr("notify.wipe_loaded"), wipe_folder, icon="wipe")

    # (destination folder under data/sceneassets, backup folder under FSW) for the two
    # places an Adboard pack installs into: the boards themselves and the corner flags.
    _ADBOARD_TARGETS = (("adboard", ".adboard_backup"), ("flag", ".cornerflag_backup"))

    def _clear_active_adboard_files(self) -> None:
        """Takes back whatever the previous adboard application installed: the
        files it added are deleted and the game's own files it overwrote are put
        back from FSW/.adboard_backup / .cornerflag_backup.

        Ported from Nono's restore_adboard_runtime(), but simplified: instead
        of tracking real match-end via a FluxHub/post-match page heuristic
        (Nono's own version of the same page-name-ambiguity problem this
        codebase already fought through for Team Entrance -- see CLAUDE.md
        §7), stale files are cleared unconditionally right before the next
        application. This is simpler and strictly safer: a round with no
        adboard match can never keep showing a stale, unrelated pack.

        Tracked on disk like Ball/Referee/Wipe (it used to delete by an in-memory
        name list): a pack whose ids are renamed to the match's league id can land
        on a file the game ships, which must come back instead of being deleted.
        """
        app = self.app
        for folder, backup in self._ADBOARD_TARGETS:
            _restored, failed = restore_tracked_files(
                app.exedir / "data" / "sceneassets" / folder, app.exedir / "FSW" / backup
            )
            if failed:
                app.log(f"Adboard: could not restore {', '.join(failed)}")
        app._active_adboard_injected_files = []

    def cleanup_startup_adboard_files(self) -> None:
        """Ported from Nono's _cleanup_injected_adboards(). Defensive cleanup
        of six fixed per-slot filenames his fork's older Adboard scheme used
        to write directly (predating the whole-folder-copy approach this port
        and his current fork both use) -- harmless no-op unless an install
        upgrading from that older scheme still has them lying around."""
        app = self.app
        target_dir = app.exedir / "data" / "sceneassets" / "adboard"
        cleanup_names = [
            "specificadboard_0_993_0_0.rx3",
            "specificadboard_0_992_0_0.rx3",
            "specificadboard_0_996_0_0.rx3",
            "specificadboard_0_991_0_0.rx3",
            "specificadboard_0_995_0_0.rx3",
            "specificadboard_0_994_0_0.rx3",
        ]
        removed = 0
        for name in cleanup_names:
            path = target_dir / name
            if path.exists():
                try:
                    path.unlink()
                    removed += 1
                except OSError as exc:
                    app.log(f"Adboard startup cleanup: could not remove {name}: {exc}")
        if removed:
            app.log(f"Startup cleanup: {removed} adboard files removed")

    def apply_adboard_runtime(self) -> None:
        """Installs the round's FSW/adboards/<folder>/ (settings.ini [adboard],
        key=TOURROUNDID), ported from Nono's fork. Competition-only, like Ball/
        Referee/Wipe: Nono's per-stadium FSW/adboards/<stadium>/ override was
        dropped -- it was never renamed to the match's league id (so it only showed
        in the one competition whose id its files carried) and had no assignment UI.
        """
        app = self.app
        if not app.module_enabled("Adboard"):
            self._clear_active_adboard_files()
            adboard_folder = app.settings_ini.read(app.TOURROUNDID, "adboard") if app.TOURROUNDID else ""
            if adboard_folder and (app.exedir / "FSW" / "adboards" / adboard_folder).exists():
                self._show_warning_toast(app.tr("notify.warn.adboard_off"), app.tr("notify.warn.assets_skipped"), icon="adboard")
            return
        self._apply_adboard_runtime_impl()

    @staticmethod
    def _adboard_selection(source_dir: Path, rename: dict[str, str]) -> tuple[dict[str, Path], dict[str, Path]]:
        """({installed name: source} for the boards, same for the corner flags) of one
        Adboard folder. Every .rx3 is a board; any file with "cornerflag" in its name
        is additionally a corner flag (they install into data/sceneassets/flag)."""
        boards: dict[str, Path] = {}
        flags: dict[str, Path] = {}
        for src in sorted(source_dir.iterdir()):
            if not src.is_file():
                continue
            installed = rename.get(src.name, src.name)
            if src.suffix.lower() == ".rx3":
                boards[installed] = src
            if "cornerflag" in src.name.lower():
                flags[installed] = src
        return boards, flags

    def _apply_adboard_runtime_impl(self) -> None:
        app = self.app
        board_selection: dict[str, Path] = {}
        flag_selection: dict[str, Path] = {}
        source_label = ""

        if app.TOURROUNDID:
            adboard_folder = app.settings_ini.read(app.TOURROUNDID, "adboard")
            if adboard_folder:
                adboards_dir = app.exedir / "FSW" / "adboards" / adboard_folder
                if adboards_dir.exists():
                    names = [item.name for item in adboards_dir.iterdir() if item.is_file()]
                    rename = {
                        **self._pack_id_rename("adboard", "Adboard", names),
                        **self._pack_id_rename("cornerflag", "Cornerflag", names),
                    }
                    board_selection, flag_selection = self._adboard_selection(adboards_dir, rename)
                    if board_selection:
                        source_label = adboard_folder
                        app.log(f"Adboard runtime: [{app.TOURROUNDID}] {adboard_folder} -> {len(board_selection)} files")
                        if flag_selection:
                            app.log(f"Cornerflag runtime: [{app.TOURROUNDID}] {adboard_folder} -> {len(flag_selection)} files copied")
                    else:
                        flag_selection = {}
                        app.log(f"Adboard: round folder [{adboard_folder}] has no .rx3 files")
                else:
                    app.log(f"Adboard folder not found: {adboards_dir}")

        # Installing the (possibly empty) selection also takes back whatever the previous
        # application put there, so a round with no adboard never keeps a stale pack.
        for (folder, backup), selection in zip(self._ADBOARD_TARGETS, (board_selection, flag_selection)):
            try:
                install_tracked_selection(
                    selection, app.exedir / "data" / "sceneassets" / folder, app.exedir / "FSW" / backup
                )
            except OSError as exc:
                app.log(f"Adboard: could not install into {folder}: {exc}")
        copied_files = list(board_selection)
        app._active_adboard_injected_files = copied_files
        if copied_files:
            # Skipped while the manual stadium picker awaits a choice (inside _show_asset_toast).
            self._show_asset_toast(app.tr("notify.adboard_loaded"), source_label, icon="adboard")

    def tv_bumper_page(self) -> None:
        app = self.app
        self.reapply_active_ball_runtime(reason="TV bumper")
        source_key = "stadiumnetid" if not app.curstad else "stadiumnetname"
        source_section = app.STADID if not app.curstad else app.StadName
        has_net_values = not app.settings_ini.key_exists(app.TOURROUNDID, "exclude") and app.settings_ini.key_exists(source_section, source_key)
        if not app.module_enabled("StadiumNet"):
            if has_net_values:
                self._show_warning_toast(app.tr("notify.warn.stadiumnet_off"), app.tr("notify.warn.assets_skipped"))
            return
        if not has_net_values:
            return
        values = app.settings_ini.read(source_section, source_key).split(",")
        for offset_group, value in zip([app.offsets.NTDP, app.offsets.NTCP, app.offsets.NTRI, app.offsets.NTTR, app.offsets.NTTT], values):
            app.memory.write_int(app.offsets.ORINETDEPTHBASE, offset_group, value)
        app._set_display("audio_last_action", app.display_value("net_profile_prefix", fallback="Net profile {name}", name=source_section))
        app.log(f"Applied stadium net values from [{source_key}] {source_section}: {values}")
