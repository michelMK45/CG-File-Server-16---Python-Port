"""
32-bit bridge: loads FifaLibrary16.dll and renders a small PNG preview of one
kit asset (jersey/shorts/crest texture, or a jersey/shorts kit-numbers digit
sample) so the desktop Kit Mixer dialog can show it without needing its own
RX3 parsing. Also reused (role="rx3_texture") by StadiumRuntime.
render_goalpost_texture_preview to preview an arbitrary single-purpose .rx3
(e.g. a goalpost net/post color pack) that has no kit-specific jersey/shorts/
crest roles to classify — just its first embedded bitmap, as-is.
role="rx3_all_textures" (AssetRuntime.render_rx3_textures, the Match Assets
preview of a ball/referee/wipe/adboard pack) instead writes EVERY embedded
bitmap, one PNG each, because those packs ship several textures per .rx3.
Must be run with a 32-bit Python interpreter — the DLL is x86-only.

Usage: python kit_preview_worker.py <dll_path> <config_json_path>

config_json_path points to a JSON file:
{
  "source": "<path to a kit .rx3, a specifickitnumbers_*.rx3, a j0_*.dds, or any other .rx3>",
  "role": "jersey" | "shorts" | "crest" | "jersey_numbers" | "shorts_numbers" | "kitui" | "rx3_texture" | "rx3_all_textures",
  "output": "<destination .png path>",            (every role except rx3_all_textures)
  "output_dir": "<destination folder>",           (rx3_all_textures only; written as 0.png, 1.png, ...)
  "max_size": 256
}

Stdout: single JSON object
  {"ok": true, "output": "..."}                   (rx3_all_textures: {"ok": true, "outputs": ["...0.png", ...]})
  or {"ok": false, "error": "message"} on failure
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kit_worker import _classify_bitmaps  # noqa: E402


def _load_config(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _thumbnail(bitmap, max_size: int):
    """Aspect-preserving downscale — unlike kit_worker's _resized_copy this
    must NOT stretch, since it's only for display."""
    from System.Drawing import Bitmap as DrawingBitmap, Graphics
    scale = min(max_size / bitmap.Width, max_size / bitmap.Height, 1.0)
    w = max(1, int(bitmap.Width * scale))
    h = max(1, int(bitmap.Height * scale))
    if w == bitmap.Width and h == bitmap.Height:
        return bitmap
    small = DrawingBitmap(w, h)
    g = Graphics.FromImage(small)
    try:
        g.DrawImage(bitmap, 0, 0, w, h)
    finally:
        g.Dispose()
    return small


def main() -> None:
    if len(sys.argv) < 3:
        print(json.dumps({"ok": False, "error": "Usage: kit_preview_worker.py <dll_path> <config_json_path>"}))
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

    source_path = Path(config["source"])
    role = config["role"]
    # rx3_all_textures writes into output_dir instead of a single output file.
    output_path = Path(config["output"]) if "output" in config else None
    max_size = int(config.get("max_size", 256))
    if role == "rx3_all_textures":
        if "output_dir" not in config:
            print(json.dumps({"ok": False, "error": "rx3_all_textures needs an output_dir"}))
            sys.exit(1)
    elif output_path is None:
        print(json.dumps({"ok": False, "error": f"Role {role!r} needs an output path"}))
        sys.exit(1)

    if not source_path.exists():
        print(json.dumps({"ok": False, "error": f"Source not found: {source_path}"}))
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
        from FifaLibrary import Rx3File, DdsFile  # type: ignore[import]
        from System.Drawing import Bitmap as DrawingBitmap, Graphics  # type: ignore[import]
        from System.Drawing.Imaging import ImageFormat  # type: ignore[import]
    except Exception as exc:
        print(json.dumps({"ok": False, "error": f"Failed to load FifaLibrary16.dll: {exc}"}))
        sys.exit(1)

    try:
        if role == "kitui":
            dds = DdsFile()
            if not dds.Load(str(source_path)):
                print(json.dumps({"ok": False, "error": f"DdsFile failed to load: {source_path}"}))
                sys.exit(1)
            preview_bitmap = dds.GetBitmap()
            thumb = _thumbnail(preview_bitmap, max_size)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            thumb.Save(str(output_path), ImageFormat.Png)
            print(json.dumps({"ok": True, "output": str(output_path)}))
            return

        rx3 = Rx3File()
        if not rx3.Load(str(source_path)):
            print(json.dumps({"ok": False, "error": f"Rx3File failed to load: {source_path}"}))
            sys.exit(1)

        bitmaps = list(rx3.GetBitmaps())
        if not bitmaps:
            print(json.dumps({"ok": False, "error": "Source has no textures"}))
            sys.exit(1)

        if role == "rx3_all_textures":
            # Every embedded bitmap, in file order: the caller steps through
            # them (a wipe pack carries about eight). Names are the bitmap's
            # index so the order survives; a bitmap that fails to save is
            # skipped rather than failing the whole file.
            output_dir = Path(config["output_dir"])
            output_dir.mkdir(parents=True, exist_ok=True)
            outputs = []
            for index, bitmap in enumerate(bitmaps):
                target = output_dir / f"{index}.png"
                try:
                    _thumbnail(bitmap, max_size).Save(str(target), ImageFormat.Png)
                except Exception:
                    continue
                outputs.append(str(target))
            if not outputs:
                print(json.dumps({"ok": False, "error": "No texture could be rendered"}))
                sys.exit(1)
            print(json.dumps({"ok": True, "outputs": outputs}))
            return
        if role == "rx3_texture":
            # No kit-specific role to classify -- just the first embedded
            # bitmap, as-is (see the module docstring).
            preview_bitmap = bitmaps[0]
        elif role in ("jersey", "shorts", "crest"):
            roles = _classify_bitmaps(bitmaps)
            idx = roles.get("crest") if role == "crest" else roles.get(f"{role}_diffuse")
            if idx is None:
                print(json.dumps({"ok": False, "error": f"Could not identify a {role} texture in {source_path.name}"}))
                sys.exit(1)
            preview_bitmap = bitmaps[idx]
        elif role in ("jersey_numbers", "shorts_numbers"):
            # specifickitnumbers_*.rx3: ten uniform digit textures indexed 0-9.
            # Composite digits "1" and "0" side by side as a representative "10".
            if len(bitmaps) < 10:
                preview_bitmap = bitmaps[0]
            else:
                d1, d0 = bitmaps[1], bitmaps[0]
                combo = DrawingBitmap(d1.Width + d0.Width, max(d1.Height, d0.Height))
                g = Graphics.FromImage(combo)
                try:
                    g.DrawImage(d1, 0, 0, d1.Width, d1.Height)
                    g.DrawImage(d0, d1.Width, 0, d0.Width, d0.Height)
                finally:
                    g.Dispose()
                preview_bitmap = combo
        else:
            print(json.dumps({"ok": False, "error": f"Unknown role: {role!r}"}))
            sys.exit(1)

        thumb = _thumbnail(preview_bitmap, max_size)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        thumb.Save(str(output_path), ImageFormat.Png)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        sys.exit(1)

    print(json.dumps({"ok": True, "output": str(output_path)}))


if __name__ == "__main__":
    main()
