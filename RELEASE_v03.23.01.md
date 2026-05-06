# RELEASE v03.23.01

Release date: 2026-05-07
Phase: RUNTIME_EDITOR_STABILITY_RELEASED
Base branch: `main`
Immediately previous release: `v03.23.00`
Release app version: `03.23.01`

## Summary

v03.23.01 is a runtime stability patch for the editor after the Stable Editor Frames release. It keeps the v03.23.00 Fast/Auto/High behavior, then tightens the parts that still affected real editing sessions: post-generation idle cleanup, slow playhead scrubbing, sidebar visibility of automatic audio/VAD choices, heavy project JSON access, and partial-write settings JSON failures.

This release note intentionally references only v03.23.00 as the previous checkpoint. Older cumulative history remains in older `RELEASE_v*.md` files and should not be copied into handoff documents.

## Changes Since v03.23.00

- Added shared safe JSON helpers for user settings, custom defaults, folder settings, and project writes.
- Made settings writes atomic and recoverable from `.bak` backups when a partial JSON file is detected during load.
- Added atomic project JSON writes without the extra large-file backup copy, while keeping process-level project cache priming after saves.
- Extended project JSON read caching so editor mode can reuse already-loaded project data when the file signature has not changed.
- Increased the default editor autosave interval and made autosave skip expensive save paths when there are no unsaved changes.
- Forced the editor back to an idle state after subtitle generation by clearing processing flags, busy cursors, background prefetch state, and delayed runtime cleanup.
- Added generation tokens to background prefetch cleanup so late worker results do not repopulate stale editor state after completion.
- Throttled timeline scrub/video preview seeks and added a lightweight preview seek path so moving the playhead is less likely to stall the editor.
- Preserved the current sidebar width while generation starts, avoiding the slight sidebar shrink caused by responsive layout recalculation.
- Surfaced the current file's automatically selected audio filter and VAD in the sidebar engine dashboard with auto markers and tooltip context.

## Compatibility Notes

- `core/runtime/config.py` remains the source of truth for `APP_VERSION`.
- The user-facing Mode values remain `fast`, `auto`, and `high`; legacy STT quality compatibility remains unchanged.
- Project writes now use temp-file replacement and no `.bak` copy to avoid doubling large autosave I/O.
- Settings JSON files still keep `.bak` backups because those files are small and should recover safely from partial-write parse errors.
- macOS and Windows remain supported targets, including Korean paths, spaces, subprocess handling, ffmpeg/ffprobe, PyQt6, OpenGL/SceneGraph, and local media cache behavior.
- The handoff set remains `AGENTS.md`, `ACTION_ITEMS.md`, `File_structure.txt`, `README.md`, and the latest `RELEASE_v*.md`.

## Verification

Completed verification for this release:

- `venv/bin/python -m pytest -q`
  - `931 passed, 1 warning, 2 subtests passed in 297.31s`
- `venv/bin/python -m json.tool dataset/user_settings.json`
- `venv/bin/python -m json.tool dataset/custom_defaults.json`
- `venv/bin/python -m json.tool dataset/folder_settings.json`
- `git diff --check -- .`

## Next Direction

No active or parked backlog remains in `ACTION_ITEMS.md`. Future work should start from user-requested product goals rather than old parked items, with the current priority remaining accuracy before speed.
