# RELEASE v04.01.01

Date: 2026-06-29
Previous release: `v04.01.00`
Release app version: `04.01.01`

## Summary

`v04.01.01` is a source-app checkpoint for the owner-approved NLE shadow-metadata path, App Store blocker proof refresh, and active commercial-editor planning lane.

This release does not claim Mac App Store submission readiness. The local machine currently has Apple Development signing only; Apple Distribution and 3rd Party Mac Developer Installer identities, signed `.pkg`, sandbox smoke, App Store Connect validation, upload, and owner-approved metadata remain incomplete.

## Key Changes

- Version and schema:
  - `core/runtime/config.py` now reports `APP_VERSION = "04.01.01"`.
  - `core/project/project_format.py` now marks newly saved project payloads as schema version `04.01.01`.

- NLE/Taption editing:
  - Approved top-level `nle` shadow metadata can now be stored only with an approved companion `nle_snapshot`, explicit `nle_persistence.persist_snapshot=true`, `persist_top_level_nle=true`, and `approval=owner_approved_20260628`.
  - The top-level shadow payload keeps `canonical_load_owner=legacy_editor_state`; persisted `_nle_project_state` and canonical NLE load ownership remain blocked.
  - Direct SRT, roughcut sidecar, render/export, and legacy save/reopen surfaces remain compatibility owners.

- App Store readiness:
  - Latest blocker evidence: `output/manual_verification/latest/app_store_owner_approval_identity_check_20260629_0026/app_store_readiness_audit.md`.
  - Current local `.app` validates with Apple Development signing only.
  - `dist/macos/AI Subtitle Studio.pkg` is still missing, so package signature, App Store Connect validation, and upload were not run.

## Validation

- `./venv/bin/python -m py_compile core/project/nle_persistence_guard.py core/project/nle_snapshot.py core/project/project_format.py tools/audit_nle_persistence_cutover.py tests/test_project_nle_persistence_guard.py tests/test_nle_persistence_cutover_audit.py`: pass
- `./venv/bin/python -m py_compile core/runtime/config.py core/project/project_format.py tools/audit_app_store_readiness.py tests/test_macos_bundle_runtime_paths.py`: pass
- Direct version assertion for `APP_VERSION` and `PROJECT_SCHEMA_VERSION`: `04.01.01` / `04.01.01`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_app_store_readiness_audit.py tests/test_macos_bundle_runtime_paths.py`: `9 passed`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_context.py tests/test_cp03_cp04_status_ui.py -k "schema or version or project_file_roundtrip or status"`: `66 passed, 79 deselected`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_persistence_guard.py`: `8 passed`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_nle_persistence_cutover_audit.py`: `6 passed`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_render_export_parity.py`: `2 passed`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_snapshot.py -k "snapshot or editor_row_readback_parity"`: `16 passed, 4 subtests passed`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_nle_persistence_cutover.py --output-dir output/manual_verification/latest/nle_top_level_shadow_metadata_20260629_0020`: `prep_ready=true`, `top_level_nle_shadow_ready=true`, full cutover `false`
- `./venv/bin/python tools/audit_app_store_readiness.py --output-dir output/manual_verification/latest/app_store_owner_approval_identity_check_20260629_0026`: `status=blocked`, `local_packaging_ready=true`, `app_store_submission_ready=false`, blocker count `13`
- `packaging/macos/validate_app_bundle.sh`: pass for the current Apple Development signed local bundle
- `pkgutil --check-signature "dist/macos/AI Subtitle Studio.pkg"`: blocked because the package does not exist

## Not Included

- No Mac App Store `.pkg` build.
- No App Store Connect validation or upload.
- No App Store submission.
- No DMG build or notarization.
- No UI/UX label, layout, color, shortcut, menu, or popup behavior change.
- No persisted `_nle_project_state` or canonical NLE disk-format load-owner cutover.
- No STT2 skip, word-precision skip, model downgrade, LLM/LoRA/VAD policy relaxation, or collect-cache default promotion.

## Remaining Risks

- Mac App Store submission remains blocked on Apple Distribution and 3rd Party Mac Developer Installer identities, signed `.pkg`, sandbox smoke, App Store Connect validation, and owner metadata/privacy/review inputs.
- The active NLE/STT/VAD live-track planning lane still needs implementation, performance proof, and UI-owner approval before visible editor-surface changes.
- STT collect-cache defaults remain disabled until explicit owner review approves promotion.
