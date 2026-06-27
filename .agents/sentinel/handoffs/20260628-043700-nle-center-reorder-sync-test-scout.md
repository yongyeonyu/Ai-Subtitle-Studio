DEX_REVIEW_READY
역할: 잼민이 (lightweight chores / prep work)
프로젝트: AI Subtitle Studio
레포지토리 경로: /Users/u_mo_c/Downloads/ai_subtitle_studio
범위: NLE center-reorder commit-boundary test scout

읽은 파일:
- `tests/test_project_nle_dual_write.py` ([test_project_nle_dual_write.py](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/tests/test_project_nle_dual_write.py))
- `tests/test_timeline_playhead_fit.py` ([test_timeline_playhead_fit.py](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/tests/test_timeline_playhead_fit.py))
- `ui/editor/ux/editor_timeline_video.py` ([editor_timeline_video.py](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/ui/editor/ux/editor_timeline_video.py))

결론: Taption immediate-neighbor `center_reorder` 마우스 릴리즈 커밋을 NLE `caption_move` dual-write로 결합하기 위한 기존 테스트 연동 구조, 최소 추가 assertion, fallback 회귀 테스트 설계 및 pytest 검증 명령을 스카우트 완료했습니다.

findings:
1) **기존 테스트 연동 구조 및 추가/수정할 최소 Assertion**:
   - `test_project_nle_dual_write.py:142` 의 `test_caption_move_dual_write_supports_taption_neighbor_reorder_contract` 는 이미 `apply_caption_move_dual_write_pilot` 를 통한 reorder contract 검증이 정밀히 되어 있습니다.
   - **추가할 assertion**: `editor_timeline_video.py` 가 `center_reorder_left/right` 에 해당하는 release 시그널을 받았을 때, NLE state의 mutable sync 결과(`reordered_rows`)와 `apply_caption_move_dual_write_pilot` 의 return parity가 동일한 frame-snapped boundary에 놓여있음을 assert.
     ```python
     # reorder_neighbor_id 가 연결된 caption_move pilot 호출 결과 assert 추가
     self.assertEqual(result.operation.metadata["reorder_direction"], "left") # or "right"
     self.assertEqual(result.projected_rows[target_idx]["start_frame"], expected_start)
     ```

2) **Fallback 회귀 테스트 설계**:
   - NLE dual-write sync 연산 도중 `NLEOperationValidationError` (예: unfixable overlap 등) 또는 `ValueError` 가 발생해 롤백될 때, 기존의 Taption magnet/gap/reorder UX를 깨뜨리지 않기 위해 즉각 레거시 timing planning 및 reloader(`plan_subtitle_timing_edit_via_swift` / `_reload_segments_from_list`)로 안전하게 fallback 하는 회귀 테스트가 필수적입니다.
   - **회귀 테스트 구현 제안**:
     ```python
     def test_on_seg_time_changed_center_reorder_fallback_on_nle_validation_failure(self):
         # 1. NLE validation error를 강제하는 mock state 주입
         # 2. _on_seg_time_changed(line, start, end, "center_reorder_left") 호출
         # 3. ValueError가 발생해도 swallow 되고 legacy swift planning 및 reloader가 안정적으로 복구 구동됨을 검증
     ```

3) **실행할 pytest / QA 검증 명령**:
   - **NLE dual-write 단위 테스트**:
     ```bash
     QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_dual_write.py
     ```
   - **타임라인 에디터 인터랙션 / magnet / reorder 테스트**:
     ```bash
     QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py -k "reorder or magnet or timing"
     ```
   - **전체 quick QA suite smoke run**:
     ```bash
     AI_SUBTITLE_STUDIO_QA_USE_SOURCE=1 ./venv/bin/python tools/qa_suite_runner.py quick
     ```

4) **지금 바로 변경하면 위험한 지점 (Risky Zones)**:
   - **NLE write 실패 시 롤백 누락**: `_on_seg_time_changed` 에서 NLE resize/move write 시도 중 예외 발생 시, `self._sync_lock` 과 QTextCursor edit block `cur.endEditBlock()` 이 제대로 해제되지 않고 locking 상태에 갇힐 경우(leak) UI가 먹통이 될 수 있습니다. 모든 NLE call은 try-finally 구조 내부에서 안전하게 보호되어야 합니다.

defer: (none)
덱스 확인 포인트:
- Taption reorder contract에 대응하여 `_on_seg_time_changed` 내에 NLE mutable `caption_move` sync를 연동하되, 예외 발생 시 레거시 fallback이 완전 차단되도록 설계에 반영.
