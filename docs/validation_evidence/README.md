# Validation Evidence

This folder is a pointer map for generated proof artifacts. Do not move large local artifacts here unless the owner explicitly asks.

Canonical locations:

- `../../output/manual_verification/latest/`
- `../../.codex_work/benchmarks/subtitle_pipeline_variants/`
- `../../test_result.md`
- `../VALIDATION.md`

Rules:

- Keep generated proof paths in reports so later agents can reproduce or inspect them.
- Treat `output/` and `.codex_work/` as local proof surfaces, not active queue storage.
- If an artifact is required for future decisions, summarize it in `test_result.md`, release notes, or `COMPLETED_ACTION_ITEMS.md`.
