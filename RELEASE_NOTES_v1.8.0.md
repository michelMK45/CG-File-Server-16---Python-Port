# CGFS 16 Server 16 Python Port v1.8.0

## Highlights

- **In-game CGFS16 menu** — a Server 16 menu inside FIFA 16's own interface. Press **R3 on the
  match hub** to assign stadiums, scoreboards, TV logos, movies and Team Kits combinations without
  leaving the game.
- **One-click install from Setup** — install, update and remove the in-game menu from the Setup tab.
  It repairs itself after a FIFA theme switch.
- **3D kit drawings** — kit pictures now use FIFA 16's own body models, with the right collar for
  each shirt.
- **Scoreboard crests are restored after each match** — crests from a scoreboard pack no longer stay
  in FIFA's menus.
- **Team entrance with the Movies module off** — the skill game on the loading screen no longer
  cuts the anthem.

## New Features

### In-game CGFS16 menu (R3 on the match hub)

A menu built into FIFA 16's own front end, styled like FIFA's Game Settings screen: tabs, rows with
`< value >`, and a picture or video preview at the top right. Open it with **R3 on the pre-match
match hub** (KickOffHub). Leave with **BACK** and Server 16 saves your choices to `settings.ini` and
applies them, just as if you had used the app or the F12 overlay.

- **Stadium:** choose what the stadium applies to (**Home Team**, **Round** or **Tournament**), add
  stadiums, and set each one's police, pitch pattern, net colour, goalpost model and texture, net
  mesh and entrance camera, as in the F12 stadium wizard. Each stadium shows its preview.
  - **Match stadium** keeps one of the assigned stadiums for every match of that assignment, even
    after a restart, instead of the random choice or the stadium picker. Set it back to
    **Selector / Random** to go back to the usual behaviour.
- **Scoreboard** and **TV Logo:** assign a pack to the Home Team, a Derby, Default/Friendly, the
  Round or the Tournament, with the pack's thumbnail. **Default (FIFA 16)** removes the assignment.
- **Movies:** assign a movie pack to the Home Team, a Derby, the Round or the Tournament. The pack's
  intro plays muted as the preview.
- **Kits:** see the next section.
- The menu's texts come in FIFA 16's 16 languages.
- Choices you saved in the menu but that Server 16 has not processed yet stay selected when you
  reopen it.

### In-game menu: Kits tab

One row for the home team and one for the away team. Each lists the team's original kits plus the
combinations saved in **Kits > Team**, each with its drawing. BACK saves both sides to the team's
`team_<id>.lua`, and the Kits > Team tab refreshes.

- Changes you make in the app, the F12 overlay or with the F7-F10 hotkeys show up in the menu.
- A side is not saved if that team's combinations changed in the app while the menu was open, so a
  deleted combination never shifts your pick onto another one.
- Requires Revolution Mod V1.3.5 (as Kits > Team). Without a match, or without saved combinations,
  the tab says so.
- Creating or editing combinations, the forced goalkeeper and Custom kits stay in the app and the F12
  overlay. As in F12, the kits apply when the match loads.

### Install the in-game menu from Setup

The Setup tab has a new **In-game menu** section. Tick it and **Run Setup** to install or update it;
**Uninstall in-game menu** removes it and puts back every game file it changed. The status shows
**Installed**, **Update available**, **Not installed** or **Installed, no R3** (a match hub the menu
cannot hook into). FIFA 16 must be closed to install or remove it.

- **FIFA themes:** a theme ships its own match hub and navigation files, which used to remove R3.
  Now any match hub is hooked at install time. A theme's match hub is kept as the original, so
  uninstalling puts the theme's file back. Server 16 checks the install when it starts and before
  **Launch FIFA 16**, and repairs it if a theme changed it. A note under the button explains this.

### 3D kit drawings

The kit drawings in Kits > Team, Custom Simple, Custom Advanced, the F12 Team Kits editor and the
in-game menu are now rendered from FIFA 16's own shirt, shorts and sock models with the kit's
textures. Each shirt uses its collar type: Server 16 reads it from `team_<id>.lua`, or from a
`teamkits.txt` export if there is one. The previous flat drawing is the fallback. Thanks to the forum
contributor whose build this comes from.

### Scoreboard crests restored after the match

Scoreboard packs that include crests (`imgassets/crest*`) or fonts used to change them in FIFA's
menus permanently. Now every pack file outside `game/` is tracked, and the original is put back:

- when you enter team selection (SelectTeam),
- after a Career or Tournament match, on the hub after the results screen (not at half-time or in
  the pause menu),
- on the next match that does not use that pack (a friendly, another pack, or the module turned off).

If your install already has special crests from earlier versions, put your "normal" files in the
optional `FSW/ScoreBoardDefaults/` folder (same layout as `data/ui`, for example
`imgAssets/crest/light/l241.dds`). Server 16 lays them down under the current pack's files.

### Quality of Life

- **About dialog:** new **Wiki** link.
- **App Options:** the toggle is now called **Show notifications** and sits next to the overlay
  switch.
- **Logs:** the "Null pointer at base chain start" lines while FIFA is still starting are written
  once per FIFA process instead of on every poll.

## Bug Fixes

- **Team entrance cut with the Movies module off.** In that case FIFA loads the match behind the skill
  game instead of the TV intro. The anthem started on the instructions screen, and pressing A to play
  cut it. It now waits for the pre-match scene before playing.

## Technical Notes

- The in-game menu (Apt movies, nav patches, release package) is built in the separate cgfs-ingame
  project. The prebuilt package ships in `resources/ingame/mod`, with one hooked `kickoffhub.big` per
  known original (vanilla and FIP) plus `hooks/kickoffhub.asm` for any other. Install state and backups
  live in `<game>/_cgfs16_ingame/manifest.json`. The install changes FIFA's `.bh` files, so FIFA must
  be closed.
- App → menu: `data/ui/cgfs16/data.big`, rendered from `resources/ingame/data_template.big` on page
  transitions. Menu → app: a read-only scan of FIFA's memory for the menu's save record, in a worker,
  after the menu screen closes. The app writes nothing into FIFA's memory for the menu.
- New modules: `ingame_menu_runtime`, `ingame_menu_install`, `ingame_kits`, `ingame_images` (320x180
  DDS previews, linked `.vp8` movies under `data/ui/cgfs16/`), `ingame_menu_texts`, and stdlib-only
  copies of the cgfs-ingame tools `ingame_datafile`, `ingame_recordscan`, `ingame_modinstall`,
  `ingame_hubpatch` and `ingame_kickhook` (generated).
- Match stadium: `settings.ini` `[ForcedStadium]` `<section>_<key>=<stadium>` (for example
  `stadium_241`, `comp_12`), read by `StadiumRuntime` before the picker or random roll.
- 3D drawings: `kit3d.py` (pure-Python + Pillow rasteriser), `kit3d_meshes.py` (meshes for 22 collar
  types), `kit_classic_shapes.py` (flat fallback). The kit art cache version is bumped, so existing
  drawings are redrawn.
- Scoreboard crests: pack files outside `game/` go through `install_tracked_selection` with backups in
  `FSW/.scoreboard_ui_backup`.
- `bin/` is rebuilt: `cgfs16_overlay.dll`, `cgfs16_inject.exe` and `KitExtractorHost.exe`.
- Locales (en/es/pt) gain `setup.*ingame_menu*`, `setup.status.ingame_*`, `message.ingame_menu.*` and
  `dialog.about.wiki`, and `locales_data.py` is regenerated.
- New tests: `test_ingame_menu_runtime`, `test_ingame_menu_install`, `test_ingame_kits`,
  `test_launch_fifa_ingame_repair`, `test_scoreboard_ui_tracking`, `test_kickoff_revisit`,
  `test_page_startup_logging`, plus new cases in `test_team_entrance` and `test_kit_classic`.
