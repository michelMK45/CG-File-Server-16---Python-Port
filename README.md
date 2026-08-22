<h1 align="center">CGFS 16 Server 16 Python Port</h1>

<p align="center">
  <a href="https://github.com/michelMK45/CG-File-Server-16---Python-Port/releases">
  <img alt="Github Downloads" src="https://img.shields.io/github/downloads/michelMK45/CG-File-Server-16---Python-Port/total?style=for-the-badge&logo=github">
  </a>
  <br>
</p>

⚠ This is a fork of the original project, continued by the community after the original author stopped developing the tool.

**CGFS 16 Server 16** is a Windows desktop control panel and in-game overlay for **FIFA 16** modding. It watches the game's live memory state while you play and automatically swaps in the right stadium, scoreboard, TV logo, movie, chants, camera package, and kit assets for the match you're about to play — no manual file-copying or alt-tabbing required. This is a full Python rewrite of the classic Server 16 tool, aimed at being easier for the community to maintain, fix, and extend.

## Features

### Live Match-Aware Asset Switching

The app attaches to FIFA 16's memory to read the current match context — home team, competition, round — and automatically applies whichever stadium, scoreboard, TV logo, movie, and chants you've assigned to that match. Assignments can be set by home team, round, tournament, or a default fallback, so there's no manual file-swapping before each match.

### In-Game Interactive Overlay

A fullscreen overlay renders directly on top of FIFA 16 — even in exclusive fullscreen — so you can assign assets without ever leaving the game.

- Open with **F12**, or hold **Start / Menu** on a gamepad for 0.6 seconds; press F12 again (or use the controller) to close it.
- Fully navigable with keyboard or controller, with on-screen button hints.
- Stadium assignment shows live preview images inline.
- Shows the active assignment mode (Round, Tournament, Home Team, or Default) for each asset type.
- Can be disabled entirely from the settings panel if you only want the desktop window.

### Stadium Management

- Assign stadiums per home team, round, or full tournament, plus randomized multi-stadium rotations.
- Load stadiums from a plain folder or from `.zip` / `.rar` archives — archives are extracted on the fly to a temp folder and cleaned up automatically afterward.
- Optional preview images shown on the dashboard, the Assign Stadium window, and the loading modal.
- Per-stadium gameplay camera overrides so the Broadcast camera's height/position can be tuned to each stadium's own geometry.
- Per-stadium goalpost files, crowd-chair replacement (`NoSeats.rx3`), and stadium-specific movies/bumpers.

### Camera Packages

Supports Anth's FIFA 16 AIO Camera Mod Package out of the box. Presets are auto-discovered with their own preview images, applied with one click, and `REGENERATOR.exe` is launched automatically afterward if it's present next to your FIFA install.

### Kit Mixer

Build a custom kit per team and kit type (home / away / keeper / third) without hand-editing `.rx3` files:

- Mix a jersey texture from one kit source with the shorts/socks from a different source, applied live.
- Swap kit numbers and the kit-selection UI thumbnail independently of the jersey texture.
- Pick a jersey name text color, including ready-made swatches parsed from any Lua bundled with the kit source.
- Selectively restore exactly what you changed — texture, numbers, thumbnail, or name color — for one team + kit type, without touching the rest.

### Assets Extractor

Unpacks vanilla FIFA game content (database, kit textures/numbers/thumbnails, team logos) into loose files, which is what lets Kit Mixer changes apply without restarting FIFA. Recommended for vanilla installs only — extracting over a total-conversion mod can overwrite and corrupt its custom content.

### Custom Substitutions

Raise FIFA 16's hardcoded 3-substitution-per-match limit to anywhere from 1–9 (1–5 have been validated in live testing). The app arms the change automatically at the right point in the match and applies it for both teams, with real-time status messages and an optional "auto-apply every match" toggle.

### Chants & Audio

Assign per-team/tournament chants and anthems under `FSW/Chants`, played back through the app's own audio engine during matches, including held goal-song playback that doesn't overlap the regular chants loop.

### Discord Rich Presence

Optionally shows your current match, teams, and stadium in your Discord status via local IPC — fully optional, and entirely local/private (no data leaves your machine except to your own Discord client). See [DISCORD_SETUP.md](DISCORD_SETUP.md) for setup.

### Assignment & Settings Editors

Built-in editors read and write `FSW/settings.ini` directly from the UI: stadium/scoreboard/TV logo/movie assignments, excluded competitions or rounds, stadium net values, scoreboard display names, and chants entries — changes apply back into the running app immediately where possible.

## Screenshots

Main overlay:

<img alt="Screenshot_2" src="https://i.ibb.co/Dq9hf5p/image.png" />

<img alt="Screenshot_1" src="https://i.ibb.co/845Kjjtz/image.png" />

<img alt="Screenshot_3" src="https://i.ibb.co/ymQqhYLp/image.png" />

## Project Status

This repository is public and open for community contributions.

The goal is to preserve and evolve the FIFA 16 Server 16 experience in a modern Python codebase that is easier to maintain, improve, and extend.

## Getting Started

1. Download the latest `Server16Python.exe` from [Releases](https://github.com/michelMK45/CG-File-Server-16---Python-Port/releases) — or run it from source, see [Running From Source](#running-from-source) further down.
2. Point it to your `FIFA 16.exe` if it isn't auto-detected.
3. Let it detect the game folder and related `FSW`, `StadiumGBD`, `ScoreBoardGBD`, `TVLogoGBD`, `MoviesGBD`, and other data folders.
4. Start FIFA 16, then use the tool in normal window mode or arm the in-game overlay.

The app stores local settings in `runtime/settings.json` and reads/writes Server 16 assignment data from `FSW/settings.ini` inside the detected FIFA 16 folder.

**Requirements to run:** Windows, FIFA 16 installed locally.

## Antivirus / Windows Defender Warnings

CGFS injects a DLL into FIFA 16's process to render its in-game overlay, and directly reads/writes FIFA's process memory to apply live match data — the Custom Substitutions feature additionally patches a small piece of executable code inside `fifa16.exe` to lift its 3-substitution limit. These are exactly the kind of API calls (`VirtualAllocEx`, `WriteProcessMemory`, `CreateRemoteThread`, remote code patching) that Windows Defender's behavioral/ML detection flags as **process injection / defense evasion**, even though nothing here touches any other process, reads personal data, or persists once FIFA closes. A detection named something like `Behavior:Win32/DefenseEvasion.A!ml` is this false positive, not a sign the download is compromised.

**Before running `Server16Python.exe` for the first time**, add an exclusion for it (and its folder) in Windows Security → Virus & threat protection → Manage settings → Add or remove exclusions. Adding the exclusion *after* Defender has already acted on a detection may not be enough — Defender's remediation can also affect the FIFA process it was attached to at the time (shown as a second `process:` entry in the detection details), which can leave FIFA unable to start ("Could not finish loading FIFA data") even once CGFS itself is trusted again. If that happens:

1. Check Windows Security → Protection History for **every** entry tied to that detection, not just the one for `Server16Python.exe` — something under your FIFA install may have been quarantined or reverted too.
2. Verify/repair your FIFA 16 game files through your launcher (Steam/Origin/EA App) to restore anything Defender touched.
3. Add the exclusion for both the CGFS folder and the FIFA 16 install folder, then relaunch.

## Detailed Guides

Reference material for setting up content packs and getting the most out of specific features. Read the [Features](#features) section above first if you just want the overview.

### Expected FIFA Folder Layout

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

### Stadium Preview Images

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

### Chants Audio Files

Per-team chants are assigned via `settings.ini [chantsid]` (edited from the asset settings
editor) and read from:

```text
FSW/Chants/<folder>/Support/*.mp3
FSW/Chants/<folder>/Complaint/*.mp3
FSW/Chants/<folder>/ClubSong.mp3
```

- `Support` covers a draw, winning, or losing by 1–2 goals (a different configured volume for
  each case).
- `Complaint` only plays when the team is losing by 3 goals or more — it's normal to rarely hear
  it in a typical match.
- `ClubSong.mp3` is the goal celebration anthem, held for at least 12s (or the track's own
  length if longer) before crowd chants resume.

Each `chantsid` entry is a 10-field CSV: `folder, vol_draw, vol_winning, vol_losing1, vol_losing2,
vol_complaint, vol_goal, silence_probability, silence_max_seconds, away_chant_probability`.

**MP3 compatibility — check this before adding new packs.** Playback goes through Windows' legacy
MCI (`mciSendStringW`, opened as `type mpegvideo`), not a modern MP3 decoder, and it is far less
tolerant of unusual file packaging than something like VLC or a phone. A file that plays fine
everywhere else can still make MCI refuse to open it, and the app has **no visible error for
this**: the track is silently skipped forever (retried every ~0.5s, always failing) while the
Chants tab freezes on whatever status was last shown. The only trace is in
`runtime/server16.log`, as a repeating `Chants monitor error: MCI command failed (277): open "...`
line.

The confirmed trigger, across two independently failing files: the leading **ID3v2 tag itself**
— not its size. One failing file had an oversized tag (~76% of file size, a large embedded cover
image); a second failing file had a perfectly ordinary tag (~0.8% of file size, no obvious defect
in the audio frames either — verified frame-by-frame end to end with no desync). Both were fixed
the same way, and isolated testing on the second file confirmed it precisely: stripping only the
leading ID3v2 tag fixed it, while stripping only the trailing ID3v1 tag (and leaving ID3v2 in
place) did not. **Tag size is not a reliable predictor** — a small, unremarkable-looking ID3v2 tag
can still make MCI refuse the file, presumably over some specific frame/encoding inside it that
this legacy driver's parser doesn't like. If a newly added chant never seems to play and the log
shows the error above:

1. Click **Fix Chant Audio Files** on the Chants tab (next to Edit Chants Settings). It walks
   every `.mp3` under `FSW/Chants`, strips any leading ID3v2 tag in place, and keeps a
   `<name>.original.mp3` backup of anything it touches — safe to run any time, including after
   adding a new pack, and safe to run repeatedly (already-clean files are left alone).
2. If you'd rather fix a single file by hand instead: strip its ID3v2 tag entirely (embedded
   artwork included) with any tag editor (Mp3tag) or
   `ffmpeg -i in.mp3 -map_metadata -1 -id3v2_version 0 -c copy out.mp3`, then replace the file and
   try again.

As a rule of thumb for any new pack: run **Fix Chant Audio Files** after adding it, rather than
only reaching for it once a specific team's chant is confirmed silent — a normal-looking tag is
not proof the file will open.

### Stadium Folder And Archive Loading

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

### Camera Packages

The Camera tab supports the exact package folder named:

```text
Anth's FIFA 16 AIO Camera Mod Package
```

The folder must contain `Instructions.txt`. Each camera preset is discovered from a child folder with a `data/` directory, and any `.png` files in that preset folder are used as preview images.

When a camera is applied, the preset's `data/` contents are synced into the FIFA `data/` folder. If `REGENERATOR.exe` is found next to the selected FIFA install, the app attempts to launch it after copying the files.

### Gameplay Camera Files

The app supports per-stadium gameplay camera overrides using `bcgameplay_176.dat` and `bcgameplay_261.dat`. These files control the **Broadcast camera height and position** during a match, allowing each stadium to have a camera angle tuned to its specific geometry and stand layout.

**Prerequisites**

- The in-game camera must be set to **Broadcast** in FIFA 16's camera settings.
- The `musedata-match.big` file must be the original or only modified for zoom changes. Free-position adjustments (height, lateral offset) are driven exclusively by the `bcgameplay_*` files and do not require modifying `musedata-match.big`.

**Per-Stadium Setup**

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

**Automatic Application**

When a stadium loads, the app copies both files from the stadium's `GameplayCamGBD/` folder to:

```text
data/bcdata/camera/bcgameplay_176.dat
data/bcdata/camera/bcgameplay_261.dat
```

No manual action is needed. If the stadium folder does not contain `GameplayCamGBD/`, the files in `data/bcdata/camera/` are left unchanged.

### Kit Mixer — `FSW/Kits` Package Structure

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
- If `FSW/Kits/` has nothing for a team, Kit Mixer falls back to whatever is already live under `data/sceneassets/kit/` — which is exactly what the Assets Extractor can populate, so running its "Extract Selected → Kit Textures" once is a quick way to get a valid template for every team without needing a community kit pack first.
- Any `.lua` dropped under `fifarna/lua/assignments/teams/` doesn't need to reference the same team ID — Kit Mixer only scans it for `assignKitDetails(...)` calls to offer as ready-made jersey-name-color swatches, regardless of which team the file was originally written for.

Kit Mixer requires the same 32-bit `FifaLibrary16.dll` bridge as database reading and BH regeneration — see [FIFA Database Reading (32-bit Bridge)](#fifa-database-reading-32-bit-bridge) further down.

⚠ **Known limitation — kit numbers / name color on a vanilla install:** the per-team kit number override and the jersey name color patch only take effect in-game through `assignKitDetails(...)`/`GetRMNumberSet(...)`, which live in CGFS's bundled `player.lua`. That file is only installed if you check **"Rev Mod Lua Assets"** in the Setup tab's Extra section (unchecked by default) — leave it unchecked on a plain vanilla install and Kit Mixer's kit-number and name-color changes are silently ignored in-game, even though Kit Mixer itself reports them as applied. Checking it, however, also installs CGFS's bundled `general.lua`, which sets the *global* kit-number identifier scheme — this can make every **other** team's kit numbers (any team you haven't touched in Kit Mixer) show a checkerboard/missing texture if your kit-number font pack expects the other scheme; toggle **"Enable custom kit numbers"** (same Extra section) to switch schemes if that happens. Total-conversion mods like FIP aren't affected — they ship their own already-compatible Lua, so the Rev Mod checkbox isn't needed (or recommended) there at all.

### Assets Extractor Details

The Setup tab's **Assets Extractor** card, backed by the standalone `bin/KitExtractorHost.exe`, unpacks vanilla game content into loose files — which is what makes Kit Mixer changes to that content apply without restarting FIFA:

- **Database** — a one-time "Extract Database" bootstrap that copies a template `fifa_ng_db.db` into place for clean vanilla installs that don't ship one as a loose file. Every other extraction requires this to already be done, and the button locks itself once a database exists so a modded/edited one is never silently overwritten.
- **Kits** — extracts, for the whole roster, kit textures (jerseys/shorts/keeper kits), kit-selection UI thumbnails, and kit numbers (shared glyph sheets plus the rare per-team override a handful of licensed clubs ship — a high failure count on that second part is normal). Checkboxes under one **"Extract Selected"** action.
- **Team Logos** — extracts the small crest images shown on the Dashboard and in-game overlay.

⚠ **Recommended for vanilla installs only** — extracting over a total-conversion mod (e.g. FIFA Infinity) can overwrite and corrupt its custom content.

Extraction doesn't regenerate BH by itself — run **Regen BH** (Installer tab) afterward so the extracted/replaced files actually show up in-game without restarting it. See [FIFA Database Reading (32-bit Bridge)](#fifa-database-reading-32-bit-bridge) further down for the native binaries this tool needs.

### Custom Substitutions Details

The **Substitutions** control on the Matchup Live card lets you raise FIFA 16's hardcoded 3-substitution-per-match limit:

1. Enter a value from 1–9 and press **Confirm**. Only 1–5 have been validated in live testing (vanilla and FIP installs, kickoff and tournament modes) — values above 5 are available but flagged as unverified.
2. The app waits for the match to reach a point where it can safely arm the change, then applies your chosen count for **both teams** — it automatically keeps waiting for the second team's first substitution if only one side was caught in time.
3. Check **"Auto-apply every match"** to have this re-armed automatically at the start of every match instead of pressing Confirm each time.

Status messages (`Waiting for match…`, `Armed…`, `Unrecognized FIFA build…`, etc.) report progress in real time. Safety checks run before anything is written to FIFA's memory, and the feature aborts without making changes if it can't verify it's safe to proceed.

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

---

## For Developers

Everything below is about building and working on the codebase itself — not needed just to run the app.

### Repository Structure

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

### Requirements

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

### Running From Source

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

Running from source also requires the native binaries described in [Overlay Requirements](#overlay-requirements) below and in [FIFA Database Reading (32-bit Bridge)](#fifa-database-reading-32-bit-bridge) above to already be present in `bin/` for overlay/DB/kit features to work — they are not fetched by `pip install`.

### Overlay Requirements

The overlay uses native C++ helpers (`bin/cgfs16_overlay.dll` and `bin/cgfs16_inject.exe`) that ship with the release build. Running from source requires these binaries to be present in the `bin/` folder. The build script (`build_exe.bat`) compiles them when Visual Studio C++ tools are available.

### Building The EXE

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
