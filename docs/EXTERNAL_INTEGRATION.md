# External Folder Integration Guide

This repository includes a script to import a non-git external project snapshot and merge it into your current work branch.

## Script

- Path: `scripts/import_external_snapshot.ps1`

## Required inputs

- `ExternalProjectPath`: folder path of the other user's project.
- `BaseRef`: commit/tag/branch from this repo that is closest to the version they started from.

## Example

```powershell
pwsh -File .\scripts\import_external_snapshot.ps1 \
  -ExternalProjectPath "D:\ExternalProjects\UserVersion" \
  -BaseRef "v0.2.3" \
  -IntegrationBranch "integration/external-user-2026-04-28" \
  -TempBranch "temp/external-user-snapshot-1"
```

## What the script does

1. Verifies the current git working tree is clean.
2. Creates the integration branch if needed.
3. Creates a temp branch from `BaseRef`.
4. Copies the external project into this repository (excluding build/cache folders).
5. Commits the imported snapshot in the temp branch.
6. Switches back to integration branch and merges temp branch.

## Notes

- Keep the temp branch until tests and manual validation are complete.
- If there are conflicts, resolve them on the integration branch and commit.
- Do not run this script with uncommitted local changes.
