DEX_REVIEW_READY
역할: 잼민이 (lightweight chores / prep work)
프로젝트: AI Subtitle Studio
레포지토리 경로: /Users/u_mo_c/Downloads/ai_subtitle_studio
범위: AI Subtitle Studio NLE next safe slice scout

findings:
1. **NLE/Video Editor 전환 로드맵 상의 다음 슬라이스 후보 비교**:
   - **Accept 후보: Trace Log Bundle framework의 진단 로그 구현 (`Diagnostics/Trace`)**
     - **이유**: `/tmp/AISubtitleStudioTemporaryWorkspace/` 하위에 비파괴적으로 JSONL 진단 로그만 append하므로 앱 정합성과 자막 품질에 영향이 없는 가장 안전한 슬라이스임.
   - **Reject 후보: Persisted NLE project fields 직렬화 활성화**
     - **이유**: 오너 승인 없는 디스크 JSON 포맷 변경은 save/reopen 하위 호환성을 무너뜨리므로 즉각 reject.
   - **Defer 후보: 60fps Source-fps visual cut boundary snap / split 적용**
     - **이유**: 자막 시간 길이를 물리적으로 프레임 경계에 스냅/트림하는 로직은 컷 경계 오검출 시 자막 품질 regression 위험이 높아 NAS 실미디어 검증 전까지 defer.
2. **추천 다음 실무 슬라이스**: **Trace Log Bundle Diagnostic Trace 구현**
3. **관련 파일**: `core/runtime/trace_logger.py` [NEW], `core/project/project_io.py`
4. **추천 테스트 (2-4개)**:
   - `tests/test_trace_logger.py` (append/cleanup 정합성)
   - `tests/test_project_io_trace_integration.py` (세이브 시 manifest 갱신 검증)
5. **수정 불가 경계 (Untouchable boundaries)**:
   - `.aissproj` 저장 포맷 (nle_persistence_guard 차단 key 유지).
   - PyQt6 UI/UX의 레이아웃, 라벨, 단축키, 다이얼로그 팝업 동작.
