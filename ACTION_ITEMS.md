<!--
Document-Version: 03.24.03
Phase: EDITOR_PERFORMANCE_RELEASED
Last-Updated: 2026-05-08
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
app_version: "03.24.03"
document_version: "03.24.03"
phase: "EDITOR_PERFORMANCE_RELEASED"
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

The v03.24.03 Editor Performance release completed the prior queue:

- Timeline canvas visibility was restored by keeping the playhead overlay on QWidget instead of a full QQuickWidget layer.
- Subtitle editor and timeline segment movement now use line-map caches, dirty-rectangle updates, and visible-window context refreshes.
- Timeline segment activation no longer recenters when the target is already visible, reducing scroll jitter during editing and playback.
- STT ensemble chunk workers now use cloned per-worker chunk directories and clean them after transcription.
- Cut-boundary pioneer/follower work now has topology-aware worker planning, lower UI progress overhead, reusable follower captures, and high-cost visual scan fallback.
- Roughcut middle-topic labeling now prefers category-level labels and repairs weak/raw subtitle-copy topics.
- Post-generation Ollama cleanup, runtime resource polling, and editor playback cleanup were tightened.
- Test video folders are ignored by Git and remain local-only.
- Release verification passed with the full current suite: `1130 passed, 1 warning, 5 subtests passed`.

Future work should start from a new user request rather than this completed backlog.
