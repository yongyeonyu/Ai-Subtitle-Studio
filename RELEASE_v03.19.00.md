# RELEASE v03.19.00

Release date: 2026-05-05
Phase: PHASE3
Base branch: `main`
Immediately previous release: `v03.18.00`
Release app version: `03.19.00`

## Summary

v03.19.00 is the Phase 3 automated LoRA personalization and runtime retrieval release. It builds on the v03.18.00 GPU/QML, lightweight project, and LoRA voice-data checkpoint by making LoRA learning easier for users: video/SRT pairs can be imported as ground truth, editorial bracket text is excluded from speech learning, LoRA data is kept as a unified local bundle, and the runtime subtitle pipeline can retrieve the most relevant learned data through scored/vectorized search.

This release note intentionally references only v03.18.00 as the previous checkpoint. Older cumulative history remains in older `RELEASE_v*.md` files and should not be copied into handoff documents.

## Changes Since v03.18.00

- Simplified the personalization workflow so users can focus on importing video/SRT pairs while the app handles ground-truth extraction, corpus updates, context rows, queueing, and idle training.
- Added exclusion handling for `()`, `[]`, and `{}` editorial subtitle notes so user explanations are stored for audit/context but are not learned as spoken subtitle text.
- Added multimodal LoRA context classification for scene environment, microphone/noise environment, topic, candidate disagreement, subtitle reading speed, and training focus.
- Added scored/vectorized LoRA retrieval with hybrid hash-vector, BM25, media-path, recency, quality, and context-facet signals so large LoRA datasets can stay fast and relevant at subtitle-generation time.
- Added runtime LoRA prompt/context helpers that bring relevant corrections, ground-truth rows, split/line-break rules, prompt/settings trials, audio presets, and multimodal context into subtitle generation.
- Added unified LoRA bundle storage and restore/reset support so local LoRA data behaves like one managed model artifact instead of a loose menu of JSONL files.
- Added idle training queue recovery and shutdown handling so interrupted LoRA jobs can resume from persisted progress after app restart or forced termination.
- Added user-facing learning information UI with latest updates, queue state, corpus counts, learned rules, voice/profile rows, and detailed LoRA inspection.
- Simplified and compacted the LoRA settings UI by hiding advanced operations behind fewer user-facing controls and moving routine learning into automatic idle behavior.
- Added a Gap dialog `자동설정` action that applies LoRA-learned timing settings to subtitle gap sliders when learned data exists.
- Extended LoRA setting trials and runtime setting overrides to include the full key gap-settings family: continuous threshold, push rate, single subtitle tail, split target length, min/max duration, max CPS, dedupe window, and silence break.
- Refactored large LoRA and project modules into focused storage, bundle, retrieval, scoring, UI-info, UI-action, and SRT helper modules while preserving public compatibility wrappers.
- Hardened Qt/offscreen test teardown by avoiding unsafe deferred widget deletion in the test runner and disabling startup-only delayed model checks during offscreen tests.

## Compatibility Notes

- The shared pipeline requirement still applies to single-file, multiclip, folder queue, iCloud, and NAS modes.
- macOS and Windows remain supported targets. Path handling must continue to cover Korean filenames, spaces, backslashes, subprocess entry points, ffmpeg/ffprobe, faster-whisper workers, QML, OpenGL/SceneGraph, PyQt6 runtime behavior, and local LoRA bundle paths.
- `core/runtime/config.py` remains the source of truth for `APP_VERSION`.
- Runtime LoRA data under `dataset/lora_personalization/` is local user data and is ignored by Git. Source code should use the storage helpers to create, restore, reset, and compact it.
- This release does not resume iPad work. `PHASE4_iPad` remains parked until the user explicitly asks to resume it.
- The handoff set remains `AGENTS.md`, `ACTION_ITEMS.md`, `File_structure.txt`, `README.md`, and the latest `RELEASE_v*.md`.

## Verification

Completed verification for this release:

- `venv/bin/python -m ruff check $(git diff --name-only -- '*.py') $(git ls-files --others --exclude-standard -- '*.py')`
- `python3 -m compileall -q main.py core ui tests`
- `git diff --check -- .`
- `venv/bin/python -m pytest -q`
  - `659 passed in 42.04s`

## Next Direction

No active non-iPad backlog remains in `ACTION_ITEMS.md`. The only parked work is `PHASE4_iPad`, and that scope remains excluded until the user explicitly asks to resume it.
