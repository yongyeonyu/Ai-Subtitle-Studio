DEX_REVIEW_READY
역할: 잼민이 (lightweight chores / prep work)
프로젝트: AI Subtitle Studio
레포지토리 경로: /Users/u_mo_c/Downloads/ai_subtitle_studio
범위: AI Subtitle Studio NLE shortcut resize guard scout

findings:
1. **NLE Resize Pilot 재사용 루트**: `_set_segment_start_to_playhead`와 `_set_segment_end_to_playhead` 호출 시, `_nle_live_editor_caption_resize_result`를 각각 `edge="square_left"` (new_start=sec) 및 `edge="square_right"` (new_end=sec) 인자와 함께 호출하여 NLE mutable resize 연산을 그대로 재사용.
2. **QTextBlock Shape 가드**: `block.userData()`가 `SubtitleBlockData`이면서 `is_gap = False`인 경우에만 NLE resize 트리거. `orig_start` 값을 key로 삼아 canonical 자막 ID 맵핑 검증.
3. **Fallback 가드**: NLE validation rejection 또는 resize 중 예외 발생 시, try-finally 구조 내부에서 즉각 catch하여 기존의 contiguous 블록 루프(`_contiguous_segment_first/last_block`) 및 `insert_gap_after`를 수행하는 기존 블록 수술 로직으로 안전하게 fallback 우회.
4. **추가할 focused tests**:
   - `test_set_segment_start_to_playhead_reuses_nle_resize_pilot` (NLE 연동 증명)
   - `test_set_segment_start_to_playhead_falls_back_on_nle_validation_failure` (fallback 동작 증명)
5. **추천 pytest expression**:
   - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py -k "shortcut or playhead"`
