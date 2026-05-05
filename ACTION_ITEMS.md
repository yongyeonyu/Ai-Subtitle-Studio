<!--
Document-Version: 03.19.00
Phase: PARKED_ONLY
Last-Updated: 2026-05-05
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
app_version: "03.19.00"
document_version: "03.19.00"
phase: "PARKED_ONLY"
next_phase: "PHASE4_iPad"
commit_policy: "Commit only when the user explicitly asks."
product_priority: "Accuracy before speed."
run_all_exclusions:
  - "PHASE4_iPad"
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

- No active non-iPad items remain.
- User-requested exclusion is still in effect for `PHASE4_iPad`.
- v03.19.00 release work is complete; LoRA automation, vector retrieval, unified uncompressed bundle storage, idle-only low-resource learning, Full learning controls, detailed learning logs, gap autosettings, and related refactors are not active backlog.

## Parked Work

### PHASE4_iPad

Status: parked
Reason: only iPad-specific scope remains, and the user-requested exclusion for iPad work is still in effect.

Parked identifiers:

- `iPad-1`
- `iPad-2`
- `iPad-3`
- `iPad-4`
- `iPad-5`
- `iPad-6`
- `iPad-7`
