# RELEASE v03.24.01

Release date: 2026-05-07
Phase: STT_MODE_RUNTIME_RELEASED
Base branch: `codex/large-file-refactor-release`
Immediately previous release: `v03.24.00`
Release app version: `03.24.01`

## Summary

v03.24.01 is the STT Mode runtime, memory, and editor responsiveness release. It builds on v03.24.00 by completing the desktop STT Mode project/runtime flow, adding cached VAD and cut-boundary reuse, tightening subtitle segmentation policy, and aggressively unloading AI/runtime processes after generation, roughcut, project transitions, and app exit.

This release also continues the large-file cleanup track: long roughcut input now runs as cut-boundary-aware LLM chunks instead of skipping outright, 1000+ line UI files were reviewed and refactored, and runtime cleanup responsibilities were split out of `main_window.py` into a dedicated mixin.

## Changes Since v03.24.00

- Added STT Mode desktop project state, runtime bundles, export preflight, learning import/export, and iPad-compatible state/schema coverage.
- Switched STT Mode dictation flow to VAD + human raw text preservation + LoRA/Deep/rules resegmentation, while keeping desktop microphone Whisper optional.
- Added Silero + TEN VAD ensemble integration and policy-aware STT VAD routing.
- Added NPU-aware Whisper/Core ML routing, runtime cleanup helpers, and automatic LLM/STT/audio model shutdown after use.
- Made Ollama lazy-load only when needed, then unload models/processes after subtitle generation, roughcut completion, editor idle cleanup, and app exit.
- Added faster project loading by reusing stored subtitle status metadata instead of recomputing per segment.
- Removed duplicate autosave/save paths and reduced editor-time blocking work by deferring heavy project/runtime cleanup.
- Reduced editor playback and typing stalls by throttling redraws, limiting provider refreshes, simplifying dense timeline rendering, and moving more UI surfaces onto GPU-preferred paths.
- Added cut-boundary and VAD cache reuse, and changed cut-boundary comparison to lower-resolution matching for faster scans.
- Changed roughcut LLM from all-or-nothing context gating to cut-boundary-aware chunked execution for long subtitle sets.
- Added stronger shared subtitle split rules so Fast, Auto, and High all use the same segmentation baseline.
- Refactored 1000+ line files in this pass, including extracting runtime cleanup responsibilities into `ui/main/main_runtime_cleanup.py` and consolidating seek state handling in `ui/editor/video_player_widget.py`.
- Fixed a same-list-reference subtitle refresh bug discovered during code review so in-place segment mutations still refresh visible subtitles.

## Code Review Notes

- Reviewed the new runtime cleanup mixin extraction for behavior regressions in fast exit, editor idle model release, and background cleanup threading. No blocking regression remained after compatibility patching for existing tests.
- Reviewed `video_player_widget.py` after seek-state consolidation. The actionable defect found was stale subtitle display when a provider or context list mutated in place but kept the same list identity; this release now keys refresh decisions off content signatures, not just object identity.
- Reviewed large-file refactors for release blockers. Responsibility boundaries improved, and no remaining release-blocking issue was found under the current test suite.

## Compatibility Notes

- `core/runtime/config.py` remains the source of truth for `APP_VERSION`.
- User-facing Mode values remain `fast`, `auto`, `high`, and `stt_mode`.
- Existing subtitle projects remain supported; lightweight project storage continues to prefer external SRT content and cached metadata reuse.
- macOS and Windows remain supported targets, including Apple Silicon GPU/NPU paths, ffmpeg/ffprobe media flows, PyQt6 scenegraph rendering, and local cache cleanup behavior.
- The handoff set remains `AGENTS.md`, `ACTION_ITEMS.md`, `File_structure.txt`, `README.md`, and the latest `RELEASE_v*.md`.

## Verification

Completed verification for this release:

- `venv/bin/python -m pytest -q`
  - `1026 passed, 1 warning, 5 subtests passed in 43.37s`
- `venv/bin/python -m pytest -q tests/test_video_player_widget.py`
  - `22 passed in 0.23s`
- `venv/bin/python -m pytest -q tests/test_sidebar_terminal_layout.py tests/test_editor_autosave_cleanup.py`
  - `55 passed, 1 warning in 6.56s`
- `venv/bin/python -m compileall -q ui/main/main_window.py ui/main/main_runtime_cleanup.py ui/editor/video_player_widget.py`

Known warning:

- `torch/cuda/__init__.py` emits the existing `pynvml` deprecation warning during the test suite.

## Next Direction

No active or parked backlog remains in `ACTION_ITEMS.md`. The next high-value cleanup candidates are still other 1000+ line UI/pipeline files such as `editor_segments.py`, `editor_pipeline.py`, and `subtitle_engine.py`, but they are not blocking this release.
