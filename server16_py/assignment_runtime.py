from __future__ import annotations

from tkinter import messagebox
from typing import TYPE_CHECKING

from .dialogs import ExcludeDialog, MovieDialog, ScoreboardDialog, StadiumDialog

if TYPE_CHECKING:
    from .app import Server16App


class AssignmentRuntime:
    def __init__(self, app: "Server16App") -> None:
        self.app = app

    def _ensure_fifa_selected(self) -> bool:
        app = self.app
        if app._has_selected_fifa_exe():
            return True
        messagebox.showwarning(app.tr("message.assignment"), app.tr("message.warning.select_fifa_first"))
        app.log("Assignment blocked: FIFA EXE not selected")
        return False

    def refresh_context_for_assignment(self) -> None:
        app = self.app
        page_name = app.labels["page"].cget("text")
        if page_name and "Process not running" not in page_name and "Offsets" not in page_name:
            app.refresh_live_context(page_name)

    def default_scope_for_scoreboard(self) -> str:
        app = self.app
        if app.TOURROUNDID:
            return "1"
        if app.TOURNAME:
            return "0"
        if app.HID:
            return "2"
        return "2"

    def default_scope_for_movie(self) -> str:
        app = self.app
        if app.TOURROUNDID:
            return "1"
        if app.TOURNAME:
            return "0"
        if app.HID and app.AID:
            return "2"
        if app.HID:
            return "3"
        return "3"

    def default_scope_for_stadium(self) -> str:
        app = self.app
        if app.TOURROUNDID:
            return "1"
        if app.TOURNAME:
            return "4"
        return "0"

    def resolve_assignment_target(self, scope: str, mapping: dict[str, tuple[str, str]]) -> tuple[str, str] | tuple[None, None]:
        app = self.app
        preferred = mapping.get(scope)
        if preferred:
            value, label = preferred
            if value:
                return value, label
        for value, label in mapping.values():
            if value:
                app.log(f"Assignment fallback to {label} because requested scope {scope} has no context")
                return value, label
        return None, None

    def assign_scoreboard(self) -> None:
        app = self.app
        self.refresh_context_for_assignment()
        app.prepare_floating_window()
        dialog = ScoreboardDialog(app, app.exedir, default_scope=self.default_scope_for_scoreboard())
        app.wait_window(dialog)
        if not dialog.result:
            return
        scope = dialog.result["selectedround"]
        tvlogo = dialog.result["Selectedtvlogo"]
        scoreboard = dialog.result["Selectedscoreboard"]
        comp, resolved = self.resolve_assignment_target(
            scope,
            {
                "0": (app.TOURNAME, "Tournament"),
                "1": (app.TOURROUNDID, "Round"),
                "2": (app.HID, "Home Team"),
            },
        )
        if not comp:
            messagebox.showwarning(app.tr("message.assignment"), app.tr("message.warning.no_context"))
            app.log("Scoreboard assignment skipped: no usable context")
            return
        app.log(f"Scoreboard assignment using {resolved}: {comp}")
        if resolved == "Home Team":
            self.teamscoreboards(comp, tvlogo, scoreboard)
        else:
            self.scoreboards(comp, tvlogo, scoreboard)

    def assign_movie(self) -> None:
        app = self.app
        self.refresh_context_for_assignment()
        app.prepare_floating_window()
        dialog = MovieDialog(app, app.exedir, default_scope=self.default_scope_for_movie())
        app.wait_window(dialog)
        if not dialog.result:
            return
        scope = dialog.result["selectedround"]
        movie = dialog.result["Selectedmovie"]
        comp, resolved = self.resolve_assignment_target(
            scope,
            {
                "0": (app.TOURNAME, "Tournament"),
                "1": (app.TOURROUNDID, "Round"),
                "2": (app.derby if app.HID and app.AID else "", "Derby"),
                "3": (app.HID, "Home Team"),
            },
        )
        if not comp:
            messagebox.showwarning(app.tr("message.assignment"), app.tr("message.warning.no_context"))
            app.log("Movie assignment skipped: no usable context")
            return
        app.log(f"Movie assignment using {resolved}: {comp}")
        if resolved == "Home Team":
            self.moviesassign(comp, movie, "TeamMovies")
        elif resolved == "Derby":
            self.moviesassign(comp, movie, "DerbyMatch")
        else:
            self.moviesassign(comp, movie, "movies")

    def assign_stadium(self) -> None:
        app = self.app
        self.refresh_context_for_assignment()
        app.prepare_floating_window()
        dialog = StadiumDialog(app, app.exedir, default_scope=self.default_scope_for_stadium())
        app.wait_window(dialog)
        if not dialog.result:
            return
        scope = dialog.result["selectedround"]
        selected_stadium = dialog.result["Selectedstadium"]
        selected_police = dialog.result["selectedpolice"]
        selected_pitch = dialog.result["selectedpitch"]
        selected_net = dialog.result["selectednet"]
        multi = dialog.result["multistadium"]
        if selected_stadium == "None":
            payload = "None"
        elif scope in {"2", "3", "4"}:
            payload = ",".join(multi + [selected_police, selected_pitch, selected_net])
        else:
            payload = ",".join([selected_stadium, selected_police, selected_pitch, selected_net])
        comp, resolved = self.resolve_assignment_target(
            scope,
            {
                "0": (app.HID, "Home Team"),
                "1": (app.TOURROUNDID, "Round"),
                "2": (app.HID, "Home Team"),
                "3": (app.TOURROUNDID, "Round"),
                "4": (app.TOURNAME, "Tournament"),
            },
        )
        if not comp:
            messagebox.showwarning(app.tr("message.assignment"), app.tr("message.warning.no_context"))
            app.log("Stadium assignment skipped: no usable context")
            return
        app.log(f"Stadium assignment using {resolved}: {comp}")
        if resolved == "Home Team":
            self.assignstadium_value(comp, payload, "stadium")
        else:
            self.assigncompstadium(comp, payload, "comp")

    def exclude_competition(self) -> None:
        app = self.app
        app.refresh_live_context(app.labels["page"].cget("text"))
        app.prepare_floating_window()
        dialog = ExcludeDialog(app)
        app.wait_window(dialog)
        if not dialog.result:
            return
        comp_id = app.TOURNAME if dialog.result == "COMP ID" else app.TOURROUNDID
        if not app.settings_ini.key_exists(comp_id, "exclude"):
            app.settings_ini.write(comp_id, "excluded from stadium server", "exclude")
            app.settings_ini.save()
            messagebox.showinfo(app.tr("message.exclude"), app.tr("message.exclude.added", comp_id=comp_id))
        elif messagebox.askyesno(app.tr("message.exclude"), app.tr("message.exclude.already", comp_id=comp_id)):
            app.settings_ini.delete_key(comp_id, "exclude")
            app.settings_ini.save()
            messagebox.showinfo(app.tr("message.exclude"), app.tr("message.exclude.removed", comp_id=comp_id))

    def scoreboards(self, comp: str, tvlogo: str, scoreboard: str) -> None:
        self.assign_with_delete(comp, "TVLogo", tvlogo, "default", f"Tournament {comp} has been assigned {tvlogo} TVLogo")
        self.assign_with_delete(comp, "Scoreboard", scoreboard, "default", f"Tournament {comp} has been assigned {scoreboard} Scoreboard")

    def teamscoreboards(self, comp: str, tvlogo: str, scoreboard: str) -> None:
        self.assign_with_delete(comp, "HomeTeamTvLogo", tvlogo, "default", f"Home Team {comp} has been assigned {tvlogo} TVLogo")
        self.assign_with_delete(comp, "HomeTeamScoreBoard", scoreboard, "default", f"Home Team {comp} has been assigned {scoreboard} Scoreboard")

    def moviesassign(self, comp: str, movie: str, section: str) -> None:
        self.assign_with_delete(comp, section, movie, "None", f"{section} for {comp} set to {movie}")

    def assignstadium_value(self, comp: str, value: str, section: str) -> None:
        self.assign_with_delete(comp, section, value, "None", f"Team {comp} stadium set to {value}")

    def assigncompstadium(self, comp: str, value: str, section: str) -> None:
        self.assign_with_delete(comp, section, value, "None", f"Tournament {comp} stadium set to {value}")

    def assign_with_delete(self, comp: str, key: str, value: str, default_value: str, success_message: str) -> None:
        app = self.app
        if not comp:
            messagebox.showwarning(app.tr("message.assignment"), app.tr("message.warning.no_context"))
            app.log(f"Assignment skipped: missing context for key={key} value={value}")
            return
        changed = False
        if not app.settings_ini.key_exists(comp, key):
            if value != default_value:
                app.settings_ini.write(comp, value, key)
                app.settings_ini.save()
                messagebox.showinfo(app.tr("message.assignment"), success_message)
                changed = True
                app.log(f"Assignment created: [{key}] {comp}={value}")
            if changed:
                app.apply_all_runtime()
            return
        if value == default_value:
            if messagebox.askyesno(app.tr("message.assignment"), app.tr("message.prompt.reset_default", comp=comp, key=key)):
                app.settings_ini.delete_key(comp, key)
                app.settings_ini.save()
                changed = True
                app.log(f"Assignment reset: [{key}] {comp}")
            if changed:
                app.apply_all_runtime()
            return
        if messagebox.askyesno(app.tr("message.assignment"), app.tr("message.prompt.replace_assignment", comp=comp, key=key)):
            app.settings_ini.write(comp, value, key)
            app.settings_ini.save()
            messagebox.showinfo(app.tr("message.assignment"), success_message)
            changed = True
            app.log(f"Assignment updated: [{key}] {comp}={value}")
        if changed:
            app.apply_all_runtime()
