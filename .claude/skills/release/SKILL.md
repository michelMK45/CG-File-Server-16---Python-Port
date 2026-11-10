---
name: release
description: Prepare a CGFS16 Server 16 release — version bump, RELEASE_NOTES_vX.Y.Z.md from git history, build checklist, tag and GitHub release. Use only when the user asks to prepare/publish a version or write release notes.
disable-model-invocation: true
---

# Release

Everything outward-facing (tag push, GitHub release, forum post) needs the user's explicit go-ahead
at that step. The user runs the build and the in-game smoke test.

1. **Range:** last tag `git tag --sort=-v:refname | head -1`; changes `git log <tag>..HEAD --oneline`
   (+ `git diff --stat <tag>..HEAD`). Version lives only in `server16_py/__init__.py`
   (`__version__`); the in-app update checker compares it with the latest GitHub release.
2. **Version:** patch for fixes only, minor for features (history: 1.6.x → 1.7.0 with Kits > Team).
   Ask if unclear. Bump `__version__` (it may already be bumped — check).
3. **Release notes:** `RELEASE_NOTES_v<ver>.md` in the repo root (bigger releases; patch releases may
   only need the GitHub text — ask). Follow `RELEASE_NOTES_v1.7.0.md`:
   `# CGFS 16 Server 16 Python Port v<ver>` → `## Highlights` (bullets, bold feature name — one line
   each) → `## New Features` (`###` per feature, user-facing wording, UI names as shown in the app:
   Kits > Team, Custom Simple...) → `## Bug Fixes` → `## Known Limitations` → `## Technical Notes`.
   Write for mod users, not developers: no internal function names except in Technical Notes. Mark
   anything still in `pending_live_confirmation` honestly (or ask the user if it was tested since).
   Pull the "why" from `docs/` current-state files, not from memory.
4. **Build checklist for the user:** `.\build_exe.bat` → `dist/Server16Python.exe`; if C++/C# changed,
   confirm `bin/cgfs16_overlay.dll`, `bin/cgfs16_inject.exe`, `bin/KitExtractorHost.exe` were rebuilt
   and are part of the commit. Smoke test: launch, Setup tab, one Kick-Off match with a custom stadium,
   F12 menu opens/closes.
5. **After the user confirms the build:** commit (`feat: <ver> release notes.` style), then — only on
   explicit OK — `git tag v<ver>` and push. Tags so far sit on commits shared by `develop` and `main`
   (kept level); merge `develop` → `main` only if the user asks. If `gh` is available,
   `gh release create v<ver> --title "v<ver>" --notes-file RELEASE_NOTES_v<ver>.md` (exe attached
   only if the user wants); otherwise give the user the release text to paste.
