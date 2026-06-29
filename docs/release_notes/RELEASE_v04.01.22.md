# RELEASE v04.01.22

Date: 2026-06-29 KST
Previous release: `v04.01.21`
Release app version: `04.01.22`
Project schema version: `04.01.22`

## Scope

`v04.01.22` is a focused G0 App Store readiness blocker matrix checkpoint. It
tightens readiness reporting so file presence cannot be mistaken for signing or
submission proof without strict `codesign` and `pkgutil --check-signature`
artifacts.

This release does not build, sign, validate, upload, or submit a Mac App Store
package. It does not complete owner metadata, change UI/UX, change subtitle
generation, change STT/cache defaults, or change NLE persistence/load behavior.

## Changes

- Version/schema:
  - `core/runtime/config.py` now reports `APP_VERSION = "04.01.22"`.
  - `core/project/project_format.py` now marks newly saved project payloads as schema version `04.01.22`.
- G0 App Store readiness:
  - `tools/audit_app_store_readiness.py` now reports `app_version`, ordered blocker groups, stoplight state, and a submission gate summary.
  - The audit now requires strict App Store-candidate `codesign` proof and `pkgutil --check-signature` proof before signed artifacts can be treated as ready.
  - `tools/generate_app_store_metadata_package.py` carries the refreshed app version, stoplight, and blocker group counts into the owner-input package while keeping raw identity names out of the public readiness snapshot.

## Evidence

- Audit report: `output/manual_verification/latest/app_store_readiness_blocker_matrix_v040122_20260629_1100/app_store_readiness_audit.md`
- Audit JSON: `output/manual_verification/latest/app_store_readiness_blocker_matrix_v040122_20260629_1100/app_store_readiness_audit.json`
- Metadata owner-input package: `output/manual_verification/latest/app_store_metadata_owner_input_package_v040122_20260629_1100/app_store_metadata_owner_input_package.md`
- Completed action archive: `docs/planning_queue/COMPLETED_ACTION_ITEMS.md#v040122-g0-app-store-readiness-blocker-matrix-audit`

Current G0 state remains blocked: `local_packaging_ready=true`,
`app_store_submission_ready=false`, overall stoplight `red`, blocker count `17`,
blocker groups `signed_artifacts=3`, `sandbox_smoke=1`, `app_store_connect=1`,
`signing_identities=4`, and `owner_metadata=8`.

## Verification

- `./venv/bin/python -m py_compile tools/audit_app_store_readiness.py tools/generate_app_store_metadata_package.py tests/test_app_store_readiness_audit.py tests/test_app_store_metadata_package.py core/runtime/config.py core/project/project_format.py tests/test_macos_bundle_runtime_paths.py` -> pass
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_app_store_readiness_audit.py tests/test_app_store_metadata_package.py tests/test_macos_bundle_runtime_paths.py` -> `17 passed`
- `./venv/bin/python tools/audit_app_store_readiness.py --output-dir output/manual_verification/latest/app_store_readiness_blocker_matrix_v040122_20260629_1100` -> `status=blocked`, overall stoplight `red`, blocker count `17`
- `./venv/bin/python tools/generate_app_store_metadata_package.py --output-dir output/manual_verification/latest/app_store_metadata_owner_input_package_v040122_20260629_1100` -> `not_submission_proof=true`, pending owner-input metadata `8/8`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_context.py tests/test_cp03_cp04_status_ui.py -k "schema or version or project_file_roundtrip or status"` -> `66 passed, 80 deselected`
- Direct version assertion -> `APP_VERSION=04.01.22`, `PROJECT_SCHEMA_VERSION=04.01.22`
- `git diff --check -- .` -> pass
