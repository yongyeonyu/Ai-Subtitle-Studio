# RELEASE v04.01.34

Date: 2026-06-30 KST

Release app version: `04.01.34`
Project schema version: `04.01.34`

## Summary

`v04.01.34` is a source-app roughcut material-card interaction preview
checkpoint.

It refines the G4 roughcut scenario-composer preview so the material card
surface behaves closer to the owner-requested NLE planning model: the default
layout is a left-to-right time sequence, parallel cut candidates stack in a
fixed 3-row column, card pins visibly hover/connect, connector lines visibly
hover, right-click deletes a connector, and the `ㅓ` frame handle can adjust
the scenario/material height as well as the left/right width.

This release keeps final subtitle authority, original media/SRT authority,
STT1/STT2/VAD runtime ownership, NLE persistence load-owner policy, App Store
readiness, DMG packaging, and real scenario MP4/SRT export behavior unchanged.

## Changes

- `core/runtime/config.py` now reports `APP_VERSION = "04.01.34"`.
- `core/project/project_format.py` now marks newly saved project payloads as
  schema version `04.01.34`.
- The roughcut `ㅓ` floating handle now also drives the scenario/material
  vertical splitter, so the left-side white/blue frame boundary can be adjusted
  up and down from the same handle.
- The `재료박스` preview now uses a fixed 3-row visual model:
  - no parallel branch: cards remain one horizontal time sequence;
  - parallel branch: up to 3 cut candidates stack in the same time column;
  - connections trigger immediate left-to-right auto layout.
- Card side pins now highlight on hover, remain highlighted while a connection
  is being drawn, and can be used to connect right pin to left pin.
- Connector lines now highlight on hover and can be removed with right click.
- The random demo connector action now applies the same immediate time-order
  auto layout instead of leaving a tangled preview state.

## Validation

- `./venv/bin/python -m py_compile ui/roughcut/roughcut_widget.py tests/test_roughcut_ui_v2.py`
  -> pass.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_roughcut_ui_v2.py -k "material_preview or frame_only_boxes"`
  -> `4 passed, 40 deselected`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_roughcut_ui_v2.py`
  -> `44 passed`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_roughcut_ui_v2.py tests/test_roughcut_candidates.py`
  -> `51 passed`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_app_command_bridge.py -k "roughcut"`
  -> `10 passed, 75 deselected`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_segment_reload.py -k "roughcut or open_project_file"`
  -> `4 passed, 86 deselected`.
- `PYTHONDONTWRITEBYTECODE=1 QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q -p no:cacheprovider tests/test_macos_bundle_runtime_paths.py tests/test_project_context.py tests/test_cp03_cp04_status_ui.py -k "schema or version or project_file_roundtrip or status"`
  -> `66 passed, 84 deselected`.
- Direct version assertion -> `APP_VERSION=04.01.34`,
  `PROJECT_SCHEMA_VERSION=04.01.34`.
- Tracked development `.md` path check, excluding `.agents` -> pass.
- `git diff --check -- .` -> pass.
- Manual preview artifact:
  `output/manual_verification/latest/roughcut_3row_connector_handles_20260630/`.

## Exclusions

- No DMG build or validation was performed for this release.
- No App Store package/signing/upload/submission readiness is claimed.
- No real scenario `_시나리오.srt` or `_시나리오.mp4` export is claimed.
- No roughcut split/merge/trim operation is committed to editor/NLE rows yet.
- No STT/cache default, subtitle generation, final subtitle authority, or NLE
  persistence load-owner policy changed.
