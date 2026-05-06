# RELEASE v03.23.00

Release date: 2026-05-07
Phase: STABLE_EDITOR_FRAMES_RELEASED
Base branch: `main`
Immediately previous release: `v03.22.00`
Release app version: `03.23.00`

## Summary

v03.23.00 is the Stable Editor Frames release. It builds on v03.22.00 by keeping Fast mode responsive while selectively rescuing low-confidence subtitle regions, preventing post-generation busy UI and playback stalls, removing duplicate Mode controls from subtitle review settings, and stabilizing the editor layout with fixed render frames for text, video, and timeline surfaces.

This release note intentionally references only v03.22.00 as the previous checkpoint. Older cumulative history remains in older `RELEASE_v*.md` files and should not be copied into handoff documents.

## Changes Since v03.22.00

- Added selective low-score STT2 rescue for Fast mode so only weak STT1 spans are rechecked instead of rerunning the full expensive accuracy path.
- Kept Fast mode overlap and runtime review settings lightweight while preserving minimum subtitle quality guards for obviously risky regions.
- Deferred automatic subtitle quality review while the editor is locked or video playback is active, reducing playback stutter immediately after generation.
- Cleared busy cursor and processing indicators after generation, quality review, save, and deferred cleanup paths so the editor does not remain in an hourglass state.
- Throttled background prefetch, post-generation roughcut work, model release, and cleanup work while video is actively playing.
- Removed the duplicate Mode selector from the subtitle review settings tab while preserving the canonical Mode controls elsewhere.
- Added `StableRenderFrame` slots for the editor text pane, video preview, and timeline so child widget state changes do not resize the main editor surfaces when Start is pressed.
- Extended start-layout snapshots to preserve stable frame sizing and splitter positions during generation startup.
- Added settings-driven GPU rendering policy for per-frame and whole-editor rendering scopes while keeping OpenGL widgets opt-in for stability.
- Routed editor, video, and timeline render backend labels through their own frame features.
- Added tests covering stable editor frame ownership, frame-based GPU policy, settings-forced video backend selection, and global Qt OpenGL settings.

## Compatibility Notes

- `core/runtime/config.py` remains the source of truth for `APP_VERSION`.
- The user-facing Mode values remain `fast`, `auto`, and `high`; legacy STT quality compatibility remains unchanged.
- GPU rendering remains conservative by default. `editor_rendering_gpu_scope` can opt into `frame` or `all`, and `editor_rendering_gpu_frames` can target individual surfaces such as `editor`, `video`, or `timeline`.
- `editor_rendering_force_qt_opengl` is required before global Qt OpenGL setup is applied from settings.
- Video preview still prefers the lightweight mpv GPU backend in real app runs when available, with QtMultimedia retained for test/offscreen safety.
- macOS and Windows remain supported targets, including Korean paths, spaces, subprocess handling, ffmpeg/ffprobe, PyQt6, OpenGL/SceneGraph, and local media cache behavior.
- The handoff set remains `AGENTS.md`, `ACTION_ITEMS.md`, `File_structure.txt`, `README.md`, and the latest `RELEASE_v*.md`.

## Verification

Completed verification for this release:

- `venv/bin/python -m pytest -q`
  - `915 passed, 2 subtests passed in 103.29s`
- `venv/bin/python -m compileall -q main.py core ui tests`
- `git diff --check -- .`

## Next Direction

No active or parked backlog remains in `ACTION_ITEMS.md`. Future work should start from user-requested product goals rather than old parked items, with the current priority remaining accuracy before speed.
