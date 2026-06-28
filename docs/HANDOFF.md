# Handoff

이 문서는 다음 세션이 빠르게 이어받을 수 있도록 현재 작업 상태와 종료 기준을 남기는 곳입니다. 긴 작업 일지 전체를 붙이는 용도가 아니라, 다음 작업자가 바로 움직일 수 있는 최소 사실을 남기는 용도입니다.

## When to update

아래 중 하나에 해당하면 세션 종료 전에 이 파일을 갱신합니다.

- 코드 또는 문서를 의미 있게 수정했을 때
- 검증 명령이나 기준을 바꿨을 때
- owner 파일이나 책임 경계를 바꿨을 때
- 다음 세션이 알아야 할 열린 리스크가 남았을 때

## What to include

- 이번 세션의 작업 범위
- 실제 수정한 파일
- 실행한 검증과 결과
- 남은 리스크 또는 미확인 사항
- 다음 세션의 첫 권장 행동

## What not to include

- 개인 메모
- 비공개 경로
- 장문의 사고 과정
- 재현 불가능한 임시 판단

## Update rules

- 상대 경로를 사용합니다.
- 사실만 적고 과장하지 않습니다.
- 다음 세션이 그대로 따라 할 수 있는 명령과 파일명을 남깁니다.
- `ACTION_ITEMS.md`와 충돌하는 임시 우선순위를 만들지 않습니다.

## Current Handoff - 2026-06-28 NLE Smart Split Undo Route

### Scope

- Continued the owner goal to import Taption-style subtitle segment editing behavior into the source-app NLE path by fixing timeline smart split undo routing while the text editor has focus.
- `ui/editor/ux/editor_timeline_gap_split.py::_arm_gap_snapshot_undo_routing(...)` now accepts `allow_revision_drift`; timeline smart split NLE-projection success arms snapshot undo routing with drift tolerance so `_route_undo()` restores the structural app snapshot instead of consuming the focused `QTextEdit` local undo stack.
- Existing runtime NLE `caption_split` projection, QTextDocument fallback, gap/delete/generate default snapshot routing, UI layout/labels/colors/menus/popups, subtitle generation policy, STT/STT2/default-cache policy, persisted `.aissproj` NLE fields, App Store packaging/signing/upload, DMG, and per-pixel NLE writes remain unchanged.

### Results

- Audit: `output/manual_verification/latest/nle_smart_split_undo_route_20260628/smart_split_undo_route.md`
- NAS HeyDealer preflight: `output/manual_verification/latest/nle_smart_split_undo_route_nas_preflight_20260628/reference_fixture_availability.md`; ready `true`, media/SRT exist `true/true`, clipped reference rows `89`.
- NAS HeyDealer current-head regression: `output/manual_verification/latest/nle_smart_split_undo_route_nas_heydealer_20260628/acceptance/reference_benchmark_acceptance.md`
- Run `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_185643/benchmark_results.json`: accepted `true`, elapsed `45.752s`, raw/final/reference `58/56/89`, quality/text/timing `93.766/94.267/0.5808s`, final invalid/non-monotonic/overlap `0/0/0`, final last end/duration bound `180.0/180.0`, short/long `0/0`, global max-active `1`, STT1/STT2/word selected `21/37/7`.
- Timeout audit: `output/manual_verification/latest/stt_worker_timeout_compare_nle_smart_split_undo_route_nas_20260628/stt_worker_timeout_audit.md`; timeout detected `false`.

### Jammini

- Scout: `.agents/sentinel/handoffs/20260628-095359-smart-split-undo-route-scout.md`
- Dex classification: accepted the scout's revision-drift owner path and kept the fix narrowed to snapshot routing. Deferred broader UI, persisted NLE, STT/default, App Store, and per-pixel write scopes.

### Verification

- `./venv/bin/python -m py_compile ui/editor/ux/editor_timeline_gap_split.py tests/test_editor_split_undo.py` -> pass.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_editor_split_undo.py::EditorSplitUndoTests::test_smart_split_undo_and_redo_follow_snapshot_history_with_text_focus -vv` -> `1 passed`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_editor_split_undo.py` -> `3 passed`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py -k "smart_split or gap_generate or seg_to_gap"` -> `4 passed, 189 deselected`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/verify_reference_fixture_availability.py --media ... --reference-srt ... --start-sec 0 --duration-sec 180 --output-dir output/manual_verification/latest/nle_smart_split_undo_route_nas_preflight_20260628` -> ready `true`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/benchmark_subtitle_pipeline_variants.py --suite modes --variants mode_high --media ... --reference-srt ... --start-sec 0 --duration-sec 180 --keep-artifacts` -> `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_185643/benchmark_results.json`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/evaluate_reference_benchmark_acceptance.py .codex_work/benchmarks/subtitle_pipeline_variants/20260628_185643/benchmark_results.json --output-dir output/manual_verification/latest/nle_smart_split_undo_route_nas_heydealer_20260628/acceptance` -> accepted `true`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_stt_worker_timeout.py .codex_work/benchmarks/subtitle_pipeline_variants/20260628_184504/benchmark_results.json .codex_work/benchmarks/subtitle_pipeline_variants/20260628_185643/benchmark_results.json --output-dir output/manual_verification/latest/stt_worker_timeout_compare_nle_smart_split_undo_route_nas_20260628` -> timeout detected `false`.

### Known Notes

- The previous `tests/test_editor_split_undo.py` smart split route note is resolved in this slice.
- Persisted NLE disk fields, runtime undo/redo UI surface redesign, per-pixel writes, QML/GPU default timeline surfaces, detector-threshold changes, App Store packaging/submission work, and STT/default-cache policy changes remain blocked until explicit owner approval and compatibility proof exist.

### Next Recommended Action

- Continue with the next safe NLE/Taption runtime contract from `ACTION_ITEMS.md`. Good candidates should be bounded to existing source-app owner paths, prove Taption release-commit/no-overlap behavior, and avoid persisted NLE fields or UI redesign unless the owner explicitly asks.
- For generation-affecting or performance/default-cache work, keep using the available NAS HeyDealer first-180s MP4/SRT preflight plus strict acceptance and timeout audit.

## Previous Handoff - 2026-06-28 NLE Undo/Redo Runtime-State Restore

### Scope

- Continued the owner goal to move AI Subtitle Studio toward a video-editor/NLE structure by syncing undo/redo restored editor rows into session-only runtime `NLEProjectState`.
- Added `ui.project.project_session_runtime.sync_runtime_nle_state_from_editor_rows(...)` and called it from `ui.editor.undo_manager.UndoManager._restore(...)` after cached segment restore.
- Added `tools/audit_nle_undo_redo_runtime_state.py`, audit tests, and focused PyQt assertions that split undo/redo restore NLE rows match visible restored captions while live preview rows stay out of the runtime NLE state.
- No UI layout/labels/colors/menus/popups, subtitle generation policy, STT/STT2/default-cache policy, persisted `.aissproj` NLE fields, App Store packaging/signing/upload, DMG, runtime undo/redo UI, or per-pixel NLE write behavior changed.

### Results

- Audit: `output/manual_verification/latest/nle_undo_redo_runtime_state_20260628/nle_undo_redo_runtime_state.md`
- `ready=true`; restore sync source `undo_redo_restore`; operation journal count `0`; storage clean of `_nle_project_state`, `nle`, and `nle_snapshot`.
- NAS HeyDealer preflight: `output/manual_verification/latest/nle_undo_redo_runtime_state_nas_preflight_20260628/reference_fixture_availability.md`; ready `true`, media/SRT exist `true/true`, clipped reference rows `89`.
- NAS HeyDealer current-head regression: `output/manual_verification/latest/nle_undo_redo_runtime_state_nas_heydealer_20260628/acceptance/reference_benchmark_acceptance.md`
- Run `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_184504/benchmark_results.json`: accepted `true`, elapsed `45.497s`, raw/final/reference `58/56/89`, quality/text/timing `93.766/94.267/0.5808s`, final invalid/non-monotonic/overlap `0/0/0`, final last end/duration bound `180.0/180.0`, short/long `0/0`, global max-active `1`, STT1/STT2/word selected `21/37/7`.
- Timeout audit: `output/manual_verification/latest/stt_worker_timeout_compare_nle_undo_redo_runtime_state_nas_20260628/stt_worker_timeout_audit.md`; timeout detected `false`.

### Jammini

- Scout: `.agents/sentinel/handoffs/20260628-093842-next-nle-taption-runtime-contract-scout.md`
- Dex classification: deferred the scout's roughcut sidecar compatibility proposal as a possible future candidate, and implemented the narrower undo/redo runtime-state restore sync found in current owner files.

### Verification

- `./venv/bin/python -m py_compile ui/project/project_session_runtime.py ui/editor/undo_manager.py tools/audit_nle_undo_redo_runtime_state.py tests/test_nle_undo_redo_runtime_state_audit.py tests/test_editor_split_undo.py` -> pass.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_nle_undo_redo_runtime_state_audit.py tests/test_editor_split_undo.py::EditorSplitUndoTests::test_text_split_undo_and_redo_follow_snapshot_history_with_text_focus tests/test_editor_split_undo.py::EditorSplitUndoTests::test_text_split_uses_legacy_fallback_when_live_preview_lane_exists` -> `4 passed`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_snapshot.py tests/test_project_nle_persistence_guard.py tests/test_project_nle_runtime_cutover.py -k "runtime_nle or save_project or undo or storage or save_export or final_overlay"` -> `10 passed, 19 deselected`.
- `./venv/bin/python tools/audit_nle_undo_redo_runtime_state.py --output-dir output/manual_verification/latest/nle_undo_redo_runtime_state_20260628` -> ready `true`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/verify_reference_fixture_availability.py --media ... --reference-srt ... --start-sec 0 --duration-sec 180 --output-dir output/manual_verification/latest/nle_undo_redo_runtime_state_nas_preflight_20260628` -> ready `true`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/benchmark_subtitle_pipeline_variants.py --suite modes --variants mode_high --media ... --reference-srt ... --start-sec 0 --duration-sec 180 --keep-artifacts` -> `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_184504/benchmark_results.json`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/evaluate_reference_benchmark_acceptance.py .codex_work/benchmarks/subtitle_pipeline_variants/20260628_184504/benchmark_results.json --output-dir output/manual_verification/latest/nle_undo_redo_runtime_state_nas_heydealer_20260628/acceptance` -> accepted `true`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_stt_worker_timeout.py .codex_work/benchmarks/subtitle_pipeline_variants/20260628_175938/benchmark_results.json .codex_work/benchmarks/subtitle_pipeline_variants/20260628_184504/benchmark_results.json --output-dir output/manual_verification/latest/stt_worker_timeout_compare_nle_undo_redo_runtime_state_nas_20260628` -> timeout detected `false`.

### Next Recommended Action

- Continue with the next safe NLE/Taption runtime contract from `ACTION_ITEMS.md` / `NLE_Action.md`. The deferred Jammini roughcut sidecar compatibility proposal is a reasonable future scout target if it is kept test/audit-only and avoids persisted NLE fields.
- For generation-affecting or performance/default-cache work, use the available NAS HeyDealer first-180s MP4/SRT preflight plus strict acceptance and timeout audit again.
- Treat persisted NLE disk fields, UI flow changes, project-storage relink schemas, per-pixel writes, QML/GPU default surfaces, detector-threshold changes, runtime undo/redo UI changes, App Store packaging/submission work, and STT/default-cache policy changes as blocked until explicit owner approval and compatibility proof exist.

## Previous Handoff - 2026-06-28 NLE Selection View-State Isolation

### Scope

- Continued the owner goal to move AI Subtitle Studio toward a video-editor/NLE structure by hardening the Taption-style rule that selection/highlight/current-segment state is view-only, not an edit commit.
- Added focused PyQt tests for text selection, `TimelineCanvas.set_active` / `clear_active_visual`, and `TimelineWidget.set_active`.
- Added `tools/audit_nle_selection_view_state_isolation.py` and audit test coverage for the same owner paths.
- No UI layout/labels/colors/menus/popups, subtitle generation, STT/STT2/default-cache policy, `.aissproj` persisted NLE fields, App Store packaging/signing/upload, DMG, runtime undo/redo UI, or per-pixel NLE write behavior changed.

### Results

- Audit: `output/manual_verification/latest/nle_selection_view_state_isolation_20260628/nle_selection_view_state_isolation.md`
- `ready=true`; selection view-state-only contract `true`; model validation/project save/NLE writes allowed `false/false/false`; primary row rewrite allowed `false`; forbidden calls/assignments `0`.
- NAS HeyDealer preflight: `output/manual_verification/latest/nle_selection_view_state_nas_preflight_20260628/reference_fixture_availability.md`; ready `true`, media/SRT exist `true/true`, clipped reference rows `89`.
- NAS HeyDealer current-head regression: `output/manual_verification/latest/nle_selection_view_state_nas_heydealer_20260628/acceptance/reference_benchmark_acceptance.md`
- Run `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_183048/benchmark_results.json`: accepted `true`, elapsed `45.999s`, raw/final/reference `58/56/89`, quality/text/timing `93.766/94.267/0.5808s`, final invalid/non-monotonic/overlap `0/0/0`, final last end/duration bound `180.0/180.0`, short/long `0/0`, global max-active `1`, STT1/STT2/word selected `21/37/7`.
- Timeout audit: `output/manual_verification/latest/stt_worker_timeout_compare_nle_selection_view_state_nas_20260628/stt_worker_timeout_audit.md`; timeout detected `false`.

### Jammini

- Scout: `.agents/sentinel/handoffs/20260628-092700-timeline-view-state-isolation-scout.md`
- Dex classification: accepted the view-state isolation direction and implemented it as focused test/audit hardening, while leaving UI flow changes, persisted NLE fields, STT/default-cache policy, App Store packaging, DMG, and per-pixel writes deferred.

### Verification

- `./venv/bin/python -m py_compile tests/test_nle_selection_view_state_isolation.py tests/test_nle_selection_view_state_isolation_audit.py tools/audit_nle_selection_view_state_isolation.py` -> pass.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_nle_selection_view_state_isolation.py tests/test_nle_selection_view_state_isolation_audit.py` -> `4 passed`.
- `./venv/bin/python tools/audit_nle_selection_view_state_isolation.py --output-dir output/manual_verification/latest/nle_selection_view_state_isolation_20260628` -> ready `true`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_wheel_zoom_decoupling.py tests/test_timeline_playhead_jump_isolation.py tests/test_timeline_time_window_decoupling.py tests/test_nle_selection_view_state_isolation.py tests/test_nle_selection_view_state_isolation_audit.py` -> `11 passed`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/verify_reference_fixture_availability.py --media ... --reference-srt ... --start-sec 0 --duration-sec 180 --output-dir output/manual_verification/latest/nle_selection_view_state_nas_preflight_20260628` -> ready `true`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/benchmark_subtitle_pipeline_variants.py --suite modes --variants mode_high --media ... --reference-srt ... --start-sec 0 --duration-sec 180 --keep-artifacts` -> `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_183048/benchmark_results.json`.
- `./venv/bin/python tools/evaluate_reference_benchmark_acceptance.py .codex_work/benchmarks/subtitle_pipeline_variants/20260628_183048/benchmark_results.json --media-duration-sec 180 --output-dir output/manual_verification/latest/nle_selection_view_state_nas_heydealer_20260628/acceptance` -> accepted `true`.
- `./venv/bin/python tools/audit_stt_worker_timeout.py .codex_work/benchmarks/subtitle_pipeline_variants/20260628_183048/benchmark_results.json --output-dir output/manual_verification/latest/stt_worker_timeout_compare_nle_selection_view_state_nas_20260628` -> timeout detected `false`.

### Next Recommended Action

- Continue with the next safe NLE/Taption runtime contract from `ACTION_ITEMS.md` / `NLE_Action.md`.
- For generation-affecting or performance/default-cache work, use the available NAS HeyDealer first-180s MP4/SRT preflight plus strict acceptance and timeout audit again.
- Treat persisted NLE disk fields, UI flow changes, project-storage relink schemas, per-pixel writes, QML/GPU default surfaces, detector-threshold changes, runtime undo/redo UI changes, App Store packaging/submission work, and STT/default-cache policy changes as blocked until explicit owner approval and compatibility proof exist.

## Previous Handoff - 2026-06-28 Trace Package Retention Contract

### Scope

- Continued the owner goal to move AI Subtitle Studio toward a video-editor/NLE structure by closing the Trace Log Bundle package-retention gap from `NLE_Action.md`.
- Added `core/runtime/temp_workspace.py::prune_trace_package_directories(...)` with a bounded default of `10` package directories.
- Updated `tools/collect_trace_package.py` so collecting an `AISSTrace-*` package prunes old package directories, keeps the current package, and records `package_retention` in `package_manifest.json`.
- Strengthened `tools/audit_trace_log_bundle.py`, `tests/test_trace_logger.py`, and `tests/test_trace_log_bundle_audit.py` so trace run retention and package retention are both proven by the same diagnostic artifact.
- No UI layout/labels/colors/menus/popups, subtitle generation, STT/STT2/default-cache policy, `.aissproj` persisted NLE fields, App Store packaging/signing/upload, DMG, runtime undo/redo UI, or per-pixel NLE write behavior changed.

### Results

- Audit: `output/manual_verification/latest/trace_package_retention_contract_20260628/trace_log_bundle_audit.md`
- Passed `true`; required dirs `true`; manifest/event missing fields `none`; exact-frame precision `true`; confirmed cut trace `true`; bounded media fingerprint `true`; package complete `true`.
- Trace run retention: `20/20`, removed count `5`.
- Trace package retention: `10/10`, removed count `4`.
- Trace disabled `false`, drop counts `{}`.
- NAS HeyDealer generation validation was not run because this slice only touches trace/temp-workspace disk-management behavior and does not affect STT/VAD/subtitle generation/final rows.

### Jammini

- Scout: `.agents/sentinel/handoffs/20260628-091806-trace-bundle-retention-scout.md`
- Dex classification: accepted the retention direction and extended it narrowly from run retention evidence to package-directory retention, leaving UI/STT/NLE mutation/App Store behavior unchanged.

### Verification

- `./venv/bin/python -m py_compile core/runtime/temp_workspace.py tools/collect_trace_package.py tools/audit_trace_log_bundle.py tests/test_trace_log_bundle_audit.py tests/test_trace_logger.py` -> pass.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_trace_logger.py tests/test_trace_log_bundle_audit.py -k "trace_package or package_retention or trace_log_bundle or prune_trace_package or temp_workspace"` -> `9 passed, 11 deselected`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_trace_logger.py tests/test_trace_log_bundle_audit.py tests/test_startup_diagnostics.py tests/test_app_command_bridge.py -k "trace or diagnostic or open_media or open_project or package"` -> `27 passed, 74 deselected`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_trace_log_bundle.py --output-dir output/manual_verification/latest/trace_package_retention_contract_20260628` -> passed `true`.

### Next Recommended Action

- Continue with the next safe NLE/Taption runtime contract from `ACTION_ITEMS.md` / `NLE_Action.md`.
- For any generation-affecting or performance/default-cache step, use the available NAS HeyDealer first-180s MP4/SRT preflight plus strict acceptance and timeout audit again.
- Treat persisted NLE disk fields, UI flow changes, project-storage relink schemas, per-pixel writes, QML/GPU default surfaces, detector-threshold changes, runtime undo/redo UI changes, App Store packaging/submission work, and STT/default-cache policy changes as blocked until explicit owner approval and compatibility proof exist.

## Previous Handoff - 2026-06-28 Direct SRT Runtime NLE Precedence Contract

### Scope

- Added the direct SRT versus linked-project/runtime-NLE precedence contract for AI Subtitle Studio.
- Updated `core/project/nle_project_state.py`, `ui/editor/editor_project_open_native.py`, `tests/test_project_segment_reload.py`, `tests/test_direct_srt_precedence_audit.py`, `tools/audit_direct_srt_precedence_contract.py`, NLE/status docs, completed action history, and the Jammini scout handoff classification.
- Linked-project direct SRT open now syncs runtime `NLEProjectState` from the exact direct SRT editor rows after metadata merge, records `last_editor_sync_source=direct_srt_open`, and marks `direct_srt_precedence_contract=srt_timing_text_wins`.
- Direct SRT timing/text remain the source of truth. Project metadata is restored only as auxiliary metadata, and persisted project storage remains clean of runtime NLE fields.
- No UI layout/labels/colors/menus/popups, subtitle quality policy, STT/STT2/default-cache policy, persisted NLE disk-format, App Store packaging/signing/upload, DMG, runtime undo/redo UI, or per-pixel NLE write behavior changed.

### Results

- Audit: `output/manual_verification/latest/direct_srt_precedence_contract_20260628/direct_srt_precedence_contract.md`
- Passed `true`; editor/NLE text both use `latest direct SRT text`; editor/NLE start/end both use `[1.2, 2.4]`; NLE sync source `direct_srt_open`; NLE precedence contract `srt_timing_text_wins`; project metadata restored `true`; storage clean of runtime NLE `true`.
- NAS HeyDealer preflight: `output/manual_verification/latest/direct_srt_precedence_nas_preflight_20260628/reference_fixture_availability.md`; ready `true`, media/SRT exist `true/true`, clipped reference rows `89`.
- NAS HeyDealer current-head regression: `output/manual_verification/latest/direct_srt_precedence_nas_heydealer_20260628/acceptance/reference_benchmark_acceptance.md`
- Run `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_181354/benchmark_results.json`: accepted `true`, elapsed `45.785s`, raw/final/reference `58/56/89`, quality/text/timing `93.766/94.267/0.5808s`, final invalid/non-monotonic/overlap `0/0/0`, final last end/duration bound `180.0/180.0`, short/long `0/0`, global max-active `1`.
- Timeout audit: `output/manual_verification/latest/stt_worker_timeout_compare_direct_srt_precedence_nas_20260628/stt_worker_timeout_audit.md`; timeout detected `false`.

### Jammini

- Scout: `.agents/sentinel/handoffs/20260628-090453-srt-precedence-contract-scout.md`
- Dex classification: accepted the direct SRT precedence contract and implemented it in the runtime NLE sync path, while deferring UI flow changes, persisted NLE disk fields, STT/default-cache policy, App Store packaging, DMG, and per-pixel writes.

### Verification

- `./venv/bin/python -m py_compile core/project/nle_project_state.py ui/editor/editor_project_open_native.py tools/audit_direct_srt_precedence_contract.py tests/test_project_segment_reload.py tests/test_direct_srt_precedence_audit.py` -> pass.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_segment_reload.py -k "linked_srt_mode or direct_srt_rows_to_runtime_nle_state or open_project_file_passes_resolved_external_srt_path"` -> `3 passed, 86 deselected`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_direct_srt_precedence_audit.py` -> `1 passed`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_direct_srt_precedence_audit.py tests/test_project_segment_reload.py -k "direct_srt_precedence or direct_srt_rows_to_runtime_nle_state or linked_srt_mode"` -> `3 passed, 87 deselected`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_direct_srt_precedence_contract.py --output-dir output/manual_verification/latest/direct_srt_precedence_contract_20260628` -> passed `true`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_editor_srt_open_refresh.py tests/test_project_segment_reload.py -k "srt or linked_srt or direct_srt"` -> `26 passed, 80 deselected`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_snapshot.py tests/test_project_nle_persistence_guard.py -k "direct_srt or runtime_nle_project_state or persistence_guard or storage_builders or reading_raw_project"` -> `7 passed, 12 deselected`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/verify_reference_fixture_availability.py --media ... --reference-srt ... --start-sec 0 --duration-sec 180 --output-dir output/manual_verification/latest/direct_srt_precedence_nas_preflight_20260628` -> ready `true`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/benchmark_subtitle_pipeline_variants.py --suite modes --variants mode_high --media ... --reference-srt ... --start-sec 0 --duration-sec 180 --keep-artifacts` -> `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_181354/benchmark_results.json`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/evaluate_reference_benchmark_acceptance.py .codex_work/benchmarks/subtitle_pipeline_variants/20260628_181354/benchmark_results.json --media-duration-sec 180.0 --output-dir output/manual_verification/latest/direct_srt_precedence_nas_heydealer_20260628/acceptance` -> accepted `true`.
- `./venv/bin/python tools/audit_stt_worker_timeout.py .codex_work/benchmarks/subtitle_pipeline_variants/20260628_181354/benchmark_results.json --output-dir output/manual_verification/latest/stt_worker_timeout_compare_direct_srt_precedence_nas_20260628` -> timeout detected `false`.
- `git diff --check -- core/project/nle_project_state.py ui/editor/editor_project_open_native.py tools/audit_direct_srt_precedence_contract.py tests/test_project_segment_reload.py tests/test_direct_srt_precedence_audit.py` -> pass.

### Next Recommended Action

- Continue with the next safe NLE/Taption runtime contract from `ACTION_ITEMS.md` / `NLE_Action.md`.
- For any generation-affecting or performance/default-cache step, use the now-available NAS HeyDealer first-180s MP4/SRT preflight plus strict acceptance and timeout audit again.
- Treat persisted NLE disk fields, UI flow changes, project-storage relink schemas, per-pixel writes, QML/GPU default surfaces, detector-threshold changes, runtime undo/redo UI changes, App Store packaging/submission work, and STT/default-cache policy changes as blocked until explicit owner approval and compatibility proof exist.

## Previous Handoff - 2026-06-28 NLE Relink Preview Cache Contract

### Scope

- Added the AI Subtitle Studio NLE relink/proxy preview-cache non-destructive contract.
- Updated `core/runtime/preview_frame_cache.py`, `tests/test_preview_frame_cache.py`, `tools/audit_nle_relink_preview_cache_contract.py`, `tests/test_nle_relink_preview_cache_contract_audit.py`, NLE/status docs, completed action history, and the Jammini scout handoff classification.
- Direct path cache lookup remains first. A bounded relink manifest scan runs only after miss and reuses an existing preview thumbnail only when media identity, fps, frame, width, preview-only provenance, and cut-boundary exclusion all match.
- No UI layout/labels/colors/menus/popups, subtitle quality policy, STT/STT2/default-cache policy, detector thresholds, project-storage relink schema, persisted NLE disk-format, App Store packaging/signing/upload, DMG, runtime undo/redo UI, or per-pixel NLE write behavior changed.

### Results

- Audit: `output/manual_verification/latest/nle_relink_preview_cache_contract_20260628/nle_relink_preview_cache_contract.md`
- `ready=true`; relink identity matches `true`; relink hit reuses original cache `true`; proxy identity blocked `true`; proxy hit blocked `true`; cached still exists `true`.
- NAS HeyDealer acceptance: `output/manual_verification/latest/nle_relink_preview_cache_nas_heydealer_20260628/acceptance/reference_benchmark_acceptance.md`
- Run `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_174547/benchmark_results.json`: accepted `true`, elapsed `45.515s`, raw/final/reference `58/56/89`, quality/text/timing `93.766/94.267/0.5808s`, final invalid/non-monotonic/overlap `0/0/0`, final last end/duration bound `180.0/180.0`, short/long `0/0`, global max-active `1`.
- Timeout audit: `output/manual_verification/latest/stt_worker_timeout_compare_nle_relink_preview_cache_nas_20260628/stt_worker_timeout_audit.md`; timeout detected `false`.

### Jammini

- Scout: `.agents/sentinel/handoffs/20260628-083937-next-nle-taption-runtime-contract-scout.md`
- Dex classification: accepted the relink/proxy preview-cache continuity direction, narrowed implementation to runtime preview-cache manifest identity plus bounded lookup fallback, and deferred persisted project relink schemas/UI flow changes.

### Verification

- `./venv/bin/python -m py_compile core/runtime/preview_frame_cache.py tools/audit_nle_relink_preview_cache_contract.py` -> pass.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_preview_frame_cache.py tests/test_nle_relink_preview_cache_contract_audit.py` -> `8 passed`.
- `./venv/bin/python tools/audit_nle_relink_preview_cache_contract.py --output-dir output/manual_verification/latest/nle_relink_preview_cache_contract_20260628` -> ready `true`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_nle_preview_skimming_cache_audit.py tests/test_video_player_widget.py -k "preview_frame_cache"` -> `3 passed, 82 deselected`.
- `git diff --check -- core/runtime/preview_frame_cache.py tests/test_preview_frame_cache.py tools/audit_nle_relink_preview_cache_contract.py tests/test_nle_relink_preview_cache_contract_audit.py` -> pass.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/verify_reference_fixture_availability.py --media ... --reference-srt ... --start-sec 0 --duration-sec 180 --output-dir output/manual_verification/latest/nle_relink_preview_cache_nas_preflight_20260628` -> ready `true`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/benchmark_subtitle_pipeline_variants.py --suite modes --variants mode_high --media ... --reference-srt ... --start-sec 0 --duration-sec 180 --keep-artifacts` -> `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_174547/benchmark_results.json`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/evaluate_reference_benchmark_acceptance.py .codex_work/benchmarks/subtitle_pipeline_variants/20260628_174547/benchmark_results.json --media-duration-sec 180.0 --output-dir output/manual_verification/latest/nle_relink_preview_cache_nas_heydealer_20260628/acceptance` -> accepted `true`.
- `./venv/bin/python tools/audit_stt_worker_timeout.py .codex_work/benchmarks/subtitle_pipeline_variants/20260628_174547/benchmark_results.json --output-dir output/manual_verification/latest/stt_worker_timeout_compare_nle_relink_preview_cache_nas_20260628` -> timeout detected `false`.

### Next Recommended Action

- Continue with the next safe NLE/Taption runtime contract from `ACTION_ITEMS.md` / `NLE_Action.md`.
- Treat persisted NLE disk fields, project-storage relink schemas, dynamic proxy mapping without source identity, per-pixel writes, QML/GPU default surfaces, detector-threshold changes, runtime undo/redo UI changes, App Store packaging/submission work, and STT/default-cache policy changes as blocked until explicit owner approval and compatibility proof exist.

## Previous Handoff - 2026-06-28 NLE Cut Marker Point Projection

### Scope

- Added runtime marker projection sanitization for AI Subtitle Studio NLE `marker_edit` dual-write.
- Updated `core/project/nle_dual_write.py`, `tests/test_project_nle_dual_write.py`, `tools/audit_nle_cut_marker_point_projection.py`, `tests/test_nle_cut_marker_point_projection_audit.py`, NLE/status docs, completed action history, and the Jammini scout handoff classification.
- No UI layout/labels/colors/menus/popups, subtitle quality policy, STT/STT2/default-cache policy, detector thresholds, persisted NLE disk-format, App Store packaging/signing/upload, DMG, runtime undo/redo UI, or per-pixel NLE write behavior changed.

### Results

- Audit: `output/manual_verification/latest/nle_cut_marker_point_projection_20260628/nle_cut_marker_point_projection.md`
- `passed=true`; observed frames `2766,2676`; marker policy `point_evidence_no_clip_span`; span leak count `0`; clip boundaries unchanged `true`; projection gate final invalid/non-monotonic/overlap `0/0/0`; global max-active `1`.
- NAS HeyDealer acceptance: `output/manual_verification/latest/nle_cut_marker_point_projection_nas_heydealer_20260628/acceptance/reference_benchmark_acceptance.md`
- Run `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_173133/benchmark_results.json`: accepted `true`, elapsed `45.036s`, raw/final/reference `58/56/89`, quality/text/timing `93.766/94.267/0.5808s`, final invalid/non-monotonic/overlap `0/0/0`, final last end/duration bound `180.0/180.0`, short/long `0/0`, global max-active `1`.
- Timeout audit: `output/manual_verification/latest/stt_worker_timeout_compare_nle_cut_marker_point_projection_nas_20260628/stt_worker_timeout_audit.md`; timeout detected `false`.

### Jammini

- Route status/probe passed before delegation; probe pointer was removed from the Sentinel index.
- Scout: `.agents/sentinel/handoffs/20260628-082222-next-nle-taption-runtime-contract-scout.md`
- Dex classification: accepted the cut-marker point-evidence direction and corrected stale scout target `2677` to current AI Subtitle Studio fixed target `2676`.

### Verification

- `./venv/bin/python -m py_compile core/project/nle_dual_write.py tools/audit_nle_cut_marker_point_projection.py tests/test_project_nle_dual_write.py tests/test_nle_cut_marker_point_projection_audit.py` -> pass.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_dual_write.py -k "marker_edit"` -> `3 passed, 35 deselected`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_nle_cut_marker_point_projection_audit.py` -> `2 passed`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_dual_write.py tests/test_nle_cut_marker_point_projection_audit.py` -> `40 passed`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_cut_boundary_preserved_marker_policy.py tests/test_nle_projection_metadata_preservation_audit.py` -> `5 passed`.
- `./venv/bin/python tools/audit_nle_cut_marker_point_projection.py --output-dir output/manual_verification/latest/nle_cut_marker_point_projection_20260628` -> passed `true`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/verify_reference_fixture_availability.py --media ... --reference-srt ... --start-sec 0 --duration-sec 180 --output-dir output/manual_verification/latest/nle_cut_marker_point_projection_nas_preflight_20260628` -> ready `true`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/benchmark_subtitle_pipeline_variants.py --suite modes --variants mode_high --media ... --reference-srt ... --start-sec 0 --duration-sec 180 --keep-artifacts` -> `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_173133/benchmark_results.json`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/evaluate_reference_benchmark_acceptance.py .codex_work/benchmarks/subtitle_pipeline_variants/20260628_173133/benchmark_results.json --media-duration-sec 180.0 --output-dir output/manual_verification/latest/nle_cut_marker_point_projection_nas_heydealer_20260628/acceptance` -> accepted `true`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_stt_worker_timeout.py .codex_work/benchmarks/subtitle_pipeline_variants/20260628_171508/benchmark_results.json .codex_work/benchmarks/subtitle_pipeline_variants/20260628_173133/benchmark_results.json --output-dir output/manual_verification/latest/stt_worker_timeout_compare_nle_cut_marker_point_projection_nas_20260628` -> timeout detected `false`.

### Next Recommended Action

- Continue with the next safe NLE/Taption runtime contract from `ACTION_ITEMS.md` / `NLE_Action.md`.
- Treat persisted NLE disk fields, per-pixel writes, QML/GPU default surfaces, detector-threshold changes, runtime undo/redo UI changes, App Store packaging/submission work, and STT/default-cache policy changes as blocked until explicit owner approval and compatibility proof exist.

## Current Handoff - 2026-06-28 NLE Projection Metadata Preservation

### Scope

- Added runtime dual-write projection metadata preservation for existing AI Subtitle Studio product metadata.
- Updated `core/project/nle_dual_write.py`, `core/project/nle_operations.py`, `tests/test_project_nle_dual_write.py`, `tools/audit_nle_projection_metadata_preservation.py`, `tests/test_nle_projection_metadata_preservation_audit.py`, NLE/status docs, completed action history, and the Jammini scout handoff classification.
- No UI layout/labels/colors/menus/popups, subtitle quality policy, STT/STT2/default-cache policy, arbitrary legacy custom schema expansion, persisted NLE disk-format, App Store packaging/signing/upload, DMG, runtime undo/redo UI, or per-pixel NLE write behavior changed.

### Results

- Audit: `output/manual_verification/latest/nle_projection_metadata_preservation_20260628/nle_projection_metadata_preservation.md`
- `ready=true`; static deepcopy contract covers retime, manual-edit, sorted projection rows, shadow rebuild rows, and operation serialization.
- Dynamic checks prove caption move preserves quality/STT candidate metadata, caption merge preserves kept-row metadata, and caption split preserves child speaker/words metadata while keeping existing manual-quality removal policy for edited split text.
- Storage check confirms legacy project storage stays clean of `_nle_project_state`, `nle`, and `nle_snapshot`.
- NAS HeyDealer acceptance: `output/manual_verification/latest/nle_projection_metadata_preservation_nas_heydealer_20260628/acceptance/reference_benchmark_acceptance.md`
- Run `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_171508/benchmark_results.json`: accepted `true`, elapsed `45.188s`, raw/final/reference `58/56/89`, quality/text/timing `93.766/94.267/0.5808s`, final invalid/non-monotonic/overlap `0/0/0`, final last end/duration bound `180.0/180.0`, short/long `0/0`, global max-active `1`.
- Timeout audit: `output/manual_verification/latest/stt_worker_timeout_compare_nle_projection_metadata_nas_20260628/stt_worker_timeout_audit.md`; timeout detected `false`.

### Jammini

- Route status/probe passed before delegation; probe pointer was removed from the Sentinel index.
- Scout: `.agents/sentinel/handoffs/20260628-080426-next-nle-taption-runtime-contract-scout.md`
- Dex classification: accepted the NLE-to-legacy metadata preservation direction with scope narrowed to existing product metadata and runtime projection deepcopy. Arbitrary legacy custom schema expansion remains out of scope.

### Verification

- `./venv/bin/python -m py_compile core/project/nle_dual_write.py core/project/nle_operations.py tools/audit_nle_projection_metadata_preservation.py tests/test_project_nle_dual_write.py tests/test_nle_projection_metadata_preservation_audit.py` -> pass.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_dual_write.py tests/test_nle_projection_metadata_preservation_audit.py -k "metadata_preservation or projection_metadata"` -> `5 passed, 34 deselected`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_dual_write.py tests/test_nle_projection_metadata_preservation_audit.py` -> `39 passed`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_snapshot.py tests/test_project_context.py tests/test_editor_srt_open_refresh.py -k "runtime_nle or direct_srt or project_file_roundtrip or metadata or save_project_routes"` -> `20 passed, 98 deselected`.
- `./venv/bin/python tools/audit_nle_projection_metadata_preservation.py --output-dir output/manual_verification/latest/nle_projection_metadata_preservation_20260628` -> ready `true`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/verify_reference_fixture_availability.py --media ... --reference-srt ... --start-sec 0 --duration-sec 180 --output-dir output/manual_verification/latest/nle_projection_metadata_preservation_nas_preflight_20260628` -> ready `true`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/benchmark_subtitle_pipeline_variants.py --suite modes --variants mode_high --media ... --reference-srt ... --start-sec 0 --duration-sec 180 --keep-artifacts` -> `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_171508/benchmark_results.json`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/evaluate_reference_benchmark_acceptance.py .codex_work/benchmarks/subtitle_pipeline_variants/20260628_171508/benchmark_results.json --media-duration-sec 180.0 --output-dir output/manual_verification/latest/nle_projection_metadata_preservation_nas_heydealer_20260628/acceptance` -> accepted `true`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_stt_worker_timeout.py .codex_work/benchmarks/subtitle_pipeline_variants/20260628_165443/benchmark_results.json .codex_work/benchmarks/subtitle_pipeline_variants/20260628_171508/benchmark_results.json --output-dir output/manual_verification/latest/stt_worker_timeout_compare_nle_projection_metadata_nas_20260628` -> timeout detected `false`.

### Next Recommended Action

- Continue with the next safe NLE/Taption runtime contract from `ACTION_ITEMS.md` / `NLE_Action.md`.
- Treat any future arbitrary custom metadata persistence or persisted NLE disk-field adoption as a separate compatibility-gated schema change.
- Keep persisted NLE project fields, per-pixel NLE writes, QML/GPU default surfaces, runtime undo/redo UI changes, App Store packaging/submission work, and STT/default-cache policy changes blocked until explicit owner approval and compatibility proof exist.

## Current Handoff - 2026-06-28 NLE Gap-Delete Sequence Policy

### Scope

- Made the current AI Subtitle Studio gap-delete dual-write behavior explicit as `remove_gap_row_no_ripple`.
- Updated `core/project/nle_dual_write.py`, `tests/test_project_nle_dual_write.py`, `tools/audit_nle_gap_delete_sequence_policy.py`, `tests/test_nle_gap_delete_sequence_policy_audit.py`, NLE/status docs, completed action history, and the Jammini scout handoff classification.
- No UI layout/labels/colors/menus/popups, subtitle quality policy, STT/STT2/default-cache policy, persisted NLE disk-format, App Store packaging/signing/upload, DMG, runtime undo/redo UI, or per-pixel NLE write behavior changed.

### Results

- Audit: `output/manual_verification/latest/nle_gap_delete_sequence_policy_20260628/nle_gap_delete_sequence_policy.md`
- `ready=true`; sequence policy `remove_gap_row_no_ripple`.
- Dynamic checks prove explicit gap-row deletion preserves adjacent caption timing in legacy editor rows, runtime NLE rows, and raw vector `editor_state` storage.
- Storage check confirms legacy project storage stays clean of `_nle_project_state`, `nle`, and `nle_snapshot`.
- NAS HeyDealer acceptance: `output/manual_verification/latest/nle_gap_delete_sequence_policy_nas_heydealer_20260628/acceptance/reference_benchmark_acceptance.md`
- Run `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_165443/benchmark_results.json`: accepted `true`, elapsed `47.979s`, raw/final/reference `58/56/89`, quality/text/timing `93.766/94.267/0.5808s`, final invalid/non-monotonic/overlap `0/0/0`, final last end/duration bound `180.0/180.0`, short/long `0/0`, global max-active `1`.
- Timeout audit: `output/manual_verification/latest/stt_worker_timeout_compare_nle_gap_delete_policy_nas_20260628/stt_worker_timeout_audit.md`; timeout detected `false`.

### Jammini

- Route status/probe passed before delegation; probe file was removed from the worktree.
- Scout: `.agents/sentinel/handoffs/20260628-074703-next-nle-taption-runtime-contract-scout.md`
- Dex classification: accepted the owner path focus on `apply_gap_delete_dual_write_pilot`, rejected the scout's ripple premise, and implemented the narrower no-ripple runtime contract. Silent gap-delete ripple remains blocked until a separate owner-approved ripple/absorb operation exists.

### Verification

- `./venv/bin/python -m py_compile core/project/nle_dual_write.py tools/audit_nle_gap_delete_sequence_policy.py tests/test_project_nle_dual_write.py tests/test_nle_gap_delete_sequence_policy_audit.py` -> pass.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_dual_write.py tests/test_nle_gap_delete_sequence_policy_audit.py -k "gap_delete or sequence_policy"` -> `5 passed, 31 deselected`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_dual_write.py tests/test_nle_gap_delete_sequence_policy_audit.py` -> `36 passed`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_nle_operation_journal_audit.py tests/test_nle_runtime_owner_map_audit.py` -> `5 passed`.
- `./venv/bin/python tools/audit_nle_gap_delete_sequence_policy.py --output-dir output/manual_verification/latest/nle_gap_delete_sequence_policy_20260628` -> ready `true`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/verify_reference_fixture_availability.py --media ... --reference-srt ... --start-sec 0 --duration-sec 180 --output-dir output/manual_verification/latest/nle_gap_delete_sequence_policy_nas_preflight_20260628` -> ready `true`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/benchmark_subtitle_pipeline_variants.py --suite modes --variants mode_high --media ... --reference-srt ... --start-sec 0 --duration-sec 180 --keep-artifacts` -> `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_165443/benchmark_results.json`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/evaluate_reference_benchmark_acceptance.py .codex_work/benchmarks/subtitle_pipeline_variants/20260628_165443/benchmark_results.json --media-duration-sec 180.0 --output-dir output/manual_verification/latest/nle_gap_delete_sequence_policy_nas_heydealer_20260628/acceptance` -> accepted `true`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_stt_worker_timeout.py .codex_work/benchmarks/subtitle_pipeline_variants/20260628_164020/benchmark_results.json .codex_work/benchmarks/subtitle_pipeline_variants/20260628_165443/benchmark_results.json --output-dir output/manual_verification/latest/stt_worker_timeout_compare_nle_gap_delete_policy_nas_20260628` -> timeout detected `false`.

### Next Recommended Action

- Continue with the next safe NLE/Taption runtime contract from `ACTION_ITEMS.md` / `NLE_Action.md`.
- Treat any future ripple/absorb-style gap delete as a new behavior, not a correction to this slice: require explicit owner approval, separate operation naming, focused undo/projection tests, and NAS proof.
- Keep persisted NLE project fields, per-pixel NLE writes, QML/GPU default surfaces, runtime undo/redo UI changes, App Store packaging/submission work, and STT/default-cache policy changes blocked until explicit owner approval and compatibility proof exist.

## Current Handoff - 2026-06-28 NLE Dual-Write Duration Bound Trim

### Scope

- Added duration-bound enforcement to row-producing NLE dual-write release-commit paths before runtime NLE state sync and raw `editor_state` rebuild.
- Updated `core/project/project_context.py`, `core/project/nle_dual_write.py`, `tests/test_project_nle_dual_write.py`, `tools/audit_nle_dual_write_duration_bound.py`, `tests/test_nle_dual_write_duration_bound_audit.py`, NLE/status docs, completed action history, and Sentinel handoff index.
- No UI layout/labels/colors/menus/popups, subtitle quality policy, STT/STT2/default-cache policy, persisted NLE disk-format, App Store packaging/signing/upload, DMG, runtime undo/redo UI, or per-pixel NLE write behavior changed.

### Results

- Audit: `output/manual_verification/latest/nle_dual_write_duration_bound_20260628/nle_dual_write_duration_bound.md`
- `ready=true`; owner coverage `11/11`.
- Dynamic checks passed: `caption_move_tail_clamp` trims `1` row and `candidate_confirm_late_drop` drops `1` row.
- The tail clamp/drop checks cover legacy editor rows, runtime NLE rows, and raw vector `editor_state` storage.
- NAS HeyDealer acceptance: `output/manual_verification/latest/nle_dual_write_duration_bound_nas_heydealer_20260628/acceptance/reference_benchmark_acceptance.md`
- Run `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_164020/benchmark_results.json`: accepted `true`, elapsed `45.946s`, raw/final/reference `58/56/89`, quality/text/timing `93.766/94.267/0.5808s`, final invalid/non-monotonic/overlap `0/0/0`, final last end/duration bound `180.0/180.0`, short/long `0/0`, global max-active `1`.
- Timeout audit: `output/manual_verification/latest/stt_worker_timeout_compare_nle_duration_bound_nas_20260628/stt_worker_timeout_audit.md`; timeout detected `false`.

### Jammini

- Route status/probe passed; probe file was removed from the worktree.
- Scout: `.agents/sentinel/handoffs/20260628-073009-nle-dual-write-duration-trim-prep.md`
- Dex classification: accepted as the next bounded mutable-edit slice after adding focused raw-storage/NLE-state tests, audit coverage, and NAS HeyDealer proof. Persisted NLE fields, per-pixel writes, UI/QML, STT/default-cache, and App Store scopes remain blocked.

### Verification

- `./venv/bin/python -m py_compile core/project/project_context.py core/project/nle_dual_write.py tools/audit_nle_dual_write_duration_bound.py tests/test_project_nle_dual_write.py tests/test_nle_dual_write_duration_bound_audit.py` -> pass.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_dual_write.py tests/test_nle_dual_write_duration_bound_audit.py -k "duration_bound or caption_move_dual_write or candidate_confirm"` -> `10 passed, 26 deselected`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_nle_operation_journal_audit.py tests/test_nle_runtime_owner_map_audit.py` -> `5 passed`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_dual_write.py` -> `34 passed`.
- `./venv/bin/python tools/audit_nle_dual_write_duration_bound.py --output-dir output/manual_verification/latest/nle_dual_write_duration_bound_20260628` -> ready `true`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/verify_reference_fixture_availability.py --media ... --reference-srt ... --start-sec 0 --duration-sec 180 --output-dir output/manual_verification/latest/nle_dual_write_duration_bound_nas_preflight_20260628` -> ready `true`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/benchmark_subtitle_pipeline_variants.py --suite modes --variants mode_high --media ... --reference-srt ... --start-sec 0 --duration-sec 180 --keep-artifacts` -> `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_164020/benchmark_results.json`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/evaluate_reference_benchmark_acceptance.py .codex_work/benchmarks/subtitle_pipeline_variants/20260628_164020/benchmark_results.json --media-duration-sec 180.0 --output-dir output/manual_verification/latest/nle_dual_write_duration_bound_nas_heydealer_20260628/acceptance` -> accepted `true`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_stt_worker_timeout.py .codex_work/benchmarks/subtitle_pipeline_variants/20260628_162124/benchmark_results.json .codex_work/benchmarks/subtitle_pipeline_variants/20260628_164020/benchmark_results.json --output-dir output/manual_verification/latest/stt_worker_timeout_compare_nle_duration_bound_nas_20260628` -> timeout detected `false`.

### Next Recommended Action

- Continue with the next safe NLE/Taption runtime contract from `ACTION_ITEMS.md` / `NLE_Action.md`.
- Treat future mutation-source adoption as fresh owner-map/audit work before implementation.
- Keep persisted NLE project fields, per-pixel NLE writes, QML/GPU default surfaces, runtime undo/redo UI changes, App Store packaging/submission work, and STT/default-cache policy changes blocked until explicit owner approval and compatibility proof exist.

## Current Handoff - 2026-06-28 NLE Inline Edit Entry Contract

### Scope

- Added Taption-style inline edit entry trace/isolation for subtitle segment double-click/edit entry.
- Updated `ui/editor/ux/timeline_canvas_editing.py`, `tests/test_timeline_hit_targets.py`, `tools/audit_nle_inline_edit_entry_contract.py`, `tests/test_nle_inline_edit_entry_contract_audit.py`, NLE/status docs, completed action history, and Sentinel handoff index.
- No UI layout/labels/colors/menus/popups, subtitle quality policy, STT/STT2 policy, collect-cache defaults, final rows, persisted NLE disk-format, App Store packaging/signing/upload, DMG, runtime undo/redo UI, or per-pixel NLE write behavior changed.

### Results

- Audit: `output/manual_verification/latest/nle_inline_edit_entry_contract_20260628/nle_inline_edit_entry_contract.md`
- `ready=true`; Taption contract `inline_edit_entry_preview_only_until_text_commit`.
- Inline-edit entry trace event: `timeline_inline_edit_entry`.
- Entry trace includes no caption text payload, no raw target IDs, no NLE write, no project save, and no primary subtitle validation/rescan.
- Existing text change commit remains the `caption_text_edit` release commit.
- NAS HeyDealer acceptance: `output/manual_verification/latest/nle_inline_edit_entry_nas_heydealer_20260628/acceptance/reference_benchmark_acceptance.md`
- Run `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_162124/benchmark_results.json`: accepted `true`, elapsed `46.481s`, raw/final/reference `58/56/89`, quality/text/timing `93.766/94.267/0.5808s`, final invalid/non-monotonic/overlap `0/0/0`, final last end/duration bound `180.0/180.0`, short/long `0/0`, global max-active `1`.
- Timeout audit: `output/manual_verification/latest/stt_worker_timeout_compare_nle_inline_entry_nas_20260628/stt_worker_timeout_audit.md`; timeout detected `false`.

### Jammini

- Route status/probe passed; probe file was removed from the worktree.
- Scout: `.agents/sentinel/handoffs/20260628-071656-next-concrete-nle-taption-slice.md`
- Dex classification: deferred the scout's duration-bound trim enforcement candidate to a future mutable-edit owner-map slice. It is broader than this inline-edit entry trace/isolation change and needs dedicated dual-write tests before adoption.

### Verification

- `./venv/bin/python -m py_compile ui/editor/ux/timeline_canvas_editing.py tools/audit_nle_inline_edit_entry_contract.py tests/test_timeline_hit_targets.py tests/test_nle_inline_edit_entry_contract_audit.py` -> pass.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_hit_targets.py tests/test_nle_inline_edit_entry_contract_audit.py -k "inline_edit_entry or inline_text_commit_routes_through_nle_caption_text_edit or stt_candidate_is_not_edit_or_drag_target"` -> `5 passed, 151 deselected`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py -k "double_click or lock_edit_allows_canvas_inline_edit"` -> `2 passed, 191 deselected`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_trace_log_bundle_audit.py tests/test_trace_logger.py tests/test_nle_operation_journal_audit.py -k "trace or operation"` -> `20 passed`.
- `./venv/bin/python tools/audit_nle_inline_edit_entry_contract.py --output-dir output/manual_verification/latest/nle_inline_edit_entry_contract_20260628` -> ready `true`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/verify_reference_fixture_availability.py --media ... --reference-srt ... --start-sec 0 --duration-sec 180 --output-dir output/manual_verification/latest/nle_inline_edit_entry_nas_preflight_20260628` -> ready `true`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/benchmark_subtitle_pipeline_variants.py --suite modes --variants mode_high --media ... --reference-srt ... --start-sec 0 --duration-sec 180 --keep-artifacts` -> wrote `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_162124/benchmark_results.json`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/evaluate_reference_benchmark_acceptance.py .codex_work/benchmarks/subtitle_pipeline_variants/20260628_162124/benchmark_results.json --media-duration-sec 180.0 --output-dir output/manual_verification/latest/nle_inline_edit_entry_nas_heydealer_20260628/acceptance` -> accepted `true`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_stt_worker_timeout.py .codex_work/benchmarks/subtitle_pipeline_variants/20260628_153555/benchmark_results.json .codex_work/benchmarks/subtitle_pipeline_variants/20260628_162124/benchmark_results.json --output-dir output/manual_verification/latest/stt_worker_timeout_compare_nle_inline_entry_nas_20260628` -> timeout detected `false`.

### Next Recommended Action

- Continue with the next safe NLE/Taption runtime contract from `ACTION_ITEMS.md` / `NLE_Action.md`.
- The Jammini duration-bound trim enforcement candidate is a plausible next slice, but treat it as a mutable dual-write behavior change: first add owner-map coverage, focused tests, strict final duration-bound acceptance, and NAS HeyDealer proof.
- Keep persisted NLE project fields, per-pixel NLE writes, QML/GPU default surfaces, runtime undo/redo UI changes, App Store packaging/submission work, and STT/default-cache policy changes blocked until explicit owner approval and compatibility proof exist.

## Current Handoff - 2026-06-28 NLE Time Window View Decoupling Guard

### Scope

- Added focused tests and static audit for fit-to-view, scheduled fit, explicit time-window display, and saved-preference edit-window display as viewport-only paths.
- Updated `tests/test_timeline_time_window_decoupling.py`, `tools/audit_nle_time_window_view_decoupling.py`, `tests/test_nle_time_window_view_decoupling_audit.py`, NLE/status docs, and completed action history.
- No UI layout/labels/colors/menus/popups, subtitle quality policy, STT/STT2 policy, subtitle generation, final rows, persisted NLE disk-format, App Store packaging/signing/upload, DMG, runtime undo/redo UI, or per-pixel NLE write behavior changed.

### Results

- Audit: `output/manual_verification/latest/nle_time_window_view_decoupling_20260628/nle_time_window_view_decoupling.md`
- `ready=true`; view-window-only contract `true`.
- Model validation allowed `false`; project save allowed `false`; NLE write allowed `false`.
- Method contracts cover `TimelineWidget.fit_to_view`, `TimelineWidget.schedule_fit_to_view`, `TimelineTimeWindowMixin.show_time_window_seconds`, `TimelineTimeWindowMixin._apply_edit_window_seconds`, and `TimelineTimeWindowMixin.show_ten_second_edit_window`; forbidden calls/assignments are `0`.
- Focused tests prove fit-to-view and explicit/saved time-window controls preserve canvas/global subtitle rows and do not append runtime NLE operation journals or save projects.
- NAS HeyDealer generation validation was not run because this view-window-only slice does not touch STT/VAD/subtitle generation/final rows.

### Jammini

- Scout: `.agents/sentinel/handoffs/20260628-070859-next-nle-taption-runtime-contract-scout.md`
- Dex classification: deferred the scout's double-click full-repaint suppression candidate because repaint suppression overlaps prior dirty-rect/repaint lessons. Landed a narrower time-window/fit-to-view decoupling guard instead.

### Verification

- `./venv/bin/python -m py_compile tools/audit_nle_time_window_view_decoupling.py tests/test_timeline_time_window_decoupling.py tests/test_nle_time_window_view_decoupling_audit.py` -> pass.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_time_window_decoupling.py tests/test_nle_time_window_view_decoupling_audit.py` -> `4 passed`.
- `./venv/bin/python tools/audit_nle_time_window_view_decoupling.py --output-dir output/manual_verification/latest/nle_time_window_view_decoupling_20260628` -> ready `true`.

### Next Recommended Action

- Continue with the next safe NLE/Taption runtime contract from `ACTION_ITEMS.md`, using owner-map/audit proof before adopting any new mutation source.
- Keep persisted NLE project fields, per-pixel NLE writes, QML/GPU default surfaces, runtime undo/redo UI changes, App Store packaging/submission work, and STT/default-cache policy changes blocked until explicit owner approval and compatibility proof exist.

## Current Handoff - 2026-06-28 NLE Playhead Jump Isolation Guard

### Scope

- Added focused tests and static audit for global minimap click, timeline global seek, and editor scrub as immediate view/playhead-only paths.
- Updated `tests/test_timeline_playhead_jump_isolation.py`, `tools/audit_nle_playhead_jump_isolation.py`, `tests/test_nle_playhead_jump_isolation_audit.py`, NLE/status docs, and completed action history.
- No UI layout/labels/colors/menus/popups, subtitle quality policy, STT/STT2 policy, subtitle generation, final rows, persisted NLE disk-format, App Store packaging/signing/upload, DMG, runtime undo/redo UI, or per-pixel NLE write behavior changed.

### Results

- Audit: `output/manual_verification/latest/nle_playhead_jump_isolation_20260628/nle_playhead_jump_isolation.md`
- `ready=true`; playhead-jump view-only contract `true`.
- Model validation allowed `false`; project save allowed `false`; NLE write allowed `false`.
- Method contracts cover `GlobalCanvas.mousePressEvent`, `TimelineWidget._on_global_seek`, and `EditorTimelineVideoMixin._on_scrub`; forbidden calls/assignments are `0`.
- Focused tests prove global minimap click and timeline global seek preserve canvas/global subtitle rows and do not append runtime NLE operation journals or save projects.
- Focused editor scrub test proves the immediate path updates timeline playhead plus lightweight preview seek without subtitle validation/rescan, dirty marking, timing mutation, or dual-write calls.
- NAS HeyDealer generation validation was not run because this view/playhead-only slice does not touch STT/VAD/subtitle generation/final rows.

### Jammini

- Scout: `.agents/sentinel/handoffs/20260628-165700-next-nle-taption-runtime-contract-scout.md`
- Dex classification: accepted with narrower scope as test/audit hardening only. The scout's absolute `0.5ms` timing gate was not adopted because it is environment-dependent; the landed guard uses state/call-path isolation instead.

### Verification

- `./venv/bin/python -m py_compile tools/audit_nle_playhead_jump_isolation.py tests/test_timeline_playhead_jump_isolation.py tests/test_nle_playhead_jump_isolation_audit.py` -> pass.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_jump_isolation.py tests/test_nle_playhead_jump_isolation_audit.py` -> `5 passed`.
- `./venv/bin/python tools/audit_nle_playhead_jump_isolation.py --output-dir output/manual_verification/latest/nle_playhead_jump_isolation_20260628` -> ready `true`.

### Next Recommended Action

- Continue with the next safe NLE/Taption runtime contract from `ACTION_ITEMS.md`, using owner-map/audit proof before adopting any new mutation source.
- Keep persisted NLE project fields, per-pixel NLE writes, QML/GPU default surfaces, runtime undo/redo UI changes, App Store packaging/submission work, and STT/default-cache policy changes blocked until explicit owner approval and compatibility proof exist.

## Current Handoff - 2026-06-28 NLE Viewport Zoom Decoupling Guard

### Scope

- Added focused tests and static audit for timeline wheel zoom/global wheel scroll as viewport-only interactions.
- Updated `tests/test_timeline_wheel_zoom_decoupling.py`, `tools/audit_nle_viewport_zoom_decoupling.py`, `tests/test_nle_viewport_zoom_decoupling_audit.py`, NLE/status docs, and completed action history.
- No UI layout/labels/colors/menus/popups, subtitle quality policy, STT/STT2 policy, subtitle generation, final rows, persisted NLE disk-format, App Store packaging/signing/upload, DMG, runtime undo/redo UI, or per-pixel NLE write behavior changed.

### Results

- Audit: `output/manual_verification/latest/nle_viewport_zoom_decoupling_20260628/nle_viewport_zoom_decoupling.md`
- `ready=true`; viewport-only contract `true`.
- Model write allowed `false`; NLE write allowed `false`.
- Method contracts cover `TimelineWidget.wheelEvent`, `TimelineWidget._apply_zoom`, `GlobalCanvas.wheelEvent`, and `TimelineCanvas.set_zoom`; forbidden calls/assignments are `0`.
- Focused tests prove Ctrl-wheel zoom and global-canvas wheel scroll preserve canvas/global subtitle rows and do not append runtime NLE operation journals.
- NAS HeyDealer generation validation was not run because this view-only slice does not touch STT/VAD/subtitle generation/final rows.

### Jammini

- Scout: `.agents/sentinel/handoffs/20260628-164700-next-nle-taption-runtime-contract-scout.md`
- Dex classification: accepted with narrower scope as test/audit hardening only. The scout's owner files were correct; no runtime zoom behavior or UI design change was adopted.

### Verification

- `./venv/bin/python -m py_compile tools/audit_nle_viewport_zoom_decoupling.py tests/test_timeline_wheel_zoom_decoupling.py tests/test_nle_viewport_zoom_decoupling_audit.py` -> pass.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_wheel_zoom_decoupling.py tests/test_nle_viewport_zoom_decoupling_audit.py` -> `4 passed`.
- `./venv/bin/python tools/audit_nle_viewport_zoom_decoupling.py --output-dir output/manual_verification/latest/nle_viewport_zoom_decoupling_20260628` -> ready `true`.

### Next Recommended Action

- Continue with the next safe NLE/Taption runtime contract from `ACTION_ITEMS.md`, using owner-map/audit proof before adopting any new mutation source.
- Keep persisted NLE project fields, per-pixel NLE writes, QML/GPU default surfaces, runtime undo/redo UI changes, App Store packaging/submission work, and STT/default-cache policy changes blocked until explicit owner approval and compatibility proof exist.

## Current Handoff - 2026-06-28 NLE Preview Cache-Miss Block-Free Guard

### Scope

- Added a focused guard for preview/skimming cache misses so slow frame preparation cannot block `VideoPlayerWidget.preview_seek()`.
- Updated `tests/test_video_player_widget.py`, `tools/audit_nle_preview_skimming_cache.py`, `tests/test_nle_preview_skimming_cache_audit.py`, NLE/status docs, and completed action history.
- No UI layout/labels/colors/menus/popups, subtitle quality policy, STT/STT2 policy, persisted NLE disk-format, App Store packaging/signing/upload, DMG, cut-boundary evidence ownership, runtime undo/redo UI, or per-pixel NLE write behavior changed.

### Results

- Audit: `output/manual_verification/latest/nle_preview_skimming_cache_miss_block_free_20260628/nle_preview_skimming_cache_audit.md`
- `ready=true`; preview cache contract remains `purpose=editor_preview_skimming`, `evidence_role=user_preview_only`, `cut_boundary_evidence=false`, `ui_thread_decode_allowed=false`.
- `cache_miss_thread_contract` fields are all `true`: worker-thread scheduling, decode inside worker, worker named `video-preview-frame-cache`, worker-active reentry guard, and signal-based ready paint.
- Focused PyQt guard proves `preview_seek()` returns before a slow worker decode completes and stays below the `50ms` acceptance threshold.
- NAS preflight: `output/manual_verification/latest/nle_preview_skimming_cache_miss_nas_preflight_20260628/reference_fixture_availability.md`; ready `true`.
- NAS acceptance: `output/manual_verification/latest/nle_preview_skimming_cache_miss_nas_heydealer_20260628/acceptance/reference_benchmark_acceptance.md`; accepted `true`, elapsed `45.744s`, raw/final/reference `58/56/89`, quality/text/timing `93.766/94.267/0.5808s`, final invalid/non-monotonic/overlap `0/0/0`, global max-active `1`.
- NAS timeout audit: `output/manual_verification/latest/stt_worker_timeout_compare_nle_preview_cache_miss_nas_20260628/stt_worker_timeout_audit.md`; timeout detected `false`.

### Jammini

- Prep: `.agents/sentinel/handoffs/20260628-163300-nle-preview-skimming-cache-miss-prep.md`
- Dex classification: accepted as a bounded support input. The implementation kept the scope to test/audit hardening and did not add new UI design, persisted NLE fields, App Store work, or runtime subtitle-generation policy changes.

### Verification

- `./venv/bin/python -m py_compile tools/audit_nle_preview_skimming_cache.py tests/test_nle_preview_skimming_cache_audit.py tests/test_video_player_widget.py` -> pass.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_video_player_widget.py -k "preview_seek_cache_miss or preview_frame_cache_prepare or nearest_preview_frame_trace"` -> `4 passed, 79 deselected`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_nle_preview_skimming_cache_audit.py tests/test_preview_frame_cache.py` -> `5 passed`.
- `./venv/bin/python tools/audit_nle_preview_skimming_cache.py --output-dir output/manual_verification/latest/nle_preview_skimming_cache_miss_block_free_20260628` -> ready `true`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/verify_reference_fixture_availability.py --start-sec 0 --duration-sec 180 --output-dir output/manual_verification/latest/nle_preview_skimming_cache_miss_nas_preflight_20260628` -> ready `true`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/benchmark_subtitle_pipeline_variants.py --suite modes --variants mode_high --media ... --reference-srt ... --start-sec 0 --duration-sec 180 --keep-artifacts` -> `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_153555/benchmark_results.json`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/evaluate_reference_benchmark_acceptance.py .codex_work/benchmarks/subtitle_pipeline_variants/20260628_153555/benchmark_results.json --media-duration-sec 180.0 --output-dir output/manual_verification/latest/nle_preview_skimming_cache_miss_nas_heydealer_20260628/acceptance` -> accepted `true`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_stt_worker_timeout.py .codex_work/benchmarks/subtitle_pipeline_variants/20260628_152303/benchmark_results.json .codex_work/benchmarks/subtitle_pipeline_variants/20260628_153555/benchmark_results.json --output-dir output/manual_verification/latest/stt_worker_timeout_compare_nle_preview_cache_miss_nas_20260628` -> timeout detected `false`.

### Next Recommended Action

- Continue with the next safe NLE/Taption runtime contract from `ACTION_ITEMS.md`, using owner-map/audit proof before adopting any new mutation source.
- Keep persisted NLE project fields, per-pixel NLE writes, QML/GPU default surfaces, runtime undo/redo UI changes, and App Store packaging/submission work blocked until explicit owner approval and compatibility proof exist.

## Current Handoff - 2026-06-28 NLE Drag Commit-Boundary Guard

### Scope

- Added a focused PyQt guard for Taption-style center body drag behavior: preview may update during mouse move, but runtime NLE dual-write must wait until release.
- Updated `ui/editor/ux/timeline_input.py`, `tests/test_editor_timeline_drag_release.py`, `tools/audit_nle_runtime_owner_map.py`, `tests/test_nle_runtime_owner_map_audit.py`, NLE/status docs, and completed action history.
- No UI layout/labels/colors/menus/popups, subtitle quality policy, STT/STT2 policy, persisted NLE disk-format, App Store packaging/signing/upload, DMG, runtime undo/redo UI, or per-pixel NLE write behavior changed.

### Results

- Audit: `output/manual_verification/latest/nle_drag_commit_boundary_guard_20260628/nle_runtime_owner_map_audit.md`
- Owner map ready `true`; covered owners `24/24`; missing owners `0`.
- Commit-boundary guards `1/1`; missing guards `0`.
- Guard: `timeline_center_drag_preview_only_until_release` / `taption_preview_only_until_release_commit`.
- PyQt test proves NLE move call count `0` during mouse move, editor rows unchanged until release, canvas preview rows updated during drag, and NLE move call count `1` on release.
- Direction-aware diamond shared-boundary release ordering keeps left/right diamond drags gap-free.
- NAS preflight: `output/manual_verification/latest/nle_drag_commit_boundary_guard_nas_preflight_20260628/reference_fixture_availability.md`; ready `true`.
- NAS acceptance: `output/manual_verification/latest/nle_drag_commit_boundary_guard_nas_heydealer_20260628/acceptance/reference_benchmark_acceptance.md`; accepted `true`, elapsed `53.919s`, raw/final/reference `58/56/89`, quality/text/timing `93.766/94.267/0.5808s`, final invalid/non-monotonic/overlap `0/0/0`, global max-active `1`.
- NAS timeout audit: `output/manual_verification/latest/stt_worker_timeout_compare_nle_drag_commit_guard_nas_20260628/stt_worker_timeout_audit.md`; timeout detected `false`.

### Jammini

- Scout: `.agents/sentinel/handoffs/20260628-161800-next-nle-taption-ux-scout.md`
- Dex classification: defer the scout's preview/skimming cache-miss UI-thread block-prevention candidate until this commit-boundary guard is landed. It remains the next safe, non-UI-design NLE/Taption candidate.

### Verification

- `./venv/bin/python -m py_compile ui/editor/ux/timeline_input.py tools/audit_nle_runtime_owner_map.py tests/test_nle_runtime_owner_map_audit.py tests/test_editor_timeline_drag_release.py` -> pass.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_editor_timeline_drag_release.py -k "center_drag_preview_waits_until_release"` -> `1 passed, 7 deselected`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_editor_timeline_drag_release.py` -> `8 passed`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_nle_runtime_owner_map_audit.py` -> `3 passed`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_nle_runtime_owner_map_audit.py tests/test_project_nle_dual_write.py` -> `35 passed`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py -k "center_drag or reorder or diamond"` -> `32 passed, 161 deselected`.
- `./venv/bin/python tools/audit_nle_runtime_owner_map.py --output-dir output/manual_verification/latest/nle_drag_commit_boundary_guard_20260628` -> pass.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/verify_reference_fixture_availability.py --start-sec 0 --duration-sec 180 --output-dir output/manual_verification/latest/nle_drag_commit_boundary_guard_nas_preflight_20260628` -> ready `true`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/benchmark_subtitle_pipeline_variants.py --suite modes --variants mode_high --media ... --reference-srt ... --start-sec 0 --duration-sec 180 --keep-artifacts` -> `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_152303/benchmark_results.json`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/evaluate_reference_benchmark_acceptance.py .codex_work/benchmarks/subtitle_pipeline_variants/20260628_152303/benchmark_results.json --media-duration-sec 180.0 --output-dir output/manual_verification/latest/nle_drag_commit_boundary_guard_nas_heydealer_20260628/acceptance` -> accepted `true`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_stt_worker_timeout.py .codex_work/benchmarks/subtitle_pipeline_variants/20260628_141640/benchmark_results.json .codex_work/benchmarks/subtitle_pipeline_variants/20260628_152303/benchmark_results.json --output-dir output/manual_verification/latest/stt_worker_timeout_compare_nle_drag_commit_guard_nas_20260628` -> timeout detected `false`.

### Next Recommended Action

- Next safe NLE/Taption slice: preview/skimming cache-miss UI-thread block-prevention tooling, using the Jammini scout above.
- Keep persisted NLE project fields, per-pixel NLE writes, QML/GPU default surfaces, runtime undo/redo UI changes, and App Store packaging/submission work blocked until explicit owner approval and compatibility proof exist.

## Current Handoff - 2026-06-28 NLE Operation Journal Trace Events

### Scope

- Added best-effort async trace events for runtime-only NLE operation journal appends.
- Updated `core/project/nle_project_state.py`, `tools/audit_nle_operation_journal.py`, `tests/test_project_nle_operations.py`, `tests/test_nle_operation_journal_audit.py`, and NLE/status docs.
- Trace payloads include operation metadata, commit provenance, undo snapshot id, projected count, final stability counts, and runtime journal counts.
- Trace payloads omit caption text, raw project paths, and raw `target_ids`.
- No UI layout/labels/colors/menus/popups, subtitle quality policy, STT/STT2 policy, persisted NLE disk-format, App Store packaging/signing/upload, DMG, runtime undo/redo UI, or per-pixel NLE write behavior changed.

### Results

- Audit: `output/manual_verification/latest/nle_operation_journal_trace_audit_20260628/nle_operation_journal_audit.md`
- `ready=true`; operation families `12`.
- Runtime journal count `12`; operation trace event count `12`.
- Operation trace event contract ok `true`.
- Storage clean count `12`.
- Final invalid/non-monotonic/overlap `0/0/0`; global max-active `1`.
- NAS preflight: `output/manual_verification/latest/nle_operation_journal_trace_nas_preflight_20260628/reference_fixture_availability.md`; ready `true`.
- NAS acceptance: `output/manual_verification/latest/nle_operation_journal_trace_nas_heydealer_20260628/acceptance/reference_benchmark_acceptance.md`; accepted `true`, elapsed `52.699s`, raw/final/reference `58/56/89`, quality/text/timing `93.766/94.267/0.5808s`.
- NAS timeout audit: `output/manual_verification/latest/stt_worker_timeout_compare_nle_operation_trace_nas_20260628/stt_worker_timeout_audit.md`; timeout detected `false`.

### Jammini

- Scout: `.agents/sentinel/handoffs/20260628-160200-nle-operation-journal-trace.md`
- Dex classification: accept the bounded recommendation. Keep trace fields to safe operation/provenance/stability metadata and exclude text, raw paths, and raw target lists.

### Verification

- `./venv/bin/python -m py_compile core/project/nle_project_state.py tools/audit_nle_operation_journal.py tests/test_project_nle_operations.py tests/test_nle_operation_journal_audit.py` -> pass.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_operations.py tests/test_nle_operation_journal_audit.py -k "operation_journal"` -> `3 passed, 5 deselected`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_operations.py tests/test_project_nle_dual_write.py tests/test_nle_operation_journal_audit.py tests/test_nle_runtime_owner_map_audit.py` -> `43 passed`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_trace_logger.py tests/test_trace_log_bundle_audit.py` -> `18 passed`.
- `./venv/bin/python tools/audit_nle_operation_journal.py --output-dir output/manual_verification/latest/nle_operation_journal_trace_audit_20260628` -> pass.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/verify_reference_fixture_availability.py --start-sec 0 --duration-sec 180 --output-dir output/manual_verification/latest/nle_operation_journal_trace_nas_preflight_20260628` -> ready `true`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/benchmark_subtitle_pipeline_variants.py --suite modes --variants mode_high --media ... --reference-srt ... --start-sec 0 --duration-sec 180 --keep-artifacts` -> wrote `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_151123/benchmark_results.json`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/evaluate_reference_benchmark_acceptance.py .codex_work/benchmarks/subtitle_pipeline_variants/20260628_151123/benchmark_results.json --media-duration-sec 180.0 --output-dir output/manual_verification/latest/nle_operation_journal_trace_nas_heydealer_20260628/acceptance` -> accepted `true`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_stt_worker_timeout.py .codex_work/benchmarks/subtitle_pipeline_variants/20260628_141640/benchmark_results.json .codex_work/benchmarks/subtitle_pipeline_variants/20260628_151123/benchmark_results.json --output-dir output/manual_verification/latest/stt_worker_timeout_compare_nle_operation_trace_nas_20260628` -> timeout detected `false`.

### Next Recommended Action

- Use the current NAS HeyDealer first-180s fixture again for the next generation-affecting or STT/runtime timing slice.
- Keep persisted NLE project fields, per-pixel NLE writes, QML/GPU default surfaces, runtime undo/redo UI changes, and App Store packaging/submission work blocked until explicit owner approval and compatibility proof exist.

## Current Handoff - 2026-06-28 Project IO Trace Contract

### Scope

- Added best-effort async trace events for project save, disk open, and cache-hit open paths.
- Updated `core/project/project_io.py`, `tests/test_trace_logger.py`, `tools/audit_project_io_trace_contract.py`, and NLE/status docs.
- Trace events use project basename plus path hash only; raw project paths are not emitted.
- No UI layout/labels/colors/menus/popups, subtitle quality policy, STT/STT2 policy, persisted NLE disk-format, App Store packaging/signing/upload, DMG, or per-pixel NLE write behavior changed.

### Results

- Audit: `output/manual_verification/latest/project_io_trace_contract_20260628/project_io_trace_contract.md`
- `passed=true`; project IO event count `3`.
- Save/disk-open/cache-hit counts `1/1/1`.
- Raw path leak `false`; storage clean `true`.
- Disk/cache NLE runtime state attached `true/true`.
- Events include `event_type`, cache source, elapsed time, NLE runtime-state attachment, storage-clean flags, payload codec/compression, and stripped runtime-key count.

### Jammini

- Scout: `.agents/sentinel/handoffs/20260628-155100-project-io-save-load-trace.md`
- Dex classification: accept the bounded recommendation for project IO trace instrumentation. Keep the event names aligned with existing trace style as `project_file_save` / `project_file_open`; include the scout's `event_type`, codec/compression, hydration, and storage-clean evidence fields.

### Verification

- `./venv/bin/python -m py_compile core/project/project_io.py tools/audit_project_io_trace_contract.py tests/test_trace_logger.py` -> pass.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_trace_logger.py tests/test_trace_log_bundle_audit.py` -> `18 passed`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_snapshot.py tests/test_project_nle_runtime_cutover.py tests/test_project_context.py -k "nle or project_file_cache or write_project_file or read_project_file or save_project_routes_editor_rows_through_runtime_nle_state_without_drift or strips_external_runtime_views"` -> `26 passed, 85 deselected, 4 subtests passed`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_context.py` -> `86 passed`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_operations.py tests/test_project_nle_dual_write.py tests/test_nle_operation_journal_audit.py tests/test_nle_runtime_owner_map_audit.py` -> `43 passed`.
- `./venv/bin/python tools/audit_project_io_trace_contract.py --output-dir output/manual_verification/latest/project_io_trace_contract_20260628` -> pass.

### Next Recommended Action

- Continue NLE adoption through the next source-app runtime contract or owner-map-backed mutation source.
- Keep persisted NLE project fields, per-pixel NLE writes, QML/GPU default surfaces, and App Store packaging/submission work blocked until explicit owner approval and compatibility proof exist.

## Current Handoff - 2026-06-28 NLE Roughcut Range Edit Operation Coverage

### Scope

- Added output-domain NLE `roughcut_range_edit` operation support for roughcut candidate order/range edits.
- Updated `core/project/nle_dual_write.py`, operation-journal/owner-map audits, focused tests, and NLE/status docs.
- Preserved existing roughcut UI behavior, final subtitle rows, global canvas ownership, roughcut sidecar schemas, and legacy `.aissproj` storage shape.
- No UI layout/labels/colors/menus/popups, STT/STT2 policy, subtitle quality gate, detector threshold, persisted NLE disk field, App Store packaging/signing/upload, DMG, or per-pixel NLE write behavior changed.

### Results

- Operation journal audit: `output/manual_verification/latest/nle_roughcut_range_edit_operation_journal_20260628/nle_operation_journal_audit.md`
- Owner-map audit: `output/manual_verification/latest/nle_roughcut_range_edit_owner_map_20260628/nle_runtime_owner_map_audit.md`
- Operation families: `12`; release metadata `12`; undo snapshots `12`; runtime journals `12`; storage clean `12`.
- Owner map covered owners: `24/24`; missing owners `0`.
- `roughcut_range_edit` is constrained to `time_domain=output`; final invalid/non-monotonic/overlap stayed `0/0/0`; global max active stayed `1`.

### NAS

- NAS preflight: `output/manual_verification/latest/nle_roughcut_range_edit_nas_heydealer_20260628/preflight/reference_fixture_availability.md`
- NAS benchmark: `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_143939/benchmark_results.json`
- NAS acceptance: `output/manual_verification/latest/nle_roughcut_range_edit_nas_heydealer_20260628/acceptance/reference_benchmark_acceptance.md`
- Accepted `true`; elapsed `51.429s`; raw/final/reference `58/56/89`.
- Quality/text/timing `93.766/94.267/0.5808s`.
- Final invalid/non-monotonic/overlap `0/0/0`; final last end/duration bound `180.0/180.0`; short/long `0/0`; global max active `1`.
- Stage spans: STT1 `18.578131s`, STT2 `17.372568s`, word precision `14.804677s`, subtitle postprocess `0.582754s`.

### Jammini

- Scout: `.agents/sentinel/handoffs/20260628-153300-nle-roughcut-range-edit-owner-map.md`
- Dex classification: accept the bounded recommendation only within the verified scope: release commit, output-domain roughcut operation, final projection unchanged, and storage clean. Ignore overbroad "no risk" phrasing outside that proof.

### Verification

- `./venv/bin/python -m py_compile core/project/nle_dual_write.py tools/audit_nle_operation_journal.py tools/audit_nle_runtime_owner_map.py tests/test_project_nle_dual_write.py` -> pass.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_dual_write.py` -> `32 passed`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_nle_operation_journal_audit.py tests/test_nle_runtime_owner_map_audit.py` -> `5 passed`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_operations.py tests/test_project_nle_dual_write.py tests/test_nle_operation_journal_audit.py tests/test_nle_runtime_owner_map_audit.py` -> `43 passed`.
- `./venv/bin/python tools/audit_nle_operation_journal.py --output-dir output/manual_verification/latest/nle_roughcut_range_edit_operation_journal_20260628` -> pass.
- `./venv/bin/python tools/audit_nle_runtime_owner_map.py --output-dir output/manual_verification/latest/nle_roughcut_range_edit_owner_map_20260628` -> pass.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/evaluate_reference_benchmark_acceptance.py .codex_work/benchmarks/subtitle_pipeline_variants/20260628_143939/benchmark_results.json --output-dir output/manual_verification/latest/nle_roughcut_range_edit_nas_heydealer_20260628/acceptance` -> accepted `true`.

### Next Recommended Action

- Continue NLE work through the next owner-map-backed mutable/edit surface only if a new bounded source is found.
- Keep persisted NLE project fields, runtime undo/redo UI changes, per-pixel writes, QML/GPU timeline defaults, and App Store work blocked until explicit owner approval and compatibility proof exist.

## Current Handoff - 2026-06-28 NLE Preserved Marker Policy Audit

### Scope

- Added a read-only preserved-marker policy audit for fixed cut-boundary frames `2766,2676`.
- Added `tools/audit_cut_boundary_preserved_marker_policy.py`.
- Added `tests/test_cut_boundary_preserved_marker_policy.py`.
- Updated `ACTION_ITEMS.md`, `NLE_Action.md`, `COMPLETED_ACTION_ITEMS.md`, `docs/VALIDATION.md`, and `test_result.md`.
- No runtime detector threshold, subtitle quality policy, STT/STT2 policy, UI layout, labels, colors, menus, popups, QML/GPU timeline surface, App Store packaging/signing/upload, DMG, or persisted NLE disk fields changed.

### Results

- Preserved-marker audit: `output/manual_verification/latest/nle_preserved_marker_policy_20260628/cut_boundary_preserved_marker_policy.md`
- Source-fps input: `output/manual_verification/latest/nle_corrected_target_source_fps_scout_20260628/source_fps_scout.json`
- Robustness input: `output/manual_verification/latest/nle_cut_boundary_2766_detector_robustness_20260628/cut_boundary_detector_evidence_robustness.json`
- `passed=true`; review required frames `[]`.
- Frame `2676`: `visual_marker_confirmed`, source status `detected`, detector classification `visual_detection_available`, best score `72.293`, best hits `4`.
- Frame `2766`: `preserved_marker_required`, source status `preserved_only`, detector classification `weak_visual_change_not_threshold_candidate`, best score `3.812`, best hits `0`.
- Confirmed cuts remain point evidence rather than clip spans; preserved marker evidence can force subtitle split/snap but must not lower visual detector thresholds.

### NAS

- NAS preflight: `output/manual_verification/latest/nle_preserved_marker_policy_nas_preflight_20260628/reference_fixture_availability.md`
- Ready `true`; media and reference SRT exist; clipped reference rows `89`.
- No new subtitle-generation benchmark was run because this slice is read-only policy evidence and does not change runtime generation behavior.

### Jammini

- Route probe: `.agents/sentinel/handoffs/20260628-142200-watchdog-handoff-probe.md`
- Scout: `.agents/sentinel/handoffs/20260628-152200-nle-preserved-marker-policy.md`
- Dex classification: accept the scout's preserved-marker recommendation. Correct the suggested new fixture test path to the existing owner path `tests/test_cut_boundary_fixture_2766_2677.py`, whose expected frames are now `2766,2676`.

### Verification

- `./venv/bin/python -m py_compile tools/audit_cut_boundary_preserved_marker_policy.py tests/test_cut_boundary_preserved_marker_policy.py` -> pass.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_cut_boundary_preserved_marker_policy.py tests/test_cut_boundary_detector_evidence_robustness.py tests/test_cut_boundary_fixture_2766_2677.py` -> `10 passed, 1 skipped`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_cut_boundary_preserved_marker_policy.py --source-fps-scout output/manual_verification/latest/nle_corrected_target_source_fps_scout_20260628/source_fps_scout.json --detector-robustness output/manual_verification/latest/nle_cut_boundary_2766_detector_robustness_20260628/cut_boundary_detector_evidence_robustness.json --output-dir output/manual_verification/latest/nle_preserved_marker_policy_20260628` -> pass.
- `AI_SUBTITLE_STUDIO_CUT_BOUNDARY_FIXTURE=... AI_SUBTITLE_STUDIO_CUT_BOUNDARY_EXPECT="2766,2676" AI_SUBTITLE_STUDIO_CUT_BOUNDARY_PIPE_MAX_FPS="60" QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_cut_boundary_fixture_2766_2677.py` -> `6 passed`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/verify_reference_fixture_availability.py --start-sec 0 --duration-sec 180 --output-dir output/manual_verification/latest/nle_preserved_marker_policy_nas_preflight_20260628` -> pass, ready `true`.

### Next Recommended Action

- Continue NLE work through the next owner-map-backed mutable/edit surface slice, preserving the `2766` marker policy instead of lowering visual detector thresholds.
- Do not relax thresholds, change STT policy, promote cache defaults, alter UI, persist NLE disk fields, map point markers as clip spans, or perform App Store work from this slice.

## Current Handoff - 2026-06-28 Live NAS HeyDealer STT Regression Refresh

### Scope

- Refreshed the owner-required HeyDealer first-180s NAS fixture after the owner reported NAS was on again.
- Ran current NAS preflight, one High-mode real-media benchmark, strict reference acceptance, and STT worker-timeout comparison.
- Updated `ACTION_ITEMS.md`, `COMPLETED_ACTION_ITEMS.md`, `test_result.md`, and this handoff.
- No runtime STT/STT2/word precision policy, collect-cache default, subtitle quality gate, UI/UX, NLE persistence, App Store packaging/signing/upload, DMG, or detector threshold changed.

### Results

- Preflight: `output/manual_verification/latest/heydealer_nas_preflight_live_20260628/reference_fixture_availability.md`
- Benchmark: `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_141640/benchmark_results.json`
- Acceptance: `output/manual_verification/latest/stt_nas_live_heydealer_20260628/acceptance/reference_benchmark_acceptance.md`
- Timeout audit: `output/manual_verification/latest/stt_worker_timeout_compare_nas_live_20260628/stt_worker_timeout_audit.md`
- Accepted `true`; elapsed `45.631s`; raw/final/reference `58/56/89`.
- Quality/text/timing `93.766/94.267/0.5808s`.
- Final invalid/non-monotonic/overlap `0/0/0`; final last end/duration bound `180.0/180.0`; short/long `0/0`; global max active `1`.
- Stage spans: STT1 `18.255019s`, STT2 `14.239592s`, word precision `12.559778s`, subtitle postprocess `0.495304s`.
- Timeout audit reports `timeout_detected=false` when comparing baseline `20260628_113906` against live run `20260628_141640`.

### Jammini

- Route probe: `.agents/sentinel/handoffs/20260628-141544-watchdog-handoff-probe.md`
- Scout: `.agents/sentinel/handoffs/20260628-151600-stt-nas-on-regression-gate.md`
- Dex classification: accept the gate checklist. Keep collect-cache default promotion deferred until explicit owner review.

### Verification

- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/verify_reference_fixture_availability.py --start-sec 0 --duration-sec 180 --output-dir output/manual_verification/latest/heydealer_nas_preflight_live_20260628` -> ready `true`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/benchmark_subtitle_pipeline_variants.py --suite modes --variants mode_high --media ... --reference-srt ... --start-sec 0 --duration-sec 180 --keep-artifacts` -> wrote `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_141640/benchmark_results.json`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/evaluate_reference_benchmark_acceptance.py .codex_work/benchmarks/subtitle_pipeline_variants/20260628_141640/benchmark_results.json --media-duration-sec 180.0 --output-dir output/manual_verification/latest/stt_nas_live_heydealer_20260628/acceptance` -> accepted `true`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_stt_worker_timeout.py .codex_work/benchmarks/subtitle_pipeline_variants/20260628_113906/benchmark_results.json .codex_work/benchmarks/subtitle_pipeline_variants/20260628_141640/benchmark_results.json --output-dir output/manual_verification/latest/stt_worker_timeout_compare_nas_live_20260628` -> timeout detected `false`.

### Next Recommended Action

- Continue active item 1 through explicit owner review of collect-cache default promotion or the next behavior-preserving STT worker lifecycle diagnostic.
- Do not promote `stt_primary_collect_cache_enabled` or `stt_recheck_collect_cache_enabled` without explicit owner approval.

## Current Handoff - 2026-06-28 NLE Cut-Boundary 2766 Detector Evidence Robustness

### Scope

- Added a read-only robustness audit for fixed cut-boundary frame `2766`.
- Added `tools/audit_cut_boundary_detector_evidence_robustness.py`.
- Added `tests/test_cut_boundary_detector_evidence_robustness.py`.
- Updated `ACTION_ITEMS.md`, `NLE_Action.md`, `COMPLETED_ACTION_ITEMS.md`, `docs/VALIDATION.md`, and `test_result.md`.
- No runtime detector thresholds, subtitle quality policy, STT/STT2 policy, UI layout, labels, colors, menus, popups, QML/GPU timeline surface, App Store packaging/signing/upload, DMG, or persisted NLE disk fields changed.

### Results

- Robustness audit: `output/manual_verification/latest/nle_cut_boundary_2766_detector_robustness_20260628/cut_boundary_detector_evidence_robustness.md`
- Target frames `2766,2676`; source-fps pairs `2765:2766,2675:2676`.
- Modes `fast4,cross5,full9`; widths `320,480,960,1920`.
- Frame `2766`: `weak_visual_change_not_threshold_candidate`; detected any mode `false`; best mode `cross5`; best width `1920`; best score `3.812`; best hits `0`; best pixel `0.034849`; best motion `1.315`.
- Frame `2676`: `visual_detection_available`; detected any mode `true`; best score `72.293`; best hits `4`; best pixel `0.884247`; best motion `65.37`.
- Detector tuning candidate count `0`; threshold relaxation allowed `false`; runtime change allowed `false`.

### Jammini

- Route probe: `.agents/sentinel/handoffs/20260628-140524-watchdog-handoff-probe.md`
- Scout: `.agents/sentinel/handoffs/20260628-141000-cut-boundary-2766-detector-scout.md`
- Dex classification: accept the scout's warning not to lower detector thresholds. Dex implemented a broader mode/width robustness audit rather than only a preserved-only regression test.

### Verification

- `./venv/bin/python -m py_compile tools/audit_cut_boundary_detector_evidence_robustness.py tests/test_cut_boundary_detector_evidence_robustness.py` -> pass.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_cut_boundary_detector_evidence_robustness.py tests/test_cut_boundary_fixture_target_correction.py tests/test_cut_boundary_fixture_2766_2677.py` -> `9 passed, 1 skipped`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_cut_boundary_detector_evidence_robustness.py "/Users/u_mo_c/Library/Mobile Documents/com~apple~CloudDocs/AI_EDIT/내 프로젝트 (3).MP4" --pairs 2765:2766,2675:2676 --output-dir output/manual_verification/latest/nle_cut_boundary_2766_detector_robustness_20260628` -> pass.

### Next Recommended Action

- Treat frame `2766` as preserved frame-grid/marker evidence or revisit fixture truth; do not lower visual detector thresholds from this fixture alone.
- Continue NLE work through marker/preserved-boundary policy or the next owner-map-backed mutable/edit surface slice.

## Current Handoff - 2026-06-28 NLE Cut-Boundary Fixture Target Correction

### Scope

- Corrected the fixed cut-boundary QA target convention from historical `2677` to `2676`.
- Added `tools/audit_cut_boundary_fixture_target_correction.py`.
- Added `tests/test_cut_boundary_fixture_target_correction.py`.
- Updated fixed fixture defaults in `tools/verify_cut_boundary_source_fps_scout.py`, `tools/audit_cut_boundary_visual_window.py`, and `tests/test_cut_boundary_fixture_2766_2677.py`.
- Updated `ACTION_ITEMS.md`, `NLE_Action.md`, `COMPLETED_ACTION_ITEMS.md`, `docs/VALIDATION.md`, and `test_result.md`.
- No runtime detector thresholds, subtitle quality policy, STT/STT2 policy, UI layout, labels, colors, menus, popups, QML/GPU timeline surface, App Store packaging/signing/upload, DMG, or persisted NLE disk fields changed.

### Results

- Target correction audit: `output/manual_verification/latest/nle_cut_boundary_fixture_target_correction_20260628/cut_boundary_fixture_target_correction.md`
- Corrected source-fps scout: `output/manual_verification/latest/nle_corrected_target_source_fps_scout_20260628/source_fps_scout.md`
- Corrected visual-window audit: `output/manual_verification/latest/nle_corrected_target_visual_window_audit_20260628/cut_boundary_visual_window_audit.md`
- Corrected frame-semantics audit: `output/manual_verification/latest/nle_corrected_target_frame_semantics_audit_20260628/cut_boundary_frame_semantics_audit.md`
- Corrected fixture convention audit: `output/manual_verification/latest/nle_corrected_target_fixture_convention_audit_20260628/cut_boundary_fixture_convention_audit.md`
- Corrected target frames `2766,2676`; corrected source-fps pairs `2765:2766,2675:2676`.
- Frame `2676`: detected `true`, target-best, score `71.932`, expected pair `2675->2676`, convention review required `false`.
- Frame `2766`: still `preserved_only` / `target_detection_gap`, score `2.059`; this remains the open detector-evidence target before threshold tuning.
- Corrected frame-semantics audit reports semantic mismatch count `0` and target detection gap count `1`.
- Corrected fixture convention audit exits `0` with fixture label/boundary convention review required `false`.

### NAS

- NAS preflight: `output/manual_verification/latest/nle_target_correction_nas_preflight_20260628/reference_fixture_availability.md`
- Ready `true`; media and reference SRT exist; clipped reference rows `89`.
- No new subtitle-generation benchmark was run because this slice changes QA target convention/default audit inputs only, not runtime generation behavior.

### Jammini

- Route probe: `.agents/sentinel/handoffs/20260628-135221-watchdog-handoff-probe.md`
- Scout: `.agents/sentinel/handoffs/20260628-133200-cut-boundary-target-correction.md`
- Dex classification: accept the `2677 -> 2676` target correction. Defer the scout's runtime offset-logic suggestion because this slice is QA target/default-audit correction only.

### Verification

- `./venv/bin/python -m py_compile tools/audit_cut_boundary_fixture_target_correction.py tests/test_cut_boundary_fixture_target_correction.py tools/verify_cut_boundary_source_fps_scout.py tools/audit_cut_boundary_visual_window.py tests/test_cut_boundary_fixture_2766_2677.py` -> pass.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_cut_boundary_fixture_target_correction.py tests/test_cut_boundary_fixture_convention_audit.py tests/test_cut_boundary_frame_semantics_audit.py tests/test_cut_boundary_fixture_2766_2677.py` -> `13 passed, 1 skipped`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_cut_boundary_fixture_target_correction.py output/manual_verification/latest/nle_cut_boundary_fixture_convention_audit_20260628/cut_boundary_fixture_convention_audit.json --output-dir output/manual_verification/latest/nle_cut_boundary_fixture_target_correction_20260628` -> pass, corrected frames `2766,2676`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/verify_cut_boundary_source_fps_scout.py ... --output-dir output/manual_verification/latest/nle_corrected_target_source_fps_scout_20260628` -> pass.
- `AI_SUBTITLE_STUDIO_CUT_BOUNDARY_FIXTURE=... AI_SUBTITLE_STUDIO_CUT_BOUNDARY_EXPECT="2766,2676" AI_SUBTITLE_STUDIO_CUT_BOUNDARY_PIPE_MAX_FPS="60" QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_cut_boundary_fixture_2766_2677.py` -> `6 passed`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_cut_boundary_visual_window.py ... --output-dir output/manual_verification/latest/nle_corrected_target_visual_window_audit_20260628` -> expected fail, exit `1`, because frame `2766` remains not detected.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_cut_boundary_frame_semantics.py ... --output-dir output/manual_verification/latest/nle_corrected_target_frame_semantics_audit_20260628` -> expected fail, exit `1`, because frame `2766` remains a target detection gap.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_cut_boundary_fixture_convention.py ... --output-dir output/manual_verification/latest/nle_corrected_target_fixture_convention_audit_20260628` -> pass.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/verify_reference_fixture_availability.py --start-sec 0 --duration-sec 180 --output-dir output/manual_verification/latest/nle_target_correction_nas_preflight_20260628` -> pass, ready `true`.

### Next Recommended Action

- Continue detector-evidence work for frame `2766`, which remains a target detection gap without a strong target/neighbor delta.
- Do not relax thresholds, change STT policy, promote cache defaults, alter UI, persist NLE disk fields, or perform App Store work from this slice.

## Current Handoff - 2026-06-28 NLE Cut-Boundary Fixture Convention Contact Sheet Audit

### Scope

- Continued the source-app NLE cut-boundary accuracy workstream by materializing actual fixed-fixture frames into contact-sheet PNG evidence.
- Added `tools/audit_cut_boundary_fixture_convention.py`.
- Added `tests/test_cut_boundary_fixture_convention_audit.py`.
- Updated `ACTION_ITEMS.md`, `NLE_Action.md`, `COMPLETED_ACTION_ITEMS.md`, `docs/VALIDATION.md`, and `test_result.md`.
- No runtime detector thresholds, subtitle quality policy, STT/STT2 policy, UI layout, labels, colors, menus, popups, QML/GPU timeline surface, App Store packaging/signing/upload, DMG, or persisted NLE disk fields changed.

### Results

- Fixture convention audit: `output/manual_verification/latest/nle_cut_boundary_fixture_convention_audit_20260628/cut_boundary_fixture_convention_audit.md`
- Contact sheets:
  - `output/manual_verification/latest/nle_cut_boundary_fixture_convention_audit_20260628/target_2677_frame_contact_sheet.png`
  - `output/manual_verification/latest/nle_cut_boundary_fixture_convention_audit_20260628/target_2766_frame_contact_sheet.png`
- `fixture_label_or_boundary_convention_review_required=true`.
- Label/boundary convention review count `1`; detector evidence required count `1`; contact sheet count `2`.
- Frame `2677`: expected pair `2676->2677` mean delta `2.381499`; strongest pair `2675->2676` mean delta `72.849699`; ratio `30.589851`. Visual inspection shows the hard visual change occurs between frames `2675` and `2676`, not `2676` and `2677`.
- Frame `2766`: expected pair `2765->2766` mean delta `2.506516`; strongest pair `2768->2769` mean delta `3.251852`; ratio `1.297359`. Treat this as detector-evidence work, not a fixture-convention correction.
- The audit exits `1` while convention review remains required. Treat that exit as expected diagnostic evidence, not a runtime regression.

### NAS

- NAS preflight: `output/manual_verification/latest/nle_fixture_convention_nas_preflight_20260628/reference_fixture_availability.md`
- Ready `true`; media and reference SRT exist; clipped reference rows `89`.
- No new subtitle-generation benchmark was run because this slice is read-only fixture evidence generation and does not change runtime behavior. Latest runtime subtitle stability proof remains the previous accepted NAS benchmark referenced in `ACTION_ITEMS.md`.

### Jammini

- Route probe: `.agents/sentinel/handoffs/20260628-134307-watchdog-handoff-probe.md`
- Scout: `.agents/sentinel/handoffs/20260628-133100-cut-boundary-fixture-contact-sheet.md`
- Dex classification: accept the contact-sheet direction, but Dex implemented fresh frame extraction/contact-sheet artifacts rather than only mapping cached thumbnail paths.

### Verification

- `./venv/bin/python -m py_compile tools/audit_cut_boundary_fixture_convention.py tests/test_cut_boundary_fixture_convention_audit.py` -> pass.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_cut_boundary_fixture_convention_audit.py tests/test_cut_boundary_frame_semantics_audit.py` -> `6 passed`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_cut_boundary_fixture_convention.py ... --output-dir output/manual_verification/latest/nle_cut_boundary_fixture_convention_audit_20260628` -> expected fail, exit `1`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/verify_reference_fixture_availability.py --start-sec 0 --duration-sec 180 --output-dir output/manual_verification/latest/nle_fixture_convention_nas_preflight_20260628` -> pass, ready `true`.

### Next Recommended Action

- Decide or correct the `2676 -> 2677` fixture label/boundary-frame convention before detector threshold tuning.
- Continue detector-evidence work for frame `2766`, which remains a target detection gap without a strong target/neighbor delta.
- Do not relax thresholds, change STT policy, promote cache defaults, alter UI, persist NLE disk fields, or perform App Store work from this slice.

## Current Handoff - 2026-06-28 NLE Cut-Boundary Frame Semantics Audit

### Scope

- Continued the source-app NLE cut-boundary accuracy workstream by adding a read-only frame-semantics classifier for the existing visual-window audit JSON.
- Added `tools/audit_cut_boundary_frame_semantics.py`.
- Added `tests/test_cut_boundary_frame_semantics_audit.py`.
- Updated `ACTION_ITEMS.md`, `NLE_Action.md`, `COMPLETED_ACTION_ITEMS.md`, `docs/VALIDATION.md`, and `test_result.md`.
- No runtime detector thresholds, subtitle quality policy, STT/STT2 policy, UI layout, labels, colors, menus, popups, QML/GPU timeline surface, App Store packaging/signing/upload, DMG, or persisted NLE disk fields changed.

### Results

- Frame semantics audit: `output/manual_verification/latest/nle_cut_boundary_frame_semantics_audit_20260628/cut_boundary_frame_semantics_audit.md`
- `frame_semantics_review_required=true`.
- Semantic mismatch count `1`; target detection gap count `2`; detected-neighbor conflict count `1`; detector-tuning candidate count `1`.
- Frame `2766`: classification `target_detection_gap`; expected transition `2765->2766`; strongest local transition `2768->2769`; strongest detected `false`.
- Frame `2677`: classification `detected_neighbor_before_target`; expected transition `2676->2677`; strongest detected transition `2675->2676`; offset `-1`; score `71.932`.
- The audit exits `1` while review is required. Treat that exit as expected diagnostic evidence, not a runtime regression.

### NAS Regression

- NAS preflight: `output/manual_verification/latest/heydealer_nas_preflight_current_20260628_latest/reference_fixture_availability.md`
- NAS benchmark: `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_133307/benchmark_results.json`
- NAS acceptance: `output/manual_verification/latest/nle_frame_semantics_nas_heydealer_20260628/acceptance/reference_benchmark_acceptance.md`
- Accepted `true`; elapsed `179.579s`; raw/final/reference `58/56/89`; quality/text/timing `93.766/94.267/0.5808s`.
- Final invalid/non-monotonic/overlap `0/0/0`; final last end/duration bound `180.0/180.0`; short/long `0/0`; global max active `1`.
- STT worker compare: `output/manual_verification/latest/stt_worker_timeout_compare_frame_semantics_nas_20260628/stt_worker_timeout_audit.md`
- Timeout detected `false`. The run is slow STT1 collect evidence (`152.487713s`), not timeout/fallback proof or speed approval.

### Jammini

- Route probe: `.agents/sentinel/handoffs/20260628-132944-watchdog-handoff-probe.md`
- Scout: `.agents/sentinel/handoffs/20260628-133000-cut-boundary-frame-semantics-audit.md`
- Dex classification: accept the scout direction to freeze a frame-semantics artifact and defer threshold changes, STT/model changes, UI/QML, App Store, and persisted NLE fields. Use Dex-generated JSON values as source truth where the scout summary differs.

### Verification

- `./venv/bin/python -m py_compile tools/audit_cut_boundary_frame_semantics.py tests/test_cut_boundary_frame_semantics_audit.py` -> pass.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_cut_boundary_frame_semantics_audit.py tests/test_cut_boundary_visual_window_audit.py` -> `6 passed`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_cut_boundary_frame_semantics.py ... --output-dir output/manual_verification/latest/nle_cut_boundary_frame_semantics_audit_20260628` -> expected fail, exit `1`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/evaluate_reference_benchmark_acceptance.py .codex_work/benchmarks/subtitle_pipeline_variants/20260628_133307/benchmark_results.json --media-duration-sec 180.0 --output-dir output/manual_verification/latest/nle_frame_semantics_nas_heydealer_20260628/acceptance` -> `accepted=true`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_stt_worker_timeout.py .codex_work/benchmarks/subtitle_pipeline_variants/20260628_113906/benchmark_results.json .codex_work/benchmarks/subtitle_pipeline_variants/20260628_133307/benchmark_results.json --output-dir output/manual_verification/latest/stt_worker_timeout_compare_frame_semantics_nas_20260628` -> pass, `timeout_detected=false`.

### Next Recommended Action

- Verify fixture label/boundary-frame convention for the `2676 -> 2677` target before tuning detector thresholds.
- Continue detector-evidence work for frame `2766`, which remains a target detection gap without a detected neighbor in the local window.
- Do not relax thresholds, change STT policy, promote cache defaults, alter UI, persist NLE disk fields, or perform App Store work from this slice.

## Current Handoff - 2026-06-28 NLE Cut-Boundary Visual Window Audit

### Scope

- Continued the source-app NLE cut-boundary accuracy workstream by adding read-only visual transition window ranking around fixed frames `2766` and `2677`.
- Added `tools/audit_cut_boundary_visual_window.py`.
- Added `tests/test_cut_boundary_visual_window_audit.py`.
- Updated `ACTION_ITEMS.md`, `NLE_Action.md`, `COMPLETED_ACTION_ITEMS.md`, `docs/VALIDATION.md`, and `test_result.md`.
- No runtime detector thresholds, subtitle quality policy, STT/STT2 policy, UI layout, labels, colors, menus, popups, QML/GPU timeline surface, App Store packaging/signing/upload, DMG, or persisted NLE disk fields changed.

### Results

- Visual window audit: `output/manual_verification/latest/nle_cut_boundary_visual_window_audit_20260628/cut_boundary_visual_window_audit.md`
- Strict targets detected: `false`.
- Target best count: `0/2`.
- Frame `2766`: detected `false`, rank `4`, target score `2.059`, best nearby frame `2769`, best score `2.715`, best detected `false`.
- Frame `2677`: detected `false`, rank `2`, target score `1.997`, best nearby frame `2676`, best score `71.932`, best detected `true`.
- The audit exits `1` while any target is not detected. Treat that exit as expected diagnostic evidence, not as a runtime regression.

### Jammini

- Route probe: `.agents/sentinel/handoffs/20260628-132057-watchdog-handoff-probe.md`
- Scout: `.agents/sentinel/handoffs/20260628-132100-cut-boundary-visual-window-audit.md`
- Dex classification: accept the read-only tooling direction. The scout recommended window ranking and explicitly deferred threshold changes, STT/model changes, UI/QML, App Store, and persisted NLE fields.

### Verification

- `./venv/bin/python -m py_compile tools/audit_cut_boundary_visual_window.py tests/test_cut_boundary_visual_window_audit.py` -> pass.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_cut_boundary_visual_window_audit.py` -> `3 passed`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_cut_boundary_visual_window.py ... --targets 2766,2677 --radius 3 --output-dir output/manual_verification/latest/nle_cut_boundary_visual_window_audit_20260628` -> expected fail, exit `1`.

### Next Recommended Action

- Investigate the frame semantics around `2676 -> 2677` before tuning detector thresholds: the strongest visual transition is currently ranked at frame `2676`, while the requested target frame is `2677`.
- Do not relax thresholds, change STT policy, promote cache defaults, alter UI, persist NLE disk fields, or perform App Store work from this slice.

## Current Handoff - 2026-06-28 NLE Fixed Cut-Boundary Visual Evidence Gate

### Scope

- Continued the source-app NLE cut-boundary accuracy workstream by separating visual detector proof from frame-grid preservation for fixed frames `2766` and `2677`.
- Modified `tools/verify_cut_boundary_source_fps_scout.py`.
- Modified `tests/test_cut_boundary_fixture_2766_2677.py`.
- Modified `tests/test_pipeline_cut_boundary_cache.py` to use the official project storage reader for current binary/json project I/O.
- Updated `ACTION_ITEMS.md`, `NLE_Action.md`, `COMPLETED_ACTION_ITEMS.md`, `docs/VALIDATION.md`, and `test_result.md`.
- No runtime detector thresholds, subtitle quality policy, STT/STT2 policy, UI layout, labels, colors, menus, popups, QML/GPU timeline surface, App Store packaging/signing/upload, DMG, or persisted NLE disk fields changed.

### Results

- Visual evidence scout: `output/manual_verification/latest/nle_fixed_cut_boundary_visual_evidence_gate_20260628/source_fps_scout.md`
- Strict visual gate: `output/manual_verification/latest/nle_fixed_cut_boundary_visual_evidence_gate_20260628_strict/source_fps_scout.md`
- Decoder frame extraction status: `ok`.
- Probe source: `ffprobe`.
- Pipe fps: `60000/1001`.
- Visual evidence available: `true`.
- Strict visual detection passed: `false`.
- Visual candidate missing count: `2`.
- Frame `2766`: `preserved_only`, score `2.059`, region hits `0`, pixel ratio `0.029392`, edge ratio `0.048021`, frame preserved `true`.
- Frame `2677`: `preserved_only`, score `1.997`, region hits `0`, pixel ratio `0.029288`, edge ratio `0.046615`, frame preserved `true`.
- Strict `--require-visual-detection` command exits `1` as expected. Treat this as a blocker for visual-detection claims, not as a regression in frame-grid preservation.

### Jammini

- Route probe: `.agents/sentinel/handoffs/20260628-131045-watchdog-handoff-probe.md`
- Scout: `.agents/sentinel/handoffs/20260628-131100-nle-fixed-cut-boundary-visual-evidence.md`
- Dex classification: accept the bounded verifier-gate direction. The scout recommended visual evidence checker integration and explicitly deferred threshold changes, STT/model changes, UI/QML, App Store, and persisted NLE fields.

### Verification

- `./venv/bin/python -m py_compile tools/verify_cut_boundary_source_fps_scout.py tests/test_cut_boundary_fixture_2766_2677.py tests/test_pipeline_cut_boundary_cache.py` -> pass.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_cut_boundary_fixture_2766_2677.py` -> `5 passed, 1 skipped`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/verify_cut_boundary_source_fps_scout.py ... --output-dir output/manual_verification/latest/nle_fixed_cut_boundary_visual_evidence_gate_20260628` -> pass, `strict_visual_detection_passed=false`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/verify_cut_boundary_source_fps_scout.py ... --require-visual-detection --output-dir output/manual_verification/latest/nle_fixed_cut_boundary_visual_evidence_gate_20260628_strict` -> expected fail, exit `1`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_cut_boundary_fixture_2766_2677.py tests/test_cut_boundary_auto_scan_backend.py tests/test_subtitle_boundary_alignment.py tests/test_pipeline_cut_boundary_cache.py` -> `78 passed, 1 skipped`.
- `git diff --check -- .` -> pass.

### Next Recommended Action

- Continue cut-boundary tuning only by improving detector evidence for frames `2766` and `2677` under `--require-visual-detection`; do not call preserved-only evidence visual detection proof.
- Do not relax thresholds, change STT policy, promote cache defaults, alter UI, persist NLE disk fields, or perform App Store work from this slice.

## Current Handoff - 2026-06-28 STT Worker Timeout Audit

### Scope

- Continued `ACTION_ITEMS.md` item `STT2 / Word Precision Generation Latency Profiling And Accuracy-Preserving Trim` by adding read-only STT worker timeout artifact audit tooling.
- Added `tools/audit_stt_worker_timeout.py`.
- Added `tests/test_stt_worker_timeout_audit.py`.
- Updated `ACTION_ITEMS.md`, `COMPLETED_ACTION_ITEMS.md`, `docs/VALIDATION.md`, and `test_result.md`.
- No runtime STT policy, model choice, STT2/word precision coverage, collect-cache defaults, quality gates, UI/UX, App Store packaging/signing/upload, DMG, or NLE persistence behavior changed.

### Results

- Timeout comparison audit: `output/manual_verification/latest/stt_worker_timeout_compare_20260628/stt_worker_timeout_audit.md`
- Compared benchmark artifacts:
  - baseline: `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_113906/benchmark_results.json`
  - slow run: `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_123336/benchmark_results.json`
- Timeout detected: `true`.
- Timeout run count: `1/2`.
- Baseline elapsed / timeout elapsed: `45.491s / 0s`.
- Slow run elapsed / timeout elapsed: `374.308s / 330.132245s`.
- Slow run timeout ratio: `0.88198`.
- Timeout labels: `STT1=1`, `Fast-STT2=1`; word-precision timeout-like collect count `1`.
- Slow run final invalid/non-monotonic/overlap stayed `0/0/0`, global max active stayed `1`, and quality/text/timing stayed `93.955/94.867/0.5536s`.
- Production change allowed: `false`.
- Default cache promotion allowed: `false`.

### Jammini

- Route probe: `.agents/sentinel/handoffs/20260628-124750-watchdog-handoff-probe.md`
- Scout: `.agents/sentinel/handoffs/20260628-125000-stt-worker-timeout-scout.md`
- Dex classification: accept the scout's diagnostic-only direction. This slice implements read-only artifact audit first; deeper worker process isolation or trace bundle instrumentation remains a separate next action.

### Verification

- `./venv/bin/python -m py_compile tools/audit_stt_worker_timeout.py tests/test_stt_worker_timeout_audit.py` -> pass.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_stt_worker_timeout_audit.py` -> `3 passed`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_stt_worker_timeout.py .codex_work/benchmarks/subtitle_pipeline_variants/20260628_113906/benchmark_results.json .codex_work/benchmarks/subtitle_pipeline_variants/20260628_123336/benchmark_results.json --output-dir output/manual_verification/latest/stt_worker_timeout_compare_20260628` -> pass, `timeout_detected=true`.

### Next Recommended Action

- If generation latency remains the next priority, inspect WhisperKit persistent worker lifecycle/process isolation before changing STT routing.
- Do not use this audit to downgrade models, skip STT2, skip word precision, relax quality gates, promote collect-cache defaults, change UI, or perform App Store work.

## Current Handoff - 2026-06-28 NLE Fixed Cut-Boundary Fixture Gate

### Scope

- Continued the source-app NLE cut-boundary accuracy workstream by adding an exact-frame fixture gate for target frames `2766` and `2677`.
- Modified `tools/verify_cut_boundary_source_fps_scout.py`.
- Added `tests/test_cut_boundary_fixture_2766_2677.py`.
- Updated `ACTION_ITEMS.md`, `NLE_Action.md`, `COMPLETED_ACTION_ITEMS.md`, `docs/VALIDATION.md`, and `test_result.md`.
- No FFmpeg/visual scorer thresholds, subtitle quality policy, STT/STT2 policy, UI layout, labels, colors, menus, popups, QML/GPU timeline surface, App Store packaging/signing/upload, DMG, or persisted NLE disk fields changed.

### Results

- Fixed fixture evidence: `output/manual_verification/latest/nle_fixed_cut_boundary_fixture_gate_20260628/source_fps_scout.md`
- Local fixture path: `/Users/u_mo_c/Library/Mobile Documents/com~apple~CloudDocs/AI_EDIT/내 프로젝트 (3).MP4`
- Pipe fps: `60000/1001`.
- Target frames: `2766`, `2677`.
- Fixture scout passed: `true`.
- Probe source: latest artifact `ffprobe`; fallback path `spotlight_fps_override` is covered when probe access times out.
- Frame extract status: `metadata_only`.
- Candidate detected: `false/false`.
- Frame preserved: `true/true`.
- This is metadata/frame-grid proof only. Do not present it as visual cut detection proof because this gate intentionally does not use visual frame extraction.
- NAS HeyDealer first-180s acceptance: `output/manual_verification/latest/nle_fixed_cut_boundary_fixture_gate_nas_heydealer_20260628/acceptance/reference_benchmark_acceptance.md`
- NAS result: accepted `true`, elapsed `374.308s`, raw/final/reference `55/57/89`, quality/text/timing `93.955/94.867/0.5536s`, final invalid/non-monotonic/overlap `0/0/0`, final last end/duration `180.0/180.0`, global max active `1`.
- NAS latency caveat: this run hit WhisperKit worker timeout/fallback for STT1 (`150s`) and STT2 (`150s`), and word precision timed out at `30s`; treat this as a separate STT runtime diagnostic, not as a cut-boundary regression.

### Jammini

- Route probe: `.agents/sentinel/handoffs/20260628-121751-watchdog-handoff-probe.md`
- Scout: `.agents/sentinel/handoffs/20260628-131900-nle-fixed-cut-boundary-fixture-proof.md`
- Dex classification: accept the bounded fixture-gate slice. Jammini recommended a mock/integration guard and explicitly deferred FFmpeg/OpenCV scene-threshold changes and QML/UI work.

### Verification

- `./venv/bin/python -m py_compile tools/verify_cut_boundary_source_fps_scout.py tests/test_cut_boundary_fixture_2766_2677.py` -> pass.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_cut_boundary_fixture_2766_2677.py` -> `2 passed, 1 skipped`.
- `AI_SUBTITLE_STUDIO_CUT_BOUNDARY_FIXTURE="/Users/u_mo_c/Library/Mobile Documents/com~apple~CloudDocs/AI_EDIT/내 프로젝트 (3).MP4" AI_SUBTITLE_STUDIO_CUT_BOUNDARY_EXPECT="2766,2677" AI_SUBTITLE_STUDIO_CUT_BOUNDARY_PIPE_MAX_FPS="60" QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_cut_boundary_fixture_2766_2677.py` -> `3 passed`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_cut_boundary_auto_scan_backend.py tests/test_subtitle_boundary_alignment.py tests/test_trace_logger.py` -> `65 passed`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/verify_cut_boundary_source_fps_scout.py "/Users/u_mo_c/Library/Mobile Documents/com~apple~CloudDocs/AI_EDIT/내 프로젝트 (3).MP4" --pairs 2765:2766,2676:2677 --pipe-max-fps 60 --fps-override 60000/1001 --allow-metadata-only --probe-timeout-sec 5 --output-dir output/manual_verification/latest/nle_fixed_cut_boundary_fixture_gate_20260628` -> pass.
- NAS preflight: `output/manual_verification/latest/nle_fixed_cut_boundary_fixture_gate_nas_heydealer_20260628/preflight/reference_fixture_availability.md` -> ready `true`, clipped reference rows `89`.
- NAS benchmark: `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_123336/benchmark_results.json`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/evaluate_reference_benchmark_acceptance.py .codex_work/benchmarks/subtitle_pipeline_variants/20260628_123336/benchmark_results.json --media-duration-sec 180.0 --output-dir output/manual_verification/latest/nle_fixed_cut_boundary_fixture_gate_nas_heydealer_20260628/acceptance` -> accepted `true`.

### Next Recommended Action

- Continue cut-boundary accuracy through real visual detection/scorer verification only after decoder access is reliable; keep the metadata-only fixture gate as a frame-grid/split-snap guard.
- Open a separate STT runtime worker timeout diagnostic if generation latency is the next owner priority.

## Current Handoff - 2026-06-28 NLE Confirmed Cut Decision Trace

### Scope

- Continued the source-app NLE cut-boundary/trace workstream by adding best-effort trace events for confirmed visual-cut split/snap/drop decisions.
- Modified `core/cut_boundary.py`, `tools/audit_trace_log_bundle.py`, and `tests/test_subtitle_boundary_alignment.py`.
- Updated `ACTION_ITEMS.md`, `NLE_Action.md`, and `COMPLETED_ACTION_ITEMS.md`.
- No FFmpeg scene threshold, cut-boundary detection threshold, subtitle quality policy, STT/STT2 policy, UI layout, labels, colors, menus, popups, QML/GPU timeline surface, App Store packaging/signing/upload, DMG, or persisted NLE disk fields changed.

### Results

- Trace evidence: `output/manual_verification/latest/nle_confirmed_cut_trace_audit_20260628/trace_log_bundle_audit.md`
- Trace audit passed: `true`.
- Confirmed cut trace ok: `true`.
- Confirmed cut event count: `2`.
- Event name: `confirmed_cut_split_snap`.
- Decision fields: `event_type=cut_boundary_decision`, `decision`, `provisional_frame`, `drop_reason`, source segment identity, start/end frame fields, `fps_num/fps_den`.
- NAS HeyDealer first-180s acceptance: `output/manual_verification/latest/nle_confirmed_cut_trace_nas_heydealer_20260628/acceptance/reference_benchmark_acceptance.md`
- NAS result: accepted `true`, raw/final/reference `58/56/89`, quality/text/timing `93.766/94.267/0.5808s`, final invalid/non-monotonic/overlap `0/0/0`, final last end/duration `180.0/180.0`, global max active `1`.

### Jammini

- Route probe: `.agents/sentinel/handoffs/20260628-120409-watchdog-handoff-probe.md`
- Scout: `.agents/sentinel/handoffs/20260628-120500-cut-boundary-trace-gap-scout.md`
- Dex classification: accept the instrumentation-only slice. The scout's requested `decision`, `provisional_frame`, and `drop_reason` fields were included; threshold tuning and QML/UI changes remain deferred.

### Verification

- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_subtitle_boundary_alignment.py tests/test_cut_boundary_auto_scan_backend.py tests/test_trace_logger.py` -> `65 passed`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_trace_log_bundle.py --output-dir output/manual_verification/latest/nle_confirmed_cut_trace_audit_20260628` -> pass, `confirmed_cut_trace_ok=true`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/benchmark_subtitle_pipeline_variants.py --suite modes --variants mode_high --media "/Volumes/photo/22_유튜브영상_개인/[20260209]헤이딜러광고/헤이딜러_최종.MP4" --reference-srt "/Volumes/photo/22_유튜브영상_개인/[20260209]헤이딜러광고/헤이딜러_최종.srt" --start-sec 0 --duration-sec 180 --keep-artifacts` -> `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_121251/benchmark_results.json`.
- `./venv/bin/python tools/evaluate_reference_benchmark_acceptance.py .codex_work/benchmarks/subtitle_pipeline_variants/20260628_121251/benchmark_results.json --media-duration-sec 180.0 --output-dir output/manual_verification/latest/nle_confirmed_cut_trace_nas_heydealer_20260628/acceptance` -> accepted `true`.

### Next Recommended Action

- Continue cut-boundary accuracy through scorer/source-fps fixture gates; keep preview thumbnail cache out of confirmed cut evidence.
- Do not promote STT collect-cache defaults, persisted NLE fields, QML/GPU defaults, packaging/signing/upload, or App Store submission actions without explicit owner approval.

## Current Handoff - 2026-06-28 NLE Preview Skimming Trace Events

### Scope

- Continued the source-app NLE preview/skimming plus trace-log workstream by adding best-effort preview cache trace events.
- Modified `ui/editor/video_player_surface.py`, `tools/audit_nle_preview_skimming_cache.py`, `tests/test_video_player_widget.py`, and `tests/test_nle_preview_skimming_cache_audit.py`.
- No UI layout, labels, colors, menus, popups, QML/GPU timeline surface, cut-boundary detection policy, STT/STT2 policy, App Store packaging/signing/upload, DMG, persisted NLE disk fields, or timeline interaction behavior changed.

### Results

- Evidence: `output/manual_verification/latest/nle_preview_skimming_trace_audit_20260628/nle_preview_skimming_cache_audit.md`
- Audit ready: `true`.
- Trace event contract: `true`.
- Events covered: `nle_preview_frame_cache_hit`, `nle_preview_frame_cache_miss`, `nle_preview_frame_cache_schedule`, `nle_preview_frame_cache_ready`.
- Trace transport: async `TraceLogger` queue, best-effort/no-op when unavailable.
- Provenance fields: `source=editor_preview_skimming`, `evidence_role=user_preview_only`, `cut_boundary_evidence=false`, `ui_thread_decode_allowed=false`.
- Exact fps fields: `fps_num/fps_den` preserved.
- Existing preview seek throttle remains present.

### Jammini

- Route probe: `.agents/sentinel/handoffs/20260628-115539-watchdog-handoff-probe.md`
- Scout: `.agents/sentinel/handoffs/20260628-115600-nle-preview-trace-event-scout.md`
- Dex classification: accept the trace-event slice. Keep the scout's high-frequency logging risk covered by the existing preview seek throttle and async TraceLogger queue.

### Verification

- `./venv/bin/python -m py_compile ui/editor/video_player_surface.py tools/audit_nle_preview_skimming_cache.py tests/test_video_player_widget.py tests/test_nle_preview_skimming_cache_audit.py` -> pass.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_video_player_widget.py -k "preview_frame_cache or paused_preview_seek or processing_thumbnail or nearest_preview_frame_trace"` -> `7 passed, 75 deselected`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_nle_preview_skimming_cache_audit.py tests/test_preview_frame_cache.py` -> `5 passed`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_runtime_memory_manager.py tests/test_trace_log_bundle_audit.py -k "preview_cache or trace_log_bundle"` -> `3 passed, 25 deselected`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_nle_preview_skimming_cache.py --output-dir output/manual_verification/latest/nle_preview_skimming_trace_audit_20260628` -> pass, `ready=true`.

### Next Recommended Action

- Keep preview/skimming trace events diagnostic only; do not put raw trace events into UDP status/ping responses.
- Continue cut-boundary accuracy work through the scorer/trace path, not preview thumbnail cache artifacts.

## Current Handoff - 2026-06-28 NLE Preview Skimming Cache Contract

### Scope

- Continued the source-app NLE preview/skimming workstream by adding preview frame-cache provenance manifests.
- Modified `core/runtime/preview_frame_cache.py`.
- Added `tools/audit_nle_preview_skimming_cache.py` and `tests/test_nle_preview_skimming_cache_audit.py`.
- Updated `tests/test_preview_frame_cache.py`.
- No UI layout, labels, colors, menus, popups, QML/GPU timeline surface, cut-boundary detection policy, STT/STT2 policy, App Store packaging/signing/upload, DMG, persisted NLE disk fields, or timeline interaction behavior changed.

### Results

- Evidence: `output/manual_verification/latest/nle_preview_skimming_cache_audit_20260628/nle_preview_skimming_cache_audit.md`
- Audit ready: `true`.
- Preview cache contract applied: `true`.
- Preview workspace isolated: `true`; cache dir uses `Preview/FrameThumbnails`, not `Diagnostics/Trace`.
- Manifest purpose: `editor_preview_skimming`.
- Manifest evidence role: `user_preview_only`.
- Manifest cut-boundary evidence: `false`.
- Manifest UI-thread decode allowed: `false`.
- Source-fps grid ok: `true` at `60000/1001` style fps.
- Video surface contract: nearest cached preview frame lookup happens before async worker scheduling, and unprimed preview seek does not call the legacy sync cached-thumbnail helper.

### Jammini

- Route probe: `.agents/sentinel/handoffs/20260628-114704-watchdog-handoff-probe.md`
- Scout: `.agents/sentinel/handoffs/20260628-114700-nle-preview-skimming-contract-scout.md`
- Dex classification: accept the non-blocking preview/skimming contract direction, but revise the scout wording that implied the Preview workspace lives under `Diagnostics/Trace`; the actual accepted path is `Preview/FrameThumbnails`.

### Verification

- `./venv/bin/python -m py_compile core/runtime/preview_frame_cache.py tools/audit_nle_preview_skimming_cache.py tests/test_preview_frame_cache.py tests/test_nle_preview_skimming_cache_audit.py` -> pass.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_preview_frame_cache.py tests/test_nle_preview_skimming_cache_audit.py` -> `5 passed`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_nle_preview_skimming_cache.py --output-dir output/manual_verification/latest/nle_preview_skimming_cache_audit_20260628` -> pass, `ready=true`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_video_player_widget.py -k "preview_frame_cache or paused_preview_seek or processing_thumbnail"` -> `5 passed, 75 deselected`.

### Next Recommended Action

- Continue NLE preview/skimming only through the existing Qt Widgets video preview surface unless the owner explicitly approves UI surface changes.
- Do not use preview frame-cache thumbnails as cut-boundary evidence; confirmed cut-boundary proof stays in the cut-boundary scorer/trace path.

## Current Handoff - 2026-06-28 NLE Runtime Operation Journal

### Scope

- Continued the source-app NLE editor-structure goal by recording a bounded runtime-only NLE operation journal inside `NLEProjectState`.
- Modified `core/project/nle_project_state.py` and `core/project/nle_dual_write.py`.
- Updated focused tests in `tests/test_project_nle_operations.py`, `tests/test_project_nle_dual_write.py`, and `tests/test_nle_operation_journal_audit.py`.
- No persisted NLE disk fields, runtime undo/redo UI behavior, per-pixel drag writes, QML/GPU timeline default surface, App Store packaging/signing/upload, DMG, STT/STT2 policy, or user-visible UI/UX behavior changed.

### Results

- NLE evidence: `output/manual_verification/latest/nle_runtime_operation_journal_20260628/nle_operation_journal_audit.md`
- NAS HeyDealer regression evidence: `output/manual_verification/latest/nle_runtime_operation_journal_nas_heydealer_20260628/acceptance/reference_benchmark_acceptance.md`
- Benchmark run: `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_113906/benchmark_results.json`
- Audit ready: `true`.
- Runtime NLE journal applied: `true`.
- Operation families covered: `11/11`.
- Runtime journal count: `11`.
- Storage clean count: `11`.
- NLE audit final invalid/non-monotonic/overlap `0/0/0`; global max-active `1`.
- NAS HeyDealer accepted: `true`; elapsed `45.491s`, raw/final/reference `58/56/89`, quality/text/timing `93.766/94.267/0.5808s`, final invalid/non-monotonic/overlap `0/0/0`, final last end/duration bound `180.0/180.0`, global max-active `1`, STT1/STT2/word selected `21/37/7`.

### Jammini

- Route probe: `.agents/sentinel/handoffs/20260628-113253-watchdog-handoff-probe.md`
- Scout: `.agents/sentinel/handoffs/20260628-113300-in-memory-nle-transaction-journal-scout.md`
- Dex classification: accept the in-memory diagnostic journal slice; keep persisted journal storage, runtime undo/redo UI behavior, per-pixel NLE drag writes, and QML/GPU timeline default changes blocked.

### Verification

- `./venv/bin/python -m py_compile core/project/nle_project_state.py core/project/nle_dual_write.py tools/audit_nle_operation_journal.py tests/test_project_nle_dual_write.py tests/test_project_nle_operations.py tests/test_nle_operation_journal_audit.py` -> pass.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_operations.py tests/test_project_nle_dual_write.py tests/test_nle_operation_journal_audit.py` -> `39 passed`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_operations.py tests/test_project_nle_dual_write.py tests/test_nle_operation_journal_audit.py tests/test_nle_adapter_consistency_audit.py tests/test_nle_persistence_cutover_audit.py` -> `47 passed`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_nle_operation_journal.py --output-dir output/manual_verification/latest/nle_runtime_operation_journal_20260628` -> pass.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/verify_reference_fixture_availability.py --media "/Volumes/photo/.../헤이딜러_최종.MP4" --reference-srt "/Volumes/photo/.../헤이딜러_최종.srt" --start-sec 0 --duration-sec 180 --output-dir output/manual_verification/latest/nle_runtime_operation_journal_nas_heydealer_20260628/preflight` -> pass.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/benchmark_subtitle_pipeline_variants.py --suite modes --variants mode_high --media "/Volumes/photo/.../헤이딜러_최종.MP4" --reference-srt "/Volumes/photo/.../헤이딜러_최종.srt" --start-sec 0 --duration-sec 180 --keep-artifacts` -> pass.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/evaluate_reference_benchmark_acceptance.py .codex_work/benchmarks/subtitle_pipeline_variants/20260628_113906/benchmark_results.json --output-dir output/manual_verification/latest/nle_runtime_operation_journal_nas_heydealer_20260628/acceptance` -> `accepted=true`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py tests/test_subtitle_live_editor_feed_facade.py tests/test_native_subtitle_segments.py tests/test_native_subtitle_stt_segments.py` -> `203 passed`.

### Next Recommended Action

- Continue NLE adoption through source-app runtime contracts only. Persisted NLE disk fields, persisted operation journals, runtime undo/redo UI changes, per-pixel NLE writes, and QML/GPU default changes remain blocked until explicit owner approval and compatibility proof exist.
- STT collect-cache default promotion remains explicit-owner-review only despite the NAS being reachable and the current regression passing.

## Current Handoff - 2026-06-28 NLE Operation Journal Contract Audit

### Scope

- Continued the source-app NLE editor-structure goal with a non-destructive NLE operation journal/undo contract audit.
- Added `tools/audit_nle_operation_journal.py` and `tests/test_nle_operation_journal_audit.py`.
- Added release commit provenance to the remaining NLE dual-write operation builders and their current UI call sites for `gap_generate`, `caption_merge`, `candidate_confirm`, `caption_delete`, `caption_resize`, and `gap_delete`.
- No persisted NLE disk fields, runtime undo/redo UI behavior, per-pixel drag writes, QML/GPU timeline default surface, App Store packaging/signing/upload, DMG, STT/STT2 policy, or user-visible UI/UX behavior changed.

### Results

- NLE evidence: `output/manual_verification/latest/nle_operation_journal_audit_20260628/nle_operation_journal_audit.md`
- NAS HeyDealer regression evidence: `output/manual_verification/latest/nle_operation_journal_nas_heydealer_20260628/acceptance/reference_benchmark_acceptance.md`
- Benchmark run: `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_112647/benchmark_results.json`
- Audit ready: `true`.
- Operation families covered: `11/11`.
- Release metadata count: `11`.
- Undo snapshot count: `11`.
- Storage clean count: `11`.
- NLE audit final invalid/non-monotonic/overlap `0/0/0`; global max-active `1`.
- NAS HeyDealer accepted: `true`; elapsed `45.846s`, raw/final/reference `58/56/89`, quality/text/timing `93.766/94.267/0.5808s`, final invalid/non-monotonic/overlap `0/0/0`, final last end/duration bound `180.0/180.0`, global max-active `1`, STT1/STT2/word selected `21/37/7`.

### Jammini

- Route probe: `.agents/sentinel/handoffs/20260628-111733-watchdog-handoff-probe.md`
- Scout: `.agents/sentinel/handoffs/20260628-111900-nle-operation-journal-undo-scout.md`
- Dex classification: accept the operation schema, undo snapshot, release metadata, final-overlap, and blocked-scope guidance; defer persisted journal storage, runtime undo/redo UI changes, per-pixel NLE writes, and QML/UI conversion.

### Verification

- `./venv/bin/python -m py_compile core/project/nle_dual_write.py ui/editor/ux/editor_timeline_video.py ui/editor/editor_segments_stt_selection_flow.py ui/editor/editor_segments_block_surgery.py tools/audit_nle_operation_journal.py tests/test_nle_operation_journal_audit.py` -> pass.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_nle_operation_journal_audit.py tests/test_project_nle_dual_write.py tests/test_project_nle_operations.py` -> `37 passed`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_nle_operation_journal.py --output-dir output/manual_verification/latest/nle_operation_journal_audit_20260628` -> pass.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/verify_reference_fixture_availability.py --media "/Volumes/photo/.../헤이딜러_최종.MP4" --reference-srt "/Volumes/photo/.../헤이딜러_최종.srt" --start-sec 0 --duration-sec 180 --output-dir output/manual_verification/latest/nle_operation_journal_nas_heydealer_20260628/preflight` -> pass.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/benchmark_subtitle_pipeline_variants.py --suite modes --variants mode_high --media "/Volumes/photo/.../헤이딜러_최종.MP4" --reference-srt "/Volumes/photo/.../헤이딜러_최종.srt" --start-sec 0 --duration-sec 180 --keep-artifacts` -> pass.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/evaluate_reference_benchmark_acceptance.py .codex_work/benchmarks/subtitle_pipeline_variants/20260628_112647/benchmark_results.json --output-dir output/manual_verification/latest/nle_operation_journal_nas_heydealer_20260628/acceptance` -> `accepted=true`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py tests/test_subtitle_live_editor_feed_facade.py tests/test_native_subtitle_segments.py tests/test_native_subtitle_stt_segments.py` -> `203 passed`.

### Next Recommended Action

- Keep persisted NLE disk fields, persisted operation journals, runtime undo/redo UI changes, per-pixel NLE writes, and QML/GPU default changes blocked until explicit owner approval and compatibility proof exist.
- The next safe NLE slice should start from `ACTION_ITEMS.md` migration status and avoid redoing completed owner-map, adapter/cache, or operation-journal audits unless new mutation sources are added.

## Current Handoff - 2026-06-28 NLE Adapter Cache Consistency Audit

### Scope

- Responded to the owner signal that NAS is back online by refreshing the current HeyDealer first-180s MP4/SRT preflight.
- Continued the source-app NLE editor-structure goal with a non-destructive NLE adapter/cache consistency audit: `tools/audit_nle_adapter_consistency.py`.
- Added focused tests: `tests/test_nle_adapter_consistency_audit.py`.
- No runtime editor behavior, UI/UX, STT/STT2, subtitle timing, save file format, persisted NLE disk fields, per-pixel NLE writes, packaging, signing, upload, notarization, App Store Connect, or DMG behavior changed.

### Results

- NLE evidence: `output/manual_verification/latest/nle_adapter_consistency_audit_20260628/nle_adapter_consistency_audit.md`
- NAS preflight: `output/manual_verification/latest/heydealer_nas_preflight_current_20260628/reference_fixture_availability.md`
- Audit ready: `true`.
- Runtime change applied: `false`.
- Repeated save/reopen cycles: `6/6`.
- Runtime state schema: `ai_subtitle_studio.nle_project_state.v1`; runtime caption count `4`.
- All cycles kept storage clean, row signature stable, runtime marker visible before cache clear, runtime marker absent after cache clear/reopen, final invalid/non-monotonic/overlap `0/0/0`, and global max-active `1`.
- LRU cache owner: `core.project.project_io._PROJECT_FILE_CACHE`; max entries `4`, paths written `6`, cache entry count `4`.
- NAS current preflight is ready: media exists `true`, reference SRT exists `true`, clipped reference rows `89`. This is availability evidence only and does not approve collect-cache default promotion.

### Jammini

- Route probe: `.agents/sentinel/handoffs/20260628-110737-watchdog-handoff-probe.md`
- Scout: `.agents/sentinel/handoffs/20260628-110800-nle-adapter-cache-consistency-scout.md`
- Dex classification: accept with a narrower proof surface. The scout's GC-release concern was not converted into a brittle hard gate; this slice proves LRU bound, cache identity, cache-clear rehydration, storage stripping, and projection stability instead.

### Verification

- `./venv/bin/python -m py_compile tools/audit_nle_adapter_consistency.py tests/test_nle_adapter_consistency_audit.py` -> pass.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_nle_adapter_consistency_audit.py` -> `3 passed`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_nle_adapter_consistency.py --output-dir output/manual_verification/latest/nle_adapter_consistency_audit_20260628` -> pass.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/verify_reference_fixture_availability.py --media "/Volumes/photo/.../헤이딜러_최종.MP4" --reference-srt "/Volumes/photo/.../헤이딜러_최종.srt" --start-sec 0 --duration-sec 180 --output-dir output/manual_verification/latest/heydealer_nas_preflight_current_20260628` -> pass.

### Next Recommended Action

- Keep persisted NLE disk fields, per-pixel NLE writes, and UI/QML default changes blocked until explicit owner approval and compatibility proof exist.
- STT collect-cache default promotion remains explicit-owner-review only. The NAS is reachable now, but the strict real-media write/hit proof remains owner-review gated in `ACTION_ITEMS.md`.

## Current Handoff - 2026-06-28 NLE Runtime Owner Map Audit

### Scope

- Continued the owner goal to push AI Subtitle Studio toward a source-app NLE editor structure while preserving Taption editing contracts.
- Added a non-destructive NLE runtime owner-map audit: `tools/audit_nle_runtime_owner_map.py`.
- Added focused tests: `tests/test_nle_runtime_owner_map_audit.py`.
- No runtime editor behavior, STT/STT2, subtitle timing, UI/UX labels/layout/colors/shortcuts/menus/popups, save file format, persisted NLE disk fields, per-pixel drag writes, packaging, signing, upload, notarization, App Store Connect, or DMG behavior changed.

### Results

- Evidence: `output/manual_verification/latest/nle_runtime_owner_map_audit_20260628/nle_runtime_owner_map_audit.md`
- Runtime owner map ready: `true`.
- Runtime change applied: `false`.
- Covered owners: `23/23`.
- Operation families covered: `candidate_confirm`, `caption_delete`, `caption_merge`, `caption_move`, `caption_range_replace`, `caption_resize`, `caption_split`, `caption_text_edit`, `gap_delete`, `gap_generate`, `marker_edit`.
- Blocked candidates remain explicit: persisted NLE project fields, per-pixel NLE writes, and QML/GPU timeline default surface changes.
- Next adoption gate for any new mutation source: fresh owner-map, Taption release-commit contract, no per-pixel NLE write, final invalid/non-monotonic/overlap `0`, global max-active `<=1`, and save/reopen identity preservation.

### Jammini

- Route probe: `.agents/sentinel/handoffs/20260628-105700-watchdog-handoff-probe.md`
- Scout: `.agents/sentinel/handoffs/20260628-105800-nle-next-safe-slice-scout.md`
- Dex classification: partially accept as next-candidate guidance. Jammini recommended an adapter/cache consistency audit; Dex completed the stronger prerequisite owner-map audit first and left adapter/cache consistency as a possible future non-destructive slice, not as completed work.

### Verification

- `./venv/bin/python -m py_compile tools/audit_nle_runtime_owner_map.py tests/test_nle_runtime_owner_map_audit.py` -> pass.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_nle_runtime_owner_map_audit.py` -> `3 passed`.
- `./venv/bin/python tools/audit_nle_runtime_owner_map.py --output-dir output/manual_verification/latest/nle_runtime_owner_map_audit_20260628` -> pass.

### Next Recommended Action

- Keep persisted NLE disk fields and per-pixel drag writes blocked until explicit owner approval and compatibility proof exist.
- A safe follow-up candidate is a read-only NLE adapter/cache consistency audit, but it should first identify concrete cache/runtime owners in current code instead of assuming an adapter leak.

## Current Handoff - 2026-06-28 STT Cache Tail-Bound Fix And Real-Media Backfill Acceptance

### Scope

- Repaired the representative HeyDealer first-180s strict acceptance failure from the prior cache backfill attempt.
- Change is limited to benchmark/evaluation projection in `tools/benchmark_subtitle_pipeline_variants.py`: final hypothesis rows are projected into the requested benchmark window after cut-boundary alignment, matching the already clipped reference window.
- Did not change runtime STT/STT2 policy, word precision policy, cache defaults, subtitle engine timing, editor UI/UX, save/load, render/export, packaging, signing, upload, notarization, App Store Connect, or DMG behavior.

### Results

- Evidence root: `output/manual_verification/latest/stt_cache_tail_bound_fix_20260628_1048/`
- Preflight: `output/manual_verification/latest/stt_cache_tail_bound_fix_20260628_1048/preflight/reference_fixture_availability.md`; ready `true`, reference SRT rows `615`, clipped rows `89`.
- Cache-write run: `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_105017/benchmark_results.json`
- Cache-hit run: `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_105119/benchmark_results.json`
- Strict acceptance: write and hit both `accepted=true`.
- Write/hit elapsed: `46.073s -> 1.266s`.
- Raw/final/reference: `58/56/89`; quality/text/timing `93.766/94.267/0.5808s`.
- Final invalid/non-monotonic/overlap `0/0/0`; final last end/duration bound `180.0/180.0`; short/long counts `0/0`; global max active `1`.
- Benchmark projection diagnostics: input/output `56/56`, clamped tail-end count `1`, dropped before/after/invalid `0/0/0`.
- Hit replay proved STT1/STT2/word collect cache hits with provider calls `false`.
- Readiness refresh: `output/manual_verification/latest/stt_cache_tail_bound_fix_20260628_1048/readiness_refresh/stt_cache_backfill_readiness.md`; all collect-cache families now report `real_backfill_present_owner_review_required`, while `production_default_recommendation=hold_default_off`.

### Jammini

- Route probe: `.agents/sentinel/handoffs/20260628-104613-watchdog-handoff-probe.md`
- Scout: `.agents/sentinel/handoffs/20260628-104600-nle-benchmark-tail-bound-projection-scout.md`
- Dex classification: accept. The scout's edge-risk warning was checked by strict acceptance: no short segments, long segments, invalid durations, non-monotonic rows, overlap, or global multi-active result appeared after the clamp.

### Verification

- `./venv/bin/python -m py_compile tools/benchmark_subtitle_pipeline_variants.py tests/test_benchmark_mode_profiles.py` -> pass.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_benchmark_mode_profiles.py -k "benchmark_window or native_segments_summary_includes_strict_duration_bounds or stage_wall_clock_summary"` -> `3 passed, 33 deselected`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_reference_benchmark_acceptance.py tests/test_stt_cache_backfill_readiness.py` -> `10 passed`.
- HeyDealer write benchmark with STT1/STT2/word/macro caches enabled -> run `20260628_105017`, pass.
- Same benchmark command with the same cache paths -> hit run `20260628_105119`, pass.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/evaluate_reference_benchmark_acceptance.py .codex_work/benchmarks/subtitle_pipeline_variants/20260628_105017/benchmark_results.json --output-dir output/manual_verification/latest/stt_cache_tail_bound_fix_20260628_1048/acceptance_write` -> `accepted=true`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/evaluate_reference_benchmark_acceptance.py .codex_work/benchmarks/subtitle_pipeline_variants/20260628_105119/benchmark_results.json --output-dir output/manual_verification/latest/stt_cache_tail_bound_fix_20260628_1048/acceptance_hit` -> `accepted=true`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_stt_cache_backfill_readiness.py --glob '.codex_work/benchmarks/subtitle_pipeline_variants/*/benchmark_results.json' --output-dir output/manual_verification/latest/stt_cache_tail_bound_fix_20260628_1048/readiness_refresh --representative-media "/Volumes/photo/.../헤이딜러_최종.MP4" --representative-reference-srt "/Volumes/photo/.../헤이딜러_최종.srt"` -> pass.

### Next Recommended Action

- Do not enable `stt_primary_collect_cache_enabled` or `stt_recheck_collect_cache_enabled` by default automatically.
- Next safe action is owner review of the accepted real-media write/hit evidence and readiness report; default promotion remains explicit-owner-approval only.

## Current Handoff - 2026-06-28 STT Cache Real-Media Backfill Attempt

### Scope

- Responded to the owner signal that NAS is back online.
- Mounted/observed `/Volumes/photo` as the SMB share and verified the exact HeyDealer MP4/SRT pair.
- Ran the representative HeyDealer first-180s STT collect-cache write plus cache-hit replay using the same STT1, STT2/word, and macro response cache paths.
- Did not change runtime behavior, cache defaults, STT/STT2 policy, word precision policy, subtitle timing algorithms, UI/UX, save/load, render/export, packaging, signing, upload, notarization, App Store Connect, or DMG behavior.

### Results

- Evidence root: `output/manual_verification/latest/stt_cache_real_media_backfill_20260628_1035/`
- Preflight: `output/manual_verification/latest/stt_cache_real_media_backfill_20260628_1035/preflight/reference_fixture_availability.md`; ready `true`, reference SRT rows `615`, clipped rows `89`.
- Cache-write run: `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_103556/benchmark_results.json`
- Cache-hit run: `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_103745/benchmark_results.json`
- Write/hit elapsed: `62.492s -> 1.186s`.
- Raw/final/reference: `58/56/89` on both runs.
- Quality/text/timing: `93.745/94.267/0.583s` on both runs.
- Final invalid/non-monotonic/overlap: `0/0/0`; final short/long counts `0/0`; global max active `1`; global stable `true`.
- Hit replay proved STT1/STT2/word collect cache hits with provider calls `false`; collect elapsed values were `0.0/0.0/0.0s`.
- High-context keep-cache also replayed on the hit run: hit count `2`, LLM calls `0`.

### Hold Reason

- Strict write acceptance: `output/manual_verification/latest/stt_cache_real_media_backfill_20260628_1035/acceptance_write/reference_benchmark_acceptance.md`
- Strict hit acceptance: `output/manual_verification/latest/stt_cache_real_media_backfill_20260628_1035/acceptance_hit/reference_benchmark_acceptance.md`
- Both strict acceptance reports are `accepted=false` with reason `final_last_end_beyond_duration_bound`.
- Final last end is `180.256s`; duration bound is `180.0s`; max final-end slack is `0.25s`. The failure margin is `0.006s`.
- Readiness refresh: `output/manual_verification/latest/stt_cache_real_media_backfill_20260628_1035/readiness_refresh/stt_cache_backfill_readiness.md`; result stays `production_default_recommendation=hold_default_off`, strict real-media write/hit counts `0/0`, because failed strict acceptance cannot count as promotion evidence.

### Jammini

- Route probe: `.agents/sentinel/handoffs/20260628-103424-watchdog-handoff-probe.md`
- Checklist scout: `.agents/sentinel/handoffs/20260628-103500-stt-cache-real-media-backfill-checklist.md`
- Dex classification: accept the checklist. The run satisfies cache-efficiency and final overlap/global-canvas gates but does not satisfy strict acceptance due to the first-180s tail-bound failure.

### Verification

- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/verify_reference_fixture_availability.py --media "/Volumes/photo/.../헤이딜러_최종.MP4" --reference-srt "/Volumes/photo/.../헤이딜러_최종.srt" --start-sec 0 --duration-sec 180 --output-dir output/manual_verification/latest/stt_cache_real_media_backfill_20260628_1035/preflight` -> pass.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/benchmark_subtitle_pipeline_variants.py --suite modes --variants mode_high ... --setting stt_primary_collect_cache_enabled=true --setting stt_recheck_collect_cache_enabled=true --setting subtitle_llm_macro_response_cache_enabled=true` -> write run `20260628_103556`, pass.
- Same benchmark command with same cache paths -> hit run `20260628_103745`, pass.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/evaluate_reference_benchmark_acceptance.py .codex_work/benchmarks/subtitle_pipeline_variants/20260628_103556/benchmark_results.json --output-dir output/manual_verification/latest/stt_cache_real_media_backfill_20260628_1035/acceptance_write` -> expected exit `2`, `accepted=false`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/evaluate_reference_benchmark_acceptance.py .codex_work/benchmarks/subtitle_pipeline_variants/20260628_103745/benchmark_results.json --output-dir output/manual_verification/latest/stt_cache_real_media_backfill_20260628_1035/acceptance_hit` -> expected exit `2`, `accepted=false`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_stt_cache_backfill_readiness.py --glob '.codex_work/benchmarks/subtitle_pipeline_variants/*/benchmark_results.json' --output-dir output/manual_verification/latest/stt_cache_real_media_backfill_20260628_1035/readiness_refresh --representative-media "/Volumes/photo/.../헤이딜러_최종.MP4" --representative-reference-srt "/Volumes/photo/.../헤이딜러_최종.srt"` -> pass, still hold.

### Next Recommended Action

- Do not enable `stt_primary_collect_cache_enabled` or `stt_recheck_collect_cache_enabled` by default yet.
- Next safe implementation target is the strict first-180s tail-bound failure: either repair the benchmark/source-app final projection so final subtitles do not exceed the requested window, then rerun write/hit acceptance, or keep this as owner-review-only evidence with the tail-bound exception explicitly approved.

## Current Handoff - 2026-06-28 Active Queue Gate Refresh

### Scope

- Refreshed the two remaining active `ACTION_ITEMS.md` gates without changing runtime behavior.
- Confirmed completed action-item history remains separated in `COMPLETED_ACTION_ITEMS.md`; `ACTION_ITEMS.md` keeps only active gates, owner blockers, and archive pointers.
- No code, UI/UX, subtitle generation, STT/STT2, word precision, save/load, render/export, packaging, signing, upload, notarization, App Store Connect, or DMG behavior changed.

### Results

- STT collect-cache refresh: `output/manual_verification/latest/stt_cache_backfill_gate_refresh_20260628/stt_cache_backfill_readiness.md`
- STT result: `production_default_recommendation=hold_default_off`, `current_real_inputs_available=false`, defaults remain `stt_primary_collect_cache_enabled=false` and `stt_recheck_collect_cache_enabled=false`.
- STT blockers: all STT1, STT2/word, and combined collect-cache families still require representative real-media cache-write plus cache-hit replay on the NAS HeyDealer first-180s fixture.
- App Store refresh: `output/manual_verification/latest/app_store_readiness_gate_refresh_20260628/app_store_readiness_audit.md`
- App Store result: `status=blocked`, `local_packaging_ready=true`, `app_store_submission_ready=false`, blocker count `14`, submission content status `blocked`, pending owner-input items `8/8`, Apple Distribution and installer signing identities not configured.
- No parked candidates remain open.

### Jammini

- Route probe: `.agents/sentinel/handoffs/20260628-093036-watchdog-handoff-probe.md`
- Blocker scout: `.agents/sentinel/handoffs/20260628-093300-active-queue-blocker-refresh.md`
- Dex classification: accept the `block` verdict. There is no safe remaining implementation slice until the NAS HeyDealer media/reference SRT returns or the owner explicitly approves App Store packaging/signing/upload/metadata steps.

### Verification

- `find /Volumes -maxdepth 5 \( -iname '*헤이딜러*' -o -iname '*heydealer*' \) 2>/dev/null | head -40` -> no visible representative NAS HeyDealer media.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_stt_cache_backfill_readiness.py --glob '.codex_work/benchmarks/subtitle_pipeline_variants/*/benchmark_results.json' --output-dir output/manual_verification/latest/stt_cache_backfill_gate_refresh_20260628 --representative-media '/Volumes/photo/헤이딜러_최종.MP4' --representative-reference-srt '/Volumes/photo/헤이딜러_최종.srt'` -> pass, blocked/hold report written.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_app_store_readiness.py --output-dir output/manual_verification/latest/app_store_readiness_gate_refresh_20260628` -> pass, blocked readiness report written.

### Next Recommended Action

- If the NAS is turned back on, run the STT cache backfill report's preflight, cache-write, cache-hit, write acceptance, hit acceptance, and readiness-refresh sequence before considering collect-cache default promotion.
- If the owner wants App Store progress, first provide/approve privacy policy URL, App Privacy answers, export compliance answers, screenshots, support URL, app review notes, age rating answers, and release notes, or explicitly approve packaging/signing/validation steps with the required Apple signing identities.

## Current Handoff - 2026-06-28 Playhead Dirty-Rect Candidate Gate

### Scope

- Executed the parked `Playhead-only dirty-rect repaint` candidate as a fresh quality gate, not as a runtime optimization.
- Created rollback branch `codex/rollback-playhead-dirty-rect-gate-20260628-0925` before editing.
- Strengthened `tools/audit_editor_rendering_ownership.py` so it reports `playhead_dirty_rect_candidate` status and can write JSON/Markdown evidence with `--output-dir`.
- Current result is `hold_full_canvas_repaint`; runtime dirty-rect repaint remains disallowed until fresh Macau visual smoke proves no residue and the owner approves a default change.
- Removed the parked candidate from `ACTION_ITEMS.md`, archived it in `COMPLETED_ACTION_ITEMS.md`, and recorded the rejected runtime-optimization direction in `waste_action_item.md`.
- No runtime repaint behavior, UI/UX, timeline drawing, NLE state, subtitle generation, STT/STT2, App Store readiness, packaging, signing, upload, notarization, or DMG behavior changed.

### Jammini

- Route probe: `.agents/sentinel/handoffs/20260628-092519-watchdog-handoff-probe.md`
- Scout: `.agents/sentinel/handoffs/20260628-092600-nle-playhead-dirty-rect-scout.md`
- Dex classification: accept the Defer/Reject recommendation for runtime dirty-rect optimization, and keep only the non-destructive audit/evidence strengthening.

### Verification

- `./venv/bin/python -m py_compile tools/audit_editor_rendering_ownership.py tests/test_editor_rendering_ownership_audit.py` -> pass.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_editor_rendering_ownership_audit.py tests/test_timeline_playhead_fit.py -k "single_owner_playhead_invalidation or playhead_canvas_repaints_full_2d_owner or shadow_playhead_repaints_canvas_full_2d_owner"` -> `3 passed, 194 deselected`.
- `./venv/bin/python tools/audit_editor_rendering_ownership.py --output-dir output/manual_verification/latest/playhead_dirty_rect_gate_20260628` -> pass.

### Results

- Evidence artifact: `output/manual_verification/latest/playhead_dirty_rect_gate_20260628/editor_rendering_ownership_audit.md`
- Audit `ok=true`, issue count `0`.
- `playhead_dirty_rect_candidate.status=hold_full_canvas_repaint`.
- `runtime_change_allowed=false`.
- `current_backend=qwidget-2d-full-canvas-repaint`.
- No parked candidates remain open in `ACTION_ITEMS.md`.

### Next Recommended Action

- Continue from `ACTION_ITEMS.md` active queue. STT cache default promotion still waits for NAS HeyDealer real-media write/hit backfill, and App Store packaging/signing/upload remains owner-gated.

## Previous Handoff - 2026-06-28 App Command/Snapshot Acknowledgement Cleanup

### Scope

- Executed the parked `App command/snapshot acknowledgement cleanup` candidate as an artifact-trust slice only.
- Created rollback branch `codex/rollback-app-command-ack-20260628-0918` before editing.
- Added direct CLI result annotations in `tools/appctl.py`:
  - `capture-snapshot` / `snapshot` now reports `data.artifact` and `data.artifact_ready` after a queued/saved response.
  - `guided-subtitle-run` `command_timeout` now keeps `ok=false` but attaches `post_timeout_status` and `post_timeout_evidence` from safe follow-up `guided-subtitle-status`.
- Updated `ACTION_ITEMS.md`, `COMPLETED_ACTION_ITEMS.md`, and `test_result.md`.
- No runtime bridge handler behavior, UI/UX, subtitle generation, STT/STT2, NLE state, App Store readiness, packaging, signing, upload, notarization, or DMG behavior changed.

### Jammini

- Route probe: `.agents/sentinel/handoffs/20260628-091814-watchdog-handoff-probe.md`
- Scout: `.agents/sentinel/handoffs/20260628-091900-app-command-ack-cleanup-scout.md`
- Dex classification: accept the artifact-trust goal, but narrow implementation to `tools/appctl.py` reporting because `tools/remote_verify.py` already verifies saved capture artifacts and runtime handler behavior did not need to change.

### Verification

- `./venv/bin/python -m py_compile tools/appctl.py tests/test_appctl.py` -> pass.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_appctl.py tests/test_automation_command_client.py tests/test_remote_verify_actions.py` -> `14 passed`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_app_command_bridge.py -k "guided_subtitle_run or capture_snapshot or command_timeout"` -> `7 passed, 71 deselected`.

### Results

- Direct `appctl capture-snapshot` output can now distinguish queued acknowledgement from actual PNG artifact readiness.
- Direct `appctl guided-subtitle-run` timeout output can now carry follow-up status evidence without turning the timeout into a false success.
- The parked candidate was removed from `ACTION_ITEMS.md` and archived in `COMPLETED_ACTION_ITEMS.md`.

### Next Recommended Action

- Continue from `ACTION_ITEMS.md` active queue. STT cache default promotion still waits for NAS HeyDealer real-media write/hit backfill, and App Store packaging/signing/upload remains owner-gated.

## Previous Handoff - 2026-06-28 Completed Action Item Archive Separation

### Scope

- Honored the owner request to keep completed action items in a separate file.
- Confirmed `ACTION_ITEMS.md` already contains only active items, open gates, rollback rules, and archive pointers.
- Removed the completed-workstream list from `NLE_Action.md` and moved that baseline into `COMPLETED_ACTION_ITEMS.md`.
- No runtime behavior, UI/UX, subtitle generation, STT/STT2, word precision, save/load, render/export, packaging, signing, upload, notarization, App Store Connect state, or DMG behavior changed.

### Verification

- `rg -n "(?i)(^## |^### |status:|완료|completed|complete|done|archiv|moved out|removed from ACTION_ITEMS|no longer active|closed)" ACTION_ITEMS.md NLE_Action.md COMPLETED_ACTION_ITEMS.md` -> reviewed.
- `git diff --check -- ACTION_ITEMS.md COMPLETED_ACTION_ITEMS.md NLE_Action.md docs/HANDOFF.md test_result.md` -> pass.

### Results

- `COMPLETED_ACTION_ITEMS.md#nle-action-completed-workstream-baseline` now owns the previous `NLE_Action.md` completed baseline.
- `NLE_Action.md` now keeps only open NLE status plus the completed archive pointer.
- `ACTION_ITEMS.md` required no content move; completed summaries were already separated there.

### Next Recommended Action

- Continue from `ACTION_ITEMS.md` active queue. STT cache default promotion still waits for NAS HeyDealer real-media write/hit backfill, and App Store packaging/signing/upload remains owner-gated.

## Previous Handoff - 2026-06-28 App Store Submission Contents Audit

### Scope

- Continued active `ACTION_ITEMS.md` item 2 without running packaging, signing, upload, notarization, release, or DMG commands.
- Extended `tools/audit_app_store_readiness.py` so non-code App Store submission contents are itemized with `status`, `draft`, `owner_decision_required`, and `acceptance_gate`.
- The audit now tracks privacy policy URL, App Privacy answers, export compliance, screenshots, support URL, app review notes, age rating, and release notes as structured owner-input blockers.
- Updated `docs/APP_STORE_SUBMISSION_READINESS.md`, `ACTION_ITEMS.md`, `COMPLETED_ACTION_ITEMS.md`, and `test_result.md` with the latest evidence.
- No runtime behavior, UI/UX, subtitle generation, STT/STT2, word precision, save/load, render/export, packaging, signing, upload, notarization, App Store Connect state, or DMG behavior changed.

### Verification

- `./venv/bin/python -m py_compile tools/audit_app_store_readiness.py tests/test_app_store_readiness_audit.py` -> pass.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_app_store_readiness_audit.py` -> `5 passed`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_app_store_readiness.py --output-dir output/manual_verification/latest/app_store_submission_contents_audit_20260628` -> pass.

### Results

- Audit artifact: `output/manual_verification/latest/app_store_submission_contents_audit_20260628/app_store_readiness_audit.md`
- `local_packaging_ready=true`.
- `app_store_submission_ready=false`, `status=blocked`, blocker count `14`.
- `submission_content_audit.status=blocked`.
- Pending owner-input items `8/8`; drafted item count `8`.
- Mac App Store `.pkg` remains the primary submission target; Developer ID beta `.dmg` remains `opt_in_hold` and not submission evidence.
- Jammini review: `.agents/sentinel/handoffs/20260628-090900-app-store-submission-contents-audit-review.md`

### Next Recommended Action

- Collect owner-approved privacy policy URL, App Privacy answers, export compliance answers, screenshots, support URL, app review notes, age rating answers, and release notes before clearing the non-code submission blocker.
- Do not run packaging/signing/upload/notarization/DMG steps without explicit owner approval.

## Previous Handoff - 2026-06-28 STT Cache Backfill Command Plan Gate

### Scope

- Continued active `ACTION_ITEMS.md` item 1 while NAS is unavailable, staying inside the allowed analysis/measurement-only scope.
- Tightened `tools/audit_stt_cache_backfill_readiness.py` so representative real-media collect-cache promotion evidence requires both a strict cache-write run and a strict cache-hit replay before owner review.
- Added `next_run_plan` to the readiness JSON/Markdown: preflight, cache-write, cache-hit, write acceptance, hit acceptance, and readiness-refresh commands for the NAS HeyDealer first-180s gate.
- Added forbidden-substitute and owner-review gate sections to prevent X5/project-reference, generated/local fixture, fallback cached-audio, preflight-only, write-only, or profiler-only evidence from being misused as production speed proof.
- No runtime behavior, STT/STT2 policy, word precision policy, cache default, subtitle timing, save/load, render/export, packaging, App Store behavior, or UI changed.

### Verification

- `./venv/bin/python -m py_compile tools/audit_stt_cache_backfill_readiness.py tests/test_stt_cache_backfill_readiness.py` -> pass.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_stt_cache_backfill_readiness.py tests/test_stage_variance_summary.py` -> `8 passed`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_stt_cache_backfill_readiness.py --glob '.codex_work/benchmarks/subtitle_pipeline_variants/*/benchmark_results.json' --output-dir output/manual_verification/latest/stt_cache_backfill_command_plan_20260628 --representative-media '/Volumes/photo/.../헤이딜러_최종.MP4' --representative-reference-srt '/Volumes/photo/.../헤이딜러_최종.srt'` -> pass.

### Results

- Audit artifact: `output/manual_verification/latest/stt_cache_backfill_command_plan_20260628/stt_cache_backfill_readiness.md`
- `production_default_recommendation=hold_default_off`.
- `current_real_inputs_available=false`.
- Defaults remain `stt_primary_collect_cache_enabled=false`, `stt_recheck_collect_cache_enabled=false`.
- Strict real-media cache-write/cache-hit counts are `0/0` for STT1, STT2/word, and combined collect-cache families.
- Family blocker set now includes `representative_real_media_currently_unavailable`, `missing_strict_real_media_cache_write_run`, and `missing_strict_real_media_cache_hit_replay`.
- Jammini route probe: `.agents/sentinel/handoffs/20260628-085829-watchdog-handoff-probe.md`
- Jammini review: `.agents/sentinel/handoffs/20260628-085900-stt-cache-backfill-readiness-plan-review.md`

### Next Recommended Action

- When the NAS HeyDealer MP4 and matching SRT are mounted, run the audit report's `preflight`, `cache_write`, `cache_hit`, `accept_write`, `accept_hit`, and `readiness_refresh` commands in order.
- Do not use generated/local fixtures, X5/project-reference fixtures, fallback cached audio, preflight-only proof, real-media cache-write without matching hit replay, or profiler elapsed to approve collect-cache defaults.

## Previous Handoff - 2026-06-28 Trace Log Bundle Contract And Retention

### Scope

- Continued the owner goal to move AI Subtitle Studio toward a video-editor/NLE structure by hardening the diagnostic Trace Log Bundle from `NLE_Action.md`.
- Added `tools/audit_trace_log_bundle.py` so the trace contract can be verified as an artifact, not only inferred from focused tests.
- Added trace run-directory retention in `core/runtime/temp_workspace.py` and invoked it from `core/runtime/trace_logger.py`; a new trace run keeps the newest 19 existing run directories, then creates itself so the post-start count stays at most 20.
- No UI/UX, subtitle generation, STT/STT2, word precision, `.aissproj` save format, packaging, or App Store behavior changed.

### Verification

- `./venv/bin/python -m py_compile core/runtime/temp_workspace.py core/runtime/trace_logger.py tools/audit_trace_log_bundle.py tests/test_trace_logger.py tests/test_trace_log_bundle_audit.py` -> pass.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_trace_logger.py tests/test_trace_log_bundle_audit.py` -> `16 passed`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_trace_log_bundle.py --output-dir output/manual_verification/latest/trace_log_bundle_retention_audit_20260628` -> pass.

### Results

- Audit artifact: `output/manual_verification/latest/trace_log_bundle_retention_audit_20260628/trace_log_bundle_audit.md`
- `passed=true`, required dirs `true`, manifest missing fields `none`, event missing fields `none`.
- Exact-frame precision: `frame_precision_ok=true` with `fps_num=60000`, `fps_den=1001` in the frame-sensitive event path.
- Bounded media fingerprint: `true`; media fingerprint keys exclude full-file hashes.
- Package complete: `true`; package files include latest JSONL, run manifest, run events, and package manifest.
- Retention: `retention_ok=true`, retained run count `20/20`, retention removed count `5`.
- Jammini route probe: `.agents/sentinel/handoffs/20260628-084655-watchdog-handoff-probe.md`
- Jammini scout: `.agents/sentinel/handoffs/20260628-084700-trace-retention-next-gap-scout.md`

### Next Recommended Action

- Continue active `ACTION_ITEMS.md` item 1 only when NAS real-media backfill is available, or keep it analysis-only while NAS is unavailable.
- For NLE, persisted `nle`, `nle_snapshot`, and `_nle_project_state` fields remain blocked until a separate owner-approved compatibility gate exists.

## Previous Handoff - 2026-06-28 NLE Marker Edit Persistence Gate

### Scope

- Continued the owner goal to move AI Subtitle Studio toward a video-editor/NLE structure while preserving the current source-app and legacy `.aissproj` compatibility.
- Strengthened `tools/audit_nle_persistence_cutover.py` so provisional cut-boundary `marker_edit` is included in the save/reopen operation roundtrip matrix.
- The audit now verifies all 11 current NLE dual-write operation families, including marker preservation after legacy project roundtrip, while keeping persisted NLE project fields blocked.
- No UI/UX, subtitle generation, STT/STT2, word precision, save file format, packaging, or App Store behavior changed.

### Verification

- `./venv/bin/python -m py_compile tools/audit_nle_persistence_cutover.py` -> pass.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_nle_persistence_cutover_audit.py` -> `5 passed`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_dual_write.py tests/test_project_nle_persistence_guard.py tests/test_project_nle_render_export_parity.py tests/test_nle_persistence_cutover_audit.py` -> `41 passed`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_nle_persistence_cutover.py --output-dir output/manual_verification/latest/nle_marker_edit_persistence_gate_20260628` -> pass.

### Results

- Audit artifact: `output/manual_verification/latest/nle_marker_edit_persistence_gate_20260628/nle_persistence_cutover_audit.md`
- `prep_ready=true`, `persistence_cutover_ready=false`.
- Operation roundtrip families: `11`, all passed.
- `marker_edit` reopened with `reopened_markers_preserved=true`, projected marker count `1`, reopened marker count `1`.
- Render/export parity remains stable; final invalid/non-monotonic/overlap `0/0/0`, global max active `1`.
- Jammini route probe: `.agents/sentinel/handoffs/20260628-083545-watchdog-handoff-probe.md`
- Jammini scout: `.agents/sentinel/handoffs/20260628-083600-nle-next-safe-slice-scout.md`

### Next Recommended Action

- Keep persisted `nle`, `nle_snapshot`, and `_nle_project_state` fields blocked until a separate owner-approved compatibility gate exists.
- The Jammini scout recommended Trace Log Bundle diagnostics as a safe next slice; Dex deferred that candidate for a later turn because this turn closed the concrete NLE persistence audit gap.

## Previous Handoff - 2026-06-28 NLE Persistence Render/Export Gate

### Scope

- Continued the owner goal to move AI Subtitle Studio toward a video-editor/NLE structure while preserving the current source-app and legacy `.aissproj` compatibility.
- Strengthened `tools/audit_nle_persistence_cutover.py` so persistence cutover readiness now includes a render/export parity fixture and gate.
- The new audit fixture writes and reopens a roughcut/export project through legacy project I/O, then verifies the same NLE final projection across `source_subtitles`, `final_overlay`, `global_canvas`, `roughcut_sidecar`, and `exported_assets`.
- No UI/UX, subtitle generation, STT/STT2, word precision, save file format, packaging, or App Store behavior changed.
- Persisted NLE project fields remain blocked until a separate owner-approved disk-format compatibility gate exists.

### Verification

- `./venv/bin/python -m py_compile tools/audit_nle_persistence_cutover.py tests/test_nle_persistence_cutover_audit.py` -> pass.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_nle_persistence_cutover_audit.py tests/test_project_nle_render_export_parity.py` -> `7 passed`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_nle_persistence_cutover.py --output-dir output/manual_verification/latest/nle_persistence_render_export_gate_20260628` -> pass.

### Results

- Audit artifact: `output/manual_verification/latest/nle_persistence_render_export_gate_20260628/nle_persistence_cutover_audit.md`
- `prep_ready=true`, `persistence_cutover_ready=false`.
- Operation roundtrip families: `10`, all passed.
- Render/export parity: stable `true`, storage clean `true`, captions/gaps/candidates `2/1/2`, render segments/manifest/stitched `2/2/1`, final invalid/non-monotonic/overlap `0/0/0`, global max active `1`.
- Stable surfaces: `source_subtitles`, `final_overlay`, `global_canvas`, `roughcut_sidecar`, `exported_assets`.
- Jammini route probe: `.agents/sentinel/handoffs/20260628-082348-watchdog-handoff-probe.md`
- Jammini scout: `.agents/sentinel/handoffs/20260628-083300-nle-persistence-next-gap-scout.md`
- Dex closeout handoff: `.agents/sentinel/handoffs/20260628-084900-nle-persistence-render-export-gate.md`

### Next Recommended Action

- Continue active `ACTION_ITEMS.md` item 1 only when NAS real-media backfill is available, or keep it analysis-only while NAS is unavailable.
- For NLE, do not persist `nle`, `nle_snapshot`, or `_nle_project_state` to `.aissproj` until a separate compatibility gate is approved.

## Previous Handoff - 2026-06-28 STT Strict Synthetic Collect-Cache Replay And Completed-Item Split

### Scope

- Continued `ACTION_ITEMS.md` item `STT2 / Word Precision Generation Latency Profiling And Accuracy-Preserving Trim`.
- Ran the owner-required NAS-off fallback as a tail-collapse-fixed strict synthetic collect-cache write/hit replay.
- Moved the completed strict synthetic replay slice into `COMPLETED_ACTION_ITEMS.md`; `ACTION_ITEMS.md` now keeps only the remaining real-media NAS backfill/default-review gate for this cache track.
- Updated `test_result.md`, `docs/VALIDATION.md`, and Sentinel handoffs with the new evidence.
- No runtime behavior, STT/STT2 policy, word precision policy, cache defaults, subtitle timing, save/load, render/export, UI, packaging, or App Store behavior changed.

### Verification

- Write run: `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/benchmark_subtitle_pipeline_variants.py --suite modes --variants mode_high --media output/manual_verification/latest/high_context_keep_cache_20260627/synthetic_fixture/synthetic_high_context_keep_cache.mp4 --reference-srt output/manual_verification/latest/high_context_keep_cache_20260627/synthetic_fixture/synthetic_high_context_keep_cache.srt --start-sec 0 --duration-sec 180 --setting ... --keep-artifacts` -> `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_081537/benchmark_results.json`.
- Write acceptance: `./venv/bin/python tools/evaluate_reference_benchmark_acceptance.py .codex_work/benchmarks/subtitle_pipeline_variants/20260628_081537/benchmark_results.json --output-dir output/manual_verification/latest/strict_synthetic_collect_cache_replay_20260628/acceptance_write` -> accepted `true`.
- Hit replay: same command and cache paths -> `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_081711/benchmark_results.json`.
- Hit acceptance: `./venv/bin/python tools/evaluate_reference_benchmark_acceptance.py .codex_work/benchmarks/subtitle_pipeline_variants/20260628_081711/benchmark_results.json --output-dir output/manual_verification/latest/strict_synthetic_collect_cache_replay_20260628/acceptance_hit` -> accepted `true`.
- Readiness re-audit: `./venv/bin/python tools/audit_stt_cache_backfill_readiness.py --glob '.codex_work/benchmarks/subtitle_pipeline_variants/20260627_*/benchmark_results.json' --glob '.codex_work/benchmarks/subtitle_pipeline_variants/20260628_*/benchmark_results.json' --output-dir output/manual_verification/latest/stt_cache_backfill_readiness_after_strict_replay_20260628` -> pass.

### Results

- Strict replay report: `output/manual_verification/latest/strict_synthetic_collect_cache_replay_20260628/strict_replay_report.md`
- Write acceptance: elapsed `79.948s`, raw/final/reference `54/54/54`, quality/text/timing `93.411/91.676/0.1391s`, final invalid/non-monotonic/overlap `0/0/0`, final last end/duration bound `180.12/180.584`, global max active `1`.
- Hit acceptance: elapsed `1.131s`, raw/final/reference `54/54/54`, quality/text/timing `93.411/91.676/0.1391s`, final invalid/non-monotonic/overlap `0/0/0`, final last end/duration bound `180.12/180.584`, global max active `1`.
- Hit replay cache proof: STT1/STT2/word collect cache hits `true`, STT1/STT2/word provider calls `false`, macro cache hit/write/provider groups `1/0/0`.
- Readiness after strict replay: `output/manual_verification/latest/stt_cache_backfill_readiness_after_strict_replay_20260628/stt_cache_backfill_readiness.md`; strict generated cache-hit runs `1`, strict real-media cache-hit runs `0`, production recommendation `hold_default_off`, family status `hold_real_media_backfill_required`.
- Jammini probe: `.agents/sentinel/handoffs/20260628-081437-watchdog-handoff-probe.md`
- Jammini prep: `.agents/sentinel/handoffs/20260628-082000-strict-synthetic-cache-replay-prep.md`
- Dex closeout handoff: `.agents/sentinel/handoffs/20260628-084500-strict-synthetic-cache-replay.md`

### Next Recommended Action

- When NAS is available, run representative HeyDealer first-180s write plus cache-hit replay before any owner review of STT collect-cache defaults.
- If NAS remains unavailable, keep this track analysis-only; do not skip STT1/STT2, disable word precision, shrink windows, promote Fast defaults, or loosen final subtitle gates.

## Previous Handoff - 2026-06-28 STT Cache Backfill Readiness Audit

### Scope

- Continued `ACTION_ITEMS.md` item `STT2 / Word Precision Generation Latency Profiling And Accuracy-Preserving Trim`.
- Added read-only STT collect-cache backfill readiness tooling in `tools/audit_stt_cache_backfill_readiness.py`.
- Added focused tests in `tests/test_stt_cache_backfill_readiness.py`.
- Ran the audit over existing 2026-06-27/2026-06-28 benchmark artifacts without changing runtime behavior, STT/STT2 policy, word precision policy, cache defaults, subtitle timing, save/load, render/export, UI, packaging, or App Store behavior.
- Updated `ACTION_ITEMS.md` so the active STT item now records the new blocker: existing generated cache-hit artifacts fail the strict duration-bound final gate and must be refreshed after the tail-collapse fix before any real-media default-review backfill.

### Verification

- `./venv/bin/python -m py_compile tools/audit_stt_cache_backfill_readiness.py tests/test_stt_cache_backfill_readiness.py` -> pass.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_stt_cache_backfill_readiness.py tests/test_stage_variance_summary.py` -> `7 passed`.
- `./venv/bin/python tools/audit_stt_cache_backfill_readiness.py --glob '.codex_work/benchmarks/subtitle_pipeline_variants/20260627_*/benchmark_results.json' --glob '.codex_work/benchmarks/subtitle_pipeline_variants/20260628_*/benchmark_results.json' --output-dir output/manual_verification/latest/stt_cache_backfill_readiness_20260628` -> pass.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_stt_recheck_service.py tests/test_media_processor_overlap.py tests/test_subtitle_engine_settings.py -k "collect_cache or macro_response_cache"` -> `4 passed, 228 deselected`.

### Results

- Readiness artifact: `output/manual_verification/latest/stt_cache_backfill_readiness_20260628/stt_cache_backfill_readiness.md`
- `run_count=36`, `real_media_run_count=10`, `generated_or_local_run_count=26`.
- `current_real_inputs_available=false`.
- Collect-cache defaults remain `stt_primary_collect_cache_enabled=false`, `stt_recheck_collect_cache_enabled=false`.
- Production recommendation remains `hold_default_off`.
- Strict real-media cache-hit replay count is `0` for STT1, STT2/word, and combined collect-cache families.
- Existing generated cache-hit artifacts are now classified as strict final-gate failures because they fail the duration-bound gate.
- Jammini probe: `.agents/sentinel/handoffs/20260628-080428-watchdog-handoff-probe.md`
- Jammini support audit: `.agents/sentinel/handoffs/20260628-081500-stt-cache-readiness-support-audit.md`

### Next Recommended Action

- While NAS remains unavailable, run a tail-collapse-fixed synthetic collect-cache write/hit replay and require strict final gates before using generated cache-hit speed deltas as current strict evidence.
- When NAS is available, run representative HeyDealer first-180s write plus cache-hit replay before any owner review of STT collect-cache defaults.
- Do not skip STT1/STT2, disable word precision, shrink windows, promote Fast defaults, or loosen final subtitle gates.

## Previous Handoff - 2026-06-28 Shortcut Split Commit And NLE Item Closeout

### Scope

- Completed the final promoted slice of `NLE Timeline Canvas State Ownership: Commit-Boundary Mutable Sync`.
- Added runtime NLE `caption_split` coverage for `_split_at_playhead_or_cut(...)` stable final-caption playhead insert/split commits.
- Preserved source-app/Taption fallback for selection cuts, STT/live preview rows, gap rows, unsupported rows, invalid split positions, or NLE rejection.
- Moved completed NLE mutable-sync status into `COMPLETED_ACTION_ITEMS.md`; `ACTION_ITEMS.md` now contains only active remaining work.
- Preserved existing UI/UX, labels, menus, shortcuts, popup behavior, subtitle generation policy, save/export behavior, packaging, and App Store behavior.

### Verification

- `./venv/bin/python -m py_compile ui/editor/ux/editor_video_controls.py tests/test_timeline_playhead_fit.py` -> pass.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py -k "split_shortcut"` -> `2 passed, 191 deselected`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py -k "split_shortcut or smart_split or gap or magnet or reorder"` -> `25 passed, 168 deselected`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_dual_write.py -k "caption_split"` -> `2 passed, 28 deselected`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_runtime_cutover.py tests/test_timeline_render_cache.py -k "timeline_canvas or projection or final_surface or save_export"` -> `5 passed, 53 deselected`.
- `AI_SUBTITLE_STUDIO_QA_USE_SOURCE=1 ./venv/bin/python tools/qa_suite_runner.py quick --output-dir output/manual_verification/latest/qa_suite_quick_nle_shortcut_split_20260628` -> pass, `failed_count=0`.

### Artifacts

- NLE shortcut split report: `output/manual_verification/latest/nle_shortcut_split_commit_sync_20260628/shortcut_split_report.md`
- Source-app quick QA: `output/manual_verification/latest/qa_suite_quick_nle_shortcut_split_20260628`
- Jammini probe: `.agents/sentinel/handoffs/20260628-075011-watchdog-handoff-probe.md`
- Jammini remaining-source audit: `.agents/sentinel/handoffs/20260628-075500-nle-remaining-release-source-audit.md`
- Dex closeout handoff: `.agents/sentinel/handoffs/20260628-081000-nle-shortcut-split-commit-sync.md`

### Next Recommended Action

- Continue with `ACTION_ITEMS.md` item 1: STT2 / word precision generation latency profiling. NAS remains the required representative real-media backfill for cache/default promotion; without NAS, stay in analysis/measurement-only work.
- For `Mac App Store Submission Readiness`, do not run packaging/signing/upload/notarization/DMG work until the owner explicitly asks.

## Previous Handoff - 2026-06-28 Partial Range Replace Commit

### Scope

- Continued `ACTION_ITEMS.md` item `NLE Timeline Canvas State Ownership: Commit-Boundary Mutable Sync`.
- Added runtime NLE `caption_range_replace` coverage for `clear_segments_in_range(...)` / `insert_partial_segments(...)` partial subtitle replacement commits.
- Preserved source-app/Taption fallback for STT/live preview rows, unsupported shapes, NLE rejection, or any outside-range drift.
- Kept completed slice history in `COMPLETED_ACTION_ITEMS.md`; `ACTION_ITEMS.md` now keeps the item active only for future uncovered release/commit sources.
- Preserved existing UI/UX, labels, menus, shortcuts, popup behavior, subtitle generation policy, save/export behavior, packaging, and App Store behavior.

### Verification

- `./venv/bin/python -m py_compile core/project/nle_operations.py core/project/nle_dual_write.py ui/editor/ux/editor_timeline_video.py ui/editor/editor_segments_manual_edits.py tests/test_project_nle_dual_write.py tests/test_timeline_playhead_fit.py` -> pass.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_dual_write.py tests/test_project_nle_operations.py tests/test_nle_persistence_cutover_audit.py` -> `39 passed`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py -k "partial_insert or gap or magnet or reorder"` -> `25 passed, 166 deselected`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_hit_targets.py tests/test_project_segment_reload.py -k "gap or magnet or reorder or caption_range_replace or identity or reload"` -> `125 passed, 116 deselected`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_runtime_cutover.py tests/test_timeline_render_cache.py -k "timeline_canvas or projection or final_surface or save_export"` -> `5 passed, 53 deselected`.
- `./venv/bin/python tools/audit_nle_persistence_cutover.py --output-dir output/manual_verification/latest/nle_persistence_identity_preservation_range_replace_20260628` -> pass, `operation_roundtrip_family_count=10`.
- `AI_SUBTITLE_STUDIO_QA_USE_SOURCE=1 ./venv/bin/python tools/qa_suite_runner.py quick --output-dir output/manual_verification/latest/qa_suite_quick_nle_range_replace_20260628` -> pass, `failed_count=0`.

### Artifacts

- NLE partial range replace report: `output/manual_verification/latest/nle_partial_range_replace_commit_sync_20260628/range_replace_report.md`
- Persistence audit: `output/manual_verification/latest/nle_persistence_identity_preservation_range_replace_20260628/nle_persistence_cutover_audit.md`
- Source-app quick QA: `output/manual_verification/latest/qa_suite_quick_nle_range_replace_20260628`
- Jammini probe: `.agents/sentinel/handoffs/20260628-073020-watchdog-handoff-probe.md`
- Jammini support audit: `.agents/sentinel/handoffs/20260628-062800-nle-range-replace-audit.md`
- Dex closeout handoff: `.agents/sentinel/handoffs/20260628-073800-nle-range-replace-commit-sync.md`

### Next Recommended Action

- Run a fresh audit for any remaining release/commit source not already covered by NLE dual-write.
- Do not write NLE mutable state on every drag pixel; only reconcile a source after proving Taption drag, magnet, gap, and no-overlap behavior again.

## Previous Handoff - 2026-06-28 Quality Review Text Commit

### Scope

- Continued `ACTION_ITEMS.md` item `NLE Timeline Canvas State Ownership: Commit-Boundary Mutable Sync`.
- Added runtime NLE `caption_text_edit` coverage for quality-review candidate / one-click text replacement commits in `ui/editor/editor_quality_review.py`.
- Restored quality-review metadata after NLE projection reload so `candidate_applied`, `manual_confirmed`, candidate reason, and quality candidates remain visible.
- Preserved existing UI/UX, labels, menus, shortcuts, popup behavior, subtitle generation policy, save/export behavior, packaging, and App Store behavior.

### Verification

- `./venv/bin/python -m py_compile ui/editor/editor_quality_review.py tests/test_timeline_playhead_fit.py` -> pass.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py -k "quality_candidate_text_commit"` -> `2 passed, 187 deselected`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py -k "quality_candidate_text_commit or replace_text_in_all_subtitles or manual_confirmed or inline_text"` -> `6 passed, 183 deselected`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_dual_write.py -k "caption_text_edit"` -> `2 passed, 26 deselected`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_hit_targets.py tests/test_timeline_playhead_fit.py -k "gap or magnet or reorder"` -> `58 passed, 284 deselected`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_runtime_cutover.py tests/test_timeline_render_cache.py -k "timeline_canvas or projection or final_surface or save_export"` -> `5 passed, 53 deselected`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_segment_reload.py -k "caption_text_edit or identity or reload"` -> `88 passed`.
- `git diff --check -- .` -> pass.
- `AI_SUBTITLE_STUDIO_QA_USE_SOURCE=1 ./venv/bin/python tools/qa_suite_runner.py quick --output-dir output/manual_verification/latest/qa_suite_quick_nle_quality_text_commit_20260628` -> pass, `failed_count=0`.

### Artifacts

- NLE quality review text commit report: `output/manual_verification/latest/nle_quality_review_text_commit_sync_20260628/quality_text_commit_report.md`
- Source-app quick QA: `output/manual_verification/latest/qa_suite_quick_nle_quality_text_commit_20260628`
- Jammini probe: `.agents/sentinel/handoffs/20260628-071837-watchdog-handoff-probe.md`
- Jammini fresh audit scout: `.agents/sentinel/handoffs/20260628-062700-nle-final-exclusions-audit.md`

### Next Recommended Action

- `clear_segments_in_range(...)` / `insert_partial_segments(...)` has since been handled by the `caption_range_replace` operation family; continue with a fresh audit for any remaining uncovered release/commit source.
- Re-run Taption gap/magnet/reorder plus NLE projection guards after any next mutable-sync slice.

## Previous Handoff - 2026-06-28 Popup Replace-All

### Scope

- Continued `ACTION_ITEMS.md` item `NLE Timeline Canvas State Ownership: Commit-Boundary Mutable Sync`.
- Added runtime NLE `caption_text_edit` coverage for popup replace-all subtitle text commits in `ui/editor/editor_segments_text_ops.py`.
- Routed safe final-caption replacements through sequential NLE text-edit operations while preserving legacy QTextDocument fallback for visible gap text, STT/live preview rows, unsupported row sets, or NLE rejection.
- Preserved existing UI/UX, labels, menus, shortcuts, popup behavior, subtitle generation policy, save/export behavior, packaging, and App Store behavior.

### Verification

- `./venv/bin/python -m py_compile ui/editor/editor_segments_text_ops.py tests/test_timeline_playhead_fit.py` -> pass.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py -k "replace_text_in_all_subtitles"` -> `3 passed, 184 deselected`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_segment_reload.py -k "replace_text_in_all_subtitles"` -> `1 passed, 87 deselected`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py tests/test_project_segment_reload.py -k "replace_text_in_all_subtitles or inline_text or text_edit or change_speaker_for_line"` -> `12 passed, 263 deselected`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_dual_write.py -k "caption_text_edit"` -> `2 passed, 26 deselected`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_hit_targets.py tests/test_timeline_playhead_fit.py -k "gap or magnet or center_reorder or center_drag or reorder"` -> `66 passed, 274 deselected`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_runtime_cutover.py -k "timeline_canvas or final_surface or global_canvas or save_export"` -> `7 passed, 3 deselected`.
- `AI_SUBTITLE_STUDIO_QA_USE_SOURCE=1 ./venv/bin/python tools/qa_suite_runner.py quick --output-dir output/manual_verification/latest/qa_suite_quick_nle_popup_replace_all_20260628` -> pass, `failed_count=0`.

### Artifacts

- NLE popup replace-all report: `output/manual_verification/latest/nle_popup_replace_all_commit_sync_20260628/popup_replace_all_report.md`
- Source-app quick QA: `output/manual_verification/latest/qa_suite_quick_nle_popup_replace_all_20260628`
- Jammini probe: `.agents/sentinel/handoffs/20260628-070530-watchdog-handoff-probe.md`
- Jammini fresh audit scout: `.agents/sentinel/handoffs/20260628-062600-nle-remaining-fresh-audit.md`

### Next Recommended Action

- Continue the fresh audit for remaining safe release/commit sources that can move to NLE dual-write without per-pixel writes or Taption UX drift.
- Do not reuse the latest Jammini scout's first three candidates as next work without rechecking, because they are already completed in `COMPLETED_ACTION_ITEMS.md`.
- Re-run Taption gap/magnet/reorder plus NLE projection guards after any next mutable-sync slice.

## Previous Handoff - 2026-06-28 Shortcut Resize

### Scope

- Continued `ACTION_ITEMS.md` item `NLE Timeline Canvas State Ownership: Commit-Boundary Mutable Sync`.
- Added runtime NLE `caption_resize` coverage for shortcut start/end-to-playhead release commits in `ui/editor/editor_segments_block_surgery.py`.
- Routed safe single-block explicit-gap absorption shapes through NLE while preserving the existing QTextBlock fallback for gap creation, gap extension, STT/live preview rows, unsupported shapes, or NLE rejection.
- Preserved existing UI/UX, labels, menus, shortcuts, popup behavior, subtitle generation policy, save/export behavior, packaging, and App Store behavior.

### Verification

- `./venv/bin/python -m py_compile ui/editor/editor_segments_block_surgery.py tests/test_timeline_playhead_fit.py` -> pass.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py -k "segment_start_shortcut or segment_end_shortcut or shortcut"` -> `6 passed, 178 deselected`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_dual_write.py -k "caption_resize"` -> `4 passed, 24 deselected`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_hit_targets.py tests/test_timeline_playhead_fit.py -k "gap or magnet or center_reorder or center_drag or reorder"` -> `65 passed, 272 deselected`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_runtime_cutover.py -k "timeline_canvas or final_surface or global_canvas or save_export"` -> `7 passed, 3 deselected`.
- `AI_SUBTITLE_STUDIO_QA_USE_SOURCE=1 ./venv/bin/python tools/qa_suite_runner.py quick --output-dir output/manual_verification/latest/qa_suite_quick_nle_shortcut_resize_20260628` -> pass, `failed_count=0`.

### Artifacts

- NLE shortcut resize report: `output/manual_verification/latest/nle_shortcut_resize_commit_sync_20260628/shortcut_resize_report.md`
- Source-app quick QA: `output/manual_verification/latest/qa_suite_quick_nle_shortcut_resize_20260628`
- Jammini probe: `.agents/sentinel/handoffs/20260628-065025-watchdog-handoff-probe.md`
- Jammini shortcut guard scout: `.agents/sentinel/handoffs/20260628-062500-nle-shortcut-resize-guard-scout.md`

### Next Recommended Action

- Run a fresh audit for remaining safe release/commit sources that can move to NLE dual-write without per-pixel writes or Taption UX drift.
- Keep `ACTION_ITEMS.md` as the active queue and `COMPLETED_ACTION_ITEMS.md` as the only completed-slice archive.
- Re-run Taption gap/magnet/reorder plus NLE projection guards after any next mutable-sync slice.

## Previous Handoff - 2026-06-28 Marker Edit

### Scope

- Continued `ACTION_ITEMS.md` item `NLE Timeline Canvas State Ownership: Commit-Boundary Mutable Sync`.
- Added runtime NLE `marker_edit` coverage for provisional cut-boundary create/delete in `core/project/nle_dual_write.py`.
- Wired `_on_provisional_cut_boundary_requested(...)` and `_on_provisional_cut_boundary_delete_requested(...)` in `ui/editor/editor_scan_cut_core.py` to record release-commit marker operations after the existing source-app scan-boundary row commit succeeds.
- Preserved existing UI/UX, labels, menus, scan-boundary rows, info-label text, subtitle generation policy, save format, packaging, and App Store behavior.

### Verification

- `./venv/bin/python -m py_compile core/project/nle_dual_write.py ui/editor/editor_scan_cut_core.py tests/test_project_nle_dual_write.py tests/test_timeline_hit_targets.py` -> pass.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_dual_write.py -k "marker_edit or gap_delete"` -> `5 passed, 23 deselected`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_hit_targets.py -k "scan_boundary_create_records_nle_marker_edit_operation or scan_boundary_delete_removes_requested_boundary_from_editor_state"` -> `2 passed, 151 deselected`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_operations.py tests/test_project_nle_dual_write.py` -> `33 passed`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_hit_targets.py -k "scan_boundary or provisional_cut_boundary or playhead_auto_cut_magnet or gap_generate"` -> `24 passed, 129 deselected`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_hit_targets.py tests/test_timeline_playhead_fit.py -k "gap or magnet or center_reorder or center_drag or reorder"` -> `62 passed, 271 deselected`.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_runtime_cutover.py -k "timeline_canvas or final_surface or global_canvas or save_export"` -> `7 passed, 3 deselected`.
- `AI_SUBTITLE_STUDIO_QA_USE_SOURCE=1 ./venv/bin/python tools/qa_suite_runner.py quick --output-dir output/manual_verification/latest/qa_suite_quick_nle_marker_edit_20260628` -> pass, `failed_count=0`.

### Artifacts

- NLE marker edit report: `output/manual_verification/latest/nle_provisional_cut_boundary_marker_edit_20260628/marker_edit_report.md`
- Source-app quick QA: `output/manual_verification/latest/qa_suite_quick_nle_marker_edit_20260628`
- Jammini probe: `.agents/sentinel/handoffs/20260628-063735-watchdog-handoff-probe.md`
- Jammini next-slice scout: `.agents/sentinel/handoffs/20260628-061300-nle-next-slice-recommendation.md`

### Next Recommended Action

- Continue item 1 with the latest named uncovered release/commit candidate: `_set_segment_start_to_playhead` / `_set_segment_end_to_playhead` in `ui/editor/editor_segments_block_surgery.py`.
- Reuse NLE `caption_resize` only if the QTextBlock-shape guard and legacy fallback prove safe.
- Keep no per-pixel NLE writes and rerun Taption gap/magnet/reorder plus NLE projection guards after the next slice.

## Current Handoff - 2026-06-27

### Scope

- Implemented Taption-derived subtitle segment editing guards for the source app.
- Preserved STT1/STT2 candidate lanes as diagnostic/editor evidence, but prevented preview rows from drawing on the video subtitle overlay once final rows exist.
- Strengthened final segment stability so `stable_for_save_reopen` requires invalid duration `0`, non-monotonic `0`, and overlap `0`.
- Added gap-aware center-drag snap filtering so a silence/gap boundary does not steal the snap guide from the real subtitle boundary beyond the gap.
- Removed the completed Taption parity item from `ACTION_ITEMS.md` per the completed-item rule. Completion evidence is in `test_result.md`.
- Completed the Taption segment UI/UX parity follow-up item and removed it from `ACTION_ITEMS.md` per the completed-item rule.
- Added the focused Taption segment UI/UX parity checklist slice: single-gap snap suppression, visible-boundary release commit, one-gap center move absorption without final overlap, one-word inline-editor up/down retention, and immediate neighbor reorder preview/commit.
- Implemented Taption immediate neighbor reorder as a coexisting body-drag path: fully crossing an attached neighbor reorders, while partial overlap keeps the existing overwrite/trim behavior.
- Added a full source-app NLE transition planning item to `ACTION_ITEMS.md`; it is an internal NLE ownership plan only and does not reopen native migration, Swift rewrite, QML migration, or visible UI clone work.
- Completed `Full NLE Transition Plan` phase 1 owner inventory. Current mutable owners are mapped in `output/manual_verification/latest/nle_owner_inventory_20260627/owner_inventory.md`.
- Completed `Full NLE Transition Plan` phase 2 domain contract. Internal NLE time domains, entities, projection surfaces, phase 3 validation checklist, and stop conditions are defined in `output/manual_verification/latest/nle_domain_contract_20260627/domain_contract.md`.
- Completed `Full NLE Transition Plan` phase 3 read-only projection parity. `core/project/nle_projection_parity.py` now produces a parity report for timeline, video overlay, global canvas, save/export, and roughcut surfaces without routing runtime writes through NLE.
- Completed `Full NLE Transition Plan` phase 4 operation model. `core/project/nle_operations.py` now defines operation/undo transaction contracts and validation rules without routing runtime writes through NLE.
- Completed `Full NLE Transition Plan` phase 5 dual-write pilot for `gap_delete`. `core/project/nle_dual_write.py` routes one explicit gap deletion through runtime `NLEProjectState` and projects the result back into legacy `editor_state`; no visible UI route or save format was changed.
- Completed `Full NLE Transition Plan` phase 6 save/reload compatibility. `core/project/nle_persistence_guard.py` strips or metadata-quarantines unapproved persisted NLE fields while keeping runtime-only `NLEProjectState` hydration and legacy-compatible disk writes.
- Completed `Full NLE Transition Plan` phase 7 render/export parity. `core/project/nle_render_export_parity.py` compares the same final caption frame projection across source subtitles, final overlay, global canvas, roughcut sidecars, and exported asset plans.
- Completed `Full NLE Transition Plan` phase 8 final-overlay runtime cutover. `core/project/nle_runtime_cutover.py` projects editor rows through runtime NLE caption state for the normal video subtitle provider; live preview, timeline, global canvas, save/reload, render/export, and persistence ownership remain unchanged.
- Completed `Full NLE Transition Plan` phase 9 cleanup gate audit. Legacy write-path deletion is blocked because only one post-cutover quick QA checkpoint exists; the older full QA checkpoint predates final-overlay cutover and cannot count as post-cutover cleanup proof.
- Completed `Full NLE Transition Plan` phase 10 release checkpoint parity and rollback proof. Two consecutive post-cutover checkpoint bundles passed, each with focused NLE runtime/save/reload/render/export/editor parity guards and source-app quick QA.
- Completed `Full NLE Transition Plan` phase 11 cleanup as a no-op code cleanup. No app code was deleted because final-overlay cutover did not create a proven-dead legacy write path; fallback context helpers remain rollback/active dependencies. The completed NLE item was removed from `ACTION_ITEMS.md`.
- Completed `Cut-Boundary Generation Latency Profiling And Safe Trim` as a no-op runtime closeout. The owner-relevant HeyDealer 180s profile showed cut-boundary owner rows below 1ms, so no cut-boundary scheduling/cache/quality change was applied.
- Captured `STT2 / Word Precision Generation Latency Profiling And Accuracy-Preserving Trim` profiling evidence and improved the verifier test method. `tools/verify_full_media_pipeline.py` now surfaces STT2/word counts, final invalid/non-monotonic/overlap stability, global canvas max-active stability, memory pressure, reference-quality fields, and generation-owner cProfile summaries.
- Added direct wall-clock stage spans for STT1 primary transcription, selective STT2 rescue, word timestamp precision, VAD/STT consensus, and subtitle postprocess. The latest HeyDealer reference-scored benchmark remains stable at quality `81.335`, timing MAE `1.5958s`, final overlap `0`, and `stable_for_save_reopen=true`.
- Applied the first safe STT2/word precision follow-up trim: zero-candidate macro LLM rows no longer resolve/warm up a local LLM before the gate proves `llm_rows > 0`. Quality/timing stability passed, but total wall-clock latency remains open because STT/word precision variance still dominates the fixture.
- Rejected and reverted the High context-boundary LLM batching candidate. It lowered reference subtitle postprocess time to `9.879991s`, but stricter HeyDealer SRT scoring dropped quality `81.335 -> 81.316`, text `94.267 -> 94.241`, and segmentation `87.879 -> 87.812`, so no batch code was kept.
- Added STT2/word precision substage timing instrumentation. `stt2_selective_recheck` and `word_precision` stage spans now include prepare/collect/annotate/batch elapsed fields; local 60s reference smoke shows the remaining cost sits in collect time, not clip preparation or annotation.
- Added STT collect fallback precision instrumentation. `stt_collect_whisperkit_fallback` stage spans now expose WhisperKit empty/timeout fallback count, reason, source/fallback model, total/max elapsed, chunk counts, emitted segment count, and word timestamp mode; local smoke confirmed repeat-summary/CSV propagation.
- Added High context-boundary diagnostics instrumentation. Benchmark/verifier artifacts now expose candidate pairs, skipped pairs, LLM calls, failed calls, changed pairs, max pairs, and elapsed time for the High context-boundary postprocess detail stage.
- Verified the new High context-boundary diagnostics on cached X5 audio 180s: pipeline `74.919s`, raw/final `43/50`, final invalid/non-monotonic/overlap `0/0/0`, `stable_for_save_reopen=true`, global max active `1`, detail top `high_context_boundary=32.230736s`, candidate/call/changed `4/4/0`.
- Did not adopt any new latency trim from the X5 audio run. The owner-required HeyDealer reference media/SRT under `/Volumes/photo/...` are unavailable, so the next latency candidate is blocked until the NAS 3-minute reference gate can run.
- Added a reference fixture availability preflight for the next latency slice. `tools/verify_reference_fixture_availability.py` now records whether the real media and reference SRT are ready, and marks fallback media as instrumentation/structural-stability proof only.
- Current preflight artifact is `output/manual_verification/latest/reference_fixture_availability_20260627/reference_fixture_availability.md`; it blocks reference-scored acceptance because the `/Volumes/photo/...` HeyDealer MP4 and matching `.srt` are missing, while the cached HeyDealer WAV is fallback-only.
- Restored a local X5 60s reference-scored smoke surface. `tools/materialize_reference_srt.py` materializes cached JSON rows into a relative-time SRT, and the local X5 smoke passed preflight and `mode_high` reference scoring.
- Current local X5 smoke artifact is `output/manual_verification/latest/x5_local_reference_fixture_20260627/reference_benchmark_report.md`; it is short-loop reference evidence only and does not replace the owner-required NAS HeyDealer 3-minute acceptance run before latency-trim adoption.
- Restored a longer X5 180s project-reference smoke surface. The accepted pair is cached X5 180s WAV plus `projects/X5_시승기_전반.assets/subtitles/final.srt`; the similarly named `X5_후반` SRT was rejected as a semantic mismatch after scoring.
- Added `tools/evaluate_reference_benchmark_acceptance.py` so scored benchmark results must pass quality, text, timing, final-overlap, and global-canvas gates before being used for latency-trim decisions.
- Owner narrowed the next latency test to the NAS HeyDealer 3-minute video. The NAS share was mounted at `/Volumes/photo`, exact MP4/SRT preflight passed, and `mode_high` first 180s reference benchmark was accepted. Latest artifact: `output/manual_verification/latest/heydealer_nas_reference_180s_20260627_2215/reference_benchmark_report.md`.
- Added STT2/word duration diagnostics and re-ran the owner-required NAS HeyDealer first 180s benchmark. Latest artifact: `output/manual_verification/latest/stt_recheck_duration_diagnostics_20260627/diagnostics_report.md`; result elapsed `59.255s`, raw/final/reference `58/56/89`, quality `81.335`, timing MAE `1.5958s`, final overlap `0`, global max active `1`, acceptance `true`.
- Important latency interpretation: `stt2_selective_recheck.applied_count=1` is one broad rescue range, not one low-value segment. It requested `180.096s`, prepared `120.000s`, collected `37` segments, and applied `37` segment-level results, so the next trim must inspect range/prepared audio and reference quality before changing STT2 behavior.
- Added STT2/word reason breakdown diagnostics and re-ran the owner-required NAS HeyDealer first 180s benchmark. Latest artifact: `output/manual_verification/latest/stt_recheck_reason_breakdown_20260627/reason_breakdown_report.md`; result elapsed `58.820s`, raw/final/reference `58/56/89`, quality `81.335`, timing MAE `1.5958s`, final overlap `0`, global max active `1`, acceptance `true`.
- Important reason interpretation: STT2 is currently a missing-voice rescue path (`missing_voice/route_hint/low_score/empty_text=1/0/0/1`). Word precision chose `25` ranges, but none were editor-selected, precision-review, needs-review, red/yellow, risk, or missing-word forced (`0/0/0/0/0/0/0`). Next speed work should look at collect scheduling/cache reuse or a decision-equivalent High context-boundary gate before changing quality policy.
- Added High context-boundary decision-action diagnostics and re-ran the owner-required NAS HeyDealer first 180s benchmark. Latest artifact: `output/manual_verification/latest/high_context_decision_diagnostics_20260627/decision_diagnostics_report.md`; result elapsed `59.559s`, raw/final/reference `58/56/89`, quality `81.335`, timing MAE `1.5958s`, final overlap `0`, global max active `1`, acceptance `true`.
- Important High context interpretation: candidate/skipped/call/failed/changed/max pairs were `2/55/2/0/0/8`; keep/move/merge/invalid were `2/0/0/0`; correction requested/applied was `0/0`. This supports investigating only a strict decision-equivalent no-change gate, not batching or broad skipping.
- Implemented and synthetic-verified the strict High context keep/no-correction cache candidate. Latest artifact: `output/manual_verification/latest/high_context_keep_cache_20260627/keep_cache_report.md`; owner stated NAS was off and asked Dex to generate/verify a video, so Dex created a 180.583s Korean fixture with 54 reference SRT rows. First write run had High context calls/cache hit-miss-write `8/0-8-8`; second cache-hit run had `0/8-0-0`, with identical quality/final gates and `accepted=true`.
- Implemented and synthetic-verified the macro proofread response replay cache. Latest artifact: `output/manual_verification/latest/macro_response_cache_20260627/macro_response_cache_report.md`; the same generated 180.583s fixture passed two scored High-mode runs. First write run `20260627_233240` wrote one exact prompt/model/provider cache entry with 14 raw chunks and had proofread elapsed `30.731199s`; second cache-hit run `20260627_233531` showed macro cache hit/write/provider groups `1/0/0`, proofread elapsed `0.545337s`, identical quality/final gates, and `accepted=true`.
- Implemented and synthetic-verified the opt-in STT2/word precision collect replay cache. Latest artifact: `output/manual_verification/latest/stt_recheck_collect_cache_20260627/collect_cache_report.md`; the same generated 180.583s fixture passed two scored High-mode runs and produced final cache-hit SRT `output/manual_verification/latest/stt_recheck_collect_cache_20260627/synthetic_final_subtitles_cache_hit.srt`. First write run `20260627_234839` had STT2 collect `14.284272s`, word precision collect `10.930693s`, cache hit/write/provider `false/true/true`, elapsed `46.498s`, and `accepted=true`; second cache-hit run `20260627_234935` had STT2 collect `0.0s`, word precision collect `0.0s`, cache hit/write/provider `true/false/false`, elapsed `20.105s`, identical quality/final gates, and `accepted=true`.
- Important latency interpretation: STT collect replay keeps provider output caching opt-in and still reruns annotation, STT2 replacement selection, word precision timing application, final integrity, and reference acceptance. Live STT2 preview callback paths disable the cache so candidate-lane preview events are not skipped. Default remains `stt_recheck_collect_cache_enabled=false` until a representative real-media backfill is accepted; after cache hits, the dominant remaining synthetic cost is STT1 primary transcribe around `18-20s`.
- Re-ran the owner-requested NAS-off generated-video validation on 2026-06-28. Latest artifact: `output/manual_verification/latest/generated_video_subtitle_validation_20260628/validation_report.md`; benchmark `20260628_000644` produced elapsed `78.344s`, raw/final/reference `54/54/54`, quality/text/timing `80.153/91.676/1.437s`, final invalid/non-monotonic/overlap `0/0/0`, save/reopen stable `true`, global max active `1`, and `accepted=true`.
- Added STT1 primary collect diagnostics and re-ran the generated 180s fixture. Latest artifact: `output/manual_verification/latest/stt_primary_collect_diagnostics_20260628/stt_primary_collect_report.md`; benchmark `20260628_001645` produced elapsed `49.380s`, raw/final/reference `54/54/54`, accepted `true`, and showed STT1 total `20.135353s` with setup `0.046327s` and collect `19.986159s`. Interpretation: STT1 cost is actual WhisperKit collect time on this fixture, not setup/idle overhead; no STT1 skip/model downgrade/window shrink is accepted.
- Implemented and synthetic-verified the opt-in STT1 primary collect replay cache. Latest artifact: `output/manual_verification/latest/stt_primary_collect_cache_20260628/primary_collect_cache_report.md`; first write run `20260628_003224` had STT1 collect `17.717081s`, cache hit/write/provider `false/true/true`, elapsed `51.964s`, and `accepted=true`; second cache-hit run `20260628_003326` had STT1 collect `0.0s`, STT1 parent `0.049428s`, cache hit/write/provider `true/false/false`, preserved provider diagnostics `whisperkit_persistent` / `whisperkit-persistent:large-v3-v20240930_turbo_632MB`, identical quality/final gates, elapsed `37.715s`, and `accepted=true`.
- Important STT1 cache interpretation: replay is exact-input only and remains default-off via `stt_primary_collect_cache_enabled=false`; cache hits are disabled when a live preview callback exists, and downstream STT2 selection, word precision, VAD/STT consensus, LLM/LoRA postprocess, final integrity, and reference acceptance still run. A NAS HeyDealer first-180s backfill is still required before treating the speed delta as representative real-footage evidence.
- Implemented and synthetic-verified combined collect cache key normalization. Latest artifact: `output/manual_verification/latest/combined_collect_cache_20260628/combined_collect_cache_report.md`; because the owner kept NAS off, the generated 180s fixture was used. First write run `20260628_004231` had elapsed `72.570s`, raw/final/reference `54/54/54`, quality/text/timing `80.153/91.676/1.437s`, final invalid/non-monotonic/overlap `0/0/0`, global max active `1`, STT1/STT2/word collect `17.752132s/14.261639s/10.621729s`, macro proofread `28.907253s`, and `accepted=true`. Second cache-hit run `20260628_004504` had elapsed `4.449s`, identical scored quality/final gates, STT1/STT2/word collect all `0.0s` with provider calls `false`, macro provider group `0`, generated final SRT block count `54`, SRT invalid/non-monotonic/overlap `0/0/0`, and `accepted=true`.
- Important combined-cache interpretation: the code change only makes STT1 and STT2/word exact replay keys ignore unrelated cache toggles/paths/max-entry settings so combined-cache runs do not duplicate provider work. `stt_primary_collect_cache_enabled` and `stt_recheck_collect_cache_enabled` remain default `false` until real-media backfill passes.
- Implemented and synthetic-verified the all-hit macro response cache warmup skip. Latest artifact: `output/manual_verification/latest/macro_cache_warmup_skip_20260628/macro_cache_warmup_skip_report.md`; with the same generated 180s fixture and populated combined-cache files, run `20260628_005314` skipped runtime LLM model resolution/Ollama warmup because every macro LLM candidate group had an exact response-cache hit. Elapsed dropped `4.449s -> 1.312s` versus the previous combined cache-hit run, macro proofread dropped `3.606041s -> 0.400186s`, macro hit/write/provider groups stayed `1/0/0`, raw/final/reference stayed `54/54/54`, quality/text/timing stayed `80.153/91.676/1.437s`, final invalid/non-monotonic/overlap stayed `0/0/0`, generated SRT block count stayed `54`, SRT invalid/non-monotonic/overlap stayed `0/0/0`, and acceptance returned `true`.
- Important macro warmup-skip interpretation: LLM preparation is skipped only when all macro groups are cache hits. Any miss or uncertain preflight preserves the old resolve/warmup path. This is still generated-fixture evidence only; NAS HeyDealer or another representative owner fixture remains required before production-wide speed claims.
- Re-ran the owner-requested NAS-off generated-video validation on the current worktree. Latest artifact: `output/manual_verification/latest/generated_video_subtitle_validation_20260628_latest/validation_report.md`; benchmark `20260628_010403` produced elapsed `44.968s`, raw/final/reference `54/54/54`, quality/text/timing `80.153/91.676/1.437s`, final invalid/non-monotonic/overlap `0/0/0`, generated SRT rows `54`, SRT invalid/non-monotonic/overlap `0/0/0`, global max active `1`, and `accepted=true`.
- Added a stricter direct SRT/media duration-bound validation for the same NAS-off generated-video run. Latest artifact: `output/manual_verification/latest/generated_video_strict_duration_validation_20260628/strict_duration_report.md`; result is `fail` because the generated final SRT extends to `182.032s` while the MP4 duration is `180.584s`, with `17` rows beyond media duration, `16` sub-0.3s tail rows, and one `59.792s` long tail row. Treat the legacy benchmark acceptance as insufficient until media-duration/min-duration/long-tail gates are added and the tail-collapse cause is fixed.
- Promoted the strict generated-video validation into the acceptance path. `tools/evaluate_reference_benchmark_acceptance.py` now rejects final `last_end` beyond the media/window duration bound, and `tools/benchmark_subtitle_pipeline_variants.py` records final min/max segment duration plus short/long counts for future runs. Re-evaluating `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_010403/benchmark_results.json` now returns `accepted=false`, reason `final_last_end_beyond_duration_bound`; artifact: `output/manual_verification/latest/generated_video_strict_acceptance_gate_20260628/reference_benchmark_acceptance.md`. Tail-collapse root cause remains open.
- Fixed the generated-video tail collapse. Root cause was `vad_stt_timing_consensus` accepting a broad full-file VAD span as an STT1/VAD-only union source, stretching later STT1 rows into a long tail row and 0.05s fragments. `core/subtitle_quality/vad_alignment_checker.py` now requires VAD/STT1 span similarity before that union path applies. Re-run `20260628_013224` passes strict acceptance: elapsed `44.307s`, raw/final/reference `54/54/54`, quality/text/timing `93.411/91.676/0.1391s`, final invalid/non-monotonic/overlap `0/0/0`, final last end/duration bound `180.12/180.584`, short/long `0/0`; artifact: `output/manual_verification/latest/generated_video_tail_collapse_fix_20260628/tail_collapse_fix_report.md`.
- Rejected and reverted the prepared recheck clip metadata reuse candidate. Artifact: `output/manual_verification/latest/recheck_prepared_clip_reuse_rejected_20260628/recheck_prepared_clip_reuse_rejection_report.md`; prepare time stayed around `0.50s` for word precision and the metadata/directory retention complexity was not justified. No code/tests from that candidate remain.
- Added NAS-off stage/memory variance analysis tooling. `tools/summarize_stage_variance.py` reads existing `benchmark_results.json` artifacts and writes JSON/Markdown summaries for elapsed variance, stage totals, cache hit/provider-call flags, memory-pressure distribution, final gates, and duration-bound failures without touching runtime behavior.
- Latest NAS-off stage variance artifact: `output/manual_verification/latest/stt_latency_stage_variance_20260628/stage_variance_summary.md`; 10 generated/cache artifacts show elapsed avg/min/max/range `41.66/1.312/82.433/81.121s`, stage ranges STT1 `20.134950s`, STT2 `15.939524s`, word precision `20.271760s`, subtitle postprocess `30.410655s`, worst memory pressure counts `unknown=4`, `normal=4`, `critical=2`, final invalid/non-monotonic/overlap/global max-active all pass, and old tail-collapse runs flagged as duration-bound failures.
- Jammini/서린 reviewed the NAS-off latency scope in `.agents/sentinel/handoffs/20260628-025200-stt-latency-nas-off-variance-review.md` and returned `HOLD` for algorithm/default changes until real-media backfill is available; analysis/measurement-only work remains allowed.
- Completed a non-destructive Mac App Store readiness audit. `tools/audit_app_store_readiness.py` reports `local_packaging_ready=true` but `app_store_submission_ready=false`; no packaging, signing, notarization, upload, tag, release, or DMG build was run.
- Added `docs/APP_STORE_SUBMISSION_READINESS.md` as the non-code submission material draft for privacy, export compliance, screenshots, support URL, review notes, age rating, release notes, and entitlement explanation.
- Completed the non-destructive Mac App Store submission target-lock slice. Latest artifact: `output/manual_verification/latest/app_store_readiness_target_lock_20260628/app_store_readiness_audit.md`; `submission_target=mac_app_store_pkg`, `local_packaging_ready=true`, `app_store_submission_ready=false`, blocker count `14`, Mac App Store `.pkg` status `blocked`, Developer ID beta `.dmg` status `opt_in_hold`.
- Jammini/한결 reviewed the App Store readiness next step in `.agents/sentinel/handoffs/20260628-031000-app-store-readiness-next-step-review.md` and returned `HOLD` for packaging/signing/upload/notarization/DMG actions; static audit and metadata documentation work remains allowed.
- Completed the first post-baseline NLE runtime editing adoption slice: `caption_move` dual-write now routes subtitle body moves through runtime `NLEProjectState`, records `caption_move` `NLEEditorOperation`, supports Taption neighbor reorder metadata, and projects back to legacy `editor_state`.
- Completed the next NLE runtime editing adoption slice: `caption_resize` dual-write now routes boundary-handle and diamond-style resize operations through runtime `NLEProjectState`, records `caption_resize` `NLEEditorOperation`, preserves Taption trim/delete/gap absorption behavior before the final-overlap gate, and projects back to legacy `editor_state`.
- Completed the live editor mutation cutover slice: `diamond` shared-boundary resize now attempts runtime NLE `caption_resize` dual-write in `_on_seg_time_changed(...)`, applies projected rows through `_reload_segments_from_list(..., preserve_view=True, mark_dirty=True)` when safe, and falls back to the existing Taption/legacy path for NLE rejection, unsupported runtime shape, or micro rows that collapse on the project floor-frame grid.
- Completed the live editor boundary-handle cutover slice: `square_left` and `square_right` subtitle boundary resizes now attempt runtime NLE `caption_resize` dual-write in `_on_seg_time_changed(...)`, apply projected rows through `_reload_segments_from_list(..., preserve_view=True, mark_dirty=True)` when safe, and fall back to the existing Taption/source-app timing path for NLE rejection, transient STT/live-preview rows, unsupported runtime shape, or invalid/collapsing rows.
- Completed the live editor caption-delete cutover slice: segment delete-to-gap now attempts runtime NLE `caption_delete` dual-write, records `replace_with_silence_gap`, projects the deleted final caption into a silence gap row, and falls back to the existing Taption/source-app direct gap conversion whenever live STT preview rows or unsupported state are present.
- Completed the live editor gap-generate cutover slice: gap generation now attempts runtime NLE `gap_generate` dual-write, preserves Taption-style left/right silence gap rows around the generated subtitle, and falls back to the existing Taption/source-app direct gap generation whenever live STT preview rows or unsupported state are present.
- Completed the live editor caption-merge cutover slice: diamond merge now attempts runtime NLE `caption_merge` dual-write for stable final caption pairs, records a `caption_merge` `NLEEditorOperation`, reloads projected rows when safe, and falls back to the existing Taption/source-app QTextDocument merge path for STT/live preview rows, NLE rejection, or unsupported state.
- Completed the live editor caption-split cutover slice: text/smart split now attempts runtime NLE `caption_split` dual-write for stable final captions, records a `caption_split` `NLEEditorOperation`, reloads projected rows when safe, keeps Taption/source-app QTextDocument split fallback for STT/live preview rows or unsupported state, and uses snapshot-signature undo routing so delayed Qt document revision changes do not break one-step undo/redo.
- Completed the live editor candidate-confirm cutover slice: STT1/STT2 candidate confirmation now attempts runtime NLE `candidate_confirm` dual-write after Taption/source-app placement computes final rows, records a `candidate_confirm` `NLEEditorOperation`, preserves candidate-lane evidence in the undo snapshot, and falls back to the existing source-app path whenever NLE projection would alter confirmed timing/text or sees unsupported rows.
- Completed the NLE final-surface overlap guard slice. Latest artifact: `output/manual_verification/latest/nle_final_surface_overlap_guard_20260628/final_surface_overlap_guard_report.md`; final overlay/global-canvas projections repair one-frame micro-overlap to a shared boundary when possible, avoid drawing unfixable overlapped final rows together, and save/export rejects unfixable final overlap before writing an overlapped final SRT.
- Completed the NLE persistence cutover audit slice. Latest artifact: `output/manual_verification/latest/nle_persistence_cutover_audit_20260628/nle_persistence_cutover_audit.md`; runtime `NLEProjectState` hydration, legacy disk cleanliness, future-payload quarantine, and save/reopen roundtrip for the then-current `8` NLE dual-write operation families are proven, while persisted NLE disk-format cutover remains blocked by `persisted_nle_project_fields_not_approved`, `legacy_disk_shape_required_for_compatibility`, and `owner_approval_required_before_disk_format_change`.
- Completed the NLE operation identity preservation slice. Latest artifact: `output/manual_verification/latest/nle_persistence_identity_preservation_20260628/nle_persistence_cutover_audit.md`; NLE shadow projection preserves non-generic operation IDs, `candidate_confirm` maps generic `caption_1`/`caption_2` rows back to existing `subtitle_vector_*` identities, live editor block metadata carries `segment_id`, explicit `save-project` uses flushed current editor rows instead of stale project/deferred rows, and the then-current `8` NLE dual-write operation families reopen with `reopened_identity_preserved=true` while disk storage remains clean of unapproved NLE fields. Final source-app quick QA artifact: `output/manual_verification/latest/qa_suite_quick_nle_identity_save_project_fix_20260628`.
- Completed the NLE timeline canvas read/projection cutover slice. Latest artifact: `output/manual_verification/latest/nle_timeline_canvas_projection_cutover_20260628/timeline_canvas_projection_report.md`; `TimelineCanvas.update_segments(...)` now normalizes incoming rows through `nle_timeline_canvas_segments_from_editor_rows(...)`, final captions are projected through the NLE `timeline_canvas` surface, STT1/STT2/live subtitle preview lanes remain visible on the main timeline canvas, explicit silence gaps remain gap rows, global canvas remains final-only, and source-app quick QA passed at `output/manual_verification/latest/qa_suite_quick_nle_timeline_canvas_projection_20260628`.
- Completed the first NLE timeline commit-boundary mutable sync slice. Latest artifact: `output/manual_verification/latest/nle_commit_boundary_reorder_sync_20260628/reorder_sync_report.md`; Taption immediate-neighbor `center_reorder_left` / `center_reorder_right` release commits now route through runtime NLE `caption_move` dual-write with `commit_boundary=release`, `commit_source=<edge>`, final overlap `0`, global max active `1`, and legacy fallback on NLE rejection.
- Completed the second NLE timeline commit-boundary mutable sync slice. Latest artifact: `output/manual_verification/latest/nle_center_move_commit_sync_20260628/center_move_sync_report.md`; safe pure body `center` move release commits now route through runtime NLE `caption_move` dual-write with `commit_boundary=release`, `commit_source=center`, final overlap `0`, global max active `1`, and fallback on NLE rejection.
- Completed the third NLE timeline commit-boundary mutable sync slice. Latest artifact: `output/manual_verification/latest/nle_complex_center_commit_sync_20260628/complex_center_sync_report.md`; Taption-style body `center` release commits for explicit silence gap absorption and previous/next overwrite trim now route through runtime NLE `caption_move` commit adoption with `commit_mode=center_gap_absorb` or `center_overwrite_trim`, final overlap `0`, global max active `1`, STT/live preview route rejection, and fallback on NLE rejection. Source-app quick QA passed at `output/manual_verification/latest/qa_suite_quick_nle_complex_center_commit_20260628`.
- Completed the fourth NLE timeline commit-boundary mutable sync slice. Latest artifact: `output/manual_verification/latest/nle_inline_text_commit_sync_20260628/inline_text_commit_report.md`; timeline inline editor text commits now route stable final-caption text changes through runtime NLE `caption_text_edit` with `commit_boundary=release`, `commit_source=timeline_inline_text`, no timing drift, `\u2028` newline save/reopen roundtrip coverage, STT/live preview route rejection, and fallback on NLE rejection. Source-app quick QA passed at `output/manual_verification/latest/qa_suite_quick_nle_inline_text_commit_20260628`.
- Refreshed the NLE persistence identity audit after `caption_text_edit`. Latest artifact: `output/manual_verification/latest/nle_persistence_identity_preservation_inline_text_20260628/nle_persistence_cutover_audit.md`; all `9` then-current NLE dual-write operation families reopened with `reopened_identity_preserved=true`, final overlap `0`, max active `1`, and disk storage remains clean of unapproved NLE fields.
- Completed the fifth NLE timeline commit-boundary mutable sync slice. Latest artifact: `output/manual_verification/latest/nle_speaker_split_text_commit_sync_20260628/speaker_split_sync_report.md`; speaker split release commits now route stable final captions through runtime NLE `caption_text_edit` with `commit_boundary=release`, `commit_source=timeline_speaker_split`, `speaker_list` save/reopen preservation, one final multi-speaker row, STT/live preview route rejection, and QTextDocument fallback on NLE rejection. Source-app quick QA passed at `output/manual_verification/latest/qa_suite_quick_nle_speaker_split_commit_20260628`.
- Completed the sixth NLE timeline commit-boundary mutable sync slice. Latest artifact: `output/manual_verification/latest/nle_diamond_delete_commit_sync_20260628/diamond_delete_sync_report.md`; diamond drag delete release commits now route keep-left/keep-right delete-plus-resize results through runtime NLE `caption_move` commit adoption with `commit_boundary=release`, `commit_source=diamond_delete`, final overlap `0`, existing line-mismatch mapping preserved, and QTextDocument fallback on NLE rejection. Source-app quick QA passed at `output/manual_verification/latest/qa_suite_quick_nle_diamond_delete_commit_20260628`.
- Completed the seventh NLE timeline commit-boundary mutable sync slice. Latest artifact: `output/manual_verification/latest/nle_speaker_drop_commit_sync_20260628/speaker_drop_sync_report.md`; same-caption speaker-circle drag/drop release commits now route stable final captions through runtime NLE `caption_text_edit` with `commit_boundary=release`, `commit_source=timeline_speaker_drop`, ordered `speaker_list` preservation, distinct-caption NLE suppression, and QTextDocument fallback on NLE rejection. Source-app quick QA passed at `output/manual_verification/latest/qa_suite_quick_nle_speaker_drop_commit_20260628`.
- Completed the eighth NLE timeline commit-boundary mutable sync slice. Latest artifact: `output/manual_verification/latest/nle_smart_split_commit_sync_20260628/smart_split_sync_report.md`; timeline smart split release commits now route stable final captions through runtime NLE `caption_split` with `commit_boundary=release`, `commit_source=timeline_smart_split`, final overlap `0`, global max active `1`, and QTextDocument fallback on NLE rejection. Source-app quick QA passed at `output/manual_verification/latest/qa_suite_quick_nle_smart_split_commit_20260628`.
- Completed the ninth NLE timeline commit-boundary mutable sync slice. Latest artifact: `output/manual_verification/latest/nle_speaker_change_commit_sync_20260628/speaker_change_sync_report.md`; direct speaker menu changes on single-block stable final captions now route through runtime NLE `caption_text_edit` with `commit_boundary=release`, `commit_source=timeline_speaker_change`, unchanged text/timing, guarded QTextBlock shape preservation for multi-block captions, and fallback on NLE rejection. Source-app quick QA passed at `output/manual_verification/latest/qa_suite_quick_nle_speaker_change_commit_20260628`.
- Completed the tenth NLE timeline commit-boundary mutable sync slice. Latest artifact: `output/manual_verification/latest/nle_partial_range_replace_commit_sync_20260628/range_replace_report.md`; partial range replacement through `clear_segments_in_range(...)` / `insert_partial_segments(...)` now routes stable final-caption replacements through runtime NLE `caption_range_replace` with `commit_boundary=release`, `commit_source=partial_insert_range_replace`, outside-range preservation guards, final overlap `0`, global max active `1`, and legacy fallback on NLE rejection. Source-app quick QA passed at `output/manual_verification/latest/qa_suite_quick_nle_range_replace_20260628`.
- Next NLE action is to audit remaining uncovered release/commit sources. Do not write NLE mutable state on every drag pixel; only reconcile a source after proving Taption drag, magnet, gap, and no-overlap behavior again.
- Completed the NLE global canvas final-projection cutover slice: `nle_global_canvas_segments_from_editor_rows(...)` now gives the global canvas subtitle lane a final-only NLE projection while timeline canvas keeps live STT/subtitle preview rows. Latest artifact: `output/manual_verification/latest/nle_global_canvas_final_projection_20260627/global_canvas_projection_report.md`; focused guards passed with `5 passed`, global-canvas subset `9 passed`, and NLE runtime/render/snapshot set `20 passed, 4 subtests passed`.
- Completed the NLE save/export final-projection cutover slice: `nle_save_export_segments_from_editor_rows(...)` now gives externalized final SRT/cache rows a final-only NLE projection while silence gaps stay on vector-canvas gap metadata and STT1/STT2 reference tracks remain separate. Latest artifact: `output/manual_verification/latest/nle_save_export_projection_cutover_20260628/save_export_projection_report.md`; focused guards passed with `4 passed`, NLE runtime/render/export/persistence/dual-write/operation/snapshot set `44 passed, 4 subtests passed`, and project external text asset subset `1 passed, 84 deselected`.
- Completed the NLE roughcut saved-candidate render-plan cutover slice: `roughcut_state` now builds saved candidate `outputs.render_plan` through the NLE snapshot adapter path used by roughcut export/render actions, with focused legacy command/manifest parity. Latest artifact: `output/manual_verification/latest/nle_roughcut_state_render_plan_cutover_20260628/roughcut_state_render_plan_report.md`; focused guards passed with `3 passed, 35 deselected`, roughcut snapshot subset `3 passed, 16 deselected`, and NLE runtime/render/export/persistence/dual-write/operation/snapshot set `48 passed, 4 subtests passed`.
- Applied Taption's `docs/agent_communication` Jammini communication pack to this repo as documentation and role-card structure only. The physical handoff source of truth remains `.agents/sentinel/`; the local mapping is documented in `docs/agent_communication/README.md`, role cards live under `.agents/sentinel/agents/`, `.agents/sentinel/BRIEFING.md` now carries the compact current-state orientation, and `cooperation.md` includes the clean-room external instruction boundary, delegate-first/batched-queue rule, NLE parallel packet protocol, routing discipline, and unknown-cause debugging protocol.
- Added an explicit Jammini identity guard: delegated packets from this repo must name `AI Subtitle Studio` and `/Users/u_mo_c/Downloads/ai_subtitle_studio`; Taption/Taption Encoder are reference projects only unless an explicit cross-project comparison is delegated.
- Added `COMPLETED_ACTION_ITEMS.md` and moved completed action-item execution history out of `ACTION_ITEMS.md`; the active queue now keeps only remaining execution steps while completed STT latency and App Store readiness steps are archived separately.
- Tightened the completed-item separation rule: completed history stays in `COMPLETED_ACTION_ITEMS.md`, `ACTION_ITEMS.md` keeps only open work/current gates/rollback, and archive source labels use stable item titles instead of active queue numbers.
- The completed `NLE Runtime Editing Adoption: Caption Resize And Live Editor Mutation Cutover` item was removed from `ACTION_ITEMS.md`; the next active item is `STT2 / Word Precision Generation Latency Profiling And Accuracy-Preserving Trim`.
- Verified the Jammini handoff route with probes `20260627-142153`, `20260627-152654`, `20260627-153303`, `20260627-153926`, `20260627-154738`, `20260627-155406`, `20260627-160313`, `20260627-161256`, `20260627-161935`, and `20260628-025102`; these probes prove communication-health only, not runtime app behavior.

### Files Changed

- `ACTION_ITEMS.md`
- `AGENTS.md`
- `.agents/sentinel/handoff.md`
- `.agents/sentinel/handoffs/20260627-142153-watchdog-handoff-probe.md`
- `.agents/sentinel/handoffs/20260627-152654-watchdog-handoff-probe.md`
- `.agents/sentinel/handoffs/20260627-153303-watchdog-handoff-probe.md`
- `.agents/sentinel/handoffs/20260627-153926-watchdog-handoff-probe.md`
- `.agents/sentinel/handoffs/20260627-154738-watchdog-handoff-probe.md`
- `.agents/sentinel/handoffs/20260627-155406-watchdog-handoff-probe.md`
- `.agents/sentinel/handoffs/20260627-160313-watchdog-handoff-probe.md`
- `.agents/sentinel/handoffs/20260627-161256-watchdog-handoff-probe.md`
- `.agents/sentinel/handoffs/20260627-161935-watchdog-handoff-probe.md`
- `.agents/sentinel/handoffs/20260627-191600-stt2-wall-clock-stage-spans.md`
- `.agents/sentinel/handoffs/20260627-stt-accuracy-test-review.md`
- `.agents/sentinel/handoffs/20260627-212955-heydealer-nas-preflight-blocked.md`
- `core/audio/media_processor_transcribe.py`
- `core/audio/media_processor_transcribe_recheck.py`
- `core/engine/subtitle_context_refiner.py`
- `core/engine/subtitle_engine.py`
- `core/engine/subtitle_macro_chunks.py`
- `core/native_subtitle_segments.py`
- `core/project/nle_dual_write.py`
- `core/project/nle_operations.py`
- `core/project/nle_persistence_guard.py`
- `core/project/nle_projection_parity.py`
- `core/project/nle_render_export_parity.py`
- `core/project/nle_runtime_cutover.py`
- `core/project/project_format.py`
- `core/project/project_io.py`
- `core/project/project_manager.py`
- `.agents/sentinel/agents/README.md`
- `.agents/sentinel/agents/hangyeol.md`
- `.agents/sentinel/agents/seorin.md`
- `.agents/sentinel/agents/yujin.md`
- `cooperation.md`
- `docs/HANDOFF.md`
- `docs/agent_communication/README.md`
- `docs/APP_STORE_SUBMISSION_READINESS.md`
- `docs/ARCHITECTURE.md`
- `docs/FEATURE_REGISTRY.md`
- `docs/PROJECT_STATE.md`
- `docs/VALIDATION.md`
- `lesson_n_learned.md`
- `test_result.md`
- `tests/test_benchmark_mode_profiles.py`
- `tests/test_subtitle_engine_settings.py`
- `tests/test_native_subtitle_segments.py`
- `tests/test_project_nle_dual_write.py`
- `tests/test_project_nle_operations.py`
- `tests/test_project_nle_persistence_guard.py`
- `tests/test_project_nle_render_export_parity.py`
- `tests/test_project_nle_runtime_cutover.py`
- `tests/test_project_nle_snapshot.py`
- `tests/test_editor_video_context_window.py`
- `tests/test_timeline_hit_targets.py`
- `tests/test_timeline_playhead_fit.py`
- `tests/test_video_player_widget.py`
- `tests/test_verify_full_media_pipeline.py`
- `tests/test_reference_fixture_availability.py`
- `tests/test_materialize_reference_srt.py`
- `tests/test_reference_benchmark_acceptance.py`
- `tests/test_app_store_readiness_audit.py`
- `tools/benchmark_subtitle_pipeline_variants.py`
- `tools/verify_full_media_pipeline.py`
- `tools/verify_reference_fixture_availability.py`
- `tools/materialize_reference_srt.py`
- `tools/evaluate_reference_benchmark_acceptance.py`
- `tools/audit_app_store_readiness.py`
- `ui/editor/ux/editor_timeline_video.py`
- `ui/editor/ux/timeline_canvas_editing.py`
- `ui/editor/ux/timeline_subtitle_segment_editing.py`
- `ui/editor/video_player_subtitles.py`
- `output/manual_verification/latest/nle_owner_inventory_20260627/owner_inventory.md`
- `output/manual_verification/latest/nle_domain_contract_20260627/domain_contract.md`
- `output/manual_verification/latest/nle_read_only_parity_20260627/projection_parity_report.md`
- `output/manual_verification/latest/nle_operation_model_20260627/operation_model_report.md`
- `output/manual_verification/latest/nle_dual_write_pilot_20260627/gap_delete_pilot_report.md`
- `output/manual_verification/latest/nle_save_reload_compat_20260627/save_reload_compat_report.md`
- `output/manual_verification/latest/nle_render_export_parity_20260627/render_export_parity_report.md`
- `output/manual_verification/latest/nle_runtime_cutover_final_overlay_20260627/final_overlay_cutover_report.md`
- `output/manual_verification/latest/nle_cleanup_gate_audit_20260627/cleanup_gate_audit.md`
- `output/manual_verification/latest/nle_release_checkpoint_parity_20260627/release_checkpoint_parity_report.md`
- `output/manual_verification/latest/nle_phase11_cleanup_20260627/cleanup_report.md`
- `output/manual_verification/latest/cut_boundary_latency_profile_20260627/latency_profile_report.md`
- `output/manual_verification/latest/nle_caption_move_dual_write_20260627/caption_move_dual_write_report.md`
- `output/manual_verification/latest/nle_caption_resize_dual_write_20260627/caption_resize_dual_write_report.md`
- `output/manual_verification/latest/qa_suite_quick_nle_caption_resize_20260627`
- `output/manual_verification/latest/nle_live_editor_diamond_cutover_20260627/live_editor_diamond_cutover_report.md`
- `output/manual_verification/latest/nle_live_editor_boundary_resize_cutover_20260627/boundary_resize_cutover_report.md`
- `output/manual_verification/latest/nle_live_editor_caption_delete_cutover_20260627/caption_delete_cutover_report.md`
- `output/manual_verification/latest/nle_live_editor_gap_generate_cutover_20260627/gap_generate_cutover_report.md`
- `output/manual_verification/latest/qa_suite_quick_nle_live_diamond_retry_20260627`
- `output/manual_verification/latest/qa_suite_quick_nle_live_diamond_20260627`
- `output/manual_verification/latest/stt2_word_precision_wall_clock_20260627/wall_clock_stage_report.md`
- `output/manual_verification/latest/stt_high_context_diag_x5_audio_20260627/high_context_diag_report.md`
- `output/manual_verification/latest/reference_fixture_availability_20260627/reference_fixture_availability.md`
- `output/manual_verification/latest/x5_local_reference_fixture_20260627/reference_benchmark_report.md`
- `output/manual_verification/latest/x5_project_reference_180s_20260627/reference_benchmark_report.md`
- `output/manual_verification/latest/heydealer_nas_reference_preflight_20260627/reference_fixture_availability.md`
- `output/manual_verification/latest/stt_recheck_duration_diagnostics_20260627/diagnostics_report.md`
- `output/manual_verification/latest/stt_recheck_reason_breakdown_20260627/reason_breakdown_report.md`
- `output/manual_verification/latest/app_store_readiness_audit_20260627/app_store_readiness_audit.md`
- `output/manual_verification/latest/taption_segment_uiux_parity_20260627/checklist.md`
- `output/manual_verification/latest/high_context_keep_cache_20260627/keep_cache_report.md`
  - `output/manual_verification/latest/high_context_keep_cache_20260627/synthetic_fixture/fixture_report.md`
  - `output/manual_verification/latest/high_context_keep_cache_20260627/synthetic_keep_cache_summary.json`

### Validation

- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_native_subtitle_segments.py tests/test_native_subtitle_stt_segments.py tests/test_video_player_widget.py` -> `87 passed`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_segment_reload.py -k "stt_candidate or live_stt_preview or stt_preview"` -> `32 passed, 56 deselected`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_hit_targets.py -k "one_word_arrow or center_segment_move or boundary_release or stt_candidate"` -> `10 passed, 138 deselected`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py -k "single_gap or center_drag or resize_overwrites"` -> `4 passed, 144 deselected`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_hit_targets.py -k "reorders_across_adjacent or reorder_release or center_drag_can_move_across"` -> `3 passed, 147 deselected`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py -k "center_reorder_commit or center_drag_right_preserves or center_drag_left_preserves"` -> `3 passed, 146 deselected`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_hit_targets.py tests/test_app_command_bridge.py -k "drag or gap or magnet or stt_candidate or boundary_release or one_word_arrow or reorder"` -> `65 passed, 161 deselected`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py tests/test_subtitle_live_editor_feed_facade.py` -> `152 passed`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py -k "center_reorder or center_drag or single_gap or resize_overwrites"` -> `5 passed, 144 deselected`
- `./venv/bin/python -m py_compile ui/editor/ux/timeline_canvas_editing.py ui/editor/ux/timeline_subtitle_segment_editing.py ui/editor/ux/editor_timeline_video.py tests/test_timeline_hit_targets.py tests/test_timeline_playhead_fit.py` -> pass
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m py_compile core/audio/media_processor_transcribe_recheck.py tools/verify_full_media_pipeline.py tests/test_media_processor_overlap.py tests/test_verify_full_media_pipeline.py` -> pass
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_media_processor_overlap.py -k "word_precision_recheck_uses_user_selected_stt1_model or selective_ensemble_runs_stt2_only_for_low_score_ranges"` -> `2 passed, 103 deselected`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_verify_full_media_pipeline.py -k "stage_wall_clock or repeat_summary_rolls_up_accuracy_preserving_stt2_metrics"` -> `2 passed, 13 deselected`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/benchmark_subtitle_pipeline_variants.py --suite modes --variants mode_high --media "/Volumes/photo/.../헤이딜러_최종.MP4" --reference-srt "/Volumes/photo/.../헤이딜러_최종.srt" --start-sec 0 --duration-sec 180 --keep-artifacts` -> pass, accepted by `tools/evaluate_reference_benchmark_acceptance.py`; latest reason breakdown run `.codex_work/benchmarks/subtitle_pipeline_variants/20260627_223426/benchmark_results.md`
- `./venv/bin/python -m py_compile ui/editor/editor_segments_timeline_context.py ui/editor/editor_segments_stt_selection_flow.py ui/editor/video_player_subtitles.py core/native_subtitle_segments.py tools/benchmark_subtitle_pipeline_variants.py ui/editor/ux/timeline_subtitle_segment_editing.py ui/editor/ux/timeline_canvas_editing.py tests/test_timeline_playhead_fit.py tests/test_timeline_hit_targets.py tests/test_video_player_widget.py tests/test_native_subtitle_segments.py tests/test_benchmark_mode_profiles.py` -> pass
- `git diff --check -- .` -> pass
- `AI_SUBTITLE_STUDIO_QA_USE_SOURCE=1 ./venv/bin/python tools/qa_suite_runner.py quick` -> pass, `failed_count=0`
- `tools/jammini_watchdog.sh --status` -> route visible
- `tools/jammini_watchdog.sh --handoff-probe` -> `20260627-152654`, handoff file visible, first line `DEX_REVIEW_READY`
- `tools/jammini_watchdog.sh --handoff-probe` -> `20260627-153303`, handoff file visible, first line `DEX_REVIEW_READY`
- `tools/jammini_watchdog.sh --handoff-probe` -> `20260627-153926`, handoff file visible, first line `DEX_REVIEW_READY`
- `tools/jammini_watchdog.sh --handoff-probe` -> `20260627-154738`, handoff file visible, first line `DEX_REVIEW_READY`
- `tools/jammini_watchdog.sh --handoff-probe` -> `20260627-155406`, handoff file visible, first line `DEX_REVIEW_READY`
- `./venv/bin/python -m py_compile core/project/nle_projection_parity.py tests/test_project_nle_snapshot.py` -> pass
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_snapshot.py -k "read_only_projection_parity or compatibility_characterization or direct_srt or roughcut_exact_join"` -> `5 passed, 10 deselected`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_snapshot.py tests/test_roughcut_v2_output_compat.py` -> `19 passed, 4 subtests passed`
- `git diff --check -- .` -> pass
- `./venv/bin/python -m py_compile core/project/nle_operations.py tests/test_project_nle_operations.py` -> pass
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_operations.py` -> `5 passed`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_operations.py tests/test_project_nle_snapshot.py tests/test_roughcut_v2_output_compat.py` -> `24 passed, 4 subtests passed`
- `git diff --check -- .` -> pass
- `./venv/bin/python -m py_compile core/project/nle_dual_write.py tests/test_project_nle_dual_write.py` -> pass
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_dual_write.py` -> `3 passed`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_dual_write.py tests/test_project_nle_operations.py tests/test_project_nle_snapshot.py tests/test_roughcut_v2_output_compat.py` -> `27 passed, 4 subtests passed`
- `tools/jammini_watchdog.sh --handoff-probe` -> `20260627-160313`, handoff file visible, first line `DEX_REVIEW_READY`
- `./venv/bin/python -m py_compile core/project/nle_persistence_guard.py core/project/project_format.py core/project/project_io.py core/project/project_manager.py tests/test_project_nle_persistence_guard.py` -> pass
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_persistence_guard.py` -> `4 passed`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_persistence_guard.py tests/test_project_nle_dual_write.py tests/test_project_nle_operations.py tests/test_project_nle_snapshot.py tests/test_roughcut_v2_output_compat.py` -> `31 passed, 4 subtests passed`
- `tools/jammini_watchdog.sh --handoff-probe` -> `20260627-161256`, handoff file visible, first line `DEX_REVIEW_READY`
- `./venv/bin/python -m py_compile core/project/nle_render_export_parity.py tests/test_project_nle_render_export_parity.py` -> pass
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_render_export_parity.py` -> `2 passed`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_render_export_parity.py tests/test_project_nle_persistence_guard.py tests/test_project_nle_dual_write.py tests/test_project_nle_operations.py tests/test_project_nle_snapshot.py tests/test_roughcut_v2_output_compat.py` -> `33 passed, 4 subtests passed`
- `tools/jammini_watchdog.sh --handoff-probe` -> `20260627-161935`, handoff file visible, first line `DEX_REVIEW_READY`
- `./venv/bin/python -m py_compile core/project/nle_runtime_cutover.py ui/editor/editor_segments_timeline_context.py tests/test_project_nle_runtime_cutover.py tests/test_editor_video_context_window.py` -> pass
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_runtime_cutover.py tests/test_editor_video_context_window.py -k "nle_runtime or video_context or live_preview"` -> `10 passed`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_runtime_cutover.py tests/test_editor_video_context_window.py tests/test_video_player_widget.py tests/test_project_nle_render_export_parity.py tests/test_project_nle_persistence_guard.py tests/test_project_nle_dual_write.py tests/test_project_nle_operations.py tests/test_project_nle_snapshot.py tests/test_roughcut_v2_output_compat.py` -> `123 passed, 4 subtests passed`
- `AI_SUBTITLE_STUDIO_QA_USE_SOURCE=1 ./venv/bin/python tools/qa_suite_runner.py quick` -> first run `output/manual_verification/latest/qa_suite_quick_20260627_162452` failed at `open_project` with `app_unreachable`; immediate rerun `output/manual_verification/latest/qa_suite_quick_20260627_162641` passed with `failed_count=0`
- `git diff --check -- .` -> pass
- Phase 9 cleanup gate audit over `ACTION_ITEMS.md`, `AGENTS.md`, `docs/HANDOFF.md`, `docs/PROJECT_STATE.md`, `test_result.md`, and phase 8 artifacts -> cleanup blocked; no code deletion performed
- Phase 10 checkpoint A:
  - `./venv/bin/python -m py_compile core/project/nle_runtime_cutover.py core/project/nle_render_export_parity.py core/project/nle_persistence_guard.py ui/editor/editor_segments_timeline_context.py tests/test_project_nle_runtime_cutover.py tests/test_project_nle_render_export_parity.py tests/test_project_nle_persistence_guard.py tests/test_editor_video_context_window.py tests/test_video_player_widget.py` -> pass
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_runtime_cutover.py tests/test_editor_video_context_window.py tests/test_video_player_widget.py tests/test_project_nle_render_export_parity.py tests/test_project_nle_persistence_guard.py tests/test_project_nle_dual_write.py tests/test_project_nle_operations.py tests/test_project_nle_snapshot.py tests/test_roughcut_v2_output_compat.py` -> `123 passed, 4 subtests passed`
  - `AI_SUBTITLE_STUDIO_QA_USE_SOURCE=1 ./venv/bin/python tools/qa_suite_runner.py quick --output-dir output/manual_verification/latest/nle_release_checkpoint_parity_20260627/checkpoint_a_quick` -> pass, `failed_count=0`
- Phase 10 checkpoint B:
  - `./venv/bin/python -m py_compile core/project/nle_runtime_cutover.py core/project/nle_render_export_parity.py core/project/nle_persistence_guard.py ui/editor/editor_segments_timeline_context.py tests/test_project_nle_runtime_cutover.py tests/test_project_nle_render_export_parity.py tests/test_project_nle_persistence_guard.py tests/test_editor_video_context_window.py tests/test_video_player_widget.py` -> pass
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_runtime_cutover.py tests/test_editor_video_context_window.py tests/test_video_player_widget.py tests/test_project_nle_render_export_parity.py tests/test_project_nle_persistence_guard.py tests/test_project_nle_dual_write.py tests/test_project_nle_operations.py tests/test_project_nle_snapshot.py tests/test_roughcut_v2_output_compat.py` -> `123 passed, 4 subtests passed`
  - `AI_SUBTITLE_STUDIO_QA_USE_SOURCE=1 ./venv/bin/python tools/qa_suite_runner.py quick --output-dir output/manual_verification/latest/nle_release_checkpoint_parity_20260627/checkpoint_b_quick` -> pass, `failed_count=0`
- Phase 11 cleanup audit found no proven-dead legacy write path; no app code deletion performed.
- Phase 11 post-cleanup-decision validation:
  - `./venv/bin/python -m py_compile core/project/nle_runtime_cutover.py core/project/nle_render_export_parity.py core/project/nle_persistence_guard.py ui/editor/editor_segments_timeline_context.py tests/test_project_nle_runtime_cutover.py tests/test_project_nle_render_export_parity.py tests/test_project_nle_persistence_guard.py tests/test_editor_video_context_window.py tests/test_video_player_widget.py` -> pass
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_runtime_cutover.py tests/test_editor_video_context_window.py tests/test_video_player_widget.py tests/test_project_nle_render_export_parity.py tests/test_project_nle_persistence_guard.py tests/test_project_nle_dual_write.py tests/test_project_nle_operations.py tests/test_project_nle_snapshot.py tests/test_roughcut_v2_output_compat.py` -> `123 passed, 4 subtests passed`
  - `AI_SUBTITLE_STUDIO_QA_USE_SOURCE=1 ./venv/bin/python tools/qa_suite_runner.py quick --output-dir output/manual_verification/latest/nle_phase11_cleanup_20260627/quick_after_cleanup` -> pass, `failed_count=0`
- Cut-boundary latency profile closeout:
  - `./venv/bin/python -m py_compile tools/verify_full_media_pipeline.py tests/test_verify_full_media_pipeline.py` -> pass
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_verify_full_media_pipeline.py` -> `10 passed`
  - Non-profile HeyDealer 180s repeat -> pipeline elapsed `[63.911, 59.479]`, avg `61.695s`, raw/final `58/55`, pass
  - Profile diagnostic HeyDealer 180s -> pipeline elapsed `64.514s`, cut-boundary top cumulative `0.000602s`, confirmed split/snap `0.000525s`, pass
  - Reference-scored HeyDealer 180s `mode_high` -> elapsed `63.617s`, raw/final `58/56`, quality `81.335`, timing MAE `1.5958s`, final overlap `0`, `stable_for_save_reopen=true`, `stable_for_global_canvas=true`
- NLE caption move dual-write slice:
  - `./venv/bin/python -m py_compile core/project/nle_dual_write.py tests/test_project_nle_dual_write.py` -> pass
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_dual_write.py` -> `6 passed`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_dual_write.py tests/test_project_nle_operations.py tests/test_project_nle_snapshot.py tests/test_roughcut_v2_output_compat.py` -> `30 passed, 4 subtests passed`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py tests/test_timeline_hit_targets.py -k "center_reorder or reorder_release or center_drag_reorders"` -> `3 passed, 296 deselected`
- NLE caption resize dual-write slice:
  - `./venv/bin/python -m py_compile core/project/nle_dual_write.py tests/test_project_nle_dual_write.py` -> pass
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_dual_write.py` -> `10 passed`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_dual_write.py tests/test_project_nle_operations.py tests/test_project_nle_snapshot.py tests/test_project_nle_persistence_guard.py tests/test_project_nle_runtime_cutover.py tests/test_project_nle_render_export_parity.py` -> `38 passed, 4 subtests passed`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py -k "resize or diamond"` -> `23 passed, 126 deselected`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_hit_targets.py tests/test_app_command_bridge.py -k "drag or gap or magnet or stt_candidate"` -> `63 passed, 163 deselected`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py tests/test_subtitle_live_editor_feed_facade.py` -> `152 passed`
  - `AI_SUBTITLE_STUDIO_QA_USE_SOURCE=1 ./venv/bin/python tools/qa_suite_runner.py quick --output-dir output/manual_verification/latest/qa_suite_quick_nle_caption_resize_20260627` -> pass, `failed_count=0`
- NLE live editor diamond cutover slice:
  - `./venv/bin/python -m py_compile ui/editor/ux/editor_timeline_video.py tests/test_timeline_playhead_fit.py` -> pass
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py -k "diamond_resize"` -> `4 passed, 148 deselected`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py -k "resize or diamond"` -> `26 passed, 126 deselected`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_dual_write.py tests/test_project_nle_operations.py tests/test_project_nle_snapshot.py tests/test_project_nle_persistence_guard.py tests/test_project_nle_runtime_cutover.py tests/test_project_nle_render_export_parity.py` -> `38 passed, 4 subtests passed`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_hit_targets.py tests/test_app_command_bridge.py -k "drag or gap or magnet or stt_candidate"` -> `63 passed, 163 deselected`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py tests/test_subtitle_live_editor_feed_facade.py` -> `155 passed`
  - first quick QA `output/manual_verification/latest/qa_suite_quick_nle_live_diamond_20260627` failed at `merge_diamond`; root cause was a one-frame-ish split row collapsing under project floor-frame normalization.
  - retry quick QA `AI_SUBTITLE_STUDIO_QA_USE_SOURCE=1 ./venv/bin/python tools/qa_suite_runner.py quick --output-dir output/manual_verification/latest/qa_suite_quick_nle_live_diamond_retry_20260627` -> pass, `failed_count=0`
- NLE live editor boundary resize cutover slice:
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m py_compile ui/editor/ux/editor_timeline_video.py tests/test_timeline_playhead_fit.py` -> pass
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py -k "square_left_resize_routes_live_editor_mutation or square_right_resize_routes_live_editor_mutation or square_resize_falls_back or diamond_resize_routes_live_editor_mutation"` -> `4 passed, 151 deselected`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py -k "resize or diamond or single_gap or center_drag"` -> `32 passed, 123 deselected`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_dual_write.py tests/test_project_nle_operations.py tests/test_project_nle_snapshot.py tests/test_project_nle_persistence_guard.py tests/test_project_nle_runtime_cutover.py tests/test_project_nle_render_export_parity.py` -> `38 passed, 4 subtests passed`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_hit_targets.py tests/test_app_command_bridge.py -k "drag or gap or magnet or stt_candidate"` -> `63 passed, 163 deselected`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py tests/test_subtitle_live_editor_feed_facade.py` -> `158 passed`
  - `git diff --check -- ui/editor/ux/editor_timeline_video.py tests/test_timeline_playhead_fit.py` -> pass
- Reference fixture availability preflight:
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m py_compile tools/verify_reference_fixture_availability.py tests/test_reference_fixture_availability.py` -> pass
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_reference_fixture_availability.py` -> `3 passed`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/verify_reference_fixture_availability.py --fallback-media "output/_audio_fingerprint/헤이딜러_최종_2c274c4ab434764a8546/헤이딜러_최종_cleaned.wav" --output-dir output/manual_verification/latest/reference_fixture_availability_20260627` -> expected exit `2`; missing reference media and SRT, fallback media available
- X5 local reference smoke:
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m py_compile tools/materialize_reference_srt.py tests/test_materialize_reference_srt.py tools/verify_reference_fixture_availability.py tests/test_reference_fixture_availability.py` -> pass
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_materialize_reference_srt.py tests/test_reference_fixture_availability.py` -> `5 passed`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/materialize_reference_srt.py --reference-json .codex_work/bench/x5_120_3s_180_3s_reference.json --output-srt output/manual_verification/latest/x5_local_reference_fixture_20260627/x5_120_3s_180_3s_reference.srt --report-json output/manual_verification/latest/x5_local_reference_fixture_20260627/materialized_reference_report.json` -> row_count `26`
  - X5 local preflight -> `ready_for_reference_scored_benchmark=true`, clipped reference segments `26`
  - X5 local `mode_high` reference benchmark -> elapsed `29.831s`, raw/final `28/23`, quality `80.914`, timing MAE `0.5608s`, final invalid/non-monotonic/overlap `0/0/0`, global max active `1`
- X5 project-reference 180s acceptance:
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m py_compile tools/evaluate_reference_benchmark_acceptance.py tests/test_reference_benchmark_acceptance.py tools/materialize_reference_srt.py tests/test_materialize_reference_srt.py tools/verify_reference_fixture_availability.py tests/test_reference_fixture_availability.py` -> pass
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_reference_benchmark_acceptance.py tests/test_materialize_reference_srt.py tests/test_reference_fixture_availability.py` -> `8 passed`
  - Accepted X5 front-reference run -> elapsed `70.383s`, raw/final/reference `43/50/67`, quality `76.387`, text `90.767`, timing MAE `1.5457s`, final invalid/non-monotonic/overlap `0/0/0`, global max active `1`
  - Rejected X5 back-reference mismatch -> quality `23.234`, text `4.756`, timing MAE `3.3362s`, rejected for quality/text/timing floors
- NAS HeyDealer owner-required 3-minute preflight:
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/verify_reference_fixture_availability.py --media "/Volumes/photo/22_유튜브영상_개인/[20260209]헤이딜러광고/헤이딜러_최종.MP4" --reference-srt "/Volumes/photo/22_유튜브영상_개인/[20260209]헤이딜러광고/헤이딜러_최종.srt" --fallback-media "output/_audio_fingerprint/헤이딜러_최종_2c274c4ab434764a8546/헤이딜러_최종_cleaned.wav" --start-sec 0 --duration-sec 180 --output-dir output/manual_verification/latest/heydealer_nas_reference_preflight_20260627` -> expected exit `2`; media/SRT missing, fallback available, not used for acceptance.
- STT2/word precision wall-clock stage-span slice:
  - `./venv/bin/python -m py_compile core/audio/media_processor_transcribe.py core/audio/media_processor_transcribe_recheck.py tools/benchmark_subtitle_pipeline_variants.py tools/verify_full_media_pipeline.py` -> pass
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_verify_full_media_pipeline.py tests/test_benchmark_mode_profiles.py` -> `46 passed`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_stt_ensemble.py tests/test_subtitle_quality_models.py -k "word_precision or stt_anchor or vad_stt_timing_consensus or selective"` -> `6 passed, 48 deselected`
  - HeyDealer 180s non-reference wall-clock probe -> elapsed `65.222s`, raw/final `58/55`, final overlap `0`, `stable_for_save_reopen=true`, global `max_active_segments=1`, STT2 selected `37`, word precision `14`, memory pressure `critical`; stage spans STT1 `18.162010s`, STT2 `14.360250s`, word precision `12.489603s`, VAD/STT consensus `0.000227s`, subtitle postprocess `20.108474s`
  - HeyDealer 180s reference-scored benchmark -> elapsed `65.824s`, raw/final `58/56`, quality `81.335`, text `94.267`, timing MAE `1.5958s`, final overlap `0`, `stable_for_save_reopen=true`, global `max_active_segments=1`; stage spans STT1 `19.519015s`, STT2 `14.229755s`, word precision `12.560951s`, VAD/STT consensus `0.000222s`, subtitle postprocess `19.406983s`
- STT2/word precision zero-candidate LLM defer trim:
  - `./venv/bin/python -m py_compile core/engine/subtitle_engine.py tests/test_subtitle_engine_settings.py` -> pass
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_subtitle_engine_settings.py -k "macro_gate_zero_llm_rows or batches_llm_into_macro_chunks or llm_confidence_gate_skips"` -> `4 passed, 79 deselected`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_subtitle_engine_settings.py -k "llm or macro or gate"` -> `17 passed, 66 deselected`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_verify_full_media_pipeline.py tests/test_benchmark_mode_profiles.py` -> `46 passed`
  - HeyDealer 180s non-profile repeat -> pipeline elapsed `[65.317, 61.873]`, avg `63.595s`, raw/final `58/55`, final overlap `0`, `stable_for_save_reopen=true`, global `max_active_segments=1`, STT2 selected `37`, word precision `14`, memory pressure `critical`
  - HeyDealer 180s profile diagnostic -> pipeline elapsed `65.057s`, raw/final `58/55`, final overlap `0`, `stable_for_save_reopen=true`, global `max_active_segments=1`, cut-boundary top cumulative `0.000941s`
  - HeyDealer 180s reference-scored benchmark -> elapsed `66.007s`, raw/final `58/56`, quality `81.335`, text `94.267`, timing MAE `1.5958s`, final overlap `0`, `stable_for_save_reopen=true`, global `max_active_segments=1`; subtitle postprocess `12.518010s`, word precision `20.851735s`
- STT2/word precision rejected High context-boundary batch candidate:
  - temporary focused candidate guards -> `tests/test_subtitle_context_refiner.py` `6 passed`; macro LLM focused subset `4 passed, 79 deselected`
  - HeyDealer 180s non-profile repeat with candidate -> pipeline elapsed `[69.223, 67.564]`, avg `68.393s`, raw/final `58/55`, final overlap `0`, `stable_for_save_reopen=true`, global `max_active_segments=1`, memory pressure `critical`
  - HeyDealer 180s reference-scored benchmark with candidate -> elapsed `64.222s`, raw/final `58/56`, quality `81.316`, text `94.241`, timing MAE `1.5958s`, segmentation `87.812`, final overlap `0`, `stable_for_save_reopen=true`; subtitle postprocess `9.879991s`
  - decision -> rejected/reverted because quality, text, and segmentation drifted below the accepted baseline.
  - rollback validation -> touched Python `py_compile` pass; `tests/test_subtitle_context_refiner.py` `4 passed`; accepted LLM defer subset `4 passed, 79 deselected`; verifier/benchmark guard `46 passed`; `git diff --check -- .` pass.
- STT2/word precision substage timing instrumentation:
  - touched Python `py_compile` -> pass
  - focused guards -> STT recheck service `3 passed, 35 deselected`; benchmark stage summary `1 passed, 30 deselected`; verifier stage/repeat summary `2 passed, 13 deselected`
  - broader guards -> verifier/benchmark `46 passed`; STT recheck/media overlap subset `46 passed, 96 deselected`; `git diff --check -- .` pass
  - local 60s reference smoke -> `.codex_work/benchmarks/subtitle_pipeline_variants/20260627_200405/benchmark_results.json`, elapsed `28.641s`, raw/final `2/2`, final overlap `0`, stable save/reopen true, global max active `1`
  - substage result -> STT2 total `11.258246s` / collect `11.201352s`; word precision total `4.368781s` / collect `4.304654s`; prepare and annotation were each below `0.1s`.
- STT High context-boundary diagnostics instrumentation:
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m py_compile core/engine/subtitle_context_refiner.py core/engine/subtitle_engine.py tools/benchmark_subtitle_pipeline_variants.py tools/verify_full_media_pipeline.py tests/test_subtitle_context_refiner.py tests/test_benchmark_mode_profiles.py tests/test_verify_full_media_pipeline.py` -> pass
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_subtitle_context_refiner.py tests/test_verify_full_media_pipeline.py -k "context_refiner or stage_wall_clock or repeat_summary"` -> `7 passed, 13 deselected`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_benchmark_mode_profiles.py -k "run_postprocess or stage_wall_clock_summary"` -> `3 passed, 29 deselected`
  - cached X5 audio 180s verifier -> `output/manual_verification/latest/stt_high_context_diag_x5_audio_20260627/tinyping_full_verify.json`, pipeline `74.919s`, raw/final `43/50`, final invalid/non-monotonic/overlap `0/0/0`, stable save/reopen true, global max active `1`, high-context candidate/call/changed `4/4/0`, failed calls `0`, elapsed `32.230357s`
  - `git diff --check -- core/engine/subtitle_context_refiner.py core/engine/subtitle_engine.py tools/benchmark_subtitle_pipeline_variants.py tools/verify_full_media_pipeline.py tests/test_subtitle_context_refiner.py tests/test_benchmark_mode_profiles.py tests/test_verify_full_media_pipeline.py` -> pass
- High context keep-cache candidate:
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m py_compile core/engine/subtitle_context_refiner.py core/runtime/config.py tools/benchmark_subtitle_pipeline_variants.py tools/verify_full_media_pipeline.py tests/test_subtitle_context_refiner.py tests/test_verify_full_media_pipeline.py tests/test_benchmark_mode_profiles.py` -> pass
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_subtitle_context_refiner.py` -> `8 passed`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_verify_full_media_pipeline.py -k "stage_wall_clock or repeat_summary_rolls_up_accuracy_preserving_stt2_metrics"` -> `2 passed, 13 deselected`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_benchmark_mode_profiles.py -k "parse_setting_overrides"` -> `1 passed, 32 deselected`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_benchmark_mode_profiles.py -k "parse_setting_overrides or cli_setting_overrides"` -> `2 passed, 32 deselected`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_subtitle_context_refiner.py tests/test_verify_full_media_pipeline.py tests/test_benchmark_mode_profiles.py -k "context_refiner or stage_wall_clock or repeat_summary_rolls_up_accuracy_preserving_stt2_metrics or parse_setting_overrides or cli_setting_overrides"` -> `13 passed, 44 deselected`
  - Generated fixture preflight -> ready, duration `180.583s`, reference rows `54`
  - First write benchmark `.codex_work/benchmarks/subtitle_pipeline_variants/20260627_231459/benchmark_results.json` -> elapsed `144.476s`, raw/final/reference `54/54/54`, quality/text/timing `80.153/91.676/1.437s`, final invalid/non-monotonic/overlap `0/0/0`, global max active `1`, High context calls/cache hit-miss-write `8/0-8-8`, accepted `true`
  - Second cache-hit benchmark `.codex_work/benchmarks/subtitle_pipeline_variants/20260627_231734/benchmark_results.json` -> elapsed `83.281s`, same quality/final gates, High context calls/cache hit-miss-write `0/8-0-0`, High context elapsed `0.003326s`, accepted `true`
  - NAS note: owner said NAS was off, so no NAS cache-hit acceptance was run in this slice.
- Mac App Store readiness audit:
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m py_compile tools/audit_app_store_readiness.py tests/test_app_store_readiness_audit.py` -> pass
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_app_store_readiness_audit.py` -> `3 passed`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_app_store_readiness.py --output-dir output/manual_verification/latest/app_store_readiness_audit_20260627` -> `local_packaging_ready=true`, `app_store_submission_ready=false`, blocker count `14`

### Artifacts

- Quick QA: `output/manual_verification/latest/qa_suite_quick_20260627_141230`
- Taption segment UI/UX parity checklist: `output/manual_verification/latest/taption_segment_uiux_parity_20260627/checklist.md`
- NLE phase 1 owner inventory: `output/manual_verification/latest/nle_owner_inventory_20260627/owner_inventory.md`
- NLE phase 2 domain contract: `output/manual_verification/latest/nle_domain_contract_20260627/domain_contract.md`
- NLE phase 3 read-only projection parity: `output/manual_verification/latest/nle_read_only_parity_20260627/projection_parity_report.md`
- NLE phase 4 operation model: `output/manual_verification/latest/nle_operation_model_20260627/operation_model_report.md`
- NLE phase 5 dual-write pilot: `output/manual_verification/latest/nle_dual_write_pilot_20260627/gap_delete_pilot_report.md`
- NLE phase 6 save/reload compatibility: `output/manual_verification/latest/nle_save_reload_compat_20260627/save_reload_compat_report.md`
- NLE phase 7 render/export parity: `output/manual_verification/latest/nle_render_export_parity_20260627/render_export_parity_report.md`
- NLE phase 8 final-overlay runtime cutover: `output/manual_verification/latest/nle_runtime_cutover_final_overlay_20260627/final_overlay_cutover_report.md`
- NLE phase 9 cleanup gate audit: `output/manual_verification/latest/nle_cleanup_gate_audit_20260627/cleanup_gate_audit.md`
- NLE phase 10 release checkpoint parity proof: `output/manual_verification/latest/nle_release_checkpoint_parity_20260627/release_checkpoint_parity_report.md`
- NLE phase 11 cleanup/no-op closeout: `output/manual_verification/latest/nle_phase11_cleanup_20260627/cleanup_report.md`
- NLE phase 11 quick QA: `output/manual_verification/latest/nle_phase11_cleanup_20260627/quick_after_cleanup`
- Cut-boundary latency closeout: `output/manual_verification/latest/cut_boundary_latency_profile_20260627/latency_profile_report.md`
- Cut-boundary profile diagnostic: `output/manual_verification/latest/cut_boundary_latency_profile_20260627/profile_diagnostic/function_profile_cut_boundary_summary.json`
- STT2/word precision latency closeout: `output/manual_verification/latest/stt2_word_precision_latency_20260627/latency_profile_report.md`
- STT2/word precision generation profile diagnostic: `output/manual_verification/latest/stt2_word_precision_latency_20260627/profile_diagnostic/function_profile_generation_summary.json`
- STT2/word precision wall-clock stage report: `output/manual_verification/latest/stt2_word_precision_wall_clock_20260627/wall_clock_stage_report.md`
- STT2/word precision wall-clock non-reference probe: `output/manual_verification/latest/stt2_word_precision_wall_clock_20260627/wall_clock_probe/tinyping_full_verify.json`
- STT2/word precision zero-candidate LLM defer report: `output/manual_verification/latest/stt2_word_precision_llm_defer_20260627/llm_defer_report.md`
- STT2/word precision rejected context-boundary batch report: `output/manual_verification/latest/stt2_word_precision_context_batch_20260627/context_batch_rejection_report.md`
- STT2/word precision substage timing report: `output/manual_verification/latest/stt2_word_precision_substage_timing_20260627/substage_timing_report.md`
- STT High context-boundary diagnostics report: `output/manual_verification/latest/stt_high_context_diag_x5_audio_20260627/high_context_diag_report.md`
- STT High context-boundary diagnostics X5 audio probe: `output/manual_verification/latest/stt_high_context_diag_x5_audio_20260627/tinyping_full_verify.json`
- NAS HeyDealer owner-required 3-minute preflight: `output/manual_verification/latest/heydealer_nas_reference_preflight_20260627/reference_fixture_availability.md`
- Mac App Store readiness audit: `output/manual_verification/latest/app_store_readiness_audit_20260627/app_store_readiness_audit.md`
- STT accuracy test QE review: `.agents/sentinel/handoffs/20260627-stt-accuracy-test-review.md`
- Latest HeyDealer reference-scored benchmark: `.codex_work/benchmarks/subtitle_pipeline_variants/20260627_192926/benchmark_results.json`
- NLE caption move dual-write: `output/manual_verification/latest/nle_caption_move_dual_write_20260627/caption_move_dual_write_report.md`
- NLE caption resize dual-write: `output/manual_verification/latest/nle_caption_resize_dual_write_20260627/caption_resize_dual_write_report.md`
- NLE caption resize quick QA: `output/manual_verification/latest/qa_suite_quick_nle_caption_resize_20260627`
- NLE live editor diamond cutover: `output/manual_verification/latest/nle_live_editor_diamond_cutover_20260627/live_editor_diamond_cutover_report.md`
- NLE live editor boundary resize cutover: `output/manual_verification/latest/nle_live_editor_boundary_resize_cutover_20260627/boundary_resize_cutover_report.md`
- NLE live editor caption split cutover: `output/manual_verification/latest/nle_live_editor_caption_split_cutover_20260628/caption_split_cutover_report.md`
- NLE caption split quick QA: `output/manual_verification/latest/qa_suite_quick_nle_caption_split_20260628`
- NLE live editor diamond quick QA pass: `output/manual_verification/latest/qa_suite_quick_nle_live_diamond_retry_20260627`
- NLE live editor diamond first failed quick QA: `output/manual_verification/latest/qa_suite_quick_nle_live_diamond_20260627`
- HeyDealer reference-scored benchmark: `.codex_work/benchmarks/subtitle_pipeline_variants/20260627_180138/benchmark_results.json`
- Latest quick QA: `output/manual_verification/latest/qa_suite_quick_20260627_162641`
- Historical HeyDealer 180s proof remains at `.codex_work/benchmarks/subtitle_pipeline_variants/20260627_031030/benchmark_results.json`.
- NAS-on current HeyDealer preflight: `output/manual_verification/latest/nas_on_current_preflight_20260628/reference_fixture_availability.md`
- NAS-on current HeyDealer acceptance: `output/manual_verification/latest/nas_on_current_heydealer_20260628/acceptance/reference_benchmark_acceptance.md`
- NAS-on current HeyDealer timeout audit: `output/manual_verification/latest/stt_worker_timeout_compare_nas_on_current_20260628/stt_worker_timeout_audit.md`

### Current State

- `ACTION_ITEMS.md` has two active items:
  - `STT2 / Word Precision Generation Latency Profiling And Accuracy-Preserving Trim`
  - `Mac App Store Submission Readiness`
- NLE runtime editing adoption is no longer an active queue item. Evidence remains in `test_result.md`, this handoff, `COMPLETED_ACTION_ITEMS.md`, and the NLE live editor cutover artifacts.
- Taption segment UI/UX parity completion is no longer an active queue item. Evidence remains in `test_result.md` and the checklist artifact.
- Full NLE transition is complete and no longer an active queue item. Phase 11 removed no app code because there was no proven-dead legacy write path from the final-overlay read/provider cutover.
- Cut-boundary latency profiling is complete and did not produce a safe runtime trim. STT2/word precision wall-clock stage spans are available, the first zero-candidate LLM defer trim is applied, the High context-boundary batch candidate is rejected/reverted, STT2/word precision substage timing now shows collect dominates prepare/annotation on the local smoke, and High context-boundary diagnostics now separate candidate/call/change counts from elapsed time. A strict High context keep/no-correction cache candidate is implemented and accepted on the owner-approved generated 3-minute fixture; real-media backfill remains useful when NAS is available.
- App Store readiness is a planning track only until the owner explicitly asks to run packaging, signing, notarization, upload, or DMG steps. Current non-destructive audit says the packaging skeleton and required entitlements are present, but submission is blocked by missing signed `.app`, signed `.pkg`, sandbox smoke, App Store Connect validation, signing identities, and owner metadata.
- Subtitle quality policy, STT2, LLM, LoRA, VAD, cut-boundary policy, model selection, save format, release, tag, push, packaging, and DMG behavior were not changed.
- STT1/STT2 candidate rows are still preserved for review/diagnostics, but the video subtitle overlay filters them out when final rows exist.
- Latest candidate-confirm cutover evidence: `output/manual_verification/latest/nle_live_editor_candidate_confirm_cutover_20260628/candidate_confirm_cutover_report.md`; source-app quick QA artifact: `output/manual_verification/latest/qa_suite_quick_nle_candidate_confirm_20260628`.

### Remaining Risk

- No live manual screenshot/video proof was captured for the Taption parity patch; coverage is offscreen widget/unit tests plus source-app quick QA.
- The Taption parity patch is source-app behavior parity only. It does not copy Swift code or add new visible UI labels/menus.
- The phase 5 pilot proves only `gap_delete` dual-write routing. It is not broad runtime cutover proof, and additional operation families must stay behind projection/adapter parity gates.
- Phase 6 proves persistence guard behavior only. It does not approve persisted NLE project fields or render/export cutover.
- Phase 7 proves read-only render/export parity only. It does not switch any runtime surface to NLE ownership.
- Phase 8 switches only the normal final video overlay provider. It is not a timeline/global-canvas/save/render/export cutover.
- Phase 9 did not approve cleanup deletion. It only confirmed that the cleanup gate is blocked until two consecutive post-cutover release checkpoints exist.
- Phase 10 is verification proof only. It did not remove legacy paths, approve persisted NLE fields, or switch timeline/global-canvas/save/render/export ownership.
- Phase 11 is a no-op cleanup closeout only. It did not approve persisted NLE fields or switch timeline/global-canvas/save/render/export ownership.
- One quick QA attempt failed at `open_project` with `app_unreachable`, but the immediate rerun passed. Treat the failed artifact as command-channel flake evidence, not final-overlay behavior proof.
- NLE adoption remains incremental under the owner's video-editor goal. Current runtime write/projection coverage is `gap_delete`, `gap_generate`, `caption_move`, `caption_resize`, `caption_text_edit`, `caption_split`, `caption_range_replace`, `caption_merge`, `caption_delete`, `candidate_confirm`, `marker_edit`, live editor `diamond`, live editor `square_left`/`square_right` boundary resize, live editor segment delete-to-gap, live editor gap-generate routes, live editor diamond merge route, live editor text/smart split route, live editor STT1/STT2 candidate-confirm route, timeline inline text commit route, shortcut split-at-playhead route, partial range replacement route, final overlay, global canvas final lane, save/export final SRT rows, roughcut saved-candidate render plans, and save/reopen identity plus marker preservation for all 11 current dual-write operation families. The known safe existing-family release/commit source audit is complete for now; persisted NLE project-field approval remains open for future items.
- Generation latency remains open. Current cut-boundary evidence points away from cut-boundary work. The zero-candidate LLM defer trim is safe but not a total latency closeout; High context-boundary batching was rejected for quality drift. Current wall-clock evidence still points toward STT primary transcription, selective STT2 recheck, word precision, and subtitle postprocess. New substage timing says STT2/word precision prepare/annotation are not the target on local smoke; High context-boundary diagnostics show cached X5 audio spent `32.230357s` on `4` pair calls with `0` changed pairs, but that non-reference run cannot approve skipping or batching. cProfile rows remain diagnostic only and must not be treated as elapsed truth.
- NAS is currently available as of the owner's latest update. The current HeyDealer first-180s refresh is accepted at `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_175938/benchmark_results.json` with elapsed `45.611s`, raw/final/reference `58/56/89`, quality/text/timing `93.766/94.267/0.5808s`, final invalid/non-monotonic/overlap `0/0/0`, global max-active `1`, and timeout detected `false`. This refresh does not approve collect-cache default promotion without explicit owner review.
- App Store submission is not ready until a signed sandboxed app bundle, signed App Store package, sandbox smoke, App Store Connect validation, and owner-approved App Store Connect metadata are produced.

### Next Recommended Action

- Continue `ACTION_ITEMS.md` item 1 from the latest NAS-on HeyDealer truth: STT1 `18.060753s`, STT2 `14.348744s`, word precision `12.616315s`, and subtitle postprocess `0.50707s` in run `20260628_175938`. Prefer redundant waiting/cache/scheduling work. Do not skip STT2, disable word precision, shrink STT windows, promote collect-cache defaults, or loosen final subtitle stability gates without explicit owner review.
- For `Mac App Store Submission Readiness`, the next owner-approved execution step is to choose whether to run the Mac App Store package path, then run build/sign/validate/package/App Store Connect validation with real identities. Do not run those commands without explicit owner approval.
