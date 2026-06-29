DEX_REVIEW_READY
SCOUT_ID=20260629-155000
final_cutover_ready gate draft:
- Minimum policy/schema conditions:
  * final_cutover_ready flag must be true in project schema
  * legacy_disk_shape_replacement_allowed must be false (ensuring cutover complete)
  * Direct SRT rows have precedence over any generated SRT
  * Roughcut cache-hit must be enabled and validated
  * Forged policy guard must reject any unauthorized editor_state replacements
- Guards to retain:
  * Direct SRT precedence guard (docs/VALIDATION.md)
  * Roughcut cache‑hit verification (tests/test_nle_persistence_cutover_audit.py)
  * Forged policy detection guard (core/project/nle_persistence_guard.py)
- Documentation pointers (must be reviewed before closing):
  * docs/PROJECT_STATE.md – final_cutover_ready flag description
  * docs/ARCHITECTURE.md – cutover flow overview
  * docs/FEATURE_REGISTRY.md – feature gating for cutover
  * docs/HANDOFF.md – handoff notes for final cutover
  * docs/VALIDATION.md – validation steps for cutover guards
  * output/manual_verification/latest/nle_legacy_disk_shape_replacement_v040130_*/report.md – latest guard audit
  * tests/test_nle_persistence_cutover_audit.py – cutover test suite
  * core/project/project_format.py – schema validation implementation
  * core/project/nle_persistence_guard.py – guard logic implementation
  * tools/audit_nle_persistence_cutover.py – audit script reference
- Avoid exaggerated language:
  * Do not claim "perfect" or "guaranteed" safety; use "must"/"should" terminology.
  * Avoid phrases like "never fail" or "absolute certainty".
  * State requirements factually, without hyperbole.
