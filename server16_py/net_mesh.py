"""Goal net mesh packs ([stadiumnetmesh], FSW/NetMesh/<name>/).

The pattern of the goal net (square, hexagonal, small/large holes) is not
geometry: it is the "goalnet_cm" texture (color + alpha, the alpha cutting the
holes) and its "goalnet_nm" normal map inside data/sceneassets/goalnet/
goalnet_{netID}.rx3. Vanilla ships goalnet_0.rx3 (square) and goalnet_1.rx3
(hexagonal), each holding four textures in this order:

    0 goalborder_cm 128x128   1 goalnet_cm 256x256
    2 goalrope_cm    64x128   3 goalnet_nm 256x256

goalnet.lua's GetRMNetShape() checks specificgoalnet_0_{stadiumID}.rx3 before
goalnet_{netID}.rx3, so a pack is installed under that slot-specific name
(stadiumID being the 176/261 injection slot) exactly like the goalpost packs,
and the net changes regardless of which netID the stadium uses.

A pack folder holds either a ready-made goalnet .rx3 (installed as-is), or a
loose pattern image: net.png (any other single image works too) plus an
optional net_nm.png normal map, generated from the pattern's alpha when absent.
Images are turned into an .rx3 by the 32-bit net_mesh_worker.py (FifaLibrary's
Rx3File.ReplaceBitmap over the vanilla goalnet_0.rx3), cached under runtime/.
"""
from __future__ import annotations

import json
import struct
import zlib
from pathlib import Path
from typing import Callable

from PIL import Image, ImageFilter

NET_MESH_TEXTURE_COUNT = 4
GOALNET_CM_INDEX = 1
GOALNET_NM_INDEX = 3
NET_MESH_IMAGE_SUFFIXES = (".png", ".bmp", ".jpg", ".jpeg")
NET_MESH_TEMPLATE_NAME = "goalnet_0.rx3"
_DIFFUSE_NAME = "net"
_NORMAL_STEMS = ("net_nm", "normal")
_PREVIEW_STEM = "preview"
_BUILT_NAME = "goalnet.rx3"
_STAMP_NAME = "source.json"


def slot_net_mesh_name(stadium_id: str) -> str:
    """The name goalnet.lua's GetRMNetShape() checks first for injection slot stadium_id."""
    return f"specificgoalnet_0_{stadium_id}.rx3"


def decompress_chunkzip(data: bytes) -> bytes:
    """Undo EA's "chunkzip" container (every vanilla .rx3 extracted from the .big
    archives uses it; FifaLibrary's Rx3File.Load() rejects it). Layout, big-endian:
    "chunkzip", version, total size, chunk size, chunk count, alignment, 0 -- then
    per chunk a (compressed size, type) pair placed so the payload that follows it
    starts on an `alignment` boundary; type 1 is raw deflate, anything else is
    stored. Data that isn't chunkzip is returned unchanged."""
    if not data.startswith(b"chunkzip"):
        return data
    _version, total, _chunk_size, count, align = struct.unpack_from(">IIIII", data, 8)
    align = max(1, align)
    offset = 0x20
    out = bytearray()
    for _ in range(count):
        offset = -(-(offset + 8) // align) * align - 8
        size, kind = struct.unpack_from(">II", data, offset)
        offset += 8
        payload = data[offset:offset + size]
        offset += size
        out += zlib.decompress(payload, -15) if kind == 1 else payload
    if len(out) != total:
        raise ValueError(f"chunkzip: expected {total} bytes, got {len(out)}")
    return bytes(out)


def _images(folder: Path) -> list[Path]:
    return sorted(
        (p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in NET_MESH_IMAGE_SUFFIXES),
        key=lambda p: p.name.lower(),
    )


def resolve_net_mesh_rx3(pack_dir: Path) -> Path | None:
    """A ready-made goalnet .rx3 shipped in the pack, used as-is."""
    if not pack_dir.is_dir():
        return None
    candidates = sorted(pack_dir.glob("*.rx3"), key=lambda p: p.name.lower())
    return candidates[0] if candidates else None


def resolve_net_mesh_images(pack_dir: Path) -> tuple[Path | None, Path | None]:
    """(pattern image, normal map image or None). The pattern is net.<ext>, or else
    the only image that is neither the normal map nor preview.<ext>."""
    if not pack_dir.is_dir():
        return None, None
    images = _images(pack_dir)
    normal = next((p for p in images if p.stem.lower() in _NORMAL_STEMS), None)
    diffuse = next((p for p in images if p.stem.lower() == _DIFFUSE_NAME), None)
    if diffuse is None:
        rest = [p for p in images if p != normal and p.stem.lower() != _PREVIEW_STEM]
        diffuse = rest[0] if len(rest) == 1 else None
    return diffuse, normal


def resolve_net_mesh_preview_path(net_mesh_dir: str | Path, name: str) -> Path | None:
    """preview.<ext> if the pack has one, else its pattern image (the most faithful
    preview there is). None for "None", a missing pack, or an .rx3-only pack."""
    name = (name or "").strip()
    if not name or name == "None":
        return None
    folder = Path(net_mesh_dir) / name
    if not folder.is_dir():
        return None
    preview = next((p for p in _images(folder) if p.stem.lower() == _PREVIEW_STEM), None)
    return preview or resolve_net_mesh_images(folder)[0]


def pack_has_net_mesh(pack_dir: Path) -> bool:
    return resolve_net_mesh_rx3(pack_dir) is not None or resolve_net_mesh_images(pack_dir)[0] is not None


def generate_normal_map(pattern: Path, output: Path, strength: float = 1.0) -> Path:
    """A tangent-space normal map from the pattern's alpha, treating the strands as
    raised: Sobel gradients of the softened alpha in R/G around 128, B fixed at 255
    (the vanilla goalnet_nm keeps B at 255 too). Without it the vanilla normal map
    would keep shading the old pattern's strands across the new holes."""
    with Image.open(pattern) as img:
        alpha = img.convert("RGBA").getchannel("A")
    height = alpha.filter(ImageFilter.GaussianBlur(1.5))
    scale = 8.0 / strength

    def _gradient(kernel: tuple[int, ...]) -> Image.Image:
        return height.filter(ImageFilter.Kernel((3, 3), kernel, scale=scale, offset=128))

    red = _gradient((1, 0, -1, 2, 0, -2, 1, 0, -1))
    green = _gradient((1, 2, 1, 0, 0, 0, -1, -2, -1))
    blue = Image.new("L", alpha.size, 255)
    output.parent.mkdir(parents=True, exist_ok=True)
    Image.merge("RGBA", (red, green, blue, Image.new("L", alpha.size, 255))).save(output)
    return output


def _source_stamp(paths: list[Path]) -> dict[str, list[int]]:
    stamp: dict[str, list[int]] = {}
    for path in paths:
        st = path.stat()
        stamp[str(path)] = [st.st_mtime_ns, st.st_size]
    return stamp


RunWorker = Callable[[dict, str], dict]


def build_net_mesh_rx3(pack_dir: Path, template_rx3: Path, cache_dir: Path, run_worker: RunWorker) -> Path:
    """The goalnet .rx3 to install for this pack. A ready-made .rx3 is returned
    directly; a pattern image is built into cache_dir/<pack>/goalnet.rx3 by the
    32-bit worker (run_worker = kit_mixer.run_fifalibrary_worker) and reused while
    neither the images nor the template changed. Blocking (seconds on a cold
    cache): call it from a worker thread. Raises when the pack holds nothing
    usable or the build fails."""
    ready = resolve_net_mesh_rx3(pack_dir)
    if ready is not None:
        return ready
    diffuse, normal = resolve_net_mesh_images(pack_dir)
    if diffuse is None:
        raise FileNotFoundError(f"No net pattern image (net.png) or .rx3 in {pack_dir}")
    if not template_rx3.is_file():
        raise FileNotFoundError(f"Vanilla goal net template not found: {template_rx3} (run Setup)")

    out_dir = cache_dir / pack_dir.name
    built = out_dir / _BUILT_NAME
    stamp_path = out_dir / _STAMP_NAME
    stamp = _source_stamp([p for p in (diffuse, normal, template_rx3) if p is not None])
    try:
        if built.is_file() and json.loads(stamp_path.read_text(encoding="utf-8")) == stamp:
            return built
    except (OSError, ValueError):
        pass

    out_dir.mkdir(parents=True, exist_ok=True)
    template = out_dir / "template.rx3"
    template.write_bytes(decompress_chunkzip(template_rx3.read_bytes()))
    generated = None
    if normal is None:
        generated = generate_normal_map(diffuse, out_dir / "net_nm.generated.png")
    try:
        run_worker(
            {
                "template": str(template),
                "output": str(built),
                "expected_count": NET_MESH_TEXTURE_COUNT,
                "replace": [
                    {"index": GOALNET_CM_INDEX, "image": str(diffuse)},
                    {"index": GOALNET_NM_INDEX, "image": str(normal or generated)},
                ],
            },
            "net_mesh_worker.py",
        )
    finally:
        template.unlink(missing_ok=True)
        if generated is not None:
            generated.unlink(missing_ok=True)
    stamp_path.write_text(json.dumps(stamp), encoding="utf-8")
    return built
