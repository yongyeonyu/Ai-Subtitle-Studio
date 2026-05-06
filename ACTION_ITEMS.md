<!--
Document-Version: 03.22.00
Phase: MODE_AUTOPILOT_RELEASED
Last-Updated: 2026-05-06
Updated-By: Codex
Purpose: Remaining work queue only.
-->
# ACTION_ITEMS.md - Remaining Work Queue

## Queue Policy

- This file contains only unfinished or parked work.
- Completed items must be removed instead of kept as history.
- Release history belongs in `RELEASE_v*.md`.
- Bootstrap and operating rules belong in `AGENTS.md`.
- Product overview belongs in `README.md`.
- Actual file tree belongs in `File_structure.txt`.

## Metadata

```yaml
app_version: "03.22.00"
document_version: "03.22.00"
phase: "MODE_AUTOPILOT_RELEASED"
next_phase: null
commit_policy: "Commit only when the user explicitly asks."
product_priority: "Accuracy before speed."
run_all_exclusions: []
root_forbidden_files:
  - "create_all*"
  - "_backup*"
  - "STRUCTURE.txt"
  - "requirements.txt"
required_requirement_files:
  - "requirements-mac.txt"
  - "requirements-windows.txt"
no_touch_without_user_request:
  - "dataset/video_preview_cache/"
release_handoff_files:
  - "AGENTS.md"
  - "ACTION_ITEMS.md"
  - "File_structure.txt"
  - "README.md"
  - "latest RELEASE_v*.md"
```

## Active Work

- None.

## Parked Work

- None.

## Completion Snapshot

The v03.22.00 Mode Autopilot release completed the prior queue:

- P0 completion stability, post-generation cleanup, and deferred editor-save LoRA learning.
- Home-idle personalization learning with Lite/Heavy ramping and blue app-indicator status.
- Fast/Auto/High Mode policy, backward compatibility, and single Mode controls across primary flows.
- Fast safety guards, Auto adaptive policy snapshots, and High full-accuracy policy activation.
- Ten-step engine dashboard with per-step values and explanations.
- Mode-specific audio, VAD, preflight, validation, scheduler, and cleanup policy fields.
- Tests and release handoff documentation.

Future work should start from a new user request rather than this completed backlog.
