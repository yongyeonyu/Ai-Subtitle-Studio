# Developer Documentation Hub

이 폴더는 `AI Subtitle Studio` 개발 문서 허브입니다. Taption식 역할 폴더 구조를 참고하되, 이 저장소의 기존 부트스트랩과 자동화 호환성을 지키기 위해 root canonical 문서는 물리적으로 이동하지 않습니다.

현재 제품 라인은 macOS Apple Silicon 우선의 Python/PyQt6 source app입니다. Native migration, Swift rewrite, QML/GPU timeline default, App Store packaging/signing/upload는 owner가 명시적으로 다시 열기 전까지 active direction이 아닙니다.

## Start Here

1. `../AGENTS.md`
2. `../ACTION_ITEMS.md`
3. `../COMPLETED_ACTION_ITEMS.md`
4. `../File_structure.txt`
5. `docs/README.md`
6. `docs/PROJECT_STATE.md`
7. `docs/FEATURE_REGISTRY.md`
8. `docs/ARCHITECTURE.md`
9. `docs/VALIDATION.md`
10. `docs/HANDOFF.md`

없는 파일은 건너뛰되, root `ACTION_ITEMS.md`와 `COMPLETED_ACTION_ITEMS.md`는 위치를 바꾸지 않습니다.

## Current Snapshot

- App checkpoint: `04.00.18` / `v04.00.18`
- Active queue: `../ACTION_ITEMS.md`
- Completed archive: `../COMPLETED_ACTION_ITEMS.md`
- Handoff: `HANDOFF.md`
- Validation: `VALIDATION.md`
- NLE plan: `../NLE_Action.md`
- App Store readiness: `APP_STORE_SUBMISSION_READINESS.md`
- Jammini mapping: `agent_communication/README.md`

## Folder Map

| Folder | Role | Canonical pointers |
| --- | --- | --- |
| `planning_queue/` | Active queue and completed-action navigation. | `../ACTION_ITEMS.md`, `../COMPLETED_ACTION_ITEMS.md`, `../waste_action_item.md`, `../lesson_n_learned.md` |
| `workflow_operations/` | Handoff, agent route, watchdog, and operational workflow docs. | `HANDOFF.md`, `agent_communication/README.md`, `../cooperation.md`, `.agents/sentinel/` |
| `project_reference/` | Product state, feature ownership, repo structure, and architecture references. | `PROJECT_STATE.md`, `FEATURE_REGISTRY.md`, `ARCHITECTURE.md`, `../README.md` |
| `quality_validation/` | Validation commands, fixture rules, and test-result pointers. | `VALIDATION.md`, `../test_case.md`, `../test_result.md` |
| `product_behavior/` | User-visible behavior, submission readiness, UI/UX guardrails, and product policy. | `APP_STORE_SUBMISSION_READINESS.md`, `../README.md`, `../AGENTS.md` |
| `nle_engine/` | NLE/source-app transition contracts, runtime projection, and Taption parity evidence. | `../NLE_Action.md`, `../COMPLETED_ACTION_ITEMS.md`, `HANDOFF.md` |
| `speech_stt/` | STT/VAD/LLM generation policy, latency gates, and cache/default evidence. | `../ACTION_ITEMS.md`, `../COMPLETED_ACTION_ITEMS.md`, `../test_result.md` |
| `validation_evidence/` | Pointers to generated local proof artifacts. | `../output/manual_verification/latest/`, `../.codex_work/benchmarks/` |
| `agent_communication/` | Taption-derived Jammini communication mapping for this repo. | `.agents/sentinel/handoffs/`, `.agents/sentinel/handoff.md` |
| `release_notes/` | Release-note navigation and retention policy. | `../RELEASE_v04.00.07.md` and newer |
| `DECISIONS/` | Durable architecture decisions. | `DECISIONS/README.md` |
| `archive_legacy/` | Historical or deprecated docs only. | Do not use for active queue or current proof. |

## Write Rules

- Keep `ACTION_ITEMS.md` active-only: remaining work, current acceptance gates, rollback rules, and short archive pointers.
- Move completed action-item summaries to `COMPLETED_ACTION_ITEMS.md`; do not duplicate completed histories back into the active queue.
- Keep detailed proof in `test_result.md`, release notes, `output/manual_verification/latest/`, or specific audit reports when future decisions need it.
- Treat docs, handoffs, and review packets as navigation and rationale. They are not behavior proof without tests, runtime artifacts, or generated evidence.
- Put new development docs in the role folder that matches their owner area, then update this hub if a new category is created.
- Do not copy Taption prompts/scripts/code into this repo. Taption is a reference project; this lane must remain labeled `AI Subtitle Studio`.
- Do not move root canonical docs unless the owner explicitly asks and the automation/Jammini compatibility risk is handled.

## Temporary Working Memory

Use `.codex_work/` for local Codex scratch output and `output/manual_verification/latest/` for generated validation artifacts. These are proof surfaces, not a place to hide active queue state.
