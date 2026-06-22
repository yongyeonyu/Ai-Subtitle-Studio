# RELEASE v04.00.12

Release date: 2026-05-21
Phase: MAC_NATIVE_APPSTORE_V4_0_12_RELEASED
Base branch: `auto_action_item`
Immediately previous release: `v04.00.11`
Release app version: `04.00.12`

## Summary

v04.00.12 is an editor stability and release-hygiene release. It keeps subtitle generation quality policy unchanged, but fixes the user-reported manual-save roughcut launch, timeline/text editing redraw instability, playhead mode persistence, shadow playhead behavior, and normal app-close termination path.

The release also finalizes the current idea/action/native planning cleanup: `idea_item.md` is the integrated execution source, `ACTION_ITEMS.md` and `NATIVE_LIB_PLAN.md` are pointer documents, older release notes before `v04.00.07` were removed, and `lesson_n_learned.md` now stores repeat-prevention notes.

## Changes Since v04.00.11

- Fixed manual save unexpectedly starting roughcut LLM.
  - `EditorSaveManagerMixin._on_save()` now cancels pending post-generation roughcut work before the no-change early return.
  - Manual save auto-project creation now calls `create_project(..., prefill_analysis_artifacts=False)` so saving an externally loaded SRT does not prefill roughcut analysis.
  - Stale Qt roughcut timer callbacks now respect the cancelled auto-schedule epoch.
- Stabilized timeline/editor 2D rendering on macOS.
  - Main timeline and minimap now use the QWidget/QPainter `qwidget-2d` path as the visible render owner.
  - QML/SceneGraph timeline body and playhead overlay rendering are disabled for the default editor path to avoid ghost playheads, stale segment paint, and canvas compositing artifacts.
  - Inline subtitle segment editing remains inside the subtitle segment text box and suppresses duplicate background text while editing.
- Fixed playhead and keyboard interaction regressions.
  - Up/down selected playhead mode/color is preserved across left/right movement, handle drag, and click seeking.
  - Cut-boundary magnet search now leaves the expected shadow playhead at the snapped boundary.
  - Space inside text inputs remains text input; Space after inline edit commit toggles canvas playback again.
  - Bare Shift in subtitle text editing no longer starts playback.
- Hardened video/player cleanup and app close behavior.
  - QWidget video control bar fallback no longer emits QML `rootObject` warnings.
  - Video shutdown only disconnects Qt signals that actually exist on the player object.
  - macOS exit watchdog is opt-in and busy close uses a delayed clean Python fallback instead of leaving `.command` with `Terminated: 15`.
- Cleaned release/control documents.
  - `AGENTS.md` now records the current Apple Silicon developer / QA persona rules, waste-note rule, and lesson-note rule.
  - `ACTION_ITEMS.md` and `NATIVE_LIB_PLAN.md` point to `idea_item.md`.
  - `check_list.md` and release notes older than `RELEASE_v04.00.07.md` were deleted.

## Code Review Notes

- Review found the manual-save bug had two paths: a pending roughcut timer path and the project-create prefill path. Both are now covered by tests.
- Review found the safest macOS timeline path is a single visible 2D paint owner. The compatibility overlay object is kept for state bookkeeping, but visible playhead rendering is owned by the canvas.
- Maintenance guard initially caught a new silent exception and changed large-file/function budget regressions. The patch was tightened until `tools/check_maintenance_budget.py --json` returned clean.
- Subtitle generation algorithms, STT model choices, LLM cleanup policy, and quality scoring were not changed in this release.

## Compatibility Notes

- `core/runtime/config.py` is the source of truth for `APP_VERSION` and now reports `04.00.12`.
- `core/project/project_format.py` now marks newly saved project payloads as schema version `04.00.12`.
- This branch remains macOS-only and Apple Silicon first.
- DMG packaging remains opt-in and was not run for this release.

## Verification

Completed verification for this release:

- Focused editor/timeline/runtime unittest sweep
  - `./venv/bin/python -m unittest tests.test_editor_autosave_cleanup tests.test_editor_roughcut_draft tests.test_editor_pipeline_partial_rerun tests.test_timeline_hit_targets tests.test_subtitle_text_edit_keys tests.test_timeline_playhead_fit tests.test_timeline_render_cache tests.test_video_player_widget tests.test_native_macos_exit tests.test_sidebar_terminal_layout -q`
  - Result: `552 tests OK`
- Syntax, diff hygiene, and maintenance guard
  - `./venv/bin/python -m compileall -q core ui tests tools`
  - `git diff --check -- core ui tests tools AGENTS.md ACTION_ITEMS.md NATIVE_LIB_PLAN.md idea_item.md README.md File_structure.txt CODEMAP.md test_result.md lesson_n_learned.md`
  - `./venv/bin/python tools/check_maintenance_budget.py --json`
  - Result: OK, `issue_count=0`
- Swift native-core checks
  - `swift test --package-path native/macos/AIStudioNative`
  - Result: `38 tests OK`
- One-command full QA runner on refreshed app bundle
  - `./packaging/macos/build_app_bundle.sh`
  - `./venv/bin/python tools/qa_suite_runner.py full`
  - Result: pass, `scenario_count=7`, `failed_count=0`
  - Artifact: `output/manual_verification/latest/qa_suite_full_20260521_022256`
  - Scenarios: `editor_compact_macau`, `video_menu_macau`, `save_export_macau`, `menu_stt_lora_macau`, `tinyping_fast_60s`, `tinyping_auto_60s`, `tinyping_high_60s`

## Remaining Risk

- The timeline renderer is intentionally conservative 2D-first now. If future GPU/QML/Metal UI experiments resume, they should be isolated behind explicit tests and feature flags.
- Full QA passed on the refreshed bundle. If command-surface changes land later, rebuild the bundle before interpreting any `unknown_command` failure.
