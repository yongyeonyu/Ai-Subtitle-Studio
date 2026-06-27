# NLE Live Editor Caption Merge Cutover

DEX_REVIEW_READY

## Summary

- Live editor diamond merge now attempts runtime NLE `caption_merge` dual-write for stable final caption pairs.
- The route records a `caption_merge` `NLEEditorOperation`, projects back through runtime `NLEProjectState`, and reloads projected legacy rows when safe.
- Existing Taption/source-app QTextDocument merge remains fallback for STT/live preview rows, NLE rejection, missing caption identity, unsupported shapes, or invalid rows.

## Files

- `core/project/nle_dual_write.py`
- `ui/editor/ux/editor_timeline_video.py`
- `ui/editor/ux/editor_timeline_segment_merge.py`
- `tests/test_project_nle_dual_write.py`
- `tests/test_timeline_playhead_fit.py`
- `output/manual_verification/latest/nle_live_editor_caption_merge_cutover_20260628/caption_merge_cutover_report.md`

## Jammini Delegation

- Delegated bounded support review via `tools/jammini_delegate.sh`.
- Scope: STT/live-preview isolation, final overlap gates, Taption fallback preservation, and doc/test evidence gaps.
- Jammini support handoff: `.agents/sentinel/handoffs/20260628-015400-nle-caption-merge-support-review.md`.

## Verification

- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m py_compile core/project/nle_dual_write.py ui/editor/ux/editor_timeline_video.py ui/editor/ux/editor_timeline_segment_merge.py tests/test_project_nle_dual_write.py tests/test_timeline_playhead_fit.py` -> pass.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_dual_write.py -k "caption_merge or caption_delete or gap_generate"` -> `6 passed, 10 deselected`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py -k "diamond_merge_routes_live_editor_mutation or diamond_merge_falls_back or diamond_merge_extends_left_segment or diamond_merge_resolves_timeline_row_line_to_document_block"` -> `4 passed, 158 deselected`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_dual_write.py tests/test_project_nle_operations.py tests/test_project_nle_snapshot.py tests/test_project_nle_persistence_guard.py tests/test_project_nle_runtime_cutover.py tests/test_project_nle_render_export_parity.py -k "caption_merge or caption_delete or gap_generate or caption_resize or caption_move or nle_operation or runtime_nle or final_overlay or save_export"` -> `25 passed, 21 deselected`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py tests/test_timeline_hit_targets.py -k "diamond_merge or merge_preview or resize or gap_generate or segment_delete"` -> `45 passed, 267 deselected`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py tests/test_subtitle_live_editor_feed_facade.py` -> `165 passed`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/evaluate_reference_benchmark_acceptance.py .codex_work/benchmarks/subtitle_pipeline_variants/20260628_013224/benchmark_results.json` -> `accepted=true`.
- `git diff --check -- core/project/nle_dual_write.py ui/editor/ux/editor_timeline_video.py ui/editor/ux/editor_timeline_segment_merge.py tests/test_project_nle_dual_write.py tests/test_timeline_playhead_fit.py` -> pass.

## Risk

- No subtitle-generation, STT2, word precision, LLM, LoRA, VAD, timing, or mode-selection behavior changed.
- This is not persisted NLE project-field approval and does not delete legacy merge paths.
- `caption_split` and candidate-confirm routes still need separate focused gates before cutover.
