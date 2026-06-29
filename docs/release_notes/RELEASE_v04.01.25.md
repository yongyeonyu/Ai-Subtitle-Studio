# RELEASE v04.01.25

Date: 2026-06-29 KST
Previous release: `v04.01.24`
Release app version: `04.01.25`
Project schema version: `04.01.25`

## Scope

`v04.01.25` is a focused G0 App Store upload preflight guard and owner-metadata
refresh checkpoint. It keeps owner approval separate from actual
upload/submission readiness by requiring exact readiness proof before
`packaging/macos/upload_app_store_build.sh upload` can run.

This release does not build, sign, validate, upload, submit, complete owner
metadata, change UI/UX, change subtitle generation, change STT/cache defaults,
or change NLE persistence/load behavior.

## Changes

- Version/schema:
  - `core/runtime/config.py` now reports `APP_VERSION = "04.01.25"`.
  - `core/project/project_format.py` now marks newly saved project payloads as schema version `04.01.25`.
- G0 App Store upload guard:
  - `packaging/macos/upload_app_store_build.sh upload` now requires `AI_SUBTITLE_STUDIO_APP_STORE_UPLOAD_CONFIRMED=1`.
  - Upload mode also requires `APP_STORE_READINESS_JSON` and `tools/check_app_store_upload_preflight.py` success for the exact `.pkg`.
  - The preflight helper requires `app_store_submission_ready=true`, no blockers, all submission gates true, and readiness `.pkg` path binding before upload mode can call `xcrun altool --upload-app`.
- G0 readiness proof hardening:
  - `tools/audit_app_store_readiness.py` now treats strict `codesign`, `pkgutil`, sandbox smoke, and App Store validation artifacts as content-bound proof rather than file presence.
  - Placeholder proof files and mismatched signing identity environment values remain blocked.
  - `tools/generate_app_store_metadata_package.py` now includes the upload execution guard in the owner-input package.

## Evidence

- Readiness audit: `output/manual_verification/latest/app_store_upload_preflight_guard_v040125_20260629_1200/app_store_readiness_audit.md`
- Readiness JSON: `output/manual_verification/latest/app_store_upload_preflight_guard_v040125_20260629_1200/app_store_readiness_audit.json`
- Metadata owner-input package: `output/manual_verification/latest/app_store_metadata_owner_input_package_v040125_20260629_1200/app_store_metadata_owner_input_package.md`
- Completed action archive: `docs/planning_queue/COMPLETED_ACTION_ITEMS.md#v040125-g0-app-store-upload-preflight-guard-and-metadata-refresh`

Current G0 state remains blocked: `app_store_submission_ready=false`, overall
stoplight `red`, blocker count `17`, signed-artifact proof/sandbox/App Store
Connect validation/signing identities/owner metadata still red, and owner-input
metadata pending `8/8`.

## Verification

- `./venv/bin/python -m py_compile tools/audit_app_store_readiness.py tools/generate_app_store_metadata_package.py tools/check_app_store_upload_preflight.py tests/test_app_store_readiness_audit.py tests/test_app_store_metadata_package.py tests/test_app_store_upload_script.py tests/test_app_store_upload_preflight.py core/runtime/config.py core/project/project_format.py tests/test_macos_bundle_runtime_paths.py` -> pass
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_app_store_readiness_audit.py tests/test_app_store_metadata_package.py tests/test_app_store_upload_script.py tests/test_app_store_upload_preflight.py tests/test_macos_bundle_runtime_paths.py` -> `26 passed`
- `./venv/bin/python tools/audit_app_store_readiness.py --output-dir output/manual_verification/latest/app_store_upload_preflight_guard_v040125_20260629_1200` -> `status=blocked`, overall stoplight `red`, blocker count `17`
- `./venv/bin/python tools/generate_app_store_metadata_package.py --output-dir output/manual_verification/latest/app_store_metadata_owner_input_package_v040125_20260629_1200` -> `not_submission_proof=true`, pending owner-input metadata `8/8`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_context.py tests/test_cp03_cp04_status_ui.py -k "schema or version or project_file_roundtrip or status"` -> `66 passed, 80 deselected`
- Direct version assertion -> `APP_VERSION=04.01.25`, `PROJECT_SCHEMA_VERSION=04.01.25`
- `git diff --check -- .` -> pass
