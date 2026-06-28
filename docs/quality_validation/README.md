# Quality Validation

This folder owns validation expectations, fixture rules, and current result
records.

Canonical files:

- `test_case.md`
- `test_result.md`
- `NAS_SUBTITLE_BENCHMARK_50_PLAN.md`
- `NAS_SUBTITLE_BENCHMARK_RECORDING_CONTEXT.md`
- `../VALIDATION.md`
- `../../output/manual_verification/latest/`

Rules:

- Separate focused tests, one-command QA, generated artifacts, and real-media proof in reports.
- Do not claim App Store readiness from source-app pytest or QA alone.
- Do not approve STT/default-cache changes from generated or short-loop evidence when the active gate requires NAS HeyDealer first 180 seconds.
- Keep new validation summaries here or in `../../output/manual_verification/latest/`; do not recreate root validation docs.
