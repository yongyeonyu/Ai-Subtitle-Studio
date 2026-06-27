DEX_REVIEW_READY

# Generated Video Subtitle Validation

- Scope: NAS-off owner fallback validation on the Dex-generated 180.583s Korean fixture.
- Report: `output/manual_verification/latest/generated_video_subtitle_validation_20260628/validation_report.md`
- Generated final SRT: `output/manual_verification/latest/generated_video_subtitle_validation_20260628/generated_final_subtitles.srt`
- Preflight: `output/manual_verification/latest/generated_video_subtitle_validation_20260628/preflight/reference_fixture_availability.md`
- Benchmark: `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_000644/benchmark_results.md`
- Acceptance: `output/manual_verification/latest/generated_video_subtitle_validation_20260628/acceptance/reference_benchmark_acceptance.md`
- Result: pass, `accepted=true`, raw/final/reference `54/54/54`, quality/text/timing `80.153/91.676/1.437s`.
- Stability: final invalid/non-monotonic/overlap `0/0/0`, save/reopen stable `true`, global canvas max active `1`.
- Interpretation: valid owner-requested generated-fixture fallback while NAS is off; not production-wide real-footage proof for enabling STT collect cache by default.
