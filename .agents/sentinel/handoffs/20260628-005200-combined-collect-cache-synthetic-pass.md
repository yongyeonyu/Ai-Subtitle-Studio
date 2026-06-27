DEX_REVIEW_READY

# Combined Collect Cache Synthetic Pass - 2026-06-28 00:52 KST

Scope:
- NAS remained off by owner direction, so Dex used the generated 180s Korean fixture.
- Normalized STT1 primary collect and STT2/word collect cache keys so unrelated cache enable/path/max-entry controls do not invalidate exact replay entries when caches are enabled together.
- Defaults remain off: `stt_primary_collect_cache_enabled=false`, `stt_recheck_collect_cache_enabled=false`.

Evidence:
- Report: `output/manual_verification/latest/combined_collect_cache_20260628/combined_collect_cache_report.md`
- Generated final SRT: `output/manual_verification/latest/combined_collect_cache_20260628/synthetic_final_from_second_run.srt`
- SRT validation: `output/manual_verification/latest/combined_collect_cache_20260628/synthetic_final_from_second_run_srt_report.json`
- First benchmark: `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_004231/benchmark_results.md`
- Second benchmark: `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_004504/benchmark_results.md`
- Acceptance: `output/manual_verification/latest/combined_collect_cache_20260628/acceptance_first/reference_benchmark_acceptance.md`, `output/manual_verification/latest/combined_collect_cache_20260628/acceptance_second/reference_benchmark_acceptance.md`

Result:
- First write run: elapsed `72.570s`, raw/final/reference `54/54/54`, quality/text/timing `80.153/91.676/1.437s`, final invalid/non-monotonic/overlap `0/0/0`, global max active `1`, accepted `true`.
- Second cache-hit run: elapsed `4.449s`, same scored quality/final gates, STT1/STT2/word collect `0.0s/0.0s/0.0s`, macro provider group `0`, accepted `true`.
- Generated final SRT: block count `54`, invalid/non-monotonic/overlap `0/0/0`.

Next:
- Keep collect caches default-off.
- When NAS is available, backfill HeyDealer first-180s with the same combined cache settings before claiming production-wide speed.
- If NAS remains off, continue only non-behavioral scheduling, duplicate-work, or memory-pressure investigation.
