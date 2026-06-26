# 자동화-4 전체 UX 테스트 결과

## NLE Slice 1 trace workspace baseline - 2026-06-27

- 실행 모드: source-app trace/temp workspace baseline for NLE action diagnostics.
- 결과: pass
- 저장 위치:
  - Action source: `NLE_Action.md`
  - Runtime owners: `core/runtime/temp_workspace.py`, `core/runtime/trace_logger.py`
  - Package collector: `tools/collect_trace_package.py`
  - Guard tests: `tests/test_trace_logger.py`, `tests/test_startup_diagnostics.py`, `tests/test_app_command_bridge.py`
  - Jammini review: `.agents/sentinel/handoffs/20260627-012027-nle-slice-1-trace-review.md`
- 수정 요약:
  - Added a per-user temp workspace with trace/package/export/voice/preview directories, cleanup, prune, and usage reporting.
  - Added bounded async trace logging with manifest, run events, `latest.jsonl`, media fingerprint metadata, FPS numerator/denominator fields, failure isolation, and fork-child singleton reset.
  - Added stable trace package collection that trims partial active JSONL lines.
  - Initialized best-effort app trace startup in `main.py`.
  - Removed completed Slice 1 from `NLE_Action.md`.
- 검증:
  - `./venv/bin/python -m py_compile main.py core/runtime/temp_workspace.py core/runtime/trace_logger.py tools/collect_trace_package.py tests/test_trace_logger.py tests/test_startup_diagnostics.py` -> pass
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_trace_logger.py` -> `12 passed`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_trace_logger.py tests/test_startup_diagnostics.py tests/test_app_command_bridge.py -k "trace or diagnostic or open_media or open_project"` -> `18 passed, 71 deselected`
  - `git diff --check -- .` -> pass
- 자막 품질 영향:
  - None. Diagnostic trace/temp workspace only; no UI/UX, subtitle timing, STT2, LLM, LoRA, VAD, model-selection, save-format, release, tag, push, or DMG behavior changed.

## NLE Slice 0.5 compatibility characterization - 2026-06-27

- 실행 모드: source-app NLE compatibility characterization before mutable write-path work.
- 결과: pass
- 저장 위치:
  - Action source: `NLE_Action.md`
  - Guard tests: `tests/test_project_nle_snapshot.py`, `tests/test_editor_srt_open_refresh.py`
  - Jammini review: `.agents/sentinel/handoffs/20260627-010819-nle-slice-05-compat-review.md`
- 수정 요약:
  - Added a legacy `.aissproj` / `NLESnapshot` characterization guard for subtitle count, first/last frame timing, gap rows, 60000/1001fps frame fields, segment metadata, roughcut exact-join sidecar shape, render-plan output duration, and non-persistence of `nle` / `nle_snapshot`.
  - Strengthened direct SRT reopen guards so SRT timing/text win over linked project metadata, including row-count mismatch cases.
  - Removed completed Slice 0.5 from `NLE_Action.md`.
- 검증:
  - `./venv/bin/python -m py_compile tests/test_project_nle_snapshot.py tests/test_editor_srt_open_refresh.py` -> pass
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_snapshot.py tests/test_editor_srt_open_refresh.py` -> `27 passed, 4 subtests passed`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_snapshot.py tests/test_project_context.py tests/test_project_segment_reload.py tests/test_editor_srt_open_refresh.py` -> `200 passed, 4 subtests passed`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_roughcut_engine1.py tests/test_roughcut_v2_output_compat.py tests/test_roughcut_ui_v2.py` -> `71 passed`
  - `git diff --check -- .` -> pass
- 자막 품질 영향:
  - None. Tests/documentation only; no STT2, LLM, LoRA, VAD, timing policy, UI/UX, save format, release, tag, push, or DMG behavior changed.

## v04.00.18 source-app timing/cut-boundary release - 2026-06-27

- 실행 모드: source-app release checkpoint without DMG.
- 결과: pass
- 저장 위치:
  - Release note: `RELEASE_v04.00.18.md`
  - Quick QA artifact: `output/manual_verification/latest/qa_suite_quick_20260627_005453`
  - NLE action source: `NLE_Action.md`
- 수정 요약:
  - App version updated to `04.00.18`.
  - Project schema version updated to `04.00.18`.
  - Added VAD/STT final timing consensus and preserved STT-backed LLM timing lock behavior.
  - Confirmed visual cuts now force subtitle split/snap at the exact frame, with derived IDs for split rows to prevent duplicate editor/save ownership.
  - High/precise mode enables the existing ffmpeg pipe pioneer scout with source-fps sampling capped at 30fps.
  - `AGENTS.md`, `ACTION_ITEMS.md`, `README.md`, `docs/PROJECT_STATE.md`, `docs/HANDOFF.md`, and `RELEASE_v04.00.18.md` synced to the new checkpoint.
- 검증:
  - `./venv/bin/python -m py_compile core/cut_boundary.py core/cut_boundary_auto_scan.py core/runtime/config.py core/project/project_format.py core/settings_profiles.py core/audio/stt_quality_presets.py core/subtitle_quality/vad_alignment_checker.py core/engine/subtitle_engine.py ui/timeline/paint_passes.py ui/timeline/timeline_paint.py tests/test_cut_boundary_auto_scan_backend.py tests/test_mode_policy.py tests/test_subtitle_boundary_alignment.py tests/test_project_context.py tests/test_subtitle_quality_models.py tests/test_timeline_render_cache.py` -> pass
  - `./venv/bin/python -m json.tool dataset/custom_defaults.json >/tmp/custom_defaults_check.json` -> pass
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_subtitle_quality_models.py -k "vad_voice_start_priority or vad_stt_timing_consensus"` -> `9 passed, 8 deselected`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_stt_ensemble.py tests/test_subtitle_boundary_alignment.py tests/test_subtitle_quality_models.py -k "stt_anchor or drift or vad_voice_start_priority or vad_stt_timing_consensus or boundary"` -> `24 passed, 44 deselected`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_subtitle_engine_settings.py -k "llm or stt_anchor or slot_order or text_only_lock"` -> `26 passed, 56 deselected`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_subtitle_boundary_alignment.py tests/test_project_context.py -k "cut_boundary or cut_boundaries or cut_frame_2677"` -> `6 passed, 93 deselected`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_render_cache.py -k "cut_boundary_work_lane"` -> `2 passed, 46 deselected`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_cut_boundary_auto_scan_backend.py tests/test_mode_policy.py -k "pipe_fps or source_fps or runtime_modes_apply_stage_policy"` -> `3 passed, 38 deselected`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_pipeline_cut_boundary_cache.py -k "split_by_saved_cut_boundaries or shift_cut_boundary_rows"` -> `2 passed, 20 deselected`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_snapshot.py tests/test_roughcut_v2_output_compat.py` -> `13 passed, 4 subtests passed`
  - `AI_SUBTITLE_STUDIO_QA_USE_SOURCE=1 ./venv/bin/python tools/qa_suite_runner.py quick` -> pass, `failed_count=0`
  - `git diff --check -- .` -> pass
- 자막 품질 영향:
  - Timing policy intentionally changed per owner request: VAD/STT 2-of-3 agreement and confirmed visual cut boundaries have higher final timing priority.
  - No UI/UX label/layout/color/shortcut/popup, STT2 execution, LLM text policy, LoRA learning policy, model-selection, DMG, App Store, or TestFlight change.

## Cut boundary priority and source-fps pioneer scout - 2026-06-26

- 실행 모드: High-mode cut-boundary accuracy hotfix for missed frame boundary around frame 2677.
- 결과: pass for focused cut-boundary timing, timeline marker paint-plan, source-fps pioneer scout, and NLE snapshot guards.
- 원인 후보:
  - Existing saved-cut split helper fit a crossing subtitle into one cut scene instead of forcing a real subtitle boundary at the cut frame.
  - High/precise mode kept cut-boundary detection on the medium-level stride family, while the existing ffmpeg pipe visual scout was disabled by default.
  - Coarse stride can miss a short hard cut completely; rollback/refine only works after a candidate exists.
- 수정 요약:
  - Confirmed cuts now force split/snap at the exact frame in `split_segments_by_cut_boundaries()`.
  - Timeline cut-boundary work-lane lines now carry `alpha=128` and paint as 50% dimmed lines in the middle-category lane.
  - Precise/High mode enables ffmpeg pipe pioneer scout with source-fps sampling capped at 30fps, preserving Fast/Auto defaults.
  - NLE status was verified as read-only baseline, not full write-path migration.
- 단위/가드:
  - `./venv/bin/python -m py_compile core/cut_boundary.py core/cut_boundary_auto_scan.py core/runtime/config.py core/settings_profiles.py core/audio/stt_quality_presets.py ui/timeline/paint_passes.py ui/timeline/timeline_paint.py tests/test_cut_boundary_auto_scan_backend.py tests/test_mode_policy.py tests/test_subtitle_boundary_alignment.py tests/test_project_context.py tests/test_timeline_render_cache.py` -> pass
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_subtitle_boundary_alignment.py tests/test_project_context.py -k "cut_boundary or cut_boundaries or cut_frame_2677"` -> `6 passed, 93 deselected`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_render_cache.py -k "cut_boundary_work_lane"` -> `2 passed, 46 deselected`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_cut_boundary_auto_scan_backend.py tests/test_mode_policy.py -k "pipe_fps or source_fps or runtime_modes_apply_stage_policy"` -> `3 passed, 38 deselected`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_stt_preview_optimizer.py tests/test_gap_simulator.py -k "cut_boundary or magnetize"` -> `4 passed, 7 deselected`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_pipeline_cut_boundary_cache.py -k "split_by_saved_cut_boundaries or shift_cut_boundary_rows"` -> `2 passed, 20 deselected`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_snapshot.py` -> `9 passed, 4 subtests passed`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_roughcut_v2_output_compat.py` -> `4 passed`
  - `git diff --check -- .` -> pass
- 잼민이 handoff 판정:
  - `.agents/sentinel/handoffs/20260626-240300-nle-cut-boundary-support-review.md` -> `accept with correction`; NLE read-only status and coarse-stride risk accepted, NLE reverse-write treated as deferred compatibility gate.
- 정책 영향:
  - Cut-boundary timing policy intentionally changed per owner request: confirmed visual cuts now outrank final subtitle segment continuity.
  - High/precise cut-boundary scouting can spend more time to avoid coarse-stride misses.
  - No STT2 execution, LLM text policy, LoRA, save/load schema, release/tag/push/DMG behavior changed.

## VAD/STT 2-of-3 timing consensus - 2026-06-26

- 실행 모드: final subtitle timing hotfix for VAD-correct but late final subtitle starts.
- 결과: pass for focused timing/consensus guard tests.
- 원인 후보:
  - VAD가 정확히 음성 시작/끝을 잡아도, 단독 VAD pull은 STT anchor lead guard에 막혀 최종 row가 여전히 늦게 남을 수 있었다.
  - STT1/STT2/VAD 중 2개가 같은 길이와 경계를 지지하는 경우를 별도 상위 규칙으로 승격하지 않아 final timing이 약한 후보에 끌릴 수 있었다.
- 수정 요약:
  - Added `apply_vad_stt_timing_consensus()` as a final timing anchor.
  - VAD+STT1 or VAD+STT2 agreement uses the VAD span with edge pad.
  - STT1+STT2 agreement applies even when VAD disagrees or is missing.
  - Added default internal settings for start/end/duration tolerance and max VAD gap.
- 단위/가드:
  - `./venv/bin/python -m py_compile core/subtitle_quality/vad_alignment_checker.py core/engine/subtitle_engine.py tests/test_subtitle_quality_models.py` -> pass
  - `./venv/bin/python -m json.tool dataset/custom_defaults.json >/tmp/custom_defaults_check.json` -> pass
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_subtitle_quality_models.py -k "vad_voice_start_priority or vad_stt_timing_consensus"` -> `8 passed, 8 deselected`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_stt_ensemble.py tests/test_subtitle_boundary_alignment.py tests/test_subtitle_quality_models.py -k "stt_anchor or drift or vad_voice_start_priority or vad_stt_timing_consensus or boundary"` -> `21 passed, 44 deselected`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_subtitle_engine_settings.py -k "llm or stt_anchor or slot_order or text_only_lock"` -> `26 passed, 56 deselected`
  - `git diff --check -- .` -> pass
- 잼민이 handoff 판정:
  - `.agents/sentinel/handoffs/20260626-234500-timing-consensus-risk-review.md` -> `revise 후 accept`; VAD missing/STT1+STT2 consensus test was added.
- 정책 영향:
  - Subtitle timing policy intentionally changed per owner request: two agreeing sources among VAD/STT1/STT2 now override weaker final timing.
  - No UI/UX label/layout/color/shortcut/popup text, STT2 execution, model-selection, save/load, release, tag, push, or DMG behavior changed.

## LLM text-only timing lock and STT slot guard - 2026-06-26

- 실행 모드: final subtitle timing hotfix for `-1` adjacent STT slot drift and long High-mode window drift diagnostics.
- 결과: pass for focused guard tests.
- 원인 후보:
  - STT1/STT2 rows could be correct, but LLM chunk output was later redistributed across word timings, creating final rows with changed count/start/end.
  - Macro LLM chunks also redistributed grouped STT rows, which could attach corrected text to an adjacent STT slot.
  - VAD voice-start priority needed to be constrained to the same STT anchor so it could not pull a row into a previous subtitle slot.
- 수정 요약:
  - Added default-on `subtitle_llm_text_only_timing_lock_enabled`.
  - STT-backed `_process_one` and `_process_one_llm_only` now keep one original STT row and preserve `start`/`end` even when LLM returns multiple chunks.
  - STT-backed macro LLM groups now apply text only when chunk count exactly matches source row count; otherwise they keep source STT rows instead of redistributing chunks over timings.
  - Added final STT slot-order guard to restore timing when final text matches STT anchor `i` but timing is attached to adjacent anchor `i-1`/`i+1`.
  - Added `vad_voice_start_priority_max_stt_lead_sec=0.12` and windowed STT `asr_metadata.window_drift_report`.
- 단위/가드:
  - `./venv/bin/python -m py_compile core/engine/subtitle_engine.py core/engine/subtitle_final_integrity.py core/engine/subtitle_macro_chunks.py core/engine/subtitle_stt_candidate_selection.py core/subtitle_quality/vad_alignment_checker.py core/audio/media_processor_transcribe_windowed.py tests/test_subtitle_engine_settings.py tests/test_subtitle_quality_models.py tests/test_media_processor_overlap.py` -> pass
  - `./venv/bin/python -m json.tool dataset/custom_defaults.json >/tmp/custom_defaults_check.json` -> pass
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_subtitle_engine_settings.py -k "text_only_lock or slot_order or macro_chunk_stt_rows"` -> `4 passed, 78 deselected`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_subtitle_quality_models.py -k "vad_voice_start_priority"` -> `4 passed, 8 deselected`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_media_processor_overlap.py -k "windowed_span_finalize"` -> `2 passed, 102 deselected`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_subtitle_engine_settings.py tests/test_subtitle_boundary_alignment.py tests/test_stt_ensemble.py tests/test_media_processor_overlap.py tests/test_subtitle_quality_models.py -k "llm or stt_anchor or vad or windowed or drift"` initially passed once with `76 passed, 171 deselected`.
  - Later rerun of that broad `-k` command aborted in pre-existing `tests/test_media_processor_overlap.py::test_vad_retry_rejects_noisy_micro_segments` during native audio memory cleanup import; final current validation used split related subsets:
    - `tests/test_subtitle_engine_settings.py -k "llm or stt_anchor or slot_order or text_only_lock"` -> `26 passed, 56 deselected`
    - `tests/test_media_processor_overlap.py -k "windowed or drift"` -> `14 passed, 90 deselected`
    - `tests/test_stt_ensemble.py tests/test_subtitle_boundary_alignment.py tests/test_subtitle_quality_models.py -k "stt_anchor or drift or vad_voice_start_priority or boundary"` -> `17 passed, 44 deselected`
  - `git diff --check -- .` -> pass
- 잼민이 handoff 판정:
  - `.agents/sentinel/handoffs/20260626-221500-timing-lock-support-risk-review.md` -> `defer`; manual editor timing-lock risks were not directly applicable to this STT-backed LLM timing-source lock.
- 정책 영향:
  - Subtitle timing policy intentionally changed per owner request: STT1/STT2-backed rows are now the final timing source of truth against LLM chunk redistribution.
  - No UI/UX label/layout/color/shortcut/popup text, STT2 execution, model-selection, save/load, release, tag, push, or DMG behavior changed.

## Final VAD voice-start priority - 2026-06-26

- 실행 모드: subtitle timing hotfix for late final starts after VAD/STT detection.
- 결과: pass for focused VAD/timing guard tests; wider macro-chunk LLM failures remain classified as unrelated environment/local-Ollama path.
- 원인 후보:
  - STT 앙상블 직후 VAD post-align은 이미 있었지만, 이후 LLM/분할/문맥보정/출력후보선택/final cleanup을 지나면서 최종 subtitle start가 VAD/STT 후보보다 늦어질 수 있었다.
- 수정 요약:
  - Added `prioritize_vad_voice_starts()` to pull late subtitle starts back to the detected VAD speech onset.
  - Wired the final pass into the STT-candidate and LLM final output paths.
  - The pass updates only `start`/`timeline_start`, preserves `end` and text, clamps against the previous subtitle boundary, and records `asr_metadata.vad_voice_start_priority`.
- 단위/가드:
  - `./venv/bin/python -m py_compile core/subtitle_quality/vad_alignment_checker.py core/engine/subtitle_engine.py tests/test_subtitle_quality_models.py` -> pass
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_subtitle_quality_models.py tests/test_stt_ensemble.py -k "vad or voice_start"` -> `9 passed, 39 deselected`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_subtitle_quality_models.py tests/test_stt_ensemble.py -k "vad or voice_start" tests/test_subtitle_engine_settings.py -k "final_gap or stt_anchor or vad" tests/test_subtitle_boundary_alignment.py` -> `40 passed, 99 deselected`
  - `git diff --check -- .` -> pass
- 미해결 검증:
  - Full `tests/test_subtitle_engine_settings.py` had 2 failures in macro-chunk LLM tests because local Ollama availability handling rolled back before the mocked `ollama_split_text` call. This did not touch or exercise the new VAD voice-start priority path.
- 정책 영향:
  - Subtitle timing policy intentionally changed per owner request: VAD speech onset now has final-start priority when the final subtitle starts late inside the same speech span.
  - No UI/UX label/layout/color/shortcut/popup text, STT2, LLM, LoRA, model-selection, save/load, release, tag, push, or DMG behavior changed.

## Foreground-safe file dialog dispatch - 2026-06-26

- 실행 모드: project/media file dialog dispatch bug fix.
- 결과: pass
- 원인 후보:
  - 일반 `파일 선택`은 `_safe_open_file_names()`를 사용했지만, `프로젝트 열기`, `프로젝트 만들기`, `프로젝트에 영상 추가`, `멀티클립 클립 추가`는 `QFileDialog`를 직접 호출했다.
  - 직접 호출 경로는 startup optional work, home rebuild, editor AI release와 선택 후 dispatch가 경쟁할 수 있었다.
- 수정 요약:
  - `ProjectUIMixin._open_project`, `_create_project`, `_add_video_to_project`를 owner의 foreground-safe dialog wrapper로 연결했다.
  - `MultiClipEditor._on_add_clip`은 parent foreground dialog runner를 먼저 사용하고, 없으면 기존 direct `QFileDialog`로 fallback한다.
  - Dialog title/filter/start folder/UI label/layout/popup behavior는 변경하지 않았다.
- 단위/가드:
  - `./venv/bin/python -m py_compile ui/main/main_file_ops.py ui/project/project_panel.py ui/project/multiclip_panel.py tests/test_main_file_ops_nonfatal.py tests/test_multiclip_panel.py` -> pass
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_main_file_ops_nonfatal.py tests/test_multiclip_panel.py` -> `20 passed`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_main_file_ops_nonfatal.py tests/test_main_window_nonfatal.py tests/test_multiclip_panel.py` -> `42 passed`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_app_command_bridge.py -k "open_project or open_media"` -> `3 passed, 71 deselected`
  - `git diff --check -- .` -> pass
- 정책 영향:
  - No UI/UX label/layout/color/shortcut/popup text, STT2, LLM, LoRA, VAD, subtitle timing, model-selection, save/load, release, tag, push, or DMG behavior changed.

## NAS 50 truth-learning dry-run manifest - 2026-06-26

- 실행 모드: read-only NAS 50 truth-learning manifest and in-memory SRT dry-run.
- 결과: pass
- 수정 요약:
  - Added `core/personalization/nas_truth_learning.py` to parse only the primary `## 50 Action Items` section from `docs/NAS_SUBTITLE_BENCHMARK_50_PLAN.md`.
  - Added `tools/nas_truth_learning.py` for read-only manifest checks before LoRA/deep-policy promotion.
  - Added `tests/test_nas_truth_learning.py` for parser scope, fixed dataset split, missing-file reporting, and store-free dry-run truth row building.
- Dry-run 결과:
  - `items_total=50`, `present_pairs=50`, `missing_media=0`, `missing_subtitle=0`
  - `dataset_splits={'holdout': 5, 'train': 40, 'validation': 5}`
  - `fixture_roles={'calibration': 2, 'primary': 48}`
  - `analyzed_pairs=50`
  - `importable_truth_rows=17262`
  - `split_analysis_effective_rows=17322`
  - `excluded_parenthetical_rows=1978`
  - `skipped_empty_text=1003`, `skipped_pure_symbols=60`
- 단위/가드:
  - `./venv/bin/python -m py_compile core/personalization/nas_truth_learning.py tools/nas_truth_learning.py tests/test_nas_truth_learning.py` -> pass
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_nas_truth_learning.py tests/test_ground_truth_import.py` -> `12 passed`
- 정책 영향:
  - No UI/UX, STT2, LLM, LoRA runtime default, VAD, model-selection, project save/load, release, tag, push, or DMG behavior changed.

## NAS 50 split protocol and Heydealer cached High validation - 2026-06-26

- 실행 모드: NAS 50 reference-SRT split analysis + LLM/LoRA prompt protocol update + Heydealer cached High postprocess validation.
- 결과: pass for prompt/protocol update; reject for forcing runtime split floor to 13.
- 50-reference analysis:
  - Source: `docs/NAS_SUBTITLE_BENCHMARK_50_PLAN.md`
  - Artifact: `output/manual_verification/latest/nas_50_subtitle_split_protocol_20260626_203523/`
  - Files found: `50/50`
  - Effective speech rows after parenthetical/dash stripping: `17,322`
  - Compact-char distribution: `p25=9`, `p50=13`, `p75=17`, `p90=22`, `p95=25`
  - Accepted protocol id: `nas_50_reference_split.v1`
- 수정 요약:
  - Added `core/personalization/subtitle_split_protocol.py` with the NAS 50 split protocol constants.
  - Updated LLM hard rule and runtime LoRA prompt from the old `18~24자` default wording to the learned `target=13`, `normal=9~17`, `soft upper=22` protocol.
  - Kept this as prompt/protocol guidance only; did not change saved project format, UI, STT2, VAD, model selection, or default runtime split floor.
- Heydealer validation:
  - Source benchmark: `.codex_work/benchmarks/subtitle_pipeline_variants/20260626_204038/benchmark_results.json`
  - NAS result SRT: `/Volumes/photo/22_유튜브영상_개인/[20260209]헤이딜러광고/자막벤치/헤이딜러_최종_벤치_v04.00.17_splitproto_20260626.srt`
  - NAS report TXT: `/Volumes/photo/22_유튜브영상_개인/[20260209]헤이딜러광고/자막벤치/헤이딜러_최종_벤치_v04.00.17_splitproto_20260626.txt`
  - Manual summary: `output/manual_verification/latest/heydealer_split_protocol_validation_20260626_204038/summary.md`
  - Score: `quality_score 87.490 -> 87.623` (`+0.133`)
  - Segment count: `417 -> 417`; this is a timing/overlap improvement, not a count-alignment improvement.
  - Runtime log: LLM candidates `3`, LoRA/Deep/STT-confirmed rows `413`, so most rows bypassed LLM and prompt changes have limited reach on this cached run.
- Rejected candidate:
  - `protocol_13_floor_runtime_candidate` with `split_length_threshold=13`, `subtitle_lora_split_floor_chars=13`, `subtitle_common_split_target_chars=13`, `subtitle_common_split_hard_max_chars=22`
  - Result: `hypothesis_segments=537`, `quality_score=85.692`, `count_score=87.317`, `split_merge_start_timing_mae_sec=0.464`, `split_merge_overlap_score=70.119`
  - Decision: reject because count improved but start/overlap/local text quality regressed and review burden rose.
- 단위/가드:
  - `./venv/bin/python -m py_compile core/personalization/subtitle_split_protocol.py core/engine/subtitle_prompts.py core/personalization/runtime_lora_context.py tests/test_subtitle_rules_runtime.py tests/test_subtitle_llm_context_policy.py` -> pass
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_subtitle_rules_runtime.py tests/test_subtitle_llm_context_policy.py` -> `8 passed`
  - `git diff --check -- .` -> pass
- Jammini:
  - `.agents/sentinel/handoffs/20260626-203500-nas-50-split-protocol-risk-review.md` reviewed as `accept/revise/defer`.
  - Accepted: STT candidate-lock conflict risk, validation false-positive risk, need to avoid count-only promotion.
  - Revised: save/reopen forced-resegment risk is not introduced by this prompt-only patch.
  - Deferred: cross-device personalization divergence and VFR/drop-frame broader matrix.

## Heydealer High reference comparison and scoring-rule fix - 2026-06-26

- 실행 모드: NAS direct Heydealer final MP4/SRT High benchmark and rescoring.
- 결과: pass for scoring-rule correction; no generation-path improvement accepted.
- 기준 파일:
  - Media: `/Volumes/photo/22_유튜브영상_개인/[20260209]헤이딜러광고/헤이딜러_최종.MP4`
  - Reference SRT: `/Volumes/photo/22_유튜브영상_개인/[20260209]헤이딜러광고/헤이딜러_최종.srt`
- 수정 요약:
  - `tools/subtitle_benchmark_scoring.py` now excludes parenthetical comments and ASCII dash marks from benchmark text accuracy.
  - Timing score now uses start-weighted timing MAE (`start 70%`, `end 30%`) while preserving the existing `timing_mae_sec` field.
  - Added focused tests for parenthetical/dash exclusion and start-time priority.
- 산출물:
  - Summary: `output/manual_verification/latest/heydealer_high_reference_compare_20260626_181155/summary.md`
  - Rescore JSON: `output/manual_verification/latest/heydealer_high_reference_compare_20260626_181155/rescore_metrics.json`
  - Baseline High benchmark: `.codex_work/benchmarks/subtitle_pipeline_variants/20260626_175343/benchmark_results.json`
  - Drift candidate benchmark: `.codex_work/benchmarks/subtitle_pipeline_variants/20260626_180253/benchmark_results.json`
  - Cached timing candidate benchmark: `.codex_work/benchmarks/subtitle_pipeline_variants/20260626_180902/benchmark_results.json`
- Heydealer High rescore:
  - `quality_score`: `81.32 -> 82.48` after owner scoring rules.
  - `CER`: `0.160803 -> 0.134089`
  - `text_score`: `85.737 -> 88.093`
  - `start_weighted_timing_mae_sec`: `0.6154`
  - `start_timing_mae_sec`: `0.6427`, `end_timing_mae_sec`: `0.5516`
  - `reference/hypothesis`: `615/417`
- 후보 판정:
  - `mode_high_piecewise_drift`: rejected; same score and timing as baseline on Heydealer.
  - Cached timing variants: rejected; best candidate scored `75.539`, `start_weighted_timing_mae_sec=0.736`, and introduced `overlap_count=28`, `max_overlap=10.26`.
  - Current High generation path remains the accepted Heydealer path for this fixture.
- 단위/가드:
  - `./venv/bin/python -m py_compile tools/subtitle_benchmark_scoring.py tools/benchmark_subtitle_pipeline_variants.py` -> pass
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_benchmark_mode_profiles.py` -> `28 passed`
  - `git diff --check -- .` -> pass
- Jammini:
  - `.agents/sentinel/handoffs/20260626-180300-heydealer-benchmark-risk-review.md` reviewed as `accept with correction`.
  - Accepted: count-score false-negative risk, duration/last_end stability, need for parenthetical/dash filtering, and start-time-priority scoring.
  - Correction: the handoff path text had a timestamp typo in the read-file line; Dex verified the real file `.codex_work/benchmarks/subtitle_pipeline_variants/20260626_175343/benchmark_results.json` directly.

## Cayenne High cut-boundary E2E runner proof - 2026-06-26

- 실행 모드: Cayenne full-duration High benchmark with confirmed visual cut-boundary input.
- 결과: pass
- 수정 요약:
  - `tools/benchmark_subtitle_pipeline_variants.py` now accepts `--cut-boundaries-json`.
  - The benchmark runner applies the same source-app confirmed cut-boundary magnet/split post-processing path before scoring and artifact export.
  - This closes the validation gap where the source-app production function improved cut-starts but the standalone benchmark did not receive saved cut boundaries.
- 산출물:
  - Summary: `output/manual_verification/latest/cayenne_high_cut_boundary_e2e_20260626_1446/summary.md`
  - Generated SRT: `output/manual_verification/latest/cayenne_high_cut_boundary_e2e_20260626_1446/mode_high_cut_boundaries_output.srt`
  - Cut-aware benchmark JSON: `.codex_work/benchmarks/subtitle_pipeline_variants/20260626_144217/benchmark_results.json`
  - No-cut benchmark JSON: `.codex_work/benchmarks/subtitle_pipeline_variants/20260626_143345/benchmark_results.json`
  - Cut-boundary input: `output/manual_verification/latest/cayenne_cut_boundary_scan_20260626_1024/cut_boundaries.json`
- Cayenne High 전/후:
  - `final_segments`: `247 -> 247`
  - `quality_score`: `77.219 -> 77.315` (`+0.096`)
  - `timing_mae_sec`: `0.7111 -> 0.7018` (`-0.0093s`)
  - `visual cut within 1 frame`: `0.0% -> 100.0%`
  - `reference-start within 0.5s on 7 cut truth rows`: `57.143% -> 85.714%`
  - `reference cut-start score`: `51.821 -> 90.667`
- 판정:
  - Confirmed cut-boundary input을 넣은 High E2E는 7개 truth cut 모두 visual cut frame에 맞췄다.
  - `78.280s` reference start vs `78.900s` visual cut은 남은 수동 판정 리스크다. 현재 결과는 visual cut에는 정확히 맞고 reference start와는 `0.620s` 차이난다.
  - UI/UX, STT2, LLM, LoRA, VAD, model selection, save/load format, render output은 변경하지 않았다.
- 단위/가드:
  - `./venv/bin/python -m py_compile core/cut_boundary.py tests/test_subtitle_boundary_alignment.py ui/editor/video_player_widget.py ui/editor/video_player_transport.py ui/editor/video_player_surface.py tests/test_video_player_widget.py tools/benchmark_subtitle_pipeline_variants.py tests/test_benchmark_mode_profiles.py` -> pass
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_subtitle_boundary_alignment.py tests/test_video_player_widget.py` -> `87 passed`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_benchmark_mode_profiles.py -k 'cut_boundary_json or cut_boundary_application'` -> `2 passed, 24 deselected`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_benchmark_mode_profiles.py` -> `26 passed`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_context.py -k 'cut_boundaries or split_segments_by_cut_boundaries'` -> `3 passed, 82 deselected`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_pipeline_cut_boundary_cache.py -k 'split_by_saved_cut_boundaries or shift_cut_boundary_rows'` -> `2 passed, 20 deselected`
- Jammini:
  - `.agents/sentinel/handoffs/20260626-143500-cayenne-e2e-validation-checklist.md` reviewed as `accept`.
  - Accepted: parenthetical/dash scoring rules, start-time weighting, 7 cut-start truth rows, `78.280s` vs `78.900s` conflict tracking, count/first/last/end drift checks.

## Cayenne reference cut truth and frame-based playback display - 2026-06-26

- 실행 모드: Cayenne reference cut truth file generation plus Taption-style playback frame/time display.
- 결과: pass
- 컷 경계 판정:
  - Current detector/production snap looks good for the Cayenne scoring truth set on `6/7` cut-start cases.
  - Remaining conflict: visual cut `78.9s` is a real visual cut, but the reference subtitle starts at `78.28s`, so exact visual-cut snapping and reference-start matching disagree there.
- 산출물:
  - `test video/카이엔 일렉트릭 리뷰_reference_cut_boundaries.txt`
  - The file records `reference_start_sec`, zero-based `frame_index`, one-based `display_frame`, frame-based time, timecode, detected visual cut time, and reference text.
  - Media basis: `60fps`, `45695` frames, frame time rule `frame_time_sec = frame_index / fps`.
- 수정 요약:
  - Playback control bar now shows frame count as `current / total`.
  - Playback time label now uses frame-based time from `frame_time_map`, formatted with milliseconds as `current / total`.
  - Seek/frame-step updates refresh the frame-based time label immediately.
- 단위/가드:
  - `ffprobe -v error -select_streams v:0 -show_entries stream=r_frame_rate,avg_frame_rate,nb_frames,duration,time_base -show_entries format=duration -of json 'test video/카이엔 일렉트릭 리뷰.MP4'` -> `60/1`, `nb_frames=45695`, `duration=761.576667`
  - `./venv/bin/python -m py_compile core/cut_boundary.py tests/test_subtitle_boundary_alignment.py ui/editor/video_player_widget.py ui/editor/video_player_transport.py ui/editor/video_player_surface.py tests/test_video_player_widget.py` -> pass
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_subtitle_boundary_alignment.py tests/test_video_player_widget.py` -> `87 passed`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_context.py -k 'cut_boundaries or split_segments_by_cut_boundaries'` -> `3 passed, 82 deselected`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_pipeline_cut_boundary_cache.py -k 'split_by_saved_cut_boundaries or shift_cut_boundary_rows'` -> `2 passed, 20 deselected`
  - `git diff --check -- .` -> pass
- Jammini:
  - `.agents/sentinel/handoffs/20260626-130000-playback-display-risk-review.md` reviewed as `accept with correction`.
  - Accepted: layout/QML sync, frame map, and 59.94fps precision risks.
  - Correction: this slice reuses the existing control-bar/QML state path and does not add a new signal channel.

## Cayenne production visual cut start-snap improvement - 2026-06-26

- 실행 모드: production `core.cut_boundary.magnetize_segments_to_cut_boundaries` rescore using Cayenne visual cut scan and owner-corrected reference rules.
- 결과: pass for the focused improvement slice; start-first score and cut-start alignment improved without changing text, STT2, LLM, LoRA, VAD, model selection, UI/UX, save format, or render output.
- 수정 요약:
  - Added `snap_late_segment_starts_to_confirmed_cuts` for confirmed visual cuts.
  - A late subtitle start is pulled to the visual cut only when the previous subtitle reaches that cut boundary, limiting silent-gap overreach.
  - Existing confirmed/provisional cut magnet and split paths remain the owner route.
- Cayenne production-function rescore:
  - artifact: `output/manual_verification/latest/cayenne_production_cut_magnet_rescore_20260626_1227/summary.md`
  - visual cuts: `35.2`, `78.9`, `118.8667`, `426.6`, `591.1667`, `640.3667`, `730.5`
  - `mode_high`: `start_priority_score=66.629` (`+8.234`), `avg_start_error_sec=0.7321` (`-0.0124s`), `ref_start_within_0_5_pct=47.719` (`+1.052pp`), `cut_start_score=90.667` (`+38.868`), `ref_cut_start_within_0_5_pct=85.714` (`+28.571pp`), `avg_end_error_sec=0.7247` (`-0.0062s`), `final/reference=246/285`
  - `mode_high_piecewise_drift`: `start_priority_score=67.100` (`+8.240`), `avg_start_error_sec=0.7186` (`-0.0126s`), `ref_start_within_0_5_pct=48.421` (`+1.053pp`), `cut_start_score=90.667` (`+38.868`), `ref_cut_start_within_0_5_pct=85.714` (`+28.571pp`), `avg_end_error_sec=0.7243` (`-0.0063s`), `final/reference=247/285`
  - note: the `78.9s` visual cut is correctly snapped to the cut, while the reference subtitle starts at `78.28s`; this is the remaining cut-vs-reference-start conflict.
- 단위/가드:
  - `./venv/bin/python -m py_compile core/cut_boundary.py tests/test_subtitle_boundary_alignment.py` -> pass
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_subtitle_boundary_alignment.py` -> `12 passed`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_context.py -k 'cut_boundaries or split_segments_by_cut_boundaries'` -> `3 passed, 82 deselected`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_pipeline_cut_boundary_cache.py -k 'split_by_saved_cut_boundaries or shift_cut_boundary_rows'` -> `2 passed, 20 deselected`
  - Broader `tests/test_pipeline_cut_boundary_cache.py -k 'cut_boundary or split_by_saved_cut_boundaries or shift_cut_boundary_rows'` exposed 5 unrelated existing failures where tests still read a project file as JSON after the current binary `.aissproj` writer stores `AISS-PROJECT` payloads.
- Jammini:
  - `.agents/sentinel/handoffs/20260626-121900-cayenne-timing-improvement-risk-review.md` reviewed as `accept with correction`.
  - Accepted: no production reference-SRT dependency, avoid false confidence when visual cut metadata is missing, keep STT/LLM/VAD policy isolated.
  - Correction: the landed slice uses `core/cut_boundary.py` production cut magnetization, not `subtitle_timing.py` reference-aware correction.

## Cayenne High start-first and visual cut-start verification - 2026-06-26

- 실행 모드: existing Cayenne High outputs rescored against owner-corrected reference rules with subtitle start time weighted first and visual cut-start alignment checked.
- 결과: start-first partial improvement only; cut-start alignment did not improve; not accepted as a material Cayenne-quality improvement.
- 판정 기준:
  - Reference text inside `(...)` or `（...）` is comment text and must be excluded from scoring.
  - Reference rows that become empty after removing parenthetical comments are excluded.
  - Dash characters are ignored for text accuracy only.
  - Subtitle start time is weighted first; end time and text accuracy are secondary.
  - Visual cut starts are scanned from the Cayenne video and checked separately.
  - `start_priority_score = 0.35*start_mae_score + 0.15*ref_start_within_0_5_pct + 0.20*cut_start_score + 0.15*unique_ref_coverage_score + 0.10*end_mae_score + 0.05*text_score`
  - Cayenne reference rows changed from `291` to `285` for this score.
  - Visual cut scan found `7` medium visual cuts: `35.2`, `78.9`, `118.8667`, `426.6`, `591.1667`, `640.3667`, `730.5`.
- 결과:
  - `mode_high`: `start_priority_score=58.395`, `avg_start_error_sec=0.7445`, `p95_start_error_sec=2.3068`, `ref_start_within_0_5_pct=46.667`, `cut_start_score=51.799`, `ref_cut_start_within_0_5_pct=57.143`, `avg_end_error_sec=0.7309`, `text_score=82.193`, `CER=0.198945`, `final/reference=246/285`
  - `mode_high_piecewise_drift`: `start_priority_score=58.860`, `avg_start_error_sec=0.7312`, `p95_start_error_sec=2.3043`, `ref_start_within_0_5_pct=47.368`, `cut_start_score=51.799`, `ref_cut_start_within_0_5_pct=57.143`, `avg_end_error_sec=0.7306`, `text_score=82.279`, `CER=0.197940`, `final/reference=247/285`
  - Delta for `mode_high_piecewise_drift` vs `mode_high`: `start_priority_score +0.465`, `avg_start_error_sec -0.0133`, `ref_start_within_0_5_pct +0.701`, `cut_start_score +0.0`, `avg_end_error_sec -0.0003`
- 산출물:
  - `output/manual_verification/latest/cayenne_high_reference_start_first_cut_20260626_1038/summary.md`
  - `output/manual_verification/latest/cayenne_high_reference_start_first_cut_20260626_1038/summary.json`
  - `output/manual_verification/latest/cayenne_cut_boundary_scan_20260626_1024/cut_boundaries.json`
  - `output/manual_verification/latest/cayenne_high_reference_start_first_cut_20260626_1038/reference_without_parenthetical_comments.srt`
- 참고:
  - STT/LLM was not rerun for the rescore; existing `output_segments.json` artifacts from the Cayenne High runs were reused. A separate visual cut scan was run for the Cayenne video.
  - This is subtitle quality/timing evidence only. It does not validate NLE exact-join marker parity, render sidecar duration parity, or save/reopen write-path compatibility.
  - No UI/UX, subtitle timing policy, STT2, LLM, LoRA, VAD, model-selection, save file, or render-output code changed.

## v04.00.17 source-app NLE baseline release - 2026-06-26

- 실행 모드: release checkpoint metadata/doc sync for completed source-app internal NLE read-only baseline, roughcut render/export snapshot routing, and X5 standard fixture QA hardening.
- 결과: pass
- 수정/확인 항목:
  - `core/runtime/config.py` app version updated to `04.00.17`.
  - `core/project/project_format.py` project schema version updated to `04.00.17`.
  - `RELEASE_v04.00.17.md`, `README.md`, `AGENTS.md`, `ACTION_ITEMS.md`, `docs/PROJECT_STATE.md`, `docs/HANDOFF.md`, and `docs/VALIDATION.md` synced to the new checkpoint.
  - UI/UX, subtitle quality policy, STT/LLM/VAD/model selection, and timing algorithms were not changed in this closeout slice.
- 단위/가드:
  - `./venv/bin/python -m py_compile core/runtime/config.py core/project/project_format.py ui/roughcut/roughcut_export.py tools/qa_suite_runner.py tests/test_project_nle_snapshot.py tests/test_qa_suite_runner.py tests/test_roughcut_ui_v2.py` -> pass
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_snapshot.py tests/test_project_context.py tests/test_project_segment_reload.py tests/test_editor_srt_open_refresh.py tests/test_roughcut_engine1.py tests/test_roughcut_v2_output_compat.py tests/test_roughcut_ui_v2.py` -> `269 passed, 4 subtests passed`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_app_command_bridge.py tests/test_qa_suite_runner.py` -> `103 passed`
  - `AI_SUBTITLE_STUDIO_QA_USE_SOURCE=1 ./venv/bin/python tools/qa_suite_runner.py full --output-dir output/manual_verification/latest/qa_suite_full_standard_x5_restored_20260626_0901` -> pass, `passed_count=9`, `failed_count=0`
  - `git diff --check -- .` -> pass
- 산출물:
  - `RELEASE_v04.00.17.md`
  - `output/manual_verification/latest/qa_suite_full_standard_x5_restored_20260626_0901`
- 참고:
  - DMG/sign/notarization/App Store upload은 실행하지 않았다. DMG packaging은 명시 요청 시에만 별도 범위로 다룬다.
  - X5 표준 fixture `test video/X5_시승기_후반.MP4`는 ignored local media로 복원되어 있으며 커밋 대상이 아니다.

## v04.00.16 source-app checkpoint release - 2026-06-26

- 실행 모드: release checkpoint metadata/doc sync for roughcut exact-join, sync-safe render, app-command, fast-exit, and internal NLE architecture planning work.
- 결과: pass
- 수정/확인 항목:
  - `core/runtime/config.py` app version updated to `04.00.16`.
  - `core/project/project_format.py` project schema version updated to `04.00.16`.
  - `RELEASE_v04.00.16.md`, `README.md`, `AGENTS.md`, `ACTION_ITEMS.md`, `docs/PROJECT_STATE.md`, `docs/HANDOFF.md`, and `File_structure.txt` synced to the new checkpoint.
  - UI/UX, subtitle quality policy, STT/LLM/VAD/model selection, and timing algorithms were not changed in this closeout slice.
- 단위/가드:
  - `./venv/bin/python -m py_compile core/runtime/config.py core/project/project_format.py` -> pass
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_context.py tests/test_project_segment_reload.py tests/test_qa_suite_runner.py tests/test_app_command_bridge.py tests/test_roughcut_engine1.py tests/test_roughcut_ui_v2.py` -> `332 passed`
  - `AI_SUBTITLE_STUDIO_QA_USE_SOURCE=1 ./venv/bin/python tools/qa_suite_runner.py quick` -> pass, `failed_count=0`
- 산출물:
  - `RELEASE_v04.00.16.md`
  - `output/manual_verification/latest/qa_suite_quick_20260626_011235`
- 참고:
  - DMG/sign/notarization/App Store upload은 실행하지 않았다. DMG packaging은 명시 요청 시에만 별도 범위로 다룬다.
  - 기존 `v04.00.16` git tag가 오래된 side-branch checkpoint를 가리켜 이번 mainline closeout에서는 태그를 이동하거나 덮어쓰지 않는다.

## Runtime resource labels, CLI compatibility, X5 benchmark, full regression - 2026-05-23

- 실행 모드: behavior-preserving `subtitle_resource_manager`/runtime active-label facade extraction + CLI/test compatibility fix + X5 High 180s reference benchmark.
- 결과: pass
- 수정/확인 항목:
  - `RuntimeResourceCoordinator`의 자막 파이프라인 활성 라벨 판단을 `core/runtime/subtitle_resource_manager.py` 순수 함수로 이동해 `pipeline/fast/cut_boundary/editor/stt/subtitle_llm/subtitle_optimize/roughcut_llm/exit` 판단을 공유.
  - 사용자/깨진 `llm_threads`와 `llm_workers` 설정값은 보존하고, Apple Silicon cap은 `llm_threads_resource_max` 등 resource max 경로로 적용하도록 보정.
  - `tools.verify_full_media_pipeline.run_full_verification()` 공개 wrapper를 복구해 `subtitle_regression_pack`/Tiniping mode-search 테스트 수집 실패를 수정.
  - 전역 training-interrupt 테스트 격리, collapsed voice/analysis lane 클릭의 subtitle select 방지, simplified settings에서 hidden roughcut LLM 자동 활성화 방지를 수정.
  - UI/UX 시나리오, STT1/STT2 선택 정책, LLM/LoRA 품질 게이트, 자막 텍스트/타이밍 정책은 변경하지 않음.
- X5 실측:
  - artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260523_205429/benchmark_results.md`
  - `quality_score=87.402`, `CER=0.088391`, `global_text_similarity=0.954667`, `timing_mae_sec=0.5742`, `raw/final=59/57`, `elapsed_sec=70.293`
  - accelerator log: STT1 WhisperKit ANE/GPU concurrency `2`, selective STT2 `14 blocks`, word precision ANE/GPU concurrency `10`.
- 단위/가드:
  - runtime/appctl/timeline/STT/mode targeted guards: pass (`102 passed`, `25 passed`, `7 passed`, focused roughcut/editor/timeline guards passed)
  - full Python regression: pass (`2634 passed, 1 warning, 5 subtests passed in 218.77s`)
  - app bundle rebuild/validation: pass (`dist/macos/AI Subtitle Studio.app`; unsigned warning only)
  - packaged app status after relaunch: pass (`ok=true`, `editor_open=false`, `backend_active=false`, `pressure_stage=normal`, `active_labels=[]`)
- 산출물: `output/manual_verification/latest/20260523_runtime_resource_labels_x5_fullsuite/verification_summary.md`
- 참고:
  - 이번 slice는 전체 `Subtitle Generation Domain Split And Native Acceleration Plan` 완료가 아니라 `subtitle_resource_manager`/runtime active-label facade + compatibility hardening sub-slice 완료임. 메인 active item은 계속 남김.

## Mac native action items and X5 reference rerun - 2026-05-23

- 실행 모드: behavior-preserving Mac native/STT/UI hot-path action-item execution + X5 High 180s reference benchmark.
- 결과: pass after rejecting one over-aggressive STT2 High-budget candidate.
- 수정/확인 항목:
  - Apple Silicon full-core native path, Swift resource allocator, WhisperKit/Core ML compute-profile handoff, VideoToolbox/Metal/GPU hints, and native resource plan reporting remain active.
  - Fast/Auto STT2는 더 적극적으로 유지하되, High/Precise STT2는 X5 timing-safe budget으로 되돌림: threshold `78`, max segments `24`, max audio `110s`, min improvement `2.0`.
  - `appctl start-multiclip` 자동화 기본 정책을 `--reuse-existing no`로 명시. 기존 sibling SRT는 `자막백업`으로 이동 후 새로 생성하며, `yes`/`ask`는 명시 선택 가능.
  - completed automation-4 multiclip reuse-policy item removed from `ACTION_ITEMS.md`.
  - UI/UX scenario, subtitle quality policy, STT1/STT2 full-parallel opt-in policy, LLM conservative gates unchanged.
- Rejected candidate:
  - artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260523_203930/benchmark_results.md`
  - `quality_score=80.561`, `CER=0.168865`, `timing_mae_sec=0.7765`, `raw/final=64/62`, `elapsed_sec=139.900`
  - rejection reason: High STT2 threshold `82` / max `36` selected too many candidates (`47 -> 35`) and regressed timing/text quality.
- Accepted X5 실측:
  - artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260523_204316/benchmark_results.md`
  - `quality_score=87.402`, `CER=0.088391`, `global_text_similarity=0.954667`, `timing_mae_sec=0.5742`, `raw/final=59/57`, `elapsed_sec=79.317`
  - accelerator log: STT1 WhisperKit ANE/GPU concurrency `2`, selective STT2 `14 blocks`, word precision ANE/GPU concurrency `10`.
- 단위/가드:
  - broad modified-surface Python guard: pass (`386 passed`)
  - Swift NativeResourceAllocatorTests: pass (`9 tests, 0 failures`)
  - STT2/recheck/straggler guard: pass (`50 passed, 84 deselected`)
  - post-tuning STT/mode guard: pass (`71 passed, 84 deselected`)
  - appctl/multiclip reuse policy guard: pass (`6 passed`)
- 산출물: `output/manual_verification/latest/20260523_action_items_mac_native_x5/verification_summary.md`

## Subtitle resource-manager accelerator flag report - 2026-05-23

- 실행 모드: Apple Silicon subtitle resource-manager flag parsing hardening + X5 High 180s reference benchmark
- 결과: pass
- 수정/확인 항목:
  - `core/runtime/subtitle_resource_manager.py`를 추가해 `_apple_m_pipeline_parallel_plan` accelerator/report boolean 해석을 분리.
  - 문자열 false/off/0/disabled 설정이 benchmark plan artifact에서 GPU/Metal/VideoToolbox/WhisperKit native allocator enabled로 잘못 기록될 수 있는 버그를 수정.
  - UI/UX 시나리오, STT1/STT2 선택 정책, LLM/LoRA 품질 게이트, 자막 텍스트/타이밍 정책은 변경하지 않음.
- 단위/가드:
  - py_compile: pass
  - targeted Apple M resource plan tests: pass (`3 passed`)
  - broader runtime/setting/benchmark/native guard: pass (`68 passed`)
- X5 실측:
  - artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260523_195117/benchmark_results.md`
  - `quality_score=87.402`, `CER=0.088391`, `global_text_similarity=0.954667`, `timing_mae_sec=0.5742`, `raw/final=59/57`, `elapsed_sec=73.604`
  - latest accepted full-core quality/timing baseline 대비 quality/CER/timing/raw/final unchanged.
  - accelerator log: STT1 `2 chunks`, selective STT2 `14 blocks`, word precision `10 chunks`; full parallel STT remains disabled unless explicitly requested.
- 산출물: `output/manual_verification/latest/20260523_resource_manager_flag_report/verification_summary.md`
- 참고:
  - 이번 slice는 전체 `Subtitle Generation Domain Split And Native Acceleration Plan` 완료가 아니라 `subtitle_resource_manager` facade/flag-report sub-slice 완료임. 메인 active item은 계속 남김.

## Metal/GPU resource hints and full-core plan accuracy - 2026-05-23

- 실행 모드: full-core Mac native resource hint hardening + X5 High 180s reference benchmark
- 결과: pass
- 수정/확인 항목:
  - full-core profile에서 `audio_torch_gpu_enabled`, `ffmpeg_videotoolbox_decode_enabled`, `scan_cut_pioneer_pipe_hwaccel_enabled`, `lora_gpu_acceleration_enabled`를 명시적으로 켜 stale manual setting이 benchmark full-core 경로를 낮추지 않게 함.
  - `_apple_m_pipeline_parallel_plan`의 `native_threads`, `audio_workers`, `llm_workers`, `llm_resource_max`, `local_llm_workers`가 full-core override 이후 실제 적용값을 기록하도록 보정.
  - Swift `NativeResourceAllocator` 기본 pipeline 요청에 `audio_ml`, `diarize`를 추가하고, VAD/audio-ML/diarize에는 `metal_ml_balanced` GPU 힌트를 부여. ANE는 WhisperKit/Core ML STT 전용으로 유지.
  - UI/UX 시나리오, STT1/STT2 선택 정책, LLM/LoRA 품질 게이트, 자막 텍스트/타이밍 정책은 변경하지 않음.
- 단위/가드:
  - py_compile: pass
  - targeted runtime/ffmpeg/torch tests: pass (`10 passed`)
  - broader runtime/benchmark/native guard: pass (`62 passed`)
  - Swift NativeResourceAllocatorTests: pass (`9 tests, 0 failures`)
  - app bundle rebuild: pass (`dist/macos/AI Subtitle Studio.app`)
  - app bundle validation: pass (`validate_app_bundle.sh`; unsigned warning only)
- X5 실측:
  - artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260523_194503/benchmark_results.md`
  - `quality_score=87.402`, `CER=0.088391`, `global_text_similarity=0.954667`, `timing_mae_sec=0.5742`, `raw/final=59/57`, `elapsed_sec=73.858`
  - latest accepted full-core quality/timing baseline 대비 quality/CER/timing/raw/final unchanged.
  - accelerator log: STT1 `2 chunks`, STT2 `8 chunks`, word precision `10 chunks`; full parallel STT remains disabled unless explicitly requested.
- 산출물: `output/manual_verification/latest/20260523_metal_gpu_resource_hints/verification_summary.md`
- 참고:
  - 이번 slice는 전체 `Subtitle Generation Domain Split And Native Acceleration Plan` 완료가 아니라 Metal/GPU resource hint 및 full-core plan accuracy sub-slice 완료임. 메인 active item은 계속 남김.

## Full-core native accelerator budget - 2026-05-23

- 실행 모드: Apple Silicon full-core/native allocator budget hardening + X5 High 180s reference benchmark
- 결과: pass
- 수정/확인 항목:
  - full-core profile에서 Swift native resource allocator reserve를 `0`으로 명시해 Python runtime reserve와 Swift allocator reserve 불일치를 제거.
  - full-core profile에서 WhisperKit native allocator worker raise, native compute profile `auto`, NPU prefer, precision GPU saturation을 명시.
  - Swift native allocator가 `apple_m_full_core_throughput`/`apple_m_full_core_aggressive_enabled`를 인식해 normal pressure pipeline의 CPU budget과 audio/STT precision cap을 전체 logical core budget까지 열도록 보정.
  - UI/UX 시나리오, STT1/STT2 선택 정책, full parallel STT opt-in 정책, 자막 텍스트/타이밍 정책은 변경하지 않음.
- 단위/가드:
  - py_compile: pass
  - targeted runtime/media/native allocator tests: pass (`6 passed`)
  - runtime/STT recheck guard: pass (`39 passed`)
  - Swift NativeResourceAllocatorTests: pass (`8 tests, 0 failures`)
  - app bundle rebuild: pass (`dist/macos/AI Subtitle Studio.app`)
  - app bundle validation: pass (`validate_app_bundle.sh`; unsigned warning only)
- X5 실측:
  - artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260523_193659/benchmark_results.md`
  - `quality_score=87.402`, `CER=0.088391`, `global_text_similarity=0.954667`, `timing_mae_sec=0.5742`, `raw/final=59/57`, `elapsed_sec=74.169`
  - latest accepted full-core quality/timing baseline 대비 quality/CER/timing/raw/final unchanged.
  - accelerator log: STT1 `2 chunks`, STT2 `8 chunks`, word precision `10 chunks`; full parallel STT remains disabled unless explicitly requested.
- 산출물: `output/manual_verification/latest/20260523_full_core_native_accelerator_budget/verification_summary.md`
- 참고:
  - 이번 slice는 전체 `Subtitle Generation Domain Split And Native Acceleration Plan` 완료가 아니라 full-core native accelerator/resource-manager sub-slice 완료임. 메인 active item은 계속 남김.

## Automation-4 open/save/export command split - 2026-05-23

- 실행 모드: app-command bridge project open/save/export fix + rebuilt bundled app major QA
- 결과: pass
- 수정/확인 항목:
  - `open-project` 내부 `PermissionError`/`EPERM`/`EACCES`를 generic `execution_exception` 대신 `project_open_permission_denied`로 분리해 artifact에서 권한 실패를 바로 판별할 수 있게 함.
  - 프로젝트 open 시 외부 `subtitles.srt_path`를 project-relative path로 해석해 editor `_last_saved_srt_outputs`에 보존.
  - `save-subtitles`/`export-subtitles`/`export-subtitle-video` 실패 데이터를 `segment_count`, 기존 output, missing output 기준으로 분리.
  - 실제 editor의 `export-subtitle-video`는 긴 render를 UDP command에서 동기 실행하지 않고 기존 background scheduler로 넘겨 `queued=true`를 반환.
  - UI/UX, 자막 텍스트/타이밍, STT/VAD/LLM 품질 정책은 변경하지 않음.
- 단위/가드:
  - py_compile: pass
  - `tests/test_app_command_bridge.py`: pass (`60 passed`)
  - `tests/test_project_segment_reload.py`: pass (`70 passed`)
  - `tests/test_appctl.py tests/test_remote_verify_actions.py tests/test_qa_suite_runner.py`: pass (`17 passed`)
  - `git diff --check`: pass
- 실앱 검증:
  - app bundle rebuild: pass (`dist/macos/AI Subtitle Studio.app`)
  - major QA artifact: `output/manual_verification/latest/20260523_action_items_app_command_save_export_rerun`
  - major QA result: pass (`failed_count=0`)
  - `save_export_macau`: `open_project`, `save_project`, `save_subtitles`, `export_subtitles`, `export_subtitle_video` all pass; video export returns `subtitle_video_export_queued`.
- 남은 위험:
  - 멀티클립 `--reuse-existing yes/no` 자동화 분리 케이스는 별도 action item으로 남김.

## Native LLM allocator full-core slice - 2026-05-23

- 실행 모드: native Swift resource allocator handoff for local subtitle/roughcut LLM worker planning + X5 High 180s reference benchmark
- 결과: pass for quality/timing, neutral for this X5 elapsed
- 수정/확인 항목:
  - `runtime_llm_worker_plan()`이 local subtitle LLM / subtitle optimize / roughcut LLM 워커 수를 Swift native allocator에 요청하도록 연결.
  - full-core mode에서 `llm_workers`와 실제 엔진이 읽는 `llm_threads`를 맞춰 alias 불일치로 LLM 워커가 낮게 남는 문제를 보정.
  - Python native-resource priority에 `subtitle_optimize`, `audio_extract`, `audio`, `vad`, `diarize`, `audio_ml`을 추가해 Swift allocator와 priority를 맞춤.
  - API LLM은 기존처럼 native allocator를 거치지 않고 1 worker 유지.
  - UI/UX 시나리오, 자막 품질 정책, STT1/STT2 선택/재검사 정책, LLM 보수 게이트, 자막 타이밍 정책은 변경하지 않음.
- 단위/가드:
  - py_compile: pass
  - runtime/native resource allocator tests: pass (`41 passed`)
  - Swift NativeResourceAllocatorTests: pass (`7 tests, 0 failures`)
- X5 실측:
  - artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260523_163616/benchmark_results.md`
  - `quality_score=87.402`, `CER=0.088391`, `global_text_similarity=0.954667`, `timing_mae_sec=0.5742`, `raw/final=59/57`, `elapsed_sec=72.257`
  - latest accepted full-core baseline 대비 quality/timing/CER unchanged, elapsed `68.032s -> 72.257s`
  - STT1/2/word precision concurrency: `2/8/10 chunks`, 장기 tail 대기 로그(`31/32 chunks`) 재현 안 됨.
  - LLM worker log: `3개 워커`; 이번 X5 slice는 conservative gate 결과 `LLM 후보 0개`라 elapsed speed-up으로는 드러나지 않음.
- 산출물: `output/manual_verification/latest/20260523_native_llm_allocator_full_core/verification_summary.md`
- 참고:
  - 이번 slice는 전체 `Subtitle Generation Domain Split And Native Acceleration Plan` 완료가 아니라 LLM/native allocator 연결 sub-slice 완료임. 메인 active item은 계속 남김.

## First file dialog guard - 2026-05-23

- 실행 모드: first-launch file dialog foreground guard + targeted UI tests
- 결과: pass
- 수정/확인 항목:
  - 첫 실행 직후 파일 다이얼로그가 열려 있는 동안 홈 iCloud/NAS 자동소스 refresh가 홈/sidebar UI를 재빌드하지 않도록 보류.
  - 파일/프로젝트/폴더 다이얼로그 wrapper에 `_file_dialog_active` foreground guard를 추가하고, 선택이 있으면 stale 홈 refresh를 버리며 취소/무선택일 때만 보류된 홈 refresh를 재실행.
  - 저장된 시작 폴더가 파일이거나 없는 경로면 홈 폴더로 보정.
  - UI/UX 시나리오, 라벨/레이아웃, 자막 품질 정책, STT/VAD/LLM 경로는 변경하지 않음.
- 단위/가드:
  - py_compile: pass
  - file dialog guard tests: pass (`5 passed`)
  - related home/folder navigation tests: pass (`3 passed`)
- 산출물: `output/manual_verification/latest/20260523_first_file_dialog_guard/verification_summary.md`

## Processing-time thumbnail ffmpeg guard - 2026-05-23

- 실행 모드: processing-time thumbnail hot-path guard + targeted tests + X5 High 180s reference benchmark
- 결과: pass
- 수정/확인 항목:
  - 자막 생성/STT/live preview 처리 중 playhead/preview thumbnail seek가 새 ffmpeg thumbnail extraction을 동기 실행하지 않도록 차단.
  - 이미 캐시된 thumbnail은 그대로 재사용하고, cache miss일 때만 처리 중 새 생성 작업을 건너뜀.
  - UI/UX 시나리오, 자막 품질 정책, STT/LLM 모델 선택, LLM 권한, 최종 자막 선택 정책은 변경하지 않음.
- 단위/가드:
  - py_compile: pass
  - processing thumbnail targeted tests: pass (`4 passed`)
- X5 실측:
  - artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260523_160923/benchmark_results.md`
  - `quality_score=87.402`, `CER=0.088391`, `global_text_similarity=0.954667`, `timing_mae_sec=0.5742`, `raw/final=59/57`, `elapsed_sec=68.032`
  - same full-core overlap baseline 대비 quality/timing unchanged, elapsed `72.202s -> 68.032s`
  - latest accepted baseline 대비 quality `-0.100`, timing MAE `+0.0053s`
  - 산출물: `output/manual_verification/latest/20260523_processing_thumbnail_ffmpeg_guard/verification_summary.md`
- 참고:
  - broad video-player sweep에서 기존 control-bar inset 기대값 불일치 1건이 남아 있으나, 이번 slice의 thumbnail processing guard 범위 밖이고 UI/UX 변경 금지 원칙에 따라 건드리지 않음.
  - 이번 slice는 전체 `Subtitle Generation Domain Split And Native Acceleration Plan` 완료가 아니라 processing-time ffmpeg thumbnail hot-path 제거 sub-slice 완료임. 메인 active item은 계속 남김.

## WhisperKit native compute profile handoff - 2026-05-23

- 실행 모드: STT submit hot-path patch + targeted/broad tests + X5 High 180s reference benchmark
- 결과: pass
- 수정/확인 항목:
  - native Swift allocator의 `compute_units` 결과를 Python WhisperKit submit 경로의 `compute_profile`로 연결.
  - 기본값을 `stt_whisperkit_compute_profile=auto`로 두어 normal pressure의 `compute_units=all`이 Swift worker `.all`로 전달되게 함.
  - 명시 override는 그대로 우선하며, critical/no-plan 경로는 기존 보수값 `ane_gpu`로 fallback.
  - UI/UX 시나리오, 자막 품질 정책, STT/LLM 모델 선택, LLM 권한은 변경하지 않음.
- 단위/가드:
  - py_compile: pass
  - targeted WhisperKit compute/profile tests: pass (`4 passed`)
  - broader STT/runtime/settings guard: pass (`179 passed, 3 subtests passed`)
- X5 실측:
  - artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260523_160000/benchmark_results.md`
  - `quality_score=87.402`, `CER=0.088391`, `global_text_similarity=0.954667`, `timing_mae_sec=0.5742`, `raw/final=59/57`, `elapsed_sec=72.202`
  - latest accepted baseline 대비 quality `-0.100`, timing MAE `+0.0053s`, elapsed `-19.590s`
  - 산출물: `output/manual_verification/latest/20260523_whisperkit_native_compute_profile/verification_summary.md`
- 참고:
  - 이번 slice는 전체 `Subtitle Generation Domain Split And Native Acceleration Plan` 완료가 아니라 native allocator compute-profile handoff sub-slice 완료임. 메인 active item은 계속 남김.

## STT preview lane stability - 2026-05-23

- 실행 모드: Timeline/STT preview visual bug fix + targeted project/live-preview tests
- 결과: pass
- 수정/확인 항목:
  - STT1/STT2 preview 후보가 2줄로 갈라질 때 `stt_preview_sublane`, `stt_preview_sublane_count`를 붙여 위/아래 위치가 playback/viewport 변화로 뒤집히지 않게 고정.
  - Timeline paint, hit-test, SceneGraph, live-preview restore/trim/undo/partial-rerun 경로가 explicit sublane metadata를 우선 사용.
  - `score_color`, `stt_score_color`, `stt_score`, `quality.confidence_score`가 STT preview fill/border를 바꾸지 못하게 분리. STT 후보 박스는 STT1/STT2 source별 고정 색만 사용.
  - 프로젝트 저장 STT preview metadata에 sublane 필드를 보존.
  - 자막 생성 정책, STT/LLM 모델, UI/UX 시나리오는 변경하지 않음.
- 단위/가드:
  - py_compile: pass
  - STT lane/fixed-fill/project/live-preview targeted tests: pass (`29 passed`)
- 산출물: `output/manual_verification/latest/20260523_stt_preview_lane_stability/verification_summary.md`
- 참고:
  - full `tests/test_timeline_segment_colors.py`에는 현재 subtitle detection 기대값 불일치 2건이 남아 있음. 이번 STT preview lane/fill 변경 범위 밖이며, targeted STT preview 검증은 모두 통과.

## STT duration-first native scheduler - 2026-05-23

- 실행 모드: Native C++ helper parity + targeted STT scheduler tests + X5 High 180s reference benchmark
- 결과: pass for quality/timing, not claimed as a speed record
- 수정/확인 항목:
  - `Fast-STT2`와 `STT-단어정밀` 보강 패스에서 긴 chunk를 먼저 WhisperKit rolling pool에 제출하도록 native duration-order helper를 추가.
  - worker 응답 index를 원래 timeline index로 재매핑해 자막 emit/save 순서는 시간순으로 유지.
  - UI/UX, 자막 LLM, STT 모델 선택, 품질 게이트, 최종 자막 정책은 변경하지 않음.
- 단위/가드:
  - `venv/bin/python -m py_compile core/native_stt_recheck.py core/audio/media_processor_transcribe.py core/audio/stt_recheck_service.py tests/test_stt_recheck_service.py tests/test_media_processor_overlap.py`: pass
  - native backend smoke: `backend=cpp`, sample duration order `[1, 2, 0, 3]`
  - focused STT scheduler/straggler tests: pass (`5 passed`)
  - broader STT guard: pass (`39 passed`)
- X5 실측:
  - artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260523_151350/benchmark_results.md`
  - `quality_score=87.502`, `CER=0.084433`, `global_text_similarity=0.95658`, `timing_mae_sec=0.5689`, `raw/final=59/56`, `elapsed_sec=91.792`
  - Fast-STT2 duration-first order `[5, 11, 9, 13, 7, 10, 1, 0]...`, concurrency `8`
  - 단어정밀 duration-first order `[40, 6, 12, 4, 18, 42, 31, 14]...`, concurrency `10`
  - 산출물: `output/manual_verification/latest/20260523_stt_duration_first_native_scheduler/verification_summary.md`
- 참고:
  - 이번 slice는 전체 `Subtitle Generation Domain Split And Native Acceleration Plan` 완료가 아니라 STT 보강 패스 scheduler sub-slice 완료임. 메인 active item은 계속 남김.
  - 이번 X5 run은 Ollama 자동 시작이 포함되어 새 최고 속도로 주장하지 않음. 품질/타이밍 보존과 tail-wait 방어만 채택.

## Native recheck budget planner - 2026-05-23

- 실행 모드: Native C++ helper parity + targeted STT rescue tests + X5 High 180s reference benchmark
- 결과: pass
- 수정/확인 항목:
  - STT2 저신뢰/누락 후보 재검사 예산 선정의 deterministic ranking/budget 계산을 기존 C++ native STT recheck helper로 분리.
  - `core/audio/stt_rescue.py`는 native helper가 가능하면 후보 index만 받고 기존 `SttRecheckRange`를 구성하며, native 비활성/실패 시 기존 Python 경로로 즉시 fallback.
  - UI/UX, 자막 LLM, STT 모델 선택, 품질 게이트, 최종 자막 정책은 변경하지 않음.
- 단위/가드:
  - `venv/bin/python -m py_compile core/native_stt_recheck.py core/audio/stt_rescue.py core/audio/stt_recheck_service.py tests/test_stt_recheck_service.py`: pass
  - `venv/bin/python -m pytest tests/test_stt_recheck_service.py::STTRecheckServiceTests::test_budget_recheck_ranges_match_python_fallback_when_native_available tests/test_stt_recheck_service.py::STTRecheckServiceTests::test_selective_secondary_recheck_ranges_deduplicate_overlapping_candidates_before_budget tests/test_stt_recheck_service.py::STTRecheckServiceTests::test_word_precision_ranges_match_python_fallback_when_native_available`: pass (`3 passed`)
  - `venv/bin/python -m pytest tests/test_stt_recheck_service.py tests/test_media_processor_overlap.py::MediaProcessorOverlapTests::test_word_precision_ranges_respect_audio_budget tests/test_media_processor_overlap.py::MediaProcessorOverlapTests::test_whisperkit_precision_aggressive_gpu_raises_slots_under_normal_pressure tests/test_media_processor_overlap.py::MediaProcessorOverlapTests::test_word_precision_straggler_skips_last_chunk_and_keeps_pipeline_moving tests/test_media_processor_overlap.py::MediaProcessorOverlapTests::test_stt_recheck_straggler_skips_remaining_chunks_without_full_fallback`: pass (`35 passed`)
  - native backend smoke: `backend=cpp`, sample selected indices `[2, 3, 1]`
- X5 실측:
  - artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260523_150222/benchmark_results.md`
  - `quality_score=87.502`, `CER=0.084433`, `global_text_similarity=0.95658`, `timing_mae_sec=0.5689`, `raw/final=59/56`, `elapsed_sec=88.829`
  - STT1 WhisperKit ANE/GPU concurrency `2`, Fast-STT2 safe fallback concurrency `8`, 단어정밀 concurrency `10`
  - 산출물: `output/manual_verification/latest/20260523_native_recheck_budget_planner/verification_summary.md`
- 참고:
  - 이번 slice는 전체 `Subtitle Generation Domain Split And Native Acceleration Plan` 완료가 아니라 STT rescue budget planner native sub-slice 완료임. 메인 active item은 계속 남김.

## Native word precision candidate planner - 2026-05-23

- 실행 모드: Native C++ helper parity + targeted STT precision tests + X5 High 180s reference benchmark
- 결과: pass
- 수정/확인 항목:
  - 단어정밀 재인식 후보 선정의 deterministic ranking/budget 계산을 기존 C++ native STT recheck helper로 분리.
  - `core/audio/stt_recheck_service.py`는 native helper가 가능하면 후보 index만 받아 기존 `SttRecheckRange`를 구성하고, native 비활성/실패 시 기존 Python 경로로 즉시 fallback.
  - UI/UX, 자막 LLM, STT 모델 선택, 품질 게이트, 최종 자막 정책은 변경하지 않음.
- 단위/가드:
  - `venv/bin/python -m py_compile core/native_stt_recheck.py core/audio/stt_recheck_service.py tests/test_stt_recheck_service.py`: pass
  - `venv/bin/python -m pytest tests/test_stt_recheck_service.py::STTRecheckServiceTests::test_word_precision_ranges_match_python_fallback_when_native_available tests/test_stt_recheck_service.py::STTRecheckServiceTests::test_word_precision_ranges_prioritize_selected_low_score_segments tests/test_stt_recheck_service.py::STTRecheckServiceTests::test_override_profiles_keep_expected_runtime_flags`: pass (`3 passed`)
  - `venv/bin/python -m pytest tests/test_stt_recheck_service.py tests/test_media_processor_overlap.py::MediaProcessorOverlapTests::test_word_precision_ranges_respect_audio_budget tests/test_media_processor_overlap.py::MediaProcessorOverlapTests::test_whisperkit_precision_aggressive_gpu_raises_slots_under_normal_pressure tests/test_media_processor_overlap.py::MediaProcessorOverlapTests::test_word_precision_straggler_skips_last_chunk_and_keeps_pipeline_moving`: pass (`33 passed`)
  - native backend smoke: `backend=cpp`, sample selected indices `[1, 2]`
- X5 실측:
  - artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260523_145636/benchmark_results.md`
  - `quality_score=87.502`, `CER=0.084433`, `global_text_similarity=0.95658`, `timing_mae_sec=0.5689`, `raw/final=59/56`, `elapsed_sec=88.036`
  - STT1 WhisperKit ANE/GPU concurrency `2`, Fast-STT2 safe fallback concurrency `8`, 단어정밀 concurrency `10`
  - 산출물: `output/manual_verification/latest/20260523_native_word_precision_candidate_planner/verification_summary.md`
- 참고:
  - 이번 slice는 전체 `Subtitle Generation Domain Split And Native Acceleration Plan` 완료가 아니라 word-precision candidate planner native sub-slice 완료임. 메인 active item은 계속 남김.

## X5 native STT safe fallback timing restore - 2026-05-23

- 실행 모드: Targeted router tests + X5 High 180s reference benchmark
- 결과: pass
- 수정/확인 항목:
  - `stt_backend_policy=native`에서 custom MLX label을 기본으로 exact 보존하던 경로가 X5 품질을 떨어뜨리는 것을 확인.
  - 기본 native STT2는 검증된 safe fallback(`mlx-community/whisper-large-v3-turbo` → WhisperKit Turbo)으로 돌리고, exact MLX 보존은 `stt_native_exact_mlx_model_enabled` opt-in일 때만 허용.
  - UI/UX, 자막 LLM 프롬프트, 자막 품질 정책은 변경하지 않음.
- 단위/가드:
  - `venv/bin/python -m pytest tests/test_runtime_optimization_profile.py::RuntimeOptimizationProfileTests::test_native_stt_policy_uses_safe_mlx_fallback_for_custom_mlx_by_default tests/test_runtime_optimization_profile.py::RuntimeOptimizationProfileTests::test_native_stt_policy_preserves_user_selected_mlx_model_when_exact_gate_is_enabled tests/test_runtime_optimization_profile.py::RuntimeOptimizationProfileTests::test_native_stt_policy_falls_back_to_mlx_when_native_experimental_paths_are_not_ready_or_opted_in tests/test_runtime_optimization_profile.py::RuntimeOptimizationProfileTests::test_komixv2_models_route_to_matching_backends`: pass (`4 passed`)
  - `venv/bin/python -m compileall core/audio/stt_backend_router.py`: pass
- X5 실측:
  - bad route: `.codex_work/benchmarks/subtitle_pipeline_variants/20260523_143338/benchmark_results.md`
    - STT2 route `native_policy_selected_mlx_model`, `quality_score=81.354`, `CER=0.174142`, `timing_mae_sec=0.6846`, `raw/final=47/61`
  - accepted route: `.codex_work/benchmarks/subtitle_pipeline_variants/20260523_144047/benchmark_results.md`
    - STT2 route `native_policy_mlx_safe_fallback` → WhisperKit Turbo, `quality_score=87.502`, `CER=0.084433`, `timing_mae_sec=0.5689`, `raw/final=59/56`, `elapsed_sec=89.657`
  - 산출물: `output/manual_verification/latest/20260523_x5_native_stt_safe_fallback_timing/verification_summary.md`
- 참고:
  - 이번 slice는 전체 `Subtitle Generation Domain Split And Native Acceleration Plan` 완료가 아니라, native STT routing/timing guard sub-slice 완료임. 메인 active item은 계속 남김.

## Macau 0075 STT/final drift route fix - 2026-05-23

- 실행 모드: Targeted router tests + Macau 0075 High 180s before/after benchmark
- 결과: partial pass
- 수정/확인 항목:
  - 화면 캡처 구간은 `DJI_20260217224203_0075_D.MP4`(`179.312467s`)로 확인. `0079`는 `42.742700s`라 해당 시간대가 아님.
  - `stt_backend_policy=native`가 사용자 선택 STT2 모델 `youngouk/whisper-medium-komixv2-mlx`를 실제 실행에서 `mlx-community/whisper-large-v3-turbo`로 바꿔 태우던 라우팅 버그를 수정.
  - native policy에서도 명시 선택된 MLX 모델은 그대로 보존하도록 `core/audio/stt_backend_router.py` 패치.
  - UI/UX, 자막 LLM 프롬프트, 자막 품질 정책은 변경하지 않음.
- 단위/가드:
  - `venv/bin/python -m pytest tests/test_runtime_optimization_profile.py::RuntimeOptimizationProfileTests::test_native_stt_policy_preserves_user_selected_mlx_model tests/test_runtime_optimization_profile.py::RuntimeOptimizationProfileTests::test_native_stt_policy_falls_back_to_mlx_when_native_experimental_paths_are_not_ready_or_opted_in tests/test_runtime_optimization_profile.py::RuntimeOptimizationProfileTests::test_komixv2_models_route_to_matching_backends`: pass (`3 passed`)
- 마카오 실측:
  - before: `quality_score=28.965`, `CER=0.7240`, `timing_mae_sec=4.002`, `avg_stt_score=22.0`, `elapsed_sec=75.824`
  - after: `quality_score=30.031`, `CER=0.7885`, `timing_mae_sec=3.371`, `avg_stt_score=40.13`, `elapsed_sec=71.560`
  - after run에서 실제 STT2 route가 `native_policy_selected_mlx_model` / `youngouk/whisper-medium-komixv2-mlx`로 확인됨.
  - 산출물: `output/manual_verification/latest/20260523_macau_0075_stt_final_drift/verification_summary.md`
  - 원본 결과:
    - before: `.codex_work/benchmarks/subtitle_pipeline_variants/20260523_141034/benchmark_results.md`
    - after: `.codex_work/benchmarks/subtitle_pipeline_variants/20260523_142144/benchmark_results.md`
- 남은 위험:
  - `00:54-01:22` 구간은 final이 raw STT를 대부분 따라가며, 큰 오인식/밀림은 raw STT 단계에서 이미 발생함.
  - 다음 좁은 수정은 final cleanup merge clamp와 별도로 STT1 long-window hallucination / VAD-bounded STT1-STT2 선택 품질을 봐야 함.

## VAD / FFmpeg native acceleration slice - 2026-05-23

- 실행 모드: Targeted + Swift native + X5 High 180s benchmark
- 결과: pass
- 변경/확인 항목:
  - `ACTION_ITEMS.md`에서 완료 slice 이력 삭제.
  - FFmpeg scene prepass에 macOS `VideoToolbox` decode hint를 우선 적용하고 실패 시 software FFmpeg로 즉시 fallback.
  - VAD flags-to-segments 후처리를 Swift native helper로 추가하고 Python fallback 유지.
  - Silero/STT-mode VAD Torch placement에 `task="vad"` 및 오디오 크기 추정치를 전달해 Apple GPU/MPS 라우팅 판단을 더 직접화.
  - UI/UX, 자막 모델, 자막 LLM 프롬프트, 품질 게이트는 변경하지 않음.
- 단위/가드:
  - `venv/bin/python -m pytest tests/test_ffmpeg_acceleration.py tests/test_cut_boundary_ffmpeg_scene.py tests/test_native_swift_vad.py tests/test_audio_presets.py`: pass (`56 passed`)
  - `venv/bin/python -m pytest tests/test_ffmpeg_acceleration.py tests/test_cut_boundary_ffmpeg_scene.py tests/test_native_swift_vad.py tests/test_stt_vad_ensemble.py tests/test_stt_vad_model_auto_mode_integration.py tests/test_torch_acceleration.py`: pass (`20 passed`)
  - `venv/bin/python -m compileall core/ffmpeg_acceleration.py core/cut_boundary_ffmpeg_scene.py core/native_swift_vad.py core/audio/media_processor_vad.py core/audio/stt_vad.py core/stt_mode/vad_provider.py core/runtime/config.py core/settings_profiles.py core/audio/audio_preset_data.py`: pass
  - `swift test --package-path native/macos/AIStudioNative --filter VADSegmentsTests`: pass (`2 tests`)
  - `swift build -c release --package-path native/macos/AIStudioNative`: pass
- X5 실측:
  - `quality_score=87.502`, `CER=0.084433`, `raw/final=59/56`, `elapsed_sec=91.08`
  - VAD post-align cache `22`개 재사용, 선택 앙상블 자막 위치 `13`개 보정.
  - 산출물: `output/manual_verification/latest/20260523_vad_ffmpeg_native_accel/verification_summary.md`
  - 원본 결과: `.codex_work/benchmarks/subtitle_pipeline_variants/20260523_140343/benchmark_results.json`
- 참고:
  - FFmpeg 오디오 필터와 Silero PyTorch VAD는 macOS에서 GPU-only/ANE-only로 강제할 수 있는 성격이 아니라서, 가능한 VideoToolbox/Swift/MPS 경로만 적용하고 안전 fallback을 유지함.
  - 별도 broad run에서 `test_cut_boundary_router_uses_existing_preview_proxy` 1건이 실패했으나, 원인은 현재 테스트가 4096바이트 미만 fake proxy를 만들고 `preview_proxy_is_valid()`가 이를 무효 처리하는 기존 경로였음. 이번 변경 범위 아님.

## WhisperKit byte-emission native I/O slice - 2026-05-23

- 실행 모드: Targeted + X5 High 180s benchmark
- 결과: pass
- 변경/확인 항목:
  - Swift WhisperKit persistent worker 응답을 `Data -> String -> Data`로 다시 만들지 않고 encoded `Data`와 newline byte로 바로 출력.
  - Python worker 요청은 `core.native_json.dumps_json_bytes(..., append_newline=True)`로 binary pipe에 직접 기록.
  - UI/UX, 모델 선택, 자막 품질 정책은 변경하지 않음.
- 단위/가드:
  - `venv/bin/python -m pytest tests/test_whisperkit_persistent_io.py tests/test_transcribe_worker_io.py tests/test_media_processor_overlap.py::MediaProcessorOverlapTests::test_whisperkit_submit_task_sends_batch_concurrency`: pass (`6 passed`)
  - `venv/bin/python -m compileall core/audio/whisperkit_persistent.py core/audio/transcribe_worker_io.py`: pass
  - `swift build -c release` in `experiments/whisperkit_persistent_worker`: pass
  - request JSON microbench: native byte encode `2.638x` faster than stdlib `json.dumps(...).encode(...)`
- X5 실측:
  - `quality_score=87.502`, `CER=0.084433`, `raw/final=59/56`, `elapsed_sec=89.018`
  - 산출물: `output/manual_verification/latest/20260523_whisperkit_byte_emit_native_io/verification_summary.md`
  - 원본 결과: `.codex_work/benchmarks/subtitle_pipeline_variants/20260523_134015/benchmark_results.json`
- 해석:
  - 품질은 최신 accepted X5 기준과 동일하게 유지.
  - 전체 wall-clock은 새 최고 기록은 아니므로 성능 최고치로 주장하지 않음.
  - repeated worker JSONL I/O overhead를 줄인 안전한 native hot-path 정리로만 채택.

## automation-4 실시간 full + manual full coverage 실행 - 2026-05-23

- 실행 모드: `qa_suite_runner.py full` + 수동 full coverage + `Tinyping fast/auto/high 60s`
- 실행 산출물:
  - `output/manual_verification/latest/qa_suite_full_20260523_100416`
  - `output/manual_verification/latest/automation4_full_manual_20260523`

### 최상단 판정 (요청 형식: O / X / 검토필요)

- O: `x5_high_rolling_180s`(qa suite), `tinyping_fast_60s`, `tinyping_auto_60s`, `tinyping_high_60s`
- X: 없음
- 검토필요:
  - `save_export_macau` - `save_subtitles` 단계 `subtitle_outputs_missing` (이미지/산출물 부재)
  - `open-project` 전면 실패: `Operation not permitted` (`ai_subtitle_studio/projects` 및 `티니핑` 경로)
  - 멀티클립 자동화: `existing_subtitles_confirmation_required`
  - 편집/저장 검증: `segment_not_found`, `subtitle_save_declined`, `subtitle_segments_missing`(precondition/산출물 상태 의존)

### 시나리오 요약

- `qa_suite_full_20260523_100416`
  - 전체: 5개 시나리오, 통과 4, 실패 1
  - 통과: `editor_compact_macau`, `video_menu_macau`, `menu_stt_lora_macau`, `x5_high_rolling_180s`
  - 실패: `save_export_macau` (`save_subtitles`) - [세부](output/manual_verification/latest/qa_suite_full_20260523_100416/save_export_macau/summary.json)
- 수동 커버리지(`automation4_full_manual_20260523`)
  - 수집: 33개 스냅샷 (home/editor/segment/video/메뉴/roughcut/final 등)
  - 티니핑 생성: fast/auto/high 60초 모두 `ok=True` (`tinyping_*_60s/tinyping_full_verify.json`)
  - 멀티클립: `start-multiclip --reuse-existing yes`(2개 클립) 명령은 `ok=True` + `queued=True` 수신
  - 시작/종료: 앱 종료 전/후 상태 전환 캡처 및 재기동 확인까지 수집

### 검토 요청 처리

- 본 실행의 안됨/검토필요 항목은 `ACTION_ITEMS.md`의 `automation-4 2026-05-23 UX/작동 이슈 검토요청`에 등록했습니다.

# 자동화-4 전체 UX 테스트 결과

## v04.00.13 selective STT2 recursion regression release - 2026-05-22

- 실행 모드: Targeted + X5 High real-media + Full
- 결과:
  - Targeted: pass
  - X5 High 3-minute: pass, `output/manual_verification/latest/20260522_x5_high_release_regression_fix`
  - Full: pass, `output/manual_verification/latest/qa_suite_full_20260522_081710`
- 수정/확인 항목:
  - Apple Silicon runtime plan 적용 후 `_fast_mode_overrides`를 다시 반영하도록 바꿔 pass-specific STT disable override가 살아남게 했다.
  - 그 결과 `선택 STT2 재검사`가 `_fast_stt2_recheck` 내부에서 자기 자신을 다시 재기동하던 재귀 경로를 차단했다.
  - UI/UX, 라벨, 레이아웃, 단축키, 자막 품질 정책은 변경하지 않았다.
- 단위/가드:
  - `./venv/bin/python -m unittest tests.test_audio_presets tests.test_media_processor_overlap.MediaProcessorOverlapTests.test_native_batch_refine_routes_precision_rechecks_after_full_stt1_pass -q`: pass (`49 tests OK`)
  - `./venv/bin/python -m py_compile core/audio/media_processor.py tests/test_audio_presets.py`: pass
  - `git diff --check -- core/audio/media_processor.py tests/test_audio_presets.py`: pass
- 실영상 검증:
  - `./venv/bin/python tools/verify_full_media_pipeline.py --media '/Users/u_mo_c/Downloads/ai_subtitle_studio/test video/X5_시승기_후반.MP4' --mode high --duration-sec 180 --output-dir output/manual_verification/latest/20260522_x5_high_release_regression_fix`
  - 결과: pass
  - 요약: `total_elapsed_sec=182.697`, `pipeline_elapsed_sec=168.115`, `peak_rss_bytes=652050432`, `final/raw=54/52`
  - 이전 실패 원인인 `_fast_stt2_recheck/.../_fast_stt2_recheck/...` 중첩과 `Failed to load audio: Interrupted system call`이 재발하지 않았다.
- full QA:
  - `./packaging/macos/build_app_bundle.sh`: pass
  - `./venv/bin/python tools/qa_suite_runner.py full`: pass
  - scenario count `5`, failed `0`
- 분류:
  - code regression: Apple Silicon runtime plan이 pass-specific STT override를 덮어써 recursive selective recheck를 유발.
  - fixture drift: 없음.
  - environment-bundle issue: 없음.
- 코드 수정 여부: 있음.
- 문서 반영 여부: 있음. `RELEASE_v04.00.13.md`, `README.md`, `AGENTS.md`, `test_result.md`.
- 남은 위험:
  - long High 경로는 여전히 memory pressure `critical`에 들어갈 수 있으므로, 이후 최적화는 메모리 압박과 STT2/word precision wall-clock을 별도로 다뤄야 한다.

## QA fixture rule update - 2026-05-21

- 실행 모드: Targeted
- 결과: pass
- 변경/확인 항목:
  - `tools/qa_suite_runner.py full`에서 기본 full-media 시나리오를 Tinyping 60초 fast/auto/high 3건에서 X5 high 3분 rolling 1건으로 변경.
  - Tinyping은 기본 QA에서 제외하고, 사용자가 명시 요청한 long-flow 수동 검증으로만 사용하도록 `AGENTS.md`, `test_case.md`, `README.md` 규칙을 갱신.
- 단위/가드:
  - `./venv/bin/python -m unittest tests.test_qa_suite_runner -q`: pass
  - `./venv/bin/python -m py_compile tools/qa_suite_runner.py tests/test_qa_suite_runner.py`: pass
  - `git diff --check -- tools/qa_suite_runner.py tests/test_qa_suite_runner.py test_case.md README.md AGENTS.md`: pass
- 실영상 검증:
  - 실행하지 않음. 이번 변경은 runner 구성/문서 규칙 변경이며, 무거운 Tinyping 검증은 기본 테스트에서 제외했다.

## 영상 오픈 전처리 지연 축소 - 2026-05-21 21:52~21:55

- 실행 모드: Targeted + 실앱 Tinyping open-media smoke
- 결과: pass
- 수정/확인 항목:
  - 영상 오픈 직후 720p HEVC preview proxy ffmpeg 빌드를 시작하지 않도록 했다.
  - single media waveform 로드는 영상 오픈 직후가 아니라 `시작` 클릭 후 파이프라인 시작 피드백이 표시된 다음 시작하도록 미뤘다.
  - 자막 품질/STT/LLM/VAD 알고리즘은 변경하지 않았다.
- 단위/가드:
  - `tests.test_project_segment_reload.ProjectSegmentReloadTests.test_native_open_media_bootstrap_defers_waveform_until_start`: pass
  - `tests.test_video_player_widget.VideoPlayerWidgetTests.test_deferred_probe_load_does_not_start_preview_proxy_build`: pass
  - `tests.test_cp03_cp04_status_ui.Cp03Cp04StatusUiTests.test_start_pipeline_marks_processing_before_cut_prescan`: pass
  - 관련 6 targeted tests: pass
  - `py_compile`: pass
  - `git diff --check`: pass
- 실앱 검증:
  - Tinyping `open-media` 응답 `0.284s`.
  - 시작 전 `preview_720p_hevc` / waveform 관련 ffmpeg 프로세스 없음.
  - 비디오 source는 원본 MP4로 로드되고 `video_duration_ms=1450265` 확인.
- 저장 위치:
  - `output/manual_verification/latest/media_open_before_start_deferred_prep.png`
- 분류:
  - code regression: 없음. 시작 전 불필요한 UI 편의 준비 작업을 지연시킨 UX/performance 개선.
  - fixture drift: 없음.
  - environment-bundle issue: 없음.
- 코드 수정 여부: 있음.
- 문서 반영 여부: 있음. `test_result.md`.
- 남은 위험:
  - 시작 직후 waveform worker가 자막 생성과 겹칠 수 있으므로, 장시간 high benchmark에서 리소스 경합이 보이면 waveform을 생성 완료 후 idle로 더 늦추는 후속 후보가 된다.

## 비디오 재생/오픈 직후 플레이헤드 레이스 회귀 수정 - 2026-05-21 21:09~21:11

- 실행 모드: Targeted + 실앱 Tinyping project smoke
- 결과: pass
- 수정/확인 항목:
  - 손상된 720p HEVC preview proxy cache가 있으면 QMediaPlayer duration이 `0`으로 떨어져 생성 후 재생이 멈출 수 있던 문제를 수정했다.
  - 프로젝트 오픈 직후 `editor-set-playhead`가 들어오면 지연 workspace restore가 저장된 마지막 위치로 다시 덮던 race를 수정했다.
  - `status` / `guided-subtitle-status`는 새 코드 재시작 후 `editor_runtime.video_*` 진단값을 정상 반환했다.
- 단위/가드:
  - `tests.test_video_preview_proxy`, 관련 `tests.test_video_player_widget`: pass
  - `tests.test_workspace_restore`: pass
  - `tests.test_app_command_bridge`: pass (`60 tests OK`)
  - `py_compile`: pass
  - `git diff --check`: pass
- 실앱 검증:
  - Tinyping project open 후 즉시 `editor-set-playhead 977.91 --center`.
  - 1.2초 후 `playhead_sec=977.910267`, `video_position_ms=977910`, `video_duration_ms=1450281`.
  - 이어서 재생 확인: `977.91s -> 978.39s`로 진행.
- 저장 위치:
  - `output/manual_verification/latest/video_playback_after_generation_fixed.png`
  - `output/manual_verification/latest/open_project_set_playhead_race_fixed.png`
- 분류:
  - code regression: preview proxy cache validation 누락, open-project 지연 restore와 즉시 seek race.
  - fixture drift: 없음.
  - environment-bundle issue: 없음.
- 코드 수정 여부: 있음.
- 문서 반영 여부: 있음. `test_result.md`.
- 남은 위험:
  - 생성 직후 아주 바쁜 STT/LLM 구간의 status fallback은 생존성 우선 정책을 유지한다. 상세 최신성은 command별 직접 응답과 artifact로 확인한다.
  - `idea_item.md` active queue는 현재 없음.

## idea_item 전체 실행 재검증 및 큐 종료 - 2026-05-21 12:15~12:19

- 실행 모드: Quick / Major / Full + Macau/X5/Tinyping benchmark
- 결과:
  - Quick: pass, `output/manual_verification/latest/qa_suite_quick_20260521_121518`
  - Major: pass, `output/manual_verification/latest/qa_suite_major_20260521_121601`
  - Full: pass, `output/manual_verification/latest/qa_suite_full_20260521_121658`
- 추가 benchmark:
  - Macau fast repeat10: pass, `output/manual_verification/latest/idea_full_execute_20260521-rerun/macau_fast_repeat10/repeat_summary.json`
    - pipeline avg/min/max `7.572s/7.427s/7.849s`, final segment `5` 유지, stage trim avg `6.0`
  - X5 modes repeat10 quality gate: pass, `output/manual_verification/latest/idea_full_execute_20260521-rerun/x5_modes_repeat10_current/repeat_summary.md`
    - `mode_high_piecewise_drift`: gate `10/10`, avg `43.693s`, p95 `44.338s`, quality `72.989`, final segments `24`
    - `mode_fast`: gate `0/10`, avg `10.250s`, p95 `11.410s`, quality `71.514`, final segments `17`
  - Tinyping long high: pass, `output/manual_verification/latest/idea_full_execute_20260521-rerun/tinyping_long_high/tinyping_full_verify.json`
    - media `24:10`, total `602.634s`, pipeline `574.298s`, peak RSS `4205363200`, final/raw `385/424`, rollback `0`
- 최종 선택:
  - 품질 동일 최종 후보는 `mode_high_piecewise_drift`.
  - `mode_fast`는 Fast 모드 속도 후보로는 유지하지만 X5 reference 품질 gate 실패 때문에 품질 동일 기본 알고리즘으로 승격하지 않는다.
- 분류:
  - regression: 없음
  - fixture drift: 없음
  - environment-bundle issue: 없음
- 코드 수정 여부: 없음. 이번 단계는 benchmark/QA refresh와 실행 큐 문서 종료.
- 문서 반영 여부: 있음. `idea_item.md`, `ACTION_ITEMS.md`, `NATIVE_LIB_PLAN.md`, `README.md`, `test_result.md`, `waste_action_item.md`, `lesson_n_learned.md`.
- 남은 위험:
  - Tinyping long high는 성공했지만 runtime pressure snapshot이 `critical`을 기록했다. 장시간 high에서 memory pressure 관찰은 계속 필요하다.
  - UI snapshot diff 자동 비교기는 별도 전용 도구가 아니라 공식 `quick/major/full` screenshot artifact 기준으로 확인했다.

## Phase 8 최종 full QA 및 알고리즘 선택 - 2026-05-21 11:37~11:39

- 실행 모드: Full
- 결과:
  - Full: pass, `output/manual_verification/latest/qa_suite_full_20260521_113718`
  - 최종 요약: `output/manual_verification/latest/idea_full_execute_20260521-1137/summary.md`
- 최종 `full` scenario:
  - `editor_compact_macau`: pass
  - `video_menu_macau`: pass
  - `save_export_macau`: pass
  - `menu_stt_lora_macau`: pass
  - `tinyping_fast_60s`: pass (`total_elapsed_sec=22.563`, `pipeline_elapsed_sec=10.015`, `peak_rss_bytes=460652544`, `final/raw=18/15`)
  - `tinyping_auto_60s`: pass (`total_elapsed_sec=43.851`, `pipeline_elapsed_sec=9.993`, `peak_rss_bytes=788611072`, `final/raw=18/15`)
  - `tinyping_high_60s`: pass (`total_elapsed_sec=25.689`, `pipeline_elapsed_sec=25.596`, `peak_rss_bytes=1299939328`, `final/raw=16/16`)
- 최종 선택:
  - X5 10회 품질 gate를 기준으로 품질 동일 최종 후보는 `mode_high_piecewise_drift`.
  - `mode_fast`는 빠르지만 품질 gate 실패로 기본 알고리즘 승격 제외.
  - STT1/STT2 full-parallel과 native policy helper default 승격은 `waste_action_item.md` 기준으로 폐기 유지.
- 코드 수정 여부: 없음. 최종 검증/문서 정리.
- 문서 반영 여부: 있음. `idea_item.md`, `README.md`, `test_result.md`.
- 남은 위험:
  - Tinyping long high 1회와 별도 UI snapshot diff 자동화는 시간상 이번 최종 full에는 포함하지 못했다.

## Phase 7 도움말 QA coverage 매핑 - 2026-05-21 11:35

- 실행 모드: Targeted
- 결과:
  - 단위/가드: pass
- 코드/문서 반영:
  - 기존 도움말 UI 순서는 유지하고 `HELP_QA_COVERAGE` 데이터만 추가했다.
  - `tests.test_help_dialog`가 모든 도움말 탭에 QA profile, owner, artifact 매핑과 owner 경로 존재 여부를 검증한다.
  - `README.md` 최신 quick baseline을 `qa_suite_quick_20260521_113130`으로 갱신했다.
  - `test_case.md` coverage matrix에 Help/manual QA map 행을 추가했다.
- 단위/가드:
  - `tests.test_help_dialog`: pass
- 분류:
  - 실패 없음.
  - code regression/fixture drift/environment-bundle issue 없음.

## Phase 6 타임라인 silent fallback 로그화 - 2026-05-21 11:26

- 실행 모드: Targeted
- 결과:
  - 단위/가드: pass
  - Quick: pass, `output/manual_verification/latest/qa_suite_quick_20260521_113130`
- 코드 반영:
  - `TimelineCanvas`의 viewport clip 실패와 voice-activity lane refresh 실패가 더 이상 조용히 묻히지 않고 key별 one-shot WARN으로 남는다.
  - 복구 동작은 유지했다. viewport clip 실패 시 full canvas repaint, voice-activity 실패 시 빈 lane 복구.
  - UI/UX 동작 변경 없음. 장애 원인 관측성만 보강.
- 단위/가드:
  - `py_compile`: pass
  - `tests.test_timeline_render_cache tests.test_editor_rendering_ownership_audit`: `40 tests OK`
  - `tools/check_maintenance_budget.py --json`: `ok=true`
  - `tools/qa_suite_runner.py quick`: pass
  - `git diff --check`: pass
- 분류:
  - 실패 없음.
  - code regression/fixture drift/environment-bundle issue 없음.

## 2D 플레이헤드 잔상 방지 repaint 가드 - 2026-05-21 11:20

- 실행 모드: Targeted
- 결과:
  - 단위/가드: pass
- 코드 반영:
  - `tools/audit_editor_rendering_ownership.py`에 `TimelineSingleOwnerPlayheadInvalidation` inventory를 추가했다.
  - single-owner 2D 경로에서 playhead, shadow playhead, drag-shadow playhead, dirty update가 full canvas repaint를 유지하는지 검사한다.
  - UI/UX 동작 변경 없음. 잔상 방지를 위해 이미 적용된 repaint 정책이 부분 repaint 최적화로 되돌아가지 않게 막는 회귀 가드다.
- 단위/가드:
  - `py_compile`: pass
  - `tools/audit_editor_rendering_ownership.py --json`: `ok=true`
  - `tests.test_editor_rendering_ownership_audit tests.test_timeline_render_cache`: `38 tests OK`
- 분류:
  - 실패 없음.
  - code regression/fixture drift/environment-bundle issue 없음.

## 2D 렌더링 ownership inventory 가드 확장 - 2026-05-21 11:16

- 실행 모드: Quick
- 결과:
  - Quick: pass, `output/manual_verification/latest/qa_suite_quick_20260521_111623`
- 코드 반영:
  - `tools/audit_editor_rendering_ownership.py`가 자막 텍스트 QML overlay, video control bar QML, video subtitle QML, timeline scenegraph layer까지 explicit diagnostic/scenegraph gate 뒤에 있는지 확인한다.
  - timeline paint 순서가 subtitle score, cut diamond, shadow/drag-shadow playhead, final playhead handle 순으로 유지되는지 검사한다.
  - UI/UX 동작 변경 없음. QML/SceneGraph 재유입을 잡는 정적 가드만 확장.
- 단위/가드:
  - `py_compile`: pass
  - `tools/audit_editor_rendering_ownership.py --json`: `ok=true`
  - `tests.test_editor_rendering_ownership_audit`: `2 tests OK`
- 분류:
  - 실패 없음.
  - code regression/fixture drift/environment-bundle issue 없음.

## automation-4 검토 항목 회수 및 full 재검증 - 2026-05-21 11:02~11:08

- 실행 모드: Major / Full
- 결과:
  - Major: pass, `output/manual_verification/latest/qa_suite_major_20260521_110523`
  - Full: pass, `output/manual_verification/latest/qa_suite_full_20260521_110628`
- 최종 `full` scenario:
  - `editor_compact_macau`: pass
  - `video_menu_macau`: pass
  - `save_export_macau`: pass
  - `menu_stt_lora_macau`: pass
  - `tinyping_fast_60s`: pass (`total_elapsed_sec=22.229`, `pipeline_elapsed_sec=9.843`, `peak_rss_bytes=431652864`, `final/raw=18/15`)
  - `tinyping_auto_60s`: pass (`total_elapsed_sec=43.163`, `pipeline_elapsed_sec=10.523`, `peak_rss_bytes=761839616`, `final/raw=18/15`)
  - `tinyping_high_60s`: pass (`total_elapsed_sec=25.561`, `pipeline_elapsed_sec=25.465`, `peak_rss_bytes=813219840`, `final/raw=16/16`)
- 실패 원인 분류 및 조치:
  - code regression: smart split 자동화가 playhead가 tiny fragment 또는 segment 밖에 있을 때 `smart_split_unavailable`로 오판하던 문제를 nearest splittable segment fallback으로 수정.
  - code regression: status/guided-subtitle-status가 UDP 제한 또는 send failure에서 `app_unreachable`로 보이던 문제를 compact/minimal fallback 응답으로 수정.
  - fixture/precondition drift: diamond 자동화가 compact 상태에서 stale line/right side를 고정해 `diamond_pair_missing`으로 실패하던 문제를 runner의 `closest` fallback으로 분리.
  - fixture/verification drift: snapshot/export command가 ok를 반환해도 산출물이 비어 있으면 실패로 기록하도록 `remote_verify.py`를 보강.
- 코드 수정 여부: 있음.
  - app command server UDP 응답 압축/최소 응답, status fallback cached resource 사용, editor smart split fallback, QA runner diamond fallback, remote verify artifact 검사.
- 문서 반영 여부: 있음.
  - `idea_item.md`, `test_result.md`, `lesson_n_learned.md` 반영.
- 남은 위험:
  - automation-4 전용 legacy coverage artifact는 과거 실패 기록이므로, 현재 기준 판정은 공식 `major/full` 통과 artifact를 기준으로 한다.
  - 멀티클립 long-running 상태 수렴은 이번 공식 suite 범위 밖이며, 이후 전용 반복 검증으로 분리한다.

## idea_item 최종 실행 QA 가드 보강 및 full 재검증 - 2026-05-21 10:12~10:26

- 실행 모드: Major / Full
- 결과:
  - Major: pass, `output/manual_verification/latest/qa_suite_major_20260521_102240`
  - Full: pass, `output/manual_verification/latest/qa_suite_full_20260521_102341`
- 최종 `full` scenario:
  - `editor_compact_macau`: pass
  - `video_menu_macau`: pass
  - `save_export_macau`: pass
  - `menu_stt_lora_macau`: pass
  - `tinyping_fast_60s`: pass (`total_elapsed_sec=22.553`, `pipeline_elapsed_sec=9.860`, `peak_rss_bytes=436256768`, `final/raw=18/15`)
  - `tinyping_auto_60s`: pass (`total_elapsed_sec=46.169`, `pipeline_elapsed_sec=10.230`, `peak_rss_bytes=783925248`, `final/raw=18/15`)
  - `tinyping_high_60s`: pass (`total_elapsed_sec=26.364`, `pipeline_elapsed_sec=26.262`, `peak_rss_bytes=1575256064`, `final/raw=16/16`)
- 실패 원인 분류 및 조치:
  - code regression: `verify_full_media_pipeline.py`가 spoken slice에서 `raw/final=0/0`이어도 pass로 집계할 수 있는 문제를 수정. 이후 non-trivial spoken slice는 자막 0개면 `empty_subtitle_output:*`로 실패한다.
  - environment-bundle issue: stale bundled Python process(`dist/macos/AI Subtitle Studio.app/Contents/Resources/app/main.py`)를 runner가 기존 앱으로 인식하지 못하던 문제를 수정. zombie/종료 중 PID는 restart blocker로 보지 않는다.
  - code regression: editor automation 중 layout/media refresh가 inline edit focus를 훔치면 `set_inline_cursor`/`commit_inline_edit`가 실패하던 문제를 마지막 smart-split request 복구로 수정.
- 코드 수정 여부: 있음.
  - QA verdict hardening, app bundle process restart detection, editor inline automation restore.
- 문서 반영 여부: 있음.
  - `test_case.md`, `README.md`, `idea_item.md`, `lesson_n_learned.md`, `waste_action_item.md`에 QA/렌더링/폐기 기준 반영.
- 남은 위험:
  - `automation4_full_ux_20260521_101007`의 추가 커버리지 항목은 이후 `qa_suite_major_20260521_110523` / `qa_suite_full_20260521_110628`에서 공식 suite 기준으로 회수했다.
  - aggressive quarter-overlap STT/LLM은 품질 barrier 전까지 default로 켜지지 않았다.

## automation-4 전체 UX + 팝업/메뉴/화면저장 보강 실행 - 2026-05-21 10:07~10:11

- 실행 모드: full 기준 커버리지를 유지한 상태에서 팝업/메뉴/화면저장 의무 화면을 모두 통합 수집.
- 실행 대상:
  - 실행 폴더 1: `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/qa_suite_full_20260521_100216`
  - 실행 폴더 2: `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/automation4_full_ux_20260521_101007`
- 결과 분류:
  - O: 43
  - X: 0
  - 검토필요: 14
- 검토필요 목록(우선순위별):
  - editor-begin-smart-split (`smart_split_unavailable`)
  - editor-set-inline-cursor (`inline_edit_inactive`)
  - editor-commit-inline-edit (`inline_edit_inactive`)
  - editor-move-diamond (`segment_not_found`)
  - editor-merge-diamond (`segment_not_found`)
  - export-subtitle-video (`command_timeout`)
  - stt-enable (`command_timeout`)
  - stt-disable (`command_timeout`)
  - lora-run-now (`command_timeout`)
  - lora-pause (`command_timeout`)
  - lora-resume (`command_timeout`)
  - start-multiclip (`command_timeout`)
  - open-home-before-multiclip (`app_unreachable`)
  - snapshot-after_save_export (`app_unreachable`)
  - snapshot-final_home (`app_unreachable`)
- 비고: 본 run은 `command_timeout`과 `app_unreachable`를 기능 실패와 분리해 추적하고, 아래 `idea_item`에 분류별 조치 요청으로 등록.
- 산출물:
  - `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/automation4_full_ux_20260521_101007/coverage_summary.json`
  - `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/automation4_full_ux_20260521_101007/coverage_steps.jsonl`
  - `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/automation4_full_ux_20260521_101007/*.png`

### 화면 저장 의무 항목(실행 보강)

- 저장된 핵심 화면:
  - `home.png`
  - `editor_after_open_project.png`
  - `editor_after_open_srt.png`
  - `editor_segment.png`
  - `roughcut_after_start.png`
  - `playback_play.png`
  - `playback_pause.png`
  - `settings_dialog.png`
  - `speaker_dialog.png`
  - `dictionary_capture2.png`
  - `dictionary_dialog.png`
  - `final_home.png`
  - `final_editor.png`
  - `video_hidden.png`
  - `video_shown.png`
- 미생성 또는 무효(0B) 화면이 확인되면 우선 `검토필요`에서 분리.

## automation-4 full + 화면 저장 커버리지 실행 - 2026-05-21 10:02~10:06

- 실행 모드: full + 보완 커버리지
- 실행 대상 fixture:
