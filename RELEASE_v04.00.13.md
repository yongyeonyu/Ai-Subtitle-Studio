# RELEASE v04.00.13

Release date: 2026-05-22
Phase: MAC_NATIVE_APPSTORE_V4_0_13_RELEASED
Base branch: `opt/one-shot-quality-speed-20260521-0228`
Immediately previous release: `v04.00.12`
Release app version: `04.00.13`

## Summary

v04.00.13 is a subtitle-generation stability release for the Apple Silicon High path. It does not change UI/UX, subtitle model identity, or the quality policy itself. Instead, it hardens pass-specific runtime overrides so selective STT2 rescue and word-timestamp precision passes do not recursively re-enter their own recheck pipeline.

The release closes the X5 High regression where `_fast_stt2_recheck` clips were being treated as fresh STT inputs again, creating nested recheck paths and eventually failing the real-media run.

## Changes Since v04.00.12

- Fixed Apple Silicon runtime override precedence for pass-specific STT behavior.
  - `VideoProcessor._load_all_settings()` now reapplies `_fast_mode_overrides` after `apply_apple_m_subtitle_pipeline_plan()`.
  - This keeps plan-shaping flags visible to the Apple M scheduler while preserving final pass-specific disables such as:
    - `stt_selective_secondary_recheck_enabled = False`
    - `stt_word_timestamps_mode = off`
    - `stt_word_timestamps_precision_enabled = False`
- Added a regression test for the override precedence.
  - `tests/test_audio_presets.py` now verifies that pass-specific runtime overrides survive the Apple Silicon runtime plan.

## Code Review Notes

- Review found the failure was not an STT model-quality issue. The real bug was settings recomposition order.
- Review confirmed the recursive `_fast_stt2_recheck/.../_fast_stt2_recheck/...` path came from a recheck pass inheriting the default Apple M selective-recheck policy again after the override had already tried to turn it off.
- The fix is intentionally narrow and keeps the existing STT1/STT2 selective ensemble policy unchanged for normal subtitle generation.

## Compatibility Notes

- `core/runtime/config.py` is the source of truth for `APP_VERSION` and now reports `04.00.13`.
- `core/project/project_format.py` now marks newly saved project payloads as schema version `04.00.13`.
- No UI/UX behavior, shortcut mapping, layout, or wording was changed in this release.
- DMG/sign/notarization/App Store upload were not run as part of this release.

## Verification

Completed verification for this release:

- Focused regression/unit checks
  - `./venv/bin/python -m unittest tests.test_audio_presets tests.test_media_processor_overlap.MediaProcessorOverlapTests.test_native_batch_refine_routes_precision_rechecks_after_full_stt1_pass -q`
  - Result: `49 tests OK`
- Syntax and diff hygiene
  - `./venv/bin/python -m py_compile core/audio/media_processor.py tests/test_audio_presets.py`
  - `git diff --check -- core/audio/media_processor.py tests/test_audio_presets.py`
  - Result: OK
- Real X5 High regression verification
  - `./venv/bin/python tools/verify_full_media_pipeline.py --media '/Users/u_mo_c/Downloads/ai_subtitle_studio/test video/X5_시승기_후반.MP4' --mode high --duration-sec 180 --output-dir output/manual_verification/latest/20260522_x5_high_release_regression_fix`
  - Result: pass
  - Artifact: `output/manual_verification/latest/20260522_x5_high_release_regression_fix/tinyping_full_verify.json`
  - Summary: `total_elapsed_sec=182.697`, `pipeline_elapsed_sec=168.115`, `peak_rss_bytes=652050432`, `final/raw=54/52`
- Refreshed app bundle and one-command full QA
  - `./packaging/macos/build_app_bundle.sh`
  - `./venv/bin/python tools/qa_suite_runner.py full`
  - Result: pass, `failed_count=0`
  - Artifact: `output/manual_verification/latest/qa_suite_full_20260522_081710`

## Remaining Risk

- The run still entered memory `critical` during long High verification, so memory-pressure follow-up remains valid even though this recursion regression is fixed.
- This release fixes the recursive recheck failure path; it does not yet optimize the High-mode wall-clock cost of STT2 rescue or word-timestamp precision on long clips.
