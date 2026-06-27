DEX_REVIEW_READY

# High Context Decision Diagnostics

- Owner task: use the NAS HeyDealer 3-minute video for the next latency test and apply the more accurate testing method.
- Scope: behavior-preserving diagnostics only.
- Changed code:
  - `core/engine/subtitle_context_refiner.py`
  - `tools/benchmark_subtitle_pipeline_variants.py`
  - `tools/verify_full_media_pipeline.py`
  - `tests/test_subtitle_context_refiner.py`
  - `tests/test_verify_full_media_pipeline.py`
- Report: `output/manual_verification/latest/high_context_decision_diagnostics_20260627/decision_diagnostics_report.md`
- Benchmark: `.codex_work/benchmarks/subtitle_pipeline_variants/20260627_224543/benchmark_results.md`
- Acceptance: `output/manual_verification/latest/high_context_decision_diagnostics_20260627/acceptance/reference_benchmark_acceptance.md`

## Result

- NAS HeyDealer first 180s `mode_high`: pass.
- Elapsed/raw/final/reference: `59.559s` / `58/56/89`.
- Quality/text/timing MAE: `81.335` / `94.267` / `1.5958s`.
- Final invalid/non-monotonic/overlap: `0/0/0`.
- Global max active: `1`.
- Acceptance: `accepted=true`.

## High Context Decision Detail

- Candidate/skipped/call/failed/changed/max pairs: `2/55/2/0/0/8`.
- Keep/move/merge/invalid decisions: `2/0/0/0`.
- Correction requested/applied: `0/0`.

## Dex Review Note

- This is not a runtime trim. It makes the next trim candidate measurable.
- Same-fixture evidence now points away from batching and broad High context-boundary skipping. A future High context candidate should be a strict decision-equivalent no-change gate, or the next slice should inspect STT collect scheduling/cache reuse.
