DEX_REVIEW_READY
SCOUT_ID=20260629-151426

### UI/UX & 데이터 흐름 Risk
- **데이터 유실 위험**: 사용자가 설정박스 내 필드(주제, 태그, 요약 텍스트)를 편집하다가 다른 노드를 선택(Selection change)할 때 변경 사항이 커밋되지 않고 날아가는 포커스 유실 위험이 높습니다. Selection 변경 이벤트 핸들러에서 임시 데이터의 Auto-commit 혹은 Dirty 감지 후 팝업 경고 등의 예방 장치가 필수적입니다.
- **타임코드 변조 위험**: 설정박스 내에 표시되는 시간/길이(Duration) 정보 필드를 실수로 편집하게 허용하면 자막 경계의 무결성이 붕괴하므로, 시간 정보 필드는 엄격하게 Read-only(QTextEdit/QLineEdit readOnly=True 또는 QLabel)로 제약해야 합니다.

### G4 계획 반영 문구 (action item wording)
- "G4. Settings Box Sub-component and Metadata Editor Panel"
  - 빨간색 설정박스(Settings Box) 영역 내에 선택된 중분류 세그먼트 카드의 상세 속성(요약 내용, 시작/종료 시간 및 길이, 주제, 태그 목록)을 렌더링하는 UI 컴포넌트를 설계합니다.
  - 주제(QComboBox / QLineEdit) 및 태그(QTextEdit / Chip editor) 입력 필드 구현 및 변경 사항 발생 시 Dirty state 감지기 및 selection-change 기반 자동 커밋 루틴을 개발합니다.

### validation checklist
- [ ] 노드 카드 선택 변경 시 설정박스의 상세 필드 내용들이 올바르게 갱신(Binding)되는지 검증
- [ ] 설정박스 내의 데이터(주제/태그 등) 수정 도중 노드 선택을 바꿨을 때 자동 저장이 누락 없이 작동하는지 검증
- [ ] 시간/길이 정보 표시 필드가 비활성화(Read-only) 상태로 키보드 입력이 차단되어 있는지 검증
- [ ] 비정상적인 포커스 아웃(앱 포커스 아웃 등) 상태에서도 편집 중이던 임시 데이터가 유실되지 않는지 강제 종료 테스트
- [ ] 저장 및 재로딩 시 설정박스에서 수정한 주제/태그 메타데이터가 프로젝트 세이브 파일에 정확하게 영속화되는지 검증

### do-not-touch list
- [ ] 세그먼트 시간/타임스탬프 정보의 강제 오버라이트 편집 입력기 차단
- [ ] STT/VAD 분석 모듈 및 최종 자막 무결성 관리자
- [ ] 세이브 포맷(.json)의 코어 자막 레코드 필드 구조

### verdict
- 제안된 상세 필드 및 PyQt6 컴포넌트 구성은 기존 NLE 아키텍처 및 2D-only UI 원칙을 침해하지 않으며, 포커스 아웃/Selection 변경 시점의 Auto-commit 메커니즘을 동반하면 안전하게 구현 가능(Ready to active)합니다.
