# RELEASE v04.01.35

Date: 2026-07-02 KST

Release app version: `04.01.35`
Project schema version: `04.01.35`

## Summary

`v04.01.35` is a source-app roughcut scenario-canvas preview checkpoint.

It refines the G4 roughcut scenario/material preview into a shared PyQt6 2D
canvas model: material cards can keep free 1-grid placement, connector routing
uses straight orthogonal paths, connector drag uses magnetic pin snapping, and
the scenario/material canvases support Command/Ctrl-wheel zoom with only small
top-right percentage indicators visible.

This release keeps final subtitle authority, original media/SRT authority,
STT1/STT2/VAD runtime ownership, NLE persistence load-owner policy, App Store
readiness, DMG packaging, and real scenario MP4/SRT export behavior unchanged.

## Changes

- `core/runtime/config.py` now reports `APP_VERSION = "04.01.35"`.
- `core/project/project_format.py` now marks newly saved project payloads as
  schema version `04.01.35`.
- Added shared `RoughcutCanvasView` behavior for roughcut scenario/material
  preview surfaces: Command/Ctrl-wheel zoom, Space/middle-button pan, internal
  reset/fit helpers, and small top-right zoom percentage indicators.
- Removed visible roughcut canvas zoom buttons from the scenario/material
  preview; zoom is now user-driven through Command/Ctrl-wheel.
- Added roughcut material storyboard snapshot fields for `canvas_grid_positions`,
  `canvas_view`, and `connector_style`, with backward-compatible fallback from
  legacy `grid_slots`.
- Changed manual material-card dragging to update free canvas placement without
  mutating connector topology, scenario order, NLE rows, final subtitle rows, or
  save/export authority.
- Changed normal connector rendering to straight orthogonal `lineTo` paths while
  preserving line-jump overlays for crossings.
- Added magnetic routing behavior so connector shadows snap to nearby target
  pins and preserve existing input-auto-copy behavior.

## Validation

- `./venv/bin/python -m py_compile ui/roughcut/editor/storyboard_view.py ui/roughcut/roughcut_widget.py tests/test_roughcut_ui_v2.py tests/test_roughcut_candidates.py`
  -> pass.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_roughcut_ui_v2.py -k "material_preview or scenario_sequence"`
  -> `26 passed, 42 deselected`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_roughcut_candidates.py -k "storyboard"`
  -> `1 passed, 7 deselected`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_roughcut_ui_v2.py tests/test_roughcut_candidates.py`
  -> `76 passed`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_app_command_bridge.py -k "roughcut"`
  -> `10 passed, 75 deselected`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_segment_reload.py -k "roughcut or open_project_file"`
  -> `4 passed, 86 deselected`.
- `PYTHONDONTWRITEBYTECODE=1 QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q -p no:cacheprovider tests/test_macos_bundle_runtime_paths.py tests/test_project_context.py tests/test_cp03_cp04_status_ui.py -k "schema or version or project_file_roundtrip or status"`
  -> `66 passed, 84 deselected`.
- Direct version assertion -> `APP_VERSION=04.01.35`,
  `PROJECT_SCHEMA_VERSION=04.01.35`.
- `git diff --check -- .` -> pass.
- Manual preview artifacts:
  `output/manual_verification/latest/roughcut_scenario_canvas_rework_20260702/roughcut_canvas_rework_preview.png`;
  `output/manual_verification/latest/roughcut_scenario_canvas_rework_20260702/roughcut_canvas_zoom_indicator_preview.png`.

## Exclusions

- No DMG build or validation was performed for this release.
- No App Store package/signing/upload/submission readiness is claimed.
- No real scenario `_시나리오.srt` or `_시나리오.mp4` export is claimed.
- No roughcut split/merge/trim operation is committed to editor/NLE rows yet.
- No STT/cache default, subtitle generation, final subtitle authority, or NLE
  persistence load-owner policy changed.
