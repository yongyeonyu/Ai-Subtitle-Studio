# RELEASE v04.01.21

Date: 2026-06-29 KST
Previous release: `v04.01.20`
Release app version: `04.01.21`
Project schema version: `04.01.21`

## Scope

`v04.01.21` is a focused G2 top-level NLE gap projection coverage checkpoint.
It closes the previous `top_level_nle_projection_gap_coverage_missing` blocker as
compatibility-audit evidence only.

This release does not switch project load ownership to NLE, make `nle_snapshot`
or top-level `nle` canonical, persist `_nle_project_state`, remove legacy
`editor_state`, change UI/UX, change STT/cache defaults, or prove App Store
packaging/signing/upload/submission readiness.

## Changes

- Version/schema:
  - `core/runtime/config.py` now reports `APP_VERSION = "04.01.21"`.
  - `core/project/project_format.py` now marks newly saved project payloads as schema version `04.01.21`.
- G2 NLE compatibility projection:
  - `core/project/nle_snapshot.py` now models legacy gap rows as non-caption `GapSegment` metadata on `Sequence.gaps` inside approved NLE shadow payloads.
  - Approved top-level `nle` shadow payloads now include a dedicated `gaps` track and `gap_count` metadata.
  - `tools/audit_nle_persistence_cutover.py` now projects top-level `nle` captions plus gap metadata into an explicit compatibility row view while preserving default legacy load ownership.
  - The audit now reports explicit top-level row/caption/gap count `3/2/1`, default legacy row/caption/gap count `3/2/1`, and `gap_coverage_ready=true`.
  - The report remains blocked for canonical cutover with `top_level_nle_canonical_projection_complete=false`, `canonical_load_owner_change_allowed=false`, and `disk_format_cutover_allowed=false`.

## Evidence

- Audit report: `output/manual_verification/latest/nle_top_level_gap_projection_v040121_20260629_1041/nle_persistence_cutover_audit.md`
- Audit JSON: `output/manual_verification/latest/nle_top_level_gap_projection_v040121_20260629_1041/nle_persistence_cutover_audit.json`
- Completed action archive: `docs/planning_queue/COMPLETED_ACTION_ITEMS.md#v040121-g2-top-level-nle-gap-projection-coverage-audit`

## Verification

- `./venv/bin/python -m py_compile core/project/nle_snapshot.py tools/audit_nle_persistence_cutover.py tests/test_nle_persistence_cutover_audit.py tests/test_project_nle_snapshot.py tests/test_project_nle_persistence_guard.py core/runtime/config.py core/project/project_format.py tests/test_macos_bundle_runtime_paths.py`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_nle_persistence_cutover_audit.py`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_persistence_guard.py tests/test_project_nle_snapshot.py -k "top_level or readback or direct_srt or snapshot_adapter"`
- `./venv/bin/python tools/audit_nle_persistence_cutover.py --output-dir output/manual_verification/latest/nle_top_level_gap_projection_v040121_20260629_1041`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_nle_persistence_cutover_audit.py tests/test_nle_canonical_load_owner_review_packet.py tests/test_project_nle_persistence_guard.py tests/test_project_nle_snapshot.py tests/test_macos_bundle_runtime_paths.py` -> `39 passed, 4 subtests passed`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_context.py tests/test_cp03_cp04_status_ui.py -k "schema or version or project_file_roundtrip or status"` -> `66 passed, 80 deselected`
- Direct version assertion -> `APP_VERSION=04.01.21`, `PROJECT_SCHEMA_VERSION=04.01.21`
- `git diff --check -- .` -> pass
