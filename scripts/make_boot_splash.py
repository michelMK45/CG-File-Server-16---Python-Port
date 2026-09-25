"""Renders the static image shown by PyInstaller's bootloader splash.

A onefile exe spends its first seconds unpacking itself, before any Python
runs -- so server16_py/splash.py cannot cover that stretch. PyInstaller can
show an image from the bootloader instead (Splash in Server16Python.spec).
This draws it with the same geometry as the live splash (compute_layout), minus
the spinner's moving tail and the status message, so when the live splash
takes over it reads as the spinner starting to turn rather than a new window.

The bootloader process is DPI-unaware (the exe's manifest declares none), so
Windows stretches this image by the display scale -- exactly what
compute_layout(scale) does for the live splash -- hence it is drawn at 100%.

Run by the spec at build time (so the version number is never stale); also
runnable by hand: python scripts/make_boot_splash.py [out.png]
"""
from __future__ import annotations

import io
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from server16_py import splash  # noqa: E402

_SUPERSAMPLE = 4
# PIL and Tk center a line of text a little differently; measured against the
# real exe, the live splash's title sits ~2 logical px lower than PIL's "lm"
# anchor puts it, which was a visible hop at the handoff.
_TITLE_NUDGE = 2
_FONT_CANDIDATES = ("bahnschrift.ttf", "segoeui.ttf", "arial.ttf")


def _font(size_px: int, bold: bool) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    fonts_dir = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    for name in _FONT_CANDIDATES:
        path = fonts_dir / name
        if not path.is_file():
            continue
        font = ImageFont.truetype(str(path), size_px)
        if bold:
            try:
                font.set_variation_by_name("Bold")
            except Exception:
                pass
        return font
    return ImageFont.load_default()


def render(out_path: str | os.PathLike, scale: float = 1.0) -> Path:
    layout = splash.compute_layout(scale)
    ss = _SUPERSAMPLE
    image = Image.new("RGB", (layout.width * ss, layout.height * ss), splash.PANEL)
    draw = ImageDraw.Draw(image)
    draw.rectangle(
        [0, 0, layout.width * ss - 1, layout.height * ss - 1], outline=splash.BORDER, width=ss,
    )

    draw.text(
        (layout.text_x * ss, (layout.title_y + round(_TITLE_NUDGE * scale)) * ss), splash.TITLE, fill=splash.FG,
        font=_font(layout.title_px * ss, bold=True), anchor="lm",
    )
    draw.text(
        (layout.text_x * ss, layout.subtitle_y * ss), f"v{splash.__version__}", fill=splash.MUTED,
        font=_font(layout.subtitle_px * ss, bold=False), anchor="lm",
    )

    # Tk strokes the ring centered on its path; PIL strokes inward from the
    # bounding box, so grow the box by half the stroke.
    half = layout.ring_width * ss / 2
    radius = layout.spin_r * ss
    cx, cy = layout.spin_cx * ss, layout.spin_cy * ss
    draw.arc(
        [cx - radius - half, cy - radius - half, cx + radius + half, cy + radius + half],
        0, 360, fill=splash.TRACK, width=layout.ring_width * ss,
    )

    image = image.resize((layout.width, layout.height), Image.LANCZOS)

    png = splash.icon_png(splash.find_icon_path(), layout.icon_px)
    if png is not None:
        icon = Image.open(io.BytesIO(png)).convert("RGBA")
        image.paste(icon, (layout.icon_x, layout.icon_y), icon)

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    image.save(out, "PNG")
    return out


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else str(REPO / "build" / "boot_splash.png")
    print(render(target))
