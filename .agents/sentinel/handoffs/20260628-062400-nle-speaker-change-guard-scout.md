DEX_REVIEW_READY
역할: 잼민이 (lightweight chores / prep work)
프로젝트: AI Subtitle Studio
레포지토리 경로: /Users/u_mo_c/Downloads/ai_subtitle_studio
범위: AI Subtitle Studio speaker change NLE guard scout

findings:
1. **가장 안전한 NLE 루트**: `apply_caption_text_edit_dual_write_pilot`은 이미 `new_speaker`와 `new_speaker_list`를 수용하도록 설계되어 있음. `_change_speaker_for_line`이 `new_text`는 원본 자막 텍스트 그대로 두고 `new_speaker=new_spk_id`를 전달하는 단일 NLE path가 가장 좁고 안전함.
2. **QTextBlock/UI-shape 가드**: `userData()`가 `SubtitleBlockData`이면서 `is_gap = False`인 확정 자막에만 적용. line index mismatch를 방지하기 위해 canonical 자막 ID를 NLE에서 맵핑하기 전 canonical ID check 가드로 방어.
3. **try-finally 락 해제 가드**: NLE sync call 실행 시 예외가 발생하더라도 `cur.endEditBlock()` 과 `self._sync_lock = False`가 정상 해제되도록 try-finally 가드 보장.
4. **실패 시 우회**: NLE write 중 `ValueError`가 발생하면 swallow하여 기존의 QTextCursor block 속성 갱신 및 rehighlighting fallback 루틴으로 정상 우회.
5. **최소 focused pytest**:
   - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py -k "speaker"`
   - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_dual_write.py -k "text_edit"`
