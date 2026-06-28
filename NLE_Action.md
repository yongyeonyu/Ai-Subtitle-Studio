# NLE_Action.md - Mutable NLE, Cut Boundary, Preview, Trace Execution Plan

<!--
Document-Version: 04.01.00-nle-action
Phase: NLE_MUTABLE_OWNER_AND_CUT_ACCURACY
Last-Updated: 2026-06-28
Owner: Dex / Codex
Purpose: Executable source of truth for the next NLE write-path, cut-boundary, preview, and trace-log slices.
-->

## Summary

This file is the execution source of truth for four connected workstreams:

1. Promote the current source-app internal NLE baseline from read-only projection toward a mutable editor/save owner.
2. Improve visual cut-boundary accuracy with source-fps frame scouting and local verification.
3. Add Final Cut Pro-style fast preview/skimming via a low-resolution preview cache while preserving the existing Qt Widgets UI surface.
4. Add temporary trace-log bundles under a system temp workspace for accuracy, performance, and UI/UX debugging.

Current NLE status:

- Completed workstream history is archived in `COMPLETED_ACTION_ITEMS.md#nle-action-completed-workstream-baseline` and the related completed NLE sections in that file; this plan keeps only open status and future gates.
- Open status: persisted NLE project fields are not approved, and per-pixel drag writes to NLE state remain explicitly out of scope. Additional runtime mutation sources require a fresh owner-map and focused audit before adoption.
- Latest owner-map audit: `output/manual_verification/latest/nle_drag_commit_boundary_guard_20260628/nle_runtime_owner_map_audit.md`; current release/commit NLE runtime mutation owners are covered `24/24` across `12` operation families, including output-domain `roughcut_range_edit`, and commit-boundary guards are covered `1/1` for `timeline_center_drag_preview_only_until_release`; runtime behavior changed `false`, and blocked candidates remain persisted NLE disk fields, per-pixel NLE writes, and QML/GPU timeline default surface changes.
- Latest adapter/cache consistency audit: `output/manual_verification/latest/nle_adapter_consistency_audit_20260628/nle_adapter_consistency_audit.md`; repeated save/reopen cycles pass `6/6`, runtime-only `_nle_project_state` markers do not persist after cache clear/reopen, storage stays clean, final invalid/non-monotonic/overlap stays `0/0/0`, global max-active stays `1`, and the project file LRU cache respects its `4` entry limit.
- Latest operation journal/undo contract audit: `output/manual_verification/latest/nle_roughcut_range_edit_operation_journal_20260628/nle_operation_journal_audit.md`; all `12` current NLE operation families carry release commit metadata and undo snapshot metadata, `roughcut_range_edit` remains output-time only, storage stays clean of operation/undo/runtime NLE schemas, final invalid/non-monotonic/overlap stays `0/0/0`, global max-active stays `1`, and runtime behavior changed `false`.
- Latest NAS HeyDealer first-180s source-app regression after the operation-journal slice: `output/manual_verification/latest/nle_operation_journal_nas_heydealer_20260628/acceptance/reference_benchmark_acceptance.md`; accepted `true`, raw/final/reference `58/56/89`, quality/text/timing `93.766/94.267/0.5808s`, final invalid/non-monotonic/overlap `0/0/0`, and global max-active `1`.
- Latest runtime in-memory operation journal audit: `output/manual_verification/latest/nle_roughcut_range_edit_operation_journal_20260628/nle_operation_journal_audit.md`; all `12` current NLE operation families now append bounded runtime-only journal entries to `NLEProjectState` while keeping legacy storage clean of operation/undo/journal/runtime NLE schemas. NAS HeyDealer first-180s regression after this slice is accepted at `output/manual_verification/latest/nle_roughcut_range_edit_nas_heydealer_20260628/acceptance/reference_benchmark_acceptance.md` with final invalid/non-monotonic/overlap `0/0/0` and global max-active `1`.
- Latest preview/skimming cache contract audit: `output/manual_verification/latest/nle_preview_skimming_cache_audit_20260628/nle_preview_skimming_cache_audit.md`; preview cache files remain under the temp `Preview/FrameThumbnails` workspace, carry `user_preview_only` manifest provenance, are explicitly not cut-boundary evidence, and cache miss continues to schedule async preparation instead of sync UI-thread decode.
- Latest preview/skimming trace-event audit: `output/manual_verification/latest/nle_preview_skimming_trace_audit_20260628/nle_preview_skimming_cache_audit.md`; preview cache hit/miss/schedule/ready events now flow through the async `TraceLogger` queue with `editor_preview_skimming`, `user_preview_only`, `cut_boundary_evidence=false`, exact `fps_num/fps_den`, and the existing preview seek throttle preserved.
- Latest preview/skimming cache-miss block-free audit: `output/manual_verification/latest/nle_preview_skimming_cache_miss_block_free_20260628/nle_preview_skimming_cache_audit.md`; slow cache-miss frame preparation is guarded to stay on the named `video-preview-frame-cache` worker and `VideoPlayerWidget.preview_seek()` must return before worker decode completes. NAS HeyDealer first-180s regression after this guard is accepted at `output/manual_verification/latest/nle_preview_skimming_cache_miss_nas_heydealer_20260628/acceptance/reference_benchmark_acceptance.md`; elapsed `45.744s`, raw/final/reference `58/56/89`, quality/text/timing `93.766/94.267/0.5808s`, final invalid/non-monotonic/overlap `0/0/0`, global max-active `1`, and timeout audit `output/manual_verification/latest/stt_worker_timeout_compare_nle_preview_cache_miss_nas_20260628/stt_worker_timeout_audit.md` reports timeout detected `false`.
- Latest viewport zoom decoupling audit: `output/manual_verification/latest/nle_viewport_zoom_decoupling_20260628/nle_viewport_zoom_decoupling.md`; timeline Ctrl-wheel zoom and global-canvas wheel scroll are proven viewport-only, with no primary subtitle row rewrite, no runtime NLE operation journal append, no project save, and no UI/layout behavior change. NAS HeyDealer generation validation is not required for this view-only contract.
- Latest playhead-jump isolation audit: `output/manual_verification/latest/nle_playhead_jump_isolation_20260628/nle_playhead_jump_isolation.md`; global minimap click, timeline global seek, and editor scrub are proven view/playhead-only immediate paths, with no primary subtitle validation/rescan, no primary row rewrite, no runtime NLE operation journal append, no project save, and no UI/layout behavior change. NAS HeyDealer generation validation is not required for this view-only contract.
- Latest time-window/fit-to-view decoupling audit: `output/manual_verification/latest/nle_time_window_view_decoupling_20260628/nle_time_window_view_decoupling.md`; fit-to-view, scheduled fit, explicit time-window, and saved-preference edit-window controls are proven viewport-only, with no primary subtitle validation/rescan, no primary row rewrite, no runtime NLE operation journal append, no project save, and no UI/layout behavior change. NAS HeyDealer generation validation is not required for this view-only contract.
- Latest selection/view-state isolation audit: `output/manual_verification/latest/nle_selection_view_state_isolation_20260628/nle_selection_view_state_isolation.md`; text selection, canvas active segment highlight, and timeline `set_active` are proven view-state-only, with no primary row rewrite, no runtime NLE operation journal append, no project save, no subtitle validation/finalize path, and no UI/layout behavior change. NAS HeyDealer first-180s current-head regression after this slice is accepted at `output/manual_verification/latest/nle_selection_view_state_nas_heydealer_20260628/acceptance/reference_benchmark_acceptance.md`; elapsed `45.999s`, raw/final/reference `58/56/89`, quality/text/timing `93.766/94.267/0.5808s`, final invalid/non-monotonic/overlap `0/0/0`, global max-active `1`, and timeout audit `output/manual_verification/latest/stt_worker_timeout_compare_nle_selection_view_state_nas_20260628/stt_worker_timeout_audit.md` reports timeout detected `false`.
- Latest undo/redo runtime-state restore audit: `output/manual_verification/latest/nle_undo_redo_runtime_state_20260628/nle_undo_redo_runtime_state.md`; undo/redo snapshot restore now syncs restored editor `cached_segments` into session-only `NLEProjectState` with `last_editor_sync_source=undo_redo_restore`, excludes live STT preview rows from that runtime state, avoids operation-journal appends, and keeps persisted storage clean of `_nle_project_state`, `nle`, and `nle_snapshot`. NAS HeyDealer first-180s regression after this slice is accepted at `output/manual_verification/latest/nle_undo_redo_runtime_state_nas_heydealer_20260628/acceptance/reference_benchmark_acceptance.md`; elapsed `45.497s`, raw/final/reference `58/56/89`, quality/text/timing `93.766/94.267/0.5808s`, final invalid/non-monotonic/overlap `0/0/0`, global max-active `1`, and timeout audit `output/manual_verification/latest/stt_worker_timeout_compare_nle_undo_redo_runtime_state_nas_20260628/stt_worker_timeout_audit.md` reports timeout detected `false`. This changes no UI layout, subtitle quality policy, STT/default-cache policy, persisted NLE disk fields, App Store behavior, runtime undo/redo UI, or per-pixel NLE writes.
- Latest roughcut sidecar compatibility audit: `output/manual_verification/latest/nle_roughcut_sidecar_compat_20260628/nle_roughcut_sidecar_compat.md`; roughcut `_render_plan.json` and `_edl.json` restore is proven against NLE render/export parity for roughcut sidecar and exported-assets surfaces, sidecar/storage forbidden key counts stay `0/0`, final invalid/non-monotonic/overlap stays `0/0/0`, and global max-active stays `1`. NAS HeyDealer first-180s regression after this slice is accepted at `output/manual_verification/latest/nle_roughcut_sidecar_compat_nas_heydealer_20260628/acceptance/reference_benchmark_acceptance.md`; elapsed `45.103s`, raw/final/reference `58/56/89`, quality/text/timing `93.766/94.267/0.5808s`, final invalid/non-monotonic/overlap `0/0/0`, global max-active `1`, and timeout audit `output/manual_verification/latest/stt_worker_timeout_compare_nle_roughcut_sidecar_compat_nas_20260628/stt_worker_timeout_audit.md` reports timeout detected `false`. This changes no UI layout, subtitle quality policy, STT/default-cache policy, persisted NLE disk fields, App Store behavior, runtime undo/redo UI, roughcut sidecar schema, or per-pixel NLE writes.
- Latest selection sync validation audit: `output/manual_verification/latest/nle_selection_sync_validation_20260628/nle_selection_sync_validation.md`; active selection parity now has a focused validation helper for reload/restore flows. The audit proves shared-boundary active time uses exact segment-start priority, editor and runtime NLE active signatures match the same caption, operation journal count stays `0`, storage forbidden key count stays `0`, and UI/layout behavior is unchanged. NAS HeyDealer first-180s regression after this slice is accepted at `output/manual_verification/latest/nle_selection_sync_validation_nas_heydealer_20260628/acceptance/reference_benchmark_acceptance.md`; elapsed `46.06s`, raw/final/reference `58/56/89`, quality/text/timing `93.766/94.267/0.5808s`, final invalid/non-monotonic/overlap `0/0/0`, global max-active `1`, and timeout audit `output/manual_verification/latest/stt_worker_timeout_compare_nle_selection_sync_validation_nas_20260628/stt_worker_timeout_audit.md` reports timeout detected `false`. This changes no UI layout, subtitle quality policy, STT/default-cache policy, persisted NLE disk fields, App Store behavior, runtime undo/redo UI, or per-pixel NLE writes.
- Latest relink parity verification audit: `output/manual_verification/latest/nle_relink_parity_20260628/nle_relink_parity.md`; project-load/media relink parity now has a focused validation helper proving editor media files, NLE snapshot clips/assets, runtime fps, and sequence duration agree after relink, while editor/timeline path drift is rejected before it can masquerade as a valid NLE projection. NAS HeyDealer first-180s regression after this slice is accepted at `output/manual_verification/latest/nle_relink_parity_nas_heydealer_20260628/acceptance/reference_benchmark_acceptance.md`; elapsed `48.693s`, raw/final/reference `58/56/89`, quality/text/timing `93.766/94.267/0.5808s`, final invalid/non-monotonic/overlap `0/0/0`, global max-active `1`, and timeout audit `output/manual_verification/latest/stt_worker_timeout_compare_nle_relink_parity_nas_20260628/stt_worker_timeout_audit.md` reports timeout detected `false`. This changes no UI layout, subtitle quality policy, STT/default-cache policy, persisted NLE disk fields, project-storage relink schema, App Store behavior, automatic relink dialogs, runtime undo/redo UI, or per-pixel NLE writes.
- Latest final/preview isolation audit: `output/manual_verification/latest/nle_final_preview_isolation_20260628/nle_final_preview_isolation.md`; live editor feed now separates confirmed `final_surface_segments` from `preview_lane_segments`, marks `combined_segments` as diagnostic candidate-lane only, and the video subtitle overlay ignores live STT/subtitle draft rows. NAS HeyDealer first-180s regression after this slice is accepted at `output/manual_verification/latest/nle_final_preview_isolation_nas_heydealer_20260628/acceptance/reference_benchmark_acceptance.md`; elapsed `46.228s`, raw/final/reference `58/56/89`, quality/text/timing `93.766/94.267/0.5808s`, final invalid/non-monotonic/overlap `0/0/0`, global max-active `1`, and timeout audit `output/manual_verification/latest/stt_worker_timeout_compare_nle_final_preview_isolation_nas_20260628/stt_worker_timeout_audit.md` reports timeout detected `false`. This changes no UI layout, subtitle quality policy, STT/default-cache policy, persisted NLE disk fields, App Store behavior, runtime undo/redo UI, or per-pixel NLE writes.
- Latest Taption voice-silence magnet parity slice: `ui/editor/ux/timeline_subtitle_segment_editing.py` now restores source metadata for native `gap`/`vad`/`voice_activity` snap candidates, recognizes silence-like `voice_activity`/`vad` rows as gap rows for center body drag suppression, and suppresses only those gap-like snap candidates while preserving real subtitle boundary snaps beyond the silence row. Focused tests passed for native-candidate voice-silence cases plus existing gap/magnet/drag/boundary regressions. NAS HeyDealer first-180s regression after this slice is accepted at `output/manual_verification/latest/nle_voice_silence_magnet_nas_heydealer_20260628/acceptance/reference_benchmark_acceptance.md`; elapsed `348.171s`, raw/final/reference `55/57/89`, quality/text/timing `93.955/94.867/0.5536s`, final invalid/non-monotonic/overlap `0/0/0`, global max-active `1`, and timeout audit `output/manual_verification/latest/stt_worker_timeout_compare_nle_voice_silence_magnet_nas_20260628/stt_worker_timeout_audit.md` reports timeout detected `true`. The timeout evidence is diagnostic only; no STT/default-cache policy, UI layout, persisted NLE disk fields, App Store behavior, runtime undo/redo UI, or per-pixel NLE writes changed.
- Latest NLE neighbor-collision guard audit: `output/manual_verification/latest/nle_neighbor_collision_guard_20260628/nle_neighbor_collision_guard.md`; caption move overlap, center commit-row overlap, and split-required resize collisions are proven to reject before mutating project rows or creating runtime NLE state, while partial resize neighbor overlap trims to a shared boundary with final overlap `0`. NAS HeyDealer first-180s regression after this slice is accepted at `output/manual_verification/latest/nle_neighbor_collision_nas_heydealer_20260628/acceptance/reference_benchmark_acceptance.md`; elapsed `94.953s`, raw/final/reference `58/56/89`, quality/text/timing `93.766/94.267/0.5808s`, final invalid/non-monotonic/overlap `0/0/0`, global max-active `1`, and timeout audit `output/manual_verification/latest/stt_worker_timeout_compare_nle_neighbor_collision_nas_20260628/stt_worker_timeout_audit.md` reports timeout detected `false`. This changes no UI layout, subtitle quality policy, STT/default-cache policy, persisted NLE disk fields, App Store behavior, runtime undo/redo UI, or per-pixel NLE writes.
- Latest inline edit entry contract audit: `output/manual_verification/latest/nle_inline_edit_entry_contract_20260628/nle_inline_edit_entry_contract.md`; Taption-style double-click/inline-edit entry is now traced as `timeline_inline_edit_entry` with no caption text payload, no NLE operation journal append, no project save, and no primary subtitle validation/rescan until the actual text commit. The existing text commit path remains the `caption_text_edit` release commit. NAS HeyDealer first-180s regression after this slice is accepted at `output/manual_verification/latest/nle_inline_edit_entry_nas_heydealer_20260628/acceptance/reference_benchmark_acceptance.md`; elapsed `46.481s`, raw/final/reference `58/56/89`, quality/text/timing `93.766/94.267/0.5808s`, final invalid/non-monotonic/overlap `0/0/0`, final last end/duration bound `180.0/180.0`, global max-active `1`, and timeout audit `output/manual_verification/latest/stt_worker_timeout_compare_nle_inline_entry_nas_20260628/stt_worker_timeout_audit.md` reports timeout detected `false`.
- Latest NLE dual-write duration-bound trim audit: `output/manual_verification/latest/nle_dual_write_duration_bound_20260628/nle_dual_write_duration_bound.md`; release-commit row-producing dual-write families now pass through the shared project duration trim before runtime NLE sync and raw `editor_state` rebuild. Owner coverage is `11/11`; dynamic checks prove tail clamp and beyond-duration row drop on legacy rows, runtime NLE rows, and raw vector storage with final invalid/non-monotonic/overlap `0/0/0` and global max-active `1`. NAS HeyDealer first-180s regression after this slice is accepted at `output/manual_verification/latest/nle_dual_write_duration_bound_nas_heydealer_20260628/acceptance/reference_benchmark_acceptance.md`; elapsed `45.946s`, raw/final/reference `58/56/89`, quality/text/timing `93.766/94.267/0.5808s`, final last end/duration bound `180.0/180.0`, global max-active `1`, and timeout audit `output/manual_verification/latest/stt_worker_timeout_compare_nle_duration_bound_nas_20260628/stt_worker_timeout_audit.md` reports timeout detected `false`. This does not approve persisted NLE disk fields, per-pixel NLE writes, UI/QML changes, STT/default-cache changes, or App Store packaging.
- Latest NLE gap-delete sequence policy audit: `output/manual_verification/latest/nle_gap_delete_sequence_policy_20260628/nle_gap_delete_sequence_policy.md`; explicit gap deletion now records `remove_gap_row_no_ripple` on the gap-delete operation, undo snapshot, and runtime NLE state, and dynamic checks prove legacy rows, runtime NLE rows, and raw vector storage preserve adjacent caption timing while only removing the gap row. NAS HeyDealer first-180s regression after this slice is accepted at `output/manual_verification/latest/nle_gap_delete_sequence_policy_nas_heydealer_20260628/acceptance/reference_benchmark_acceptance.md`; elapsed `47.979s`, raw/final/reference `58/56/89`, quality/text/timing `93.766/94.267/0.5808s`, final invalid/non-monotonic/overlap `0/0/0`, final last end/duration bound `180.0/180.0`, global max-active `1`, and timeout audit `output/manual_verification/latest/stt_worker_timeout_compare_nle_gap_delete_policy_nas_20260628/stt_worker_timeout_audit.md` reports timeout detected `false`. This explicitly rejects silent gap-delete ripple behavior unless the owner approves a separate ripple/absorb operation.
- Latest NLE projection metadata preservation audit: `output/manual_verification/latest/nle_projection_metadata_preservation_20260628/nle_projection_metadata_preservation.md`; runtime dual-write projection row construction now deep-copies retimed/manual/sorted/shadow/serialized rows so existing product metadata survives move, merge, and split projections without shared nested references. Dynamic checks prove caption move preserves quality/STT candidate metadata, caption merge preserves kept-row metadata, and caption split preserves child speaker/words metadata while keeping existing manual-quality removal policy. NAS HeyDealer first-180s regression after this slice is accepted at `output/manual_verification/latest/nle_projection_metadata_preservation_nas_heydealer_20260628/acceptance/reference_benchmark_acceptance.md`; elapsed `45.188s`, raw/final/reference `58/56/89`, quality/text/timing `93.766/94.267/0.5808s`, final invalid/non-monotonic/overlap `0/0/0`, final last end/duration bound `180.0/180.0`, global max-active `1`, and timeout audit `output/manual_verification/latest/stt_worker_timeout_compare_nle_projection_metadata_nas_20260628/stt_worker_timeout_audit.md` reports timeout detected `false`. This does not approve arbitrary legacy custom schema expansion, persisted NLE disk fields, per-pixel NLE writes, UI/QML changes, STT/default-cache changes, or App Store packaging.
- Latest NLE cut marker point-evidence projection audit: `output/manual_verification/latest/nle_cut_marker_point_projection_20260628/nle_cut_marker_point_projection.md`; marker edit dual-write now sanitizes confirmed/provisional cut markers into point evidence, removes clip-span mapping keys, keeps clip boundaries unchanged, and records `point_evidence_no_clip_span` on operation/undo/runtime metadata. NAS HeyDealer first-180s regression after this slice is accepted at `output/manual_verification/latest/nle_cut_marker_point_projection_nas_heydealer_20260628/acceptance/reference_benchmark_acceptance.md`; elapsed `45.036s`, raw/final/reference `58/56/89`, quality/text/timing `93.766/94.267/0.5808s`, final invalid/non-monotonic/overlap `0/0/0`, final last end/duration bound `180.0/180.0`, global max-active `1`, and timeout audit `output/manual_verification/latest/stt_worker_timeout_compare_nle_cut_marker_point_projection_nas_20260628/stt_worker_timeout_audit.md` reports timeout detected `false`. This does not approve detector threshold changes, persisted NLE disk fields, per-pixel NLE writes, UI/QML changes, STT/default-cache changes, or App Store packaging.
- Latest NLE relink/proxy preview-cache contract audit: `output/manual_verification/latest/nle_relink_preview_cache_contract_20260628/nle_relink_preview_cache_contract.md`; preview frame manifests now carry path-independent media identity, direct-path cache lookup remains first, bounded relink scan reuses an existing preview thumbnail only for same media identity plus same fps/frame/width and preview-only provenance, and proxy/transcoded files with different identity are blocked from reuse. NAS HeyDealer first-180s regression after this slice is accepted at `output/manual_verification/latest/nle_relink_preview_cache_nas_heydealer_20260628/acceptance/reference_benchmark_acceptance.md`; elapsed `45.515s`, raw/final/reference `58/56/89`, quality/text/timing `93.766/94.267/0.5808s`, final invalid/non-monotonic/overlap `0/0/0`, final last end/duration bound `180.0/180.0`, global max-active `1`, and timeout audit `output/manual_verification/latest/stt_worker_timeout_compare_nle_relink_preview_cache_nas_20260628/stt_worker_timeout_audit.md` reports timeout detected `false`. This does not approve project-storage relink schemas, proxy dynamic mapping without source identity, persisted NLE disk fields, per-pixel NLE writes, UI/QML changes, STT/default-cache changes, or App Store packaging.
- Latest Trace Log Bundle package-retention audit: `output/manual_verification/latest/trace_package_retention_contract_20260628/trace_log_bundle_audit.md`; package collection now enforces bounded `Diagnostics/Packages/AISSTrace-*` retention in addition to trace-run retention, keeps the current package, records retention in `package_manifest.json`, and proves retained package count `10/10` with removed count `4`. This closes the trace temp-workspace disk-growth gap without changing UI, subtitle generation, STT/default-cache policy, persisted NLE fields, App Store packaging, or per-pixel writes.
- Latest confirmed cut-boundary decision trace audit: `output/manual_verification/latest/nle_confirmed_cut_trace_audit_20260628/trace_log_bundle_audit.md`; confirmed visual-cut split/snap/drop decisions now emit async `confirmed_cut_split_snap` events with `event_type=cut_boundary_decision`, `decision`, `provisional_frame`, `drop_reason`, exact `fps_num/fps_den`, and no detector-threshold, UI, or persisted-NLE behavior change. NAS HeyDealer first-180s regression after this slice is accepted at `output/manual_verification/latest/nle_confirmed_cut_trace_nas_heydealer_20260628/acceptance/reference_benchmark_acceptance.md`.
- Latest project IO save/load trace contract audit: `output/manual_verification/latest/project_io_trace_contract_20260628/project_io_trace_contract.md`; project save/open/cache-hit paths now emit async best-effort `project_file_save` / `project_file_open` trace events with raw paths excluded, basename plus path hash only, NLE runtime-state hydration evidence, storage clean evidence, payload codec/compression fields, and no UI/layout, persisted NLE disk-format, or App Store behavior change.
- Latest NLE operation journal trace-event audit: `output/manual_verification/latest/nle_operation_journal_trace_audit_20260628/nle_operation_journal_audit.md`; runtime-only operation journal appends now emit async best-effort `nle_operation_journal_append` trace events for all `12` operation families, contract ok `true`, storage clean `12`, final invalid/non-monotonic/overlap `0/0/0`, global max-active `1`, and no caption text, raw project path, or raw `target_ids` in the trace payload.
- Latest NAS HeyDealer first-180s regression after the operation-journal trace slice: `output/manual_verification/latest/nle_operation_journal_trace_nas_heydealer_20260628/acceptance/reference_benchmark_acceptance.md`; accepted `true`, elapsed `52.699s`, raw/final/reference `58/56/89`, quality/text/timing `93.766/94.267/0.5808s`, final invalid/non-monotonic/overlap `0/0/0`, global max-active `1`, and timeout audit `output/manual_verification/latest/stt_worker_timeout_compare_nle_operation_trace_nas_20260628/stt_worker_timeout_audit.md` reports timeout detected `false`.
- Latest NLE drag commit-boundary guard audit: `output/manual_verification/latest/nle_drag_commit_boundary_guard_20260628/nle_runtime_owner_map_audit.md`; center body drag is now explicitly covered as Taption-style preview-only until release commit, with NLE move calls `0` during mouse move and `1` on release, and direction-aware diamond shared-boundary release ordering keeps left/right diamond drags gap-free. NAS HeyDealer first-180s regression after this guard is accepted at `output/manual_verification/latest/nle_drag_commit_boundary_guard_nas_heydealer_20260628/acceptance/reference_benchmark_acceptance.md`; elapsed `53.919s`, raw/final/reference `58/56/89`, quality/text/timing `93.766/94.267/0.5808s`, final invalid/non-monotonic/overlap `0/0/0`, global max-active `1`, and timeout audit `output/manual_verification/latest/stt_worker_timeout_compare_nle_drag_commit_guard_nas_20260628/stt_worker_timeout_audit.md` reports timeout detected `false`.
- Latest cut-boundary fixture target correction audit: `output/manual_verification/latest/nle_cut_boundary_fixture_target_correction_20260628/cut_boundary_fixture_target_correction.md`; the fixed fixture QA target is corrected from historical `2677` to `2676`, with current target frames `2766,2676` and source-fps pairs `2765:2766,2675:2676`. Runtime detector thresholds, subtitle policy, STT policy, UI, App Store work, and persisted NLE disk fields remain unchanged.
- Latest corrected source-fps scout: `output/manual_verification/latest/nle_corrected_target_source_fps_scout_20260628/source_fps_scout.md`; decoder extraction succeeds, frame `2676` is visually detected with score `71.932`, and frame `2766` remains `preserved_only` with score `2.059`, so `strict_visual_detection_passed=false` still blocks visual-detection claims for the full pair.
- Latest corrected visual window / frame-semantics / convention audits: `output/manual_verification/latest/nle_corrected_target_visual_window_audit_20260628/cut_boundary_visual_window_audit.md`, `output/manual_verification/latest/nle_corrected_target_frame_semantics_audit_20260628/cut_boundary_frame_semantics_audit.md`, and `output/manual_verification/latest/nle_corrected_target_fixture_convention_audit_20260628/cut_boundary_fixture_convention_audit.md`; the corrected `2676` target is target-best and convention-clean, semantic mismatch count is now `0`, and frame `2766` remains not visually detected while frame-preserved.
- Latest `2766` detector-evidence robustness audit: `output/manual_verification/latest/nle_cut_boundary_2766_detector_robustness_20260628/cut_boundary_detector_evidence_robustness.md`; modes `fast4,cross5,full9` across widths `320,480,960,1920` classify frame `2766` as `weak_visual_change_not_threshold_candidate` with best score `3.812`, best hits `0`, best pixel `0.034849`, and best motion `1.315`, while frame `2676` remains visually detected. Detector threshold tuning candidate count is `0`; preserve `2766` as frame-grid/marker evidence or revisit fixture truth instead of lowering visual thresholds from this fixture.
- Latest preserved-marker policy audit: `output/manual_verification/latest/nle_preserved_marker_policy_20260628/cut_boundary_preserved_marker_policy.md`; the combined source-fps plus robustness evidence now classifies frame `2676` as `visual_marker_confirmed` and frame `2766` as `preserved_marker_required`, with review required count `0`. Confirmed cuts remain point markers rather than clip spans, preserved marker evidence may force split/snap but must not lower visual detector thresholds, and per-pixel NLE writes remain blocked.
- Current NAS fixture preflight after the target-correction slice is ready at `output/manual_verification/latest/nle_target_correction_nas_preflight_20260628/reference_fixture_availability.md`; media and reference SRT exist and clipped reference rows are `89`. Runtime generation behavior was not changed, so no new subtitle-generation benchmark was run for this QA-target correction.

This plan does not approve native migration, Swift rewrite, QML migration, OpenGL/Metal UI-surface defaults, DMG work, release tag movement, App Store/TestFlight work, or UI/UX label/layout/color/shortcut/popup changes.

## Fixed Fixture

Primary cut-boundary fixture:

- Path: `/Users/u_mo_c/Library/Mobile Documents/com~apple~CloudDocs/AI_EDIT/내 프로젝트 (3).MP4`
- Video: `3840x2160`
- FPS: `60000/1001` (`59.94fps`)
- Duration: `465.849s`
- Frames: `27923`

Target cut-boundary frames:

- `2765 -> 2766` (`frame 2766`, approx `46.1461s`)
- `2675 -> 2676` (`frame 2676`, approx `44.6446s`)

Historical correction note:

- The old `2676 -> 2677` / `frame 2677` fixture target is superseded. Contact-sheet evidence shows the hard visual transition is `2675 -> 2676`; frame `2677` is one frame late for this fixed fixture's QA target.

Boundary semantics:

- A cut boundary is the transition from the previous frame into the boundary frame.
- A subtitle that starts one frame before a confirmed boundary must snap to the boundary frame when that avoids crossing a visual hard cut.
- A subtitle crossing a confirmed visual hard cut must split or edge-snap at the exact boundary frame.
- Frame/time conversion for this fixture must use the exact rational fps `60000/1001`; do not round to `60fps` for boundary assertions.

## Current Dirty Boundary

Before widening any slice, run:

```bash
git status --short --branch
```

As of this action file creation, the worktree already contains unrelated or earlier in-flight edits in VAD/STT timing, cut-boundary, docs, and tests. Do not revert user or earlier Dex work. Keep each new slice reviewable and report whether a diff belongs to:

- pre-existing timing/VAD work,
- pre-existing cut-boundary work,
- this `NLE_Action.md` lane,
- or a new implementation slice.

## Target Architecture

### Mutable NLE Owner

Goal: make NLE state the editor/save timing source of truth while preserving legacy compatibility.

Required behavior:

- Legacy project load hydrates a mutable `NLEProjectState`.
- `NLEProjectState` starts as an in-memory editor/session owner; do not persist `nle` or `nle_snapshot` fields into `.aissproj` during the pilot slices.
- Editor/timeline/save actions update NLE state first.
- Main timeline canvas read rows pass through the NLE `timeline_canvas` projection before paint/hit-test state is built.
- Timeline drag/release mutable sync must happen only at commit boundaries; do not write NLE state on every drag pixel.
- Save/reopen projects keep existing `.aissproj` legacy fields intact.
- Legacy payload projection is generated from NLE state.
- Existing direct SRT open, roughcut sidecar restore, and rendered roughcut reopen compatibility remain intact.
- Missing media, relink, proxy, and cache metadata remain non-destructive.

Stop conditions:

- duplicate mutable timing state appears,
- subtitle count drifts unexpectedly,
- first/last subtitle time drifts unexpectedly,
- output duration drifts,
- sidecar metadata changes without explicit compatibility proof,
- direct SRT reopen or legacy `.aissproj` reopen breaks,
- NLE-to-legacy projection drops frame-quantized fields or custom metadata required for reopen.
- direct SRT timing/text precedence is overwritten by linked project or NLE-derived metadata.

Latest direct SRT precedence proof:

- `output/manual_verification/latest/direct_srt_precedence_contract_20260628/direct_srt_precedence_contract.md`; linked-project direct SRT open now syncs runtime `NLEProjectState` from the direct SRT editor rows, records `last_editor_sync_source=direct_srt_open` and `direct_srt_precedence_contract=srt_timing_text_wins`, preserves project metadata only as auxiliary metadata, and keeps persisted storage clean of runtime NLE fields. This closes the stop condition where linked project or NLE-derived subtitle rows could overwrite directly opened SRT timing/text. NAS HeyDealer current-head regression after the slice accepted at `output/manual_verification/latest/direct_srt_precedence_nas_heydealer_20260628/acceptance/reference_benchmark_acceptance.md` with final invalid/non-monotonic/overlap `0/0/0`, global max-active `1`, and timeout detected `false`.

### Cut Boundary Accuracy

Goal: stop missing short visual cuts caused by coarse stride plus rollback-only recovery.

Implementation direction:

- In High mode, run a low-resolution source-fps frame scout in parallel.
- For exact-frame fixture proof, the scout must be allowed to sample the fixture at source fps (`60000/1001`) or an explicit `60fps` test override; the previous `30fps` cap is not enough to prove 1-frame hard cuts at `2766` and `2676`.
- Compute per-frame visual evidence:
  - luma delta,
  - HSV histogram delta,
  - edge delta,
  - dHash/pHash-style perceptual change,
  - pixel-change ratio.
- Keep the fusion/scoring surface centralized in the visual-cut scorer path so manual scan and auto scan share the same luma/pixel/edge/hash/histogram/flow interpretation.
- Keep the existing skip/rollback path as follower/refine logic.
- Make the 1-frame scout the candidate generator for hard cuts.
- Use a local verifier around `n-2 ~ n+2` frames to confirm the exact boundary frame.
- Use optical-flow residual or motion coherence as a false-positive veto for fast camera motion, but do not let flow alone reject an otherwise strong hard-cut candidate.
- Treat VAD/audio change as supporting evidence only; it must not override a confirmed visual hard cut.

Primary fixture acceptance:

- High-mode scan must find or preserve cut evidence at frames `2766` and `2676` on the fixed fixture.
- Final subtitle rows must not cross those confirmed visual cuts.
- If a subtitle starts at frame `2675` and the visual boundary is frame `2676`, it must snap to `2676` when the cut is confirmed.
- Split/snap must not create an invalid subtitle shorter than the minimum duration policy; if a forced split would violate minimum duration, it must be recorded as an explicit trim/drop candidate with trace evidence.

### NLE Marker Contract

Confirmed cuts are point evidence, not clip spans.

Required mapping:

- confirmed visual cut -> `TimelineMarker` / cut-boundary row,
- roughcut exact join -> output-time marker/edit-point candidate,
- clip boundary span -> `Clip` source/sequence span.

Rules:

- Do not mix cut-boundary point and clip-boundary span ownership.
- A confirmed visual cut can force subtitle split/snap.
- A marker does not become a media clip range.
- STT2, LLM, LoRA, and VAD default policies remain unchanged unless a separate owner-approved slice says otherwise.

### Fast Preview / Skimming

Goal: add Final Cut Pro-style immediate preview behavior without changing visible UI layout or introducing a new UI surface.

Implementation direction:

- Keep runtime cut detection separate from preview/skimming.
- Create a low-resolution `Preview` temp cache.
- Pre-decode nearest-frame thumbnails or proxy frames.
- During drag/hover/seek, display the nearest decoded preview frame through the existing video preview surface.
- Cache miss must not decode synchronously on the UI thread.
- Preview/skimming cache is user-preview evidence only; it must never be promoted to confirmed cut-boundary evidence.
- Do not change UI labels, layout, colors, shortcuts, menus, or popup behavior.
- Do not make OpenGL/Metal/QML a new UI default.

### Trace Log Bundle

Goal: make future accuracy, performance, and UI/UX debugging traceable through temporary logs that can be deleted as one workspace.

Temp root:

```text
/tmp/AISubtitleStudioTemporaryWorkspace/
```

Required directories:

- `Diagnostics/Trace`
- `Diagnostics/Packages`
- `Exports`
- `Voice`
- `Preview`

Required files:

- `Diagnostics/Trace/latest.jsonl`
- `Diagnostics/Trace/runs/<run_id>/events.jsonl`
- `Diagnostics/Trace/runs/<run_id>/manifest.json`
- `Diagnostics/Packages/AISSTrace-YYYYMMDD-HHMMSS/`

Manifest fields:

- app name,
- app version,
- git commit,
- git dirty flag,
- Python version,
- macOS version,
- machine,
- pid,
- started timestamp,
- media fingerprint,
- mode/settings snapshot hash.

Media fingerprint rule:

- Do not hash an entire 4K media file for the trace manifest.
- Use bounded identity fields such as size, `mtime_ns`, basename/path hash, duration, frame count, and rational fps.

Event fields:

- common: `ts`, `seq`, `run_id`, `session_id`, `event`, `stage`, `level`, `thread`, `media_id`, `project_id`
- timing/cut: `frame`, `time_sec`, `fps`, `subtitle_index`, `start_sec`, `end_sec`, `duration_sec`, `source`
- performance: `elapsed_ms`, `rss_bytes`, `queue_depth`, `worker_count`
- UI/UX: `widget`, `action`, `geometry`, `visible`, `focused`, `playhead_frame`, `playhead_sec`
- error: `error_type`, `error_message`, `traceback_tail`

Exact frame trace rule:

- For frame-sensitive events, store `fps_num` and `fps_den` alongside any float `fps`.
- The `2766` and `2676` fixture gates must not depend on float-only frame math.

Trace scope:

- pipeline lifecycle,
- media/project open,
- project save,
- queue start/end,
- mode/settings snapshot,
- STT1/STT2/VAD/final segment count,
- first/last subtitle time,
- start/end drift,
- timing consensus decision,
- cut-boundary candidate and score components,
- confirmed cut frame,
- split/snap/drop reason,
- cut-boundary cache restore,
- memory pressure,
- worker lifecycle,
- rolling-window drift,
- file-dialog selected/dispatch,
- editor ready,
- playhead frame/time,
- timeline repaint summary,
- selected subtitle changes.

Performance rule:

- Trace logging must be lightweight and best-effort.
- Frame image dumps are off by default.
- Per-frame scout logs must record score/candidate metadata only unless an explicit debug flag enables bounded image sampling.
- Trace writers must use per-run directories and atomic append/replace patterns so STT workers, FFmpeg helpers, and UI automation do not contend for the same mutable file.
- Trace retention must include a bounded cleanup or package-only retention policy so system temp disk usage cannot grow without limit.
- Trace failure must not call `get_logger().log()` from inside the trace sink; use one-shot disable/drop counters to avoid recursion.
- Do not put raw trace events into `status`, `ping`, or `guided-subtitle-status` UDP responses; those responses must stay compact and point to package paths only.

## Agent Plan

### Jammini

Run:

```bash
tools/jammini_watchdog.sh --status
tools/jammini_watchdog.sh --handoff-probe
tools/jammini_delegate.sh --bootstrap
```

Support packet:

- review this `NLE_Action.md`,
- identify hidden compatibility gaps,
- suggest validation shortlist,
- do not implement code,
- return `DEX_REVIEW_READY` through `.agents/sentinel/handoffs/*.md`.

Dex must classify Jammini output as `accept`, `revise`, `defer`, or `reject` before adoption.

### Agent 1 - NLE Mutable Owner

Responsibility:

- `core/project`,
- editor save/load,
- legacy projection,
- NLE mutable state boundaries.

Output:

- migration slice map,
- data flow,
- compatibility risks,
- focused test list.

No code changes in the first review pass.

### Agent 2 - Cut Boundary + Preview

Responsibility:

- frame scout,
- local verifier,
- preview cache/skimming,
- target fixture frames `2766` and `2676`.

Output:

- algorithm plan,
- score thresholds,
- candidate/verification event schema,
- preview cache integration risks.

No code changes in the first review pass.

### Agent 3 - Trace + QA

Responsibility:

- temp workspace,
- trace logger,
- diagnostics package collector,
- validation gates.

Output:

- trace schema review,
- test plan,
- overhead guard,
- QA command bundle.

No code changes in the first review pass.

## Execution Slices

No active execution slices remain in this file.

## Validation Gates

Basic gate for every slice:

```bash
git status --short --branch
git diff --check -- .
./venv/bin/python -m py_compile <touched Python files>
```

NLE/save/load:

```bash
QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q \
  tests/test_project_nle_snapshot.py \
  tests/test_project_context.py \
  tests/test_project_segment_reload.py \
  tests/test_editor_srt_open_refresh.py
```

Roughcut/export:

```bash
QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q \
  tests/test_roughcut_engine1.py \
  tests/test_roughcut_v2_output_compat.py \
  tests/test_roughcut_ui_v2.py
```

Cut boundary:

```bash
QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q \
  tests/test_cut_boundary_auto_scan_backend.py \
  tests/test_subtitle_boundary_alignment.py \
  tests/test_pipeline_cut_boundary_cache.py
```

Fixed fixture cut-boundary proof:

```bash
AI_SUBTITLE_STUDIO_CUT_BOUNDARY_FIXTURE="/Users/u_mo_c/Library/Mobile Documents/com~apple~CloudDocs/AI_EDIT/내 프로젝트 (3).MP4" \
AI_SUBTITLE_STUDIO_CUT_BOUNDARY_EXPECT="2766,2676" \
AI_SUBTITLE_STUDIO_CUT_BOUNDARY_PIPE_MAX_FPS="60" \
QT_QPA_PLATFORM=offscreen \
./venv/bin/python -m pytest -q tests/test_cut_boundary_fixture_2766_2677.py
```

When the local iCloud fixture is present but FFmpeg/OpenCV decoder access stalls, keep visual detection claims separate and run the metadata/frame-grid verifier explicitly:

```bash
QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/verify_cut_boundary_source_fps_scout.py \
  "/Users/u_mo_c/Library/Mobile Documents/com~apple~CloudDocs/AI_EDIT/내 프로젝트 (3).MP4" \
  --pairs 2765:2766,2675:2676 \
  --pipe-max-fps 60 \
  --fps-override 60000/1001 \
  --allow-metadata-only \
  --probe-timeout-sec 5 \
  --output-dir output/manual_verification/latest/nle_fixed_cut_boundary_fixture_gate_YYYYMMDD
```

This verifier proves exact frame-grid preservation and split/snap guardability only. If `candidate_detected=false`, do not call it visual cut detection proof.

When decoder access is available, run the visual-evidence verifier without metadata fallback and keep the strict detector gate separate:

```bash
QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/verify_cut_boundary_source_fps_scout.py \
  "/Users/u_mo_c/Library/Mobile Documents/com~apple~CloudDocs/AI_EDIT/내 프로젝트 (3).MP4" \
  --pairs 2765:2766,2675:2676 \
  --pipe-max-fps 60 \
  --fps-override 60000/1001 \
  --probe-timeout-sec 5 \
  --frame-extract-timeout-sec 45 \
  --output-dir output/manual_verification/latest/nle_fixed_cut_boundary_visual_evidence_gate_YYYYMMDD

QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/verify_cut_boundary_source_fps_scout.py \
  "/Users/u_mo_c/Library/Mobile Documents/com~apple~CloudDocs/AI_EDIT/내 프로젝트 (3).MP4" \
  --pairs 2765:2766,2675:2676 \
  --pipe-max-fps 60 \
  --fps-override 60000/1001 \
  --probe-timeout-sec 5 \
  --frame-extract-timeout-sec 45 \
  --require-visual-detection \
  --output-dir output/manual_verification/latest/nle_fixed_cut_boundary_visual_evidence_gate_YYYYMMDD_strict
```

The second command is expected to fail while frame `2766` remains `preserved_only`. The corrected frame `2676` is the detected target; a partial preserved-only pass must not be reported as full visual detection proof.

To inspect whether the target frame or a neighbor owns the strongest visual transition before tuning detector thresholds, run the read-only window audit:

```bash
QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_cut_boundary_visual_window.py \
  "/Users/u_mo_c/Library/Mobile Documents/com~apple~CloudDocs/AI_EDIT/내 프로젝트 (3).MP4" \
  --targets 2766,2676 \
  --radius 3 \
  --pipe-max-fps 60 \
  --fps-override 60000/1001 \
  --probe-timeout-sec 5 \
  --frame-extract-timeout-sec 45 \
  --output-dir output/manual_verification/latest/nle_cut_boundary_visual_window_audit_YYYYMMDD
```

This command returns exit `1` while any target is not detected. That failure is expected evidence, not a runtime regression.

Then freeze target-vs-neighbor frame semantics from that window artifact:

```bash
QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_cut_boundary_frame_semantics.py \
  output/manual_verification/latest/nle_cut_boundary_visual_window_audit_YYYYMMDD/cut_boundary_visual_window_audit.json \
  --output-dir output/manual_verification/latest/nle_cut_boundary_frame_semantics_audit_YYYYMMDD
```

This command returns exit `1` while target detection gaps or neighbor-frame semantic conflicts remain. Treat that as a fixture/convention review gate before detector threshold tuning.

When frame-semantics review remains required, materialize actual fixture frames into PNG contact sheets before changing detector thresholds:

```bash
QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_cut_boundary_fixture_convention.py \
  output/manual_verification/latest/nle_cut_boundary_frame_semantics_audit_YYYYMMDD/cut_boundary_frame_semantics_audit.json \
  --output-dir output/manual_verification/latest/nle_cut_boundary_fixture_convention_audit_YYYYMMDD
```

This command also returns exit `1` while fixture label/boundary convention review remains required. Treat that as visual evidence that blocks threshold tuning until the target-frame convention is decided.

If a convention audit proves a requested target is one frame late, write the corrected QA target map before changing detector thresholds:

```bash
QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_cut_boundary_fixture_target_correction.py \
  output/manual_verification/latest/nle_cut_boundary_fixture_convention_audit_YYYYMMDD/cut_boundary_fixture_convention_audit.json \
  --output-dir output/manual_verification/latest/nle_cut_boundary_fixture_target_correction_YYYYMMDD
```

This command is read-only for runtime behavior. It may update future QA target inputs, but it must not approve threshold relaxation, subtitle/STT policy changes, UI/QML work, persisted NLE fields, or App Store work.

When a corrected target remains preserved-only, prove whether it is actually a detector tuning candidate across scorer modes and widths:

```bash
QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_cut_boundary_detector_evidence_robustness.py \
  "/Users/u_mo_c/Library/Mobile Documents/com~apple~CloudDocs/AI_EDIT/내 프로젝트 (3).MP4" \
  --pairs 2765:2766,2675:2676 \
  --output-dir output/manual_verification/latest/nle_cut_boundary_2766_detector_robustness_YYYYMMDD
```

This command is read-only for runtime behavior. If it reports `weak_visual_change_not_threshold_candidate`, keep the frame as preserved marker/frame-grid evidence or revisit fixture truth; do not lower visual detector thresholds from that fixture alone.

Trace:

```bash
QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q \
  tests/test_trace_logger.py \
  tests/test_startup_diagnostics.py \
  tests/test_app_command_bridge.py \
  -k "trace or diagnostic or open_media or open_project"
```

Fixture proof:

- Run the fixed fixture in High mode.
- Verify frame `2766` and `2676` cut detection/split/snap.
- Verify X5/Macau subtitle count, first/last time, output duration, and sidecar metadata do not drift.
- If affected, run:

```bash
AI_SUBTITLE_STUDIO_QA_USE_SOURCE=1 ./venv/bin/python tools/qa_suite_runner.py quick
```

## Commit And Release Policy

- Commit only when the owner explicitly asks.
- Push only when the owner explicitly asks.
- Do not build DMG.
- Do not move release tags.
- Do not perform App Store/TestFlight work.
