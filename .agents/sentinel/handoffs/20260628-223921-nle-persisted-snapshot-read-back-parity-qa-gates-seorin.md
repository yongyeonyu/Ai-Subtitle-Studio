DEX_REVIEW_READY
역할: 서린
범위: AI Subtitle Studio NLE persisted snapshot read-back parity QA gates
읽은 파일:
- tests/test_project_nle_persistence_guard.py
- tests/test_project_nle_snapshot.py
결론: Persisted snapshot 패리티 검증을 위한 Strict QA Gate와 거짓 양성(Misleading Green) 차단 수칙을 수립했습니다.

### 🔍 1. 거짓 양성(Misleading Green) 방지를 위한 Negative Tests
단순히 예외 없이 로드된다고 해서 패리티가 완벽하다고 볼 수 없습니다. 이를 강제하기 위해 다음 음성 검증(Negative Verification) 설계가 수립되어야 합니다.

*   **의도적 불일치 피처 (Negative Fixture Test)**:
    - [ ] 레거시 자막 `editor_state.segments`와 파일 내 `nle_snapshot`의 자막 수 또는 특정 타임스탬프(start/end) 값을 의도적으로 다르게 수정한 깨진 프로젝트 파일(corrupted fixture)을 로드합니다.
    - [ ] 이때 로더가 경고 없이 그대로 로드를 끝내지 않고, **패리티 불일치(Drift)를 올바르게 감지하여 `quarantine_drift_report`에 불일치 내역(mismatch count, key drift)을 상세 기록하는지** 검증하는 테스트 케이스를 반드시 추가해야 합니다.

### 📋 2. 필수 실행 테스트 및 저장 키 Assertions
*   **Must-Run Tests**:
    - [ ] `tests/test_project_nle_persistence_guard.py`
    - [ ] `tests/test_project_nle_snapshot.py`
    - [ ] `tests/test_project_segment_reload.py`
    - 위의 테스트가 `QT_QPA_PLATFORM=offscreen pytest` 하에 `failed_count=0`으로 통과하는지 확인해야 합니다.
*   **Storage-Key Assertions**:
    - [ ] 저장 파일(`.aissproj`) JSON을 날것(raw)으로 파싱하여, 금지된 키(`nle`, `_nle_project_state`, `nle_snapshot_quarantine`)가 물리 디스크에 유출되지 않았는지 단언(assert)해야 합니다.
    - [ ] 오직 허용된 `nle_snapshot`과 메타데이터만 스키마에 기록되는지 직접 `dict.keys()` 수준에서 스캔합니다.

### 🎯 3. 증적 제출 범위 (Evidence Criteria)
*   **Direct SRT**: 직접 열기한 SRT 타임라인 상태가 `direct_srt_precedence_contract=srt_timing_text_wins`에 따라 런타임 NLE 스냅샷 데이터와 프레임 단위로 100% 일치함을 나타내는 로그 증적.
*   **Roughcut Sidecar**: EDL 연동 결과로 도출된 컷 경계 오프셋이 NLE 렌더 플랜 내의 `stitched_cut_boundaries`와 완벽히 동치인 것을 증명하는 JSON 증적.
*   **Save/Reopen**: 연속 3회 이상의 입출력 루프를 거친 후에도 `invalid_duration_count = 0`, `overlap_count = 0`, `max_active_segments <= 1` 상태가 항시 보존되는 증적 자료 제출.
