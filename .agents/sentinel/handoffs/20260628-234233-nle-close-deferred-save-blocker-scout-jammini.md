DEX_REVIEW_READY
역할: jammini
범위: AI Subtitle Studio G2 close deferred-save blocker scout
읽은 파일:
- docs/planning_queue/ACTION_ITEMS.md
- ui/editor/editor_save_manager.py
- core/project/nle_runtime_cutover.py
- core/project/nle_project_state.py
- projects/내 프로젝트 (5).aissproj
결론: 자막 닫기(close) 지연 저장 시 NLE save/export 프로젝션이 실패(`nle_save_export_final_overlap`)하는 vector canvas `time` 딕셔너리 구조적 정규화 누락 원인과 해결 방안 스카우트를 완료했습니다.

*   **프로젝트명**: AI Subtitle Studio
*   **저장소 루트**: `/Users/u_mo_c/Downloads/ai_subtitle_studio`

---

### ⚠️ 1. 근본 원인 분석 (Root Cause Analysis)

`내 프로젝트 (5).aissproj` 자막 데이터(`/editor_state/rendering/subtitle_canvas/segments`)를 디코딩해 본 결과, 벡터 캔버스 자막 행들의 시간 정보가 최상위 키가 아닌 중첩된 `time` 딕셔너리 구조 내부에 프레임 단위로 수록되어 있습니다:
```json
"time": {
  "start_frame": 0,
  "end_frame": 200,
  "timeline_frame_rate": 59.94005994005994,
  "unit": "frame"
}
```
*   **시간 디코딩 실패**:
    - NLE 연산부인 `nle_runtime_cutover.py`와 `nle_project_state.py`의 `_row_frame_bounds` 함수는 `row.get("start_frame")`이나 `row.get("frame_range")`만 조회하므로, `time` 구조 하위의 프레임 값을 전혀 디코딩하지 못해 **모두 0 프레임(start=0, end=0)으로 간주**합니다.
*   **에러 유발 및 세이브 루프 교착**:
    - 이로 인해 `end_frame <= start_frame`이 참이 되어 `nle_save_export_invalid_duration` 또는 `nle_save_export_final_overlap` 예외가 강제 발생하고, 지연 저장 스냅샷 쓰기가 실패하여 앱 종료가 차단되는 교착 상태가 일어납니다.

---

### 🧩 2. 최소 변경 후보 파일 (Minimum Change Candidate Files)

*   **`core/project/nle_runtime_cutover.py`** & **`core/project/nle_project_state.py`**:
    - 각각의 `_row_frame_bounds` 헬퍼 함수 내부에서 `row.get("time", {})` 딕셔너리를 검사하여 `start_frame` / `end_frame`을 추출하는 정규화 폴백 로직을 보완합니다.
    ```python
    # 안전 설계 예시 (nle_runtime_cutover.py)
    def _row_frame_bounds(row: dict[str, Any]) -> tuple[int, int]:
        t_dict = row.get("time", {}) if isinstance(row.get("time"), dict) else {}
        start_frame = row.get("start_frame", row.get("timeline_start_frame", t_dict.get("start_frame")))
        ...
    ```

---

### 📋 3. 위험한 결합 지점 및 테스트 수립 (Risks & Test Gates)

*   **시간 스케일 변환 오차 위험 (Jitter/Drift Risk)**:
    - 벡터 캔버스 내 `time.timeline_frame_rate`가 `59.94fps`로 세팅되어 있는데 런타임의 `primary_fps`가 `30.0fps` 등으로 불일치할 경우, 프레임 비율 정밀 스케일링이 누락되면 자막의 물리적 경계가 엇나갈 위험이 있습니다.
    - 따라서 `timeline_frame_rate`를 디코딩에 올바르게 적용하거나, `fps`를 상호 호환 정비하는 정밀 검증이 수반되어야 합니다.
*   **테스트 대상**:
    - `tests/test_project_nle_runtime_cutover.py`: vector layout 자막행을 투입하여 `nle_save_export_segments_from_editor_rows`가 예외 없이 정상 복구되는지 검사하는 케이스 추가.
