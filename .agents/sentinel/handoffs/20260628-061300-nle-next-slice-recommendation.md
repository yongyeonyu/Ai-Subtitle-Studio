DEX_REVIEW_READY
역할: 잼민이 (lightweight chores / prep work)
프로젝트: AI Subtitle Studio
레포지토리 경로: /Users/u_mo_c/Downloads/ai_subtitle_studio
범위: AI Subtitle Studio NLE next commit-source implementation scout

findings:
1. **후보 (1) 단축키 자막 시작/끝 시간을 플레이헤드에 스냅 변경**:
   - **NLE 커버리지**: 기존 NLE `caption_resize` pilot (`apply_caption_resize_dual_write_pilot`)을 100% 재사용할 수 있어 추가 schema/operation kind 신설 작업이 불필요함.
   - **Owner function**: `editor_segments_block_surgery.py` 의 `_set_segment_start_to_playhead` / `_set_segment_end_to_playhead`
   - **행동 위험**: 극단적인 단축키 스냅 시 발생할 수 있는 overlap validation reject에 대응하여 try-finally 가드 및 legacy fallback 보장 필수.
   - **테스트**: `test_timeline_playhead_fit.py` 에 단축키 스냅 검증 테스트 추가 및 `pytest -k "shortcut"` 실행.
2. **후보 (2) 임시 편집선 추가/삭제**:
   - **NLE 커버리지**: `cut_boundaries` 변경용 pilot이 없으므로 NLE operation kind 스키마 및 write helper 신설이 수반되는 broad schema work 필요.
   - **Owner function**: `editor_scan_cut_core.py` 의 `_on_provisional_cut_boundary_requested` / `_on_provisional_cut_boundary_delete_requested`
   - **행동 위험**: snapping rounding 오차로 인한 frame drift 발생 시 auto-cut boundary와 불일치하여 컷 경계가 렌더링 손실되는 리스크.
   - **테스트**: `test_project_context.py` 내 cut_boundaries fixture 검증 및 `pytest -k "cut_boundary"` 실행.
3. **최종 추천 슬라이스**: **후보 (1) 단축키 시작/끝 시간을 플레이헤드에 스냅 변경**
   - **선정 근거**: 추가 operation kind 확장 부담 없이 기존 resize pilot을 활용한 bounded slice로 즉각 안전하게 연동 가능.
