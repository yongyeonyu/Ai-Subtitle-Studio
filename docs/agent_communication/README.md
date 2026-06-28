# Jammini Communication Pack

This folder documents how Taption's `docs/agent_communication` Jammini pack is
adapted in AI Subtitle Studio. It is a routing and process reference, not the
physical handoff store.

## Local Identity Guard

Every delegated packet from this repo must identify the project as
`AI Subtitle Studio` and the repo root as
`/Users/u_mo_c/Downloads/ai_subtitle_studio`. Taption and Taption Encoder are
reference projects only; do not label the active lane, delegated scope,
artifact path, or proof target as Taption/Taption Encoder unless the task is an
explicit cross-project comparison.

## Taption Source Reviewed

The source pack reviewed for this repo is:

- `/Users/u_mo_c/Documents/taption/docs/agent_communication/README.md`
- `/Users/u_mo_c/Documents/taption/docs/agent_communication/cooperation.md`
- `/Users/u_mo_c/Documents/taption/docs/agent_communication/jammini_history.md`
- `/Users/u_mo_c/Documents/taption/docs/agent_communication/jammini_history_complete.md`
- `/Users/u_mo_c/Documents/taption/docs/agent_communication/scripts/`
- `/Users/u_mo_c/Documents/taption/docs/agent_communication/sentinel/agents/`
- `/Users/u_mo_c/Documents/taption/docs/agent_communication/sentinel/BRIEFING.md`
- `/Users/u_mo_c/Documents/taption/docs/agent_communication/sentinel/handoff.md`

Taption's archived handoff history is reference material only. It should not be
copied into this repo because those files describe Taption/iOS-specific work,
device proof, and old implementation decisions.

## Local Mapping

| Taption source | AI Subtitle Studio target |
| --- | --- |
| `docs/agent_communication/scripts/` | `tools/jammini_watchdog.sh`, `tools/jammini_delegate.sh`, `tools/lib/jammini_conversation_resolver.py` |
| `docs/agent_communication/sentinel/handoffs/` | `.agents/sentinel/handoffs/` |
| `docs/agent_communication/sentinel/handoff.md` | `.agents/sentinel/handoff.md` |
| `docs/agent_communication/sentinel/agents/` | `.agents/sentinel/agents/` |
| `docs/agent_communication/sentinel/BRIEFING.md` | `.agents/sentinel/BRIEFING.md` |
| `docs/agent_communication/cooperation.md` | `docs/workflow_operations/cooperation.md` |
| `runtime/watchdog/` | `.codex_work/jammini_watchdog/` |

## Applied Matrix

| Taption section | Local status | Notes |
| --- | --- | --- |
| Pack overview | Adapted | This README is the local overview and keeps the physical handoff path explicit. |
| Cooperation contract | Adapted | Canonical local file is `docs/workflow_operations/cooperation.md`. |
| Helper scripts | Adapted | Scripts live in `tools/` and keep AI Subtitle Studio read order, queue parsing, and `.agents/sentinel` paths. |
| Resolver helper | Adapted | `tools/lib/jammini_conversation_resolver.py` resolves the active Antigravity route for this repo. |
| Sentinel role cards | Adapted | AI Subtitle Studio cards live under `.agents/sentinel/agents/`. |
| Sentinel briefing | Adapted | `.agents/sentinel/BRIEFING.md` gives Jammini a compact mission, constraints, artifact index, and current owner queue without copying Taption-specific state. |
| Handoff index | Adapted | Canonical local index is `.agents/sentinel/handoff.md`; prepend only. |
| Handoff files | Adapted | Canonical local handoff files are `.agents/sentinel/handoffs/*.md`. |
| Runtime watchdog state | Adapted | Local state/logs live under `.codex_work/jammini_watchdog/`. |
| `jammini_history*.md` | Not copied | Taption-specific archive; use only as source context when explicitly needed. |
| Taption `ios-sentinel/` | Not copied | Legacy Taption/iOS-local channel; not applicable to this source-app repo. |

## Entry Points

```bash
tools/jammini_watchdog.sh --status
tools/jammini_watchdog.sh --handoff-probe
tools/jammini_delegate.sh --bootstrap --dry-run
tools/jammini_delegate.sh --role 서린 --scope "changed files" --request "false confidence risk만 검토"
```

`tools/jammini_watchdog.sh --status` is the first routing check. Chat
`ACK`/`WORKING` signals are diagnostic only; the reliable result is a physical
`DEX_REVIEW_READY` handoff file under `.agents/sentinel/handoffs/` plus an index
pointer prepended to `.agents/sentinel/handoff.md`.

## Applied Rules

- Dex keeps final implementation, verification, and owner-facing reporting.
- Jammini handles bounded support: narrow search, file reads, review drafts,
  QA checklists, validation prep, and handoff drafts.
- For non-trivial owner work, default to delegate-first when a safe bounded
  support slice exists; when there are multiple review/prep tracks, prefer one
  batched queue packet over many fragmented packets.
- 한결, 서린, and 유진 role cards live under `.agents/sentinel/agents/`.
- `.agents/sentinel/BRIEFING.md` is the compact current-state entrypoint for
  Jammini. Keep it light, source-app specific, and free of Taption/iOS runtime
  claims.
- External workflow packs are source material only. Adapt clean-room workflow
  principles; do not import license-bound code, long prompt blocks, or hidden
  provider claims.
- For NLE work, split review packets by owner lane and require a physical
  handoff before Dex treats the result as evidence.
- Unknown-cause regressions must be reproduced before implementation unless the
  owner explicitly asks for planning only.

## Verification

Use these checks after changing this communication layer:

```bash
bash -n tools/jammini_watchdog.sh tools/jammini_delegate.sh
tools/jammini_watchdog.sh --status
tools/jammini_delegate.sh --bootstrap --dry-run
```

`--status` proves only route resolution. `--bootstrap --dry-run` proves prompt
rendering only. A real delegated result is trusted only after Dex reads the
physical `DEX_REVIEW_READY` handoff file and classifies it as accept, revise,
defer, or reject.

## Maintenance Rules

- Do not move physical handoffs into `docs/agent_communication/`.
- Do not let `.agents/sentinel/BRIEFING.md` become a second action queue; it is
  a compact orientation file that points back to `docs/planning_queue/ACTION_ITEMS.md` and
  `docs/HANDOFF.md`.
- Do not copy Taption's old history or old iOS-local sentinel channel into this
  repo.
- Keep helper scripts under `tools/` so shell entrypoints match `AGENTS.md`.
- Keep the role cards short and source-app specific.
- If the handoff path, helper command, or role-card location changes, update
  `AGENTS.md`, `docs/README.md`, `docs/workflow_operations/cooperation.md`, and this file in the same
  task.
