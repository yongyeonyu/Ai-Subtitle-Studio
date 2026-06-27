DEX_REVIEW_READY
역할: 잼민이 (lightweight chores / prep work)
프로젝트: AI Subtitle Studio
레포지토리 경로: /Users/u_mo_c/Downloads/ai_subtitle_studio
범위: AI Subtitle Studio speaker split NLE test-risk scout

findings (12줄 이내 요약):
1. **QTextDocument fallback 조건**: `split_speaker_segment_with_text` (in `editor_segments_manual_edits.py:401`)는 동일 시간에 overlap 자막을 만드는 구조이므로 NLE `max_active_segments <= 1` overlap 가드와 충돌함. NLE validation 터질 시 기존 QTextCursor 기반 UI 분할 흐름으로 강제 우회 필요.
2. **speaker_list 보존 조건**: 화자 변경/분할 시 NLE `editor_state` 및 project metadata에 `speaker_list` 변경분이 실시간 병합되지 않으면 `save-project` 시 projection mismatch 에러 발생하므로 mapping parity 보장 필수.
3. **더미 에디터 위치 및 위험**: `tests/test_timeline_playhead_fit.py` 내 `_TabTimingEditor` 등에서 mock 처리 시 overlap active 가드 누수로 인한 state corrupt.
4. **추천 pytest 명령**: `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py -k "split or speaker or timing"`
