<!--
Document-Version: 03.23.00
Phase: STABLE_EDITOR_FRAMES_RELEASED
Last-Updated: 2026-05-07
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
app_version: "03.23.00"
document_version: "03.23.00"
phase: "STABLE_EDITOR_FRAMES_RELEASED"
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

The v03.23.00 Stable Editor Frames release completed the prior queue:

- Fast mode selective low-score STT2 rescue and lightweight overlap/review policy.
- Post-generation busy cursor cleanup and playback-safe deferral of review, roughcut, prefetch, cleanup, and model-release work.
- Removal of the duplicate subtitle-review Mode selector.
- Stable editor text/video/timeline render frames and start-layout restoration.
- Frame-based and whole-editor GPU rendering policy with conservative OpenGL opt-ins.
- Tests and release handoff documentation.

Future work should start from a new user request rather than this completed backlog.
