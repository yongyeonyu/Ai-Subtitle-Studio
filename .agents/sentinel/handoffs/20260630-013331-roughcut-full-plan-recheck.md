DEX_READY
SCOUT_ID=20260630-013331

### G4 Roughcut Scenario Composer Full-Plan Recheck Summary

---

### 1. G4 전체 계획 통합 검토 및 목표 부합성

1. **100% NLE 전환 및 응답성/최적화**:
   - `Final Cut Pro` (Magnetic Timeline), `DaVinci Resolve` (Cut Page), `Lightworks` (Database-centric Timeline)의 NLE 아키텍처를 벤치마킹하여, CPU 2D 뷰포트 클리핑 및 가벼운 Reference ID 기반 샌드박스 상태 관리를 계획하였습니다.
   - OpenGL/QML 3D 가속을 일절 차단하고 순수 PyQt6 2D GraphicsView/QPainter를 통한 초정밀 2D-only 렌더링 및 디바운싱 타이머로 60 FPS급 반응성 목표를 확립했습니다.
2. **에디터 ↔ 러프컷 양방향 Sync 및 Final Subtitle Authority**:
   - 편집 도중 자막 무결성 붕괴를 막기 위해, 러프컷 내의 모든 편집본은 `Roughcut state` (Sandbox) 내에 격리 관리됩니다.
   - 사용자가 '커밋/적용' 버튼을 명시적으로 클릭할 때에만 비로소 `Editor state` (최종 자막 결정 권한)로 타임코드가 병합(Commit Boundary)되며, 충돌/오버랩 감지 시 즉각 롤백(Rollback)되는 안전장치 가드를 수립했습니다.
3. **4대 박스 고정 역할 명확화**:
   - **흰색 (시나리오박스)**: 노드 카드를 드래그 조립하고 스토리라인 노선도를 확인할 무한 2D 캔버스.
   - **파란색 (재료박스)**: 추출된 컷 세그먼트 목록을 담는 Bin 패널.
   - **노란색 (비디오박스)**: 재생 및 실시간 썸네일을 표시할 미디어 프리뷰어.
   - **빨간색 (설정박스)**: 주제, 태그, 요약 텍스트 및 오버라이트 차단된 시간/길이 정보(Display-only) 편집 패널.
4. **연습노트 후보군 및 프로젝트 영속성**:
   - 복수의 조립 시나리오(연습노트 A/B)를 독립적인 Undo/Redo 이력과 함께 메모리에 유지합니다.
   - 프로젝트 저장 단위를 3대 도메인(`Editor`, `Roughcut`, `Shortform`)으로 구분하여 단일 JSON 루트 사전에 안전하게 영속화하고, 구버전 파일 로드 시 누락값 무해화(Null-safe parsing) 마이그레이션 모듈을 제공합니다.
5. **숏폼 Handoff 브릿지 및 스토리라인 시각화**:
   - `Plottr` (Subway-map timeline) 및 `Scrivener` (Logline grid flow)의 대본 지향 스토리보드 개념을 차용하여 병렬 궤적 노선도를 시각화합니다.
   - 숏폼 바구니(Basket)에 60.0초 시간 검증(60s Limit Validation) 실시간 게이지 바를 상시 노출하여 초과를 방지하고, 수직 크로핑 프레임 메타데이터와 함께 숏폼 스텁으로 무손실 핸드오프합니다.
6. **보안성 및 App Store Trace**:
   - 외부 LLM API 전송 시 개인정보 식별 정보(PII)를 제거하는 익명화 메타데이터 가공 파이프라인과 App Store sandbox 정책을 준수하는 익명화 로그 추적기 연동을 설계했습니다.

---

### 2. 안전한 단계별 구현 Phase 분할 계획

- **Phase 1: Foundation & Skeleton Layout (G4.1 ~ G4.2)**
  * 기존 UI 숨김 처리 및 4대 박스 2D PyQt6 레이아웃 뼈대 구축.
  * 2대 초기 시드(기본 시간순/LLM 추천 순서) 선택 스위처 UI 및 연습노트 데이터 스키마와 프로젝트 저장/불러오기(.json) 입출력 연동.
- **Phase 2: Storyboard & 2D Graphics Canvas (G4.3 ~ G4.5)**
  * PyQt6 2D GraphicsView 기반의 UML 노드/커넥터 렌더링 및 드래그 스냅 가이드.
  * 카드 순서 재조합(Reordering), 분할(Split) 및 드래그 병합(Merge) UI와 후보별 개별 Undo/Redo 메모리 스택 구현.
  * Plottr 노선도형 다중 스토리라인 시각화 캔버스 및 대본 트리 아웃라인 뷰.
- **Phase 3: Metadata Editor & Feedback Systems (G4.6 ~ G4.9)**
  * 설정박스 세부 필드(요약, 주제, 태그) 바인딩 및 관계 궁합 점수(비대칭/양방향) 편집 콤보박스 구현.
  * LoRA 피드백 데이터 로컬 수집기 및 PII 익명화 전송 API 가드 설계.
  * VAD RMS 오디오 에너지 기반 오프닝/엔딩(인트로/아웃트로) 추천 및 B-roll 레이아웃 표식 연동.
- **Phase 4: NLE Sync & Shortform Handoff Bridge (G4.10 ~ G4.12)**
  * `Roughcut state` 샌드박스로부터 명시적 적용 시점에 `Editor state`로 타임코드를 전사하는 'NLE Commit Boundary' 연산 및 Overlap/역전 감지 롤백 가드 완성.
  * 60초 초과 경고 게이지 가드 및 숏폼 9:16 프레이밍 오프셋 동봉 핸드오프 브릿지 완성.

---

### 3. 대표님께 질문할 불명확 항목 Top 5

1. **[Q2] Roughcut -> Editor commit timing**: 러프컷 조립 변경사항의 에디터 실제 반영 시점을 '적용/커밋' 버튼 클릭 순간으로 한정하는 샌드박스 정책이 맞으신가요?
2. **[Q3] Editor changes while roughcut has manual work**: 수동 조립 완료 후 에디터 자막 수정 시, 자막 내용은 갱신하되 요약/관계 점수/숏폼 후보는 자동으로 재생성하지 않고 Stale(만료) 표시로 제한하는 방식이 맞으신가요?
3. **[Q6] Split through an active subtitle row**: 세그먼트 분할 시 자막 한 가운데 프레임을 지날 때, 안전을 위해 가까운 자막 경계로 자동 스냅(Snap)하여 쪼개는 방식이 맞으신가요?
4. **[Q8] Alternate take and B-roll scope**: G4 첫 번째 구현 단계에서 대체 촬영본(Alternate) 및 B-roll 레이어링은 데이터 구조/프리뷰 메타데이터 설계만 우선 구현하고, 실제 다중 비디오 트랙 편집 기능은 후속 단계로 미루는 방향이 맞으신가요?
5. **[Q20] First implementation slice**: G4 구현 착수 시 최우선 순위 마일스톤을 '4박스 빈 레이아웃 + 기존 UI 숨김 + 2대 시드 스위칭 스켈레톤 + 저장/불러오기'로 잡는 단계적 분할이 맞으신가요?
