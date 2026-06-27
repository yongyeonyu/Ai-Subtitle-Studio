DEX_REVIEW_READY

# STT2 / Word Precision Substage Timing

## Summary

- Added instrumentation only: STT2/word precision batch preparation, collect, annotation, and total batch elapsed are now recorded.
- No subtitle generation policy, model selection, STT2 coverage, word precision coverage, or final stability rule changed.
- Local 60s reference smoke confirms the values are present in `stage_wall_clock_summary`.

## Evidence

- Report: `output/manual_verification/latest/stt2_word_precision_substage_timing_20260627/substage_timing_report.md`
- Local smoke: `.codex_work/benchmarks/subtitle_pipeline_variants/20260627_200405/benchmark_results.json`
- STT2: total `11.258246s`, prepare `0.054922s`, collect `11.201352s`, annotate `0.000620s`, batch `11.256907s`.
- Word precision: total `4.368781s`, prepare `0.062083s`, collect `4.304654s`, annotate `0.000297s`, batch `4.367046s`.
- Stability: raw/final `2/2`, final overlap `0`, stable save/reopen true, global max active `1`.

## Validation

- Touched Python `py_compile` -> pass.
- Focused service/summary guards -> `3 passed, 35 deselected`, `1 passed, 30 deselected`, `2 passed, 13 deselected`.
- Broader guards -> verifier/benchmark `46 passed`; STT recheck/media overlap subset `46 passed, 96 deselected`; `git diff --check -- .` pass.

## Next

- Rerun substage timing on HeyDealer/X5 when fixture paths are available.
- Next optimization should inspect collect/worker scheduling or duplicate cache work, not clip preparation/annotation.
