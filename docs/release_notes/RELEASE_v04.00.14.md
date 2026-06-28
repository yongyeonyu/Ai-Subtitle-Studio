# RELEASE v04.00.14

Release date: 2026-05-24
Phase: MAC_NATIVE_APPSTORE_V4_0_14_RELEASED
Base branch: `main`
Immediately previous release: `v04.00.13`
Release app version: `04.00.14`

## Summary

v04.00.14 is a Mac-native subtitle pipeline hardening release. It keeps the existing UI/UX scenario intact while splitting more subtitle generation hot paths into Swift/C++ native helpers and fixing the real Macau editor/timeline drift cases where STT1/STT2 evidence, final subtitle segments, and the left subtitle editor could disagree after save/reopen or roughcut completion.

This release also improves Apple Silicon resource planning for STT2/precision passes, audio-route/VAD preservation, global canvas diagnostics, and post-generation playback responsiveness without relaxing subtitle quality gates.

## Changes Since v04.00.13

- Added Swift/C++ backed subtitle-core helpers for deterministic compute surfaces.
  - Native contracts now cover subtitle segment summaries, STT segment summaries, timing metrics, global canvas summaries, waveform summaries, STT lattice matching, LoRA selective merge policy, STT duration-first ordering, transcribe worker timeout/straggler policy, and audio-route filter decisions.
  - Python facades keep fallback behavior and parity tests so native helpers can fail closed without changing the user workflow.
- Hardened Apple Silicon resource allocation.
  - STT2/recheck and precision passes can request fuller ANE/GPU worker budgets instead of being capped by the initial configured worker count.
  - Native resource summaries now keep STT2 visible as its own task when selective recheck is active.
- Fixed Macau subtitle/editor/timeline drift regressions.
  - Final subtitle rows are canonicalized once for editor, timeline, save/reopen, and roughcut consumers.
  - External STT1/STT2 candidates are reattached by safe time overlap when LLM split/re-timing means frame-exact matching is no longer valid.
  - Workspace restore now syncs by playhead time instead of stale text-block index, and it prevents delayed initial fit timers from overwriting the restored 8-second editing window.
- Preserved STT1/STT2 evidence lanes after post-generation cleanup.
  - Ghost rows are cleaned without deleting the live STT preview lane that the user needs for candidate comparison.
- Fixed timeline interaction and visual regressions.
  - Playback entry points restart the playhead timer so video, timeline, and editor stay on the same clock.
  - Seeking into a silent gap syncs the editor to the nearest real subtitle instead of leaving it on an unrelated old row.
  - The 8-second window dialog cancel path releases lingering Qt focus/grab/cursor state so toolbar buttons keep working.
  - Roughcut visual markers are widened for readability but clamped so adjacent markers do not overlap.
  - Timeline focus borders are moved up by border thickness so the cyan/green lower edges remain visible.
- Tightened noisy-audio routing without weakening quality.
  - Confident audio-route decisions preserve the baseline VAD configuration instead of letting an aggressive audio filter force a mismatched VAD path.
  - High-risk audio only hints STT2 rescue when confidence is low enough to justify the extra pass.

## Code Review Notes

- Review focused on the two highest-risk surfaces: subtitle text/timing ownership and native helper parity.
- The drift root cause was not one single painter bug. It was a data ownership split: saved final rows, STT candidates, restored editor cursor block, and timeline view timers could all point at different post-processed rows. The fix makes final row ordering canonical and uses playhead-time synchronization for reopen/seek paths.
- Roughcut completion no longer calls fit-to-view as a side effect. That preserves the user's current editing window and avoids the visible "screen moves back" behavior after LLM completion.
- DMG/sign/notarization/App Store upload were not run as part of this release because DMG packaging is only run when explicitly requested.

## Verification

Completed verification for this release:

- Static and syntax checks
  - `git diff --check -- .`
  - `./venv/bin/python3.11 -m compileall -q main.py core ui tests tools`
  - Result: OK
- Full Python regression suite
  - `./venv/bin/python3.11 -m pytest -q`
  - Result: `2750 passed, 1 warning, 5 subtests passed`
- Swift native core tests
  - `swift test`
  - Result: `84 XCTest checks passed` plus `2 Swift Testing checks passed`
- macOS app bundle build and validation
  - `./packaging/macos/build_app_bundle.sh`
  - `./packaging/macos/validate_app_bundle.sh`
  - Result: bundle validation passed for `dist/macos/AI Subtitle Studio.app`
- One-command app smoke QA
  - `./venv/bin/python3.11 tools/qa_suite_runner.py quick`
  - Result: pass, `failed_count=0`
  - Artifact: `output/manual_verification/latest/qa_suite_quick_20260524_150340`

## Remaining Risk

- The active `ACTION_ITEMS.md` native split plan remains open because further migration still needs fixture-level parity and real-app benchmark proof before defaulting more compute paths to native.
- Long High-mode media can still enter memory warning or critical pressure during model-heavy phases; this release improves cleanup/resource planning but does not remove the need for continued memory-pressure profiling.
