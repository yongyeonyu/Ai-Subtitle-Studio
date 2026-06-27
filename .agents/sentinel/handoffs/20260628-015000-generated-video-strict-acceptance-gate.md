# DEX_REVIEW_READY - Generated Video Strict Acceptance Gate

- Scope: harden generated/reference benchmark acceptance after NAS-off generated-video strict duration failure.
- Code changed:
  - `tools/evaluate_reference_benchmark_acceptance.py`
  - `tools/benchmark_subtitle_pipeline_variants.py`
  - `tests/test_reference_benchmark_acceptance.py`
  - `tests/test_benchmark_mode_profiles.py`
- Behavior:
  - Acceptance now computes a media/window duration bound and rejects final `last_end` beyond that bound.
  - Benchmark native segment summary now records final min/max segment duration and short/long segment counts for future acceptance checks.
- Proof:
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m py_compile tools/evaluate_reference_benchmark_acceptance.py tools/benchmark_subtitle_pipeline_variants.py tests/test_reference_benchmark_acceptance.py tests/test_benchmark_mode_profiles.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_reference_benchmark_acceptance.py tests/test_benchmark_mode_profiles.py -k "reference_benchmark_acceptance or native_segments_summary"` -> `7 passed, 33 deselected`.
  - Re-evaluating `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_010403/benchmark_results.json` now returns `accepted=false`, exit code `2`, reason `final_last_end_beyond_duration_bound`.
- Artifact: `output/manual_verification/latest/generated_video_strict_acceptance_gate_20260628/reference_benchmark_acceptance.md`
- Subtitle quality impact: no generation/STT/LLM/LoRA/VAD/timing/model-selection behavior changed; this is proof-gate hardening only.
- Next: investigate and fix the generated-fixture tail collapse that produces `last_end=182.032s`, 0.05s tail rows, and one 59.792s tail segment.
