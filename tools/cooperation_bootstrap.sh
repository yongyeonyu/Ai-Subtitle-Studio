#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: $0 /absolute/project/path [owner_name]" >&2
  exit 1
fi

target_root="$1"
owner_name="${2:-대표님}"
target_file="${target_root%/}/doc/cooperation.md"

mkdir -p "$target_root" "${target_root%/}/doc"

if [[ -e "$target_file" ]]; then
  echo "doc/cooperation.md already exists: $target_file" >&2
  exit 1
fi

cat >"$target_file" <<EOF
# Codex x Antigravity Cooperation

Purpose: This file defines how Dex (Codex) and Jammini / Antigravity collaborate in this repository.

## Owner

- Primary owner name: ${owner_name}

## Read Order

1. AGENTS.md
2. doc/ACTION_ITEMS.md
3. doc/HANDOFF.md
4. doc/README.md
5. doc/cooperation.md

## Working Split

- Dex owns final implementation, verification, and owner reporting.
- Jammini owns bounded support slices such as review, UI drafts, QA checklists, and handoff prep.
- If a task has simple, repetitive, low-risk, or narrowly reviewable support work, Dex should route that slice to Jammini first instead of keeping all support work locally.
- Jammini must return delegated work in a review-ready form and stop.
- If Jammini appears idle while safe support work still exists, Dex should wake Jammini immediately instead of letting the support queue stall.

## Delegation Rules

- Dex may proactively delegate bounded, low-risk, reviewable work.
- During any non-trivial task, Dex should first look for at least one simple delegated slice such as narrow search, file reading, state summary, doc sync, shortlist drafting, or validation prep.
- If Jammini appears idle while Dex still has obvious support work, Dex should queue the next safe simple slice immediately.
- For longer tasks, Dex should run a simple watchdog loop so Jammini keeps receiving bounded support work without waiting for manual reminders.
- Jammini must not broaden the scope without explicit approval.
- Save/load format changes, rewrites, migration decisions, release actions, and semantics-changing edits stay with Dex unless explicitly reassigned.

## Return Format

Every delegated packet should begin with:

\`\`\`text
DEX_REVIEW_READY
\`\`\`

Then include:

1. Narrow scope handled
2. Files read or touched
3. Findings or draft proposal
4. Validation or proof status
5. Open risks

## Communication Route

- Chat signals such as ACK, WORKING, DONE, and BLOCKED are progress signals.
- Durable support proof should be a review-ready handoff path or artifact path.
- If this repo has `tools/jammini_watchdog.sh`, use `--status` for local route
  state and `--handoff-probe` for physical handoff-path proof before treating a
  chat ACK as reliable proof.
- Use `--handoff-list` to inspect the latest local physical handoff files.
- Prefer `--conversation-id auto` when reconnecting, so the watchdog selects an
  Antigravity conversation whose workspace matches the current project instead
  of trusting a possibly stale global `last` conversation cache.
- Dex must read Jammini output directly and classify it as accepted, accepted
  with edits, deferred, or rejected.

## Example Shell Pattern

\`\`\`bash
tools/jammini_watchdog.sh --status
tools/jammini_watchdog.sh --handoff-probe
tools/jammini_watchdog.sh --handoff-list
tools/jammini_watchdog.sh --conversation-id auto --once --dry-run
tools/jammini_watchdog.sh --conversation-id <jammini-conversation-id> --once
\`\`\`

## Bootstrap Prompt

\`\`\`text
이 프로젝트에서 Codex(덱스)와 협업합니다.
작업 전 AGENTS.md, doc/ACTION_ITEMS.md, doc/HANDOFF.md, doc/README.md, doc/cooperation.md를 읽으세요.
덱스는 최종 구현과 검증을 담당하고, 잼민이는 bounded support work만 수행합니다.
단순하고 bounded한 일은 기본적으로 잼민이에게 먼저 위임됩니다.
delegated slice가 끝나면 DEX_REVIEW_READY로 반환하고 멈추세요.
\`\`\`
EOF

echo "Created $target_file"
