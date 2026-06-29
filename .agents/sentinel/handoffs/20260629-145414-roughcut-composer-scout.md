DEX_REVIEW_READY
SCOUT_ID=20260629-145414

### UI draft risk
- 러프컷 내의 기존 UI 요소를 단순히 화면에서 숨김(hide) 처리할 때, 숨겨진 레이아웃이 잔존하여 4영역(흰색, 파란색, 노란색, 빨간색)의 고정 레이아웃 배치를 훼손하거나 UI가 깨질 위험이 있습니다. 완전히 layout flow에서 제외하거나 크기를 0으로 만드는 조치가 수반되어야 합니다.
- 색상 테마가 지정되었으나, 기존 AI Subtitle Studio의 다크 모드 및 브랜드 컬러 가이드라인을 어기지 않는 선에서 자연스러운 보더/배경 톤 조절이 필요합니다.

### action item wording
- "G4. Roughcut Scenario Composer Integration and Region Consolidation"
  - 러프컷(Roughcut) 레이아웃 내에서 기존의 개별 컨트롤러들을 정리하고, 4개의 핵심 박스(흰색: 시나리오박스, 파란색: 재료박스, 노란색: 비디오박스, 빨간색: 설정박스) 영역으로 역할을 고정합니다.
  - 시나리오 컷 편집 시 deterministic 규칙(컷 경계, 자막 매칭 기준)을 최우선으로 제공하고, LLM 연동은 시나리오 요약, 제목 추천 및 시나리오 제안 보조 역할에만 제한합니다.
  - 시나리오 생성 모드로 conservative, balanced, highlight 3가지의 후보 제안 알고리즘을 도입합니다.

### validation checklist
- [ ] 4대 영역(시나리오박스, 재료박스, 비디오박스, 설정박스)의 고정된 배경색/보더 및 영역 배치 정합성 확인
- [ ] 기존 러프컷 화면 컨트롤러들이 레이아웃에서 숨겨졌으나, 내부 시그널/슬롯 및 함수가 정상 보존되어 호출 시 오동작하지 않는지 확인
- [ ] deterministic 방식의 컷 후보 탐색 결과와 LLM 보조 결과의 UI 표시 및 합성 파이프라인 검증
- [ ] 시나리오 모드(conservative, balanced, highlight) 전환 및 각각의 시나리오 persistence 정상 작동 여부 검증
- [ ] 편집 이후의 최종 자막 export 및 세션 세이브 파일 무결성(기존 스키마 호환성) 검증

### do-not-touch list
- [ ] STT1, STT2, VAD 연동부 등 core 자막 분석 알고리즘
- [ ] 최종 자막 결정 권한(final subtitle authority) 제어 엔진 및 타임라인 편집 커밋 모델
- [ ] 프로젝트 세이브(.json) 스키마 중 기존 자막 데이터 구조 및 NLE 타임라인 데이터 구조 보존 상태
- [ ] 비디오 렌더러/플레이헤드 및 NLE Export Core 모듈

### verdict
- G4 Roughcut Scenario Composer 초안의 요구사항은 현재 NLE 아키텍처 및 자막 무결성 규칙을 위배하지 않으며 구현 가능한 수준입니다. 단, 기존 UI 요소의 hide 처리가 레이아웃 붕괴를 초래하지 않도록 QLayout 계층 구조에서 정교한 분리 제어가 필요하며, 이 조건이 지켜질 경우 승인(Ready to active) 판정을 내립니다.
