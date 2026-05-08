<!--
Document-Version: 03.25.00
Phase: NATIVE_PERFORMANCE_UI_RELEASED
Last-Updated: 2026-05-09
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
app_version: "03.25.00"
document_version: "03.25.00"
phase: "NATIVE_PERFORMANCE_UI_RELEASED"
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

The v03.25.00 Native Performance and UI release completed the prior queue:

- Cut-boundary pioneer/follower work now has backend routing, optional C++ helper kernels, FFmpeg scene prepass support, proxy reuse, and candidate-only optical-flow follower verification.
- Long-media audio extraction now has quality-safe direct FFmpeg chunk routing, fused filter graphs, and backend profile hooks.
- STT/VAD/LLM/backend selection now flows through shared auto/native/fast/legacy routing helpers and optional local benchmark profile materialization.
- Korean KomixV2 Whisper candidates are available and clearly labeled across STT2 surfaces.
- Editor mode gained lighter segment/waveform rendering paths, preview proxy reuse, tighter playback/editor sync, and safer post-generation runtime cleanup.
- Settings, context menus, message dialogs, and bottom/global menu buttons were compacted with Apple-style hover/press feedback and outside-click popup dismissal.
- Test video folders are ignored by Git and remain local-only.
- Release verification passed with the full current suite: `1222 passed, 1 warning, 5 subtests passed`.

Future work should start from a new user request rather than this completed backlog.
