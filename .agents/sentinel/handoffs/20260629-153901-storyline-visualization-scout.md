DEX_REVIEW_READY
SCOUT_ID=20260629-153901

### 분석 레퍼런스 및 적용 모델
1. **Plottr (Subway-map Visual Timeline / Storyline)**
   - **벤치마킹**: 스토리의 캐릭터 궤적이나 테마(Plot line)를 가로축 시간에 따라 노선도 형태로 시각화하는 방식.
   - **G4 적용**: 중분류 세그먼트 카드를 주제, 주요 인물, 또는 자막 톤에 따라 병렬 궤적(Plot lines)으로 배치하여 교차 편집 흐름을 한눈에 보여주는 2D 지하철 노선도 형태의 타임라인을 제공.
2. **Scrivener Index Card Flow (Index Card Grid/Flow)**
   - **벤치마킹**: 카드의 표면에 핵심 로그라인(Logline) 및 요약 시놉시스를 배치하여 전체 플롯 흐름을 텍스트와 레이아웃으로 동시에 추적하는 방식.
   - **G4 적용**: 각 세그먼트 카드 내부에 LLM이 추출한 대표 로그라인(요약 줄거리)을 시각적으로 결합하여 직관성을 극대화.

### UI/UX & 데이터 흐름 Risk
- **레이아웃 꼬임 및 성능 저하**: 노선도 형태의 스토리라인(Plot lines)을 수많은 노드 사이에 드로잉할 때, 노드 수가 50개 이상만 되어도 선이 꼬여 spaghetti UI가 될 위험이 있습니다. 최단 경로 라우팅 계산 및 격자 스냅(Snapping) 가이드가 필수적입니다.
- **2D-only UI 원칙 준수**: 복잡한 노선도와 줌 기능 렌더링에 QML, OpenGL 또는 3D 캔버스를 도입하려는 유혹을 피하고, 오직 PyQt6 `QGraphicsView`의 CPU 2D 좌표 변환만 사용하여 렌더링 부하를 제어해야 합니다.

### G4 계획 반영 문구 (action item wording)
- "G4. Scenario Storyline Visualization and Subway-map Timeline"
  - Plottr의 지하철 노선도(Subway-map) 스타일 벤치마킹을 통해, 중분류 세그먼트 카드를 테마/인물별 병렬 궤적의 2D 스토리라인 타임라인으로 시각화하는 PyQt6 뷰를 설계합니다.
  - 각 세그먼트 카드 내부에 로그라인(요약)을 삽입하는 2D 템플릿과 2D 캔버스 내에서의 노선 경로 연산 모듈을 구축합니다.

### validation checklist
- [ ] 2D QGraphicsView 내에서 노선도 및 화살표 커넥터가 겹침 없이 부드럽게 그려지는지 레이아웃 가시성 검증
- [ ] 스토리라인 캔버스 드래그 패닝(Panning) 및 줌인/줌아웃 시 프레임이 30 FPS 밑으로 떨어지지 않는지 드로잉 부하 테스트
- [ ] 노드 내 텍스트 로그라인이 영역을 벗어나지 않고 엘립시스(...) 처리로 깔끔히 정렬되는지 확인
- [ ] 저장 및 재로딩 시 연습노트별 스토리라인 배치 상태와 궤적 메타데이터가 정상 영속화되는지 검증
- [ ] 구버전 세이브 파일 로드 시 예외 크래시 방지 및 기본 1개 단일 라인으로의 안전한 마이그레이션 확인

### do-not-touch list
- [ ] QML SceneGraph, OpenGL/Metal 가속 뷰어 등 3D 드로잉 라이브러리 도입 금지
- [ ] 최종 자막 결정 모델 및 코어 데이터 모델
- [ ] STT/VAD 음성 분석 엔진

### verdict
- 복잡한 3D 가속 없이 PyQt6 2D GraphicsView를 유지하고, 선 꼬임 방지를 위한 격자 및 최단 경로 스냅 규칙이 구현된다면 본 줄거리 시각화 계획안은 안전하게 추진 가능(Ready to active)합니다.
