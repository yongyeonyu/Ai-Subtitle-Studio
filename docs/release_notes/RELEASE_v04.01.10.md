# RELEASE v04.01.10

Date: 2026-06-29
Previous release: `v04.01.09`
Release app version: `04.01.10`

## Summary

`v04.01.10` is a focused source-app G2/G3 final save/export checkpoint.

This release repairs tiny final SRT/frame-quantization overlaps by projecting them to a shared boundary before final save/export surfaces are written. It keeps the strict `nle_save_export_final_overlap` guard intact for broader or collapse-risk overlaps and does not claim full same-media save/reopen, final export, global-canvas, or quality/speed acceptance.

## Key Changes

- Version and schema:
  - `core/runtime/config.py` now reports `APP_VERSION = "04.01.10"`.
  - `core/project/project_format.py` now marks newly saved project payloads as schema version `04.01.10`.

- Final save/export micro-overlap repair:
  - `core/project/nle_runtime_cutover.py` now repairs final save/export overlaps up to the greater of one frame or `0.035s` by moving the later row to the previous shared boundary when the row remains valid.
  - Broader or collapse-risk overlaps still raise `nle_save_export_final_overlap`.
  - Direct opened-media SRT persistence and the `export-subtitles` app-command path now route final rows through the same NLE save/export projection before writing SRT.

## Evidence

- Jammini route proof: `.agents/sentinel/handoffs/20260629-032124-watchdog-handoff-probe.md`
- Three sub-agent reviews were used for architecture, QE, and editor-workflow guardrails.
- Live SRT projection artifact: `output/manual_verification/latest/nle_save_export_micro_overlap_v040110_20260629/micro_overlap_report.md`
  - source/projected rows: `64/64`
  - overlap: `1 -> 0`
  - repaired row count: `1`
- Project-5 projection artifact: `output/manual_verification/latest/nle_save_export_micro_overlap_v040110_20260629/project5_micro_overlap_report.md`
  - source/projected rows: `170/170`
  - repair count: `2`
  - projected overlap count: `0`

## Validation

- `./venv/bin/python -m py_compile core/project/nle_runtime_cutover.py ui/editor/editor_save_manager.py ui/main/app_command_bridge_handlers.py tests/test_project_nle_runtime_cutover.py tests/test_project_assets.py tests/test_editor_autosave_cleanup.py tests/test_app_command_bridge.py tests/test_macos_bundle_runtime_paths.py`: pass
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_runtime_cutover.py -k "save_export_cutover or micro_overlap"`: `8 passed, 7 deselected`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_assets.py -k "externalize_project_text_assets"`: `5 passed, 3 deselected`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_editor_autosave_cleanup.py -k "persist_editor_srts or deferred_project_save or close_flush_failure"`: `9 passed, 43 deselected`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_app_command_bridge.py -k "export_subtitles_command or save_subtitles_command or status"`: `22 passed, 59 deselected`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_runtime_cutover.py tests/test_project_assets.py tests/test_editor_autosave_cleanup.py tests/test_app_command_bridge.py`: `156 passed`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_app_store_readiness_audit.py tests/test_macos_bundle_runtime_paths.py`: `9 passed`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_context.py tests/test_cp03_cp04_status_ui.py -k "schema or version or project_file_roundtrip or status"`: `66 passed, 79 deselected`
- Direct version assertion: `APP_VERSION=04.01.10`, `PROJECT_SCHEMA_VERSION=04.01.10`
- `git diff --check -- .`: pass

## Not Included

- No weakening of `nle_save_export_final_overlap`.
- No row dropping to hide final overlaps.
- No same-media quality/speed, save/reopen, global-canvas, or final export acceptance claim.
- No visible UI label, layout, color, shortcut, menu, popup, timeline strip, or minimap change.
- No STT/VAD algorithm, worker fan-out, model-selection, cache default, or subtitle-quality policy change.
- No persisted NLE disk-format cutover.
- No App Store package, validation, upload, metadata submission, or final App Store submission.

## Remaining Risks

- G3 still needs same-media quality/speed, save/reopen, final export, global-canvas, and UI/app-command responsiveness acceptance before the broader runtime-visibility gate can close.
- Multiclip SRT persistence was intentionally left unchanged because local-offset rows need a separate owner-map before widening this projection path.
