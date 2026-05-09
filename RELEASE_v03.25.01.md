# RELEASE v03.25.01

Release date: 2026-05-09
Phase: NATIVE_STT_PIPELINE_RELEASED
Base branch: `main`
Immediately previous release: `v03.25.00`
Release app version: `03.25.01`

## Summary

v03.25.01 is the native STT pipeline and release-cleanup patch. It builds on v03.25.00 by wiring the macOS-native STT experiments into the production Python pipeline, keeping default subtitle quality intact while reducing the amount of expensive work done on every chunk.

The release keeps MLX as the stable macOS default, adds opt-in Swift WhisperKit persistent and whisper.cpp routes, makes word timestamps selective instead of always-on, and moves slow ClearVoice work to a native FFmpeg path when the selected quality preset allows it.

## Changes Since v03.25.00

- Added a Swift WhisperKit persistent worker package and Python wrapper so WhisperKit can be benchmarked and reused without starting a new model process for every chunk.
- Added a whisper.cpp CLI backend with model/binary discovery, JSON parsing, word timestamp support, native-policy routing, and MLX/faster fallback when the binary or ggml model is unavailable.
- Added STT backend selection support for `mlx`, `whisperkit-persistent`, `whisper.cpp`, Core ML, Transformers, and faster-whisper through the same transcription pipeline.
- Changed default STT word timestamp behavior to a fast first pass, then selective precision rechecks only for low-score, editor-selected, precision-review, or VAD-risk spans.
- Changed STT1/STT2 scheduling so the secondary model is used as a selective recheck path instead of always doing full parallel work.
- Added native FFmpeg audio preprocessing orchestration for overlapped extraction/enhancement work.
- Added native ClearVoice FFmpeg single-pass handling so long clips no longer wait on the slow deep-learning ClearVoice path by default.
- Added Codex ChatGPT CLI as a subscription-backed OpenAI-like provider for subtitle and roughcut LLM work without requiring an API key or Ollama preflight.
- Preserved subtitle timing quality by combining segment timestamps, selective word timestamps, VAD alignment, cut-boundary signals, and candidate scoring in the final STT path.
- Tightened UI bounds, sidebar layout, popup sizing, editor/video/timeline stability, and menu cleanup from the current release work.

## Code Review Notes

- Reviewed the new native STT paths for fallback behavior. Missing WhisperKit binaries, missing whisper.cpp binaries, and missing ggml models now fall back instead of aborting generation.
- Reviewed subprocess and cleanup paths so persistent MLX, WhisperKit, whisper.cpp, Transformers, and faster-whisper workers do not leave active child processes behind.
- Removed a duplicate ignore entry and checked the STT transcription path for stale unreachable code before release.
- SwiftPM build output and local benchmark artifacts remain ignored; source package files and tests are included.

## Compatibility Notes

- `core/runtime/config.py` remains the source of truth for `APP_VERSION`.
- Existing settings remain compatible. New STT settings default to selective word timestamps and selective STT2 rechecks.
- `whisper.cpp:large-v3-turbo` appears in model settings, but it requires a local `whisper-cli` binary and a matching ggml model file. If unavailable, the app falls back safely.
- The Swift WhisperKit route is opt-in through `whisperkit-persistent:<model>` and still falls back to MLX if the worker cannot build or launch.
- Codex ChatGPT CLI support requires the local `codex` command to be installed and logged in.

## Verification

Completed verification for this release:

- `venv/bin/python -m compileall -q main.py core ui tests`
- `git diff --check -- .`
- `venv/bin/python -m pytest -q`
  - `1260 passed, 1 warning, 5 subtests passed in 105.69s`
- whisper.cpp native smoke with `/opt/homebrew/bin/whisper-cli`
  - `backend=whisper.cpp`, `returncode=0`

Known warning:

- `torch/cuda/__init__.py` emits the existing `pynvml` deprecation warning during the test suite.

## Next Direction

The next safe follow-up is real-media benchmarking on the user's target Mac: compare MLX large/turbo, Swift WhisperKit persistent, and whisper.cpp ggml models on 1-minute truth-aligned Korean samples, then store only the winning backend profile locally.
