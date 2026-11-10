---
paths:
  - "server16_py/app_overlay.py"
  - "server16_py/d3d_injector.py"
  - "server16_py/d3d_overlay/*.cpp"
  - "server16_py/d3d_overlay/*.h"
  - "server16_py/d3d_overlay/**/*.rml"
  - "server16_py/d3d_overlay/**/*.rcss"
  - "tests/test_overlay*.py"
---
F12 overlay / D3D11 DLL. Read `docs/overlay-d3d.md`; for any key/mouse/gamepad input change also
`docs/bugs-overlay-input.md`.
- `OverlayShared` (`cgfs16_overlay.cpp`) and the `ctypes.Structure` in `d3d_injector.py` are kept in sync
  BY HAND (mapping `Local\CGFS16_Overlay_v2`, no versioning). Add new fields only at the END, same
  types/sizes/alignment on both sides, and check `ctypes.sizeof` against the C++ `sizeof`.
- Any C++/RML change needs the user to run `build_exe.bat` (rebuilds `bin/cgfs16_overlay.dll`); say so
  in the wrap-up. Python-only overlay changes don't. You cannot see the overlay render — mark such
  changes "offline-tested".
- The `WH_KEYBOARD_LL` hook is installed ONLY while the menu/picker is open; never make it permanent
  (FIFA menus become sluggish). A key-up goes where its key-down went.
- Overlay-wizard strings are hardcoded English (not routed through locales); dashboard cap is
  `MAX_DASH_ITEMS` = 10 lines.
- Timing bugs here: reproduce with a real-threaded harness (fake `user32.GetAsyncKeyState`, real poll
  thread) before concluding; check the DLL log `%TEMP%\cgfs16_overlay.log` first.
