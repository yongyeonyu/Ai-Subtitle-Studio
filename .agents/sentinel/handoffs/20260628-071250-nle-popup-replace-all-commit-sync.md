DEX_REVIEW_READY
역할: 덱스
프로젝트: AI Subtitle Studio
레포지토리 경로: /Users/u_mo_c/Downloads/ai_subtitle_studio
범위: NLE popup replace-all commit sync

결론:
- `_replace_text_in_all_subtitles(...)` safe final-caption replacement now attempts sequential runtime NLE `caption_text_edit` operations.
- Operation metadata records `commit_boundary=release` and `commit_source=popup_replace_all`.
- Visible gap text, STT/live preview rows, unsupported row sets, and NLE rejection keep the existing QTextDocument fallback path.

수정 파일:
- `ui/editor/editor_segments_text_ops.py`
- `tests/test_timeline_playhead_fit.py`
- `ACTION_ITEMS.md`
- `COMPLETED_ACTION_ITEMS.md`
- `docs/HANDOFF.md`
- `test_result.md`

검증:
- `./venv/bin/python -m py_compile ui/editor/editor_segments_text_ops.py tests/test_timeline_playhead_fit.py` -> pass
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py -k "replace_text_in_all_subtitles"` -> `3 passed, 184 deselected`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_segment_reload.py -k "replace_text_in_all_subtitles"` -> `1 passed, 87 deselected`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py tests/test_project_segment_reload.py -k "replace_text_in_all_subtitles or inline_text or text_edit or change_speaker_for_line"` -> `12 passed, 263 deselected`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_dual_write.py -k "caption_text_edit"` -> `2 passed, 26 deselected`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_hit_targets.py tests/test_timeline_playhead_fit.py -k "gap or magnet or center_reorder or center_drag or reorder"` -> `66 passed, 274 deselected`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_runtime_cutover.py -k "timeline_canvas or final_surface or global_canvas or save_export"` -> `7 passed, 3 deselected`
- `AI_SUBTITLE_STUDIO_QA_USE_SOURCE=1 ./venv/bin/python tools/qa_suite_runner.py quick --output-dir output/manual_verification/latest/qa_suite_quick_nle_popup_replace_all_20260628` -> pass, `failed_count=0`

다음:
- Continue fresh audit for any remaining safe release/commit source. Do not reuse the latest Jammini scout's first three candidates without rechecking; they are already completed.
