# DEX_REVIEW_READY - Generated Video Strict Duration Validation Fail

- Scope: owner requested NAS-off generated video/subtitle verification.
- Legacy benchmark run: `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_010403/benchmark_results.md`
- Legacy result: `accepted=true`, raw/final/reference `54/54/54`, quality/text/timing `80.153/91.676/1.437s`, final invalid/non-monotonic/overlap `0/0/0`.
- Strict report: `output/manual_verification/latest/generated_video_strict_duration_validation_20260628/strict_duration_report.md`
- Strict result: `fail`.
- Reason: MP4 duration is `180.584s`, generated final SRT last end is `182.032s`, rows beyond media duration `17`, sub-0.3s rows `16`, long tail rows over 12s `1`.
- Interpretation: final subtitles do not overlap internally, but the generated output is not production-acceptable under media-bound subtitle validation.
- Next recommended action: add media-duration, min-duration, and long-tail gates to generated-video/reference acceptance, then investigate the tail-collapse cause before claiming generated-fixture proof as pass.
