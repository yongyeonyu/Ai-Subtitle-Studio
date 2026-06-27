DEX_REVIEW_READY

# NLE Live Boundary Resize Cutover

## Scope

- Extended the source-app live editor NLE `caption_resize` route beyond `diamond`.
- `square_left` and `square_right` boundary-handle subtitle resizes now attempt runtime NLE dual-write before falling back to the existing Taption/source-app timing path.

## Files

- `ui/editor/ux/editor_timeline_video.py`
- `tests/test_timeline_playhead_fit.py`
- `output/manual_verification/latest/nle_live_editor_boundary_resize_cutover_20260627/boundary_resize_cutover_report.md`

## Validation

- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m py_compile ui/editor/ux/editor_timeline_video.py tests/test_timeline_playhead_fit.py` -> pass
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py -k "square_left_resize_routes_live_editor_mutation or square_right_resize_routes_live_editor_mutation or square_resize_falls_back or diamond_resize_routes_live_editor_mutation"` -> `4 passed, 151 deselected`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py -k "resize or diamond or single_gap or center_drag"` -> `32 passed, 123 deselected`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_dual_write.py tests/test_project_nle_operations.py tests/test_project_nle_snapshot.py tests/test_project_nle_persistence_guard.py tests/test_project_nle_runtime_cutover.py tests/test_project_nle_render_export_parity.py` -> `38 passed, 4 subtests passed`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_hit_targets.py tests/test_app_command_bridge.py -k "drag or gap or magnet or stt_candidate"` -> `63 passed, 163 deselected`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py tests/test_subtitle_live_editor_feed_facade.py` -> `158 passed`
- `git diff --check -- ui/editor/ux/editor_timeline_video.py tests/test_timeline_playhead_fit.py` -> pass

## Review

- Accept as another incremental NLE runtime editing adoption slice.
- No visible UI/UX, subtitle quality policy, STT2, LLM, LoRA, VAD, save format, render/export, packaging, release, commit, or push behavior changed.
