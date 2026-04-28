# CGFS 16 Server 16 Python Port

Python conversion of the original CGFS 16 Server 16 tool for FIFA 16.

This project is a community-friendly, public rewrite of the classic FIFA 16 Server 16 workflow. It provides a Windows desktop control panel and in-game overlay for managing stadium assignments, scoreboards, TV logos, movies, chants, and camera packages while FIFA 16 is running.

## What This Project Does

- Converts the legacy Server 16 behavior into Python.
- Attaches to FIFA 16 memory to read live match context.
- Applies stadium, scoreboard, TV logo, movie, and chants logic based on the current match state.
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
`

<img width="1010" height="698" alt="Screenshot_3" src="https://github.com/user-attachments/assets/c3a08a83-bef0-4dd4-a445-336ea80be6ea" />


These paths are reserved so contributors can add screenshots later without changing the documentation structure.

## Repository Structure

- `main.py`: project entry point.
- `server16_py/`: main application source code.
- `server16_py/app.py`: primary UI, overlay management, and runtime coordination.
- `server16_py/stadium_runtime.py`: stadium loading and application logic.
- `server16_py/asset_runtime.py`: scoreboard, TV logo, movie, and related routing.
- `server16_py/chants_runtime.py`: chants and audio playback runtime.
- `server16_py/settings_editor.py`: settings editing UI.
- `server16_py/dialogs.py`: assignment dialogs.
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
  - `pyinstaller` for packaging

Depending on your environment, additional packages may be needed if they are introduced by future changes.

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
python -m pip install psutil pillow pygame pyinstaller
python main.py
```

## First-Time Setup

When the tool opens:

1. Point it to your `FIFA 16.exe` if needed.
2. Let it detect the game folder and related `FSW`, `StadiumGBD`, `ScoreBoardGBD`, `MoviesGBD`, and other data folders.
3. Start FIFA 16.
4. Use the tool in normal window mode or arm the overlay mode.

The application stores local settings in `runtime/settings.json`.

## Stadium Preview Images

The project supports optional preview images for stadiums.

When present, these images are shown in:

- the dashboard `Stadium Bay`
- the `Assign Stadium` window under `Visual Details`
- the `Loading Stadium` modal during stadium application

To be detected correctly, the image must follow this folder layout:

```text
StadiumGBD/<stadium name>/render/thumbnail/stadium/stadium.png
```

or:

```text
StadiumGBD/<stadium name>/render/thumbnail/stadium/stadium.jpg
StadiumGBD/<stadium name>/render/thumbnail/stadium/stadium.jpeg
```

Example:

```text
StadiumGBD/BRA - Maracana - Flamengo/render/thumbnail/stadium/stadium.jpg
```

Notes:

- The `<stadium name>` folder must exactly match the stadium folder used by the assignment.
- The file name must be `stadium` with one of the supported extensions: `.png`, `.jpg`, `.jpeg`, or `.jepg`.
- If no preview image exists, the stadium still works normally; the preview area is simply hidden where applicable.
- This structure is intended to make community stadium packs easy to organize and share.

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
