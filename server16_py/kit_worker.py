"""
32-bit bridge: loads FifaLibrary16.dll and builds a mixed kit .rx3 by swapping
the jersey and/or shorts+socks textures of a template kit for textures taken
from another kit file or from a loose image (PNG/BMP/JPG).
Must be run with a 32-bit Python interpreter — the DLL is x86-only.

Usage: python kit_worker.py <dll_path> <config_json_path>

config_json_path points to a JSON file:
{
  "template": "<path to the kit .rx3 used as the base — its textures are kept
                for every role that is not overridden below>",
  "output": "<destination .rx3 path — does NOT need to exist yet>",
  "jersey": {"mode": "keep" | "rx3" | "img", "path": "<source path, absent for keep>"},
  "shorts": {"mode": "keep" | "rx3" | "img", "path": "<source path, absent for keep>"},
  "crest":  {"mode": "keep" | "rx3" | "img", "path": "<source path, absent for keep>"}
}

"crest" targets the "crest_cm" decal the game extracts from the kit file and
draws on top of the jersey (see player.lua: extracttexture crest_cm). It is a
single texture, not a diffuse+normal pair — mixing a jersey from a different
team without also picking a matching crest source is what causes two crests
to render on top of each other in-game.

Stdout: single JSON object
  {"ok": true, "output": "...", "roles": {...}}
  or {"ok": false, "error": "message"} on failure
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path


def _load_config(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _classify_bitmaps(bitmaps) -> dict:
    """Group a kit's textures by role using their aspect ratio / size, not a
    fixed index — the jersey (torso) texture is roughly square, the
    shorts+socks texture is roughly twice as wide as tall. Within each group
    the larger one is the diffuse map and the smaller one is the normal map.
    Any remaining small square-ish texture (there is normally exactly one) is
    the "crest_cm" badge decal the engine overlays on the jersey — see the
    module docstring.
    """
    entries = [(i, bmp.Width, bmp.Height, bmp.Width * bmp.Height) for i, bmp in enumerate(bitmaps)]
    square = sorted((e for e in entries if abs(e[1] - e[2]) <= max(e[1], e[2]) * 0.1), key=lambda e: -e[3])
    wide = sorted((e for e in entries if e[1] >= e[2] * 1.5), key=lambda e: -e[3])
    return {
        "jersey_diffuse": square[0][0] if len(square) > 0 else None,
        "jersey_normal": square[1][0] if len(square) > 1 else None,
        "crest": square[2][0] if len(square) > 2 else None,
        "shorts_diffuse": wide[0][0] if len(wide) > 0 else None,
        "shorts_normal": wide[1][0] if len(wide) > 1 else None,
    }


def _resized_copy(bitmap, width: int, height: int):
    from System.Drawing import Bitmap as DrawingBitmap, Graphics, GraphicsUnit
    if bitmap.Width == width and bitmap.Height == height:
        return bitmap
    resized = DrawingBitmap(width, height)
    g = Graphics.FromImage(resized)
    try:
        g.DrawImage(bitmap, 0, 0, width, height)
    finally:
        g.Dispose()
    return resized


def main() -> None:
    if len(sys.argv) < 3:
        print(json.dumps({"ok": False, "error": "Usage: kit_worker.py <dll_path> <config_json_path>"}))
        sys.exit(1)

    dll_path = Path(sys.argv[1])
    config_path = sys.argv[2]

    if not dll_path.exists():
        print(json.dumps({"ok": False, "error": f"DLL not found: {dll_path}"}))
        sys.exit(1)

    try:
        config = _load_config(config_path)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": f"Invalid config: {exc}"}))
        sys.exit(1)

    template_path = Path(config["template"])
    output_path = Path(config["output"])
    jersey_cfg = config.get("jersey", {"mode": "keep"})
    shorts_cfg = config.get("shorts", {"mode": "keep"})
    crest_cfg = config.get("crest", {"mode": "keep"})

    if not template_path.exists():
        print(json.dumps({"ok": False, "error": f"Template kit not found: {template_path}"}))
        sys.exit(1)

    dll_dir = str(dll_path.parent)
    if dll_dir not in sys.path:
        sys.path.insert(0, dll_dir)
    os.environ["PATH"] = dll_dir + os.pathsep + os.environ.get("PATH", "")

    try:
        clr = __import__("clr")
        try:
            clr.AddReference(str(dll_path))
        except Exception:
            System = __import__("System")
            System.Reflection.Assembly.LoadFrom(str(dll_path))
            clr.AddReference("FifaLibrary16")
        from FifaLibrary import Rx3File  # type: ignore[import]
        from System.Drawing import Bitmap as DrawingBitmap  # type: ignore[import]
    except Exception as exc:
        print(json.dumps({"ok": False, "error": f"Failed to load FifaLibrary16.dll: {exc}"}))
        sys.exit(1)

    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        # Rx3File.Save() writes in place into an already-existing file, so the
        # output must start out as a byte copy of the template.
        shutil.copyfile(str(template_path), str(output_path))

        rx3 = Rx3File()
        if not rx3.Load(str(output_path)):
            print(json.dumps({"ok": False, "error": f"Rx3File failed to load template: {template_path}"}))
            sys.exit(1)

        bitmaps = list(rx3.GetBitmaps())
        roles = _classify_bitmaps(bitmaps)

        def apply_role(role_cfg: dict, diffuse_role: str, normal_role: str | None = None) -> None:
            mode = role_cfg.get("mode", "keep")
            if mode == "keep":
                return
            diffuse_idx = roles.get(diffuse_role)
            normal_idx = roles.get(normal_role) if normal_role else None
            source_path = role_cfg.get("path")
            if not source_path:
                raise ValueError(f"Missing 'path' for mode={mode!r}")
            if mode == "rx3":
                src = Rx3File()
                if not src.Load(source_path):
                    raise ValueError(f"Failed to load source kit: {source_path}")
                src_bitmaps = list(src.GetBitmaps())
                src_roles = _classify_bitmaps(src_bitmaps)
                src_diffuse_idx = src_roles.get(diffuse_role)
                src_normal_idx = src_roles.get(normal_role) if normal_role else None
                if diffuse_idx is not None and src_diffuse_idx is not None:
                    bmp = _resized_copy(src_bitmaps[src_diffuse_idx], bitmaps[diffuse_idx].Width, bitmaps[diffuse_idx].Height)
                    if not rx3.ReplaceBitmap(bmp, diffuse_idx):
                        raise ValueError(f"ReplaceBitmap failed for {diffuse_role}")
                if normal_idx is not None and src_normal_idx is not None:
                    bmp = _resized_copy(src_bitmaps[src_normal_idx], bitmaps[normal_idx].Width, bitmaps[normal_idx].Height)
                    if not rx3.ReplaceBitmap(bmp, normal_idx):
                        raise ValueError(f"ReplaceBitmap failed for {normal_role}")
            elif mode == "img":
                if diffuse_idx is None:
                    raise ValueError(f"Template has no {diffuse_role} slot to replace")
                img = DrawingBitmap(source_path)
                bmp = _resized_copy(img, bitmaps[diffuse_idx].Width, bitmaps[diffuse_idx].Height)
                if not rx3.ReplaceBitmap(bmp, diffuse_idx):
                    raise ValueError(f"ReplaceBitmap failed for {diffuse_role}")
                # A loose image only supplies a diffuse/color map — the normal
                # map slot (if any) is left untouched on purpose.
            else:
                raise ValueError(f"Unknown mode: {mode!r}")

        apply_role(jersey_cfg, "jersey_diffuse", "jersey_normal")
        apply_role(shorts_cfg, "shorts_diffuse", "shorts_normal")
        apply_role(crest_cfg, "crest")

        if not rx3.Save(str(output_path), True, True):
            print(json.dumps({"ok": False, "error": "Rx3File.Save() returned False"}))
            sys.exit(1)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        sys.exit(1)

    print(json.dumps({"ok": True, "output": str(output_path), "roles": roles}))


if __name__ == "__main__":
    main()
