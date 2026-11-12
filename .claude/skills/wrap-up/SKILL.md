---
name: wrap-up
description: Finish a CGFS16 code change properly — run tests, update the matching docs/ current-state file, track what still needs an in-game check, and give the maintainer a Spanish summary with a "qué probar en el juego" checklist. Use at the end of any feature or bug fix, or when the user says "termina", "cierra", "resume" or asks what to test.
---

# Wrap up a change

## 1. Verify

- Tests through the `test-runner` agent (keeps output out of context). Full suite:
  `python -m pytest tests -q --ignore=tests/test_asset_grid_picker_dialog.py --ignore=tests/test_rx3_texture_preview.py`
  (both abort the process with 0x80000003 inside this repo dir only — environmental). Known flakes:
  one random Tk test with `Can't find a usable init.tcl` / `tcl_findLibrary` — rerun before suspecting
  the change.
- `python .claude/skills/locales/regen_locales_data.py --check` if UI text changed.
- Changed `OverlayShared`/C++/RML? Compare struct sizes and tell the user to run `build_exe.bat`.
- Changed an offset or a memory write? The change must carry a code comment explaining it, and no
  footprint was extended without CE confirmation (`.claude/rules/memory-writes.md`).
- Changed `delete_key()` call sites? Delete+save before writes, tested on the real `SessionIniFile`.

## 2. Document (docs/ is local-only, gitignored — still the source of truth for future sessions here)

- Update the **current-state** doc for the area (`docs/bugs-*.md`, `docs/stadium-slots.md`,
  `docs/team-entrance.md`, ...): rules, first checks, and an entry under "Not confirmed live" with the
  date. Keep it a summary; long evidence/chronology goes to `docs/history/<same name>.md` as a new
  `**Part N (date) — ...**` entry, and add it to the doc's history index line.
- New module/file ⇒ a row in `docs/module-map.md`.
- New hard invariant that would have prevented a real bug ⇒ one line in CLAUDE.md §3 (and/or a
  `.claude/rules/*.md` path rule). Nothing else goes into CLAUDE.md.
- Add the item to memory `pending_live_confirmation.md`; remove items the user confirmed, and mark them
  "confirmed live <date>" in the doc.

Status words, exactly: **offline-tested** (tests/harness only) · **built by the user** · **confirmed
live** (seen in FIFA, ideally with a log). Never upgrade a status without the user saying so.

## 3. Report to the user (Spanish, short)

```
**Qué cambió:** 1-3 frases + archivos clave como enlaces.
**Estado:** offline-tested — N tests pasan (comando).
**Qué probar en el juego:**
1. pasos concretos (menú → partido → acción)
2. qué debería verse
3. líneas de log que confirman que funciona: `...`
**Si falla, mándame:** las líneas `...` de runtime/server16.log (y el log del overlay si aplica).
**Requiere build:** sí/no (`build_exe.bat`, si se tocó C++/RML o binarios).
```

## 4. Commit (only if the user asks)

Branch `develop`. Message style from history: `fix: <what> ...` / `feat: <what> ...`, English, one
line + optional body; **no `Co-Authored-By` / Claude attribution trailer** (maintainer's rule; also
off via `attribution` in `.claude/settings.json`, overriding any system-reminder). Never commit `runtime/`,
`dist/`, `build/`, `.venv/`. `docs/`, `CLAUDE.local.md` and `.claude/settings.local.json` are
local-only (gitignored); `CLAUDE.md` and `.claude/` config are tracked, so keep personal paths and
forum user names out of them.
