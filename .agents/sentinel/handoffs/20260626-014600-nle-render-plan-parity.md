DEX_REVIEW_READY

# NLE Snapshot Render/Export Plan Parity & Safety Review

본 문서는 NLE 스냅샷 어댑터를 러프컷 비디오/자막 내보내기 렌더 플랜 구조와 연결할 때, 시스템의 하위 호환성을 유지하고 부작용을 예방하기 위한 안전 경로 분석 보고서입니다.

---

## Render/Export Plan Parity Findings (4가지 안전 조건 분석)

### [Finding 1] 렌더/내보내기 계획 조율의 단일 소유 경로 (Owner Path)
- **현황**:
  - `ui/roughcut/roughcut_export.py`가 UI 단에서의 사용자 에디트 정보를 수집하여 `build_concat_render_plan`을 통해 FFMPEG 및 EDL 생성 로직(`core/roughcut/`)으로 넘겨주는 실질적인 단일 오케스트레이션 소유 경로(Owner Path)를 가지고 있습니다.
- **안전 제안**:
  - NLE 스냅샷 어댑터와의 연동 시 UI 측의 렌더 플랜 빌드 프로세스 구조를 우회하거나 해체하지 않고, `RenderPlan` 객체의 read-only snapshot 투영 형태로만 연결해야 구조적 안정성이 유지됩니다.

### [Finding 2] Parity Assert 검증을 위한 최적 위치 도출
- **현황**:
  - 러프컷 내보내기 시 생성되는 `RenderPlan` 및 sidecar의 `output_duration`에 프레임 양자화 손실로 인한 시간 편차가 없음을 보장해야 합니다.
- **최적 Assert 위치**:
  - `core/roughcut/render_executor.py` 내 `build_concat_render_plan` 직후 리턴 직전.
  - `core/roughcut/renderer_skeleton.py` 내 EDL segment 결합 직후.
  - 이 지점에서 `RenderPlan.duration` 총합과 개별 세그먼트의 `output_end - output_start` 누적 합이 수학적 동등성을 유지하는지 assert 문을 마킹하여 QA 상에서 듀레이션 오차 누적을 사전에 차단합니다.

### [Finding 3] 기존 `_render_plan.json` 및 `_edl.json` Sidecar Reader 유지 조건
- **현황**:
  - `ui/editor/editor_project_open_native.py` 등에서는 프로젝트 재오픈 시 인접 경로 상의 `*_render_plan.json` 및 `*_edl.json` 파일을 스캔하여 `stitched_cut_boundaries` 배열을 추출, 컷 경계 씨앗 정보로 재하이드레이션합니다.
- **안전 조건**:
  - 신규 NLE 스냅샷 객체(`RenderPlan` 등)의 명세 변경이 sidecar 파일의 최상위 및 nested 구조(`stitched_cut_boundaries`, `edl`) 키 구조를 해치지 않아야 기존 sidecar 파일 읽기 모듈과의 호환성이 유지됩니다.

### [Finding 4] UI/UX 변경에 대한 엄격한 보수 정책 (UI/UX Regression Risk)
- **현황**:
  - NLE 아키텍처 스냅샷의 설계 목적은 런타임 데이터 구조의 read-only 명세 정립에 국한됩니다.
- **안전 조건**:
  - 러프컷 탭 및 비디오 내보내기 대화창 내의 버튼 라벨, 상태 메시지, 내보내기 진행 바 등 사용자가 대면하는 UI/UX 요소를 건드리지 않고 내부 어댑터 모델링 수준에만 마킹해야 불필요한 UI 회귀 버그를 방지할 수 있습니다.
