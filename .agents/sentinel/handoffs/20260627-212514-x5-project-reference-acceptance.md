DEX_REVIEW_READY

# X5 Project Reference Acceptance

Scope: Restored a longer 180s X5 project-reference smoke and added an acceptance classifier so semantic media/SRT mismatches are not treated as valid reference fixtures.

Changed files:

- `tools/evaluate_reference_benchmark_acceptance.py`
- `tests/test_reference_benchmark_acceptance.py`
- `ACTION_ITEMS.md`
- `AGENTS.md`
- `docs/VALIDATION.md`
- `docs/HANDOFF.md`
- `test_result.md`
- `lesson_n_learned.md`

Artifacts:

- `output/manual_verification/latest/x5_project_reference_180s_20260627/reference_benchmark_report.md`
- `output/manual_verification/latest/x5_project_reference_180s_20260627/acceptance_front/reference_benchmark_acceptance.md`
- `output/manual_verification/latest/x5_project_reference_180s_20260627/acceptance_rejected_back/reference_benchmark_acceptance.md`
- `.codex_work/benchmarks/subtitle_pipeline_variants/20260627_211807/benchmark_results.json`
- `.codex_work/benchmarks/subtitle_pipeline_variants/20260627_211602/benchmark_results.json`

Validation:

- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m py_compile tools/evaluate_reference_benchmark_acceptance.py tests/test_reference_benchmark_acceptance.py tools/materialize_reference_srt.py tests/test_materialize_reference_srt.py tools/verify_reference_fixture_availability.py tests/test_reference_fixture_availability.py` -> pass
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_reference_benchmark_acceptance.py tests/test_materialize_reference_srt.py tests/test_reference_fixture_availability.py` -> `8 passed`
- Accepted front-reference run -> elapsed `70.383s`, raw/final/reference `43/50/67`, quality `76.387`, text `90.767`, timing MAE `1.5457s`, final invalid/non-monotonic/overlap `0/0/0`, global max active `1`
- Rejected back-reference mismatch -> quality `23.234`, text `4.756`, timing MAE `3.3362s`

Result:

- The cached X5 180s WAV is aligned with `X5_전반` project SRT, not `X5_후반`.
- Reference-fit now requires scored acceptance, not only media/SRT existence.

Next:

- Use the accepted 180s X5 project-reference fixture to evaluate a behavior-preserving High context-boundary optimization candidate, then confirm on NAS HeyDealer when mounted.
