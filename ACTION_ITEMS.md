<!--
Document-Version: 04.00.02-mac-native
Phase: MAC_NATIVE_APPSTORE_V4_0_2_RELEASED
Last-Updated: 2026-05-12
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
app_version: "04.00.02"
document_version: "04.00.02-mac-native"
phase: "MAC_NATIVE_APPSTORE_V4_0_2_RELEASED"
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

The v04.00.02 Mac-native release completed the prior queue:

- The repository now targets macOS Apple Silicon only on this branch; Windows launcher and Windows-only dependency files were removed from the active release path.
- Apple Silicon scheduling now includes chip-aware worker budgeting, FFmpeg thread caps, pioneer/follower cut-boundary planning, and accelerator slot distribution for the detected Mac.
- STT candidate scoring and STT1/STT2 merge work now reuse indexed or native overlap calculations instead of rescanning every peer segment.
- Native Swift bridges now cover subtitle/project/timeline/waveform/policy quality helpers intended for later reuse in a future iPad app, with Python kept as a fallback only where quality or compatibility still requires it.
- Production macOS runtime now enables only benchmark-safe native routes by default and keeps Swift LoRA/Deep/LLM policy helpers behind an explicit experimental gate until speed and LoRA ranking parity are proven.
- Native macOS memory helpers, packaging scripts, and benchmark tools are part of the active release set so the app can be profiled, packaged, and iterated as a Mac-first product.
- Generation completion now waits for real saveable subtitle segments before marking the editor complete, then retries the completion autosave until segments are available.
- Exit confirmation now asks to save unsaved editor changes before quick exit or window close cleanup runs.
- Project JSON backups now live under `프로젝트백업/` instead of filling the project root with numbered backup files.
- Canonical project JSON saves now keep the `video` header first, use frame/FPS metadata as the reload contract, and reload external subtitle/STT assets through project-path-aware readers.
- Background LoRA and app-exit cleanup now tolerate old and new trainer shutdown signatures so input or quit requests can pause runtime work without blocking the UI.
- Correction-dictionary cleanup, STT worker I/O, subtitle segment filtering, subtitle accuracy helpers, cut-boundary cache handling, and editor segment bulk loading have smaller native-ready modules.
- Release verification should be re-read from the latest `RELEASE_v*.md` only.

Future work should start from a new user request rather than this completed backlog.
