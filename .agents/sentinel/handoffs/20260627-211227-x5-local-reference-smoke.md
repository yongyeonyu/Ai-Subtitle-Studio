DEX_REVIEW_READY

# X5 Local Reference Smoke

Scope: Restored a short-loop reference-scored X5 fixture while keeping the longer latency-trim acceptance gate intact.

Changed files:

- `tools/materialize_reference_srt.py`
- `tests/test_materialize_reference_srt.py`
- `ACTION_ITEMS.md`
- `AGENTS.md`
- `docs/VALIDATION.md`
- `docs/HANDOFF.md`
- `test_result.md`

Artifacts:

- `output/manual_verification/latest/x5_local_reference_fixture_20260627/reference_benchmark_report.md`
- `output/manual_verification/latest/x5_local_reference_fixture_20260627/x5_120_3s_180_3s_reference.srt`
- `output/manual_verification/latest/x5_local_reference_fixture_20260627/preflight/reference_fixture_availability.md`
- `.codex_work/benchmarks/subtitle_pipeline_variants/20260627_210811/benchmark_results.json`

Validation:

- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m py_compile tools/materialize_reference_srt.py tests/test_materialize_reference_srt.py tools/verify_reference_fixture_availability.py tests/test_reference_fixture_availability.py` -> pass
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_materialize_reference_srt.py tests/test_reference_fixture_availability.py` -> `5 passed`
- Local X5 preflight -> `ready_for_reference_scored_benchmark=true`, clipped reference segments `26`
- Local X5 `mode_high` benchmark -> elapsed `29.831s`, raw/final `28/23`, quality `80.914`, timing MAE `0.5608s`, final invalid/non-monotonic/overlap `0/0/0`, global max active `1`

Result:

- Short-loop X5 reference scoring is now available.
- This does not approve a broad latency trim.

Next:

- Restore or mount a longer reference-scored HeyDealer/X5 fixture before adopting STT2 collect, word precision collect, High context-boundary, worker scheduling, or cleanup latency changes.
