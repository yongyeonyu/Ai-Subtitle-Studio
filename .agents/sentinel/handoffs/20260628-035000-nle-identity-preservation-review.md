DEX_REVIEW_READY
역할: 한결 (architecture & maintainability)
범위: AI Subtitle Studio NLE identity preservation review
읽은 파일:
- `core/project/project_context.py` ([project_context.py](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/core/project/project_context.py))
- `core/project/nle_dual_write.py` ([nle_dual_write.py](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/core/project/nle_dual_write.py))
- `tests/test_project_nle_dual_write.py` ([test_project_nle_dual_write.py](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/tests/test_project_nle_dual_write.py))
- `tests/test_nle_persistence_cutover_audit.py` ([test_nle_persistence_cutover_audit.py](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/tests/test_nle_persistence_cutover_audit.py))

결론: 일반 `build_editor_state` 동작과의 하위 호환성을 완격히 유지하면서, NLE shadow projection 시에만 안전하게 ID preservation이 격리 적용되고 있음을 아키텍처 관점에서 확인 및 승인합니다.

findings:
1) **`build_editor_state` legacy canonicalization 호환성**:
   - `core/project/project_context.py:988` 의 `build_editor_state` 정의 및 내부 헬퍼 `_normalize_editor_segments` 에서 `preserve_segment_identity: bool = False` 가 기본값으로 명확히 규정되어 있습니다.
   - 이로 인해 일반 UI 로직이나 레거시 세그먼트 생성 흐름에서는 정규화 규칙(ID 재생성 등)이 기존과 완전히 호환되는 상태로 보존됩니다.

2) **NLE shadow scope 에서의 격리 적용**:
   - `core/project/nle_dual_write.py` 의 `_shadow_project_with_rows` 내에서만 `build_editor_state(..., preserve_segment_identity=True)`를 켜도록 구현되어 있어, 듀얼라이트 섀도 프로젝션 중 임시 roundtrip을 검사할 때만 ID 유실이 차단되도록 스코프가 좁고 안전하게 격리되었습니다.

3) **`candidate_confirm` 의 Identity Preservation 및 Canonicalization**:
   - 헬퍼 함수 `_canonicalize_confirmed_caption_identities`가 confirm 대상 후보 자막(`caption_1` 등)을 이전 자막 집합(`before_candidates`)의 시간 영역과 대조하여 최적의 오버랩을 가진 기존 `subtitle_vector_XXXX` ID로 안전하게 복원/대체시켜 줍니다.
   - 매칭되지 않는 완전 신규 자막의 경우 `id`를 `pop`하여 dynamic ID 발급을 유도하므로, STT 후보와 최종 row 간의 drift가 원천 차단됩니다.

4) **무승인 디스크 포맷(shape) 변경 통제**:
   - `UNAPPROVED_NLE_PERSISTENCE_KEYS` 가드 코드로 인해, 듀얼라이트 상태를 검증하는 도중 작성되는 모든 `.aissproj` 임시 세이브 파일의 디스크 스토리지에는 어떠한 unapproved persisted NLE 필드(`nle`, `nle_snapshot`, `_nle_project_state`)도 기록되지 않고 격리(Quarantine) 처리되는 상태를 확답합니다. (단위 테스트 `test_gap_delete_dual_write_does_not_persist_runtime_nle_fields`가 이를 상시 QE 게이트로 강제함)

defer: (none)
덱스 확인 포인트:
- `build_editor_state` 기본값 호환성과 NLE shadow 스코프에서의 `preserve_segment_identity=True` 격리 스위칭 상태 확인.
- `_canonicalize_confirmed_caption_identities` 내에서 overlap 0초 초과(`best_overlap > 0.0`) 조건과 ID pop 동작을 통한 STT2 후보 confirm 정규화 안정성 확인.
