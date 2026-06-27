# DEX_REVIEW_READY - STT Recheck Collect Cache Synthetic Pass

## Summary

- Implemented an opt-in STT2/word precision collect replay cache.
- Default remains `stt_recheck_collect_cache_enabled=false`.
- Cache hits skip provider collect only; annotation, STT2 replacement selection, word precision timing application, final integrity, and reference acceptance still run.
- Live STT2 preview callback paths disable this cache so candidate-lane preview events are not skipped.
- Owner had turned NAS off, so proof uses the generated 180.583s Korean fixture only.

## Evidence

- Report: `output/manual_verification/latest/stt_recheck_collect_cache_20260627/collect_cache_report.md`
- Final cache-hit SRT: `output/manual_verification/latest/stt_recheck_collect_cache_20260627/synthetic_final_subtitles_cache_hit.srt`
- Cache file: `output/manual_verification/latest/stt_recheck_collect_cache_20260627/stt_recheck_collect_cache.json`
- First write run: `.codex_work/benchmarks/subtitle_pipeline_variants/20260627_234839/benchmark_results.md`
- Second cache-hit run: `.codex_work/benchmarks/subtitle_pipeline_variants/20260627_234935/benchmark_results.md`

## Metrics

- First run: elapsed `46.498s`, raw/final/reference `54/54/54`, quality `80.153`, timing MAE `1.437s`, final invalid/non-monotonic/overlap `0/0/0`, global max active `1`.
- First run cache: STT2 collect `14.284272s`, word precision collect `10.930693s`, cache hit/write/provider `false/true/true`.
- Second run: elapsed `20.105s`, same quality/final gates, accepted `true`.
- Second run cache: STT2 collect `0.0s`, word precision collect `0.0s`, cache hit/write/provider `true/false/false`.

## Validation

- `./venv/bin/python -m py_compile core/audio/stt_recheck_service.py core/audio/media_processor_transcribe_recheck.py core/runtime/config.py tools/benchmark_subtitle_pipeline_variants.py tools/verify_full_media_pipeline.py tests/test_stt_recheck_service.py tests/test_verify_full_media_pipeline.py` -> pass.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_stt_recheck_service.py -k "prepare_and_collect_recheck_segments or collect_and_annotate_segments"` -> `4 passed, 35 deselected`.
- `./venv/bin/python -m pytest -q tests/test_verify_full_media_pipeline.py -k "stage_wall_clock_rollup"` -> `1 passed, 14 deselected`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_media_processor_overlap.py -k "word_precision_recheck_uses_user_selected_stt1_model or word_precision_recheck_allows_explicit_precision_model or selective or recheck"` -> `14 passed, 91 deselected`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_benchmark_mode_profiles.py -k "stage_wall_clock_summary"` -> `1 passed, 33 deselected`.
- `tools/evaluate_reference_benchmark_acceptance.py` on both synthetic collect-cache benchmark results -> `accepted=true`.

## Next

- Run NAS HeyDealer first 180s backfill when NAS is available again.
- Do not enable this cache by default until representative real-media acceptance passes.
