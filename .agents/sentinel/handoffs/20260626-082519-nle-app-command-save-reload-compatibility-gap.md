DEX_REVIEW_READY
역할: 서린 (Strict QE Reviewer)
범위: NLE app-command save-reload compatibility gap review (tools/appctl.py, tests/test_app_command_bridge.py)
읽은 파일:
- `ui/roughcut/roughcut_export.py`
- `tests/test_roughcut_ui_v2.py`
- `tests/test_app_command_bridge.py`
- `tests/test_project_nle_snapshot.py`
- `tools/appctl.py`

결론:
NLE snapshot 기반의 렌더/내보내기 라우팅을 도입할 때, 자동화 도구(`appctl`)의 외장 명령어 호출 맥락, direct SRT 실행 시 사이드카 exact-join 검출, 가상 세그먼트(Gap)를 지닌 legacy `.aissproj` 저장/복원, 그리고 비동기 QThread 렌더 실행 시의 메모리 경계 측면에서 중대한 호환성 갭(Compatibility Gap)이 발견되었습니다.

findings:

1. NLE 라우팅 전환 시 호환성 갭 (4개)
- **갭 1: 자동화 명령(app-command) 렌더링 시의 render_mode 실시간 변이 누락**
  - **원인**: `appctl`을 통해 `roughcut-render-video` 명령이 트리거될 때 UI 환경설정 등에서 코덱이나 렌더 모드(`roughcut_render_mode()`)가 실시간으로 바뀔 수 있습니다.
  - **리스크**: NLE snapshot이 렌더 계획을 덤프할 때, 실시간으로 변동된 렌더 설정 상태가 snapshot 객체에 제때 갱신(sync)되지 않고 snapshot 생성 시점의 구버전 상태로 렌더가 기동되어 결과물이 불일치하게 됩니다.
- **갭 2: Direct SRT 열기 시 Exact-Join 사이드카 복구 누락**
  - **원인**: 에디터는 프로젝트 파일 없이 `.srt`만 직접 열 때 동일 경로의 `_edl.json`과 `_render_plan.json` 사이드카 데이터를 직접 스캔하여 컷 경계(`exact-join`) 마커를 UI에 주입합니다 (`load_stitched_cut_boundaries_for_srt_open`).
  - **리스크**: 렌더 구조를 snapshot 기반으로 교체하면 프로젝트 인스턴스가 불완전한 direct SRT 오픈 상태에서 sidecar raw 데이터를 snapshot의 `TimelineMarker`로 추출할 수 없어, exact-join 경계가 유실되고 마커 렌더링에 실패합니다.
- **갭 3: legacy aissproj 내의 가상 갭 세그먼트(`is_gap`) 누락**
  - **원인**: legacy 프로젝트는 타임라인 상 자막이 없는 빈 시간 구간을 `is_gap: True` 객체로 관리합니다. NLE snapshot 빌더(`nle_snapshot.py` -> `_build_captions`)는 `is_gap`인 행을 루프에서 원천 차단합니다.
  - **리스크**: NLE snapshot을 디스크에 저장하거나 역직렬화할 때 갭 정보가 전부 유실되어, 타임라인의 빈 시간 공간 정보가 소멸되고 자막이 앞쪽으로 무단 정렬되어 싱크 파괴가 유발됩니다.
- **갭 4: 비동기 QThread (`_RoughcutRenderWorker`)의 스레드 바운더리 크래시**
  - **원인**: `RoughcutWidget`은 렌더 플랜 실행을 백그라운드 QThread에 위임합니다.
  - **리스크**: 스레드 실행 시점에 snapshot frozen 객체의 참조를 넘기려 할 때, GUI 스레드에서 해당 객체가 가비지 컬렉션되거나 해제되면 비동기 스레드가 유효하지 않은 포인터를 참조하여 Qt 런타임 세그먼테이션 폴트(Segmentation Fault) 크래시가 유발됩니다.

2. Focused Pytest 추천 후보
- **`test_nle_snapshot_srt_open_sidecar_recovery_parity`**:
  - **내용**: 프로젝트가 없는 환경에서 SRT 파일과 사이드카 `_edl.json`만 주어졌을 때, legacy sidecar recovery 결과와 NLE snapshot `TimelineMarker`로 수집된 exact-join의 동치성을 검증.
- **`test_nle_snapshot_save_reload_gap_integrity`**:
  - **내용**: 3초 간격의 자막 갭(`is_gap=True`)이 존재하는 legacy aissproj를 로드하여 snapshot으로 매핑했다가 다시 복원할 때, 갭 구간 정보와 타임라인 sequence duration이 정확히 보존되는지 단언(Assert).
- **`test_app_command_roughcut_export_routing_parity`**:
  - **내용**: mock app context를 통해 `roughcut-export-srt` 및 `roughcut-render-video` UDP 명령을 송신한 뒤, snapshot-derived plan이 legacy plan과 동일한 FFMPEG flag 및 sidecar JSON 파일들을 생성하는지 단언.

defer:
- 테스트 코드 구현 및 런타임 패치는 본 QE review 단계에서는 수행하지 않으며, Codex(덱스) 구현 단계로 위임합니다.

덱스 확인 포인트:
1. `nle_snapshot.py`가 자막 세그먼트를 캡처할 때 `is_gap=True`인 속성을 임시 metadata에 저장해 두었다가 복원 시 다시 gap 세그먼트로 복구할 수 있는 필드 보존 장치를 마련해야 합니다.
2. `RoughcutWidget` 렌더 스레드 구동 시 snapshot 데이터를 deepcopy된 일반 dict나 독립 인스턴스로 분리해서 QThread에 안전하게 파라미터로 넘기도록 조치해야 합니다.
