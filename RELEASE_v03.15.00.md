# RELEASE v03.15.00

Release date: 2026-05-04
Phase: PHASE2
Base branch: `main`
Immediately previous release: `v03.14.00`
Release app version: `03.15.00`

## Summary

v03.15.00 is the accuracy-first workflow release. It turns the post-v03.14 refactor work into a shared production path for single-file, folder queue, multiclip, iCloud, and NAS processing. The release focuses on first-pass subtitle correctness: automatic audio routing is expanded, subtitle timing follows cut boundaries and VAD more consistently, STT1/STT2 metadata is persisted more completely, folder selection behaves as a true queue, and the handoff documents are reset for clean continuation.

This release note intentionally references only v03.14.00 as the previous checkpoint. Older cumulative history remains in older `RELEASE_v*.md` files and should not be copied into handoff documents.

## Changes Since v03.14.00

- Added an accuracy-first policy layer and enabled stricter default settings for STT ensemble scoring, low-score recheck, VAD review, correction memory, wrong-answer memory, subtitle quality correction, and chunk-aware audio routing.
- Reworked automatic audio preset classification so clip and chunk profiles can route FFmpeg preprocessing, voice filtering, and VAD choices without exposing manual audio/VAD selectors to the user.
- Hardened audio extraction and preprocessing cleanup so external termination, ffmpeg failure, and app/home shutdown paths are reported more clearly.
- Improved subtitle timing alignment around confirmed cut boundaries, provisional cut boundaries, VAD islands, gap settings, and STT1/STT2 candidate spans.
- Added shared project I/O coverage so STT1/STT2 candidates, subtitle segments, timeline metadata, model settings, dirty state, and frame-based project fields persist consistently.
- Fixed folder selection so folder processing is a sequential queue of individual files, while multiclip editing remains an explicit multiclip workflow.
- Updated folder and file selection UI with thumbnail-aware rows, individual selection toggles, subtitle-video output options, subtitle quality selection, and safer confirm/cancel behavior.
- Simplified sidebar subtitle quality controls into independent fast/balanced/precise scopes for regular work, iCloud, and NAS, while preserving shared model settings per quality preset.
- Improved subtitle editor behavior for STT candidate selection, text replacement, playhead stability, zoom retention across middle-segment transitions, and dirty-state save prompts.
- Expanded gap simulator behavior so parameter tuning, split/delete criteria, confirmed cut boundaries, and provisional cut boundaries can be simulated together.
- Optimized timeline and subtitle canvas rendering with cache-aware painting, dirty-region redraw paths, and GPU-capable widget choices where safe.
- Added Ollama startup/readiness retry handling and reduced misleading shutdown logs by passing the correct `app exit`, `home navigation`, or `pipeline stop` cleanup context.
- Removed stale temporary files and regenerated the project file structure as an actual tree without review-note sections.
- Rewrote the five handoff documents in English with non-overlapping roles so a future chat can continue from `AGENTS.md` alone.

## Compatibility Notes

- The shared pipeline requirement applies to single-file, multiclip, folder queue, iCloud, and NAS modes.
- macOS and Windows remain supported targets. Path handling must continue to cover Korean filenames, spaces, backslashes, subprocess entry points, ffmpeg/ffprobe, faster-whisper workers, and PyQt6 runtime behavior.
- `core/runtime/config.py` remains the source of truth for `APP_VERSION`.
- The launcher script outside the repository, `/Users/u_mo_c/Downloads/ai_subtitle_studio.command`, was updated locally to hide a noisy macOS TSM input-method warning. It is outside the Git repository and is not part of this commit.

## Verification

Completed verification for this release:

- `./venv/bin/python -m pytest -q` (`465 passed`)
- `./venv/bin/python -m compileall -q main.py core ui tests`
- `bash -n /Users/u_mo_c/Downloads/ai_subtitle_studio.command`
- `git diff --check`
- source-tree temporary/cache scan

## Next Direction

The next major planned work is `PHASE3_LORA_GROUND_TRUTH_TRAINING`: a persistent personalization system that imports verified media/subtitle pairs, builds a truth table, learns subtitle style and timing rules, searches settings against ground truth, and applies learned recommendations across all processing modes.
