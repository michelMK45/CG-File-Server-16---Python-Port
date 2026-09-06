from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

from .file_tools import copy, copy_if_exists, copy_tvlogo

if TYPE_CHECKING:
    from .app import Server16App


class AssetRuntime:
    def __init__(self, app: "Server16App") -> None:
        self.app = app

    def _show_asset_toast(self, title: str, body: str, duration_ms: int = 3500, icon: str = "") -> None:
        app = self.app
        slot = app._show_toast_notification(title, body, icon=icon)
        if slot != -1:
            app.after(duration_ms, lambda s=slot: app._hide_toast_notification(s))

    def _show_warning_toast(self, title: str, body: str, duration_ms: int = 5000, icon: str = "") -> None:
        app = self.app
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
                    (app.HID, "HomeTeamTvLogo"),
                ],
                fallback=("0", "TVLogo"),
            )
            app._tvlogo_assignment_type = self._resolve_assignment_type_label(
                [
                    (app.TOURROUNDID, "TVLogo", "Round"),
                    (app.TOURNAME, "TVLogo", "Tournament"),
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
                    (app.HID, "HomeTeamScoreBoard"),
                ],
                fallback=("0", "Scoreboard"),
            )
            app._scoreboard_assignment_type = self._resolve_assignment_type_label(
                [
                    (app.TOURROUNDID, "Scoreboard", "Round"),
                    (app.TOURNAME, "Scoreboard", "Tournament"),
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

    def apply_ball_runtime(self) -> None:
        """Copies FSW/balls/<folder>/*.rx3 for the current round, ported from
        Nono's fork (see CLAUDE.md). Ini-only: assign by hand under
        settings.ini's [ball] section, key=TOURROUNDID value=<folder> (same
        section/key shape Nono's server reads).

        Applied before Stadium/Scoreboard in apply_all_runtime (Nono found the
        ball arriving 7-11s late when it went after the scoreboard copy), and
        remembered per kickoff generation so tv_bumper_page() can reapply it
        if anything overwrites data/sceneassets/ball/ later in the same match.
        """
        app = self.app
        app._active_ball_runtime = None
        key = app.TOURROUNDID
        ball_folder = app.settings_ini.read(key, "ball") if key else ""
        if not app.module_enabled("Ball"):
            if ball_folder and (app.exedir / "FSW" / "balls" / ball_folder).exists():
                self._show_warning_toast(app.tr("notify.warn.ball_off"), app.tr("notify.warn.assets_skipped"))
            return
        if not key or not ball_folder:
            return
        src_dir = app.exedir / "FSW" / "balls" / ball_folder
        if not src_dir.exists():
            app.log(f"Ball folder not found: {src_dir}")
            return
        target_dir = app.exedir / "data" / "sceneassets" / "ball"
        copy(src_dir, target_dir)
        app._active_ball_runtime = {
            "generation": app._kickoff_generation,
            "key": key,
            "folder": ball_folder,
            "src_dir": str(src_dir),
        }
        app.log(f"Ball runtime: [{key}] {ball_folder} applied")
        self._show_asset_toast(app.tr("notify.ball_loaded"), ball_folder)

    def reapply_active_ball_runtime(self, *, reason: str) -> bool:
        """Re-copies the currently active Ball profile, if any, as long as no
        newer match (kickoff generation) has started since it was applied."""
        app = self.app
        profile = app._active_ball_runtime
        if not profile or profile.get("generation") != app._kickoff_generation:
            return False
        src_dir = Path(str(profile["src_dir"]))
        if not src_dir.exists():
            return False
        target_dir = app.exedir / "data" / "sceneassets" / "ball"
        copy(src_dir, target_dir)
        app.log(f"Ball priority preserved ({reason}): [{profile['key']}] {profile['folder']}")
        return True

    def apply_referee_runtime(self) -> None:
        """Copies FSW/referee/<folder>/*.rx3 for the current round to
        data/sceneassets/kit/ (same destination team kits use), ported from
        Nono's fork. Ini-only: settings.ini [referee], key=TOURROUNDID.
        No stadium dependency, so — like Ball — this runs early in
        apply_all_runtime, before Stadium/Scoreboard."""
        app = self.app
        key = app.TOURROUNDID
        referee_folder = app.settings_ini.read(key, "referee") if key else ""
        if not app.module_enabled("Referee"):
            if referee_folder and (app.exedir / "FSW" / "referee" / referee_folder).exists():
                self._show_warning_toast(app.tr("notify.warn.referee_off"), app.tr("notify.warn.assets_skipped"))
            return
        if not key or not referee_folder:
            return
        src_dir = app.exedir / "FSW" / "referee" / referee_folder
        if not src_dir.exists():
            app.log(f"Referee folder not found: {src_dir}")
            return
        target_dir = app.exedir / "data" / "sceneassets" / "kit"
        copy(src_dir, target_dir)
        app.log(f"Referee runtime: [{key}] {referee_folder} applied")
        self._show_asset_toast(app.tr("notify.referee_loaded"), referee_folder)

    def apply_wipe_runtime(self) -> None:
        """Copies FSW/wipe/<folder>/*.rx3 for the current round to
        data/sceneassets/wipe3d/ (the 3D scene-transition wipe), ported from
        Nono's fork. Ini-only: settings.ini [wipe], key=TOURROUNDID."""
        app = self.app
        key = app.TOURROUNDID
        wipe_folder = app.settings_ini.read(key, "wipe") if key else ""
        if not app.module_enabled("Wipe"):
            if wipe_folder and (app.exedir / "FSW" / "wipe" / wipe_folder).exists():
                self._show_warning_toast(app.tr("notify.warn.wipe_off"), app.tr("notify.warn.assets_skipped"))
            return
        if not key or not wipe_folder:
            return
        src_dir = app.exedir / "FSW" / "wipe" / wipe_folder
        if not src_dir.exists():
            app.log(f"Wipe folder not found: {src_dir}")
            return
        target_dir = app.exedir / "data" / "sceneassets" / "wipe3d"
        copy(src_dir, target_dir)
        app.log(f"Wipe runtime: [{key}] {wipe_folder} applied")
        self._show_asset_toast(app.tr("notify.wipe_loaded"), wipe_folder)

    def _clear_active_adboard_files(self) -> None:
        """Deletes whatever the previous adboard application injected.

        Ported from Nono's restore_adboard_runtime(), but simplified: instead
        of tracking real match-end via a FluxHub/post-match page heuristic
        (Nono's own version of the same page-name-ambiguity problem this
        codebase already fought through for Team Entrance -- see CLAUDE.md
        §7), stale files are cleared unconditionally right before the next
        application. This is simpler and strictly safer: a round with no
        adboard match can never keep showing a stale, unrelated pack.
        """
        app = self.app
        target_dir = app.exedir / "data" / "sceneassets" / "adboard"
        for name in getattr(app, "_active_adboard_injected_files", []):
            path = target_dir / name
            if path.exists():
                try:
                    path.unlink()
                except OSError as exc:
                    app.log(f"Adboard: could not remove stale file {name}: {exc}")
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
        """Entry point ported from Nono's fork. Priority: current stadium's
        own FSW/adboards/<stadium>/ folder, falling back to the round's
        FSW/adboards/<folder>/ (settings.ini [adboard], key=TOURROUNDID) only
        if the stadium folder is missing/empty. Ini-only, no assignment UI.

        If Stadium is enabled and its background copy job is still running,
        app.curstad isn't final yet -- wait for it on a background thread
        (without blocking the UI) before picking a priority, same as Nono's
        fork does for the same reason.
        """
        app = self.app
        if not app.module_enabled("Adboard"):
            self._clear_active_adboard_files()
            adboard_folder = app.settings_ini.read(app.TOURROUNDID, "adboard") if app.TOURROUNDID else ""
            has_assignment = bool(
                (app.curstad and (app.exedir / "FSW" / "adboards" / app.curstad).exists())
                or (adboard_folder and (app.exedir / "FSW" / "adboards" / adboard_folder).exists())
            )
            if has_assignment:
                self._show_warning_toast(app.tr("notify.warn.adboard_off"), app.tr("notify.warn.assets_skipped"))
            return
        if app.module_enabled("Stadium") and app._stadium_task_running:
            def _wait_and_apply() -> None:
                waited = 0.0
                while app._stadium_task_running and waited < 20.0:
                    time.sleep(0.25)
                    waited += 0.25
                if app._stadium_task_running:
                    app.log("Adboard: timeout waiting for stadium task, continuing anyway")
                if app.module_enabled("Adboard"):
                    self._apply_adboard_runtime_impl()

            threading.Thread(target=_wait_and_apply, daemon=True, name="AdboardWaitStadium").start()
        else:
            self._apply_adboard_runtime_impl()

    def _apply_adboard_runtime_impl(self) -> None:
        app = self.app
        self._clear_active_adboard_files()
        target_dir = app.exedir / "data" / "sceneassets" / "adboard"
        flag_target_dir = app.exedir / "data" / "sceneassets" / "flag"

        def _copy_cornerflags(source_dir: Path) -> int:
            copied = 0
            for src in sorted(source_dir.iterdir()):
                if src.is_file() and "cornerflag" in src.name.lower():
                    copy_if_exists(src, flag_target_dir / src.name)
                    copied += 1
            return copied

        copied_files: list[str] = []
        stadium_matched = False
        source_label = ""

        if app.curstad:
            stadium_dir = app.exedir / "FSW" / "adboards" / app.curstad
            if stadium_dir.exists():
                for src in sorted(stadium_dir.iterdir()):
                    if src.suffix.lower() != ".rx3":
                        continue
                    copy_if_exists(src, target_dir / src.name)
                    copied_files.append(src.name)
                if copied_files:
                    stadium_matched = True
                    source_label = app.curstad
                    app.log(f"Adboard runtime: stadium [{app.curstad}] -> {len(copied_files)} files")
                    flags_copied = _copy_cornerflags(stadium_dir)
                    if flags_copied:
                        app.log(f"Cornerflag runtime: stadium [{app.curstad}] -> {flags_copied} files copied")
                else:
                    app.log(f"Adboard: stadium folder [{app.curstad}] has no .rx3 files")
            else:
                app.log(f"Adboard: no stadium folder for [{app.curstad}] (tried: {stadium_dir})")

        if not stadium_matched and app.TOURROUNDID:
            adboard_folder = app.settings_ini.read(app.TOURROUNDID, "adboard")
            if adboard_folder:
                adboards_dir = app.exedir / "FSW" / "adboards" / adboard_folder
                if adboards_dir.exists():
                    for src in sorted(adboards_dir.iterdir()):
                        if src.suffix.lower() != ".rx3":
                            continue
                        copy_if_exists(src, target_dir / src.name)
                        copied_files.append(src.name)
                    if copied_files:
                        source_label = adboard_folder
                        app.log(f"Adboard runtime: [{app.TOURROUNDID}] {adboard_folder} -> {len(copied_files)} files")
                        flags_copied = _copy_cornerflags(adboards_dir)
                        if flags_copied:
                            app.log(f"Cornerflag runtime: [{app.TOURROUNDID}] {adboard_folder} -> {flags_copied} files copied")
                    else:
                        app.log(f"Adboard: round folder [{adboard_folder}] has no .rx3 files")
                else:
                    app.log(f"Adboard folder not found: {adboards_dir}")

        app._active_adboard_injected_files = copied_files
        if copied_files:
            # Routed through the worker queue rather than called directly:
            # this may be running on the AdboardWaitStadium background thread,
            # and Tk calls (app.after, used by _show_asset_toast) aren't safe
            # off the main thread -- same reason stadium_runtime.py's own
            # background copy steps queue their toasts instead of calling
            # _show_toast_notification directly.
            app._worker_queue.put(("toast", app.tr("notify.adboard_loaded"), source_label, 3500, ""))

    def tv_bumper_page(self) -> None:
        app = self.app
        self.reapply_active_ball_runtime(reason="TV bumper")
        if not app.module_enabled("StadiumNet"):
            return
        source_key = "stadiumnetid" if not app.curstad else "stadiumnetname"
        source_section = app.STADID if not app.curstad else app.StadName
        if app.settings_ini.key_exists(app.TOURROUNDID, "exclude") or not app.settings_ini.key_exists(source_section, source_key):
            return
        values = app.settings_ini.read(source_section, source_key).split(",")
        for offset_group, value in zip([app.offsets.NTDP, app.offsets.NTCP, app.offsets.NTRI, app.offsets.NTTR], values):
            app.memory.write_int(app.offsets.ORINETDEPTHBASE, offset_group, value)
        app._set_display("audio_last_action", app.display_value("net_profile_prefix", fallback="Net profile {name}", name=source_section))
        app.log(f"Applied stadium net values from [{source_key}] {source_section}: {values}")
