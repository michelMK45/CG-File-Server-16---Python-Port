"""
32-bit bridge: loads FifaLibrary16.dll and builds a goal net texture .rx3 by
swapping some of a template goalnet_*.rx3's textures for loose images.
Must be run with a 32-bit Python interpreter — the DLL is x86-only.

Usage: python net_mesh_worker.py <dll_path> <config_json_path>

config_json_path points to a JSON file:
{
  "template": "<uncompressed goalnet_*.rx3 used as the base — Rx3File.Load()
                rejects the chunkzip-compressed vanilla file, see
                net_mesh.decompress_chunkzip>",
  "output": "<destination .rx3 path — does NOT need to exist yet>",
  "expected_count": <optional: number of textures the template must hold>,
  "replace": [{"index": <texture index>, "image": "<PNG/BMP/JPG path>"}, ...]
}

Each image is resized to the template texture's own size, so the engine
keeps getting the dimensions/format it was built for.

Stdout: single JSON object
  {"ok": true, "output": "...", "sizes": [[w, h], ...]}
  or {"ok": false, "error": "message"} on failure
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path


def _resized_copy(bitmap, width: int, height: int):
    from System.Drawing import Bitmap as DrawingBitmap, Graphics
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
        print(json.dumps({"ok": False, "error": "Usage: net_mesh_worker.py <dll_path> <config_json_path>"}))
        sys.exit(1)

    dll_path = Path(sys.argv[1])
    if not dll_path.exists():
        print(json.dumps({"ok": False, "error": f"DLL not found: {dll_path}"}))
        sys.exit(1)

    try:
        config = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
        template_path = Path(config["template"])
        output_path = Path(config["output"])
        replacements = list(config.get("replace", []))
        expected_count = config.get("expected_count")
    except Exception as exc:
        print(json.dumps({"ok": False, "error": f"Invalid config: {exc}"}))
        sys.exit(1)

    if not template_path.exists():
        print(json.dumps({"ok": False, "error": f"Template not found: {template_path}"}))
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
            raise ValueError(f"Rx3File failed to load template: {template_path}")

        bitmaps = list(rx3.GetBitmaps())
        if expected_count is not None and len(bitmaps) != int(expected_count):
            raise ValueError(f"Template holds {len(bitmaps)} textures, expected {expected_count}")

        for entry in replacements:
            index = int(entry["index"])
            if not 0 <= index < len(bitmaps):
                raise ValueError(f"Texture index {index} out of range (template holds {len(bitmaps)})")
            img = DrawingBitmap(str(entry["image"]))
            bmp = _resized_copy(img, bitmaps[index].Width, bitmaps[index].Height)
            if not rx3.ReplaceBitmap(bmp, index):
                raise ValueError(f"ReplaceBitmap failed for texture {index}")

        if not rx3.Save(str(output_path), True, True):
            raise ValueError("Rx3File.Save() returned False")
    except Exception as exc:
        output_path.unlink(missing_ok=True)
        print(json.dumps({"ok": False, "error": str(exc)}))
        sys.exit(1)

    print(json.dumps({"ok": True, "output": str(output_path), "sizes": [[b.Width, b.Height] for b in bitmaps]}))


if __name__ == "__main__":
    main()
