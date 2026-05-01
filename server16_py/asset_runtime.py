from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from .file_tools import copy, copy_if_exists, copy_tvlogo, extra_setup

if TYPE_CHECKING:
    from .app import Server16App


class AssetRuntime:
    def __init__(self, app: "Server16App") -> None:
        self.app = app

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
            if tvlogo:
                source = app.TVLogo / tvlogo
            if not Path(source).exists():
                app.log(f"TV logo source not found, falling back to default: {source}")
                source = default_source
            app.tvlogoscoreboardtype = copy_tvlogo(source, app.TVdata)
            app._set_display("tvlogo", Path(source).name)
            app.log(f"Applied TV logo source: {source}")
        else:
            app._set_display("tvlogo", app.display_value("tvlogo_module_disable"))
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
            if scoreboard:
                variant = app.ScoreBoard / scoreboard / app.tvlogoscoreboardtype
                scoreboard_dir = app.ScoreBoard / scoreboard
                if app.tvlogoscoreboardtype != "default" and variant.exists():
                    copy(variant, app.Scoredata)
                elif scoreboard_dir.exists():
                    copy(scoreboard_dir, app.Scoredata)
                else:
                    app.log(f"Scoreboard directory not found, keeping default scoreboard: {scoreboard_dir}")
                    scoreboard = ""
                if scoreboard:
                    app._set_display("scoreboard", scoreboard)
                    app.log(f"Applied scoreboard: {scoreboard}")
            else:
                app.log("No scoreboard assignment found; default scoreboard active")
        else:
            app._set_display("scoreboard", app.display_value("scoreboard_module_disable"))
        self.update_audio_overview()

    def apply_movie_runtime(self) -> None:
        app = self.app
        app._set_display("movie", "default")
        if not app.module_enabled("Movies"):
            app._set_display("movie", app.display_value("movie_module_disable"))
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
        if movie:
            movie_dir = app.Movies / movie
            if movie_dir.exists():
                copy_if_exists(movie_dir / "bootflowoutro.vp8", app.Movdata)
                copy_if_exists(movie_dir / "bumper.big", app.MOVBUMP)
                app._set_display("movie", movie)
                app._set_display("audio_current", movie)
                app._set_display("audio_last_action", app.display_value("movie_prefix", fallback="Movie {name}", name=movie))
                app.log(f"Applied movie: {movie}")
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

    def tv_bumper_page(self) -> None:
        app = self.app
        if not app.module_enabled("StadiumNet"):
            return
        extra_setup(app.Nsource, app.Ndest, "0", "netcolor", "0")
        source_key = "stadiumnetid" if not app.curstad else "stadiumnetname"
        source_section = app.STADID if not app.curstad else app.StadName
        if app.settings_ini.key_exists(app.TOURROUNDID, "exclude") or not app.settings_ini.key_exists(source_section, source_key):
            return
        values = app.settings_ini.read(source_section, source_key).split(",")
        for offset_group, value in zip([app.offsets.NTDP, app.offsets.NTCP, app.offsets.NTRI, app.offsets.NTTR], values):
            app.memory.write_int(app.offsets.ORINETDEPTHBASE, offset_group, value)
        app._set_display("audio_last_action", app.display_value("net_profile_prefix", fallback="Net profile {name}", name=source_section))
        app.log(f"Applied stadium net values from [{source_key}] {source_section}: {values}")
