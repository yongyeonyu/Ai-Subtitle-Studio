DEX_REVIEW_READY
역할: 잼민이 (lightweight chores / prep work)
프로젝트: AI Subtitle Studio
레포지토리 경로: /Users/u_mo_c/Downloads/ai_subtitle_studio
범위: AI Subtitle Studio diamond delete NLE atomicity scout

findings (12줄 이내 요약):
1. **기존 테스트 위치**: `tests/test_timeline_playhead_fit.py` 의 `test_tab_moves_attached_boundary_as_diamond` 및 `_on_diamond_delete` 헬퍼 함수군.
2. **위험 (keep-left/right 및 line mismatch)**: `keep_raw_line` 판정 오류나 GUI-NLE line 인덱스 mismatch 발생 시, 엉뚱한 자막 ID가 디스크에서 삭제되거나 save/reopen roundtrip parity가 깨질 위험.
3. **재사용성 및 Fallback**: `apply_caption_move_dual_write_pilot`은 move 전용이므로 재사용이 어렵고, delete와 resize pilot을 원자적으로 연쇄 처리하거나 전용 pilot 신설 필요. NLE validation reject 발생 시 기존 QTextDocument block 지우기 로직으로 즉각 복구 fallback 해야 UI 락 방지 가능.
4. **추천 pytest 명령**: `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py -k "diamond or magnet"`
