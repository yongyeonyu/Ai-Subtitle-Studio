# RELEASE v04.01.03

Date: 2026-06-29
Previous release: `v04.01.02`
Release app version: `04.01.03`

## Summary

`v04.01.03` is a focused source-app G3 runtime NLE lane owner-map checkpoint.

This release adds a read-only runtime track contract for VAD, STT1, STT2, subtitle-preview, and final lanes while preserving final subtitle authority for render/export/save surfaces.

## Key Changes

- Version and schema:
  - `core/runtime/config.py` now reports `APP_VERSION = "04.01.03"`.
  - `core/project/project_format.py` now marks newly saved project payloads as schema version `04.01.03`.

- Runtime NLE lane contract:
  - `core/engine/subtitle_live_editor_feed.py` now exposes `runtime_tracks` for `VAD`, `STT1`, `STT2`, `subtitle_preview`, and `final`.
  - Runtime reference tracks carry `_nle_runtime_role=runtime_reference_only` and `_nle_save_export_authority=false`.
  - The final track is the only track marked authoritative for save/export.

- Final authority guard:
  - `core/project/nle_runtime_cutover.py` now rejects runtime reference rows from final overlay, global canvas, and save/export projection even if those rows contain text.
  - Timeline canvas can still preserve runtime reference rows for display/projection without promoting them to final output.

## Validation

- `./venv/bin/python -m py_compile core/engine/subtitle_live_editor_feed.py core/project/nle_runtime_cutover.py tests/test_subtitle_live_editor_feed_facade.py tests/test_project_nle_runtime_cutover.py`: pass
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_subtitle_live_editor_feed_facade.py tests/test_project_nle_runtime_cutover.py`: `17 passed`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_subtitle_live_editor_feed_facade.py tests/test_subtitle_stt_segments_facade.py tests/test_subtitle_global_canvas_facade.py tests/test_project_nle_runtime_cutover.py`: `25 passed`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py -k "global_canvas_silence_and_subtitle_lanes_share_expanded_height_evenly or timeline_update_segments_can_project_final_only_rows_to_global_canvas"`: `2 passed, 191 deselected`
- Direct version assertion: `APP_VERSION=04.01.03`, `PROJECT_SCHEMA_VERSION=04.01.03`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_app_store_readiness_audit.py tests/test_macos_bundle_runtime_paths.py`: `9 passed`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_context.py tests/test_cp03_cp04_status_ui.py -k "schema or version or project_file_roundtrip or status"`: `66 passed, 79 deselected`
- `git diff --check -- .`: pass
- Jammini route proof: `.agents/sentinel/handoffs/20260629-010211-watchdog-handoff-probe.md`
- Jammini G3 scout: `.agents/sentinel/handoffs/20260628-230544-nle-g3-runtime-lane-owner-map-scout-jammini.md`

## Not Included

- No UI/UX label, layout, color, shortcut, menu, or popup behavior change.
- No new global-canvas strip or visible timeline redesign.
- No scheduler/resource-budget change.
- No persisted `_nle_project_state` or canonical NLE disk-format load-owner cutover.
- No STT2 skip, word-precision skip, model downgrade, VAD visual-cut override, or cache default promotion.
- No App Store `.pkg`, validation, upload, or submission.

## Remaining Risks

- G3 still needs separate bounded slices for live status/feed wiring, scheduler budget enforcement, and visual/runtime proof.
- Mac App Store submission remains blocked on Distribution/Installer identities, signed `.pkg`, sandbox smoke, App Store Connect validation, and owner metadata.
