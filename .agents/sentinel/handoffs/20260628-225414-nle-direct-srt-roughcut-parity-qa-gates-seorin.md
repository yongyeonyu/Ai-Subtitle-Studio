DEX_REVIEW_READY
역할: 서린
범위: AI Subtitle Studio NLE direct SRT/roughcut read-back parity QA gates
읽은 파일:
- core/project/nle_snapshot.py
- core/project/project_io.py
- tests/test_project_nle_snapshot.py
결론: Direct SRT 오픈 및 Roughcut sidecar 복구 영역의 패리티 확장을 검증하기 위한 Strict QA Gate 및 거짓 양성(False Green) 배제 수칙을 수립했습니다.

### 🔍 1. 거짓 양성 배제용 음성 검증 (Negative Fixture Test)

*   **Direct SRT 의도적 불일치 검증 (Negative Test)**:
    - [ ] 로드할 SRT 파일의 특정 자막 텍스트나 타임라인을 의도적으로 변형시킨 뒤, 프로젝트에 포함된 기존 `nle_snapshot`과 대조하여 `checked=True`, `stable=False` 판정이 명확하게 유도되는지 확인하는 Negative Test를 구축해야 합니다. (무조건 성공으로 보고되는 False Green 감쇄 장치)
*   **Roughcut 마커 불일치 감지**:
    - [ ] EDL 파일에 기술된 조인 지점의 수와 스냅샷 markers 내의 `roughcut_exact_join` 수가 다를 때, `build_nle_snapshot_readback_parity_report`가 이를 `checked=True`, `stable=False`로 바르게 색출해 내는지 점검합니다.

### 📋 2. 스토리지 단언 및 필수 검증 (Raw Storage Assertions)

*   **런타임 패리티 리포트 유출 스캔 (Quarantine Key Assertion)**:
    - [ ] direct SRT 및 roughcut 로드/저장 루프를 3회 이상 실행한 후, 생성된 `.aissproj` 저장 파일을 직접 파싱하여 런타임 보고서용 임시 키인 `_nle_snapshot_readback_parity` 가 완전히 strip 되었음을 단언(`self.assertNotIn`)합니다.
*   **자막 상태 메트릭 보존**:
    - [ ] open/restore 시점 직후 `invalid_duration_count = 0`, `overlap_count = 0`, `max_active_segments <= 1` 상태가 엄격하게 깨지지 않는지 assert.

### 🎯 3. 집중 검증 명령 셋 (Focused Pytest & Audit Commands)

*   **로컬 타겟 테스트 실행**:
    ```bash
    QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -v \
      tests/test_project_nle_snapshot.py \
      tests/test_project_nle_persistence_guard.py \
      -k "direct_srt or roughcut or sidecar or parity"
    ```
*   **지연시간 및 성능 오버헤드 측정**:
    - [ ] `perf_counter`를 활용하여 direct SRT open 및 roughcut restore 시 스냅샷 패리티 비교 루프가 로딩 성능에 주는 오버헤드(`elapsed_ms`)를 측정하고 기록용 로그에 반영하는 증적 제출.
