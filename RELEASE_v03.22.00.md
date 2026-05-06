# RELEASE v03.22.00

Release date: 2026-05-06
Phase: MODE_AUTOPILOT_RELEASED
Base branch: `main`
Immediately previous release: `v03.21.00`
Release app version: `03.22.00`

## Summary

v03.22.00 is the Mode Autopilot release. It builds on v03.21.00 by replacing scattered subtitle-quality and operation-mode controls with one user-facing Mode system, stabilizing generation completion, moving editor-save learning to Home-idle processing, and exposing a ten-step engine dashboard that explains what the pipeline is doing.

This release note intentionally references only v03.21.00 as the previous checkpoint. Older cumulative history remains in older `RELEASE_v*.md` files and should not be copied into handoff documents.

## Changes Since v03.21.00

- Added `core/mode_policy.py` as the shared Fast/Auto/High resolver for subtitle mode normalization, runtime settings, policy snapshots, preflight decisions, and ten-step dashboard payloads.
- Preserved legacy settings compatibility: `balanced`, `normal`, `보통`, and `균형` map to Auto, while old `fast` and `precise` STT quality choices migrate to Fast and High when no explicit `subtitle_mode` is present.
- Replaced the AI settings dialog's duplicate mode/quality controls with one primary `Mode` selector while preserving direct controls for STT1, STT2, subtitle LLM, roughcut LLM, audio model, and VAD model.
- Updated sidebar, folder, multiclip, iCloud, and NAS Mode controls and summaries to use Fast, Auto, and High labels.
- Added Fast runtime policy for cut-boundary off, STT2 off, lightweight scheduling, high-confidence LoRA buckets, and cheap hallucination guard activation.
- Added Auto runtime policy for default adaptive processing, short sampling policy, confidence-gated LoRA/deep/LLM usage, and gradual resource ramping.
- Added High runtime policy for cut-boundary, STT2, dual-VAD, speaker diarization, full LoRA buckets, deep validation, and full-resource startup.
- Added the ten-step engine dashboard rows: cut boundary, preprocessing, audio filter, STT1, STT2, VAD, subtitle LLM, roughcut LLM, LoRA, and deep learning.
- Added per-step policy values and explanations through the Mode policy snapshot and sidebar rendering.
- Moved editor-save truth capture and text LoRA accumulation out of foreground editor save and generation-complete paths into deferred Home-idle queue jobs.
- Added `core/personalization/deferred_editor_learning.py` for compact editor-learning jobs and idle trainer execution.
- Updated idle learning so automatic LoRA/personalization work starts only after Home has been idle for five minutes, ramps from Lite to Heavy, and stops quickly on mouse or keyboard activity.
- Added blue Lite/Heavy learning status on the top-left app indicator, with 1.0 second Lite blinking and 0.1 second Heavy blinking.
- Added post-generation cleanup that invalidates clip-owned prefetch work, clears processing indicators, releases transient runtime state, and returns the UI to interactivity before deferred learning starts.
- Added scoped text-LoRA accumulation support for alternate personalization stores so deferred idle tests and local stores do not leak into global runtime data.
- Tightened STT candidate LLM selection so current runtime/user settings are honored and the candidate-choice response cannot leak into the subtitle-splitting pass for short selected candidates.
- Restored LoRA retrieval prompt facet visibility so scene/topic/mic/noise context remains visible in runtime prompts.
- Updated defaults, tests, and handoff documents for the released Mode Autopilot behavior.

## Compatibility Notes

- `core/runtime/config.py` remains the source of truth for `APP_VERSION`.
- The user-facing Mode values are `fast`, `auto`, and `high`; internal STT quality compatibility keys remain `fast`, `balanced`, and `precise`.
- Existing projects and settings that only contain legacy STT quality keys should continue to load without schema migration.
- Single-file, multiclip, folder queue, iCloud, and NAS workflows should resolve Mode through the same policy path.
- macOS and Windows remain supported targets. Path handling must continue to cover Korean filenames, spaces, backslashes, subprocess entry points, ffmpeg/ffprobe, faster-whisper workers, QML, OpenGL/SceneGraph, PyQt6 runtime behavior, and local LoRA bundle paths.
- Runtime LoRA data under `dataset/lora_personalization/` is local user data and is ignored by Git. Source code should use the storage helpers to create, restore, reset, compact, bucket, and promote it.
- Manual correction data such as `dataset/dataset_correction.json` can change during local editing sessions and should not be treated as release history unless intentionally curated.
- The handoff set remains `AGENTS.md`, `ACTION_ITEMS.md`, `File_structure.txt`, `README.md`, and the latest `RELEASE_v*.md`.

## Verification

Completed verification for this release:

- `venv/bin/python -m pytest -q`
  - `905 passed, 2 subtests passed in 70.92s`
- `venv/bin/python -m compileall -q main.py core ui tests`
- `git diff --check -- .`

## Next Direction

No active or parked backlog remains in `ACTION_ITEMS.md`. Future work should start from user-requested product goals rather than old parked items, with the current priority remaining accuracy before speed.
