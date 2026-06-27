# NLE Roughcut State Render Plan Cutover

DEX_REVIEW_READY

## Summary

- Saved roughcut candidate `outputs.render_plan` construction now routes through the existing NLE snapshot adapter path used by roughcut export/render actions.
- This is an internal source-app NLE ownership adoption slice only. It does not approve persisted NLE project fields, delete legacy render helpers, or change visible roughcut UI/UX.

## Files

- `ui/roughcut/roughcut_state.py`
- `tests/test_roughcut_ui_v2.py`
- `output/manual_verification/latest/nle_roughcut_state_render_plan_cutover_20260628/roughcut_state_render_plan_report.md`

## Verification

- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m py_compile ui/roughcut/roughcut_state.py tests/test_roughcut_ui_v2.py` -> pass.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_roughcut_ui_v2.py -k "saved_candidate_render_plan_uses_nle_snapshot_adapter_with_legacy_parity or render_plan_builders_route_through_nle_snapshot_adapter_with_legacy_parity or app_command_roughcut_export_and_render_use_nle_snapshot_route"` -> `3 passed, 35 deselected`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_roughcut_v2_output_compat.py tests/test_project_nle_snapshot.py -k "nle_snapshot_render_plan_matches_legacy_concat_builder or render_plan or roughcut_exact_join or save_reload"` -> `3 passed, 16 deselected`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_runtime_cutover.py tests/test_project_nle_render_export_parity.py tests/test_project_nle_persistence_guard.py tests/test_project_nle_dual_write.py tests/test_project_nle_operations.py tests/test_project_nle_snapshot.py tests/test_roughcut_v2_output_compat.py` -> `48 passed, 4 subtests passed`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/evaluate_reference_benchmark_acceptance.py .codex_work/benchmarks/subtitle_pipeline_variants/20260628_013224/benchmark_results.json` -> `accepted=true`.
- `git diff --check -- ui/roughcut/roughcut_state.py tests/test_roughcut_ui_v2.py` -> pass.

## Risk

- No subtitle-generation, STT2, word precision, LLM, LoRA, VAD, timing, or model-selection behavior changed.
- Broader roughcut interaction/export smoke remains useful before future cleanup of legacy roughcut render-plan paths.
