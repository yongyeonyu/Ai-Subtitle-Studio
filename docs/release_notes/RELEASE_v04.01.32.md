# RELEASE v04.01.32

Date: 2026-06-29 KST

Release app version: `04.01.32`
Project schema version: `04.01.32`

## Summary

`v04.01.32` is a documentation-consolidation, code-review, release, and
new-chat bootstrap checkpoint.

It preserves the `v04.01.31` source-app NLE persistence behavior, App Store
blockers, STT/cache defaults, and UI/UX behavior. The release only bumps the
app/project schema version, records the docs consolidation, refreshes
AGENTS/HANDOFF for the next chat, and keeps Jammini physical handoff evidence
tracked.

This is not full QA, App Store package/signing/upload/submission proof, owner
metadata completion, STT/cache default promotion, UI/UX change, or NLE runtime
behavior change.

## Changes

- `core/runtime/config.py` now reports `APP_VERSION = "04.01.32"`.
- `core/project/project_format.py` now marks newly saved project payloads as
  schema version `04.01.32`.
- Development docs remain consolidated under `docs/`, with root
  development-documentation limited to protected `AGENTS.md`.
- The stale local duplicate `doc/ACTION_ITEMS.md` queue remains removed; the
  active queue is `docs/planning_queue/ACTION_ITEMS.md`.
- `AGENTS.md`, `docs/PROJECT_STATE.md`, `docs/HANDOFF.md`,
  `docs/README.md`, `docs/planning_queue/ACTION_ITEMS.md`,
  `docs/planning_queue/COMPLETED_ACTION_ITEMS.md`, and
  `docs/quality_validation/test_result.md` are refreshed for the new-chat
  continuation state.
- A fresh Jammini physical route probe is recorded at
  `.agents/sentinel/handoffs/20260629-214917-watchdog-handoff-probe.md`.

## Review Notes

- Review scope: latest documentation consolidation commit and current release
  bootstrap/version state.
- No runtime-code defect requiring app behavior changes was found.
- Fixes applied during review:
  - refreshed stale AGENTS current-state pointers,
  - removed a duplicated current guard line from the new-chat summary,
  - aligned version/schema/release pointers to `04.01.32`,
  - preserved `.agents/sentinel/` as the physical Jammini handoff store instead
    of moving it under `docs/`.

## Validation

- `./venv/bin/python -m py_compile core/runtime/config.py core/project/project_format.py`
  -> pass.
- `PYTHONDONTWRITEBYTECODE=1 QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q -p no:cacheprovider tests/test_macos_bundle_runtime_paths.py tests/test_project_context.py tests/test_cp03_cp04_status_ui.py -k "schema or version or project_file_roundtrip or status"`
  -> `66 passed, 84 deselected`.
- Documentation consolidation presence check -> `docs_consolidation_presence=pass`.
- Tracked development `.md` path check, excluding `.agents`, `.codex_work`,
  `_backup_mac_migration`, `checkpoints`, and `output` -> only `./AGENTS.md`
  remains outside `docs/`.
- Direct version assertion -> `APP_VERSION=04.01.32`,
  `PROJECT_SCHEMA_VERSION=04.01.32`.
- `git diff --check -- .` -> pass.

## Coordination

Jammini communication is available again through physical handoff files. The
latest probe starts with `DEX_REVIEW_READY` and includes
`PROBE_ID=20260629-214917`.
