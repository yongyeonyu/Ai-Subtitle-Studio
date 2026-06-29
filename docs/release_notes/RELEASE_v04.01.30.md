# RELEASE v04.01.30

Date: 2026-06-29 KST

Release app version: `04.01.30`
Project schema version: `04.01.30`

## Summary

`v04.01.30` is a focused G2 legacy disk-shape replacement opt-in proof
checkpoint. It allows legacy-compatible `editor_state` rows to be regenerated
from the approved standalone `nle_snapshot` canonical source only when the
distinct owner-approved replacement policy is present. The `editor_state` key
remains present for compatibility, supplemental `_nle_project_state`
persistence stays policy-gated, and final disk-format cutover remains blocked.

This is not a default authority switch for all projects, `editor_state` key
removal, roughcut sidecar change, final NLE cutover, UI/UX change, STT/cache
default change, or App Store package/signing/upload/submission proof.

## Changes

- `core/runtime/config.py` now reports `APP_VERSION = "04.01.30"`.
- `core/project/project_format.py` now marks newly saved project payloads as
  schema version `04.01.30`.
- `core/project/nle_persistence_guard.py` now requires a distinct
  legacy-disk-shape replacement approval schema and snapshot projection source
  before accepting replacement.
- `core/project/project_format.py` now regenerates legacy-compatible
  `editor_state` rows from approved standalone `nle_snapshot` rows only for the
  explicit replacement policy.
- `core/project/nle_snapshot.py` now extracts rows from tuple or list payloads,
  covering pre-pack dataclass output and post-disk readback consistently.
- `core/project/project_io.py` preserves `_nle_project_state` for the explicit
  replacement policy only when the nested runtime payload remains approved.
- `tools/audit_nle_persistence_cutover.py` now includes legacy disk-shape
  replacement opt-in proof and keeps final cutover blocked.

## Evidence

- NLE audit:
  `output/manual_verification/latest/nle_legacy_disk_shape_replacement_v040130_20260629_143522/nle_persistence_cutover_audit.md`
- Audit state: `status=blocked`, `prep_ready=true`,
  `persistence_cutover_ready=false`, overall stoplight `red`, ready/blocked
  gates `11/1`.
- Explicit opt-in canonical owner: `nle_snapshot`.
- Ready gates: `nle_snapshot_canonical_load_source_allowed`,
  `runtime_project_state_persistence_allowed`, and
  `legacy_disk_shape_replacement_allowed`.
- Replacement proof: loaded/runtime/reloaded/storage snapshot/runtime/editor
  rows all keep first caption text `legacy replacement canonical first`.
- Cache-hit proof: read/resave hydrates runtime state and keeps approved
  `_nle_project_state` on disk only for the explicit policy.
- Fail-closed proof: forged replacement policy is blocked.
- Precedence proof: Direct SRT precedence is preserved.
- Remaining blocked gate: `final_cutover_ready`.

## Validation

- `./venv/bin/python -m py_compile core/project/nle_snapshot.py core/project/nle_persistence_guard.py core/project/project_io.py core/project/project_format.py core/runtime/config.py tools/audit_nle_persistence_cutover.py tests/test_project_nle_persistence_guard.py tests/test_nle_persistence_cutover_audit.py tests/test_macos_bundle_runtime_paths.py`
  -> pass
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_persistence_guard.py -k "legacy_disk_shape or runtime_nle_project_state"`
  -> `5 passed, 17 deselected`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_nle_persistence_cutover_audit.py -k "cutover"`
  -> `6 passed`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_persistence_guard.py tests/test_nle_persistence_cutover_audit.py tests/test_direct_srt_precedence_audit.py tests/test_macos_bundle_runtime_paths.py`
  -> `33 passed`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_nle_persistence_cutover.py --output-dir output/manual_verification/latest/nle_legacy_disk_shape_replacement_v040130_20260629_143522`
  -> `status=blocked`, ready/blocked gates `11/1`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_context.py tests/test_cp03_cp04_status_ui.py -k "schema or version or project_file_roundtrip or status"`
  -> `66 passed, 80 deselected`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_segment_reload.py -k "direct_srt_rows_to_runtime_nle_state or direct_srt_readback_drift_without_overwriting_srt_rows" tests/test_editor_autosave_cleanup.py -k "direct_srt_mode or direct_srt_micro_overlap"`
  -> `2 passed, 140 deselected`
- Direct version assertion -> `APP_VERSION=04.01.30`,
  `PROJECT_SCHEMA_VERSION=04.01.30`
- `git diff --check -- .` -> pass

## Coordination

Three sub-agent reviews were used as architecture, QE, and editor-workflow
guardrails. Jammini `--status` resolved the active route and Jammini received a
bounded G2 scout request, but no fresh physical Jammini result file arrived
before this implementation closed. The latest physical route proof remains
`.agents/sentinel/handoffs/20260629-070211-watchdog-handoff-probe.md`.
