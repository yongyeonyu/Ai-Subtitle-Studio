<!--
Document-Version: 04.00.15-mac-native
Phase: MAC_NATIVE_APPSTORE_V4_0_15_RELEASED
Last-Updated: 2026-05-25
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

Status: completed

Progress:

- 2026-05-24: Execution order 1 completed with `SUBTITLE_GENERATION_DOMAIN_MAP.md`, covering current owners and dependency edges from `core/audio/media_processor*`, `core/engine/subtitle_engine.py`, `core/pipeline/*`, `core/personalization/*`, `ui/editor/*`, and `ui/timeline/*`. Drift guard added in `tests/test_subtitle_generation_domain_map.py`.
- 2026-05-24: Execution order 2 started with the first pure Python facade: `core/engine/subtitle_segments.py` now owns save/reopen segment preparation for `core/engine/srt_writer.py`, with coverage in `tests/test_subtitle_segments_facade.py`.
- 2026-05-24: Execution order 2 continued with `core/engine/subtitle_stt_segments.py`, a pure Python facade for shared STT1/STT2 preview timeline row shaping used by `core/pipeline/stt_preview_optimizer.py`. Coverage added in `tests/test_subtitle_stt_segments_facade.py`.
- 2026-05-24: Execution order 2 continued for `subtitle_resource_manager`: `core/runtime/subtitle_resource_manager.py` now owns accelerator name normalization and mixed accelerator parallelism floor decisions used by `core/runtime/multi_process.py`. Coverage added in `tests/test_subtitle_resource_manager.py`.
- 2026-05-24: Execution order 2 continued for `subtitle_global_canvas`: `core/engine/subtitle_global_canvas.py` now owns minimap lane row preparation and merge-helper request shaping used by `ui/timeline/timeline_global.py`. Coverage added in `tests/test_subtitle_global_canvas_facade.py`.
- 2026-05-24: Execution order 2 continued for `subtitle_waveform`: `core/engine/subtitle_waveform.py` now owns global-canvas waveform column feed calculation used by `ui/timeline/timeline_global.py`. Coverage added in `tests/test_subtitle_waveform_facade.py`.
- 2026-05-24: Execution order 2 continued for `subtitle_timing`: `core/engine/subtitle_timing_contracts.py` now owns pure timing bounds/scope/text normalization, frame-field payload construction, and timing-fusion policy payloads consumed by `core/engine/subtitle_timing.py`. Coverage added in `tests/test_subtitle_timing_contracts.py`.
- 2026-05-24: Execution order 2 continued for `subtitle_parallel_manager`: `core/pipeline/subtitle_parallel_manager.py` now owns pure queue progress, cut-boundary iteration planning, and subtitle stage DAG contracts consumed through `core/pipeline/single_pipeline_plan.py`. Coverage added in `tests/test_subtitle_parallel_manager.py`.
- 2026-05-24: Execution order 2 continued for `subtitle_cut_boundary`: `core/engine/subtitle_cut_boundary.py` now owns pure cut-boundary cache settings/payload summaries consumed through `core/pipeline/cut_boundary_cache.py`. Coverage added in `tests/test_subtitle_cut_boundary_facade.py`.
- 2026-05-24: Execution order 2 continued for `subtitle_dictionary`: `core/engine/subtitle_dictionary.py` now owns immutable dictionary lookup/update request payloads and wrong-answer phrase removal consumed by `core/subtitle_quality/candidate_generator.py`. Coverage added in `tests/test_subtitle_dictionary_facade.py`.
- 2026-05-24: Execution order 2 continued for `subtitle_live_sync_manager`: `core/engine/subtitle_live_sync_manager.py` now owns pure live progress/status normalization and cut-boundary topicless live payload shaping consumed by `ui/editor/editor_pipeline_status.py` and `ui/editor/editor_pipeline_signal_bridge.py`. Coverage added in `tests/test_subtitle_live_sync_manager.py`.
- 2026-05-24: Execution order 2 continued for `subtitle_live_editor_feed`: `core/engine/subtitle_live_editor_feed.py` now owns immutable confirmed/STT-preview/subtitle-preview feed payload assembly consumed by `ui/editor/editor_segments_stt_selection_flow.py`. Coverage added in `tests/test_subtitle_live_editor_feed_facade.py`.
- 2026-05-24: Execution order 2 continued for `subtitle_speaker_diarization`: `core/engine/subtitle_speaker_diarization.py` now owns pure speaker-id normalization, speaker-map segment lookup, inline two-speaker dialogue restoration, and runtime row grouping consumed through `core/pipeline/pipeline_helpers.py` and `core/audio/diarize.py`. Coverage added in `tests/test_subtitle_speaker_diarization_facade.py`.
- 2026-05-24: Execution order 3 started with `tests/test_subtitle_facade_project_reopen_contracts.py`, which drives representative DJI/X5-style rows through segment preparation, external SRT project storage/reopen hydration, STT1 candidate tracks, global canvas rows, waveform feed, and subtitle parallel iteration planning.
- 2026-05-24: Execution order 4 readiness guard started with `core/runtime/subtitle_native_readiness.py`, a metadata-only manifest for existing feature-flagged native subtitle helpers. Coverage added in `tests/test_subtitle_native_readiness.py` to keep Python fallback paths enabled when native flags are off and avoid unsupported ANE claims.
- 2026-05-24: Verification gate refreshed after domain split work: full pytest passed (`2788 passed, 1 warning, 5 subtests`) and X5 High 180s full-media verification passed at `output/manual_verification/latest/20260524_domain_split_x5_high_180/tinyping_full_verify.json` (`ok=true`, `pipeline_elapsed_sec=84.786`, `final_segment_count=56`, `raw_segment_count=49`). App quick smoke was attempted at `output/manual_verification/latest/20260524_domain_split_quick_app` but remains a separate app-UI gate because the default Macau project path was missing (`project_not_found`) and the app command endpoint later timed out.
- 2026-05-24: App quick smoke gate fixed and passed: `tools/qa_suite_runner.py` now creates a temporary Macau fixture project under the suite output directory when the legacy default project file is absent, normalizes CLI output paths to absolute paths for bundled app command handling, and passed `quick` at `output/manual_verification/latest/20260524_domain_split_quick_app_retry2` (`failed_count=0`).
- 2026-05-24: Full regression refreshed after QA runner and `subtitle_cut_boundary` facade work: `venv/bin/python -m pytest tests -q` passed (`2796 passed, 1 warning, 5 subtests`) in `181.21s`.
- 2026-05-24: Full regression refreshed after `subtitle_dictionary` and `subtitle_live_editor_feed` facade work: `venv/bin/python -m pytest tests -q` passed (`2804 passed, 1 warning, 5 subtests`) in `179.39s`. `subtitle_speaker_diarization` focused guard passed with `tests/test_subtitle_speaker_diarization_facade.py tests/test_pipeline_speaker_diarization.py` (`9 passed`), then full regression refreshed after the speaker facade passed (`2809 passed, 1 warning, 5 subtests`) in `180.16s`.
- 2026-05-24: `subtitle_live_sync_manager` focused guard passed with `tests/test_subtitle_live_sync_manager.py tests/test_subtitle_generation_domain_map.py tests/test_single_pipeline_ui_guard.py tests/test_runtime_multi_process.py::RuntimeMultiProcessTests::test_runtime_resource_coordinator_active_labels_include_live_pipeline_stages` (`19 passed`), then full regression refreshed after the live-sync facade passed (`2815 passed, 1 warning, 5 subtests`) in `179.35s`.
- 2026-05-25: Long-file cleanup continued without subtitle policy changes. `core/audio/media_processor_transcribe.py` was split into policy/recheck/run/windowed mixins; `core/audio/media_processor_audio.py` now delegates adaptive audio-route helpers to `core/audio/media_processor_audio_route.py`; and `core/engine/subtitle_engine.py` was reduced below 2000 lines by extracting LoRA packaging, LLM runtime wrappers, final-integrity guards, and STT candidate helper/selection modules.
- 2026-05-25: The current top three runtime-code files were reduced below 2000 lines without UI/UX behavior changes: `tools/benchmark_subtitle_pipeline_variants.py` -> 1997 lines via benchmark settings/readability/artifact helpers, `ui/main/main_window.py` -> 1772 lines via automation/personalization mixins, and `ui/timeline/timeline_widget.py` -> 1849 lines via playhead overlay/time-window mixins.
- 2026-05-25: Focused guards passed after the split work: `tests/test_media_processor_transcribe_split.py` (`4 passed`), `tests/test_benchmark_mode_profiles.py` (`24 passed`), `tests/test_timeline_playhead_fit.py` (`144 passed`), `tests/test_timeline_hit_targets.py tests/test_sidebar_terminal_layout.py` (`241 passed`), and subtitle/domain focused set (`104 passed`). X5 후반 60s High benchmark completed with no error at `.codex_work/benchmarks/subtitle_pipeline_variants/20260525_065941/benchmark_results.json` (`quality_score=72.239`, `raw_segments=33`, `final_segments=29`, Swift/native summaries stable).
- 2026-05-25: Long-file cleanup continued until no non-test Python runtime file exceeds 2000 lines. Split behavior-preserving helpers into `core/roughcut/editor_draft_llm.py`, `core/pipeline/cut_boundary_snapshot.py`, `core/pipeline/cut_boundary_segment_ops.py`, `ui/editor/editor_quality_review.py`, `ui/editor/editor_scan_cut_project.py`, and `ui/editor/ux/timeline_input_shadow.py`; current top runtime files are `tools/benchmark_subtitle_pipeline_variants.py` 1997, `core/roughcut/editor_draft.py` 1984, `ui/timeline/timeline_paint.py` 1964. Focused guards passed: `tests/test_pipeline_cut_boundary_cache.py` (`21 passed`), `tests/test_timeline_hit_targets.py` (`144 passed`), `tests/test_editor_roughcut_draft.py` plus Codex roughcut provider guard (`57 passed`), and targeted py_compile checks for split modules.
- 2026-05-25: Completion evidence for the long-file pass added in `LONG_FILE_OWNERSHIP_MAP.md` and linked from `SUBTITLE_GENERATION_DOMAIN_MAP.md`; map guard coverage updated in `tests/test_subtitle_generation_domain_map.py`.
- 2026-05-25: Source-app quick smoke passed at `output/manual_verification/latest/20260525_action_item_completion_quick_source` (`failed_count=0`) after making the QA runner able to force current source execution with `AI_SUBTITLE_STUDIO_QA_USE_SOURCE=1`; automation-only smart-split guards now cover editor/canvas line-key drift without changing subtitle quality or UI/UX behavior.

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
app_version: "04.00.15"
document_version: "04.00.15-mac-native"
phase: "MAC_NATIVE_APPSTORE_V4_0_15_RELEASED"
queue_source_of_truth: "ACTION_ITEMS.md"
commit_policy: "Commit only when the user explicitly asks."
product_priority: "Accuracy before speed; optimize generation time only with behavior-preserving changes."
```
