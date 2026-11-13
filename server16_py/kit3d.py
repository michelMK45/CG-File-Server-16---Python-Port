"""3D kit preview: the FIFA 16 body models (shirt, shorts, socks) textured with the kit
and drawn by a small software rasteriser (pure Python + Pillow, no numpy).

The three garments are rendered as separate transparent layers over one shared camera,
so stacking them (socks, shorts, shirt) gives the whole figure and the F12 overlay can
still load them one by one. The socks are moved up and apart (as in the flat drawing)
so the figure fits the thumbnail's shape."""

from __future__ import annotations

import base64
import math
import struct
import zlib
from functools import lru_cache

from PIL import Image, ImageFilter

try:
    from .kit3d_meshes import BOUNDS_JERSEY, MESHES
except ImportError:  # standalone use
    from kit3d_meshes import BOUNDS_JERSEY, MESHES

SOCK_SPREAD = 17.0    # each sock moves this far outwards (model units, ~cm)
SOCK_LIFT = 30.0      # ...and up
LIGHT = (-0.35, 0.45, 0.82)
AMBIENT = 0.58
GAIN = 1.12
OUTLINE = (84, 86, 96)
LAYER_MESH = {"socks": "sock", "shorts": "shorts", "shirt": "jersey0"}


COLLARS = 22          # collar models 0..21 (teamkits.jerseycollargeometrytype)


def jersey_key(collar) -> str:
    try:
        collar = int(collar)
    except (TypeError, ValueError):
        collar = 0
    return "jersey%d" % (collar if 0 <= collar < COLLARS else 0)


@lru_cache(maxsize=None)
def _mesh(key: str):
    raw = zlib.decompress(base64.b64decode("".join(MESHES[key])))
    nv, ni = struct.unpack_from("<II", raw, 0)
    o = 8
    pos = struct.unpack_from("<%dh" % (3 * nv), raw, o); o += 6 * nv
    nor = struct.unpack_from("<%db" % (3 * nv), raw, o); o += 3 * nv
    uv = struct.unpack_from("<%dH" % (2 * nv), raw, o); o += 4 * nv
    idx = struct.unpack_from("<%dH" % ni, raw, o)
    verts = []
    for i in range(nv):
        x, y, z = pos[3 * i] / 100.0, pos[3 * i + 1] / 100.0, pos[3 * i + 2] / 100.0
        if key == "sock":
            sgn = 1.0 if x >= 0 else -1.0
            x += sgn * SOCK_SPREAD
            y += SOCK_LIFT
        verts.append(((x, y, z), (nor[3 * i] / 127.0, nor[3 * i + 1] / 127.0, nor[3 * i + 2] / 127.0),
                      (uv[2 * i] / 65535.0, uv[2 * i + 1] / 65535.0)))
    return verts, idx


@lru_cache(maxsize=None)
def _bounds():
    x0, x1, y0, y1 = BOUNDS_JERSEY
    for key in ("shorts", "sock"):
        for p, _n, _u in _mesh(key)[0]:
            x0 = min(x0, p[0]); x1 = max(x1, p[0]); y0 = min(y0, p[1]); y1 = max(y1, p[1])
    return x0, x1, y0, y1


JERSEY_U_SHIFT = 0.012   # kit makers centre the shirt art a hair right of u=0.5: sample that much to the right
# The two sock panels of the shorts+socks atlas mirror each other around u=0.5145 (measured on 102 FIP kits
# with patterned socks, 87 of them exactly there), but the sock mesh is mirrored around 0.5: unshifted, the
# left sock missed its top band and showed the ankle band instead. Shifted, both tops sit on the panels'
# inner edges (0.503 / 0.527).
SOCK_U_SHIFT = 0.0145
NECK_Y = 148.0   # the inside back of the neck: vertices above this height ...
NECK_V = (0.40, 0.52)   # ... whose texture row ...
NECK_U = (0.30, 0.70)   # ... and column fall in the lining area of the texture


LINING_SHADE = 0.86  # otherwise the inside of the neck is the shirt colour, a little darker


def _lining_colour(tex: Image.Image):
    """Main colour of the shirt (median of the front torso). The texture's own neck lining is
    filler of every sort (grey, black, half red/half white) and drawn as it is it looked like
    a tube standing in the neck, so the inside of the neck is painted with the shirt colour."""
    tw, th = tex.size
    body = tex.convert("RGB").crop((int(0.38 * tw), int(0.60 * th), int(0.62 * tw), int(0.88 * th))).resize((16, 16))
    data = list(body.getdata())
    return tuple(sorted(c[i] for c in data)[len(data) // 2] for i in range(3))


def _render(key, tex: Image.Image, W: int, H: int):
    verts, idx = _mesh(key)
    x0b, x1b, y0b, y1b = _bounds()
    sc = min(W * 0.97 / (x1b - x0b), H * 0.97 / (y1b - y0b))
    cx, cy = W / 2.0 - (x0b + x1b) / 2.0 * sc, H / 2.0 + (y0b + y1b) / 2.0 * sc
    lx, ly, lz = LIGHT
    ln = math.sqrt(lx * lx + ly * ly + lz * lz); lx, ly, lz = lx / ln, ly / ln, lz / ln
    tw, th = tex.size
    tpx = tex.convert("RGB").tobytes()
    lining = _lining_colour(tex) if key.startswith("jersey") else None
    pv = []
    for p, n, uv in verts:
        u_ = uv[0]
        if key.startswith("jersey"):
            u_ += JERSEY_U_SHIFT
        elif key == "sock":
            u_ += SOCK_U_SHIFT
        lam = n[0] * lx + n[1] * ly + n[2] * lz
        sh = (AMBIENT + (1 - AMBIENT) * (lam if lam > 0 else 0.0)) * GAIN
        is_lining = 1.0 if (lining is not None and p[1] > NECK_Y and NECK_V[0] <= uv[1] < NECK_V[1]
                            and NECK_U[0] <= uv[0] <= NECK_U[1]) else 0.0
        pv.append((cx + p[0] * sc, cy - p[1] * sc, -p[2], sh, u_ * (tw - 1), uv[1] * (th - 1), is_lining))
    zbuf = [1e30] * (W * H)
    out = bytearray(W * H * 4)
    for t in range(0, len(idx), 3):
        a, b, c = pv[idx[t]], pv[idx[t + 1]], pv[idx[t + 2]]
        x0, y0, x1, y1, x2, y2 = a[0], a[1], b[0], b[1], c[0], c[1]
        den = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
        if abs(den) < 1e-9:
            continue
        inv = 1.0 / den
        minx = max(0, int(min(x0, x1, x2))); maxx = min(W - 1, int(max(x0, x1, x2)) + 1)
        miny = max(0, int(min(y0, y1, y2))); maxy = min(H - 1, int(max(y0, y1, y2)) + 1)
        for yy in range(miny, maxy + 1):
            py = yy + 0.5
            row = yy * W
            for xx in range(minx, maxx + 1):
                px = xx + 0.5
                l0 = ((y1 - y2) * (px - x2) + (x2 - x1) * (py - y2)) * inv
                if l0 < -1e-4:
                    continue
                l1 = ((y2 - y0) * (px - x2) + (x0 - x2) * (py - y2)) * inv
                if l1 < -1e-4:
                    continue
                l2 = 1.0 - l0 - l1
                if l2 < -1e-4:
                    continue
                k = row + xx
                z = l0 * a[2] + l1 * b[2] + l2 * c[2]
                if z >= zbuf[k]:
                    continue
                zbuf[k] = z
                iu = int(l0 * a[4] + l1 * b[4] + l2 * c[4] + 0.5)
                iv = int(l0 * a[5] + l1 * b[5] + l2 * c[5] + 0.5)
                iu = 0 if iu < 0 else (tw - 1 if iu >= tw else iu)
                iv = 0 if iv < 0 else (th - 1 if iv >= th else iv)
                sh = l0 * a[3] + l1 * b[3] + l2 * c[3]
                o = (iv * tw + iu) * 3
                q = k * 4
                if lining is not None and l0 * a[6] + l1 * b[6] + l2 * c[6] > 0.5:
                    sh *= LINING_SHADE
                    r_ = int(lining[0] * sh); g_ = int(lining[1] * sh); b_ = int(lining[2] * sh)
                else:
                    r_ = int(tpx[o] * sh); g_ = int(tpx[o + 1] * sh); b_ = int(tpx[o + 2] * sh)
                out[q] = 255 if r_ > 255 else r_
                out[q + 1] = 255 if g_ > 255 else g_
                out[q + 2] = 255 if b_ > 255 else b_
                out[q + 3] = 255
    return Image.frombytes("RGBA", (W, H), bytes(out))


def _grey(w: int, h: int) -> Image.Image:
    return Image.new("RGB", (w, h), (96, 96, 96))


def render_layer(layer: str, texture: Image.Image | None, w: int, h: int, ss: int = 3, collar: int = 0) -> Image.Image:
    """One garment (`layer`: socks/shorts/shirt) as an RGBA image of w x h pixels."""
    tex = texture if texture is not None else _grey(8, 8)
    key = jersey_key(collar) if layer == "shirt" else LAYER_MESH[layer]
    big = _render(key, tex, w * ss, h * ss)
    # soft edges: average colour weighted by alpha, then a thin outline underneath
    alpha = big.getchannel("A")
    rgb = Image.merge("RGB", [big.getchannel(i) for i in range(3)])
    if ss > 1:
        a_small = alpha.resize((w, h), Image.BOX)
        # premultiply so transparent black doesn't darken the edge
        pre = Image.merge("RGB", [Image.composite(rgb.getchannel(i), Image.new("L", rgb.size, 0), alpha) for i in range(3)])
        pre = pre.resize((w, h), Image.BOX)
        ab = list(a_small.getdata())
        chans = [list(pre.getchannel(i).getdata()) for i in range(3)]
        data = bytearray(w * h * 4)
        for i, a in enumerate(ab):
            if a:
                f = 255.0 / a
                data[4 * i] = min(255, int(chans[0][i] * f + 0.5))
                data[4 * i + 1] = min(255, int(chans[1][i] * f + 0.5))
                data[4 * i + 2] = min(255, int(chans[2][i] * f + 0.5))
                data[4 * i + 3] = a
        img = Image.frombytes("RGBA", (w, h), bytes(data))
    else:
        img = big
    halo = img.getchannel("A").filter(ImageFilter.MaxFilter(3))
    edge = Image.new("RGBA", (w, h), OUTLINE + (255,))
    edge.putalpha(halo.point(lambda v: int(v * 0.9)))
    edge.alpha_composite(img)
    return edge
