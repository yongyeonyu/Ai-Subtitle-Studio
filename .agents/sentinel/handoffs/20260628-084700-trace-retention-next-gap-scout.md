DEX_REVIEW_READY
역할: 잼민이 (lightweight chores / prep work)
프로젝트: AI Subtitle Studio
레포지토리 경로: /Users/u_mo_c/Downloads/ai_subtitle_studio
범위: AI Subtitle Studio Trace Log Bundle next safe slice scout

findings:
1. **Trace Log Bundle 계약 및 현황 감사**:
   - `core/runtime/trace_logger.py` 와 `tools/collect_trace_package.py` 가 잘 동작 중이나, 시스템 임시 디스크 무한 잠식을 방지하기 위한 오래된 run 디렉토리 자동 정리(cleanup) 및 보관 개수 제한(retention policy) 계약 부분이 누락되어 있음.
2. **Accept 후보: Trace run directory retention & auto-cleanup 구현**
   - **설명**: `temp_workspace.py` 에 최대 보관할 run 폴더의 개수(예: 20개)를 초과할 경우 수정 시간이 오래된 `runs/<run_id>` 폴더를 자동으로 삭제하는 로직 추가.
   - **이유**: 디스크 공간을 안전하게 보존하며, UI/UX나 제품 로직에 주는 사이드 이펙트가 전혀 없는 가장 안전한 비파괴 보강 조각임.
3. **Defer 후보: 실시간 UI/재생 스크롤링 프레임 단위 trace logging 연동**
   - **이유**: 프레임 스크롤링 단위의 I/O 로그가 쏟아질 시 비동기 큐의 런타임 오버헤드 유발 및 playback lag 리스크가 존재하므로 유보.
4. **Reject 후보: Trace I/O 에러 발생 시 UI 에러 팝업 노출**
   - **이유**: 비파괴 진단 도구 실패가 메인 앱 기능 차단으로 이어지게 만들며, UI/UX 변경 금지 원칙과 정면 충돌하여 reject.
5. **추천 테스트**:
   - `tests/test_trace_logger_retention.py` (run 개수 20개 초과 시 오래된 디렉토리 자동 삭제 정합성)
6. **수정 불가 경계**:
   - `.aissproj` 저장 포맷, 메인 자막 편집 및 텍스트/시간 검증 로직.
