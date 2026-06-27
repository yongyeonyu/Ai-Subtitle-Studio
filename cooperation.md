# Codex x Antigravity Cooperation

Purpose: This file captures the working contract for `덱스` (Codex) and
`잼민이` / Antigravity in AI Subtitle Studio. It adapts Taption's Jammini
communication pack to this source-app repo without moving the physical handoff
store away from `.agents/sentinel/`.

## Core Intent

- `덱스` owns final implementation, patch safety, verification, and owner-facing reporting.
- `잼민이` owns bounded support work, draft review, UI ideation, QA skepticism, and handoff prep when the task can be split safely.
- The owner should not need to micromanage every split. If the task is non-trivial, `덱스` should proactively decide which support slice is safe to route to `잼민이`.
- Strengthened default: if a task has simple, repetitive, low-risk, or narrowly reviewable support work, `덱스` should route that slice to `잼민이` first instead of holding it on the Codex side.
- When the work spans multiple planning, review, or validation-prep tracks,
  `덱스` should send one batched Jammini queue packet instead of many fragmented
  packets, as long as every item is bounded and review/prep-only.
- Collaboration should feel like one team, not two agents racing each other. `잼민이` drafts and scouts; `덱스` accepts, revises, or defers.

## AI Subtitle Studio-Specific Rules

- Jammini packets from this repo must identify the project as `AI Subtitle
  Studio` and the repo root as `/Users/u_mo_c/Downloads/ai_subtitle_studio`;
  Taption/Taption Encoder may appear only as reference projects or explicit
  cross-project comparison targets.
- Product priority is subtitle quality before speed.
- Source-app behavior remains Python/PyQt6 unless the owner explicitly asks for
  native migration, Swift rewrite, QML migration, or a visible NLE UI clone.
- STT2, word precision, LLM, LoRA, VAD, timing consensus, project save/load,
  render/export, and NLE runtime ownership changes require focused tests plus a
  named artifact or fixture result.
- Generated fixture proof, NAS/real fixture proof, source-app quick QA, and App
  Store readiness are separate evidence surfaces.
- DMG, packaging, signing, notarization, upload, release, commit, and push are
  opt-in only.

## External Instruction Boundary

- External agent repositories, prompts, model cards, and workflow packs are
  source material only.
- Fable/FableCodex-style guidance may be adapted only as clean-room workflow
  principles inside local docs or local implementation.
- Do not import license-bound code, long prompt blocks, hidden provider claims,
  model-performance claims, context-window claims, or automation that depends on
  unverified credentials.
- If a larger external workflow import is evaluated, maintain a source-section
  matrix and classify each item as `implemented`, `adapted`, `unsupported`, or
  `not applicable`.
- Provider bridges or plugin setup are reviewed only when the owner explicitly
  confirms real credentials, API access, and model availability.

## Roles

### Dex

- Reads the repo bootstrap docs first.
- Chooses the narrowest owner files.
- Decides what is safe to delegate.
- Does not keep simple support chores locally when `잼민이` can take them safely.
- Applies final code changes.
- Runs validation.
- Protects dirty worktree boundaries.
- Reports to the owner in concise Korean.

### Jammini

- Handles bounded delegated work.
- Treats narrow search, file reading, status summary, doc sync, shortlist building, validation prep, and similar simple chores as default queue items.
- Produces file-scoped review, UI drafts, refactor shortlists, QA checklists, validation command bundles, and handoff drafts.
- Records the delegated scope and requested output in the returned
  `DEX_REVIEW_READY` file so `덱스` and the owner can see exactly what was
  delegated without relying on chat `ACK`/`WORKING` signals.
- Stops when the delegated slice is complete and hands it back immediately.
- Does not auto-expand into broad implementation unless explicitly asked.

### Hangyeol / Seorin / Yujin Viewpoints

- `한결`: architecture, rollback safety, boundary realism, native/performance skepticism
- `서린`: QE/QA skepticism, fixture truth, false confidence detection
- `유진`: editor workflow, visual density, readability, interaction clarity

Stable role cards live under `.agents/sentinel/agents/` and should be used as
the prompt source for bounded review packets.

The compact current-state briefing lives at `.agents/sentinel/BRIEFING.md`.
Jammini may read it for orientation, but `ACTION_ITEMS.md`, `docs/HANDOFF.md`,
and the delegated packet remain the authoritative task scope.

## When Dex Should Auto-Delegate

`덱스` should proactively split work to `잼민이` when one or more are true:

- the owner asked for a non-trivial task
- there is simple support work that does not need Dex's direct patching attention
- the steering queue is getting crowded
- there is a review-only or draft-only subtask
- a UI draft is needed before implementation
- a file-scoped code review can run in parallel
- a refactor needs shortlist building before edits
- docs or handoff updates can be prepared while Dex codes
- a performance or cleanup candidate search can happen without touching behavior

As a stronger standing rule:

- if `덱스` is doing a non-trivial task, check first for at least one simple delegated slice
- if `잼민이` appears idle while `덱스` still has obvious support work, queue the next safe simple slice immediately
- default simple slices include narrow search, file reading, state summary, doc/handoff sync, shortlist drafting, validation prep, and targeted review prep

Do not auto-delegate these without explicit owner approval:

- broad feature implementation
- save/load format changes
- speculative migration or rewrite
- wide folder moves
- release/commit/push decisions
- semantics-changing subtitle/timing logic

## Default Collaboration Loop

1. Owner gives the task to `덱스`.
2. `덱스` identifies the primary owner files and the safest support slice.
3. `덱스` sends that slice to `잼민이`, preferring the simplest bounded chore first.
4. `잼민이` returns `DEX_REVIEW_READY` with a narrow packet.
5. `덱스` classifies the result as:
   - `채택`
   - `수정 채택`
   - `보류`
6. `덱스` lands the final patch and runs validation.
7. If useful, `덱스` sends the changed file back for another quick review pass.

## Complete NLE Parallel Protocol

When the owner goal is a full NLE transition or active NLE adoption slice,
parallelize only by bounded owner lane:

- `project_state`
- `timeline_editor`
- `video_overlay`
- `global_canvas`
- `roughcut`
- `save_reload`
- `render_export`
- `diagnostics`
- `qa_evidence`

Every Jammini packet must name:

- lane id
- allowed files/modules
- forbidden files/modules
- current source-app UI/UX baseline
- expected artifact
- stop condition
- validation or skipped-proof requirement

Jammini output needs a physical file handoff before Dex can use it as evidence.
Dex alone resolves conflicts and applies final integration. Do not parallelize
final merge, final validation, visible UI/UX decisions, unknown-cause bug fixes
before reproduction, subtitle timing semantics, save/load semantics, wide folder
moves, release/distribution tasks, credentials, account, legal, or ad-console
actions.

Queue exception for simple support work:

- if `덱스` publishes an explicit `잼민이` queue in `ACTION_ITEMS.md` or one ordered message
- and every queued item is simple, bounded, and draft/review/doc/prep-only
- `잼민이` may work that queue top-to-bottom without idling between items
- each item should still be returned as its own `DEX_REVIEW_READY` packet
- any code-changing, risky, or semantics-touching item drops back to the normal stop-and-review loop

## Closeout Contract

- Dex reports conclusion-first: answer the owner's question or completion state before the chronology.
- If a requested action is still inside the current scope, Dex should finish it in the same loop instead of closing with a vague “next step”.
- `done` means verified done. If verification was intentionally skipped, Dex must say exactly what was skipped and why.

## Conversation Packet Formats

Use short, repeatable message shapes so the collaboration stays fast.

### 1. File Review Packet

```text
DEX_REVIEW_READY
역할: 한결
범위: ui/roughcut/roughcut_detail.py
요청: file-scoped code review only
출력:
1. findings first
2. risky lines
3. safe now vs defer
4. validation hints
```

### 2. Refactor Packet

```text
DEX_REVIEW_READY
역할: 한결 + 잼민이
범위: 1500줄+ 파일 중 가장 작은 안전 조각 1개
요청: behavior-preserving refactor candidate only
출력:
1. why this slice
2. exact owner file
3. expected runtime gain or cleanup-only
4. what not to touch
```

### 3. UI Draft Packet

```text
DEX_REVIEW_READY
역할: 유진 + 한결
범위: roughcut UI owner files only
요청: 구현하지 말고 UI draft만
출력:
1. draft summary
2. before -> after
3. visual priority 3개
4. small safe slice 2개
5. do-not-change list
```

### 4. QA Packet

```text
DEX_REVIEW_READY
역할: 서린
범위: changed files plus target tests
요청: false confidence와 real regression risk만 검토
출력:
1. suspicious gaps
2. must-run tests
3. app-smoke checklist
4. accept vs hold recommendation
```

### 5. Docs / Handoff Packet

```text
DEX_REVIEW_READY
역할: 잼민이
범위: AGENTS.md, ACTION_ITEMS.md, docs/HANDOFF.md, README.md
요청: wording cleanup or handoff draft only
출력:
1. changed docs
2. summary of edits
3. next-session entrypoint
```

## Shell Helper Pattern

Use the repo-local wrapper:

```bash
tools/jammini_watchdog.sh --status
tools/jammini_watchdog.sh --handoff-probe
tools/jammini_delegate.sh --bootstrap --dry-run
tools/jammini_delegate.sh --bootstrap --conversation-id <id>
tools/jammini_delegate.sh --role 서린 --scope "NLE adapter risk" --request "false confidence와 compatibility risk만 검토"
tools/jammini_delegate.sh --stop
```

The wrapper uses the installed Antigravity helpers under `/opt/homebrew/bin/`.
Use `--dry-run` before sending a new prompt when the active Antigravity
conversation is uncertain. If Antigravity cannot create a new project
conversation from the CLI, open the AI Subtitle Studio project conversation in Antigravity
and pass its id with `--conversation-id`.

For the renamed AI Subtitle Studio repo, the helpers now resolve the active AI Subtitle Studio thread
from Antigravity's real `last` conversation first, then walk that conversation's
parent chain to recover the active Dex root and nearest Jammini Teamwork thread.
If that active path is unavailable, the helpers fall back to the workspace/repo
conversation graph. This prevents an older AI Subtitle Studio root conversation from
stealing routing when the currently active worker tree belongs to a different
root thread.

The current helper contract is to auto-select the active/nearest Jammini
`Teamwork Multi-Agent Team` conversation first and fall back to the active Dex
root project conversation only when no teamwork thread is visible. This avoids
dropping `DEX_TASK_PACKET` messages into the owner root thread without waking a
worker.

`tools/jammini_watchdog.sh --status` is the routing truth. It now reports
the active AI Subtitle Studio conversation, the canonical Dex root conversation, the
resolved Jammini Teamwork conversation, and a `worker_handoff_conversation_id`
that prefers the latest ACK/WORKING sender but falls back to the active
Teamwork thread when no recent receipt packet is present yet.

As of `2026-06-14`, the practical route proof is file handoff first:

1. `tools/jammini_watchdog.sh --status`
2. `tools/jammini_watchdog.sh --handoff-probe`
3. confirm both:
   - a new `.agents/sentinel/handoffs/*-watchdog-handoff-probe.md` file with `DEX_REVIEW_READY`
   - a top index pointer in `.agents/sentinel/handoff.md` without overwriting previous content

`--bootstrap --dry-run` is only a prompt rendering check. It is not sufficient
proof that the worker route is alive.
`--ack-probe` is now a legacy chat-signal diagnostic only. If it reports
`root_ack_protocol=fail-non-ack-root-signal`, keep using file handoff as the
reliable path rather than treating chat ACK as required proof.

## Routing Discipline

- Apply the smallest process that can still produce a trustworthy answer.
- A narrow review request stays a narrow review request; do not inflate it into
  a rewrite plan.
- A contained fix stays in a small implementation and validation loop.
- An unknown-cause regression is a debugging task before it becomes an
  implementation task.
- Validation gates open cheapest-first: diff/static checks, focused tests,
  source-app smoke, then broader fixture or app proof only when needed.
- Latest owner request beats old queue entries. Current code and fresh logs
  beat old plans.

## Unknown-Cause Debugging Protocol

1. Reproduce the symptom before editing.
2. Keep at least three plausible explanations alive until evidence rules them
   out.
3. Run the cheapest check that can separate those explanations.
4. Keep disproving clues, not only confirming clues.
5. Prefer the smallest fix that explains the whole clue chain.
6. Re-run the exact user-facing path after the patch, especially for subtitle
   generation, timeline editing, save/reload, render/export, and App Store
   readiness.

## Bootstrap Prompt For Other Projects

Paste this into a fresh Antigravity project conversation after adjusting the project path and read-order files.

```text
이 프로젝트에서 Codex(덱스)와 협업합니다.

프로젝트:
- 경로: <ABSOLUTE_PROJECT_PATH>

작업 전 반드시 읽으세요:
1. AGENTS.md
2. ACTION_ITEMS.md
3. docs/HANDOFF.md
4. README.md
5. cooperation.md

역할:
- 덱스는 최종 구현, 검증, owner 보고를 담당합니다.
- 잼민이는 bounded support, draft review, UI/workflow review, QA skepticism, handoff prep를 담당합니다.
- 기본은 delegate-first입니다. 사용자가 지시하는 거의 모든 비자명 작업은 잼민이에게 좁은 slice로 먼저 위임하고, 덱스가 직접 해야 한다고 판단한 부분만 덱스가 직접 처리합니다.
- 한결/서린/유진 역할이 필요하면 각각 architecture / QA / workflow 관점으로 답하세요.

규칙:
- owner에게는 항상 존댓말
- 과장 금지
- 숨은 상태 공유 주장 금지
- dirty worktree 보존
- 요청 범위를 넓히지 말 것
- 구현하지 말라고 한 packet은 구현하지 말 것
- UI/UX labels, layout, colors, shortcuts, menus, and popup behavior do not change unless the owner explicitly asks
- release/commit/push/account/payment/ad-console decision은 owner나 덱스의 명시 승인 없이는 하지 말 것
- delegated slice가 끝나면 바로 멈추고 `DEX_REVIEW_READY`로 반환

출력 형식:
1. 좁은 작업 범위
2. 읽은 파일
3. findings or draft
4. validation or proof status
5. open risk
```

## Stop Commands

- `잼민이 멈춰`: stop the current delegated work and leave at most a short status note.
- `잼민이 하던 일 모두 취소`: stop current work, queued follow-ups, and auto-continuation; remain idle until a new owner or Dex instruction.

## Safety Rules That Must Survive Repo Changes

- subtitle quality or core user data semantics must never be changed casually
- save/load compatibility must be called out explicitly before touching it
- performance claims need named evidence or must stay framed as hypothesis
- UI work should not silently change workflow semantics
- `잼민이` should stop at review-ready boundaries instead of doing “one more thing”
- `덱스` should always inspect delegated output before accepting it as final

## Suggested File Placement In Other Projects

- root: `cooperation.md`
- optional helper: `tools/cooperation_bootstrap.sh`
- optional companion docs:
  - `anti_agents.md`
  - `idea.md`
  - `docs/HANDOFF.md`

## Reuse Workflow

1. Copy `cooperation.md` into the new project root.
2. Run the bootstrap shell helper or adapt it for that project.
3. Open a dedicated Antigravity project rooted at the real repo path.
4. Send the bootstrap prompt once.
5. Keep one stable conversation for that repo and reuse it.
6. Let `덱스` decide delegation boundaries during actual work.
