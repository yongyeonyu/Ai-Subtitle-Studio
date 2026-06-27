# DEX_REVIEW_READY - Generated Video Tail Collapse Fix

- Scope: fix NAS-off generated-fixture final subtitle tail collapse after strict duration validation failed.
- Root cause: `vad_stt_timing_consensus` accepted a broad full-file VAD span `[0.0, 180.912]` as an STT1/VAD-only union source for later STT1 rows.
- Code changed:
  - `core/subtitle_quality/vad_alignment_checker.py`
  - `tests/test_subtitle_quality_models.py`
- Behavior:
  - STT1/VAD-only union now requires VAD and STT1 spans to be similar.
  - Existing close VAD/STT1 union behavior remains covered.
- Proof:
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m py_compile core/subtitle_quality/vad_alignment_checker.py tools/evaluate_reference_benchmark_acceptance.py tools/benchmark_subtitle_pipeline_variants.py tests/test_subtitle_quality_models.py tests/test_reference_benchmark_acceptance.py tests/test_benchmark_mode_profiles.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_subtitle_quality_models.py -k "vad_voice_start_priority or vad_stt_timing_consensus"` -> `10 passed, 8 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_reference_benchmark_acceptance.py tests/test_benchmark_mode_profiles.py -k "reference_benchmark_acceptance or native_segments_summary"` -> `7 passed, 33 deselected`.
  - Fixed benchmark `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_013224/benchmark_results.json` -> strict acceptance `accepted=true`.
- Fixed metrics: elapsed `44.307s`, raw/final/reference `54/54/54`, quality/text/timing `93.411/91.676/0.1391s`, final invalid/non-monotonic/overlap `0/0/0`, final last end/duration bound `180.12/180.584`, short/long `0/0`.
- Artifact: `output/manual_verification/latest/generated_video_tail_collapse_fix_20260628/tail_collapse_fix_report.md`
- Remaining risk: generated-fixture proof only while NAS is off; keep STT collect caches default-off until representative real-footage backfill passes.
