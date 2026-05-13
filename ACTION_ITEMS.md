<!--
Document-Version: 04.00.05-mac-native
Phase: MAC_NATIVE_APPSTORE_V4_0_5_RELEASED
Last-Updated: 2026-05-14
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
app_version: "04.00.05"
document_version: "04.00.05-mac-native"
phase: "MAC_NATIVE_APPSTORE_V4_0_5_RELEASED"
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
- If VAD mode locking remains a product direction, automate the benchmark-refresh path that mines dense dialogue windows from `test video/` and re-scores the locked Fast/Auto/High VAD profiles before future releases.

## Completion Snapshot

The v04.00.05 Mac-native release completed the prior queue:

- Runtime ETA prediction now learns from actual runs using mode/STT/media/cache variants, recent-history weighting, and a shared `core.runtime_eta` payload used by queue, startup diagnostics, and history writes.
- Swift-native helpers now own runtime ETA estimation, startup diagnostic shaping, and cut-boundary cache planning while Python keeps orchestration and fallback paths.
- Editor live STT previews now stay on timeline/STT lanes only, while confirmed subtitle segments remain the only rows rendered into the editor text pane and playback subtitle lane.
- Generation-complete/save recovery now restores backend subtitle backups when transient empty-segment races appear during autosave or manual save.
- Playback rendering now keeps segment text visible during playback and reapplies hidden video subtitle overlays when provider context is still valid.
- Verified cut-boundary UI cleanup now strips stale audio provisional styling from real visual cuts and hides follower-checked helper lines plus terminal end-frame markers from the normal editor UI while preserving project metadata.
- Codex roughcut draft calls now use wider context, longer timeout, override-model inheritance fixes, and a local-rule fallback after timeout.

Future work should start from a new user request rather than this completed backlog.
