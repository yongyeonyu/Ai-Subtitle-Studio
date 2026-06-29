# RELEASE v04.01.26

Date: 2026-06-29 KST
Previous release: `v04.01.25`
Release app version: `04.01.26`
Project schema version: `04.01.26`

## Scope

`v04.01.26` is a focused G0 owner metadata values preflight guard checkpoint.
It prevents owner approval, generated drafts, or partial metadata from being
treated as App Store submission-ready metadata.

This release does not build, sign, validate, upload, submit, complete owner
metadata, change UI/UX, change subtitle generation, change STT/cache defaults,
or change NLE persistence/load behavior.

## Changes

- Version/schema:
  - `core/runtime/config.py` now reports `APP_VERSION = "04.01.26"`.
  - `core/project/project_format.py` now marks newly saved project payloads as schema version `04.01.26`.
- Owner metadata values preflight:
  - `tools/check_app_store_owner_metadata_values.py` validates explicit owner values JSON before owner metadata can be considered ready.
  - The preflight requires field values, owner approval evidence, app-version match, public URL owner-control confirmation, App Store Connect record bundle binding, signed-candidate screenshot binding, and forbidden-copy scan pass.
  - Forbidden imported-copy claims now include App Store readiness, offline-only, 100% accuracy, validation, commercial NLE replacement, full/native NLE, and real-time editing claims.
- G0 readiness audit and package:
  - `tools/audit_app_store_readiness.py` now reports both non-code owner input blockers and App Store Connect metadata blockers under the owner metadata group.
  - `tools/generate_app_store_metadata_package.py` reuses the audit preflight result and writes `owner_values_preflight.json`.
  - `tools/check_app_store_upload_preflight.py` rejects minimal forged readiness JSON without schema/root/current app version and `owner_metadata_values_preflight.ready=true`.

## Evidence

- Readiness audit: `output/manual_verification/latest/app_store_owner_metadata_values_preflight_v040126_20260629_1228/app_store_readiness_audit.md`
- Readiness JSON: `output/manual_verification/latest/app_store_owner_metadata_values_preflight_v040126_20260629_1228/app_store_readiness_audit.json`
- Metadata owner-input package: `output/manual_verification/latest/app_store_metadata_owner_input_package_v040126_20260629_1228/app_store_metadata_owner_input_package.md`
- Completed action archive: `docs/planning_queue/COMPLETED_ACTION_ITEMS.md#v040126-g0-owner-metadata-values-preflight-guard`

Current G0 state remains blocked: `app_store_submission_ready=false`, overall
stoplight `red`, blocker count `25`, owner metadata blocker count `16`,
owner-input metadata pending `8/8`, App Store Connect metadata pending `8`,
signed-artifact proof/sandbox/App Store Connect validation/signing identities
still red, and no owner metadata values JSON is present.

## Verification

- `./venv/bin/python -m py_compile tools/audit_app_store_readiness.py tools/generate_app_store_metadata_package.py tools/check_app_store_owner_metadata_values.py tools/check_app_store_upload_preflight.py tests/test_app_store_readiness_audit.py tests/test_app_store_metadata_package.py tests/test_app_store_metadata_values_preflight.py tests/test_app_store_upload_script.py tests/test_app_store_upload_preflight.py core/runtime/config.py core/project/project_format.py tests/test_macos_bundle_runtime_paths.py` -> pass
- `PYTHONDONTWRITEBYTECODE=1 QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q -p no:cacheprovider tests/test_app_store_metadata_values_preflight.py tests/test_app_store_readiness_audit.py tests/test_app_store_metadata_package.py tests/test_app_store_upload_preflight.py tests/test_app_store_upload_script.py tests/test_macos_bundle_runtime_paths.py` -> `37 passed`
- `./venv/bin/python tools/audit_app_store_readiness.py --output-dir output/manual_verification/latest/app_store_owner_metadata_values_preflight_v040126_20260629_1228` -> `status=blocked`, overall stoplight `red`, blocker count `25`
- `./venv/bin/python tools/generate_app_store_metadata_package.py --output-dir output/manual_verification/latest/app_store_metadata_owner_input_package_v040126_20260629_1228` -> `not_submission_proof=true`, pending owner-input metadata `8/8`, pending App Store Connect metadata `8`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_context.py tests/test_cp03_cp04_status_ui.py -k "schema or version or project_file_roundtrip or status"` -> `66 passed, 80 deselected`
- Direct version assertion -> `APP_VERSION=04.01.26`, `PROJECT_SCHEMA_VERSION=04.01.26`
- `git diff --check -- .` -> pass
