DEX_REVIEW_READY

# Macro Proofread Response Cache Synthetic Pass

- Scope: Implemented exact macro proofread LLM response replay cache for repeat generation latency. Cache hit skips only the external provider call; candidate-lock/verifier/Deep rerank still run on replayed chunks.
- Files: `core/engine/subtitle_macro_chunks.py`, `core/engine/subtitle_engine.py`, `core/runtime/config.py`, `tools/benchmark_subtitle_pipeline_variants.py`, `tests/test_subtitle_engine_settings.py`, `ACTION_ITEMS.md`, `test_result.md`, `docs/HANDOFF.md`.
- Verification: focused py_compile passed; focused pytest `6 passed, 112 deselected`; generated 180.583s fixture first/second High-mode benchmarks both accepted by `tools/evaluate_reference_benchmark_acceptance.py`.
- Evidence: `output/manual_verification/latest/macro_response_cache_20260627/macro_response_cache_report.md`; first run `20260627_233240` proofread `30.731199s`; second run `20260627_233531` proofread `0.545337s`, macro cache hit/write/provider groups `1/0/0`, final invalid/non-monotonic/overlap `0/0/0`, global max active `1`.
- Remaining risk: synthetic fixture proof only. Backfill on NAS HeyDealer or another representative owner fixture before claiming production-wide speed. Latest cache-hit run still points to STT1/STT2/word collect cost.
