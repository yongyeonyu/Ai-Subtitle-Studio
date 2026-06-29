<!--
Document-Version: 04.01.31-codemap
Last-Updated: 2026-06-29
Updated-By: Codex
Purpose: Concise responsibility map for token-efficient code navigation.
-->
# CODEMAP.md

## Purpose

Use this file for fast navigation. It is intentionally responsibility-driven and compact.

- Use `docs/project_reference/File_structure.txt` for shallow orientation only.
- Use `docs/project_reference/CODEMAP.md` for deciding which files to inspect first.
- Use `rg` for exact call sites, symbol lookups, and follow-up detail.

## Entry Points

- `main.py`: desktop app bootstrap.
- `ui/main/main_window.py`: top-level application window and runtime wiring.
- `ui/main/app_command_bridge.py`: automation/appctl command execution inside the running app.
- `tools/appctl.py`: external command-line entry point for remote app control.
- `tools/remote_verify.py`: higher-level remote verification runner, artifact capture, and G3 live NLE runtime observability proof harness.
- `tools/qa_suite_runner.py`: official one-command QA runner for `quick`, `major`, and `full` profiles.
- `tools/automation_command_client.py`: retry-aware command client used by appctl and verification helpers for read-only status/ping surfaces.
- `tools/debug_guided_subtitle_memory.py`: guided subtitle repeat-run memory/status debugger for Macau/X5/Tinyping performance investigations.
- `tools/overnight_optimize.py`: compact baseline/check runner that writes long-run artifacts under `output/manual_verification/latest/`.
- `tools/benchmark_tiniping_mode_search.py`: CLI entry point for Tiniping mode search and regression-pack generation.
- `tools/benchmark_tiniping_timing_ideas.py`: Tiniping timing-idea benchmark runner for reference-aligned timing experiments.
- `tools/tiniping_mode_search_phases.py`: phase-by-phase Tiniping search orchestration for primary/pair/audio/method/cached/long validation passes.
- `tools/subtitle_regression_pack.py`: repeatable subtitle regression-pack builder for X5, Macau, and Tinyping artifacts under `output/manual_verification/latest/`.
- `tools/check_maintenance_budget.py`: changed-file guard for file/function length and broad silent-exception regressions.
- `tools/verify_full_media_pipeline.py`: full-media verification runner with top-level performance/quality summary metrics.
- `tools/audit_app_store_readiness.py`: non-destructive Mac App Store readiness blocker audit with version lock, stoplight, blocker-group, strict codesign, and package-signature gates.
- `tools/generate_app_store_metadata_package.py`: Mac App Store owner-input metadata package generator; writes checklist/matrix/guardrail artifacts without claiming submission proof.
- `tools/check_app_store_owner_metadata_values.py`: Mac App Store owner metadata values preflight helper; validates explicit owner values JSON, approval evidence, URL ownership, signed-candidate screenshot binding, App Store Connect metadata, and forbidden-copy claims.
- `tools/check_app_store_upload_preflight.py`: Mac App Store upload preflight helper; requires exact readiness JSON, exact `.pkg` binding, no blockers, and all submission gates true before upload mode can run.
- `tools/generate_stt_cache_default_review_packet.py`: G1 STT collect-cache owner-review packet generator; summarizes existing NAS cache write/hit evidence without enabling production cache defaults.
- `tools/generate_nle_canonical_load_owner_review_packet.py`: G2 NLE canonical load-owner owner-review packet generator; summarizes NLE persistence cutover audit evidence without changing project load ownership.
- `tools/audit_nle_persistence_cutover.py`: G2 NLE persistence audit; includes explicit top-level `nle` caption plus gap compatibility projection, canonical load-owner gate matrix, rollback-boundary proof, owner-approved top-level canonical load opt-in proof, owner-approved standalone `nle_snapshot` load-source opt-in proof, supplemental `_nle_project_state` persistence opt-in proof, legacy-compatible `editor_state` row replacement opt-in proof, and final source-app persistence load-owner opt-in proof.

## UI Areas

- `ui/editor/editor_widget.py`: main editor composition root.
- `ui/editor/video_player_widget.py`: video player composition root with frame/seek helpers and shared wiring.
- `ui/editor/video_player_overlay_mixin.py`: video subtitle overlay layout, QWidget/QML fallback ownership, and export-style paint routing.
- `ui/editor/video_player_transport.py`: transport controls, quick-control-bar sync, frame-step hold, and playback status widgets.
- `ui/editor/video_player_audio.py`: audio-output creation, route rebinding, and vocal-player lifecycle helpers.
- `ui/editor/video_player_surface.py`: media-source loading, preview proxy, thumbnail/surface stack, and navigation/shutdown handling.
- `ui/editor/video_player_subtitles.py`: subtitle overlay context/provider refresh and lookup logic for the video player.
- `ui/home/ux/auto_source_settings_dialog.py`: dedicated NAS/iCloud auto-source settings popup flow and shared sidebar state bridge.
- `ui/ux/`: reusable Apple-black popup palette/theme helpers and shared UX color tables.
- `ui/editor/ux/`: editor interaction mixins.
  - `editor_timeline_video.py`: playback sync, playhead behavior, editor/timeline coordination.
  - `editor_timeline_gap_split.py`: gap conversion/generation plus smart-split interaction scenarios.
  - `editor_segments_live_preview.py`: in-progress STT/subtitle preview rows and preview-stage coordination.
  - `timeline_input.py`: timeline mouse/key input, scrubbing, drag entry points.
  - `timeline_subtitle_segment_editing.py`: segment-edge, center, diamond drag, snap behavior.
- `ui/timeline/`: timeline rendering and viewport systems.
  - `timeline_widget.py`: scroll/zoom container, playhead overlay, fit behavior.
  - `timeline_canvas.py`: timeline state, frame/second math, hit targets.
  - `timeline_paint.py`: painter rendering path.
- `ui/project/`: multiclip/project session UI.
- `ui/home_sidebar.py`, `ui/queue_widget.py`: home dashboard, queue status, progress cards.
- `ui/queue/queue_state_model.py`: canonical queue row state, progress snapshots, and widget/sidebar/top-card synchronization seams.
- `ui/settings/settings_dictionary.py`: correction-dictionary management dialog and CRUD/search workflow.
- `ui/editor/editor_session_model.py`: lightweight editor subtitle/STT/preview lane session model extracted from owner widgets.

## Pipeline Areas

- `core/pipeline/`: queue/runtime orchestration and backend coordination.
- `core/audio/`: audio extraction, preprocessing, STT/VAD backend routing.
  - `media_processor_audio.py`: adaptive audio routing, chunk profile memory, preview guard, selective split experiments.
  - `media_processor_transcribe.py`: rolling STT windows, overlap/hysteresis finalize, ensemble window orchestration.
  - `preset_auto_classifier.py`: auto audio profile classification and candidate ranking.
- `core/engine/`: subtitle generation, scoring, timing, correction, LLM chunking.
  - `subtitle_timing.py`: final timing fusion, piecewise drift experiments, common split guards.
- `core/llm/`: provider routing and model adapters.
- `core/roughcut/`: roughcut draft and LLM-assisted roughcut logic.

## Project And Persistence

- `core/project/`: project JSON, snapshots, model settings, timeline metadata.
- `core/project/project_assets.py`: external text-asset/SRT persistence, row-copy helpers, and STT candidate-track cache shaping.
- `core/project/project_runtime_capture.py`: editor auxiliary project-state copy helpers plus lightweight status-count snapshots.
- `core/project/project_session_service.py`: project open/save/reopen/resume lifecycle service and serialization entry seam.
- `core/project/nle_persistence_guard.py`: NLE persistence policy guard for legacy shadow metadata, explicit top-level canonical load opt-in, standalone `nle_snapshot` load-source opt-in, supplemental `_nle_project_state` persistence opt-in, legacy disk-shape replacement opt-in, and unapproved future payload quarantine.
- `core/project/nle_project_state.py`: runtime NLE sequence/project-state model plus approved supplemental persisted runtime-state payload serialization and hydration helpers.
- `core/project/nle_snapshot.py`: NLE snapshot builders plus top-level `nle` / `nle_snapshot` row projection helpers.
- `core/project/project_context.py`: project load-to-editor projection, including explicit top-level `nle` canonical opt-in with `nle_snapshot` companion drift fail-closed to legacy rows.
- `core/project/project_format.py`: project storage payload builder, version/schema ownership, approved NLE snapshot/top-level/runtime-state metadata persistence, legacy-compatible `editor_state` row projection, and rollback key preservation.
- `core/mode_manager.py`: central Fast/Auto/High/STT mode ownership and user-selectable model snapshot policy.
- `core/audio/stt_quality_presets.py`: benchmark-locked Fast/Auto/High defaults, VAD lock notes, and STT recommendation tags.
- `core/mode_policy.py`: runtime mode enforcement layer that applies benchmark-locked mode settings on top of persisted user model routes.
- `core/speaker_profile_settings.py`: learned speaker-profile enablement and runtime diarization preference policy.
- `ui/editor/editor_project_open_native.py`: SRT/project open flows and workspace restore.
- `ui/editor/editor_save_manager.py`: save/export/project persistence actions.

## Native And Performance

- `native/macos/AIStudioNative/`: Swift-native package for shared macOS-first core logic.
- `native/macos/AIStudioNative/Sources/AIStudioCore/TimelineEditing*.swift`: split Swift timeline core; models/contracts, drag geometry, magnet passes, preview/STT selection, and persistence/serialization now live in separate files.
- `native/macos/AIStudioNative/Sources/AIStudioCore/RuntimeETAEstimator*.swift`: split Swift ETA core; public API, request parsing, prediction math, and store persistence are separated for smaller native migration seams.
- `core/native/_native_cut_boundary.cpp`: native cut-boundary scan/alignment hot loop used behind Python parity checks.
- `core/native/_native_stt_lattice.cpp`, `core/native_stt_lattice.py`, `core/audio/stt_lattice_service.py`: native-backed STT lattice helpers with Python fallback and parity tests.
- `core/native/_native_stt_recheck.cpp`, `core/native_stt_recheck.py`, `core/audio/stt_recheck_service.py`: native-backed STT recheck candidate helpers with Python fallback and parity tests.
- `core/subtitle_core_contract.py`, `core/native_swift_subtitle_core.py`, `native/macos/AIStudioNative/Sources/AIStudioCore/SubtitleCore.swift`: subtitle-core contract and current Swift bridge seam for future native migration.
- `core/native_swift_*.py`: Python bridges into Swift/native functionality.
- `core/runtime_eta.py`: queue/startup ETA estimation and history.
- `core/performance.py`: runtime profiling and performance helpers.
- `core/pipeline_status.py`: current-stage summary reduction and native/Python adaptive status parsing.
- `core/runtime/logger.py`: staged runtime log buffer, recent-tail reads, and appctl/status log-summary hot path.
- `core/media_info.py`: ffprobe normalization, media-probe cache keys, and copy-safe probe result helpers.
- `core/native_swift_media_info.py`, `core/native_swift_pipeline_status.py`: native bridge entry points for media probe/status hot paths.
- `core/runtime/memory_manager.py`: runtime RSS snapshots plus streaming disk-cache accounting/pruning.
- `core/runtime/memory_trim_summary.py`: per-stage trim rollup helper for repeated subtitle-generation memory diagnostics.
- `core/runtime/subtitle_resource_manager.py`: runtime active-label helpers, accelerator flags, and live NLE projection scheduler-budget telemetry.

## Hot Verification Map

- Timeline/playhead/zoom/smart split:
  - `tests/test_timeline_playhead_fit.py`
  - `tests/test_timeline_hit_targets.py`
  - `tests/test_timeline_render_cache.py`
  - `tests/test_editor_split_undo.py`
  - `tests/test_editor_open_layout.py`
- Video subtitle overlay:
  - `tests/test_video_player_widget.py`
  - `tests/test_editor_video_context_window.py`
  - `tests/test_project_segment_reload.py`
- App automation and remote control:
  - `tests/test_app_command_bridge.py`
  - `tests/test_app_command_server.py`
  - `tests/test_app_command_protocol.py`
  - `tests/test_automation_command_client.py`
  - `tests/test_remote_verify_actions.py`
  - `tests/test_qa_suite_runner.py`
- Media probe/cache performance:
  - `tests/test_media_info_cache.py`
- Full-media verification summaries:
  - `tests/test_verify_full_media_pipeline.py`
- Audio/adaptive-routing and timing regressions:
  - `tests/test_audio_presets.py`
  - `tests/test_preset_auto_classifier.py`
  - `tests/test_media_processor_overlap.py`
  - `tests/test_subtitle_engine_settings.py`
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
- Editor multiline/timeline drag regressions:
  - `tests/test_subtitle_line_breaks.py`
  - `tests/test_timeline_hit_targets.py`
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
  - `ui/editor/video_player_overlay_mixin.py`
  - `ui/editor/video_player_subtitles.py`
  - `ui/editor/editor_segments_timeline_context.py`
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
