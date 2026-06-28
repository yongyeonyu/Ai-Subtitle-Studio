#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: $0 /absolute/project/path [owner_name]" >&2
  exit 1
fi

target_root="$1"
owner_name="${2:-대표님}"
target_file="${target_root%/}/docs/workflow_operations/cooperation.md"

mkdir -p "$(dirname "$target_file")"

if [[ -e "$target_file" ]]; then
  echo "docs/workflow_operations/cooperation.md already exists: $target_file" >&2
  exit 1
fi

cat >"$target_file" <<EOF
# Codex x Antigravity Cooperation

Purpose: This file defines how Dex (Codex) and Jammini / Antigravity collaborate in this repository.

## Owner

- Primary owner name: ${owner_name}

## Read Order

1. AGENTS.md
2. docs/planning_queue/ACTION_ITEMS.md
3. docs/HANDOFF.md
4. docs/project_reference/PRODUCT_README.md
5. docs/workflow_operations/cooperation.md

## Working Split

- Dex owns final implementation, verification, and owner reporting.
- Jammini owns bounded support slices such as review, UI drafts, QA checklists, and handoff prep.
- If a task has simple, repetitive, low-risk, or narrowly reviewable support work, Dex should route that slice to Jammini first instead of keeping all support work locally.
- Jammini must return delegated work in a review-ready form and stop.

## Delegation Rules

- Dex may proactively delegate bounded, low-risk, reviewable work.
- During any non-trivial task, Dex should first look for at least one simple delegated slice such as narrow search, file reading, state summary, doc sync, shortlist drafting, or validation prep.
- If Jammini appears idle while Dex still has obvious support work, Dex should queue the next safe simple slice immediately.
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

## Example Shell Pattern

\`\`\`bash
source <(/opt/homebrew/bin/antigravity-send.sh env --shell)
ag-send-last "DEX_REVIEW_READY ..."
\`\`\`

## Bootstrap Prompt

\`\`\`text
이 프로젝트에서 Codex(덱스)와 협업합니다.
작업 전 AGENTS.md, docs/planning_queue/ACTION_ITEMS.md, docs/HANDOFF.md, docs/project_reference/PRODUCT_README.md, docs/workflow_operations/cooperation.md를 읽으세요.
덱스는 최종 구현과 검증을 담당하고, 잼민이는 bounded support work만 수행합니다.
단순하고 bounded한 일은 기본적으로 잼민이에게 먼저 위임됩니다.
delegated slice가 끝나면 DEX_REVIEW_READY로 반환하고 멈추세요.
\`\`\`
EOF

echo "Created $target_file"
