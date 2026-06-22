# Verification Results

This document is the current verification ledger. Keep detailed logs in `output/manual_verification/latest/` or release notes, not here.

## Current Baselines

### Full QA Baseline

- Artifact: `output/manual_verification/latest/qa_suite_full_20260522_081710`
- Command: `./venv/bin/python tools/qa_suite_runner.py full`
- Result: pass, `failed_count=0`
- Scenarios: `editor_compact_macau`, `video_menu_macau`, `save_export_macau`, `menu_stt_lora_macau`, `x5_high_rolling_180s`

### Source-App Quick Smoke

- Artifact: `output/manual_verification/latest/qa_suite_quick_20260525_141648`
- Command: `AI_SUBTITLE_STUDIO_QA_USE_SOURCE=1 ./venv/bin/python tools/qa_suite_runner.py quick`
- Result: pass, `failed_count=0`

### X5 Post-STT Hot-Path Proof

- Artifact: `output/manual_verification/latest/20260527_x5_hot_path_trim_proof/`
- Result: `ok=true`
- `pipeline_elapsed_sec=66.576`
- `total_elapsed_sec=71.285`
- `peak_rss_bytes=1776435200`
- `raw/final=49/56`
- Pressure transition: `critical -> warning`

### High-Refresh Editor/Timeline Proof

- Artifact: `output/manual_verification/latest/20260526_225507_high_refresh_source_app_proof/verification_summary.md`
- Scope: source-app editor/timeline visual proof for the high-refresh path.
- Caveat: keep Macau/X5 real-app proof separate from simulator/offscreen confidence.

## Latest Focused Checks

### 2026-06-23 Source-App Editor Geometry Quick

- Scope: source-app editor compact path, first editor interactions, diamond move/merge automation, and geometry capture after the editor-ready grace change.
- Command: `AI_SUBTITLE_STUDIO_QA_USE_SOURCE=1 ./venv/bin/python tools/qa_suite_runner.py quick --output-dir output/manual_verification/latest/20260623_editor_ready_geometry_source_quick_final9`
- Result: pass, `failed_count=0`
- Artifact: `output/manual_verification/latest/20260623_editor_ready_geometry_source_quick_final9`
- Evidence:
  - `editor_compact_macau` pass with isolated `_suite_fixtures/DJI_20260217224203_0075_D.aissproj` instead of saving the root ignored fixture.
  - `move_diamond_resolved.json`: previous runtime source, command `editor-move-diamond --side closest`.
  - `merge_diamond_resolved.json`: previous runtime source, command `editor-merge-diamond --side closest`.
  - `final_status.stdout`: geometry retained in the compact status payload; final `segment_count=35`, `status_response_truncated=true`.
  - Captured geometry includes `main_window 1710x966`, `video_frame 676x420`, `timeline_frame 1471x496`, `timeline_global_canvas 1451x99`, and splitter sizes `[218, 1477]` / `[790, 676]`.
- Additional checks:
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_editor_automation.py tests/test_qa_suite_runner.py tests/test_app_command_bridge.py tests/test_app_command_server.py`: `107 passed`
  - `./venv/bin/python -m py_compile ui/editor/editor_automation.py tools/qa_suite_runner.py core/automation/app_command_server.py ui/main/app_command_bridge_handlers.py`: pass
- Caveat: this proves source-app editor automation and geometry on the copied Macau fixture. The original Macau media folder and original X5 MP4 are still absent, so fresh post-generation media proof and X5 promotion remain separate.

### 2026-06-23 Post-Generation Editor-Ready Grace

- Change: completion background bundle (`_post_generation_resource_cleanup` + deferred waveform load) now waits for a short editor-ready grace window instead of running on the immediate `0ms` event turn.
- Scope: reduce post-generation interaction lock and first-click/playback contention without changing subtitle quality, UI layout, labels, or roughcut behavior.
- Command: `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_editor_autosave_cleanup.py tests/test_editor_roughcut_draft.py`
- Result: `104 passed`
- Additional focused checks:
  - `tests/test_sidebar_terminal_layout.py::SidebarTerminalLayoutTests::test_prioritize_video_playback_runtime_defers_heavy_release_while_starting_playback`
  - `tests/test_sidebar_terminal_layout.py::SidebarTerminalLayoutTests::test_prioritize_video_playback_runtime_skips_while_generation_is_still_running`
  - `tests/test_sidebar_terminal_layout.py::SidebarTerminalLayoutTests::test_prioritize_manual_editor_interaction_runtime_skips_while_generation_is_still_running`
  - Result: `3 passed`
- Caveat: this is an offscreen contract lock. Real source-app Macau/X5 geometry and first-interaction proof still need capture.

### 2026-06-22 Duplicate Subtitle Guard

- Command: `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_stt_recheck_service.py tests/test_subtitle_engine_settings.py tests/test_subtitle_accuracy_pipeline.py`
- Result: `170 passed, 1 skipped, 3 subtests passed`
- Additional checks:
  - `./venv/bin/python -m py_compile core/audio/stt_recheck_service.py core/engine/subtitle_final_integrity.py core/engine/subtitle_engine.py core/engine/subtitle_accuracy_pipeline.py`: pass
  - `git diff --check`: pass
- Synthetic repro: close duplicate STT2 recheck rows and output-selector tandem repeats now both return `["안 바뀌어요"]`.
- X5 cached replay artifact: `output/manual_verification/latest/20260622_233750_duplicate_guard_x5_cached/summary.md`
  - Result: pass; accepted X5 output has `0` tandem repeats, `0` close duplicate pairs, and current final cleanup reapplies without changing the text sequence.
  - Stress probes from the X5 `안 바뀌어요` row: tandem repeat, adjacent duplicate, and recheck replacement duplicate all collapse to one row.
- Follow-up guard: standalone measurement rows such as `11.4` are preserved before expanded measurement phrases instead of being shadow-dropped or merged into the previous continuation row.
- Focused retest: `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_subtitle_engine_settings.py::SubtitleEngineSettingsTests::test_final_sequence_cleanup_collapses_exact_tandem_repeat_inside_row tests/test_subtitle_engine_settings.py::SubtitleEngineSettingsTests::test_final_sequence_cleanup_keeps_standalone_measurement_before_expanded_phrase tests/test_stt_recheck_service.py::STTRecheckServiceTests::test_merge_segments_with_replacements_dedupes_close_duplicate_recheck_rows` -> `3 passed`.
- Caveat: this is a cached real-X5 artifact replay, not a fresh media benchmark promotion; `test video/X5_시승기_후반.MP4` is not present in the current checkout.

### 2026-06-22 Subtitle Accuracy Regression Lock

- Command: `./venv/bin/python -m pytest -q tests/test_subtitle_engine_settings.py tests/test_benchmark_mode_profiles.py`
- Result: `108 passed, 1 skipped, 3 subtests passed`
- Scope: all-singleton digit common-split guard regression and benchmark profile behavior.
- Caveat: this is a regression lock, not accepted benchmark artifact promotion.

### 2026-06-22 Jammini Route Recovery Check

- Command: `tools/jammini_watchdog.sh --conversation-id auto --once --dry-run --dispatch-cooldown-sec 0`
- Result: project-matching Antigravity conversation selected, `STATE_UNCHANGED=yes`
- Scope: dry-run route selection and watchdog state safety.
- Caveat: dry-run proves routing selection, not worker execution quality.

### 2026-06-22 Documentation Cleanup

- Scope: compact development docs, remove merged scratch/decision/reference docs, keep guarded reference maps.
- Result: pass.
- Completed checks:
  - `find doc -maxdepth 4 -type f | sort`
  - `for f in doc/idea.md doc/DECISIONS/server_mode_benchmarking.md doc/reference/CODEMAP.md doc/reference/File_structure.txt; do test ! -e "$f" || exit 1; done`: pass
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_subtitle_generation_domain_map.py`: `4 passed`
  - `git diff --check -- AGENTS.md doc tools/cooperation_bootstrap.sh`: pass
  - trailing-whitespace scan for `AGENTS.md` and `doc/`: pass

## Update Rules

- Add only current verification summaries here.
- Store long logs, screenshots, JSON, and generated media under `output/manual_verification/latest/`.
- Keep release history in `doc/releases/`.
- Do not use this file as an active task queue. Use `doc/ACTION_ITEMS.md`.
