DEX_REVIEW_READY
역할: 덱스
프로젝트: AI Subtitle Studio
레포지토리 경로: /Users/u_mo_c/Downloads/ai_subtitle_studio
범위: NLE quality-review text commit sync closeout

결론:
- ACCEPTED. Quality-review candidate / one-click text replacement commits now attempt runtime NLE `caption_text_edit` for stable final-caption rows.
- Existing QTextDocument fallback remains for STT/live preview, unchanged text, unsupported rows, or NLE rejection.
- Quality metadata is restored after NLE projection reload so `candidate_applied`, `manual_confirmed`, candidate reason, and quality candidates remain visible.

수정 파일:
- `ui/editor/editor_quality_review.py`
- `tests/test_timeline_playhead_fit.py`
- `ACTION_ITEMS.md`
- `COMPLETED_ACTION_ITEMS.md`
- `docs/HANDOFF.md`
- `test_result.md`

검증:
- `./venv/bin/python -m py_compile ui/editor/editor_quality_review.py tests/test_timeline_playhead_fit.py` -> pass.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py -k "quality_candidate_text_commit"` -> `2 passed, 187 deselected`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py -k "quality_candidate_text_commit or replace_text_in_all_subtitles or manual_confirmed or inline_text"` -> `6 passed, 183 deselected`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_dual_write.py -k "caption_text_edit"` -> `2 passed, 26 deselected`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_hit_targets.py tests/test_timeline_playhead_fit.py -k "gap or magnet or reorder"` -> `58 passed, 284 deselected`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_runtime_cutover.py tests/test_timeline_render_cache.py -k "timeline_canvas or projection or final_surface or save_export"` -> `5 passed, 53 deselected`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_segment_reload.py -k "caption_text_edit or identity or reload"` -> `88 passed`.
- `git diff --check -- .` -> pass.
- `AI_SUBTITLE_STUDIO_QA_USE_SOURCE=1 ./venv/bin/python tools/qa_suite_runner.py quick --output-dir output/manual_verification/latest/qa_suite_quick_nle_quality_text_commit_20260628` -> pass, `failed_count=0`.

다음 확인 포인트:
- `clear_segments_in_range(...)` / `insert_partial_segments(...)` remains deferred until a richer NLE range-replace/transaction operation family is designed.
