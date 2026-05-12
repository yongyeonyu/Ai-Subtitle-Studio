<!--
Document-Version: 04.00.03-mac-native
Phase: MAC_NATIVE_APPSTORE_V4_0_3_RELEASED
Last-Updated: 2026-05-13
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
app_version: "04.00.03"
document_version: "04.00.03-mac-native"
phase: "MAC_NATIVE_APPSTORE_V4_0_3_RELEASED"
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

- Actual App Store Connect upload requires the user's Apple Developer account, signing identities, App Store Connect API key or app-specific password, and team configuration.
- Future iPadOS app reuse is expected. Keep Swift-native subtitle, LoRA, deep policy, project I/O, timeline, and waveform logic as Apple-platform reusable core modules, with macOS-only UI, process, file-watcher, and packaging code kept at the edges.

## Completion Snapshot

The v04.00.03 Mac-native release completed the prior queue:

- App startup, Home-idle cleanup, and foreground busy-state release now avoid blocking the first editor/home transition on interrupted-training recovery or deferred learning work.
- Playback and timeline interaction now keep the playhead visually synchronized with VLC-backed playback, preserve the playhead during subtitle handle drags, and avoid overlay ghost artifacts.
- Cut-boundary navigation now adds visual jump scouting plus follower rollback verification so `<<` and `>>` can land on hard cuts that look similar in color.
- Project save/load now preserves STT1/STT2 preview tracks inside project JSON, normalizes subtitle timing on the frame grid, and suppresses lingering audio-only provisional cut guides after reload.
- ChatGPT Codex CLI can now be selected as both subtitle LLM and roughcut LLM through the app settings and model lists.
- Multi-speaker generation now supports whole-audio speaker pre-assignment before Whisper finalization and Netflix-style multiline overlap captions with preserved `speaker_list` metadata.
- Release verification should be re-read from the latest `RELEASE_v*.md` only.

Future work should start from a new user request rather than this completed backlog.
