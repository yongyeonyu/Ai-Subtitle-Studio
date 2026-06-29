DEX_REVIEW_READY
SCOUT_ID=20260629-154450

### Screenplay Composer 관점 추가/수정 기능 설계안
1. **대본 계층 구조화 (Sequence/Scene/Beat/Dialogue)**
   - 중분류 카드를 대본의 Sequence > Scene > Beat > Dialogue/Action 계층에 매핑하고, 설정박스 내에 '씬 목적(Cut purpose)' 및 '비트 성격' 분류 필드를 지원합니다.
2. **샷 어셈블리 및 아웃라인 (Shot Assembly & Script Outline)**
   - 대본 목차(Script Outline) 패널을 좌측 트리 뷰로 구현하고, 트리 항목 클릭 시 2D 시나리오 캔버스의 매칭 노드로 화면이 즉시 포커스 스크롤되도록 연동합니다.
3. **연속성 및 B-roll/대체 테이크 (Continuity, Alternate Takes & B-roll/Insert/Reaction)**
   - 씬 카드 내에 주영상(A-roll) 외에 B-roll, 인서트, 리액션 샷을 레이어 구조로 할당하여 연속성(Continuity)을 시각화합니다.
   - 동일 구간에 대해 복수의 촬영본(Alternate takes)이 존재할 경우 카드 내 스위처를 통해 손쉽게 전환할 수 있도록 구조화합니다.
4. **누락/갭 감지 및 감독 메모 (Missing Shot/Gap Detection & Director Note)**
   - 자막이 비어 있거나 오디오 신호가 없는 갭(Gap) 구간을 자동 스캔하여 적색 빈 슬롯 플레이스홀더 카드로 캔버스 상에 노출합니다.
   - 각 카드마다 연출 지시사항을 기록할 Director Note 메모 필드와 변경 기록(Revision History) 저널링을 탑재합니다.
5. **테이블 리드 프리뷰 (Table-read Style Preview)**
   - 비디오 없이 대본 형식의 텍스트 스크롤 뷰어 형태로 시나리오 조립본을 순서대로 읽고, 스크롤 플레이헤드를 비디오 프레임 시간대와 2D 싱크 연동하여 추적합니다.

### UI/UX & 데이터 흐름 Risk
- **대형 아웃라인 연산 성능**: 대본의 계층이 깊어지고 자막 수천 개가 결합되면 대본 뷰어와 아웃라인 트리의 렌더링 성능이 하락할 수 있어 비동기 레이아웃 생성 모델이 필수적입니다.
- **Shot-to-subtitle Authority Guard**: 대본 재조립 연산 시 자막의 시간 경계가 어긋나거나 중첩되지 않도록, NLE Commit Boundary 진입 전에 타임코드 충돌 및 자막 무결성 규칙을 선제 검사해야 합니다.

### validation checklist
- [ ] 대본 아웃라인 트리 항목 클릭 시 2D 캔버스의 노드 카드로 부드럽게 화면 이동이 유기적으로 이루어지는지 검증
- [ ] Gap 감지기가 타임라인 내 자막/영상 공백 구간을 ms 단위로 정확히 찾아내어 적색 Placeholder 카드로 시각화하는지 정밀도 검증
- [ ] Alternate take 전환 스위치 작동 시, 메모리 상의 대상 클립 영상 정보가 즉시 갱신 및 재생 싱크와 맞물리는지 검증
- [ ] 테이블 리드 뷰어의 텍스트 줄바꿈 및 스크롤 추적 시 플레이헤드 싱크와 2D 오차가 없는지 프레임 정밀도 측정
- [ ] 저장 및 재로딩 시 대본 구조, 감독 메모, B-roll 레이어 및 Alternate take 선택 상태가 프로젝트 json 스키마에 안전하게 영속화되는지 검증

### do-not-touch list
- [ ] QML/OpenGL 기반의 가속 대본 렌더링 엔진 차단 (순수 2D PyQt GUI 유지)
- [ ] 최종 자막 권한 트랜잭션 관리자 및 STT/VAD 음성 처리 모듈
- [ ] 프로젝트 세이브(.json) 파일 포맷 파서 하위 호환성 레이어

### verdict
- 2D-only UI 원칙을 엄격하게 지키고, 대본 조립 데이터와 자막 데이터의 동기화 무결성을 지킬 Shot-to-subtitle guardrail이 전제된다면 본 대본 지향 컷 조립 계획안은 안전하게 구현 가능(Ready to active)합니다.
