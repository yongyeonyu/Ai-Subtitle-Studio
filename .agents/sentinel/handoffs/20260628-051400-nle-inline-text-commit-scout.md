DEX_REVIEW_READY
역할: 잼민이 (lightweight chores / prep work)
프로젝트: AI Subtitle Studio
레포지토리 경로: /Users/u_mo_c/Downloads/ai_subtitle_studio
범위: NLE remaining release source scout

findings (10줄 이내 요약):
1. **커밋 연동 후보**: `_commit_inline_edit` 에 의한 텍스트 확정 시 `_on_inline_text_changed` (in `editor_widget.py:962`)가 호출되며, 이때 `apply_caption_text_edit_dual_write_pilot` (신규)을 호출해 NLE State의 텍스트를 atomically 갱신.
2. **NLE operation kind 확장 위험**: 텍스트 수정 시 `quality` (확정 여부), `speaker` 등의 legacy metadata 가 NLE projection parity 계산 시 누락될 경우 `operation_projection_drift` 발생. 빈 문자열 입력 시 `caption_delete` (gap 변환) 연동 경계에서의 꼬임 위험.
3. **테스트 포인트**: `tests/test_project_nle_dual_write.py` 에 `test_caption_text_edit_dual_write_pilot` 추가, 텍스트 수정 후 디스크 save 및 reopened 자막의 UTF-8 문자열/개행(`\u2028`) roundtrip 무결성 검증.
