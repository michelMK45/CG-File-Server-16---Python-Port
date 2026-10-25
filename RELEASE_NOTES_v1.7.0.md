# CGFS 16 Server 16 Python Port v1.7.0

## Highlights

- **Kits > Team** — a new first Kits subtab that mixes shirt, shorts and socks from a team's own
  kits, with several named combinations per team. No `.rx3` is touched.
- **Team Kits editor in the F12 overlay** — a PES-style home/away kit editor you can drive with a
  gamepad, with the same result as the Python Team tab.
- **Custom input bindings** — rebind the overlay, Team Kits and kit hotkey keys, plus gamepad
  combos, from the new Settings > Controls.
- **F11 "Team combination" mode** — step each side's saved kit combinations in-game without
  opening the menu.
- **New goalposts** — six new goalpost models (6-11) and three new goalpost colors.
- **Overlay input fixes** — F12 no longer reopens the menu after closing it, or closes it again
  while held.

## New Features

### Kits > Team (Classic)

A new first subtab in Kits. It mixes shirt, shorts and socks from a team's own kits through Rev Mod
V1.3.5 `swapTeamKit` part codes, written as a marked block in `team_<id>.lua`.

- Several named combinations per team, a Home/Away choice per side, and a forced goalkeeper per
  side. The format is compatible with Dinei's Kit Mixer.
- The side is detected when the file runs, like Dinei's tool. A team playing itself gets both
  combinations.
- The block undoes what earlier saves left in the game, so removed mixes and forced keepers no
  longer linger. Rev Mod only clears its tables on a stadium load.
- Warning when home and away mix the same kit differently. An amber note says the game's
  team-selection kit previews may differ until the match starts.
- The combination strip scrolls by dragging and the mouse wheel scrolls the page.
- The subtabs are now named **Team**, **Custom Simple** and **Custom Advanced**.
- The bundled Revolution Mod for Setup is updated to **v1.3.5**.

### Kit drawings

Kit drawings now appear in Team, Simple and Advanced. Click one to open a larger view. The PNGs are
cached in `runtime/kit_art_cache`.

### F12 overlay: Team Kits editor

The overlay's Kits tab now starts on a **Team Kits / Custom Kits** chooser, and remembers the last
mode. Custom Kits is the previous flow (side → kit type → kit set).

- **Team Kits** is a PES-style two-half editor, with the home team on the left and the away team on
  the right. Each side has a combination row (original kits, saved ones, or + new), a kit slot
  (view only), and shirt, shorts, socks and goalkeeper rows.
- Left/Right change a row. A/Enter or the side's Save button saves the garments. The combination
  row saves at once.
- It is read-only without Rev Mod support, and shows a message when there is no match.
- Kits are drawn as three transparent garment layers (socks/shorts/shirt), so a garment swaps
  instantly. A background worker draws them: every kit of both teams in advance, and only the
  visible ones in performance mode.
- **Shortcut:** holding gamepad **Select** for 0.6 s opens the menu straight on Kits > Team Kits,
  or moves an open menu there. F12 still opens on press, and held for 0.6 s it jumps to Team Kits.

### Custom input bindings (Settings > Controls)

- Rebind the overlay, Team Kits and kit hotkey keys, plus gamepad combos.
- Each row has a separate keyboard and gamepad **Hold**, so one key can serve two actions (for
  example F12, and F12 held).

### F11 "Team combination" kit hotkey mode

The F11 kit type cycle gains a fifth step, **Team combination**. F7-F10 then step each side's
Kits > Team combinations (original kits plus saved ones), saved at once to `team_<id>.lua`. The
carousel draws the previous, current and next combination.

- A combination is drawn with the kit it actually mixes.
- With only two choices, the other one is no longer shown twice.
- The Kit row in the F12 editor follows the side's combination, so one that only mixes another kit
  (for example kit 3) no longer shows the original kit.

### Goalposts

- Six new goalpost models: **6-9** (added in 1.6.5) and **10-11** (new in this release).
- Three new goalpost colors: **Dark Green**, **Grey** and **Leeds United**.

### Quality of Life

- **Chants editor:** the `chantsid` section is keyed by team id, so it now offers the
  home/away/pick-team helpers instead of the round/tournament ones.
- **Stadium revisit:** returning from Team Management or Settings to KickOffHub no longer
  re-applies the runtime, so the stadium is loaded only once per match preparation.
- **Cache cleanup:** *Clean Cache* now also removes `kit_art_cache` and `match_asset_previews`. A
  new switch next to it deletes, in the background on startup, the generated caches left by
  earlier sessions (only files older than this launch).
- **About dialog:** FifaLibrary16 is now credited to Rinaldo.

## Bug Fixes

- **F12 reopened the menu on Team Kits after closing it with Esc.** The keyboard hook ate F12's
  key-up, which left `GetAsyncKeyState` stuck "down", so "F12 held" fired. Key-ups of keys the
  system saw go down are now passed on.
- **Holding F12 closed the menu again about 0.5 s later.** Windows auto-repeat `WM_KEYDOWN`s were
  latched as new presses. The keyboard hook now seeds keys that are already held before it
  publishes itself.
- **Kit Mixer team lookup.** Side detection is back to Dinei's run-time approach, after four
  redesigns. Lookup-time wrapping was tried and dropped (see `docs/kit-mixer-and-extractor.md`
  §5.2.1).

## Known Limitations

- The F12 Team Kits editor, the custom input bindings and the F11 Team combination mode were
  tested offline only (unit tests and screenshots). Report any problems seen in a real FIFA session.
- The game's team-selection kit previews may differ from the mixed kit until the match starts.

## Technical Notes

- A new `KitEditorShared` block is appended at the end of `OverlayShared`
  (`d3d_injector.set_kit_editor`, sizes checked equal). `#kit-editor` in `menu.rml` is drawn by
  `SyncKitEditor` in `cgfs16_rmlui_menu.cpp`. The struct layouts still have to match by hand.
- New modules: `kit_classic*.py`, `kit_classic_editor.py` (Tk-free `TeamKitSide` model used by the
  overlay), `kit_classic_art.py`, `kit_art_preview`, `image_zoom_dialog` and `input_bindings.py`.
- `bin/` is rebuilt: `cgfs16_overlay.dll`, `cgfs16_inject.exe` and `KitExtractorHost.exe`.
- Locales (en/es/pt) gain new `overlay.kits.*`, `overlay.teamkits.*`, `kitsimple.hotkey_*` and
  `help.overlay_toggle` strings, and `locales_data.py` is regenerated.
- New tests: `test_kit_classic` (the Lua tests need the optional `lupa`), `test_kit_classic_editor`,
  `test_overlay_team_kits`, `test_kit_art_preview`, `test_startup_cache_cleanup`, `test_file_tools`.
