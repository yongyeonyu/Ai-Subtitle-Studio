# RELEASE v04.00.11

Release date: 2026-05-20
Phase: MAC_NATIVE_APPSTORE_V4_0_11_RELEASED
Base branch: `auto_action_item`
Immediately previous release: `v04.00.10`
Release app version: `04.00.11`

## Summary

v04.00.11 is a focused reliability, automation, and performance release for repeated subtitle generation on memory-constrained Apple Silicon Macs. It keeps subtitle-quality defaults conservative, but changes the runtime cleanup policy when the system reaches critical memory pressure so STT and LLM residency cannot keep slowing later runs through compression and swap.

This release also lands the one-command QA runner, records the current Macau/X5/Tinyping optimization ideas, splits oversized Swift native-core files, adds native-backed STT candidate helper seams with Python fallbacks, and fixes the video subtitle preview path so editor selection/playhead automation and project-open restores show the same subtitle context in the video overlay.

## Changes Since v04.00.10

- Hardened repeated-generation cleanup under memory pressure.
  - `core/audio/media_processor_transcribe.py` now avoids reusing STT collect worker caches when the runtime memory stage is `critical`.
  - STT release cleanup now drops macOS WhisperKit/MLX persistent workers under `critical` pressure instead of keeping them warm.
  - `core/runtime/memory_manager.py` now allows `SubtitleGenerationMemoryGuard.checkpoint()` to force GPU/runtime cleanup on critical checkpoints even when the caller requested a lighter checkpoint.
- Added focused performance review artifacts.
  - `idea_item.md` records quality-preserving speed ideas from Macau/X5/Tinyping benchmarking.
  - `idea_item.md` now also records the aggressive Apple Silicon acceleration plan: stage-DAG execution, STT1/STT2 runtime split, CoreML/ANE VAD isolation, LLM parallel parity checks, and Swift/C++ batch scoring candidates.
  - `waste_action_item.md` records candidates that should not be repeated after benchmark regression or weak evidence.
  - `ACTION_ITEMS.md` now keeps the follow-up trim-cost and memory-pressure work in the active optimization queue.
- Added the official one-command QA runner.
  - `tools/qa_suite_runner.py` runs `quick`, `major`, and `full` profiles against real app sequences and Tinyping full-media slices.
  - `test_case.md`, `test_result.md`, `README.md`, and `AGENTS.md` now document the runner recipes, artifact expectations, and current full-pass baseline.
  - The latest current-code bundle refreshed full run is `output/manual_verification/latest/qa_suite_full_20260520_210149`.
- Improved app-command automation under busy runtime work.
  - `core/automation/app_command_server.py` now lets read-only `ping`, `status`, and `guided-subtitle-status` requests run concurrently while state-changing commands remain serialized.
  - `ui/main/app_command_bridge.py` was split with `ui/main/app_command_bridge_handlers.py` so command families are easier to review and the maintenance-budget guard can pass.
  - Remaining busy-state timeout risk is tracked in `ACTION_ITEMS.md` item 12.
- Hardened MPS crash-prone paths without changing subtitle quality.
  - `ui/main/main_window.py` defers runtime memory trimming while editor/backend AI work is busy.
  - `core/runtime/memory_manager.py` records `trim_deferred_reason=busy_runtime_work` and stage-level trim summaries.
  - `core/audio/diarize.py` keeps SpeechBrain diarization off torch/MPS by default on macOS unless explicitly opted in.
- Advanced native-library seams without changing default subtitle quality.
  - `core/audio/stt_lattice_service.py`, `core/native_stt_lattice.py`, and `core/native/_native_stt_lattice.cpp` add a tested native-backed STT lattice helper path.
  - `core/audio/stt_recheck_service.py`, `core/native_stt_recheck.py`, and `core/native/_native_stt_recheck.cpp` add a tested native-backed STT recheck helper path.
  - `core/cut_boundary_verify_strategy.py` narrows cut-boundary verification strategy ownership before deeper native migration.
  - `RuntimeETAEstimator.swift` and `TimelineEditing.swift` were split into smaller Swift files so future native acceleration work can stay scoped.
- Fixed video subtitle overlay freshness in editor verification paths.
  - `ui/editor/editor_segments_timeline_context.py` and `ui/editor/editor_segments_stt_selection_flow.py` now feed the live preview window into the video subtitle provider during generation and STT candidate preview.
  - `ui/editor/ux/editor_timeline_video.py` now syncs paused segment selection to the video player's subtitle display time.
  - `ui/editor/video_player_overlay_mixin.py` now uses the QWidget subtitle label as the visible fallback when no QML subtitle overlay is active, because macOS video surfaces can composite above `QGraphicsScene` subtitle items.
  - `ui/editor/video_player_subtitles.py` now reapplies hidden widget overlays instead of only checking the scene overlay.
- Kept UI/UX behavior scoped.
  - No arbitrary layout redesign was made.
  - The overlay fix only restores expected subtitle text visibility for the existing video preview.
  - Current mode labels and sidebar workflows remain unchanged.

## Code Review Notes

- Review found that paused editor selection could move the timeline playhead without moving the video subtitle lookup time, so the visible video overlay could stay stale until playback or another refresh. The selection sync path now updates both.
- Review also found that relying on the `QGraphicsScene` subtitle item is not sufficient on macOS video surfaces. The QWidget label fallback is now the visible non-QML owner, while the scene item stays cleared to avoid duplicate overlay paint.
- The memory-pressure cleanup is intentionally gated to `critical` so normal-memory runs still keep the persistent STT worker warm for speed.
- The MPS crash mitigation intentionally avoids making torch/MPS a default diarization path on macOS, and defers trim calls during busy AI work instead of interrupting the active subtitle pipeline.
- App-command read-only concurrency improves observability during busy work, but it does not claim item 12 is fully closed; post-save/export `ping` collapse remains tracked.
- Native STT helper paths keep Python fallbacks and focused tests; they are not promoted as a blanket quality-changing algorithm.
- Review found the new native STT helper modules were missing from the standard native-extension build script; `tools/build_native_extensions.py` now compiles them with the existing release build command.

## Compatibility Notes

- `core/runtime/config.py` is the source of truth for `APP_VERSION` and now reports `04.00.11`.
- `core/project/project_format.py` now marks newly saved project payloads as schema version `04.00.11`.
- This branch remains macOS-only and Apple Silicon first.
- DMG packaging remains opt-in and was not run for this release.

## Verification

Completed verification for this release:

- Python syntax and diff hygiene
  - `./venv/bin/python -m compileall -q core ui tests tools`
  - `git diff --check -- core ui tests tools ACTION_ITEMS.md NATIVE_LIB_PLAN.md idea_item.md test_case.md waste_action_item.md`
- Native extension build
  - `./venv/bin/python tools/build_native_extensions.py build_ext --inplace`
- Focused unittest sweep
  - `./venv/bin/python -m unittest tests.test_video_player_widget tests.test_timeline_playhead_fit tests.test_editor_video_context_window tests.test_project_segment_reload tests.test_runtime_memory_manager tests.test_media_processor_overlap tests.test_action_item_runtime_services tests.test_ollama_provider tests.test_app_command_bridge tests.test_cut_boundary_verify_strategy tests.test_stt_lattice_service tests.test_stt_recheck_service tests.test_timeline_paint_passes tests.test_qml_popup_guard -q`
  - Result: `468 tests OK`
- App-command, QA runner, memory, and MPS focused checks
  - `./venv/bin/python -m unittest tests.test_app_command_server tests.test_app_command_bridge tests.test_automation_command_client tests.test_remote_verify_actions tests.test_qa_suite_runner tests.test_runtime_memory_manager tests.test_diarize_dependencies tests.test_sidebar_terminal_layout tests.test_timeline_playhead_fit tests.test_verify_full_media_pipeline -q`
  - Result: `335 tests OK`; after the maintenance-guard helper extraction, targeted rerun `tests.test_mode_policy tests.test_diarize_dependencies tests.test_sidebar_terminal_layout tests.test_runtime_memory_manager tests.test_app_command_bridge` also passed with `183 tests OK`.
- Swift native-core checks
  - `swift test --package-path native/macos/AIStudioNative`
  - Result: `38 tests OK`
- One-command QA runner
  - `./packaging/macos/build_app_bundle.sh`
  - `./venv/bin/python tools/qa_suite_runner.py full`
  - Result: pass, `scenario_count=7`, `failed_count=0`
  - Artifact: `output/manual_verification/latest/qa_suite_full_20260520_210149`
- Earlier memory-pressure focused checks from the same release pass
  - `./venv/bin/python -m unittest tests.test_runtime_memory_manager tests.test_media_processor_overlap.MediaProcessorOverlapTests.test_release_after_transcribe_keeps_macos_persistent_worker_warm tests.test_media_processor_overlap.MediaProcessorOverlapTests.test_release_after_transcribe_stops_warm_worker_under_critical_memory -q`
  - Result: `24 tests OK`
  - `./venv/bin/python -m py_compile core/runtime/memory_manager.py core/audio/media_processor_transcribe.py tests/test_runtime_memory_manager.py tests/test_media_processor_overlap.py`
  - Result: OK
- Real Macau app verification
  - Generated subtitles for `/Users/u_mo_c/Downloads/마카오테스트/DJI_20260217225132_0079_D.MP4`.
  - Produced `/Users/u_mo_c/Downloads/마카오테스트/DJI_20260217225132_0079_D.srt` with 5 final cues.
  - Preserved snapshots under `output/manual_verification/latest/20260520_macau_guided_snapshot/`.
  - Confirmed video subtitle overlay at `28.995633s` in `12_overlay_mid_segment.png`.
- Real Macau fast smoke from the same release pass
  - `./venv/bin/python tools/verify_full_media_pipeline.py --media "/Users/u_mo_c/Downloads/마카오테스트/DJI_20260217225132_0079_D.MP4" --mode fast --output-dir output/manual_verification/latest/20260520_macau_fast_memory_pressure_smoke`
  - Result: success, media duration `42.743s`, total elapsed `7.466s`, pipeline elapsed `6.994s`, peak RSS `266076160`, final segments `5`.

## Next Direction

The next optimization pass should use the recorded Macau/X5/Tinyping ideas to measure stage-level trim cost before loosening more cleanup calls. If repeated generation still slows down, inspect Ollama runner residency, `SubtitleGenerationMemoryGuard` trim frequency, and STT selective recheck cost before changing subtitle-quality defaults.
