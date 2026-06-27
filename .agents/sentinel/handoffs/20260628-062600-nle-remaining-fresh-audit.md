DEX_REVIEW_READY
역할: 잼민이 (lightweight chores / prep work)
프로젝트: AI Subtitle Studio
레포지토리 경로: /Users/u_mo_c/Downloads/ai_subtitle_studio
범위: AI Subtitle Studio remaining NLE release-source audit

findings:
1. **Candidate 1: 단순 화자 변경 (`_change_speaker_for_line` / `_on_speaker_circle_dropped`)**
   - **안전성**: 1위 (가장 안전). 시간 축 수정 없이 화자 ID 메타데이터만 갱신.
   - **Owner path**: `ui/editor/editor_speaker_ops.py` 의 관련 핸들러들.
   - **Fallback**: NLE 에러 시 기존 QTextDocument block `userData.spk_id` 직접 갱신 및 rehighlighting 우회.
   - **NLE Family**: `caption_text_edit` (기존 `apply_caption_text_edit_dual_write_pilot` 재사용).
   - **Focused tests**: `test_timeline_playhead_fit.py` 내 `speaker` 키워드 테스트.
2. **Candidate 2: 스마트 자막 분할 (`_on_smart_split`)**
   - **안전성**: 2위 (보통). 시간 분할이 동반되나 split point가 snapping된 단일 자막 쪼개기.
   - **Owner path**: `ui/editor/ux/editor_timeline_gap_split.py` 내 `_on_smart_split`.
   - **Fallback**: NLE validation 에러 시 기존 QTextCursor 기반 block split 및 `_finalize_edit` 복구.
   - **NLE Family**: `caption_split` (`apply_caption_split_dual_write_pilot`).
   - **Focused tests**: `test_timeline_playhead_fit.py` 내 `split` 키워드 테스트.
3. **Candidate 3: Diamond Drag Delete (`_on_diamond_delete`)**
   - **안전성**: 3위 (주의 필요). 자막 완전 삭제와 인접 자막 확장이 연쇄되는 복합 연산.
   - **Owner path**: `ui/editor/ux/editor_timeline_segment_merge.py` 내 `_on_diamond_delete`.
   - **Fallback**: reject 시 기존 `_delete_block_group` 및 `_set_block_group_start/end` 로직으로 즉시 fallback.
   - **NLE Family**: delete + resize atomic pilot 결합 또는 전용 pilot 구축.
   - **Focused tests**: `test_timeline_playhead_fit.py` 내 `diamond` 키워드 테스트.
