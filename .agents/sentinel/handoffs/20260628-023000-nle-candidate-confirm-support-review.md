DEX_REVIEW_READY
역할: 서린 (strict QE)
범위: NLE candidate-confirm cutover support review
읽은 파일:
- `core/project/nle_dual_write.py` ([core/project/nle_dual_write.py](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/core/project/nle_dual_write.py))
- `ui/editor/editor_segments_stt_selection_flow.py` ([ui/editor/editor_segments_stt_selection_flow.py](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/ui/editor/editor_segments_stt_selection_flow.py))
- `ui/editor/ux/editor_segments_live_preview.py` ([ui/editor/ux/editor_segments_live_preview.py](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/ui/editor/ux/editor_segments_live_preview.py))
- `tests/test_project_nle_dual_write.py` ([tests/test_project_nle_dual_write.py](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/tests/test_project_nle_dual_write.py))
결론: STT 후보 선택 및 확정(confirm) 자막 승격 시 NLE dual-write 연동을 위한 안전 가드 설계, 데이터 격리, Fallback 보존, 포커스 및 실행 취소(Undo) 정밀성 검증 방안을 수립하였습니다.
findings:
1. **자막 피드와 STT Candidate Lane의 격리**:
   - `build_subtitle_live_editor_feed`를 통한 타임라인 렌더링 피드와 STT candidate lane의 데이터 경계가 confirm 라우팅 시 섞이지 않도록 candidate 메타데이터(`stt_candidates`, `linked_caption_id` 등)가 NLE snapshot 내에 누락되지 않고 정확히 기재되어야 합니다.
2. **후보 선택 시 overlap/non_monotonic/invalid gate**:
   - `select_stt_candidate_as_subtitle` 에서 `extend_manual_stt_selection_into_trailing_silence` 로 인해 자막 끝점이 무음 구간을 흡수하며 변경되는데, 이로 인한 타임라인 상의 monotonic 순서와 overlap 위반 여부가 `_validate_after_projection`에서 빈틈없이 검출되어야 합니다.
3. **기존 Taption/source-app 후보 선택 fallback 보존**:
   - `apply_candidate_confirm_dual_write_pilot` 호출 후 예외가 발생하거나 `None`이 반환되는 즉시 기존 로컬 `QTextDocument` 기반 후보 선택 갱신 로직(`_trim_final_segments_around_candidate` 및 `_reload_segments_from_list` 편집 루틴)으로 자연스럽게 fallback 하도록 예외 처리 분기가 이중화되어야 합니다.
4. **Undo/Snapshot Focus 보존**:
   - 후보 확정 완료 후 에디터의 텍스트 포커스(text_edit.hasFocus())와 커서 위치가 유지되어야 하며, 실행 취소(Undo) 시 원본 텍스트 및 시간 정보가 QTextDocument 스냅샷 역사에 맞추어 오차 없이 복원되어야 합니다.
5. **focused tests와 문서 evidence gap**:
   - `tests/test_project_nle_dual_write.py` 내에 `test_candidate_confirm_dual_write_routes_through_nle_state` 및 `test_candidate_confirm_dual_write_rejects_overlap` 테스트 케이스 추가가 필요합니다.
   - `tests/test_stt_recheck_service.py`에 후보 선택 전후의 STT candidate validation 검증 테스트가 보완되어야 합니다.
defer: (none)
덱스 확인 포인트:
- 후보 선택 시 final subtitle 영역과 stt candidate lane이 NLE state 내에서 target_ids 바인딩을 통해 정밀 격리되고 올바르게 confirm 상태가 전이되는지 구조 확인.
