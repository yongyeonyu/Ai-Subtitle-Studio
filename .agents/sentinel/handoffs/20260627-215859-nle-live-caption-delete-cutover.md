# DEX_REVIEW_READY: NLE Live Caption Delete Cutover

- Scope: source-app NLE runtime editing adoption for live editor segment delete-to-gap.
- Changed files: `core/project/nle_dual_write.py`, `ui/editor/ux/editor_timeline_video.py`, `ui/editor/ux/editor_timeline_gap_split.py`, `tests/test_project_nle_dual_write.py`, `tests/test_timeline_playhead_fit.py`.
- Behavior: stable final segment deletion now attempts NLE `caption_delete` dual-write and records `replace_with_silence_gap`; live STT preview presence keeps the legacy Taption/source-app gap conversion path.
- Evidence: `output/manual_verification/latest/nle_live_editor_caption_delete_cutover_20260627/caption_delete_cutover_report.md`.
- Focused validation: NLE delete/gap/resize `9 passed, 3 deselected`; live delete/resize route `4 passed, 153 deselected`; Taption gap/delete `13 passed, 137 deselected`; NLE operation/persistence/runtime/render-export `40 passed, 4 subtests passed`; timeline/feed `160 passed`; drag/gap/magnet/app-command/delete `68 passed, 158 deselected`.
