DEX_REVIEW_READY
역할: 한결
범위: AI Subtitle Studio owner-approved persisted NLE cutover architecture scout
읽은 파일:
- docs/nle_engine/NLE_Action.md
- docs/ARCHITECTURE.md
- core/project/nle_persistence_guard.py
- core/project/project_format.py
- core/project/project_manager.py
결론: Persisted NLE 디스크 필드 적용을 위한 최소 안전 슬라이스(Minimum Safe Slice) 아키텍처 제안을 구성했습니다.

### 🧩 1. Minimum Safe Slice (최소 안전 슬라이스 제안)
Persisted NLE 데이터를 한 번에 프로젝트 파일 전체에 적용하는 것은 위험합니다. 따라서 단계적인 점진적 컷오버(Cutover) 방식을 제안합니다.

*   **Slice 01: 읽기 전용 저장 구조 정의 및 Persistence Guard**
    - `core/project/project_format.py`에 신규 NLE 스키마 정의 (`nle` 및 `nle_snapshot` 필드)하되, 쓰기(Write) 동작을 수행할 때 빈 구조 또는 기본 플레이스홀더 데이터만 기록합니다.
    - 기존 레거시 `cached_segments` 저장 로직은 100% 동일하게 유지합니다.
*   **Slice 02: NLEProjectState 복구(Hydration) 구현**
    - 저장 장치에서 프로젝트를 열 때, 프로젝트 내 `nle` 스키마가 존재하면 이를 바탕으로 `NLEProjectState`를 온전히 복구하고, 존재하지 않으면 레거시 `cached_segments`를 NLE snapshot 형식으로 자동 변환해 주는 복구 로직 구현.
*   **Slice 03: 가역 쓰기 활성화 및 이중 쓰기(Dual-Write) 검증**
    - 편집 이벤트가 발생할 때 `NLEProjectState`를 직렬화(serialize)하여 프로젝트 파일 내 `nle` 필드에 실제로 쓰기 시작하되, 유저가 수동 롤백하거나 에러를 낼 경우 `cached_segments` 레거시 자막 데이터를 우선 신뢰하도록 강제하는 스위치 가드 장착.

### 🛡️ 2. 아키텍처 가이드 및 위험 완화 (Mitigation)

*   **레거시 호환성 및 롤백 (Legacy Compatibility & Rollback)**:
    - 만약 새로 도입된 NLE 직렬화 데이터가 깨지거나 불일치할 경우, 프로젝트 파일 파서가 이를 안전하게 버리고 레거시 데이터로부터 NLEProjectState를 재생성하는 자동 자가 복구(auto-recovery) 아키텍처를 `core/project/nle_persistence_guard.py`에 확립해야 합니다.
*   **오너쉽 맵 (Owner-Map & State Contention)**:
    - 편집기가 활성화되어 있을 때, 타이밍의 원천 정보 오너십은 메모리 상의 `NLEProjectState`가 가지며, 파일 저장(`.aissproj`) 시점에는 이 메모리 상태를 최종 스냅샷하여 저장 장치에 전달합니다. 메모리 오너십과 저장 오너십 간의 시점 동기화를 위해 트랜잭션 락(Transaction lock) 구조가 유지되어야 합니다.
*   **저장 스키마 버전 분리 (Storage Schema Versioning)**:
    - `PROJECT_SCHEMA_VERSION = "04.01.00-nle"` 형태로 서브 버전을 식별하게 하여 구버전 파서가 이를 감지했을 때 안전하게 대체 모드로 동작하도록 안전 마진을 마련해야 합니다.
