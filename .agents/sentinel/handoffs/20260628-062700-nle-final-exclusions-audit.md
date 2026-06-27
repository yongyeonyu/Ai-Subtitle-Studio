DEX_REVIEW_READY
역할: 잼민이 (lightweight chores / prep work)
프로젝트: AI Subtitle Studio
레포지토리 경로: /Users/u_mo_c/Downloads/ai_subtitle_studio
범위: AI Subtitle Studio remaining NLE release-source audit after completed exclusions

findings:
1. **Candidate 1: 품질 검사 원클릭 자동 교정 (`_handle_one_click_fix_action` / `_replace_segment_text_by_line`)**
   - **안전성**: 1위 (가장 안전). 텍스트 대체 중심의 mutation이므로 기존 text pilot을 손쉽게 재사용 가능.
   - **Owner path**: `ui/editor/editor_quality_review.py` 의 관련 함수들.
   - **Fallback**: NLE 에러 시 기존 QTextCursor 기반 블록 텍스트 직접 교체 및 rehighlighting 우회.
   - **NLE Family**: `caption_text_edit` (`apply_caption_text_edit_dual_write_pilot` 재사용).
   - **Focused tests**: `test_timeline_playhead_fit.py` 내 `quality` 키워드 테스트.
2. **Candidate 2: 부분 자막 삽입 (`insert_partial_segments` / `clear_segments_in_range`)**
   - **안전성**: 2위 (주의 필요). 특정 범위의 자막을 delete하고 new rows를 insert하므로 복수 트랜잭션 수반.
   - **Owner path**: `ui/editor/editor_segments_manual_edits.py` 의 관련 함수들.
   - **Fallback**: NLE 에러 시 기존 QTextCursor 기반의 range clear 및 부분 insert 로직 우회.
   - **NLE Family**: `caption_delete` + `candidate_confirm` (복합 트랜잭션).
   - **Focused tests**: `test_timeline_playhead_fit.py` 내 `partial` 키워드 테스트.
3. **감사 총평**: 팝업 replace-all, 임시 편집선, 화자 변경, 스마트 분할 등 기존에 스카우트된 timing/metadata edit sources는 이미 NLE dual-write에 모두 묶여 성공 검증되었음. 이로써 잔여 후보 감사 완료. **audit-only closeout recommended**.
