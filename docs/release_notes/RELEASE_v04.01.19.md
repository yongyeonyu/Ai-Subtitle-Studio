# RELEASE v04.01.19

Date: 2026-06-29
Previous release: `v04.01.18`
Release app version: `04.01.19`

## Summary

`v04.01.19` is a focused G2 NLE canonical load-owner review packet checkpoint.

This release creates an owner-review blocker map from the existing NLE
persistence cutover audit. It does not switch project load ownership to NLE and
does not perform an NLE disk-format cutover.

## Key Changes

- Version and schema:
  - `core/runtime/config.py` now reports `APP_VERSION = "04.01.19"`.
  - `core/project/project_format.py` now marks newly saved project payloads as schema version `04.01.19`.

- NLE canonical load-owner review packet:
  - Added `tools/generate_nle_canonical_load_owner_review_packet.py`.
  - Added `tests/test_nle_canonical_load_owner_review_packet.py`.
  - Generated review artifact: `output/manual_verification/latest/nle_canonical_load_owner_review_packet_v040119_20260629_095907/nle_canonical_load_owner_review_packet.md`.
  - Generated source audit artifact: `output/manual_verification/latest/nle_canonical_load_owner_audit_v040119_20260629_095907/nle_persistence_cutover_audit.md`.
  - Packet state: `owner_review_required_blocked`, `canonical_load_owner_unchanged=true`, current canonical owner `legacy_editor_state`, `canonical_load_owner_change_allowed=false`, `disk_format_cutover_allowed=false`.

## Evidence

- Review packet: `output/manual_verification/latest/nle_canonical_load_owner_review_packet_v040119_20260629_095907/nle_canonical_load_owner_review_packet.md`
- Decision matrix: `output/manual_verification/latest/nle_canonical_load_owner_review_packet_v040119_20260629_095907/decision_matrix.json`
- Source audit: `output/manual_verification/latest/nle_canonical_load_owner_audit_v040119_20260629_095907/nle_persistence_cutover_audit.md`
- Preserved audit values: `prep_ready=true`, `persistence_cutover_ready=false`, `top_level_nle_shadow_ready=true`, operation roundtrip `11` families all passed, render/export parity passed, top-level `nle` schema `ai_subtitle_studio.nle_shadow_project.v1`, role `shadow_metadata`, canonical load owner `legacy_editor_state`, runtime project state persisted `false`, final invalid/non-monotonic/overlap `0/0/0`, and global max active `1`.
- Three sub-agent reviews were used for release boundary, QE, and editor-workflow wording guardrails.
- Jammini `--status` resolved the active route. The current `--handoff-probe` packet did not produce a fresh physical handoff file, so `.agents/sentinel/handoffs/20260629-070211-watchdog-handoff-probe.md` remains the latest physical route proof.

## Validation

- `./venv/bin/python -m py_compile tools/generate_nle_canonical_load_owner_review_packet.py tests/test_nle_canonical_load_owner_review_packet.py core/runtime/config.py core/project/project_format.py tests/test_macos_bundle_runtime_paths.py`: pass
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_nle_canonical_load_owner_review_packet.py tests/test_nle_persistence_cutover_audit.py tests/test_macos_bundle_runtime_paths.py`: `15 passed`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_context.py tests/test_cp03_cp04_status_ui.py -k "schema or version or project_file_roundtrip or status"`: `66 passed, 80 deselected`
- Direct version assertion: `APP_VERSION=04.01.19`, `PROJECT_SCHEMA_VERSION=04.01.19`
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

- G2 full NLE disk-format cutover still requires explicit owner approval for the exact canonical load-owner change plus rollback boundaries.
- Future cutover proof must cover legacy project compatibility, direct SRT precedence, roughcut sidecar restore, save/reopen parity, render/export parity, final invalid/non-monotonic/overlap `0/0/0`, and rollback/quarantine behavior.
- G0 remains blocked until Apple Distribution and 3rd Party Mac Developer Installer identities, exact signed package, sandbox smoke, App Store Connect validation, upload/submission evidence, and owner-approved metadata values are available.
