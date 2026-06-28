# RELEASE v04.01.08

Date: 2026-06-29
Previous release: `v04.01.07`
Release app version: `04.01.08`

## Summary

`v04.01.08` is a focused source-app G3 representative real-media live runtime observability checkpoint.

This release proves that compact live status can observe VAD, STT1, and STT2 runtime tracks on a NAS-derived HeyDealer first-180s run while preserving final-authority and projection-budget guards. It does not claim same-media quality/speed, save/reopen, or final export acceptance.

## Key Changes

- Version and schema:
  - `core/runtime/config.py` now reports `APP_VERSION = "04.01.08"`.
  - `core/project/project_format.py` now marks newly saved project payloads as schema version `04.01.08`.

- G3 real-media live observability:
  - `core/engine/subtitle_live_editor_feed.py` now counts STT-source-tagged subtitle-preview rows as runtime-reference STT1/STT2 observations without making them final save/export authority.
  - `ui/main/app_command_bridge.py` preserves compact `live_nle_projection_budget` telemetry in normal and busy/fallback status snapshots.
  - `tools/remote_verify.py live-nle-proof` records status timeout/cache/fallback/truncation diagnostics and no longer infers completion from cached timeout status alone.

## Evidence

- NAS MP4/SRT preflight: `output/manual_verification/latest/g3_live_nle_real_media_preflight_20260629/reference_fixture_availability.md`
  - `ready_for_reference_scored_benchmark=true`
  - `segment_count=615`, `clipped_segment_count=89`
- Representative live proof: `output/manual_verification/latest/g3_live_nle_real_media_observability_timeout20_20260629/live_nle_runtime_proof.md`
  - `status=passed`, `issues=[]`
  - `failed_sample_count=0`, `generation_completed=true`
  - pre-final VAD/STT1/STT2 observations `16/172/44`
  - raw leak, final-authority drift, and projection-budget failures all empty
  - snapshot count `21`

## Validation

- `./venv/bin/python -m py_compile core/engine/subtitle_live_editor_feed.py ui/main/app_command_bridge.py tools/remote_verify.py tests/test_subtitle_live_editor_feed_facade.py tests/test_app_command_bridge.py tests/test_remote_verify_actions.py tests/test_macos_bundle_runtime_paths.py`: pass
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_subtitle_live_editor_feed_facade.py tests/test_app_command_bridge.py tests/test_remote_verify_actions.py`: `95 passed`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_remote_verify_actions.py tests/test_app_command_bridge.py tests/test_app_command_server.py tests/test_subtitle_live_editor_feed_facade.py tests/test_project_nle_runtime_cutover.py`: `117 passed`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_app_store_readiness_audit.py tests/test_macos_bundle_runtime_paths.py`: `9 passed`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_context.py tests/test_cp03_cp04_status_ui.py -k "schema or version or project_file_roundtrip or status"`: `66 passed, 79 deselected`
- Direct version assertion: `APP_VERSION=04.01.08`, `PROJECT_SCHEMA_VERSION=04.01.08`
- `git diff --check -- .`: pass
- Jammini route proof: `.agents/sentinel/handoffs/20260629-023155-watchdog-handoff-probe.md`

## Not Included

- No visible UI label, layout, color, shortcut, menu, popup, timeline strip, or minimap change.
- No STT/VAD algorithm, worker fan-out, model-selection, cache default, or subtitle-quality policy change.
- No persisted NLE disk-format cutover.
- No App Store package, validation, upload, metadata submission, or final App Store submission.
- No same-media quality/speed, save/reopen, global-canvas, or final export acceptance claim.

## Remaining Risks

- The live run saved SRT successfully but then exposed `nle_save_export_final_overlap` in save/export and repeated deferred-save retry failures. Keep that guard strict and fix it as a separate G2/G3 blocker before claiming broader save/reopen or final-export readiness.
- G3 still needs same-media quality/speed evidence before the broader runtime-visibility acceptance gate can close.
