# RELEASE v03.18.00

Release date: 2026-05-05
Phase: PHASE3
Base branch: `main`
Immediately previous release: `v03.17.00`
Release app version: `03.18.00`

## Summary

v03.18.00 is the Phase 3 GPU/QML, lightweight project, and LoRA voice-data release. It builds on the v03.17.00 personalization release by moving the editor toward lighter rendering and project state, adding QML/SceneGraph foundations for timeline and panel migration, making subtitle-video output part of the standard save flow, and expanding LoRA personalization from text/rule learning into transcript-aligned voice data preparation.

This release note intentionally references only v03.17.00 as the previous checkpoint. Older cumulative history remains in older `RELEASE_v*.md` files and should not be copied into handoff documents.

## Changes Since v03.17.00

- Added GPU/QML migration foundations for timeline rendering, subtitle text editing, video subtitle overlay, settings panels, and project/sidebar shells.
- Added timeline rendering cache and visible-range rendering improvements so long videos and dense subtitle timelines update less work per interaction.
- Added project context/frame metadata helpers and lighter project snapshot paths so subtitle segment and vector-friendly timeline state can be saved and restored more efficiently.
- Added automatic subtitle-video output behavior after subtitle save/generation, with regression coverage for the editor auto-export path.
- Added a lightweight video playback backend abstraction and codec/export helper updates to support lower-memory playback choices and future roughcut lossless export workflows.
- Added roughcut render skeleton and export path refinements, including safer copy/lossless-oriented render planning hooks.
- Expanded LoRA personalization with LLM review JSON export/import, retention policy and low-score pruning, unified `lora_data_bundle.json`, and richer menu help.
- Added voice LoRA data preparation from subtitle segments: `voice_lora_bridge`, speaker profile manifests, training plans, transcript-aligned WAV clip extraction, and dataset manifests.
- Moved voice LoRA WAV extraction off the settings dialog thread into a `QThread` worker so long ffmpeg batches do not freeze the personalization dialog.
- Hardened idle voice-profile jobs so missing media or ffmpeg failures no longer silently mark voice extraction as fully complete.
- Updated voice audio readiness counts to verify actual WAV file existence rather than trusting stale manifest flags.
- Added tests for voice LoRA success, missing source media, ffmpeg failure, idle extraction failure handling, and deleted-WAV manifest counting.
- Added Python code-quality cleanup for undefined variables, unsafe late-bound closures in threaded pipeline callbacks, unused imports/locals, duplicate dictionary keys, and overwritten dead helper implementations.
- Kept cross-platform requirement files aligned for the new rendering/playback dependencies.

## Compatibility Notes

- The shared pipeline requirement still applies to single-file, multiclip, folder queue, iCloud, and NAS modes.
- macOS and Windows remain supported targets. Path handling must continue to cover Korean filenames, spaces, backslashes, subprocess entry points, ffmpeg/ffprobe, faster-whisper workers, QML, OpenGL/SceneGraph, and PyQt6 runtime behavior.
- `core/runtime/config.py` remains the source of truth for `APP_VERSION`.
- This release does not resume iPad work. `PHASE4_iPad` remains parked until the user explicitly asks to resume it.
- Runtime artifacts under `dataset/lora_personalization/`, `output/`, and `projects/` may exist locally but should not be treated as source release history.
- The handoff set remains `AGENTS.md`, `ACTION_ITEMS.md`, `File_structure.txt`, `README.md`, and the latest `RELEASE_v*.md`.

## Verification

Completed verification for this release:

- `python3 -m compileall -q main.py core ui tests`
- `venv/bin/python -m ruff check . --select F,E9,B006,B008,B023,B904,PLE --exclude venv --exclude dataset/video_preview_cache --exclude output --exclude projects`
- `venv/bin/python -m pytest -q --ignore=tests/test_sidebar_terminal_layout.py`
  - `600 passed in 12.42s`
- `venv/bin/python -m pytest -q tests/test_sidebar_terminal_layout.py`
  - `41 passed in 9.26s`
- Combined verified tests: `641 passed`
- `git diff --check -- .`

The sidebar-terminal UI suite is verified separately in offscreen mode because a single all-in-one PyQt test process can still abort during widget teardown on macOS.

## Next Direction

No active non-iPad backlog remains in `ACTION_ITEMS.md`. The only parked work is `PHASE4_iPad`, and that scope remains excluded until the user explicitly asks to resume it.
