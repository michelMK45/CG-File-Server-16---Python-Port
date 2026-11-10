---
paths:
  - "server16_py/locales/*.json"
  - "server16_py/locales_data.py"
---
UI strings. Use the `/locales` skill for adding keys.
- Add every new key to `en.json`; add `es.json`/`pt.json` translations too (they are intentionally
  partial and fall back to `en`, so a missing es/pt key is not a bug by itself).
- Edit the JSON files with the Edit tool (working tree is CRLF; don't rewrite whole files).
- `locales_data.py` is a generated fallback copy: never hand-edit it. A local PostToolUse hook (if
  configured in `.claude/settings.local.json`) regenerates it after edits of `locales/*.json`; otherwise run
  `python .claude/skills/locales/regen_locales_data.py` (byte-identical, CRLF).
