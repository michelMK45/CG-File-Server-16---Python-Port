# CGFS 16 Server 16 Python Port v1.4.0

## Highlights

- **New Setup tab** — one-click installation and repair with per-item status checks and checkboxes to customize what gets installed.
- **Dashboard setup notice** — an amber banner points new/incomplete installs to the Setup tab until every prerequisite folder is in place.
- **Rev Mod lua assets are now installed automatically** by Setup — required for custom stadium/scoreboard/TV logo/movie assets to load in-game.
- **In-game warnings for disabled modules** — if a module (TV Logo, Scoreboard, Movies, etc.) is turned off in settings but an assignment for the current match exists, the overlay now shows a toast warning that those assets were skipped instead of silently doing nothing.
- **Migrated from FifaLibrary14 to FifaLibrary16** for reading the FIFA t3db database and regenerating `.big` BH entries.
- **Database and BH regeneration now run in a dedicated 32-bit Python subprocess** instead of loading the (x86-only) DLL in-process via pythonnet — this removes the need for a 32-bit build of the main app.
- New `scripts/setup_python32.bat` provisions a bundled 32-bit Python embeddable automatically as part of `build_exe.bat`.
- Fix: a race condition that could make FIFA silently fall back to the vanilla default stadium when the game read the injection slot ID before a stadium's files had finished copying (176/261 mismatch bug).
- Fix: RAR stadium archives now extract correctly on machines without `unrar`/`7z` installed, by using the `tar` command bundled with Windows.
- Discord stadium preview uploads now back off for 5 minutes after a failure instead of retrying (and potentially spamming) immediately.

## New Features

### Setup Tab
A new **Setup** tab turns first-time installation and troubleshooting into a guided, one-click flow:

- **Run Setup** copies the bundled `install_data` (FSW nav/nets/pitch/police assets, a default `settings.ini` when one doesn't exist yet, and the Rev Mod lua asset files needed to load custom content) into the FIFA folder, then extracts the remaining FSW sources (police, nets, pitch, stadium, scoreboard, TV logo) directly from the game's `.big` archives, with a real progress bar reflecting actual extraction progress.
- **Checkboxes for custom install** let you skip individual FSW sources (settings.ini, Nav, police, nets, pitch, stadium, scoreboard, TV logo) instead of always doing a full install — useful for repairing a single broken piece without touching the rest.
- **Live status indicators** (● green/red or ○ neutral) show, per item, whether prerequisites, FSW sources, user asset folders (StadiumGBD, TVLogoGBD, ScoreBoardGBD, MoviesGBD), and destination game folders are present and populated.
- **Regenerate BH** (now backed by the 32-bit `bh_worker.py` bridge described below) is only enabled once the setup is detected as complete, and shows real per-file progress instead of a spinner.
- A **Refresh** button re-checks all statuses without re-running the install.

### Dashboard Setup Notice
Until every prerequisite is satisfied, the dashboard now shows an amber notice explaining what's missing and offering a **Go to Setup** button that jumps straight to the Setup tab. It disappears automatically once `_is_setup_complete()` confirms every FSW source, user folder, and destination folder exists.

### Disabled Module Warnings
Previously, disabling a module (e.g. TV Logo or Scoreboard) in the Modules card silently skipped applying that asset with no in-overlay feedback, even if an assignment existed for the current match. The overlay now shows a distinct warning-style toast (e.g. "TV Logo off — assets skipped") whenever a module is disabled *and* there was a real assignment that would otherwise have applied, so it's clear the missing asset is expected rather than a bug.

### 32-bit Subprocess Bridge for FifaLibrary16
`FifaLibrary16.dll` is x86-only, which previously required loading it in-process with `pythonnet`. That coupling is now replaced by two standalone worker scripts invoked through a dedicated 32-bit Python interpreter:

| Worker | Purpose |
|---|---|
| `server16_py/db_worker.py` | Reads team and stadium names from `fifa_ng_db.db` and prints the result as JSON. |
| `server16_py/bh_worker.py` | Regenerates BH entries for every `.big` file in the game directory, streaming JSON progress lines. |

`FifaDatabase.connect()` and the **Regenerate BH** action in the Setup tab now launch these workers via `subprocess`, parse their JSON output, and surface errors/progress in the UI exactly as before — the difference is invisible to end users.

### Bundled 32-bit Python (`scripts/setup_python32.bat`)
A new setup script downloads the official Python 3.9.13 x86 embeddable package, enables `site-packages`, installs `pip`, and installs `pythonnet` into `bin/python32/`. It is:

- Safe to re-run (no-ops if `bin/python32/python.exe` already exists).
- Wired into `build_exe.bat` as a build step, so packaged releases always ship a working 32-bit interpreter.
- Discoverable at runtime from the bundled `bin/python32/` folder, the Windows Python Launcher (`py -3-32`), or common x86 install paths, in that order.

## Fixes

- Fixed a race condition where the stadium injection slot ID could be written to game memory before the background file-copy job for that stadium finished, causing FIFA to read an empty/partial slot and silently load the vanilla default stadium instead. The injection ID is now written and verified only after the copy job fully completes.
- Fixed RAR archive extraction failing on systems without `unrar.exe` or `7z` installed — `rarfile` is now configured to use the `tar` (bsdtar) command that ships with Windows.
- Added a warning log when a stadium's model file is missing after copying, to help diagnose archive extraction issues.
- Discord stadium preview uploads that fail now enter a 5-minute cooldown before being retried, instead of being retried on every subsequent request.

## Internal

- `server16_py/fifa_db.py` rewritten to resolve the DLL, 32-bit interpreter, and worker script paths (bundled and source layouts) and delegate to `db_worker.py` over `subprocess`, instead of loading the CLR assembly directly.
- `_find_python32()` helper added to `app_ui.py` for locating a usable 32-bit interpreter ahead of BH regeneration.
- `Server16Python.spec` and `build_exe.bat` updated to bundle `FifaLibrary16.dll`, `bin/python32/`, `bh_worker.py`, and `db_worker.py` in packaged builds.
- `server16_py/big4_extractor.py` (new) extracts FSW sources directly from the game's `.big4` archives for the Setup tab's extraction step.
- `install_data/` now bundles the Rev Mod lua asset files, FSW `Nav`/`Images` (nets, pitch, police) content, and a default `settings.ini`, all copied into place by **Run Setup**.
- `asset_runtime.py`, `d3d_injector.py`, and the C++ overlay (`cgfs16_overlay.cpp`) gained a warning-style toast variant (`style=1`) used by the disabled-module notices.
- `DISCORD_SETUP.md` updated to reference `FifaLibrary16.dll`.
- Version bumped to `1.4.0`.

## Release Asset

- `Server16Python.exe`
