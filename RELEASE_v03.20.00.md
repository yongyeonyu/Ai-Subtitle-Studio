# RELEASE v03.20.00

Release date: 2026-05-05
Phase: PHASE3
Base branch: `main`
Immediately previous release: `v03.19.00`
Release app version: `03.20.00`

## Summary

v03.20.00 is the Phase 3 LoRA runtime quality, live-editor preview, and responsiveness release. It builds on v03.19.00 automated LoRA personalization by making learned data safer to use during subtitle generation, adding STT1 adapter planning, showing live subtitle drafts in the editor while generation is still running, and reducing background/cleanup work that made the editor feel busy during manual correction.

This release note intentionally references only v03.19.00 as the previous checkpoint. Older cumulative history remains in older `RELEASE_v*.md` files and should not be copied into handoff documents.

## Changes Since v03.19.00

- Added a subtitle-quality LoRA runtime policy: fast/low quality uses STT1 without LoRA, balanced/normal quality uses STT1 plus minimal LoRA timing/audio/model hints, and precise/high quality can use the full LoRA context with STT ensemble.
- Added STT1 Whisper adapter training-plan and runtime-manifest preparation so the retrieval-based LoRA workflow can later pair with a dedicated STT1 adapter artifact when a runtime-ready model exists.
- Extended Whisper runtime handling to recognize local adapter-style model directories for STT1 runtime overrides.
- Added live editor subtitle previews during subtitle generation so STT/LLM/ensemble progress can appear in the subtitle editor before final segments are committed.
- Kept live preview blocks out of saved SRT/project segment extraction, and replaced overlapping draft blocks when final LLM/ensemble segments arrive.
- Added low-resource idle-learning safeguards: slower idle start, longer cooldowns, coarser progress writes, less frequent retrieval-index rebuilds, retention-prune skipping during idle learning, and automatic downgrade of leftover Full audio-extraction jobs when they resume in background mode.
- Prevented LoRA idle learning from starting while the user is actively editing, opening foreground workflows, or entering file/folder/project/iCloud/NAS work.
- Prevented editor text edits and manual correction popup saves from repeatedly unloading Ollama/STT models during active editing.
- Kept manual editor saves lightweight by avoiding immediate subtitle-video MOV rendering from the editor save path; queue/iCloud/NAS generation-completion flows still own render output.
- Improved queue card/status behavior with per-clip elapsed/estimated time updates and clearer active-stage display.
- Added live processing stage signals so editor status can show LLM review, ensemble, and STT preview activity with lower UI churn.
- Added and updated tests covering quality-tier LoRA policy, STT1 adapter runtime override readiness, live editor previews, idle-learning downgrade behavior, queue elapsed time, and editor responsiveness safeguards.

## Compatibility Notes

- The shared pipeline requirement still applies to single-file, multiclip, folder queue, iCloud, and NAS modes.
- macOS and Windows remain supported targets. Path handling must continue to cover Korean filenames, spaces, backslashes, subprocess entry points, ffmpeg/ffprobe, faster-whisper workers, QML, OpenGL/SceneGraph, PyQt6 runtime behavior, and local LoRA bundle paths.
- `core/runtime/config.py` remains the source of truth for `APP_VERSION`.
- Runtime LoRA data under `dataset/lora_personalization/` is local user data and is ignored by Git. Source code should use the storage helpers to create, restore, reset, and compact it.
- The primary LoRA learning artifact remains `dataset/lora_personalization/lora_data_bundle.zip`, written as an uncompressed managed ZIP bundle.
- Manual correction data such as `dataset/dataset_correction.json` can change during local editing sessions and should not be treated as release history unless intentionally curated.
- This release does not resume iPad work. `PHASE4_iPad` remains parked until the user explicitly asks to resume it.
- The handoff set remains `AGENTS.md`, `ACTION_ITEMS.md`, `File_structure.txt`, `README.md`, and the latest `RELEASE_v*.md`.

## Verification

Completed verification for this release:

- `venv/bin/python -m pytest -q tests/test_personalization_idle_runtime.py`
- `venv/bin/python -m pytest -q tests/test_lora_vector_retriever.py tests/test_project_segment_reload.py tests/test_pipeline_status.py`
- `venv/bin/python -m pytest -q tests/test_cp03_cp04_status_ui.py::Cp03Cp04StatusUiTests::test_editor_manual_edit_pauses_idle_work_without_unloading_models tests/test_editor_auto_export.py tests/test_personalization_idle_runtime.py`
- `venv/bin/python -m pytest -q tests/test_project_segment_reload.py tests/test_pipeline_status.py tests/test_lora_vector_retriever.py tests/test_sidebar_terminal_layout.py::SidebarTerminalLayoutTests::test_editor_mode_releases_idle_ai_models_without_stopping_backend tests/test_sidebar_terminal_layout.py::SidebarTerminalLayoutTests::test_editor_mode_does_not_release_models_while_processing`
- `venv/bin/python -m pytest -q`
  - `683 passed in 40.74s`
- `python3 -m compileall -q core ui tests`
- `python3 -m compileall -q main.py core ui tests`
- `git diff --check -- .`

## Next Direction

No active non-iPad backlog remains in `ACTION_ITEMS.md`. The only parked work is `PHASE4_iPad`, and that scope remains excluded until the user explicitly asks to resume it.
