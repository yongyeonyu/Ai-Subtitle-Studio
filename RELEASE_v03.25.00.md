# RELEASE v03.25.00

Release date: 2026-05-09
Phase: NATIVE_PERFORMANCE_UI_RELEASED
Base branch: `codex/large-file-refactor-release`
Immediately previous release: `v03.24.03`
Release app version: `03.25.00`

## Summary

v03.25.00 is the native performance, backend-routing, and UI polish release. It builds on v03.24.03 by moving expensive long-media work behind explicit backend routers, adding optional native C++ helper kernels and FFmpeg scene/audio fast paths, reusing editor preview proxies, and tightening editor-mode rendering and popup/menu responsiveness.

The release keeps accuracy before speed. Faster paths are selected only through policy/profile gates or quality-safe conditions, while fallback Python/OpenCV/FFmpeg behavior remains available for compatibility across macOS and Windows.

## Changes Since v03.24.03

- Added shared backend policy helpers for STT, VAD, cut-boundary, audio extraction, local LLM, and editor rendering.
- Added optional benchmark-profile materialization so measured best backends can be reused without committing local profile data.
- Added optional native C++ cut-boundary helper kernels plus build tooling, with Python fallbacks when the extension is unavailable.
- Added FFmpeg scene-prepass support and candidate-only optical-flow follower verification for cut-boundary rollback checks.
- Reused existing 720p editor preview proxies for cut-boundary scans to avoid repeated 4K decode work.
- Improved long-media audio extraction with direct FFmpeg chunk routing, fused filter graphs, and lower IO overhead when quality-safe.
- Added Korean KomixV2 Whisper candidates for STT2, including alias, Hugging Face original, and MLX variants with distinct sidebar labels.
- Added Transformers alias normalization for `whisper-medium-komixv2` to `seastar105/whisper-medium-komixv2`.
- Added local LLM provider routing, including an optional llama.cpp provider path and safer Ollama request/cleanup handling.
- Tightened subtitle quality paths around STT candidate scoring, VAD alignment, timestamp regrouping, and guarded LLM correction.
- Improved project/media fingerprint caches, preview proxy helpers, project segment reload behavior, and editor video context windows.
- Added lighter subtitle segment stores, timeline rendering cache refinements, waveform worker tests, and smoother subtitle editor key/scroll behavior.
- Refreshed QML context menus, message dialogs, settings panels, tab/action bars, and bottom/global menu buttons with compact Apple-style sizing, hover/press feedback, outside-click dismissal, and Korean-only labels.
- Suppressed noisy idle runtime logs and macOS TSM keyboard stderr noise so logs stay focused on actionable pipeline events.
- Kept test videos, projects, output, preview cache, runtime optimization profiles, and native build artifacts out of Git.

## Code Review Notes

- Reviewed release scope for generated media, local project data, and native build outputs. Source files and tests are included; ignored runtime data and compiled `.so` artifacts remain excluded.
- Verified the KomixV2 model menu regression with direct STT2 menu tests so alias, MLX, and Hugging Face original labels no longer collapse to the same display text.
- Verified popup dismissal and shared button feedback tests after the QML popup/menu refresh.
- The native C++ extension is optional. Runtime code must continue to tolerate missing native modules and fall back to Python paths.

## Compatibility Notes

- `core/runtime/config.py` remains the source of truth for `APP_VERSION`.
- User-facing Mode values remain `fast`, `auto`, `high`, and `stt_mode`.
- Backend policies default to `auto`; legacy and safe fallback paths remain available.
- Local benchmark profiles are ignored through `dataset/runtime_optimization_profile.json`.
- Compiled native artifacts are ignored; use `tools/build_native_extensions.py` to rebuild local native helpers when needed.
- Existing project files remain compatible; preview proxies and runtime caches are rebuilt on demand.
- macOS and Windows remain supported. Optional Apple Silicon MLX paths remain available, and native helpers are disabled automatically when unavailable.

## Verification

Completed verification for this release:

- `venv/bin/python -m compileall -q main.py core ui tests`
- `git diff --check -- .`
- `QT_QPA_PLATFORM=offscreen venv/bin/python -m pytest tests/test_button_click_feedback.py tests/test_sidebar_terminal_layout.py tests/test_popup_dismiss.py tests/test_whisper_model_catalog.py -q`
  - `70 passed, 1 warning`
- `QT_QPA_PLATFORM=offscreen venv/bin/python -m pytest -q`
  - `1222 passed, 1 warning, 5 subtests passed in 48.83s`

Known warning:

- `torch/cuda/__init__.py` emits the existing `pynvml` deprecation warning during the test suite.

## Next Direction

The next safe follow-up is runtime benchmarking on fresh user videos after this release lands, especially comparing FFmpeg scene-prepass, native cut-boundary helper availability, and KomixV2 STT2 accuracy on short 1-minute truth-aligned samples.
