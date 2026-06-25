DEX_REVIEW_READY

# Source-App Internal NLE Snapshot Read-Only Adapter - QA Validation Gap Review

본 문서는 NLE 아키텍처 스냅샷의 read-only adapter 적용 시 요구되는 최소한의 QA 검증 항목 및 기존 테스트 커버리지의 갭(Gap)을 분석한 리포트입니다.

---

## NLE Validation Gap Findings (최소 테스트 갭 분석)

### [Finding 1] Legacy `.aissproj` 복구 시 스키마 결손에 대한 폴백 테스트 부족
- **위험 요소**:
  - 과거 버전을 로드할 때 `timeline.timebase`나 `video` 헤더가 없는 레거시 프로젝트 구조가 감지되면, `hydrate_project_runtime_views`에서 default 30.0fps 기반으로 강제 스냅 및 보정이 트리거됩니다.
- **테스트 Gap**:
  - `tests/test_project_context.py` 내에 v3 이하의 불완전한 JSON 페이로드 구조를 가상으로 모킹하여, hydrated 뷰가 timeline duration과 클립 총 프레임 수를 원본 값의 누실 없이 정확하게 복원해내는지 검증하는 예외 상황 유닛 테스트가 부재합니다.

### [Finding 2] Direct SRT Open 시의 프레임 양자화(Frame Quantization) 검증 부재
- **위험 요소**:
  - 영상 소스 없이 자막만 오픈하는 경우 default 30.0fps 기반의 글로벌 캔버스 규격(`SRT_FRAME_QUANTIZATION_MODE`)에 맞춰 자막 세그먼트의 시간 정보가 밀리초에서 프레임 그리드로 재해석됩니다.
- **테스트 Gap**:
  - 밀리초 단위 경계가 프레임 그리드 경계와 미세하게 불일치할 때(예: 0.001초 미만의 타임스탬프 어긋남) 발생하는 소수점 버림/올림 변이가 read-only sequence mapping에서 1프레임 미만의 오차로 누적되어 Sequence `CaptionSegment`에 드리프트가 생기는 것을 감지하고 격리하는 회귀 테스트가 누락되어 있습니다.

### [Finding 3] Roughcut 챕터/후보 스팬과 Output Timebase의 듀레이션 오차 검증 Gap
- **위험 요소**:
  - 복수 미디어 클립을 접합하는 러프컷 후보 출력 시, 각 클립의 Local Timebase 오프셋과 output-time 상의 `exact_join` 프레임 포인트가 결합되는 과정에서 초(second) 단위의 유실이 생길 수 있습니다.
- **테스트 Gap**:
  - `tests/test_roughcut_ui_v2.py` 및 `edl_generator.py`를 연동하여 멀티클립 접합 EDL을 생성할 때, 렌더 플랜 상의 `RenderPlan.duration` 합산값과 FFMPEG 커팅 뼈대(`renderer_skeleton.py`) 명령어로 파싱되어 나온 output duration의 수학적 정밀도가 완전히 일치(byte/metadata-equivalent)함을 검증하는 검문소 격의 assert문이 테스트 상에 빈약합니다.

### [Finding 4] 중복 가변 타이밍 상태(Duplicate Mutable Timing State) False Confidence 리스크
- **위험 요소**:
  - 세그먼트 내부에는 초 단위의 `start`/`end` 필드와 프레임 단위의 `start_frame`/`end_frame` 필드가 중복 존재하여 타이밍 가변 상태(mutable state)의 진실이 분산되어 있습니다.
- **테스트 Gap**:
  - 만약 read-only adapter가 초 단위 데이터만 읽고 Sequence를 동기화하는 구조로 안주(False Confidence)할 경우, 실제 타임라인 위젯 UI(`timeline_canvas.py` 등)의 프레임 드래그 편집 로직이 `start_frame`만 우선 수정한 직후 발생하는 상태 정합성 불일치를 감지하지 못합니다.
  - 가변 타이밍 소스의 비동기 업데이트 시, 두 상태가 항상 스냅 보정되어 양방향 정합성을 이루는지 증명하는 락-스텝(lock-step) 검증 테스트 시나리오를 추가 보강해야 합니다.
