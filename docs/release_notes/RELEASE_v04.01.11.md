# RELEASE v04.01.11

Date: 2026-06-29
Previous release: `v04.01.10`
Release app version: `04.01.11`

## Summary

`v04.01.11` is a focused source-app G3 proof-harness checkpoint.

This release records current-head same-media NAS HeyDealer benchmark acceptance and hardens `tools/remote_verify.py editor-sequence` so app-command proof failures are reported quickly and durably instead of hanging or losing partial evidence. It does not claim full G3 completion because app-command save/export proof remains blocked by `open_app_unreachable` in the guarded proof attempt.

## Key Changes

- Version and schema:
  - `core/runtime/config.py` now reports `APP_VERSION = "04.01.11"`.
  - `core/project/project_format.py` now marks newly saved project payloads as schema version `04.01.11`.

- Same-media benchmark proof:
  - NAS HeyDealer original MP4/SRT preflight passed for `0-180s`.
  - High-mode benchmark acceptance passed with final `0/0/0`, save/reopen stable `true`, global max active `1`, and `timeout_detected=false`.

- Editor-sequence proof harness:
  - `tools/remote_verify.py editor-sequence` now flushes `report.json` / `report.md` after each step.
  - Post-step `status` probes are capped at `4s`, and step snapshots are capped at `8s`, while the actual command timeout remains unchanged.
  - Returned `export-subtitle-video` MOV artifacts are validated by path existence and file size.
  - If `open-media` reports `app_unreachable`, the sequence aborts immediately with `abort_reason=open_app_unreachable`.

## Evidence

- Jammini route proof: `.agents/sentinel/handoffs/20260629-070211-watchdog-handoff-probe.md`
- Three sub-agent reviews were used for architecture, QE, and editor-workflow guardrails.
- Preflight: `output/manual_verification/latest/g3_same_media_quality_speed_v040111_20260629_preflight/reference_fixture_availability.md`
- Benchmark: `.codex_work/benchmarks/subtitle_pipeline_variants/20260629_070403/benchmark_results.json`
- Acceptance: `output/manual_verification/latest/g3_same_media_quality_speed_v040111_20260629/acceptance/reference_benchmark_acceptance.md`
- Timeout audit: `output/manual_verification/latest/g3_same_media_quality_speed_v040111_20260629/timeout_audit/stt_worker_timeout_audit.md`
- Guarded app-command proof attempt: `output/manual_verification/latest/g3_same_media_app_commands_v040111_20260629_guarded/report.md`

## Validation

- `./venv/bin/python -m py_compile tools/remote_verify.py tests/test_remote_verify_actions.py tests/test_macos_bundle_runtime_paths.py`: pass
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_remote_verify_actions.py -k "editor_sequence or export_subtitle_video_step or capture_snapshot"`: `7 passed, 6 deselected`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_remote_verify_actions.py`: `13 passed`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_app_store_readiness_audit.py tests/test_macos_bundle_runtime_paths.py`: `9 passed`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_context.py tests/test_cp03_cp04_status_ui.py -k "schema or version or project_file_roundtrip or status"`: `66 passed, 79 deselected`
- Same-media benchmark acceptance: `accepted=true`
- STT worker timeout audit: `timeout_detected=false`
- Direct version assertion: `APP_VERSION=04.01.11`, `PROJECT_SCHEMA_VERSION=04.01.11`
- `git diff --check -- .`: pass

## Not Included

- No full G3 completion claim.
- No app-command final export acceptance; guarded proof currently records `open_app_unreachable`.
- No UI label, layout, color, shortcut, menu, popup, timeline strip, or minimap change.
- No STT/VAD algorithm, worker fan-out, model-selection, cache default, or subtitle-quality policy change.
- No persisted NLE disk-format cutover.
- No App Store package, validation, upload, metadata submission, or final App Store submission.

## Remaining Risks

- G3 still needs a reachable app automation bridge for same-media app-command save/project/SRT/video export, reopened project state, export artifact bytes, and UI/app-command responsiveness proof.
