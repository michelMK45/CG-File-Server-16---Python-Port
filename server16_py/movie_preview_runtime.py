"""
movie_preview_runtime.py
-------------------------
Live video playback for the D3D overlay's Movies-tab hero panel.

Every other overlay-menu preview (Stadiums/Kits/ScoreBoard/TVLogo) is a
single static image, loaded once by the DLL via RmlUi's WIC-backed
LoadTexture and cached until the path changes — see app_overlay.py's
_update_d3d_preview_image() and file_tools.resolve_asset_thumbnail_path().
Movies assets are themselves short video clips (bootflowoutro.vp8), and the
desktop UI's own Movies preview (video_preview.py's MoviePreviewPanel)
already plays them back live with audio the moment one is selected — this
module ports that same "autoplay on select" behavior into the in-game F12
menu.

The D3D overlay has no video-frame rendering pipeline of its own (RmlUi's
LoadTexture only ever loads a static file once, and a fresh video frame
arrives ~15-30x/second — far too often to recreate a whole RmlUi texture
for). This runtime decodes frames with ffpyplayer (same library/backend as
video_preview.py, same proven segfault-avoidance rules — see below) on a
dedicated background thread and streams each one into a second, dedicated
shared-memory buffer (_OverlayVideoShared, see d3d_injector.py and
OverlayVideoShared in cgfs16_overlay.cpp) that the DLL renders as a
manually-drawn, per-frame-updated D3D11 texture (cgfs16_rmlui.cpp's
EnsureVideoTexture/DrawVideoQuad, driven from cgfs16_rmlui_menu.cpp's
TAB_MOVIES handling) instead of through RmlUi's own texture pipeline.

Audio plays automatically via ffpyplayer's own SDL output — the same
mechanism MoviePreviewPanel already relies on. This project's chants/
entrance-anthem code already establishes the precedent of a second audio
stream playing concurrently with FIFA's own game audio (see
chants_runtime.py/entrance_runtime.py), so this isn't a new category of
behavior for this codebase, just a new source.

Segfault-avoidance rules ported from video_preview.py (found via manual
testing 2026-09-04 against a real .vp8 file — re-verify against a real file
before changing either):
  1. Never call MediaPlayer.seek() — reliably segfaults near EOF. This
     runtime has no scrub control, so it never needs to.
  2. Never call MediaPlayer.set_volume() — calling it (even once) reliably
     segfaults the *next* MediaPlayer created anywhere in this process
     afterward, including one created later by MoviePreviewPanel. Volume
     here is fixed for the process's lifetime via the `volume` ff_opts
     constructor argument instead, a different (and safe) code path.
"""
from __future__ import annotations

import sys
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image as PILImage

from .d3d_injector import _VIDEO_FRAME_BYTES, _VIDEO_H, _VIDEO_W

if TYPE_CHECKING:
    from .app import Server16App

_player_class = None
_load_attempted = False


def _load_player_class():
    """Imports ffpyplayer's MediaPlayer exactly once per process, caching
    the result — mirrors video_preview.py's own _load_player_class(), kept
    as a separate copy rather than a shared import since the two modules'
    failure/logging needs differ slightly and neither is large."""
    global _player_class, _load_attempted
    if _load_attempted:
        return _player_class
    _load_attempted = True
    try:
        from ffpyplayer.player import MediaPlayer  # type: ignore
    except Exception:
        return None
    _player_class = MediaPlayer
    return _player_class


def player_available() -> bool:
    return _load_player_class() is not None


class MoviePreviewRuntime:
    """Drives at most one background ffpyplayer decode loop at a time for
    the D3D overlay's Movies-tab hero panel. start_for_item()/stop() are the
    only entry points app_overlay.py needs; a generation counter (same
    cancellation pattern as TeamEntranceRuntime, see entrance_runtime.py)
    makes switching items or stopping mid-decode safe without the old
    worker's stray frames landing after a newer one has taken over."""

    # Lower than MoviePreviewPanel's own 0.8 default: this plays *alongside*
    # FIFA's own live game audio (and possibly chants), not in the isolated
    # desktop-dialog context the UI's preview panel is used in.
    DEFAULT_VOLUME = 0.45

    def __init__(self, app: "Server16App") -> None:
        self.app = app
        self._lock = threading.Lock()
        self._generation = 0
        self._running = False
        self._current_path: Path | None = None
        # Persists across item switches within one F12 session (mute the
        # panel, keep browsing — it should stay muted) rather than resetting
        # per-item, AND across app restarts via SettingsStore (runtime/
        # settings.json's MOVIE_PREVIEW_MUTED) — see toggle_mute(). Plain
        # bool: read/written from the Tk main thread (via toggle_mute()) and
        # read from the decode worker thread, but Python's GIL already makes
        # a single bool read/write atomic enough here — no lock needed for a
        # flag with no other invariant tied to it, unlike _generation/
        # _running above.
        try:
            self._muted = bool(app.settings.movie_preview_muted)
        except Exception:
            self._muted = False

    @property
    def is_muted(self) -> bool:
        return self._muted

    def toggle_mute(self) -> bool:
        """Flips the mute flag, persists it to settings.json so the next time
        the F12 menu is opened (this session or a future one) remembers it,
        and — if a worker is currently playing — applies it live via
        MediaPlayer.set_volume(). That live call is safe here specifically
        because the worker only ever makes it well after its first decoded
        frame (see _run_worker's mute-poll below and the module docstring's
        segfault-avoidance rule #2: the danger is calling set_volume()
        *before* the first frame, not calling it repeatedly afterward —
        video_preview.py's own volume slider already does exactly that,
        live, proven in production). Returns the new muted state."""
        self._muted = not self._muted
        try:
            self.app.settings.movie_preview_muted = self._muted
        except Exception:
            pass
        return self._muted

    def start_for_item(self, path: Path) -> None:
        """Starts playing *path* — a no-op if it's already the one playing."""
        with self._lock:
            if self._running and self._current_path == path:
                return
            self._generation += 1
            generation = self._generation
            self._running = True
            self._current_path = path
        # Hide whatever frame is already in the buffer immediately rather
        # than leaving the previous item's last frame visible until the new
        # worker's own first frame arrives and overwrites it.
        inj = getattr(self.app, "_d3d_injector", None)
        if inj is not None:
            try:
                inj.set_video_playing(False)
            except Exception:
                pass
        threading.Thread(
            target=self._run_worker,
            args=(generation, path),
            daemon=True,
            name="MoviePreview",
        ).start()

    def stop(self) -> None:
        with self._lock:
            self._generation += 1
            self._running = False
            self._current_path = None
        inj = getattr(self.app, "_d3d_injector", None)
        if inj is not None:
            try:
                inj.set_video_playing(False)
            except Exception:
                pass

    def _is_current(self, generation: int) -> bool:
        with self._lock:
            return generation == self._generation

    def _run_worker(self, generation: int, path: Path) -> None:
        app = self.app
        media_player_cls = _load_player_class()
        if media_player_cls is None:
            with self._lock:
                if generation == self._generation:
                    self._running = False
            return

        try:
            player = media_player_cls(
                str(path),
                ff_opts={
                    # Decoding straight to the shared-memory buffer's fixed
                    # size avoids any per-frame resize on the C++ side, same
                    # reasoning as MoviePreviewPanel.play()'s own vf=scale.
                    "vf": [f"scale={_VIDEO_W}:{_VIDEO_H}"],
                    "out_fmt": "bgra",  # matches DXGI_FORMAT_B8G8R8A8_UNORM directly, no channel swizzle needed
                    # Deliberately NO "volume" key here — found live not to
                    # reliably suppress audio (2026-09-04: starting already
                    # muted, the button showed "muted" but audio kept
                    # playing). MoviePreviewPanel.play() (video_preview.py)
                    # never uses this ff_opts key either — it always leaves
                    # the starting volume unspecified and applies the real
                    # value via a deferred set_volume() call once the first
                    # frame arrives instead (see the `applied_muted = None`
                    # handling below). Match that exact proven mechanism
                    # rather than a second, less-tested one.
                },
            )
        except Exception as exc:
            app.log(f"Movie preview playback failed for {path}", exc, exc_info=sys.exc_info())
            with self._lock:
                if generation == self._generation:
                    self._running = False
            return

        announced = False
        logged_size = False
        # None until the first real frame applies it (see below) — tracks
        # what set_volume() last actually set, so a later mute toggle can
        # tell whether it needs to call set_volume() again.
        applied_muted = None
        try:
            while self._is_current(generation):
                inj = getattr(app, "_d3d_injector", None)
                if inj is None:
                    time.sleep(0.05)
                    continue
                try:
                    frame, val = player.get_frame()
                except Exception as exc:
                    app.log(f"Movie preview frame read failed for {path}", exc, exc_info=sys.exc_info())
                    break
                if val == "eof":
                    # Hold the last frame visible — matches MoviePreviewPanel's
                    # own stop(), which never clears the displayed image on
                    # EOF. Just stop pumping new frames; `playing` stays 1.
                    break
                if frame is not None:
                    image, _pts = frame
                    w, h = image.get_size()
                    if not logged_size:
                        logged_size = True
                        # First real frame — now safe to set the initial
                        # volume (module docstring's segfault-avoidance rule
                        # #2), mirroring MoviePreviewPanel.play()'s own
                        # _volume_applied gate exactly rather than the
                        # ff_opts "volume" key this used to rely on.
                        applied_muted = self._muted
                        try:
                            player.set_volume(0.0 if applied_muted else self.DEFAULT_VOLUME)
                        except Exception as exc:
                            app.log(f"Movie preview initial volume failed for {path}", exc, exc_info=sys.exc_info())
                    try:
                        buf = bytes(image.to_bytearray()[0])
                    except Exception:
                        buf = b""
                    if buf and (w, h) != (_VIDEO_W, _VIDEO_H):
                        # ff_opts' vf=scale is expected to force an exact
                        # _VIDEO_W x _VIDEO_H frame, but has been observed to
                        # not always do so (aspect-locked scale, filter
                        # rejected, etc.) — the shared-memory buffer on the
                        # C++ side is a FIXED size (OverlayVideoShared has no
                        # width/height fields, see its header comment), so a
                        # mismatched frame must be resized here rather than
                        # sent as-is (which write_video_frame would just
                        # silently drop via its length check). Treating BGRA
                        # as PIL's generic 4-byte "RGBA" mode is safe for a
                        # pure resize: PIL interpolates 4 opaque byte lanes
                        # per pixel without caring what they represent.
                        try:
                            resized = PILImage.frombytes("RGBA", (w, h), buf).resize(
                                (_VIDEO_W, _VIDEO_H), PILImage.BILINEAR
                            )
                            buf = resized.tobytes()
                        except Exception as exc:
                            app.log(f"Movie preview resize failed for {path}", exc, exc_info=sys.exc_info())
                            buf = b""
                    if len(buf) == _VIDEO_FRAME_BYTES:
                        try:
                            inj.write_video_frame(buf)
                            if not announced:
                                inj.set_video_playing(True)
                                announced = True
                        except Exception:
                            pass
                # Live mute toggle — checked every tick (not just when a
                # fresh frame arrived) for the fastest response; gated on
                # applied_muted already being set, i.e. the initial
                # application above has already happened for this worker.
                if applied_muted is not None and self._muted != applied_muted:
                    applied_muted = self._muted
                    try:
                        player.set_volume(0.0 if applied_muted else self.DEFAULT_VOLUME)
                    except Exception as exc:
                        app.log(f"Movie preview mute toggle failed for {path}", exc, exc_info=sys.exc_info())
                delay_s = val if isinstance(val, float) else 0.01
                time.sleep(max(0.001, min(0.2, delay_s)))
        except Exception as exc:
            app.log(f"Movie preview loop failed for {path}", exc, exc_info=sys.exc_info())
        finally:
            try:
                player.close_player()
            except Exception:
                pass
            with self._lock:
                if generation == self._generation:
                    self._running = False
