DEX_REVIEW_READY

# STT1 Primary Collect Diagnostics

- Scope: behavior-preserving STT1 collect diagnostics for the active generation-latency item.
- Report: `output/manual_verification/latest/stt_primary_collect_diagnostics_20260628/stt_primary_collect_report.md`
- Benchmark: `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_001645/benchmark_results.md`
- Acceptance: `output/manual_verification/latest/stt_primary_collect_diagnostics_20260628/acceptance/reference_benchmark_acceptance.md`
- Result: pass, `accepted=true`, raw/final/reference `54/54/54`, final invalid/non-monotonic/overlap `0/0/0`, global max active `1`.
- STT1 finding: total `20.135353s`, setup `0.046327s`, collect `19.986159s`, backend `whisperkit_persistent`, chunks `2`, worker count `2`, worker cache hit `false`.
- Interpretation: STT1 cost is actual collect time on this fixture, not setup/idle overhead; no STT1 skip/model downgrade/window shrink is justified.
