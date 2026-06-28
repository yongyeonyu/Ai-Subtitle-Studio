# RELEASE v04.00.09

Release date: 2026-05-18
Phase: MAC_NATIVE_APPSTORE_V4_0_9_RELEASED
Base branch: `main`
Immediately previous release: `v04.00.08`
Release app version: `04.00.09`

## Summary

v04.00.09 turns the current Tiniping benchmark run into real runtime defaults. The release locks Fast, Auto, and High to the STT1/STT2, audio, VAD, LoRA, Deep, and timing-anchor combinations that won the 티니핑 0~3분 sweep and the 0~11분 final validation, then surfaces those winning STT models back into the UI as `[Fast]`, `[Auto]`, and `[High]` recommendation tags.

This release also hardens the manual roughcut rerun path from the lower global timeline canvas. Running roughcut LLM manually now saves the current subtitle state first, reruns only the roughcut LLM path, and re-sorts middle rows chronologically before applying them so manual refresh cannot reintroduce stale local fallback order.

## Changes Since v04.00.08

- Locked Fast/Auto/High defaults to the latest Tiniping benchmark winners.
  - `core/audio/stt_quality_presets.py` now owns benchmark-locked mode settings for STT1/STT2, audio filter, VAD thresholds, LoRA bucket selection, Deep selector gates, packaging, and timing anchors.
  - `core/mode_policy.py` now applies those benchmark-locked settings at runtime without overriding user-selected model identities.
  - Fast, Auto, and High now all preserve selective STT2 rescue where the benchmark chose it; High alone keeps subtitle LLM review active.
- Surfaced benchmark recommendations in model-selection UI.
  - `ui/settings/settings_common.py` now appends `[Fast]`, `[Auto]`, and `[High]` tags to benchmark-winning STT models when requested.
  - `ui/settings/settings_ai.py` shows the recommendation tags in the STT1/STT2 model combos.
  - `ui/home_sidebar.py` shows the same tagged names in the sidebar model-selection popup menus.
- Added a reusable Tiniping benchmark orchestrator and scoring cleanup.
  - `tools/benchmark_tiniping_mode_search.py` runs the 3-minute search and 11-minute final validation flow and writes summary artifacts.
  - `tools/benchmark_subtitle_pipeline_variants.py` now ignores only parentheses during reference compaction while preserving punctuation such as `..`, `!`, and `~` for score comparison.
- Hardened manual roughcut rerun behavior from the global timeline canvas.
  - `ui/timeline/timeline_global.py` and `ui/timeline/timeline_widget.py` expose a right-click `러프컷 LLM 실행` action from the lower global canvas.
  - `ui/editor/editor_roughcut_draft.py` now saves the current subtitle state before manual roughcut rerun, re-schedules only the roughcut LLM path, and sorts returned middle rows before applying them.
  - `core/project/project_assets.py` now preserves original STT anchor timing metadata when final subtitle rows are externalized and restored.

## Code Review Notes

- Fixed a new recursion regression in `core/audio/stt_quality_presets.py` by removing preset-loader recursion from mode-key normalization after introducing benchmark-locked mode settings.
- Fixed a route-preservation regression in `core/mode_policy.py` so user-selected STT1/STT2 and model identities survive runtime benchmark locking instead of being replaced by benchmark defaults.
- Updated the benchmark-mode profile tests so the expected runtime path matches the new selective-ensemble winners instead of the older STT1-only / word-precision assumptions.

## Compatibility Notes

- `core/runtime/config.py` is the source of truth for `APP_VERSION` and now reports `04.00.09`.
- `core/project/project_format.py` now marks newly saved project payloads as schema version `04.00.09`.
- This branch remains macOS-only and Apple Silicon first.
- DMG packaging remains opt-in and was not run for this release because the user requested code, benchmark, and git release flow only.

## Verification

Completed verification for this release:

- Tiniping benchmark run
  - `./venv/bin/python tools/benchmark_tiniping_mode_search.py --manual-seeds-json .codex_work/benchmarks/tiniping_manual_seeds.json --keep-artifacts`
  - summary artifact: `output/manual_verification/latest/tiniping_benchmark_summary.md`
  - final winners:
    - Fast: KomixV2 MLX + WhisperKit Large V3
    - Auto: WhisperKit Large V3 Turbo + WhisperKit Large V3
    - High: WhisperKit Large V3 + WhisperKit Large V3 Turbo
- Consolidated release unittest sweep
  - `./venv/bin/python -m unittest tests.test_stt_quality_presets tests.test_mode_policy tests.test_whisper_model_catalog tests.test_tiniping_mode_search tests.test_benchmark_mode_profiles tests.test_editor_roughcut_draft tests.test_project_context tests.test_timeline_hit_targets tests.test_ai_settings_runtime_apply tests.test_stt_mode_policy`
  - `291 passed`
- Python syntax checks
  - `./venv/bin/python -m compileall -q main.py core ui tests tools`
- Working-tree hygiene
  - `git diff --check -- .`

Additional runtime-release note:

- This release used the real Tiniping media benchmark as the main runtime validation surface. A fresh interactive GUI walk-through was not re-recorded in the same batch after the benchmark lock patch, so the benchmark summary and targeted regression tests are the primary release evidence.

## Next Direction

The next highest-value follow-up is to keep pushing the subtitle score gap down against the final Tiniping answer key. The current benchmark now gives a repeatable winner-selection scaffold, but the best 11-minute score is still far from exact-match subtitle parity, so the next batch should focus on text accuracy deltas, timing mismatch clusters, and extending the same benchmark flow to X5 and Macau fixtures.
