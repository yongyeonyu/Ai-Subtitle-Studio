# RELEASE v04.01.29

Date: 2026-06-29 KST

Release app version: `04.01.29`
Project schema version: `04.01.29`

## Summary

`v04.01.29` is a focused G2 runtime `_nle_project_state` persistence opt-in
proof checkpoint. It allows `_nle_project_state` to persist only as an explicit
owner-approved supplemental runtime-state payload tied to the approved
standalone `nle_snapshot` load-source policy. Legacy `editor_state` remains on
disk for rollback and default project authority is unchanged.

This is not legacy disk-shape replacement, final NLE cutover, UI/UX change,
STT/cache default change, or App Store package/signing/upload/submission proof.

## Changes

- `core/runtime/config.py` now reports `APP_VERSION = "04.01.29"`.
- `core/project/project_format.py` now marks newly saved project payloads as
  schema version `04.01.29`.
- `core/project/nle_persistence_guard.py` now separates owner-approved
  supplemental runtime-state persistence from forged or unapproved persisted
  runtime payloads.
- `core/project/nle_project_state.py` now serializes and hydrates approved
  runtime NLE state payloads only after validating them against project
  segments.
- `core/project/project_io.py` preserves `_nle_project_state` on disk only when
  explicit runtime-state persistence approval is present.
- `core/project/project_format.py` writes approved supplemental
  `_nle_project_state` payloads while keeping legacy `editor_state` rollback
  rows.
- `tools/audit_nle_persistence_cutover.py` now includes runtime-state
  persistence opt-in proof and keeps legacy disk-shape replacement plus final
  cutover blocked.

## Evidence

- NLE audit:
  `output/manual_verification/latest/nle_runtime_state_persistence_v040129_20260629_140053/nle_persistence_cutover_audit.md`
- Audit state: `status=blocked`, `prep_ready=true`,
  `persistence_cutover_ready=false`, overall stoplight `red`, ready/blocked
  gates `10/2`.
- Explicit opt-in canonical owner: `nle_snapshot`.
- Ready gates: `nle_snapshot_canonical_load_source_allowed` and
  `runtime_project_state_persistence_allowed`.
- Runtime-state proof: storage contains `_nle_project_state` only under the
  explicit runtime persistence policy and cache-hit read hydrates runtime state
  from the approved persisted payload.
- Rollback proof: legacy `editor_state` first caption text after resave remains
  `first`.
- Fail-closed proof: forged or unapproved persisted runtime payloads are
  stripped instead of becoming default project authority.
- Remaining blocked gates: `legacy_disk_shape_replacement_allowed` and
  `final_cutover_ready`.

## Validation

- `./venv/bin/python -m py_compile core/project/nle_persistence_guard.py core/project/nle_project_state.py core/project/project_io.py core/project/project_format.py tools/audit_nle_persistence_cutover.py tests/test_project_nle_persistence_guard.py tests/test_nle_persistence_cutover_audit.py tests/test_macos_bundle_runtime_paths.py core/runtime/config.py`
  -> pass
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_persistence_guard.py tests/test_nle_persistence_cutover_audit.py tests/test_macos_bundle_runtime_paths.py`
  -> `30 passed`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_nle_persistence_cutover.py --output-dir output/manual_verification/latest/nle_runtime_state_persistence_v040129_20260629_140053`
  -> `status=blocked`, ready/blocked gates `10/2`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_context.py tests/test_cp03_cp04_status_ui.py -k "schema or version or project_file_roundtrip or status"`
  -> `66 passed, 80 deselected`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_segment_reload.py -k "direct_srt_rows_to_runtime_nle_state or direct_srt_readback_drift_without_overwriting_srt_rows" tests/test_editor_autosave_cleanup.py -k "direct_srt_mode or direct_srt_micro_overlap"`
  -> `2 passed, 140 deselected`
- Direct version assertion -> `APP_VERSION=04.01.29`,
  `PROJECT_SCHEMA_VERSION=04.01.29`
- `git diff --check -- .` -> pass

## Coordination

Three sub-agent reviews were used as architecture, QE, and editor-workflow
guardrails. Jammini `--status` resolved the active route and Jammini received a
bounded G2 scout request, but no fresh physical Jammini result file arrived
before this implementation closed. The latest physical route proof remains
`.agents/sentinel/handoffs/20260629-070211-watchdog-handoff-probe.md`.
