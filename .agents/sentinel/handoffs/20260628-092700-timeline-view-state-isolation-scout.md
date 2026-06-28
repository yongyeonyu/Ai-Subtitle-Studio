DEX_REVIEW_READY
역할: 잼민이 (lightweight chores / prep work)
프로젝트: AI Subtitle Studio
레포지토리 경로: /Users/u_mo_c/Downloads/ai_subtitle_studio
범위: AI Subtitle Studio NLE/Taption selection hover view-state isolation scout

findings:
1. **문제 정의 (Taption식 뷰-격리 계약)**:
   - 자막 카드 hover, selection(선택), highlight, current-segment 지정 등의 단순 뷰-피드백(view-only) 상태 변경이, NLE operation journal append, project save, primary subtitle row rewrite, subtitle validation/rescan 을 부작용으로 유발하여 GUI 프레임 스텁 및 불필요한 디스크 I/O를 일으키지 않도록 격리 장벽 확보 필요.
2. **오너 파일 (Owner Files)**:
   - `ui/timeline/timeline_canvas.py` (hover / mouse move 이벤트 핸들러)
   - `ui/editor/ux/timeline_input.py` (또는 selection handling 믹스인)
3. **Focused Tests to add**:
   - `tests/test_timeline_view_state_isolation.py` [NEW] : hover_line 갱신 및 segment select trigger 시, `NLEProjectState.operation_journal` 에 entry 가 추가되지 않으며 `project_io.py` 의 `_project_payload_for_disk` (세이브 준비)가 호출되지 않음을 spy 단언으로 검증하는 unit test.
4. **Audit Artifact Path**:
   - `tools/audit_nle_view_state_isolation.py` [NEW] : timeline widget 마우스 hover/selection event handler 호출 경로 상에 `project_io` write 및 `validate_segments` 로의 호출 흐름이 정적으로 존재하지 않음을 코드 파싱으로 진단.
5. **NAS 필요 여부 (NAS HeyDealer validation)**:
   - **불필요 (No)**: 자막 생성 파이프라인(STT/VAD/Word Precision/Postprocess)에 일체 영향이 없는 순수 GUI view-state 상호작용 격리 작업이므로 HeyDealer benchmark validation 이 불필요함.

defer:
- **실제 UI/UX 디자인 변경, 뷰어 개조, QML/GPU UI 도입**: Defer 함.
- **실제 .aissproj 파일의 디스크 저장 스키마 변경 (persisted NLE fields)**: Defer 함.
- **per-pixel NLE writes 실시간 디스크/DB 동기화**: Defer 함.
- **STT policy/default cache promotion**: Defer 함.
- **App Store packaging, DMG 빌드**: Defer 함.

덱스 확인 포인트:
- `.agents/sentinel/handoffs/20260628-092700-timeline-view-state-isolation-scout.md` 파일 내용 및 index 맵핑 상태 점검.

DEX_CLASSIFICATION:
- verdict: accepted
- accepted_scope: selection/highlight/current-segment view-state isolation test/audit hardening for AI Subtitle Studio
- applied_as: `tests/test_nle_selection_view_state_isolation.py`, `tools/audit_nle_selection_view_state_isolation.py`, `tests/test_nle_selection_view_state_isolation_audit.py`
- evidence: `output/manual_verification/latest/nle_selection_view_state_isolation_20260628/nle_selection_view_state_isolation.md`; NAS regression accepted at `output/manual_verification/latest/nle_selection_view_state_nas_heydealer_20260628/acceptance/reference_benchmark_acceptance.md`
- deferred: UI/layout changes, persisted NLE disk fields, per-pixel NLE writes, STT/default-cache policy, and App Store packaging/submission
