# AI Subtitle Studio 리팩토링 및 파일 분할 계획서

본 문서는 AI Subtitle Studio 프로젝트 내 소스 코드 중 **2,000줄 이상**인 파일들을 식별하고, 기능(UI/UX 및 런타임 동작)의 변경 없이 구조적 가독성과 유지보수성을 극대화하기 위한 안전한 리팩토링 계획을 수립합니다.

> [!IMPORTANT]
> **리팩토링 대원칙**: 모든 UI Layout, 메뉴 라벨, 단축키, 팝업 상태 등 사용자 환경(UI/UX)과 NLE 세션 상태 로직은 **절대 수정하거나 변경하지 않으며**, 순수하게 구조 분할(Behavior-preserving refactoring)만 수행합니다.

---

## 1. 리팩토링 폴더 분류 및 파일 분할 기준

1. **줄 수 기준 분할 (Threshold)**: 
   - 단일 파일의 라인 수가 **2,000줄 이상**이 되는 경우, 해당 파일은 너무 많은 책임(God Object/God Class)을 지고 있을 확률이 높으므로 SRP(단일 책임 원칙)에 의거하여 분할을 권장합니다.
2. **폴더 분류 기준 (Architecture-based Isolation)**:
   - `ui/`: PyQt GUI 드로잉, 렌더링, 페인팅, 마우스/키보드 이벤트 캡처 전담. (비즈니스 로직 배제)
   - `core/`: NLE 편집 계산, 상태 머신, 파일 IO, STT/VAD 음성 분석 등 비즈니스 연산 및 핵심 알고리즘 전담. (PyQt GUI 의존성 완벽히 배제)
3. **클래스 및 모듈 분할 기준 (SRP)**:
   - **View와 Controller의 분리**: GUI 위젯 내부에 구현된 연산 로직을 별도의 컨트롤러/매니저 클래스로 추출하여 파일로 분리합니다.
   - **데이터 스키마와 변환기(Converter) 분리**: 파일 쓰기/읽기 핸들러와 데이터 변환 검증 코드를 격리합니다.

---

## 2. 프로덕션 소스 코드 내 2,000줄 초과 파일 목록 (우선순위 순)

프로젝트 스캔 결과, `ui/` 및 `core/` 내에서 2,000줄을 초과하는 핵심 소스 코드는 총 **7개**로 확인되었습니다. 각 파일의 중요도, 리팩토링 시 위험도, 가독성 저하 유발 정도를 종합 분석하여 우선순위를 산정했습니다.

### [1위] ui/roughcut/roughcut_widget.py (3,723줄)
- **현상**: 러프컷 조립용 GraphicsView 시각화 및 카드 위젯, 마우스 드래그앤드롭 이벤트 처리, 비디오박스 및 설정 연동 스텁 코드까지 하나의 파일에 집중되어 복잡도가 매우 높습니다.
- **분할 계획**:
  - `roughcut_canvas.py`: PyQt 2D QGraphicsView 및 무한 캔버스 드로잉 로직 전담.
  - `roughcut_node_item.py`: 카드 노드 컴포넌트 클래스(`RoughcutNodeCard`) 및 2D 텍스트/보더 페인팅.
  - `roughcut_connector.py`: 노드 간의 2D 화살표 커넥터 페인팅 및 스냅 라우팅 연산.
  - `roughcut_controller.py`: 시나리오 시드 스위칭, 숏폼 바구니 버짓 검증 등 GUI 외부 연산 브릿지 역할.

### [2위] ui/editor/ux/editor_timeline_video.py (2,216줄)
- **현상**: 메인 자막 타임라인 트랙 렌더링, 비디오 싱크, 눈금자(Ruler) 드로잉, 줌/스크롤 제어 등 복합적인 UI 로직이 중첩되어 있습니다.
- **분할 계획**:
  - `timeline_ruler.py`: 타임라인 상단 시간 눈금자 및 틱 마크 렌더링 분리.
  - `timeline_track_renderer.py`: 세그먼트 및 자막 블록 2D 영역 QPainter 드로잉 로직 분리.
  - `timeline_view_state.py`: 줌 인/아웃 배율, 스크롤 오프셋, 플레이헤드 위치 등 뷰포트 상태 변수 관리 격리.

### [3위] ui/editor/ux/timeline_subtitle_segment_editing.py (2,120줄)
- **현상**: 타임라인 내 개별 자막 텍스트 직접 편집 기능, 인아웃 트림 핸들링, 마우스 더블클릭 오작동 복구 코드 등이 함께 들어가 있습니다.
- **분할 계획**:
  - `segment_inplace_editor.py`: 자막 텍스트 인플레이스 QTextEdit 포커싱 및 폰트 크기 변경 제어.
  - `segment_trim_handler.py`: 좌우 드래그를 통한 타임코드 프레임 Trimming 이벤트 및 가이드라인 오버레이.

### [4위] core/project/nle_dual_write.py (2,331줄)
- **현상**: `nle_snapshot`과 레거시 `editor_state` 간의 동시 정합성 검증 및 예외 저널 파일 저장이 단일 파일 내에서 방대한 예외 스코프로 분기되어 있습니다.
- **분할 계획**:
  - `nle_dual_write_validator.py`: 쓰기 전 상태 일관성 및 정밀 오버랩 검출 로직 분리.
  - `nle_journal_writer.py`: 파일 쓰기 실패 대비 백업 덤프 및 파일 복구 트랜잭션 로직 격리.

### [5위] core/engine/subtitle_engine.py (2,077줄)
- **현상**: VAD, STT1, STT2 멀티프로세스 자원 조율과 결과 병합 알고리즘 및 텍스트 보정 연산이 복잡하게 얽혀 있습니다.
- **분할 계획**:
  - `subtitle_resource_coordinator.py`: CPU interactive reserve 코어 할당 및 멀티프로세스 생명주기 관리.
  - `subtitle_postprocessor.py`: 자막 문장 부호 제거, 한글 맞춤법 보정 규칙 기반 텍스트 필터 격리.

### [6위] core/project/project_manager.py (2,066줄)
- **현상**: 세이브 파일 JSON 로드/세이브 스키마 관리, 다중 프로젝트 관리, 캐시 디렉터리 동기화 로직이 공존합니다.
- **분할 계획**:
  - `project_schema_validator.py`: JSON 파일에 대한 Null-safe 파싱 및 마이그레이션 호환성 판정.
  - `project_state_holder.py`: 메모리 상의 활성 프로젝트 상태 관리 클래스 격리.

### [7위] core/cut_boundary_auto_scan.py (2,055줄)
- **현상**: VAD 무음 및 장면 전환(Scene cut) 프레임을 스캔하여 추천 컷 경계를 도출하는 무거운 수학 연산과 VAD 캐시 연동 코드가 얽혀 있습니다.
- **분할 계획**:
  - `scene_cut_detector.py`: 비디오 픽셀 분석 기반 장면 전환 지점 검출 엔진 분리.
  - `vad_boundary_scanner.py`: 오디오 파형 RMS 에너지 연산 및 임계치 검출 기능 격리.

---

## 3. 리팩토링 검증 및 안전성 확보 방안 (Validation)

- **QA Test Suite 연동**: 모든 파일 분할 작업 단계에서 `./venv/bin/python tools/qa_suite_runner.py quick` 및 `major` 명령을 실행하여, 기능 변화가 전혀 일어나지 않았음을(Behavior-preserved) 정량 증명해야 합니다.
- **동적 바인딩 확인**: 모듈 분할로 인해 기존 PyQt Sign/Slot 및 Signal이 끊기지 않는지, 런타임 이벤트 바인딩 테스트를 필수로 진행합니다.
