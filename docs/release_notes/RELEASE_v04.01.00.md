# RELEASE v04.01.00

Date: 2026-06-28
Previous release: `v04.00.18`
Release app version: `04.01.00`

## Summary

`v04.01.00` is a source-app checkpoint release for the NLE/Taption subtitle editing line, release-readiness review, and development-documentation cleanup after `v04.00.18`.

This release keeps the Python/PyQt6 source-app product line. It does not claim Mac App Store submission readiness, build a DMG, upload a package, migrate to Swift/QML, approve persisted NLE disk fields, or change STT2/word precision/default-cache policy.

## Key Changes

- Version and schema:
  - `core/runtime/config.py` now reports `APP_VERSION = "04.01.00"`.
  - `core/project/project_format.py` now marks newly saved project payloads as schema version `04.01.00`.
  - `tests/test_trace_logger.py` now checks trace manifest app version against `config.APP_VERSION` instead of a release-specific literal.

- NLE/Taption editing checkpoint:
  - The completed NLE runtime/Taption subtitle editing slices remain archived in `docs/planning_queue/COMPLETED_ACTION_ITEMS.md` and `docs/quality_validation/test_result.md`.
  - `docs/planning_queue/ACTION_ITEMS.md` now keeps only active gates and archive pointers instead of duplicating completed NLE proof logs.
  - Persisted NLE project fields, per-pixel drag writes, QML/GPU default UI surfaces, and native migration remain blocked unless the owner explicitly opens a new compatibility gate.

- Development documentation:
  - `docs/README.md` now acts as the development-documentation hub.
  - Role folders under `docs/` point to planning queue, workflow operations, project reference, validation, product behavior, NLE, STT, evidence, release notes, and legacy archives.
  - `AGENTS.md` documents the root-doc policy, active-only queue policy, physical Jammini handoff priority, and clean-room Taption reference handling.

- Release/code review:
  - Jammini route was confirmed through a physical handoff probe.
  - Release-review scout identified version/schema/test/docs surfaces that must move together for `04.01.00`.
  - App Store readiness language was kept blocked: no signed `.app`, signed `.pkg`, sandbox smoke, App Store Connect validation, or owner-approved submission metadata exists in this release.

## Validation

- `./venv/bin/python -m py_compile core/runtime/config.py core/project/project_format.py tests/test_trace_logger.py tools/audit_app_store_readiness.py`: pass
- Direct version assertion for `APP_VERSION` and `PROJECT_SCHEMA_VERSION`: `04.01.00` / `04.01.00`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_trace_logger.py tests/test_app_store_readiness_audit.py`: `23 passed`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_context.py tests/test_cp03_cp04_status_ui.py -k "schema or version or project_file_roundtrip or status"`: `66 passed, 79 deselected`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_snapshot.py tests/test_project_nle_dual_write.py tests/test_project_nle_operations.py tests/test_project_nle_persistence_guard.py tests/test_project_nle_render_export_parity.py`: `67 passed, 4 subtests passed`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py`: `193 passed`
- `./venv/bin/python tools/audit_app_store_readiness.py --output-dir output/manual_verification/latest/app_store_readiness_v040100_20260628`: `status=blocked`, `local_packaging_ready=true`, `app_store_submission_ready=false`, config app version `04.01.00`
- `AI_SUBTITLE_STUDIO_QA_USE_SOURCE=1 ./venv/bin/python tools/qa_suite_runner.py quick --output-dir output/manual_verification/latest/qa_suite_quick_v040100_20260628`: pass, `failed_count=0`
- `git diff --check -- .`: pass

## Not Included

- No DMG build.
- No App Store package build, validation, upload, or submission.
- No notarization.
- No UI/UX label, layout, color, shortcut, menu, or popup behavior change.
- No native migration, Swift rewrite, QML migration, OpenGL/Metal UI-surface default, or Premiere-style UI clone.
- No persisted NLE disk-format cutover.
- No per-pixel NLE write path.
- No STT2 skip, word-precision skip, model downgrade, LLM/LoRA/VAD policy relaxation, or collect-cache default promotion.

## Remaining Risks

- Mac App Store submission remains blocked on signed app/pkg artifacts, sandbox smoke, App Store Connect validation, signing identities, and owner-provided metadata/privacy/review inputs.
- STT collect-cache defaults remain disabled until explicit owner review approves promotion.
- Persisted NLE disk fields remain unapproved; runtime/session NLE evidence must continue to preserve legacy save/reopen compatibility.
- Source-fps cut-boundary detector tuning for weak preserved markers remains a separate gate and must not be inferred from this release note.
