# RELEASE v04.01.20

Date: 2026-06-29
Previous release: `v04.01.19`
Release app version: `04.01.20`

## Summary

`v04.01.20` is a focused G2 top-level NLE compatibility projection audit checkpoint.

This release extends the existing NLE persistence cutover audit so it can read
approved top-level `nle` shadow metadata explicitly while proving the default
project load path still uses legacy `editor_state` rows. It does not switch
project load ownership to NLE and does not perform an NLE disk-format cutover.

## Key Changes

- Version and schema:
  - `core/runtime/config.py` now reports `APP_VERSION = "04.01.20"`.
  - `core/project/project_format.py` now marks newly saved project payloads as schema version `04.01.20`.

- NLE compatibility projection audit:
  - `tools/audit_nle_persistence_cutover.py` now includes `top_level_nle_compatibility_projection`.
  - The audit mutates a temp project so top-level `nle` shadow captions intentionally differ from legacy editor rows, then proves default load still uses legacy rows.
  - The explicit top-level projection currently covers `2` captions and `0` gaps, while default load remains `3` rows, `2` captions, and `1` gap.
  - The remaining blocker is `top_level_nle_projection_gap_coverage_missing`.

## Evidence

- Audit report: `output/manual_verification/latest/nle_top_level_compatibility_projection_v040120_20260629_1018/nle_persistence_cutover_audit.md`
- Audit JSON: `output/manual_verification/latest/nle_top_level_compatibility_projection_v040120_20260629_1018/nle_persistence_cutover_audit.json`
- Audit state: `status=blocked`, `prep_ready=true`, `top_level_nle_compatibility_projection_passed=true`, `top_level_nle_canonical_projection_complete=false`.
- Compatibility projection state: `compatibility_projection_partial_blocked`, `not_runtime_change=true`, `canonical_load_owner_unchanged=true`, current canonical owner `legacy_editor_state`, `canonical_load_owner_change_allowed=false`, and `disk_format_cutover_allowed=false`.
- Resave rebuilt the top-level shadow from legacy rows and runtime report/state/quarantine stayed unpersisted.
- Three sub-agent reviews were used for architecture boundary, QE false-positive guards, and editor-workflow wording constraints.
- Jammini `--status` resolved the active route. The current `--handoff-probe` packet did not produce a fresh physical handoff file, so `.agents/sentinel/handoffs/20260629-070211-watchdog-handoff-probe.md` remains the latest physical route proof.

## Validation

- `./venv/bin/python -m py_compile tools/audit_nle_persistence_cutover.py tests/test_nle_persistence_cutover_audit.py core/runtime/config.py core/project/project_format.py tests/test_macos_bundle_runtime_paths.py`: pass
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_nle_persistence_cutover_audit.py tests/test_nle_canonical_load_owner_review_packet.py tests/test_project_nle_persistence_guard.py tests/test_macos_bundle_runtime_paths.py`: `23 passed`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_snapshot.py -k "readback or direct_srt"`: `3 passed, 13 deselected`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_context.py tests/test_cp03_cp04_status_ui.py -k "schema or version or project_file_roundtrip or status"`: `66 passed, 80 deselected`
- Direct version assertion: `APP_VERSION=04.01.20`, `PROJECT_SCHEMA_VERSION=04.01.20`
- `git diff --check -- .`: pass

## Not Included

- No project load/save behavior change.
- No top-level `nle` canonical load-owner switch.
- No `nle_snapshot` canonical load-source switch.
- No persisted `_nle_project_state`.
- No legacy `editor_state` compatibility removal.
- No per-pixel NLE writes.
- No visible UI/UX, label, layout, shortcut, color, or popup change.
- No STT/cache default change.
- No App Store packaging, signing, upload, or submission proof.

## Remaining Risks

- G2 full NLE disk-format cutover still requires gap-row coverage, exact canonical load-owner scope, rollback boundaries, and legacy/direct-SRT/roughcut/render-export proof.
- Future cutover proof must keep final invalid/non-monotonic/overlap `0/0/0`, save/reopen parity, render/export parity, runtime-state stripping, and quarantine behavior explicit.
- G0 remains blocked until Apple Distribution and 3rd Party Mac Developer Installer identities, exact signed package, sandbox smoke, App Store Connect validation, upload/submission evidence, and owner-approved metadata values are available.
