"""
32-bit bridge: loads FifaLibrary16.dll and bakes a loose PNG/BMP/JPG image into
a .dds file, matching the pixel dimensions of an existing template .dds (kit UI
thumbnails have a fixed slot size/compression the game expects) via
FifaLibrary's DdsFile.ReplaceBitmap. Must be run with a 32-bit Python
interpreter - the DLL is x86-only.

Usage: python dds_image_worker.py <dll_path> <config_json_path>

config_json_path points to a JSON file:
{
  "template": "<path to an existing .dds - supplies target dimensions/format>",
  "image": "<path to a loose PNG/BMP/JPG image>",
  "output": "<destination .dds path - does NOT need to exist yet>"
}

Stdout: single JSON object
  {"ok": true, "output": "..."}
  or {"ok": false, "error": "message"} on failure
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kit_worker import _resized_copy  # noqa: E402


def _load_config(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main() -> None:
    if len(sys.argv) < 3:
        print(json.dumps({"ok": False, "error": "Usage: dds_image_worker.py <dll_path> <config_json_path>"}))
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
    image_path = Path(config["image"])
    output_path = Path(config["output"])

    if not template_path.exists():
        print(json.dumps({"ok": False, "error": f"Template DDS not found: {template_path}"}))
        sys.exit(1)
    if not image_path.exists():
        print(json.dumps({"ok": False, "error": f"Source image not found: {image_path}"}))
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
        from FifaLibrary import DdsFile  # type: ignore[import]
        from System.Drawing import Bitmap as DrawingBitmap  # type: ignore[import]
    except Exception as exc:
        print(json.dumps({"ok": False, "error": f"Failed to load FifaLibrary16.dll: {exc}"}))
        sys.exit(1)

    try:
        # DdsFile.Save(fileName) opens the target with FileMode.Open, which
        # requires the file to already exist (same constraint Rx3File.Save has
        # in kit_worker.py) - so output_path must start out as a byte copy of
        # the template, then get loaded/mutated/saved in place.
        output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(str(template_path), str(output_path))

        dds = DdsFile()
        if not dds.Load(str(output_path)):
            print(json.dumps({"ok": False, "error": f"DdsFile failed to load template: {template_path}"}))
            sys.exit(1)
        target = dds.GetBitmap()

        img = DrawingBitmap(str(image_path))
        bmp = _resized_copy(img, target.Width, target.Height)
        # DdsFile.ReplaceBitmap (unlike Rx3File.ReplaceBitmap) returns void, not
        # bool - pythonnet maps that to None, so checking its return value here
        # would always look like failure. It also has no failure mode of its
        # own; the mip-chain rebuild inside it can only throw, not return false.
        dds.ReplaceBitmap(bmp)

        if not dds.Save(str(output_path)):
            print(json.dumps({"ok": False, "error": "DdsFile.Save() returned False"}))
            sys.exit(1)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        sys.exit(1)

    print(json.dumps({"ok": True, "output": str(output_path)}))


if __name__ == "__main__":
    main()
