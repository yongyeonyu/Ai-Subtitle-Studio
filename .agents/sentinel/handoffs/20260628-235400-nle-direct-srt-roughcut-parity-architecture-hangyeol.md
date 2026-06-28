DEX_REVIEW_READY
역할: 한결
범위: AI Subtitle Studio NLE direct SRT/roughcut read-back parity architecture review
읽은 파일:
- core/project/nle_snapshot.py
- core/project/project_io.py
- ui/editor/editor_project_open_native.py
- ui/roughcut/roughcut_state.py
- ui/roughcut/roughcut_export.py
결론: Direct SRT 오픈 및 Roughcut sidecar 복구 영역으로 패리티 가드(read-back parity guard)를 확장할 때 적용해야 할 아키텍처 리스크 제어 및 최소 안전 설계를 구성했습니다.

### 🛡️ 1. 구조적 경계 및 리스크 (Architectural Risks)

*   **Direct SRT Precedence 침해 (우선권 침해 리스크)**:
    - `srt_timing_text_wins` 계약이 최우선이므로, direct SRT open 시 스냅샷 패리티 가드 연산이 SRT 파싱 데이터의 내용이나 타임스탬프를 임의로 덮어쓰거나 오염(pollute)시키지 않는 상태 오너십 구조를 강제해야 합니다.
*   **런타임 전용 리포트 유출 (Data Leak Risk)**:
    - 패리티 비교 결과로 생성되는 `_nle_snapshot_readback_parity` 보고서는 순수 메모리 상의 런타임 전용 데이터입니다.
    - 이 키가 파일 저장 전 정화(sanitize) 단계인 `project_io._project_payload_for_disk` 또는 `nle_persistence_guard`에서 안전하게 제거(strip)되지 않으면, 불필요한 메타데이터가 `.aissproj` 디스크 파일에 영구 기록되어 스키마를 오염시키는 아키텍처 결합이 발생합니다.
*   **러프컷 EDL 및 EDL 스키마 버전 분리 (Schema Contention)**:
    - roughcut sidecar 복구 시, `_render_plan.json` 및 `_edl.json` 등 NLE 렌더 플랜 내의 복잡한 EDL 메타데이터와 NLE snapshot 간의 정렬이 어긋날 때, 무조건 로드를 차단하기보다 무해한 로깅(Warning-only) 수준으로 롤백 경로를 격리해야 합니다.

### 🧩 2. 최소 안전 설계 제안 (Minimum Safe Architecture)

*   **동기식 로드 순서의 격리 (Load Order Gating)**:
    - **Step 1**: direct SRT 오픈 또는 roughcut 복구가 수행되어 최종 자막 행(`editor_state.segments`)이 메모리에 완전히 정착됩니다.
    - **Step 2**: 이 확정된 자막 행을 canonical owner로 인식하여 `fresh_snapshot`을 런타임에 빌드합니다.
    - **Step 3**: 파일에 보존되어 있던 `persisted_snapshot`이 존재하는 경우에만 두 스냅샷 간의 패리티 일치성을 비교하여 런타임 리포트를 작성합니다. (만약 persisted_snapshot이 없는 SRT 단독 오픈 시에는 검증을 조용히 skip하여 `checked=False` 처리)
*   **런타임 전용 키 필터링 (Filter-out Guard)**:
    - 저장 파이프라인(`build_storage_project_payload` 및 `_project_payload_for_disk`) 내의 `_PROJECT_RUNTIME_KEYS` 리스트에 `_nle_snapshot_readback_parity`를 강제 추가하여, 디스크로 방출되기 전 100% 필터링(strip)되는 메모리 격리 장치를 공고히 해야 합니다.
