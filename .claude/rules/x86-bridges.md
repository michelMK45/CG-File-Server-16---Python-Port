---
paths:
  - "server16_py/*_worker.py"
  - "server16_py/native_tools/**"
  - "tests/test_*worker*.py"
---
32-bit bridges (`FifaLibrary16.dll` is x86-only). Read `docs/memory-and-bridges.md`.
- Never load `FifaLibrary16.dll` (or any x86 DLL) in-process. Workers run under `bin/python32/python.exe`
  (provisioned by `scripts/setup_python32.bat`) and speak newline-delimited JSON on stdout:
  `{"t":"ready"|"progress"|"done"|"error"}`.
- Tests fake `clr`/`FifaLibrary`/GDI+; a real render through the bridge is never exercised by the test
  suite — say "offline-tested" unless you actually ran the real worker.
- Vanilla `.rx3` from `.big` are EA `chunkzip`; `Rx3File.Load` rejects them (`net_mesh.decompress_chunkzip`).
- Never write `fifa_ng_db.db` on disk.
