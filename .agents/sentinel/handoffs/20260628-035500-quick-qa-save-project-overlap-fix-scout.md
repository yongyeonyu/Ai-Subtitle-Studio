DEX_REVIEW_READY
역할: 잼민이 (lightweight chores / prep work)
범위: AI Subtitle Studio quick QA save-project failure support
읽은 파일:
- `output/manual_verification/latest/qa_suite_quick_nle_identity_preservation_retry_20260628/editor_compact_macau/summary.json` ([summary.json](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/qa_suite_quick_nle_identity_preservation_retry_20260628/editor_compact_macau/summary.json))
- `output/manual_verification/latest/qa_suite_quick_nle_identity_preservation_retry_20260628/editor_compact_macau/logs/save_project.stdout` ([save_project.stdout](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/qa_suite_quick_nle_identity_preservation_retry_20260628/editor_compact_macau/logs/save_project.stdout))
- `ui/main/app_command_bridge_handlers.py` ([app_command_bridge_handlers.py](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/ui/main/app_command_bridge_handlers.py))
- `ui/project/project_panel.py` ([project_panel.py](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/ui/project/project_panel.py))
- `ui/editor/editor_save_manager.py` ([editor_save_manager.py](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/ui/editor/editor_save_manager.py))

결론: `save-project` 커맨드 브릿지 핸들러에서 에디터의 지연 큐(`_flush_pending_segment_queue_now`)를 먼저 비우지 않고 segments를 stale 상태로 직접 getter 추출하여 `_save_current_project`에 주입함으로써, 임시 overlap 상태가 그대로 디스크로 프로젝션되어 `nle_save_export_final_overlap` 에러를 터트린 구조적 오동작 원인을 포착했습니다.

findings:
1) **동기화 큐 누락 분석**:
   - `app_command_bridge_handlers.py:793`에서 `save-project` 명령 처리 시 `editor._get_current_segments()`를 직접 실행하여 `segments` 변수에 긁어 담습니다.
   - 이후 `project_panel.py:382`의 `_save_current_project(segments=segments)` 가 실행될 때, 파라미터 `segments`가 None이 아니므로 `if segments is None and editor is not None:` 조건 블록이 우회됩니다.
   - 이로 인해 에디터의 변경 사항 지연 반영 큐를 강제 flush하는 `editor._flush_pending_segment_queue_now()` 가 완전히 생략되며, `merge_diamond` 직전의 smart split 과도기/stale segments가 디스크 세이브용 projection에 넘어가게 되어 overlap 에러를 유발합니다.

2) **소유 경로 (Owner Paths)**:
   - Command Bridge Routing: `ui/main/app_command_bridge_handlers.py` -> `_handle_save_export_command`
   - UI Project State Owner: `ui/project/project_panel.py` -> `_save_current_project`
   - Active Queue Synchronizer: `ui/editor/editor_save_manager.py` 및 `ui/editor/editor_actions.py` -> `_flush_pending_segment_queue_now`

3) **누락된 회귀 테스트 제안 (Missing Regression Test)**:
   - `tests/test_app_command_bridge.py` 상에 "큐에 펜딩된 세그먼트 데이터가 존재하는 상태에서 `save-project` 브릿지 명령이 유입되었을 때, 큐가 정상적으로 flush 및 sync된 최신 세그먼트로 저장 완료되는지" 검증하는 단위 테스트 추가가 필요합니다.
   ```python
   def test_bridge_save_project_flushes_pending_segment_queue_first(self):
       # 1. Mock editor와 pending queue를 가진 project_panel 셋업
       # 2. _segment_queue에 overlap을 유발할 수 있는 dirty state 적재
       # 3. app_command_bridge를 통해 "save-project" 전송
       # 4. _flush_pending_segment_queue_now 호출 여부 및 최종 target segments에 flush 결과 반영 검증
   ```

defer: (none)
덱스 확인 포인트:
- `app_command_bridge_handlers.py`의 `save-project` 처리 로직에서 segments를 getter로 긁기 직전에 `editor._flush_pending_segment_queue_now()`를 명시적으로 먼저 찌르도록 보강하는 조치를 덱스(Codex) 구현 시점으로 넘겨 검토.
