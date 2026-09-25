# CGFS 16 Server 16 Python Port v1.6.0

## Highlights

- **F12 overlay menu rebuilt on RmlUi** — the entire hand-rolled D3D11 menu renderer was replaced
  with an RmlUi-based one: a draggable/resizable window, an animated tab glider, full mouse
  support (click/drag on tabs, rows, and the scrollbar), and live preview/video panels for every
  asset type.
- **Team Entrance** — an optional per-home-team `Entrance.mp3` now plays during FIFA's pre-kickoff
  3D walkout, through its own independent audio player so it never competes with the regular
  chants loop.
- **Kit Sets** — apply a full kit (jersey + numbers + thumbnail, with an optional linked
  goalkeeper kit) in one click from a new "Simple" Kit Mixer tab, or cycle through them in-game
  with F7–F11.
- **Manual in-game stadium picker** — turn off random stadium selection and pick from a
  scrollable, thumbnail-backed in-game list instead; a team/round/tournament can now hold more
  than one stadium with individually-editable Police/Pitch/Net/Goalpost values per stadium.
- **Four new asset modules** — Ball, Referee, Wipe, and Adboard packages, assignable per
  round/tournament from the Settings Editor.
- **Live previews everywhere** — the Settings Editor, asset dialogs, and the F12 overlay's
  Scoreboards/TV Logos/Movies tabs now show a real preview image or playable video for whatever
  you're about to assign, instead of just a filename.
- **`scoreboardstdname` finally renders in-game** — after extensive live investigation, the custom
  pre-match stadium-name override now actually shows on FIFA's presentation screen (it previously
  wrote successfully to memory with zero visible effect).
- **Settings Export/Import** — share stadium/scoreboard/chants/etc. bindings as a standalone
  `.ini` file, with an explicit Replace/Merge choice and a conflict preview on import.
- **Gamepads tab** — bridge up to 4 physical controllers (non-Xbox pads)
  into virtual Xbox 360 pads so FIFA reads them correctly, with an optional HidHide layer that
  hides the raw pad from FIFA and a live controller test panel.
- **League Logos extraction** and new browsable **Team Picker** / **Stadium Picker** dialogs with
  crest/logo previews.

## New Features

### Major Features

#### F12 Overlay Menu: RmlUi Rewrite
The entire in-game F12 menu — tabs, dashboard, item lists, scrollbar, wizard header, split
preview, hint bars — is now rendered by RmlUi instead of a hand-rolled D3D11 renderer
(`cgfs16_overlay.cpp` shrank from ~1770 to ~770 lines with the old rendering pipeline removed).
This unlocked several follow-up upgrades in the same cycle:
- The panel can be **dragged and resized** like a real window, and remembers its position/size
  across close/reopen.
- **Full mouse support** — click tabs, rows, and the scrollbar directly; the tab indicator now
  glides smoothly to whatever's hovered or selected.
- A live **scoreboard widget** (both crests, score, match clock) on the dashboard.
- A new **country filter panel** on the Stadiums tab (gamepad Y or a mouse "Filter" button) —
  multi-select by country code, plus an A-Z/Z-A sort toggle.
- Live previews were extended to the Scoreboards, TV Logos, and Movies tabs, including real
  playing video with audio and a mute toggle for movies.

⚠ **Known limitation, carried over from the old renderer:** a mouse click can still also reach
FIFA's own menu underneath while the overlay is open, since FIFA reads mouse input through
exclusive DirectInput rather than window messages. Mouse works fine for navigating the CGFS menu
itself — just be mindful of where you click on screen while it's open.

#### Team Entrance (New)
An optional per-home-team walkout anthem: drop `Entrance.mp3` under `FSW/Chants/<team>/` and it
plays through its own independent audio player during FIFA's pre-kickoff 3D walkout, fading out
the instant real kick-off is detected. Configured from the same Chants editor as regular chants
(its own volume and delay fields). Toggle it from the Modules card.

#### Kit Sets
A new **Simple** tab in Kit Mixer (alongside the existing **Advanced** one) lets you pick a
ready-made kit set — jersey, numbers, and UI thumbnail together — and apply it in one action, with
an optional linked goalkeeper kit per tournament. A new in-game overlay tab ("Kits") walks through
scope → kit type → kit set the same way the Stadiums tab does, and **F7/F8** (home prev/next),
**F9/F10** (away prev/next), and **F11** (cycle kit type) let you cycle through them without
opening the menu at all, shown as a stacked carousel with prev/current/next thumbnails.

#### Manual In-Game Stadium Picker & Multi-Stadium Assignments
A new **"Random stadium selection"** toggle (on by default, preserving prior behavior) — turn it
off and, whenever a team/round/tournament has more than one stadium assigned, an in-game picker
panel opens instead of a random pick. The assignment model backing this now supports more than
one stadium per key with independent Police/Pitch/Net/Goalpost values each, editable from a new
Assigned/Available two-list UI in the Settings Editor, matching the in-game picker's ordering
(64-item cap).

#### New Asset Modules: Ball, Referee, Wipe, Adboard
Four new ini-only asset modules, each assignable per round/tournament from the Settings Editor
exactly like Scoreboard/TV Logo/Movies already were:
- **Ball** (`data/sceneassets/ball`)
- **Referee** kits (`data/sceneassets/kit`)
- **Wipe** (transition animations, `data/sceneassets/wipe3d`)
- **Adboard** (`data/sceneassets/adboard`, plus corner-flag routing), which also supports a
  per-stadium `FSW/adboards/<stadium>` folder taking priority over the round-based assignment.

Each has its own Setup tab checkbox and warns if assets are assigned while its module is switched
off. Ported from a community contributor's fork.

#### Live Previews & Reveal in Explorer
The Settings Editor and asset dialogs (Assign Movie, Assign Stadium, etc.) now show a real preview
— a playable video for movies (autoplaying, with a volume slider and fullscreen button), per-track
play/stop for chants, and thumbnail images for stadiums/scoreboards/TV logos/pitch/net/police —
instead of just a filename. A new **"Reveal in Explorer"** button opens the currently selected
asset's folder or archive directly.

In the Assign Stadium window and the Settings Editor's Stadium Settings tab, the Police / Pitch /
Net / Goalpost Model / Goalpost Texture dropdowns also get a small **▦** button that opens a grid of
every option with its preview and name, so you can pick visually instead of stepping through the
dropdown one value at a time.

#### Settings Export / Import
Share stadium/scoreboard/chants/etc. bindings between installs: export selected `settings.ini`
sections to a standalone `.ini` file, then import it back on another install with an explicit
**Replace** (clears the section first) or **Merge** (only fills in missing keys) choice, and a
conflict preview before anything is overwritten.

#### League Logos & Team/Stadium Picker Dialogs
The Assets Extractor can now pull league logos (`data/ui/imgassets/league/`) alongside kits and
team crests. New browsable **Team Picker** and **Stadium Picker** dialogs, with crest/logo
previews and search, replace plain dropdowns in Kit Mixer's "Pick Team" flow and elsewhere.

#### Gamepads Bridge (ViGEmBus + HidHide)
A new **Gamepads** tab translates up to 4 physical controllers into virtual Xbox 360 pads through
ViGEmBus/`vgamepad`, since FIFA 16 only reliably reads XInput input. It is app-level (starts with
the app, not gated on FIFA running) and stores its config in `runtime/settings.json`.
- **Install/Uninstall Driver** buttons for ViGEmBus and HidHide (UAC elevation, real install state
  re-checked afterwards), each with a link to the official repository; ViGEmBus falls back to the
  installer vendored inside `vgamepad`.
- **Hide from FIFA** (per slot, optional) uses HidHide to cloak the physical pad from `fifa16.exe`,
  because FIFA was confirmed to also read the raw device directly, causing garbled/phantom input.
- **Test** button opens a live (~30Hz) panel showing raw physical input next to the translated
  Xbox output; identical pads are resolved per slot.
- **Remove** button resets a slot and lifts its HidHide cloak unless another slot of the same model
  still needs it.
- ViGEmBus and HidHide are credited in the About dialog. Hide-from-FIFA is not yet re-confirmed
  live against a real FIFA session.

#### Kit UI Thumbnail Import from PNG/JPG
Kit Mixer can now bake a loose `.png`/`.jpg` image directly into a kit-selection UI thumbnail via
a new 32-bit bridge, using `FifaLibrary`'s `DdsFile.ReplaceBitmap` — no more hand-preparing `.dds`
files just to customize a kit-selector thumbnail.

### Quality of Life / Secondary Features

- **Dedicated Settings tab** — "App Options" split off the Dashboard's Modules card into its own
  tab with separate App Settings and Overlay Settings cards, plus hover tooltips for the less
  obvious toggles.
- **UI zoom control** — a magnifying-glass popup (-/%/+) scales fonts, widget sizing, and
  window/dialog geometry app-wide.
- **New notification style with icons.**
- **Keyboard hint icons** — the overlay's keyboard hint bar now shows real key icons instead of
  text badges, matching the existing gamepad icon hint bar.
- **Overlay performance mode** — skips stadium thumbnail/preview rendering in the overlay for
  lower-end setups.
- **Goalpost Model & Texture packs** — a stadium's goalpost can now be overridden with two
  independent, freely mixable packs instead of one bundled folder: a **Model**
  (`FSW/Goalpost/GoalpostModel/<name>/`) and a **Texture/Color**
  (`FSW/Goalpost/GoalpostColor/<name>/`), each pickable per stadium name from both the Assign
  Stadium dialog and the Settings Editor's Stadium Settings tab, with its own preview — a static
  image for the model, a rendered texture preview for the color/net.
- **Chant audio auto-fix tool** — scans your Chants folder for MP3s with a leading ID3v2 tag that
  Windows' legacy MCI driver refuses to open, and strips it (with an optional backup).
- **Update-check badge** — a small red badge appears on "Check for Updates" a few seconds after
  launch if a newer release exists, instead of only surfacing status on a manual check.
- **FIFA install-location mismatch warning** — warns (and offers to close, or continue in an
  unsupported mode) if CGFS16 isn't running from the same folder as the linked `fifa16.exe`.
- **Launch and close splash screen** — a small loading window with the app icon, name/version and a
  spinner now shows while the app starts and again while it shuts down. The single-file `.exe` also
  shows a static splash while it unpacks, so there is no blank wait after double-clicking it.
- **Goalpost Model / Texture steps in the F12 overlay** — the Stadiums tab's assign wizard now
  continues past Police/Pitch/Net with **Goalpost Model** and **Goalpost Texture** steps, with the
  same previews and `None` option as the Assign Stadium dialog.
- **ImgBB API key setting** — a new "ImgBB API Key" button in Settings lets you configure the
  Discord stadium-preview uploader without editing `settings.json`; it applies without a restart.
- **"Clean Cache" button** (Setup tab) — clears generated goalpost/kit preview PNGs and
  kit-import temp files.
- **About dialog** now credits RmlUi and FreeType.

## Fixes

- **`scoreboardstdname` now actually renders in-game.** The custom pre-match stadium-name override
  previously wrote successfully to FIFA's process memory with no visible effect — the buffers it
  targeted don't feed the presentation screen at all. Replaced with a coordinator that scans
  FIFA's live memory for the vanilla stadium name and overwrites it in place, with proper isolation
  checks, real (not fixed) buffer-capacity probing, and a bounded retry loop; also widened the
  memory-scan cap from 512MB to 4GB so a heavily modded process's full working set actually gets
  scanned instead of silently truncated.
- **`scoreboardstdname` was intermittently late on the second match of a session.** The name
  buffer only exists once match loading starts and the pre-match screen reads it around the
  `TV/bumper` page, so slow scans could land after it was read. Scans now overlap instead of
  queueing, and a fast ~150ms watch of the known memory window patches it as soon as it appears.
- Fixed goalpost model/texture overrides (`[stadiumgoalpost]`/`[stadiumgoalposttexture]`) sticking
  to whichever pack loaded first: packs share fixed filenames, so they are now installed under
  per-slot (176/261) names, the same technique used for net colors.
- Fixed a flood of memory-read errors in the log during pre-match menus (a new process handle was
  opened on every read, and errors were never de-duplicated).
- Fixed the practice arena playing the chants of the match you had just abandoned: after Abandon →
  main menu → training, CGFS still saw the old match as running. Reaching the first out-of-match
  page (training/skill games/arena) now clears the live match state, chants, entrance anthem and
  substitution state once, until the next KickOffHub.
- Fixed the PyInstaller build missing `ViGEmClient.dll` (crash at startup of the built exe).
- Fixed stadium net color not updating between matches without restarting FIFA — the engine only
  re-reads the shared net texture file once per session, so a per-slot override path is now also
  written.
- Fixed several overlay input reliability issues: gamepad button presses and keyboard-hook edge
  cases that completed within a single ~40ms poll tick could be missed entirely; the left analog
  stick's X axis was never read, so filter grids couldn't be navigated left/right with the stick;
  the low-level mouse hook could swallow clicks on FIFA's own window chrome or another window's
  scroll-wheel input while the F12 menu was open.
- Fixed the F12 menu's mouse-wheel list navigation moving 3 items per notch instead of 1, which
  could feel reversed or random on short lists.
- Fixed multi-second UI freezes when quickly arrow-keying through the movie list in Assign Movie,
  by moving video decode off the Tk main thread onto its own worker thread.
- Fixed image previews being cropped to ~60px tall in the Settings Editor and asset dialogs.
- Fixed a stadium preview-thumbnail-only entry (no matching model/folder) being able to surface as
  a selectable stadium with nothing to actually copy on apply.

## Internal

- `cgfs16_rmlui.cpp/.h`, `cgfs16_rmlui_menu.cpp/.h` (new) — the RmlUi renderer and menu logic;
  `resources/rmlui/*.rml` loaded as loose files so content can be tweaked without recompiling.
- `kit_mixer.py` gained kit "packs"/Kit Sets (`FSW/Kits/<team>/packs/<name>/`) and `[kitgk]`
  linked-goalkeeper support; `dds_image_worker.py` (new) is the 32-bit PNG/JPG → DDS bridge.
- `stadium_runtime.py`'s `_parse_stadium_entries` now supports per-stadium Police/Pitch/Net/
  Goalpost triples instead of one shared triple per key.
- `team_picker_dialog.py`, `stadium_picker_dialog.py` (new, split out of `dialogs.py`).
- `video_preview.py` (new) — shared `ffpyplayer`-based movie preview widget, now running its
  decode loop on a dedicated worker thread; `movie_preview_runtime.py` (new) streams decoded
  frames into the D3D overlay via a second shared-memory channel (`OverlayVideoShared`).
- `match_string_patcher.py` gained `StadiumDbNamePatchCoordinator` for the `scoreboardstdname`
  fix; `memory_access.py`'s safe-write helpers now measure real buffer slack instead of a fixed
  cap.
- `ini_file.py` gained `import_sections()` (Replace/Merge); `KitExtractorHost.cs` gained a
  `leaguelogo` extraction mode and a second `DbFile` handle for the `leagues`/`leagueteamlinks`
  tables.
- `gamepad_bridge_runtime.py`, `hidhide_runtime.py`, `win_elevation.py`, `gamepad_test_dialog.py`
  (new); `Server16Python.spec`/`build_exe.bat` bundle `bin/ViGEmBus`, `bin/HidHide` and
  `vgamepad`'s data files.
- `en`/`es`/`pt` locale files updated throughout for all new UI strings.
- Rebuilt `bin/cgfs16_overlay.dll`, `bin/cgfs16_inject.exe`, `bin/KitExtractorHost.exe` from the
  updated native sources.
- Version bumped to `1.6.0`.

## Release Asset

- `Server16Python.exe`
