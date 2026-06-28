DEX_REVIEW_READY
역할: 잼민이
범위: AI Subtitle Studio NLE direct SRT and roughcut sidecar read-back parity scout
읽은 파일:
- core/project/nle_snapshot.py
- core/project/project_io.py
- tests/test_project_nle_snapshot.py
- tests/test_project_nle_persistence_guard.py
결론: Direct SRT 오픈 및 Roughcut sidecar 복구 영역으로 패리티 가드(read-back parity guard)를 확장하기 위한 스카우트 분석을 완료했습니다.

*   **프로젝트명**: AI Subtitle Studio
*   **저장소 루트 (Repo Root)**: `/Users/u_mo_c/Downloads/ai_subtitle_studio`

---

### 🧩 1. 최소 변경 후보 파일 (Minimum Change Candidate Files)
*   **`core/project/project_io.py` & `core/project/project_context.py`**:
    - direct SRT를 여는 진입점(예: `read_project_file` 외에 SRT Import/Parsing 지점) 및 roughcut EDL sidecar 파일의 로드/복구(restore) 지점 종료부에서 `_attach_nle_snapshot_readback_parity` 헬퍼 함수를 추가로 호출하도록 바인딩.
*   **`core/project/nle_snapshot.py`**:
    - `attach_nle_snapshot_readback_parity` 내부의 `_build_assets_and_clips`에서 미디어 경로가 누락되었거나 direct SRT 단독 오픈 상황일 때 프레임 경계 변환(`fps` 획득 에러 등) 오차가 나지 않도록 폴백 처리를 확장.

### 📋 2. 기존 테스트 후보 (Existing Test Candidates)
*   **`tests/test_project_nle_snapshot.py`**:
    - `test_direct_srt_sidecar_rows_project_to_nle_exact_join_markers`: direct SRT의 자막 행이 NLE exact join 마커로 바르게 투영되는지 패리티 검사.
    - `test_roughcut_sidecar_payload_shapes_project_to_exact_join_markers`: 러프컷 EDL/sidecar 로드 결과물 검사.
    - `test_nle_project_state_handles_direct_srt_rows_without_media_or_sidecar`: 미디어 결여 상태에서의 SRT 단독 로드 동작 검사.
    - `test_nle_project_state_preserves_roughcut_exact_join_marker_parity`: 러프컷 마커 보존 정합성 검사.

### ⚠️ 3. 위험한 결합 지점 (Dangerous Coupling Points)
*   **미디어 FPS/Duration 누락 결합**:
    - direct SRT 단독 오픈 시 실제 비디오 미디어 소스(WAV, MP4)가 연결되어 있지 않은 경우가 많습니다. 이때 기본 fps(예: 30.0fps)로 가정하고 시간(sec)<->프레임(frame) 변환 연산을 적용하면, 나중에 미디어가 Relink 되었을 때 소스 fps(예: 59.94fps)와 불일치가 생겨 freshly rebuilt snapshot 패리티 에러가 강제 유발될 위험이 있습니다.
*   **우선순위 역전 (Precedence Inversion Risk)**:
    - `direct_srt_precedence_contract=srt_timing_text_wins`에 의거하여 직접 연 SRT 자막 행이 절대적 진실의 원천이 되어야 합니다. 하지만 패리티 가드가 작동하면서 저장된 `nle_snapshot` 기반의 정보가 더 우선시되어, 사용자가 메모장에서 직접 수정한 SRT 텍스트가 덮어씌워질 위험이 있습니다.

### 🎯 4. 추천 Focused Verification Shortlist
*   `tests/test_project_segment_reload.py` (세그먼트 리로드 및 뷰 동기화)
*   `tests/test_project_nle_snapshot.py` (투영 메트릭 전체 점검)
*   `tools/audit_nle_persistence_cutover.py` (저장 및 스키마 직렬화 정합성 오디트)
