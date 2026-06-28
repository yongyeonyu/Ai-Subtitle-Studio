DEX_REVIEW_READY
역할: 잼민이
범위: AI Subtitle Studio NLE approved snapshot read-back parity scout
읽은 파일:
- core/project/project_format.py
- core/project/nle_persistence_guard.py
- tests/test_project_nle_persistence_guard.py
- tests/test_project_nle_snapshot.py
결론: Persisted snapshot과 Freshly rebuilt snapshot 간의 패리티(Parity) 검증을 위한 기존 테스트 분석 및 최소 위험 검증 경로(Save/Reopen 표면) 제안을 완료했습니다.

### 🔍 1. 기존 검증 함수 및 테스트 후보
*   **후보 1 (직렬화 라운드트립): `tests/test_project_nle_persistence_guard.py`**
    - `test_owner_approved_nle_snapshot_persistence_roundtrips_with_legacy_rows`:
      승인된 `nle_persistence` 옵션 하에 `nle_snapshot`이 `.aissproj` 파일에 올바르게 직렬화되어 저장되고, 재오픈 시 런타임 `NLEProjectState`로 유실 없이 복구되는지 검사하는 유일한 라운드트립 테스트 케이스입니다.
*   **후보 2 (복합 패리티 투영): `tests/test_project_nle_snapshot.py`**
    - `test_read_only_projection_parity_covers_timeline_overlay_global_save_and_roughcut`:
      타임라인, 에디터 자막 행, 분석용 컷 경계, 러프컷 데이터 등 다양한 런타임 요소가 NLE snapshot과 레거시 구조 양측으로 완벽히 투영(projection)되는지 패리티 일치를 포괄적으로 검증합니다.
    - `test_save_project_routes_editor_rows_through_runtime_nle_state_without_drift`:
      저장 및 복구 과정에서 자막 프레임 타이밍이나 메타데이터의 누락(drift)이 없는지 보장하는 핵심 유틸리티입니다.

### 🛡️ 2. 최소 위험 검증 경로 제안 (Safe Verification Route)
*   **제안 경로: `save/reopen` 라운드트립 기반의 격리 패리티 검증**
    - **이유**: `direct SRT` 나 `roughcut sidecar` 표면은 외부 자막 리소스의 우선순위 정책(`direct_srt_precedence_contract`)이나 EDL 미디어 Relink, 시퀀스 조인 등의 복잡한 결합도가 높습니다. 반면, `save/reopen` 표면은 오직 프로젝트 직렬화(`.aissproj` JSON 입출력) 단계에서의 `nle_snapshot` 키 보존 및 복구 유효성만을 다루므로 검증 스케일이 좁고 부작용 전파가 최소화됩니다.
*   **구체적 구현 가이드 (Next Safe Slice)**:
    - `tests/test_project_nle_persistence_guard.py` 내의 `test_owner_approved_nle_snapshot_persistence_roundtrips_with_legacy_rows` 테스트를 확장하거나 파생 테스트를 설계합니다.
    - 프로젝트 저장 시점의 메모리 상 `NLEProjectState.to_snapshot()` 값과, 이를 디스크에 기록했다가 다시 읽어와 재구축한 `loaded_state.to_snapshot()` 간의 deep-equal 패리티 검사를 추가(assert)하는 슬라이스를 첫 단추로 잡을 것을 권장합니다.
