DEX_REVIEW_READY
역할: 유진
범위: AI Subtitle Studio owner-approved NLE UI workflow scout
읽은 파일:
- docs/nle_engine/NLE_Action.md
- docs/ARCHITECTURE.md
- docs/project_reference/PRODUCT_README.md
결론: 대표님 승인에 따른 Taption UX 시나리오 대응을 위한 첫 번째 UI/NLE 구조 슬라이스를 제안합니다.

### 🎨 1. 제1차 UI/NLE 구조 슬라이스 제안 (First Recommended Slice)
타임라인 조작의 효율성과 가시적인 워크플로우를 보존하기 위한 첫 번째 UI 슬라이스는 **"자막 세그먼트 드래그 릴리스 시점의 NLE Commit 가드와 최종 오버레이 동기화"**입니다.

*   **구현 방향**:
    - 사용자가 타임라인에서 자막을 마우스로 드래그하는 도중에는 NLE 상태를 변경하지 않고 임시 UI 가이드만 그리며, 마우스를 릴리스(Release)하는 커밋 시점에만 단일 NLE 편집 연산(`caption_move` 또는 `caption_resize`)을 실행하여 이중 쓰기를 수행합니다.
    - 이를 통해 매 프레임마다 불필요한 NLE 유효성 검사 및 정렬 계산이 루프를 도는 현상을 방지하고, 화면 프리징(Freezing) 없는 매끄러운 60fps 드래그 조작 효율을 제공합니다.

### 🔍 2. 워크플로우 검증 기준 (Workflow Checkpoints)

*   **가시적 워크플로우 (Visible Workflow & UI Layout)**:
    - 대표님의 명시적 지시가 없는 한 타임라인의 트랙 색상, 마우스 커서 스타일, 팝업 메뉴 배치, 버튼 레이아웃은 기존 PyQt6 위젯 디자인을 철저히 고수합니다.
    - 드래그 중인 미확정 자막 세그먼트 가이드는 점선 혹은 반투명 가이드박스로 그리되, 비디오 뷰어 상의 실제 자막 오버레이(Final Overlay)는 드래그 릴리스가 일어나기 전까지 기존의 확정 자막 상태를 일관되게 렌더링해야 합니다.
*   **저장/재오픈 일관성 (Save/Reopen Continuity)**:
    - 드래그 및 크기 조절 후 단일 연산 커밋이 끝난 직후 저장(`.aissproj` 쓰기) 루틴이 호출되어도, 런타임 편집 상태와 직렬화된 파일 데이터 사이에 불일치가 존재하지 않아야 합니다.
*   **자막 경계 충돌 완화 (Collision & Magnet behavior)**:
    - 자막 이동이나 크기 조절 시 인접 자막과의 겹침(overlap)이 감지되면 Taption 규칙(인접 영역의 비파괴적 압착 또는 침범 금지 정책)에 따라 NLE 내부에서 충돌을 자동 계산해 교정하되, 사용자 워크플로우에서는 자막이 튕기거나 갑자기 사라지는 등 어색한 시각적 효과가 발생하지 않도록 부드러운 스냅 상태로 나타나야 합니다.
