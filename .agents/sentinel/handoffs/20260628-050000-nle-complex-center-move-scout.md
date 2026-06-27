DEX_REVIEW_READY
역할: 잼민이 (lightweight chores / prep work)
프로젝트: AI Subtitle Studio
레포지토리 경로: /Users/u_mo_c/Downloads/ai_subtitle_studio
범위: NLE complex center move commit scout

findings (10줄 이내 요약):
1. **필요 owner 함수**: `core/native_swift_timeline.py` 의 `plan_subtitle_timing_edit_via_swift` (Taption timing 계산), `editor_timeline_video.py` 의 `_on_seg_time_changed` (커밋 핸들러), `nle_dual_write.py` 의 `apply_caption_move_dual_write_pilot` (NLE 연산).
2. **주요 위험**: Swift-based timing plan 이 반환하는 complex gap absorption/overwrite trim 연산이 NLE `caption_move` 연산의 final-overlap validation 가드와 충돌하여 롤백(validation failure)을 발생시킬 우려가 큼. stt_pending draft 가 섞일 시 projection mismatch 위험 존재.
3. **테스트 갱신 포인트**: `tests/test_project_nle_dual_write.py` 및 `tests/test_timeline_playhead_fit.py` 에 complex center shift (magnet/gap snap/overwrite) 발생 시 NLE dual-write mapping 정합성 및 frame-snapped projected_rows 호환 검증 테스트 추가.
