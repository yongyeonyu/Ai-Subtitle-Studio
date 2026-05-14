<!--
Document-Version: 04.00.05-mac-native
Phase: MAC_NATIVE_APPSTORE_V4_0_5_RELEASED
Last-Updated: 2026-05-14
Updated-By: Codex
Purpose: Remaining work queue only.
-->
# ACTION_ITEMS.md - Remaining Work Queue

## Queue Policy

- This file contains only unfinished or parked work.
- Completed items must be removed instead of kept as history.
- Release history belongs in `RELEASE_v*.md`.
- Bootstrap and operating rules belong in `AGENTS.md`.
- Product overview belongs in `README.md`.
- Actual file tree belongs in `File_structure.txt`.

## Metadata

```yaml
app_version: "04.00.05"
document_version: "04.00.05-mac-native"
phase: "MAC_NATIVE_APPSTORE_V4_0_5_RELEASED"
next_phase: null
commit_policy: "Commit only when the user explicitly asks."
product_priority: "Accuracy before speed."
run_all_exclusions: []
root_forbidden_files:
  - "create_all*"
  - "_backup*"
  - "STRUCTURE.txt"
  - "requirements.txt"
required_requirement_files:
  - "requirements-mac.txt"
no_touch_without_user_request:
  - "dataset/video_preview_cache/"
release_handoff_files:
  - "AGENTS.md"
  - "ACTION_ITEMS.md"
  - "File_structure.txt"
  - "README.md"
  - "latest RELEASE_v*.md"
review_scope:
  - "core/**/*.py"
  - "ui/**/*.py"
  - "ui/qml/**/*.qml"
  - "native/macos/AIStudioNative/Sources/**/*.swift"
  - "core/native/**/*.cpp"
review_excluded_generated:
  - "venv/"
  - "build/"
  - "dist/"
  - "output/"
  - "projects/"
  - "__pycache__/"
review_method:
  - "Repository-wide AST complexity scan"
  - "Repository-wide duplicate helper scan"
  - "Repository-wide dead-code candidate scan (vulture/high-confidence)"
  - "Repository-wide broad-exception and silent-pass scan"
  - "Manual hotspot review of main UI, editor, timeline, project, audio, pipeline, roughcut, personalization, and native core modules"
```

## Active Work

### P0 - Stability and architectural debt that is now slowing every release

- [ ] Split `ui/editor/editor_segments.py` into focused modules.
  Goal: separate live preview ingest, subtitle row selection, batch queue flush, save-time normalization, and STT candidate management.
  Why: this file is 3,651 lines, 98 functions, and currently owns too many unrelated editor behaviors.
  Progress: live preview ingest/seam helpers, STT candidate selection helpers, manual STT selection flow/timeline preview redraw, queue append/flush flow, current document-to-segment serialization, bulk-load row normalization, queue post-flush/autoseek policy, bulk-load document apply/finalize steps, text search/replace, popup-trigger, line-edit mutation helpers, shared segment reload flow, manual edit/split handlers, timeline redraw/context/drag lifecycle, low-level block surgery helpers, and dirty/runtime activity/cache invalidation helpers are now extracted into `ui/editor/editor_segments_live_preview.py`, `ui/editor/editor_segments_stt_candidates.py`, `ui/editor/editor_segments_stt_selection_flow.py`, `ui/editor/editor_segments_queue_flush.py`, `ui/editor/editor_segments_current_state.py`, `ui/editor/editor_segments_bulk_prepare.py`, `ui/editor/editor_segments_text_ops.py`, `ui/editor/editor_segments_reload.py`, `ui/editor/editor_segments_manual_edits.py`, `ui/editor/editor_segments_timeline_context.py`, `ui/editor/editor_segments_block_surgery.py`, and `ui/editor/editor_segments_runtime_cache.py`.
  Remaining targets: `editor_multiclip` stack의 남은 orchestration polish와 owner synchronization 예외 정리입니다. owner/runtime state access는 `ui/editor/editor_multiclip_owner_bridge.py`와 `ui/editor/editor_multiclip_runtime_state.py`로 이미 상당 부분 축소됐습니다.

- [ ] Split `ui/editor/editor_pipeline.py` into lifecycle-safe services.
  Goal: isolate backend start/stop orchestration, queue updates, post-process cleanup, and partial rerun logic.
  Why: this file mixes UI mutation, worker lifecycle, state recovery, and exception swallowing; it is one of the highest-risk regression zones.
  Progress: processing/abort helpers and generation-complete cleanup/autosave/fallback recovery helpers are now extracted into `ui/editor/editor_pipeline_cleanup.py`; backend signal wiring plus cut-boundary placeholder bridge are now extracted into `ui/editor/editor_pipeline_signal_bridge.py`; partial rerun state preparation and `_run_partial_backend` worker orchestration are now extracted into `ui/editor/editor_pipeline_partial_rerun.py`; startup/prescan/layout restore orchestration is now extracted into `ui/editor/editor_pipeline_startup.py`; live processing stage/progress/final status updates are now extracted into `ui/editor/editor_pipeline_status.py`; generation-complete UI sync/deferred-learning/resource-cleanup orchestration is now extracted into `ui/editor/editor_pipeline_completion.py`; playhead menu/cut-boundary submenu/manual rerun actions are now extracted into `ui/editor/editor_pipeline_playhead_actions.py`.
  Remaining targets: `ui/editor/editor_pipeline.py` itself is now mostly a composition shell; the remaining work is broad-exception cleanup and a few direct UI/backend convenience calls across the extracted pipeline service modules.

- [ ] Split `ui/editor/video_player_widget.py` into overlay, transport, and provider adapters.
  Goal: move playback controls, subtitle overlay state, frame sync, and provider-specific rendering into separate units.
  Why: 2,184 lines and 140 functions makes this the single largest UI function surface; playback regressions are hard to isolate.
  Extra note: several silent exception blocks here hide video subtitle overlay failures.

- [ ] Break up `ui/timeline/timeline_paint.py` and stop using one giant `paintEvent`.
  Goal: move row layout, subtitle lane text painting, helper-line painting, selection overlays, and playhead/marker painting into separate paint passes.
  Why: `paintEvent` alone is 1,341 lines, which makes rendering behavior fragile and hard to benchmark.
  Success condition: each paint pass becomes independently testable and cacheable.

- [ ] Refactor the cut-boundary stack away from monolithic helper builders.
  Files: `core/pipeline/cut_boundary_helpers.py`, `core/cut_boundary_auto_scan.py`, `core/cut_boundary_auto_verify.py`, `core/cut_boundary.py`.
  Goal: replace giant helper-install functions and embedded closures with explicit strategy objects.
  Why: the worst functions in the repository are here, including a 1,788-line helper builder and 1,096-line scan routine.
  Priority reason: this area also drives many of the recent UI helper-line regressions.

- [ ] Split `core/pipeline/single_pipeline.py` into a pure execution planner and a UI-bound progress coordinator.
  Goal: keep media processing decisions separate from queue header updates, autosave hooks, project writes, and UI callbacks.
  Why: `_process_one` is 845 lines and currently interleaves business logic with UI transport concerns.

- [ ] Break `core/project/project_manager.py` into create/save/load/session modules.
  Goal: isolate project creation, save payload assembly, external asset persistence, and recovery metadata.
  Why: `save_project` is 483 lines and `create_project` is 223 lines; the file also mixes media probing, segment export, text-asset persistence, and runtime cache stripping.
  Progress: create/save/add-media now share `_build_clip_rows(...)` and a per-operation media probe cache so duplicate paths and same-operation probe reuse avoid repeated `probe_media_many/_get_media_probe` work. Remaining work is the larger create/save/load/session ownership split plus lazy hydration.

- [ ] Split the audio pipeline into durable service boundaries.
  Files: `core/audio/media_processor.py`, `core/audio/media_processor_audio.py`, `core/audio/media_processor_transcribe.py`, `core/audio/media_processor_vad.py`.
  Goal: separate extraction, chunking, transcription, VAD, cache decisions, and worker pooling.
  Why: the current audio path duplicates retry/error handling, subprocess orchestration, and resource cleanup across multiple large files.
  Progress: capture-style subprocess execution is now shared through `core/runtime/subprocess_utils.py`, and the common audio command helpers plus Codex CLI task runner already use that path for timeout/env/backoff handling. Remaining work is broader extraction/chunking/transcription service separation and typed exception cleanup.

### P0 - Exception hygiene and silent failure removal

- [ ] Replace broad `except Exception: pass` / `except: pass` patterns with typed handling plus structured logging.
  Highest-priority files:
  `ui/main/main_runtime_cleanup.py`
  `ui/main/main_window.py`
  `ui/main/main_signals.py`
  `ui/main/main_file_ops.py`
  `ui/editor/editor_pipeline.py`
  `ui/editor/video_player_widget.py`
  `core/pipeline/cut_boundary_helpers.py`
  `core/audio/media_processor.py`
  `core/audio/media_processor_audio.py`
  `ui/dialogs/export_dialog.py`
  `core/project/data_manager.py`
  Why: repository-wide scan found very large numbers of silent failure paths; many current bugs become invisible instead of diagnosable.

- [ ] Introduce a shared `log_and_swallow` helper only for truly non-fatal UI cleanup code.
  Goal: centralize cases where best-effort cleanup is acceptable while still recording what failed.
  Why: the current codebase has many ad hoc silent cleanup blocks and no consistent policy.
  Progress: `ui/editor/editor_pipeline_safety.py` now provides shared best-effort helpers (`_pipeline_best_effort`, `_pipeline_call_if_callable`, `_pipeline_stop_timer`, `_pipeline_clear_attr`, `_pipeline_set_attr`) and the editor pipeline startup/cleanup/signal-bridge services already use it to replace a chunk of silent cleanup and owner-callback handling. The same policy now has a `ui/main/main_nonfatal.py` variant and is applied to `ui/main/main_runtime_cleanup.py` wrapper helpers plus the high-traffic signal paths in `ui/main/main_signals.py` (`append_segments`, `clear_editor`, `restart_multiclip`, `refresh_cut_boundary_placeholder`). Release review also converted remaining broad-silent cleanup in `ui/editor/editor_lifecycle.py`, `ui/editor/editor_widget.py`, `ui/dialogs/export_dialog.py`, `core/audio/diarize.py`, `core/audio/media_processor.py`, `core/audio/media_processor_vad.py`, `core/path_manager.py`, and `core/project/data_manager.py` to typed/logged handling.
  Remaining targets: spread the same policy deeper into the rest of `ui/main/*`; `ui/main/main_file_ops.py` now routes dialog prep / quick-exit non-fatal cleanup through the shared helper path, and `ui/main/main_window.py` startup/home auto-source refresh/runtime manager initialization-polling plus responsive layout/sidebar terminal recovery helpers now also use it. Next high-value targets are the remaining `main_window.py` restore/restart helpers, then `ui/editor/video_player_widget.py`, `core/pipeline/cut_boundary_helpers.py`, and the audio/media/project modules called out above.

## Full Repository Review Backlog

### 1. Repository-wide complexity reduction

- [ ] Establish a hard module budget for Python source files.
  Proposed budget:
  `<= 900` lines for normal modules
  `<= 1,200` lines for service orchestrators
  `<= 120` lines for individual functions
  Why: the following files are far beyond reasonable maintenance size:
  `ui/editor/editor_segments.py`
  `core/engine/subtitle_engine.py`
  `ui/editor/video_player_widget.py`
  `ui/home_sidebar.py`
  `core/engine/subtitle_accuracy_pipeline.py`
  `ui/editor/editor_scan_cut_core.py`
  `ui/editor/editor_pipeline.py`
  `core/audio/media_processor_transcribe.py`
  `core/pipeline/cut_boundary_helpers.py`
  `core/roughcut/editor_draft.py`
  `core/cut_boundary_auto_scan.py`
  `ui/timeline/timeline_input.py`
  `ui/timeline/timeline_widget.py`
  `core/audio/media_processor_audio.py`
  `core/project/project_manager.py`
  `ui/main/main_window.py`
  `ui/timeline/timeline_paint.py`
  `ui/editor/editor_widget.py`

- [ ] Add a CI guard that fails when a new function exceeds the agreed complexity budget.
  Suggested tools: `ruff`, `radon`, or a custom AST rule.
  Why: without an automated budget, large functions keep growing during urgent bugfixes.

### 2. Duplicate helper consolidation

- [ ] Consolidate repeated numeric/string coercion helpers into shared utility modules.
  Confirmed repeated names from repository-wide scan:
  `_safe_float` appears 34 times
  `_as_float` appears 25 times
  `_safe_int` appears 20 times
  `_setting_bool` appears 19 times
  `_safe_bool` appears 13 times
  `_compact` appears 8 times
  `_json_default` appears 6 times
  Why: repeated implementations drift subtly and are expensive to audit.
  Candidate destinations:
  `core/coerce.py`
  `core/runtime/json_utils.py`
  `core/runtime/setting_utils.py`

### 3. Dead-code and wrong-wiring cleanup

- [ ] Verify low-reference functions before deleting them.
  Candidate list from repository-wide symbol scan:
  `core/audio/live_stt.py: transcribe_microphone_once`
  `core/native_swift_policy.py: trim_native_policy_worker_cache`
  `ui/main/main_signals.py: update_editor_status`
  `ui/main/main_signals.py: update_project_boundary_times`
  `core/project/data_manager.py: update_split_rule`
  `ui/editor/subtitle_text_edit.py: visible_block_numbers`
  `core/path_manager.py`: watch-folder helpers if no active UI still calls them
  Action rule: verify dynamic signal/Qt/QML wiring before removal.

- [ ] Compare and deduplicate duplicate native cut-boundary implementations.
  Files:
  `core/native/_native_cut_boundary.cpp`
  `native/cut_boundary/native_cut_boundary.cpp`
  Why: two similar native codepaths increase maintenance cost and make bug parity hard to guarantee.

- [ ] Audit all `.qml` shells for stale bindings to Python properties that no longer exist.
  Files to verify first:
  `ui/qml/sidebar_queue_panel.qml`
  `ui/qml/status_rail.qml`
  `ui/qml/timeline_playhead_overlay.qml`
  `ui/qml/project_info_overlay.qml`
  Why: several UI regressions have recently come from state existing in Python but not being wired consistently into QML.

### 4. Memory reduction ideas

- [ ] Reduce segment duplication between editor, timeline, STT preview, and save pipeline state.
  Suspected duplication points:
  `ui/editor/editor_segments.py`
  `ui/editor/editor_canvas_state.py`
  `ui/timeline/timeline_scenegraph.py`
  `ui/timeline/timeline_canvas.py`
  `core/project/project_context.py`
  Why: the same logical segment rows are copied into multiple lists/dicts for subtitle, STT1, STT2, live preview, queue flush, and save payload construction.
  Proposed direction: canonical segment store plus lightweight lane-specific views.

- [ ] Stop copying full row dictionaries in background prefetch.
  File: `core/pipeline/background_prefetch.py`
  Why: nearby segments are cloned and then used for LLM/Lora/STT prefetch decisions, which adds avoidable CPU and memory churn.
  Proposed direction: immutable row references plus a small precomputed feature bundle instead of full dict copies.
  Progress: nearby rows are now projected into lightweight prefetch payloads instead of `dict(row)` copies, and timeline playback reuses the cached segment list when scheduling prefetch.

- [ ] Add hard cache budgets and pruning to thumbnail and preview caches.
  Files:
  `core/roughcut/thumbnail_cache.py`
  `core/video_preview_proxy.py`
  runtime disk cache paths in `core/runtime/memory_manager.py`
  Why: thumbnail and preview caches grow independently and are not clearly governed by one budget.

- [ ] Make project load/save lazily hydrate large text assets.
  Files:
  `core/project/project_manager.py`
  `core/project/project_context.py`
  `core/project/project_assets.py`
  Why: STT tracks, candidate lattices, preview rows, and subtitle quality payloads do not all need to enter memory at open time.
  Proposed direction: keep file-backed metadata handles until a lane or panel is actually opened.

- [ ] Pool audio workers and tear them down on inactivity instead of per-instance retention.
  Files:
  `core/audio/media_processor.py`
  `core/audio/media_processor_transcribe.py`
  `core/audio/whisper_worker.py`
  `core/audio/worker_threads.py`
  Why: persistent workers are useful, but today their ownership is diffuse and easy to leak across editor/backend transitions.

- [ ] Replace repeated recursive cache-size scans with indexed accounting.
  File: `core/runtime/memory_manager.py`
  Why: repeated directory walks are resource-heavy and scale poorly as runtime caches grow.
  Proposed direction: maintain an incremental size ledger updated on write/delete plus occasional reconciliation scan.

- [ ] Review personalization bundle memory pressure before more learning features are added.
  Files:
  `core/personalization/idle_trainer.py`
  `core/personalization/lora_store_bundle.py`
  `core/personalization/subtitle_lora_runtime.py`
  Why: training queues, bundle manifests, retrieval indexes, and large JSON/JSONL payloads are loaded and reshaped in multiple places.
  Proposed direction: stream JSONL where possible, cap in-memory training history windows, and lazily rebuild retrieval indexes.

### 5. Resource and CPU reduction ideas

- [ ] Replace repeated full-home rebuilds with persistent widgets plus state patching.
  File: `ui/home_ui.py`
  Why: `_build_home_content` tears down and rebuilds substantial UI trees, increasing flicker, allocation churn, and signal rewiring risk.

- [ ] Stop doing heavy media probing inside project save/open hot paths.
  Files:
  `core/project/project_manager.py`
  `core/project/project_context.py`
  related media helpers in `core/media_info.py`
  Why: project I/O should mostly be serialization and validation, not repeated probing unless the media fingerprint changed.

- [ ] Replace repeated full-list sorts and per-frame recomputations in timeline/editor hot paths with visible-window caches.
  Files:
  `ui/timeline/timeline_paint.py`
  `ui/timeline/timeline_input.py`
  `ui/timeline/timeline_canvas.py`
  `ui/editor/editor_timeline_video.py`
  Why: playback and scrubbing should not rebuild or re-sort everything when only a narrow time range is visible.
  Progress: timeline canvas now exposes cached visible subtitle/STT lane partitions for paint hot paths, scenegraph subtitle sync consumes visible window rows instead of cloning the full segment list, background prefetch no longer deep-copies every segment dict before windowing, and timeline click nearest-start fallback now uses cached `starts` arrays instead of scanning the entire segment list.

- [ ] Audit icon/style generation caching.
  File: `ui/style.py`
  Why: `line_icon` is unusually large for a style helper and is a good candidate for memoization or prebuilt assets.
  Progress: `line_icon` now shares one cache insertion path, and SVG icon assets are read once then recolored from an in-memory template cache instead of re-reading the file on each color/size miss.

- [ ] Move repeated subprocess retry/backoff policies into shared helpers.
  Files:
  `core/audio/media_processor_audio.py`
  `core/audio/media_processor.py`
  `core/llm/codex_provider.py`
  Why: the same resource error handling pattern is duplicated across ffmpeg, whisper backends, and Codex CLI execution.

### 6. Python-specific optimization opportunities

- [ ] Replace large ad hoc dict payload assembly with typed lightweight models in project and editor code.
  Files:
  `core/project/project_manager.py`
  `core/project/project_context.py`
  `ui/editor/editor_segments.py`
  Why: repeated dict cloning and key juggling are expensive and error-prone.

- [ ] Convert repeated text cleanup and similarity loops to shared vectorized/native helpers where already available.
  Candidate files:
  `core/engine/subtitle_accuracy_pipeline.py`
  `core/engine/subtitle_timing.py`
  `core/engine/word_resegmenter.py`
  `core/audio/stt_candidate_scorer.py`
  Why: Python currently repeats normalization/scoring passes across many candidate rows.

- [ ] Reduce repeated JSON serialization for size estimation and cache bookkeeping.
  Files:
  `core/personalization/lora_store_bundle.py`
  `core/runtime/memory_manager.py`
  `core/runtime_eta.py`
  Why: serialization-heavy bookkeeping is convenient but costly when done often.
  Progress: `runtime_eta` now reuses a path/mtime keyed in-memory history-store cache for repeated prediction/record lookups, and runtime disk-cache usage scans are shared through a short TTL cache instead of rescanning the same directories immediately.

## App-by-App Review Results and Follow-up Actions

### Home App

- [ ] Extract a `home_presenter` layer for queue/ETA/status/view-model generation.
  Files:
  `ui/home_ui.py`
  `ui/home_sidebar.py`
  `ui/home_sidebar_presets.py`
  Why: home/dashboard state is split across widget creation, sidebar mixins, and queue formatting helpers.

- [ ] Separate source discovery from Home UI rendering.
  Files:
  `ui/home_ui.py`
  `ui/cloud_ui.py`
  `core/path_manager.py`
  Why: NAS/iCloud discovery, mount checks, and UI updates should not share the same call stack.

### Editor App

- [ ] Create an explicit editor session model that owns canonical subtitle/STT/preview lanes.
  Files:
  `ui/editor/editor_widget.py`
  `ui/editor/editor_segments.py`
  `ui/editor/editor_canvas_state.py`
  `ui/timeline/timeline_scenegraph.py`
  Why: editor state now leaks across multiple widgets and helper mixins.

- [ ] Move video subtitle overlay ownership out of `video_player_widget.py`.
  Files:
  `ui/editor/video_player_widget.py`
  `ui/editor/video_overlay_widgets.py`
  `ui/editor/video_playback_backend.py`
  Why: overlay behavior and transport control should not be entangled.
  Progress: subtitle context rows were already lightweight; the player now also reuses prebuilt normalized rows and parallel timing arrays instead of duplicating them on every provider/context refresh, and overlay geometry/text/style ownership is extracted into a dedicated overlay mixin so transport code is less entangled with overlay updates.

- [ ] Reduce editor save/reload race surfaces.
  Files:
  `ui/editor/editor_save_manager.py`
  `core/project/project_manager.py`
  `core/project/project_context.py`
  Why: save-time normalization, backup restore, and project serialization currently touch the same data in multiple places.

- [ ] Simplify subtitle assist/magnet flow and make native fallback behavior explicit.
  File: `ui/editor/editor_subtitle_assist.py`
  Why: the function count is reasonable, but control flow is still hard to audit because native and Python fallback logic are interleaved.

### Timeline App

- [ ] Split timeline responsibilities into separate adapters.
  Files:
  `ui/timeline/timeline_widget.py`
  `ui/timeline/timeline_input.py`
  `ui/timeline/timeline_canvas.py`
  `ui/timeline/timeline_canvas_editing.py`
  `ui/timeline/timeline_paint.py`
  Why: render, input, edit semantics, and scenegraph projection should be separable and benchmarkable.

- [ ] Add a single authoritative helper-line visibility policy.
  Files:
  `ui/timeline/timeline_segment_style.py`
  `ui/timeline/timeline_paint.py`
  `core/project/project_context.py`
  Why: visual helper lines, provisional boundaries, and verified helper markers have regressed repeatedly because visibility rules are scattered.

### Roughcut App

- [ ] Split roughcut draft generation from roughcut UI orchestration.
  Files:
  `core/roughcut/editor_draft.py`
  `core/roughcut/pipeline.py`
  `ui/roughcut/roughcut_widget.py`
  Why: draft logic, LLM fallback policy, boundary splitting, and UI state are currently too tightly coupled.

### Settings App

- [ ] Reduce constructor size and inline widget creation in settings screens.
  Files:
  `ui/settings/settings_personalization.py`
  `ui/settings/settings_ai.py`
  Why: these modules are building very large forms procedurally; they need schema-driven row builders or grouped presenters.

- [ ] Audit settings read/write helpers and unify setting coercion.
  Files:
  `core/settings.py`
  `core/settings_profiles.py`
  settings UI modules under `ui/settings/`
  Why: repeated `_setting_bool` and related coercion logic already drifted across many modules.

### Project / Queue / Cloud App Surfaces

- [ ] Create a project session service that owns open/save/reopen/resume flows.
  Files:
  `ui/project/project_panel.py`
  `ui/main/main_file_ops.py`
  `core/project/project_manager.py`
  `core/project/project_context.py`
  Why: project lifecycle is currently split between UI panels, main window mixins, and core serialization helpers.
  Progress:
  common session helpers now cover file/folder/recent detaches, project create/open attaches, native project-open runtime setup, linked SRT open, auto-created project save paths, multiclip runtime remaps, restart-time boundary clears, undo restores, roughcut draft auto-project creation, and editor cut-boundary prefix synchronization.
  Remaining:
  runtime session ownership is centralized; remaining work is architectural: move more save/load serialization responsibilities out of `core/project/project_manager.py` and `core/project/project_context.py` into dedicated session/serialization modules.

- [ ] Unify queue state as a real model instead of direct widget mutation.
  Files:
  `ui/queue_widget.py`
  `ui/queue/queue_panel_widget.py`
  `ui/queue/sidebar_queue_panel.py`
  backend emitters in `core/backend_fast.py`, `core/pipeline/backend_core.py`, `core/pipeline/single_pipeline.py`, `core/pipeline/multiclip_pipeline.py`
  Why: there are too many codepaths that directly set queue labels and ETA text.
  Progress:
  shared formatting is already centralized, queue rows now cache a normalized sidebar/panel payload instead of rebuilding ad hoc display fields at every consumer, backend queue/header emitters now funnel through shared helper methods instead of open-coded signal writes, `QueueMixin` can now consume structured queue/header payload dicts in addition to the legacy positional signal arguments, `MainWindow` now exposes object-payload queue signals wired into the queue update path, queue-related UI callers now prefer the payload path, `SinglePipelineMixin._ui_emit(...)` now upgrades queue/header emits onto the payload signals, the old positional queue signal definitions/connections have been removed from `MainWindow`, editor save/manual-save completion now goes through shared queue dispatch + saved-state helpers, queue row lookup plus saved-state sidebar/header policy now lives on `QueueMixin`, row-level status/expected/elapsed/progress access is increasingly pulled behind queue helper methods instead of ad hoc sidebar/backend reads, `QueueMixin` now also owns sidebar header/item view models plus queue completion/probe helpers, `ui/home_sidebar.py` no longer needs direct `queue_table` reads for queue header/item/progress/completion inference because it now falls back to queue caches/helper outputs instead, sidebar panel refresh now goes through public queue payload/refresh helpers (`queue_sidebar_panel_payload`, `sync_sidebar_queue_panel`, `refresh_queue_views`) instead of open-coded cache+panel update sequences, the sidebar panel path now has explicit assembly/apply stages (`_queue_sidebar_panel_header`, `_queue_sidebar_panel_items`, `_apply_queue_sidebar_panel_payload`, `_clear_sidebar_queue_panel_ref`) so payload creation and panel mutation/fallback cleanup are no longer interleaved, bottom queue table/header mutation has started moving behind `QueueMixin` accessors (`_queue_table_ref`, `_queue_table_item_text`, `_set_queue_table_item_text`, `_set_queue_header_text`, `_clear_queue_table_rows`, `_insert_queue_table_row`, `_populate_queue_table_row`), queue row snapshot/iteration helpers (`queue_row_snapshot`, `_queue_row_status_state`, `_queue_row_indices`, `_queue_row_items`, `_queue_row_visual_palette`) now drive more of the status/color/probe loops instead of direct per-cell traversal, queue row cache rebuild now has dedicated row-model helpers (`_queue_sidebar_item_for_row`, `_queue_sidebar_placeholder_item`, `_set_queue_row_cache_entry`) so initial queue seeding, sparse row backfill, and full cache resync no longer rebuild display payloads through repeated ad hoc list mutation, sidebar cache reads now also share copy helpers (`_queue_row_cache_items_copy`, `_sidebar_queue_cache_items_copy`, `_queue_sidebar_items_from_cache`) instead of duplicating list cloning/fallback logic across `queue_sidebar_items()` and `_refresh_sidebar_queue_cache()`, probe/view-model extraction now also goes through snapshot helpers (`_queue_probe_value_from_snapshot`, `_queue_probe_parts_from_snapshot`) so `queue_status_probe_parts()` no longer keeps separate table/cache string extraction branches, `update_queue_status()` now routes start/completion/expected-time mutation through dedicated row-operation helpers (`_queue_mark_row_started`, `_queue_record_completed_row`, `_queue_apply_expected_time_text`, `_queue_apply_row_status_text`) instead of keeping all lifecycle branches inline, the remaining completed/error/restart skip logic now also sits behind explicit policy helpers (`_queue_existing_row_update_policy`, `_queue_status_text_for_row_update`, `_queue_skip_row_update`) instead of being embedded directly in the main update loop, `update_queue_header()` now mirrors that structure by routing row-status collection, restart-reset allowance, percent clamping, and final completion marking through dedicated helpers (`_queue_row_statuses`, `_queue_header_restart_reset_allowed`, `_queue_header_effective_pct`, `_queue_finalize_header_completion`) instead of open-coded branch clusters, `_update_live_queue_header()` now reuses dedicated progress helpers (`_queue_done_reuse_counts_from_metrics`, `_queue_completion_percent`, `_queue_live_header_percent`, `_queue_apply_done_row_visuals`) instead of keeping its own inline done/reuse/pct loops, elapsed/expected ETA text generation is now centralized behind `_queue_row_elapsed_label` and `_queue_eta_text_with_elapsed` so completion updates, active-row ticking, and incoming expected-time writes all share the same clock formatting path, and row-level time/state collection now has shared `queue_row_metrics()` / `_queue_row_metrics_list()` helpers so progress snapshots and active-row ticking can consume the same expected/elapsed/status bundle instead of recomputing it independently.
  Remaining:
  finish moving the remaining producer-side direct queue widget mutations and progress ownership behind a true queue state service/model so producers stop reasoning about queue table internals, queue row lifecycle, or sidebar refresh rules; then complete the bottom queue table migration by replacing the remaining raw visual/row-cache update loops in `QueueMixin` with row-model/panel-level operations instead of direct `QTableWidget` mutation.

- [ ] Separate cloud watcher logic from widget updates.
  Files:
  `ui/cloud_ui.py`
  `core/cloud_sync.py`
  `core/path_manager.py`

### Native macOS App Core

- [ ] Split `TimelineEditing.swift` by domain before adding more native editing features.
  Proposed split:
  `TimelineEditingGeometry.swift`
  `TimelineEditingMagnet.swift`
  `TimelineEditingUndo.swift`
  `TimelineEditingSerialization.swift`
  Why: 1,815 lines is already too large for safe native expansion.

- [ ] Split `NativePolicyEngine.swift` into scoring, retrieval, and decision modules.
  Why: candidate generation, deep reranking, and runtime scoring should not live in one file.

- [ ] Split `RuntimeETAEstimator.swift` persistence from prediction logic.
  Why: model behavior and file I/O should be independently testable and reusable on iPadOS.

- [ ] Review native/Python boundary payload sizes.
  Files:
  `core/native_swift_policy.py`
  `core/native_swift_subtitle.py`
  `core/native_swift_timeline.py`
  `core/native_json.py`
  Why: large JSON payloads across the bridge can erase native performance gains.

## Functions and files that need simplification

- [ ] Break apart the following oversized functions first:
  `core/cut_boundary_auto_scan.py: build_auto_grid_scan_helpers`
  `ui/timeline/timeline_paint.py: paintEvent`
  `core/cut_boundary_auto_verify.py: build_strict_verify_helpers`
  `core/cut_boundary_auto_scan.py: scan_media_cut_boundary_provisionals`
  `core/pipeline/cut_boundary_helpers.py: _auto_scan_cut_boundaries_for_start_sync`
  `core/pipeline/single_pipeline.py: _process_one`
  `core/audio/media_processor_transcribe.py: transcribe`
  `core/pipeline/topicless_segments.py: install_topicless_segment_helpers`
  `core/project/project_manager.py: save_project`
  `core/audio/media_processor.py: extract_audio`
  `core/cut_boundary_auto_verify.py: _auto_grid_v3_manual_verify_impl`
  `core/pipeline/multiclip_pipeline.py: _run_multiclip_stt_llm_pipeline`
  `ui/editor/editor_segments_stt_selection_flow.py: select_stt_candidate_as_subtitle`
  `ui/editor/editor_segments_queue_flush.py: _flush_queue`
  `ui/editor/editor_pipeline.py: _run_partial_backend`
  `ui/editor/editor_timeline_video.py: _on_seg_time_changed`
  `ui/timeline/timeline_canvas_editing.py: apply_timing_drag`

- [ ] Replace helper-installer patterns with normal modules and explicit objects.
  Files:
  `core/cut_boundary_auto_verify.py`
  `core/cut_boundary_fps.py`
  `core/pipeline/topicless_segments.py`
  Why: giant functions that define many nested helpers are difficult to type-check, test, and reuse.

## Swift / C++ migration candidates

- [ ] Consider moving cut-boundary scoring and alignment loops into native code after Python-side refactor.
  Candidate Python files:
  `core/pipeline/cut_boundary_helpers.py`
  `core/cut_boundary_auto_scan.py`
  `core/cut_boundary_auto_verify.py`
  Why: these modules are numerically heavy and already have native adjacency.
  Important: do not port before the Python logic is split into stable interfaces.

- [ ] Consider moving subtitle candidate scoring and sequence smoothing into Swift/C++.
  Candidate Python files:
  `core/audio/stt_candidate_scorer.py`
  `core/audio/stt_lattice.py`
  `core/engine/subtitle_accuracy_pipeline.py`
  `core/engine/subtitle_timing.py`
  `core/engine/word_resegmenter.py`
  Why: these are algorithm-heavy loops with repetitive normalization and overlap scoring.

- [ ] Consider moving personalization retrieval/scoring hot paths into native code only after bundle format is stabilized.
  Candidate Python files:
  `core/personalization/lora_vector_retriever.py`
  `core/personalization/subtitle_lora_runtime.py`
  `core/personalization/deep_subtitle_policy.py`
  Why: current bundle/index formats are still evolving, so a direct native port now would freeze unstable boundaries too early.

## Static-analysis and tooling follow-up

- [ ] Add a `vulture` or equivalent dead-code scan to CI and keep a suppression allowlist if needed.
  Why: even high-confidence unused imports already remain in shipping files.

- [ ] Add a repository-wide "broad exception" lint rule.
  Why: current silent failure density is too high for a UI-heavy app with many background workers.

- [ ] Add a "max function length" and "max file length" gate for source under `core/`, `ui/`, and `native/`.

## Parked Work

- [ ] Actual App Store Connect upload remains blocked on the user's Apple Developer account, signing identities, App Store Connect API key or app-specific password, and team configuration.

- [ ] Future iPadOS reuse remains a design requirement.
  Rule: keep Swift-native subtitle, LoRA, deep policy, project I/O, timeline, and waveform logic reusable as Apple-platform core modules, with macOS-only UI, process, file-watcher, and packaging code kept at the edges.

- [ ] If VAD mode locking remains a product direction, automate the benchmark-refresh path that mines dense dialogue windows from `test video/` and re-scores the locked Fast/Auto/High VAD profiles before future releases.
