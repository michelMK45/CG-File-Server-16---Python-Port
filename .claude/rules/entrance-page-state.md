---
paths:
  - "server16_py/entrance_runtime.py"
  - "server16_py/app_game.py"
  - "server16_py/chants_runtime.py"
  - "tests/test_team_entrance*.py"
  - "tests/test_entrance_*.py"
---
Team Entrance is a page-name state machine (20 documented parts). Before editing, read
`docs/team-entrance.md` and the current-state `docs/bugs-entrance.md` (history in `docs/history/`).
- Do not add per-attempt counters (e.g. `_entrance_sequence`) to `TeamEntranceRuntime._match_key()`; only `_kickoff_generation` + team/tournament ids.
- Do not gate the pause->resume decision on clock speed (unsatisfiable before kick-off).
- Any counter debounced on "consecutive" ticks must reset on EVERY disqualifying tick.
- A new menu page leaking audio => extend `_page_blocks_team_entrance()` (app_game.py) and `pause_menu_tokens` (entrance_runtime.py) — they are separate lists.
- Tests must not mock `time.sleep` in a way that hides real tick-rate speed math.
