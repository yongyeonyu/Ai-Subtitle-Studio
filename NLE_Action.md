# NLE_Action.md - Mutable NLE, Cut Boundary, Preview, Trace Execution Plan

<!--
Document-Version: 04.00.18-nle-action
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
- Latest owner-map audit: `output/manual_verification/latest/nle_runtime_owner_map_audit_20260628/nle_runtime_owner_map_audit.md`; current release/commit NLE runtime mutation owners are covered `23/23`, runtime behavior changed `false`, and blocked candidates remain persisted NLE disk fields, per-pixel NLE writes, and QML/GPU timeline default surface changes.
- Latest adapter/cache consistency audit: `output/manual_verification/latest/nle_adapter_consistency_audit_20260628/nle_adapter_consistency_audit.md`; repeated save/reopen cycles pass `6/6`, runtime-only `_nle_project_state` markers do not persist after cache clear/reopen, storage stays clean, final invalid/non-monotonic/overlap stays `0/0/0`, global max-active stays `1`, and the project file LRU cache respects its `4` entry limit.
- Latest operation journal/undo contract audit: `output/manual_verification/latest/nle_operation_journal_audit_20260628/nle_operation_journal_audit.md`; all `11` current NLE operation families carry release commit metadata and undo snapshot metadata, storage stays clean of operation/undo/runtime NLE schemas, final invalid/non-monotonic/overlap stays `0/0/0`, global max-active stays `1`, and runtime behavior changed `false`.
- Latest NAS HeyDealer first-180s source-app regression after the operation-journal slice: `output/manual_verification/latest/nle_operation_journal_nas_heydealer_20260628/acceptance/reference_benchmark_acceptance.md`; accepted `true`, raw/final/reference `58/56/89`, quality/text/timing `93.766/94.267/0.5808s`, final invalid/non-monotonic/overlap `0/0/0`, and global max-active `1`.
- Latest runtime in-memory operation journal audit: `output/manual_verification/latest/nle_runtime_operation_journal_20260628/nle_operation_journal_audit.md`; all `11` current NLE operation families now append bounded runtime-only journal entries to `NLEProjectState` while keeping legacy storage clean of operation/undo/journal/runtime NLE schemas. NAS HeyDealer first-180s regression after this slice is accepted at `output/manual_verification/latest/nle_runtime_operation_journal_nas_heydealer_20260628/acceptance/reference_benchmark_acceptance.md` with final invalid/non-monotonic/overlap `0/0/0` and global max-active `1`.
- Latest preview/skimming cache contract audit: `output/manual_verification/latest/nle_preview_skimming_cache_audit_20260628/nle_preview_skimming_cache_audit.md`; preview cache files remain under the temp `Preview/FrameThumbnails` workspace, carry `user_preview_only` manifest provenance, are explicitly not cut-boundary evidence, and cache miss continues to schedule async preparation instead of sync UI-thread decode.
- Latest preview/skimming trace-event audit: `output/manual_verification/latest/nle_preview_skimming_trace_audit_20260628/nle_preview_skimming_cache_audit.md`; preview cache hit/miss/schedule/ready events now flow through the async `TraceLogger` queue with `editor_preview_skimming`, `user_preview_only`, `cut_boundary_evidence=false`, exact `fps_num/fps_den`, and the existing preview seek throttle preserved.
- Latest confirmed cut-boundary decision trace audit: `output/manual_verification/latest/nle_confirmed_cut_trace_audit_20260628/trace_log_bundle_audit.md`; confirmed visual-cut split/snap/drop decisions now emit async `confirmed_cut_split_snap` events with `event_type=cut_boundary_decision`, `decision`, `provisional_frame`, `drop_reason`, exact `fps_num/fps_den`, and no detector-threshold, UI, or persisted-NLE behavior change. NAS HeyDealer first-180s regression after this slice is accepted at `output/manual_verification/latest/nle_confirmed_cut_trace_nas_heydealer_20260628/acceptance/reference_benchmark_acceptance.md`.
- Latest fixed cut-boundary visual evidence gate: `output/manual_verification/latest/nle_fixed_cut_boundary_visual_evidence_gate_20260628/source_fps_scout.md`; decoder-based frame extraction now succeeds on the local 60000/1001fps fixture, target frames `2766` and `2677` are preserved on the exact frame grid, and the verifier separates `preserved_only` from `detected`. Current evidence reports `strict_visual_detection_passed=false`, `visual_candidate_missing_count=2`, and the strict `--require-visual-detection` artifact at `output/manual_verification/latest/nle_fixed_cut_boundary_visual_evidence_gate_20260628_strict/source_fps_scout.md` fails as expected, so visual detector tuning remains open.
- Latest cut-boundary visual window audit: `output/manual_verification/latest/nle_cut_boundary_visual_window_audit_20260628/cut_boundary_visual_window_audit.md`; the read-only ±3 frame ranking keeps runtime behavior unchanged and shows target frames `2766` and `2677` are not the strongest visual transitions in their local windows. Frame `2766` ranks `4` with score `2.059` and best nearby frame `2769` score `2.715`; frame `2677` ranks `2` with score `1.997`, while frame `2676` scores `71.932` and is detected. Treat this as frame-semantics/detector-tuning evidence, not a threshold-change approval.
- Latest cut-boundary frame-semantics audit: `output/manual_verification/latest/nle_cut_boundary_frame_semantics_audit_20260628/cut_boundary_frame_semantics_audit.md`; the read-only classifier reports `frame_semantics_review_required=true`, semantic mismatch count `1`, target detection gaps `2`, detected-neighbor conflict count `1`, detector-tuning candidate count `1`, and `runtime_change_allowed=false`. Frame `2766` remains a target detection gap, while frame `2677` is classified as `detected_neighbor_before_target` because the strongest detected transition is `2675 -> 2676`; verify fixture label/boundary-frame convention before threshold tuning. NAS HeyDealer first-180s regression after this slice accepted at `output/manual_verification/latest/nle_frame_semantics_nas_heydealer_20260628/acceptance/reference_benchmark_acceptance.md`, but elapsed `179.579s` is a slow STT1 collect run, not a speed approval.

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
- `2676 -> 2677` (`frame 2677`, approx `44.6613s`)

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

### Cut Boundary Accuracy

Goal: stop missing short visual cuts caused by coarse stride plus rollback-only recovery.

Implementation direction:

- In High mode, run a low-resolution source-fps frame scout in parallel.
- For exact-frame fixture proof, the scout must be allowed to sample the fixture at source fps (`60000/1001`) or an explicit `60fps` test override; the previous `30fps` cap is not enough to prove 1-frame hard cuts at `2766` and `2677`.
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

- High-mode scan must find or preserve cut evidence at frames `2766` and `2677` on the fixed fixture.
- Final subtitle rows must not cross those confirmed visual cuts.
- If a subtitle starts at frame `2676` and the visual boundary is frame `2677`, it must snap to `2677` when the cut is confirmed.
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
- The `2766` and `2677` fixture gates must not depend on float-only frame math.

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
- target fixture frames `2766` and `2677`.

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
AI_SUBTITLE_STUDIO_CUT_BOUNDARY_EXPECT="2766,2677" \
AI_SUBTITLE_STUDIO_CUT_BOUNDARY_PIPE_MAX_FPS="60" \
QT_QPA_PLATFORM=offscreen \
./venv/bin/python -m pytest -q tests/test_cut_boundary_fixture_2766_2677.py
```

When the local iCloud fixture is present but FFmpeg/OpenCV decoder access stalls, keep visual detection claims separate and run the metadata/frame-grid verifier explicitly:

```bash
QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/verify_cut_boundary_source_fps_scout.py \
  "/Users/u_mo_c/Library/Mobile Documents/com~apple~CloudDocs/AI_EDIT/내 프로젝트 (3).MP4" \
  --pairs 2765:2766,2676:2677 \
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
  --pairs 2765:2766,2676:2677 \
  --pipe-max-fps 60 \
  --fps-override 60000/1001 \
  --probe-timeout-sec 5 \
  --frame-extract-timeout-sec 45 \
  --output-dir output/manual_verification/latest/nle_fixed_cut_boundary_visual_evidence_gate_YYYYMMDD

QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/verify_cut_boundary_source_fps_scout.py \
  "/Users/u_mo_c/Library/Mobile Documents/com~apple~CloudDocs/AI_EDIT/내 프로젝트 (3).MP4" \
  --pairs 2765:2766,2676:2677 \
  --pipe-max-fps 60 \
  --fps-override 60000/1001 \
  --probe-timeout-sec 5 \
  --frame-extract-timeout-sec 45 \
  --require-visual-detection \
  --output-dir output/manual_verification/latest/nle_fixed_cut_boundary_visual_evidence_gate_YYYYMMDD_strict
```

The second command is expected to fail until the detector itself finds frames `2766` and `2677`. A preserved-only pass must not be reported as visual detection proof.

To inspect whether the target frame or a neighbor owns the strongest visual transition before tuning detector thresholds, run the read-only window audit:

```bash
QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_cut_boundary_visual_window.py \
  "/Users/u_mo_c/Library/Mobile Documents/com~apple~CloudDocs/AI_EDIT/내 프로젝트 (3).MP4" \
  --targets 2766,2677 \
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
- Verify frame `2766` and `2677` cut detection/split/snap.
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
