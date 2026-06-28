# RELEASE v04.01.14

Date: 2026-06-29
Previous release: `v04.01.13`
Release app version: `04.01.14`

## Summary

`v04.01.14` is a focused source-app G3 active global-canvas responsiveness checkpoint.

This release proves that the same-media app-command path can keep timeline/global-canvas view controls, play/pause, status, and guided-status responsive while subtitle generation workers are active. It does not change visible UI or final save/export authority.

## Key Changes

- Version and schema:
  - `core/runtime/config.py` now reports `APP_VERSION = "04.01.14"`.
  - `core/project/project_format.py` now marks newly saved project payloads as schema version `04.01.14`.

- Proof harness:
  - `tools/remote_verify.py editor-sequence` can now call existing automation commands for `timeline-zoom-in`, `timeline-zoom-out`, `timeline-fit`, `timeline-time-window`, `timeline-max`, and `zoom-max`.
  - `tests/test_remote_verify_actions.py` covers the new action-to-command mapping.

## Evidence

- Active global-canvas proof: `output/manual_verification/latest/g3_global_canvas_responsiveness_v040114_20260629_084817/report.md`
- Three sub-agent reviews were used for architecture, QE, and editor-workflow guardrails.
- The current Jammini `--handoff-probe` packet timed out without a fresh physical handoff file; `.agents/sentinel/handoffs/20260629-070211-watchdog-handoff-probe.md` remains the latest physical route proof.

## Validation

- `./venv/bin/python -m py_compile core/runtime/config.py core/project/project_format.py tools/remote_verify.py tests/test_remote_verify_actions.py tests/test_macos_bundle_runtime_paths.py`: pass
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_remote_verify_actions.py -k "global_canvas_responsiveness or generation_status_and_wait or active_worker_control"`: `3 passed, 13 deselected`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_app_command_bridge.py -k "editor_timeline_view_command_exercises_zoom_and_fit or status_command_reports_compact_nle_runtime_track_counts or dispatch_status_command"`: `7 passed, 77 deselected`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_app_store_readiness_audit.py tests/test_macos_bundle_runtime_paths.py`: `9 passed`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_context.py tests/test_cp03_cp04_status_ui.py -k "schema or version or project_file_roundtrip or status"`: `66 passed, 80 deselected`
- Active global-canvas proof: `open-media` returned `media_opened`, `start-current-pipeline` returned `pipeline_started`, active samples reported `ST_PROC/backend_active=true`, timeline zoom/fit/time-window/max plus zoom-max/play/pause/status/guided-status all returned `ok=true`, max command elapsed was `0.267435s`, all `19` snapshots were nonzero, final track count stayed `0`, and cancel returned to `backend_active=false`.
- Direct version assertion: `APP_VERSION=04.01.14`, `PROJECT_SCHEMA_VERSION=04.01.14`
- `git diff --check -- .`: pass

## Not Included

- No full G3 completion claim.
- No UI label, layout, color, shortcut, menu, popup, timeline strip, minimap, or visual redesign change.
- No STT/VAD algorithm, worker fan-out, model-selection, cache default, or subtitle-quality policy change.
- No persisted NLE disk-format cutover.
- No active video-export while generation is running.
- No App Store package, validation, upload, metadata submission, or final App Store submission.

## Remaining Risks

- Any additional active-worker final-surface proof remains a separate G3 gate if selected by the queue.
- G0 App Store has owner approval for packaging/signing/upload/metadata execution, but remains blocked on Apple Distribution/Installer identities, signed `.pkg`, sandbox smoke, App Store Connect validation, and owner metadata values.
