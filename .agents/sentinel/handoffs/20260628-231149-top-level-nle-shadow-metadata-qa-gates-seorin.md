DEX_REVIEW_READY
역할: 서린
범위: AI Subtitle Studio top-level nle QA gates
읽은 파일:
- core/project/project_format.py
- core/project/nle_persistence_guard.py
- tests/test_project_nle_persistence_guard.py
결론: Top-level NLE 페이로드를 오너 승인형 섀도우 메타데이터(Shadow Metadata)로 저장할 때 적용할 strict QA 게이트 가이드라인을 작성했습니다.

*   **프로젝트명**: AI Subtitle Studio
*   **저장소 루트**: `/Users/u_mo_c/Downloads/ai_subtitle_studio`

---

### 🔍 1. 거짓 양성(False Green) 배제용 음성 검증 (Negative Fixture Test)

*   **디스크 섀도우 데이터 의도적 조작 검증 (Negative Test)**:
    - [ ] 저장 파일(`.aissproj`) 내의 `nle_snapshot` 내부 프레임 경계나 자막 수 메타데이터를 강제로 조작한 부정 테스트 피처(negative fixture)를 준비합니다.
    - [ ] 이 파일을 로드했을 때 로더가 조용히 넘어가지 않고, 패리티 가드에 의해 **`checked=True` 및 `stable=False` 판정이 명확히 감출되며 불일치 정보가 `quarantine_drift_report`에 바르게 등재되는지** 검사하여 무조건 PASS 처리되는 오탐을 차단합니다.

### 📋 2. 스토리지 단언 검증 (Storage-Key Assertions)

*   **비인가 잔여 상태 격리 검증 (Key Scanning)**:
    - [ ] 프로젝트 세이브 완료 후 저장된 디바이스 JSON 객체 최상단에서 키 리스트를 검사하여 `nle_snapshot` 과 `nle_persistence` 이외의 런타임 잔류 키(`nle`, `_nle_project_state`, `_nle_snapshot_readback_parity`)가 100% 필터링되어 완전히 존재하지 않음(`self.assertNotIn`)을 단언합니다.
*   **자막 메트릭 일관성 검사**:
    - [ ] 로드 완료 시점의 런타임 메모리 자막 세그먼트들이 `invalid_duration_count = 0`, `overlap_count = 0`, `max_active_segments <= 1` 상태를 엄격히 보존하는지 단언합니다.

### 🎯 3. 집중 검증 명령 셋 (Focused Pytest & Audit Commands)

*   **로컬 타겟 테스트 실행**:
    ```bash
    QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -v \
      tests/test_project_nle_persistence_guard.py \
      tests/test_project_nle_snapshot.py \
      -k "persistence or guard or roundtrip"
    ```
*   **디렉토리 내 파일 검증 자동화**:
    - [ ] `tools/audit_nle_persistence_cutover.py`를 활용하여 저장된 파일의 NLE 섀도우 메타데이터 직렬화 정합성 오디트 런을 수행하고 결과 리포트를 증적으로 제출합니다.
