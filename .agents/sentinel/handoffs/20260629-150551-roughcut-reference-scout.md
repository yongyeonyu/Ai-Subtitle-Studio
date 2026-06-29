DEX_REVIEW_READY
SCOUT_ID=20260629-150551

### 분석 레퍼런스 대상 및 벤치마킹 포인트
1. **Obsidian Canvas & Figma FigJam (2D 노드 그래프 / 화이트보드)**
   - **영감 포인트**: 2D 무한 캔버스 위에 텍스트 카드(노드)를 자유롭게 배치하고, 커넥터(선)로 관계 및 흐름을 연결하는 직관적 레이아웃.
   - **G4 적용**: 중분류 세그먼트 카드를 2D 노드로 시각화하고, 시나리오 진행 순서를 화살표 커넥터로 연결하여 전체 시나리오 흐름을 시각적으로 파악하도록 구성.
2. **Scrivener Index Card & Trello (스토리보드 / 칸반)**
   - **영감 포인트**: 시나리오의 씬(Scene)을 개별 인덱스 카드로 카드화하여, 카드 순서를 재배치하면 전체 글/시나리오 구성 순서가 동기화되어 재조립되는 흐름.
   - **G4 적용**: 러프컷 에디터에서 세그먼트 카드의 위치를 물리적으로 드래그 앤 드롭하여 재정렬(Reordering)하면 메인 에디터의 자막 타임라인 구조와 길이가 실시간 동기화되는 NLE Sync 모델의 기초로 활용.
3. **DaVinci Resolve Storyboard Mode (NLE Bin / Storyboard)**
   - **영감 포인트**: 미디어 클립을 타임라인이 아닌 스토리보드 형태의 썸네일 카드로 나열하고 각각의 인/아웃 포인트를 시각적으로 트림 조절하는 구조.
   - **G4 적용**: 노란색 비디오박스 내에 컷의 대표 프레임 썸네일을 표시하고, 카드 상에서 직접 길이를 줄이거나 트림할 수 있는 인터페이스 차용.

### UI/UX & 데이터 흐름 Risk
- **2D-only 규칙 준수**: 캔버스의 확대/축소(Zooming) 및 드래그 스크롤 구현 시, 하드 룰에 맞춰 WebGL이나 OpenGL 3D 기법을 일절 배제해야 합니다. 오직 PyQt6 `QGraphicsView`의 CPU 기반 2D Transform 및 `QPainterPath` 렌더링으로 최적화하여 1000개 이상의 자막 노드가 렌더링될 때의 FPS 저하를 방지해야 합니다.
- **레이아웃 꼬임**: 노드 재배치 시 커넥터 라인들이 복잡하게 얽히는 현상(Spaghetti code style UI)을 막기 위해, 기본적인 격자 정렬(Grid snapping) 및 위상 정렬(Topological sort) 기반 자동 배치 알고리즘이 보조적으로 지원되어야 합니다.

### G4 계획 반영 문구 (action item wording)
- "G4. Reference-driven 2D Node Layout and Segment Card Storyboarding"
  - Obsidian Canvas 및 Scrivener의 카드 지향 재조립 개념을 벤치마킹하여, PyQt6 2D GraphicsView 환경 하에 세그먼트 카드 정렬 및 노드 인터페이스 레이아웃을 구현합니다.
  - 마우스 드래그 기반 격자 스냅 및 자동 커넥터 라우팅 엔진을 2D-only 환경에서 순수 수학적 좌표 계산을 통해 설계합니다.

### validation checklist
- [ ] Obsidian Canvas 스타일의 노드 연결 상태 시각화 및 커넥터 렌더링 성능 검증 (OpenGL/QML 호출 전무함 검증)
- [ ] 마우스 드래그 앤 드롭을 통한 세그먼트 카드 순서 재조립 및 그리드 스냅 정상 작동 확인
- [ ] 카드가 100개 이상 배치된 대형 프로젝트 캔버스에서 Zoom In/Out 및 패닝(Panning) 시 프레임 유지력(최소 30 FPS 이상) 검증
- [ ] 노드 연결선(Connector) 드로잉 시 순수 `QPainter`만을 사용해 라인과 화살표 머리가 깨짐 없이 부드럽게 그려지는지 검사

### do-not-touch list
- [ ] OpenGL 가속 레이어, QML WebEngine 뷰어 등 3D 및 웹 가속 기반 렌더링 모듈 도입 절대 차단
- [ ] 타임라인 자막 트랜잭션 코어 모듈 및 STT/VAD 음성 인식 백엔드

### verdict
- 제안된 벤치마킹 레퍼런스는 하드 룰(2D-only) 범주 내인 PyQt6 `QGraphicsView` 기술 셋으로 충분히 커버가 가능하며, 러프컷의 스토리보드 조립 UX 사용성을 극대화하므로 안전하게 추진 가능(Ready to active)합니다.
