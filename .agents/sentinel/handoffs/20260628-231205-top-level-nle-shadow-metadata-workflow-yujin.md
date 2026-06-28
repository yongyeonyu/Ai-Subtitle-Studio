DEX_REVIEW_READY
역할: 유진
범위: AI Subtitle Studio top-level nle workflow review
읽은 파일:
- docs/project_reference/PRODUCT_README.md
- docs/nle_engine/NLE_Action.md
결론: Top-level NLE 페이로드를 오너 승인형 섀도우 메타데이터(Shadow Metadata)로 저장할 때 적용할 편집 워크플로우 가이드를 마련했습니다.

*   **프로젝트명**: AI Subtitle Studio
*   **저장소 루트**: `/Users/u_mo_c/Downloads/ai_subtitle_studio`

---

### 🎨 1. 사용자 경험 및 워크플로우 체크포인트 (Workflow Checkpoints)

*   **비가시적 백그라운드 인프라 (Invisible Infrastructure)**:
    - [ ] `nle_snapshot`을 디스크에 쓰는 동작이 파일 세이브(`.aissproj` 쓰기) 시 디스크 입출력 병목을 가져와 UI 프레임을 저하시키거나 세이브 지연(lag)을 초래하지 않는가?
    - [ ] 패리티 오류 감지 시 백그라운드에서 오프라인 자막으로 조용하고 안전하게 복구(fallback)되어 사용자가 데이터의 뒤틀림이나 유실을 인지하지 않는가?
*   **Direct SRT & Roughcut 내보내기 안정성 (Precedence & Export)**:
    - [ ] 섀도우 메타데이터가 적용된 프로젝트 로드 하에서도 단독 SRT 파일 열기 시 기존 `srt_timing_text_wins` 우선권이 정상적으로 작동하여 SRT 자막 정보가 변경 없이 복원되는가?
    - [ ] 러프컷 EDL 내보내기(Export) 실행 시 NLE 스냅샷에 기록된 컷 경계가 왜곡 없이 그대로 EDL 및 렌더 플랜에 동기화되는가?

### ⚠️ 2. UI 변경 금지 및 개별 승인 대상 격리 (UI Boundary)
*   **경고 다이얼로그 및 시각적 위젯 추가 금지**:
    - 스냅샷 패리티 감지에 관한 경고 상태 표시 위젯이나 에러 팝업창을 마음대로 추가하는 것은 대표님 승인 없는 UI/UX 변경에 해당합니다.
    - 패리티 가드의 보고서 내역은 철저히 **디버그 로그 수준으로 격리**하며, 유저 대면(User-facing) UI 변경이 필요할 시 반드시 구현 이전에 대표님의 개별 승인 트랙으로 다룹니다.
