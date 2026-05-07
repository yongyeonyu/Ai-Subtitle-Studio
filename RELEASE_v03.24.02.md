# RELEASE v03.24.02

Release date: 2026-05-08
Phase: RUNTIME_ORCHESTRATION_RELEASED
Base branch: `codex/large-file-refactor-release`
Immediately previous release: `v03.24.01`
Release app version: `03.24.02`

## Summary

v03.24.02 is the runtime orchestration, QML expansion, and accelerator scheduling release. It builds on v03.24.01 by pushing more editor and settings chrome onto QML surfaces, adding a global runtime/memory coordinator, strengthening CPU multi-core planning, and making STT/LoRA/runtime paths more explicit about how they use CPU, GPU, and NPU backends.

This release also tightens learning-data quality control. LoRA bucket promotion is stricter, bundle budgets are capped per quality bucket, STT mode now has its own runtime/LoRA bundle layer, and long-running personalization/runtime cleanup paths were reviewed to reduce stale cache growth and shutdown drag.

## Changes Since v03.24.01

- Added QML-backed message dialogs, context menus, global menu components, action bars, tab bars, video controls, sidebar navigation, and subtitle/editor surfaces across more app flows.
- Restored the classic painter timeline canvas as the default body while keeping lighter QML overlays where they help responsiveness.
- Added `core/runtime/memory_manager.py` and `core/runtime/multi_process.py` so runtime state, cache trimming, worker planning, and resource snapshots are managed from one layer.
- Expanded accelerator-aware scheduling so mixed backend workloads can keep parallelism when STT, Torch, Core ML, MLX, or MPS paths are split across CPU/GPU/NPU combinations.
- Added `core/audio/torch_acceleration.py` and routed Torch-backed VAD/diarization helpers through shared backend and memory-pressure decisions.
- Added STT mode LoRA/runtime policy support and surfaced `STT` as a full mode alongside `Fast`, `Auto`, and `High`.
- Tightened LoRA quality bucket thresholds and per-bucket bundle budgets so only stronger data reaches the `high` bucket and runtime ZIP size stays bounded.
- Added safer unified LoRA bundle writing and cleanup rules to avoid temp ZIP races during refresh, migration, and shutdown.
- Continued 1000+ line refactors in large UI/runtime files, including splitting large settings/video/sidebar/pipeline responsibilities into smaller helpers.
- Final code review fixes in this release addressed runtime helper compatibility, stale temp cleanup behavior, and legacy test patch-point compatibility.

## Code Review Notes

- Reviewed final runtime scheduling changes with targeted tests around STT ensemble live flush, sidebar exit cleanup, LoRA bundle refresh, and personalization dialogs. The only actionable defects found were compatibility regressions and temp ZIP cleanup edge cases; all were fixed in this release.
- Reviewed large-file refactors after the new runtime/memory layer landed. Responsibility boundaries improved without introducing a new blocking issue under the full current suite.
- Re-ran static checks after the final fixes to keep the touched runtime/UI files free of undefined names and unused-import drift in the reviewed scope.

## Compatibility Notes

- `core/runtime/config.py` remains the source of truth for `APP_VERSION`.
- User-facing Mode values remain `fast`, `auto`, `high`, and `stt_mode`.
- Existing projects remain compatible with the current project/runtime state files and cached metadata strategy.
- macOS and Windows remain supported targets, with Apple Silicon GPU/NPU paths continuing to prefer Core ML, MLX, MPS, and QML/scenegraph-backed UI where available.
- The handoff set remains `AGENTS.md`, `ACTION_ITEMS.md`, `File_structure.txt`, `README.md`, and the latest `RELEASE_v*.md`.

## Verification

Completed verification for this release:

- `venv/bin/python -m compileall -q main.py core ui tests`
- `venv/bin/ruff check core/personalization/lora_store_bundle.py core/audio/media_processor_transcribe.py core/runtime/multi_process.py ui/editor/video_player_widget.py ui/settings/settings_ai.py ui/home_sidebar.py`
- `venv/bin/python -m pytest -q tests/test_torch_acceleration.py tests/test_runtime_multi_process.py tests/test_video_player_widget.py tests/test_sidebar_terminal_layout.py tests/test_ai_settings_runtime_apply.py`
  - `97 passed, 1 warning`
- `venv/bin/python -m pytest -q`
  - `1075 passed, 1 warning, 5 subtests passed in 91.45s`

Known warning:

- `torch/cuda/__init__.py` emits the existing `pynvml` deprecation warning during the test suite.

## Next Direction

No blocking issue remains from the final review pass. The next cleanup candidates are still large editor/runtime files that remain above 1000 lines, but they are no longer release blockers after the current orchestration and stability work.
