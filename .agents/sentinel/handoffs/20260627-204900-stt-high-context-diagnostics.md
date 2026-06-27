DEX_REVIEW_READY

역할: 덱스
범위: STT2/word precision latency item - High context-boundary diagnostics and accuracy-first test surface

읽은 파일:
- `ACTION_ITEMS.md`
- `waste_action_item.md`
- `lesson_n_learned.md`
- `core/engine/subtitle_context_refiner.py`
- `core/engine/subtitle_engine.py`
- `tools/benchmark_subtitle_pipeline_variants.py`
- `tools/verify_full_media_pipeline.py`
- `.agents/sentinel/handoffs/20260627-stt-accuracy-test-review.md`

결론:
- High context-boundary behavior was not optimized or skipped.
- Added diagnostics so future latency candidates can distinguish elapsed time from candidate-pair count, LLM call count, failed calls, and actual changed-pair count.
- Cached X5 audio 180s proved the metrics are emitted, but no reference-scored quality acceptance was claimed.

검증:
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m py_compile core/engine/subtitle_context_refiner.py core/engine/subtitle_engine.py tools/benchmark_subtitle_pipeline_variants.py tools/verify_full_media_pipeline.py tests/test_subtitle_context_refiner.py tests/test_benchmark_mode_profiles.py tests/test_verify_full_media_pipeline.py` -> pass.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_subtitle_context_refiner.py tests/test_verify_full_media_pipeline.py -k "context_refiner or stage_wall_clock or repeat_summary"` -> `7 passed, 13 deselected`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_benchmark_mode_profiles.py -k "run_postprocess or stage_wall_clock_summary"` -> `3 passed, 29 deselected`.
- Cached X5 audio 180s verifier -> pipeline `74.919s`, raw/final `43/50`, final invalid/non-monotonic/overlap `0/0/0`, stable save/reopen true, global max active `1`, high-context candidate/call/changed `4/4/0`, failed calls `0`, elapsed `32.230357s`.
- `git diff --check -- core/engine/subtitle_context_refiner.py core/engine/subtitle_engine.py tools/benchmark_subtitle_pipeline_variants.py tools/verify_full_media_pipeline.py tests/test_subtitle_context_refiner.py tests/test_benchmark_mode_profiles.py tests/test_verify_full_media_pipeline.py` -> pass.

남은 리스크:
- `/Volumes/photo/.../헤이딜러_최종.MP4` and `.srt` were not mounted.
- Repo-local X5 reference SRT was unavailable.
- Next latency trim adoption needs reference-scored HeyDealer/X5 quality/text/timing/segmentation parity.
- Memory pressure still reached `critical` on the X5 audio run.

덱스 확인 포인트:
- Continue `ACTION_ITEMS.md` item 1 by restoring/mounting a reference-scored fixture first.
- Do not retry High context-boundary batching or skipping from the non-reference `changed_pair_count=0` result alone.
