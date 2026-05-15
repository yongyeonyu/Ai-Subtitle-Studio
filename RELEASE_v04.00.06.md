# RELEASE v04.00.06

Release date: 2026-05-16
Phase: MAC_NATIVE_APPSTORE_V4_0_6_RELEASED
Base branch: `main`
Immediately previous release: `v04.00.05`
Release app version: `04.00.06`

## Summary

v04.00.06 is an editor UX, remote verification, and shutdown-hardening release for the macOS Apple Silicon branch. It keeps the runtime ETA and save/recovery work from v04.00.05, then focuses on making live editor verification more deterministic from Codex, unifying timeline-open behavior across Fast/Auto/High, tightening smart-split and playhead editing flows, hardening LoRA/background shutdown, and smoothing Home/sidebar responsiveness during active generation.

The release goal is to reduce "looks different in the real app" gaps: automation can now drive more of the running editor directly, progress/logging is better exposed during roughcut and multiclip work, restart and shutdown paths fail less often, and timeline/playhead editing behavior is more consistent under high zoom and real-media usage.

## Changes Since v04.00.05

- Added a reusable app-automation command path through `core/automation/`, `ui/main/app_command_bridge.py`, and `tools/appctl.py` so a running app can expose deterministic editor actions, status snapshots, and remote verification hooks to Codex.
- Added `tools/remote_verify.py` plus richer runtime capture helpers so status JSON, snapshots, and short reports can be written into `output/manual_verification/latest/` and named verification folders instead of relying on large chat logs.
- Fixed completed-state restart recovery so dead backend-thread restart attempts fall back to a fresh `start_pipeline(..., is_auto_start=True)` path rather than silently reusing invalid backend state.
- Unified initial timeline-fit behavior for raw media open across Fast, Auto, and High so delayed waveform/workspace restore work can no longer leave Fast unfit or High on a mismatched initial zoom.
- Added multiclip automation entry points and fixed a multiclip runtime-state bug where the automation/runtime status path referenced the wrong clip-list source during live processing.
- Promoted roughcut LLM execution into explicit queue/home progress reporting so chunk start/complete/fallback logs now include percent progress and the queue/header time display continues through roughcut rather than appearing done too early.
- Reworked smart split into an explicit right-click `Split Subtitle` mode: the split target is staged visually, inline text editing becomes the only active input, diamond and segment-edge adjustments are blocked during split mode, and Enter commits a split using both the armed playhead position and the current text cursor.
- Added a single shadow-playhead reference line that can be pinned automatically or via automation and used as a magnetic edit target for segment handles, diamonds, and timeline adjustments.
- Reduced high-zoom playback jitter by centering playback follow behavior on frame-based scroll math so the playhead stays visually stable while the background scrolls.
- Hardened editor teardown and shutdown around background LoRA work by adding cancellable subprocess handling, fast detach/shutdown guards, and deleted-Qt-object protection in subtitle text edit focus-loss paths.
- Moved runtime resource usage from the lower sidebar card into the top progress card, reduced unnecessary sidebar re-renders during saved-state blinking, and made the sidebar width fully responsive instead of partially user-resizable.
- Consolidated more repeated coercion and JSON/setting helpers into shared utility modules while keeping project/runtime/timeline/native paths on the same helper semantics.

## Code Review Notes

- Reviewed the media-processor overlap regression and fixed two tests that were still patching the old `core.audio.media_processor.subprocess.Popen` location after the FFmpeg progress logic moved into `core.audio.media_processor_audio`.
- Reviewed the scan-boundary hover coverage and stabilized the flaky UI test by asserting the direct hit-target/hover-state path instead of depending on full-suite-sensitive synthetic mouse-move delivery.
- Reviewed the Home/sidebar refresh path and removed an over-eager nav refresh triggered by saved-status updates, which had made active-generation UI noticeably slower than intended.

## Compatibility Notes

- `core/runtime/config.py` is the source of truth for `APP_VERSION` and now reports `04.00.06`.
- `core/project/project_format.py` now marks newly saved project payloads as schema version `04.00.06`.
- Remote verification artifacts should default to `output/manual_verification/latest/`, with named sibling folders used only when a task needs a preserved archive.
- This branch remains macOS-only and Apple Silicon first.

## Verification

Completed verification for this release:

- `venv/bin/python -m pytest -q`
  - `1950 passed, 5 subtests passed in 120.26s (0:02:00)`
- `venv/bin/python -m compileall -q main.py core ui tests`
- `git diff --check -- .`
- `swift test` in `native/macos/AIStudioNative`
  - `23 tests, 0 failures`
- `packaging/macos/build_beta_dmg.sh`
  - Built, signed, validated, and verified `/Users/u_mo_c/Downloads/ai_subtitle_studio/dist/macos/AI Subtitle Studio-04.00.06-macOS.dmg`
  - Gatekeeper assessment failed as expected for the ad-hoc local test build; notarization was skipped because `NOTARY_KEYCHAIN_PROFILE` was not configured

Additional targeted verification during review:

- `venv/bin/python -m pytest -q tests/test_media_processor_overlap.py -k "ffmpeg_progress_pipe_emits_percent_stage_updates or ffmpeg_progress_suppresses_duplicate_percent_updates"`
  - `2 passed`
- `venv/bin/python -m pytest -q tests/test_timeline_hit_targets.py -k "scan_boundary_hover_sets_cyan_highlight_index"`
  - `1 passed`
- `venv/bin/python -m pytest -q tests/test_cp03_cp04_status_ui.py tests/test_sidebar_terminal_layout.py tests/test_responsive_profile.py`
  - `129 passed`

## Next Direction

The next useful follow-up is to keep reducing broad-exception paths and oversized orchestration shells, especially in `ui/main/main_window.py`, `ui/editor/video_player_widget.py`, and the cut-boundary/audio stacks, while preserving the now-expanded automation surface so real-app verification stays deterministic during future refactors.
