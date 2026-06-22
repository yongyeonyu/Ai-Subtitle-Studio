# RELEASE v04.00.15

Release date: 2026-05-25
Phase: MAC_NATIVE_APPSTORE_V4_0_15_RELEASED
Base branch: `main`
Immediately previous release: `v04.00.14`
Release app version: `04.00.15`

## Summary

v04.00.15 is a behavior-preserving cleanup and stabilization release after the subtitle generation domain split. It keeps subtitle quality policy and UI/UX behavior intact while reducing long-file ownership, preserving STT1/STT2 and LLM pipeline parity, and tightening the release-time compatibility seams introduced by the refactor.

This release also carries the recent editor/save/export/timeline fixes, the project-info terminal toggle behavior, source-app quick smoke support, and a safer post-generation runtime cleanup path for playback responsiveness.

## Changes Since v04.00.14

- Completed the current long-file cleanup pass without changing subtitle policy.
  - `core/audio/media_processor_transcribe.py`, `core/audio/media_processor_audio.py`, `core/engine/subtitle_engine.py`, `tools/benchmark_subtitle_pipeline_variants.py`, `core/roughcut/editor_draft.py`, `ui/timeline/timeline_paint.py`, `ui/timeline/timeline_widget.py`, `ui/main/main_window.py`, and related owners now delegate to focused helper modules.
  - `doc/reference/LONG_FILE_OWNERSHIP_MAP.md` records the current under-2000-line runtime ownership map and verification anchors.
- Hardened refactor compatibility surfaces found during release review.
  - Benchmark scoring and roughcut chunk planning now inject native backends by argument instead of temporarily mutating module globals.
  - Split STT modules continue honoring the legacy test/runtime patch points for memory-pressure stage and parallel worker planning.
  - The split subtitle LLM runtime imports the canonical subtitle text cleaner directly.
- Updated editor rendering ownership audits for the new helper-module split while keeping Qt Widgets/QPainter as the default 2D owner.
- Fixed project-info terminal temporary text clearing so the sidebar terminal restores correctly after the second click.
- Preserved recent UI and workflow fixes in the release set:
  - Video filename display uses the widened one-line right-aligned footer area.
  - Subtitle segment selection boxes are removed from segment cards.
  - Export dialog supports subtitle-only versus video+subtitle output selection.
  - Subtitle output buttons now open the export settings dialog directly instead of showing an intermediate popup menu.
  - Project save path can prioritize fast SRT saving before heavier project persistence.
  - Post-generation playback cleanup is deferred to avoid immediately stalling the video player.

## Code Review Notes

- Review focused on refactor-induced regressions rather than new feature work.
- The highest-risk issue found was temporary global mutation in extracted helper wrappers. That is now replaced with explicit backend injection.
- The full test run also caught three compatibility misses where extracted STT modules bypassed old patch points. Those were fixed by routing through compatibility helpers.
- `tools/check_maintenance_budget.py --json` still reports changed-scope long-file and silent-exception backlog items. Those are tracked as continuing cleanup work and were not treated as this release's blocking gate because the active release gate is behavior parity and app smoke.
- DMG/sign/notarization/App Store upload were not run. DMG packaging remains opt-in only.

## Verification

Completed verification for this release:

- Static and syntax checks
  - `venv/bin/python -m compileall -q main.py core ui tests tools`
  - `git diff --check -- .`
  - Result: OK
- Full Python regression suite
  - `venv/bin/python -m pytest -q`
  - Result: `2854 passed, 1 warning, 5 subtests passed`
- Swift native core tests
  - `swift test --package-path native/macos/AIStudioNative`
  - Result: `84 XCTest checks passed` plus `2 Swift Testing checks passed`
  - Historical release-time note: the current source-app line no longer treats the in-repo Xcode/Swift migration package as a default validation entrypoint.
- Source-app quick smoke QA
  - `AI_SUBTITLE_STUDIO_QA_USE_SOURCE=1 venv/bin/python tools/qa_suite_runner.py quick`
  - Result: pass, `failed_count=0`
  - Artifact: `output/manual_verification/latest/qa_suite_quick_20260525_141648`

## Remaining Risk

- Maintenance-budget cleanup is not finished; several changed helper files still exceed the stricter 1200-line soft limit or contain silent exception handlers inherited during the split.
- Long High-mode media can still enter memory warning/critical pressure during model-heavy phases; this release keeps the existing quality-first behavior and compatibility guards rather than lowering workload.
