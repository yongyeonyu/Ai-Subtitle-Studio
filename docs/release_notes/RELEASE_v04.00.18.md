# RELEASE v04.00.18

Date: 2026-06-27
Previous release: `v04.00.17`
Release app version: `04.00.18`

## Summary

`v04.00.18` is a source-app checkpoint release for subtitle timing and cut-boundary accuracy work after the internal NLE read-only baseline. It keeps the Python/PyQt6 source app line, legacy project compatibility, roughcut sidecar compatibility, direct SRT reopen behavior, and visible UI/UX layout intact.

This release does not build a DMG, move App Store/TestFlight state, migrate to native Swift/QML, or change STT2, LLM, LoRA, VAD model-selection defaults beyond the owner-approved timing consensus and cut-boundary priority policy.

## Key Changes

- VAD/STT timing consensus:
  - Added a final timing consensus rule across VAD, STT1, and STT2.
  - If two of the three timing sources agree on start/end/duration, that pair can become the final timing anchor.
  - VAD+STT agreement prefers the VAD span with the existing edge pad.
  - STT1-only mode uses the earlier start and later end across STT1/VAD as requested.
  - STT1+STT2 agreement can still preserve timing when VAD is missing or clearly disagrees.

- Cut-boundary priority:
  - Confirmed visual cut boundaries now force subtitle split or edge-snap at the exact boundary frame.
  - The owner's `2676 -> 2677` case is represented by a focused split/snap guard.
  - Split rows now receive deterministic derived IDs while retaining `cut_boundary_source_id`, preventing duplicate editor/save row ownership after forced cut splits.
  - Cut-boundary work-lane lines paint at 50% alpha in the middle-category lane without changing labels, layout, menus, or shortcuts.

- Source-fps pioneer scout:
  - High/precise mode enables the existing ffmpeg pipe pioneer scout with source-fps sampling capped at 30fps.
  - The old skip/rollback path remains as follower/refine logic.
  - Exact 59.94fps fixture proof at frames `2766` and `2677` remains the next source-fps/60fps validation slice in `NLE_Action.md`.

- NLE action planning and agent governance:
  - Added `NLE_Action.md` as the execution source of truth for the next NLE mutable-owner, frame-scout cut-boundary, preview/skimming, and temp trace-log slices.
  - Jammini handoff results were reviewed by Dex and classified before adoption.
  - The current NLE state remains a read-only baseline; mutable NLE write ownership is planned but not silently promoted in this release.

- Version and schema:
  - `core/runtime/config.py` now reports `APP_VERSION = "04.00.18"`.
  - `core/project/project_format.py` now marks newly saved project payloads as schema version `04.00.18`.

## Validation

- `./venv/bin/python -m py_compile ...` for touched Python files: pass
- `./venv/bin/python -m json.tool dataset/custom_defaults.json >/tmp/custom_defaults_check.json`: pass
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_subtitle_quality_models.py -k "vad_voice_start_priority or vad_stt_timing_consensus"`: `9 passed, 8 deselected`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_stt_ensemble.py tests/test_subtitle_boundary_alignment.py tests/test_subtitle_quality_models.py -k "stt_anchor or drift or vad_voice_start_priority or vad_stt_timing_consensus or boundary"`: `24 passed, 44 deselected`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_subtitle_engine_settings.py -k "llm or stt_anchor or slot_order or text_only_lock"`: `26 passed, 56 deselected`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_subtitle_boundary_alignment.py tests/test_project_context.py -k "cut_boundary or cut_boundaries or cut_frame_2677"`: `6 passed, 93 deselected`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_render_cache.py -k "cut_boundary_work_lane"`: `2 passed, 46 deselected`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_cut_boundary_auto_scan_backend.py tests/test_mode_policy.py -k "pipe_fps or source_fps or runtime_modes_apply_stage_policy"`: `3 passed, 38 deselected`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_pipeline_cut_boundary_cache.py -k "split_by_saved_cut_boundaries or shift_cut_boundary_rows"`: `2 passed, 20 deselected`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_snapshot.py tests/test_roughcut_v2_output_compat.py`: `13 passed, 4 subtests passed`
- `AI_SUBTITLE_STUDIO_QA_USE_SOURCE=1 ./venv/bin/python tools/qa_suite_runner.py quick`: pass, `failed_count=0`, artifact `output/manual_verification/latest/qa_suite_quick_20260627_005453`
- `git diff --check -- .`: pass

## Not Included

- No DMG build.
- No release tag movement beyond the new `v04.00.18` tag.
- No App Store/TestFlight work.
- No UI/UX label, layout, color, shortcut, menu, or popup behavior changes.
- No native migration, Swift rewrite, QML migration, or Premiere-style UI clone.
- No change to STT2 execution policy, LLM text policy, LoRA learning policy, or model-selection policy.

## Remaining Risks

- The High/precise pipe scout currently keeps a 30fps cap; exact 59.94fps frame proof for frames `2766` and `2677` is documented as the next `NLE_Action.md` validation slice.
- VAD/STT timing consensus is intentionally timing-affecting, so real High-mode fixtures should continue checking subtitle count, first/last time, output duration, and sidecar metadata drift.
- Mutable NLE write ownership is still deferred; the current release remains compatible with the read-only NLE baseline.
