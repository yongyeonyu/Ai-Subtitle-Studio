DEX_REVIEW_READY
역할: 한결
범위: AI Subtitle Studio top-level nle architecture review
읽은 파일:
- core/project/project_format.py
- core/project/nle_persistence_guard.py
- core/project/project_io.py
결론: Top-level NLE 페이로드를 오너 승인형 섀도우 메타데이터(Shadow Metadata)로 저장하기 위한 차기 아키텍처 가이드라인을 작성했습니다.

*   **프로젝트명**: AI Subtitle Studio
*   **저장소 루트**: `/Users/u_mo_c/Downloads/ai_subtitle_studio`

---

### 🛡️ 1. canonical load owner 보존 및 저장 아키텍처 경계
*   **보조 데이터(Shadow Metadata) 격리 원칙**:
    - 파일에 저장되는 `nle_snapshot`은 어디까지나 호환성 및 패리티 검증용 보조 데이터(Shadow metadata)이며, 로드 시점의 canonical load owner가 되어서는 안 됩니다. 
    - 여전히 레거시 자막 구조(`editor_state.segments`)를 유일한 로드 오너(Single Source of Truth)로 격리하여 둡니다.
*   **런타임 잔여물 오염 방지 (Leak Control)**:
    - 런타임 전용 인프라인 `_nle_project_state`와 패리티 검증 리포트(`_nle_snapshot_readback_parity`)가 직렬화 필터인 `nle_persistence_guard.py`를 우회하여 실제 저장소 장치(`.aissproj`)로 유출되어 오염시키는 아키텍처적 위협을 철저히 제어해야 합니다.

### 🧩 2. 최소 안전 설계 및 롤백 (Fallback Design)
*   **결함 격리 및 자가 복구 (Graceful Fallback)**:
    - 파일에서 복구된 `persisted_nle_snapshot`의 구조가 깨져있거나(JSON syntax), 런타임에 빌드된 `fresh_snapshot`과의 시간/텍스트 정합성 비교에서 드리프트(drift)가 감출될 경우:
    - 시스템 예외나 크래시를 내지 않고 섀도우 메타데이터를 즉각 무시(discard/quarantine)하며, 신뢰할 수 있는 레거시 자막 데이터를 우선 삼아 NLEProjectState를 무중단 재건(Rebuild)하는 복구 루틴을 공고히 해야 합니다.
*   **스키마 안전 장치**:
    - `PROJECT_SCHEMA_VERSION = "04.01.00-nle"` 등으로 버전을 명확히 표기하여, 구버전 런타임이 이 새로운 섀도우 필드를 마주하더라도 오류 없이 무시하고 기존 파서로 올바르게 파싱하도록 하위 호환성을 보장해야 합니다.
