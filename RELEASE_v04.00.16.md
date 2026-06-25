# RELEASE v04.00.16

Release date: 2026-06-26
Phase: SOURCE_APP_CONTINUATION_V4_0_16_RELEASED
Base branch: `main`
Immediately previous release: `v04.00.15`
Release app version: `04.00.16`

## Summary

v04.00.16 is a source-app checkpoint release for the roughcut, exact-join, app-command, fast-exit, and next-architecture planning work completed after v04.00.15. It keeps the existing Python/PyQt6 product line, subtitle quality policy, and UI/UX defaults intact.

This checkpoint also promotes the next active execution lane: a Premiere-style internal NLE timeline architecture plan for the source app. That plan is intentionally limited to domain contracts and read-only adapters first; it is not native migration, Swift rewrite, QML adoption, or a visible Premiere UI clone.

## Changes Since v04.00.15

- Hardened roughcut exact-join metadata and reopen behavior.
  - Roughcut EDL/render-plan sidecars carry `stitched_cut_boundaries` so joined roughcut outputs can seed exact cut boundaries without rescanning the rendered video.
  - Direct SRT reopen and project reopen paths can restore exact joins from adjacent `_edl.json` and `_render_plan.json` sidecars.
  - Multi-boundary source-app proof showed sidecar-assisted reopen/start reducing avoidable cut-boundary prescan.
- Made roughcut video rendering safer for subtitle sync.
  - Roughcut video export defaults to sync-safe rendering instead of stream-copy trimming.
  - Rendered video exports write adjacent `_render_plan.json` and `_edl.json` sidecars for later reopen.
  - A roughcut render app-command smoke covers export, render queueing, sidecar paths, and reopen behavior.
- Improved editor and automation verification surfaces.
  - Added editor timeline view automation for zoom, fit, time-window, and max-view checks.
  - Added explicit app-command coverage for subtitle magnet smoke and safe bottom global-menu actions.
  - Source-app quick smoke now exercises the editor interaction commands added after the previous release.
- Reduced quit/exit perceived latency.
  - Fast-exit cleanup now avoids expensive navigation cleanup and GPU/runtime cache clearing on the foreground quit path while still reaping heavy child processes and preview proxies.
- Added the next prioritized architecture plan.
  - `ACTION_ITEMS.md` now puts `Source-App Internal NLE Timeline Architecture Plan` first.
  - The plan sequences project/media/sequence/track/clip/caption/marker/render-plan ownership before runtime routing changes.
  - It explicitly separates cut boundary point data from clip boundary span data before implementation.

## Code Review Notes

- Review found no unintended subtitle-generation, STT, LLM, VAD, timing, model-selection, or visible UI/UX changes in this release closeout slice.
- Runtime code changed only for release version metadata:
  - `core/runtime/config.py` now reports `APP_VERSION = "04.00.16"`.
  - `core/project/project_format.py` now marks newly saved project payloads as schema version `04.00.16`.
- The NLE timeline work remains a documented execution plan and has not yet been implemented as runtime state.
- DMG/sign/notarization/App Store upload were not run. DMG packaging remains opt-in only.

## Verification

Completed verification for this release:

- Version syntax check
  - `./venv/bin/python -m py_compile core/runtime/config.py core/project/project_format.py`
  - Result: OK
- Focused project, roughcut, app-command, and QA-runner guard set
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_context.py tests/test_project_segment_reload.py tests/test_qa_suite_runner.py tests/test_app_command_bridge.py tests/test_roughcut_engine1.py tests/test_roughcut_ui_v2.py`
  - Result: `332 passed`
- Source-app quick smoke QA
  - `AI_SUBTITLE_STUDIO_QA_USE_SOURCE=1 ./venv/bin/python tools/qa_suite_runner.py quick`
  - Result: pass, `failed_count=0`
  - Artifact: `output/manual_verification/latest/qa_suite_quick_20260626_011235`

## Remaining Risk

- The NLE timeline architecture is still a plan. The first implementation slice must start with docs/schema and read-only adapters, then prove legacy project/sidecar round-trip before replacing owners.
- Long High-mode media can still enter memory warning/critical pressure during model-heavy phases; this release does not change quality-first runtime workload.
- A pre-existing `v04.00.16` git tag points at an older side-branch checkpoint, so this mainline release closeout does not move or overwrite that tag.
