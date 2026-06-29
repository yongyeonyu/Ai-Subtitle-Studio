# RELEASE v04.01.27

Date: 2026-06-29 KST

Release app version: `04.01.27`
Project schema version: `04.01.27`

## Summary

`v04.01.27` is a focused G2 top-level `nle` canonical load opt-in proof checkpoint.
It allows top-level `nle` rows to drive project load only when an explicit
owner-approved canonical-load policy is present and paired `nle_snapshot` rows
agree. Legacy `editor_state` remains on disk for rollback.

This is not `nle_snapshot` standalone canonical sourcing, persisted
`_nle_project_state`, legacy disk-shape replacement, final NLE cutover, UI/UX
change, STT/cache default change, or App Store package/signing/upload/submission
proof.

## Changes

- `core/runtime/config.py` now reports `APP_VERSION = "04.01.27"`.
- `core/project/project_format.py` now marks newly saved project payloads as
  schema version `04.01.27`.
- `core/project/nle_persistence_guard.py` separates legacy top-level shadow
  metadata from explicit top-level canonical-load opt-in policy.
- `core/project/nle_snapshot.py` exposes top-level `nle` / `nle_snapshot` row
  projection helpers for caption and gap rows.
- `core/project/project_context.py` uses top-level `nle` rows only when explicit
  opt-in policy exists and paired `nle_snapshot` rows agree; companion drift
  fails closed to legacy rows.
- `core/project/project_format.py` preserves legacy `editor_state` rows for
  rollback while writing approved canonical-load metadata and matching
  `nle_snapshot` metadata.
- `tools/audit_nle_persistence_cutover.py` now includes the canonical load opt-in
  proof and exposes the remaining cutover blockers directly.

## Evidence

- NLE audit:
  `output/manual_verification/latest/nle_canonical_load_opt_in_v040127_20260629_1248/nle_persistence_cutover_audit.md`
- Audit state: `status=blocked`, `prep_ready=true`,
  `persistence_cutover_ready=false`, overall stoplight `red`, ready/blocked
  gates `8/4`.
- Explicit opt-in canonical owner: `top_level_nle_shadow_metadata`.
- Ready gate added: `canonical_load_owner_change_allowed`.
- Canonical load proof: loaded/runtime/reloaded/storage `nle`/storage
  `nle_snapshot` first caption text all remain `nle canonical first`.
- Rollback proof: legacy `editor_state` first caption text after resave remains
  `first`.
- Remaining blocked gates: `nle_snapshot_canonical_load_source_allowed`,
  `runtime_project_state_persistence_allowed`,
  `legacy_disk_shape_replacement_allowed`, and `final_cutover_ready`.

## Validation

- `./venv/bin/python -m py_compile core/project/nle_persistence_guard.py core/project/project_format.py core/project/nle_snapshot.py core/project/project_context.py tools/audit_nle_persistence_cutover.py tests/test_project_nle_persistence_guard.py tests/test_nle_persistence_cutover_audit.py tests/test_macos_bundle_runtime_paths.py core/runtime/config.py`
  -> pass
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_persistence_guard.py tests/test_nle_persistence_cutover_audit.py tests/test_macos_bundle_runtime_paths.py`
  -> `22 passed`
- `./venv/bin/python tools/audit_nle_persistence_cutover.py --output-dir output/manual_verification/latest/nle_canonical_load_opt_in_v040127_20260629_1248`
  -> `status=blocked`, ready/blocked gates `8/4`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_context.py tests/test_cp03_cp04_status_ui.py -k "schema or version or project_file_roundtrip or status"`
  -> `66 passed, 80 deselected`
- Direct version assertion -> `APP_VERSION=04.01.27`,
  `PROJECT_SCHEMA_VERSION=04.01.27`
- `git diff --check -- .` -> pass

## Coordination

Three sub-agent reviews were used as architecture, QE, and editor-workflow
guardrails. Jammini `--status` resolved the active route, but the current
`--handoff-probe` packet did not produce a fresh physical handoff file; the
latest physical route proof remains
`.agents/sentinel/handoffs/20260629-070211-watchdog-handoff-probe.md`.
