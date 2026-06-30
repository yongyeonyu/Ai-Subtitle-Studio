DEX_REVIEW_READY
SCOUT_ID=20260701-014518

### 프로젝트 소스 코드 리팩토링 계획 및 우선순위 분석서

#### 1. 리팩토링 대상 파일 분석 결과
- **2,000줄 초과 파일 목록**: 
  - `ui/roughcut/roughcut_widget.py` (3,723줄)
  - `core/project/nle_dual_write.py` (2,331줄)
  - `ui/editor/ux/editor_timeline_video.py` (2,216줄)
  - `ui/editor/ux/timeline_subtitle_segment_editing.py` (2,120줄)
  - `core/engine/subtitle_engine.py` (2,077줄)
  - `core/project/project_manager.py` (2,066줄)
  - `core/cut_boundary_auto_scan.py` (2,055줄)

#### 2. 리팩토링 우선순위 선정 (가장 긴 파일 순 및 복잡도 기준)
1. **`ui/roughcut/roughcut_widget.py` (1순위)**: 러프컷 4대 고정 박스의 2D UI 연산과 데이터 매핑이 하나의 클래스에 과도하게 밀집됨.
2. **`ui/editor/ux/editor_timeline_video.py` (2순위)**: 타임라인 2D 렌더링, 눈금자 드로잉, 뷰포트 스크롤 상태가 혼재하여 분리 시급.
3. **`ui/editor/ux/timeline_subtitle_segment_editing.py` (3순위)**: 타임라인 내 직접 텍스트 변경 이벤트와 인플레이스 편집 UI 결합.
4. **`core/project/nle_dual_write.py` (4순위)**: `nle_snapshot`과 레거시 `editor_state` 동시 쓰기 정합성 및 백업 저널 가드 로직.
5. **`core/engine/subtitle_engine.py` (5순위)**: VAD/STT1/STT2 백엔드 스레드 조율 및 자막 전처리 필터.
6. **`core/project/project_manager.py` (6순위)**: 프로젝트 세이브 스키마 마이그레이션 호환성 판정 및 임시 상태 세션 관리.
7. **`core/cut_boundary_auto_scan.py` (7순위)**: 장면 전환 감지 연산 및 VAD 추천 컷 경계 스캔.

#### 3. 분할 기준 및 룰
- **UI/UX 절대 보존(Do-not-touch)**: 레이아웃, 컬러, 단축키, 마우스 액션, 팝업 윈도우 등 사용자 대면 디자인은 100% 동일하게 2D-only로 보존.
- **검증 규칙**: 리팩토링 전후로 동일한 QA suite를 실행하여 `failed_count=0` 상태를 유지하고, PyQt 시그널 바인딩 유지를 위한 동적 런타임 이벤트 테스트.
