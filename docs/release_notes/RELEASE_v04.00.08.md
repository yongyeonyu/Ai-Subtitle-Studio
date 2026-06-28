# RELEASE v04.00.08

Release date: 2026-05-17
Phase: MAC_NATIVE_APPSTORE_V4_0_8_RELEASED
Base branch: `main`
Immediately previous release: `v04.00.07`
Release app version: `04.00.08`

## Summary

v04.00.08 is a mode-policy, editor-interactivity, and timeline-convergence stabilization release for the macOS Apple Silicon branch. It keeps the broader subtitle-quality and UX refactors already in the working tree, then focuses this release cutoff on three things that were still risky at ship time: centralizing Fast/Auto/High/STT mode ownership, making post-generation roughcut completion return control to the editor without blocking save or quit, and making late layout correction converge instead of stopping one pass short.

The practical goal of this release is to make the current branch safer to continue from. User-facing mode selection now has one explicit owner, autopilot no longer writes back mode-managed audio/VAD routes that can fight the selected mode, roughcut completion no longer leaves the editor in a half-locked state while waiting on a heavy project re-save, and the editor's video/timeline split has a bounded follow-up rebalance path so small visual gaps do not survive the first pass after open or resize.

## Changes Since v04.00.07

- Centralized user-facing processing-mode ownership in `core/mode_manager.py`.
  - Fast, Auto, High, and STT are now treated as the only user-facing processing abstractions.
  - Mode-managed route keys such as audio preset, VAD choice, and ensemble gates are explicitly separated from user-selectable model identities.
  - Per-mode persistence is now scoped to STT1, STT2, subtitle LLM, and roughcut LLM model identity choices rather than low-level route overrides.
- Hardened LoRA/autopilot settings persistence around the new mode-manager policy.
  - `core/personalization/settings_autopilot.py` now skips mode-managed route keys when promoting learned settings back into saved defaults.
  - Tests now verify that mode-managed audio selection stays untouched while safe user-selected values can still persist.
- Reduced post-generation editor lock contention in the roughcut completion path.
  - `core/project/project_manager.py` now exposes `save_project_roughcut_state(...)` so post-generation roughcut metadata can be persisted without forcing a full project save at the same moment.
  - `ui/editor/editor_roughcut_draft.py` now clears post-generation busy/input-lock state explicitly in `finally`, restoring segment-edge edits, diamond edits, save, and quit responsiveness after subtitle generation.
  - `ui/main/main_runtime_cleanup.py` now clears timeline input-lock flags during forced editor-idle recovery so cleanup and interaction state cannot diverge.
- Made late editor shell rebalancing converge instead of leaving a small persistent gap.
  - `ui/editor/editor_widget.py` now allows a few bounded follow-up rebalance passes after resize/open when the first pass still leaves a visible mismatch between the video area and timeline allocation.
  - The goal is not continuous relayout churn; it is a short convergence window that brings the split into the expected tolerance band.
- Continued the active v04.00.08 refactor/documentation surfaces already present in the working tree.
  - Dedicated NAS/iCloud auto-source UX now lives under `ui/home/ux/auto_source_settings_dialog.py`.
  - Shared Apple-black popup and palette tokens now live under `ui/ux/`.
  - Timeline roughcut paint preparation now has a dedicated helper surface in `ui/timeline/timeline_roughcut_paint.py`.

## Code Review Notes

- Fixed the release-blocking regression in `tests/test_editor_stable_frames.py::EditorStableFrameTests::test_editor_rebalances_video_gap_into_timeline_height` by letting the video/timeline rebalance flow schedule a bounded number of follow-up passes instead of treating the first pass as final.
- Fixed the release-blocking regression in `tests/test_lora_settings_autopilot.py::LoraSettingsAutopilotTests::test_autopilot_smoothly_promotes_safe_lora_settings` by aligning autopilot write-back policy with `core/mode_manager.py`; mode-managed routes are now skipped instead of silently overwriting mode-owned settings.
- Re-verified the full Python suite after the code-review fixes before cutting this release.

## Compatibility Notes

- `core/runtime/config.py` is the source of truth for `APP_VERSION` and now reports `04.00.08`.
- `core/project/project_format.py` now marks newly saved project payloads as schema version `04.00.08`.
- This branch remains macOS-only and Apple Silicon first.
- DMG packaging remains opt-in and was not re-run for this release batch because the user did not request packaging work.

## Verification

Completed verification for this release:

- `PYTHONPATH=/Users/u_mo_c/Downloads/ai_subtitle_studio venv/bin/python -m pytest -q`
  - `2145 passed, 5 subtests passed in 279.49s (0:04:39)`
- `PYTHONPATH=/Users/u_mo_c/Downloads/ai_subtitle_studio venv/bin/python -m pytest -q tests/test_editor_stable_frames.py::EditorStableFrameTests::test_editor_rebalances_video_gap_into_timeline_height tests/test_lora_settings_autopilot.py::LoraSettingsAutopilotTests::test_autopilot_smoothly_promotes_safe_lora_settings`
  - `2 passed in 2.18s`
- `QT_QPA_PLATFORM=offscreen venv/bin/python` smoke for `ui.main.main_window.MainWindow`
  - `offscreen_mainwindow_smoke_ok`
- `venv/bin/python -m compileall -q main.py core ui tests`
- `git diff --check -- .`
- `swift test` in `native/macos/AIStudioNative`
  - `36 tests, 0 failures`

Additional runtime-release note:

- A fresh guided real-media automation run was not completed in this batch. A pre-existing user-session app instance did not answer `venv/bin/python tools/appctl.py --timeout 3 ping` within timeout, so this release gate used the full automated suite plus offscreen `MainWindow` smoke instead of a new guided media run.

## Next Direction

The next highest-value follow-up is still to close the remaining subtitle-quality and editor-behavior items in `ACTION_ITEMS.md`, especially final subtitle versus STT evidence lock-in, repeatable real-media regression packs, remaining `ux/` extraction, and deeper timeline/session-model splits, while keeping the current mode-manager ownership and post-generation editor interactivity stable.
