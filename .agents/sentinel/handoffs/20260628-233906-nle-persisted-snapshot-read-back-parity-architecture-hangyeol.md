DEX_REVIEW_READY
역할: 한결
범위: AI Subtitle Studio NLE persisted snapshot read-back parity architecture review
읽은 파일:
- core/project/nle_persistence_guard.py
- core/project/project_format.py
- core/project/nle_project_state.py
결론: Persisted snapshot과 Freshly rebuilt snapshot 간의 아키텍처 패리티 증명을 위한 최소 안전 설계안을 도출했습니다.

### 🛡️ 1. canonical load owner 승격 제어 및 상태 오너십 경계
*   **레거시의 진실의 원천(Single Source of Truth) 유지**:
    - 프로젝트 로드 시점에는 파일 내에 기록된 `nle_snapshot`을 주 오너(Canonical load owner)로 승격시키지 않습니다. 여전히 레거시 자막 행(`editor_state.segments`)이 진실의 원천입니다.
    - 파일에서 복구된 `persisted_nle_snapshot`은 오직 **오프라인 검증 및 일치성 비교용 섀도우(shadow) 소스**로만 격리되어 다루어져야 합니다.
*   **상태 격리 규칙 (Schema Isolation)**:
    - 런타임에 작동하는 `_nle_project_state`와 탑레벨 임시 `nle` 스키마가 직렬화 필터링 가드(`nle_persistence_guard.py`)를 우회하여 실제 저장소 장치에 불법적으로 영구 보존되는 경로가 완전히 차단되었는지 보장해야 합니다.

### 🧩 2. 최소 안전 설계 제안 (Minimum Safe Parity Design)
*   **비파괴적 패리티 가드 (Non-destructive Parity Guard)**:
    - **Step 1**: 프로젝트 오픈 시, 파일에서 로드한 레거시 자막 행을 기반으로 런타임에 `fresh_snapshot`을 새로 빌드합니다.
    - **Step 2**: 파일 내 보존되어 있던 `persisted_snapshot`과 메모리에서 재구축한 `fresh_snapshot` 간의 핵심 시그니처(자막 수, 텍스트 해시, rational fps 기반 시작/끝 프레임) 일치성을 검사합니다.
    - **Step 3 (핵심 롤백/복구)**: 만약 두 스냅샷 간에 패리티 드리프트(불일치)가 감지되었을 경우, 시스템을 크래시시키거나 사용자 데이터 로드를 중단하지 않고, **경고 메타데이터(`quarantine_drift_report`)를 런타임 객체에 바인딩한 뒤, 최신 레거시 자막 행을 기준으로 NLE 상태를 클린 리빌드(fallback & rebuild)**하도록 설계해야 데이터 안전성(safety)이 보장됩니다.
