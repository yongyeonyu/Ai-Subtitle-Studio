DEX_REVIEW_READY

# NLE Save/Export Projection Cutover

- Scope: source-app internal NLE runtime adoption slice for final SRT/cache rows.
- Report: `output/manual_verification/latest/nle_save_export_projection_cutover_20260628/save_export_projection_report.md`
- Behavior: `nle_save_export_segments_from_editor_rows(...)` projects externalized final SRT/cache rows through NLE caption state with `_nle_runtime_surface=save_export`.
- Safety: silence gaps stay in vector-canvas gap metadata, final SRT/cache drops live STT/subtitle preview rows and STT candidate payloads, and STT1/STT2 reference tracks remain separate.
- Verification:
  - `py_compile` for touched modules/tests -> pass.
  - `tests/test_project_nle_runtime_cutover.py tests/test_project_assets.py -k "save_export or externalize_project_text_assets"` -> `4 passed, 6 deselected`.
  - NLE runtime/render/export/persistence/dual-write/operation/snapshot set -> `44 passed, 4 subtests passed`.
  - `tests/test_project_context.py -k "externalize_project_text_assets or external_text_assets or hot_open_subtitle_segments_cache"` -> `1 passed, 84 deselected`.
- Remaining: persisted NLE project fields and broader legacy cleanup remain gated; no visible UI or subtitle-generation policy changed.
