DEX_REVIEW_READY
역할: 잼민이 (lightweight chores / prep work)
프로젝트: AI Subtitle Studio
레포지토리 경로: /Users/u_mo_c/Downloads/ai_subtitle_studio
범위: AI Subtitle Studio remaining NLE release source scout after diamond delete

findings (12줄 이내 요약):
1. **후보1: 스마트 자막 분할 (`_on_smart_split`)**
   - **Owner function**: `ui/editor/ux/editor_timeline_gap_split.py` 의 `_on_smart_split`
   - **설명**: 오디오 타임라인 시점을 기점으로 자막 행을 두 개로 쪼개어 새 자막을 생성하는 commit.
   - **위험**: 쪼개진 자막의 start/end와 텍스트 분할이 NLE State의 split pilot으로 실시간 투영되지 않으면 save/reopen 후 자막이 합쳐져 유실될 위험.
   - **추천 pytest**: `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py -k "split or timing"`
2. **후보2: 화자 변경/드롭 (`_change_speaker_for_line` / `_on_speaker_circle_dropped`)**
   - **Owner function**: `ui/editor/editor_speaker_ops.py` 내 화자 연산 핸들러들.
   - **설명**: 화자를 바꾸거나 마우스 드래그-드롭으로 화자 정보를 덮어쓰고 확정하는 release commit.
   - **위험**: 화자 ID 변경이 NLE State metadata에 동기화되지 않을 시 `save-project` 시점의 projection drift 에러 유발.
   - **추천 pytest**: `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py -k "speaker"`
