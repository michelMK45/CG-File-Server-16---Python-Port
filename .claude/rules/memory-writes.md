---
paths:
  - "server16_py/memory_access.py"
  - "server16_py/offsets.py"
  - "server16_py/match_string_patcher.py"
  - "server16_py/substitution_runtime.py"
  - "server16_py/stadium_runtime.py"
---
Live FIFA memory is dangerous. Read `docs/memory-and-bridges.md`; for name patching `docs/bugs-scoreboardstdname.md`; for the hook `docs/substitution-hook.md`.
- Never extend a write past a proven-safe footprint (or add/remove an address suffix from `STDNAME_SAFE_EXTEND_*`) without the user's own Cheat Engine confirmation at that address.
- Never patch/breakpoint any code address other than `Offsets.SUBHOOKRVA`.
- `Memory.write_process_memory` does not restore page protection; do protect/write/restore for code pages.
- Changing any offset requires a code comment or PR note explaining it.
- Don't reintroduce early "prewarm" patch requests for scoreboardstdname (buffer doesn't exist before loading starts).
