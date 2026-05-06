# RELEASE v03.21.00

Release date: 2026-05-06
Phase: COMPLETE
Base branch: `main`
Immediately previous release: `v03.20.00`
Release app version: `03.21.00`

## Summary

v03.21.00 is the accuracy automation, recovery safety, and tablet-readiness release. It builds on v03.20.00 by moving subtitle generation away from one-shot LLM cleanup and toward a decision pipeline where media fingerprints, STT candidates, LoRA retrieval, deep-learning policies, LLM verification, cut-boundary evidence, and user corrections all feed measurable subtitle decisions.

This release note intentionally references only v03.20.00 as the previous checkpoint. Older cumulative history remains in older `RELEASE_v*.md` files and should not be copied into handoff documents.

## Changes Since v03.20.00

- Added media fingerprint cache keys and fingerprint-scoped audio output paths so same-name replacement videos cannot reuse stale duration, waveform, audio, or chunk artifacts.
- Added STT lattice artifacts and candidate-policy helpers so STT1, STT2, VAD variants, rescue attempts, and minimal-edit LLM proposals can be scored instead of overwritten.
- Added a subtitle accuracy graph that records STT decisions, LoRA evidence, deep-learning scores, LLM gate decisions, verifier rollbacks, timing metrics, and hard-case signals per subtitle.
- Added stronger LLM controls: candidate-only prompting, confidence gating, minimal-edit policy, preservation checks, hallucination proxies, and automatic rollback to STT/LoRA-backed candidates when verification fails.
- Added LoRA/deep-learning runtime automation for subtitle-specific gap, bundle, context, style, timing, line-break, quality-bucket, and settings-autopilot decisions.
- Added user-edit capture and hard-case memory so corrected subtitles can feed future ground-truth retrieval, scoring, and policy learning.
- Added audio-energy cut-boundary evidence, fused visual/audio/text boundary helpers, provisional audio boundaries, and middle-classification policies for more stable subtitle grouping.
- Added dynamic scheduler and startup diagnostics helpers so processing can adapt to workload, CPU/GPU availability, memory, battery, and user interaction instead of relying on fixed thread counts.
- Added background prefetch and incremental cache safeguards while keeping hard cut-boundary splitting tied to the current verified boundary fingerprint.
- Unified roughcut LLM configuration paths and applied roughcut LLM draft output to the normal roughcut pipeline instead of leaving successful calls as no-ops.
- Preserved project analysis metadata during queued project saves and refreshed recovery controls after stale recovery-state detection.
- Added portable iPad exchange manifest validation using relative-path fallback and digest checks when bundles move between local, iCloud, and tablet locations.
- Added tablet-aware responsive profiles, settings dialog scaling, timeline hit-target expansion, and viewport smoke tests while preventing desktop windows from being misclassified as tablets by size alone.
- Added automatic problem-area concepts, subtitle why/one-click-fix helpers, golden regression scaffolding, and simplified settings profiles so future UI can hide low-level controls behind automatic quality modes.
- Added and updated tests for fingerprint caches, media processing, STT lattices, LLM candidate policy, LoRA/deep runtime policies, cut-boundary fusion, startup diagnostics, recovery state, iPad exchange, responsive profiles, tablet timeline targets, roughcut behavior, and settings materialization.

## Compatibility Notes

- The shared pipeline requirement still applies to single-file, multiclip, folder queue, iCloud, and NAS modes.
- macOS and Windows remain supported targets. Path handling must continue to cover Korean filenames, spaces, backslashes, subprocess entry points, ffmpeg/ffprobe, faster-whisper workers, QML, OpenGL/SceneGraph, PyQt6 runtime behavior, local LoRA bundle paths, and portable iPad exchange bundles.
- `core/runtime/config.py` remains the source of truth for `APP_VERSION`.
- Runtime LoRA data under `dataset/lora_personalization/` is local user data and is ignored by Git. Source code should use the storage helpers to create, restore, reset, compact, bucket, and promote it.
- The four quality-tier LoRA artifacts are runtime data: high, medium, low, and pending-delete. Source code should treat the score index as the priority authority when retrieved rules overlap.
- Manual correction data such as `dataset/dataset_correction.json` can change during local editing sessions and should not be treated as release history unless intentionally curated.
- Tablet/iPad readiness is implemented as responsive scaffolding and exchange helpers; desktop behavior must remain the default unless platform/touch/override signals clearly request tablet mode.
- The handoff set remains `AGENTS.md`, `ACTION_ITEMS.md`, `File_structure.txt`, `README.md`, and the latest `RELEASE_v*.md`.

## Verification

Completed verification for this release:

- `venv/bin/python -m pytest -q`
  - `882 passed, 2 subtests passed in 728.22s`
- `python3 -m compileall -q main.py core ui tests`
- `git diff --check -- .`

## Next Direction

No active or parked backlog remains in `ACTION_ITEMS.md`. Future work should start from user-requested product goals rather than old parked items, with the current priority remaining accuracy before speed.
