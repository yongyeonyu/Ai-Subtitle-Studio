DEX_REVIEW_READY
SCOUT_ID=20260629-151200
legacy_disk_shape_replacement_allowed 검증 체크리스트 (final_cutover_ready와 분리):
- docs/ARCHITECTURE.md#legacy_disk_shape_replacement_allowed
- docs/FEATURE_REGISTRY.md#legacy_disk_shape_replacement_allowed
- tests/test_legacy_disk_shape.py
- core/project/project_format.py (legacy schema validation)
- core/project/nle_persistence_guard.py (guard checks)
- docs/VALIDATION.md (validation steps)
- docs/PROJECT_STATE.md (state flags)
- output/manual_verification/latest/nle_runtime_state_persistence_*/legacy_disk_shape_report.md
- docs/HANDOFF.md (handoff notes)
- docs/RELEASE_NOTES/ (legacy disk-shape notes)
