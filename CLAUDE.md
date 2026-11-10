# CLAUDE.md — CGFS16 Server 16 (Python Port)

Persistent context for this repo. **Kept deliberately short**: detail lives in `docs/` and is read on
demand (§5). If something here stops matching the code, trust the code and fix this file. No bug
chronologies here — current state goes in `docs/<area>.md`, evidence in `docs/history/`.
Tracked (public repo): this file, `.claude/settings.json`, `.claude/{agents,skills,rules}/`. Local only
(gitignored): `CLAUDE.local.md` (machine paths), `.claude/settings.local.json`, and `docs/` — so a fresh
clone has no `docs/`; never put personal paths or forum user names in tracked files.

## 1. What this is

**CG File Server 16 (CGFS16 / "Server 16")**: Windows-only modding tool for **FIFA 16** (PC). A Tk
control panel + in-game D3D11 overlay that swaps assets (stadiums, scoreboards, TV logos, movies,
chants, cameras, kits) **while FIFA runs**, by reading the game's live memory (teams/stadium/
competition/page) and copying files / writing a few values into the game process. Python rewrite
(`server16_py/`) of a closed-source .NET tool (decompiled remnants in `legacy/`), packaged with
PyInstaller, plus native C++ overlay (`server16_py/d3d_overlay/`) and a bridge to the closed x86
`FifaLibrary16.dll`. Not a network server; "Server" is legacy branding.

## 2. Architecture in brief

One Tkinter process, `App` (`app.py`) composed of mixins. Full per-module table: `docs/module-map.md`.

- **UI:** `app_ui.py` (main window/Setup/Kit Mixer UI), `dialogs.py`, `settings_editor.py`,
  `asset_grid_*`, `video_preview.py`, `splash.py`.
- **Game loop:** `app_game.py` (`poll_process` 500ms, `stats_loop` 250ms, page-transition handling),
  `memory_access.py` (`Memory`: Read/WriteProcessMemory + pointer chains), `offsets.py` (live source
  of truth; `offsets.json` is NOT loaded).
- **Assignment/runtimes:** `assignment_runtime.py` → `stadium_runtime.py`, `asset_runtime.py`,
  `chants_runtime.py`, `entrance_runtime.py`, `camera_runtime.py`, `substitution_runtime.py`,
  `kit_mixer.py`, `kit_classic*.py`; helpers in `file_tools.py`, `ini_file.py`.
- **Overlay:** `app_overlay.py` + `d3d_injector.py` ↔ `cgfs16_overlay.dll` via named shared memory
  `Local\CGFS16_Overlay_v2` (struct layouts MUST match by hand, no versioning). F12 menu is RmlUi.
- **Scoreboard stadium name:** `match_string_patcher.py` (`StadiumDbNamePatchCoordinator`).
- **Gamepads:** `gamepad_bridge_runtime.py`, `hidhide_runtime.py`, `vigembus_uninstall.py`, `win_elevation.py`.
- **32-bit bridges** (`FifaLibrary16.dll` is x86-only): `*_worker.py` run under `bin/python32/`,
  standalone `KitExtractorHost.exe`. Newline-delimited JSON on stdout (`{"t":"ready"|"progress"|"done"|"error"}`).
- **Settings:** `runtime/settings.json` (app) vs `FSW/settings.ini` (game assignments) — never conflate.
  Strings in `server16_py/locales/{en,es,pt}.json` (`locales_data.py` is generated).

## 3. Hard invariants (violating these caused real bugs)

- **Stadium slots:** only two engine slots exist, `176`/`261`, ping-ponged (`file_tools.inc_count`/
  `set_inj_id`). Write `ORISTADIDBASE` only AFTER the file copy is verified. Idle slot is restored to
  vanilla, never emptied. All stadium file work goes through `stadium_runtime.py`. Known unfixed:
  vanilla match → custom match gives green/blue textures. → `docs/stadium-slots.md`
- **FIFA caches resolved asset paths per session:** per-stadium variants are installed under
  slot-specific `specific*_0_{176|261}` names. → `docs/bugs-goalpost.md`
- **Never extend a live memory write past a proven-safe footprint** without the user's own Cheat
  Engine confirmation per address (edit + visible effect + full match without crash) — `/ce-check`.
  Never repoint the substitution hook (`SUBHOOKRVA`); never set breakpoints on FIFA. Any offset change
  carries a comment explaining it. → `docs/substitution-hook.md`, `.claude/rules/memory-writes.md`
- **`Memory.write_process_memory` does NOT restore page protection** — never aim it at code pages;
  do protect/write/restore yourself (see `substitution_runtime._patch_hook_site`). All memory access
  goes through `memory_access.Memory`; offsets live in `offsets.py`.
- **`SessionIniFile.delete_key()` reloads from disk first** and drops unsaved writes *and unsaved
  earlier deletes*: `save()` after each delete, then do all writes, then save. Test against the real
  `SessionIniFile`, not a fake.
- **Never write to `fifa_ng_db.db` on disk** (`db_patcher.patch_stadium_names` is dead code; it
  corrupted installs). Never load `FifaLibrary16.dll` (or any x86 DLL) in-process.
- **Team Entrance is a page-name state machine** with 20 documented parts. Don't add counters to
  `TeamEntranceRuntime._match_key()`, don't gate resume on clock speed, and extend
  `_page_blocks_team_entrance()` AND `pause_menu_tokens` when a new menu page leaks audio.
  → `docs/bugs-entrance.md`
- **Tk threading:** never touch Tk from worker threads (post via queue / `after`); no `asyncio`.
  `splash.py` runs its own Tk interpreter on its own thread — read its docstring before editing. A
  `BaseDialog` opened from another modal `BaseDialog` must `grab_set()` the parent afterwards.
- **`msiexec` switches must not be quoted** (`win_elevation.RawArg`).
- **FIFA's exclusive-fullscreen** hides input from polling APIs; low-level hooks see it. A Python
  `WH_KEYBOARD_LL` hook installed permanently makes FIFA's own menus sluggish → keep it menu-scoped.
  → `docs/bugs-overlay-input.md`

## 4. Build, run, test

```powershell
.\build_exe.bat                         # -> dist/Server16Python.exe (C++/C#/32-bit bridge/PyInstaller)
python main.py                          # from source (needs bin/ native binaries)
python -m pytest tests -q --ignore=tests/test_asset_grid_picker_dialog.py --ignore=tests/test_rx3_texture_preview.py
```
The two ignored files abort pytest (0x80000003) inside this repo dir only — environmental. If
`python` is not on the shell's PATH, see `CLAUDE.local.md` for this machine's interpreter.
Prefer the `test-runner` agent. Details, binaries, PyInstaller pitfalls: `docs/dependencies-build.md`.
Windows only; no cross-platform code. Don't commit `runtime/`, `dist/`, `build/`, `.venv/`.

## 5. Read on demand — "if you touch X, read Y first"

Each `docs/bugs-*.md` is a short **current state** (rules, first checks, open items); the full
chronology is in `docs/history/<same name>.md` — grep it for `**Part N` only when needed.

| Working on | Read |
|---|---|
| any module, who owns what | `docs/module-map.md` |
| overlay DLL, shared-memory struct, F12 menu, RmlUi | `docs/overlay-d3d.md` |
| memory reads, pointer chains, 32-bit bridges | `docs/memory-and-bridges.md` |
| `.big` / `.bh` / hashing | `docs/file-formats.md` |
| stadium loading, 176/261 slots, KickOffHub revisits | `docs/stadium-slots.md` |
| goalposts, net color, net mesh, F12 stadium wizard | `docs/bugs-goalpost.md` |
| Kit Mixer (Team = `kit_classic*`, Custom Simple, Custom Advanced), `KitExtractorHost`, league logos | `docs/kit-mixer-and-extractor.md` |
| substitution limit hook | `docs/substitution-hook.md` |
| Team Entrance / Support-chants guard | `docs/team-entrance.md`, then `docs/bugs-entrance.md` |
| `scoreboardstdname` / stadium name on pre-match screen | `docs/bugs-scoreboardstdname.md` |
| F12/kit hotkeys, custom bindings (`input_bindings.py`), mouse/keyboard hooks | `docs/bugs-overlay-input.md` |
| Gamepads tab, HidHide, ViGEmBus | `docs/gamepads-hidhide-vigembus.md` |
| t3db database, `db_patcher` | `docs/database.md` |
| older/misc fixes (RAR5, goal songs, Discord, context-read spam, practice arena, SkillGamePause) | `docs/bugs-misc.md` |
| deps, build, native binaries | `docs/dependencies-build.md` |
| in-game CGFS16 menu (FIFA's own UI), `ingame_*` modules | `docs/ingame-menu.md` |
| roadmap, open items, `legacy/` map | `docs/roadmap-legacy.md` |

Logs (`runtime/server16.log`, `.previous.log`, forum `Log*.txt`) can be tens of thousands of lines:
analyse them with the `log-analyst` agent (or grep a time window), never read them whole.

## 6. Working here

- **Skills:** `/triage` (bug report or log → mechanism + evidence, before code), `/wrap-up` (end of
  every change: tests, docs current-state, pending-live list, Spanish "qué probar en el juego"),
  `/locales` (UI strings), `/ce-check` (Cheat Engine confirmation request), `/release` (version,
  notes, tag — user-invoked only).
- **Agents:** `test-runner` (pytest, failures only), `log-analyst` (log timelines).
- **Path rules** in `.claude/rules/` load automatically for: memory writes, entrance/chants, overlay
  shared memory, stadium files, ini/dialogs, x86 bridges, locales.
- **Hook** (local, `.claude/settings.local.json`): editing `server16_py/locales/*.json` regenerates
  `locales_data.py`. Without it, run `python .claude/skills/locales/regen_locales_data.py`.
- **Status words:** offline-tested → built by the user → confirmed live. Claude never sees the game;
  never call something confirmed unless the user said so.
- **Conventions:** file ops via `file_tools.py` manifest helpers (copy/clear symmetric, no raw
  `shutil`); archives extract into `runtime/` temp folders and are always cleaned; new dialogs follow
  `dialogs.py`; all user-facing text through locales (overlay wizard text is the hardcoded-English
  exception).
