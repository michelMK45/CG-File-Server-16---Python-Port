"""Kit drawings for the Kits tab: a flat shirt + shorts + socks figure painted with
the real kit textures. Classic uses it for its combinations, Simple for the
selected kit set and Advanced for the mix being built (see kit_art_preview.py).

Ported from Dinei's Kit Mixer. Reads the .rx3 directly (no 32-bit FifaLibrary
bridge): the shirt is the largest square DXT1 texture of the file and shorts +
socks share the largest 2:1 DXT1 "atlas" (socks band on top, shorts below). A
source can also be a plain image file holding that same texture layout (the
Advanced tab's "Import image..."). Unlike his pure-Python DXT1 decoder, decoding
goes through Pillow by wrapping the raw texture data in a DDS header, and the
shape masks are drawn with Pillow too, so even the large zoom render is quick.
Kits whose textures aren't DXT1 (a handful of patch kits use 32-bit textures)
draw in grey.

Pure functions plus IconFactory; no Tk here, so rendering can run on a worker
thread and only the finished PNG is handed to the UI.
"""

from __future__ import annotations

import hashlib
import io
import struct
from collections import OrderedDict
from pathlib import Path
from typing import Callable, Optional

from PIL import Image, ImageDraw, ImageFilter

RX3_MAGIC = b"RX3l"
RX3_TYPE_TEXTURE = 0x7A0B60DA
RX3_TYPE_TABLE = 0x6BD085DC
FMT_DXT1 = 0

# Textures are downsampled by this factor before sampling: a 1024 px shirt becomes
# 256 px, plenty for thumbnails of a couple of hundred pixels. Drawings of at least
# FULL_TEXTURE_SIZE (the zoom dialog's) use the textures at full resolution.
TEXTURE_REDUCE = 4
FULL_TEXTURE_SIZE = 200
IMAGE_TEXTURE_MAX = 512   # imported image sources are shrunk to at most this width

ART_VERSION = 5   # bump when shapes/crops change: invalidates the disk cache

# Where each piece takes its colours from: name -> (texture, crop in fractions).
# "shirt" = shirt texture (1024x1024), "shorts"/"sock" = socks+shorts atlas (1024x512).
ART_REGIONS = {
    "body": ("shirt", (0.315, 0.50, 0.685, 0.90)),
    "hem": ("shirt", (0.315, 0.90, 0.685, 0.945)),
    "collar": ("shirt", (0.00, 0.955, 0.26, 1.00)),
    "sleeve": ("shirt", (0.222, 0.03, 0.362, 0.32)),
    "cuff": ("shirt", (0.190, 0.03, 0.218, 0.32)),
    "waist": ("shorts", (0.12, 0.372, 0.88, 0.452)),
    "shorts": ("shorts", (0.03, 0.47, 0.97, 0.95)),
    "sock": ("sock", (0.245, 0.19, 0.448, 0.36)),
    "sockcuff": ("sock", (0.200, 0.00, 0.243, 0.36)),
}


def _mirror(poly):
    return [(1.0 - x, y) for x, y in reversed(poly)]


_SLEEVE_L = [(0.30, 0.07), (0.21, 0.10), (0.10, 0.17), (0.155, 0.265), (0.30, 0.20)]
_CUFF_L = [(0.10, 0.17), (0.155, 0.265), (0.176, 0.247), (0.12, 0.155)]
_SOCK_L = [(0.325, 0.88), (0.465, 0.88), (0.465, 0.99), (0.325, 0.99)]
_SOCKCUFF_L = [(0.325, 0.88), (0.465, 0.88), (0.465, 0.91), (0.325, 0.91)]

# (name, region, polygon in 0..1 of the thumbnail, shading 0..1), drawn in order.
ART_SHAPES = [
    ("sock_l", "sock", _SOCK_L, 0.5),
    ("sock_r", "sock", _mirror(_SOCK_L), 0.5),
    ("sockcuff_l", "sockcuff", _SOCKCUFF_L, 0.2),
    ("sockcuff_r", "sockcuff", _mirror(_SOCKCUFF_L), 0.2),
    ("legs", "shorts", [(0.285, 0.615), (0.715, 0.615), (0.74, 0.82), (0.525, 0.82), (0.50, 0.71),
                        (0.475, 0.82), (0.26, 0.82)], 0.5),
    ("waist", "waist", [(0.285, 0.615), (0.715, 0.615), (0.72, 0.66), (0.28, 0.66)], 0.2),
    ("sleeve_l", "sleeve", _SLEEVE_L, 0.5),
    ("sleeve_r", "sleeve", _mirror(_SLEEVE_L), 0.5),
    ("cuff_l", "cuff", _CUFF_L, 0.2),
    ("cuff_r", "cuff", _mirror(_CUFF_L), 0.2),
    ("body", "body", [(0.30, 0.075), (0.42, 0.045), (0.58, 0.045), (0.70, 0.075), (0.705, 0.505),
                      (0.295, 0.505)], 0.5),
    ("hem", "hem", [(0.295, 0.505), (0.705, 0.505), (0.705, 0.55), (0.295, 0.55)], 0.2),
    ("collar", "collar", [(0.42, 0.045), (0.58, 0.045), (0.55, 0.095), (0.50, 0.13), (0.45, 0.095)], 0.1),
]
ART_ROW_AVG = ("sock", "sockcuff")   # socks: keep the horizontal stripes, drop the artwork
ART_ASPECT = 1.2                     # thumbnail height / width
ART_OUTLINE = (84, 86, 96)           # grey outline, readable on dark and light backgrounds
ART_MISSING = (96, 96, 96)


class Rx3Error(Exception):
    pass


class Tex:
    def __init__(self, index: int, fmt: int, w: int, h: int, mips: int, offset: int, size: int) -> None:
        self.index, self.fmt, self.w, self.h = index, fmt, w, h
        self.mips, self.offset, self.size = mips, offset, size


def parse_rx3(path: Path) -> list[Tex]:
    """Texture table of an .rx3, without reading the texture data."""
    with open(path, "rb") as f:
        head = f.read(16)
        if len(head) < 16 or head[:4] != RX3_MAGIC:
            raise Rx3Error("not an RX3 file")
        count = struct.unpack_from("<I", head, 12)[0]
        if not 0 < count <= 64:
            raise Rx3Error("unexpected RX3 header")
        entries = []
        for _ in range(count):
            raw = f.read(16)
            if len(raw) < 16:
                raise Rx3Error("truncated RX3 file")
            entries.append(struct.unpack("<IIII", raw))
        tables = [e for e in entries if e[0] == RX3_TYPE_TABLE]
        texs = [e for e in entries if e[0] == RX3_TYPE_TEXTURE]
        if not tables or not texs:
            raise Rx3Error("RX3 has no texture table")
        f.seek(tables[0][1])
        table = f.read(tables[0][2])
    n = struct.unpack_from("<I", table, 0)[0]
    out = []
    for i in range(min(n, len(texs))):
        d = table[0x10 + 16 * i: 0x20 + 16 * i]
        if len(d) < 16:
            break
        w, h = struct.unpack_from("<HH", d, 8)
        out.append(Tex(i, d[5], w, h, d[14], texs[i][1], texs[i][2]))
    return out


def pick_textures(texs: list[Tex]) -> tuple[Optional[Tex], Optional[Tex]]:
    """(shirt, socks+shorts atlas): the largest square and 2:1 DXT1 textures."""
    shirt = [t for t in texs if t.fmt == FMT_DXT1 and t.w == t.h]
    atlas = [t for t in texs if t.fmt == FMT_DXT1 and t.w == 2 * t.h]

    def area(t: Tex) -> int:
        return t.w * t.h

    return (max(shirt, key=area) if shirt else None, max(atlas, key=area) if atlas else None)


def _dxt1_dds_header(w: int, h: int) -> bytes:
    pixel_format = struct.pack("<II4sIIIII", 32, 4, b"DXT1", 0, 0, 0, 0, 0)
    flags = 0x1 | 0x2 | 0x4 | 0x1000 | 0x80000   # CAPS | HEIGHT | WIDTH | PIXELFORMAT | LINEARSIZE
    return (struct.pack("<4sIIIIIII", b"DDS ", 124, flags, h, w, w * h // 2, 0, 1)
            + b"\0" * 44 + pixel_format + struct.pack("<IIIII", 0x1000, 0, 0, 0, 0))


def _decode_rows(path: Path, tex: Tex, reduce: int = TEXTURE_REDUCE) -> list[bytes]:
    with open(path, "rb") as f:
        f.seek(tex.offset)
        data = f.read(tex.w * tex.h // 2)
    if len(data) < tex.w * tex.h // 2:
        raise Rx3Error("texture data shorter than expected")
    image = Image.open(io.BytesIO(_dxt1_dds_header(tex.w, tex.h) + data)).convert("RGB")
    if reduce > 1 and image.width >= 4 * reduce:
        image = image.reduce(reduce)
    return _image_rows(image)


def _image_rows(image: Image.Image) -> list[bytes]:
    raw = image.tobytes()
    stride = image.width * 3
    return [raw[y * stride:(y + 1) * stride] for y in range(image.height)]


def load_image_texture_rows(path: Path, max_width: int = IMAGE_TEXTURE_MAX) -> list[bytes]:
    """A plain image file used as the texture itself (same layout as the .rx3's)."""
    with Image.open(path) as image:
        image = image.convert("RGB")
    if image.width > max_width:
        image = image.resize((max_width, max(1, round(image.height * max_width / image.width))), Image.BOX)
    return _image_rows(image)


def load_shirt_rows(path: Path, reduce: int = TEXTURE_REDUCE) -> Optional[list[bytes]]:
    if Path(path).suffix.lower() != ".rx3":
        return load_image_texture_rows(path, IMAGE_TEXTURE_MAX * 4 // reduce)
    shirt, _ = pick_textures(parse_rx3(path))
    return _decode_rows(path, shirt, reduce) if shirt else None


def load_atlas_rows(path: Path, reduce: int = TEXTURE_REDUCE) -> Optional[list[bytes]]:
    if Path(path).suffix.lower() != ".rx3":
        return load_image_texture_rows(path, IMAGE_TEXTURE_MAX * 4 // reduce)
    _, atlas = pick_textures(parse_rx3(path))
    return _decode_rows(path, atlas, reduce) if atlas else None


# ---------------------------------------------------------------------------
# Drawing
# ---------------------------------------------------------------------------

_COVERAGE_CACHE: dict = {}


def _mask(poly, w: int, h: int, ss: int = 4) -> Image.Image:
    """Antialiased coverage mask ("L", 0..255) of a polygon given in 0..1 fractions:
    drawn ss times larger and box-filtered down."""
    big = Image.new("L", (w * ss, h * ss), 0)
    ImageDraw.Draw(big).polygon([(x * w * ss, y * h * ss) for x, y in poly], fill=255)
    return big.resize((w, h), Image.BOX)


def _as_rows(mask: Image.Image) -> list[list[float]]:
    data = mask.tobytes()
    w = mask.width
    return [[v / 255.0 for v in data[y * w:(y + 1) * w]] for y in range(mask.height)]


def _shape_masks(w: int, h: int):
    key = (ART_VERSION, w, h)
    if key not in _COVERAGE_CACHE:
        out = []
        for name, region, poly, shade in ART_SHAPES:
            mask = _mask(poly, w, h)
            bbox = mask.getbbox()
            if bbox is None:
                continue
            # The dilated mask is the 1 px outline drawn under each piece.
            out.append((name, region, shade, _as_rows(mask), _as_rows(mask.filter(ImageFilter.MaxFilter(3))), bbox))
        _COVERAGE_CACHE[key] = out
    return _COVERAGE_CACHE[key]


def _sample_crop(rows: list[bytes], crop, outw: int, outh: int) -> list[list[tuple[int, int, int]]]:
    """Shrink the `crop` (fractions) of `rows` to outw x outh by averaging samples."""
    sh = len(rows)
    sw = len(rows[0]) // 3
    x0, y0, x1, y1 = crop
    px0, py0, px1, py1 = x0 * sw, y0 * sh, x1 * sw, y1 * sh
    out = []
    for j in range(outh):
        ya = py0 + (py1 - py0) * j / outh
        yb = py0 + (py1 - py0) * (j + 1) / outh
        ys = sorted({min(sh - 1, max(0, int(ya + (yb - ya) * t))) for t in (0.1, 0.37, 0.63, 0.9)})
        line = []
        for i in range(outw):
            xa = px0 + (px1 - px0) * i / outw
            xb = px0 + (px1 - px0) * (i + 1) / outw
            xs = sorted({min(sw - 1, max(0, int(xa + (xb - xa) * t))) for t in (0.1, 0.37, 0.63, 0.9)})
            r = g = b = n = 0
            for yy in ys:
                row = rows[yy]
                for xx in xs:
                    o = xx * 3
                    r += row[o]
                    g += row[o + 1]
                    b += row[o + 2]
                    n += 1
            line.append((r // n, g // n, b // n))
        out.append(line)
    return out


def _blend(row: bytearray, x: int, rgb, a: float) -> None:
    if a <= 0:
        return
    o = x * 4
    ba = row[o + 3] / 255.0
    oa = a + ba * (1.0 - a)
    for i in range(3):
        row[o + i] = int((rgb[i] * a + row[o + i] * ba * (1.0 - a)) / oa + 0.5)
    row[o + 3] = int(oa * 255 + 0.5)


def art_size(size: int = 56) -> tuple[int, int]:
    """(width, height) in pixels of a thumbnail of nominal `size`."""
    w = max(24, int(round(size * 1.2)))
    return w, int(round(w * ART_ASPECT))


def make_kit_icon(shirt_rows, shorts_atlas_rows, socks_atlas_rows, size: int = 56) -> Image.Image:
    """RGBA thumbnail (transparent background): shirt, shorts and socks painted with
    the given textures, thin outline and a little volume shading. A None texture
    paints that piece grey."""
    w, h = art_size(size)
    rows = [bytearray(w * 4) for _ in range(h)]
    src = {"shirt": shirt_rows, "shorts": shorts_atlas_rows, "sock": socks_atlas_rows}
    for _name, region, shade, cov, dil, (bx0, by0, bx1, by1) in _shape_masks(w, h):
        tex_name, crop = ART_REGIONS[region]
        tex = src[tex_name]
        bw, bh = bx1 - bx0, by1 - by0
        colors = _sample_crop(tex, crop, bw, bh) if tex is not None else None
        if colors is not None and region in ART_ROW_AVG:
            colors = [[tuple(sum(c[i] for c in line) // len(line) for i in range(3))] * len(line) for line in colors]
        for y in range(max(0, by0 - 1), min(h, by1 + 1)):
            drow = rows[y]
            for x in range(max(0, bx0 - 1), min(w, bx1 + 1)):
                a = dil[y][x]
                if a > 0:
                    _blend(drow, x, ART_OUTLINE, a * 0.9)
        cx = (bx0 + bx1) / 2.0
        half = max(1.0, (bx1 - bx0) / 2.0)
        for y in range(by0, by1):
            crow = cov[y]
            drow = rows[y]
            dy = (y - by0) / float(max(1, bh))
            for x in range(bx0, bx1):
                a = crow[x]
                if a <= 0:
                    continue
                r, g, b = colors[y - by0][x - bx0] if colors is not None else ART_MISSING
                dx = (x + 0.5 - cx) / half
                f = 1.04 - shade * (0.16 * dx * dx + 0.05 * dy)
                _blend(drow, x, (min(255, int(r * f)), min(255, int(g * f)), min(255, int(b * f))), a)
    return Image.frombytes("RGBA", (w, h), b"".join(bytes(r) for r in rows))


class IconFactory:
    """Renders (and caches on disk) kit drawings.

    render_png(shirt, shorts, socks, size) takes the three texture sources as file
    paths (.rx3 or image, None = grey); icon_png(team, tourn, shirt, shorts, socks)
    is the Classic shortcut that resolves kit types through `kit_path(team, tourn,
    ktype) -> Path | None`. Not thread-safe: callers serialize with one lock
    (KitClassicRuntime.art_lock)."""

    def __init__(self, kit_path: Callable[[int, int, int], Optional[Path]], cache_dir: Optional[Path]) -> None:
        self.kit_path = kit_path
        self.cache_dir = cache_dir
        self._textures: OrderedDict = OrderedDict()

    def _rows(self, path: Optional[Path], kind: str, reduce: int = TEXTURE_REDUCE):
        if path is None:
            return None
        try:
            mtime = Path(path).stat().st_mtime
        except OSError:
            return None
        key = (str(path), mtime, kind, reduce)
        if key in self._textures:
            self._textures.move_to_end(key)
            return self._textures[key]
        try:
            rows = load_shirt_rows(path, reduce) if kind == "shirt" else load_atlas_rows(path, reduce)
        except Exception:  # noqa: BLE001 - unreadable/odd kit file: draw grey
            rows = None
        self._textures[key] = rows
        while len(self._textures) > 16:
            self._textures.popitem(last=False)
        return rows

    def icon_png(self, team: int, tourn: int, shirt: int, shorts: int, socks: int, size: int = 56) -> bytes:
        return self.render_png(*(self.kit_path(team, tourn, k) for k in (shirt, shorts, socks)), size=size)

    def render_png(self, shirt: Optional[Path], shorts: Optional[Path], socks: Optional[Path], size: int = 56) -> bytes:
        paths = [Path(p) if p is not None else None for p in (shirt, shorts, socks)]

        def stamp(p: Optional[Path]):
            try:
                return str(p), p.stat().st_mtime if p is not None else 0
            except OSError:
                return str(p), 0

        sig = hashlib.md5(repr((ART_VERSION, size, [stamp(p) for p in paths])).encode("utf-8", "replace")).hexdigest()
        cache = None
        if self.cache_dir is not None:
            cache = self.cache_dir / f"kit_v{ART_VERSION}_{size}_{sig[:16]}.png"
            try:
                return cache.read_bytes()
            except OSError:
                pass
        reduce = 1 if size >= FULL_TEXTURE_SIZE else TEXTURE_REDUCE
        image = make_kit_icon(self._rows(paths[0], "shirt", reduce), self._rows(paths[1], "atlas", reduce),
                              self._rows(paths[2], "atlas", reduce), size)
        buf = io.BytesIO()
        image.save(buf, "PNG")
        png = buf.getvalue()
        if cache is not None:
            try:
                cache.parent.mkdir(parents=True, exist_ok=True)
                tmp = cache.with_name(cache.name + ".tmp")
                tmp.write_bytes(png)
                tmp.replace(cache)
            except OSError:
                pass
        return png
