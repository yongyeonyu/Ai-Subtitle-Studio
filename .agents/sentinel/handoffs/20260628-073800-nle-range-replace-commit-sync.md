# DEX_REVIEW_READY - AI Subtitle Studio NLE Range Replace Commit Sync

- Project: AI Subtitle Studio
- Repo root: `/Users/u_mo_c/Downloads/ai_subtitle_studio`
- Scope: `clear_segments_in_range(...)` / `insert_partial_segments(...)` partial subtitle replacement commit boundary.
- Result: implemented `caption_range_replace` runtime NLE dual-write with legacy fallback.

## Summary

- Added `caption_range_replace` to the NLE operation model and persistence audit matrix.
- Added a range-replace pilot that replaces target-start rows only, preserves before/after rows, assigns unique identities to inserted rows, and rejects STT/live preview or unsupported row shapes.
- Routed source-app partial insert commits through the NLE pilot after legacy rows are committed, then reloads projected rows only when the NLE result is safe.
- Kept UI/UX, visible labels, generation policy, save format, packaging, and App Store behavior unchanged.

## Evidence

- Report: `output/manual_verification/latest/nle_partial_range_replace_commit_sync_20260628/range_replace_report.md`.
- Persistence audit: `output/manual_verification/latest/nle_persistence_identity_preservation_range_replace_20260628/nle_persistence_cutover_audit.md`.
- Source-app quick QA: `output/manual_verification/latest/qa_suite_quick_nle_range_replace_20260628`.

## Verification

- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_dual_write.py tests/test_project_nle_operations.py tests/test_nle_persistence_cutover_audit.py` -> `39 passed`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py -k "partial_insert or gap or magnet or reorder"` -> `25 passed, 166 deselected`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_hit_targets.py tests/test_project_segment_reload.py -k "gap or magnet or reorder or caption_range_replace or identity or reload"` -> `125 passed, 116 deselected`.
- `AI_SUBTITLE_STUDIO_QA_USE_SOURCE=1 ./venv/bin/python tools/qa_suite_runner.py quick --output-dir output/manual_verification/latest/qa_suite_quick_nle_range_replace_20260628` -> pass, `failed_count=0`.
