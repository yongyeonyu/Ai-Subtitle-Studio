DEX_REVIEW_READY
역할: 서린 (Strict QE Reviewer)
범위: NLE render/export parity risk review (core/project/nle_snapshot.py, ui/roughcut/roughcut_export.py)
읽은 파일:
- `core/project/nle_snapshot.py`
- `ui/roughcut/roughcut_export.py`
- `core/roughcut/render_executor.py`
- `tests/test_roughcut_v2_output_compat.py`

결론:
Roughcut의 렌더 및 내보내기 계획 생성을 NLE Snapshot 기반의 라우팅으로 전환할 때, 프레임 레이트 보정 편차로 인한 1프레임 싱크 오차(drift)가 발생할 수 있으며, UI 고유 메타데이터의 누락 및 구버전 sidecar 스키마와의 호환성 파괴가 초래될 수 있는 심각한 위험 지점들이 존재합니다.

findings:

1. 렌더/내보내기 Parity Drift 위험 지점 (4개)
- **위험 1: VFR/비표준 FPS에서의 Output Duration 연산 불일치**
  - **원인**: NLE Snapshot(`_edl_duration`)은 `output_end` 최대값을 취하거나 FPS 보정을 통해 duration을 소수점 이하로 반올림하여 계산하는 반면, legacy builder는 FFMPEG 소스 컨테이너 본래의 duration을 사용합니다.
  - **리스크**: 23.976 fps, 29.97 fps, 혹은 가변 프레임(VFR) 미디어를 처리할 때, Snapshot Duration과 실제 렌더링된 비디오 길이 사이에 미세한 프레임 둥글림(Quantization) 오차가 누적되어 최종 렌더링 결과물에서 싱크 밀림이 마스킹된 채 통과될 수 있습니다.
- **위험 2: `_render_plan.json` 메타데이터 유실 (Silent Drop)**
  - **원인**: `ui/roughcut/roughcut_export.py`의 `_render_plan_payload`는 `srt_path`, `video_vcodec`, `video_acodec`, `render_mode` 등의 상세 UI 실행 맥락을 담고 있습니다. 반면 NLE snapshot의 `RenderPlan` 메타데이터는 `candidate_id` 및 `edl_duration` 위주로만 단순 직렬화합니다.
  - **리스크**: 렌더링 파이프라인이 Snapshot을 경유하게 되면, 기존 sidecar에 저장되어 프로젝트 복구 시 참조되던 비디오 코덱 정보와 실행 경로 속성들이 영구적으로 드랍되어 복구 실패를 초래합니다.
- **위험 3: 구버전 `_edl.json` Restore 호환성 정합성 파괴**
  - **원인**: legacy EDL 구조는 `ai_subtitle_studio.roughcut.edl.v1` 스키마를 고수합니다.
  - **리스크**: NLE snapshot 라우팅 시 snapshot 포맷이 디스크에 오염(spillover)되거나 sidecar schema 형식이 일방적으로 변경되면, 이전에 사용자가 내보내기 했던 구버전 `.json` 프로젝트를 다시 열어 EDL을 복원할 때 스키마 불일치로 예외가 발생하여 프로젝트 읽기가 중단됩니다.
- **위험 4: Exact-Join (Stitched Cut Boundary) 마커의 1프레임 드리프트**
  - **원인**: `normalize_cut_boundaries`에서 `primary_fps`를 강제 주입해 타임스탬프를 30fps 기준으로 정규화합니다.
  - **리스크**: 원본 소스의 실제 FPS가 다를 때 이 정규화가 FFMPEG 명령어로 변환되면 `-ss`와 `-to` 절삭 구간 타임라인 오프셋이 미세하게 어긋나, 컷 전환부에 이전 챕터의 1프레임 잔상이 남는 고스트 프레임(Ghost Frame) 결함이 발생합니다.

2. Focused Pytest 추천 후보
- **`test_nle_snapshot_output_duration_parity`**:
  - **내용**: VFR 및 23.976 fps 가상 비디오 데이터를 Fixture로 제공한 후, legacy EDL builder의 총 duration과 NLE snapshot `output_duration`이 소수점 6자리까지 완벽히 일치하는지 단언(Assert).
- **`test_nle_snapshot_render_plan_metadata_roundtrip`**:
  - **내용**: `_render_plan_payload`를 NLE snapshot으로 라우팅했다가 다시 legacy payload 형식으로 맵을 역변환했을 때, `srt_path`, `render_mode` 등 UI 제어 속성들이 그대로 보존되는지 100% 동치성을 검증.
- **`test_nle_snapshot_exact_join_frame_drift_prevention`**:
  - **내용**: 29.97 fps 소스 미디어를 기반으로 렌더 명령어를 빌드했을 때, `build_concat_render_plan_from_snapshot`의 결과물 `extract_commands` 타임스탬프 파라미터가 legacy command 파라미터와 바이트 단위로 일치함을 단언하여 1프레임 드리프트 부재를 증명.

defer:
- 런타임 코드 패치 및 테스트 구현은 본 QE review 단계에서는 일체 수행하지 않으며, 덱스(Codex)의 구현 slice 단계로 위임합니다.

덱스 확인 포인트:
1. `_render_plan_payload`의 복잡한 UI 속성들이 NLE snapshot의 `RenderPlan.metadata` 맵 내에 온전히 봉인되어 직렬화되도록 덱스 구현 시 메타데이터 deepcopy 처리가 누락되지 않도록 해야 합니다.
2. VFR 미디어에 대응하기 위해 NLE snapshot이 정규화된 30.0 fps 대신 원본 미디어 자산의 `fps` 속성을 동적으로 참조하도록 로직 보완 여부를 검토해야 합니다.
