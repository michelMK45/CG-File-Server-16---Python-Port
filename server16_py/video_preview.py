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
from get_frame(), does not. The worker loop below applies the initial volume
this second way (see volume_applied) rather than right after construction --
do not move that call back to immediately-after-construction without
re-verifying this finding first.

Threading model (added 2026-09-16): MediaPlayer construction/close and the
per-frame decode+colorspace-convert used to run synchronously on the Tk main
thread. Opening/probing a movie file inside the MediaPlayer constructor is a
genuinely blocking call, so rapidly changing the selection (e.g. arrow-key
navigation through MovieDialog's listbox, each keystroke firing a
set_movie() -> stop()+play() pair) froze the whole UI for several seconds --
one blocking open+close per keystroke, all on the thread that also has to
keep processing Tk events. Per-frame work (get_frame() + the RGB buffer copy
+ Image.frombytes()) competing with every other `after()`-driven timer this
app runs (game-memory polling, the D3D overlay sync loop, etc.) was also the
likely source of the reported playback jank even without touching the
selection at all.

Fix: a single background thread owns the actual `MediaPlayer` instance for
the lifetime of the panel. The Tk thread only ever talks to it through two
queues -- `_cmd_queue` (UI -> worker: open/stop/volume/shutdown) and
`_frame_queue`/`_status_queue` (worker -> UI: decoded frames, EOF, errors).
Every command the worker pulls off `_cmd_queue` is first collapsed to the
*latest* one still pending (`_drain_latest_command`) before being acted on,
so a burst of selection changes opens only the last-requested movie -- the
intermediate ones are never even constructed, which is what actually removes
the multi-second freeze (not just moving it off-thread). Only
`ImageTk.PhotoImage` construction and `Label.configure` remain on the main
thread, since Tk widgets/images can only be touched from the thread that
owns the Tk interpreter; `_ui_poll()` drains both queues at a fixed ~60Hz
tick to pick those up.

Because only the worker thread ever touches a given MediaPlayer instance,
the segfault-avoidance rules above (no seek(), delay set_volume() until the
first frame) are enforced entirely inside `_worker_loop` now. Also note:
`app.log()` writes to a Tk Text widget and must never be called from the
worker thread -- errors are posted onto `_status_queue` as plain data and
logged from `_ui_poll` on the main thread instead.
"""

from __future__ import annotations

import queue
import threading
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

_CMD_OPEN = "open"
_CMD_STOP = "stop"
_CMD_VOLUME = "volume"
_CMD_SHUTDOWN = "shutdown"


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
    owns the ffpyplayer MediaPlayer lifecycle (on a background worker
    thread -- see the module docstring) from there.

    The Autoplay checkbox is persistent state, not a momentary Play/Stop
    button: while checked, every set_movie() call (i.e. every time the user
    picks a different movie) starts playing the new one immediately, so
    there's no need to press Play after each selection. Unchecking it stops
    playback and leaves further selections stopped until re-checked.
    """

    DEFAULT_VOLUME = 0.8
    _UI_POLL_MS = 15

    def __init__(
        self,
        parent: tk.Misc,
        app,
        width: int = 340,
        height: int = 191,
        show_fullscreen_button: bool = True,
    ) -> None:
        super().__init__(parent, bg=app.card)
        self.app = app
        self._movie_path: Path | None = None
        self._destroyed = False
        self._poll_job = None
        self._photo: ImageTk.PhotoImage | None = None
        self._surface_width = width
        self._surface_height = height
        self._volume = self.DEFAULT_VOLUME
        self._generation = 0

        # UI <-> worker handoff. _frame_queue is bounded to 1: the worker
        # always evicts any not-yet-shown frame before pushing a new one, so
        # the UI thread only ever sees the freshest decoded frame instead of
        # working through a backlog if it's briefly slower than decode.
        self._cmd_queue: "queue.Queue" = queue.Queue()
        self._frame_queue: "queue.Queue" = queue.Queue(maxsize=1)
        self._status_queue: "queue.Queue" = queue.Queue()
        self._worker_thread: threading.Thread | None = None

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
        # The panel embedded inside _open_fullscreen()'s own Toplevel is
        # already fullscreen -- showing this button there let a click spawn a
        # second, larger fullscreen window on top instead of closing anything.
        if show_fullscreen_button:
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
            self._worker_thread = threading.Thread(
                target=self._worker_loop, name="MoviePreviewWorker", daemon=True
            )
            self._worker_thread.start()

        self.bind("<Destroy>", self._on_destroy)
        self._poll_job = self.after(self._UI_POLL_MS, self._ui_poll)

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
        if self._worker_thread is not None:
            self._cmd_queue.put((_CMD_VOLUME, self._volume))

    def play(self) -> None:
        if self._movie_path is None or not player_available():
            return
        self._generation += 1
        self._drain(self._frame_queue)
        self._drain(self._status_queue)
        # The generation/volume travel with the OPEN command itself (rather
        # than being read back from shared state) so a burst of rapid
        # switches can never apply a stale volume to the movie that actually
        # ends up opened, even after _drain_latest_command discards the
        # commands in between.
        self._cmd_queue.put((_CMD_OPEN, self._movie_path, self._generation, self._volume))

    def stop(self) -> None:
        """Halts playback (tab-switch cleanup, switching movies with
        Autoplay off, unchecking Autoplay, or panel destroy) without
        touching the Autoplay checkbox's own checked state -- see the class
        docstring. EOF is handled entirely inside the worker loop and does
        not route through here."""
        self._generation += 1
        if self._worker_thread is not None:
            self._cmd_queue.put((_CMD_STOP,))
        self._drain(self._frame_queue)
        self._drain(self._status_queue)

    @staticmethod
    def _drain(q: "queue.Queue") -> None:
        while True:
            try:
                q.get_nowait()
            except queue.Empty:
                return

    @staticmethod
    def _drain_latest_command(first_cmd, cmd_queue: "queue.Queue"):
        """Collapses any commands already queued behind first_cmd down to
        just the most recent one -- a burst of rapid selection changes then
        only ever opens the last-requested movie; the intermediate ones are
        never constructed at all, which is what actually removes the
        multi-second freeze from rapid list navigation (not merely moving
        the work off the Tk thread)."""
        cmd = first_cmd
        while True:
            try:
                cmd = cmd_queue.get_nowait()
            except queue.Empty:
                return cmd

    # -- worker thread -----------------------------------------------------
    # Everything below this point runs on the background worker thread and
    # must never touch a Tk widget or call self.app.log() directly (see the
    # module docstring) -- only the two queues above are safe to cross back
    # to the UI thread.

    def _worker_loop(self) -> None:
        media_player_cls = _load_player_class()
        player = None
        generation = -1
        movie_name = "?"
        volume = self._volume
        volume_applied = False
        wait_s = None  # block indefinitely until there's a player to pump

        while True:
            try:
                cmd = self._cmd_queue.get(timeout=wait_s)
            except queue.Empty:
                cmd = None

            if cmd is not None:
                cmd = self._drain_latest_command(cmd, self._cmd_queue)
                kind = cmd[0]
                if kind == _CMD_SHUTDOWN:
                    if player is not None:
                        try:
                            player.close_player()
                        except Exception:
                            pass
                    return
                if kind == _CMD_STOP:
                    if player is not None:
                        try:
                            player.close_player()
                        except Exception:
                            pass
                        player = None
                    wait_s = None
                    continue
                if kind == _CMD_VOLUME:
                    volume = cmd[1]
                    if player is not None and volume_applied:
                        try:
                            player.set_volume(volume)
                        except Exception:
                            pass
                    continue
                if kind == _CMD_OPEN:
                    _, path, generation, volume = cmd
                    movie_name = path.name
                    if player is not None:
                        try:
                            player.close_player()
                        except Exception:
                            pass
                        player = None
                    try:
                        # Decoding straight to the preview box's own pixel
                        # size avoids a per-frame PIL resize of the (often
                        # 1280x720) source frame.
                        player = media_player_cls(
                            str(path),
                            ff_opts={"vf": [f"scale={self._surface_width}:{self._surface_height}"]},
                        )
                        volume_applied = False
                    except Exception as exc:
                        self._status_queue.put(("error", generation, movie_name, exc))
                        player = None
                        wait_s = None
                        continue
                    wait_s = 0.001
                    continue

            if player is None:
                wait_s = None
                continue

            try:
                frame, val = player.get_frame()
            except Exception as exc:
                self._status_queue.put(("error", generation, movie_name, exc))
                try:
                    player.close_player()
                except Exception:
                    pass
                player = None
                wait_s = None
                continue

            if val == "eof":
                try:
                    player.close_player()
                except Exception:
                    pass
                player = None
                wait_s = None
                continue

            if frame is not None:
                image, _pts = frame
                width, height = image.get_size()
                pil_image = None
                try:
                    buf = bytes(image.to_bytearray()[0])
                    pil_image = Image.frombytes("RGB", (width, height), buf)
                except Exception:
                    pass
                if not volume_applied:
                    # First real frame -- now safe to set the initial
                    # volume, see the module docstring's second finding.
                    try:
                        player.set_volume(volume)
                    except Exception:
                        pass
                    volume_applied = True
                if pil_image is not None:
                    self._drain(self._frame_queue)
                    try:
                        self._frame_queue.put_nowait((generation, pil_image))
                    except queue.Full:
                        pass

            delay_s = val if isinstance(val, float) else 0.01
            wait_s = max(0.001, min(0.2, delay_s))

    # -- UI thread -----------------------------------------------------

    def _ui_poll(self) -> None:
        if self._destroyed:
            return
        self._poll_job = self.after(self._UI_POLL_MS, self._ui_poll)

        while True:
            try:
                message = self._status_queue.get_nowait()
            except queue.Empty:
                break
            self._handle_status_message(message)

        latest_frame = None
        while True:
            try:
                latest_frame = self._frame_queue.get_nowait()
            except queue.Empty:
                break
        if latest_frame is not None:
            generation, pil_image = latest_frame
            if generation == self._generation:
                self._apply_frame(pil_image)

    def _apply_frame(self, pil_image) -> None:
        # Re-creating a Tk PhotoImage from scratch every frame (the previous
        # approach) allocates a brand-new Tcl-side image object and copies
        # the whole pixel buffer through the Tcl/Tk C API each time -- cheap
        # enough at the small inline-preview size, but at fullscreen
        # resolution (_open_fullscreen can target up to ~90% of the screen,
        # many times the pixel count) this was the actual remaining
        # bottleneck on the Tk main thread, unaffected by moving decode
        # itself onto the worker thread. PhotoImage.paste() updates the
        # existing image's pixels in place instead, reusing the same
        # Tcl-side object -- added after the worker-thread change (which
        # fixed selection-switch freezes) was reported live as not helping
        # fullscreen playback smoothness (2026-09-16), where the pixel count
        # is far higher. Falls back to a fresh PhotoImage the first time, or
        # if the frame size ever changes (shouldn't happen mid-playback --
        # decode target size is fixed per panel -- but paste() would raise
        # on a size mismatch).
        try:
            if (
                self._photo is not None
                and self._photo.width() == pil_image.width
                and self._photo.height() == pil_image.height
            ):
                self._photo.paste(pil_image)
            else:
                self._photo = ImageTk.PhotoImage(pil_image)
                self.video_label.configure(image=self._photo)
        except Exception:
            pass

    def _handle_status_message(self, message) -> None:
        kind, generation = message[0], message[1]
        if generation != self._generation:
            return  # stale -- superseded by a later stop()/play() already
        if kind == "error":
            _, _, movie_name, exc = message
            self.app.log(f"Movie preview playback failed for {movie_name}", exc)
            self.status_var.set(self.app.tr("dialog.movie_preview.play_failed", file=movie_name))
        # "eof" is deliberately a no-op here, matching the previous
        # behavior: playback just freezes on the last decoded frame.

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

        big_panel = MoviePreviewPanel(
            win, self.app, width=target_w, height=target_h, show_fullscreen_button=False
        )
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
        self._destroyed = True
        if self._poll_job is not None:
            try:
                self.after_cancel(self._poll_job)
            except Exception:
                pass
            self._poll_job = None
        if self._worker_thread is not None:
            self._cmd_queue.put((_CMD_SHUTDOWN,))
            # Deliberately not joined -- close_player() can take a moment and
            # this runs on the Tk callback tearing the widget down. The
            # worker is a daemon thread and exits on its own shortly after.
            self._worker_thread = None
