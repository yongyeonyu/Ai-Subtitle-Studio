# RELEASE v04.01.24

Date: 2026-06-29 KST
Previous release: `v04.01.23`
Release app version: `04.01.24`
Project schema version: `04.01.24`

## Scope

`v04.01.24` is a focused G2 canonical load-owner rollback-boundary audit
checkpoint. It proves a future candidate payload that claims canonical
top-level `nle`, `nle_snapshot`, or runtime-state ownership is stripped back to
legacy `editor_state` loading before default load or resave can adopt it.

This release does not switch project load ownership, make top-level `nle` or
`nle_snapshot` canonical, persist `_nle_project_state`, replace legacy
`editor_state`, change UI/UX, change subtitle generation, change STT/cache
defaults, build/sign/upload App Store packages, or claim App Store readiness.
Owner approval exists for the G0 App Store execution lane and persisted NLE/UI
structure scope, but this checkpoint is audit evidence only.

## Changes

- Version/schema:
  - `core/runtime/config.py` now reports `APP_VERSION = "04.01.24"`.
  - `core/project/project_format.py` now marks newly saved project payloads as schema version `04.01.24`.
- G2 NLE rollback-boundary audit:
  - `tools/audit_nle_persistence_cutover.py` now includes a canonical load-owner rollback-boundary check.
  - The check writes a candidate payload that attempts to promote top-level `nle`, `nle_snapshot`, and `_nle_project_state` to canonical/runtime persistence, then proves read/load strips those claims and preserves legacy rows.
  - The canonical load-owner gate matrix now records `rollback_boundary_defined=ready`, while load-owner change, `nle_snapshot` canonical source, runtime-state persistence, legacy disk-shape replacement, and final cutover remain blocked.

## Evidence

- Audit report: `output/manual_verification/latest/nle_load_owner_rollback_boundary_v040124_20260629_1138/nle_persistence_cutover_audit.md`
- Audit JSON: `output/manual_verification/latest/nle_load_owner_rollback_boundary_v040124_20260629_1138/nle_persistence_cutover_audit.json`
- Completed action archive: `docs/planning_queue/COMPLETED_ACTION_ITEMS.md#v040124-g2-canonical-load-owner-rollback-boundary-audit`

Current G2 state remains blocked: `persistence_cutover_ready=false`,
`overall_stoplight=red`, ready/blocked gates `7/5`, current canonical owner
`legacy_editor_state`, target candidate `top_level_nle_shadow_metadata`, and
`rollback_boundary_defined=ready`.

## Verification

- `./venv/bin/python -m py_compile tools/audit_nle_persistence_cutover.py tests/test_nle_persistence_cutover_audit.py core/runtime/config.py core/project/project_format.py tests/test_macos_bundle_runtime_paths.py` -> pass
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_nle_persistence_cutover_audit.py` -> `6 passed`
- `./venv/bin/python tools/audit_nle_persistence_cutover.py --output-dir output/manual_verification/latest/nle_load_owner_rollback_boundary_v040124_20260629_1138` -> `status=blocked`, `overall_stoplight=red`, ready/blocked gates `7/5`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_nle_persistence_cutover_audit.py tests/test_nle_canonical_load_owner_review_packet.py tests/test_project_nle_persistence_guard.py tests/test_project_nle_snapshot.py tests/test_macos_bundle_runtime_paths.py` -> `39 passed, 4 subtests passed`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_context.py tests/test_cp03_cp04_status_ui.py -k "schema or version or project_file_roundtrip or status"` -> `66 passed, 80 deselected`
- Direct version assertion -> `APP_VERSION=04.01.24`, `PROJECT_SCHEMA_VERSION=04.01.24`
- `git diff --check -- .` -> pass
