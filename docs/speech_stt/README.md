# Speech And STT

This folder points to STT/VAD/LLM generation policy, latency profiling, and cache/default evidence.

Canonical files:

- `../../ACTION_ITEMS.md#1-stt2--word-precision-generation-latency-profiling-and-accuracy-preserving-trim`
- `../../COMPLETED_ACTION_ITEMS.md#stt2--word-precision-generation-latency-profiling-and-accuracy-preserving-trim`
- `../../test_result.md`
- `../../tools/benchmark_subtitle_pipeline_variants.py`
- `../../tools/evaluate_reference_benchmark_acceptance.py`

Rules:

- Do not skip STT2, disable word precision, lower LLM/LoRA/VAD quality policy, or loosen final subtitle stability gates as a speed shortcut.
- Keep collect-cache defaults disabled until explicit owner review approves promotion.
- Use NAS HeyDealer first 180 seconds for production-facing latency/default gates when available.
