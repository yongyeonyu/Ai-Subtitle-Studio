# RELEASE v04.00.05

Release date: 2026-05-14
Phase: MAC_NATIVE_APPSTORE_V4_0_5_RELEASED
Base branch: `codex/release-v04.00.05`
Immediately previous release: `v04.00.04`
Release app version: `04.00.05`

## Summary

v04.00.05 is a runtime ETA, native helper, playback subtitle visibility, and editor-save recovery update for the macOS Apple Silicon branch. It keeps the VAD/mode hardening from v04.00.04, then makes queue/startup ETA more data-aware, moves more deterministic planners into the Swift core package, restores playback subtitle detail that regressed during timeline cleanup, and hardens the editor so transient STT preview or generation-complete races do not wipe the visible subtitle state during save/reload.

The release goal is to make long-running generation and review feel more trustworthy: users should see a better ETA before and during processing, should not lose subtitle text while playback is active, and should not carry stale cut-boundary helper lines or transient STT preview rows into the final editor state.

## Changes Since v04.00.04

- Replaced the flat runtime history estimator with `core.runtime_eta`, which records mode, STT1/STT2 pairing, LLM/audio/VAD choices, media duration/FPS/resolution, queue position, and cache state, then weights recent runs more heavily when predicting ETA.
- Routed queue headers, queue rows, startup diagnostics, single-pipeline startup ETA, multiclip ETA, and backend completion history writes through the shared runtime ETA payload so expected-time math is consistent across screens and processing modes.
- Added Swift-native `RuntimeETAEstimator`, `StartupDiagnostics`, and `CutBoundaryCachePlanner` helpers, together with Python bridges and CLI coverage, while keeping Python fallbacks for parity and packaged-app safety.
- Emitted lightweight raw STT preview rows immediately for STT1/STT2 timeline lanes, but kept transient STT previews out of the editor text pane so only committed subtitle segments render as editable text.
- Hardened generation-complete and manual save recovery to rebuild from backend subtitle backups when a temporary empty-segment state appears just before autosave or project save finishes.
- Added completion-card subtitle self-review score surfacing so finished queue items show the final rounded quality score beside elapsed/expected time in the Home sidebar.
- Restored playback subtitle visibility by forcing full segment-text detail during playback, reapplying hidden subtitle overlays when provider context still covers the current time, and keeping final subtitle text visible in the timeline lanes while the video is playing.
- Sanitized verified visual cut rows so stale audio-provisional styling is stripped, then hid follower-checked helper rows plus terminal end-frame markers from the normal official-boundary UI while still preserving the stored project metadata.
- Hardened Codex roughcut draft execution with wider chunk/context defaults, longer timeout settings, proper roughcut override-model inheritance, and clean fallback to local-rule drafts after Codex CLI timeout.
- Replaced several remaining silent cleanup/error-swallow paths in editor teardown, export-dialog settings/SRT scratch cleanup, diarization cache I/O, VAD strict metadata persistence, and folder/project helper code with typed handling plus logging.
- Added a documented first native-library bundle plan in `NATIVE_LIB_PLAN.md` so future migrations prefer deterministic JSON-in/JSON-out planners instead of pushing orchestration-heavy Python files directly into a compiled library.

## Code Review Notes

- Reviewed the boundary-marker cleanup to ensure only helper/provisional auto-cut rows are hidden after verification; manual or non-cut verified visual markers still keep their visible official style.
- Reviewed the editor/timeline split so live STT preview rows improve realtime feedback without repopulating the editor text pane or overwriting committed subtitle rows.
- Reviewed remaining `except: pass` hotspots in editor/export/audio/cache cleanup paths and converted the release-critical ones to typed/logged handling so teardown/save/export failures no longer disappear silently.
- Reviewed the Swift migration scope and kept ETA/diagnostic/cache logic as narrow planner-style helpers with Python fallbacks instead of attempting to native-port the larger editor or pipeline orchestrators.

## Compatibility Notes

- `core/runtime/config.py` is the source of truth for `APP_VERSION` and now reports `04.00.05`.
- `core/project/project_format.py` now marks newly saved project payloads as schema version `04.00.05`.
- Runtime ETA history now uses schema `ai_subtitle_studio.runtime_eta_store.v2`; `core.time_history` remains as a compatibility wrapper so older imports continue to work.
- Project cut-boundary metadata still stores follower-checked/provisional rows and terminal helper boundaries even though the normal editor UI now hides them after verification.
- This branch remains macOS-only and Apple Silicon first.

## Verification

Completed verification for this release:

- `venv/bin/python -m compileall -q main.py core ui tests`
- `git diff --check -- .`
- `QT_QPA_PLATFORM=offscreen venv/bin/python -m pytest -q`
  - `1704 passed, 5 subtests passed in 317.48s (0:05:17)`
- `swift test` in `native/macos/AIStudioNative`
  - `23 tests, 0 failures`
- `packaging/macos/build_beta_dmg.sh`
  - Built, signed, validated, and verified `/Users/u_mo_c/Downloads/ai_subtitle_studio/dist/macos/AI Subtitle Studio-04.00.05-macOS.dmg`
  - Gatekeeper assessment failed as expected for the ad-hoc local test build; notarization was skipped because `NOTARY_KEYCHAIN_PROFILE` was not configured

Additional targeted verification during review:

- `QT_QPA_PLATFORM=offscreen venv/bin/python -m pytest -q tests/test_timeline_segment_colors.py tests/test_timeline_hit_targets.py::TimelineHitTargetTests::test_scan_boundary_hides_checked_audio_rows_from_ui_preview_only tests/test_timeline_hit_targets.py::TimelineHitTargetTests::test_official_boundary_marker_visual_distinguishes_manual_verified_rows`
  - `49 passed in 1.42s`
- `venv/bin/python -m compileall -q ui/timeline/timeline_segment_style.py ui/timeline/timeline_paint.py tests/test_timeline_segment_colors.py`
- `git diff --check -- ui/timeline/timeline_segment_style.py ui/timeline/timeline_paint.py tests/test_timeline_segment_colors.py`

## Next Direction

The next useful follow-up is to keep calibrating runtime ETA against real benchmark media while moving only the next deterministic planner-style families into the Swift core package, especially where JSON-in/JSON-out parity can be tested before any broader orchestration migration is attempted.
