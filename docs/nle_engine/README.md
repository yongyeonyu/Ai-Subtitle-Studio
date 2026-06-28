# NLE Engine

This folder owns the source-app NLE plan, Taption-derived subtitle editing
contracts, runtime projection boundaries, and NLE validation pointers.

Canonical files:

- `NLE_Action.md`
- `../planning_queue/COMPLETED_ACTION_ITEMS.md#source-app-nle-runtime-adoption-and-migration-status`
- `../HANDOFF.md`
- `../quality_validation/test_result.md`

Rules:

- Completed NLE slice histories belong in `../planning_queue/COMPLETED_ACTION_ITEMS.md`, not the active queue.
- Persisted NLE project fields remain gated until a fresh compatibility gate and owner approval exist.
- Do not reopen native migration, Swift rewrite, QML/GPU timeline defaults, or per-pixel NLE writes without explicit owner scope.
