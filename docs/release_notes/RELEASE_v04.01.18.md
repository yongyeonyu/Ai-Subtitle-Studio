# RELEASE v04.01.18

Date: 2026-06-29
Previous release: `v04.01.17`
Release app version: `04.01.18`

## Summary

`v04.01.18` is a focused G1 STT collect-cache default review packet checkpoint.

This release creates an owner-review packet from the existing representative NAS
collect-cache write/hit evidence. It does not enable collect caches by default
and does not claim production speed improvement.

## Key Changes

- Version and schema:
  - `core/runtime/config.py` now reports `APP_VERSION = "04.01.18"`.
  - `core/project/project_format.py` now marks newly saved project payloads as schema version `04.01.18`.

- STT cache default review packet:
  - Added `tools/generate_stt_cache_default_review_packet.py`.
  - The packet summarizes the existing NAS evidence at `output/manual_verification/latest/stt_cache_backfill_real_nas_20260628_2202/`.
  - Generated owner-review artifact: `output/manual_verification/latest/stt_cache_default_review_packet_v040118_20260629_094703/stt_cache_default_review_packet.md`.
  - Packet state: `owner_review_required`, `production_defaults_unchanged=true`, `default_promotion_allowed=false`.
  - Current defaults remain `stt_primary_collect_cache_enabled=false` and `stt_recheck_collect_cache_enabled=false`.

## Evidence

- Review packet: `output/manual_verification/latest/stt_cache_default_review_packet_v040118_20260629_094703/stt_cache_default_review_packet.md`
- Decision matrix: `output/manual_verification/latest/stt_cache_default_review_packet_v040118_20260629_094703/decision_matrix.json`
- Source NAS backfill evidence: `output/manual_verification/latest/stt_cache_backfill_real_nas_20260628_2202/`
- Preserved evidence values: write/hit elapsed `177.888s -> 1.183s`, raw/final/reference `58/56/89`, quality/text/timing `93.766/94.267/0.5808s`, final invalid/non-monotonic/overlap `0/0/0`, final last end/duration bound `180.0/180.0`, global max active `1`, timeout detected `false`.
- Three sub-agent reviews were used for release boundary, QE, and editor-workflow wording guardrails.
- Jammini `--status` resolved the active route. The current `--handoff-probe` packet did not produce a fresh physical handoff file, so `.agents/sentinel/handoffs/20260629-070211-watchdog-handoff-probe.md` remains the latest physical route proof.

## Validation

- `./venv/bin/python -m py_compile tools/generate_stt_cache_default_review_packet.py tests/test_stt_cache_default_review_packet.py core/runtime/config.py core/project/project_format.py tests/test_macos_bundle_runtime_paths.py`: pass
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_stt_cache_default_review_packet.py tests/test_macos_bundle_runtime_paths.py`: `10 passed`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_context.py tests/test_cp03_cp04_status_ui.py -k "schema or version or project_file_roundtrip or status"`: `66 passed, 80 deselected`
- Direct version assertion: `APP_VERSION=04.01.18`, `PROJECT_SCHEMA_VERSION=04.01.18`
- `git diff --check -- .`: pass

## Not Included

- No collect-cache default enablement.
- No production speedup claim.
- No STT2 skipping, word precision disablement, model downgrade, Fast-mode promotion, or quality-gate relaxation.
- No UI/UX, NLE persistence, save/load, render/export, or App Store packaging/signing/upload/submission change.
- No claim that the cache-hit `1.183s` path represents first-run user speed.

## Remaining Risks

- G1 collect-cache defaults still require explicit owner approval before any promotion.
- Any future default promotion must happen one cache at a time with a rollback commit boundary and focused same-fixture proof.
- G0 remains blocked until Apple Distribution and 3rd Party Mac Developer Installer identities, exact signed package, sandbox smoke, App Store Connect validation, upload/submission evidence, and owner-approved metadata values are available.
