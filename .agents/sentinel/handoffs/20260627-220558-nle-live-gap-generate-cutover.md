# DEX_REVIEW_READY: NLE Live Gap Generate Cutover

- Scope: source-app NLE runtime editing adoption for live editor silence-gap subtitle generation.
- Changed files: `core/project/nle_dual_write.py`, `ui/editor/ux/editor_timeline_video.py`, `ui/editor/ux/editor_timeline_gap_split.py`, `tests/test_project_nle_dual_write.py`, `tests/test_timeline_playhead_fit.py`.
- Behavior: stable gap generation now attempts NLE `gap_generate` dual-write and preserves Taption-style left/right silence gap rows around the generated subtitle; live STT preview presence keeps the legacy Taption/source-app gap generation path.
- Evidence: `output/manual_verification/latest/nle_live_editor_gap_generate_cutover_20260627/gap_generate_cutover_report.md`.
- Focused validation: gap-generate/delete NLE `7 passed, 7 deselected`; live gap-generate/delete route `3 passed, 156 deselected`; Taption gap/delete `13 passed, 137 deselected`; NLE operation/persistence/runtime/render-export `42 passed, 4 subtests passed`; timeline/feed `162 passed`; drag/gap/magnet/app-command/delete `68 passed, 158 deselected`.
