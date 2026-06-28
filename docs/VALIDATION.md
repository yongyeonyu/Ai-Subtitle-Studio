# Validation Guide

이 문서는 현재 저장소에서 실제로 확인되는 검증 경로만 정리합니다. 새 인프라를 상정하지 말고, 이미 있는 pytest, QA 스크립트, source-app smoke 흐름을 우선 사용합니다.

## Validation principles

- 수정 범위에 맞는 가장 좁은 검증부터 시작합니다.
- 편집기/타임라인/UI 변경은 가능하면 `QT_QPA_PLATFORM=offscreen` 검증을 포함합니다.
- 릴리스 수준 변경이나 생성 파이프라인 변경은 pytest만으로 끝내지 말고 `tools/qa_suite_runner.py` 또는 실앱 검증 산출물을 남깁니다.
- 문서만 수정했더라도 handoff와 diff 검토는 생략하지 않습니다.

## Syntax / compile validation

코드 파일을 수정했다면 안전한 기본 문법 검사는 아래 중 하나를 사용합니다.

```bash
python -m compileall .
```

가상환경 기준으로 저장소가 자주 사용하는 더 좁은 명령은 아래와 같습니다.

```bash
./venv/bin/python -m compileall -q main.py core ui tests tools
```

문서 전용 작업이라면 코드 파일을 바꾸지 않았는지 먼저 확인하고, 코드 변경이 없으면 compile 단계는 선택적으로 생략할 수 있습니다.

## Import validation

가벼운 import 검증이 필요하면 아래처럼 owner 모듈을 직접 import 합니다.

```bash
QT_QPA_PLATFORM=offscreen ./venv/bin/python - <<'PY'
from ui.main.main_window import MainWindow
print("import-ok", MainWindow.__name__)
PY
```

편집기 owner를 건드렸다면 `ui.editor.editor_widget`, 타임라인이면 `ui.timeline.timeline_widget`, 프로젝트면 `core.project.project_format` 같은 직접 owner import를 우선 선택합니다.

## Tests

전체 스위트와 빠른 검증 경로가 함께 존재합니다.

빠른 표준 검증:

```bash
./venv/bin/python tools/qa_suite_runner.py quick
```

주요 검증:

```bash
./venv/bin/python tools/qa_suite_runner.py major
```

전체 검증:

```bash
./venv/bin/python tools/qa_suite_runner.py full
```

`full`의 기본 X5 경로는 `test video/X5_시승기_후반.MP4`입니다. 자동 fallback 후보는 오디오 스트림이 있을 때만 선택되며, 표준 MP4가 없으면 X5 시나리오는 `media_missing`으로 실패해야 합니다. 오디오가 있는 외부 X5 소스를 보조 proof로 사용할 때만 아래처럼 명시 override를 사용하고, 결과 보고서에는 표준 MP4 proof와 구분해서 기록합니다.

```bash
AI_SUBTITLE_STUDIO_QA_USE_SOURCE=1 AI_SUBTITLE_STUDIO_QA_X5_MEDIA='/path/to/audio-bearing-x5-media' ./venv/bin/python tools/qa_suite_runner.py full
```

기능별로는 owner 주변의 좁은 pytest를 먼저 사용합니다. 예시는 아래와 같습니다.

```bash
./venv/bin/python -m pytest -q tests/test_main_window_nonfatal.py
./venv/bin/python -m pytest -q tests/test_editor_srt_open_refresh.py tests/test_project_segment_reload.py
./venv/bin/python -m pytest -q tests/test_timeline_*.py
./venv/bin/python -m pytest -q tests/test_roughcut_*.py
```

## Trace workspace validation

Trace/temp-workspace changes should first prove syntax, focused trace behavior, then the startup/app-command diagnostic guard.

```bash
./venv/bin/python -m py_compile main.py core/runtime/temp_workspace.py core/runtime/trace_logger.py tools/collect_trace_package.py tools/audit_trace_log_bundle.py tests/test_trace_logger.py tests/test_trace_log_bundle_audit.py tests/test_startup_diagnostics.py
QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_trace_logger.py tests/test_trace_log_bundle_audit.py
QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_trace_log_bundle.py --output-dir output/manual_verification/latest/trace_log_bundle_audit_YYYYMMDD
QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_trace_logger.py tests/test_startup_diagnostics.py tests/test_app_command_bridge.py -k "trace or diagnostic or open_media or open_project"
```

Trace packages are collected with:

```bash
./venv/bin/python tools/collect_trace_package.py --run-id <trace-run-id>
```

The trace audit must prove required temp directories, manifest/latest/events JSONL, bounded media fingerprinting, exact-frame `fps_num`/`fps_den`, package collection, trace failure isolation, and run-directory retention. Current retention policy keeps at most 20 trace run directories after a new trace run starts.

## Cut-boundary source-fps scout validation

For the fixed 60000/1001fps NLE Slice 2 fixture, use the narrow verifier before broad QA:

```bash
AI_SUBTITLE_STUDIO_CUT_BOUNDARY_FIXTURE="/Users/u_mo_c/Library/Mobile Documents/com~apple~CloudDocs/AI_EDIT/내 프로젝트 (3).MP4" \
AI_SUBTITLE_STUDIO_CUT_BOUNDARY_EXPECT="2766,2676" \
AI_SUBTITLE_STUDIO_CUT_BOUNDARY_PIPE_MAX_FPS="60" \
QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_cut_boundary_fixture_2766_2677.py

QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/verify_cut_boundary_source_fps_scout.py \
  "/Users/u_mo_c/Library/Mobile Documents/com~apple~CloudDocs/AI_EDIT/내 프로젝트 (3).MP4" \
  --pairs 2765:2766,2675:2676 \
  --pipe-max-fps 60 \
  --fps-override 60000/1001 \
  --allow-metadata-only \
  --probe-timeout-sec 5 \
  --output-dir output/manual_verification/latest/nle_fixed_cut_boundary_fixture_gate_YYYYMMDD
```

This verifier records whether target frames `2766` and `2676` are newly detected or at least preserved on the exact source-fps frame grid. The old `2677` target is superseded by corrected frame `2676`. If `candidate_detected=false`, report that as a remaining false-negative tuning risk even when `frame_preserved=true`. The `--allow-metadata-only` path is allowed only when decoder access to the fixed fixture stalls; it proves frame-grid preservation and split/snap guardability, not visual cut detection.

When decoder access is available, run the visual-evidence path without `--allow-metadata-only` and keep the strict detector gate separate:

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

The strict command must fail while any current target frame is only `preserved_only`; that failure is useful evidence and blocks full visual-detection claims until detector tuning is separately proven. Current evidence detects corrected frame `2676` and keeps frame `2766` open.

Before changing detector thresholds, rank the target frame against its neighboring transitions:

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

This audit is read-only and exits `1` while any target is not detected. Use it to decide whether the next slice is detector tuning or frame-semantics correction; do not use it to relax thresholds by itself.

When the window audit shows a detected neighbor instead of the requested target frame, freeze the frame-semantics classification before changing detector thresholds:

```bash
QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_cut_boundary_frame_semantics.py \
  output/manual_verification/latest/nle_cut_boundary_visual_window_audit_YYYYMMDD/cut_boundary_visual_window_audit.json \
  --output-dir output/manual_verification/latest/nle_cut_boundary_frame_semantics_audit_YYYYMMDD
```

This audit reads the previous window JSON only. It exits `1` while a target detection gap or neighbor-frame semantic conflict remains, and that failure must be treated as review evidence. Do not use it to approve threshold relaxation, subtitle/STT policy changes, UI/QML work, persisted NLE fields, or App Store work.

If the frame-semantics audit still requires convention review, create actual fixture-frame contact sheets before tuning the detector:

```bash
QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_cut_boundary_fixture_convention.py \
  output/manual_verification/latest/nle_cut_boundary_frame_semantics_audit_YYYYMMDD/cut_boundary_frame_semantics_audit.json \
  --output-dir output/manual_verification/latest/nle_cut_boundary_fixture_convention_audit_YYYYMMDD
```

This command materializes PNG contact sheets for the target and strongest neighbor transitions, then exits `1` while fixture label/boundary-frame convention review remains required. The report is visual evidence only; it must not approve threshold relaxation, subtitle/STT policy changes, UI/QML work, persisted NLE fields, or App Store work.

If the convention audit proves a requested target is one frame late, run the read-only target-correction audit before updating future fixed-fixture QA inputs:

```bash
QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_cut_boundary_fixture_target_correction.py \
  output/manual_verification/latest/nle_cut_boundary_fixture_convention_audit_YYYYMMDD/cut_boundary_fixture_convention_audit.json \
  --output-dir output/manual_verification/latest/nle_cut_boundary_fixture_target_correction_YYYYMMDD
```

This command may correct QA target frames such as historical `2677 -> 2676`, but it must not approve threshold relaxation, subtitle/STT policy changes, UI/QML work, persisted NLE fields, or App Store work.

When a corrected target remains only frame-preserved, audit whether the miss is a real detector-tuning candidate across existing scorer modes and widths:

```bash
QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_cut_boundary_detector_evidence_robustness.py \
  "/Users/u_mo_c/Library/Mobile Documents/com~apple~CloudDocs/AI_EDIT/내 프로젝트 (3).MP4" \
  --pairs 2765:2766,2675:2676 \
  --output-dir output/manual_verification/latest/nle_cut_boundary_2766_detector_robustness_YYYYMMDD
```

If this audit reports `weak_visual_change_not_threshold_candidate`, treat that as a threshold-tuning stop sign for the fixture. Preserve the boundary as frame-grid/marker evidence or revisit fixture truth instead of lowering visual detector thresholds from that evidence alone.

When a corrected target is frame-preserved but not a detector-tuning candidate, freeze the marker policy before any broader NLE/cut-boundary work:

```bash
QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_cut_boundary_preserved_marker_policy.py \
  --source-fps-scout output/manual_verification/latest/nle_corrected_target_source_fps_scout_YYYYMMDD/source_fps_scout.json \
  --detector-robustness output/manual_verification/latest/nle_cut_boundary_2766_detector_robustness_YYYYMMDD/cut_boundary_detector_evidence_robustness.json \
  --output-dir output/manual_verification/latest/nle_preserved_marker_policy_YYYYMMDD
```

This audit should classify visually detected frames as `visual_marker_confirmed` and weak-but-preserved frames such as `2766` as `preserved_marker_required`. It must keep confirmed cuts as point evidence rather than clip spans, block visual threshold lowering from preserved markers, and reference the split/snap no-crossing guard in `tests/test_cut_boundary_fixture_2766_2677.py`.

## Preview frame cache validation

Preview/skimming cache changes should prove temp-workspace cache lookup, nonblocking preview seek behavior, and unchanged timeline scrub routing.

```bash
./venv/bin/python -m py_compile core/runtime/temp_workspace.py core/runtime/preview_frame_cache.py ui/editor/video_player_widget.py ui/editor/video_player_surface.py tests/test_preview_frame_cache.py tests/test_video_player_widget.py
QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_preview_frame_cache.py tests/test_video_player_widget.py -k "preview_frame_cache or preview_seek or processing_thumbnail"
QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py -k "scrub_updates_playhead_immediately_and_uses_lightweight_preview_seek or scrub_throttles_video_seek_during_fast_mouse_moves or timing_drag_preview_updates_playhead_and_uses_lightweight_preview_seek or auto_cut_boundary_preview_moves_playhead_without_thumbnail_work"
```

For cache-miss UI-thread block prevention, add the stricter slow-worker guard and audit:

```bash
./venv/bin/python -m py_compile tools/audit_nle_preview_skimming_cache.py tests/test_nle_preview_skimming_cache_audit.py tests/test_video_player_widget.py
QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_video_player_widget.py -k "preview_seek_cache_miss or preview_frame_cache_prepare or nearest_preview_frame_trace"
QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_nle_preview_skimming_cache_audit.py tests/test_preview_frame_cache.py
./venv/bin/python tools/audit_nle_preview_skimming_cache.py --output-dir output/manual_verification/latest/nle_preview_skimming_cache_miss_block_free_YYYYMMDD
```

Acceptance requires audit `ready=true`, every `cache_miss_thread_contract` field `true`, slow-worker `preview_seek()` elapsed below `50ms`, preview provenance `user_preview_only`, `cut_boundary_evidence=false`, and `ui_thread_decode_allowed=false`.

## NLE mutable owner pilot validation

Runtime-only NLE state changes should prove legacy hydration, non-persistence of NLE runtime fields, direct SRT/no-media safety, save/reopen compatibility, final-surface no-overlap projection, and roughcut sidecar/render parity.

```bash
./venv/bin/python -m py_compile core/project/nle_project_state.py core/project/project_io.py core/project/project_format.py core/project/project_manager.py tests/test_project_nle_snapshot.py
QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_snapshot.py -k "runtime_nle or save_project_routes or direct_srt_rows or roughcut_exact_join_marker_parity or compatibility_characterization or project_file_roundtrip"
QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_snapshot.py tests/test_project_context.py tests/test_project_segment_reload.py tests/test_editor_srt_open_refresh.py
QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_roughcut_engine1.py tests/test_roughcut_v2_output_compat.py tests/test_roughcut_ui_v2.py
QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_runtime_cutover.py tests/test_timeline_playhead_fit.py tests/test_subtitle_live_editor_feed_facade.py -k "final_overlay or global_canvas or save_export or overlap or nle"
QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_nle_persistence_cutover.py --output-dir output/manual_verification/latest/nle_persistence_cutover_audit_YYYYMMDD
QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_persistence_guard.py tests/test_nle_persistence_cutover_audit.py tests/test_project_nle_dual_write.py -k "persistence or cutover or dual_write or gap_delete or caption_move or caption_resize or caption_split or caption_range_replace or caption_merge or caption_delete or candidate_confirm or marker_edit"
```

The persistence cutover audit must also report provisional `marker_edit` save/reopen preservation plus render/export parity before any future persisted NLE format proposal: all 12 current dual-write operation families pass, including output-domain `roughcut_range_edit`; marker rows are preserved after reopen, stable `source_subtitles`, `final_overlay`, `global_canvas`, `roughcut_sidecar`, and `exported_assets` surfaces; final invalid/non-monotonic/overlap `0/0/0`; global max active `1`; and disk storage clean of unapproved NLE runtime fields.

## NLE operation journal trace validation

Runtime-only operation journal trace changes should prove one safe event per commit-family append, no raw caption text or project path leakage, no raw target id list, and unchanged legacy storage/final-surface stability.

```bash
./venv/bin/python -m py_compile core/project/nle_project_state.py tools/audit_nle_operation_journal.py tests/test_project_nle_operations.py tests/test_nle_operation_journal_audit.py
QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_operations.py tests/test_nle_operation_journal_audit.py -k "operation_journal"
QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_operations.py tests/test_project_nle_dual_write.py tests/test_nle_operation_journal_audit.py tests/test_nle_runtime_owner_map_audit.py
./venv/bin/python tools/audit_nle_operation_journal.py --output-dir output/manual_verification/latest/nle_operation_journal_trace_audit_YYYYMMDD
```

The audit must report operation trace event count `12`, trace event contract ok `True`, final invalid/non-monotonic/overlap `0/0/0`, global max active `1`, clean legacy storage, and no emitted caption text, raw project path, or raw `target_ids`.

## NLE gap-delete sequence policy validation

Gap-delete dual-write changes must prove the current AI Subtitle Studio contract: explicit gap delete removes the gap row and preserves adjacent caption timing. It must not silently ripple the timeline unless the owner approves a separate ripple/absorb operation.

```bash
./venv/bin/python -m py_compile core/project/nle_dual_write.py tools/audit_nle_gap_delete_sequence_policy.py tests/test_project_nle_dual_write.py tests/test_nle_gap_delete_sequence_policy_audit.py
QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_dual_write.py tests/test_nle_gap_delete_sequence_policy_audit.py -k "gap_delete or sequence_policy"
./venv/bin/python tools/audit_nle_gap_delete_sequence_policy.py --output-dir output/manual_verification/latest/nle_gap_delete_sequence_policy_YYYYMMDD
```

Acceptance requires audit `ready=true`, sequence policy `remove_gap_row_no_ripple`, adjacent caption bounds preserved in legacy rows, runtime NLE rows, and raw vector storage, clean legacy project storage, final invalid/non-monotonic/overlap `0/0/0`, and global max active `1`. Run NAS HeyDealer first-180s regression when this runtime dual-write contract changes.

## NLE cut marker point projection validation

Marker-edit dual-write changes must prove confirmed/provisional cut markers stay point evidence and do not leak clip-span mapping into legacy editor context.

```bash
./venv/bin/python -m py_compile core/project/nle_dual_write.py tools/audit_nle_cut_marker_point_projection.py tests/test_project_nle_dual_write.py tests/test_nle_cut_marker_point_projection_audit.py
QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_dual_write.py tests/test_nle_cut_marker_point_projection_audit.py -k "marker_edit or cut_marker_point"
./venv/bin/python tools/audit_nle_cut_marker_point_projection.py --output-dir output/manual_verification/latest/nle_cut_marker_point_projection_YYYYMMDD
```

Acceptance requires audit `passed=true`, observed frames `2766,2676`, marker policy `point_evidence_no_clip_span`, span leak count `0`, clip boundaries unchanged, final invalid/non-monotonic/overlap `0/0/0`, global max active `1`, and clip-span mapping allowed `false`. Run NAS HeyDealer first-180s regression when this runtime marker projection contract changes.

## NLE projection metadata preservation validation

Runtime dual-write projection metadata changes must prove existing product metadata survives NLE-to-legacy projection without adding new persisted NLE fields or arbitrary legacy custom schema expansion.

```bash
./venv/bin/python -m py_compile core/project/nle_dual_write.py core/project/nle_operations.py tools/audit_nle_projection_metadata_preservation.py tests/test_project_nle_dual_write.py tests/test_nle_projection_metadata_preservation_audit.py
QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_dual_write.py tests/test_nle_projection_metadata_preservation_audit.py -k "metadata_preservation or projection_metadata"
QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_snapshot.py tests/test_project_context.py tests/test_editor_srt_open_refresh.py -k "runtime_nle or direct_srt or project_file_roundtrip or metadata or save_project_routes"
./venv/bin/python tools/audit_nle_projection_metadata_preservation.py --output-dir output/manual_verification/latest/nle_projection_metadata_preservation_YYYYMMDD
```

Acceptance requires audit `ready=true`, static deepcopy contract true for retime/manual/sort/shadow/operation serialization, caption move preserving quality/STT candidate metadata, caption merge preserving kept-row metadata, caption split preserving child speaker/words metadata while keeping manual-quality removal policy, clean legacy project storage, final invalid/non-monotonic/overlap `0/0/0`, and global max active `1`. Run NAS HeyDealer first-180s regression when this runtime dual-write projection contract changes.

## NLE drag commit-boundary validation

Timeline body drag changes must prove Taption-style preview-only behavior until release. Mouse-move previews may update the canvas insertion/neighbor preview, but runtime NLE dual-write must stay at `0` calls until the release commit.

```bash
./venv/bin/python -m py_compile ui/editor/ux/timeline_input.py tools/audit_nle_runtime_owner_map.py tests/test_nle_runtime_owner_map_audit.py tests/test_editor_timeline_drag_release.py
QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_editor_timeline_drag_release.py -k "center_drag_preview_waits_until_release"
QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_nle_runtime_owner_map_audit.py
./venv/bin/python tools/audit_nle_runtime_owner_map.py --output-dir output/manual_verification/latest/nle_drag_commit_boundary_guard_YYYYMMDD
```

The audit must report runtime owner map ready `True`, covered owners `24/24`, commit-boundary guards `1/1`, missing commit-boundary guards `0`, and `timeline_center_drag_preview_only_until_release` covered. The focused PyQt test must prove NLE move call count `0` during mouse move, call count `1` on release, unchanged editor rows until release, and updated canvas preview rows before release. Broader drag validation should also keep left/right diamond shared-boundary drags gap-free.

## NLE viewport zoom decoupling validation

Timeline wheel zoom/scroll changes must prove they update viewport scale or scroll only. They must not rewrite primary subtitle rows, append runtime NLE operation journals, save projects, or change UI layout/labels/menus.

```bash
./venv/bin/python -m py_compile tools/audit_nle_viewport_zoom_decoupling.py tests/test_timeline_wheel_zoom_decoupling.py tests/test_nle_viewport_zoom_decoupling_audit.py
QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_wheel_zoom_decoupling.py tests/test_nle_viewport_zoom_decoupling_audit.py
./venv/bin/python tools/audit_nle_viewport_zoom_decoupling.py --output-dir output/manual_verification/latest/nle_viewport_zoom_decoupling_YYYYMMDD
```

Acceptance requires audit `ready=true`, viewport-only contract `true`, model/NLE writes allowed `false/false`, forbidden wheel-method calls/assignments `0`, and focused tests proving canvas/global subtitle rows are unchanged after wheel interactions. NAS HeyDealer generation validation is not required unless the slice touches STT/VAD/subtitle generation or final subtitle rows.

## NLE playhead jump isolation validation

Timeline/global-canvas playhead jump changes must prove they update only scrub/playhead/preview state in the immediate path. They must not validate or rewrite primary subtitle rows, append runtime NLE operation journals, save projects, run STT/LLM/backend model checks, or change UI layout/labels/menus.

```bash
./venv/bin/python -m py_compile tools/audit_nle_playhead_jump_isolation.py tests/test_timeline_playhead_jump_isolation.py tests/test_nle_playhead_jump_isolation_audit.py
QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_jump_isolation.py tests/test_nle_playhead_jump_isolation_audit.py
./venv/bin/python tools/audit_nle_playhead_jump_isolation.py --output-dir output/manual_verification/latest/nle_playhead_jump_isolation_YYYYMMDD
```

Acceptance requires audit `ready=true`, playhead-jump view-only contract `true`, model validation/project save/NLE writes allowed `false/false/false`, forbidden method calls/assignments `0`, and focused tests proving canvas/global subtitle rows are unchanged after playhead-jump interactions. NAS HeyDealer generation validation is not required unless the slice touches STT/VAD/subtitle generation or final subtitle rows.

## NLE time-window view decoupling validation

Timeline fit-to-view and time-window controls must prove they update only viewport scale, scroll, global viewport, and overlay sync state. They must not validate or rewrite primary subtitle rows, append runtime NLE operation journals, save projects, run STT/LLM/backend model checks, or change UI layout/labels/menus.

```bash
./venv/bin/python -m py_compile tools/audit_nle_time_window_view_decoupling.py tests/test_timeline_time_window_decoupling.py tests/test_nle_time_window_view_decoupling_audit.py
QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_time_window_decoupling.py tests/test_nle_time_window_view_decoupling_audit.py
./venv/bin/python tools/audit_nle_time_window_view_decoupling.py --output-dir output/manual_verification/latest/nle_time_window_view_decoupling_YYYYMMDD
```

Acceptance requires audit `ready=true`, view-window-only contract `true`, model validation/project save/NLE writes allowed `false/false/false`, forbidden method calls/assignments `0`, and focused tests proving canvas/global subtitle rows are unchanged after fit/time-window interactions. NAS HeyDealer generation validation is not required unless the slice touches STT/VAD/subtitle generation or final subtitle rows.

## Project IO trace validation

Project save/load trace changes should prove best-effort trace events without raw path leakage, runtime NLE state hydration on read, and clean legacy storage on write.

```bash
./venv/bin/python -m py_compile core/project/project_io.py tools/audit_project_io_trace_contract.py tests/test_trace_logger.py
QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_trace_logger.py tests/test_trace_log_bundle_audit.py
./venv/bin/python tools/audit_project_io_trace_contract.py --output-dir output/manual_verification/latest/project_io_trace_contract_YYYYMMDD
```

## Post-generation editor readiness validation

Post-generation editor readiness changes should prove command responsiveness, subtitle-time-edit interaction recovery, editor shell geometry stability, and any requested bottom-menu affordance.

```bash
QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_app_command_bridge.py tests/test_sidebar_terminal_layout.py tests/test_global_menu_bar.py tests/test_editor_precision_refine.py -k "post_generation_pending_cleanup_keeps_editor_commands_interactive or subtitle_time_edit_leaves_editor_controls_interactive or post_generation_cleanup_keeps_editor_shell_geometry_stable or precision_button or precision_refine_applies_quality_timing_and_magnet_result"
```

When the owner asks to limit real-media validation to the NAS HeyDealer first three minutes, use the reference-SRT benchmark path below instead of broad Macau/X5/Tinyping QA.

```bash
QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/benchmark_subtitle_pipeline_variants.py --suite modes --variants mode_high --media "/Volumes/photo/22_유튜브영상_개인/[20260209]헤이딜러광고/헤이딜러_최종.MP4" --reference-srt "/Volumes/photo/22_유튜브영상_개인/[20260209]헤이딜러광고/헤이딜러_최종.srt" --start-sec 0 --duration-sec 180 --keep-artifacts
```

## STT collect-cache readiness validation

When NAS is unavailable and STT collect-cache defaults are under review, use the read-only readiness audit before any production/default claim. This reads existing benchmark artifacts only.

```bash
./venv/bin/python tools/audit_stt_cache_backfill_readiness.py --glob '.codex_work/benchmarks/subtitle_pipeline_variants/*/benchmark_results.json' --output-dir output/manual_verification/latest/stt_cache_backfill_readiness_YYYYMMDD --representative-media '<NAS_HEYDEALER_MP4>' --representative-reference-srt '<NAS_HEYDEALER_SRT>'
```

Focused guards:

```bash
./venv/bin/python -m py_compile tools/audit_stt_cache_backfill_readiness.py tests/test_stt_cache_backfill_readiness.py
QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_stt_cache_backfill_readiness.py tests/test_stage_variance_summary.py
QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_stt_recheck_service.py tests/test_media_processor_overlap.py tests/test_subtitle_engine_settings.py -k "collect_cache or macro_response_cache"
```

The readiness report must keep `stt_recheck_collect_cache_enabled=false` and `stt_primary_collect_cache_enabled=false` by default unless representative real-media cache-write and cache-hit replay evidence both pass the strict final gates. When NAS returns, run the report's generated `preflight`, `cache_write`, `cache_hit`, `accept_write`, `accept_hit`, and `readiness_refresh` commands in order before any owner review.

After timing or tail-collapse fixes, refresh generated-fixture cache-hit evidence with a write run and a hit replay using dedicated STT1, STT2/word, macro, and High-context cache paths. Evaluate both benchmark outputs with `tools/evaluate_reference_benchmark_acceptance.py`; the generated replay is current only if both runs pass strict final gates and the hit replay shows STT1/STT2/word collect cache hit/provider-call `true/false`, macro provider group `0`, final invalid/non-monotonic/overlap `0/0/0`, and global max active `1`. This generated replay still cannot promote collect-cache defaults without representative real-media backfill.

## Real-media latency profiling validation

When diagnosing generation latency, keep three evidence surfaces separate:

- non-profile `verify_full_media_pipeline.py --repeat` runs are the wall-clock speed truth.
- `stage_wall_clock_summary` in verifier and benchmark results is the named-stage elapsed truth for STT1, selective STT2 rescue, word precision, VAD/STT consensus, subtitle postprocess, and High context-boundary pair diagnostics.
- `verify_full_media_pipeline.py --profile-functions` runs are ownership diagnostics only; cProfile cumulative rows are non-additive and can overlap.
- `benchmark_subtitle_pipeline_variants.py --reference-srt` runs are the reference quality and timing truth.

For non-trivial media slices, the verifier fails if final subtitles have invalid duration, non-monotonic order, overlap, or `stable_for_save_reopen=false`. Reference-scored or generated-fixture acceptance must also verify final SRT bounds against the actual media duration, reject sub-0.3s tail fragments, and flag long tail rows; do not treat global canvas duration derived from subtitle `last_end` as a media-duration proof. The summary metrics also expose STT2/word precision counts, global canvas max-active stability, memory pressure, High context-boundary candidate/call/change counts, and generation-owner profile summaries. If the reference media/SRT is unavailable, a non-reference run can prove instrumentation and structural stability only; it must not approve a latency trim that can change subtitle text, timing, segmentation, or LLM/STT decisions.

```bash
QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/verify_reference_fixture_availability.py --fallback-media "output/_audio_fingerprint/헤이딜러_최종_2c274c4ab434764a8546/헤이딜러_최종_cleaned.wav" --output-dir output/manual_verification/latest/reference_fixture_availability_YYYYMMDD
QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/verify_full_media_pipeline.py --media "/Volumes/photo/22_유튜브영상_개인/[20260209]헤이딜러광고/헤이딜러_최종.MP4" --mode high --output-dir output/manual_verification/latest/<artifact> --run-prefix baseline_repeat2 --start-sec 0 --duration-sec 180 --repeat 2
QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/verify_full_media_pipeline.py --media "/Volumes/photo/22_유튜브영상_개인/[20260209]헤이딜러광고/헤이딜러_최종.MP4" --mode high --output-dir output/manual_verification/latest/<artifact> --run-prefix profile_diagnostic --start-sec 0 --duration-sec 180 --profile-functions --profile-top 160
QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/benchmark_subtitle_pipeline_variants.py --suite modes --variants mode_high --media "/Volumes/photo/22_유튜브영상_개인/[20260209]헤이딜러광고/헤이딜러_최종.MP4" --reference-srt "/Volumes/photo/22_유튜브영상_개인/[20260209]헤이딜러광고/헤이딜러_최종.srt" --start-sec 0 --duration-sec 180 --keep-artifacts
```

If a benchmark is slow, compare the slow artifact with the nearest accepted baseline before changing STT policy:

```bash
QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_stt_worker_timeout.py \
  .codex_work/benchmarks/subtitle_pipeline_variants/<baseline_run>/benchmark_results.json \
  .codex_work/benchmarks/subtitle_pipeline_variants/<slow_run>/benchmark_results.json \
  --output-dir output/manual_verification/latest/stt_worker_timeout_compare_YYYYMMDD
```

The timeout audit is read-only. It can justify a worker lifecycle diagnostic or retry plan, but it must not approve model downgrade, STT2/word precision skipping, quality-gate relaxation, collect-cache default promotion, UI changes, or App Store work.

If the long HeyDealer/X5 reference fixture is unavailable, the cached X5 60s rows can be materialized for short-loop reference-scored smoke only. Do not use this as broad trim acceptance.

```bash
QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/materialize_reference_srt.py --reference-json .codex_work/bench/x5_120_3s_180_3s_reference.json --output-srt output/manual_verification/latest/x5_local_reference_fixture_YYYYMMDD/x5_120_3s_180_3s_reference.srt --report-json output/manual_verification/latest/x5_local_reference_fixture_YYYYMMDD/materialized_reference_report.json
QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/verify_reference_fixture_availability.py --media .codex_work/bench/x5_120_3s_180_3s.wav --reference-srt output/manual_verification/latest/x5_local_reference_fixture_YYYYMMDD/x5_120_3s_180_3s_reference.srt --start-sec 0 --duration-sec 60 --output-dir output/manual_verification/latest/x5_local_reference_fixture_YYYYMMDD/preflight
QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/benchmark_subtitle_pipeline_variants.py --suite modes --variants mode_high --media .codex_work/bench/x5_120_3s_180_3s.wav --reference-srt output/manual_verification/latest/x5_local_reference_fixture_YYYYMMDD/x5_120_3s_180_3s_reference.srt --start-sec 0 --duration-sec 60 --keep-artifacts
QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/evaluate_reference_benchmark_acceptance.py .codex_work/benchmarks/subtitle_pipeline_variants/<timestamp>/benchmark_results.json --output-dir output/manual_verification/latest/x5_local_reference_fixture_YYYYMMDD/acceptance
```

For a longer local project-reference smoke, use the cached 180s X5 audio with the semantically aligned `X5_전반` project SRT, then classify acceptance after scoring. The same audio with `X5_후반` SRT is known to be a semantic mismatch and should be rejected.

```bash
QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/verify_reference_fixture_availability.py --media output/_audio_fingerprint/X5_시승기_후반_32346f324ad776ce0fe2/X5_시승기_후반_cleaned.wav --reference-srt projects/X5_시승기_전반.assets/subtitles/final.srt --start-sec 0 --duration-sec 180 --output-dir output/manual_verification/latest/x5_project_reference_180s_YYYYMMDD/preflight_front
QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/benchmark_subtitle_pipeline_variants.py --suite modes --variants mode_high --media output/_audio_fingerprint/X5_시승기_후반_32346f324ad776ce0fe2/X5_시승기_후반_cleaned.wav --reference-srt projects/X5_시승기_전반.assets/subtitles/final.srt --start-sec 0 --duration-sec 180 --keep-artifacts
QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/evaluate_reference_benchmark_acceptance.py .codex_work/benchmarks/subtitle_pipeline_variants/<timestamp>/benchmark_results.json --output-dir output/manual_verification/latest/x5_project_reference_180s_YYYYMMDD/acceptance_front
```

## Mac App Store readiness audit

App Store readiness checks must stay separate from normal source-app pytest/QA. The audit below is non-destructive: it does not build, sign, notarize, upload, or create a DMG.

```bash
QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_app_store_readiness.py --output-dir output/manual_verification/latest/app_store_readiness_audit_YYYYMMDD
QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_app_store_readiness_audit.py
```

Do not claim App Store submission readiness unless the audit and separate artifacts prove a signed sandboxed `.app`, strict `codesign` validation, signed App Store `.pkg`, package signature check, sandbox smoke, App Store Connect validation output, and owner-approved App Store Connect metadata. The non-code metadata gate must itemize privacy policy URL, App Privacy answers, export compliance, screenshots, support URL, app review notes, age rating, and release notes with `status`, `draft`, `owner_decision_required`, and `acceptance_gate` fields.

## PyQt / offscreen UI validation

PyQt UI 회귀는 화면 서버에 의존하지 않는 경로를 우선 사용합니다.

```bash
QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_video_player_widget.py tests/test_timeline_playhead_fit.py
```

실행 중 앱 확인이 필요하면 저장소 도구를 사용합니다.

```bash
./venv/bin/python tools/appctl.py status
```

편집기 타임라인 확대/축소/맞춤 자동화 smoke가 필요하면 source app에서 프로젝트를 연 뒤 아래 명령을 사용합니다.

```bash
./venv/bin/python tools/appctl.py editor-timeline-view zoom-in
./venv/bin/python tools/appctl.py editor-timeline-view zoom-out
./venv/bin/python tools/appctl.py editor-timeline-view fit
./venv/bin/python tools/appctl.py editor-timeline-view time-window
./venv/bin/python tools/appctl.py editor-timeline-view max
```

자막자석은 실제 자막 타이밍을 바꿀 수 있으므로 기본 quick smoke에는 넣지 말고, 명시 검증 artifact를 만들 때만 아래 명령을 사용합니다.

```bash
./venv/bin/python tools/appctl.py editor-subtitle-magnet
```

편집기 하단 전역 메뉴 버튼의 안전한 smoke는 아래처럼 확인합니다. `global-menu-status`는 전체 등록 버튼을 조회하고, `global-menu-action`은 설정/화자/사전/저장/비디오/음성처럼 자동화-safe 버튼만 허용합니다.

```bash
./venv/bin/python tools/appctl.py global-menu-status
./venv/bin/python tools/appctl.py global-menu-action settings
./venv/bin/python tools/appctl.py global-menu-action speaker
./venv/bin/python tools/appctl.py global-menu-action dictionary
./venv/bin/python tools/appctl.py global-menu-action save
./venv/bin/python tools/appctl.py global-menu-action video
./venv/bin/python tools/appctl.py global-menu-action stt
```

roughcut 영상 렌더와 exact-join sidecar smoke가 필요하면 source app에서 roughcut 프로젝트를 연 뒤 아래 순서로 확인합니다.

```bash
./venv/bin/python tools/appctl.py open-project projects/codex_live_roughcut_export_chain_20260623.aissproj
./venv/bin/python tools/appctl.py open-roughcut
./venv/bin/python tools/appctl.py roughcut-export-srt output/manual_verification/latest/<artifact>/exports/app_command_render.srt
./venv/bin/python tools/appctl.py roughcut-render-video output/manual_verification/latest/<artifact>/exports/app_command_render.mov
./venv/bin/python tools/appctl.py open-srt output/manual_verification/latest/<artifact>/exports/app_command_render.srt
```

실제 미디어 기반 smoke 또는 수동 검증은 요청 범위가 클 때만 사용합니다.

```bash
./venv/bin/python tools/verify_full_media_pipeline.py --help
```

## Docs validation

문서 작업 후에는 링크와 필수 문서 존재 여부를 최소한 확인합니다.

```bash
find docs -maxdepth 2 -type f | sort
rg -n "## AI agent read order|## Before coding|## Temporary working memory" docs/README.md
rg -n "^# Project State|^# Feature Registry|^# Architecture|^# Validation Guide|^# Handoff" docs/*.md
```

## Git diff review

항상 아래 세 가지를 확인합니다.

```bash
git status --short
git diff --stat
git diff
```

## Whitespace check

텍스트와 코드 모두 trailing whitespace, patch corruption을 막기 위해 아래 검사를 사용합니다.

```bash
git diff --check -- .
```

## Forbidden root-file scan

요청되지 않은 루트 파일 추가를 막기 위해 루트 레벨 파일 변화를 확인합니다.

```bash
find . -maxdepth 1 -type f | sort
git status --short
```

새 루트 파일이 필요했다면 요청과 이 문서에 맞는지 다시 확인합니다.

## Handoff check

의미 있는 작업을 마칠 때는 아래를 확인합니다.

- `docs/HANDOFF.md`가 이번 세션 상태를 반영하는지
- 변경으로 인해 `docs/PROJECT_STATE.md`, `docs/FEATURE_REGISTRY.md`, `docs/ARCHITECTURE.md`, `docs/VALIDATION.md` 중 갱신이 필요한 파일이 빠지지 않았는지
- `ACTION_ITEMS.md`와 현재 작업 상태가 충돌하지 않는지

## Minimum validation before claiming completion

문서 전용 작업의 최소 완료선은 아래입니다.

- `git status --short` 확인
- `git diff --stat` 확인
- `git diff` 확인
- `git diff --check -- .` 통과 확인
- `docs/README.md`에서 새 문서들이 read order와 역할 설명에 연결되어 있는지 확인
- `docs/HANDOFF.md`가 업데이트되었는지 확인
- 코드 파일을 건드렸다면 안전한 syntax/import 검증을 추가 실행

코드 변경이 포함된 작업이라면 위 최소선에 더해 owner 기능의 targeted pytest 또는 QA runner를 반드시 붙여야 합니다.
