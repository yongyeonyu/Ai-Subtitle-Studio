# RELEASE v04.01.17

Date: 2026-06-29
Previous release: `v04.01.16`
Release app version: `04.01.17`

## Summary

`v04.01.17` is a focused source-app G0 quick QA baseline checkpoint before packaging.

This release refreshes the current source-app quick QA baseline for the Mac App
Store lane without treating it as packaging, sandbox, validation, upload, or
submission proof.

## Key Changes

- Version and schema:
  - `core/runtime/config.py` now reports `APP_VERSION = "04.01.17"`.
  - `core/project/project_format.py` now marks newly saved project payloads as schema version `04.01.17`.

- Source-app quick QA baseline:
  - Quick QA was rerun at `output/manual_verification/latest/qa_suite_quick_v040117_20260629_0929`.
  - Result: `profile=quick`, `scenario_count=1`, scenario `editor_compact_macau`, `passed_count=1`, `failed_count=0`.
  - The proof scope is source-app compact editor workflow baseline only: project open, snapshots, playhead, smart split, inline edit, timeline view controls, global-menu save/status, play/pause command, segment/diamond edit, save, and final status.

## Evidence

- Quick QA baseline: `output/manual_verification/latest/qa_suite_quick_v040117_20260629_0929/suite_result.md`
- Three sub-agent reviews were used for release boundary, QE, and editor-workflow wording guardrails.
- Jammini `--status` resolved the active route. The current `--handoff-probe` packet did not produce a fresh physical handoff file, so `.agents/sentinel/handoffs/20260629-070211-watchdog-handoff-probe.md` remains the latest physical route proof.

## Validation

- `AI_SUBTITLE_STUDIO_QA_USE_SOURCE=1 QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/qa_suite_runner.py quick --output-dir output/manual_verification/latest/qa_suite_quick_v040117_20260629_0929`: `failed_count=0`
- `./venv/bin/python -m py_compile core/runtime/config.py core/project/project_format.py tests/test_macos_bundle_runtime_paths.py`: pass
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_macos_bundle_runtime_paths.py`: `4 passed`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_context.py tests/test_cp03_cp04_status_ui.py -k "schema or version or project_file_roundtrip or status"`: `66 passed, 80 deselected`
- Direct version assertion: `APP_VERSION=04.01.17`, `PROJECT_SCHEMA_VERSION=04.01.17`
- `git diff --check -- .`: pass

## Not Included

- No App Store submission-ready claim.
- No Apple Distribution signed `.app`.
- No signed App Store `.pkg`.
- No `pkgutil --check-signature` pass.
- No sandbox workflow smoke.
- No App Store Connect validation, upload, or submission.
- No owner metadata, privacy, export compliance, screenshot, review-note, age-rating, or release-note completion.
- No full QA, real-media STT quality, roughcut, or X5 rolling proof.
- No Developer ID DMG work or claim that a DMG is Mac App Store submission evidence.
- No UI/UX, subtitle-generation, cache-default, NLE behavior, or worker-scheduling change.

## Remaining Risks

- G0 remains blocked until the required Apple Distribution and 3rd Party Mac Developer Installer identities, exact signed `.pkg`, sandbox smoke, App Store Connect validation, upload/submission decision, and owner-approved metadata values are available.
