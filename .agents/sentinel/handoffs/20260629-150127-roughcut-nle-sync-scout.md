DEX_REVIEW_READY
SCOUT_ID=20260629-150127

### UI/UX & 데이터 흐름 Risk
- UML 스타일의 노드/커넥터 구조를 PyQt6 GUI 상에 구현할 때, AGENTS.md의 Hard Rules에 명시된 '자막 에디터 상호작용 표면은 2D-only' 규칙을 반드시 준수해야 합니다. QML, OpenGL/Metal 기반의 3D 렌더링 도입은 엄격히 차단되며, 오직 PyQt6의 2D QGraphicsView/QPainter를 통해서만 안전하게 구현되어야 합니다.
- 자막/시나리오/길이 재조립 시 메인 에디터 타임라인의 전체 타임스탬프 일관성이 깨질 위험이 크므로, NLE Mutation 작업 시 트랜잭션 단위 롤백 제어가 동반되어야 합니다.

### action item wording
- "G4. Roughcut Editor NLE Sync & 2D UML-style Segment Nodes"
  - 러프컷과 메인 에디터 간의 자막, 시나리오 순서, 세그먼트 길이 조정 데이터를 NLE 데이터 구조로 연동 및 즉각 양방향 전파를 설계합니다.
  - 중분류 세그먼트 카드를 PyQt6 2D QGraphicsView/QPainter 기반의 UML node 및 connector 방식으로 렌더링하고 레이아웃 흐름을 동기화합니다.

### validation checklist
- [ ] 메인 에디터 자막 수정 시 러프컷 세그먼트 카드 내의 텍스트가 정상 전파 및 즉시 반영되는지 검증
- [ ] 러프컷 세그먼트 순서 변경(Reordering) 및 길이 트림 시 메인 에디터 자막 구조가 정상 재배치되는지 무결성 검증
- [ ] UML 노드/커넥터 렌더링 시 QML/OpenGL 가속이 아닌 순수 PyQt6 2D GraphicsView API만 사용되었는지 소스 검증
- [ ] 대용량 프로젝트(자막 1000개 이상) 로드 상태에서 노드 그래픽 렌더링의 FPS 저하 및 메모리 누수 발생 여부 스트레스 테스트
- [ ] NLE 데이터 동기화 동작 중 자막 타임코드 간 중첩(Overlap)이나 꼬임 현상이 발생하는지 검증

### do-not-touch list
- [ ] QML SceneGraph, OpenGL/Metal-backed UI surface 및 3D 렌더링 라이브러리 도입 차단
- [ ] STT1/STT2 및 VAD 핵심 자막 분석/정밀도 향상 모듈
- [ ] 타임라인 최종 자막 권한(Final Subtitle Authority)의 핵심 트랜잭션 관리 커널

### verdict
- 하드 룰인 2D-only UI 원칙을 위배하지 않는 설계(PyQt6 QGraphicsView 기반)를 유지하고 NLE Sync 무결성 보장을 위한 롤백 기능이 전제된다면, 본 요구사항은 안전하게 구현 가능(Ready to active)합니다.
