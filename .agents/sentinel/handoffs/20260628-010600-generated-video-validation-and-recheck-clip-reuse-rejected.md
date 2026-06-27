DEX_REVIEW_READY

# Generated Video Validation And Recheck Clip Reuse Rejection

- Scope: NAS-off owner-requested generated-video subtitle validation plus cleanup of the prepared recheck clip reuse candidate.
- Generated-video validation report: `output/manual_verification/latest/generated_video_subtitle_validation_20260628_latest/validation_report.md`
- Generated final SRT: `output/manual_verification/latest/generated_video_subtitle_validation_20260628_latest/generated_final_subtitles.srt`
- Benchmark: `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_010403/benchmark_results.md`
- Acceptance: `output/manual_verification/latest/generated_video_subtitle_validation_20260628_latest/acceptance/reference_benchmark_acceptance.md`
- Result: pass, elapsed `44.968s`, raw/final/reference `54/54/54`, quality/text/timing `80.153/91.676/1.437s`, final invalid/non-monotonic/overlap `0/0/0`, generated SRT rows `54`, SRT invalid/non-monotonic/overlap `0/0/0`, global max active `1`, `accepted=true`.
- Rejected candidate report: `output/manual_verification/latest/recheck_prepared_clip_reuse_rejected_20260628/recheck_prepared_clip_reuse_rejection_report.md`
- Rejected candidate: prepared STT2/word clip metadata reuse on collect-cache hit. Prepare time did not materially drop and metadata/directory retention complexity was not accepted; code/tests were reverted.
- Next: keep STT collect caches default-off. When NAS returns, run HeyDealer first-180s real-media backfill before production-wide speed claims.
