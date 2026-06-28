# RELEASE v04.01.13

Date: 2026-06-29
Previous release: `v04.01.12`
Release app version: `04.01.13`

## Summary

`v04.01.13` is a focused source-app G3 app-command responsiveness checkpoint.

This release proves that the same-media app-command path can open media, start generation, keep status/guided-status responsive while workers are active, and then execute automation-only cancel, close, and quit requests without changing visible UI.

## Key Changes

- Version and schema:
  - `core/runtime/config.py` now reports `APP_VERSION = "04.01.13"`.
  - `core/project/project_format.py` now marks newly saved project payloads as schema version `04.01.13`.

- Active-worker automation controls:
  - Added automation-only `cancel-current-pipeline`, `app-close-request`, and `app-quit-request` app commands.
  - These commands are intentionally separate from global menu actions and do not widen the global menu allowlist.
  - `tools/appctl.py` and `tools/remote_verify.py` can issue the new commands.
  - `tools/remote_verify.py editor-sequence` now supports `start-current-pipeline`, `status-probe`, `guided-status-probe`, `wait-N`, and per-command elapsed timing.

## Evidence

- Cancel proof: `output/manual_verification/latest/g3_open_media_generation_responsiveness_v040113_cancel_20260629_083050/report.md`
- Close proof: `output/manual_verification/latest/g3_open_media_generation_responsiveness_v040113_close_20260629_083123/report.json`
- Quit proof: `output/manual_verification/latest/g3_open_media_generation_responsiveness_v040113_quit_20260629_083225/report.json`
- Three sub-agent reviews were used for architecture, QE, and editor-workflow guardrails.
- The current Jammini `--handoff-probe` packet timed out without a fresh physical handoff file; `.agents/sentinel/handoffs/20260629-070211-watchdog-handoff-probe.md` remains the latest physical route proof.

## Validation

- `./venv/bin/python -m py_compile ui/main/app_command_bridge_handlers.py tools/appctl.py tools/remote_verify.py tests/test_app_command_bridge.py tests/test_appctl.py tests/test_remote_verify_actions.py`: pass
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_appctl.py tests/test_remote_verify_actions.py -k "active_worker_control or generation_status_and_wait or editor_sequence_maps_play_pause"`: `4 passed, 18 deselected`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_app_command_bridge.py -k "cancel_current_pipeline or app_close_and_quit_requests or global_menu_action_rejects_unsafe_action or start_current_pipeline"`: `4 passed, 80 deselected`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_app_store_readiness_audit.py tests/test_macos_bundle_runtime_paths.py`: `9 passed`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_context.py tests/test_cp03_cp04_status_ui.py -k "schema or version or project_file_roundtrip or status"`: `66 passed, 80 deselected`
- Cancel proof: `open-media` returned `media_opened`, `start-current-pipeline` returned `pipeline_started`, active samples reported `ST_PROC/backend_active=true`, status/guided-status command elapsed samples stayed below `0.01s`, and `cancel-current-pipeline` returned `current_pipeline_cancel_requested` before post-cancel status reported `ST_IDLE/backend_active=false`.
- Close proof: `app-close-request` returned `app_close_requested` in `0.009954s` while active, then the bridge became `app_unreachable` after app exit.
- Quit proof: `app-quit-request` returned `app_quit_requested` in `0.001577s` while active, then the bridge became `app_unreachable` after app exit.
- Direct version assertion: `APP_VERSION=04.01.13`, `PROJECT_SCHEMA_VERSION=04.01.13`
- `git diff --check -- .`: pass

## Not Included

- No full G3 completion claim.
- No UI label, layout, color, shortcut, menu, popup, timeline strip, or minimap change.
- No STT/VAD algorithm, worker fan-out, model-selection, cache default, or subtitle-quality policy change.
- No persisted NLE disk-format cutover.
- No App Store package, validation, upload, metadata submission, or final App Store submission.

## Remaining Risks

- Broader same-media global-canvas responsiveness and any additional active-worker final-surface proof remain separate G3 gates.
- G0 App Store remains blocked on Apple Distribution/Installer identities, signed `.pkg`, sandbox smoke, App Store Connect validation, and owner metadata.
