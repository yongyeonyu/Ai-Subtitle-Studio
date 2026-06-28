DEX_REVIEW_READY
역할: 유진
범위: AI Subtitle Studio NLE direct SRT/roughcut read-back parity workflow review
읽은 파일:
- docs/project_reference/PRODUCT_README.md
- docs/nle_engine/NLE_Action.md
결론: Direct SRT 오픈 및 Roughcut sidecar 영역의 패리티 확장 도입 시 편집기 워크플로우 보존 체크포인트와 UI 변경 금지 범위를 수립했습니다.

### 🎨 1. 워크플로우 검증 체크포인트 (Workflow Checkpoints)

*   **무중단 데이터 머지 (Non-intrusive Metadata Merge)**:
    - [ ] 연결 프로젝트 메타데이터 머지(Linked project metadata merge) 또는 SRT 단독 로드 과정에서 패리티 계산 오버헤드로 인해 타임라인 캔버스 렌더링이 멈추거나(Frame drop) 반응성이 떨어지는 일이 없는가?
    - [ ] 패리티 연산 실패 시 데이터 강제 삭제나 유실 없이 레거시 자막을 진실의 원천으로 삼아 즉각 복구되는가?
*   **러프컷 재오픈/내보내기 일치 (Roughcut Reopen/Export Parity)**:
    - [ ] EDL 러프컷 내보내기(Export) 후 재오픈(Reopen)했을 때, 타임라인 트랙 상의 클립 범위와 자막 정합성이 패리티 가드로 인해 밀리거나 비정상 스냅되는 현상(jitter)이 발생하지 않는가?

### ⚠️ 2. UI 변경 금지 및 오너 승인 범위 (UI Change Isolation)
*   **패리티 이상 알림 UI 추가 전면 보류**:
    - 패리티 가드 결과 불일치가 검출되었을 때, 이를 에디터 화면에 시각적으로 표시하기 위한 새로운 경고 아이콘, 로딩 스피너, 에러 팝업창 등을 추가하는 설계는 UI/UX 원형 보존 원칙에 위배됩니다.
    - 따라서 이상 징후 알림은 무조건 **디버그 로그 수준으로 격리**하며, 가시적인 UI 변경이 필요할 경우 반드시 구현 전 대표님의 개별 검토 및 최종 승인을 얻는 별도 승인 트랙으로 다룹니다.
