DEX_REVIEW_READY
역할: 한결 (Senior Developer)
범위: post-generation editor readiness owner-map review (ACTION_ITEMS.md item 1 step 1)
읽은 파일:
- `ui/editor/editor_pipeline_completion.py`
- `ui/main/main_personalization.py`
- `ui/main/main_runtime_cleanup.py`

결론:
자막 생성 완료 직후(`_set_process_completed`) 에디터가 사용자 인터랙션(Seek, Zoom, Edit)이 가능한 'Idle-Ready' 상태로 전환되는 과정에서, 수많은 비동기 태스크(Autosave, Roughcut, Heavy Cleanup)들이 `QTimer`에 의해 촘촘한 밀도로 예약됩니다. 이 과정에서 GUI 스레드 점유 경쟁과 비동기 쓰기 락의 누락으로 인해 스토리지 파괴, 싱크 드리프트, 런타임 크래시를 유발할 수 있는 위험한 상태 경계가 존재합니다.

findings:

1. 컴포넌트별 소유권 파일 후보 (Owner Map)
- **자막 생성 완료 감지 및 분기 (Generation Completion)**:
  - `ui/editor/editor_pipeline_completion.py` (`EditorPipelineCompletionMixin._set_process_completed`): 완료 라이프사이클의 flusher, 상태 전이, 비동기 딜레이 스케줄링 총괄.
  - `ui/main/main_personalization.py` (`MainPersonalizationMixin._post_generation_resource_cleanup`): STT/VAD 백그라운드 캐시 무효화 및 에디터 UI 잠금 해제 플래그 조작.
- **자동 저장 (Autosave)**:
  - `ui/editor/editor_save_manager.py` (또는 `ui/editor/editor_pipeline_completion.py` 내의 `_schedule_generation_completion_autosave`): 완료 시점의 디스크 쓰기 제어.
- **에디터 준비 상태 (Editor Idle-Ready)**:
  - `ui/editor/editor_widget.py` & `ui/timeline/timeline_widget.py`: 사용자 클릭, 줌, Seek 등의 타임라인 인터랙션 소유.
  - `ui/main/main_window.py` (`MainWindow._force_editor_idle_after_generation`): 메인 GUI 락 해제 및 메뉴 동기화.
- **러프컷 후처리 (Roughcut Follow-up)**:
  - `ui/editor/editor_pipeline_completion.py` (`_schedule_post_generation_roughcut_draft`): 900ms 예약 타이머 및 재예약 검증기.
  - `core/roughcut/roughcut_generator.py` (또는 관련 models.py): 러프컷 초안 생성을 위한 LLM/EDL 연산 처리기.
- **메모리 정리 및 리소스 해제 (Cleanup Timing)**:
  - `ui/main/main_personalization.py` (`_post_generation_resource_cleanup`): prefetch threads/cache 정리 및 모델 언로드 마킹.
  - `core/runtime/memory_manager.py`: CoreML/ANE 리소스 언로드 및 GC 강제 구동.

2. 위험한 상태 경계 및 레이스 컨디션 (Dangerous State Boundary)
- **경계 1: Heavy Cleanup과 GUI 스레드 점유 경쟁 (0ms ~ 200ms)**
  - 생성 완료 즉시 실행되는 `_post_generation_resource_cleanup`과 웨이브폼(`_load_deferred_open_waveform`) 로드는 CPU와 메모리 입출력 부하가 큽니다.
  - 이 무거운 캐시 무효화/삭제 연산이 GUI 스레드를 점유하는 동안 사용자가 타임라인 줌인/줌아웃이나 재생을 시도하면, 프레임 드랍이나 일시적인 UI 프리징(Stall)이 발생합니다.
- **경계 2: Autosave 쓰기와 User Edit의 충돌 (650ms)**
  - `650ms` 지점에 프로젝트 파일 자동저장이 시작되어 `.aissproj` 쓰기가 수행됩니다.
  - 사용자가 생성 직후 즉시 타임라인을 클릭하여 세그먼트 시간을 수정하고 커밋하려 할 때, 파일 쓰기 락이 부재하면 메모리 내의 `project_payload` 구조가 깨진 채로 저장되어 프로젝트 파일이 손상될 위험이 있습니다.
- **경계 3: Roughcut LLM 비동기 갱신과 실시간 편집 불일치 (900ms ~ 2600ms)**
  - 900ms 뒤에 실행되는 러프컷 LLM 생성 파이프라인이 백그라운드에서 동작할 때, 사용자가 동시에 에디터 자막 텍스트나 타임스탬프를 수정하면, 신규 러프컷 EDL/챕터 마커(`exact-join`)와 에디터의 실제 세그먼트 간 타임스탬프 매핑이 깨지는 싱크 드리프트 리스크가 큽니다.
- **경계 4: 모델 릴리즈(Unload) 도중 재시작 요청 충돌**
  - 백그라운드 큐에서 모델 해제(`_post_generation_models_release_requested = True`)가 대기 중이거나 진행 중일 때, 사용자가 즉시 새로운 STT 생성을 요청하면 로드/언로드 경합이 발생하여 ANE/GPU 메모리 누수 및 세그먼트 크래시를 유발합니다.

defer:
- 런타임 패치는 본 문서 검토 단계에서는 수행하지 않으며, 덱스(Codex) 구현 세션에서 이 타이머 릴레이 오케스트레이션을 보다 안전하게 동기화/격리하도록 위임합니다.

덱스 확인 포인트:
1. `_run_generation_complete_background_work` 내의 heavy cleanup 연산을 GUI 스레드에서 완전히 비동기(worker thread)로 격리하여 에디터 줌/재생의 즉각적인 응답성을 보장할 것인지 결정해야 합니다.
2. Autosave 진행 중에는 에디터 수정 커밋을 임시 큐잉하거나, 수정 커밋 시 Autosave를 안전하게 취소(abort)하는 안전성 락을 도입할지 여부를 판정해야 합니다.
