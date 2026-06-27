DEX_REVIEW_READY
역할: 덱스
프로젝트: AI Subtitle Studio
레포지토리 경로: /Users/u_mo_c/Downloads/ai_subtitle_studio
범위: NLE shortcut split-at-playhead commit sync

결론:
- `_split_at_playhead_or_cut(...)` now routes stable final-caption playhead split commits through runtime NLE `caption_split`.
- Existing Taption/source-app QTextDocument fallback remains active for STT/live preview rows, gap rows, unsupported rows, invalid split positions, selection cuts, and NLE rejection.
- `ACTION_ITEMS.md` now contains only active remaining work; completed NLE mutable-sync evidence lives in `COMPLETED_ACTION_ITEMS.md`.

수정 파일:
- `ui/editor/ux/editor_video_controls.py`
- `tests/test_timeline_playhead_fit.py`
- `ACTION_ITEMS.md`
- `COMPLETED_ACTION_ITEMS.md`
- `docs/HANDOFF.md`
- `test_result.md`
- `docs/PROJECT_STATE.md`
- `docs/FEATURE_REGISTRY.md`
- `output/manual_verification/latest/nle_shortcut_split_commit_sync_20260628/shortcut_split_report.md`

검증:
- `./venv/bin/python -m py_compile ui/editor/ux/editor_video_controls.py tests/test_timeline_playhead_fit.py` -> pass.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py -k "split_shortcut"` -> `2 passed, 191 deselected`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py -k "split_shortcut or smart_split or gap or magnet or reorder"` -> `25 passed, 168 deselected`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_dual_write.py -k "caption_split"` -> `2 passed, 28 deselected`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_runtime_cutover.py tests/test_timeline_render_cache.py -k "timeline_canvas or projection or final_surface or save_export"` -> `5 passed, 53 deselected`.
- `AI_SUBTITLE_STUDIO_QA_USE_SOURCE=1 ./venv/bin/python tools/qa_suite_runner.py quick --output-dir output/manual_verification/latest/qa_suite_quick_nle_shortcut_split_20260628` -> pass, `failed_count=0`.

아티팩트:
- `output/manual_verification/latest/nle_shortcut_split_commit_sync_20260628/shortcut_split_report.md`
- `output/manual_verification/latest/qa_suite_quick_nle_shortcut_split_20260628`
- `.agents/sentinel/handoffs/20260628-075011-watchdog-handoff-probe.md`
- `.agents/sentinel/handoffs/20260628-075500-nle-remaining-release-source-audit.md`

덱스 확인 포인트:
- Persisted NLE project fields remain gated.
- Future NLE write expansion should start from a new owner-approved active item and must re-prove fallback plus Taption rules.
