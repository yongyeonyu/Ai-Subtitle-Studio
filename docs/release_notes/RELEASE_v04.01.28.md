# RELEASE v04.01.28

Date: 2026-06-29 KST

Release app version: `04.01.28`
Project schema version: `04.01.28`

## Summary

`v04.01.28` is a focused G2 standalone `nle_snapshot` canonical load-source
opt-in proof checkpoint. It allows `nle_snapshot` rows to drive project load only
when an explicit owner-approved snapshot canonical-load policy is present.
Legacy `editor_state` remains on disk for rollback.

This is not persisted `_nle_project_state`, legacy disk-shape replacement, final
NLE cutover, UI/UX change, STT/cache default change, or App Store
package/signing/upload/submission proof.

## Changes

- `core/runtime/config.py` now reports `APP_VERSION = "04.01.28"`.
- `core/project/project_format.py` now marks newly saved project payloads as
  schema version `04.01.28`.
- `core/project/nle_persistence_guard.py` separates compatibility-only snapshot
  persistence from explicit standalone `nle_snapshot` load-source approval.
- `core/project/project_context.py` uses `nle_snapshot` rows only when the
  explicit snapshot canonical-load policy and approved snapshot payload are
  present.
- `core/project/project_format.py` preserves approved snapshot rows on resave
  while keeping legacy `editor_state` rows for rollback compatibility.
- `tools/audit_nle_persistence_cutover.py` now includes the standalone
  `nle_snapshot` load-source opt-in proof and keeps the remaining cutover
  blockers explicit.

## Evidence

- NLE audit:
  `output/manual_verification/latest/nle_snapshot_canonical_load_source_v040128_20260629_1325/nle_persistence_cutover_audit.md`
- Audit state: `status=blocked`, `prep_ready=true`,
  `persistence_cutover_ready=false`, overall stoplight `red`, ready/blocked
  gates `9/3`.
- Explicit opt-in canonical owner: `nle_snapshot`.
- Ready gate added: `nle_snapshot_canonical_load_source_allowed`.
- Snapshot load proof: loaded/runtime/reloaded/storage `nle_snapshot` first
  caption text remains `snapshot canonical first`.
- Rollback proof: legacy `editor_state` first caption text after resave remains
  `first`.
- Fail-closed proof: compatibility-only, forged, empty, and ambiguous dual-owner
  payloads fall back to legacy rows.
- Remaining blocked gates: `runtime_project_state_persistence_allowed`,
  `legacy_disk_shape_replacement_allowed`, and `final_cutover_ready`.

## Validation

- `./venv/bin/python -m py_compile core/project/nle_persistence_guard.py core/project/project_format.py core/project/nle_snapshot.py core/project/project_context.py tools/audit_nle_persistence_cutover.py tests/test_project_nle_persistence_guard.py tests/test_nle_persistence_cutover_audit.py tests/test_macos_bundle_runtime_paths.py core/runtime/config.py`
  -> pass
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_persistence_guard.py tests/test_nle_persistence_cutover_audit.py tests/test_macos_bundle_runtime_paths.py`
  -> `27 passed`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_nle_persistence_cutover.py --output-dir output/manual_verification/latest/nle_snapshot_canonical_load_source_v040128_20260629_1325`
  -> `status=blocked`, ready/blocked gates `9/3`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_context.py tests/test_cp03_cp04_status_ui.py -k "schema or version or project_file_roundtrip or status"`
  -> `66 passed, 80 deselected`
- Direct version assertion -> `APP_VERSION=04.01.28`,
  `PROJECT_SCHEMA_VERSION=04.01.28`
- `git diff --check -- .` -> pass

## Coordination

Three sub-agent reviews were used as architecture, QE, and editor-workflow
guardrails. Jammini `--status` resolved the active route and Jammini received a
bounded G2 scout request, but no fresh physical Jammini result file arrived
before this implementation closed. The latest physical route proof remains
`.agents/sentinel/handoffs/20260629-070211-watchdog-handoff-probe.md`.
