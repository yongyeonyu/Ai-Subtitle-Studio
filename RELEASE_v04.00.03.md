# RELEASE v04.00.03

Release date: 2026-05-13
Phase: MAC_NATIVE_APPSTORE_V4_0_3_RELEASED
Base branch: `codex/mac-native-appstore`
Immediately previous release: `v04.00.02`
Release app version: `04.00.03`

## Summary

v04.00.03 is a playback, cut-boundary navigation, project-persistence, and speaker-aware subtitle release for the macOS Apple Silicon branch. It keeps the native-first macOS routing from v04.00.02, then fixes the startup and editor regressions that were slowing app launch, desynchronizing the playhead, dropping timeline labels during playback, losing STT1/STT2 state on project reload, and missing exact hard-cut landings in similar-color footage.

The release also finishes a full-stack speaker-aware path: whole-audio speaker pre-assignment before Whisper finalization, word-level speaker propagation, and Netflix-style multiline overlap captions with project persistence.

## Changes Since v04.00.02

- Delayed interrupted personalization-job recovery until after the first window becomes visible, reducing startup latency.
- Deferred Home-idle learning restarts until editor cleanup and foreground busy-state release complete, avoiding repeated editor/runtime cleanup loops.
- Preserved STT1/STT2 preview and candidate tracks inside project JSON so reload no longer depends on sidecar `stt1.srt` and `stt2.srt`.
- Kept final subtitle timing frame-quantized on save/load and prevented lingering audio-only provisional cut guides from rendering as roughcut precision markers after project reopen.
- Added a visual-jump cut search path for `<<` and `>>` using grayscale/edge residual checks, dense optical flow, and follower rollback verification to land on exact hard-cut frames in similar-color scenes.
- Exposed in-progress UI feedback for visual cut search controls and bounded status progress fills that stop at `99%` until true completion.
- Switched macOS playback preference to the VLC-backed runtime path, added monotonic playhead interpolation, and fixed playhead overlay ghost artifacts.
- Kept the playhead fixed while dragging subtitle segment diamonds or edge handles.
- Restored non-subtitle timeline labels during playback and normalized STT, subtitle, speaker, and score font sizes on the canvas.
- Added ChatGPT Codex CLI login/status controls in settings and exposed Codex subscription-backed models in both subtitle LLM and roughcut LLM model lists.
- Added whole-audio speaker pre-assignment before Whisper finalization, propagated speaker IDs to word timestamps, and generated Netflix-style multiline overlap captions such as `- line A / - line B` while preserving `speaker_list`.

## Code Review Notes

- Reviewed the new speaker pre-assignment path and removed a release-blocking regression that would have disabled the direct FFmpeg chunk fast path for unrelated single-speaker work.
- Reviewed playback/timeline UI changes and updated the one stale timeline font-size test that still expected the old STT preview size.
- Re-ran the full repository regression suite after both review fixes instead of relying only on targeted tests.

## Compatibility Notes

- `core/runtime/config.py` is the source of truth for `APP_VERSION` and now reports `04.00.03`.
- `core/project/project_format.py` now marks newly saved project payloads as schema version `04.00.03`.
- This branch remains macOS-only and Apple Silicon first.
- The ChatGPT Codex CLI path requires a locally installed and authenticated `codex` binary; API-key-backed providers remain available.
- The speaker-aware overlap subtitle path preserves `speaker_list` metadata in project JSON and color SRT output, but plain SRT remains text-only by format design.

## Verification

Completed verification for this release:

- `venv/bin/python -m compileall -q main.py core ui tests`
- `git diff --check -- .`
- `QT_QPA_PLATFORM=offscreen venv/bin/python -m pytest -q`
  - `1681 passed, 5 subtests passed in 84.32s`
- `swift test` in `native/macos/AIStudioNative`
  - `16 tests, 0 failures`
- `packaging/macos/build_beta_dmg.sh`
  - built, signed, validated app bundle and created `dist/macos/AI Subtitle Studio-04.00.03-macOS.dmg`

Additional targeted verification during review:

- `venv/bin/python -m pytest -q tests/test_subtitle_line_breaks.py tests/test_media_processor_overlap.py`
  - `61 passed in 1.53s`
- `QT_QPA_PLATFORM=offscreen venv/bin/python -m pytest -q tests/test_timeline_hit_targets.py::TimelineHitTargetTests::test_native_inline_editor_routes_canvas_click_to_exact_cursor_position`
  - `1 passed in 0.56s`

Known warnings or limits:

- App Store credentialed upload was not attempted in this release pass because no Apple signing or upload credentials were provided in the environment.
- DMG notarization was skipped because `NOTARY_KEYCHAIN_PROFILE` was not set; Gatekeeper rejection remained expected for the ad-hoc local validation build.

## Next Direction

The next risky area is end-to-end speaker-aware generation quality on long real projects: verify that whole-audio speaker pre-assignment improves overlap caption quality without over-splitting single-speaker narration, then keep the native-first playback and visual cut-boundary paths benchmarked against the canonical local fixtures.
