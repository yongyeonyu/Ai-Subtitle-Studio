# RELEASE v04.00.17

Release date: 2026-06-26
Phase: SOURCE_APP_CONTINUATION_V4_0_17_RELEASED
Base branch: `main`
Immediately previous release: `v04.00.16`
Release app version: `04.00.17`

## Summary

v04.00.17 is a source-app checkpoint release for the completed internal NLE read-only baseline. It keeps the existing Python/PyQt6 product line, subtitle quality policy, save/reopen compatibility, roughcut sidecar compatibility, and visible UI/UX behavior intact.

This checkpoint also hardens the full QA X5 fixture path so audio-less fallback media cannot silently stand in for real source proof. DMG packaging, signing, notarization, and App Store/TestFlight work were not run.

## Changes Since v04.00.16

- Completed the source-app internal NLE read-only baseline.
  - Documented the owner map and domain contract for `ProjectAsset`, `Sequence`, `Track`, `Clip`, `CaptionSegment`, `TimelineMarker`, and `RenderPlan`.
  - Added read-only snapshot coverage for existing project/editor/roughcut state without adding save-file writes or visible UI state changes.
  - Kept cut-boundary point evidence separate from clip boundary spans.
- Connected roughcut exact-join and render/export parity through the NLE snapshot route.
  - `stitched_cut_boundaries` are projected as output-time `TimelineMarker` evidence.
  - Roughcut SRT/video render plan construction now reads through `build_concat_render_plan_from_snapshot`.
  - Legacy `_render_plan.json` and `_edl.json` payloads, sidecar readers, output duration semantics, and reopen behavior remain compatible.
- Hardened X5 full QA fixture selection.
  - Automatic X5 media candidates now require an audio stream.
  - Missing X5 full media reports a structured `media_missing` result instead of an empty verifier traceback.
  - The standard ignored local fixture path `test video/X5_시승기_후반.MP4` was restored and used for final source-app full QA proof.
- Updated handoff and validation docs for the completed NLE baseline and next `Post-Generation Editor Readiness And Verification Index` queue item.

## Code Review Notes

- The NLE snapshot remains read-only and does not persist `nle` fields into `.aissproj` files.
- Review found no intended changes to subtitle generation policy, STT2, LLM, LoRA, VAD, timing rules, model selection, UI labels, layout, shortcuts, colors, menus, or popup behavior.
- The render/export route builds the same legacy roughcut command plan shape from a snapshot projection; it does not replace the roughcut sidecar schema.
- Runtime code changed for release version metadata:
  - `core/runtime/config.py` now reports `APP_VERSION = "04.00.17"`.
  - `core/project/project_format.py` now marks newly saved project payloads as schema version `04.00.17`.

## Verification

Completed verification for this release:

- Syntax checks
  - `./venv/bin/python -m py_compile core/runtime/config.py core/project/project_format.py ui/roughcut/roughcut_export.py tools/qa_suite_runner.py tests/test_project_nle_snapshot.py tests/test_qa_suite_runner.py tests/test_roughcut_ui_v2.py`
  - Result: OK
- Focused NLE/project/editor/roughcut guard set
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_snapshot.py tests/test_project_context.py tests/test_project_segment_reload.py tests/test_editor_srt_open_refresh.py tests/test_roughcut_engine1.py tests/test_roughcut_v2_output_compat.py tests/test_roughcut_ui_v2.py`
  - Result: `269 passed, 4 subtests passed`
- App-command and QA-runner guard set
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_app_command_bridge.py tests/test_qa_suite_runner.py`
  - Result: `103 passed`
- Source-app full QA with standard X5 fixture path
  - `AI_SUBTITLE_STUDIO_QA_USE_SOURCE=1 ./venv/bin/python tools/qa_suite_runner.py full --output-dir output/manual_verification/latest/qa_suite_full_standard_x5_restored_20260626_0901`
  - Result: pass, `passed_count=9`, `failed_count=0`
  - X5 artifact: `output/manual_verification/latest/qa_suite_full_standard_x5_restored_20260626_0901/x5_high_rolling_180s`
  - X5 counts: `final_segment_count=55`, `raw_segment_count=56`
  - X5 timing: `total_elapsed_sec=48.511`, `pipeline_elapsed_sec=48.327`
  - X5 LLM rollback count: `0`
- Diff hygiene
  - `git diff --check -- .`
  - Result: OK

## Remaining Risk

- The NLE snapshot is intentionally read-only. Any future persistent NLE schema field must pass a separate compatibility gate for legacy `.aissproj`, direct SRT open, sidecars, and rendered roughcut reopen.
- The standard X5 media file is an ignored local fixture; if `test video/` is cleaned, restore `test video/X5_시승기_후반.MP4` before relying on default full QA.
- Long High-mode media can still enter memory warning/critical pressure during model-heavy phases; this release does not reduce the quality-first workload.
