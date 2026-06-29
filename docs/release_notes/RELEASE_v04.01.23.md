# RELEASE v04.01.23

Date: 2026-06-29 KST
Previous release: `v04.01.22`
Release app version: `04.01.23`
Project schema version: `04.01.23`

## Scope

`v04.01.23` is a focused G2 canonical load-owner gate matrix audit checkpoint.
It records exactly which preflight gates are ready and which still block any
future move from legacy `editor_state` loading toward top-level `nle` shadow
metadata.

This release does not switch project load ownership, make top-level `nle` or
`nle_snapshot` canonical, persist `_nle_project_state`, replace legacy
`editor_state`, change UI/UX, change subtitle generation, change STT/cache
defaults, build/sign/upload App Store packages, or claim App Store readiness.

## Changes

- Version/schema:
  - `core/runtime/config.py` now reports `APP_VERSION = "04.01.23"`.
  - `core/project/project_format.py` now marks newly saved project payloads as schema version `04.01.23`.
- G2 NLE cutover audit:
  - `tools/audit_nle_persistence_cutover.py` now reports `app_version`.
  - The audit now includes a canonical load-owner gate matrix with ordered ready/blocked gates, red stoplight, current owner, target candidate, and non-cutover flags.
  - The compatibility projection check now proves a deliberate top-level `nle` text override is visible only in explicit shadow projection while default load and resave preserve legacy caption text.

## Evidence

- Audit report: `output/manual_verification/latest/nle_canonical_load_owner_gate_matrix_v040123_20260629_1115/nle_persistence_cutover_audit.md`
- Audit JSON: `output/manual_verification/latest/nle_canonical_load_owner_gate_matrix_v040123_20260629_1115/nle_persistence_cutover_audit.json`
- Completed action archive: `docs/planning_queue/COMPLETED_ACTION_ITEMS.md#v040123-g2-canonical-load-owner-gate-matrix-audit`

Current G2 state remains blocked: `persistence_cutover_ready=false`,
`overall_stoplight=red`, ready/blocked gates `6/6`, current canonical owner
`legacy_editor_state`, and target candidate `top_level_nle_shadow_metadata`.

## Verification

- `./venv/bin/python -m py_compile tools/audit_nle_persistence_cutover.py tests/test_nle_persistence_cutover_audit.py core/runtime/config.py core/project/project_format.py tests/test_macos_bundle_runtime_paths.py` -> pass
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_nle_persistence_cutover_audit.py` -> `6 passed`
- `./venv/bin/python tools/audit_nle_persistence_cutover.py --output-dir output/manual_verification/latest/nle_canonical_load_owner_gate_matrix_v040123_20260629_1115` -> `status=blocked`, `overall_stoplight=red`, ready/blocked gates `6/6`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_nle_persistence_cutover_audit.py tests/test_nle_canonical_load_owner_review_packet.py tests/test_project_nle_persistence_guard.py tests/test_project_nle_snapshot.py tests/test_macos_bundle_runtime_paths.py` -> `39 passed, 4 subtests passed`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_context.py tests/test_cp03_cp04_status_ui.py -k "schema or version or project_file_roundtrip or status"` -> `66 passed, 80 deselected`
- Direct version assertion -> `APP_VERSION=04.01.23`, `PROJECT_SCHEMA_VERSION=04.01.23`
- `git diff --check -- .` -> pass
