"""
32-bit bridge: loads FifaLibrary16.dll and regenerates .big BH entries.
Must be run with a 32-bit Python interpreter — the DLL is x86-only.

Usage: python bh_worker.py <dll_path> <game_dir>

Stdout protocol (JSON lines):
  {"t":"ready"}
  {"t":"progress","i":1,"total":10,"file":"x.big","ok":true}
  {"t":"progress","i":2,"total":10,"file":"y.big","ok":false,"error":"msg"}
  {"t":"done","ok":9,"failed":1}
  {"t":"error","msg":"fatal message"}
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def emit(obj: dict) -> None:
    print(json.dumps(obj), flush=True)


def main() -> None:
    if len(sys.argv) < 3:
        emit({"t": "error", "msg": "Usage: bh_worker.py <dll_path> <game_dir>"})
        sys.exit(1)

    dll_path = Path(sys.argv[1])
    game_dir = Path(sys.argv[2])

    if not dll_path.exists():
        emit({"t": "error", "msg": f"DLL not found: {dll_path}"})
        sys.exit(1)

    if not game_dir.is_dir():
        emit({"t": "error", "msg": f"Game directory not found: {game_dir}"})
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
        from FifaLibrary import BhFile  # type: ignore[import]
    except Exception as exc:
        emit({"t": "error", "msg": f"Failed to load FifaLibrary16.dll: {exc}"})
        sys.exit(1)

    big_files = sorted(game_dir.glob("*.big"))
    if not big_files:
        emit({"t": "error", "msg": "No .big files found in game directory"})
        sys.exit(1)

    emit({"t": "ready"})

    total = len(big_files)
    ok = 0
    failed = 0
    for i, big in enumerate(big_files):
        try:
            BhFile.Regenerate(str(big), True)
            emit({"t": "progress", "i": i + 1, "total": total, "file": big.name, "ok": True})
            ok += 1
        except Exception as exc:
            emit({"t": "progress", "i": i + 1, "total": total, "file": big.name, "ok": False, "error": str(exc)})
            failed += 1

    emit({"t": "done", "ok": ok, "failed": failed})


if __name__ == "__main__":
    main()
