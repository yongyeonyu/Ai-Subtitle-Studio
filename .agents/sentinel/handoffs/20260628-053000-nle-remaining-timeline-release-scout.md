DEX_REVIEW_READY
역할: 잼민이 (lightweight chores / prep work)
프로젝트: AI Subtitle Studio
레포지토리 경로: /Users/u_mo_c/Downloads/ai_subtitle_studio
범위: AI Subtitle Studio remaining NLE timeline release source scout

findings (12줄 이내 요약):
1. **후보1: Diamond drag delete (`_on_diamond_delete`)**
   - **Owner function**: `ui/editor/ux/editor_timeline_segment_merge.py` 의 `_on_diamond_delete`
   - **설명**: 자막 경계선을 다른 자막으로 덮어쓸 때, 팝업 메뉴에서 "지우기" 선택 시 발생하는 release commit.
   - **위험**: 한쪽 자막은 삭제되고 남은 자막은 확장되는 복합 수정이며, NLE delete와 resize pilot이 원자적으로 수행되지 않으면 save/reopen 정합성 붕괴 위험.
   - **추천 테스트**: `tests/test_timeline_playhead_fit.py` 에 diamond drag delete triggering 후 NLE projected_rows의 overlap-free 병합 검증 추가.
2. **후보2: 화자 드롭/분할 (`speaker_circle_dropped` / `sig_speaker_split_request`)**
   - **Owner function**: `editor_widget.py` 의 화자 변경 및 split/merge 핸들러.
   - **설명**: 화자 서클을 드래그-드롭하여 자막의 화자를 병합하거나 쪼개서 확정하는 release commit.
   - **위험**: 화자 ID 변경이 NLE State Runtime에 sync되지 않을 시 `save-project` projection drift 유발.
   - **추천 테스트**: `tests/test_project_nle_dual_write.py` 에 speaker split/change NLE parity roundtrip 검증 추가.
