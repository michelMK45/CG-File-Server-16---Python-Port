# CGFS 16 Server 16 Python Port v0.2.1

## Highlights

- Fixed the Windows build flow so `build_exe.bat` correctly generates `dist/Server16Python.exe` using the PyInstaller spec file.
- Added the custom `server16.ico` as the executable icon and as the runtime window icon while the app is open.
- Bundled the runtime icon asset into the one-file executable so the app no longer falls back to the default Python icon.
- Kept the packaging flow self-contained for release uploads based on the generated executable.

## Included Fixes

- `build_exe.bat` now calls `Server16Python.spec` without invalid extra makespec options.
- The PyInstaller spec keeps `server16.ico` available at runtime for Tkinter windows.
- Main window, floating dialogs, and auxiliary windows now reuse the same application icon.

## Release Asset

- `Server16Python.exe`

## Recommended Release Message

This patch release fixes the Windows packaging flow and finalizes the application icon setup.

`build_exe.bat` now generates the executable correctly again, the `.exe` keeps the custom icon, and the running app window no longer shows the default Python icon.
