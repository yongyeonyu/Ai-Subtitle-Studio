# RELEASE v04.01.04

Date: 2026-06-29
Previous release: `v04.01.03`
Release app version: `04.01.04`

## Summary

`v04.01.04` is a focused source-app G3 compact live status-feed checkpoint.

This release wires compact VAD/STT1/STT2/subtitle-preview/final runtime lane counts into `status`, `ping`, and `guided-subtitle-status` without sending raw candidate rows or changing visible UI layout.

## Key Changes

- Version and schema:
  - `core/runtime/config.py` now reports `APP_VERSION = "04.01.04"`.
  - `core/project/project_format.py` now marks newly saved project payloads as schema version `04.01.04`.

- Compact runtime status:
  - `SubtitleLiveEditorFeed.runtime_status()` exposes count/active/role/authority fields only.
  - `ui/editor/editor_automation.py` builds compact `nle_runtime_tracks` from final rows, live STT preview rows, live subtitle-preview rows, and VAD rows.
  - `ui/main/app_command_bridge.py` exposes `nle_runtime_track_counts` through `status`, `ping`, and `guided-subtitle-status`.
  - `core/automation/app_command_server.py` preserves `nle_runtime_track_counts` when oversized UDP status responses are compacted.

## Validation

- `./venv/bin/python -m py_compile core/engine/subtitle_live_editor_feed.py ui/editor/editor_automation.py ui/main/app_command_bridge.py core/automation/app_command_server.py tests/test_subtitle_live_editor_feed_facade.py tests/test_app_command_bridge.py tests/test_app_command_server.py`: pass
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_subtitle_live_editor_feed_facade.py tests/test_app_command_bridge.py tests/test_app_command_server.py tests/test_project_nle_runtime_cutover.py`: `106 passed`
- Direct version assertion: `APP_VERSION=04.01.04`, `PROJECT_SCHEMA_VERSION=04.01.04`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_app_store_readiness_audit.py tests/test_macos_bundle_runtime_paths.py`: `9 passed`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_context.py tests/test_cp03_cp04_status_ui.py -k "schema or version or project_file_roundtrip or status"`: `66 passed, 79 deselected`
- `git diff --check -- .`: pass
- Jammini route proof: `.agents/sentinel/handoffs/20260629-012024-watchdog-handoff-probe.md`
- Jammini compact-feed review: `.agents/sentinel/handoffs/20260628-232716-g3-compact-status-feed-review-jammini.md`

## Not Included

- No UI/UX label, layout, color, shortcut, menu, or popup behavior change.
- No new global-canvas strip, minimap row, or visible timeline redesign.
- No scheduler/resource-budget change.
- No persisted `_nle_project_state` or canonical NLE disk-format load-owner cutover.
- No STT2 skip, word-precision skip, model downgrade, VAD visual-cut override, or cache default promotion.
- No App Store `.pkg`, validation, upload, or submission.

## Remaining Risks

- G3 still needs separate bounded slices for scheduler budget enforcement and visual/runtime proof.
- Mac App Store submission remains blocked on Distribution/Installer identities, signed `.pkg`, sandbox smoke, App Store Connect validation, and owner metadata.
