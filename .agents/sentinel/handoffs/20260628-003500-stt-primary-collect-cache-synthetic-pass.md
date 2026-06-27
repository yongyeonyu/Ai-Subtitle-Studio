DEX_REVIEW_READY

# STT1 Primary Collect Cache Synthetic Pass - 2026-06-28

## Scope

- Implemented an opt-in exact STT1 primary collect replay cache.
- Default remains `stt_primary_collect_cache_enabled=false`.
- Cache hits are disabled when a live `preview_callback` exists, so STT1 preview events are not skipped.
- Cache replay still runs STT2 selection, word precision, VAD/STT consensus, LLM/LoRA postprocess, final integrity, and reference acceptance.

## Evidence

- Report: `output/manual_verification/latest/stt_primary_collect_cache_20260628/primary_collect_cache_report.md`
- Cache file: `output/manual_verification/latest/stt_primary_collect_cache_20260628/primary_collect_cache_diagnostics.json`
- First write benchmark: `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_003224/benchmark_results.md`
  - elapsed `51.964s`
  - raw/final/reference `54/54/54`
  - quality/text/timing `80.153/91.676/1.437s`
  - final invalid/non-monotonic/overlap `0/0/0`
  - global max active `1`
  - STT1 collect `17.717081s`
  - cache hit/write/provider `false/true/true`
  - acceptance `accepted=true`
- Second cache-hit benchmark: `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_003326/benchmark_results.md`
  - elapsed `37.715s`
  - same quality/text/timing/final gates
  - STT1 collect `0.0s`
  - STT1 parent `0.049428s`
  - cache hit/write/provider `true/false/false`
  - backend/model preserved as `whisperkit_persistent` / `whisperkit-persistent:large-v3-v20240930_turbo_632MB`
  - acceptance `accepted=true`

## Verification

- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m py_compile core/audio/media_processor_transcribe.py core/runtime/config.py tools/verify_full_media_pipeline.py tests/test_media_processor_overlap.py tests/test_verify_full_media_pipeline.py` -> pass.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_media_processor_overlap.py -k "collect_transcribe_result"` -> `4 passed, 103 deselected`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_verify_full_media_pipeline.py -k "stage_wall_clock_rollup"` -> `1 passed, 14 deselected`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_verify_full_media_pipeline.py tests/test_benchmark_mode_profiles.py -k "stage_wall_clock or parse_setting_overrides or cli_setting_overrides"` -> `4 passed, 45 deselected`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_media_processor_overlap.py -k "collect_transcribe_result or word_precision_recheck_uses_user_selected_stt1_model or word_precision_recheck_allows_explicit_precision_model or selective or recheck"` -> `18 passed, 89 deselected`.
- `git diff --check -- core/audio/media_processor_transcribe.py core/runtime/config.py tools/verify_full_media_pipeline.py tests/test_media_processor_overlap.py tests/test_verify_full_media_pipeline.py` -> pass.

## Next

- Keep `stt_primary_collect_cache_enabled=false`.
- When NAS is available, backfill STT1 plus STT2/word collect caches on HeyDealer first 180s before using cache speed deltas as production evidence.
- If NAS remains off, inspect only non-behavioral scheduling or memory-pressure variance; do not skip STT1/STT2, downgrade models, shrink windows, remove word precision, or loosen final stability gates.
