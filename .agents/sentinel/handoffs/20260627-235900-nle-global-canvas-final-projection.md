# DEX_REVIEW_READY - NLE Global Canvas Final Projection Cutover

## Summary

- Added `nle_global_canvas_segments_from_editor_rows(...)` in `core/project/nle_runtime_cutover.py`.
- Added optional `global_rows` to `TimelineWidget.update_segments(...)`.
- Editor redraw and live-preview timeline update paths pass confirmed final rows through NLE global-canvas projection.
- Timeline canvas still keeps live STT/subtitle preview rows; global canvas subtitle lane can now be final-only.

## Evidence

- Report: `output/manual_verification/latest/nle_global_canvas_final_projection_20260627/global_canvas_projection_report.md`

## Validation

- `./venv/bin/python -m py_compile core/project/nle_runtime_cutover.py ui/editor/editor_segments_timeline_context.py ui/editor/editor_segments_stt_selection_flow.py ui/timeline/timeline_widget.py tests/test_project_nle_runtime_cutover.py tests/test_timeline_playhead_fit.py` -> pass.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_runtime_cutover.py tests/test_timeline_playhead_fit.py -k "nle_runtime_cutover or final_overlay_cutover or global_canvas_cutover or final_only_rows_to_global_canvas or project_loaded_stt_preview"` -> `5 passed, 158 deselected`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py -k "global_canvas or project_loaded_stt_preview or final_only_rows_to_global_canvas"` -> `9 passed, 151 deselected`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_runtime_cutover.py tests/test_project_nle_render_export_parity.py tests/test_project_nle_snapshot.py` -> `20 passed, 4 subtests passed`.
- `git diff --check -- core/project/nle_runtime_cutover.py ui/editor/editor_segments_timeline_context.py ui/editor/editor_segments_stt_selection_flow.py ui/timeline/timeline_widget.py tests/test_project_nle_runtime_cutover.py tests/test_timeline_playhead_fit.py` -> pass.

## Notes

- No UI labels, colors, layout, menus, shortcuts, popups, STT, LLM, LoRA, VAD, timing, or model-selection policy changed.
- This is a source-app runtime NLE adoption slice only; save/reload, render/export, and broad persistence ownership cleanup remain gated.
