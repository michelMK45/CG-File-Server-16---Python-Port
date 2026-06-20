# CGFS 16 Server 16 Python Port v1.3.1

## Highlights

- **In-game toast notifications** — the overlay now shows compact pop-ups when FIFA attaches and when assets (scoreboard, TV logo, movie, camera, goalposts) are loaded.
- **Keep open after game exits (useful for RFS)** — new toggle to prevent the server from closing automatically when the game process ends.
- **Left stick navigation** in the overlay menu (in addition to right stick and D-pad).
- **Log filter checkboxes** — hide Pointer trace and DiscordRPC entries from the log view.
- **App Options section label** in the Modules card to distinguish app-level toggles from the settings.ini module list.
- Fix: stadium textures sometimes loading with incorrect colors (green/blue texture bug).
- Fix: compressed scoreboards (zip/rar) were not being extracted after the app.py refactor.

## New Features

### In-Game Toast Notifications
A new stackable toast notification system (up to 6 simultaneous slots) renders pop-ups inside the overlay for:

| Event | Notification |
|---|---|
| FIFA 16 attached | FIFA Attached — Server connected to FIFA 16 |
| Scoreboard loaded | Scoreboard |
| TV Logo loaded | TV Logo |
| Movie loaded | Movie |
| Gameplay camera loaded | Gameplay Camera |
| Goalposts loaded | Goalposts |

Toasts respect the existing *Show loading notification* toggle. Each slot is independently shown and hidden.

### Keep Open After Game Exits
A new **Keep open after game exits** toggle in the Modules card lets the server stay running when the FIFA 16 process closes, instead of shutting down automatically. The setting is persisted to `settings.ini`.

### Left Stick Overlay Navigation
The overlay menu now accepts input from the **left analog stick** (LY axis) in addition to the existing right stick and D-pad support. Navigation includes acceleration for fast scrolling and repeat delay, consistent with the other axes.

### Log Filter Checkboxes
Two checkboxes in the Logs tab header let you filter noise without losing those entries in the log file:

| Checkbox | Effect |
|---|---|
| Hide Pointer traces | Hides high-frequency pointer read lines |
| Hide DiscordRPC | Hides Discord presence update lines |

### App Options Section Label
The **Modules** card now shows an **App Options** label above the application-level toggles (Show loading notification, Enable in-game overlay, Keep open after game exits), making it clear they are not part of the `settings.ini` module list.

## Fixes

- Fixed stadium textures occasionally loading with wrong colors (green or blue) due to a race condition in texture file copying.
- Restored zip/rar scoreboard extraction that was accidentally removed during the `app.py` refactor; compressed archives are now properly extracted before being applied.
- Runtime errors in individual modules (stadium, scoreboard, movie, etc.) are now isolated — a failure in one no longer aborts the rest of `apply_all_runtime`.
- Fixed overlay list rendering cutting off the last items behind the info panel.
- Fixed missing translation texts for the new asset notifications.
- `desktop.ini` and `Thumbs.db` files inside asset archives are now skipped during extraction to avoid Permission Denied errors.
- Attach notification display time extended from 7 s to 11 s.

## Internal

- Toast notification stack (`_ToastEntry` × 6 slots) added to the shared memory structure in `d3d_injector.py`; overlay DLL updated accordingly.
- `_get_gamepad_snapshot` helper extracts `sThumbLY` alongside the existing axes.
- `label.app_options` translation key added to all locale catalogs (EN / ES / PT).

## Release Asset

- `Server16Python.exe`
