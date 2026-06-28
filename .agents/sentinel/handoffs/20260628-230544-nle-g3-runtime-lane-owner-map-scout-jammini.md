DEX_REVIEW_READY
역할: jammini
범위: AI Subtitle Studio G3 runtime lane owner-map scout
읽은 파일:
- core/engine/subtitle_live_editor_feed.py
- core/engine/subtitle_global_canvas.py
- tests/test_subtitle_live_editor_feed_facade.py
- docs/project_reference/SUBTITLE_GENERATION_DOMAIN_MAP.md
결론: G3 실시간 NLE STT/VAD 트랙 시각화 인프라 구축의 첫 단계로, 런타임 레인 오너맵(runtime lane owner-map) 연계를 위한 구조 분석 및 영향 범위를 정리했습니다.

*   **프로젝트명**: AI Subtitle Studio
*   **저장소 루트**: `/Users/u_mo_c/Downloads/ai_subtitle_studio`

---

### 🧩 1. 최소 변경 후보 파일 (Minimum Change Candidate Files)

*   **`core/engine/subtitle_global_canvas.py`**:
    - `subtitle_global_canvas_lane_for_segment(seg)` 매핑 함수를 보완하여, STT1/STT2/SUBTITLE 외에 VAD 세그먼트 판정 조건(예: `seg.get("lane") == "VAD"` 또는 `seg.get("voice_active")`가 참일 경우)을 식별하고 `"VAD"` 레인을 바르게 리턴하도록 확장합니다.
*   **`core/engine/subtitle_live_editor_feed.py`**:
    - `SubtitleLiveEditorFeed` 데이터 클래스 및 `build_subtitle_live_editor_feed` 생성기에 VAD/Voice Activity 세그먼트 리스트(`vad_segments`)를 인입할 수 있는 인터페이스를 보강하여, 타임라인 및 미니맵 위젯으로 흘러가는 런타임 피드 단일 구조에 VAD 트랙을 통합합니다.
*   **`docs/project_reference/SUBTITLE_GENERATION_DOMAIN_MAP.md`**:
    - `subtitle_live_editor_feed` 및 `subtitle_global_canvas` 섹션의 도메인 의존 데이터 흐름(Dependency Flow)과 소유 파일 명세를 동기화하여 문서 일치성을 확보합니다.

---

### 📋 2. 기존 테스트 및 검증 후보 (Test Gates)

*   **`tests/test_subtitle_live_editor_feed_facade.py`**:
    - `test_live_editor_feed_sorts_and_counts_rows_without_mutating_inputs`와 유사한 방식으로, 새롭게 인입되는 VAD 세그먼트가 `combined_segments`에 바르게 정렬 정합성을 이루고 복사되는지 검증하는 단위 테스트 추가.
*   **`tests/test_subtitle_global_canvas_facade.py`**:
    - 글로벌 캔버스 미니맵 세그먼트 병합 루틴(`merged_global_canvas_minimap_segments`) 상에서 VAD 레인(Lane) 데이터가 필터링되지 않고 올바르게 출력 레인으로 정렬 및 병합되는지 확인하는 테스트 구성.

---

### ⚠️ 3. 위험한 결합 지점 및 격리 (Risks & Coupling Points)

*   **GUI 렌더러 반응성 지연 위험 (UI Thread Latency Jitter)**:
    - 실시간 생성 단계에서 VAD 세그먼트와 STT1/STT2 후보행이 폭증할 때, `build_subtitle_live_editor_feed`의 내부 정렬 루틴(`_sort_rows`)이 호출되면 GUI 메인 스레드 상의 일시적 병목(프레임 드롭)을 일으킬 수 있습니다.
    - **격리 설계**: 복사 및 정렬 오버헤드를 낮추기 위해 연산부를 오프스크린/비동기로 격리하거나, 실시간 수신률을 제한(Throttling)하는 장치가 수반되어야 합니다.
*   **최종 저장 데이터 오염 위험 (Final Subtitle Pollution)**:
    - 런타임에 시각화하기 위해 임시 생성한 VAD/STT 후보 자막 세그먼트가 에디터의 canonical segments로 유출되거나 오염을 일으켜, 파일 저장 시 불필요한 VAD 데이터가 `.aissproj` 또는 SRT 파일에 영구 기록될 위험이 있습니다.
    - **격리 설계**: VAD/STT2 임시 행들의 `is_gap=True` 또는 `stt_pending` 등의 플래그를 확실히 필터링하고 저장 시점에 격리하는 `editor_save_manager`와의 경계를 지켜야 합니다.
