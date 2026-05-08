# RELEASE v03.24.03

Release date: 2026-05-08
Phase: EDITOR_PERFORMANCE_RELEASED
Base branch: `codex/large-file-refactor-release`
Immediately previous release: `v03.24.02`
Release app version: `03.24.03`

## Summary

v03.24.03 is the editor responsiveness, cut-boundary scheduling, and runtime cleanup release. It builds on v03.24.02 by keeping the classic painter timeline visible and fast, moving segment/editor sync onto lookup-backed paths, and reducing unnecessary model/runtime work while the user is editing or playing video.

The release also incorporates benchmark-driven defaults for the current test-video workload: cut-boundary pioneer/follower work uses CPU topology-aware scheduling, OpenCV worker threading is capped where needed, expensive 4K visual scans can fall back to audio-gain boundaries, and chunk-level audio routing is disabled by default because it was slower than the accuracy benefit on the reviewed samples.

## Changes Since v03.24.02

- Restored the QWidget playhead overlay as the safe timeline path so QML/Quick compositing cannot hide the canvas on macOS/Metal.
- Added vector-style timeline rendering caches for subtitle strips, waveform lanes, hit targets, and quality color/style reuse.
- Made subtitle line edits update the in-memory line map and the affected timeline dirty rectangle instead of rebuilding every segment lookup on each keystroke.
- Added visible-window subtitle/video context refreshes so editor playback and thumbnail context use nearby segments rather than the full subtitle list.
- Reduced editor scroll jitter by only moving the subtitle editor cursor when needed, respecting recent manual scrolling, and avoiding timeline recentering when the active segment is already visible.
- Added button press feedback helpers and applied click-state feedback to the main action buttons.
- Hardened STT ensemble chunk handling by cloning per-worker chunk directories and cleaning them after transcription, preventing one worker from deleting files still needed by another worker.
- Improved cut-boundary startup feedback, incremental save throttling, provisional boundary emission, and follower verification worker reuse.
- Added CPU/GPU/NPU-aware runtime scheduling refinements, including topology-aware cut-boundary worker caps and less expensive runtime resource polling.
- Improved roughcut middle-topic labels by giving the LLM clearer category-level instructions and replacing weak/raw subtitle-copy labels with keyword/category fallbacks.
- Added more complete Ollama shutdown cleanup after generation so editor playback can recover memory and CPU more reliably.
- Updated defaults for the benchmarked workflow: disable chunk audio routing by default, cap audio route workers, disable STT NPU preference by default, keep Torch/GPU acceleration available, and keep runtime tracing off unless explicitly enabled.

## Code Review Notes

- Reviewed the changed cut-boundary, STT ensemble, runtime scheduling, editor sync, timeline rendering, and cleanup paths after the refactor. The main actionable defect found during verification was a timeline click compatibility regression in lightweight test editors; it was fixed by falling back to a direct lookup build when the full editor cache rebuild method is unavailable.
- Confirmed that test media remains excluded from Git via `test video/` in `.gitignore`.
- Ruff still reports pre-existing style-only issues in legacy UI files, mostly one-line statements and import placement. They are not new blocking runtime failures under the current suite, and broad style cleanup is intentionally left out of this release to avoid risky churn.

## Compatibility Notes

- `core/runtime/config.py` remains the source of truth for `APP_VERSION`.
- User-facing Mode values remain `fast`, `auto`, `high`, and `stt_mode`.
- Existing project files remain compatible; subtitle/editor caches are rebuilt from current project data when needed.
- Test videos and generated output remain local-only and are not part of the repository.
- macOS and Windows remain supported. Apple Silicon acceleration remains available through MLX/MPS/Core ML paths, but small cut-boundary verification kernels stay CPU-first by default.
- The handoff set remains `AGENTS.md`, `ACTION_ITEMS.md`, `File_structure.txt`, `README.md`, and the latest `RELEASE_v*.md`.

## Verification

Completed verification for this release:

- `venv/bin/python -m compileall -q main.py core ui tests`
- `git diff --check -- .`
- `QT_QPA_PLATFORM=offscreen venv/bin/python -m pytest tests/test_timeline_hit_targets.py tests/test_timeline_render_cache.py tests/test_timeline_segment_colors.py tests/test_timeline_playhead_fit.py -q`
  - `149 passed`
- `QT_QPA_PLATFORM=offscreen venv/bin/python -m pytest -q`
  - `1130 passed, 1 warning, 5 subtests passed in 36.57s`

Known warning:

- `torch/cuda/__init__.py` emits the existing `pynvml` deprecation warning during the test suite.

## Next Direction

No blocking issue remains from the editor performance review. The next safe cleanup is to reduce legacy UI style debt in small, behavior-preserving batches so Ruff can become a stricter release gate later.
