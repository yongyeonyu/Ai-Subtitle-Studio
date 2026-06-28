# RELEASE v04.01.12

Date: 2026-06-29
Previous release: `v04.01.11`
Release app version: `04.01.12`

## Summary

`v04.01.12` is a focused source-app G3 app-command save/reopen/export checkpoint.

This release fixes direct-SRT app-command project save so the saved project and external subtitle asset preserve the opened SRT rows instead of re-splitting them at project cut boundaries. It also proves the same project can be reopened through the app-command bridge and exported again with matching SRT block count and nonzero MOV output bytes.

## Key Changes

- Version and schema:
  - `core/runtime/config.py` now reports `APP_VERSION = "04.01.12"`.
  - `core/project/project_format.py` now marks newly saved project payloads as schema version `04.01.12`.

- Direct-SRT project save stability:
  - `save-project` now reports the segment count it passes to the project saver.
  - App-command `save-project` uses the same SRT-output segment authority as `save-subtitles` and `export-subtitles`.
  - Direct SRT edit mode skips project-save cut-boundary re-splitting, so save/reopen preserves the opened SRT row count.
  - Default non-direct-SRT project save cut-boundary behavior remains enabled.

## Evidence

- Direct SRT save/export proof: `output/manual_verification/latest/g3_same_media_app_commands_srt_fixed_v2_20260629/report.md`
- Reopen/export proof: `output/manual_verification/latest/g3_same_media_app_commands_reopen_fixed_v2_20260629/report.md`
- Direct-SRT saved project check: `projects/heydealer_first_180s_from_nas.aissproj` and `projects/heydealer_first_180s_from_nas.assets/subtitles/final.srt` both saved `64` final rows during the proof.
- Three sub-agent reviews were used for architecture, QE, and editor-workflow guardrails.

## Validation

- `./venv/bin/python -m py_compile core/project/project_manager.py ui/project/project_panel.py ui/editor/editor_save_manager.py ui/main/app_command_bridge_handlers.py tests/test_project_context.py tests/test_app_command_bridge.py`: pass
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_context.py -k "skip_cut_boundary_snap_for_direct_srt_rows or cut_boundary_fit_prevents"`: `2 passed, 85 deselected`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_app_command_bridge.py -k "save_project_command"`: `4 passed, 78 deselected`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_app_command_bridge.py tests/test_project_context.py tests/test_editor_autosave_cleanup.py tests/test_project_segment_reload.py tests/test_project_nle_runtime_cutover.py tests/test_project_assets.py -k "save_project_command or skip_cut_boundary_snap_for_direct_srt_rows or direct_srt or deferred_project_save or save_export_cutover or externalize"`: `37 passed, 297 deselected`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_app_store_readiness_audit.py tests/test_macos_bundle_runtime_paths.py`: `9 passed`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_context.py tests/test_cp03_cp04_status_ui.py -k "schema or version or project_file_roundtrip or status"`: `66 passed, 80 deselected`
- Direct-SRT app-command save/export proof: save-project `segment_count=64`, export-subtitles `segment_count=64`, manual export SRT `64` blocks, editor final count `64`, project saved row count `64`, project final SRT `64` blocks, MOV output `6764026` bytes.
- Reopen/export proof: reopened editor final count `64`, export-subtitles `segment_count=64`, manual export SRT `64` blocks, NLE runtime final track `64`, MOV output `6764026` bytes.
- Direct version assertion: `APP_VERSION=04.01.12`, `PROJECT_SCHEMA_VERSION=04.01.12`
- `git diff --check -- .`: pass

## Not Included

- No full G3 completion claim.
- No UI label, layout, color, shortcut, menu, popup, timeline strip, or minimap change.
- No STT/VAD algorithm, worker fan-out, model-selection, cache default, or subtitle-quality policy change.
- No persisted NLE disk-format cutover.
- No App Store package, validation, upload, metadata submission, or final App Store submission.

## Remaining Risks

- `open-media` generation app-command proof, active-worker cancel/quit/close responsiveness, and broader same-media global-canvas responsiveness remain separate G3 proof gates.
- G0 App Store remains blocked on Apple Distribution/Installer identities, signed `.pkg`, sandbox smoke, App Store Connect validation, and owner metadata.
