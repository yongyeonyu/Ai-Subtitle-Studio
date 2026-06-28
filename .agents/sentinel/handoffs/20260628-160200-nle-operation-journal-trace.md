DEX_REVIEW_READY
역할: 잼민이 (lightweight chores / prep work)
프로젝트: AI Subtitle Studio
레포지토리 경로: /Users/u_mo_c/Downloads/ai_subtitle_studio
범위: AI Subtitle Studio NLE operation journal trace scout 20260628

findings:
1. **TraceLogger event 삽입 안전 필드**:
   - `operation_id`, `operation_kind`, `operation_family`, `commit_boundary`, `commit_source` (NLE 연산의 계통/단위 제어 메타데이터)
   - `sequence`, `target_count`, `projected_count` (연산 처리량 및 순서)
   - `after_invalid_duration_count`, `after_non_monotonic_count`, `after_overlap_count` (연산 직후 자막 시퀀스 무결성 카운트)
2. **Raw Text / Path 누출 위험 방지 (Security)**:
   - **위험**: 자막의 실제 내용(`text`)이나 프로젝트 절대 경로(`source_project_path`)를 그대로 trace log 에 노출할 시 개인정보 유출 리스크 발생.
   - **방어**: trace event 에는 절대 `text` 필드를 싣지 않고, `source_project_path` 대신 `_short_hash(source_project_path)` 를 project_id 로 덤프해야 함.
3. **Storage Persistence Risk (저장 위험성)**:
   - `_nle_project_state` 와 `operation_journal` 은 `project_io.py` 의 `strip_unapproved_nle_persistence_fields` 에 의해 디스크 저장 전 강제 strip(소거)되므로, 디스크 파일 포맷 오염 위협이 완전히 격리됨.
4. **추천 다음 슬라이스**:
   - **추천 항목**: **"NLE Operation Journal Trace Event Assertion Test" (NLE 저널 trace 이벤트 검증 테스트 보강)**
5. **focused test gaps**:
   - 현재 `tests/test_project_nle_operations.py` 및 `tests/test_nle_operation_journal_audit.py` 에서 NLE 연산(caption_move, caption_split 등)이 실행될 때 `nle_operation_journal_append` trace event 가 정상적으로 발생하고 수신되는지 확인하는 assert 검증이 부재(gap)함.

defer:
- **실제 .aissproj 파일의 디스크 저장 스키마 변경**: Defer 함.
- **실제 NLE 연산 비즈니스 로직(undo_snapshot deepcopy 등) 튜닝**: Defer 함.
- **QML/UI 및 App Store 관련 작업**: Defer 함.

덱스 확인 포인트:
- `.agents/sentinel/handoffs/20260628-160200-nle-operation-journal-trace.md` 파일 내용 및 index 맵핑 상태 점검.
