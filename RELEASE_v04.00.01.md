# RELEASE v04.00.01

Release date: 2026-05-10
Phase: MAC_NATIVE_APPSTORE_V4_0_1_RELEASED
Base branch: `codex/mac-native-appstore`
Immediately previous release: `v04.00.00`
Release app version: `04.00.01`

## Summary

v04.00.01 is a macOS-native performance and stability release. It keeps the v04.00.00 Apple Silicon direction, but tightens the production runtime so only native paths with measured speed or quality benefit are enabled by default.

The release also keeps user-facing model choices intact while reducing accidental heavyweight work. STT routes stay user-selectable, native STT uses WhisperKit/Core ML/MLX where available, VAD alignment and LLM macro grouping use native C++ helpers, and Swift policy workers for LoRA, Deep Learning, and LLM candidates are isolated behind an explicit experimental gate until benchmarks prove both speed and LoRA ranking parity.

## Changes Since v04.00.00

- Added a central macOS native acceleration plan in `core/native_macos_acceleration.py` so STT, VAD, LoRA, Deep Learning, LLM, Swift quality scoring, and Swift common split routing are described and controlled in one place.
- Enabled benchmark-safe native defaults: WhisperKit/Core ML/MLX STT routing, C++ VAD interval overlap/alignment math, C++ LLM macro grouping, adaptive Swift batch quality scoring, and adaptive Swift common split planning.
- Locked Swift LoRA scoring, Swift Deep rerank, and Swift LLM candidate policy behind `native_swift_policy_experimental_enabled` or the explicit experimental environment gate because prior benchmarks showed slower behavior or changed LoRA top ranking.
- Reduced unnecessary Swift worker import/branch overhead in the LoRA, Deep Learning, and LLM candidate Python call sites when experimental native policy mode is not enabled.
- Updated Apple Silicon runtime planning so experimental Swift policy helpers are forced off in production while safe Swift batch thresholds can still respect manual override settings.
- Refined Fast, Auto, High, and STT Mode runtime policies around user-selected STT1/STT2 models, selective word timestamps, STT rescue behavior, VAD post-alignment, and LLM confidence gating.
- Added cut-boundary API/jump helpers and tests so editor cut navigation and adaptive cut-boundary level behavior can be verified independently.
- Expanded benchmark tooling for subtitle pipeline variants and LLM model variants using the local benchmark fixture folder.
- Updated model/default metadata so installed macOS-compatible STT and AI model choices are represented more consistently in settings.
- Hardened subtitle generation completion so STT progress cannot mark the editor complete before backend optimization, quality review, and saveable subtitle segments are ready.
- Added completion autosave retry behavior for the short window where backend subtitles are finalized but the editor/timeline model has not yet received saveable segments.
- Restored dirty-editor save confirmation for both quick exit and native window close paths before runtime pause, model cleanup, or app quit.
- Moved numbered project JSON backups into `프로젝트백업/` and migrated legacy root-level numbered backups into that folder on the next project save.

## Code Review Notes

- Reviewed the native policy gate path end-to-end so stale settings cannot accidentally re-enable slower Swift LoRA/Deep/LLM policy helpers during normal subtitle generation.
- Reviewed runtime override handling so only unproven policy workers are hard-disabled; safe native batch parameters remain configurable where manual override mode is active.
- Reviewed mode policy behavior so user-selected STT2 settings are preserved when the user explicitly enables them, while default Fast/Auto/High behavior avoids unnecessary secondary STT work.
- Reviewed benchmark-safe cut-boundary worker locks so the release does not reintroduce slower fanout or MPS follower paths for the current Apple Silicon workload.
- Reviewed generation finalization and autosave ordering so the UI does not show completion or attempt final save while the subtitle segment model is still empty.
- Reviewed project backup behavior so active project roots stay lightweight while preserving numbered JSON recovery files.

## Compatibility Notes

- `core/runtime/config.py` remains the source of truth for `APP_VERSION`.
- This branch remains macOS-only and Apple Silicon first.
- Existing project and settings files remain compatible. Legacy or user-saved Swift policy flags are normalized by runtime policy unless the experimental gate is explicitly enabled.
- STT1/STT2 model choices remain user-selectable; release defaults avoid unsupported or non-macOS-ready routes where possible.
- Existing root-level numbered project JSON backups are compatible and will be moved into `프로젝트백업/` automatically when the base project is next saved.

## Verification

Completed verification for this release:

- `python3 -m py_compile core/native_macos_acceleration.py core/native_swift_policy.py core/engine/llm_candidate_policy.py core/personalization/deep_subtitle_policy.py core/personalization/lora_retrieval_scoring.py core/runtime/multi_process.py core/mode_policy.py tests/test_runtime_multi_process.py tests/test_native_macos_acceleration.py tests/test_native_swift_adaptive.py tests/test_native_policy_engine.py`
- `venv/bin/python -m pytest -q tests/test_native_macos_acceleration.py tests/test_native_swift_adaptive.py tests/test_native_policy_engine.py tests/test_runtime_multi_process.py tests/test_subtitle_quality_pipeline.py tests/test_subtitle_engine_settings.py tests/test_word_resegmenter.py tests/test_npu_acceleration.py tests/test_runtime_optimization_profile.py tests/test_whisper_coreml.py tests/test_whisper_model_catalog.py tests/test_stt_quality_presets.py tests/test_mode_policy.py tests/test_stt_mode_policy.py`
  - `155 passed, 3 subtests passed in 0.97s`
- `./venv/bin/python -m py_compile ui/editor/editor_pipeline.py ui/main/main_file_ops.py ui/main/main_window.py core/project/project_manager.py tests/test_editor_autosave_cleanup.py tests/test_sidebar_terminal_layout.py tests/test_project_context.py`
- `./venv/bin/python -m pytest tests/test_editor_autosave_cleanup.py tests/test_sidebar_terminal_layout.py tests/test_project_context.py -q`
  - `102 passed in 21.84s`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest tests/test_gpu_rendering.py -q`
  - `22 passed in 0.03s`
- `git diff --check -- .`
- `venv/bin/python -m compileall -q main.py core ui tests tools`
- `QT_QPA_PLATFORM=offscreen venv/bin/python -c 'import sys; from PyQt6.QtWidgets import QApplication; from ui.main.main_window import MainWindow; app = QApplication(sys.argv); win = MainWindow(); print("MainWindow OK")'`
  - `MainWindow OK`
- `QT_QPA_PLATFORM=offscreen venv/bin/python -m pytest -q`
  - `1428 passed, 5 subtests passed in 57.91s`

Known warnings or limits:

- DMG/App Store packaging was not rebuilt because this release request did not explicitly ask for installer or distribution package generation.
- Swift LoRA/Deep/LLM policy helpers remain experimental until a benchmark proves both speed and output parity.

## Next Direction

Continue moving only quality-neutral or quality-positive heavy loops into Swift/C++ on Apple Silicon. Prioritize STT/VAD/cut-boundary/timing work where native code reduces runtime without changing subtitle decisions, and keep LoRA/Deep/LLM policy ranking in Python unless benchmark parity is proven.
