# RELEASE v04.01.31

Date: 2026-06-29 KST

Release app version: `04.01.31`
Project schema version: `04.01.31`

## Summary

`v04.01.31` is a focused G2 final source-app project persistence load-owner
opt-in proof checkpoint. It allows the approved payload to declare
`default_project_authority=nle_snapshot` only when the distinct final approval
schema and all approved snapshot/runtime/legacy-projection policy flags are
present.

The `editor_state` key remains present as a compatibility projection. This is
not dual canonical ownership, `editor_state` key removal, per-pixel NLE writes,
UI/UX change, STT/cache default change, full QA, or App Store
package/signing/upload/submission proof.

## Changes

- `core/runtime/config.py` now reports `APP_VERSION = "04.01.31"`.
- `core/project/project_format.py` now marks newly saved project payloads as
  schema version `04.01.31`.
- `core/project/nle_persistence_guard.py` now requires the distinct
  `ai_subtitle_studio.nle_final_cutover_approval.v1` schema before accepting
  `final_cutover_ready`.
- `core/project/project_format.py` now writes the final policy only for the
  explicit owner-approved payload, keeps `editor_state` present as a
  compatibility projection, and records `default_project_authority=nle_snapshot`.
- `core/project/project_io.py` preserves `_nle_project_state` for the explicit
  final policy only when the runtime payload itself remains approved.
- `tools/audit_nle_persistence_cutover.py` now includes final cutover-ready
  opt-in proof and requires forged-policy, cache-hit, Direct SRT, roughcut,
  readback, render/export, and compatibility-key guards before reporting ready.

## Evidence

- NLE audit:
  `output/manual_verification/latest/nle_final_cutover_ready_v040131_20260629_150156/nle_persistence_cutover_audit.md`
- Audit state: `status=ready`, `prep_ready=true`,
  `persistence_cutover_ready=true`, blockers `[]`, overall stoplight `green`,
  ready/blocked gates `12/0`.
- Explicit opt-in canonical owner: `nle_snapshot`.
- Ready gates: `nle_snapshot_canonical_load_source_allowed`,
  `runtime_project_state_persistence_allowed`,
  `legacy_disk_shape_replacement_allowed`, and `final_cutover_ready`.
- Final proof: loaded/runtime/reloaded/storage snapshot/runtime/editor rows all
  keep first caption text `final cutover canonical first`.
- Compatibility proof: `editor_state` remains present as a compatibility
  projection and does not mean dual canonical ownership.
- Cache-hit proof: read/resave hydrates runtime state and keeps approved
  `_nle_project_state` on disk only for the explicit policy.
- Fail-closed proof: forged final policy is blocked.
- Precedence proof: Direct SRT precedence is preserved.

## Validation

- `./venv/bin/python -m py_compile core/project/nle_persistence_guard.py core/project/project_format.py core/project/project_io.py tools/audit_nle_persistence_cutover.py tests/test_project_nle_persistence_guard.py tests/test_nle_persistence_cutover_audit.py core/runtime/config.py tests/test_macos_bundle_runtime_paths.py`
  -> pass
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_persistence_guard.py tests/test_nle_persistence_cutover_audit.py tests/test_macos_bundle_runtime_paths.py`
  -> `34 passed`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_nle_persistence_cutover.py --output-dir output/manual_verification/latest/nle_final_cutover_ready_v040131_20260629_150156`
  -> `status=ready`, ready/blocked gates `12/0`, blockers `[]`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_context.py tests/test_cp03_cp04_status_ui.py -k "schema or version or project_file_roundtrip or status"`
  -> `66 passed, 80 deselected`
- Direct version assertion -> `APP_VERSION=04.01.31`,
  `PROJECT_SCHEMA_VERSION=04.01.31`
- `git diff --check -- .` -> pass

## Coordination

Three sub-agent reviews were used as architecture, QE, and editor-workflow
guardrails. Jammini `--status` resolved the active route and Jammini received a
bounded G2 scout request, but no fresh physical Jammini result file arrived
before this implementation closed. The latest physical route proof remains
`.agents/sentinel/handoffs/20260629-070211-watchdog-handoff-probe.md`.
