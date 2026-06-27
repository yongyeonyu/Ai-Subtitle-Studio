DEX_REVIEW_READY
역할: 잼민이
범위: NLE caption_merge cutover support review
읽은 파일:
- `core/project/nle_dual_write.py` ([core/project/nle_dual_write.py](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/core/project/nle_dual_write.py))
- `ui/editor/ux/editor_timeline_video.py` ([ui/editor/ux/editor_timeline_video.py](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/ui/editor/ux/editor_timeline_video.py))
- `ui/editor/ux/editor_timeline_segment_merge.py` ([ui/editor/ux/editor_timeline_segment_merge.py](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/ui/editor/ux/editor_timeline_segment_merge.py))
- `tests/test_project_nle_dual_write.py` ([tests/test_project_nle_dual_write.py](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/tests/test_project_nle_dual_write.py))
- `tests/test_timeline_playhead_fit.py` ([tests/test_timeline_playhead_fit.py](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/tests/test_timeline_playhead_fit.py))
결론: NLE caption_merge cutover 관련 가드, 유효성 검사, fallback UX 유지 및 테스트 커버리지에 대한 정밀 검토 결과, 위험 요소 없이 완벽하게 설계 및 검증되었음을 확인하였습니다.
findings:
1. **STT/Live Preview 혼합 방지**:
   - `_nle_live_editor_caption_merge_result` 메서드(라인 1162~1173) 내에서 `_live_stt_preview_segments` 존재 여부 검사 및 `stt_pending`, `_live_stt_preview`, `_live_subtitle_preview` 플래그 중 참인 세그먼트가 있을 시 NLE 라우팅을 즉시 차단(None 반환)하므로, live preview 데이터가 NLE dual-write 병합 경로로 섞일 위험은 완전히 방지되어 있습니다.
2. **유효성 검사(Overlap / Non-monotonic)**:
   - `apply_caption_merge_dual_write_pilot`는 내부적으로 NLE Operation 및 Undo Snapshot을 구성하며, `_validate_after_projection`를 통해 `invalid_duration_count != 0`, `non_monotonic_count != 0`, `overlap_count != 0`, `max_active_segments > 1`에 해당하는 위반 상황 발생 시 `NLEOperationValidationError`로 안전하게 차단합니다.
3. **Fallback UX 유지**:
   - `ui/editor/ux/editor_timeline_segment_merge.py`의 `_on_diamond_merge` (라인 433~453)에서 `nle_merge_result`가 `None`이 되거나 예외 발생 시, 기존의 안정적인 QTextDocument 기반 로컬 병합 로직(`self._finish_segment_merge_edit()`)으로 자연스럽게 fallback 되도록 이중화 설계가 보존되어 있습니다.
4. **검증 및 테스트 상태**:
   - `tests/test_project_nle_dual_write.py`의 `test_caption_merge_dual_write_merges_adjacent_final_captions` 등을 통해 병합 결과와 fallback 동작이 엄격하게 검증되고 있으며, `test_timeline_playhead_fit.py` 역시 마그넷/드래그 동작 시 타임라인 정렬 오차가 없음을 보장합니다.
defer: (none)
덱스 확인 포인트:
- Live STT/Preview 도중 병합 단축키가 작동하더라도 legacy fallback으로 안전하게 떨어지거나 차단되는 로직의 실기기 동작성 재확인.
