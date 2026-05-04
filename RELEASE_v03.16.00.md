# RELEASE v03.16.00

Release date: 2026-05-05
Phase: PHASE2
Base branch: `main`
Immediately previous release: `v03.15.00`
Release app version: `03.16.00`

## Summary

v03.16.00 is the timeline-stability and queue-consistency release. It keeps the accuracy-first direction from v03.15.00, but focuses on making the editor easier to trust during long real subtitle sessions: FPS-based timing moves further into the project model, queue cards and auto-processing states stay synchronized with actual save/export completion, timeline lanes behave more consistently during clip-to-clip work, and live microphone input becomes usable without optional Python speech-recognition dependencies.

This release note intentionally references only v03.15.00 as the previous checkpoint. Older cumulative history remains in older `RELEASE_v*.md` files and should not be copied into handoff documents.

## Changes Since v03.15.00

- Extended frame-based timing support so timeline movement, project snapshots, playback edge handling, and subtitle regeneration paths rely more consistently on FPS-derived boundaries instead of mixed time-only state.
- Reworked queue-state synchronization across single-file, folder queue, iCloud, and NAS processing so completion status, elapsed/expected time, save/export phases, and sidebar queue cards stay aligned with actual work instead of stale intermediate text.
- Mapped automatic processing presets to the same `빠름 / 보통 / 높음` subtitle-quality model used in the editor, including legacy preset normalization and sidebar sync behavior.
- Improved the queue sidebar card UI with denser card layout, left-aligned status text, clearer elapsed/expected time display, active-card focus behavior, and more stable completion coloring.
- Hardened pipeline stage reporting so disabled stages show as complete from the start, saved states no longer leave STT rows yellow by mistake, and active STT/LLM/cut-boundary progress is reflected more reliably in the left sidebar.
- Added central helpers for queue ordering and subtitle-status persistence so independent clip processing, nested folder ordering, and per-clip save/export completion behave consistently.
- Improved single-clip queue-mode behavior so iCloud, NAS, and folder processing reset editor context between clips, preserve clip independence, and auto-save/export before advancing.
- Expanded timeline editing behavior around subtitle confirmation, temporary vs confirmed boundaries, candidate selection, gap handling, snapping, and lane-specific status rendering.
- Removed fragile subtitle preview and resize side effects that caused playhead text flicker, disappearing handles, failed first-segment deletion, and unstable segment drag or trim behavior.
- Refined playback and zoom behavior near end-of-media and during fit/zoom transitions so playhead movement, frame stepping, and viewport anchoring remain stable while the user is editing.
- Added live microphone capture through a Qt audio session path and rendered the incoming waveform inside the active subtitle segment, eliminating the previous `speech_recognition` dependency failure path.
- Added a reusable video codec helper and related renderer/player updates to support codec-policy cleanup and HEVC-oriented workflows more centrally.
- Improved Ollama/STT integration with better fallback handling, clearer readiness behavior, and safer status parsing during LLM-assisted subtitle cleanup.
- Added project-persistence coverage for richer subtitle status metadata, STT candidate state, queue status recovery, and frame-aware snapshot reloads.
- Added regression coverage for queue completion order, batch editor activation, live microphone sessions, individual queue context resets, FPS/playhead behavior, stage-status parsing, and subtitle/timeline color logic.

## Compatibility Notes

- The shared pipeline requirement still applies to single-file, multiclip, folder queue, iCloud, and NAS modes.
- macOS and Windows remain supported targets. Path handling must continue to cover Korean filenames, spaces, backslashes, subprocess entry points, ffmpeg/ffprobe, faster-whisper workers, and PyQt6 runtime behavior.
- `core/runtime/config.py` remains the source of truth for `APP_VERSION`.
- The handoff set remains `AGENTS.md`, `ACTION_ITEMS.md`, `File_structure.txt`, `README.md`, and the latest `RELEASE_v*.md`.

## Verification

Completed verification for this release:

- `venv/bin/python -m pytest -q --ignore=tests/test_sidebar_terminal_layout.py`
  - `546 passed in 12.65s`
- `venv/bin/python -m pytest tests/test_sidebar_terminal_layout.py -q`
  - `41 passed in 8.21s`
- Combined verified tests: `587 passed`
- `python3 -m compileall -q main.py core ui tests`
- `git diff --check -- .`

The sidebar-terminal UI suite is verified separately in offscreen mode because a single all-in-one PyQt test process can abort during widget teardown on macOS even after the individual suites pass.

## Next Direction

The next major planned work remains `PHASE3_LORA_GROUND_TRUTH_TRAINING`: a persistent personalization system that imports verified media/subtitle pairs, builds a truth table, learns subtitle style and timing rules, searches settings against ground truth, and applies learned recommendations across all processing modes.
