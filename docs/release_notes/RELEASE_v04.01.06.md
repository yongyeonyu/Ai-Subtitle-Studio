# RELEASE v04.01.06

Date: 2026-06-29
Previous release: `v04.01.05`
Release app version: `04.01.06`

## Summary

`v04.01.06` is a focused source-app G3 live NLE runtime observability proof harness checkpoint.

This release adds a remote verification path that can start a guided subtitle run, poll compact `guided-subtitle-status` samples, and write a proof report showing whether `VAD`, `STT1`, and `STT2` were observed before final generation completed.

## Key Changes

- Version and schema:
  - `core/runtime/config.py` now reports `APP_VERSION = "04.01.06"`.
  - `core/project/project_format.py` now marks newly saved project payloads as schema version `04.01.06`.

- G3 live runtime proof harness:
  - `tools/remote_verify.py live-nle-proof` starts `guided-subtitle-run`, polls `guided-subtitle-status`, and writes `live_nle_runtime_proof.md`, `live_nle_runtime_proof.json`, and `status_samples.json`.
  - The proof requires pre-final samples where `VAD`, `STT1`, and `STT2` have positive `nle_runtime_track_counts`.
  - The proof rejects raw runtime payload leakage, non-final save/export authority drift, and live projection budget drift on active pre-final samples.
  - Optional snapshots can be captured through the existing snapshot path; no new UI lane or label is introduced.

## Validation

- `./venv/bin/python -m py_compile tools/remote_verify.py tests/test_remote_verify_actions.py`: pass
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_remote_verify_actions.py`: `7 passed`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_remote_verify_actions.py tests/test_app_command_bridge.py tests/test_app_command_server.py tests/test_subtitle_live_editor_feed_facade.py tests/test_project_nle_runtime_cutover.py`: `113 passed`
- Direct version assertion: `APP_VERSION=04.01.06`, `PROJECT_SCHEMA_VERSION=04.01.06`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_app_store_readiness_audit.py tests/test_macos_bundle_runtime_paths.py`: `9 passed`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_context.py tests/test_cp03_cp04_status_ui.py -k "schema or version or project_file_roundtrip or status"`: `66 passed, 79 deselected`
- Jammini route proof: `.agents/sentinel/handoffs/20260629-020008-watchdog-handoff-probe.md`
- Jammini proof-harness review: `.agents/sentinel/handoffs/20260628-270641-g3-live-runtime-observability-proof-review-jammini.md`

## Not Included

- No visible UI label, layout, color, shortcut, menu, popup, timeline strip, or minimap change.
- No raw STT/VAD/subtitle-preview segment payload added to status/UDP responses.
- No final overlay, save/export authority, persisted NLE disk-format, STT/VAD algorithm, worker fan-out, cache default, App Store package, upload, or submission change.

## Remaining Risks

- This checkpoint adds the harness and redaction gates. A real-media run still needs to execute `live-nle-proof` and pair the status time-series with snapshots plus final quality/speed proof before the broader G3 acceptance gate can close.
