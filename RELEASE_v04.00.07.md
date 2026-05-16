# RELEASE v04.00.07

Release date: 2026-05-16
Phase: MAC_NATIVE_APPSTORE_V4_0_7_RELEASED
Base branch: `main`
Immediately previous release: `v04.00.06`
Release app version: `04.00.07`

## Summary

v04.00.07 is a performance, verification-surface, and project-persistence hardening release for the macOS Apple Silicon branch. It keeps the accuracy-first subtitle pipeline from v04.00.06, then focuses on making live processing feedback cleaner for users, moving a few proven hot paths into Swift where the bridge cost is justified, and reducing save/open/runtime memory churn without changing subtitle quality policy.

The release goal is to make the real app feel tighter during actual work: queue timing and lower-status feedback match runtime behavior more closely, the player/control surfaces expose richer source metadata, repeated project/media/runtime bookkeeping work is lighter, and project save/enrich flows stop dropping external subtitle or STT metadata during edge-case recovery.

## Changes Since v04.00.06

- Polished live editor/runtime UI behavior without changing subtitle-generation logic:
  - queue elapsed time now starts only after real execution begins;
  - lower-left pipeline stage colors and simplified terminal messages now align with the actual live stage state;
  - the player control bar now splits source metadata and filename into stable left/right halves;
  - bottom menu/canvas frame alignment and rounded-border clipping were corrected for the active editor shell.
- Added Swift-native media-probe normalization through `native/macos/AIStudioNative/Sources/AIStudioCore/MediaProbe.swift` plus `core/native_swift_media_info.py`, while keeping immediate Python fallback. Player/runtime metadata can now reuse normalized bitrate and color fields without reopening the Python shaping path.
- Added an adaptive native pipeline-status summarizer through `native/macos/AIStudioNative/Sources/AIStudioCore/PipelineStatus.swift` plus `core/native_swift_pipeline_status.py`, so larger multiline status blobs can use the native worker path while smaller updates stay on the lower-overhead Python parser.
- Reduced repeated cache/copy work across project/media/runtime hot paths:
  - media fingerprint digest reuse now avoids repeated final hash work for unchanged files;
  - project open/save can reuse persisted media header hints before falling back to fresh probing;
  - runtime logger/appctl status snapshots now reuse one log-tail read and cheaper filtered tail extraction;
  - thumbnail/runtime-memory/personalization bundle helpers now avoid avoidable rescans or repeated JSON/materialization work;
  - multiple project save/open helpers now reuse shared row-copy, frame-normalization, and external-track persistence paths instead of open-coded duplicate loops.
- Hardened external text-asset persistence and phase1b enrich flows after code review:
  - `save_project(...)` now externalizes the normalized project segment rows rather than raw input rows, so STT-selected source and candidate metadata survive ordinary subtitle edits;
  - empty-final-subtitle save passes now recover sibling `final.srt` independently from STT track recovery instead of overwriting external subtitle assets with an empty manifest;
  - phase1b enrich now externalizes normalized segments directly and falls back to already persisted STT tracks when rebuilt candidate tracks are temporarily absent.
- Added and expanded repository maintenance/review tooling:
  - `tools/check_maintenance_budget.py` now guards changed-file size/function-length and broad silent-exception regressions;
  - `tools/overnight_optimize.py` and `tools/verify_full_media_pipeline.py` keep optimization and full-media verification runs file-backed instead of chat-log heavy.

## Code Review Notes

- Fixed `tests/test_project_context.py::ProjectContextTests::test_project_save_and_phase1b_enrich_preserve_stt1_stt2_tracks` by preserving normalized STT metadata through save/externalize and phase1b enrich paths.
- Fixed `tests/test_project_context.py::ProjectContextTests::test_save_project_restores_external_asset_manifest_from_sibling_assets_when_segments_are_temporarily_empty` by recovering final subtitle assets independently from STT asset recovery when the in-memory subtitle list is transiently empty.
- Re-ran the broader save/open, media-cache, runtime-status, personalization, and UI regression suites before release to confirm the optimization batches did not change subtitle-quality behavior.

## Compatibility Notes

- `core/runtime/config.py` is the source of truth for `APP_VERSION` and now reports `04.00.07`.
- `core/project/project_format.py` now marks newly saved project payloads as schema version `04.00.07`.
- This branch remains macOS-only and Apple Silicon first.
- Local beta packaging continues to use ad-hoc signing for test builds, so Gatekeeper rejection remains expected until Developer ID notarization is configured.

## Verification

Completed verification for this release:

- `venv/bin/python -m pytest -q`
  - `2010 passed, 5 subtests passed in 140.49s (0:02:20)`
- `QT_QPA_PLATFORM=offscreen venv/bin/python` smoke for `ui.main.main_window.MainWindow`
  - `MainWindow OK`
- `venv/bin/python -m compileall -q main.py core ui tests`
- `git diff --check -- .`
- `swift test` in `native/macos/AIStudioNative`
  - `29 tests, 0 failures`
- `packaging/macos/build_beta_dmg.sh`
  - Built, signed, validated, and verified `/Users/u_mo_c/Downloads/ai_subtitle_studio/dist/macos/AI Subtitle Studio-04.00.07-macOS.dmg`
  - Gatekeeper assessment failed as expected for the ad-hoc local test build; notarization was skipped because `NOTARY_KEYCHAIN_PROFILE` was not configured

Additional targeted verification during review:

- `venv/bin/python -m pytest -q tests/test_project_context.py -k "test_project_save_and_phase1b_enrich_preserve_stt1_stt2_tracks or test_save_project_restores_external_asset_manifest_from_sibling_assets_when_segments_are_temporarily_empty"`
  - `2 passed`
- `venv/bin/python -m pytest -q tests/test_project_context.py tests/test_recovery_state.py tests/test_project_analysis_store.py tests/test_project_runtime_capture.py tests/test_media_fingerprint.py tests/test_performance_media_cache.py tests/test_video_preview_proxy.py tests/test_runtime_memory_manager.py tests/test_runtime_logger.py tests/test_runtime_multi_process.py tests/test_roughcut_thumbnail_cache.py tests/test_lora_personalization_storage.py tests/test_subtitle_accuracy_graph.py tests/test_stt_lattice.py tests/test_media_info_cache.py`
  - `208 passed`
- `venv/bin/python -m pytest -q tests/test_codex_provider.py tests/test_app_command_bridge.py tests/test_pipeline_status.py tests/test_cp03_cp04_status_ui.py tests/test_sidebar_terminal_layout.py tests/test_queue_dispatch.py tests/test_video_player_widget.py tests/test_editor_canvas_state.py tests/test_timeline_render_cache.py`
  - `300 passed`
- `swift test --filter 'MediaProbeNativeTests|PipelineStatusTests'`
  - `6 tests, 0 failures`

## Next Direction

The next useful follow-up is to keep shrinking the largest orchestration shells and remaining broad-exception cleanup targets, especially in `ui/editor/video_player_widget.py`, `ui/timeline/timeline_paint.py`, `core/project/project_manager.py`, and the cut-boundary/audio stacks, while holding the line on subtitle-quality parity and only moving code native where the payload size justifies the bridge cost.
