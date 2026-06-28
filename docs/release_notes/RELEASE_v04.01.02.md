# RELEASE v04.01.02

Date: 2026-06-29
Previous release: `v04.01.01`
Release app version: `04.01.02`

## Summary

`v04.01.02` is a focused source-app NLE close/deferred-save boundary checkpoint.

This release fixes the vector-canvas timing interpretation that made raw `subtitle_canvas.vector.v2` rows collapse to invalid zero-duration rows during NLE save/export projection, and it prevents close-triggered deferred-save failures from rescheduling the same stale snapshot indefinitely.

## Key Changes

- Version and schema:
  - `core/runtime/config.py` now reports `APP_VERSION = "04.01.02"`.
  - `core/project/project_format.py` now marks newly saved project payloads as schema version `04.01.02`.

- NLE close/deferred save:
  - `core/frame_time.py` now reads nested vector-canvas `time.start_frame/end_frame/timeline_frame_rate` payloads and converts them through the row's source FPS before returning target-frame bounds.
  - `NLECaptionState` and NLE runtime save/export projections now share that frame-boundary interpretation.
  - Close/exit forced deferred-save failures no longer schedule a 5-second stale retry loop; background/manual deferred-save retry behavior remains unchanged.

- Guardrails preserved:
  - True final subtitle overlaps still raise `nle_save_export_final_overlap`.
  - Raw vector rows from `projects/내 프로젝트 (5).aissproj` now reach the final-overlap guard instead of `nle_save_export_invalid_duration`, proving the timing-shape bug is fixed without silently writing overlapped final SRT rows.

## Validation

- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_runtime_cutover.py tests/test_project_assets.py tests/test_editor_autosave_cleanup.py -q`: `68 passed`
- Read-only project-5 probe:
  - before fix: raw vector rows failed as `nle_save_export_invalid_duration`
  - after fix: raw vector rows fail only as `nle_save_export_final_overlap`
- Jammini route proof: `.agents/sentinel/handoffs/20260629-004654-watchdog-handoff-probe.md`
- Jammini blocker scout: `.agents/sentinel/handoffs/20260628-234233-nle-close-deferred-save-blocker-scout-jammini.md`

## Not Included

- No UI/UX label, layout, color, shortcut, menu, or popup behavior change.
- No automatic overlap repair beyond the existing one-frame micro-overlap rule.
- No persisted `_nle_project_state` or canonical NLE disk-format load-owner cutover.
- No App Store `.pkg`, validation, upload, or submission.
- No STT2 skip, word-precision skip, model downgrade, or collect-cache default promotion.

## Remaining Risks

- `projects/내 프로젝트 (5).aissproj` still contains two true 2-frame final subtitle overlaps. Those remain blocked by `nle_save_export_final_overlap` and need a separate owner-approved subtitle-row repair or editing-surface fix if the owner wants that specific project to save final assets cleanly.
- Mac App Store submission remains blocked on Distribution/Installer identities, signed `.pkg`, sandbox smoke, App Store Connect validation, and owner metadata.
