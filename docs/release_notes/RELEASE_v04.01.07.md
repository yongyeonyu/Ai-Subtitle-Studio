# RELEASE v04.01.07

Date: 2026-06-29
Previous release: `v04.01.06`
Release app version: `04.01.07`

## Summary

`v04.01.07` is a focused source-app G3 live NLE runtime observability strong-evidence gate checkpoint.

This release tightens the `live-nle-proof` harness so a pass requires repeated pre-final runtime-track observations, generation completion, compact payload preservation, and JSONL sample evidence. It does not claim that a real-media proof run has already passed.

## Key Changes

- Version and schema:
  - `core/runtime/config.py` now reports `APP_VERSION = "04.01.07"`.
  - `core/project/project_format.py` now marks newly saved project payloads as schema version `04.01.07`.

- G3 live runtime proof gate:
  - `tools/remote_verify.py live-nle-proof` now requires each required runtime track (`VAD`, `STT1`, `STT2`) to appear in at least two distinct active pre-final polls by default.
  - The proof now blocks `generation_not_completed` and non-compact runtime payloads instead of treating partial or ambiguous status evidence as a pass.
  - The report schema is now `ai_subtitle_studio.live_nle_runtime_proof.v2`.
  - The writer keeps the redacted summary separate from detailed samples and now writes `observability_samples.jsonl` in addition to `status_samples.json`.

## Validation

- `./venv/bin/python -m py_compile tools/remote_verify.py tests/test_remote_verify_actions.py`: pass
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_remote_verify_actions.py`: `9 passed`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_remote_verify_actions.py tests/test_app_command_bridge.py tests/test_app_command_server.py tests/test_subtitle_live_editor_feed_facade.py tests/test_project_nle_runtime_cutover.py`: `115 passed`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_app_store_readiness_audit.py tests/test_macos_bundle_runtime_paths.py`: `9 passed`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_context.py tests/test_cp03_cp04_status_ui.py -k "schema or version or project_file_roundtrip or status"`: `66 passed, 79 deselected`
- Direct version assertion: `APP_VERSION=04.01.07`, `PROJECT_SCHEMA_VERSION=04.01.07`
- Jammini route proof: `.agents/sentinel/handoffs/20260629-021822-watchdog-handoff-probe.md`
- Jammini strong-evidence gate review: `.agents/sentinel/handoffs/20260628-272711-g3-observability-strong-evidence-gate-review-jammini.md`

## Not Included

- No real-media `live-nle-proof` run was claimed in this checkpoint.
- No visible UI label, layout, color, shortcut, menu, popup, timeline strip, or minimap change.
- No raw STT/VAD/subtitle-preview segment payload added to status/UDP responses.
- No final overlay, save/export authority, persisted NLE disk-format, STT/VAD algorithm, worker fan-out, cache default, App Store package, upload, or submission change.

## Remaining Risks

- The next G3 proof still needs an actual representative-media `live-nle-proof` run with snapshots and separate same-media final quality/speed evidence before the broader G3 acceptance gate can close.
