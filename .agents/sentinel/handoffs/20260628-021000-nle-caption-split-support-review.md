DEX_REVIEW_READY
역할: 서린 (strict QE)
범위: NLE caption_split cutover support review
읽은 파일:
- `core/project/nle_dual_write.py` ([core/project/nle_dual_write.py](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/core/project/nle_dual_write.py))
- `ui/editor/editor_segments_manual_edits.py` ([ui/editor/editor_segments_manual_edits.py](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/ui/editor/editor_segments_manual_edits.py))
- `tests/test_project_nle_dual_write.py` ([tests/test_project_nle_dual_write.py](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/tests/test_project_nle_dual_write.py))
- `tests/test_editor_split_undo.py` ([tests/test_editor_split_undo.py](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/tests/test_editor_split_undo.py))
- `ui/editor/ux/editor_timeline_gap_split.py` ([ui/editor/ux/editor_timeline_gap_split.py](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/ui/editor/ux/editor_timeline_gap_split.py))
결론: Smart split 및 Text/Speaker split 시 NLE dual-write 연동을 위한 안전 가드 설계, Fallback 보존, 포커스 및 실행 취소(Undo) 정밀성 검증 방안을 수립하였습니다.
findings:
1. **STT/Live Preview 격리 및 NLE split 라우팅 차단**:
   - `stt_pending`, `_live_stt_preview`, `_live_subtitle_preview` 플래그 중 하나라도 참인 프리뷰/임시 세그먼트가 에디터에 존재할 경우 NLE split 라우팅을 즉시 거부하고 `None`을 반환하여 legacy fallback을 안전하게 타도록 유도해야 합니다.
2. **final invalid/non_monotonic/overlap 무결성 게이트**:
   - 분할 기준 시간(`split_sec`)이 대상 자막의 `start_sec + 0.05` 이하이거나 `end_sec - 0.05` 이상일 경우, NLE validator가 무결성 위반으로 차단하기 전에 에디터 단에서 신속히 `return` 또는 거절해야 합니다.
   - 분할로 인해 생성된 2개의 세그먼트가 타임라인 상에서 겹치지 않고(overlap=0), 순차적 배열(non_monotonic=0)을 충족하는지 `_validate_after_projection`에서 한 번 더 검증되어야 합니다.
3. **기존 Taption/source-app split UX fallback 보존**:
   - `apply_caption_split_dual_write_pilot` 호출 후 예외가 발생하거나 `None`이 반환되는 즉시 기존 로컬 `QTextDocument` 기반 병합/분할 루틴(`split_segment_with_text` 및 `_on_smart_split` 내 QTextCursor 편집 로직)으로 자연스럽게 fallback 하도록 예외 처리 분기가 이중화되어야 합니다.
4. **Undo/Snapshot Focus 보존**:
   - `test_editor_split_undo.py`에서 증명하듯이 분할 완료 후 에디터의 텍스트 포커스(text_edit.hasFocus())와 커서 위치가 유지되어야 하며, 실행 취소(Undo) 시 원본 텍스트 및 시간 정보가 QTextDocument 스냅샷 역사에 맞추어 오차 없이 복원되어야 합니다.
5. **focused tests와 문서 evidence gap**:
   - `tests/test_project_nle_dual_write.py` 내에 `test_caption_split_dual_write_splits_caption` 및 `test_caption_split_dual_write_rejects_invalid_split_times` 테스트 케이스 추가가 필요합니다.
   - `test_editor_split_undo.py`에 NLE 라우팅 활성화 조건 하의 통합 실행 취소 검증 테스트가 보완되어야 합니다.
defer: (none)
덱스 확인 포인트:
- smart split(시간 분할)과 speaker split(화자 분할) 모두에 대해 NLE 듀얼라이트가 각각 고유의 `caption_split` 오퍼레이션 명세로 분기 라우팅되는지 설계 구조 확인.
