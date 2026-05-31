# idea.md

Purpose: Shared scratchpad for `덱스` and `잼민이` when a refactor or optimization task surfaces ideas worth discussing before implementation.

Rules:

- This file is a discussion and candidate log, not the source of truth for execution order.
- `ACTION_ITEMS.md` remains the source of truth for active queue and accepted execution items.
- Use this file to capture optimization ideas, native-capable hotspots, algorithm simplification candidates, rollback concerns, and open questions for cross-review.
- Do not treat an idea in this file as approved work until the owner or `덱스` explicitly promotes it into an execution task.
- If `덱스` asks `잼민이` to review specific files, capture any still-open review questions or disputed ideas here before execution if they need cross-check discussion.
- If a task was delegated from steering overflow, note that here when it helps explain why the work was split between `덱스` and `잼민이`.

## Current Shared Goal

- Improve app responsiveness and reduce CPU/core and RAM pressure.
- Preserve subtitle quality and editing correctness as the top constraint.
- Prefer Apple Silicon-friendly ANE/GPU paths where the workload can realistically move off repeated CPU-side processing.
- Prefer safe native-capable hotspots in `.cpp` or `.swift` only when behavior boundaries are clear and rollback is practical.
- Prefer one-pass or reduced-pass data flow where it lowers redundant work without harming correctness.
- Prefer algorithmic simplification over large rewrites when the win is real and validation scope is manageable.
- Remove genuinely unused functions, variables, imports, or helper layers when Dex confirms the deletion is safe and the cleanup does not hide runtime-sensitive behavior.
- Reorganize files or folders only when the role map is clear and Dex can supervise the move order and rollback plan.

## Non-Negotiables

- No subtitle-quality regression.
- No save/load compatibility break.
- No speculative broad native migration.
- No “error-free by assumption” claims; every risky change needs explicit validation and rollback notes.

## Candidate Ledger

| Status | Area | File(s) | Idea | Expected Win | Risk | Proposed Validation | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| open | Pass Reduction | `core/engine/subtitle_timing.py` | VAD/타이밍 정렬의 다중 패스 루프를 단일 패스로 병합 | CPU 오버헤드 감소 | 타이밍 우선순위 왜곡 및 자막 겹침 발생 리스크 | `tests/test_subtitle_boundary_alignment.py` | Dex 최종 승인 후 설계 검토 |
| open | RAM / CPU | `ui/editor/ux/timeline_subtitle_segment_editing.py` | 드래그/수정 시 전체 repaint 차단 및 dirty-rect 부분 그리기 적용 | CPU 점유율 하락, 발열 억제 | 타임라인 캔버스 잔상 발생 가능성 | `tests/test_timeline_hit_targets.py` 및 Macau 실앱 조작 검증 | 서린(QE)의 엄격한 모니터링 요구 |
| open | Native-capable | `core/pipeline/cut_boundary_helpers.py` | 컷 스캔 픽셀 비교 루프를 Apple Silicon Accelerate(vDSP)/Metal로 위임 | 대용량 비디오 씬 스캔 시간 대폭 단축 | 씬 감지 감도 불일치 및 컷 경계 이탈 리스크 | `tests/test_cut_boundary_ffmpeg_scene.py` | .cpp/.swift 바인딩 범위 격리 |
| open | CPU | `ui/editor/ux/timeline_input.py` | 타임라인 마우스 드래그/무브 이벤트 스로틀링 (Throttling) 도입 | 드래그 조작 시 순간 CPU 튀는 현상 차단 | 미세 조작 반응 시간 딜레이(Lag) 느낌 유발 | 마우스 움직임 실앱 프레임 타임 측정 | 한결(시니어) 피드백 필요 |
| open | Pass Reduction | `ui/timeline/timeline_paint.py` | 현재 화면 밖 웨이브폼 드로잉 연산 차단 (visible time window 필터링) | 대형 파일 스크롤 시 CPU 낭비 해소 | 스크롤 시 일시적인 파형 빈 공간 깜빡임 리스크 | X5 fixture 수동 줌/스크롤 렌더링 측정 | visual playhead 정렬 유지 필수 |
| completed | Unused Code | `ui/home_sidebar.py` | 미사용 임포트(`QCursor`, `QDialogButtonBox`, `show_context_menu`) 제거 및 백그라운드 터미널 중복 레이아웃 재빌드 차단 제안 | RAM 절감 및 UI 스레드 오버헤드 완화 | 없음 (side-effect-free) | `tests/test_sidebar_terminal_layout.py` 및 부팅 동작 | 잼민이 1순위 초소형 패치 완료 (untracked) |
| open | Pass Reduction | `core/engine/subtitle_timing.py` | 자막 최소 지속 시간 정렬 루프의 redundant pass 축소 | 자막이 많을 때의 CPU 오프셋 절감 | 자막 세그먼트 소실 또는 겹침 리스크 | `tests/test_timeline_playhead_fit.py` | 자막 품질 최우선 보장 규칙 준수 |
| open | Unused Code | `ui/timeline/timeline_widget.py`, `ui/editor/editor_widget.py` | 미사용 QML/SceneGraph 엔진 포트 및 브리지 레퍼런스, 미사용 CSS 정리 | 앱 기동 시 RAM 로드량 절감 및 경량화 | dynamic reference 실패 시 ImportError 유발 | `tests/test_main_file_ops_nonfatal.py` 부팅 테스트 | 덱스 확인 후 safe delete |
| open | CPU | `ui/main/main_window.py` | 홈/에디터 전환 시 발생하는 다중 연쇄 리사이즈 레이아웃 리밸런싱 이벤트 차단 | 화면 흔들림(Shake) 방지 및 CPU 병목 해소 | 리사이즈가 생략되어 일부 레이아웃이 깨질 리스크 | 실앱 크기 조절 테스트 및 `00:00 / 00:00` 정렬 확인 | 유진(에디터) 뷰포인트 점검 필요 |
| open | Native-capable | `core/engine/subtitle_engine.py` | STT 입력용 16kHz 모노 오디오 변환 시 CPU 패스 대신 Accelerate(vDSP) 또는 ANE 전처리 사용 | 오디오 추출 및 변환 속도 대폭 단축 | VAD/STT 정확도 하락 리스크 (자막 품질 최우선 제약) | X5 fixtures 및 `tests/test_whisper_coreml.py` 일치도 검사 | 자막 정확도 검증 세트 통과 필수 |

## Questions For Dex And Jammini

- Which 1500+ line file has the smallest safe optimization slice with measurable benefit?
- Which repeated passes can be merged into a single pass without changing subtitle semantics?
- Which hotspots are best moved to `.cpp` or `.swift` while keeping the Python source app as the baseline?
- Which workloads can realistically use Core ML / ANE / Metal / MLX / Accelerate instead of repeated CPU-side work?
- Which unused functions, variables, imports, or helper layers are safe cleanup wins versus risky false positives that Dex should review first?
- Which files or folders have drifted from their real responsibilities enough that a supervised reorganization would improve maintainability without destabilizing runtime behavior?
- What evidence would prove reduced CPU/core usage or RAM pressure on real fixtures?

## Jammini Readiness Scout

### 1. Completion-to-Idle Call Order
생성 파이프라인(`EditorPipelineCompletionMixin._set_process_completed`) 완료 후 에디터가 대기 상태에 진입하기까지의 호출 순서:
1. `_process_completed_finalized = True` 플래그 셋 및 `_flush_pending_segment_queue_now()` 가동 (미완료 세그먼트 최종 플러시).
2. `_clear_live_generation_preview_artifacts()`를 통한 임시 프리뷰 에셋 소거.
3. `_schedule_generation_complete_timestamp_refresh()`로 타임태그 복원 및 동기화 (즉시 및 0ms, 120ms, 360ms 시차 렌더링).
4. `_mark_generation_complete_state()` 호출해 상태 머신을 `ST_COMP` (완료)로 전이.
5. `_clear_processing_indicators()`가 GUI 처리 표시를 소거하고, `_sync_generation_complete_ui(main_w)` 호출:
   - `_force_editor_idle_after_generation()` 기동하여 마우스/키보드 인풋 락 및 플레이헤드 락을 즉각 해제하고 일반 마우스 커서 복원(`_restore_normal_cursor`).
6. 후속 부가 리소스 태스크들을 싱글샷 타이머로 흩뿌림(Scatter):
   - **즉시**: `_queue_generation_complete_learning` (LoRA foreground 학습 큐 등록 및 보류)
   - **즉시**: `_run_generation_complete_cleanup` (비동기 GPU/Model 메모리 GC 스케줄러 트리거)
   - **즉시**: `_load_generation_complete_waveform` (오디오 타임라인 파형 로드)
   - **200ms 뒤**: `_post_completion_sync` (자막 싱크 최종 정렬 보정)
   - **650ms 뒤**: `_schedule_generation_completion_autosave` (자동 저장 임시 체크포인트 스냅샷 저장)
   - **900ms 뒤**: `_schedule_post_generation_roughcut_draft` (러프컷 LLM 초안 초단위 예약 기동)
   - **1300ms 뒤**: `unlock_sidebar` (사이드바 폭 잠금 해제)
   - **2600ms 뒤**: `_verify_generation_complete_roughcut_followup` (러프컷 유실 방지 최종 수동 확인)

### 2. Immediate UI-Critical Steps
* **에디터 인풋 락 전면 해제**: `_force_editor_idle_after_generation()` 가 위젯과 캔버스 스레드 락을 완전히 풀어 조작 권한을 사용자에게 넘김.
* **마우스 커서 즉시 원복**: PyQt 기동 스피너 로딩 마우스 포인터를 일반 포인터로 되돌리는 `_restore_normal_cursor()` 및 240ms 스로틀링 필터.
* **자막 조각 최종 동기화**: `_flush_pending_segment_queue_now()` 및 자막 복원 layer 렌더링.

### 3. Heavy Cleanup / Background Candidates
* **개인화 LoRA 학습 큐 등록**: `_queue_generation_complete_learning` (백그라운드 가상 큐로 위임).
* **GPU & MLX 모델 메모리 GC 해제**: `_run_generation_complete_cleanup` (사용자가 재생을 즉시 시작할 경우 `_prioritize_video_playback_runtime` 기법에 의해 2200ms 단위로 지속 유보되어 재생 stutter 방지).
* **러프컷 LLM 초안 자동 드래프트**: `_schedule_post_generation_roughcut_draft` (900ms 뒤 싱글샷 기동).

### 4. The Safest Next Large Slice Dex Should Do Next
* **에디터 사용자 수동 인터랙션 시 AI 후처리 유보(Throttling)**:
  - 현재 비디오 재생 시그널(`video_playback_start`)에만 연동되어 있는 러프컷 LLM 초안 즉각 취소(`_cancel_post_generation_roughcut_draft`) 및 대기 상태 전이 메커니즘을, **사용자의 마우스 타임라인 드래그 조작 개시(Scrubbing)나 자막 텍스트 에디터 창 포커스 획득 시점**에도 즉시 반응하도록 연동 범위를 확장하는 것.
  - 이를 통해 생성 완료 직후 AI 연산과 디스크 I/O가 얽혀 발생하는 일시적 UI 얼어붙음(Freeze)을 원천 차단하고 즉각적인 에디터 조작성을 100% 보장함. 자막 품질 및 STT 알고리즘에 주는 리스크가 전혀 없는 **가장 안전한 대형 UX 최적화 슬라이스**임.

### 5. The Tests Dex Should Trust for That Slice
* `tests/test_timeline_playhead_fit.py` (타임라인 플레이헤드 맞춤 및 seek 무회귀 검증)
* `tests/test_editor_autosave_cleanup.py` (비동기 완료 후 autosave 정리 안정성 입증)
* `tests/test_project_segment_reload.py` (생성 완료 후 재로드 시 세그먼트 손실 회귀 방지)

## Decision Log

### 2026-05-31 - Manual Interaction Priority Slice

- `덱스` 구현 범위:
  - `ui/main/main_runtime_cleanup.py`
  - `ui/editor/ux/editor_timeline_video.py`
  - `ui/editor/ux/subtitle_text_edit.py`
  - 관련 테스트 파일
- 구현 내용:
  - post-generation foreground helper를 공용화하고,
  - 첫 active scrub 시작과 subtitle text focus 시점에만
    manual-interaction runtime priority를 걸어
    roughcut/GC follow-up이 즉시 편집 체감을 막지 않도록 했습니다.
- `잼민이` 합동 리뷰 결론:
  - 판정: `Accept`
  - `roughcut_reason`은 스크럽과 텍스트 포커스를 따로 나누지 말고 `"편집 시작"`으로 통합 유지 권장
  - save/load 및 playback runtime semantics 회귀는 현재 패치 범위에서 없다고 판단
  - 다음 보강 후보는 `scrub <-> play` 비동기 스트레스 시나리오
- 현 시점 권장 검증:
  - `tests/test_editor_autosave_cleanup.py`
  - `tests/test_project_segment_reload.py`
  - `tests/test_timeline_playhead_fit.py`
  - `tests/test_subtitle_text_edit_keys.py`
  - `tests/test_sidebar_terminal_layout.py`
  - 이후 source app에서 Macau/X5 실앱 스모크
