"""Stadium previews for the in-game CGFS16 menu (cgfs-ingame project, docs/ingame-menu.md).

The menu shows an image per value with FIFA 16's own ImageLoader, which loads .dds files relative to
data/ui (as FIFA's hub tiles). Stadium packs bring a JPG/PNG preview (StadiumGBD/render/thumbnail/stadium/,
resolved by the app's _resolve_stadium_preview_path); this module turns them into uncompressed 32-bit DDS
(a format FIFA 16's UI loads, checked with the menu's own logo) under data/ui/cgfs16/img/std/, named by a hash of
the stadium name (ASCII-only paths for the movie's loadMovie). Made once and reused while the source is not
newer; ~230 KB each at 320x180.
"""
from __future__ import annotations

import hashlib
import struct
from pathlib import Path

from PIL import Image, ImageOps

IMAGE_DIR = Path("data/ui/cgfs16/img/std")   # under the game folder
SIZE = (320, 180)                             # the menu's image area (top right, like FIFA's Game Settings)


PLACEHOLDER_REL = "cgfs16/img/std/placeholder.dds"   # the app's stadium-placeholder.png, for stadiums without one


MOVIE_PLACEHOLDER_REL = "cgfs16/img/mov/placeholder.dds"   # the app's movie-placeholder.png
MOVIE_DIR = Path("data/ui/cgfs16/mov")


def ensure_placeholder(exedir: str | Path, source: Path, rel: str = PLACEHOLDER_REL) -> bool:
    """A placeholder's DDS (the stadium one by default); True if it was (re)made."""
    target = Path(exedir) / "data" / "ui" / rel
    if target.exists() and target.stat().st_mtime >= Path(source).stat().st_mtime:
        return False
    make_preview(Path(source), target)
    return True


def stadium_image_rel(name: str) -> str:
    """The menu's path for a stadium's preview (relative to data/ui, what ImageLoader gets)."""
    return "cgfs16/img/std/" + hashlib.sha1(name.encode("utf-8")).hexdigest()[:16] + ".dds"


def stadium_image_file(exedir: str | Path, name: str) -> Path:
    return Path(exedir) / "data" / "ui" / stadium_image_rel(name)


def dds_a8r8g8b8(img: Image.Image) -> bytes:
    """DDS bytes, uncompressed 32-bit BGRA, no mipmaps (same writer as cgfs-ingame's tileimage.py)."""
    img = img.convert("RGBA")
    w, h = img.size
    flags = 0x1 | 0x2 | 0x4 | 0x8 | 0x1000                     # CAPS, HEIGHT, WIDTH, PITCH, PIXELFORMAT
    pf = struct.pack("<II4sIIIII", 32, 0x1 | 0x40, b"\0\0\0\0", 32,   # ALPHAPIXELS | RGB
                     0x00FF0000, 0x0000FF00, 0x000000FF, 0xFF000000)
    header = struct.pack("<I", 124) + struct.pack("<IIIIII", flags, h, w, w * 4, 0, 0) + bytes(44)
    header += pf + struct.pack("<IIIII", 0x1000, 0, 0, 0, 0)       # DDSCAPS_TEXTURE
    r, g, b, a = img.split()
    return b"DDS " + header + Image.merge("RGBA", (b, g, r, a)).tobytes()


def make_preview(source: Path, target: Path) -> None:
    with Image.open(source) as image:
        picture = ImageOps.fit(image.convert("RGB"), SIZE, Image.LANCZOS)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".tmp")
    tmp.write_bytes(dds_a8r8g8b8(picture))
    tmp.replace(target)  # never a half-written file for FIFA to load


def ensure_stadium_images(exedir: str | Path, names: list[str], resolve) -> tuple[int, int]:
    """Makes the missing/outdated previews. resolve(name) -> the pack's preview image Path or None.
    Returns (made, available). Runs in a worker thread: no Tk, no settings."""
    made = available = 0
    for name in names:
        source = resolve(name)
        if source is None:
            continue
        target = stadium_image_file(exedir, name)
        try:
            if not target.exists() or target.stat().st_mtime < Path(source).stat().st_mtime:
                make_preview(Path(source), target)
                made += 1
            available += 1
        except Exception:  # noqa: BLE001 - a broken preview only means no image for that stadium
            continue
    return made, available


# --- the stadium options' pictures (pitch mow pattern, net colour: FSW/Images/<kind folder>/<n>.png) --------

def asset_image_rel(kind: str, stem: str) -> str:
    """The menu's path for a picture of a stadium option value ("pitch"/"net" + the file's stem)."""
    return f"cgfs16/img/{kind}/" + hashlib.sha1(stem.encode("utf-8")).hexdigest()[:16] + ".dds"


def asset_image_file(exedir: str | Path, kind: str, stem: str) -> Path:
    return Path(exedir) / "data" / "ui" / asset_image_rel(kind, stem)


def make_contained(source: Path, target: Path) -> None:
    """The whole picture inside SIZE, centred on transparency (a 1024x2048 mow pattern, a 128x128 net)."""
    with Image.open(source) as image:
        picture = ImageOps.contain(image.convert("RGBA"), SIZE, Image.LANCZOS)
    canvas = Image.new("RGBA", SIZE, (0, 0, 0, 0))
    canvas.alpha_composite(picture, ((SIZE[0] - picture.width) // 2, (SIZE[1] - picture.height) // 2))
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".tmp")
    tmp.write_bytes(dds_a8r8g8b8(canvas))
    tmp.replace(target)


def ensure_asset_images(exedir: str | Path, assets: list[tuple[str, str, Path]]) -> tuple[int, int]:
    """[(kind, stem, source picture)] -> (made, available), as ensure_stadium_images."""
    made = available = 0
    for kind, stem, source in assets:
        target = asset_image_file(exedir, kind, stem)
        try:
            if not target.exists() or target.stat().st_mtime < Path(source).stat().st_mtime:
                make_contained(Path(source), target)
                made += 1
            available += 1
        except Exception:  # noqa: BLE001
            continue
    return made, available


# --- movie previews: the packs' bootflowoutro.vp8, where the menu's MoviePlayer can play them -----------------

def movie_video_file(exedir: str | Path, name: str) -> Path:
    return Path(exedir) / MOVIE_DIR / (hashlib.sha1(name.encode("utf-8")).hexdigest()[:16] + ".vp8")


def movie_video_play_path(name: str) -> str:
    """What MoviePlayer.Play gets: relative to the game folder with backslashes, as FIFA's own
    'data\\ui\\external\\ion_fut\\artAssets\\movies\\futIntroVideo.vp8'."""
    return "data\\ui\\cgfs16\\mov\\" + hashlib.sha1(name.encode("utf-8")).hexdigest()[:16] + ".vp8"


def ensure_movie_videos(exedir: str | Path, videos: list[tuple[str, Path]]) -> tuple[int, int]:
    """[(pack name, its .vp8)] -> (made, available): a hard link (no extra disk space; same volume as the
    game) or, if that fails, a copy, redone when the source changed (size or modification time)."""
    import os
    import shutil
    made = available = 0
    for name, source in videos:
        target = movie_video_file(exedir, name)
        try:
            src = Path(source).stat()
            if target.exists():
                dst = target.stat()
                if dst.st_size == src.st_size and int(dst.st_mtime) == int(src.st_mtime):
                    available += 1
                    continue
                target.unlink()
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.link(source, target)
            except OSError:
                shutil.copy2(source, target)
            made += 1
            available += 1
        except Exception:  # noqa: BLE001 - no preview for that pack
            continue
    return made, available
