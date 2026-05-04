# RELEASE v03.14.00

Release date: 2026-05-04
Phase: PHASE2
Base branch: `main`
Immediately previous release: `v03.13.00`
Release app version: `03.14.00`

## Summary

v03.14.00 is the structural stabilization checkpoint after the v03.13.00 feature release. The release keeps user-visible behavior intact while reducing large-file responsibility, moving runtime globals into `core/runtime`, and splitting cut-boundary, audio, project, subtitle, roughcut, and sidebar helpers into clearer modules.

This release note intentionally references only v03.13.00 as the previous checkpoint. Older cumulative history remains in older `RELEASE_v*.md` files and should not be copied into handoff documents.

## Changes Since v03.13.00

- Moved root runtime files into `core/runtime/config.py` and `core/runtime/logger.py`, then rewired imports to the new runtime package.
- Split cut-boundary auto-grid, FPS-aware normalization, profile, strict verification, and pioneer/follower scan helpers out of the long `core/cut_boundary.py` path.
- Reduced `core/audio/media_processor.py` to orchestration plus mixin composition by extracting audio command/cache, VAD, Whisper transcription, STT ensemble, low-score recheck, and payload de-duplication helpers.
- Moved curated audio preset data into `core/audio/audio_preset_data.py` so `audio_presets.py` can focus on loading, routing, and applying preset decisions.
- Split project frame metadata and model-setting snapshot helpers out of `core/project/project_manager.py`.
- Split subtitle runtime settings, prompt templates, and final timing/gap passes out of `core/engine/subtitle_engine.py`.
- Split roughcut topicless placeholder conversion into `ui/roughcut/roughcut_topicless.py` and removed duplicated fallback behavior.
- Split editor scan-cut helpers, video overlay widgets, roughcut draft helpers, AI roughcut settings helpers, home sidebar helpers, and pipeline cut-boundary helpers into smaller modules.
- Removed unreachable duplicate cut-boundary detector/profile implementations that were overwritten by the stable detector path.
- Added local personalization output paths to ignore rules so future LoRA artifacts remain outside source control.

## Compatibility Notes

- Public helper names and patch entry points were preserved where tests or compatibility paths still depend on them.
- Runtime configuration now comes from `core/runtime/config.py`.
- Runtime logging now comes from `core/runtime/logger.py`.
- Cross-platform behavior remains a requirement for macOS and Windows.

## Verification

Completed verification for the release line:

- `python3 -m compileall -q main.py core ui tests`
- full pytest pass for the refactor line
- focused tests for audio presets, roughcut state/UI, project context, multiclip, subtitle engine, STT ensemble, word resegmenting, cut-boundary, project helpers, and UI cache paths
- `git diff --check`
- root forbidden-file scan
- Python AST scan for legacy root `config` and `logger` imports

Latest local verification after the following document handoff cleanup should be recorded by the assistant in the final chat response, not expanded into this release note.

## Next Direction

The next major planned work is `PHASE3_LORA_GROUND_TRUTH_TRAINING`: a persistent personalization system that imports verified media/subtitle pairs, builds a truth table, learns subtitle style and timing rules, searches settings against ground truth, and applies learned recommendations across all processing modes.
