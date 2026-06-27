DEX_REVIEW_READY
역할: 잼민이 (lightweight chores / prep work)
프로젝트: AI Subtitle Studio
레포지토리 경로: /Users/u_mo_c/Downloads/ai_subtitle_studio
범위: AI Subtitle Studio NLE range-replace support audit

findings:
1. **NLE Operation Shape**: `clear_segments_in_range` 와 `insert_partial_segments` 가 쌍으로 동작하는 transaction이므로, NLE `caption_delete` (범위 내 자막 제거) 후 `candidate_confirm` (새 자막 atomic insert)을 수행하는 복합 NLE 트랜잭션 구조로 설계.
2. **Fallback Points**: NLE validation 실패 시, NLE state write-path 트랜잭션을 롤백하고 기존 `QTextCursor.removeSelectedText()` 및 `insert_partial_segments` 의 block/userData 직접 갱신 로직으로 우회. try-finally 가드로 UI lockup 차단.
3. **Overlap Gates**: 삽입될 `new_segments` 상호 간의 중첩 검사 및 앞뒤 인접 자막과의 micro-overlap 발생 영역을 shared boundary로 보정(repair)하는 `max_active_segments <= 1` 가드 적용.
4. **필요 테스트 3개**:
   - `test_range_replace_clear_and_insert_syncs_nle` (연동 증명)
   - `test_range_replace_fails_on_overlap_rejection_and_falls_back` (fallback 우회 증명)
   - `test_range_replace_gaps_are_rebuilt_correctly` (gap 재건 정합성 증명)
5. **추천 pytest**:
   - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py -k "partial or range"`
6. **Accept Risk**: clear 경계면(`target_start/end`)과 신규 자막의 boundary 사이 rounding 오차로 인한 frame drift 발생 시 parity check error 유발 리스크.
7. **Defer Risk**: partial replacement 연동 유보 시, 부분 자막 업데이트(STT2 백필 등) 후 save/reopen 시점에 metadata parity 불일치 및 자막 손실 우려.
