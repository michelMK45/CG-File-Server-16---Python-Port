# CGFS 16 Server 16 Python Port v1.3.0

## Highlights

- **About panel** with project links and community credits.
- **Overlay assignment mode labels** — the overlay now shows whether the active assignment comes from a Round, Tournament, Home Team, or Default rule.
- **Keyboard hint bar** in the overlay showing key shortcuts (UP/DOWN, Wheel, RIGHT/LEFT, Enter, Esc) alongside the existing gamepad hints.
- **Log auto-follow toggle** — scroll back through the log history at any time without losing your place; resume following with a single click.
- **Goal model import** — stadiums can now include GoalpostGBD files that are applied and cleaned up automatically.
- Stadium camera override files (`bcgameplay_*.dat`) are now properly removed when the loaded stadium does not include them.
- Stadium asset patterns (police, field/pitch) now load all available options instead of only the first one found.
- Code refactorization: `app.py` reduced from 4 000+ lines to ~620 by splitting into focused mixin modules.

## New Features

### About Panel
A new **About** button opens a dialog showing:
- Links to the GitHub repository, legacy GitHub, community Forum, and Trello board.
- A Credits section listing the original developer, collaborators, and special thanks to community members.

The dialog is fully localized (EN / ES / PT).

### Overlay Assignment Mode Labels
The in-game overlay now displays the **assignment rule that is active** for TV logos, scoreboards, movies, and stadiums. Each asset shows one of:
- **Round** — assigned by tournament round
- **Tournament** — assigned by tournament name
- **Home Team** — assigned by home team
- **Default** — falling back to the default rule

### Overlay Keyboard Hint Bar
The overlay now renders a **keyboard shortcut bar** at the bottom of the menu, mirroring the existing gamepad hint bar:

| Key | Action |
|---|---|
| UP / DOWN | Navigate items |
| Mouse Wheel | Scroll list |
| RIGHT / LEFT | Switch tab |
| Enter | Select |
| Esc | Back/Close |

### Log Auto-Follow Toggle
The Logs tab has a new **Auto-follow** checkbox. When checked (default), the log scrolls to the latest entry automatically. Unchecking it lets you browse history freely; re-checking resumes following.

### Goal Model Import
Stadium folders can now include a `GoalpostGBD/` subfolder. When present, those files are copied to the game's goal-net directory. A manifest file tracks which files were written so they are removed cleanly when the next stadium (without goalposts) loads.

## Fixes

- Fixed `bcgameplay_176.dat` and `bcgameplay_261.dat` not being removed when the loaded stadium does not include them — the app now restores the original files or deletes them as appropriate.
- Fixed police pattern and field/pitch mow pattern assets not showing all available options in the overlay and assignment dialogs.
- Fixed two simultaneous scrollbars appearing in the TVLogo / Scoreboard assignment window.

## Internal

- `app.py` was refactored from 4 000+ lines into six mixin modules (`app_localization`, `app_logging`, `app_ui`, `app_overlay`, `app_game`, `app_settings`) and a shared `win32_types` module. Runtime behavior is unchanged.
- `copy_bcgameplay` and `copy_goalpost` / `clear_goalpost` helpers added to `file_tools.py` for manifest-tracked file management.
- Assignment type resolution logic centralized in `asset_runtime.py`.

## Release Asset

- `Server16Python.exe`
