# RELEASE v04.01.33

Date: 2026-06-30 KST

Release app version: `04.01.33`
Project schema version: `04.01.33`

## Summary

`v04.01.33` is a source-app roughcut scenario-composer preview checkpoint.

It collects the G4 roughcut page frame cleanup, video-box playback surface,
editor-mode responsiveness benchmark plan, material-card drag/drop preview,
grid-aligned card layout, and parallel connector auto-sort preview into one
release checkpoint.

This release keeps final subtitle authority, original media/SRT authority,
STT1/STT2/VAD runtime ownership, App Store readiness, DMG packaging, and real
scenario MP4/SRT export behavior unchanged. The new roughcut scenario-composer
controls are preview/state scaffolding only until a later NLE-backed commit and
export slice is explicitly implemented.

## Changes

- `core/runtime/config.py` now reports `APP_VERSION = "04.01.33"`.
- `core/project/project_format.py` now marks newly saved project payloads as
  schema version `04.01.33`.
- The roughcut page keeps the owner-defined four-frame layout while hiding the
  old visible roughcut internals without deleting legacy functions, app
  commands, save/reopen helpers, or export helpers.
- The `비디오박스` now has the compact roughcut playback preview surface with
  subtitle preview and smaller control buttons.
- The `재료박스` preview supports 30 grid-snapped middle-segment cards, 20-card
  visible pages, horizontal scrolling beyond 20 cards, left/right card pins,
  random demo connections, up to 3 parallel outgoing connector lanes, and
  connector-order `자동정렬`.
- The `시나리오박스` preview shows the selected card or generated connector path
  as a one-line video/subtitle placeholder sequence.
- The `설정박스` exposes preview-only controls for `시나리오생성`, `멀티선택`,
  `합치기`, `분할`, `삭제`, and left/right trim adjustments.
- `docs/planning_queue/ACTION_ITEMS.md` and
  `docs/planning_queue/COMPLETED_ACTION_ITEMS.md` record the completed G4
  preview slices while keeping real editor binding, NLE commit, project
  persistence, split/merge/trim authority, and scenario export as remaining G4
  work.

## Validation

- `./venv/bin/python -m py_compile ui/roughcut/roughcut_widget.py tests/test_roughcut_ui_v2.py`
  -> pass.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_roughcut_ui_v2.py -k "material_preview or frame_only_boxes"`
  -> `3 passed, 40 deselected`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_roughcut_ui_v2.py tests/test_roughcut_candidates.py`
  -> `50 passed`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_app_command_bridge.py -k "roughcut"`
  -> `10 passed, 75 deselected`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_segment_reload.py -k "roughcut or open_project_file"`
  -> `4 passed, 86 deselected`.
- `PYTHONDONTWRITEBYTECODE=1 QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q -p no:cacheprovider tests/test_macos_bundle_runtime_paths.py tests/test_project_context.py tests/test_cp03_cp04_status_ui.py -k "schema or version or project_file_roundtrip or status"`
  -> `66 passed, 84 deselected`.
- Direct version assertion -> `APP_VERSION=04.01.33`,
  `PROJECT_SCHEMA_VERSION=04.01.33`.
- Tracked development `.md` path check, excluding `.agents`, `.codex_work`,
  `_backup_mac_migration`, `checkpoints`, and `output` -> pass.
- `git diff --check -- .` -> pass.
- Manual preview artifacts:
  `output/manual_verification/latest/roughcut_parallel_r_grid_20260630/`.

## Exclusions

- No DMG build or validation was performed for this release.
- No App Store package/signing/upload/submission readiness is claimed.
- No real scenario `_시나리오.srt` or `_시나리오.mp4` export is claimed.
- No roughcut split/merge/trim operation is committed to editor/NLE rows yet.
- No STT/cache default, subtitle generation, final subtitle authority, or NLE
  persistence load-owner policy changed.
