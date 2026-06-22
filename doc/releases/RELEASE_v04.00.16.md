# RELEASE v04.00.16

Release date: 2026-06-23
Phase: SOURCE_APP_EDITOR_AUTOMATION_V4_0_16_RELEASED
Base branch: `codex/apple-stt-sidebar-menu`
Immediately previous release: `v04.00.15`
Release app version: `04.00.16`

## Summary

v04.00.16 is an editor automation and release-hygiene stabilization release for the Python/PyQt6 source app. It keeps subtitle generation quality policy, UI/UX layout, model choices, and project storage format unchanged while making the source-app quick flow more reliable and easier to audit.

The release focuses on the post-generation editor-readiness line: compact geometry evidence is now available through app-command status, diamond move/merge automation can survive stale status snapshots, and the Macau project fixture used by the QA runner is isolated under the run output so quick saves do not keep mutating the root ignored fixture.

## Changes Since v04.00.15

- Added compact editor geometry evidence to automation snapshots and app-command compact status.
  - Geometry covers the main window, workspace/editor splitters, editor, video frame/player, timeline frame/canvas, global minimap canvas, bottom panel, and global menu bar.
  - The app-command server strips nonessential/debug geometry fields before returning compact status.
- Hardened source-app editor compact automation.
  - Inline edit commit now flushes pending editor events before returning the next runtime snapshot.
  - Diamond move/merge commands first use the previous successful runtime snapshot, then fall back to a fresh compact status read.
  - If compact status has a stale active segment but a valid playhead, the QA runner uses the status playhead rather than driving the next step from an old segment.
- Isolated the Macau QA fixture.
  - `tools/qa_suite_runner.py` copies the ignored Macau `.aissproj` and sibling `.assets` into the suite output before opening it.
  - This keeps source-app quick runs from repeatedly saving over the root ignored fixture.
- Updated release documentation and handoff state for `04.00.16`.
  - `core/runtime/config.py` is the source of truth for `APP_VERSION` and now reports `04.00.16`.
  - `core/project/project_format.py` remains at project schema `04.00.15` because this release does not change `.aissproj` storage semantics.

## Code Review Notes

- Review found no release-blocking code issues after the cleanup pass.
- The main risk checked was status payload growth from geometry evidence; the server-side compactor keeps only rect booleans, rect numbers, and splitter sizes.
- The stale-runtime risk is bounded to automation command resolution. User-facing editor behavior and subtitle timing persistence are not changed by this release.
- DMG/sign/notarization/App Store upload were not run. DMG packaging remains opt-in only.

## Verification

Completed verification for this release:

- Focused editor/app-command regression set
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_editor_automation.py tests/test_qa_suite_runner.py tests/test_app_command_bridge.py tests/test_app_command_server.py`
  - Result: `107 passed`
- Syntax check for touched Python modules
  - `./venv/bin/python -m py_compile ui/editor/editor_automation.py tools/qa_suite_runner.py core/automation/app_command_server.py ui/main/app_command_bridge_handlers.py`
  - Result: OK
- Source-app quick smoke QA
  - `AI_SUBTITLE_STUDIO_QA_USE_SOURCE=1 ./venv/bin/python tools/qa_suite_runner.py quick --output-dir output/manual_verification/latest/20260623_editor_ready_geometry_source_quick_final9`
  - Result: pass, `failed_count=0`
  - Artifact: `output/manual_verification/latest/20260623_editor_ready_geometry_source_quick_final9`
- Patch integrity
  - `git diff --check -- .`
  - Result: OK

## Remaining Risk

- The latest source-app quick proof uses a copied Macau project fixture. The original `/Users/u_mo_c/Downloads/마카오테스트` folder and original `test video/X5_시승기_후반.MP4` were not present, so this is not fresh Macau media or fresh X5 media promotion proof.
- Long High-mode media can still enter memory warning/critical pressure during model-heavy phases; this release does not change subtitle generation workload or model residency policy.
- Project schema stays at `04.00.15`; this is intentional because the release changes automation and verification behavior, not stored project format.
