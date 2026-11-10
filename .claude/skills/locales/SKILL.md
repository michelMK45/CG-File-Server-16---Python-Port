---
name: locales
description: Add or change user-facing UI strings in CGFS16 (locales/en,es,pt.json + generated locales_data.py). Use whenever new Tk/UI text, tooltips, toasts or module labels are added, or the user asks for a translation.
---

# Adding UI strings

All user-facing text in the Tk app goes through `server16_py/locales/{en,es,pt}.json`; hardcoding it
caused a string of translation-gap fixes. Exception: the F12 overlay wizard text is hardcoded English.

1. **Find the naming pattern** for the area first: `grep` an existing neighbour key in `en.json`
   (e.g. `module.<slug>`, `tooltip.module.<slug>`, `module.category.<cat>`, `kitclassic.*`).
   Modules also need `module_catalog.py` (`MODULE_SLUGS`, `MODULE_CATEGORIES`, `INI_MODULE_NAMES`).
2. **Edit `en.json`, `es.json`, `pt.json` with the Edit tool** (CRLF working tree; never rewrite whole
   files). Write natural Spanish and Brazilian Portuguese, not word-for-word; keep `{placeholders}`
   identical in all three. es/pt may stay partial (fallback to en) only if the user says so.
3. **`locales_data.py` regenerates automatically** where the local PostToolUse hook is configured
   (`.claude/settings.local.json`). Otherwise, or if you edited the JSON some other way, run `python .claude/skills/locales/regen_locales_data.py`; `--check` verifies it is current.
   Never hand-edit `locales_data.py`.
4. Use the key from code via the local `tr(key, **kwargs)` helper (`app_localization.py` for the app
   mixins, `dialogs.py` / `settings_editor.py` have their own `tr`; backend is
   `localization.translate`). Placeholders are `str.format`-style kwargs.
5. Run the relevant tests (`tests/test_gamepad_locale_keys.py`, `tests/test_module_catalog.py`, or the
   UI test of the area).
