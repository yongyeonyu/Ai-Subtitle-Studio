# RELEASE v04.01.09

Date: 2026-06-29
Previous release: `v04.01.08`
Release app version: `04.01.09`

## Summary

`v04.01.09` is a focused source-app G3/G2 deferred-save retry checkpoint.

This release keeps the strict `nle_save_export_final_overlap` guard intact while stopping that nonretryable final-overlap save/export failure from causing repeated deferred project-save retries. It does not claim that the underlying final subtitle overlap, same-media save/reopen, or final export gate is fixed.

## Key Changes

- Version and schema:
  - `core/runtime/config.py` now reports `APP_VERSION = "04.01.09"`.
  - `core/project/project_format.py` now marks newly saved project payloads as schema version `04.01.09`.

- Deferred save retry guard:
  - `ui/editor/editor_save_manager.py` now treats `nle_save_export_final_overlap` as a nonretryable deferred project-save error outside close/exit paths as well.
  - The nonretryable path clears stale pending deferred-save snapshots, segments, and options, records the error, and avoids scheduling another retry timer.
  - Retryable writer failures still reschedule through the existing deferred-save retry path.

## Evidence

- Jammini route proof: `.agents/sentinel/handoffs/20260629-030627-watchdog-handoff-probe.md`
- Three sub-agent reviews were used for architecture, QE, and editor-workflow guardrails.

## Validation

- `./venv/bin/python -m py_compile ui/editor/editor_save_manager.py tests/test_editor_autosave_cleanup.py tests/test_macos_bundle_runtime_paths.py`: pass
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_editor_autosave_cleanup.py -k "deferred_project_save or close_flush_failure"`: `7 passed, 44 deselected`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_runtime_cutover.py -k "save_export_cutover"`: `5 passed, 8 deselected`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_runtime_cutover.py tests/test_project_assets.py tests/test_editor_autosave_cleanup.py`: `71 passed`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_app_store_readiness_audit.py tests/test_macos_bundle_runtime_paths.py`: `9 passed`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_context.py tests/test_cp03_cp04_status_ui.py -k "schema or version or project_file_roundtrip or status"`: `66 passed, 79 deselected`
- Direct version assertion: `APP_VERSION=04.01.09`, `PROJECT_SCHEMA_VERSION=04.01.09`
- `git diff --check -- .`: pass

## Not Included

- No weakening of `nle_save_export_final_overlap`.
- No same-media quality/speed, save/reopen, global-canvas, or final export acceptance claim.
- No visible UI label, layout, color, shortcut, menu, popup, timeline strip, or minimap change.
- No STT/VAD algorithm, worker fan-out, model-selection, cache default, or subtitle-quality policy change.
- No persisted NLE disk-format cutover.
- No App Store package, validation, upload, metadata submission, or final App Store submission.

## Remaining Risks

- The final subtitle overlap that triggers `nle_save_export_final_overlap` remains an open G2/G3 blocker.
- G3 still needs same-media quality/speed, save/reopen, final export, and global-canvas acceptance before the broader runtime-visibility gate can close.
