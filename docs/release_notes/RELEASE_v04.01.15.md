# RELEASE v04.01.15

Date: 2026-06-29
Previous release: `v04.01.14`
Release app version: `04.01.15`

## Summary

`v04.01.15` is a focused source-app G0 App Store readiness blocker-refresh checkpoint.

This release hardens the non-destructive Mac App Store readiness audit so it records actual local keychain signing identity availability. The result remains blocked: Apple Distribution and 3rd Party Mac Developer Installer identities are not present locally, no signed App Store `.pkg` exists, sandbox smoke and App Store Connect validation are missing, and owner metadata is still pending.

## Key Changes

- Version and schema:
  - `core/runtime/config.py` now reports `APP_VERSION = "04.01.15"`.
  - `core/project/project_format.py` now marks newly saved project payloads as schema version `04.01.15`.

- App Store readiness audit:
  - `tools/audit_app_store_readiness.py` now records local keychain identity evidence from `security find-identity`.
  - The audit reports Apple Development, Apple Distribution, and 3rd Party Mac Developer Installer presence flags.
  - The audit now emits explicit blockers for missing Apple Distribution and installer identities in the local keychain.

## Evidence

- Blocker refresh audit: `output/manual_verification/latest/app_store_identity_metadata_blocker_v040115_20260629_0907/app_store_readiness_audit.md`
- Keychain snapshots and signature placeholders are stored in the same artifact directory.
- Three sub-agent reviews were used for release boundary, QE, and metadata/review-flow guardrails.
- The current Jammini `--handoff-probe` packet timed out without a fresh physical handoff file; `.agents/sentinel/handoffs/20260629-070211-watchdog-handoff-probe.md` remains the latest physical route proof.

## Validation

- `./venv/bin/python -m py_compile tools/audit_app_store_readiness.py tests/test_app_store_readiness_audit.py core/runtime/config.py core/project/project_format.py tests/test_macos_bundle_runtime_paths.py`: pass
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_app_store_readiness_audit.py tests/test_macos_bundle_runtime_paths.py`: `10 passed`
- Latest readiness audit: `status=blocked`, `submission_target=mac_app_store_pkg`, `local_packaging_ready=true`, `app_store_submission_ready=false`, blocker count `15`, Apple Development identity present, Apple Distribution identity missing, installer identity missing, and owner-input metadata pending `8/8`.
- Direct version assertion: `APP_VERSION=04.01.15`, `PROJECT_SCHEMA_VERSION=04.01.15`
- `git diff --check -- .`: pass

## Not Included

- No App Store submission-ready claim.
- No Apple Distribution signed `.app`.
- No signed App Store `.pkg`.
- No `pkgutil --check-signature` pass.
- No sandbox workflow smoke.
- No App Store Connect validation, upload, or submission.
- No owner metadata, privacy, export compliance, screenshot, review-note, age-rating, or release-note completion.
- No Developer ID DMG work or claim that a DMG is Mac App Store submission evidence.
- No UI/UX, subtitle-generation, cache-default, NLE behavior, or worker-scheduling change.

## Remaining Risks

- G0 remains blocked until the required Apple Distribution and 3rd Party Mac Developer Installer identities, exact signed `.pkg`, sandbox smoke, App Store Connect validation, upload/submission decision, and owner-approved metadata values are available.
