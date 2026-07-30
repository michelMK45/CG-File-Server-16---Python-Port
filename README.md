<h1 align="center">CGFS 16 Server 16 Python Port</h1>

<p align="center">
  <a href="https://github.com/michelMK45/CG-File-Server-16---Python-Port/releases">
  <img alt="Github Downloads" src="https://img.shields.io/github/downloads/michelMK45/CG-File-Server-16---Python-Port/total?style=for-the-badge&logo=github">
  </a>
  <br>
</p>

⚠This is a fork from the orignal project, as the original author stopped developing the tool. So the community can continue.

Python conversion of the original CGFS 16 Server 16 tool for FIFA 16.

This project is a community-friendly, public rewrite of the classic FIFA 16 Server 16 workflow. It provides a Windows desktop control panel and in-game overlay for managing stadium assignments, scoreboards, TV logos, movies, chants, and camera packages while FIFA 16 is running.

## What This Project Does

- Converts the legacy Server 16 behavior into Python.
- Attaches to FIFA 16 memory to read live match context.
- Applies stadium, scoreboard, TV logo, movie, chants, and camera logic based on the current match state.
- Loads assigned stadiums from normal folders or `.zip` / `.rar` archives.
- Provides a **fullscreen in-game overlay** for assigning assets without leaving FIFA 16, fully controllable with a gamepad or keyboard.
- Opens secondary editors and assignment dialogs as floating windows outside the overlay flow.
- Includes tools for editing `settings.ini`-driven assignment data.
- Packages the project as a standalone Windows executable with PyInstaller.

## Project Status

This repository is intended to be public and open for community contributions.

The goal is to preserve and evolve the FIFA 16 Server 16 experience in a modern Python codebase that is easier to maintain, improve, and extend.

## Screenshots

Main overlay:

<img alt="Screenshot_2" src="https://i.ibb.co/Dq9hf5p/image.png" />

<img alt="Screenshot_1" src="https://i.ibb.co/845Kjjtz/image.png" />

<img alt="Screenshot_3" src="https://i.ibb.co/ymQqhYLp/image.png" />

## Repository Structure

- `main.py`: project entry point.
- `server16_py/`: main application source code.
- `server16_py/app.py`: application entry class; assembles the mixin modules below.
- `server16_py/app_ui.py`: main window construction, dashboard layout, and UI helpers.
- `server16_py/app_overlay.py`: in-game overlay loop, gamepad/keyboard input handling, and D3D menu rendering.
- `server16_py/app_game.py`: game process polling, live match context reading, and stats loop.
- `server16_py/app_settings.py`: settings loading, module state management, and worker queue.
- `server16_py/app_logging.py`: runtime log panel and auto-follow toggle.
- `server16_py/app_localization.py`: language switching and UI string application.
- `server16_py/win32_types.py`: shared Win32 ctypes type definitions.
- `server16_py/assignment_runtime.py`: assignment flow for stadiums, scoreboards, TV logos, movies, and exclusions.
- `server16_py/stadium_runtime.py`: stadium loading and application logic, including folder and archive sources.
- `server16_py/asset_runtime.py`: scoreboard, TV logo, movie, and related routing.
- `server16_py/chants_runtime.py`: chants and audio playback runtime.
- `server16_py/camera_runtime.py`: Anth camera package discovery, preview, and application.
- `server16_py/kit_mixer.py`: Kit Mixer runtime — mixes jersey/shorts textures, kit numbers, kit UI thumbnails, and jersey name color, with a per-kit-type restore manager.
- `server16_py/substitution_runtime.py`: live in-game hook that lets you raise FIFA 16's hardcoded substitution limit for the current match.
- `server16_py/settings_editor.py`: settings editing UI.
- `server16_py/dialogs.py`: assignment dialogs.
- `server16_py/file_tools.py`: shared file-copying, archive extraction, and setup helpers.
- `server16_py/fifa_db.py`: reads team/stadium names from the FIFA t3db database via the `db_worker.py` subprocess bridge.
- `server16_py/db_worker.py` / `server16_py/bh_worker.py` / `server16_py/kit_worker.py` / `server16_py/kit_preview_worker.py`: 32-bit subprocess workers that load `FifaLibrary16.dll` (x86-only) to read the database, regenerate BH entries, and mix/preview kit textures, respectively.
- `server16_py/native_tools/kit_extractor/`: source for `KitExtractorHost.exe` (`bin/KitExtractorHost.exe`), a standalone x86 tool that bulk-extracts kits/database content used by the Setup tab's Assets Extractor.
- `runtime/`: local runtime data such as settings and logs.
- `legacy/`: reference material from the original project/conversion process.
- `scripts/setup_python32.bat`: provisions the bundled 32-bit Python interpreter used by the workers above.
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
  - `pypresence` for Discord Rich Presence (optional, see [DISCORD_SETUP.md](DISCORD_SETUP.md))
  - `pyinstaller` for packaging

RAR stadium archives can also be extracted through the Windows `tar` command when `rarfile` is not installed (and `rarfile` itself is configured to use it as a fallback when `unrar`/`7z` are unavailable). Depending on your environment, additional packages may be needed if they are introduced by future changes.

### FIFA Database Reading (32-bit Bridge)

Team names, stadium names, and BH regeneration are read/written through `bin/FifaLibrary16.dll`, which is x86-only. Since the main app can run as 64-bit Python, these operations are delegated to a dedicated 32-bit Python subprocess:

- Run `scripts\setup_python32.bat` once to provision a 32-bit Python embeddable (with `pythonnet` installed) at `bin/python32/`. It is idempotent and is also run automatically by `build_exe.bat`.
- If `bin/python32/` is not present, the app falls back to the Windows Python Launcher (`py -3-32`) or common x86 install paths.
- Without a working 32-bit interpreter, Discord Rich Presence team/stadium name resolution, the **Regenerate BH** action in the Setup tab, and **Kit Mixer** will all be unavailable.

The Setup tab's **Assets Extractor** additionally requires `bin/KitExtractorHost.exe` (built from `server16_py/native_tools/kit_extractor/` via `build_exe.bat`, or from the prebuilt binary) plus `fifa16_decryptor.exe`, `un_chunlzma.exe`, and `zlib.net.dll` in `bin/` — these three ship with third-party tools (**Creation Master 16** / **FIF Converter**) and are not built or redistributed by this repository, so they must be copied into `bin/` manually if missing.

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
python -m pip install psutil pillow pygame rarfile pypresence pyinstaller
python main.py
```

## First-Time Setup

When the tool opens:

1. Point it to your `FIFA 16.exe` if needed.
2. Let it detect the game folder and related `FSW`, `StadiumGBD`, `ScoreBoardGBD`, `TVLogoGBD`, `MoviesGBD`, and other data folders.
3. Start FIFA 16.
4. Use the tool in normal window mode or arm the overlay mode.

The application stores local settings in `runtime/settings.json` and reads/writes Server 16 assignment data from `FSW/settings.ini` inside the detected FIFA 16 folder.

## In-Game Interactive Overlay

The overlay lets you assign stadiums, scoreboards, TV logos, movies, and other CGFS assets without alt-tabbing out of FIFA 16. It runs in fullscreen mode on top of the game.

### Opening and Closing

| Action | Input |
|---|---|
| Open overlay | **F12** |
| Open overlay (gamepad) | Hold **Start / Menu** for 0.6 seconds |
| Close overlay | Press **F12** again, or close with the controller |

### What You Can Do Inside the Overlay

- Assign stadiums — with visual preview images shown directly in the overlay.
- Assign scoreboards, TV logos, movies, and other CGFS assets.
- See the **active assignment mode** (Round, Tournament, Home Team, or Default) for each asset type.
- Navigate all sections using **controller button hints** displayed on screen.
- Use **keyboard shortcuts** shown in the hint bar at the bottom of the overlay (UP/DOWN, Wheel, RIGHT/LEFT, Enter, Esc).

### Enabling or Disabling the Overlay

A checkbox in the settings panel allows you to enable or disable the in-game overlay independently. When disabled, F12 and the Start button hold have no effect.

### Requirements

The overlay uses native C++ helpers (`bin/cgfs16_overlay.dll` and `bin/cgfs16_inject.exe`) that ship with the release build. Running from source requires these binaries to be present in the `bin/` folder. The build script (`build_exe.bat`) compiles them when Visual Studio C++ tools are available.

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
- If no preview image exists for a stadium that *is* actually assigned, the dashboard, `Assign Stadium` window, and loading overlay fall back to a bundled generic stadium image instead of showing nothing. The preview area only stays empty when there's no stadium assigned at all.
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
GameplayCamGBD/
GoalpostGBD/
```

Optional files supported by the runtime:

- `NoSeats.rx3` for crowd-chair replacement.
- `StadiumMovie.vp8` and `StadiumBumper.big` for stadium-specific movies.
- `GameplayCamGBD/bcgameplay_176.dat` and `GameplayCamGBD/bcgameplay_261.dat` for per-stadium gameplay camera overrides.
- `GoalpostGBD/` for per-stadium goal model files. Contents are copied to the game's goal-net directory on load and removed automatically when the next stadium (without goalposts) is applied.

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

## Gameplay Camera Files

The app supports per-stadium gameplay camera overrides using `bcgameplay_176.dat` and `bcgameplay_261.dat`. These files control the **Broadcast camera height and position** during a match, allowing each stadium to have a camera angle tuned to its specific geometry and stand layout.

### Prerequisites

- The in-game camera must be set to **Broadcast** in FIFA 16's camera settings.
- The `musedata-match.big` file must be the original or only modified for zoom changes. Free-position adjustments (height, lateral offset) are driven exclusively by the `bcgameplay_*` files and do not require modifying `musedata-match.big`.

### Per-Stadium Setup

Create a `GameplayCamGBD/` folder inside each stadium folder in `StadiumGBD/` and place both files inside it:

```text
StadiumGBD/
  ENG - Luton Town - Kenilworth Road/
    GameplayCamGBD/
      bcgameplay_176.dat
      bcgameplay_261.dat
    EntranceScene/
    1/
    3/
    model.rx3
    texture_day.rx3
    ...
```

Both files must be present. They should contain identical content — the game assigns injection ID 176 or 261 at runtime and reads the matching file, so both need to carry the same camera data.

### Automatic Application

When a stadium loads, the app copies both files from the stadium's `GameplayCamGBD/` folder to:

```text
data/bcdata/camera/bcgameplay_176.dat
data/bcdata/camera/bcgameplay_261.dat
```

No manual action is needed. If the stadium folder does not contain `GameplayCamGBD/`, the files in `data/bcdata/camera/` are left unchanged.

## Kit Mixer

The **Kit Mixer** tab lets you build a custom kit per team and kit type (home/away/keeper/third) without hand-editing `.rx3` files:

- Mix a jersey texture from one kit source with the shorts/socks from a different source, applied live to `data/sceneassets/kit/`. Pick a matching crest source alongside the jersey when mixing across teams, to avoid two badges rendering on top of each other.
- Swap kit numbers and the kit-selection UI thumbnail per team/kit type independently of the jersey texture.
- Pick a jersey name text color with a color picker, including ready-made swatches parsed from any Lua bundled with the kit source.
- Use the restore manager to selectively revert exactly what you changed (texture, numbers, UI thumbnail, or name color) for one team + kit type, without touching the rest.

Kit Mixer requires the same 32-bit `FifaLibrary16.dll` bridge as database reading and BH regeneration — see [FIFA Database Reading (32-bit Bridge)](#fifa-database-reading-32-bit-bridge) above.

⚠ **Known limitation — kit numbers / name color on a vanilla install:** the per-team kit number override and the jersey name color patch only take effect in-game through `assignKitDetails(...)`/`GetRMNumberSet(...)`, which live in CGFS's bundled `player.lua`. That file is only installed if you check **"Rev Mod Lua Assets"** in the Setup tab's Extra section (unchecked by default) — leave it unchecked on a plain vanilla install and Kit Mixer's kit-number and name-color changes are silently ignored in-game, even though Kit Mixer itself reports them as applied. Checking it, however, also installs CGFS's bundled `general.lua`, which sets the *global* kit-number identifier scheme — this can make every **other** team's kit numbers (any team you haven't touched in Kit Mixer) show a checkerboard/missing texture if your kit-number font pack expects the other scheme; toggle **"Enable custom kit numbers"** (same Extra section) to switch schemes if that happens. Total-conversion mods like FIP aren't affected — they ship their own already-compatible Lua, so the Rev Mod checkbox isn't needed (or recommended) there at all.

### `FSW/Kits` Package Structure

Kit Mixer looks for source kits under `FSW/Kits/<name>/`, where `<name>` is either the team's raw numeric ID or a friendly folder name mapped to that ID via `settings.ini [kitsid]` (the same mechanism used for chants' `[chantsid]`, edited from the asset settings editor):

```text
FSW/Kits/<name>/
  sceneassets/kit/kit_<team_id>_<kittype>_<tourn_id>.rx3
  sceneassets/kitnumbers/specifickitnumbers_<team_id>_<jerseyOrShorts>_<tourn_id>_<kittype>.rx3
  ui/imgAssets/kits/j<kittype>_<team_id>_0.dds
  fifarna/lua/assignments/teams/<any-name>.lua        (optional)
```

`kittype` is `0` = home, `1` = away, `2` = keeper, `3` = third; `tourn_id` is normally `0` (the tournament-agnostic slot the engine falls back to).

Notes:

- At least one `.rx3` under `sceneassets/kit/` is required before Kit Mixer can mix that team + kit type — it's used as the template whose non-mixed parts (e.g. the badge decal) are kept.
- If `FSW/Kits/` has nothing for a team, Kit Mixer falls back to whatever is already live under `data/sceneassets/kit/` — which is exactly what the Assets Extractor (below) can populate, so running its "Extract Selected → Kit Textures" once is a quick way to get a valid template for every team without needing a community kit pack first.
- Any `.lua` dropped under `fifarna/lua/assignments/teams/` doesn't need to reference the same team ID — Kit Mixer only scans it for `assignKitDetails(...)` calls to offer as ready-made jersey-name-color swatches, regardless of which team the file was originally written for.

## Assets Extractor

The Setup tab's **Assets Extractor** card, backed by the standalone `bin/KitExtractorHost.exe`, unpacks vanilla game content into loose files — which is what makes Kit Mixer changes to that content apply without restarting FIFA:

- **Database** — a one-time "Extract Database" bootstrap that copies a template `fifa_ng_db.db` into place for clean vanilla installs that don't ship one as a loose file. Every other extraction requires this to already be done, and the button locks itself once a database exists so a modded/edited one is never silently overwritten.
- **Kits** — extracts, for the whole roster, kit textures (jerseys/shorts/keeper kits), kit-selection UI thumbnails, and kit numbers (shared glyph sheets plus the rare per-team override a handful of licensed clubs ship — a high failure count on that second part is normal). Checkboxes under one **"Extract Selected"** action.
- **Team Logos** — extracts the small crest images shown on the Dashboard and in-game overlay.

⚠ **Recommended for vanilla installs only** — extracting over a total-conversion mod (e.g. FIFA Infinity) can overwrite and corrupt its custom content.

Extraction doesn't regenerate BH by itself — run **Regen BH** (Installer tab) afterward so the extracted/replaced files actually show up in-game without restarting it. See [FIFA Database Reading (32-bit Bridge)](#fifa-database-reading-32-bit-bridge) above for the native binaries this tool needs.

## Custom Substitutions

The **Substitutions** control on the Matchup Live card lets you raise FIFA 16's hardcoded 3-substitution-per-match limit:

1. Enter a value from 1–9 and press **Confirm**. Only 1–5 have been validated in live testing (vanilla and FIP installs, kickoff and tournament modes) — values above 5 are available but flagged as unverified.
2. The app waits for the match to reach a point where it can safely arm the change, then applies your chosen count for **both teams** — it automatically keeps waiting for the second team's first substitution if only one side was caught in time.
3. Check **"Auto-apply every match"** to have this re-armed automatically at the start of every match instead of pressing Confirm each time.

Status messages (`Waiting for match…`, `Armed…`, `Unrecognized FIFA build…`, etc.) report progress in real time. Safety checks run before anything is written to FIFA's memory, and the feature aborts without making changes if it can't verify it's safe to proceed.

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
- `RELEASE_NOTES_v<version>.md`
- release notes summarizing major fixes and improvements
- optional screenshots or changelog excerpts

Previous release notes: [v1.2.0](RELEASE_NOTES_v1.2.0.md) · [v1.3.0](RELEASE_NOTES_v1.3.0.md) · [v1.3.1](RELEASE_NOTES_v1.3.1.md) · [v1.4.0](RELEASE_NOTES_v1.4.0.md) · [v1.5.0](RELEASE_NOTES_v1.5.0.md)

## Credits

- Original concept and workflow: CGFS 16 Server 16 for FIFA 16
- Python port and ongoing maintenance: this community project and its contributors
- Support development: [Donate via PayPal](https://paypal.me/michellmk)

## Disclaimer

This project is an unofficial community tool for FIFA 16 modding workflows. Use it at your own risk and always keep backups of important game and mod files.
