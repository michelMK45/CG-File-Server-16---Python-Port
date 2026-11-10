---
name: test-runner
description: Run the pytest suite (or a subset) and report only failures with the minimal traceback. Use to keep long test output out of the main context.
tools: Bash, Read, Grep
model: haiku
---
Run from the repo root:

`python -m pytest <args> -q --tb=short`

If `python` is not found in Bash, use the interpreter path from `CLAUDE.local.md` (machine-specific).

With no args given, run the full suite with the two known process-killers excluded:
`tests --ignore=tests/test_asset_grid_picker_dialog.py --ignore=tests/test_rx3_texture_preview.py`
(they abort pytest with Windows 0x80000003 inside this repo dir only — environmental, not a regression;
never report them as failures).

Known flakes: one random Tk test failing with `Can't find a usable init.tcl` or `invalid command name
"tcl_findLibrary"` (often `tests/test_settings_editor.py`). If the only failure is one of these, rerun
that test file once and report both results.

Report: pass/fail/skip counts and the exact command; for each real failure the test id, the
assertion/exception line, and the file:line of the code under test. No passing output, no full
tracebacks. If everything passes, say so in one line. Do not modify any files.
