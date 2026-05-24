<!--
Document-Version: 04.00.14-mac-native
Phase: MAC_NATIVE_APPSTORE_V4_0_14_RELEASED
Last-Updated: 2026-05-24
Updated-By: Codex
Purpose: Consolidated active execution queue. Former `idea_item.md` and `NATIVE_LIB_PLAN.md` content lives here.
-->
# ACTION_ITEMS.md - Active Execution Queue

This file is now the single source of truth for active performance ideas,
action items, native migration candidates, execution order, QA gates, and
rollback rules.

Former sources merged into this file:

- `idea_item.md`
- `NATIVE_LIB_PLAN.md`

Those standalone files were intentionally removed after consolidation.

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

## Active Execution Queue

### 1. Subtitle Generation Domain Split And Native Acceleration Plan

Goal: 자막 생성 전체를 기능 경계별 파일/함수로 분리하고, 안정된 compute hot path만 Swift/C++ native helper로 승격해 Apple Silicon ANE/GPU 사용 가능성을 넓힌다.

Status: in_progress

Owner intent:

- 지금처럼 한 경로에 자막 생성, STT, LLM, LoRA, 러프컷, editor live update, timeline paint가 얽히는 구조를 줄인다.
- UI/UX와 자막 품질 정책은 변경하지 않는다.
- 모델 축소, STT2 생략, LLM 생략, 품질 게이트 완화 없이 구조/성능만 개선한다.
- native는 Python parity와 실앱 artifact가 확보된 부분만 적용한다.

Target split map:

- `subtitle_cut_boundary`: 컷 경계 탐지, 컷 후발대, playhead 주변 컷 검증
- `subtitle_stt`: STT orchestration, STT worker lifecycle, rolling window scheduling
- `subtitle_stt1_segments`: STT1 preview/final candidate segment model and timeline feed
- `subtitle_stt2_segments`: STT2 verification candidate segment model and timeline feed
- `subtitle_llm`: 자막 LLM cleanup, conservative prompt, provider routing
- `subtitle_deep_learning`: deep runtime adaptation, confidence gate tuning, learned policy application
- `subtitle_lora`: LoRA retrieval, training-plan metadata, runtime personalization, GPU/native scoring helpers
- `subtitle_roughcut`: roughcut LLM, topic/scene row generation, post-subtitle roughcut ordering
- `subtitle_dictionary`: 단어장/교정 memory/wrong-answer memory lookup and update
- `subtitle_timing`: 자막 간격, 재정렬, frame-grid snap, fixed boundary rules
- `subtitle_parallel_manager`: cut/STT/STT2/LLM/roughcut dependency DAG and bounded parallel execution
- `subtitle_resource_manager`: native resource allocator, Apple core/memory pressure, ANE/GPU/CPU budget hints
- `subtitle_live_sync_manager`: backend progress to editor/timeline/video overlay live event bridge
- `subtitle_live_editor_feed`: generated subtitle rows pushed into editor almost-real-time
- `subtitle_segments`: canonical final subtitle segment schema, merge/split/save/reopen invariants
- `subtitle_waveform`: waveform extraction/cache/render feed
- `subtitle_global_canvas`: minimap/global canvas lanes and segment summaries
- `subtitle_speaker_diarization`: 화자인식/분리, speaker map, two-speaker row payload

Native / open-source candidate policy:

- Swift first for Apple platform helpers with stable structs and deterministic output.
- C++ first for tight loops, interval math, frame-grid timing, waveform summarization, and cache-friendly segment transforms.
- Core ML / Vision / Accelerate / vDSP candidates: waveform stats, simple vector reductions, audio feature windows, cut-boundary numeric kernels.
- Metal / MLX candidates: bounded vector scoring, LoRA retrieval math, batch numeric transforms. Keep PyTorch MPS behind an explicit experimental gate unless a crash-free real fixture run proves safety.
- ANE candidates must go through Core ML models only; do not claim ANE use for ordinary C++/Metal/Python loops.
- External OSS is allowed only when it removes a proven hot path and passes license/runtime packaging checks. Candidate classes: `whisper.cpp`/CoreML only for STT helper parity, `mlx`/`mlx-lm` only for Mac-native LoRA training/scoring experiments, `onnxruntime-coreml` only if package size and runtime stability are acceptable.

Execution order:

1. Inventory current owners and write a dependency map from `core/audio/media_processor*`, `core/engine/subtitle_engine.py`, `core/pipeline/*`, `core/personalization/*`, `ui/editor/*`, and `ui/timeline/*`.
2. Extract pure Python facade modules first with no behavior change and no native code.
3. Add contract tests for each facade using existing X5/Macau/Tinyping fixtures and current project reopen/save paths.
4. Move only stable compute kernels into Swift/C++ helpers behind feature flags.
5. Verify parity against Python on unit tests and real app artifacts before enabling any native helper by default.
6. Run one real High-mode app test and capture queue, terminal logs, timeline, editor, overlay, STT1/STT2 rows, global canvas, waveform, and output SRT.

Acceptance gates:

- Existing subtitle text/timing quality does not regress on representative fixtures.
- Editor, video overlay, timeline segment, STT1 segment, STT2 segment, and saved SRT stay aligned.
- Running app remains responsive during STT/LLM/LoRA/roughcut stages.
- Memory pressure does not worsen compared with latest baseline.
- Native helper can be disabled with a setting/env flag and Python fallback remains correct.

Rollback:

- Revert native feature flag to Python path first.
- If UI/live sync regresses, revert only the affected facade wiring and keep pure extraction modules if tests pass.

## Native Migration Rules

- Native migration follows the same active queue above; do not maintain a separate native queue.
- Native candidates graduate only when Swift/C++ parity is proven against Python behavior and real fixtures show equal or better performance.
- Do not migrate live Qt widget ownership, mutable editor state, subprocess orchestration, model-worker lifetime, or UI callback surfaces wholesale into native code.
- Prefer native compute helpers for bounded hot paths with stable inputs and outputs.
- Completed native-library items must be removed from this file instead of kept as checked history.

## Parked Candidates

These are not active queue items. Before executing one, create a fresh quality
gate and rollback branch.

- Playhead-only dirty-rect repaint: 현재 single-owner 2D full-canvas repaint가 잔상을 막는다. Macau visual smoke로 잔상 없음이 증명될 때만 별도 실험.
- App command/snapshot acknowledgement cleanup: `guided-subtitle-run`과 `capture-snapshot`이 실제 작업은 시작/저장했는데 CLI 응답은 timeout 또는 queued로 남는 관찰이 있었다. 성능 핵심 경로는 아니므로 active item 뒤에, artifact 신뢰도 개선으로만 다룬다.
- Larger real-index Swift/native policy helper: corrected 500-doc synthetic에서 parity는 통과했지만 speedup이 `< 1.0`이다. 큰 payload에서 새 speedup 근거가 나오기 전까지 Python 유지.

## Waste And Lessons

- 폐기 후보 상세: `waste_action_item.md`
- 반복 금지 교훈: `lesson_n_learned.md`
- 공식 테스트 결과: `test_result.md`

## Metadata

```yaml
app_version: "04.00.14"
document_version: "04.00.14-mac-native"
phase: "MAC_NATIVE_APPSTORE_V4_0_14_RELEASED"
queue_source_of_truth: "ACTION_ITEMS.md"
commit_policy: "Commit only when the user explicitly asks."
product_priority: "Accuracy before speed; optimize generation time only with behavior-preserving changes."
```
