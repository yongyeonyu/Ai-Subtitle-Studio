<!--
Document-Version: 04.00.09-codemap
Last-Updated: 2026-05-18
Updated-By: Codex
Purpose: Concise responsibility map for token-efficient code navigation.
-->
# CODEMAP.md

## Purpose

Use this file for fast navigation. It is intentionally responsibility-driven and compact.

- Use `File_structure.txt` for shallow orientation only.
- Use `CODEMAP.md` for deciding which files to inspect first.
- Use `rg` for exact call sites, symbol lookups, and follow-up detail.

## Entry Points

- `main.py`: desktop app bootstrap.
- `ui/main/main_window.py`: top-level application window and runtime wiring.
- `ui/main/app_command_bridge.py`: automation/appctl command execution inside the running app.
- `tools/appctl.py`: external command-line entry point for remote app control.
- `tools/remote_verify.py`: higher-level remote verification runner and artifact capture.
- `tools/overnight_optimize.py`: compact baseline/check runner that writes long-run artifacts under `output/manual_verification/latest/`.
- `tools/benchmark_tiniping_mode_search.py`: CLI entry point for Tiniping mode search and regression-pack generation.
- `tools/tiniping_mode_search_phases.py`: phase-by-phase Tiniping search orchestration for primary/pair/audio/method/cached/long validation passes.
- `tools/subtitle_regression_pack.py`: repeatable subtitle regression-pack builder for X5, Macau, and Tinyping artifacts under `output/manual_verification/latest/`.
- `tools/check_maintenance_budget.py`: changed-file guard for file/function length and broad silent-exception regressions.
- `tools/verify_full_media_pipeline.py`: full-media verification runner with top-level performance/quality summary metrics.

## UI Areas

- `ui/editor/editor_widget.py`: main editor composition root.
- `ui/editor/video_player_widget.py`: video player composition and transport shell.
- `ui/editor/video_player_subtitles.py`: subtitle overlay context/provider refresh and lookup logic for the video player.
- `ui/home/ux/auto_source_settings_dialog.py`: dedicated NAS/iCloud auto-source settings popup flow and shared sidebar state bridge.
- `ui/ux/`: reusable Apple-black popup palette/theme helpers and shared UX color tables.
- `ui/editor/ux/`: editor interaction mixins.
  - `editor_timeline_video.py`: playback sync, playhead behavior, editor/timeline coordination.
  - `timeline_input.py`: timeline mouse/key input, scrubbing, drag entry points.
  - `timeline_subtitle_segment_editing.py`: segment-edge, center, diamond drag, snap behavior.
- `ui/timeline/`: timeline rendering and viewport systems.
  - `timeline_widget.py`: scroll/zoom container, playhead overlay, fit behavior.
  - `timeline_canvas.py`: timeline state, frame/second math, hit targets.
  - `timeline_paint.py`: painter rendering path.
- `ui/project/`: multiclip/project session UI.
- `ui/home_sidebar.py`, `ui/queue_widget.py`: home dashboard, queue status, progress cards.

## Pipeline Areas

- `core/pipeline/`: queue/runtime orchestration and backend coordination.
- `core/audio/`: audio extraction, preprocessing, STT/VAD backend routing.
- `core/engine/`: subtitle generation, scoring, timing, correction, LLM chunking.
- `core/llm/`: provider routing and model adapters.
- `core/roughcut/`: roughcut draft and LLM-assisted roughcut logic.

## Project And Persistence

- `core/project/`: project JSON, snapshots, model settings, timeline metadata.
- `core/project/project_assets.py`: external text-asset/SRT persistence, row-copy helpers, and STT candidate-track cache shaping.
- `core/project/project_runtime_capture.py`: editor auxiliary project-state copy helpers plus lightweight status-count snapshots.
- `core/mode_manager.py`: central Fast/Auto/High/STT mode ownership and user-selectable model snapshot policy.
- `core/audio/stt_quality_presets.py`: benchmark-locked Fast/Auto/High defaults, VAD lock notes, and STT recommendation tags.
- `core/mode_policy.py`: runtime mode enforcement layer that applies benchmark-locked mode settings on top of persisted user model routes.
- `ui/editor/editor_project_open_native.py`: SRT/project open flows and workspace restore.
- `ui/editor/editor_save_manager.py`: save/export/project persistence actions.

## Native And Performance

- `native/macos/AIStudioNative/`: Swift-native package for shared macOS-first core logic.
- `core/native_swift_*.py`: Python bridges into Swift/native functionality.
- `core/runtime_eta.py`: queue/startup ETA estimation and history.
- `core/performance.py`: runtime profiling and performance helpers.
- `core/pipeline_status.py`: current-stage summary reduction and native/Python adaptive status parsing.
- `core/runtime/logger.py`: staged runtime log buffer, recent-tail reads, and appctl/status log-summary hot path.
- `core/media_info.py`: ffprobe normalization, media-probe cache keys, and copy-safe probe result helpers.
- `core/native_swift_media_info.py`, `core/native_swift_pipeline_status.py`: native bridge entry points for media probe/status hot paths.
- `core/runtime/memory_manager.py`: runtime RSS snapshots plus streaming disk-cache accounting/pruning.

## Hot Verification Map

- Timeline/playhead/zoom/smart split:
  - `tests/test_timeline_playhead_fit.py`
  - `tests/test_timeline_hit_targets.py`
  - `tests/test_timeline_render_cache.py`
  - `tests/test_editor_split_undo.py`
  - `tests/test_editor_open_layout.py`
- App automation and remote control:
  - `tests/test_app_command_bridge.py`
  - `tests/test_app_command_protocol.py`
- Media probe/cache performance:
  - `tests/test_media_info_cache.py`
- Full-media verification summaries:
  - `tests/test_verify_full_media_pipeline.py`
- Queue/progress/runtime ETA:
  - `tests/test_queue_dispatch.py`
  - `tests/test_pipeline_status.py`
  - `tests/test_runtime_logger.py`
  - `tests/test_runtime_eta.py`
  - `tests/test_runtime_memory_manager.py`
- Project open/save/reload:
  - `tests/test_project_assets.py`
  - `tests/test_project_context.py`
  - `tests/test_project_runtime_capture.py`
  - `tests/test_project_segment_reload.py`
  - `tests/test_editor_srt_open_refresh.py`
- Roughcut:
  - `tests/test_editor_roughcut_draft.py`
  - `tests/test_roughcut_*.py`
- Mode defaults / benchmark locks:
  - `tests/test_stt_quality_presets.py`
  - `tests/test_mode_policy.py`
  - `tests/test_benchmark_mode_profiles.py`

## Real Media Fixtures

- Short smoke and UI/runtime checks:
  - `/Users/u_mo_c/Downloads/마카오테스트`
- Long runtime/performance checks:
  - `/Users/u_mo_c/Downloads/티니핑/티니핑_유스어드벤처.MP4`
- Accuracy truth/reference pair:
  - `/Users/u_mo_c/Downloads/ai_subtitle_studio/test video/X5_시승기_후반.MP4`
  - sibling `.srt`

## Current Hot Paths

- Mode/preset ownership and persistence:
  - `core/mode_manager.py`
  - `core/settings_profiles.py`
  - `core/personalization/settings_autopilot.py`
- Sidebar auto-source UX and popup styling:
  - `ui/home/ux/auto_source_settings_dialog.py`
  - `ui/ux/apple_black_palette.py`
  - `ui/ux/apple_popup_theme.py`
- Restart/completed-state recovery:
  - `ui/editor/editor_roughcut_draft.py`
  - `ui/main/main_runtime_cleanup.py`
  - `ui/editor/editor_pipeline.py`
  - `ui/editor/editor_pipeline_completion.py`
  - `ui/editor/editor_pipeline_startup.py`
- Appctl/live verification:
  - `ui/main/app_command_bridge.py`
  - `ui/editor/editor_automation.py`
  - `tools/appctl.py`
  - `tools/remote_verify.py`
- Timeline editing UX:
  - `ui/timeline/timeline_roughcut_paint.py`
  - `ui/editor/ux/timeline_input.py`
  - `ui/editor/ux/timeline_subtitle_segment_editing.py`
  - `ui/timeline/timeline_widget.py`
  - `ui/timeline/timeline_canvas.py`
- Sidebar runtime layout and responsive shell:
  - `ui/home_sidebar.py`
  - `ui/home_ui.py`
  - `ui/sidebar/home_sidebar_nav_widget.py`
  - `ui/main/main_window.py`

## Maintenance Rule

Keep this file short. Update it when a refactor changes module ownership, entry points, or the first files a future assistant should inspect.
