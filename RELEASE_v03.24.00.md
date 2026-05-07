# RELEASE v03.24.00

Release date: 2026-05-07
Phase: REFACTOR_QUALITY_RELEASED
Base branch: `codex/large-file-refactor-release`
Immediately previous release: `v03.23.01`
Release app version: `03.24.00`

## Summary

v03.24.00 is a refactor and subtitle-quality routing release. It keeps the v03.23.01 runtime stability work, then makes the user-facing Mode control map directly to the subtitle tool stack: Fast uses LoRA only, Auto uses LoRA plus Deep Learning, and High uses LoRA plus Deep Learning plus chunked LLM review.

This release also extracts the 10-15 subtitle LLM macro chunk orchestration out of the large subtitle engine file into `core.engine.subtitle_macro_chunks`, preserving the existing final LoRA/Deep timing and gap passes while reducing the engine's responsibilities.

## Changes Since v03.23.01

- Added explicit subtitle tool-stack policy metadata for Fast, Auto, and High modes.
- Fast mode now disables subtitle Deep/LLM runtime work and keeps LoRA/pattern-based subtitle post-processing.
- Auto mode now enables LoRA + Deep candidate/timing policy while keeping subtitle LLM disabled.
- High mode enables LoRA + Deep + subtitle LLM macro chunk processing.
- Preserved user-selected subtitle LLM model settings while making Fast/Auto disable LLM only at runtime, so model choices are not lost.
- Added `subtitle_llm_runtime_enabled`, `subtitle_llm_mode_disabled`, and `subtitle_llm_effective_model` runtime fields to make the effective LLM state auditable.
- Moved macro LLM grouping, cut-boundary-aware 10-15 row chunking, chunk distribution, and group execution into `core.engine.subtitle_macro_chunks`.
- Kept `subtitle_engine.py` focused on orchestration, LoRA/Deep prepass, final timing/gap passes, quality review, and SRT output.
- Retained project-lightweight storage, native JSON, compact LoRA pattern-index matching, LoRA retention pruning, and external SRT sidecar changes from the active workstream.

## Code Review Notes

- Reviewed 1000+ line source files for immediate release-blocking risks. The actionable issue found during this pass was the subtitle-engine macro chunk responsibility being embedded inside an already large engine file; this is now extracted.
- Reviewed the Fast/Auto/High LLM policy interaction. The initial implementation could have overwritten user-selected LLM model settings in Fast/Auto; it now preserves stored settings while disabling effective subtitle LLM execution by mode.
- Remaining 1000+ line UI and pipeline files are stable under the current test suite. They remain candidates for future responsibility-based splits, but no blocking behavior bug was found in this release pass.

## Compatibility Notes

- `core/runtime/config.py` remains the source of truth for `APP_VERSION`.
- The user-facing Mode values remain `fast`, `auto`, and `high`; legacy STT quality compatibility remains unchanged.
- Direct user controls for STT1, STT2, subtitle LLM, roughcut LLM, audio model list, and VAD model list remain available.
- Stored subtitle LLM choices are preserved even when Fast/Auto disables subtitle LLM at runtime.
- macOS and Windows remain supported targets, including Korean paths, spaces, subprocess handling, ffmpeg/ffprobe, PyQt6, OpenGL/SceneGraph, and local media cache behavior.
- The handoff set remains `AGENTS.md`, `ACTION_ITEMS.md`, `File_structure.txt`, `README.md`, and the latest `RELEASE_v*.md`.

## Verification

Completed verification for this release:

- `PYTHONPATH=. venv/bin/pytest -q`
  - `943 passed, 1 warning, 2 subtests passed in 73.40s`
- `venv/bin/python -m py_compile core/engine/subtitle_engine.py core/engine/subtitle_macro_chunks.py`
- `venv/bin/python -m py_compile core/mode_policy.py core/engine/subtitle_settings.py core/settings_profiles.py core/runtime/config.py`
- `git diff --check -- core/mode_policy.py core/engine/subtitle_settings.py tests/test_mode_policy.py`

Known warning:

- `torch/cuda/__init__.py` emits the existing `pynvml` deprecation warning in `tests/test_sidebar_terminal_layout.py`.

## Next Direction

No active or parked backlog remains in `ACTION_ITEMS.md`. Future refactors should continue splitting 1000+ line files by responsibility, with the highest-value candidates being UI window/sidebar modules and long-running pipeline helpers.
