<!--
Document-Version: 04.00.04-mac-native
Phase: MAC_NATIVE_APPSTORE_V4_0_4_RELEASED
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
app_version: "04.00.04"
document_version: "04.00.04-mac-native"
phase: "MAC_NATIVE_APPSTORE_V4_0_4_RELEASED"
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

The v04.00.04 Mac-native release completed the prior queue:

- Fast/Auto/High now own benchmark-locked VAD defaults on this branch, and direct VAD controls were removed from the simplified AI settings and advanced tuning dialog.
- Automatic audio preset detection now tunes only the audio frontend stack and no longer overwrites mode-owned VAD policy.
- Correction-dictionary runtime lookup now has a SQLite-backed indexed path while keeping `dataset_correction.json` as the editable source of truth.
- Editor startup, file-open, save, and post-generation cleanup now defer heavy idle-learning and analysis work so foreground UI becomes interactive sooner.
- Manual `<<` / `>>` cut hits are promoted into persistent confirmed cut boundaries for later subtitle magnet alignment work.
- Quick-exit and close-event cleanup now schedule forced exit before runtime pause work so cleanup exceptions cannot trap the app open.
- Project schema/version helpers now share one source of truth again instead of carrying stale `03.00.26` literals in older save helpers.
- Release verification should be re-read from the latest `RELEASE_v*.md` only.

Future work should start from a new user request rather than this completed backlog.
