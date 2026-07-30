# CGFS 16 Server 16 Python Port v1.5.0

## Highlights

- **Custom Substitutions** — override FIFA 16's hardcoded 3-substitution-per-match limit (1–9,
  officially validated up to 5) live, while a match is in progress, with an optional "auto-apply
  every match" checkbox so you don't have to confirm it every kickoff.
- **New Kit Mixer tab** — mix a jersey texture from one kit source with the shorts/socks from
  another, per team and kit type, with support for kit numbers, kit-selection UI thumbnails, and
  a jersey name color picker, plus a restore manager to selectively revert individual modified
  kits instead of all-or-nothing per team.
- **New Assets Extractor** (Setup tab) — bulk-extracts kit textures, kit numbers, kit UI
  thumbnails, and team crests from FIFA 16's packed archives into loose files, and can bootstrap
  a missing `fifa_ng_db.db` for clean vanilla installs. This is also the fastest way to seed
  valid templates for Kit Mixer (see below).
- **Stadium preview placeholder** — stadiums without their own thumbnail now show a bundled
  generic stadium image instead of a blank box, in the dashboard, the Assign Stadium dialog, and
  the loading overlay. A donate link was also added to the About dialog.
- Fix: stadiums without their own entrance-camera or goalpost/goalnet files no longer leave the
  *previous* stadium's camera or goal model data active in the slot.
- Fix: mousewheel scrolling on the dashboard and Setup tab no longer fight over the same handler —
  each tab scrolls independently again.

## New Features

### Custom Substitutions
A new **Substitutions** control on the Matchup Live card lets you raise FIFA 16's hardcoded
3-substitution limit for the current match:

- Enter a value from 1–9 and press **Confirm**; the app installs a small, verified code-cave hook
  at a single, extensively pre-tested instruction inside `fifa16.exe` (never touching anything
  else), then waits for the match to reach a state where it can safely record where the
  substitutions-remaining value lives in memory before writing your chosen count.
- Handles **both teams independently** — the hook fires for whichever side substitutes first, so
  the app re-arms and keeps waiting (with a longer timeout) until the other team's first
  substitution has also been caught, rather than only fixing the side that happened to go first.
- An **"Auto-apply every match"** checkbox re-arms the hook automatically at the start of every
  match instead of requiring a manual Confirm each time.
- Values above 5 are exposed but flagged as unverified beyond that point, since only 1–5 were
  validated in live testing (vanilla and FIP installs, kickoff and tournament modes).
- Extensive safety checks are built in: the original bytes at the hook site are verified before
  any patch is written, the FIFA build is checked before touching memory, and clear status
  messages (`Waiting for match…`, `Armed…`, `Timed out…`, `Unrecognized FIFA build…`, etc.) report
  exactly what's happening at each step.

### Kit Mixer (New)
A brand new **Kit Mixer** tab, backed by `FifaLibrary16.dll` through the 32-bit `kit_worker.py`/
`kit_preview_worker.py` bridges, lets you build a custom kit per team and kit type
(home/away/keeper/third) without hand-editing `.rx3` files:

- **Mix jersey and shorts+socks independently** — pick one source `.rx3` for the jersey and a
  different one for the shorts/socks, and Kit Mixer combines them into a single output texture
  applied live to `data/sceneassets/kit/`. A matching crest source can be picked alongside the
  jersey to avoid two team badges rendering on top of each other when mixing across teams.
- **Kit numbers and kit-selection UI thumbnails** can be swapped per team/kit type independently
  of the jersey texture itself.
- **Jersey name color** — a color picker patches just the `namecolour` argument of that team's
  `assignKitDetails(...)` Lua call (the only place a kit's jersey name color lives; it's not part
  of the texture), offering ready-made swatches parsed from any Lua already bundled with the kit
  source. Kept as its own action since it lives in one shared per-team Lua file, not per kit type.
- **Per-kit-type restore manager** — every change is backed up as an `<original>.original.<ext>`
  sidecar the first time it's touched, independently per team + kit type + asset kind (texture,
  numbers, UI thumbnail), plus its own name-color restore (since that one is per-team, not per
  kit type). A restore manager popup lists every modified team/kit type combination and lets you
  revert exactly the piece you want — e.g. keep a mixed Home kit while reverting Away.
- See **[Kit Mixer: How To Structure An `FSW/Kits` Package](#kit-mixer-how-to-structure-an-fswkits-package)**
  below for where to place source kits so Kit Mixer can find them.

⚠ **Known limitation — kit numbers / name color on a vanilla install:** the per-team kit number
override and the jersey name color patch only take effect in-game through `assignKitDetails(...)`/
`GetRMNumberSet(...)`, which live in CGFS's bundled `player.lua`. That file is only installed if
you check **"Rev Mod Lua Assets"** in the Setup tab's Extra section (unchecked by default) — leave
it unchecked on a plain vanilla install and Kit Mixer's kit-number and name-color changes are
silently ignored in-game, even though Kit Mixer itself reports them as applied. Checking it,
however, also installs CGFS's bundled `general.lua`, which sets the *global* kit-number identifier
scheme — this can make every **other** team's kit numbers (any team you haven't touched in Kit
Mixer) show a checkerboard/missing texture if your kit-number font pack expects the other scheme;
toggle **"Enable custom kit numbers"** (same Extra section) to switch schemes if that happens.
Total-conversion mods like FIP aren't affected — they ship their own already-compatible Lua, so the
Rev Mod checkbox isn't needed (or recommended) there at all.

### Assets Extractor
A new **Assets Extractor** card on the Setup tab, backed by a standalone x86 `.NET` host
(`KitExtractorHost.exe`), unpacks vanilla game content into loose files — which is what makes
Kit Mixer changes to that content apply without restarting FIFA:

- **Database** — a one-time bootstrap ("Extract Database") that copies a template
  `fifa_ng_db.db` into place for clean vanilla installs that don't ship one as a loose file. Every
  other extraction requires this to already be done, and the button locks itself once a database
  exists so a modded/edited one is never silently overwritten.
- **Kits** — extracts, for the whole roster, kit textures (jerseys/shorts/keeper kits, into
  `data/sceneassets/kit`), kit-selection UI thumbnails (`data/ui/imgAssets/kits`), and kit
  numbers (the shared glyph sheets used by every kit, plus the rare per-team override a handful
  of licensed clubs ship — a high failure count on that second part is expected and not a sign of
  a problem). All three are checkboxes under one **"Extract Selected"** action.
- **Team Logos** — extracts the small crest images shown on the Dashboard and in-game overlay
  (`data/ui/imgAssets/crest50x50/light`).
- Runs in small per-team batches, restarting `KitExtractorHost.exe` between batches to work
  around a native resource leak inside `FifaLibrary16.dll` that otherwise throws an
  `OutOfMemoryException` around team index ~195.
- **Recommended for vanilla installs only** — the UI warns that extracting over a
  total-conversion mod (e.g. FIFA Infinity) can overwrite and corrupt its custom content.
- Doesn't regenerate BH by itself — run **Regen BH** (Installer tab) afterward so the extracted
  or replaced files actually show up in-game without restarting it.

### Kit Mixer: How To Structure An `FSW/Kits` Package
Since Kit Mixer is brand new this release, here's where it looks for source kits: for a custom
kit pack to appear as a source in Kit Mixer, place it under `FSW/Kits/<name>/`, where `<name>` is
either the team's raw numeric ID or a friendly folder name
mapped to that ID via `settings.ini [kitsid]` (the same mechanism the Chants feature uses for
`[chantsid]`, edited from the same asset settings editor):

```
FSW/Kits/<name>/
  sceneassets/kit/kit_<team_id>_<kittype>_<tourn_id>.rx3
  sceneassets/kitnumbers/specifickitnumbers_<team_id>_<jerseyOrShorts>_<tourn_id>_<kittype>.rx3
  ui/imgAssets/kits/j<kittype>_<team_id>_0.dds
  fifarna/lua/assignments/teams/<any-name>.lua        (optional)
```

Where `kittype` is `0` = home, `1` = away, `2` = keeper, `3` = third, and `tourn_id` is normally
`0` (the tournament-agnostic slot the engine falls back to).

- At least one `.rx3` under `sceneassets/kit/` is required before Kit Mixer can mix that team +
  kit type — it's used as the template whose non-mixed parts (e.g. the badge decal) are kept.
- If `FSW/Kits/` has nothing for a team, Kit Mixer falls back to whatever is already live under
  `data/sceneassets/kit/` — exactly what the new Assets Extractor populates, so running
  **Extract Selected → Kit Textures** once is the quickest way to get a valid template for every
  team without needing a community kit pack first.
- Any `.lua` dropped under `fifarna/lua/assignments/teams/` doesn't need to reference the same
  team ID — Kit Mixer only scans it for `assignKitDetails(...)` calls to offer as ready-made
  jersey-name-color swatches, regardless of which team the file was originally written for.

### Setup Tab: Optional Rev Mod / Kit Number Scheme
- Rev Mod lua assets are no longer required for Setup to report complete — `data/fifarna/lua` is
  now considered satisfied if *any* `.lua` files are present, so installs using a total-conversion
  mod that ships its own Lua (e.g. FIFA Infinity) aren't flagged as broken.
- Both "Rev Mod Lua Assets" and the "Enable custom kit numbers" toggle (which flips
  `general.lua` between the two competing community `kitnumbers_X_Y.rx3` naming conventions) now
  live in an unchecked-by-default, non-blocking **"Extra"** section, and `general.lua` is only
  ever edited by CGFS if it still matches CGFS's own bundled template — a mod's own Lua is left
  untouched.
- **GoalNet** was added as its own extractable/restorable FSW source, so a vanilla backup exists
  to restore goal net/post models from (see the goalpost fix below).

### Stadium Preview Placeholder
When an assigned stadium has no preview thumbnail of its own, the dashboard, the Assign Stadium
dialog, and the loading overlay now fall back to a bundled generic stadium image instead of an
empty box — stadiums with no assignment still show nothing, so the placeholder only appears when
there's a real (but unpictured) stadium.

## Fixes

- Fixed entrance-camera data going stale across stadium switches: stadiums that don't ship their
  own `EntranceScene/bcstadiumcams` file now have the destination file deleted instead of left
  with the previous stadium's camera data, which could desync camera angles from the new
  stadium's geometry.
- Fixed goalpost/goalnet models getting stuck on a stale, previously-loaded stadium's assets:
  clearing a stadium's custom `GoalpostGBD` now restores the vanilla `goalnet_*`/`goalpost_*`
  files from an `FSW/GoalNet` backup instead of leaving the slot empty for the engine to
  (sometimes) keep showing the last thing it loaded.
- Fixed the idle injection slot (176/261) being left empty by `clear_stadium_inj_files()` —
  replaced with `restore_stadium_inj_files()`, which resets the idle slot to its vanilla default
  instead. An empty slot could be read mid-transition (or during a BH regen) and get stuck
  permanently showing the default stadium.
- Fixed the dashboard and Setup tab both binding `bind_all("<MouseWheel>")`, so only the
  last-registered tab could actually scroll — each tab now scopes its own scroll handler.
- Added a checkerboard fallback for referee kits in the bundled `player.lua`.

## Internal

- `substitution_runtime.py` (new) implements the code-cave hook install, per-side arming/polling
  state machine, and safety checks described above; `offsets.py` gained `SUBHOOKRVA`,
  `SUBHOOKORIGBYTES`, and `SUBREADOFFSET`; `win32_types.py` gained the Win32 structures needed for
  remote code-cave allocation.
- `kit_mixer.py`, `kit_worker.py`, and `kit_preview_worker.py` (new) implement the Kit Mixer
  feature end-to-end: the 32-bit `FifaLibrary16.dll` bridge for texture mixing/preview, and (added
  slightly later in the same cycle) `restore_kit_type()`/`list_modified_kits()` plus the
  jersey-name-color Lua patch/restore path; `app_ui.py` gained the Kit Mixer tab and the
  restore-manager popup.
- `server16_py/native_tools/kit_extractor/KitExtractorHost.cs` (new), built as a standalone x86
  `.exe` via `server16_py/native_tools/kit_extractor/build.bat` and wired into
  `Server16Python.spec`/`build_exe.bat`; runs in small per-batch subprocess launches to work
  around a `FifaLibrary` native-resource leak around team index ~195.
- `big4_extractor.py` gained a GoalNet source; `file_tools.py` gained
  `stadium_preview_fallback_path()` for the bundled `resources/stadium-placeholder.png`.
- `settings_store.py` gained persistence for the substitutions auto-apply toggle and count.
- `en`/`es`/`pt` locale files updated for all new UI strings (substitutions, Kit Extractor, About
  donate link, placeholder text).
- Version bumped to `1.5.0`.

## Release Asset

- `Server16Python.exe`
