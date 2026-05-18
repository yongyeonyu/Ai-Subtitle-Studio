# RELEASE v04.00.10

Release date: 2026-05-19
Phase: MAC_NATIVE_APPSTORE_V4_0_10_RELEASED
Base branch: `main`
Immediately previous release: `v04.00.09`
Release app version: `04.00.10`

## Summary

v04.00.10 hardens the post-v04.00.09 subtitle runtime instead of widening the visible UI surface. The release keeps the benchmark-winning High timing path alive inside the real transcribe runtime, adds a conservative adaptive-audio routing engine for mixed environments such as indoor, in-car, and outdoor footage, and fixes two editor regressions discovered during manual subtitle review: diamond drag cut search was heavier than needed, and some multiline hyphen subtitles could leak their second line into a separate normal segment.

The adaptive-audio engine is intentionally guarded. This release ships the route classifier, profile-memory reuse, preview self-score gate, and switch-confirmation heuristics, but it does not force every experimental route into the benchmark-locked High default unless long-fixture validation actually improved.

## Changes Since v04.00.09

- Hardened benchmark-locked High timing in the production transcribe path.
  - `core/audio/stt_quality_presets.py` now locks High to `ffmpeg/silero relaxed` plus a 120-second rolling STT window with 8-second overlap and 4-second hysteresis.
  - `core/audio/media_processor_transcribe.py` now finalizes windowed STT spans inside the real ensemble runtime, trims overlap commits safely, and keeps helper metadata for later dedupe/finalize decisions.
  - `core/audio/media_processor.py` and `core/pipeline/pipeline_helpers.py` now respect benchmark-locked audio settings so runtime auto-tune does not silently override benchmarked routes.
- Added a conservative adaptive-audio routing engine for general mixed-environment video.
  - `core/audio/media_processor_audio.py` now supports chunk-profile sampling, preview self-score comparison, baseline guard, profile-memory reuse, switch confirmation, and selective split experiments.
  - `core/audio/preset_auto_classifier.py` now classifies clean dialog, roomy indoor dialog, driving noise, and volatile scenes, and exposes stable candidate ranking helpers for route selection.
  - `tools/benchmark_subtitle_pipeline_variants.py`, `tools/benchmark_tiniping_mode_search.py`, and `tools/benchmark_tiniping_timing_ideas.py` now cover the new routing/timing experiments with reproducible artifact output.
- Added timing and subtitle-core experiments without promoting unstable defaults.
  - `core/engine/subtitle_timing.py` now contains optional piecewise drift correction experiments behind settings gates.
  - `tests/test_audio_presets.py`, `tests/test_preset_auto_classifier.py`, `tests/test_media_processor_overlap.py`, `tests/test_subtitle_engine_settings.py`, and `tests/test_tiniping_timing_ideas.py` now cover the new adaptive routing, rolling-window, and timing-policy behavior.
- Reduced diamond drag cut-search cost and added drag-shadow feedback.
  - `ui/editor/ux/timeline_subtitle_segment_editing.py` now searches only in the drag direction and only inside a one-second local window near the playhead when resolving live cut snaps.
  - `ui/timeline/timeline_canvas.py` and `ui/timeline/timeline_paint.py` now show a dedicated temporary drag shadow playhead for the detected cut target.
- Fixed multiline hyphen subtitle leakage into a separate normal segment.
  - `ui/editor/editor_helpers.py`, `ui/editor/editor_segments_queue_flush.py`, `ui/editor/editor_segments_bulk_prepare.py`, and `ui/editor/editor_segments_manual_edits.py` now split `-` prefixed multiline rows into separate text blocks only when the segment payload actually carries multiple speakers.
  - `tests/test_subtitle_line_breaks.py` now verifies single-speaker hyphen line breaks stay in one segment while real multi-speaker rows still use grouped blocks.
- Expanded correction-dictionary coverage for a newly observed error.
  - `dataset/dataset_correction.json` now maps `원 청포논` to `완성품은`.

## Code Review Notes

- Kept the adaptive-audio engine behind benchmark-safe guards after review showed that always-on selective split could improve timing but still lower overall quality on some fixtures.
- Kept the production defaults conservative even after the X5 spot benchmark because the new `mode_auto_adaptive_split_drift` path won that fixture, but earlier Tiniping/BMW validation still showed cross-fixture trade-offs that do not justify a blanket default flip yet.
- Verified that the multiline subtitle fix does not change the existing multi-speaker grouped-block path; only the false positive split path was removed.
- Verified that the diamond drag shadow playhead is isolated from the pinned shadow playhead, so drag preview cannot overwrite the existing playhead-shadow UX state.

## Compatibility Notes

- `core/runtime/config.py` is the source of truth for `APP_VERSION` and now reports `04.00.10`.
- `core/project/project_format.py` now marks newly saved project payloads as schema version `04.00.10`.
- This branch remains macOS-only and Apple Silicon first.
- DMG packaging remains opt-in and was not run for this release.

## Verification

Completed verification for this release:

- Focused unittest sweeps
  - `./venv/bin/python -m unittest tests.test_stt_quality_presets tests.test_mode_policy tests.test_ai_settings_runtime_apply tests.test_benchmark_mode_profiles -q`
  - `./venv/bin/python -m unittest tests.test_audio_presets tests.test_preset_auto_classifier tests.test_media_processor_overlap tests.test_subtitle_engine_settings -q`
  - `./venv/bin/python -m unittest tests.test_subtitle_line_breaks tests.test_timeline_hit_targets -q`
  - `./venv/bin/python -m unittest tests.test_tiniping_timing_ideas tests.test_tiniping_mode_search -q`
- Python syntax and diff hygiene
  - `./venv/bin/python -m compileall -q main.py core ui tests tools`
  - `git diff --check -- .`
- Real media benchmark fixture
  - `./venv/bin/python tools/benchmark_subtitle_pipeline_variants.py --suite modes --media "test video/X5_시승기_후반.MP4" --reference-srt "test video/X5_시승기_후반.srt" --start-sec 0 --duration-sec 180 --keep-artifacts`
  - summary artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260519_014420/benchmark_results.md`
  - result snapshot: `mode_auto_adaptive_split_drift` ranked first on the X5 fixture (`quality 81.490`, `timing MAE 0.602s`, `18.692s`) ahead of current `mode_auto` (`quality 81.229`, `timing MAE 0.616s`, `17.025s`) and `mode_high` (`quality 79.359`, `timing MAE 0.608s`, `184.965s`)

## Next Direction

The next highest-value follow-up is not another broad default flip. The new adaptive-audio engine is now in place, so the next work should widen the real-media benchmark corpus and only promote additional split/drift policies when they improve both timing and overall subtitle quality on more than one representative fixture.
