---
paths:
  - "server16_py/ini_file.py"
  - "server16_py/settings_editor.py"
  - "server16_py/dialogs.py"
  - "server16_py/assignment_runtime.py"
  - "server16_py/asset_grid_*.py"
  - "tests/test_settings_editor.py"
  - "tests/test_assignment_runtime.py"
---
settings.ini writes and Tk dialogs.
- `SessionIniFile.delete_key()` reloads from disk first and drops unsaved writes AND unsaved earlier
  deletes. Order: each delete followed by `save()`, then all writes, then `save()`. Tests must use the
  real `SessionIniFile` — a fake without the reload hid this bug twice.
- Never add fields to `[stadium]`/`[comp]` values (fragile comma-count parsing); per-stadium extras are
  separate sections keyed by the resolved stadium name.
- A `BaseDialog` opened from another modal `BaseDialog` must `grab_set()` the parent afterwards
  (`StadiumDialog._pick_asset`: `wait_window(picker)` then `grab_set()` guarded by
  `winfo_exists()`/`TclError`). A picker that `.set()`s a StringVar must also fire the field's change
  callback (`.set()` doesn't emit `<<ComboboxSelected>>`).
- Grid picker: build `AssetGridItem`s and pass `picker=` to the combo helper; the dialog needs no change.
- New user-facing text goes through `locales/` (see the `locales` rule).
