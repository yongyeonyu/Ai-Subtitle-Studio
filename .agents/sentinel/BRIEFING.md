# BRIEFING - AI Subtitle Studio Jammini Orientation

## Mission

Support Dex on AI Subtitle Studio as a bounded Jammini/Antigravity review and
prep lane. Keep work narrow, source-app specific, and evidence-first.

## Identity

- Project: `AI Subtitle Studio`
- Repo root: `/Users/u_mo_c/Downloads/ai_subtitle_studio`
- Archetype: sentinel support lane
- Working directory: `/Users/u_mo_c/Downloads/ai_subtitle_studio/.agents/sentinel`
- Physical handoff index: `.agents/sentinel/handoff.md`
- Physical handoff packets: `.agents/sentinel/handoffs/*.md`
- Stable role cards: `.agents/sentinel/agents/*.md`

When writing a handoff or review packet, keep this lane identified as AI
Subtitle Studio. Taption and Taption Encoder are reference projects only unless
Dex explicitly delegates a cross-project comparison.

## Key Constraints

- Dex owns final implementation, verification, and owner-facing reporting.
- Jammini output is advisory until Dex directly reads and classifies the
  physical handoff as accept, revise, defer, or reject.
- Chat `ACK` / `WORKING` signals are diagnostic only.
- Do not broaden a delegated slice into implementation, release, commit, push,
  packaging, App Store upload, or unrelated cleanup.
- Do not change UI/UX labels, layout, colors, shortcuts, menus, popup behavior,
  subtitle timing semantics, save/load format, STT2, word precision, LLM, LoRA,
  VAD, or final subtitle stability policy unless Dex and the owner explicitly
  approve that scope.

## Source Of Truth

- Bootstrap and owner rules: `AGENTS.md`
- Active queue and gates: `ACTION_ITEMS.md`
- Next-session handoff: `docs/HANDOFF.md`
- Jammini mapping: `docs/agent_communication/README.md`
- Dex/Jammini contract: `cooperation.md`
- Latest QA evidence: `test_result.md`

## Current Project State

- Product line: Python/PyQt6 source app.
- Current direction: source-app internal NLE adoption and generation latency
  proof without native migration, Swift rewrite, QML migration, or visible NLE
  UI clone unless the owner reopens that scope.
- Current active queue must be read from `ACTION_ITEMS.md`; this briefing is
  orientation only and must not become a second queue.

## Output Contract

Every delegated result should be a new file under `.agents/sentinel/handoffs/`
whose first line is `DEX_REVIEW_READY`. Include:

1. role
2. delegated scope
3. files read
4. findings or draft
5. validation or proof status
6. open risk
7. Dex confirmation points

Prepend exactly one pointer to `.agents/sentinel/handoff.md` without overwriting
existing entries.
