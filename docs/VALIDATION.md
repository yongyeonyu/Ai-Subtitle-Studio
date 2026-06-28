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
AI_SUBTITLE_STUDIO_CUT_BOUNDARY_EXPECT="2766,2677" \
AI_SUBTITLE_STUDIO_CUT_BOUNDARY_PIPE_MAX_FPS="60" \
QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_cut_boundary_fixture_2766_2677.py

QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/verify_cut_boundary_source_fps_scout.py \
  "/Users/u_mo_c/Library/Mobile Documents/com~apple~CloudDocs/AI_EDIT/내 프로젝트 (3).MP4" \
  --pairs 2765:2766,2676:2677 \
  --pipe-max-fps 60 \
  --fps-override 60000/1001 \
  --allow-metadata-only \
  --probe-timeout-sec 5 \
  --output-dir output/manual_verification/latest/nle_fixed_cut_boundary_fixture_gate_YYYYMMDD
```

This verifier records whether target frames `2766` and `2677` are newly detected or at least preserved on the exact source-fps frame grid. If `candidate_detected=false`, report that as a remaining false-negative tuning risk even when `frame_preserved=true`. The `--allow-metadata-only` path is allowed only when decoder access to the fixed fixture stalls; it proves frame-grid preservation and split/snap guardability, not visual cut detection.

## Preview frame cache validation

Preview/skimming cache changes should prove temp-workspace cache lookup, nonblocking preview seek behavior, and unchanged timeline scrub routing.

```bash
./venv/bin/python -m py_compile core/runtime/temp_workspace.py core/runtime/preview_frame_cache.py ui/editor/video_player_widget.py ui/editor/video_player_surface.py tests/test_preview_frame_cache.py tests/test_video_player_widget.py
QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_preview_frame_cache.py tests/test_video_player_widget.py -k "preview_frame_cache or preview_seek or processing_thumbnail"
QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py -k "scrub_updates_playhead_immediately_and_uses_lightweight_preview_seek or scrub_throttles_video_seek_during_fast_mouse_moves or timing_drag_preview_updates_playhead_and_uses_lightweight_preview_seek or auto_cut_boundary_preview_moves_playhead_without_thumbnail_work"
```

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

The persistence cutover audit must also report provisional `marker_edit` save/reopen preservation plus render/export parity before any future persisted NLE format proposal: all 11 current dual-write operation families pass, marker rows are preserved after reopen, stable `source_subtitles`, `final_overlay`, `global_canvas`, `roughcut_sidecar`, and `exported_assets` surfaces; final invalid/non-monotonic/overlap `0/0/0`; global max active `1`; and disk storage clean of unapproved NLE runtime fields.

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
