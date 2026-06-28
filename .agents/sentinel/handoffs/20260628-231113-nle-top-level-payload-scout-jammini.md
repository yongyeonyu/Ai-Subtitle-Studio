DEX_REVIEW_READY
역할: 잼민이
범위: AI Subtitle Studio next NLE top-level payload scout
읽은 파일:
- core/project/project_format.py
- core/project/nle_persistence_guard.py
- tests/test_project_nle_persistence_guard.py
- docs/planning_queue/ACTION_ITEMS.md
결론: 대표님 승인 하의 Persisted NLE/UI 구조 확장 다음 단계로서, NLE top-level payload 저장 활성화를 위한 차기 G2 슬라이스 후보 스카우트를 완료했습니다.

*   **프로젝트명**: AI Subtitle Studio
*   **저장소 루트**: `/Users/u_mo_c/Downloads/ai_subtitle_studio`

---

### 🧩 G2 차기 슬라이스 후보: "NLE Snapshot 디스크 직렬화 저장 가드 해제 및 라운드트립 패리티 가드 활성화"

이 단계의 목표는 `nle_snapshot`을 저장 시점에 파일로 실제로 쓰고 다시 읽어들이는 스위치를 활성화하고, 이 과정에서 레거시 자막 오너십을 해치지 않고 패리티 정합성만 검사하는 것입니다.

#### 1. 최소 변경 후보 파일 (Minimum Change Candidate Files)
*   **`core/project/nle_persistence_guard.py`**:
    - `NLE_SNAPSHOT_PERSISTENCE_APPROVAL_ID` 승인 ID를 활성화하는 쓰기 가드(`persist_snapshot=True`)의 기본 통과 조건을 제공하여, 프로젝트 저장(`write_project_file`) 시 `nle_snapshot` 필드가 `.aissproj`에 온전히 직렬화되어 방출되도록 가드를 해제합니다.
*   **`core/project/project_format.py` & `project_io.py`**:
    - 직렬화 가드 정화 처리(`_project_payload_for_disk`) 단계에서 `nle_snapshot` 키가 필터링(pop)되지 않고 스토리지 명세에 최종 포함되도록 보장합니다.

#### 2. 기존 테스트 및 신규 오디터 후보
*   **`tests/test_project_nle_persistence_guard.py`**:
    - `test_owner_approved_nle_snapshot_persistence_roundtrips_with_legacy_rows`: 실제 디스크 쓰기 가드 해제 시의 정상 라운드트립 패리티 일치성을 확보하는 단독 검증.
*   **`tools/audit_nle_persistence_cutover.py`**:
    - 저장 직후 raw JSON 내부 구조에 `nle_snapshot` 스키마가 안정적으로 기록되어 있고, 금지된 런타임용 임시 키(`nle`, `_nle_project_state`, `_nle_snapshot_readback_parity`)가 완전히 정화(strip)되었는지 최종 점검하는 오디터 스크립트 작성.

#### 3. 위험한 결합 지점 및 복구 (Rollback Risk)
*   **스키마 불일치 저장 위험 (Data Drift on Storage)**:
    - 런타임 NLE 편집 데이터와 저장 장치에 방출된 `nle_snapshot` 사이에 데이터 동기화 지연이나 타이밍 불일치가 생길 위험이 큽니다.
    - **해결책**: 로드 시 패리티 가드(`attach_nle_snapshot_readback_parity`) 결과 `stable=False`인 경우, 파일 내 스냅샷 데이터를 버리고(quarantine) 검증된 레거시 자막 행(`editor_state.segments`)에서 NLEProjectState를 새로 재생성(rebuild)하여 덮어쓰기 없이 안전하게 롤백하도록 복구 경로를 마련해야 합니다.
