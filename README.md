# CGFS 16 Server 16 Python Port

Python conversion of the original CGFS 16 Server 16 tool for FIFA 16.

This project is a community-friendly, public rewrite of the classic FIFA 16 Server 16 workflow. It provides a Windows desktop control panel and in-game overlay for managing stadium assignments, scoreboards, TV logos, movies, chants, and camera packages while FIFA 16 is running.

## What This Project Does

- Converts the legacy Server 16 behavior into Python.
- Attaches to FIFA 16 memory to read live match context.
- Applies stadium, scoreboard, TV logo, movie, chants, and camera logic based on the current match state.
- Loads assigned stadiums from normal folders or `.zip` / `.rar` archives.
- Supports an overlay-style main UI that can appear on top of FIFA 16.
- Opens secondary editors and assignment dialogs as floating windows outside the overlay flow.
- Includes tools for editing `settings.ini`-driven assignment data.
- Packages the project as a standalone Windows executable with PyInstaller.

## Project Status

This repository is intended to be public and open for community contributions.

The goal is to preserve and evolve the FIFA 16 Server 16 experience in a modern Python codebase that is easier to maintain, improve, and extend.

## Screenshots


Main overlay:

<img width="1007" height="667" alt="Screenshot_2" src="https://github.com/user-attachments/assets/9b533e22-21c2-46e2-adc0-a40a71e3ec3a" />

<img width="1008" height="694" alt="Screenshot_1" src="https://github.com/user-attachments/assets/ed0296f2-a270-48c0-a0cf-91d90054891c" />

<img width="1010" height="698" alt="Screenshot_3" src="https://github.com/user-attachments/assets/c3a08a83-bef0-4dd4-a445-336ea80be6ea" />


These paths are reserved so contributors can add screenshots later without changing the documentation structure.

## Repository Structure

- `main.py`: project entry point.
- `server16_py/`: main application source code.
- `server16_py/app.py`: primary UI, overlay management, and runtime coordination.
- `server16_py/assignment_runtime.py`: assignment flow for stadiums, scoreboards, TV logos, movies, and exclusions.
- `server16_py/stadium_runtime.py`: stadium loading and application logic, including folder and archive sources.
- `server16_py/asset_runtime.py`: scoreboard, TV logo, movie, and related routing.
- `server16_py/chants_runtime.py`: chants and audio playback runtime.
- `server16_py/camera_runtime.py`: Anth camera package discovery, preview, and application.
- `server16_py/settings_editor.py`: settings editing UI.
- `server16_py/dialogs.py`: assignment dialogs.
- `server16_py/file_tools.py`: shared file-copying, archive extraction, and setup helpers.
- `runtime/`: local runtime data such as settings and logs.
- `legacy/`: reference material from the original project/conversion process.
- `build_exe.bat`: convenience build script for Windows.
- `Server16Python.spec`: PyInstaller spec file.

## Requirements

- Windows
- FIFA 16 installed locally
- Python 3.10+ recommended
- The Python packages used by the project, especially:
  - `psutil`
  - `Pillow`
  - `pygame`
  - `rarfile` for native RAR extraction when available
  - `pyinstaller` for packaging

RAR stadium archives can also be extracted through the Windows `tar` command when `rarfile` is not installed. Depending on your environment, additional packages may be needed if they are introduced by future changes.

## Running From Source

1. Clone the repository.
2. Create and activate a virtual environment.
3. Install the dependencies you need.
4. Run the app with Python.

Example:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install psutil pillow pygame rarfile pyinstaller
python main.py
```

## First-Time Setup

When the tool opens:

1. Point it to your `FIFA 16.exe` if needed.
2. Let it detect the game folder and related `FSW`, `StadiumGBD`, `ScoreBoardGBD`, `TVLogoGBD`, `MoviesGBD`, and other data folders.
3. Start FIFA 16.
4. Use the tool in normal window mode or arm the overlay mode.

The application stores local settings in `runtime/settings.json` and reads/writes Server 16 assignment data from `FSW/settings.ini` inside the detected FIFA 16 folder.

## Expected FIFA Folder Layout

The runtime resolves mod folders from the selected `FIFA 16.exe` directory:

```text
FIFA 16/
  FSW/
    settings.ini
    stadium/
    ScoreBoard/
    TVLogo/
    Nav/
    Chants/
    Images/
      PitchMowPattern/
      Nets/
      Police/
  StadiumGBD/
    render/
      thumbnail/
        stadium/
  ScoreBoardGBD/
  TVLogoGBD/
  MoviesGBD/
```

For pitch, net, and police assets, the current code supports both the root `FSW` folders and the older `FSW/Images` folders:

```text
FSW/PitchMowPattern/
FSW/Nets/
FSW/Police/

FSW/Images/PitchMowPattern/
FSW/Images/Nets/
FSW/Images/Police/
```

Runtime bootstrap copying prefers the root `FSW/PitchMowPattern`, `FSW/Nets`, and `FSW/Police` folders when they exist. The stadium assignment dialog uses the `FSW/Images/...` folders first for selector values and preview PNGs, then falls back to the root folders.

## Stadium Preview Images

The project supports optional preview images for stadiums.

When present, these images are shown in:

- the dashboard `Stadium Bay`
- the `Assign Stadium` window under `Visual Details`
- the `Loading Stadium` modal during stadium application

To be detected correctly, stadium preview images now live in one shared thumbnail folder:

```text
StadiumGBD/render/thumbnail/stadium/
```

Each preview file must use the stadium name as its file name. If the stadium is loaded from a `.zip` or `.rar`, use the archive stem.

```text
StadiumGBD/render/thumbnail/stadium/<stadium name>.png
StadiumGBD/render/thumbnail/stadium/<stadium name>.jpg
StadiumGBD/render/thumbnail/stadium/<stadium name>.jpeg
```

Example:

```text
StadiumGBD/ARG - Diego Armando Maradona.zip
StadiumGBD/render/thumbnail/stadium/ARG - Diego Armando Maradona.jpg
```

Notes:

- The preview file stem must exactly match the stadium folder name or archive stem used by the assignment.
- Supported preview extensions are `.png`, `.jpg`, `.jpeg`, and `.jepg`.
- The app also uses this folder when discovering stadium names for the assignment and settings editors, alongside normal stadium folders and `.zip` / `.rar` files in `StadiumGBD`.
- The old per-stadium layouts `StadiumGBD/<stadium name>/render/thumbnail/stadium.*` and `StadiumGBD/<stadium name>/render/thumbnail/stadium/stadium.*` are no longer used by the current code.
- If no preview image exists, the stadium still works normally; the preview area is simply hidden where applicable.
- This structure is intended to make community stadium packs easy to organize and share.

## Stadium Folder And Archive Loading

Stadium assignments are read from `FSW/settings.ini`. A stadium value can point to:

```text
StadiumGBD/<stadium name>/
StadiumGBD/<stadium name>.zip
StadiumGBD/<stadium name>.rar
```

When an assignment points to an archive, the app extracts it into a temporary folder under `runtime/`, finds the first valid stadium folder inside it, applies the stadium files, and then cleans up the temporary extraction.

Valid stadium folders are expected to include normal Server 16 stadium files such as:

```text
model.rx3
texture_day.rx3
texture_night.rx3
crowd_day.dat
crowd_night.dat
EntranceScene/
1/
3/
```

Optional files supported by the runtime:

- `NoSeats.rx3` for crowd-chair replacement.
- `StadiumMovie.vp8` and `StadiumBumper.big` for stadium-specific movies.

Archive extraction is used only for loading the stadium files. Preview lookup does not extract archives, so preview images are resolved from `StadiumGBD/render/thumbnail/stadium/<stadium name>.*`.

## Assignment And Settings Editors

The app can create and update `settings.ini` entries from the UI:

- stadium assignments by home team, round, or full tournament
- multi-stadium assignments for randomized stadium rotation
- scoreboard and TV logo assignments by tournament, round, or home team
- movie assignments by tournament, round, derby, or home team
- excluded competitions or rounds
- stadium net values and scoreboard display names
- chants entries under `FSW/Chants`

Changes saved through the editor are applied back into the runtime immediately where possible.

## Camera Packages

The Camera tab supports the exact package folder named:

```text
Anth's FIFA 16 AIO Camera Mod Package
```

The folder must contain `Instructions.txt`. Each camera preset is discovered from a child folder with a `data/` directory, and any `.png` files in that preset folder are used as preview images.

When a camera is applied, the preset's `data/` contents are synced into the FIFA `data/` folder. If `REGENERATOR.exe` is found next to the selected FIFA install, the app attempts to launch it after copying the files.

## Building The EXE

You can build the standalone executable with the included batch file:

```powershell
.\build_exe.bat
```

The batch file compiles the C++ overlay helpers when Visual Studio C++ tools are available. If they
are not installed, it uses the existing helper binaries in `bin/` and still runs the PyInstaller
package step.

Or run PyInstaller directly:

```powershell
pyinstaller --noconfirm --clean --distpath dist --workpath build\pyinstaller Server16Python.spec
```

The resulting executable will be created at:

```text
dist/Server16Python.exe
```

## How To Contribute

Contributions are welcome.

You can help by:

- fixing runtime bugs
- improving the overlay UX
- refining stadium, scoreboard, and movie workflows
- improving audio/chants behavior
- expanding documentation
- testing on different FIFA 16 setups

Suggested contribution flow:

1. Fork the repository.
2. Create a feature branch.
3. Make focused changes.
4. Test locally.
5. Open a pull request with a clear description.

## Notes For Contributors

- Keep Windows compatibility in mind.
- Avoid committing build outputs and local runtime artifacts.
- Prefer small, reviewable pull requests.
- If you change behavior tied to FIFA memory offsets or file routing, document it in the PR.

## Release Assets

Suggested GitHub release contents:

- `Server16Python.exe`
- `RELEASE_NOTES_v0.2.1.md`
- release notes summarizing major fixes and improvements
- optional screenshots or changelog excerpts

## Credits

- Original concept and workflow: CGFS 16 Server 16 for FIFA 16
- Python port and ongoing maintenance: this community project and its contributors

## Disclaimer

This project is an unofficial community tool for FIFA 16 modding workflows. Use it at your own risk and always keep backups of important game and mod files.
