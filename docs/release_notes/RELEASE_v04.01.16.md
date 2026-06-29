# RELEASE v04.01.16

Date: 2026-06-29
Previous release: `v04.01.15`
Release app version: `04.01.16`

## Summary

`v04.01.16` is a focused source-app G0 App Store metadata owner-input package checkpoint.

This release adds a generated owner-input package so the remaining App Store
metadata decisions can be collected without overclaiming submission readiness.
The result remains blocked: the package is `not_submission_proof=true`,
`owner_input_complete=false`, and `app_store_submission_ready=false`.

## Key Changes

- Version and schema:
  - `core/runtime/config.py` now reports `APP_VERSION = "04.01.16"`.
  - `core/project/project_format.py` now marks newly saved project payloads as schema version `04.01.16`.

- App Store metadata owner-input package:
  - `tools/generate_app_store_metadata_package.py` generates JSON/Markdown owner-input artifacts from the existing readiness audit constants and report surface.
  - The package separates the audit-backed `8` non-code owner-input blockers from additional App Store Connect metadata-fill fields such as subtitle, keywords, description, marketing URL, app record, SKU/locale, pricing, and availability.
  - The package writes review-note, screenshot-plan, copy-guardrail, submission-blocker, forbidden-claim scan, and sanitized readiness snapshot artifacts.
  - `tests/test_app_store_metadata_package.py` covers the false-positive case where technical package/validation prerequisites are faked green but missing owner metadata still keeps submission readiness blocked.

## Evidence

- Metadata owner-input package: `output/manual_verification/latest/app_store_metadata_owner_input_package_v040116_20260629_0921/app_store_metadata_owner_input_package.md`
- Package state: `status=blocked`, `not_submission_proof=true`, `owner_input_complete=false`, `app_store_submission_ready=false`, pending owner-input metadata `8/8`, forbidden-claim scan `pass` with `0` matches, and sanitized readiness snapshot without raw keychain identity names.
- Three sub-agent reviews were used for release boundary, QE, and metadata/review-flow guardrails.
- Jammini `--status` resolved the active route. The current `--handoff-probe` packet did not produce a fresh physical handoff file, so `.agents/sentinel/handoffs/20260629-070211-watchdog-handoff-probe.md` remains the latest physical route proof.

## Validation

- `./venv/bin/python -m py_compile tools/generate_app_store_metadata_package.py tools/audit_app_store_readiness.py tests/test_app_store_metadata_package.py tests/test_app_store_readiness_audit.py core/runtime/config.py core/project/project_format.py tests/test_macos_bundle_runtime_paths.py`: pass
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_app_store_metadata_package.py tests/test_app_store_readiness_audit.py tests/test_macos_bundle_runtime_paths.py`: `14 passed`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_context.py tests/test_cp03_cp04_status_ui.py -k "schema or version or project_file_roundtrip or status"`: `66 passed, 80 deselected`
- Direct version assertion: `APP_VERSION=04.01.16`, `PROJECT_SCHEMA_VERSION=04.01.16`
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
