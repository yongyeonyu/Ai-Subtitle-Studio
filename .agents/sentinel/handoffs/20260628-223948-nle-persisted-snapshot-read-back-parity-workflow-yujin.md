DEX_REVIEW_READY
역할: 유진
범위: AI Subtitle Studio NLE persisted snapshot read-back parity workflow review
읽은 파일:
- docs/project_reference/PRODUCT_README.md
- docs/nle_engine/NLE_Action.md
결론: NLE 스냅샷 패리티 도입 과정에서 사용자 편집 흐름과 기존 데이터 접근 안전성을 보존하기 위한 워크플로우 체크포인트를 구성했습니다.

### 🎨 1. 편집 워크플로우 체크포인트 (Workflow Checkpoints)

*   **무장애 저장/재오픈 (Zero-Friction Save/Reopen)**:
    - [ ] 패리티 검증(Parity checking) 및 복구 로직이 작동하는 도중 사용자에게 불필요한 지연(lag)이나 "응답 없음" 현상이 전혀 없으며 백그라운드에서 투명하게 완료되는가?
    - [ ] 검증 시 사소한 편차가 발생하더라도 자막 데이터 손실이나 강제 종료 없이, 자동으로 레거시 원본 행을 기준으로 화면을 즉각 리빌드하여 사용자가 느끼는 끊김이 없는가?
*   **Direct SRT 우선권 보존 (Direct SRT Flow Integrity)**:
    - [ ] 사용자가 프로젝트 파일이 아닌 단독 SRT 파일을 직접 열어 편집할 때, 런타임 NLE 스냅샷 검증이 작동하더라도 SRT에 기재된 텍스트 및 시간 정보가 100% 우선순위로 로드되며 변형되지 않는가?
*   **러프컷 EDL 호환성 (Roughcut EDL Integrity)**:
    - [ ] 러프컷 EDL 파일 또는 `_render_plan.json`을 복구하는 과정에서 타임라인 마커와 자막 세그먼트 스냅 위치가 기존 작업물과 한 프레임의 오차도 없이 동일하게 배치되는가?

### ⚠️ 2. 승인 필요 UI 변경 격리 (UI Changes Requiring Approval)
*   **패리티 경고 UI 분리**:
    - 패리티 에러 발생 시 로그 기록 외에 상태 바(Status Bar)에 경고 텍스트를 출력하거나 경고 팝업 다이얼로그를 제공해야 하는 경우가 있다면, 이는 기존 UI/UX 변경에 해당하므로 **구현 전에 대표님의 명시적 승인을 구하도록 설계 및 구현 범위에서 별도 격리**해 두어야 합니다.
