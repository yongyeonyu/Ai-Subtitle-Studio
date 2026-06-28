DEX_REVIEW_READY
역할: jammini
범위: AI Subtitle Studio G3 compact status feed review
읽은 파일:
- core/engine/subtitle_live_editor_feed.py
- ui/main/app_command_bridge.py
- core/automation/app_command_server.py
- tests/test_subtitle_live_editor_feed_facade.py
결론: G3 실시간 컴팩트 상태 피드 와이어링(wiring) 슬라이스의 영향 범위 및 통신 데이터 정화 설계를 검토 완료했습니다.

*   **프로젝트명**: AI Subtitle Studio
*   **저장소 루트**: `/Users/u_mo_c/Downloads/ai_subtitle_studio`

---

### ⚠️ 1. 발견된 핵심 이슈 (Crucial Findings)

*   **메개변수 불일치 에러 (Signature Mismatch)**:
    - `ui/main/app_command_bridge.py` 내 `_editor_runtime_track_status_snapshot` 함수(Line 717)에서 `build_subtitle_live_editor_feed`를 호출할 때 `vad_segments=vad_segments`를 인자로 넘기고 있습니다.
    - 그러나 `core/engine/subtitle_live_editor_feed.py`에 정의된 `build_subtitle_live_editor_feed` 시그니처에는 `vad_segments` 매개변수가 존재하지 않아 **`TypeError` 예외가 발생**합니다.
    - 이 예외는 내부 `try-except` 블록에 의해 조용히 묻히고 빈 딕셔너리(`{}`)가 반환되어, 결과적으로 UDP/status 응답에서 **`nle_runtime_track_counts` 정보가 누락/유실되는 상태**에 빠지게 됩니다.

---

### 🛡️ 2. 구조적 정화 및 설계 권장 (Wiring Constraints)

1.  **자막 원본 데이터 유출 차단 (No Raw Segments in Status)**:
    - `guided-subtitle-status`, `status`, `ping` 통신 시 사용자가 작성 중인 자막 원본 텍스트 데이터나 타임라인 segments 배열을 통째로 포함해 전송하는 일을 엄격히 막아야 합니다.
    - `_status_snapshot` 및 그 하위 헬퍼들은 오직 각 트랙의 **아이템 수(count) 및 활성화 상태(active), 런타임 수치 메트릭**만 포함하는 컴팩트 정보로 제한 전송되어야 합니다.
2.  **UDP 컴팩트 시 `nle_runtime_track_counts` 보존**:
    - `_compact_nle_runtime_track_status` 함수가 `VAD`, `STT1`, `STT2`, `subtitle_preview`, `final`의 고정 5대 레인에 대해 `"count"`, `"active"`, `"role"` 정보를 1차 컴팩트화하여 압축 전송하므로, UDP 전송 후에도 이 계층구조(`counts` 및 `tracks`)가 원형 그대로 파싱 보존될 수 있습니다.
3.  **최종 권한(Final Authority) 보호**:
    - NLE 연동에서 `final` 레인만 `"authoritative_for_save_export": True` 권한을 갖도록 상시 가딩 처리되어 있으므로, VAD 나 STT 후보 등의 참고 데이터가 저장 권한을 침범하지 못해 진실의 원천(SOT)이 보호됩니다.

---

### 📋 3. 최소 변경 후보 및 테스트

*   **`core/engine/subtitle_live_editor_feed.py`**:
    - `build_subtitle_live_editor_feed` 및 `SubtitleLiveEditorFeed`에 `vad_segments` 매개변수를 추가하고, 이를 포함한 런타임 피드 상태(`runtime_status()`) 반환 헬퍼를 노출하도록 수정이 시급합니다.
*   **테스트 대상**:
    - `tests/test_subtitle_live_editor_feed_facade.py`
    - `tests/test_app_command_bridge.py`
    - `tests/test_app_command_server.py`
