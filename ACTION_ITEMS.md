<!--
Document-Version: 03.25.01
Phase: NATIVE_STT_PIPELINE_RELEASED
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
app_version: "03.25.01"
document_version: "03.25.01"
phase: "NATIVE_STT_PIPELINE_RELEASED"
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

The v03.25.01 Native STT Pipeline release completed the prior queue:

- Cut-boundary pioneer/follower work now has backend routing, optional C++ helper kernels, FFmpeg scene prepass support, proxy reuse, and candidate-only optical-flow follower verification.
- Long-media audio extraction now has quality-safe direct FFmpeg chunk routing, overlapped native preprocessing, fused filter graphs, native ClearVoice FFmpeg fallback, and backend profile hooks.
- STT/VAD/LLM/backend selection now flows through shared auto/native/fast/legacy routing helpers and optional local benchmark profile materialization.
- Korean KomixV2 Whisper candidates are available and clearly labeled across STT2 surfaces; Swift WhisperKit persistent and whisper.cpp backends are available as opt-in native STT routes.
- Word timestamps are off by default for speed and re-run only on low-score, selected, precision-review, or VAD-risk spans.
- The Codex ChatGPT CLI provider is available for subtitle and roughcut LLM work without requiring an OpenAI API key.
- Editor mode gained lighter segment/waveform rendering paths, preview proxy reuse, tighter playback/editor sync, and safer post-generation runtime cleanup.
- Settings, context menus, message dialogs, and bottom/global menu buttons were compacted with Apple-style hover/press feedback and outside-click popup dismissal.
- Test video folders are ignored by Git and remain local-only.
- Release verification passed with the full current suite: `1260 passed, 1 warning, 5 subtests passed`.

Future work should start from a new user request rather than this completed backlog.
