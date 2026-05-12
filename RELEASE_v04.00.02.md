# RELEASE v04.00.02

Release date: 2026-05-12
Phase: MAC_NATIVE_APPSTORE_V4_0_2_RELEASED
Base branch: `codex/mac-native-appstore`
Immediately previous release: `v04.00.01`
Release app version: `04.00.02`

## Summary

v04.00.02 is a stability, project-persistence, and native-readiness release for the macOS Apple Silicon branch. It keeps the v04.00.01 production-native policy, then tightens the paths that were causing slow project reloads, stale STT1/STT2 lanes, lingering provisional cut-boundary markers, slow correction-dictionary cleanup, roughcut LLM fallback behavior, and slow shutdown/foreground interruption.

The release also splits several of the longest Python modules by responsibility. The goal is not cosmetic line-count reduction; it creates smaller seams for Swift/C++ migration while preserving verified behavior.

## Changes Since v04.00.01

- Added canonical project storage formatting with the top-level `video` header first, including frame/FPS duration metadata as the reload contract.
- Kept Swift project read/validation available while making Swift project write opt-in through `AI_SUBTITLE_STUDIO_SWIFT_PROJECT_WRITE` until the native writer can preserve the canonical key-order contract.
- Strengthened project reload behavior for external SRT subtitle assets so final subtitles and STT1/STT2 tracks hydrate through project-path-aware readers instead of resolving relative assets from the current working directory.
- Preserved frame-quantized subtitle/STT timing across save/load so subtitle magnet work cannot mutate original STT1/STT2 timing lanes.
- Added and verified native macOS input-activity helpers so background LoRA/personalization work can stop quickly when mouse or keyboard activity returns.
- Hardened app-exit runtime cleanup so old and new trainer shutdown APIs both receive non-blocking `timeout_sec=0.0` behavior.
- Added native text-cleanup support and tests for faster correction-dictionary application without moving correction data into source-controlled secrets or private user data.
- Preserved roughcut LLM-created major-segment titles when later topic labeling falls back to local heuristics.
- Kept provisional audio/visual cut-boundary data in the project while ensuring follower-reviewed UI state can clear reviewed provisional markers and rely on reviewed middle segments.
- Fixed diamond-edge subtitle timing resize behavior so adjacent segment timing updates without introducing a gap.
- Updated toolbar and multiclip cache tests to match current editor UI and save-manager ownership.
- Ignored `voice_data/` so private voice samples are not accidentally staged or pushed.

## Refactor Notes

- Moved STT worker JSON parsing and cloned chunk-directory setup into `core.audio.transcribe_worker_io`.
- Moved subtitle filtering, global deduplication, tiny-segment absorption, and pre-merge configuration into `core.engine.subtitle_segment_filter`.
- Moved subtitle accuracy utility helpers into `core.engine.subtitle_accuracy_utils`.
- Moved cut-boundary cache validation and save/load helpers into `core.pipeline.cut_boundary_cache`.
- Moved editor segment bulk-load and quality tooltip/signature helpers into `ui.editor.editor_segments_bulk_load`.

## Code Review Notes

- Reviewed project save/load ordering from `save_project()` through `write_project_file()` and verified the raw JSON starts with `video`, `app`, and `version`.
- Reviewed external subtitle/STT asset hydration so direct project reads use the project path for relative asset resolution.
- Reviewed fast-exit cleanup to avoid joining backend threads on the UI path while still signalling backend events, live STT, watchdogs, and personalization trainers.
- Reviewed roughcut topic labeling so LLM-confirmed major segments are not collapsed by heuristic relabeling.
- Reviewed private data handling and added `voice_data/` to ignored runtime/user data.

## Compatibility Notes

- `core/runtime/config.py` remains the source of truth for `APP_VERSION`.
- `core/project/project_format.py` now marks newly saved project payloads as schema version `04.00.02`.
- This branch remains macOS-only and Apple Silicon first.
- Existing v04 project data remains loadable through the runtime hydration path. The release intentionally prioritizes the new canonical v04 project-save format over legacy file-layout compatibility.
- Swift project write is disabled by default for canonical ordering; set `AI_SUBTITLE_STUDIO_SWIFT_PROJECT_WRITE=1` only for native writer experiments.

## Verification

Completed verification for this release:

- `venv/bin/python -m compileall -q main.py core ui tests`
- `git diff --check -- .`
- `swift test` in `native/macos/AIStudioNative`
  - `16 tests, 0 failures`
- `QT_QPA_PLATFORM=offscreen venv/bin/python -m pytest -q tests/test_project_context.py::ProjectContextTests::test_saved_project_writes_video_header_first_and_drops_legacy_runtime_duplicates tests/test_sidebar_terminal_layout.py::SidebarTerminalLayoutTests::test_fast_exit_pause_signals_runtime_without_joining_backend_threads tests/test_stt_lattice.py::STTLatticeTests::test_project_metadata_and_artifact_preserve_lattice_after_save`
  - `3 passed in 1.33s`
- `QT_QPA_PLATFORM=offscreen venv/bin/python -m pytest -q`
  - `1633 passed, 5 subtests passed in 148.82s`

Known warnings or limits:

- DMG/App Store packaging was not rebuilt because this release request did not explicitly ask for installer or distribution package generation.
- GitHub CLI release administration was not available locally because `gh` is not authenticated. Public GitHub release listing returned no release objects, and remote tags before `v03.00.00` were not present.

## Next Direction

Continue moving only behavior-preserving heavy loops into Swift/C++ and keep project persistence centered on the canonical frame/FPS schema. The next risky area is full roughcut LLM output validation against real long projects after the user selects a usable roughcut LLM provider.
