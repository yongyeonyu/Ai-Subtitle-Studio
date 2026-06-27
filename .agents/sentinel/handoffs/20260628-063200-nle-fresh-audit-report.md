DEX_REVIEW_READY
역할: 잼민이 (lightweight chores / prep work)
프로젝트: AI Subtitle Studio
레포지토리 경로: /Users/u_mo_c/Downloads/ai_subtitle_studio
범위: AI Subtitle Studio remaining NLE release source fresh audit

findings (12줄 이내 요약):
1. **후보1: 단축키 자막 시작/끝 플레이헤드 스냅 (`_set_segment_start_to_playhead/end`)**
   - **Owner function**: `ui/editor/editor_segments_block_surgery.py` 의 관련 함수들.
   - **설명**: 단축키 `[`, `]` 등을 눌러 현재 자막 시작/끝 지점을 플레이헤드 위치로 스냅 확정하는 commit.
   - **위험**: NLE resize pilot 연산이 연동되지 않을 시 save-project parity 에러 유발 리스크.
   - **추천 pytest**: `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py -k "shortcut"`
2. **후보2: 임시 편집선 추가/삭제 (`_on_provisional_cut_boundary_requested/delete`)**
   - **Owner function**: `ui/editor/editor_scan_cut_core.py` 의 관련 함수들.
   - **설명**: 마우스 우클릭으로 타임라인 상에 임시 컷 경계를 추가/제거하여 메모리에 커밋하는 시점.
   - **위험**: NLE State `cut_boundaries` 누출로 인한 save/reopen 후 컷 정보 손실 및 렌더링 drift 리스크.
   - **추천 pytest**: `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_context.py -k "cut_boundary"`
3. **감사 총평**: Tab timing magnet 등 타 조작들은 이미 `_on_seg_time_changed` NLE sync로 위임되므로 추가 후보 없음. **audit-only closeout recommended**.
