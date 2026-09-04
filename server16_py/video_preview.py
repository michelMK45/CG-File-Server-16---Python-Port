"""Embedded movie (.vp8) preview playback for the assignment/settings dialogs.

CGFS16's `.vp8` movie files are, on inspection, plain WebM containers (EBML
header, VP8 video + audio) just carrying a `.vp8` extension -- not a bare
VP8 elementary stream. That means they can be decoded by any normal WebM
decoder, not just VLC. This module uses `ffpyplayer` (a Python binding to
FFmpeg + SDL2, whose prebuilt Windows wheel bundles both statically -- no
external player/runtime install required by the end user) to decode and
play them, and drives a small embedded preview surface (with an Autoplay
toggle, a volume slider, and a fullscreen button) shared by dialogs.py's
MovieDialog and settings_editor.py's Movies / TeamMovies / DerbyMatch tabs.

Playback is Play/Stop only -- deliberately no seek/scrub control.
ffpyplayer's MediaPlayer.seek() was found to segfault the whole process
(not just raise a Python exception) when called near end-of-file against a
real CGFS movie asset during manual testing (2026-09-04); natural playback
to EOF and many repeated create/stop/close cycles were both solid. Do not
add a seek/scrub control to this widget without first re-verifying that
finding against a real .vp8 file -- if it still reproduces, it would crash
the whole app, not just the preview.

Second finding from the same round of testing: calling MediaPlayer.set_volume()
immediately after construction (before the player has produced its first
frame) does not fail on that call itself, but reliably segfaults the *next*
MediaPlayer created later in the same process -- isolated via a standalone
repro (2026-09-04): two back-to-back MediaPlayer/set_volume/close cycles with
no delay crash on the second cycle every time; the same cycle with a ~300ms
delay, or with set_volume() deferred until the first real frame comes back
from get_frame(), does not. play()/_pump() below apply the initial volume
this second way (see _volume_applied) rather than right after construction --
do not move that call back to immediately-after-construction without
re-verifying this finding first.
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import ttk

from PIL import Image, ImageTk

PLAY_ICON = "▶"
FULLSCREEN_ICON = "⛶"
VOLUME_ICON = "🔊"

_player_class = None
_load_error: str | None = None
_load_attempted = False


def _load_player_class():
    """Imports ffpyplayer's MediaPlayer exactly once per process, caching
    the result (class or failure reason) for every later call/panel."""
    global _player_class, _load_error, _load_attempted
    if _load_attempted:
        return _player_class
    _load_attempted = True
    try:
        from ffpyplayer.player import MediaPlayer  # type: ignore
    except Exception as exc:  # noqa: BLE001 - report any import failure, not just ImportError
        _load_error = str(exc)
        return None
    _player_class = MediaPlayer
    return MediaPlayer


def player_available() -> bool:
    return _load_player_class() is not None


def player_unavailable_reason() -> str | None:
    _load_player_class()
    return _load_error


class MoviePreviewPanel(tk.Frame):
    """A small embedded video surface with an Autoplay toggle, a volume
    slider, and a fullscreen button.

    Shared by MovieDialog (dialogs.py) and the Settings Editor's Movies /
    TeamMovies / DerbyMatch tabs (settings_editor.py) -- callers just call
    set_movie(path_or_None) whenever the selection changes and this widget
    owns the ffpyplayer MediaPlayer lifecycle from there.

    The Autoplay checkbox is persistent state, not a momentary Play/Stop
    button: while checked, every set_movie() call (i.e. every time the user
    picks a different movie) starts playing the new one immediately, so
    there's no need to press Play after each selection. Unchecking it stops
    playback and leaves further selections stopped until re-checked.
    """

    DEFAULT_VOLUME = 0.8

    def __init__(self, parent: tk.Misc, app, width: int = 340, height: int = 191) -> None:
        super().__init__(parent, bg=app.card)
        self.app = app
        self._movie_path: Path | None = None
        self._player = None
        self._playing = False
        self._poll_job = None
        self._photo: ImageTk.PhotoImage | None = None
        self._surface_width = width
        self._surface_height = height
        self._volume = self.DEFAULT_VOLUME
        self._volume_applied = False

        surface = tk.Frame(
            self, bg="black", width=width, height=height, highlightthickness=1, highlightbackground="#243654"
        )
        surface.pack(fill="x")
        surface.pack_propagate(False)
        self.video_label = tk.Label(surface, bg="black", bd=0, highlightthickness=0)
        self.video_label.pack(fill="both", expand=True)

        controls = tk.Frame(self, bg=app.card)
        controls.pack(fill="x", pady=(6, 0))
        self.autoplay_var = tk.BooleanVar(value=True)
        self.autoplay_check = ttk.Checkbutton(
            controls,
            text=f"{PLAY_ICON} {app.tr('dialog.movie_preview.autoplay')}",
            variable=self.autoplay_var,
            style="Switch.TCheckbutton",
            command=self._on_autoplay_toggle,
            state="disabled",
        )
        self.autoplay_check.pack(side="left")
        self.fullscreen_button = ttk.Button(
            controls, text=FULLSCREEN_ICON, width=3, command=self._open_fullscreen, state="disabled"
        )
        self.fullscreen_button.pack(side="left", padx=(6, 0))
        self.status_var = tk.StringVar()
        tk.Label(
            controls,
            textvariable=self.status_var,
            bg=app.card,
            fg=app.muted,
            font=("Bahnschrift", 9),
            anchor="w",
        ).pack(side="left", fill="x", expand=True, padx=(8, 0))

        volume_row = tk.Frame(self, bg=app.card)
        volume_row.pack(fill="x", pady=(4, 0))
        tk.Label(volume_row, text=VOLUME_ICON, bg=app.card, fg=app.muted, font=("Bahnschrift", 9)).pack(side="left")
        self.volume_var = tk.DoubleVar(value=self._volume * 100)
        self.volume_scale = tk.Scale(
            volume_row,
            from_=0,
            to=100,
            orient="horizontal",
            variable=self.volume_var,
            command=self._on_volume_change,
            bg=app.card,
            fg=app.fg,
            troughcolor=app.panel_alt,
            activebackground=app.accent,
            highlightthickness=0,
            bd=0,
            showvalue=False,
            sliderlength=14,
        )
        self.volume_scale.pack(side="left", fill="x", expand=True, padx=(6, 0))

        if not player_available():
            self.status_var.set(app.tr("dialog.movie_preview.unavailable"))
            reason = player_unavailable_reason()
            if reason:
                app.log(f"Movie preview disabled: {reason}")
        else:
            self.status_var.set(app.tr("dialog.movie_preview.no_selection"))

        self.bind("<Destroy>", self._on_destroy)

    def set_movie(self, path: "Path | None") -> None:
        self.stop()
        self._movie_path = path
        self._photo = None
        try:
            self.video_label.configure(image="")
        except Exception:
            pass
        if not player_available():
            return
        if path is None:
            self.autoplay_check.configure(state="disabled")
            self.fullscreen_button.configure(state="disabled")
            self.status_var.set(self.app.tr("dialog.movie_preview.no_selection"))
        else:
            self.autoplay_check.configure(state="normal")
            self.fullscreen_button.configure(state="normal")
            self.status_var.set(path.parent.name)
            if self.autoplay_var.get():
                self.play()

    def _on_autoplay_toggle(self) -> None:
        if self.autoplay_var.get():
            if self._movie_path is not None:
                self.play()
        else:
            self.stop()

    def _on_volume_change(self, _value=None) -> None:
        self._volume = max(0.0, min(1.0, self.volume_var.get() / 100.0))
        # Only push it live once the player has cleared the same first-frame
        # gate _pump() uses -- see play()'s comment on why set_volume() is
        # unsafe before that point. If it hasn't yet, _pump() will pick up
        # the updated self._volume itself when that gate opens.
        if self._player is not None and self._volume_applied:
            try:
                self._player.set_volume(self._volume)
            except Exception:
                pass

    def play(self) -> None:
        if self._movie_path is None or not player_available():
            return
        self.stop()
        media_player_cls = _load_player_class()
        try:
            # Decoding straight to the preview box's own pixel size avoids a
            # per-frame PIL resize of the (often 1280x720) source frame.
            self._player = media_player_cls(
                str(self._movie_path),
                ff_opts={"vf": [f"scale={self._surface_width}:{self._surface_height}"]},
            )
            # Deliberately NOT calling set_volume() here -- doing so immediately
            # after construction (before the player has produced its first
            # frame) reliably segfaulted the whole process on the *next*
            # MediaPlayer created in this run, confirmed by isolated repro
            # (2026-09-04). _pump() applies it once the first real frame
            # arrives instead; see _volume_applied below.
        except Exception as exc:
            self.app.log(f"Movie preview playback failed for {self._movie_path}", exc)
            self.status_var.set(self.app.tr("dialog.movie_preview.play_failed", file=self._movie_path.name))
            self._player = None
            return
        self._playing = True
        self._volume_applied = False
        self._pump()

    def stop(self) -> None:
        """Halts playback (tab-switch cleanup, EOF, switching movies with
        Autoplay off, or unchecking Autoplay) without touching the Autoplay
        checkbox's own checked state -- see the class docstring."""
        if self._poll_job is not None:
            try:
                self.after_cancel(self._poll_job)
            except Exception:
                pass
            self._poll_job = None
        if self._player is not None:
            try:
                self._player.close_player()
            except Exception:
                pass
            self._player = None
        self._playing = False

    def _pump(self) -> None:
        self._poll_job = None
        if self._player is None or not self._playing:
            return
        try:
            frame, val = self._player.get_frame()
        except Exception as exc:
            self.app.log(f"Movie preview frame read failed for {self._movie_path}", exc)
            self.stop()
            return
        if val == "eof":
            self.stop()
            return
        if frame is not None:
            self._show_frame(frame)
            if not self._volume_applied:
                # First real frame -- now safe to set the initial volume,
                # see play()'s comment.
                try:
                    self._player.set_volume(self._volume)
                except Exception:
                    pass
                self._volume_applied = True
        delay_s = val if isinstance(val, float) else 0.01
        delay_ms = max(1, min(200, int(delay_s * 1000)))
        self._poll_job = self.after(delay_ms, self._pump)

    def _show_frame(self, frame) -> None:
        image, _pts = frame
        width, height = image.get_size()
        try:
            buf = bytes(image.to_bytearray()[0])
            pil_image = Image.frombytes("RGB", (width, height), buf)
            self._photo = ImageTk.PhotoImage(pil_image)
            self.video_label.configure(image=self._photo)
        except Exception:
            pass

    def _open_fullscreen(self) -> None:
        if self._movie_path is None or not player_available():
            return
        # Stop the inline copy first so its audio doesn't play alongside the
        # fullscreen window's own independent decode/playback below.
        self.stop()

        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        max_w, max_h = int(screen_w * 0.9), int(screen_h * 0.9)
        if max_w * 9 <= max_h * 16:
            target_w, target_h = max_w, int(max_w * 9 / 16)
        else:
            target_h, target_w = max_h, int(max_h * 16 / 9)

        win = tk.Toplevel(self)
        win.configure(bg="black")
        win.transient(self.winfo_toplevel())
        win.attributes("-fullscreen", True)

        big_panel = MoviePreviewPanel(win, self.app, width=target_w, height=target_h)
        big_panel.pack(expand=True)

        def _close(_event=None) -> None:
            big_panel.stop()
            win.destroy()

        ttk.Button(win, text=self.app.tr("dialog.movie_preview.close_fullscreen"), command=_close).place(
            relx=1.0, x=-16, y=16, anchor="ne"
        )
        win.bind("<Escape>", _close)
        win.protocol("WM_DELETE_WINDOW", _close)
        win.focus_force()

        # autoplay_var defaults to True on the fresh panel, so this starts
        # playback immediately -- opening fullscreen *is* the play action.
        big_panel.set_movie(self._movie_path)

    def _on_destroy(self, _event=None) -> None:
        if self._poll_job is not None:
            try:
                self.after_cancel(self._poll_job)
            except Exception:
                pass
            self._poll_job = None
        if self._player is not None:
            try:
                self._player.close_player()
            except Exception:
                pass
            self._player = None
