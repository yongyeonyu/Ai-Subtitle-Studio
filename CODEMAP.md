<!--
Document-Version: 04.00.06-codemap
Last-Updated: 2026-05-16
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

## UI Areas

- `ui/editor/editor_widget.py`: main editor composition root.
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
- `ui/editor/editor_project_open_native.py`: SRT/project open flows and workspace restore.
- `ui/editor/editor_save_manager.py`: save/export/project persistence actions.

## Native And Performance

- `native/macos/AIStudioNative/`: Swift-native package for shared macOS-first core logic.
- `core/native_swift_*.py`: Python bridges into Swift/native functionality.
- `core/runtime_eta.py`: queue/startup ETA estimation and history.
- `core/performance.py`: runtime profiling and performance helpers.

## Hot Verification Map

- Timeline/playhead/zoom/smart split:
  - `tests/test_timeline_playhead_fit.py`
  - `tests/test_timeline_hit_targets.py`
  - `tests/test_editor_split_undo.py`
  - `tests/test_editor_open_layout.py`
- App automation and remote control:
  - `tests/test_app_command_bridge.py`
  - `tests/test_app_command_protocol.py`
- Queue/progress/runtime ETA:
  - `tests/test_queue_dispatch.py`
  - `tests/test_pipeline_status.py`
  - `tests/test_runtime_eta.py`
- Project open/save/reload:
  - `tests/test_project_context.py`
  - `tests/test_project_runtime_capture.py`
  - `tests/test_project_segment_reload.py`
  - `tests/test_editor_srt_open_refresh.py`
- Roughcut:
  - `tests/test_editor_roughcut_draft.py`
  - `tests/test_roughcut_*.py`

## Real Media Fixtures

- Short smoke and UI/runtime checks:
  - `/Users/u_mo_c/Downloads/마카오테스트`
- Long runtime/performance checks:
  - `/Users/u_mo_c/Downloads/티니핑/티니핑_유스어드벤처.MP4`
- Accuracy truth/reference pair:
  - `/Users/u_mo_c/Downloads/ai_subtitle_studio/test video/X5_시승기_후반.MP4`
  - sibling `.srt`

## Current Hot Paths

- Restart/completed-state recovery:
  - `ui/editor/editor_pipeline.py`
  - `ui/editor/editor_pipeline_completion.py`
  - `ui/editor/editor_pipeline_startup.py`
- Appctl/live verification:
  - `ui/main/app_command_bridge.py`
  - `ui/editor/editor_automation.py`
  - `tools/appctl.py`
  - `tools/remote_verify.py`
- Timeline editing UX:
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
