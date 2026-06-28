# RELEASE v04.01.05

Date: 2026-06-29
Previous release: `v04.01.04`
Release app version: `04.01.05`

## Summary

`v04.01.05` is a focused source-app G3 live NLE projection scheduler-budget telemetry checkpoint.

This release exposes a compact runtime budget report proving that live VAD/STT/NLE status projection uses existing row snapshots, coalesces updates, drops stale preview frames, and does not take worker threads from the subtitle conversion path.

## Key Changes

- Version and schema:
  - `core/runtime/config.py` now reports `APP_VERSION = "04.01.05"`.
  - `core/project/project_format.py` now marks newly saved project payloads as schema version `04.01.05`.

- Live NLE projection budget:
  - `core/runtime/subtitle_resource_manager.py` adds `live_nle_projection_scheduler_budget(...)`.
  - The budget reports `dedicated_worker_count=0`, `max_projection_workers=0`, `shares_subtitle_worker_pool=false`, `uses_existing_row_snapshots=true`, `coalesces_updates=true`, and `drops_stale_preview_frames=true`.
  - VAD, save, export, and close foreground labels are detected from cheap runtime booleans without reading preview row payloads.
  - Warning/foreground states increase the coalesce interval, while critical/exit states disable projection.

- Runtime/status telemetry:
  - `RuntimeResourceCoordinator.poll()` attaches `live_nle_projection_budget` to the runtime resource snapshot.
  - `status`, `ping`, `guided-subtitle-status`, and UDP status compaction preserve the compact budget telemetry without raw STT/VAD/subtitle-preview rows.

## Validation

- `./venv/bin/python -m py_compile core/runtime/subtitle_resource_manager.py core/runtime/multi_process.py core/automation/app_command_server.py tests/test_subtitle_resource_manager.py tests/test_runtime_multi_process.py tests/test_app_command_bridge.py tests/test_app_command_server.py`: pass
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_subtitle_resource_manager.py tests/test_runtime_multi_process.py tests/test_app_command_bridge.py tests/test_app_command_server.py`: `135 passed`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_subtitle_live_editor_feed_facade.py tests/test_app_command_bridge.py tests/test_app_command_server.py tests/test_project_nle_runtime_cutover.py tests/test_runtime_multi_process.py tests/test_subtitle_resource_manager.py tests/test_action_item_runtime_services.py tests/test_runtime_stage_metrics.py tests/test_project_nle_render_export_parity.py tests/test_subtitle_global_canvas_facade.py`: `171 passed`
- Direct version assertion: `APP_VERSION=04.01.05`, `PROJECT_SCHEMA_VERSION=04.01.05`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_app_store_readiness_audit.py tests/test_macos_bundle_runtime_paths.py`: `9 passed`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_context.py tests/test_cp03_cp04_status_ui.py -k "schema or version or project_file_roundtrip or status"`: `66 passed, 79 deselected`
- Jammini route proof: `.agents/sentinel/handoffs/20260629-013822-watchdog-handoff-probe.md`
- Jammini scheduler-budget review: `.agents/sentinel/handoffs/20260628-234452-nle-g3-scheduler-budget-telemetry-review-jammini.md`

## Not Included

- No UI/UX label, layout, color, shortcut, menu, or popup behavior change.
- No new global-canvas strip, minimap row, or visible timeline redesign.
- No actual worker fan-out increase, full-parallel STT default, STT2 skip, word-precision skip, model downgrade, VAD visual-cut override, or cache default promotion.
- No persisted `_nle_project_state` or canonical NLE disk-format load-owner cutover.
- No App Store `.pkg`, validation, upload, or submission.

## Remaining Risks

- G3 still needs separate visual/runtime proof showing progressively observable VAD/STT1/STT2 tracks during a real generation run.
- Mac App Store submission remains blocked on Distribution/Installer identities, signed `.pkg`, sandbox smoke, App Store Connect validation, and owner metadata.
