DEX_REVIEW_READY
역할: 잼민이 (lightweight chores / prep work)
프로젝트: AI Subtitle Studio
레포지토리 경로: /Users/u_mo_c/Downloads/ai_subtitle_studio
범위: NLE center body move commit-boundary scout

읽은 파일:
- `ACTION_ITEMS.md` ([ACTION_ITEMS.md](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/ACTION_ITEMS.md))
- `ui/editor/ux/editor_timeline_video.py` ([editor_timeline_video.py](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/ui/editor/ux/editor_timeline_video.py))
- `core/project/nle_dual_write.py` ([nle_dual_write.py](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/core/project/nle_dual_write.py))
- `tests/test_project_nle_dual_write.py` ([test_project_nle_dual_write.py](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/tests/test_project_nle_dual_write.py))

결론: 자막 바디 드래그 이동(center move) 완료 시점 중 final-caption overlap이 생기지 않는 순수 이동(pure move)만을 NLE `caption_move` dual-write로 결합하기 위한 연동 흐름, 추가 테스트, fallback 조건 및 리스크 분석을 스카우트 완료했습니다.

findings:
1) **추가해야 할 최소 테스트 설계**:
   - `test_project_nle_dual_write.py` 내에 순수 center move 검증 케이스 추가:
     - `test_caption_move_pure_center_shift_without_overlap`: 이웃 자막들과 겹치지 않는 빈 gap 영역으로 자막을 이동(`center`) 시켰을 때 NLE dual-write가 에러 없이 통과하고 projected_rows에 최종 시간이 정상 반영되는지 검증.
     - `test_caption_move_pure_center_shift_rejects_overlap_without_reorder`: reorder 인자 없이 center move 시켜 이웃 자막과 강제 중첩을 유도했을 때, `NLEOperationValidationError` (또는 `operation_final_overlap`)가 정상적으로 raise 되며 state mutation이 롤백되는지 검증.

2) **레거시 fallback 조건 (Taption 규칙 보존)**:
   - `_on_seg_time_changed` 진입 시 NLE sync를 시도하되, 아래 조건 중 하나에 걸리면 레거시 timing planning(`plan_subtitle_timing_edit_via_swift` / `reloader`)으로 즉각 우회(fallback) 처리해야 합니다:
     - `editing_transient_stt = True` (STT2 preview나 live_preview 등 draft 자막을 다루는 경우 - NLE는 final captions만 관리함)
     - NLE dual-write 호출 중 `NLEOperationValidationError` 또는 `ValueError` 예외가 발생한 경우 (unfixable overlap 등)
     - Taption gap absorption 이나 복잡한 magnet-off gap overwrite 규칙 등 projection consistency assertion을 일시적으로 이탈하는 sequence timing edit가 감지될 때.

3) **피해야 할 위험 (Risky Zones)**:
   - **NLE projection consistent 오염 방지**: `stt_pending` 또는 `_live_stt_preview` 가 섞인 segments 데이터를 NLE state에 주입하여 write-path를 찌르면 consistent validation assertion이 터집니다. 반드시 NLE projection 전 clean-up 필터링 단계를 유지해야 합니다.
   - **Save/Reopen ID 보존 누출**: center move 시 자막의 canonical ID mapping이 틀어지면 save/reopen 후 자막 데이터가 유실되거나 꼬입니다. atomic undo snapshot 및 ID 보존 로직과 완전히 정합하는 안전지대 안에서만 sync해야 합니다.
   - **try-finally 구조 가드 누락**: NLE write 동작 중 예외 발생 시 `self._sync_lock = False` 및 `QTextCursor.endEditBlock()` 해제가 누락될 경우 UI lockup leak이 생기므로, 모든 NLE mutable call은 안전한 try-finally 내부에서 보호되어야 합니다.

defer: (none)
덱스 확인 포인트:
- `_on_seg_time_changed` 내에서 `center` move 동작이 일어났을 때, overlap이 없는 pure shift 조건에서 NLE dual-write를 결합하되 예외 시 레거시 fallback이 완전 작동하도록 구조 설계.
