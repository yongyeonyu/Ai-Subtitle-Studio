# Performance Ideas And Execution Plan

이 파일은 성능 아이디어, 이전 action/native queue, 실행 순서, QA 게이트를 합친 단일 실행 원천이다.
사용자가 `아이디어 전부 실행해`라고 말하면 이 문서의 순서대로 진행한다.

## Hard Rules

- 자막 품질이 속도보다 우선이다.
- UI/UX는 명시 요청 없이 변경하지 않는다.
- 모델 축소, STT2 생략, LLM 생략, 품질 게이트 완화는 기본 최적화 후보가 아니다.
- Apple Silicon에서는 Apple Neural Engine, 즉 `ANE` 기준으로 표현한다. Core ML이 ANE/GPU/CPU 배치를 결정하고, Metal/MLX/whisper.cpp는 주로 GPU/CPU 경로로 검증한다.
- PyTorch MPS는 과거 `metal gpu stream` crash 근거가 있으므로 production default가 아니라 격리 실험 후보로만 둔다.
- native 승격은 Swift/C++가 Python과 parity를 갖고 real fixture에서 같거나 빠를 때만 한다.
- live Qt widget, mutable editor state, subprocess orchestration, model-worker ownership, UI callback은 native로 통째 이전하지 않는다.
- 자막 에디터 상호작용 표면은 2D-only이다. 자막 본문 편집, 자막 세그먼트 편집/생성/삭제, 플레이헤드 이동, 컷 경계, 다이아몬드, waveform/minimap 렌더링에 3D view, QML SceneGraph, OpenGL/Metal-backed UI surface를 새 default로 도입하지 않는다.
- 전체 앱 shell, 메뉴, 팝업, 다이얼로그의 새 UI 기본값은 `Qt Widgets`로 고정한다. QML은 새 UI default에서 제외하고, Metal은 UI renderer가 아니라 native compute 후보로만 검토한다.
- 아이디어 발굴 또는 실행 전 `waste_action_item.md`와 `lesson_n_learned.md`를 먼저 읽고, 폐기된 아이디어를 새 근거 없이 반복하지 않는다.
- 실패/무효 후보는 `waste_action_item.md`에 hypothesis, change, metrics, quality, artifact, rejection reason을 남긴다.
- 반복하면 안 되는 진단/실험/운영 실수는 `lesson_n_learned.md`에 남긴다.
- 정상 완료된 idea/action/native item은 이 파일에서 삭제한다. 완료 이력은 필요할 때만 `test_result.md`, release note, `output/manual_verification/latest/`, `waste_action_item.md`, 또는 `lesson_n_learned.md`에 남긴다.

## Current Baseline Notes

- 유지 후보: `candidate1`
- 유지 이유: subtitle quality를 유지하면서 X5 평균 시간이 가장 안정적이었다.
- 최신 실행 브랜치: `opt/one-shot-quality-speed-20260521-0228`
- 최신 완료 배치: 2D rendering ownership inventory + automation command QA hardening
- 최신 산출물: `output/manual_verification/latest/qa_suite_quick_20260521_111623`
- 최신 검증:
  - rendering ownership audit 확장: subtitle text QML overlay, video control bar QML, video subtitle QML, timeline scenegraph layer가 explicit diagnostic/scenegraph gate 뒤에 있는지 검사.
  - paint ordering audit 확장: subtitle score -> diamond -> shadow/drag-shadow playhead -> final playhead handle 순서 고정 검사.
  - `tools/audit_editor_rendering_ownership.py --json`: `ok=true` with 15-owner inventory
  - `tests.test_editor_rendering_ownership_audit`: `2 tests OK`
  - `tools/qa_suite_runner.py quick`: `failed_count=0`, artifact `output/manual_verification/latest/qa_suite_quick_20260521_111623`
  - automation-4 검토 항목 재분류/수정: smart split precondition fallback, status UDP compact/minimal fallback, snapshot/export artifact existence check, app runner diamond fallback.
  - `tests.test_app_command_server`, `tests.test_app_command_bridge`, `tests.test_qa_suite_runner`: `73 tests OK`
  - `tests/test_editor_automation.py tests/test_remote_verify_actions.py`: `8 passed`
  - `tools/check_maintenance_budget.py --json`: `ok=true`
  - `tools/qa_suite_runner.py major`: `failed_count=0`, artifact `output/manual_verification/latest/qa_suite_major_20260521_110523`
  - `tools/qa_suite_runner.py full`: `failed_count=0`, artifact `output/manual_verification/latest/qa_suite_full_20260521_110628`
  - `tools/audit_editor_rendering_ownership.py --json`: `ok=true` with TimelineCanvas/GlobalCanvas/TimelineWidget/PaintMixin/PaintPassPlanner/InputHitTargets/WaveformSource/STTPreviewLaneLayout/InlineTextEdit/GpuRenderingGate inventory
  - `tests.test_editor_rendering_ownership_audit`: `2 tests OK`
  - `tools/qa_suite_runner.py major`: `failed_count=0`, artifact `output/manual_verification/latest/qa_suite_major_20260521_102240`
  - `tools/qa_suite_runner.py full`: `failed_count=0`, artifact `output/manual_verification/latest/qa_suite_full_20260521_102341`
  - spoken `full_media` verifier: raw/final subtitle가 0개인 non-trivial slice는 더 이상 pass 처리하지 않는다.
  - app runner bootstrap: bundled Python main process(`dist/macos/AI Subtitle Studio.app/Contents/Resources/app/main.py`)와 zombie/종료 중 PID를 구분한다.
  - editor automation: smart split 중 layout/media refresh가 inline edit focus를 훔쳐도 마지막 inline edit request를 복구한다.
  - `tests.test_action_item_runtime_services`, `tests.test_project_runtime_capture`, `tests.test_runtime_multi_process`, `tests.test_media_processor_overlap`, `tests.test_ollama_provider`, `tests.test_timeline_hit_targets`, `tests.test_timeline_render_cache`: `248 tests OK`
  - `tools/check_maintenance_budget.py --json`: `ok=true`
  - `tools/qa_suite_runner.py quick`: `failed_count=0`, artifact `output/manual_verification/latest/qa_suite_quick_20260521_082403`
  - `tools/qa_suite_runner.py major`: `failed_count=0`, artifact `output/manual_verification/latest/qa_suite_major_20260521_082424`
  - `tools/qa_suite_runner.py full`: `failed_count=0`, artifact `output/manual_verification/latest/qa_suite_full_20260521_082856`
- 최신 측정:
  - Macau fast smoke: total `8.064s`, pipeline `7.556s`, final/raw `5/3`, peak RSS `370835456`, stage trim failure `0`
  - X5 60s modes: `mode_high_piecewise_drift` quality winner `40.920s`, quality `72.989`, readability `94.568`, timing MAE `0.6455`
  - X5 60s speed/quality tradeoff: `mode_fast` `9.809s`, quality `71.514`, readability `93.057`, timing MAE `0.7347`
  - X5 60s full-parallel STT: `10.387~10.625s`로 빠르지만 quality `71.563`, timing MAE `0.7392`, final `17`이라 High 기본값 승격 폐기
  - X5 60s quality-gated rerun: `.codex_work/benchmarks/subtitle_pipeline_variants/20260521_084657/benchmark_quality_gate.md`
  - Macau fast repeat10: pipeline avg/min/max `7.628s/7.516s/7.854s`, final segment `5` 유지
  - X5 modes repeat10: `mode_fast` avg `10.373s` but gate `0/10`; `mode_high_piecewise_drift` avg `47.811s`, quality `72.989`, gate `10/10`
  - Swift/native policy corrected mini benchmark: parity pass, but Swift helper speedup `< 1.0`; adoption은 `python_*_preferred`
  - Tinyping fast 60s: total `22.326s`, pipeline `9.804s`, final/raw `18/15`
  - Tinyping auto 60s: total `44.152s`, pipeline `9.833s`, final/raw `18/15`
  - Tinyping high 60s: total `19.526s`, pipeline `19.431s`, final/raw `16/16`
  - Latest full QA Tinyping fast/auto/high 60s: pipeline `9.843s/10.523s/25.465s`, total `22.229s/43.163s/25.561s`, peak RSS `431652864/761839616/813219840`, final/raw `18/15`, `18/15`, `16/16`
- 현재 선택:
  - 기존 `candidate1` 품질 보존 파이프라인을 유지한다.
  - 이번 배치의 stage-owned STT/LLM resource policy, quarter prescan metadata, opaque 2D inline editor 안정화는 채택한다.
  - 에디터/타임라인 UI 렌더링 기본값은 Qt Widgets/QPainter 2D로 고정하고, QML/SceneGraph는 explicit opt-in diagnostic으로만 둔다.
  - X5 60s에서 품질 단독 1위는 `mode_high_piecewise_drift`, 속도/품질 균형은 `mode_fast`가 유리하다. 단, 10회 반복 평균/p95 전까지 기본 알고리즘 자동 승격은 하지 않는다.
  - 전체 STT1/STT2 full-parallel은 빠르지만 X5 품질과 segment count가 낮아져 기본 승격하지 않는다.
  - benchmark 후보 선택은 `tools/apply_subtitle_benchmark_quality_gate.py`로 품질 gate를 통과한 후보만 승격한다.
  - X5 10회 기준 자막 품질을 유지하는 최종 후보는 `mode_high_piecewise_drift`이다. `mode_fast`는 속도 후보로는 유효하지만 품질 동일 조건의 최종 알고리즘 후보에서는 제외한다.
  - Swift/native policy helper는 parity를 맞췄지만 현재 synthetic 500-doc benchmark에서 Python보다 느려 기본값으로 승격하지 않는다.
  - aggressive quarter-parallel STT/LLM, native deterministic batch 승격은 parity 구현과 X5/Tinyping 반복 품질 게이트 전까지 채택하지 않는다.
- 이전 현재 기준:
  - Macau avg `6.770`, min `6.604`, max `7.240`
  - X5 avg `61.252`, min `60.705`, max `62.201`
  - artifact: `output/manual_verification/latest/20260520_perf_cycle2_candidate1`
- 폐기 후보:
  - `candidate2`: `cut_prescan_done cleanup=True` 제거. X5 평균 악화.
  - `candidate3`: `subtitle_optimize_done warning-stage GPU trim` 제거. 짧은 Macau만 일부 이득, X5 평균 악화.
- 폐기 상세는 `waste_action_item.md`를 기준으로 한다.

## Fixtures

- Macau quick/smoke: `/Users/u_mo_c/Downloads/마카오테스트/DJI_20260217225132_0079_D.MP4`
- X5 accuracy: `test video/X5_시승기_후반.MP4` + sibling `.srt`
- Tinyping long-flow: `/Users/u_mo_c/Downloads/티니핑/티니핑_유스어드벤처.MP4`
- Artifact root: `output/manual_verification/latest/idea_full_execute_<timestamp>/`

## One-Shot Execution Order

### Phase 2. Canonical State Ownership

Goal:
- STT/LLM 병렬화 전에 editor, project, queue가 같은 canonical state를 보게 만든다.

Work:
- Editor session model: subtitle, STT evidence, preview rows, final rows, voice activity, project-save views.
- Project session service: create/open/save/reopen/linked-SRT lifecycle.
- Queue state model: queue table/sidebar/top-card/backend progress emit.
- Lazy hydration: candidate lattice, preview rows, quality payload, optional STT tracks는 필요한 lane/panel/save path에서만 materialize.

Quality/UX gate:
- UI layout, labels, colors, menu, shortcuts, popup behavior 변경 금지.
- final subtitle output과 project JSON contract 유지.

QA:
- project open/save/reopen tests.
- queue/sidebar tests.
- Tinyping project-open smoke.
- Macau project smoke.
- `./venv/bin/python tools/qa_suite_runner.py major`

Commit:
- `refactor: add canonical editor project and queue state services`

### Phase 3. Audio/STT Services And Stage-Owned Memory

Goal:
- 쓸 때만 확보하고, 다음 stage에서 쓰지 않으면 즉시 release하는 ownership을 만든다.

Work:
- audio extraction, chunking, transcription, VAD, cache decision, worker pooling, retry, cleanup을 durable services로 분리.
- WhisperKit, MLX, whisper.cpp, Ollama, audio chunks, proxy frames, candidate lattice, word timestamp payload에 ownership policy 추가.
- `pressure_stage=normal`: warm reuse 허용.
- `pressure_stage=warning`: LLM/STT2 warm 폭 축소.
- `pressure_stage=critical`: immediate release.
- release 시점이 `stt_transcribe_chunk`, `subtitle_optimize_done`, `save_export_done` 전후 어디인지 artifact로 기록.
- Swift runtime cache cleanup 호출 수와 elapsed 중복 제거.

2026-05-21 partial done:
- `StageOwnedResourcePolicy`를 공용 audio runtime service로 추가하고 STT collect worker reuse, STT warm worker, Ollama keep-alive/warmup 정책이 같은 pressure-stage 판단을 보게 했다.
- critical stage에서는 STT collect worker 재사용 금지, warm worker release, LLM residency 해제를 같은 policy로 결정한다.
- host memory 상태에 흔들리지 않도록 관련 unit test는 normal/critical snapshot을 명시한다.

QA:
- `tests.test_media_processor_overlap`
- `tests.test_runtime_memory_manager`
- audio/STT targeted tests.
- repeated Macau 10회.
- X5 10회.
- residual process snapshot.

Commit:
- `perf: make audio stt resources stage owned`

### Phase 4. Apple Silicon Parallel Pipeline

Goal:
- 동일 품질을 유지한 채 CPU/GPU/ANE 자원 사용률을 높인다.

Work:
- STT1: WhisperKit/Core ML persistent worker 유지.
- STT2 matrix:
  - MLX Whisper worker.
  - whisper.cpp Metal.
  - whisper.cpp Core ML encoder + Metal decoder.
  - whisper.cpp CPU/Accelerate fallback.
- STT1/STT2 per-worker chunk workspace 분리로 cleanup race 방지.
- cut-boundary prescan을 1/4 quarter로 나누고, quarter 완료 즉시 audio/STT 준비 시작.
- quarter 1 STT 후보가 준비되면 quarter 2 STT 중 quarter 1 LLM cleanup/rerank를 provisional로 선행 처리.
- final commit barrier 유지: 전체 timing/gap/final pass는 기존 순서로 확정.
- VAD는 torch/MPS 위험을 피하고 Core ML/ONNX/ANE 또는 stable CPU path로 격리.
- resource scheduler가 CPU/GPU/ANE/memory pressure를 보고 STT2/LLM parallel width를 조절.

2026-05-21 partial done:
- cut-boundary 1/4 quarter plan metadata와 Apple M runtime plan flag를 추가했다.
- 아직 STT/LLM quarter-overlap execution은 켜지지 않았다. 품질 barrier와 X5/Tinyping 반복 검증 전까지 계획/계측 단계로 둔다.

Quality gate:
- X5 reference accuracy가 baseline보다 나빠지면 폐기.
- final text/timing drift가 생기면 폐기.
- quarter boundary gap/split regression이 생기면 폐기.
- `pressure_stage=critical` 빈도가 늘면 폐기.

QA:
- STT ensemble/lattice/recheck tests.
- cut-boundary tests.
- LLM provider/cache parity tests.
- X5 accuracy slice 3회.
- Tinyping 60s fast/auto/high.
- `./venv/bin/python tools/qa_suite_runner.py major`

Commit:
- `perf: add guarded parallel stt llm quarter pipeline`

### Phase 5. Native Deterministic Batch Promotion

Goal:
- 모델 자체가 아니라 deterministic hot loop와 large-batch transform만 native로 승격한다.

Work:
- media-info normalization/cache-key shaping Swift benchmark.
- cut-boundary color/gray/delta/alignment scoring, dense frame comparison, boundary-candidate numeric reduction Swift/C++ batch 후보.
- `stt_candidate_scorer`, `stt_lattice`, `subtitle_accuracy_pipeline`, `subtitle_timing`, `word_resegmenter` batch bridge 후보.
- `NativePolicyEngine.swift`를 scoring/retrieval/decision 책임으로 분리.
- Python fallback과 row-level parity test 유지.

2026-05-21 partial done:
- Swift/native policy benchmark의 adoption 판정을 parity-aware로 수정했다.
- Swift policy benchmark 설정에 experimental gate를 명시해 실제 Swift helper를 측정하도록 고쳤다.
- LoRA native scoring tie-break를 `retrieval_score -> quality -> docIndex`로 고정해 Python 상위 순서와 맞췄다.
- corrected benchmark에서 LLM/deep/batch/LoRA top5 parity는 통과했지만 Swift helper가 Python보다 느려 `python_*_preferred`로 유지했다.
- native policy helper는 계속 실험 후보이며, production/default 승격은 row-level parity와 speedup이 동시에 통과한 뒤에만 한다.

Stop rules:
- live Qt object, mutable editor state, subprocess orchestration, model-worker ownership, UI callback은 native로 이동하지 않는다.
- small payload가 bridge overhead 때문에 느리면 Python 유지.

QA:
- `swift test` in `native/macos/AIStudioNative`.
- native bridge parity tests.
- X5 accuracy slice.
- Macau visual smoke.
- `./venv/bin/python tools/qa_suite_runner.py full`

Commit:
- `native: batch deterministic subtitle and boundary loops`

### Phase 5.5. Mac-Native 2D Timeline And Editor Rendering Rewrite

Decision:
- 전체 앱 shell은 `Qt Widgets`를 기본값으로 한다.
- 메뉴, 팝업, 다이얼로그도 `Qt Widgets`를 기본값으로 유지한다.
- 자막 에디터 편집, 자막 세그먼트 편집/생성/삭제, 플레이헤드 이동, 컷 경계/다이아몬드, waveform/minimap은 모두 2D-only로 간다.
- 타임라인, 미니맵, waveform, playhead, shadow playhead, cut diamond는 `QPainter` 단일 paint owner가 그린다.
- 자막 세그먼트 편집은 opaque `QWidget` 또는 canvas-owned 2D editor로만 구현한다.
- 이 앱의 에디터에는 3D가 없다. QML SceneGraph, OpenGL view, Metal-backed editor surface, SwiftUI/Metal timeline renderer는 default 후보가 아니다.
- QML은 새 UI 기본값에서 제외한다.
- Metal은 UI가 아니라 native compute 후보로만 사용한다.
- macOS에서 가장 가볍고 예측 가능한 기본 경로는 `Qt Widgets + QWidget + QPainter + opaque child widgets`이다. Qt가 macOS native window/compositor 위에서 2D raster paint를 담당하게 하고, Python은 상태 계산/이벤트 라우팅만 맡긴다.

Already done:
- 2026-05-21 1차 구현 완료: 메인 타임라인과 미니맵을 `QWidget + QPainter` 2D 단일 렌더러로 고정했다.
- 완료 범위: `TimelineCanvasBase` / `GlobalCanvasBase`를 QWidget 경로로 고정, timeline render backend `qwidget-2d` 기록, scenegraph/QML timeline body 비활성화, playhead overlay는 상태 호환 객체로만 유지하고 실제 렌더링은 canvas paint pass로 단일화, playhead/shadow/active dirty update는 full canvas repaint로 전환.
- 완료 검증: `tests.test_timeline_hit_targets`, `tests.test_timeline_playhead_fit`, `tests.test_timeline_render_cache`.
- 2026-05-21 2차 구현 완료: 자막 세그먼트 인라인 편집기를 opaque `QWidget`으로 분리하고, segment fill과 같은 배경을 가진 단일 child editor로 고정했다.
- 완료 범위: 투명 child editor를 제거하고, 편집 중 canvas segment text와 editor text가 겹쳐 그려지지 않도록 geometry/style sync path를 정리했다.
- 완료 검증: `tests.test_timeline_hit_targets`, `tests.test_timeline_render_cache`, 공식 `quick/major/full` QA.
- 2026-05-21 3차 구현 완료: `ui.gpu_rendering`의 SceneGraph 기본값을 off로 바꾸고, legacy settings의 `editor_rendering_scenegraph_enabled=true`가 새 opt-in flag 없이 QML UI를 되살리지 못하게 했다.
- 완료 범위: timeline/project renderer metadata를 `timeline-qwidget-2d`로 정리, runtime optimization editor backend를 `qwidget_2d`로 갱신, custom/default settings에서 OpenGL/SceneGraph 기본값을 off로 정리.
- 완료 검증: `tests.test_gpu_rendering`, `tests.test_project_context`, `tests.test_timeline_render_cache`, 관련 runtime/native tests.
- 2026-05-21 4차 구현 완료: `tools/audit_editor_rendering_ownership.py`를 추가해 TimelineCanvas/GlobalCanvas/TimelineWidget/PaintMixin/inline editor/GPU gate가 qwidget-2d owner 원칙을 어기면 실패하도록 했다.
- 완료 검증: `tools/audit_editor_rendering_ownership.py --json`, `tests.test_editor_rendering_ownership_audit`.
- 2026-05-21 5차 구현 완료: 렌더링 inventory 가드를 segment text painter, cut diamond, shadow playhead, STT preview lane planner, waveform data source, timeline input hit target까지 확대했다.
- 완료 검증: `tools/audit_editor_rendering_ownership.py --json`, `tests.test_editor_rendering_ownership_audit`, 공식 `full` QA `output/manual_verification/latest/qa_suite_full_20260521_102341`.
- 2026-05-21 6차 구현 완료: `full_media` verifier가 spoken slice의 `raw/final=0/0`을 pass로 오판하지 않게 막고, bundled app process 재시작 감지와 editor inline automation 복구를 추가했다.
- 완료 검증: `tests.test_qa_suite_runner`, `tests.test_verify_full_media_pipeline`, `tests.test_editor_automation`, 공식 `major/full` QA.
- 2026-05-21 7차 구현 완료: single-owner 2D에서 playhead/shadow/drag-shadow/dirty update가 full canvas repaint를 유지하는 audit를 추가했다.
- 완료 범위: `TimelineSingleOwnerPlayheadInvalidation` inventory로 플레이헤드 잔상 방지 경로를 고정하고, `dirty-rect band repaint`는 실제 visual proof 전까지 default로 되돌리지 않도록 가드했다.
- 완료 검증: `tests.test_editor_rendering_ownership_audit`, `tests.test_timeline_render_cache`, `tools/audit_editor_rendering_ownership.py --json`.

Remaining follow-up:
- 모든 에디터 paint는 single 2D owner 원칙으로 정리한다. 같은 시각 요소를 QML overlay, child widget, scenegraph, canvas paint가 동시에 그리지 않게 한다.
- playhead, shadow playhead, selected segment, hover handle, cut diamond는 한 paint pass에서 z-order를 고정한다. 클릭/드래그/키보드 이동은 색상/모드를 렌더러가 재해석하지 않고 canonical state만 읽는다.
- 성능은 2D 단일 owner를 유지한 상태에서만 최적화한다: pre-rendered waveform pixmap/cache, `QStaticText`/text layout cache, devicePixelRatio-aware backing pixmap을 순서대로 측정한다. playhead-only dirty-rect band repaint는 잔상 방지 visual proof가 있을 때만 별도 실험으로 다시 연다.
- 실제 Macau project/app visual smoke로 재생, 스크럽, 확대/축소, inline 편집, 자막 드래그, 자막 생성 후 잔상 여부를 스냅샷으로 확인한다.

Quality/UX gate:
- 색상, 위치, 라벨, 단축키, hit target, menu behavior는 계속 유지한다.
- 화면 변경은 잔상 제거, paint ordering 안정화, macOS compositing 안정화에 한정한다.
- STT/final subtitle text, timing, project save/load schema, LLM cleanup 결과는 절대 변경하지 않는다.

Waste rule:
- QML SceneGraph, OpenGL/Metal-backed UI renderer, SwiftUI/Metal timeline renderer, 3D/canvas hybrid renderer가 검은 surface, stale overlay, input focus regression, frame pacing 악화, UI diff, subtitle-quality drift를 만들면 `waste_action_item.md`에 기록하고 default 승격하지 않는다.
- "더 빠를 것 같아서 GPU/Metal UI surface로 바꾸기"는 측정 전 기본 후보가 아니며, 에디터 상호작용 기본 경로로 채택하지 않는다.

QA:
- `./venv/bin/python -m unittest tests.test_timeline_hit_targets tests.test_timeline_playhead_fit tests.test_timeline_render_cache -q`
- inline editor targeted tests.
- Macau app visual smoke snapshot: playback, scrub, click-move playhead, left/right/up/down playhead mode, segment create/edit/drag/delete, zoom in/out.
- If render ownership changes command surface or bundle behavior, rebuild bundle and run `./venv/bin/python tools/qa_suite_runner.py major`.

Commit:
- `refactor: enforce mac native 2d editor rendering`

### Phase 6. Code Review, Logging, Stale Wiring

Goal:
- 전문 개발자 관점의 코드 리뷰 뒤, 품질 테스트 관점으로 다시 리뷰한다.

Work:
- touched high-risk UI/runtime/audio/project/cut-boundary paths의 broad silent catch를 typed nonfatal logging으로 교체.
- high-confidence unused Python functions, stale QML property bindings, duplicate native cut-boundary paths, dynamic Qt signal wiring 제거 또는 기록.
- 삭제는 static/dynamic wiring 확인 뒤에만 한다.
- 코드 리뷰 persona: Apple Silicon/macOS senior developer.
- QA 리뷰 persona: 꼼꼼한 품질 테스트 엔지니어.

Already done:
- 2026-05-21 1차 구현 완료: 타임라인 viewport clip fallback과 voice-activity lane refresh 실패를 silent fallback에서 one-shot nonfatal warning + 기존 복구 동작으로 바꿨다.
- 완료 범위: 예외 시 전체 repaint 또는 빈 lane 복구는 유지하고, 실패 원인만 `timeline` stage WARN 로그로 남긴다.
- 완료 검증: `tests.test_timeline_render_cache`, `tests.test_editor_rendering_ownership_audit`, `tools/check_maintenance_budget.py --json`, 공식 `quick` QA `output/manual_verification/latest/qa_suite_quick_20260521_113130`.

QA:
- `tools/check_maintenance_budget.py --json`
- targeted symbol scan.
- QML/offscreen smoke where applicable.
- touched test modules.

Commit:
- `chore: clean stale runtime wiring after performance work`

### Phase 7. Help Manual And QA Mapping

Goal:
- 최종 구조가 안정된 뒤 도움말과 QA matrix를 맞춘다.

Work:
- Help order: `기초 사용 -> 편집/캔버스 -> 메뉴/고급 기능 -> 저장/출력 -> 문제 확인`.
- 홈, 프로젝트/미디어/SRT 열기, 자막 생성, roughcut, 비디오/캔버스/타임라인, segment edit, menu/popup, save/export, speaker/STT/LoRA 흐름의 owner file/function matrix.
- 각 장마다 `quick`, `major`, `full` 책임 profile과 snapshot/artifact 경로 연결.
- 새 UX/명령이 생겼으면 `test_case.md`, `tools/qa_suite_runner.py`, `tests/test_qa_suite_runner.py`, `README.md`를 함께 갱신.

QA:
- `./venv/bin/python tools/qa_suite_runner.py quick`
- `./venv/bin/python tools/qa_suite_runner.py major`
- changed runner tests.

Commit:
- `docs: map help chapters to qa coverage`

### Phase 8. Final Benchmark, Full QA, Selection

Goal:
- 가장 빠른 후보가 아니라 속도와 품질이 함께 가장 좋은 알고리즘을 선택한다.

Work:
- baseline 대비 성능/품질 표 작성.
- 후보 ranking은 `benchmark_results.json` 원본 순위와 별개로 `tools/apply_subtitle_benchmark_quality_gate.py`를 통과한 결과만 최종 선택 대상으로 삼는다.
- 채택 후보는 `idea_item.md`에 정리.
- 폐기 후보는 `waste_action_item.md`에 정리.
- 반복 금지 lesson은 `lesson_n_learned.md`에 정리.
- 정상 완료된 실행 항목은 `idea_item.md`, `ACTION_ITEMS.md`, `NATIVE_LIB_PLAN.md`에서 삭제한다.
- App Store Connect upload blocker와 future iPadOS reuse는 blocked/future lane으로만 기록.

Mandatory QA:
- `./venv/bin/python tools/qa_suite_runner.py quick`
- `./venv/bin/python tools/qa_suite_runner.py major`
- `./venv/bin/python tools/qa_suite_runner.py full`
- Macau benchmark 10회.
- X5 benchmark 10회 + reference accuracy.
- Tinyping 60s fast/auto/high.
- 가능하면 Tinyping long high 1회.
- UI snapshot diff: 의도하지 않은 UI/UX diff 0.

Final artifacts:
- `output/manual_verification/latest/idea_full_execute_<timestamp>/summary.md`
- `idea_item.md` performance table and chosen algorithm.
- `waste_action_item.md` rejected attempts.
- `lesson_n_learned.md` repeat-prevention lessons.

Commit/push:
- Phase commits are allowed inside the execution branch.
- Push only when the owner explicitly asks.

## Final Selection Criteria

1. Baseline 대비 average와 p95가 모두 개선된다.
2. X5/Tinyping quality metric이 baseline보다 나빠지지 않는다.
3. final subtitle text/timing drift가 없거나 quality metric이 더 좋다.
4. `pressure_stage=critical` 빈도가 늘지 않는다.
5. residual STT/LLM worker가 다음 run을 느리게 만들지 않는다.
6. app-command `status/ping/guided-subtitle-status`가 busy generation/save/export 중에도 관측 가능하다.
7. UI/UX는 요청 없이 바뀌지 않는다.
