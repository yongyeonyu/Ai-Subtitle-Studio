# Developer Documentation Hub

This folder is the canonical documentation home for `AI Subtitle Studio`.
The repository root keeps only `AGENTS.md` as a development-documentation file;
all active plans, release notes, validation notes, reference maps, and workflow
docs live under `docs/`.

The current product line remains the macOS Apple Silicon first Python/PyQt6
source app. Native migration, Swift rewrite, QML/GPU timeline defaults, and DMG
release work stay opt-in unless the owner explicitly reopens that scope. Mac
App Store packaging/signing/upload/metadata execution has owner approval for the
G0 lane, but signed package, validation, upload, and metadata proof remain open.

## Start Here

1. `../AGENTS.md`
2. `planning_queue/ACTION_ITEMS.md`
3. `planning_queue/COMPLETED_ACTION_ITEMS.md`
4. `PROJECT_STATE.md`
5. `FEATURE_REGISTRY.md`
6. `ARCHITECTURE.md`
7. `VALIDATION.md`
8. `HANDOFF.md`
9. `project_reference/PRODUCT_README.md`
10. `quality_validation/test_case.md`
11. `quality_validation/test_result.md`
12. Latest `release_notes/RELEASE_v*.md`

## Current Snapshot

- App checkpoint: `04.01.29` / `v04.01.29`
- Active queue: `planning_queue/ACTION_ITEMS.md`
- Completed archive: `planning_queue/COMPLETED_ACTION_ITEMS.md`
- Handoff: `HANDOFF.md`
- Validation: `VALIDATION.md`
- Product README: `project_reference/PRODUCT_README.md`
- NLE plan: `nle_engine/NLE_Action.md`
- App Store readiness: `APP_STORE_SUBMISSION_READINESS.md`
- Jammini mapping: `agent_communication/README.md`

## Folder Map

| Folder | Role | Canonical pointers |
| --- | --- | --- |
| `planning_queue/` | Active queue, completed-action archive, rejected ideas, and lessons. | `ACTION_ITEMS.md`, `COMPLETED_ACTION_ITEMS.md`, `waste_action_item.md`, `lesson_n_learned.md`, `idea.md` |
| `workflow_operations/` | Handoff, Jammini cooperation, Antigravity role docs, watchdog and operational workflow. | `cooperation.md`, `anti_agents.md`, `../HANDOFF.md`, `../agent_communication/README.md`, `../../.agents/sentinel/` |
| `project_reference/` | Product README, repo structure, code map, owner maps, and stable project references. | `PRODUCT_README.md`, `File_structure.txt`, `CODEMAP.md`, `LONG_FILE_OWNERSHIP_MAP.md`, `SUBTITLE_GENERATION_DOMAIN_MAP.md` |
| `quality_validation/` | Validation commands, fixture rules, benchmark plans, and current result records. | `test_case.md`, `test_result.md`, `NAS_SUBTITLE_BENCHMARK_50_PLAN.md`, `NAS_SUBTITLE_BENCHMARK_RECORDING_CONTEXT.md`, `../VALIDATION.md` |
| `product_behavior/` | User-visible behavior, submission readiness, UI/UX guardrails, and product policy. | `../APP_STORE_SUBMISSION_READINESS.md`, `../PROJECT_STATE.md`, `../../AGENTS.md` |
| `nle_engine/` | NLE/source-app transition contracts, runtime projection, Taption parity evidence, and NLE gates. | `NLE_Action.md`, `../planning_queue/COMPLETED_ACTION_ITEMS.md`, `../HANDOFF.md` |
| `speech_stt/` | STT/VAD/LLM generation policy, latency gates, and cache/default evidence. | `../planning_queue/ACTION_ITEMS.md`, `../planning_queue/COMPLETED_ACTION_ITEMS.md`, `../quality_validation/test_result.md` |
| `validation_evidence/` | Pointers to generated local proof artifacts. | `../../output/manual_verification/latest/`, `../../.codex_work/benchmarks/` |
| `agent_communication/` | Taption-derived Jammini communication mapping for this repo. | `../../.agents/sentinel/handoffs/`, `../../.agents/sentinel/handoff.md` |
| `release_notes/` | Release-note files and retention policy. | `RELEASE_v04.00.07.md` and newer |
| `DECISIONS/` | Durable architecture decisions. | `DECISIONS/README.md` |
| `archive_legacy/` | Historical or deprecated docs only. | Do not use for active queue or current proof. |

## Write Rules

- Keep `planning_queue/ACTION_ITEMS.md` active-only: remaining work, current acceptance gates, rollback rules, and short archive pointers.
- Move completed action-item summaries to `planning_queue/COMPLETED_ACTION_ITEMS.md`; do not duplicate completed histories back into the active queue.
- Keep detailed proof in `quality_validation/test_result.md`, release notes, `output/manual_verification/latest/`, or specific audit reports when future decisions need it.
- Treat docs, handoffs, and review packets as navigation and rationale. They are not behavior proof without tests, runtime artifacts, or generated evidence.
- Put new development docs in the role folder that matches their owner area, then update this hub if a new category is created.
- Do not copy Taption prompts/scripts/code into this repo. Taption is a reference project; this lane must remain labeled `AI Subtitle Studio`.
- Do not add new root development docs. `AGENTS.md` is the only root dev-doc exception.

## Archive Policy

- Keep release notes from `release_notes/RELEASE_v04.00.07.md` onward.
- Move stale, superseded, or historical documents to `archive_legacy/` only when they are not active gates, not current proof, and not needed by scripts/tests.
- Do not archive `.agents/sentinel/` handoff files; those are physical handoff evidence.
- Do not delete old release notes or validation records unless the owner explicitly approves a retention change.

## Temporary Working Memory

Use `.codex_work/` for local Codex scratch output and
`output/manual_verification/latest/` for generated validation artifacts. These
are proof surfaces, not a place to hide active queue state.
