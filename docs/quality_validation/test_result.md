# 자동화-4 전체 UX 테스트 결과

## v04.01.34 Roughcut 3-Row Connector Interaction Preview - 2026-06-30 KST

- 실행 모드: source-app roughcut UI/state preview release checkpoint; no real
  scenario export or NLE commit authority change.
- 결과: pass for focused roughcut frame/material interactions, roughcut
  candidate, app-command, and project reload guards.
- 저장 위치:
  - Release note: `docs/release_notes/RELEASE_v04.01.34.md`
  - Manual preview:
    `output/manual_verification/latest/roughcut_3row_connector_handles_20260630/`
- 실제 결과:
  - `APP_VERSION` updated to `04.01.34`.
  - `PROJECT_SCHEMA_VERSION` updated to `04.01.34`.
  - The roughcut `ㅓ` floating handle now also adjusts the scenario/material
    vertical split.
  - Roughcut `재료박스` preview now keeps non-parallel cards as one
    left-to-right time sequence and stacks up to 3 parallel cut candidates in a
    fixed 3-row column.
  - Card pins highlight on hover and while drawing a connection.
  - Connector lines highlight on hover and right-click deletes the selected
    connector.
  - This does not write NLE rows, final subtitle rows, source media/SRT files,
    `_시나리오.srt`, or `_시나리오.mp4`.
- 검증:
  - `./venv/bin/python -m py_compile ui/roughcut/roughcut_widget.py tests/test_roughcut_ui_v2.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_roughcut_ui_v2.py -k "material_preview or frame_only_boxes"` -> `4 passed, 40 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_roughcut_ui_v2.py` -> `44 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_roughcut_ui_v2.py tests/test_roughcut_candidates.py` -> `51 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_app_command_bridge.py -k "roughcut"` -> `10 passed, 75 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_segment_reload.py -k "roughcut or open_project_file"` -> `4 passed, 86 deselected`.
  - `PYTHONDONTWRITEBYTECODE=1 QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q -p no:cacheprovider tests/test_macos_bundle_runtime_paths.py tests/test_project_context.py tests/test_cp03_cp04_status_ui.py -k "schema or version or project_file_roundtrip or status"` -> `66 passed, 84 deselected`.
  - Direct version assertion -> `APP_VERSION=04.01.34`, `PROJECT_SCHEMA_VERSION=04.01.34`.
  - Tracked development `.md` path check excluding `.agents` -> pass.
  - `git diff --check -- .` -> pass.
- 제외:
  - This does not prove full QA, DMG build/validation, App Store
    package/signing/upload/submission, owner metadata completion, real scenario
    MP4/SRT export, or NLE-backed split/merge/trim commit.

## v04.01.33 Roughcut Scenario Composer Preview Checkpoint - 2026-06-30 KST

- 실행 모드: source-app roughcut UI/state preview release checkpoint; no real
  scenario export or NLE commit authority change.
- 결과: pass for focused roughcut preview, roughcut candidate, app-command,
  project reload, and version/schema guards.
- 저장 위치:
  - Release note: `docs/release_notes/RELEASE_v04.01.33.md`
  - Manual preview: `output/manual_verification/latest/roughcut_parallel_r_grid_20260630/`
  - Completed archive:
    `docs/planning_queue/COMPLETED_ACTION_ITEMS.md#v040132-g4-parallel-connector-auto-sort-preview-slice`
- 실제 결과:
  - `APP_VERSION` updated to `04.01.33`.
  - `PROJECT_SCHEMA_VERSION` updated to `04.01.33`.
  - Roughcut `재료박스` preview now supports 30 grid-snapped cards, 20-card
    visible pages, horizontal scrolling, left/right pins, random demo
    connections, up to 3 parallel connector lanes, and connector-order
    `자동정렬`.
  - Roughcut `시나리오박스` preview shows the selected card or generated
    connector path as a one-line video/subtitle placeholder sequence.
  - Roughcut `설정박스` exposes preview-only `시나리오생성`, `멀티선택`,
    `합치기`, `분할`, `삭제`, and left/right trim controls.
  - This does not write NLE rows, final subtitle rows, source media/SRT files,
    `_시나리오.srt`, or `_시나리오.mp4`.
- 검증:
  - `./venv/bin/python -m py_compile ui/roughcut/roughcut_widget.py tests/test_roughcut_ui_v2.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_roughcut_ui_v2.py -k "material_preview or frame_only_boxes"` -> `3 passed, 40 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_roughcut_ui_v2.py tests/test_roughcut_candidates.py` -> `50 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_app_command_bridge.py -k "roughcut"` -> `10 passed, 75 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_segment_reload.py -k "roughcut or open_project_file"` -> `4 passed, 86 deselected`.
  - `PYTHONDONTWRITEBYTECODE=1 QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q -p no:cacheprovider tests/test_macos_bundle_runtime_paths.py tests/test_project_context.py tests/test_cp03_cp04_status_ui.py -k "schema or version or project_file_roundtrip or status"` -> `66 passed, 84 deselected`.
  - Direct version assertion -> `APP_VERSION=04.01.33`, `PROJECT_SCHEMA_VERSION=04.01.33`.
  - Tracked development `.md` path check excluding `.agents`, `.codex_work`,
    `_backup_mac_migration`, `checkpoints`, and `output` -> pass.
  - `git diff --check -- .` -> pass.
- 제외:
  - This does not prove full QA, DMG build/validation, App Store
    package/signing/upload/submission, owner metadata completion, real scenario
    MP4/SRT export, or NLE-backed split/merge/trim commit.

## v04.01.32 Code Review, Version Release, And Agent Bootstrap Refresh - 2026-06-29 KST

- 실행 모드: documentation/release/code-review checkpoint; no runtime behavior change.
- 결과: pass for focused version/schema/status and docs-consolidation guards.
- 저장 위치:
  - Release note: `docs/release_notes/RELEASE_v04.01.32.md`
  - Completed archive: `docs/planning_queue/COMPLETED_ACTION_ITEMS.md#v040132-code-review-version-release-and-agent-bootstrap-refresh`
  - Jammini probe: `.agents/sentinel/handoffs/20260629-214917-watchdog-handoff-probe.md`
- 실제 결과:
  - `APP_VERSION` updated to `04.01.32`.
  - `PROJECT_SCHEMA_VERSION` updated to `04.01.32`.
  - `AGENTS.md` new-chat continuation now points at the `v04.01.32` release checkpoint, latest docs-consolidation guard, latest G0/G1 evidence pointers, and latest physical Jammini probe.
  - Code review found no runtime app-code issue requiring behavior changes. The applied fixes were documentation/bootstrap consistency fixes.
  - Active queue remains `docs/planning_queue/ACTION_ITEMS.md`; completed history remains `docs/planning_queue/COMPLETED_ACTION_ITEMS.md`.
- 검증:
  - `./venv/bin/python -m py_compile core/runtime/config.py core/project/project_format.py` -> pass.
  - `PYTHONDONTWRITEBYTECODE=1 QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q -p no:cacheprovider tests/test_macos_bundle_runtime_paths.py tests/test_project_context.py tests/test_cp03_cp04_status_ui.py -k "schema or version or project_file_roundtrip or status"` -> `66 passed, 84 deselected`.
  - Docs consolidation presence check -> `docs_consolidation_presence=pass`.
  - Tracked development `.md` path check excluding `.agents`, `.codex_work`, `_backup_mac_migration`, `checkpoints`, and `output` -> only `./AGENTS.md` remains outside `docs/`.
  - Direct version assertion -> `APP_VERSION=04.01.32`, `PROJECT_SCHEMA_VERSION=04.01.32`.
  - `git diff --check -- .` -> pass.
- 제외:
  - This does not prove full QA, App Store package/signing/upload/submission, owner metadata completion, STT/cache default promotion, UI/UX change, or NLE runtime behavior change.

## v04.01.31 G0 Owner Metadata Values Template Support - 2026-06-29 KST

- 실행 모드: non-destructive App Store owner metadata values template support.
- 결과: pass for template generation and guard behavior. The generated template is a fill-in aid only and does not clear owner metadata.
- 저장 위치:
  - Template artifact: `output/manual_verification/latest/app_store_owner_metadata_values_template_v040131_20260629_1625/owner_metadata_values_template.json`
  - Metadata package with template: `output/manual_verification/latest/app_store_metadata_owner_input_template_v040131_20260629_1625/app_store_metadata_owner_input_package.md`
  - Completed archive: `docs/planning_queue/COMPLETED_ACTION_ITEMS.md#v040131-g0-owner-metadata-values-template-support`
- 실제 결과:
  - `tools/check_app_store_owner_metadata_values.py --write-template` writes schema `ai_subtitle_studio.app_store_owner_metadata_values.v1`.
  - `tools/generate_app_store_metadata_package.py` now emits `owner_metadata_values_template.json`; generated package returned `file_count=16` and `has_template=True`.
  - Empty generated template remains blocked: `exit_code=65`, `ready=False`, issue count `58`, owner-input ready `0/8`, App Store Connect metadata ready `0/8`.
  - This preserves the rule that owner metadata requires explicit values, owner approval evidence, URL ownership, screenshot signed-candidate binding, App Store Connect metadata, and forbidden-copy scan pass.
- 검증:
  - `./venv/bin/python -m py_compile tools/check_app_store_owner_metadata_values.py tools/generate_app_store_metadata_package.py tests/test_app_store_metadata_values_preflight.py tests/test_app_store_metadata_package.py` -> pass.
  - `PYTHONDONTWRITEBYTECODE=1 QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q -p no:cacheprovider tests/test_app_store_metadata_values_preflight.py tests/test_app_store_metadata_package.py` -> `13 passed`.
  - `PYTHONDONTWRITEBYTECODE=1 QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q -p no:cacheprovider tests/test_app_store_metadata_values_preflight.py tests/test_app_store_readiness_audit.py tests/test_app_store_metadata_package.py tests/test_app_store_upload_preflight.py tests/test_app_store_upload_script.py tests/test_macos_bundle_runtime_paths.py` -> `39 passed`.
  - Template generation command -> wrote `owner_metadata_values_template.json`.
  - Metadata package generation command -> `file_count=16`, `has_template=True`.
  - Empty template validation -> `exit_code=65`, `ready=False`, owner metadata not ready.
  - This recheck does not prove App Store readiness, signed package readiness, upload/submission, sandbox smoke, App Store Connect validation, or owner metadata completion.

## v04.01.31 G0/G1/G2/G3 Blocker Recheck And Active-Queue Metadata Sync - 2026-06-29 KST

- 실행 모드: non-destructive active-group blocker recheck and documentation sync.
- 결과: pass for documentation/source-of-truth consistency; remaining executable release/default/NLE work is still blocked by explicit owner/external gates.
- 저장 위치:
  - G0 readiness audit: `output/manual_verification/latest/app_store_current_blocker_recheck_v040131_20260629_1608/app_store_readiness_audit.md`
  - G0 metadata owner-input package: `output/manual_verification/latest/app_store_metadata_owner_input_recheck_v040131_20260629_1608/app_store_metadata_owner_input_package.md`
  - Completed archive: `docs/planning_queue/COMPLETED_ACTION_ITEMS.md#v040131-g0g1g2g3-blocker-recheck-and-active-queue-metadata-sync`
- 실제 결과:
  - G0 remains `status=blocked`, `app_store_submission_ready=false`, overall stoplight `red`, blocker count `25`.
  - Blocker groups: signed artifacts `3`, sandbox smoke `1`, App Store Connect `1`, signing identities `4`, owner metadata `16`.
  - Local signing identity proof shows only `Apple Development: axony99@gmail.com (5M6F7NN5SW)`.
  - Required App Store signing/metadata/upload env vars were unset for the current process.
  - Owner metadata remains incomplete: owner-input metadata `0/8`, App Store Connect metadata `0/8`, owner-values preflight `ready=false`, issue count `75`, forbidden-claim scan `pass`.
  - G1 remains owner-review gated for exactly one cache default promotion plus rollback boundary and same-fixture proof after any default change.
  - G2/G3 have no currently selected wider editing/NLE implementation gate beyond the approved persistence/runtime guard scope.
  - `docs/planning_queue/ACTION_ITEMS.md` bottom metadata was corrected from stale `04.01.25` to `04.01.31`.
- 검증:
  - `tools/jammini_watchdog.sh --status` resolved the active route; `--handoff-probe` packet `20260629-160626` did not produce a physical handoff file.
  - Three read-only sub-agent reviews completed for G0, G1, and G2/G3.
  - This recheck does not prove App Store readiness, upload/submission, metadata completion, STT cache default promotion, NLE 100% completion, UI/UX change, or new runtime behavior.

## v04.01.31 G3 Stronger Live Active-Final Artifact Audit - 2026-06-29 KST

- 실행 모드: source-app G3 offline audit of existing representative live-NLE runtime/status artifact for active pre-final `final > 0` observations.
- 결과: pass for the bounded stronger live active-final artifact audit. This closes only the selected runtime/status artifact gate; it is not full G3 completion or a new live run.
- 저장 위치:
  - Audit report: `output/manual_verification/latest/g3_active_final_surface_audit_v040131_20260629_1558/g3_active_final_surface_audit.md`
  - Audit JSON: `output/manual_verification/latest/g3_active_final_surface_audit_v040131_20260629_1558/g3_active_final_surface_audit.json`
  - Source live proof: `output/manual_verification/latest/g3_live_nle_real_media_observability_timeout20_20260629/live_nle_runtime_proof.json`
  - Source status samples: `output/manual_verification/latest/g3_live_nle_real_media_observability_timeout20_20260629/status_samples.json`
  - Completed archive: `docs/planning_queue/COMPLETED_ACTION_ITEMS.md#v040131-g3-stronger-live-active-final-artifact-audit`
- 실제 결과:
  - Audit state: `status=passed`, source live proof status `passed`, source sample count `206`, source failed sample count `0`, source generation completed `true`, issues `[]`.
  - Active pre-final `final > 0` observations: `12`, spanning poll `193` through `204`, elapsed `99.882s` through `107.317s`, with active final count `47`.
  - Runtime reference tracks remained present during the active-final samples: max STT1 `146`, STT2 `39`, subtitle-preview `8`.
  - Exact snapshot pair: `snapshots/live_nle_13_107317ms.png`, sample elapsed `107.317s`, snapshot elapsed `107.317s`, delta `0.0s`, bytes `176725`.
  - Final-only authority and projection budget stayed valid in the saved compact-contract fields; raw-leak evidence is derived from saved compact-contract flags and source summary failure lists because raw status payloads were intentionally not stored.
  - `audit_app_version=04.01.31` identifies the audit code only; `source_proof_app_version=unknown_not_reexecuted_by_this_audit`.
  - This audit does not prove new live execution, active video export while generation is running, save/export artifact counts, UI/UX change, STT/cache default promotion, worker fan-out/scheduler change, persisted NLE disk-format cutover, App Store readiness, upload, or submission.
- 검증:
  - `./venv/bin/python -m py_compile tools/audit_g3_active_final_surface.py tests/test_g3_active_final_surface_audit.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_g3_active_final_surface_audit.py` -> `3 passed`.
  - `./venv/bin/python tools/audit_g3_active_final_surface.py --output-dir output/manual_verification/latest/g3_active_final_surface_audit_v040131_20260629_1558` -> `status=passed valid_active_final_observations=12 snapshot_pairs=1`.

## v04.01.31 G3 Active-Worker Export Final-Surface Regression Guard - 2026-06-29 KST

- 실행 모드: source-app G3 app-command export final-surface regression guard for active-worker status.
- 결과: pass for the bounded regression guard. This is not full G3 completion or a live real-media active `final > 0` final-surface proof.
- 저장 위치:
  - Test guard: `tests/test_app_command_bridge.py::AppCommandBridgeTests::test_active_worker_export_subtitles_keeps_runtime_reference_rows_off_final_surface`
  - Completed archive: `docs/planning_queue/COMPLETED_ACTION_ITEMS.md#v040131-g3-active-worker-export-final-surface-regression-guard`
- 실제 결과:
  - The guard sets `backend._active=true` and editor state `ST_PROC`.
  - Editor rows include two final rows plus VAD, STT1, STT2, and subtitle-preview runtime-reference rows that carry text.
  - `export-subtitles` writes an SRT with exactly two final blocks and excludes the runtime VAD/STT1/STT2/subtitle-preview text from the final save/export surface.
  - `guided-subtitle-status` keeps compact runtime-track counts `VAD/STT1/STT2/subtitle_preview/final = 1/1/1/1/2`.
  - `final` remains the only save/export authority; runtime reference tracks are not authoritative and raw runtime segment text does not leak into compact status.
  - Production code was unchanged.
  - This guard does not prove active live real-media final-surface snapshots, active video export while generation is running, UI/UX change, STT/cache default promotion, worker fan-out/scheduler change, persisted NLE disk-format cutover, App Store readiness, upload, or submission.
- 검증:
  - `./venv/bin/python -m py_compile tests/test_app_command_bridge.py ui/main/app_command_bridge.py ui/main/app_command_bridge_handlers.py core/project/nle_runtime_cutover.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_app_command_bridge.py -k "active_worker_export_subtitles_keeps_runtime_reference_rows_off_final_surface or export_subtitles_command or status_command_reports_compact_nle_runtime_track_counts"` -> `4 passed, 81 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_runtime_cutover.py tests/test_subtitle_live_editor_feed_facade.py tests/test_remote_verify_actions.py tests/test_app_command_bridge.py -k "nle or runtime or status or live_nle or save_export or cancel_current_pipeline or app_close or app_quit or active_worker_export_subtitles"` -> `57 passed, 64 deselected`.
  - Direct version assertion -> `APP_VERSION=04.01.31`, `PROJECT_SCHEMA_VERSION=04.01.31`.
  - `git diff --check -- .` -> pass.

## v04.01.31 G1 STT Cache Default Review Packet Evidence Binding Refresh - 2026-06-29 KST

- 실행 모드: source-app G1 owner-review packet evidence-binding refresh for NAS HeyDealer first-180s collect-cache write/hit evidence.
- 결과: pass for the bounded review-packet refresh. G1 remains owner-review gated; runtime defaults remain off and default promotion is not allowed by this packet.
- 저장 위치:
  - Review packet: `output/manual_verification/latest/stt_cache_default_review_packet_v040131_20260629_1527/stt_cache_default_review_packet.md`
  - Packet JSON: `output/manual_verification/latest/stt_cache_default_review_packet_v040131_20260629_1527/stt_cache_default_review_packet.json`
  - Decision matrix: `output/manual_verification/latest/stt_cache_default_review_packet_v040131_20260629_1527/decision_matrix.json`
  - Completed archive: `docs/planning_queue/COMPLETED_ACTION_ITEMS.md#v040131-g1-stt-cache-default-review-packet-evidence-binding-refresh`
- 실제 결과:
  - `tools/generate_stt_cache_default_review_packet.py` now selects the readiness run matching accepted write/hit elapsed, quality, and segment-count evidence.
  - Selected write run: `20260628_220327`, elapsed `177.888s`.
  - Selected hit run: `20260628_220718`, elapsed `1.183s`.
  - Packet state: `status=owner_review_required`, `production_defaults_unchanged=true`, `default_promotion_allowed=false`, current defaults `stt_primary_collect_cache_enabled=false` and `stt_recheck_collect_cache_enabled=false`.
  - NAS acceptance remains strict: raw/final/reference `58/56/89`, quality/text/timing `93.766/94.267/0.5808s`, final invalid/non-monotonic/overlap `0/0/0`, final last end/duration bound `180.0/180.0`, save/reopen stable `true`, global max active `1`, timeout detected `false`.
  - The `1.183s` value is same-fixture cache-hit replay evidence, not first-run production speed.
  - This refresh does not promote cache defaults, change `DEFAULT_ADV_SETTINGS`, skip STT2, disable word precision, downgrade models, relax quality gates, change UI/UX, build/sign/upload App Store artifacts, or change NLE behavior.
- 검증:
  - `./venv/bin/python -m py_compile tools/generate_stt_cache_default_review_packet.py tests/test_stt_cache_default_review_packet.py core/runtime/config.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_stt_cache_default_review_packet.py` -> `6 passed`.
  - `./venv/bin/python tools/generate_stt_cache_default_review_packet.py --evidence-dir output/manual_verification/latest/stt_cache_backfill_real_nas_20260628_2202 --output-dir output/manual_verification/latest/stt_cache_default_review_packet_v040131_20260629_1527` -> `status=owner_review_required`, `production_defaults_unchanged=true`, `default_promotion_allowed=false`.
  - `git diff --check -- .` -> pass.

## v04.01.31 G0 App Store Current-Version Readiness Refresh - 2026-06-29 KST

- 실행 모드: source-app G0 non-destructive current-version App Store readiness audit and metadata owner-input package refresh.
- 결과: pass for the bounded refresh. G0 remains blocked; this is not package signing, sandbox smoke, validation, upload, submission, or owner metadata completion proof.
- 저장 위치:
  - Readiness audit: `output/manual_verification/latest/app_store_current_version_refresh_v040131_20260629_151653/app_store_readiness_audit.md`
  - Readiness JSON: `output/manual_verification/latest/app_store_current_version_refresh_v040131_20260629_151653/app_store_readiness_audit.json`
  - Metadata owner-input package: `output/manual_verification/latest/app_store_metadata_owner_input_package_v040131_20260629_151653/app_store_metadata_owner_input_package.md`
  - Completed archive: `docs/planning_queue/COMPLETED_ACTION_ITEMS.md#v040131-g0-app-store-current-version-readiness-refresh`
- 실제 결과:
  - App version stayed `04.01.31`.
  - Readiness state: `status=blocked`, `local_packaging_ready=true`, `app_store_submission_ready=false`, overall stoplight `red`, blocker count `25`.
  - Blocker groups: `signed_artifacts=3`, `sandbox_smoke=1`, `app_store_connect=1`, `signing_identities=4`, `owner_metadata=16`.
  - Owner metadata values preflight: `ready=false`, issue count `75`, owner-input metadata `0/8` ready, App Store Connect metadata `0/8` ready, forbidden-claim scan `pass`.
  - Missing proof remains: signed App Store `.pkg`, strict content-bound `codesign`, content-bound `pkgutil --check-signature`, sandbox smoke, App Store Connect validation, Apple Distribution identity, 3rd Party Mac Developer Installer identity, upload/submission proof, and owner-approved metadata values JSON.
  - This refresh does not change UI/UX, subtitle generation, STT/cache defaults, NLE behavior, package signing, upload, or submission state.
- 검증:
  - `./venv/bin/python -m py_compile tools/audit_app_store_readiness.py tools/generate_app_store_metadata_package.py tools/check_app_store_owner_metadata_values.py tools/check_app_store_upload_preflight.py tests/test_app_store_readiness_audit.py tests/test_app_store_metadata_package.py tests/test_app_store_metadata_values_preflight.py tests/test_app_store_upload_preflight.py tests/test_app_store_upload_script.py core/runtime/config.py tests/test_macos_bundle_runtime_paths.py` -> pass.
  - `PYTHONDONTWRITEBYTECODE=1 QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q -p no:cacheprovider tests/test_app_store_metadata_values_preflight.py tests/test_app_store_readiness_audit.py tests/test_app_store_metadata_package.py tests/test_app_store_upload_preflight.py tests/test_app_store_upload_script.py tests/test_macos_bundle_runtime_paths.py` -> `37 passed`.
  - `./venv/bin/python tools/audit_app_store_readiness.py --output-dir output/manual_verification/latest/app_store_current_version_refresh_v040131_20260629_151653` -> `status=blocked`, blocker count `25`.
  - `./venv/bin/python tools/generate_app_store_metadata_package.py --output-dir output/manual_verification/latest/app_store_metadata_owner_input_package_v040131_20260629_151653` -> `not_submission_proof=true`, owner-input metadata `8/8` pending, App Store Connect metadata `8` pending.

## v04.01.31 G2 Final Cutover Ready Opt-In Proof - 2026-06-29 KST

- 실행 모드: source-app G2 owner-approved final project persistence load-owner opt-in proof, forged-policy guard, cache-hit hydration guard, Direct SRT precedence guard, compatibility `editor_state` projection guard, and version/schema bump.
- 결과: pass for the bounded final cutover-ready proof. The NLE persistence audit reports ready for the explicit approved payload, while UI/UX, STT/cache defaults, full QA, package signing/upload, owner metadata, and App Store submission remain separate proof surfaces.
- 저장 위치:
  - Release note: `docs/release_notes/RELEASE_v04.01.31.md`
  - Audit report: `output/manual_verification/latest/nle_final_cutover_ready_v040131_20260629_150156/nle_persistence_cutover_audit.md`
  - Audit JSON: `output/manual_verification/latest/nle_final_cutover_ready_v040131_20260629_150156/nle_persistence_cutover_audit.json`
  - Completed archive: `docs/planning_queue/COMPLETED_ACTION_ITEMS.md#v040131-g2-final-cutover-ready-opt-in-proof`
- 실제 결과:
  - App version updated to `04.01.31`.
  - Project schema version updated to `04.01.31`.
  - Final source-app project persistence load-owner policy is accepted only when the distinct final schema and all approved snapshot/runtime/legacy-projection policy flags are present.
  - `default_project_authority=nle_snapshot` is declared for the approved payload; the `editor_state` key remains present as a compatibility projection and does not mean dual canonical ownership.
  - Cache-hit read/resave hydrates approved runtime state and preserves `_nle_project_state` only for the explicit approved payload.
  - Forged final policy is blocked, Direct SRT precedence is preserved, and top-level/readback/quarantine payloads do not persist.
  - Audit state: `status=ready`, `app_version=04.01.31`, `prep_ready=true`, `persistence_cutover_ready=true`, blockers `[]`, overall stoplight `green`, ready/blocked gates `12/0`.
  - Ready gates added/kept: `nle_snapshot_canonical_load_source_allowed`, `runtime_project_state_persistence_allowed`, `legacy_disk_shape_replacement_allowed`, and `final_cutover_ready`.
  - This is explicit source-app persistence load-owner proof only; it is not `editor_state` key removal, per-pixel NLE writes, UI/UX change, STT/cache default change, full QA, or App Store package/signing/upload/submission proof.
- 검증:
  - `./venv/bin/python -m py_compile core/project/nle_persistence_guard.py core/project/project_format.py core/project/project_io.py tools/audit_nle_persistence_cutover.py tests/test_project_nle_persistence_guard.py tests/test_nle_persistence_cutover_audit.py core/runtime/config.py tests/test_macos_bundle_runtime_paths.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_persistence_guard.py tests/test_nle_persistence_cutover_audit.py tests/test_macos_bundle_runtime_paths.py` -> `34 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_nle_persistence_cutover.py --output-dir output/manual_verification/latest/nle_final_cutover_ready_v040131_20260629_150156` -> `status=ready`, overall stoplight `green`, ready/blocked gates `12/0`, blockers `[]`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_context.py tests/test_cp03_cp04_status_ui.py -k "schema or version or project_file_roundtrip or status"` -> `66 passed, 80 deselected`.
  - Direct version assertion -> `APP_VERSION=04.01.31`, `PROJECT_SCHEMA_VERSION=04.01.31`.
  - `git diff --check -- .` -> pass.

## v04.01.30 G2 Legacy Disk Shape Replacement Opt-In Proof - 2026-06-29 KST

- 실행 모드: source-app G2 owner-approved legacy-compatible `editor_state` row replacement opt-in proof, forged-policy guard, cache-hit hydration guard, Direct SRT precedence guard, and version/schema bump.
- 결과: pass for the bounded legacy disk-shape replacement proof. Full NLE disk-format cutover remains blocked because `final_cutover_ready` remains incomplete.
- 저장 위치:
  - Release note: `docs/release_notes/RELEASE_v04.01.30.md`
  - Audit report: `output/manual_verification/latest/nle_legacy_disk_shape_replacement_v040130_20260629_143522/nle_persistence_cutover_audit.md`
  - Audit JSON: `output/manual_verification/latest/nle_legacy_disk_shape_replacement_v040130_20260629_143522/nle_persistence_cutover_audit.json`
  - Completed archive: `docs/planning_queue/COMPLETED_ACTION_ITEMS.md#v040130-g2-legacy-disk-shape-replacement-opt-in-proof`
- 실제 결과:
  - App version updated to `04.01.30`.
  - Project schema version updated to `04.01.30`.
  - Legacy-compatible `editor_state` rows regenerate from approved standalone `nle_snapshot` rows only when the distinct owner-approved replacement policy is present.
  - The `editor_state` key remains present for compatibility; this is row projection proof, not key removal or final cutover.
  - Cache-hit read/resave hydrates approved runtime state and preserves `_nle_project_state` only for the explicit approved payload.
  - Forged replacement policy is blocked, Direct SRT precedence is preserved, and top-level/readback/quarantine payloads do not persist.
  - Audit state: `status=blocked`, `app_version=04.01.30`, `prep_ready=true`, `persistence_cutover_ready=false`, overall stoplight `red`, ready/blocked gates `11/1`.
  - Ready gates added/kept: `nle_snapshot_canonical_load_source_allowed`, `runtime_project_state_persistence_allowed`, and `legacy_disk_shape_replacement_allowed`.
  - Blocked gate: `final_cutover_ready`.
  - This is explicit legacy-compatible row projection proof only; it is not final NLE disk-format cutover, UI/UX change, STT/cache default change, or App Store package/signing/upload/submission proof.
- 검증:
  - `./venv/bin/python -m py_compile core/project/nle_snapshot.py core/project/nle_persistence_guard.py core/project/project_io.py core/project/project_format.py core/runtime/config.py tools/audit_nle_persistence_cutover.py tests/test_project_nle_persistence_guard.py tests/test_nle_persistence_cutover_audit.py tests/test_macos_bundle_runtime_paths.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_persistence_guard.py -k "legacy_disk_shape or runtime_nle_project_state"` -> `5 passed, 17 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_nle_persistence_cutover_audit.py -k "cutover"` -> `6 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_persistence_guard.py tests/test_nle_persistence_cutover_audit.py tests/test_direct_srt_precedence_audit.py tests/test_macos_bundle_runtime_paths.py` -> `33 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_nle_persistence_cutover.py --output-dir output/manual_verification/latest/nle_legacy_disk_shape_replacement_v040130_20260629_143522` -> `status=blocked`, overall stoplight `red`, ready/blocked gates `11/1`, blockers `1`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_context.py tests/test_cp03_cp04_status_ui.py -k "schema or version or project_file_roundtrip or status"` -> `66 passed, 80 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_segment_reload.py -k "direct_srt_rows_to_runtime_nle_state or direct_srt_readback_drift_without_overwriting_srt_rows" tests/test_editor_autosave_cleanup.py -k "direct_srt_mode or direct_srt_micro_overlap"` -> `2 passed, 140 deselected`.
  - Direct version assertion -> `APP_VERSION=04.01.30`, `PROJECT_SCHEMA_VERSION=04.01.30`.

## v04.01.29 G2 Runtime _nle_project_state Persistence Opt-In Proof - 2026-06-29 KST

- 실행 모드: source-app G2 owner-approved supplemental `_nle_project_state` persistence opt-in proof, cache-hit hydration guard, legacy rollback preservation, and version/schema bump.
- 결과: pass for the bounded runtime-state persistence proof. Full NLE disk-format cutover remains blocked because legacy disk-shape replacement and final cutover proof remain incomplete.
- 저장 위치:
  - Release note: `docs/release_notes/RELEASE_v04.01.29.md`
  - Audit report: `output/manual_verification/latest/nle_runtime_state_persistence_v040129_20260629_140053/nle_persistence_cutover_audit.md`
  - Audit JSON: `output/manual_verification/latest/nle_runtime_state_persistence_v040129_20260629_140053/nle_persistence_cutover_audit.json`
  - Completed archive: `docs/planning_queue/COMPLETED_ACTION_ITEMS.md#v040129-g2-runtime-_nle_project_state-persistence-opt-in-proof`
- 실제 결과:
  - App version updated to `04.01.29`.
  - Project schema version updated to `04.01.29`.
  - `_nle_project_state` persists only when explicit runtime persistence approval, approved standalone `nle_snapshot` policy, and approved nested runtime payload are all present.
  - Runtime object save and approved persisted-dict resave paths both preserve approved supplemental runtime state while keeping legacy `editor_state` rollback rows.
  - Cache-hit read hydrates `_nle_project_state` back into runtime state only after rows are verified against the current project segments.
  - Forged or unapproved persisted runtime dicts are stripped on resave.
  - Audit state: `status=blocked`, `app_version=04.01.29`, `prep_ready=true`, `persistence_cutover_ready=false`, overall stoplight `red`, ready/blocked gates `10/2`.
  - Ready gates added/kept: `nle_snapshot_canonical_load_source_allowed` and `runtime_project_state_persistence_allowed`.
  - Blocked gates: `legacy_disk_shape_replacement_allowed` and `final_cutover_ready`.
  - This is explicit supplemental runtime-state persistence proof only; it is not legacy `editor_state` replacement, final NLE disk-format cutover, UI/UX change, STT/cache default change, or App Store package/signing/upload/submission proof.
- 검증:
  - `./venv/bin/python -m py_compile core/project/nle_persistence_guard.py core/project/nle_project_state.py core/project/project_io.py core/project/project_format.py tools/audit_nle_persistence_cutover.py tests/test_project_nle_persistence_guard.py tests/test_nle_persistence_cutover_audit.py tests/test_macos_bundle_runtime_paths.py core/runtime/config.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_persistence_guard.py tests/test_nle_persistence_cutover_audit.py tests/test_macos_bundle_runtime_paths.py` -> `30 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_nle_persistence_cutover.py --output-dir output/manual_verification/latest/nle_runtime_state_persistence_v040129_20260629_140053` -> `status=blocked`, overall stoplight `red`, ready/blocked gates `10/2`, blockers `2`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_context.py tests/test_cp03_cp04_status_ui.py -k "schema or version or project_file_roundtrip or status"` -> `66 passed, 80 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_segment_reload.py -k "direct_srt_rows_to_runtime_nle_state or direct_srt_readback_drift_without_overwriting_srt_rows" tests/test_editor_autosave_cleanup.py -k "direct_srt_mode or direct_srt_micro_overlap"` -> `2 passed, 140 deselected`.
  - Direct version assertion -> `APP_VERSION=04.01.29`, `PROJECT_SCHEMA_VERSION=04.01.29`.

## v04.01.28 G2 NLE Snapshot Standalone Canonical Load Opt-In Proof - 2026-06-29 KST

- 실행 모드: source-app G2 owner-approved standalone `nle_snapshot` canonical load-source opt-in proof, fail-closed compatibility/forgery/empty/ambiguity guards, legacy rollback preservation, and version/schema bump.
- 결과: pass for the bounded NLE snapshot load-source proof. Full NLE disk-format cutover remains blocked because runtime-state persistence, legacy disk-shape replacement, and final cutover proof remain incomplete.
- 저장 위치:
  - Release note: `docs/release_notes/RELEASE_v04.01.28.md`
  - Audit report: `output/manual_verification/latest/nle_snapshot_canonical_load_source_v040128_20260629_1325/nle_persistence_cutover_audit.md`
  - Audit JSON: `output/manual_verification/latest/nle_snapshot_canonical_load_source_v040128_20260629_1325/nle_persistence_cutover_audit.json`
  - Completed archive: `docs/planning_queue/COMPLETED_ACTION_ITEMS.md#v040128-g2-nle-snapshot-standalone-canonical-load-opt-in-proof`
- 실제 결과:
  - App version updated to `04.01.28`.
  - Project schema version updated to `04.01.28`.
  - `core/project/nle_persistence_guard.py` separates compatibility-only snapshot persistence from explicit standalone snapshot load-source approval.
  - `core/project/project_context.py` uses `nle_snapshot` rows only when explicit snapshot canonical-load policy and approved payload are present.
  - `core/project/project_format.py` preserves approved snapshot rows on resave while keeping legacy `editor_state` rows for rollback.
  - Audit state: `status=blocked`, `app_version=04.01.28`, `prep_ready=true`, `persistence_cutover_ready=false`, overall stoplight `red`, ready/blocked gates `9/3`.
  - Current canonical owner for explicit opt-in payloads: `nle_snapshot`; `nle_snapshot_canonical_load_source_allowed=ready`.
  - Snapshot opt-in proof: loaded/runtime/reloaded/storage `nle_snapshot` first caption text remains `snapshot canonical first`; legacy `editor_state` first caption text after resave remains `first`.
  - Blocked gates: `runtime_project_state_persistence_allowed`, `legacy_disk_shape_replacement_allowed`, and `final_cutover_ready`.
  - This is explicit opt-in load-source proof only; it is not persisted `_nle_project_state`, legacy `editor_state` replacement, final NLE disk-format cutover, UI/UX change, STT/cache default change, or App Store package/signing/upload/submission proof.
- 검증:
  - `./venv/bin/python -m py_compile core/project/nle_persistence_guard.py core/project/project_format.py core/project/nle_snapshot.py core/project/project_context.py tools/audit_nle_persistence_cutover.py tests/test_project_nle_persistence_guard.py tests/test_nle_persistence_cutover_audit.py tests/test_macos_bundle_runtime_paths.py core/runtime/config.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_persistence_guard.py tests/test_nle_persistence_cutover_audit.py tests/test_macos_bundle_runtime_paths.py` -> `27 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_nle_persistence_cutover.py --output-dir output/manual_verification/latest/nle_snapshot_canonical_load_source_v040128_20260629_1325` -> `status=blocked`, overall stoplight `red`, ready/blocked gates `9/3`, blockers `3`.
  - Project/status guard and direct version assertion are recorded in the completed archive and release note for this checkpoint.

## v04.01.27 G2 Top-Level NLE Canonical Load Opt-In Proof - 2026-06-29 KST

- 실행 모드: source-app G2 owner-approved top-level `nle` canonical load opt-in proof, paired `nle`/`nle_snapshot` readback guard, legacy rollback preservation, and version/schema bump.
- 결과: pass for the bounded NLE persistence/load proof. Full NLE disk-format cutover remains blocked because `nle_snapshot` standalone canonical sourcing, runtime-state persistence, legacy disk-shape replacement, and final cutover proof remain incomplete.
- 저장 위치:
  - Release note: `docs/release_notes/RELEASE_v04.01.27.md`
  - Audit report: `output/manual_verification/latest/nle_canonical_load_opt_in_v040127_20260629_1248/nle_persistence_cutover_audit.md`
  - Audit JSON: `output/manual_verification/latest/nle_canonical_load_opt_in_v040127_20260629_1248/nle_persistence_cutover_audit.json`
  - Completed archive: `docs/planning_queue/COMPLETED_ACTION_ITEMS.md#v040127-g2-top-level-nle-canonical-load-opt-in-proof`
- 실제 결과:
  - App version updated to `04.01.27`.
  - Project schema version updated to `04.01.27`.
  - `core/project/nle_persistence_guard.py` separates legacy top-level shadow metadata from explicit top-level canonical load opt-in policy.
  - `core/project/nle_snapshot.py` exposes top-level `nle` / `nle_snapshot` row projection helpers.
  - `core/project/project_context.py` uses top-level `nle` rows only when explicit opt-in policy exists and paired `nle_snapshot` rows agree; companion drift falls back to legacy rows.
  - `core/project/project_format.py` preserves legacy `editor_state` rows for rollback while writing approved top-level canonical-load metadata and matching `nle_snapshot` metadata.
  - Audit state: `status=blocked`, `app_version=04.01.27`, `prep_ready=true`, `persistence_cutover_ready=false`, overall stoplight `red`, ready/blocked gates `8/4`.
  - Current canonical owner for explicit opt-in payloads: `top_level_nle_shadow_metadata`; `canonical_load_owner_change_allowed=ready`.
  - Canonical opt-in proof: loaded/runtime/reloaded/storage `nle`/storage `nle_snapshot` first caption text all remain `nle canonical first`; legacy `editor_state` first caption text after resave remains `first`.
  - Blocked gates: `nle_snapshot_canonical_load_source_allowed`, `runtime_project_state_persistence_allowed`, `legacy_disk_shape_replacement_allowed`, and `final_cutover_ready`.
  - This is explicit opt-in load proof only; it is not `nle_snapshot` standalone canonical sourcing, persisted `_nle_project_state`, legacy `editor_state` replacement, final NLE disk-format cutover, UI/UX change, STT/cache default change, or App Store package/signing/upload/submission proof.
- 검증:
  - `./venv/bin/python -m py_compile core/project/nle_persistence_guard.py core/project/project_format.py core/project/nle_snapshot.py core/project/project_context.py tools/audit_nle_persistence_cutover.py tests/test_project_nle_persistence_guard.py tests/test_nle_persistence_cutover_audit.py tests/test_macos_bundle_runtime_paths.py core/runtime/config.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_persistence_guard.py tests/test_nle_persistence_cutover_audit.py tests/test_macos_bundle_runtime_paths.py` -> `22 passed`.
  - `./venv/bin/python tools/audit_nle_persistence_cutover.py --output-dir output/manual_verification/latest/nle_canonical_load_opt_in_v040127_20260629_1248` -> `status=blocked`, overall stoplight `red`, ready/blocked gates `8/4`, blockers `4`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_context.py tests/test_cp03_cp04_status_ui.py -k "schema or version or project_file_roundtrip or status"` -> `66 passed, 80 deselected`.
  - Direct version assertion -> `APP_VERSION=04.01.27`, `PROJECT_SCHEMA_VERSION=04.01.27`.
  - `git diff --check -- .` -> pass.

## v04.01.26 G0 Owner Metadata Values Preflight Guard - 2026-06-29 KST

- 실행 모드: source-app G0 owner metadata values preflight/import guard, imported-copy forbidden-claim scan, exact proof-path binding, upload readiness hardening, and version/schema bump.
- 결과: pass for the bounded guard/audit/package slice. App Store submission remains blocked because signed `.pkg`, strict content-bound `codesign`, content-bound `pkgutil --check-signature`, sandbox smoke, App Store Connect validation, Apple Distribution/installer identities, upload/submission proof, and owner-approved metadata values JSON are still missing.
- 저장 위치:
  - Release note: `docs/release_notes/RELEASE_v04.01.26.md`
  - Readiness audit: `output/manual_verification/latest/app_store_owner_metadata_values_preflight_v040126_20260629_1228/app_store_readiness_audit.md`
  - Readiness JSON: `output/manual_verification/latest/app_store_owner_metadata_values_preflight_v040126_20260629_1228/app_store_readiness_audit.json`
  - Metadata owner-input package: `output/manual_verification/latest/app_store_metadata_owner_input_package_v040126_20260629_1228/app_store_metadata_owner_input_package.md`
  - Completed archive: `docs/planning_queue/COMPLETED_ACTION_ITEMS.md#v040126-g0-owner-metadata-values-preflight-guard`
- 실제 결과:
  - App version updated to `04.01.26`.
  - Project schema version updated to `04.01.26`.
  - `tools/check_app_store_owner_metadata_values.py` validates explicit owner values JSON before owner metadata can be ready.
  - `tools/audit_app_store_readiness.py` now keeps App Store Connect listing metadata in the owner metadata blocker group instead of counting only the previous 8 non-code items.
  - `tools/generate_app_store_metadata_package.py` now writes `owner_values_preflight.json` and scans imported owner values for forbidden claims.
  - `tools/check_app_store_upload_preflight.py` now rejects minimal forged readiness JSON without schema/root/current app version and `owner_metadata_values_preflight.ready=true`.
  - Current readiness state: `status=blocked`, `local_packaging_ready=true`, `app_store_submission_ready=false`, overall stoplight `red`, blocker count `25`.
  - Blocker groups: `version_lock=0`, `packaging_template=0`, `signed_artifacts=3`, `sandbox_smoke=1`, `app_store_connect=1`, `signing_identities=4`, `owner_metadata=16`, `unknown=0`.
  - Metadata package remains `not_submission_proof=true`, `owner_input_complete=false`, `app_store_submission_ready=false`, pending owner-input metadata `8/8`, pending App Store Connect metadata `8`, owner values preflight `false`, forbidden-claim scan `pass`.
  - This is guard/audit/package evidence only; it is not package creation, Apple Distribution signing, App Store Connect validation, upload, submission, owner metadata completion, UI/UX change, subtitle-generation change, STT/cache default change, or NLE persistence/load behavior change.
- 검증:
  - `./venv/bin/python -m py_compile tools/audit_app_store_readiness.py tools/generate_app_store_metadata_package.py tools/check_app_store_owner_metadata_values.py tools/check_app_store_upload_preflight.py tests/test_app_store_readiness_audit.py tests/test_app_store_metadata_package.py tests/test_app_store_metadata_values_preflight.py tests/test_app_store_upload_script.py tests/test_app_store_upload_preflight.py core/runtime/config.py core/project/project_format.py tests/test_macos_bundle_runtime_paths.py` -> pass.
  - `PYTHONDONTWRITEBYTECODE=1 QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q -p no:cacheprovider tests/test_app_store_metadata_values_preflight.py tests/test_app_store_readiness_audit.py tests/test_app_store_metadata_package.py tests/test_app_store_upload_preflight.py tests/test_app_store_upload_script.py tests/test_macos_bundle_runtime_paths.py` -> `37 passed`.
  - `./venv/bin/python tools/audit_app_store_readiness.py --output-dir output/manual_verification/latest/app_store_owner_metadata_values_preflight_v040126_20260629_1228` -> `status=blocked`, overall stoplight `red`, blocker count `25`.
  - `./venv/bin/python tools/generate_app_store_metadata_package.py --output-dir output/manual_verification/latest/app_store_metadata_owner_input_package_v040126_20260629_1228` -> `not_submission_proof=true`, pending owner-input metadata `8/8`, pending App Store Connect metadata `8`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_context.py tests/test_cp03_cp04_status_ui.py -k "schema or version or project_file_roundtrip or status"` -> `66 passed, 80 deselected`.
  - Direct version assertion -> `APP_VERSION=04.01.26`, `PROJECT_SCHEMA_VERSION=04.01.26`.
  - `git diff --check -- .` -> pass.

## v04.01.25 G0 App Store Upload Preflight Guard And Metadata Refresh - 2026-06-29 KST

- 실행 모드: source-app G0 App Store upload preflight guard, readiness proof-content hardening, metadata owner-input package refresh, and version/schema bump.
- 결과: pass for the bounded guard/audit/package slice. App Store submission remains blocked because signed `.pkg`, content-bound strict `codesign`, content-bound `pkgutil --check-signature`, sandbox smoke, App Store Connect validation, Apple Distribution/installer identities, and owner metadata values are still missing.
- 저장 위치:
  - Release note: `docs/release_notes/RELEASE_v04.01.25.md`
  - Readiness audit: `output/manual_verification/latest/app_store_upload_preflight_guard_v040125_20260629_1200/app_store_readiness_audit.md`
  - Readiness JSON: `output/manual_verification/latest/app_store_upload_preflight_guard_v040125_20260629_1200/app_store_readiness_audit.json`
  - Metadata owner-input package: `output/manual_verification/latest/app_store_metadata_owner_input_package_v040125_20260629_1200/app_store_metadata_owner_input_package.md`
  - Completed archive: `docs/planning_queue/COMPLETED_ACTION_ITEMS.md#v040125-g0-app-store-upload-preflight-guard-and-metadata-refresh`
- 실제 결과:
  - App version updated to `04.01.25`.
  - Project schema version updated to `04.01.25`.
  - `packaging/macos/upload_app_store_build.sh upload` now requires `AI_SUBTITLE_STUDIO_APP_STORE_UPLOAD_CONFIRMED=1` plus `APP_STORE_READINESS_JSON`.
  - `tools/check_app_store_upload_preflight.py` now blocks upload unless readiness JSON has `app_store_submission_ready=true`, no blockers, all submission gates true, and exact `.pkg` path binding.
  - `tools/audit_app_store_readiness.py` now rejects placeholder proof files for `codesign`, `pkgutil`, sandbox smoke, and App Store validation, and requires configured signing identities to match keychain identity text.
  - Current readiness state: `status=blocked`, `local_packaging_ready=true`, `app_store_submission_ready=false`, overall stoplight `red`, blocker count `17`.
  - Blocker groups: `version_lock=0`, `packaging_template=0`, `signed_artifacts=3`, `sandbox_smoke=1`, `app_store_connect=1`, `signing_identities=4`, `owner_metadata=8`, `unknown=0`.
  - Metadata package remains `not_submission_proof=true`, `owner_input_complete=false`, `app_store_submission_ready=false`, pending owner metadata `8/8`, forbidden-claim scan `pass`.
  - This is guard/audit/package evidence only; it is not package creation, Apple Distribution signing, App Store Connect validation, upload, submission, owner metadata completion, UI/UX change, subtitle-generation change, STT/cache default change, or NLE persistence/load behavior change.
- 검증:
  - `./venv/bin/python -m py_compile tools/audit_app_store_readiness.py tools/generate_app_store_metadata_package.py tools/check_app_store_upload_preflight.py tests/test_app_store_readiness_audit.py tests/test_app_store_metadata_package.py tests/test_app_store_upload_script.py tests/test_app_store_upload_preflight.py core/runtime/config.py core/project/project_format.py tests/test_macos_bundle_runtime_paths.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_app_store_readiness_audit.py tests/test_app_store_metadata_package.py tests/test_app_store_upload_script.py tests/test_app_store_upload_preflight.py tests/test_macos_bundle_runtime_paths.py` -> `26 passed`.
  - `./venv/bin/python tools/audit_app_store_readiness.py --output-dir output/manual_verification/latest/app_store_upload_preflight_guard_v040125_20260629_1200` -> `status=blocked`, overall stoplight `red`, blocker count `17`.
  - `./venv/bin/python tools/generate_app_store_metadata_package.py --output-dir output/manual_verification/latest/app_store_metadata_owner_input_package_v040125_20260629_1200` -> `not_submission_proof=true`, pending owner-input metadata `8/8`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_context.py tests/test_cp03_cp04_status_ui.py -k "schema or version or project_file_roundtrip or status"` -> `66 passed, 80 deselected`.
  - Direct version assertion -> `APP_VERSION=04.01.25`, `PROJECT_SCHEMA_VERSION=04.01.25`.
  - `git diff --check -- .` -> pass.

## v04.01.24 G2 Canonical Load-Owner Rollback Boundary Audit - 2026-06-29 KST

- 실행 모드: source-app G2 NLE canonical load-owner rollback-boundary audit, compatibility false-positive guards, and version/schema bump.
- 결과: pass for the bounded audit slice. Full NLE disk-format cutover remains blocked because canonical load-owner change, `nle_snapshot` canonical-source policy, runtime-state persistence policy, legacy disk-shape replacement policy, and final cutover proof remain incomplete.
- 저장 위치:
  - Release note: `docs/release_notes/RELEASE_v04.01.24.md`
  - Audit report: `output/manual_verification/latest/nle_load_owner_rollback_boundary_v040124_20260629_1138/nle_persistence_cutover_audit.md`
  - Audit JSON: `output/manual_verification/latest/nle_load_owner_rollback_boundary_v040124_20260629_1138/nle_persistence_cutover_audit.json`
  - Completed archive: `docs/planning_queue/COMPLETED_ACTION_ITEMS.md#v040124-g2-canonical-load-owner-rollback-boundary-audit`
- 실제 결과:
  - App version updated to `04.01.24`.
  - Project schema version updated to `04.01.24`.
  - `tools/audit_nle_persistence_cutover.py` now includes a canonical load-owner rollback-boundary check.
  - Audit state: `status=blocked`, `app_version=04.01.24`, `prep_ready=true`, `persistence_cutover_ready=false`, `top_level_nle_compatibility_projection_passed=true`.
  - Gate matrix: `overall_stoplight=red`, ready/blocked gates `7/5`, current canonical owner `legacy_editor_state`, target candidate `top_level_nle_shadow_metadata`, and `rollback_boundary_defined=ready`.
  - Blocked gates: `canonical_load_owner_change_allowed`, `nle_snapshot_canonical_load_source_allowed`, `runtime_project_state_persistence_allowed`, `legacy_disk_shape_replacement_allowed`, and `final_cutover_ready`.
  - Rollback proof: candidate top-level `nle`, `nle_snapshot`, and `_nle_project_state` canonical/runtime-persistence claims are stripped on read. Candidate shadow text `rollback candidate shadow text` does not leak to default load or resave; both keep first caption text `first`.
  - Resave regenerates approved top-level `nle`/`nle_snapshot` shadow metadata with `canonical_load_owner=legacy_editor_state`, no persisted runtime state, and no quarantine.
  - This is rollback-boundary audit evidence only; it is not a canonical load-owner switch, disk-format cutover, runtime-state persistence, legacy shape replacement, UI/UX change, or App Store packaging/signing/upload/submission proof.
- 검증:
  - `./venv/bin/python -m py_compile tools/audit_nle_persistence_cutover.py tests/test_nle_persistence_cutover_audit.py core/runtime/config.py core/project/project_format.py tests/test_macos_bundle_runtime_paths.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_nle_persistence_cutover_audit.py` -> `6 passed`.
  - `./venv/bin/python tools/audit_nle_persistence_cutover.py --output-dir output/manual_verification/latest/nle_load_owner_rollback_boundary_v040124_20260629_1138` -> `status=blocked`, `overall_stoplight=red`, ready/blocked gates `7/5`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_nle_persistence_cutover_audit.py tests/test_nle_canonical_load_owner_review_packet.py tests/test_project_nle_persistence_guard.py tests/test_project_nle_snapshot.py tests/test_macos_bundle_runtime_paths.py` -> `39 passed, 4 subtests passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_context.py tests/test_cp03_cp04_status_ui.py -k "schema or version or project_file_roundtrip or status"` -> `66 passed, 80 deselected`.
  - Direct version assertion -> `APP_VERSION=04.01.24`, `PROJECT_SCHEMA_VERSION=04.01.24`.
  - `git diff --check -- .` -> pass.

## v04.01.23 G2 Canonical Load-Owner Gate Matrix Audit - 2026-06-29 KST

- 실행 모드: source-app G2 NLE canonical load-owner gate matrix audit, compatibility false-positive guards, and version/schema bump.
- 결과: pass for the bounded audit slice. Full NLE disk-format cutover remains blocked because rollback boundary, canonical load-owner approval, `nle_snapshot` canonical-source policy, runtime-state persistence policy, legacy disk-shape replacement policy, and final cutover proof are still incomplete.
- 저장 위치:
  - Release note: `docs/release_notes/RELEASE_v04.01.23.md`
  - Audit report: `output/manual_verification/latest/nle_canonical_load_owner_gate_matrix_v040123_20260629_1115/nle_persistence_cutover_audit.md`
  - Audit JSON: `output/manual_verification/latest/nle_canonical_load_owner_gate_matrix_v040123_20260629_1115/nle_persistence_cutover_audit.json`
  - Completed archive: `docs/planning_queue/COMPLETED_ACTION_ITEMS.md#v040123-g2-canonical-load-owner-gate-matrix-audit`
- 실제 결과:
  - App version updated to `04.01.23`.
  - Project schema version updated to `04.01.23`.
  - `tools/audit_nle_persistence_cutover.py` now reports app version and canonical load-owner gate matrix state.
  - Audit state: `status=blocked`, `app_version=04.01.23`, `prep_ready=true`, `persistence_cutover_ready=false`, `top_level_nle_compatibility_projection_passed=true`, `top_level_nle_canonical_projection_complete=false`.
  - Gate matrix: `overall_stoplight=red`, ready/blocked gates `6/6`, current canonical owner `legacy_editor_state`, target candidate `top_level_nle_shadow_metadata`.
  - Blocked gates: `rollback_boundary_defined`, `canonical_load_owner_change_allowed`, `nle_snapshot_canonical_load_source_allowed`, `runtime_project_state_persistence_allowed`, `legacy_disk_shape_replacement_allowed`, and `final_cutover_ready`.
  - False-positive guard: explicit top-level `nle` projection first caption text is `nle shadow first`; default load and resave first caption text remain legacy `first`.
  - This is cutover preflight audit evidence only; it is not a canonical load-owner switch, disk-format cutover, runtime-state persistence, legacy shape replacement, or UI/UX change.
- 검증:
  - `./venv/bin/python -m py_compile tools/audit_nle_persistence_cutover.py tests/test_nle_persistence_cutover_audit.py core/runtime/config.py core/project/project_format.py tests/test_macos_bundle_runtime_paths.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_nle_persistence_cutover_audit.py` -> `6 passed`.
  - `./venv/bin/python tools/audit_nle_persistence_cutover.py --output-dir output/manual_verification/latest/nle_canonical_load_owner_gate_matrix_v040123_20260629_1115` -> `status=blocked`, `overall_stoplight=red`, ready/blocked gates `6/6`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_nle_persistence_cutover_audit.py tests/test_nle_canonical_load_owner_review_packet.py tests/test_project_nle_persistence_guard.py tests/test_project_nle_snapshot.py tests/test_macos_bundle_runtime_paths.py` -> `39 passed, 4 subtests passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_context.py tests/test_cp03_cp04_status_ui.py -k "schema or version or project_file_roundtrip or status"` -> `66 passed, 80 deselected`.
  - Direct version assertion -> `APP_VERSION=04.01.23`, `PROJECT_SCHEMA_VERSION=04.01.23`.
  - `git diff --check -- .` -> pass.

## v04.01.22 G0 App Store Readiness Blocker Matrix Audit - 2026-06-29 KST

- 실행 모드: non-destructive G0 App Store readiness blocker matrix audit, metadata owner-input package refresh, false-positive guard tests, and version/schema bump.
- 결과: pass for the bounded audit/package slice. App Store submission remains blocked because signed `.pkg`, strict App Store-candidate `codesign`, `pkgutil --check-signature`, sandbox smoke, App Store Connect validation, Apple Distribution/installer identities, and owner metadata values are still missing.
- 저장 위치:
  - Release note: `docs/release_notes/RELEASE_v04.01.22.md`
  - Audit report: `output/manual_verification/latest/app_store_readiness_blocker_matrix_v040122_20260629_1100/app_store_readiness_audit.md`
  - Audit JSON: `output/manual_verification/latest/app_store_readiness_blocker_matrix_v040122_20260629_1100/app_store_readiness_audit.json`
  - Metadata owner-input package: `output/manual_verification/latest/app_store_metadata_owner_input_package_v040122_20260629_1100/app_store_metadata_owner_input_package.md`
  - Completed archive: `docs/planning_queue/COMPLETED_ACTION_ITEMS.md#v040122-g0-app-store-readiness-blocker-matrix-audit`
- 실제 결과:
  - App version updated to `04.01.22`.
  - Project schema version updated to `04.01.22`.
  - `tools/audit_app_store_readiness.py` now reports app version, blocker group counts, stoplight state, and submission gate summary.
  - Strict `codesign` and `pkgutil --check-signature` proof artifacts are required before signed artifacts can be treated as ready.
  - `tools/generate_app_store_metadata_package.py` now carries the refreshed readiness snapshot, app version, stoplight, and blocker group counts into the owner-input package.
  - Current readiness state: `local_packaging_ready=true`, `app_store_submission_ready=false`, overall stoplight `red`, blocker count `17`.
  - Blocker groups: `version_lock=0`, `packaging_template=0`, `signed_artifacts=3`, `sandbox_smoke=1`, `app_store_connect=1`, `signing_identities=4`, `owner_metadata=8`, `unknown=0`.
  - Submission gates ready: version lock, packaging template, signed app bundle presence, and App Store Connect auth.
  - Submission gates not ready: signed App Store `.pkg`, strict `codesign`, `pkgutil --check-signature`, signed-artifacts group, sandbox smoke, App Store Connect validation, Apple Distribution identity, installer identity, owner metadata, and final submission.
- 검증:
  - `./venv/bin/python -m py_compile tools/audit_app_store_readiness.py tools/generate_app_store_metadata_package.py tests/test_app_store_readiness_audit.py tests/test_app_store_metadata_package.py core/runtime/config.py core/project/project_format.py tests/test_macos_bundle_runtime_paths.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_app_store_readiness_audit.py tests/test_app_store_metadata_package.py tests/test_macos_bundle_runtime_paths.py` -> `17 passed`.
  - `./venv/bin/python tools/audit_app_store_readiness.py --output-dir output/manual_verification/latest/app_store_readiness_blocker_matrix_v040122_20260629_1100` -> `status=blocked`, overall stoplight `red`, blocker count `17`.
  - `./venv/bin/python tools/generate_app_store_metadata_package.py --output-dir output/manual_verification/latest/app_store_metadata_owner_input_package_v040122_20260629_1100` -> `not_submission_proof=true`, pending owner-input metadata `8/8`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_context.py tests/test_cp03_cp04_status_ui.py -k "schema or version or project_file_roundtrip or status"` -> `66 passed, 80 deselected`.
  - Direct version assertion -> `APP_VERSION=04.01.22`, `PROJECT_SCHEMA_VERSION=04.01.22`.
  - `git diff --check -- .` -> pass.

## v04.01.21 G2 Top-Level NLE Gap Projection Coverage Audit - 2026-06-29 KST

- 실행 모드: source-app G2 NLE top-level shadow gap projection coverage audit, compatibility false-positive guards, and version/schema bump.
- 결과: pass for the bounded compatibility-audit slice. The previous gap coverage blocker is closed, but the audit remains blocked for canonical cutover because default project load still uses legacy `editor_state` rows and load-owner/disk-format cutover remains disallowed.
- 저장 위치:
  - Release note: `docs/release_notes/RELEASE_v04.01.21.md`
  - Audit report: `output/manual_verification/latest/nle_top_level_gap_projection_v040121_20260629_1041/nle_persistence_cutover_audit.md`
  - Audit JSON: `output/manual_verification/latest/nle_top_level_gap_projection_v040121_20260629_1041/nle_persistence_cutover_audit.json`
  - Completed archive: `docs/planning_queue/COMPLETED_ACTION_ITEMS.md#v040121-g2-top-level-nle-gap-projection-coverage-audit`
- 실제 결과:
  - App version updated to `04.01.21`.
  - Project schema version updated to `04.01.21`.
  - `core/project/nle_snapshot.py` now represents legacy gap rows as non-caption `GapSegment` metadata on `Sequence.gaps` inside approved top-level `nle` shadow payloads.
  - `tools/audit_nle_persistence_cutover.py` now reports explicit top-level caption plus gap compatibility projection while preserving default legacy project load.
  - Audit state: `status=blocked`, `prep_ready=true`, `persistence_cutover_ready=false`, `top_level_nle_compatibility_projection_passed=true`, `top_level_nle_canonical_projection_complete=false`.
  - Compatibility projection state: `status=gap_projection_coverage_ready_blocked`, `not_runtime_change=true`, current canonical owner `legacy_editor_state`, default load source `legacy_editor_state`, explicit projection source `top_level_nle_shadow_metadata`, explicit/default row-caption-gap counts `3/2/1`, and `gap_coverage_ready=true`.
  - Canonical load-owner change and disk-format cutover remain disallowed.
- 검증:
  - `./venv/bin/python -m py_compile core/project/nle_snapshot.py tools/audit_nle_persistence_cutover.py tests/test_nle_persistence_cutover_audit.py tests/test_project_nle_snapshot.py tests/test_project_nle_persistence_guard.py core/runtime/config.py core/project/project_format.py tests/test_macos_bundle_runtime_paths.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_nle_persistence_cutover_audit.py` -> `6 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_persistence_guard.py tests/test_project_nle_snapshot.py -k "top_level or readback or direct_srt or snapshot_adapter"` -> `7 passed, 17 deselected`.
  - `./venv/bin/python tools/audit_nle_persistence_cutover.py --output-dir output/manual_verification/latest/nle_top_level_gap_projection_v040121_20260629_1041` -> `status=blocked`, `gap_coverage_ready=true`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_nle_persistence_cutover_audit.py tests/test_nle_canonical_load_owner_review_packet.py tests/test_project_nle_persistence_guard.py tests/test_project_nle_snapshot.py tests/test_macos_bundle_runtime_paths.py` -> `39 passed, 4 subtests passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_context.py tests/test_cp03_cp04_status_ui.py -k "schema or version or project_file_roundtrip or status"` -> `66 passed, 80 deselected`.
  - Direct version assertion -> `APP_VERSION=04.01.21`, `PROJECT_SCHEMA_VERSION=04.01.21`.
  - `git diff --check -- .` -> pass.

## v04.01.20 G2 Top-Level NLE Compatibility Projection Audit - 2026-06-29 KST

- 실행 모드: source-app G2 NLE persistence cutover audit extension, compatibility projection false-positive guards, and version/schema bump.
- 결과: pass for the bounded compatibility-audit slice. The audit remains blocked for canonical cutover because top-level projection gap coverage is incomplete and default project load still uses legacy `editor_state` rows.
- 저장 위치:
  - Release note: `docs/release_notes/RELEASE_v04.01.20.md`
  - Audit report: `output/manual_verification/latest/nle_top_level_compatibility_projection_v040120_20260629_1018/nle_persistence_cutover_audit.md`
  - Audit JSON: `output/manual_verification/latest/nle_top_level_compatibility_projection_v040120_20260629_1018/nle_persistence_cutover_audit.json`
  - Completed archive: `docs/planning_queue/COMPLETED_ACTION_ITEMS.md#v040120-g2-top-level-nle-compatibility-projection-audit`
- 실제 결과:
  - App version updated to `04.01.20`.
  - Project schema version updated to `04.01.20`.
  - `tools/audit_nle_persistence_cutover.py` now reports `top_level_nle_compatibility_projection`.
  - Audit state: `status=blocked`, `prep_ready=true`, `top_level_nle_compatibility_projection_passed=true`, `top_level_nle_canonical_projection_complete=false`.
  - Compatibility projection state: `status=compatibility_projection_partial_blocked`, `not_runtime_change=true`, current canonical owner `legacy_editor_state`, default load source `legacy_editor_state`, explicit projection source `top_level_nle_shadow_metadata`, explicit projection differs from default legacy captions, explicit projection caption/gap count `2/0`, default row/caption/gap count `3/2/1`, and `gap_coverage_ready=false`.
  - Canonical load-owner change and disk-format cutover remain disallowed.
- 검증:
  - `./venv/bin/python -m py_compile tools/audit_nle_persistence_cutover.py tests/test_nle_persistence_cutover_audit.py core/runtime/config.py core/project/project_format.py tests/test_macos_bundle_runtime_paths.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_nle_persistence_cutover_audit.py tests/test_nle_canonical_load_owner_review_packet.py tests/test_project_nle_persistence_guard.py tests/test_macos_bundle_runtime_paths.py` -> `23 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_snapshot.py -k "readback or direct_srt"` -> `3 passed, 13 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_context.py tests/test_cp03_cp04_status_ui.py -k "schema or version or project_file_roundtrip or status"` -> `66 passed, 80 deselected`.
  - Direct version assertion -> `APP_VERSION=04.01.20`, `PROJECT_SCHEMA_VERSION=04.01.20`.
  - `git diff --check -- .` -> pass.

## v04.01.19 G2 NLE Canonical Load-Owner Review Packet - 2026-06-29 KST

- 실행 모드: source-app G2 NLE canonical load-owner owner-review packet generator, false-positive guard tests, and version/schema bump.
- 결과: pass for the bounded owner-review packet slice. This is review evidence only; it does not switch project load ownership to NLE and does not enable full NLE disk-format cutover.
- 저장 위치:
  - Release note: `docs/release_notes/RELEASE_v04.01.19.md`
  - Review packet: `output/manual_verification/latest/nle_canonical_load_owner_review_packet_v040119_20260629_095907/nle_canonical_load_owner_review_packet.md`
  - Decision matrix: `output/manual_verification/latest/nle_canonical_load_owner_review_packet_v040119_20260629_095907/decision_matrix.json`
  - Source audit: `output/manual_verification/latest/nle_canonical_load_owner_audit_v040119_20260629_095907/nle_persistence_cutover_audit.md`
  - Completed archive: `docs/planning_queue/COMPLETED_ACTION_ITEMS.md#v040119-g2-nle-canonical-load-owner-review-packet`
- 실제 결과:
  - App version updated to `04.01.19`.
  - Project schema version updated to `04.01.19`.
  - `tools/generate_nle_canonical_load_owner_review_packet.py` now writes JSON/Markdown owner-review artifacts from the current NLE persistence cutover audit.
  - Generated packet state: `status=owner_review_required_blocked`, `not_runtime_change=true`, `canonical_load_owner_unchanged=true`, current canonical owner `legacy_editor_state`, `canonical_load_owner_change_allowed=false`, `disk_format_cutover_allowed=false`.
  - Evidence preserved: `prep_ready=true`, `persistence_cutover_ready=false`, `top_level_nle_shadow_ready=true`, top-level `nle` schema `ai_subtitle_studio.nle_shadow_project.v1`, role `shadow_metadata`, runtime project state persisted `false`, operation roundtrip `11` families all passed, render/export final invalid/non-monotonic/overlap `0/0/0`, and global max active `1`.
  - Decision matrix keeps top-level `nle` canonical load-owner switch, `nle_snapshot` canonical load-source switch, persisted `_nle_project_state`, and legacy `editor_state` compatibility removal owner-approved, rollback-boundary gated, and currently disallowed.
- 검증:
  - `./venv/bin/python -m py_compile tools/generate_nle_canonical_load_owner_review_packet.py tests/test_nle_canonical_load_owner_review_packet.py core/runtime/config.py core/project/project_format.py tests/test_macos_bundle_runtime_paths.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_nle_canonical_load_owner_review_packet.py tests/test_nle_persistence_cutover_audit.py tests/test_macos_bundle_runtime_paths.py` -> `15 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_context.py tests/test_cp03_cp04_status_ui.py -k "schema or version or project_file_roundtrip or status"` -> `66 passed, 80 deselected`.
  - Direct version assertion -> `APP_VERSION=04.01.19`, `PROJECT_SCHEMA_VERSION=04.01.19`.
  - `git diff --check -- .` -> pass.

## v04.01.18 G1 STT Cache Default Review Packet - 2026-06-29 KST

- 실행 모드: source-app G1 collect-cache owner-review packet generator, false-positive guard tests, and version/schema bump.
- 결과: pass for the bounded owner-review packet slice. This is review evidence only; it does not enable collect caches by default and does not claim production speed improvement.
- 저장 위치:
  - Release note: `docs/release_notes/RELEASE_v04.01.18.md`
  - Review packet: `output/manual_verification/latest/stt_cache_default_review_packet_v040118_20260629_094703/stt_cache_default_review_packet.md`
  - Decision matrix: `output/manual_verification/latest/stt_cache_default_review_packet_v040118_20260629_094703/decision_matrix.json`
  - Completed archive: `docs/planning_queue/COMPLETED_ACTION_ITEMS.md#v040118-g1-stt-cache-default-review-packet`
- 실제 결과:
  - App version updated to `04.01.18`.
  - Project schema version updated to `04.01.18`.
  - `tools/generate_stt_cache_default_review_packet.py` now writes JSON/Markdown owner-review artifacts from the existing NAS collect-cache backfill evidence.
  - Generated packet state: `status=owner_review_required`, `not_runtime_change=true`, `production_defaults_unchanged=true`, `default_promotion_allowed=false`, current defaults `false/false`.
  - Evidence preserved: write/hit elapsed `177.888s -> 1.183s`, raw/final/reference `58/56/89`, quality/text/timing `93.766/94.267/0.5808s`, final invalid/non-monotonic/overlap `0/0/0`, final last end/duration bound `180.0/180.0`, global max active `1`, timeout detected `false`.
  - Decision matrix keeps STT1, STT2 recheck, and word precision cache promotion owner-approved, one-cache-at-a-time, and rollback-boundary gated.
- 검증:
  - `./venv/bin/python -m py_compile tools/generate_stt_cache_default_review_packet.py tests/test_stt_cache_default_review_packet.py core/runtime/config.py core/project/project_format.py tests/test_macos_bundle_runtime_paths.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_stt_cache_default_review_packet.py tests/test_macos_bundle_runtime_paths.py` -> `10 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_context.py tests/test_cp03_cp04_status_ui.py -k "schema or version or project_file_roundtrip or status"` -> `66 passed, 80 deselected`.
  - Direct version assertion -> `APP_VERSION=04.01.18`, `PROJECT_SCHEMA_VERSION=04.01.18`.
  - `git diff --check -- .` -> pass.

## v04.01.17 G0 Source Quick QA Baseline Before Packaging - 2026-06-29 KST

- 실행 모드: source-app G0 quick QA baseline before packaging and version/schema bump.
- 결과: pass for the bounded source-app baseline slice. This is source-app editor workflow baseline only; it is not signed package, sandbox smoke, App Store validation/upload/submission, owner metadata, full QA, real-media STT quality, roughcut, or X5 rolling proof.
- 저장 위치:
  - Release note: `docs/release_notes/RELEASE_v04.01.17.md`
  - Quick QA baseline: `output/manual_verification/latest/qa_suite_quick_v040117_20260629_0929/suite_result.md`
  - Completed archive: `docs/planning_queue/COMPLETED_ACTION_ITEMS.md#v040117-g0-source-quick-qa-baseline-before-packaging`
- 실제 결과:
  - App version updated to `04.01.17`.
  - Project schema version updated to `04.01.17`.
  - Quick QA result: `profile=quick`, `scenario_count=1`, scenario `editor_compact_macau`, `passed_count=1`, `failed_count=0`.
  - The quick path covered source-app compact editor automation: project open, snapshots, playhead, smart split, inline edit, timeline view controls, global menu save/status, play/pause command, segment/diamond edit, save, and final status.
- 검증:
  - `AI_SUBTITLE_STUDIO_QA_USE_SOURCE=1 QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/qa_suite_runner.py quick --output-dir output/manual_verification/latest/qa_suite_quick_v040117_20260629_0929` -> `failed_count=0`.
  - `./venv/bin/python -m py_compile core/runtime/config.py core/project/project_format.py tests/test_macos_bundle_runtime_paths.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_macos_bundle_runtime_paths.py` -> `4 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_context.py tests/test_cp03_cp04_status_ui.py -k "schema or version or project_file_roundtrip or status"` -> `66 passed, 80 deselected`.
  - Direct version assertion -> `APP_VERSION=04.01.17`, `PROJECT_SCHEMA_VERSION=04.01.17`.
  - `git diff --check -- .` -> pass.

## v04.01.16 G0 App Store Metadata Owner-Input Package - 2026-06-29 KST

- 실행 모드: source-app G0 Mac App Store metadata owner-input package generator, false-positive guard tests, and version/schema bump.
- 결과: pass for the bounded owner-input package slice. This is not App Store submission proof because the generated package remains `not_submission_proof=true`, `owner_input_complete=false`, and `app_store_submission_ready=false`.
- 저장 위치:
  - Release note: `docs/release_notes/RELEASE_v04.01.16.md`
  - Metadata owner-input package: `output/manual_verification/latest/app_store_metadata_owner_input_package_v040116_20260629_0921/app_store_metadata_owner_input_package.md`
  - Completed archive: `docs/planning_queue/COMPLETED_ACTION_ITEMS.md#v040116-g0-app-store-metadata-owner-input-package`
- 실제 결과:
  - App version updated to `04.01.16`.
  - Project schema version updated to `04.01.16`.
  - `tools/generate_app_store_metadata_package.py` now writes JSON/Markdown owner-input artifacts from the existing App Store readiness audit constants and report surface.
  - Generated package state: `status=blocked`, `not_submission_proof=true`, `owner_input_complete=false`, `app_store_submission_ready=false`, pending owner-input metadata `8/8`, and forbidden-claim scan `pass` with `0` matches.
  - The package includes a sanitized readiness snapshot without raw keychain identity names, plus separate audit owner-input and App Store Connect metadata-fill matrices.
- 검증:
  - `./venv/bin/python -m py_compile tools/generate_app_store_metadata_package.py tools/audit_app_store_readiness.py tests/test_app_store_metadata_package.py tests/test_app_store_readiness_audit.py core/runtime/config.py core/project/project_format.py tests/test_macos_bundle_runtime_paths.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_app_store_metadata_package.py tests/test_app_store_readiness_audit.py tests/test_macos_bundle_runtime_paths.py` -> `14 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_context.py tests/test_cp03_cp04_status_ui.py -k "schema or version or project_file_roundtrip or status"` -> `66 passed, 80 deselected`.
  - Direct version assertion -> `APP_VERSION=04.01.16`, `PROJECT_SCHEMA_VERSION=04.01.16`.
  - `git diff --check -- .` -> pass.

## v04.01.15 G0 App Store Identity And Metadata Blocker Refresh - 2026-06-29 KST

- 실행 모드: source-app G0 Mac App Store readiness blocker refresh, keychain identity audit hardening, and version/schema bump.
- 결과: pass for the bounded blocker-refresh slice. This is not App Store submission proof because the latest audit remains `status=blocked` and `app_store_submission_ready=false`.
- 저장 위치:
  - Release note: `docs/release_notes/RELEASE_v04.01.15.md`
  - Blocker refresh audit: `output/manual_verification/latest/app_store_identity_metadata_blocker_v040115_20260629_0907/app_store_readiness_audit.md`
  - Completed archive: `docs/planning_queue/COMPLETED_ACTION_ITEMS.md#v040115-g0-app-store-identity-and-metadata-blocker-refresh`
- 실제 결과:
  - App version updated to `04.01.15`.
  - Project schema version updated to `04.01.15`.
  - `tools/audit_app_store_readiness.py` now records local keychain identity presence for Apple Development, Apple Distribution, and 3rd Party Mac Developer Installer identities.
  - The readiness audit now emits explicit blockers for `apple_distribution_identity_missing_from_keychain` and `installer_identity_missing_from_keychain`.
  - Latest audit result: `status=blocked`, `submission_target=mac_app_store_pkg`, `local_packaging_ready=true`, `app_store_submission_ready=false`, blocker count `15`, Apple Development identity present, Apple Distribution identity missing, installer identity missing, and owner-input metadata pending `8/8`.
- 검증:
  - `./venv/bin/python -m py_compile tools/audit_app_store_readiness.py tests/test_app_store_readiness_audit.py core/runtime/config.py core/project/project_format.py tests/test_macos_bundle_runtime_paths.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_app_store_readiness_audit.py tests/test_macos_bundle_runtime_paths.py` -> `10 passed`.
  - Direct version assertion -> `APP_VERSION=04.01.15`, `PROJECT_SCHEMA_VERSION=04.01.15`.
  - `git diff --check -- .` -> pass.

## v04.01.14 G3 Active Global-Canvas Responsiveness Proof - 2026-06-29 KST

- 실행 모드: source-app G3 same-media active global-canvas/timeline responsiveness proof and version/schema bump.
- 결과: pass for the bounded active global-canvas responsiveness slice. This is not full G3 completion because any additional active-worker final-surface proof remains a separate gate if selected by the queue.
- 저장 위치:
  - Release note: `docs/release_notes/RELEASE_v04.01.14.md`
  - Active global-canvas proof: `output/manual_verification/latest/g3_global_canvas_responsiveness_v040114_20260629_084817/report.md`
  - Completed archive: `docs/planning_queue/COMPLETED_ACTION_ITEMS.md#v040114-g3-active-global-canvas-responsiveness-proof`
- 실제 결과:
  - App version updated to `04.01.14`.
  - Project schema version updated to `04.01.14`.
  - `tools/remote_verify.py editor-sequence` can now map existing timeline/global proof actions: `timeline-zoom-in`, `timeline-zoom-out`, `timeline-fit`, `timeline-time-window`, `timeline-max`, and `zoom-max`.
  - Active proof: `open-media` and `start-current-pipeline` succeeded, active samples reported `ST_PROC/backend_active=true`, timeline zoom/fit/time-window/max plus zoom-max/play/pause/status/guided-status all returned `ok=true`, max command elapsed was `0.267435s`, all `19` snapshots were nonzero, final track count stayed `0`, and cancel returned to `backend_active=false`.
- 검증:
  - `./venv/bin/python -m py_compile core/runtime/config.py core/project/project_format.py tools/remote_verify.py tests/test_remote_verify_actions.py tests/test_macos_bundle_runtime_paths.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_remote_verify_actions.py -k "global_canvas_responsiveness or generation_status_and_wait or active_worker_control"` -> `3 passed, 13 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_app_command_bridge.py -k "editor_timeline_view_command_exercises_zoom_and_fit or status_command_reports_compact_nle_runtime_track_counts or dispatch_status_command"` -> `7 passed, 77 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_app_store_readiness_audit.py tests/test_macos_bundle_runtime_paths.py` -> `9 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_context.py tests/test_cp03_cp04_status_ui.py -k "schema or version or project_file_roundtrip or status"` -> `66 passed, 80 deselected`.
  - Direct version assertion -> `APP_VERSION=04.01.14`, `PROJECT_SCHEMA_VERSION=04.01.14`.
  - `git diff --check -- .` -> pass.

## v04.01.13 G3 Open-Media Generation And Active-Worker Responsiveness Proof - 2026-06-29 KST

- 실행 모드: source-app G3 same-media app-command open/start/status/cancel/close/quit responsiveness proof and version/schema bump.
- 결과: pass for the bounded active-worker responsiveness slice. This is not full G3 completion because broader global-canvas responsiveness and any additional active-worker final-surface proof remain separate gates.
- 저장 위치:
  - Release note: `docs/release_notes/RELEASE_v04.01.13.md`
  - Cancel proof: `output/manual_verification/latest/g3_open_media_generation_responsiveness_v040113_cancel_20260629_083050/report.md`
  - Close proof: `output/manual_verification/latest/g3_open_media_generation_responsiveness_v040113_close_20260629_083123/report.json`
  - Quit proof: `output/manual_verification/latest/g3_open_media_generation_responsiveness_v040113_quit_20260629_083225/report.json`
  - Completed archive: `docs/planning_queue/COMPLETED_ACTION_ITEMS.md#v040113-g3-open-media-generation-and-active-worker-responsiveness-proof`
- 실제 결과:
  - App version updated to `04.01.13`.
  - Project schema version updated to `04.01.13`.
  - `cancel-current-pipeline`, `app-close-request`, and `app-quit-request` are available as automation-only app commands.
  - `tools/remote_verify.py editor-sequence` can now record `start-current-pipeline`, active status probes, guided-status probes, `wait-N`, and command elapsed timings.
  - Cancel proof: `open-media` and `start-current-pipeline` succeeded, active samples reported `ST_PROC/backend_active=true`, status/guided-status command elapsed samples stayed below `0.01s`, and cancel returned `current_pipeline_cancel_requested` before post-cancel `ST_IDLE/backend_active=false`.
  - Close proof: `app-close-request` returned while active in `0.009954s`, then bridge became `app_unreachable` after app exit.
  - Quit proof: `app-quit-request` returned while active in `0.001577s`, then bridge became `app_unreachable` after app exit.
- 검증:
  - `./venv/bin/python -m py_compile ui/main/app_command_bridge_handlers.py tools/appctl.py tools/remote_verify.py tests/test_app_command_bridge.py tests/test_appctl.py tests/test_remote_verify_actions.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_appctl.py tests/test_remote_verify_actions.py -k "active_worker_control or generation_status_and_wait or editor_sequence_maps_play_pause"` -> `4 passed, 18 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_app_command_bridge.py -k "cancel_current_pipeline or app_close_and_quit_requests or global_menu_action_rejects_unsafe_action or start_current_pipeline"` -> `4 passed, 80 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_app_store_readiness_audit.py tests/test_macos_bundle_runtime_paths.py` -> `9 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_context.py tests/test_cp03_cp04_status_ui.py -k "schema or version or project_file_roundtrip or status"` -> `66 passed, 80 deselected`.
  - Direct version assertion -> `APP_VERSION=04.01.13`, `PROJECT_SCHEMA_VERSION=04.01.13`.
  - `git diff --check -- .` -> pass.

## v04.01.12 G3 Direct-SRT App-Command Save/Reopen/Export Proof - 2026-06-29 KST

- 실행 모드: source-app G3 direct-SRT app-command save/project/SRT/video export, reopened project export proof, and version/schema bump.
- 결과: pass for direct-SRT app-command save/reopen/export stability. This is not full G3 completion because `open-media` generation proof and active-worker cancel/quit/close responsiveness remain separate gates.
- 저장 위치:
  - Release note: `docs/release_notes/RELEASE_v04.01.12.md`
  - Direct SRT save/export proof: `output/manual_verification/latest/g3_same_media_app_commands_srt_fixed_v2_20260629/report.md`
  - Reopen/export proof: `output/manual_verification/latest/g3_same_media_app_commands_reopen_fixed_v2_20260629/report.md`
  - Completed archive: `docs/planning_queue/COMPLETED_ACTION_ITEMS.md#v040112-g3-direct-srt-app-command-savereopenexport-proof`
- 실제 결과:
  - App version updated to `04.01.12`.
  - Project schema version updated to `04.01.12`.
  - `save-project` app command now uses the same final SRT segment authority as `save-subtitles` / `export-subtitles` and reports `segment_count`.
  - Direct SRT project save skips cut-boundary re-splitting, preserving opened SRT rows for save/reopen.
  - Direct proof: `save-project segment_count=64`, `export-subtitles segment_count=64`, manual export SRT `64` blocks, editor/runtime final count `64`, project saved row count `64`, project final SRT `64` blocks, MOV output `6764026` bytes.
  - Reopen proof: reopened editor final count `64`, export-subtitles `segment_count=64`, manual export SRT `64` blocks, NLE runtime final track `64`, MOV output `6764026` bytes.
- 검증:
  - `./venv/bin/python -m py_compile core/project/project_manager.py ui/project/project_panel.py ui/editor/editor_save_manager.py ui/main/app_command_bridge_handlers.py tests/test_project_context.py tests/test_app_command_bridge.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_context.py -k "skip_cut_boundary_snap_for_direct_srt_rows or cut_boundary_fit_prevents"` -> `2 passed, 85 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_app_command_bridge.py -k "save_project_command"` -> `4 passed, 78 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_app_command_bridge.py tests/test_project_context.py tests/test_editor_autosave_cleanup.py tests/test_project_segment_reload.py tests/test_project_nle_runtime_cutover.py tests/test_project_assets.py -k "save_project_command or skip_cut_boundary_snap_for_direct_srt_rows or direct_srt or deferred_project_save or save_export_cutover or externalize"` -> `37 passed, 297 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_app_store_readiness_audit.py tests/test_macos_bundle_runtime_paths.py` -> `9 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_context.py tests/test_cp03_cp04_status_ui.py -k "schema or version or project_file_roundtrip or status"` -> `66 passed, 80 deselected`.
  - Direct version assertion -> `APP_VERSION=04.01.12`, `PROJECT_SCHEMA_VERSION=04.01.12`.
  - `git diff --check -- .` -> pass.

## v04.01.11 G3 Same-Media Benchmark Acceptance And Editor-Sequence Guard - 2026-06-29 KST

- 실행 모드: source-app G3 same-media NAS HeyDealer benchmark acceptance, STT timeout audit, editor-sequence proof-harness guard, and version/schema bump.
- 결과: pass for same-media benchmark acceptance and proof-harness guard. This is not full G3 app-command save/export acceptance because the guarded app-command proof attempt recorded `open_app_unreachable`.
- 저장 위치:
  - Release note: `docs/release_notes/RELEASE_v04.01.11.md`
  - Preflight: `output/manual_verification/latest/g3_same_media_quality_speed_v040111_20260629_preflight/reference_fixture_availability.md`
  - Benchmark: `.codex_work/benchmarks/subtitle_pipeline_variants/20260629_070403/benchmark_results.json`
  - Acceptance: `output/manual_verification/latest/g3_same_media_quality_speed_v040111_20260629/acceptance/reference_benchmark_acceptance.md`
  - Timeout audit: `output/manual_verification/latest/g3_same_media_quality_speed_v040111_20260629/timeout_audit/stt_worker_timeout_audit.md`
  - Guarded app-command proof attempt: `output/manual_verification/latest/g3_same_media_app_commands_v040111_20260629_guarded/report.md`
  - Jammini probe: `.agents/sentinel/handoffs/20260629-070211-watchdog-handoff-probe.md`
- 실제 결과:
  - App version updated to `04.01.11`.
  - Project schema version updated to `04.01.11`.
  - Same-media NAS HeyDealer preflight passed with media/SRT present, SRT parse OK, and clipped reference rows `89`.
  - Same-media High-mode benchmark was accepted: elapsed `45.671s`, raw/final/reference `58/56/89`, quality/text/timing `93.766/94.267/0.5808`, final invalid/non-monotonic/overlap `0/0/0`, final stable `true`, final last end/duration bound `180.0/180.0`, final short/long `0/0`, global max active `1`, and global stable `true`.
  - STT worker timeout audit reported `timeout_detected=false`.
  - `tools/remote_verify.py editor-sequence` now writes partial reports step-by-step, caps post-step probes, validates returned video export artifacts, and aborts immediately when `open-media` is app-unreachable.
  - Guarded app-command proof attempt produced a durable report with `abort_reason=open_app_unreachable`; app-command final export proof remains HOLD.
- 검증:
  - `./venv/bin/python -m py_compile tools/remote_verify.py tests/test_remote_verify_actions.py tests/test_macos_bundle_runtime_paths.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_remote_verify_actions.py -k "editor_sequence or export_subtitle_video_step or capture_snapshot"` -> `7 passed, 6 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_remote_verify_actions.py` -> `13 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_app_store_readiness_audit.py tests/test_macos_bundle_runtime_paths.py` -> `9 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_context.py tests/test_cp03_cp04_status_ui.py -k "schema or version or project_file_roundtrip or status"` -> `66 passed, 79 deselected`.
  - Direct version assertion -> `APP_VERSION=04.01.11`, `PROJECT_SCHEMA_VERSION=04.01.11`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/evaluate_reference_benchmark_acceptance.py .codex_work/benchmarks/subtitle_pipeline_variants/20260629_070403/benchmark_results.json --media-duration-sec 180.0 --output-dir output/manual_verification/latest/g3_same_media_quality_speed_v040111_20260629/acceptance` -> `accepted=true`.
  - `./venv/bin/python tools/audit_stt_worker_timeout.py .codex_work/benchmarks/subtitle_pipeline_variants/20260629_070403/benchmark_results.json --output-dir output/manual_verification/latest/g3_same_media_quality_speed_v040111_20260629/timeout_audit` -> `timeout_detected=false`.

## v04.01.10 G2/G3 Final Save-Export Micro-Overlap Shared-Boundary Repair - 2026-06-29 KST

- 실행 모드: source-app G2/G3 final save/export micro-overlap repair, direct SRT/export-subtitles projection routing, and version/schema bump.
- 결과: pass for focused final save/export micro-overlap projection behavior. This is not same-media quality/speed, save/reopen, global-canvas, or final export acceptance.
- 저장 위치:
  - Release note: `docs/release_notes/RELEASE_v04.01.10.md`
  - Live SRT projection: `output/manual_verification/latest/nle_save_export_micro_overlap_v040110_20260629/micro_overlap_report.md`
  - Project-5 projection: `output/manual_verification/latest/nle_save_export_micro_overlap_v040110_20260629/project5_micro_overlap_report.md`
  - Jammini probe: `.agents/sentinel/handoffs/20260629-032124-watchdog-handoff-probe.md`
- 실제 결과:
  - App version updated to `04.01.10`.
  - Project schema version updated to `04.01.10`.
  - `core/project/nle_runtime_cutover.py` repairs final save/export overlaps up to the greater of one frame or `0.035s` to a shared boundary when the later row remains valid.
  - Broader or collapse-risk final overlaps still raise `nle_save_export_final_overlap`.
  - Direct opened-media SRT persistence and `export-subtitles` now route rows through the same NLE save/export projection before writing SRT.
  - Live SRT projection stayed `64 -> 64` rows, overlap changed `1 -> 0`, and repaired row count was `1`.
  - Project-5 projection stayed `170 -> 170` rows, repair count was `2`, and projected overlap count was `0`.
- 검증:
  - `./venv/bin/python -m py_compile core/project/nle_runtime_cutover.py ui/editor/editor_save_manager.py ui/main/app_command_bridge_handlers.py tests/test_project_nle_runtime_cutover.py tests/test_project_assets.py tests/test_editor_autosave_cleanup.py tests/test_app_command_bridge.py tests/test_macos_bundle_runtime_paths.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_runtime_cutover.py -k "save_export_cutover or micro_overlap"` -> `8 passed, 7 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_assets.py -k "externalize_project_text_assets"` -> `5 passed, 3 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_editor_autosave_cleanup.py -k "persist_editor_srts or deferred_project_save or close_flush_failure"` -> `9 passed, 43 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_app_command_bridge.py -k "export_subtitles_command or save_subtitles_command or status"` -> `22 passed, 59 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_runtime_cutover.py tests/test_project_assets.py tests/test_editor_autosave_cleanup.py tests/test_app_command_bridge.py` -> `156 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_app_store_readiness_audit.py tests/test_macos_bundle_runtime_paths.py` -> `9 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_context.py tests/test_cp03_cp04_status_ui.py -k "schema or version or project_file_roundtrip or status"` -> `66 passed, 79 deselected`.
  - Direct version assertion -> `APP_VERSION=04.01.10`, `PROJECT_SCHEMA_VERSION=04.01.10`.
  - `git diff --check -- .` -> pass.

## v04.01.09 G3/G2 Final-Overlap Deferred-Save Retry Guard - 2026-06-29 KST

- 실행 모드: source-app G3/G2 deferred-save retry guard, final-overlap nonretryable cleanup, retryable deferred-save preservation, and version/schema bump.
- 결과: pass for focused deferred-save retry behavior. This is not same-media save/reopen or final export acceptance.
- 저장 위치:
  - Release note: `docs/release_notes/RELEASE_v04.01.09.md`
  - Jammini probe: `.agents/sentinel/handoffs/20260629-030627-watchdog-handoff-probe.md`
- 실제 결과:
  - App version updated to `04.01.09`.
  - Project schema version updated to `04.01.09`.
  - `ui/editor/editor_save_manager.py` treats `nle_save_export_final_overlap` as a nonretryable deferred project-save error outside close/exit paths.
  - Final-overlap deferred save clears stale pending snapshot state and does not schedule another retry timer.
  - Retryable writer failures still reschedule through the existing deferred-save retry path.
  - The strict `nle_save_export_final_overlap` save/export guard remains active; the underlying final subtitle overlap remains a separate G2/G3 blocker.
- 검증:
  - `./venv/bin/python -m py_compile ui/editor/editor_save_manager.py tests/test_editor_autosave_cleanup.py tests/test_macos_bundle_runtime_paths.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_editor_autosave_cleanup.py -k "deferred_project_save or close_flush_failure"` -> `7 passed, 44 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_runtime_cutover.py -k "save_export_cutover"` -> `5 passed, 8 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_runtime_cutover.py tests/test_project_assets.py tests/test_editor_autosave_cleanup.py` -> `71 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_app_store_readiness_audit.py tests/test_macos_bundle_runtime_paths.py` -> `9 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_context.py tests/test_cp03_cp04_status_ui.py -k "schema or version or project_file_roundtrip or status"` -> `66 passed, 79 deselected`.
  - Direct version assertion -> `APP_VERSION=04.01.09`, `PROJECT_SCHEMA_VERSION=04.01.09`.
  - `git diff --check -- .` -> pass.

## v04.01.08 G3 Real-Media Live Runtime Observability Proof - 2026-06-29 KST

- 실행 모드: source-app G3 representative real-media live runtime/status proof, STT-source preview-row runtime counting, status budget preservation, and version/schema bump.
- 결과: pass for representative NAS-derived HeyDealer first-180s runtime/status observability. This is not final quality/speed, save/reopen, or final export acceptance.
- 저장 위치:
  - Release note: `docs/release_notes/RELEASE_v04.01.08.md`
  - NAS preflight: `output/manual_verification/latest/g3_live_nle_real_media_preflight_20260629/reference_fixture_availability.md`
  - Live proof: `output/manual_verification/latest/g3_live_nle_real_media_observability_timeout20_20260629/live_nle_runtime_proof.md`
  - Jammini probe: `.agents/sentinel/handoffs/20260629-023155-watchdog-handoff-probe.md`
- 실제 결과:
  - App version updated to `04.01.08`.
  - Project schema version updated to `04.01.08`.
  - `core/engine/subtitle_live_editor_feed.py` counts STT-source-tagged subtitle-preview rows as runtime-reference STT1/STT2 observations without making them final save/export authority.
  - `ui/main/app_command_bridge.py` preserves compact `live_nle_projection_budget` telemetry in normal and busy/fallback status snapshots.
  - `tools/remote_verify.py live-nle-proof` records status timeout/cache/fallback/truncation diagnostics and avoids cached-timeout completion inference.
  - Live proof passed with `failed_sample_count=0`, `generation_completed=true`, pre-final VAD/STT1/STT2 observations `16/172/44`, no missing or insufficient tracks, no raw leak, no final-authority drift, no projection-budget drift, and `21` snapshots.
  - The same run exposed post-SRT-save `nle_save_export_final_overlap` plus repeated deferred-save retry failures; this remains a separate blocker and was not bypassed.
- 검증:
  - `./venv/bin/python -m py_compile core/engine/subtitle_live_editor_feed.py ui/main/app_command_bridge.py tools/remote_verify.py tests/test_subtitle_live_editor_feed_facade.py tests/test_app_command_bridge.py tests/test_remote_verify_actions.py tests/test_macos_bundle_runtime_paths.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_subtitle_live_editor_feed_facade.py tests/test_app_command_bridge.py tests/test_remote_verify_actions.py` -> `95 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_remote_verify_actions.py tests/test_app_command_bridge.py tests/test_app_command_server.py tests/test_subtitle_live_editor_feed_facade.py tests/test_project_nle_runtime_cutover.py` -> `117 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_app_store_readiness_audit.py tests/test_macos_bundle_runtime_paths.py` -> `9 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_context.py tests/test_cp03_cp04_status_ui.py -k "schema or version or project_file_roundtrip or status"` -> `66 passed, 79 deselected`.
  - Direct version assertion -> `APP_VERSION=04.01.08`, `PROJECT_SCHEMA_VERSION=04.01.08`.
  - `git diff --check -- .` -> pass.

## v04.01.07 G3 Live Runtime Observability Strong Evidence Gate - 2026-06-29 KST

- 실행 모드: source-app G3 live NLE runtime observability harness guard, stronger pre-final observation gate, JSONL sample artifact, and version/schema bump.
- 결과: pass for focused mocked status contract coverage. The harness now blocks single-sample observation, completed-sample miscounting, incomplete generation, non-compact runtime payloads, raw runtime payload leakage, final-authority drift, live projection budget drift, and missing/insufficient pre-final VAD/STT1/STT2 observations.
- 저장 위치:
  - Release note: `docs/release_notes/RELEASE_v04.01.07.md`
  - Jammini probe: `.agents/sentinel/handoffs/20260629-021822-watchdog-handoff-probe.md`
  - Jammini review: `.agents/sentinel/handoffs/20260628-272711-g3-observability-strong-evidence-gate-review-jammini.md`
- 실제 결과:
  - App version updated to `04.01.07`.
  - Project schema version updated to `04.01.07`.
  - `tools/remote_verify.py live-nle-proof` now requires at least two distinct active pre-final polls for each required runtime track by default.
  - The harness writes `observability_samples.jsonl` alongside `status_samples.json`, while keeping `live_nle_runtime_proof.json` redacted from detailed sample bodies.
  - No real-media live proof, final quality/speed acceptance, UI layout/label change, STT/VAD algorithm change, worker fan-out change, cache default promotion, App Store package/upload/submission, or persisted NLE disk-format change was performed.
- 검증:
  - `./venv/bin/python -m py_compile tools/remote_verify.py tests/test_remote_verify_actions.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_remote_verify_actions.py` -> `9 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_remote_verify_actions.py tests/test_app_command_bridge.py tests/test_app_command_server.py tests/test_subtitle_live_editor_feed_facade.py tests/test_project_nle_runtime_cutover.py` -> `115 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_app_store_readiness_audit.py tests/test_macos_bundle_runtime_paths.py` -> `9 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_context.py tests/test_cp03_cp04_status_ui.py -k "schema or version or project_file_roundtrip or status"` -> `66 passed, 79 deselected`.
  - Direct version assertion -> `APP_VERSION=04.01.07`, `PROJECT_SCHEMA_VERSION=04.01.07`.

## v04.01.06 G3 Live Runtime Observability Proof Harness - 2026-06-29 KST

- 실행 모드: source-app G3 live NLE runtime observability proof harness, compact status time-series gate, and version/schema bump.
- 결과: pass for harness parser/gate unit coverage, pre-final VAD/STT1/STT2 count acceptance, raw runtime payload leak rejection, final-authority drift rejection, live projection budget drift rejection, and redacted summary/sample artifact separation.
- 저장 위치:
  - Release note: `docs/release_notes/RELEASE_v04.01.06.md`
  - Jammini probe: `.agents/sentinel/handoffs/20260629-020008-watchdog-handoff-probe.md`
  - Jammini review: `.agents/sentinel/handoffs/20260628-270641-g3-live-runtime-observability-proof-review-jammini.md`
- 실제 결과:
  - App version updated to `04.01.06`.
  - Project schema version updated to `04.01.06`.
  - `tools/remote_verify.py live-nle-proof` can start `guided-subtitle-run`, poll compact `guided-subtitle-status`, and write `live_nle_runtime_proof.md/json` plus `status_samples.json`.
  - The harness requires pre-final active samples for `VAD`, `STT1`, and `STT2`, and rejects raw runtime payload leakage, non-final save/export authority drift, and live projection budget drift.
  - No real-media live proof, final quality/speed acceptance, UI layout/label change, STT/VAD algorithm change, worker fan-out change, cache default promotion, App Store package/upload/submission, or persisted NLE disk-format change was performed.
- 검증:
  - `./venv/bin/python -m py_compile tools/remote_verify.py tests/test_remote_verify_actions.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_remote_verify_actions.py` -> `7 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_remote_verify_actions.py tests/test_app_command_bridge.py tests/test_app_command_server.py tests/test_subtitle_live_editor_feed_facade.py tests/test_project_nle_runtime_cutover.py` -> `113 passed`.
  - Direct version assertion -> `APP_VERSION=04.01.06`, `PROJECT_SCHEMA_VERSION=04.01.06`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_app_store_readiness_audit.py tests/test_macos_bundle_runtime_paths.py` -> `9 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_context.py tests/test_cp03_cp04_status_ui.py -k "schema or version or project_file_roundtrip or status"` -> `66 passed, 79 deselected`.

## v04.01.05 G3 Live NLE Projection Scheduler Budget Telemetry - 2026-06-29 KST

- 실행 모드: source-app G3 live NLE projection scheduler-budget telemetry, runtime resource status preservation, and version/schema bump.
- 결과: pass for zero-worker live projection telemetry, active VAD/save/export/close labels, status/busy fallback/UDP telemetry preservation, and expanded final-authority/resource guard coverage.
- 저장 위치:
  - Release note: `docs/release_notes/RELEASE_v04.01.05.md`
  - Jammini probe: `.agents/sentinel/handoffs/20260629-013822-watchdog-handoff-probe.md`
  - Jammini review: `.agents/sentinel/handoffs/20260628-234452-nle-g3-scheduler-budget-telemetry-review-jammini.md`
- 실제 결과:
  - App version updated to `04.01.05`.
  - Project schema version updated to `04.01.05`.
  - `RuntimeResourceCoordinator` now reports `live_nle_projection_budget`.
  - Live projection telemetry keeps `dedicated_worker_count=0`, `max_projection_workers=0`, `shares_subtitle_worker_pool=false`, coalesced updates, stale preview-frame drops, and interactive reserve cores.
  - `status`, `ping`, `guided-subtitle-status`, busy fallback, and UDP compact status preserve the compact scheduler-budget telemetry without raw runtime row payloads.
- 검증:
  - `./venv/bin/python -m py_compile core/runtime/subtitle_resource_manager.py core/runtime/multi_process.py core/automation/app_command_server.py tests/test_subtitle_resource_manager.py tests/test_runtime_multi_process.py tests/test_app_command_bridge.py tests/test_app_command_server.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_subtitle_resource_manager.py tests/test_runtime_multi_process.py tests/test_app_command_bridge.py tests/test_app_command_server.py` -> `135 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_subtitle_live_editor_feed_facade.py tests/test_app_command_bridge.py tests/test_app_command_server.py tests/test_project_nle_runtime_cutover.py tests/test_runtime_multi_process.py tests/test_subtitle_resource_manager.py tests/test_action_item_runtime_services.py tests/test_runtime_stage_metrics.py tests/test_project_nle_render_export_parity.py tests/test_subtitle_global_canvas_facade.py` -> `171 passed`.
  - Direct version assertion -> `APP_VERSION=04.01.05`, `PROJECT_SCHEMA_VERSION=04.01.05`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_app_store_readiness_audit.py tests/test_macos_bundle_runtime_paths.py` -> `9 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_context.py tests/test_cp03_cp04_status_ui.py -k "schema or version or project_file_roundtrip or status"` -> `66 passed, 79 deselected`.

## v04.01.04 G3 Compact Live Status Feed - 2026-06-29 KST

- 실행 모드: source-app G3 compact live status/feed wiring, UDP compact count preservation, and version/schema bump.
- 결과: pass for compact runtime lane status, status/ping/guided-subtitle-status count exposure, UDP compact preservation, and final-authority guard coverage.
- 저장 위치:
  - Release note: `docs/release_notes/RELEASE_v04.01.04.md`
  - Jammini probe: `.agents/sentinel/handoffs/20260629-012024-watchdog-handoff-probe.md`
  - Jammini review: `.agents/sentinel/handoffs/20260628-232716-g3-compact-status-feed-review-jammini.md`
- 실제 결과:
  - App version updated to `04.01.04`.
  - Project schema version updated to `04.01.04`.
  - `status`, `ping`, and `guided-subtitle-status` now expose compact `nle_runtime_track_counts`.
  - Raw STT/VAD/subtitle-preview segment text is not included in the compact runtime status payload.
  - UDP status compaction preserves `nle_runtime_track_counts`.
- 검증:
  - `./venv/bin/python -m py_compile core/engine/subtitle_live_editor_feed.py ui/editor/editor_automation.py ui/main/app_command_bridge.py core/automation/app_command_server.py tests/test_subtitle_live_editor_feed_facade.py tests/test_app_command_bridge.py tests/test_app_command_server.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_subtitle_live_editor_feed_facade.py tests/test_app_command_bridge.py tests/test_app_command_server.py tests/test_project_nle_runtime_cutover.py` -> `106 passed`.
  - Direct version assertion -> `APP_VERSION=04.01.04`, `PROJECT_SCHEMA_VERSION=04.01.04`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_app_store_readiness_audit.py tests/test_macos_bundle_runtime_paths.py` -> `9 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_context.py tests/test_cp03_cp04_status_ui.py -k "schema or version or project_file_roundtrip or status"` -> `66 passed, 79 deselected`.
  - `git diff --check -- .` -> pass.

## v04.01.03 G3 Runtime NLE Lane Owner Map / Final Authority Guard - 2026-06-29 KST

- 실행 모드: source-app G3 runtime NLE lane owner-map, final authority guard, and version/schema bump.
- 결과: pass for runtime feed contract, final/save-export authority isolation, surrounding STT/global-canvas façade guards, and final-only timeline smoke.
- 저장 위치:
  - Release note: `docs/release_notes/RELEASE_v04.01.03.md`
  - Jammini probe: `.agents/sentinel/handoffs/20260629-010211-watchdog-handoff-probe.md`
  - Jammini scout: `.agents/sentinel/handoffs/20260628-230544-nle-g3-runtime-lane-owner-map-scout-jammini.md`
- 실제 결과:
  - App version updated to `04.01.03`.
  - Project schema version updated to `04.01.03`.
  - Runtime live-editor feed now has `VAD`, `STT1`, `STT2`, `subtitle_preview`, and `final` track metadata.
  - Only the `final` runtime track carries save/export authority.
  - Runtime reference rows with text no longer promote into final overlay, global canvas, or save/export projection.
- 검증:
  - `./venv/bin/python -m py_compile core/engine/subtitle_live_editor_feed.py core/project/nle_runtime_cutover.py tests/test_subtitle_live_editor_feed_facade.py tests/test_project_nle_runtime_cutover.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_subtitle_live_editor_feed_facade.py tests/test_project_nle_runtime_cutover.py` -> `17 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_subtitle_live_editor_feed_facade.py tests/test_subtitle_stt_segments_facade.py tests/test_subtitle_global_canvas_facade.py tests/test_project_nle_runtime_cutover.py` -> `25 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py -k "global_canvas_silence_and_subtitle_lanes_share_expanded_height_evenly or timeline_update_segments_can_project_final_only_rows_to_global_canvas"` -> `2 passed, 191 deselected`.
  - Direct version assertion -> `APP_VERSION=04.01.03`, `PROJECT_SCHEMA_VERSION=04.01.03`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_app_store_readiness_audit.py tests/test_macos_bundle_runtime_paths.py` -> `9 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_context.py tests/test_cp03_cp04_status_ui.py -k "schema or version or project_file_roundtrip or status"` -> `66 passed, 79 deselected`.
  - `git diff --check -- .` -> pass.

## v04.01.02 NLE Close / Deferred-Save Boundary Fix - 2026-06-29 KST

- 실행 모드: source-app NLE close/deferred-save boundary fix, vector-canvas time normalization, close retry-loop guard, and version/schema bump.
- 결과: pass for focused NLE save/export projection, project text asset externalization, and editor deferred-save close regression coverage.
- 저장 위치:
  - Release note: `docs/release_notes/RELEASE_v04.01.02.md`
  - Close/deferred-save report: `output/manual_verification/latest/nle_close_deferred_save_v040102_20260629/close_deferred_save_report.md`
  - Jammini probe: `.agents/sentinel/handoffs/20260629-004654-watchdog-handoff-probe.md`
  - Jammini scout: `.agents/sentinel/handoffs/20260628-234233-nle-close-deferred-save-blocker-scout-jammini.md`
- 실제 결과:
  - App version updated to `04.01.02`.
  - Project schema version updated to `04.01.02`.
  - Raw vector-canvas `time.start_frame/end_frame` rows no longer collapse to `nle_save_export_invalid_duration`.
  - Close/exit forced deferred-save failures no longer reschedule stale deferred-save retries.
  - True final subtitle overlaps remain blocked by `nle_save_export_final_overlap`.
- 검증:
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_runtime_cutover.py tests/test_project_assets.py tests/test_editor_autosave_cleanup.py -q` -> `68 passed`.
  - Read-only project-5 raw vector projection probe -> `ValueError nle_save_export_final_overlap`, confirming vector-time normalization works and strict final-overlap protection remains active.

## v04.01.01 Source-App Checkpoint / App Store Identity Blocker - 2026-06-29 KST

- 실행 모드: source-app version/schema bump, owner-approved App Store packaging lane blocker refresh, NLE top-level shadow metadata closeout, and active G3 planning preservation.
- 결과: pass for focused NLE persistence guards, render/export parity, snapshot subset, local Apple Development bundle validation, and App Store readiness blocked-state audit.
- 저장 위치:
  - Release note: `docs/release_notes/RELEASE_v04.01.01.md`
  - App Store identity audit: `output/manual_verification/latest/app_store_v040101_identity_check_20260629_0036/app_store_readiness_audit.md`
  - Current local signing evidence: `output/manual_verification/latest/app_store_owner_approval_identity_check_20260629_0026/current_app_codesign_identity.txt`
  - Jammini probe: `.agents/sentinel/handoffs/20260629-002637-watchdog-handoff-probe.md`
- 실제 결과:
  - App version updated to `04.01.01`.
  - Project schema version updated to `04.01.01`.
  - App Store submission remains blocked: local keychain has Apple Development signing only; Apple Distribution and 3rd Party Mac Developer Installer identities are missing.
  - Signed Mac App Store `.pkg`, sandbox smoke, App Store Connect validation, upload, and owner metadata are still missing.
- 검증:
  - `./venv/bin/python -m py_compile core/runtime/config.py core/project/project_format.py tools/audit_app_store_readiness.py tests/test_macos_bundle_runtime_paths.py` -> pass.
  - Direct version assertion for `APP_VERSION` and `PROJECT_SCHEMA_VERSION` -> `04.01.01` / `04.01.01`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_app_store_readiness_audit.py tests/test_macos_bundle_runtime_paths.py` -> `9 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_context.py tests/test_cp03_cp04_status_ui.py -k "schema or version or project_file_roundtrip or status"` -> `66 passed, 79 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_persistence_guard.py` -> `8 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_nle_persistence_cutover_audit.py` -> `6 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_render_export_parity.py` -> `2 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_snapshot.py -k "snapshot or editor_row_readback_parity"` -> `16 passed, 4 subtests passed`.
  - `packaging/macos/validate_app_bundle.sh` -> pass for the existing Apple Development signed local bundle.
  - `./venv/bin/python tools/audit_app_store_readiness.py --output-dir output/manual_verification/latest/app_store_v040101_identity_check_20260629_0036` -> `status=blocked`, `local_packaging_ready=true`, `app_store_submission_ready=false`, blocker count `13`.
  - `pkgutil --check-signature "dist/macos/AI Subtitle Studio.pkg"` -> blocked because the package does not exist.

## Documentation Relocation / App Store Launch Planning - 2026-06-28 KST

- 실행 모드: root development-doc relocation, grouped action plan, Mac App Store launch plan, docs consolidation, and path-compatibility fix.
- 결과: pass for docs relocation presence, script syntax, Python compile, focused pytest, Jammini route/bootstrap, old NAS doc path cleanup, and whitespace check.
- 저장 위치:
  - Active queue: `docs/planning_queue/ACTION_ITEMS.md`
  - App Store launch plan: `docs/APP_STORE_SUBMISSION_READINESS.md`
  - Docs hub: `docs/README.md`
  - Project state: `docs/PROJECT_STATE.md`
  - Handoff: `docs/HANDOFF.md`
  - Product README: `docs/project_reference/PRODUCT_README.md`
  - NAS benchmark plan: `docs/quality_validation/NAS_SUBTITLE_BENCHMARK_50_PLAN.md`
  - Jammini route probe: `.agents/sentinel/handoffs/20260628-211017-watchdog-handoff-probe.md`
  - Jammini docs risk scout: `.agents/sentinel/handoffs/20260628-211046-docs-relocation-risk-scout.md`
- 실제 결과:
  - Repository root now keeps `AGENTS.md` as the only root development-documentation file; non-doc runtime/config files remain at root.
  - Active queue is grouped into `G0. Mac App Store Launch Program`, `G1. STT2 / Word Precision...`, and `G2. Source-App NLE / Taption Editing Continuity`.
  - App Store launch plan now has Phase 0-6 gates covering owner inputs, source baseline, sandboxed app bundle, signed package, App Store Connect validation, submission assembly, and review/release.
  - Moved root docs into `docs/planning_queue/`, `docs/project_reference/`, `docs/quality_validation/`, `docs/release_notes/`, `docs/nle_engine/`, and `docs/workflow_operations/`.
  - Updated `tools/jammini_watchdog.sh`, `tools/jammini_delegate.sh`, `tools/cooperation_bootstrap.sh`, `tests/test_subtitle_generation_domain_map.py`, `ui/help/help_content.py`, `tools/nas_truth_learning.py`, and `core/personalization/nas_truth_learning.py` for new paths.
  - No subtitle-generation policy, UI/UX, package build, signing, upload, notarization, DMG, App Store submission, STT/default-cache promotion, or persisted NLE disk-format change was performed.
- 검증:
  - `bash -n tools/jammini_watchdog.sh tools/jammini_delegate.sh tools/cooperation_bootstrap.sh` -> pass.
  - `./venv/bin/python -m py_compile core/personalization/nas_truth_learning.py tools/nas_truth_learning.py tests/test_subtitle_generation_domain_map.py ui/help/help_content.py` -> pass.
  - `test -f docs/planning_queue/ACTION_ITEMS.md && test -f docs/project_reference/PRODUCT_README.md && test -f docs/release_notes/RELEASE_v04.01.00.md && test ! -f ACTION_ITEMS.md && test ! -f README.md && test ! -f RELEASE_v04.01.00.md` -> `docs_presence_and_root_doc_move=pass`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_subtitle_generation_domain_map.py tests/test_help_dialog.py -k "subtitle_generation_domain_map or help"` -> `7 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_subtitle_generation_domain_map.py tests/test_help_dialog.py tests/test_nas_truth_learning.py -k "subtitle_generation_domain_map or help or nas_truth"` -> `12 passed`.
  - `tools/jammini_watchdog.sh --status` -> active/canonical conversation `d2075935-3595-4188-baed-4ee0b45cb7a8`.
  - `tools/jammini_watchdog.sh --once --dry-run` -> rendered a DEX task packet without dispatching work.
  - `tools/jammini_delegate.sh --bootstrap --dry-run` -> read order uses `docs/planning_queue/ACTION_ITEMS.md`, `docs/project_reference/File_structure.txt`, and `docs/workflow_operations/cooperation.md`.
  - `rg -n "docs/NAS_SUBTITLE_BENCHMARK" docs core tools tests --glob '!docs/quality_validation/test_result.md'` -> no old-path matches.
  - `git diff --check -- .` -> pass.

## v04.01.00 Source-App Release - 2026-06-28 KST

- 실행 모드: source-app release checkpoint, version/schema bump, code-review fix, docs update, and release validation.
- 결과: pass for version/schema assert, trace/App Store readiness tests, project/status UI subset, NLE parity subset, timeline/playhead suite, source-app quick QA, and App Store readiness blocked-state audit.
- 저장 위치:
  - Release note: `RELEASE_v04.01.00.md`
  - Quick QA: `output/manual_verification/latest/qa_suite_quick_v040100_20260628/suite_result.md`
  - App Store readiness audit: `output/manual_verification/latest/app_store_readiness_v040100_20260628/app_store_readiness_audit.md`
  - Jammini release scout: `.agents/sentinel/handoffs/20260628-115644-release-readiness-scout.md`
  - 한결 review: `.agents/sentinel/handoffs/20260628-120244-release-architecture-review-hangyeol.md`
  - 서린 review: `.agents/sentinel/handoffs/20260628-120230-release-qa-review-seorin.md`
  - 유진 review: `.agents/sentinel/handoffs/20260628-120241-release-workflow-review-yujin.md`
- 실제 결과:
  - App version updated to `04.01.00`.
  - Project schema version updated to `04.01.00`.
  - Trace manifest version test now follows `config.APP_VERSION` instead of a hard-coded release literal.
  - Quick QA profile `quick` passed with `failed_count=0`; passed scenario `editor_compact_macau`.
  - App Store readiness audit reads config app version `04.01.00` but remains `status=blocked`, `app_store_submission_ready=false`, blocker count `14`.
  - No DMG build, App Store package build, upload, notarization, persisted NLE disk-format cutover, per-pixel NLE write path, UI/QML default change, or STT/default-cache promotion was performed.
- 검증:
  - `./venv/bin/python -m py_compile core/runtime/config.py core/project/project_format.py tests/test_trace_logger.py tools/audit_app_store_readiness.py` -> pass.
  - Direct version assertion for `APP_VERSION` and `PROJECT_SCHEMA_VERSION` -> `04.01.00` / `04.01.00`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_trace_logger.py tests/test_app_store_readiness_audit.py` -> `23 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_context.py tests/test_cp03_cp04_status_ui.py -k "schema or version or project_file_roundtrip or status"` -> `66 passed, 79 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_snapshot.py tests/test_project_nle_dual_write.py tests/test_project_nle_operations.py tests/test_project_nle_persistence_guard.py tests/test_project_nle_render_export_parity.py` -> `67 passed, 4 subtests passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py` -> `193 passed`.
  - `./venv/bin/python tools/audit_app_store_readiness.py --output-dir output/manual_verification/latest/app_store_readiness_v040100_20260628` -> `status=blocked`, `local_packaging_ready=true`, `app_store_submission_ready=false`.
  - `AI_SUBTITLE_STUDIO_QA_USE_SOURCE=1 ./venv/bin/python tools/qa_suite_runner.py quick --output-dir output/manual_verification/latest/qa_suite_quick_v040100_20260628` -> `failed_count=0`.

## Development Documentation Organization And Active Queue Hygiene - 2026-06-28 KST

- 실행 모드: Taption-style docs organization adapted to AI Subtitle Studio, plus active queue cleanup.
- 결과: pass for docs role-bucket presence, active queue cleanup grep, Jammini route status, existing 3-agent role-card confirmation, and whitespace diff validation.
- 저장 위치:
  - Docs hub: `docs/README.md`
  - Planning bucket: `docs/planning_queue/README.md`
  - Workflow bucket: `docs/workflow_operations/README.md`
  - Project reference bucket: `docs/project_reference/README.md`
  - Validation bucket: `docs/quality_validation/README.md`
  - Product behavior bucket: `docs/product_behavior/README.md`
  - NLE bucket: `docs/nle_engine/README.md`
  - STT bucket: `docs/speech_stt/README.md`
  - Evidence bucket: `docs/validation_evidence/README.md`
  - Release bucket: `docs/release_notes/README.md`
  - Legacy bucket: `docs/archive_legacy/README.md`
  - Jammini scout: `.agents/sentinel/handoffs/20260628-113530-taption-docs-parity-scout.md`
- 실제 결과:
  - `ACTION_ITEMS.md` now keeps completed NLE regression proof as archive pointers instead of duplicating completed histories in the active STT2 item.
  - `docs/README.md` is now the development-documentation hub and preserves root canonical document locations.
  - `AGENTS.md` now records development-documentation organization rules, active-only queue policy, physical Jammini handoff priority, and clean-room Taption reference handling.
  - Existing role cards confirmed: `.agents/sentinel/agents/hangyeol.md`, `.agents/sentinel/agents/seorin.md`, and `.agents/sentinel/agents/yujin.md`.
  - Jammini route status confirmed active/canonical conversation `d2075935-3595-4188-baed-4ee0b45cb7a8`; route probe and scout were delivered as physical handoff files.
  - Runtime code, UI/UX, STT/default-cache policy, App Store packaging/signing/upload, and persisted NLE disk format did not change.
- 검증:
  - `for f in docs/README.md docs/planning_queue/README.md docs/workflow_operations/README.md docs/project_reference/README.md docs/quality_validation/README.md docs/product_behavior/README.md docs/nle_engine/README.md docs/speech_stt/README.md docs/validation_evidence/README.md docs/release_notes/README.md docs/archive_legacy/README.md; do test -f "$f" || exit 1; done` -> `docs_readme_presence=pass`.
  - `rg -n "Latest NAS HeyDealer first-180s regression after the NLE|NLE operation-journal slice|nle_neighbor_collision|nle_voice_silence|nle_final_preview_isolation" ACTION_ITEMS.md || true` -> no matches.
  - `tools/jammini_watchdog.sh --status` -> active/canonical conversation matched.
  - `git diff --check -- .` -> pass.

## NLE Neighbor Collision Guard - 2026-06-28 KST

- 실행 모드: Taption-style subtitle neighbor-collision guard for NLE release/commit paths.
- 결과: pass for caption move overlap rejection, center commit-row overlap rejection, split-required resize collision rejection, partial resize trim-to-shared-boundary, strict NAS HeyDealer first-180s final stability, and no STT worker timeout.
- 저장 위치:
  - Audit: `output/manual_verification/latest/nle_neighbor_collision_guard_20260628/nle_neighbor_collision_guard.md`
  - NAS preflight: `output/manual_verification/latest/nle_neighbor_collision_nas_preflight_20260628/reference_fixture_availability.md`
  - NAS benchmark: `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_202739/benchmark_results.json`
  - NAS acceptance: `output/manual_verification/latest/nle_neighbor_collision_nas_heydealer_20260628/acceptance/reference_benchmark_acceptance.md`
  - NAS timeout audit: `output/manual_verification/latest/stt_worker_timeout_compare_nle_neighbor_collision_nas_20260628/stt_worker_timeout_audit.md`
  - Jammini scout: `.agents/sentinel/handoffs/20260628-112236-neighbor-collision-validation-scout.md`
- 실제 결과:
  - Audit `ready=true`; checks `6/6`.
  - Rejected collision paths do not mutate project rows and do not create runtime `NLEProjectState`.
  - Partial resize neighbor collision trims to a shared boundary with final overlap `0`.
  - NAS acceptance `accepted=true`, elapsed `94.953s`, raw/final/reference `58/56/89`, quality/text/timing `93.766/94.267/0.5808s`.
  - Final invalid/non-monotonic/overlap `0/0/0`; final last end/duration bound `180.0/180.0`; short/long `0/0`; global max active `1`.
  - STT1/STT2/word selected `21/37/7`; stage spans STT1 `47.229656s`, STT2 `20.522164s`, word precision `25.214521s`, subtitle postprocess `1.616752s`; timeout audit `timeout_detected=false`.
- 검증:
  - `./venv/bin/python -m py_compile tools/audit_nle_neighbor_collision.py tests/test_nle_neighbor_collision_audit.py tests/test_project_nle_dual_write.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_nle_neighbor_collision_audit.py tests/test_project_nle_dual_write.py -k "neighbor_collision or overlap or center_overwrite_trim or split_required"` -> `9 passed, 33 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_nle_neighbor_collision.py --output-dir output/manual_verification/latest/nle_neighbor_collision_guard_20260628` -> ready `true`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_dual_write.py tests/test_nle_neighbor_collision_audit.py` -> `42 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_operations.py tests/test_project_nle_runtime_cutover.py -k "overlap or operation_journal or final_overlay or global_canvas or save_export"` -> `11 passed, 5 deselected`.

## NLE Voice-Silence Magnet Parity - 2026-06-28 KST

- 실행 모드: Taption-style subtitle center-drag magnet parity for silence-like `voice_activity`/`vad` rows returned through native snap candidates.
- 결과: pass for subtitle-boundary snap beyond a voice-silence row, no automatic voice-silence attachment when no subtitle target exists, existing explicit gap suppression, and strict NAS HeyDealer first-180s final stability. The NAS run was accepted, but STT worker timeout/fallback occurred and is recorded as diagnostic evidence only.
- 저장 위치:
  - NAS preflight: `output/manual_verification/latest/nle_voice_silence_magnet_nas_preflight_20260628/reference_fixture_availability.md`
  - NAS benchmark: `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_201007/benchmark_results.json`
  - NAS acceptance: `output/manual_verification/latest/nle_voice_silence_magnet_nas_heydealer_20260628/acceptance/reference_benchmark_acceptance.md`
  - NAS timeout audit: `output/manual_verification/latest/stt_worker_timeout_compare_nle_voice_silence_magnet_nas_20260628/stt_worker_timeout_audit.md`
  - Jammini scout: `.agents/sentinel/handoffs/20260628-110359-next-nle-taption-runtime-contract-scout.md` (deferred adjacent neighbor-collision recommendation)
- 실제 결과:
  - Native snap candidates now regain local `gap`/`vad`/`voice_activity` source metadata before Python filtering.
  - Silence-like `voice_activity`/`vad` rows join the Taption gap-attachment suppression check for center body moves.
  - Suppression removes only gap-like snap candidates and keeps real subtitle boundary candidates available beyond the silence row.
  - NAS acceptance `accepted=true`, elapsed `348.171s`, raw/final/reference `55/57/89`, quality/text/timing `93.955/94.867/0.5536s`.
  - Final invalid/non-monotonic/overlap `0/0/0`; final last end/duration bound `180.0/180.0`; short/long `0/0`; global max active `1`.
  - Timeout audit `timeout_detected=true`; compared non-timeout run `20260628_195502` with timeout run `20260628_201007`, timeout elapsed `330.059168s`, and production change/default-cache promotion allowed `false`.
- 검증:
  - `./venv/bin/python -m py_compile ui/editor/ux/timeline_subtitle_segment_editing.py tests/test_timeline_hit_targets.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_hit_targets.py -k "voice_silence or center_segment_move_prefers_subtitle_boundary_snap_beyond_gap or center_segment_move_suppresses_single_gap_snap_without_subtitle_target"` -> `4 passed, 152 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_hit_targets.py -k "gap or magnet or drag or boundary_release"` -> `58 passed, 98 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py -k "center_drag_over_single_gap_absorbs_gap_without_final_overlap or gap_generate or overwrite_trim"` -> `4 passed, 189 deselected`.

## NLE Final/Preview Isolation - 2026-06-28 KST

- 실행 모드: Taption-style final subtitle surface isolation for video overlay/global canvas/save-style feeds while keeping STT/subtitle drafts in timeline/editor candidate lanes.
- 결과: pass for final-only video subtitle overlay, final-only NLE/global surfaces, diagnostic-only combined live feed, strict NAS HeyDealer first-180s acceptance, and no STT worker timeout. UI layout/labels/colors/menus/popups, subtitle quality policy, STT/STT2/default-cache policy, persisted NLE disk-format, App Store packaging/signing/upload, DMG behavior, and per-pixel NLE writes did not change.
- 저장 위치:
  - Audit: `output/manual_verification/latest/nle_final_preview_isolation_20260628/nle_final_preview_isolation.md`
  - NAS preflight: `output/manual_verification/latest/nle_final_preview_isolation_nas_preflight_20260628/reference_fixture_availability.md`
  - NAS benchmark: `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_195502/benchmark_results.json`
  - NAS acceptance: `output/manual_verification/latest/nle_final_preview_isolation_nas_heydealer_20260628/acceptance/reference_benchmark_acceptance.md`
  - NAS timeout audit: `output/manual_verification/latest/stt_worker_timeout_compare_nle_final_preview_isolation_nas_20260628/stt_worker_timeout_audit.md`
  - Jammini scout: `.agents/sentinel/handoffs/20260628-104950-next-nle-taption-runtime-contract-scout.md` (rejected as duplicate playhead-jump scope)
- 실제 결과:
  - Audit `ready=true`; final overlay/global canvas/save-style surfaces are `confirmed_final_rows_only`; combined live feed is `diagnostic_candidate_lane_only`.
  - Checks passed: feed final surface confirmed-only, preview lane keeps candidates, combined feed diagnostic-only, final overlay filters preview rows, global canvas filters preview rows, video overlay ignores live preview context.
  - NAS acceptance `accepted=true`, elapsed `46.228s`, raw/final/reference `58/56/89`, quality/text/timing `93.766/94.267/0.5808s`.
  - Final invalid/non-monotonic/overlap `0/0/0`; final last end/duration bound `180.0/180.0`; short/long `0/0`; global max active `1`.
  - STT1/STT2/word selected `21/37/7`; timeout audit `timeout_detected=false`.
- 검증:
  - `./venv/bin/python -m py_compile core/engine/subtitle_live_editor_feed.py ui/editor/editor_segments_timeline_context.py tools/audit_nle_final_preview_isolation.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_subtitle_live_editor_feed_facade.py tests/test_project_segment_reload.py` -> `92 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_runtime_cutover.py tests/test_timeline_playhead_fit.py -k "stt_preview or final_overlay or global_canvas or video_subtitle_context"` -> `18 passed, 185 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_nle_final_preview_isolation.py --output-dir output/manual_verification/latest/nle_final_preview_isolation_20260628` -> ready `true`.

## NLE Relink Parity Verification - 2026-06-28 KST

- 실행 모드: source-app project-load/media relink parity validation between editor media files and runtime `NLEProjectState` snapshot assets/clips.
- 결과: pass for updated relink media path parity, editor/timeline path drift rejection, runtime fps drift rejection, clean persisted storage, strict NAS HeyDealer first-180s acceptance, and no STT worker timeout. UI layout/labels/colors/menus/popups, subtitle quality policy, STT/STT2/default-cache policy, persisted NLE disk-format, project-storage relink schema, App Store packaging/signing/upload, DMG behavior, and per-pixel NLE writes did not change.
- 저장 위치:
  - Audit: `output/manual_verification/latest/nle_relink_parity_20260628/nle_relink_parity.md`
  - NAS preflight: `output/manual_verification/latest/nle_relink_parity_nas_preflight_20260628/reference_fixture_availability.md`
  - NAS benchmark: `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_194124/benchmark_results.json`
  - NAS acceptance: `output/manual_verification/latest/nle_relink_parity_nas_heydealer_20260628/acceptance/reference_benchmark_acceptance.md`
  - NAS timeout audit: `output/manual_verification/latest/stt_worker_timeout_compare_nle_relink_parity_nas_20260628/stt_worker_timeout_audit.md`
  - Jammini scout: `.agents/sentinel/handoffs/20260628-103348-next-nle-taption-runtime-contract-scout.md`
- 실제 결과:
  - Audit `ready=true`; project/NLE media counts `1/1/1`; project/runtime/sequence fps `30.0/30.0/30.0`; project/sequence duration `6.0/6.0`.
  - Relink parity consistent `true`; path drift rejected `true` with `nle_media_path_order_drift:0`; operation journal count `0`; storage forbidden key count `0`.
  - NAS acceptance `accepted=true`, elapsed `48.693s`, raw/final/reference `58/56/89`, quality/text/timing `93.766/94.267/0.5808s`.
  - Final invalid/non-monotonic/overlap `0/0/0`; final last end/duration bound `180.0/180.0`; short/long `0/0`; global max active `1`.
  - STT1/STT2/word selected `21/37/7`; stage spans STT1 `18.621955s`, STT2 `16.476798s`, word precision `13.022902s`, subtitle postprocess `0.491175s`.
  - Timeout audit `timeout_detected=false`.
- 검증:
  - `./venv/bin/python -m py_compile core/project/nle_project_state.py tools/audit_nle_relink_parity.py tests/test_nle_relink_verification.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_nle_relink_verification.py` -> `5 passed`.
  - `./venv/bin/python tools/audit_nle_relink_parity.py --output-dir output/manual_verification/latest/nle_relink_parity_20260628` -> ready `true`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_snapshot.py -k "runtime_nle_project_state or direct_srt_rows or compatibility_characterization or read_only_projection_parity or relink"` -> `4 passed, 11 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_nle_selection_sync_validation.py tests/test_project_nle_persistence_guard.py` -> `7 passed`.

## NLE Selection Sync Validation - 2026-06-28 KST

- 실행 모드: source-app reload/restore active selection parity validation between visible editor rows and runtime `NLEProjectState`.
- 결과: pass for exact-start shared-boundary active selection, matching editor/NLE active signatures, clean persisted storage, zero operation-journal writes, strict NAS HeyDealer first-180s acceptance, and no STT worker timeout. UI layout/labels/colors/menus/popups, subtitle quality policy, STT/STT2/default-cache policy, persisted NLE disk-format, App Store packaging/signing/upload, DMG behavior, and per-pixel NLE writes did not change.
- 저장 위치:
  - Audit: `output/manual_verification/latest/nle_selection_sync_validation_20260628/nle_selection_sync_validation.md`
  - NAS preflight: `output/manual_verification/latest/nle_selection_sync_validation_nas_preflight_20260628/reference_fixture_availability.md`
  - NAS benchmark: `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_192507/benchmark_results.json`
  - NAS acceptance: `output/manual_verification/latest/nle_selection_sync_validation_nas_heydealer_20260628/acceptance/reference_benchmark_acceptance.md`
  - NAS timeout audit: `output/manual_verification/latest/stt_worker_timeout_compare_nle_selection_sync_validation_nas_20260628/stt_worker_timeout_audit.md`
  - Jammini scout: `.agents/sentinel/handoffs/20260628-101805-next-nle-taption-runtime-contract-scout.md`
- 실제 결과:
  - Audit `ready=true`; active boundary policy `exact_start_frame_wins_at_shared_boundary`.
  - Editor active signature id `caption_0002`; NLE active signature id `caption_0002`.
  - Operation journal count `0`; storage forbidden key count `0`; persisted NLE fields changed `false`.
  - NAS acceptance `accepted=true`, elapsed `46.06s`, raw/final/reference `58/56/89`, quality/text/timing `93.766/94.267/0.5808s`.
  - Final invalid/non-monotonic/overlap `0/0/0`; final last end/duration bound `180.0/180.0`; short/long `0/0`; global max active `1`.
  - Timeout audit `timeout_detected=false`.
- 검증:
  - `./venv/bin/python -m py_compile core/project/nle_project_state.py tools/audit_nle_selection_sync_validation.py tests/test_nle_selection_sync_validation.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_nle_selection_sync_validation.py` -> `3 passed`.
  - `./venv/bin/python tools/audit_nle_selection_sync_validation.py --output-dir output/manual_verification/latest/nle_selection_sync_validation_20260628` -> ready `true`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_segment_reload.py -k "reload_replaces_pending_segments_before_project_restore or live_stt_preview_updates_timeline_without_editor_commit"` -> `2 passed, 87 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_snapshot.py -k "runtime_nle_project_state or direct_srt_rows"` -> `2 passed, 13 deselected`.

## NLE Roughcut Sidecar Compatibility - 2026-06-28 KST

- 실행 모드: source-app roughcut `_render_plan.json` / `_edl.json` sidecar restore plus NLE render/export parity compatibility audit.
- 결과: pass for stitched cut-boundary sidecar restore, roughcut sidecar/exported-assets parity, clean sidecar/storage payloads, strict NAS HeyDealer first-180s acceptance, and no STT worker timeout. UI layout/labels/colors/menus/popups, subtitle quality policy, STT/STT2/default-cache policy, persisted NLE disk-format, App Store packaging/signing/upload, DMG behavior, and per-pixel NLE writes did not change.
- 저장 위치:
  - Audit: `output/manual_verification/latest/nle_roughcut_sidecar_compat_20260628/nle_roughcut_sidecar_compat.md`
  - NAS preflight: `output/manual_verification/latest/nle_roughcut_sidecar_compat_nas_preflight_20260628/reference_fixture_availability.md`
  - NAS benchmark: `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_191031/benchmark_results.json`
  - NAS acceptance: `output/manual_verification/latest/nle_roughcut_sidecar_compat_nas_heydealer_20260628/acceptance/reference_benchmark_acceptance.md`
  - NAS timeout audit: `output/manual_verification/latest/stt_worker_timeout_compare_nle_roughcut_sidecar_compat_nas_20260628/stt_worker_timeout_audit.md`
  - Jammini scout: `.agents/sentinel/handoffs/20260628-100359-roughcut-sidecar-nle-compatibility-scout.md`
- 실제 결과:
  - Audit `ready=true`; sidecar restore matches `true`; parity diff summary `ok`.
  - Roughcut sidecar stable `true`; exported assets stable `true`; render/manifest/stitched counts `2/2/1`.
  - Sidecar forbidden key count `0`; storage forbidden key count `0`.
  - NAS acceptance `accepted=true`, elapsed `45.103s`, raw/final/reference `58/56/89`, quality/text/timing `93.766/94.267/0.5808s`.
  - Final invalid/non-monotonic/overlap `0/0/0`; final last end/duration bound `180.0/180.0`; short/long `0/0`; global max active `1`.
  - Timeout audit `timeout_detected=false`.
- 검증:
  - `./venv/bin/python -m py_compile tools/audit_nle_roughcut_sidecar_compat.py tests/test_nle_roughcut_sidecar_compat_audit.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_nle_roughcut_sidecar_compat_audit.py` -> `2 passed`.
  - `./venv/bin/python tools/audit_nle_roughcut_sidecar_compat.py --output-dir output/manual_verification/latest/nle_roughcut_sidecar_compat_20260628` -> ready `true`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_roughcut_v2_output_compat.py tests/test_project_nle_render_export_parity.py tests/test_project_nle_snapshot.py -k "roughcut or render_export_parity or sidecar"` -> `12 passed, 9 deselected, 4 subtests passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_roughcut_ui_v2.py -k "sidecar or render_plan_builders_route_through_nle_snapshot_adapter_with_legacy_parity"` -> `3 passed, 35 deselected`.

## NLE Smart Split Undo Route - 2026-06-28 KST

- 실행 모드: source-app Taption-style smart split snapshot undo routing under text-editor focus.
- 결과: pass for structural smart split undo/redo using the app snapshot route instead of the focused `QTextEdit` local undo stack, plus strict NAS HeyDealer first-180s acceptance and no STT worker timeout. UI layout/labels/colors/menus/popups, subtitle quality policy, STT/STT2/default-cache policy, persisted NLE disk-format, App Store packaging/signing/upload, DMG behavior, and per-pixel NLE writes did not change.
- 저장 위치:
  - Audit: `output/manual_verification/latest/nle_smart_split_undo_route_20260628/smart_split_undo_route.md`
  - NAS preflight: `output/manual_verification/latest/nle_smart_split_undo_route_nas_preflight_20260628/reference_fixture_availability.md`
  - NAS benchmark: `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_185643/benchmark_results.json`
  - NAS acceptance: `output/manual_verification/latest/nle_smart_split_undo_route_nas_heydealer_20260628/acceptance/reference_benchmark_acceptance.md`
  - NAS timeout audit: `output/manual_verification/latest/stt_worker_timeout_compare_nle_smart_split_undo_route_nas_20260628/stt_worker_timeout_audit.md`
  - Jammini scout: `.agents/sentinel/handoffs/20260628-095359-smart-split-undo-route-scout.md`
- 실제 결과:
  - Smart split repro `1 passed`; full split undo file `3 passed`; smart/gap timeline subset `4 passed, 189 deselected`.
  - NAS acceptance `accepted=true`, elapsed `45.752s`, raw/final/reference `58/56/89`, quality/text/timing `93.766/94.267/0.5808s`.
  - Final invalid/non-monotonic/overlap `0/0/0`; final last end/duration bound `180.0/180.0`; short/long `0/0`; global max active `1`.
  - STT1/STT2/word selected `21/37/7`; timeout audit `timeout_detected=false`.
- 검증:
  - `./venv/bin/python -m py_compile ui/editor/ux/editor_timeline_gap_split.py tests/test_editor_split_undo.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_editor_split_undo.py::EditorSplitUndoTests::test_smart_split_undo_and_redo_follow_snapshot_history_with_text_focus -vv` -> `1 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_editor_split_undo.py` -> `3 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py -k "smart_split or gap_generate or seg_to_gap"` -> `4 passed, 189 deselected`.

## NLE Undo/Redo Runtime-State Restore - 2026-06-28 KST

- 실행 모드: source-app NLE undo/redo restored-row runtime-state sync contract.
- 결과: pass for session-only `NLEProjectState` sync after undo/redo restore, live STT preview isolation from restored runtime NLE state, clean persisted storage, strict NAS HeyDealer first-180s acceptance, and no STT worker timeout. No UI/UX layout/labels/colors/menus/popups, subtitle quality policy, STT/STT2/default-cache policy, persisted NLE disk-format, App Store packaging/signing/upload, DMG behavior, runtime undo/redo UI, or per-pixel NLE write changed.
- 저장 위치:
  - Audit: `output/manual_verification/latest/nle_undo_redo_runtime_state_20260628/nle_undo_redo_runtime_state.md`
  - NAS preflight: `output/manual_verification/latest/nle_undo_redo_runtime_state_nas_preflight_20260628/reference_fixture_availability.md`
  - NAS benchmark: `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_184504/benchmark_results.json`
  - NAS acceptance: `output/manual_verification/latest/nle_undo_redo_runtime_state_nas_heydealer_20260628/acceptance/reference_benchmark_acceptance.md`
  - NAS timeout audit: `output/manual_verification/latest/stt_worker_timeout_compare_nle_undo_redo_runtime_state_nas_20260628/stt_worker_timeout_audit.md`
  - Jammini scout: `.agents/sentinel/handoffs/20260628-093842-next-nle-taption-runtime-contract-scout.md` (deferred for roughcut sidecar compatibility)
- 실제 결과:
  - Audit `ready=true`; sync source `undo_redo_restore`; operation journal count `0`; storage runtime NLE key `false`.
  - Runtime before/after signatures: `[("before", 30, 90)]` -> `[("after left", 30, 60), ("after right", 60, 90)]`.
  - NAS acceptance `accepted=true`, elapsed `45.497s`, raw/final/reference `58/56/89`, quality/text/timing `93.766/94.267/0.5808s`.
  - Final invalid/non-monotonic/overlap `0/0/0`; final last end/duration bound `180.0/180.0`; short/long `0/0`; global max active `1`.
  - STT1/STT2/word selected `21/37/7`; timeout audit `timeout_detected=false`.
- 검증:
  - `./venv/bin/python -m py_compile ui/project/project_session_runtime.py ui/editor/undo_manager.py tools/audit_nle_undo_redo_runtime_state.py tests/test_nle_undo_redo_runtime_state_audit.py tests/test_editor_split_undo.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_nle_undo_redo_runtime_state_audit.py tests/test_editor_split_undo.py::EditorSplitUndoTests::test_text_split_undo_and_redo_follow_snapshot_history_with_text_focus tests/test_editor_split_undo.py::EditorSplitUndoTests::test_text_split_uses_legacy_fallback_when_live_preview_lane_exists` -> `4 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_snapshot.py tests/test_project_nle_persistence_guard.py tests/test_project_nle_runtime_cutover.py -k "runtime_nle or save_project or undo or storage or save_export or final_overlay"` -> `10 passed, 19 deselected`.

## NLE Relink Preview Cache Contract - 2026-06-28 KST

- 실행 모드: source-app NLE preview/skimming frame-cache relink/proxy non-destructive contract.
- 결과: pass for same-media relink preview-cache reuse, proxy/different-media reuse blocking, existing preview-cache worker behavior, strict NAS HeyDealer first-180s acceptance, and no STT worker timeout. No UI/UX layout/labels/colors/menus/popups, subtitle quality policy, STT/STT2/default-cache policy, detector threshold, project-storage relink schema, persisted NLE disk-format, App Store packaging/signing/upload, DMG behavior, runtime undo/redo UI, or per-pixel NLE write changed.
- 저장 위치:
  - Audit: `output/manual_verification/latest/nle_relink_preview_cache_contract_20260628/nle_relink_preview_cache_contract.md`
  - Audit JSON: `output/manual_verification/latest/nle_relink_preview_cache_contract_20260628/nle_relink_preview_cache_contract.json`
  - NAS preflight: `output/manual_verification/latest/nle_relink_preview_cache_nas_preflight_20260628/reference_fixture_availability.md`
  - NAS benchmark: `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_174547/benchmark_results.json`
  - NAS acceptance: `output/manual_verification/latest/nle_relink_preview_cache_nas_heydealer_20260628/acceptance/reference_benchmark_acceptance.md`
  - NAS timeout audit: `output/manual_verification/latest/stt_worker_timeout_compare_nle_relink_preview_cache_nas_20260628/stt_worker_timeout_audit.md`
  - Jammini scout: `.agents/sentinel/handoffs/20260628-083937-next-nle-taption-runtime-contract-scout.md`
- 실제 결과:
  - Audit `ready=true`, relink identity matches `true`, relink hit reuses original cache `true`.
  - Proxy identity blocked `true`, proxy hit blocked `true`, cached still exists `true`.
  - NAS acceptance `accepted=true`, elapsed `45.515s`, raw/final/reference `58/56/89`, quality/text/timing `93.766/94.267/0.5808s`.
  - Final invalid/non-monotonic/overlap `0/0/0`; final last end/duration bound `180.0/180.0`; short/long `0/0`; global max active `1`.
  - STT1/STT2/word selected `21/37/7`; timeout audit `timeout_detected=false`.
- 검증:
  - `./venv/bin/python -m py_compile core/runtime/preview_frame_cache.py tools/audit_nle_relink_preview_cache_contract.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_preview_frame_cache.py tests/test_nle_relink_preview_cache_contract_audit.py` -> `8 passed`.
  - `./venv/bin/python tools/audit_nle_relink_preview_cache_contract.py --output-dir output/manual_verification/latest/nle_relink_preview_cache_contract_20260628` -> ready `true`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_nle_preview_skimming_cache_audit.py tests/test_video_player_widget.py -k "preview_frame_cache"` -> `3 passed, 82 deselected`.
  - `git diff --check -- core/runtime/preview_frame_cache.py tests/test_preview_frame_cache.py tools/audit_nle_relink_preview_cache_contract.py tests/test_nle_relink_preview_cache_contract_audit.py` -> pass.

## NLE Cut Marker Point Projection - 2026-06-28 KST

- 실행 모드: source-app NLE marker-edit cut-boundary point-evidence projection guard.
- 결과: pass for confirmed/provisional cut markers staying point evidence, no clip-span mapping leakage, unchanged clip boundaries, strict NAS HeyDealer first-180s acceptance, and no STT worker timeout. No UI/UX layout/labels/colors/menus/popups, subtitle quality policy, STT/STT2/default-cache policy, detector threshold, persisted NLE disk-format, App Store packaging/signing/upload, DMG behavior, runtime undo/redo UI, or per-pixel NLE write changed.
- 저장 위치:
  - Audit: `output/manual_verification/latest/nle_cut_marker_point_projection_20260628/nle_cut_marker_point_projection.md`
  - Audit JSON: `output/manual_verification/latest/nle_cut_marker_point_projection_20260628/nle_cut_marker_point_projection.json`
  - NAS preflight: `output/manual_verification/latest/nle_cut_marker_point_projection_nas_preflight_20260628/reference_fixture_availability.md`
  - NAS benchmark: `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_173133/benchmark_results.json`
  - NAS acceptance: `output/manual_verification/latest/nle_cut_marker_point_projection_nas_heydealer_20260628/acceptance/reference_benchmark_acceptance.md`
  - NAS timeout audit: `output/manual_verification/latest/stt_worker_timeout_compare_nle_cut_marker_point_projection_nas_20260628/stt_worker_timeout_audit.md`
  - Jammini scout: `.agents/sentinel/handoffs/20260628-082222-next-nle-taption-runtime-contract-scout.md`
- 실제 결과:
  - Audit `passed=true`, observed frames `2766,2676`, marker policy `point_evidence_no_clip_span`.
  - Span leak count `0`; clip boundaries unchanged `true`.
  - Projection gate final invalid/non-monotonic/overlap `0/0/0`; global max active `1`.
  - NAS acceptance `accepted=true`, elapsed `45.036s`, raw/final/reference `58/56/89`, quality/text/timing `93.766/94.267/0.5808s`, final last end/duration bound `180.0/180.0`, short/long `0/0`.
  - Timeout audit `timeout_detected=false`.
- 검증:
  - `./venv/bin/python -m py_compile core/project/nle_dual_write.py tools/audit_nle_cut_marker_point_projection.py tests/test_project_nle_dual_write.py tests/test_nle_cut_marker_point_projection_audit.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_dual_write.py tests/test_nle_cut_marker_point_projection_audit.py` -> `40 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_cut_boundary_preserved_marker_policy.py tests/test_nle_projection_metadata_preservation_audit.py` -> `5 passed`.
  - `./venv/bin/python tools/audit_nle_cut_marker_point_projection.py --output-dir output/manual_verification/latest/nle_cut_marker_point_projection_20260628` -> passed `true`.

## NLE Time Window View Decoupling Guard - 2026-06-28 KST

- 실행 모드: source-app NLE fit-to-view / time-window viewport-only contract guard.
- 결과: pass for preserving canvas/global subtitle rows, avoiding runtime NLE operation journal appends, avoiding project saves, and keeping fit/time-window paths out of subtitle validation/rescan and timing mutation calls. No UI/UX layout/labels/colors/menus/popups, subtitle quality policy, STT/STT2 policy, subtitle generation, final rows, persisted NLE disk-format, App Store packaging/signing/upload, DMG behavior, runtime undo/redo UI, or per-pixel NLE write changed.
- 저장 위치:
  - Audit: `output/manual_verification/latest/nle_time_window_view_decoupling_20260628/nle_time_window_view_decoupling.md`
  - Audit JSON: `output/manual_verification/latest/nle_time_window_view_decoupling_20260628/nle_time_window_view_decoupling.json`
  - Jammini scout: `.agents/sentinel/handoffs/20260628-070859-next-nle-taption-runtime-contract-scout.md`
- 실제 결과:
  - Audit `ready=true`.
  - View-window-only contract `true`.
  - Model validation/project save/NLE writes allowed `false/false/false`.
  - Method contracts: `TimelineWidget.fit_to_view`, `TimelineWidget.schedule_fit_to_view`, `TimelineTimeWindowMixin.show_time_window_seconds`, `TimelineTimeWindowMixin._apply_edit_window_seconds`, `TimelineTimeWindowMixin.show_ten_second_edit_window`.
  - Forbidden calls/assignments `0`.
  - Focused tests prove fit-to-view and explicit/saved time-window controls preserve subtitle rows and avoid project save/NLE journal calls.
- NAS 상태:
  - Not run. This is a view-window-only timeline contract and does not touch STT/VAD/subtitle generation/final rows.
- 검증:
  - `./venv/bin/python -m py_compile tools/audit_nle_time_window_view_decoupling.py tests/test_timeline_time_window_decoupling.py tests/test_nle_time_window_view_decoupling_audit.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_time_window_decoupling.py tests/test_nle_time_window_view_decoupling_audit.py` -> `4 passed`.
  - `./venv/bin/python tools/audit_nle_time_window_view_decoupling.py --output-dir output/manual_verification/latest/nle_time_window_view_decoupling_20260628` -> ready `true`.

## NLE Playhead Jump Isolation Guard - 2026-06-28 KST

- 실행 모드: source-app NLE global minimap click / global seek / editor scrub immediate-path contract guard.
- 결과: pass for preserving canvas/global subtitle rows, avoiding runtime NLE operation journal appends, avoiding project saves, and keeping the immediate scrub path out of subtitle validation/rescan, dirty marking, timing mutation, and dual-write calls. No UI/UX layout/labels/colors/menus/popups, subtitle quality policy, STT/STT2 policy, subtitle generation, final rows, persisted NLE disk-format, App Store packaging/signing/upload, DMG behavior, runtime undo/redo UI, or per-pixel NLE write changed.
- 저장 위치:
  - Audit: `output/manual_verification/latest/nle_playhead_jump_isolation_20260628/nle_playhead_jump_isolation.md`
  - Audit JSON: `output/manual_verification/latest/nle_playhead_jump_isolation_20260628/nle_playhead_jump_isolation.json`
  - Jammini scout: `.agents/sentinel/handoffs/20260628-165700-next-nle-taption-runtime-contract-scout.md`
- 실제 결과:
  - Audit `ready=true`.
  - Playhead-jump view-only contract `true`.
  - Model validation/project save/NLE writes allowed `false/false/false`.
  - Method contracts: `GlobalCanvas.mousePressEvent`, `TimelineWidget._on_global_seek`, `EditorTimelineVideoMixin._on_scrub`.
  - Forbidden calls/assignments `0`.
  - Focused tests prove global minimap click and timeline global seek preserve subtitle rows, and editor scrub updates playhead plus lightweight preview seek without immediate validation/save/NLE write calls.
- NAS 상태:
  - Not run. This is a view/playhead-only timeline contract and does not touch STT/VAD/subtitle generation/final rows.
- 검증:
  - `./venv/bin/python -m py_compile tools/audit_nle_playhead_jump_isolation.py tests/test_timeline_playhead_jump_isolation.py tests/test_nle_playhead_jump_isolation_audit.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_jump_isolation.py tests/test_nle_playhead_jump_isolation_audit.py` -> `5 passed`.
  - `./venv/bin/python tools/audit_nle_playhead_jump_isolation.py --output-dir output/manual_verification/latest/nle_playhead_jump_isolation_20260628` -> ready `true`.

## NLE Viewport Zoom Decoupling Guard - 2026-06-28 KST

- 실행 모드: source-app NLE viewport-only wheel zoom/global scroll contract guard.
- 결과: pass for timeline Ctrl-wheel zoom and global-canvas wheel scroll preserving primary subtitle rows, avoiding runtime NLE operation journal appends, and passing static viewport-only audit. No UI/UX layout/labels/colors/menus/popups, subtitle quality policy, STT/STT2 policy, subtitle generation, final rows, persisted NLE disk-format, App Store packaging/signing/upload, DMG behavior, runtime undo/redo UI, or per-pixel NLE write changed.
- 저장 위치:
  - Audit: `output/manual_verification/latest/nle_viewport_zoom_decoupling_20260628/nle_viewport_zoom_decoupling.md`
  - Audit JSON: `output/manual_verification/latest/nle_viewport_zoom_decoupling_20260628/nle_viewport_zoom_decoupling.json`
  - Jammini scout: `.agents/sentinel/handoffs/20260628-164700-next-nle-taption-runtime-contract-scout.md`
- 실제 결과:
  - Audit `ready=true`.
  - Viewport-only contract `true`.
  - Model/NLE writes allowed `false/false`.
  - Method contracts: `TimelineWidget.wheelEvent`, `TimelineWidget._apply_zoom`, `GlobalCanvas.wheelEvent`, `TimelineCanvas.set_zoom`.
  - Forbidden wheel-method calls/assignments `0`.
  - Focused tests prove canvas/global subtitle rows are unchanged after wheel interactions and runtime NLE journal append is not called.
- NAS 상태:
  - Not run. This is a view-only timeline contract and does not touch STT/VAD/subtitle generation/final rows.
- 검증:
  - `./venv/bin/python -m py_compile tools/audit_nle_viewport_zoom_decoupling.py tests/test_timeline_wheel_zoom_decoupling.py tests/test_nle_viewport_zoom_decoupling_audit.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_wheel_zoom_decoupling.py tests/test_nle_viewport_zoom_decoupling_audit.py` -> `4 passed`.
  - `./venv/bin/python tools/audit_nle_viewport_zoom_decoupling.py --output-dir output/manual_verification/latest/nle_viewport_zoom_decoupling_20260628` -> ready `true`.

## NLE Preview Cache-Miss Block-Free Guard - 2026-06-28 KST

- 실행 모드: source-app NLE preview/skimming cache-miss UI-thread block-prevention guard.
- 결과: pass for slow cache-miss worker nonblocking behavior, preview-cache worker contract audit, NAS HeyDealer first-180s strict acceptance, and timeout comparison. No UI/UX layout/labels/colors/menus/popups, subtitle quality policy, STT/STT2 policy, persisted NLE disk-format, App Store packaging/signing/upload, DMG behavior, runtime undo/redo UI, cut-boundary evidence ownership, or per-pixel NLE write changed.
- 저장 위치:
  - Audit: `output/manual_verification/latest/nle_preview_skimming_cache_miss_block_free_20260628/nle_preview_skimming_cache_audit.md`
  - Audit JSON: `output/manual_verification/latest/nle_preview_skimming_cache_miss_block_free_20260628/nle_preview_skimming_cache_audit.json`
  - NAS preflight: `output/manual_verification/latest/nle_preview_skimming_cache_miss_nas_preflight_20260628/reference_fixture_availability.md`
  - NAS benchmark: `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_153555/benchmark_results.json`
  - NAS acceptance: `output/manual_verification/latest/nle_preview_skimming_cache_miss_nas_heydealer_20260628/acceptance/reference_benchmark_acceptance.md`
  - NAS timeout audit: `output/manual_verification/latest/stt_worker_timeout_compare_nle_preview_cache_miss_nas_20260628/stt_worker_timeout_audit.md`
  - Jammini prep: `.agents/sentinel/handoffs/20260628-163300-nle-preview-skimming-cache-miss-prep.md`
- 실제 결과:
  - Audit `ready=true`.
  - Preview provenance `purpose=editor_preview_skimming`, `evidence_role=user_preview_only`, `cut_boundary_evidence=false`, `ui_thread_decode_allowed=false`.
  - `cache_miss_thread_contract` all `true`: worker-thread scheduling, in-worker decode, named `video-preview-frame-cache` worker, worker-active reentry guard, and signal-based ready paint.
  - Focused PyQt guard proves `preview_seek()` returns before slow worker decode completes and stays below `50ms`.
- NAS 상태:
  - Preflight ready `true`; media exists `true`; reference SRT exists `true`; clipped reference rows `89`.
  - Acceptance `true`; elapsed `45.744s`; raw/final/reference `58/56/89`.
  - Quality/text/timing `93.766/94.267/0.5808s`.
  - Final invalid/non-monotonic/overlap `0/0/0`; final last end/duration bound `180.0/180.0`; short/long `0/0`; global max-active `1`.
  - STT1/STT2/word selected `21/37/7`.
  - Stage spans: STT1 `18.261775s`, STT2 `14.358197s`, word precision `12.541529s`, subtitle postprocess `0.500109s`.
  - Timeout comparison against baseline `20260628_152303`: `timeout_detected=false`.
- 검증:
  - `./venv/bin/python -m py_compile tools/audit_nle_preview_skimming_cache.py tests/test_nle_preview_skimming_cache_audit.py tests/test_video_player_widget.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_video_player_widget.py -k "preview_seek_cache_miss or preview_frame_cache_prepare or nearest_preview_frame_trace"` -> `4 passed, 79 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_nle_preview_skimming_cache_audit.py tests/test_preview_frame_cache.py` -> `5 passed`.
  - `./venv/bin/python tools/audit_nle_preview_skimming_cache.py --output-dir output/manual_verification/latest/nle_preview_skimming_cache_miss_block_free_20260628` -> ready `true`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/verify_reference_fixture_availability.py --start-sec 0 --duration-sec 180 --output-dir output/manual_verification/latest/nle_preview_skimming_cache_miss_nas_preflight_20260628` -> ready `true`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/benchmark_subtitle_pipeline_variants.py --suite modes --variants mode_high --media ... --reference-srt ... --start-sec 0 --duration-sec 180 --keep-artifacts` -> wrote `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_153555/benchmark_results.json`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/evaluate_reference_benchmark_acceptance.py .codex_work/benchmarks/subtitle_pipeline_variants/20260628_153555/benchmark_results.json --media-duration-sec 180.0 --output-dir output/manual_verification/latest/nle_preview_skimming_cache_miss_nas_heydealer_20260628/acceptance` -> accepted `true`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_stt_worker_timeout.py .codex_work/benchmarks/subtitle_pipeline_variants/20260628_152303/benchmark_results.json .codex_work/benchmarks/subtitle_pipeline_variants/20260628_153555/benchmark_results.json --output-dir output/manual_verification/latest/stt_worker_timeout_compare_nle_preview_cache_miss_nas_20260628` -> timeout detected `false`.

## NLE Drag Commit-Boundary Guard - 2026-06-28 KST

- 실행 모드: source-app Taption-style timeline body-drag commit-boundary guard.
- 결과: pass for preview-only mouse-move behavior, release-only NLE commit, diamond shared-boundary no-gap behavior, runtime owner-map guard coverage, NAS HeyDealer first-180s strict acceptance, and timeout comparison. No UI/UX layout/labels/colors/menus/popups, subtitle quality policy, STT/STT2 policy, persisted NLE disk-format, App Store packaging/signing/upload, DMG behavior, runtime undo/redo UI, or per-pixel NLE write changed.
- 저장 위치:
  - Audit: `output/manual_verification/latest/nle_drag_commit_boundary_guard_20260628/nle_runtime_owner_map_audit.md`
  - Audit JSON: `output/manual_verification/latest/nle_drag_commit_boundary_guard_20260628/nle_runtime_owner_map_audit.json`
  - NAS preflight: `output/manual_verification/latest/nle_drag_commit_boundary_guard_nas_preflight_20260628/reference_fixture_availability.md`
  - NAS benchmark: `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_152303/benchmark_results.json`
  - NAS acceptance: `output/manual_verification/latest/nle_drag_commit_boundary_guard_nas_heydealer_20260628/acceptance/reference_benchmark_acceptance.md`
  - NAS timeout audit: `output/manual_verification/latest/stt_worker_timeout_compare_nle_drag_commit_guard_nas_20260628/stt_worker_timeout_audit.md`
  - Jammini scout: `.agents/sentinel/handoffs/20260628-161800-next-nle-taption-ux-scout.md`
- 실제 결과:
  - Owner map ready `true`; covered owners `24/24`; missing owners `0`.
  - Commit-boundary guards `1/1`; missing guards `0`.
  - Guard `timeline_center_drag_preview_only_until_release` is covered as `taption_preview_only_until_release_commit`.
  - Focused PyQt drag test: NLE move call count `0` during mouse move, unchanged editor rows until release, changed canvas preview rows during drag, and NLE move call count `1` on release.
  - Direction-aware diamond shared-boundary release ordering keeps left/right diamond drags gap-free.
- NAS 상태:
  - Preflight ready `true`; media exists `true`; reference SRT exists `true`; clipped reference rows `89`.
  - Acceptance `true`; elapsed `53.919s`; raw/final/reference `58/56/89`.
  - Quality/text/timing `93.766/94.267/0.5808s`.
  - Final invalid/non-monotonic/overlap `0/0/0`; final last end/duration bound `180.0/180.0`; short/long `0/0`; global max-active `1`.
  - STT1/STT2/word selected `21/37/7`.
  - Stage spans: STT1 `18.472196s`, STT2 `18.348319s`, word precision `16.007801s`, subtitle postprocess `0.947687s`.
  - Timeout comparison against baseline `20260628_141640`: `timeout_detected=false`.
- 검증:
  - `./venv/bin/python -m py_compile ui/editor/ux/timeline_input.py tools/audit_nle_runtime_owner_map.py tests/test_nle_runtime_owner_map_audit.py tests/test_editor_timeline_drag_release.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_editor_timeline_drag_release.py -k "center_drag_preview_waits_until_release"` -> `1 passed, 7 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_editor_timeline_drag_release.py` -> `8 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_nle_runtime_owner_map_audit.py` -> `3 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_nle_runtime_owner_map_audit.py tests/test_project_nle_dual_write.py` -> `35 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py -k "center_drag or reorder or diamond"` -> `32 passed, 161 deselected`.
  - `./venv/bin/python tools/audit_nle_runtime_owner_map.py --output-dir output/manual_verification/latest/nle_drag_commit_boundary_guard_20260628` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/verify_reference_fixture_availability.py --start-sec 0 --duration-sec 180 --output-dir output/manual_verification/latest/nle_drag_commit_boundary_guard_nas_preflight_20260628` -> ready `true`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/benchmark_subtitle_pipeline_variants.py --suite modes --variants mode_high --media ... --reference-srt ... --start-sec 0 --duration-sec 180 --keep-artifacts` -> wrote `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_152303/benchmark_results.json`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/evaluate_reference_benchmark_acceptance.py .codex_work/benchmarks/subtitle_pipeline_variants/20260628_152303/benchmark_results.json --media-duration-sec 180.0 --output-dir output/manual_verification/latest/nle_drag_commit_boundary_guard_nas_heydealer_20260628/acceptance` -> accepted `true`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_stt_worker_timeout.py .codex_work/benchmarks/subtitle_pipeline_variants/20260628_141640/benchmark_results.json .codex_work/benchmarks/subtitle_pipeline_variants/20260628_152303/benchmark_results.json --output-dir output/manual_verification/latest/stt_worker_timeout_compare_nle_drag_commit_guard_nas_20260628` -> timeout detected `false`.

## NLE Operation Journal Trace Event Audit - 2026-06-28 KST

- 실행 모드: source-app runtime-only NLE operation journal trace contract.
- 결과: pass for runtime journal append trace events, safe payload contract, clean legacy storage, and final-surface stability. No UI/UX, subtitle quality, persisted NLE disk-format, App Store packaging/signing/upload, DMG behavior, runtime undo/redo UI, or per-pixel NLE write changed.
- 저장 위치:
  - Audit: `output/manual_verification/latest/nle_operation_journal_trace_audit_20260628/nle_operation_journal_audit.md`
  - Audit JSON: `output/manual_verification/latest/nle_operation_journal_trace_audit_20260628/nle_operation_journal_audit.json`
  - Jammini scout: `.agents/sentinel/handoffs/20260628-160200-nle-operation-journal-trace.md`
- 실제 결과:
  - `ready=true`; operation family count `12`.
  - Runtime journal count `12`; operation trace event count `12`; operation trace event contract ok `true`.
  - Storage clean count `12`.
  - Final invalid/non-monotonic/overlap `0/0/0`; global max-active `1`.
  - Trace payloads include operation/provenance/stability metadata and exclude caption text, raw project paths, and raw `target_ids`.
- 검증:
  - `./venv/bin/python -m py_compile core/project/nle_project_state.py tools/audit_nle_operation_journal.py tests/test_project_nle_operations.py tests/test_nle_operation_journal_audit.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_operations.py tests/test_nle_operation_journal_audit.py -k "operation_journal"` -> `3 passed, 5 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_operations.py tests/test_project_nle_dual_write.py tests/test_nle_operation_journal_audit.py tests/test_nle_runtime_owner_map_audit.py` -> `43 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_trace_logger.py tests/test_trace_log_bundle_audit.py` -> `18 passed`.
  - `./venv/bin/python tools/audit_nle_operation_journal.py --output-dir output/manual_verification/latest/nle_operation_journal_trace_audit_20260628` -> pass.
- NAS 상태:
  - Preflight: `output/manual_verification/latest/nle_operation_journal_trace_nas_preflight_20260628/reference_fixture_availability.md`; ready `true`, media exists `true`, reference SRT exists `true`, clipped reference rows `89`.
  - Benchmark: `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_151123/benchmark_results.json`.
  - Acceptance: `output/manual_verification/latest/nle_operation_journal_trace_nas_heydealer_20260628/acceptance/reference_benchmark_acceptance.md`; accepted `true`, elapsed `52.699s`, raw/final/reference `58/56/89`, quality/text/timing `93.766/94.267/0.5808s`, final invalid/non-monotonic/overlap `0/0/0`, final last end/duration bound `180.0/180.0`, short/long `0/0`, global max-active `1`, STT1/STT2/word selected `21/37/7`.
  - Timeout audit: `output/manual_verification/latest/stt_worker_timeout_compare_nle_operation_trace_nas_20260628/stt_worker_timeout_audit.md`; timeout detected `false`.
  - This remains regression evidence only. It does not promote collect-cache defaults or change STT/STT2/word precision policy.

## Project IO Trace Contract - 2026-06-28 KST

- 실행 모드: source-app NLE save/load diagnostic trace contract.
- 결과: pass for project save/open/cache-hit trace events, raw path exclusion, runtime NLE hydration evidence, and clean legacy storage. No UI/UX, subtitle quality, persisted NLE disk-format, App Store packaging/signing/upload, DMG behavior, or per-pixel NLE write changed.
- 저장 위치:
  - Audit: `output/manual_verification/latest/project_io_trace_contract_20260628/project_io_trace_contract.md`
  - Audit JSON: `output/manual_verification/latest/project_io_trace_contract_20260628/project_io_trace_contract.json`
  - Jammini scout: `.agents/sentinel/handoffs/20260628-155100-project-io-save-load-trace.md`
- 실제 결과:
  - `passed=true`; project IO event count `3`.
  - Save/disk-open/cache-hit counts `1/1/1`.
  - Raw path leak `false`; storage clean `true`.
  - Disk/cache NLE runtime state attached `true/true`.
  - Events include `event_type`, basename, path hash, cache source, elapsed time, payload codec/compression, storage clean flags, and stripped runtime-key count.
- 검증:
  - `./venv/bin/python -m py_compile core/project/project_io.py tools/audit_project_io_trace_contract.py tests/test_trace_logger.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_trace_logger.py tests/test_trace_log_bundle_audit.py` -> `18 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_snapshot.py tests/test_project_nle_runtime_cutover.py tests/test_project_context.py -k "nle or project_file_cache or write_project_file or read_project_file or save_project_routes_editor_rows_through_runtime_nle_state_without_drift or strips_external_runtime_views"` -> `26 passed, 85 deselected, 4 subtests passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_context.py` -> `86 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_operations.py tests/test_project_nle_dual_write.py tests/test_nle_operation_journal_audit.py tests/test_nle_runtime_owner_map_audit.py` -> `43 passed`.
  - `./venv/bin/python tools/audit_project_io_trace_contract.py --output-dir output/manual_verification/latest/project_io_trace_contract_20260628` -> pass.

## NLE Preserved Marker Policy Audit - 2026-06-28 KST

- 실행 모드: corrected source-fps scout plus detector-robustness evidence를 결합한 source-app fixed cut-boundary preserved-marker policy read-only audit.
- 결과: pass for diagnostic tooling, fixed-fixture policy evidence, split/snap guard, and NAS availability preflight. No runtime detector threshold, subtitle quality policy, STT/STT2 policy, UI/UX, QML/GPU default, App Store packaging/signing/upload, DMG behavior, clip-span mapping, per-pixel NLE write, or persisted NLE disk field changed.
- 저장 위치:
  - Preserved-marker audit: `output/manual_verification/latest/nle_preserved_marker_policy_20260628/cut_boundary_preserved_marker_policy.md`
  - Preserved-marker JSON: `output/manual_verification/latest/nle_preserved_marker_policy_20260628/cut_boundary_preserved_marker_policy.json`
  - NAS preflight: `output/manual_verification/latest/nle_preserved_marker_policy_nas_preflight_20260628/reference_fixture_availability.md`
  - Jammini route probe: `.agents/sentinel/handoffs/20260628-142200-watchdog-handoff-probe.md`
  - Jammini scout: `.agents/sentinel/handoffs/20260628-152200-nle-preserved-marker-policy.md`
- 실제 fixed-fixture 결과:
  - `passed=true`; all target frames have marker policy; review required frames `[]`.
  - Frame `2676`: `visual_marker_confirmed`, source status `detected`, detector classification `visual_detection_available`, best score `72.293`, best hits `4`.
  - Frame `2766`: `preserved_marker_required`, source status `preserved_only`, detector classification `weak_visual_change_not_threshold_candidate`, best score `3.812`, best hits `0`.
  - Confirmed cuts remain point evidence rather than clip spans; preserved marker evidence can force subtitle split/snap but must not lower visual detector thresholds.
  - Final subtitle guard requires invalid/non-monotonic/overlap `0/0/0`, global max active `1`, and no row crossing confirmed markers through `tests/test_cut_boundary_fixture_2766_2677.py::test_confirmed_fixture_cut_frames_split_snap_without_crossing_rows`.
- NAS fixture:
  - Current NAS HeyDealer first-180s preflight `ready_for_reference_scored_benchmark=true`; media and SRT both exist; clipped reference rows `89`.
  - No new subtitle-generation benchmark was run because this slice is read-only policy evidence and does not change runtime generation behavior.
- 검증:
  - `./venv/bin/python -m py_compile tools/audit_cut_boundary_preserved_marker_policy.py tests/test_cut_boundary_preserved_marker_policy.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_cut_boundary_preserved_marker_policy.py tests/test_cut_boundary_detector_evidence_robustness.py tests/test_cut_boundary_fixture_2766_2677.py` -> `10 passed, 1 skipped`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_cut_boundary_preserved_marker_policy.py --source-fps-scout output/manual_verification/latest/nle_corrected_target_source_fps_scout_20260628/source_fps_scout.json --detector-robustness output/manual_verification/latest/nle_cut_boundary_2766_detector_robustness_20260628/cut_boundary_detector_evidence_robustness.json --output-dir output/manual_verification/latest/nle_preserved_marker_policy_20260628` -> pass.
  - `AI_SUBTITLE_STUDIO_CUT_BOUNDARY_FIXTURE=... AI_SUBTITLE_STUDIO_CUT_BOUNDARY_EXPECT="2766,2676" AI_SUBTITLE_STUDIO_CUT_BOUNDARY_PIPE_MAX_FPS="60" QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_cut_boundary_fixture_2766_2677.py` -> `6 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/verify_reference_fixture_availability.py --start-sec 0 --duration-sec 180 --output-dir output/manual_verification/latest/nle_preserved_marker_policy_nas_preflight_20260628` -> ready `true`.

## Live NAS HeyDealer STT Regression Refresh - 2026-06-28 KST

- 실행 모드: owner-required HeyDealer first-180s NAS fixture preflight plus High-mode real-media regression after NAS was reported on again.
- 결과: pass for preflight, strict reference acceptance, final subtitle stability, global canvas stability, and worker-timeout comparison. No runtime STT/STT2/word precision policy, collect-cache default, subtitle quality gate, UI/UX, NLE persistence, App Store packaging/signing/upload, DMG behavior, or detector threshold changed.
- 저장 위치:
  - Preflight: `output/manual_verification/latest/heydealer_nas_preflight_live_20260628/reference_fixture_availability.md`
  - Benchmark: `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_141640/benchmark_results.json`
  - Acceptance: `output/manual_verification/latest/stt_nas_live_heydealer_20260628/acceptance/reference_benchmark_acceptance.md`
  - Timeout audit: `output/manual_verification/latest/stt_worker_timeout_compare_nas_live_20260628/stt_worker_timeout_audit.md`
  - Jammini route probe: `.agents/sentinel/handoffs/20260628-141544-watchdog-handoff-probe.md`
  - Jammini scout: `.agents/sentinel/handoffs/20260628-151600-stt-nas-on-regression-gate.md`
- 실제 NAS fixture 결과:
  - Preflight ready `true`; media exists `true`; reference SRT exists `true`; clipped reference rows `89`.
  - Acceptance `true`; elapsed `45.631s`; raw/final/reference `58/56/89`.
  - Quality/text/timing `93.766/94.267/0.5808s`.
  - Final invalid/non-monotonic/overlap `0/0/0`; final last end/duration bound `180.0/180.0`; short/long `0/0`; global max active `1`.
  - STT1/STT2/word selected `21/37/7`.
  - Stage spans: STT1 `18.255019s`, STT2 `14.239592s`, word precision `12.559778s`, subtitle postprocess `0.495304s`.
  - Timeout comparison against baseline `20260628_113906`: `timeout_detected=false`, timeout run count `0/2`, timeout elapsed `0s`.
- 해석:
  - NAS availability and the current High-mode real-media path are healthy in this run.
  - This is regression evidence only. `stt_primary_collect_cache_enabled=false` and `stt_recheck_collect_cache_enabled=false` remain production defaults until explicit owner review.
- 검증:
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/verify_reference_fixture_availability.py --start-sec 0 --duration-sec 180 --output-dir output/manual_verification/latest/heydealer_nas_preflight_live_20260628` -> ready `true`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/benchmark_subtitle_pipeline_variants.py --suite modes --variants mode_high --media ... --reference-srt ... --start-sec 0 --duration-sec 180 --keep-artifacts` -> wrote `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_141640/benchmark_results.json`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/evaluate_reference_benchmark_acceptance.py .codex_work/benchmarks/subtitle_pipeline_variants/20260628_141640/benchmark_results.json --media-duration-sec 180.0 --output-dir output/manual_verification/latest/stt_nas_live_heydealer_20260628/acceptance` -> accepted `true`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_stt_worker_timeout.py .codex_work/benchmarks/subtitle_pipeline_variants/20260628_113906/benchmark_results.json .codex_work/benchmarks/subtitle_pipeline_variants/20260628_141640/benchmark_results.json --output-dir output/manual_verification/latest/stt_worker_timeout_compare_nas_live_20260628` -> timeout detected `false`.

## NLE Cut-Boundary 2766 Detector Evidence Robustness Audit - 2026-06-28 KST

- 실행 모드: source-app fixed cut-boundary frame `2766` detector-evidence read-only robustness audit.
- 결과: pass for diagnostic tooling and real fixed-fixture evidence; no runtime detector thresholds, subtitle quality policy, STT/STT2 policy, UI/UX, QML/GPU default, App Store packaging/signing/upload, DMG behavior, or persisted NLE disk field changed.
- 저장 위치:
  - Robustness audit: `output/manual_verification/latest/nle_cut_boundary_2766_detector_robustness_20260628/cut_boundary_detector_evidence_robustness.md`
  - Robustness JSON: `output/manual_verification/latest/nle_cut_boundary_2766_detector_robustness_20260628/cut_boundary_detector_evidence_robustness.json`
  - Jammini route probe: `.agents/sentinel/handoffs/20260628-140524-watchdog-handoff-probe.md`
  - Jammini scout: `.agents/sentinel/handoffs/20260628-141000-cut-boundary-2766-detector-scout.md`
- 수정 요약:
  - Added `tools/audit_cut_boundary_detector_evidence_robustness.py`.
  - Added `tests/test_cut_boundary_detector_evidence_robustness.py`.
  - Updated `ACTION_ITEMS.md`, `NLE_Action.md`, `COMPLETED_ACTION_ITEMS.md`, `docs/VALIDATION.md`, and `docs/HANDOFF.md`.
- 실제 fixed-fixture 결과:
  - Target frames `2766,2676`; pairs `2765:2766,2675:2676`.
  - Modes `fast4,cross5,full9`; widths `320,480,960,1920`.
  - Frame `2766`: classification `weak_visual_change_not_threshold_candidate`; detected any mode `false`; best mode `cross5`, best width `1920`, best score `3.812`, best hits `0`, best pixel `0.034849`, best motion `1.315`.
  - Frame `2676`: classification `visual_detection_available`; detected any mode `true`; best score `72.293`, best hits `4`, best pixel `0.884247`, best motion `65.37`.
  - Detector tuning candidate count `0`; threshold relaxation allowed `false`; runtime change allowed `false`.
- 해석:
  - `2766`은 visual detector threshold를 낮춰 살릴 후보가 아니라 low-contrast/static frame-grid marker evidence로 취급해야 한다.
  - 다음 NLE cut-boundary 작업은 `2766`을 preserved marker/frame-grid evidence로 유지하거나 fixture truth를 재검토하는 쪽이어야 하며, threshold relaxation은 이 fixture만으로 승인하지 않는다.
- 검증:
  - `./venv/bin/python -m py_compile tools/audit_cut_boundary_detector_evidence_robustness.py tests/test_cut_boundary_detector_evidence_robustness.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_cut_boundary_detector_evidence_robustness.py tests/test_cut_boundary_fixture_target_correction.py tests/test_cut_boundary_fixture_2766_2677.py` -> `9 passed, 1 skipped`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_cut_boundary_detector_evidence_robustness.py "/Users/u_mo_c/Library/Mobile Documents/com~apple~CloudDocs/AI_EDIT/내 프로젝트 (3).MP4" --pairs 2765:2766,2675:2676 --output-dir output/manual_verification/latest/nle_cut_boundary_2766_detector_robustness_20260628` -> pass.

## NLE Cut-Boundary Fixture Target Correction - 2026-06-28 KST

- 실행 모드: source-app fixed cut-boundary QA target correction from historical frame `2677` to corrected frame `2676`.
- 결과: pass for target correction tooling, corrected fixture proof, and NAS availability preflight. No runtime detector threshold, subtitle quality policy, STT/STT2 policy, UI/UX, QML/GPU default, App Store packaging/signing/upload, DMG behavior, or persisted NLE disk field changed.
- 저장 위치:
  - Target correction audit: `output/manual_verification/latest/nle_cut_boundary_fixture_target_correction_20260628/cut_boundary_fixture_target_correction.md`
  - Corrected source-fps scout: `output/manual_verification/latest/nle_corrected_target_source_fps_scout_20260628/source_fps_scout.md`
  - Corrected visual-window audit: `output/manual_verification/latest/nle_corrected_target_visual_window_audit_20260628/cut_boundary_visual_window_audit.md`
  - Corrected frame-semantics audit: `output/manual_verification/latest/nle_corrected_target_frame_semantics_audit_20260628/cut_boundary_frame_semantics_audit.md`
  - Corrected fixture convention audit: `output/manual_verification/latest/nle_corrected_target_fixture_convention_audit_20260628/cut_boundary_fixture_convention_audit.md`
  - NAS preflight: `output/manual_verification/latest/nle_target_correction_nas_preflight_20260628/reference_fixture_availability.md`
  - Jammini route probe: `.agents/sentinel/handoffs/20260628-135221-watchdog-handoff-probe.md`
  - Jammini scout: `.agents/sentinel/handoffs/20260628-133200-cut-boundary-target-correction.md`
- 실제 fixed-fixture 결과:
  - Corrected target frames `2766,2676`; corrected source-fps pairs `2765:2766,2675:2676`.
  - Target correction count `1`; detector evidence required count `1`; runtime change allowed `false`; QA fixture target change allowed `true`.
  - Frame `2676`: detected `true`, target-best, score `71.932`, expected pair `2675->2676`, convention review required `false`.
  - Frame `2766`: still `preserved_only` / `target_detection_gap`, score `2.059`; this remains detector-evidence work before any threshold tuning.
  - Corrected frame-semantics audit now reports semantic mismatch count `0`, detected-neighbor conflict count `0`, target detection gap count `1`.
  - Corrected fixture convention audit exits `0` with fixture label/boundary convention review required `false`; the only open cut-boundary target is detector evidence for `2766`.
- NAS fixture:
  - Current NAS HeyDealer first-180s preflight `ready_for_reference_scored_benchmark=true`; media and SRT both exist; clipped reference rows `89`.
  - No new subtitle-generation benchmark was run because this slice changes QA target convention/default audit inputs only, not runtime generation behavior.
- 검증:
  - `./venv/bin/python -m py_compile tools/audit_cut_boundary_fixture_target_correction.py tests/test_cut_boundary_fixture_target_correction.py tools/verify_cut_boundary_source_fps_scout.py tools/audit_cut_boundary_visual_window.py tests/test_cut_boundary_fixture_2766_2677.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_cut_boundary_fixture_target_correction.py tests/test_cut_boundary_fixture_convention_audit.py tests/test_cut_boundary_frame_semantics_audit.py tests/test_cut_boundary_fixture_2766_2677.py` -> `13 passed, 1 skipped`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_cut_boundary_fixture_target_correction.py output/manual_verification/latest/nle_cut_boundary_fixture_convention_audit_20260628/cut_boundary_fixture_convention_audit.json --output-dir output/manual_verification/latest/nle_cut_boundary_fixture_target_correction_20260628` -> pass, corrected frames `2766,2676`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/verify_cut_boundary_source_fps_scout.py ... --output-dir output/manual_verification/latest/nle_corrected_target_source_fps_scout_20260628` -> pass, frame `2676` detected and frame `2766` preserved-only.
  - `AI_SUBTITLE_STUDIO_CUT_BOUNDARY_FIXTURE=... AI_SUBTITLE_STUDIO_CUT_BOUNDARY_EXPECT="2766,2676" AI_SUBTITLE_STUDIO_CUT_BOUNDARY_PIPE_MAX_FPS="60" QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_cut_boundary_fixture_2766_2677.py` -> `6 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_cut_boundary_visual_window.py ... --output-dir output/manual_verification/latest/nle_corrected_target_visual_window_audit_20260628` -> expected fail, exit `1`, because frame `2766` remains not detected.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_cut_boundary_frame_semantics.py output/manual_verification/latest/nle_corrected_target_visual_window_audit_20260628/cut_boundary_visual_window_audit.json --output-dir output/manual_verification/latest/nle_corrected_target_frame_semantics_audit_20260628` -> expected fail, exit `1`, because frame `2766` remains a target detection gap.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_cut_boundary_fixture_convention.py output/manual_verification/latest/nle_corrected_target_frame_semantics_audit_20260628/cut_boundary_frame_semantics_audit.json --output-dir output/manual_verification/latest/nle_corrected_target_fixture_convention_audit_20260628` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/verify_reference_fixture_availability.py --start-sec 0 --duration-sec 180 --output-dir output/manual_verification/latest/nle_target_correction_nas_preflight_20260628` -> pass, ready `true`.

## NLE Cut-Boundary Fixture Convention Contact Sheet Audit - 2026-06-28 KST

- 실행 모드: source-app fixed cut-boundary frame convention read-only visual evidence generation.
- 결과: pass for diagnostic tooling and visual artifact generation; audit command intentionally exits `1` because fixture label/boundary convention review remains required before detector threshold tuning.
- 저장 위치:
  - Fixture convention audit: `output/manual_verification/latest/nle_cut_boundary_fixture_convention_audit_20260628/cut_boundary_fixture_convention_audit.md`
  - Fixture convention JSON: `output/manual_verification/latest/nle_cut_boundary_fixture_convention_audit_20260628/cut_boundary_fixture_convention_audit.json`
  - Frame `2677` contact sheet: `output/manual_verification/latest/nle_cut_boundary_fixture_convention_audit_20260628/target_2677_frame_contact_sheet.png`
  - Frame `2766` contact sheet: `output/manual_verification/latest/nle_cut_boundary_fixture_convention_audit_20260628/target_2766_frame_contact_sheet.png`
  - NAS preflight: `output/manual_verification/latest/nle_fixture_convention_nas_preflight_20260628/reference_fixture_availability.md`
  - Jammini route probe: `.agents/sentinel/handoffs/20260628-134307-watchdog-handoff-probe.md`
  - Jammini scout: `.agents/sentinel/handoffs/20260628-133100-cut-boundary-fixture-contact-sheet.md`
- 수정 요약:
  - Added `tools/audit_cut_boundary_fixture_convention.py`.
  - Added `tests/test_cut_boundary_fixture_convention_audit.py`.
  - Updated `ACTION_ITEMS.md`, `NLE_Action.md`, `COMPLETED_ACTION_ITEMS.md`, `docs/VALIDATION.md`, and `docs/HANDOFF.md`.
  - No runtime detector thresholds, subtitle quality policy, STT/STT2 policy, UI/UX, QML/GPU defaults, App Store packaging/signing/upload, DMG behavior, or persisted NLE disk fields changed.
- 실제 fixed-fixture 결과:
  - `fixture_label_or_boundary_convention_review_required=true`, label/boundary review count `1`, detector evidence required count `1`, contact sheet count `2`, runtime change allowed `false`.
  - Frame `2677`: classification `detected_neighbor_before_target`; expected pair `2676->2677`, mean delta `2.381499`; strongest pair `2675->2676`, mean delta `72.849699`; ratio `30.589851`.
  - Frame `2766`: classification `target_detection_gap`; expected pair `2765->2766`, mean delta `2.506516`; strongest pair `2768->2769`, mean delta `3.251852`; ratio `1.297359`.
  - Visual inspection of `target_2677_frame_contact_sheet.png` shows the hard visual change between frames `2675` and `2676`, while frames `2676`, `2677`, and `2678` stay within the same shot.
- NAS fixture:
  - Current NAS HeyDealer first-180s preflight `ready_for_reference_scored_benchmark=true`; media and SRT both exist; clipped reference rows `89`.
  - No new subtitle-generation benchmark was run because this slice is read-only fixture evidence generation and does not change runtime behavior.
- 검증:
  - `./venv/bin/python -m py_compile tools/audit_cut_boundary_fixture_convention.py tests/test_cut_boundary_fixture_convention_audit.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_cut_boundary_fixture_convention_audit.py tests/test_cut_boundary_frame_semantics_audit.py` -> `6 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_cut_boundary_fixture_convention.py ... --output-dir output/manual_verification/latest/nle_cut_boundary_fixture_convention_audit_20260628` -> expected fail, exit `1`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/verify_reference_fixture_availability.py --start-sec 0 --duration-sec 180 --output-dir output/manual_verification/latest/nle_fixture_convention_nas_preflight_20260628` -> pass, ready `true`.

## NLE Cut-Boundary Frame Semantics Audit - 2026-06-28 KST

- 실행 모드: existing visual-window JSON을 입력으로 하는 source-app fixed cut-boundary frame semantics read-only classification.
- 결과: pass for diagnostic tooling; audit command intentionally exits `1` because review is required before detector threshold tuning.
- 저장 위치:
  - Frame semantics audit: `output/manual_verification/latest/nle_cut_boundary_frame_semantics_audit_20260628/cut_boundary_frame_semantics_audit.md`
  - Frame semantics JSON: `output/manual_verification/latest/nle_cut_boundary_frame_semantics_audit_20260628/cut_boundary_frame_semantics_audit.json`
  - NAS acceptance: `output/manual_verification/latest/nle_frame_semantics_nas_heydealer_20260628/acceptance/reference_benchmark_acceptance.md`
  - STT worker timeout compare: `output/manual_verification/latest/stt_worker_timeout_compare_frame_semantics_nas_20260628/stt_worker_timeout_audit.md`
  - NAS benchmark: `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_133307/benchmark_results.json`
  - Jammini route probe: `.agents/sentinel/handoffs/20260628-132944-watchdog-handoff-probe.md`
  - Jammini scout: `.agents/sentinel/handoffs/20260628-133000-cut-boundary-frame-semantics-audit.md`
- 수정 요약:
  - Added `tools/audit_cut_boundary_frame_semantics.py`.
  - Added `tests/test_cut_boundary_frame_semantics_audit.py`.
  - Updated `ACTION_ITEMS.md`, `NLE_Action.md`, `COMPLETED_ACTION_ITEMS.md`, `docs/VALIDATION.md`, and `docs/HANDOFF.md`.
  - No runtime detector thresholds, subtitle quality policy, STT/STT2 policy, UI/UX, QML/GPU defaults, App Store packaging/signing/upload, DMG behavior, or persisted NLE disk fields changed.
- 실제 frame-semantics 결과:
  - `frame_semantics_review_required=true`, semantic mismatch count `1`, target detection gap count `2`, detected-neighbor conflict count `1`, detector-tuning candidate count `1`.
  - Frame `2766`: classification `target_detection_gap`; expected transition `2765->2766`, strongest local transition `2768->2769`, strongest detected `false`, offset `+3`.
  - Frame `2677`: classification `detected_neighbor_before_target`; expected transition `2676->2677`, strongest detected transition `2675->2676`, offset `-1`, score `71.932`.
- NAS HeyDealer regression:
  - Acceptance `true`; elapsed `179.579s`; raw/final/reference `58/56/89`.
  - Quality/text/timing `93.766/94.267/0.5808s`.
  - Final invalid/non-monotonic/overlap `0/0/0`; final last end/duration bound `180.0/180.0`; short/long `0/0`; global max active `1`.
  - STT stages: STT1 `152.487713s`, STT2 `14.151725s`, word precision `12.359951s`, subtitle postprocess `0.498793s`.
  - Timeout audit `timeout_detected=false`; this is slow STT1 collect evidence, not timeout/fallback proof or a speed approval.
- 검증:
  - `./venv/bin/python -m py_compile tools/audit_cut_boundary_frame_semantics.py tests/test_cut_boundary_frame_semantics_audit.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_cut_boundary_frame_semantics_audit.py tests/test_cut_boundary_visual_window_audit.py` -> `6 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_cut_boundary_frame_semantics.py ... --output-dir output/manual_verification/latest/nle_cut_boundary_frame_semantics_audit_20260628` -> expected fail, exit `1`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/evaluate_reference_benchmark_acceptance.py .codex_work/benchmarks/subtitle_pipeline_variants/20260628_133307/benchmark_results.json --media-duration-sec 180.0 --output-dir output/manual_verification/latest/nle_frame_semantics_nas_heydealer_20260628/acceptance` -> `accepted=true`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_stt_worker_timeout.py .codex_work/benchmarks/subtitle_pipeline_variants/20260628_113906/benchmark_results.json .codex_work/benchmarks/subtitle_pipeline_variants/20260628_133307/benchmark_results.json --output-dir output/manual_verification/latest/stt_worker_timeout_compare_frame_semantics_nas_20260628` -> pass, `timeout_detected=false`.

## NLE Cut-Boundary Visual Window Audit - 2026-06-28 KST

- 실행 모드: source-app fixed cut-boundary frame `2766`/`2677` read-only visual transition window ranking.
- 결과: pass for diagnostic tooling; strict target detection intentionally fails because neither requested target is the strongest detected transition in its local window.
- 저장 위치:
  - Visual window audit: `output/manual_verification/latest/nle_cut_boundary_visual_window_audit_20260628/cut_boundary_visual_window_audit.md`
  - Visual window JSON: `output/manual_verification/latest/nle_cut_boundary_visual_window_audit_20260628/cut_boundary_visual_window_audit.json`
  - Jammini route probe: `.agents/sentinel/handoffs/20260628-132057-watchdog-handoff-probe.md`
  - Jammini scout: `.agents/sentinel/handoffs/20260628-132100-cut-boundary-visual-window-audit.md`
- 수정 요약:
  - Added `tools/audit_cut_boundary_visual_window.py` to rank visual transition scores around fixed target frames.
  - Added `tests/test_cut_boundary_visual_window_audit.py`.
  - Updated `ACTION_ITEMS.md`, `NLE_Action.md`, `COMPLETED_ACTION_ITEMS.md`, `docs/VALIDATION.md`, and `docs/HANDOFF.md`.
  - No runtime detector thresholds, subtitle quality policy, STT/STT2 policy, UI/UX, QML/GPU defaults, App Store packaging/signing/upload, DMG behavior, or persisted NLE disk fields changed.
- 실제 고정 fixture 결과:
  - Strict targets detected `false`; target best count `0/2`; window radius `3`.
  - Frame `2766`: target detected `false`, rank `4`, target score `2.059`, best nearby frame `2769`, best score `2.715`, best detected `false`.
  - Frame `2677`: target detected `false`, rank `2`, target score `1.997`, best nearby frame `2676`, best score `71.932`, best detected `true`.
  - The audit exits `1` while strict targets are not detected; this is expected diagnostic evidence and blocks visual-detection claims.
- 검증:
  - `./venv/bin/python -m py_compile tools/audit_cut_boundary_visual_window.py tests/test_cut_boundary_visual_window_audit.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_cut_boundary_visual_window_audit.py` -> `3 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_cut_boundary_visual_window.py ... --targets 2766,2677 --radius 3 --output-dir output/manual_verification/latest/nle_cut_boundary_visual_window_audit_20260628` -> expected fail, exit `1`.

## NLE Fixed Cut-Boundary Visual Evidence Gate - 2026-06-28 KST

- 실행 모드: source-app fixed cut-boundary frame `2766`/`2677` decoder visual-evidence classification plus strict visual-detection gate.
- 결과: pass for frame-grid preservation and validator clarity; strict visual detection intentionally fails because both target frames are still `preserved_only`, not `detected`.
- 저장 위치:
  - Visual evidence scout: `output/manual_verification/latest/nle_fixed_cut_boundary_visual_evidence_gate_20260628/source_fps_scout.md`
  - Strict visual gate: `output/manual_verification/latest/nle_fixed_cut_boundary_visual_evidence_gate_20260628_strict/source_fps_scout.md`
  - Jammini route probe: `.agents/sentinel/handoffs/20260628-131045-watchdog-handoff-probe.md`
  - Jammini scout: `.agents/sentinel/handoffs/20260628-131100-nle-fixed-cut-boundary-visual-evidence.md`
- 수정 요약:
  - `tools/verify_cut_boundary_source_fps_scout.py` now emits `visual_candidate_status`, `visual_evidence_available`, `visual_detection_summary`, and optional `--require-visual-detection`.
  - `tests/test_cut_boundary_fixture_2766_2677.py` now covers metadata-only, preserved-only, strict-fail, and strong detected visual candidates.
  - `tests/test_pipeline_cut_boundary_cache.py` now reads saved project payloads through `read_project_storage_payload(...)`, matching current binary/json project I/O.
  - No runtime detector thresholds, subtitle quality policy, STT/STT2 policy, UI/UX, QML/GPU defaults, App Store packaging/signing/upload, DMG behavior, or persisted NLE disk fields changed.
- 실제 고정 fixture 결과:
  - Decoder extraction status `ok`; probe source `ffprobe`; pipe fps `60000/1001`.
  - Visual evidence available `true`; strict visual detection passed `false`; visual candidate missing count `2`.
  - Frame `2766`: status `preserved_only`, score `2.059`, region hits `0`, pixel ratio `0.029392`, edge ratio `0.048021`, frame preserved `true`.
  - Frame `2677`: status `preserved_only`, score `1.997`, region hits `0`, pixel ratio `0.029288`, edge ratio `0.046615`, frame preserved `true`.
  - Strict command with `--require-visual-detection` returns exit `1`; this blocks visual cut detection claims until a separate detector-tuning slice is proven.
- 검증:
  - `./venv/bin/python -m py_compile tools/verify_cut_boundary_source_fps_scout.py tests/test_cut_boundary_fixture_2766_2677.py tests/test_pipeline_cut_boundary_cache.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_cut_boundary_fixture_2766_2677.py` -> `5 passed, 1 skipped`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/verify_cut_boundary_source_fps_scout.py ... --output-dir output/manual_verification/latest/nle_fixed_cut_boundary_visual_evidence_gate_20260628` -> pass, `strict_visual_detection_passed=false`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/verify_cut_boundary_source_fps_scout.py ... --require-visual-detection --output-dir output/manual_verification/latest/nle_fixed_cut_boundary_visual_evidence_gate_20260628_strict` -> expected fail, exit `1`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_cut_boundary_fixture_2766_2677.py tests/test_cut_boundary_auto_scan_backend.py tests/test_subtitle_boundary_alignment.py tests/test_pipeline_cut_boundary_cache.py` -> `78 passed, 1 skipped`.
  - `git diff --check -- .` -> pass.

## STT Worker Timeout Audit - 2026-06-28 KST

- 실행 모드: NAS HeyDealer first-180s benchmark artifacts read-only STT worker timeout audit.
- 결과: pass; the current slow accepted run is timeout-dominated, while the nearest accepted NAS baseline has no worker-timeout evidence.
- 저장 위치:
  - Timeout compare audit: `output/manual_verification/latest/stt_worker_timeout_compare_20260628/stt_worker_timeout_audit.md`
  - Timeout compare JSON: `output/manual_verification/latest/stt_worker_timeout_compare_20260628/stt_worker_timeout_audit.json`
  - Baseline benchmark: `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_113906/benchmark_results.json`
  - Slow benchmark: `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_123336/benchmark_results.json`
  - Jammini route probe: `.agents/sentinel/handoffs/20260628-124750-watchdog-handoff-probe.md`
  - Jammini scout: `.agents/sentinel/handoffs/20260628-125000-stt-worker-timeout-scout.md`
- 수정 요약:
  - Added `tools/audit_stt_worker_timeout.py` to compare benchmark artifacts and detect WhisperKit worker timeout/fallback spans plus timeout-like word-precision collect failures.
  - Added `tests/test_stt_worker_timeout_audit.py`.
  - Updated `ACTION_ITEMS.md`, `COMPLETED_ACTION_ITEMS.md`, `docs/VALIDATION.md`, and `docs/HANDOFF.md`.
  - No runtime STT policy, model choice, STT2/word precision coverage, collect-cache defaults, quality gates, UI/UX, App Store packaging/signing/upload, DMG, or NLE persistence behavior changed.
- 실제 감사 결과:
  - Timeout detected `true`; artifact/run count `2/2`; timeout run count `1`; timeout total elapsed `330.132245s`.
  - Production change allowed `false`; default cache promotion allowed `false`.
  - Baseline `20260628_113906`: elapsed `45.491s`, timeout elapsed `0s`, final invalid/non-monotonic/overlap `0/0/0`, global max active `1`, quality/text/timing `93.766/94.267/0.5808s`.
  - Slow run `20260628_123336`: elapsed `374.308s`, timeout elapsed `330.132245s`, timeout ratio `0.88198`, timeout labels `STT1=1`, `Fast-STT2=1`, word-precision timeout-like count `1`, final invalid/non-monotonic/overlap `0/0/0`, global max active `1`, quality/text/timing `93.955/94.867/0.5536s`.
  - Blocked from this audit alone: model downgrade, STT2 skipping, word precision skipping, quality-gate relaxation, collect-cache default promotion, UI changes, and App Store work.
- 검증:
  - `./venv/bin/python -m py_compile tools/audit_stt_worker_timeout.py tests/test_stt_worker_timeout_audit.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_stt_worker_timeout_audit.py` -> `3 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_stt_worker_timeout.py .codex_work/benchmarks/subtitle_pipeline_variants/20260628_113906/benchmark_results.json .codex_work/benchmarks/subtitle_pipeline_variants/20260628_123336/benchmark_results.json --output-dir output/manual_verification/latest/stt_worker_timeout_compare_20260628` -> pass, `timeout_detected=true`.

## NLE Fixed Cut-Boundary Fixture Gate - 2026-06-28 KST

- 실행 모드: source-app fixed cut-boundary frame `2766`/`2677` fixture gate plus NAS HeyDealer first-180s regression.
- 결과: pass; exact 60000/1001fps frame-grid preservation and split/snap no-crossing guards are covered, with NAS first-180s strict acceptance still passing.
- 저장 위치:
  - Fixed fixture scout: `output/manual_verification/latest/nle_fixed_cut_boundary_fixture_gate_20260628/source_fps_scout.md`
  - NAS preflight: `output/manual_verification/latest/nle_fixed_cut_boundary_fixture_gate_nas_heydealer_20260628/preflight/reference_fixture_availability.md`
  - NAS acceptance: `output/manual_verification/latest/nle_fixed_cut_boundary_fixture_gate_nas_heydealer_20260628/acceptance/reference_benchmark_acceptance.md`
  - NAS benchmark: `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_123336/benchmark_results.json`
  - Jammini route probe: `.agents/sentinel/handoffs/20260628-121751-watchdog-handoff-probe.md`
  - Jammini scout: `.agents/sentinel/handoffs/20260628-131900-nle-fixed-cut-boundary-fixture-proof.md`
- 수정 요약:
  - `tools/verify_cut_boundary_source_fps_scout.py` now supports probe/frame-extract timeouts, `--pipe-max-fps`, `--fps-override`, `--allow-metadata-only`, and markdown evidence output.
  - `tests/test_cut_boundary_fixture_2766_2677.py` covers metadata-only frame-grid preservation, env-gated real fixture proof, and confirmed split/snap rows that do not cross target frames.
  - No FFmpeg/visual scorer thresholds, subtitle quality policy, STT/STT2 policy, UI/UX, QML/GPU defaults, App Store packaging/signing/upload, DMG behavior, or persisted NLE disk fields changed.
- 실제 고정 fixture 결과:
  - Scout passed `true`; pipe fps `60000/1001`; target frames `2766`, `2677`.
  - Probe source latest artifact `ffprobe`; fallback path `spotlight_fps_override` is covered when probe access times out; frame extract status `metadata_only`.
  - Candidate detected `false/false`; frame preserved `true/true`.
  - This is metadata/frame-grid proof only, not visual cut detection proof.
- NAS HeyDealer regression:
  - Acceptance `true`; elapsed `374.308s`; raw/final/reference `55/57/89`.
  - Quality/text/timing `93.955/94.867/0.5536s`.
  - Final invalid/non-monotonic/overlap `0/0/0`; final last end/duration bound `180.0/180.0`; final short/long `0/0`; global max active `1`.
  - Latency caveat: STT1 and STT2 WhisperKit workers each timed out at `150s` before MLX fallback, and word precision timed out at `30s`; this is a separate STT runtime diagnostic, not a cut-boundary failure.
- 검증:
  - `./venv/bin/python -m py_compile tools/verify_cut_boundary_source_fps_scout.py tests/test_cut_boundary_fixture_2766_2677.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_cut_boundary_fixture_2766_2677.py` -> `2 passed, 1 skipped`.
  - `AI_SUBTITLE_STUDIO_CUT_BOUNDARY_FIXTURE=... AI_SUBTITLE_STUDIO_CUT_BOUNDARY_EXPECT="2766,2677" AI_SUBTITLE_STUDIO_CUT_BOUNDARY_PIPE_MAX_FPS="60" QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_cut_boundary_fixture_2766_2677.py` -> `3 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_cut_boundary_auto_scan_backend.py tests/test_subtitle_boundary_alignment.py tests/test_trace_logger.py` -> `65 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/verify_cut_boundary_source_fps_scout.py ... --fps-override 60000/1001 --allow-metadata-only --probe-timeout-sec 5 --output-dir output/manual_verification/latest/nle_fixed_cut_boundary_fixture_gate_20260628` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/evaluate_reference_benchmark_acceptance.py .codex_work/benchmarks/subtitle_pipeline_variants/20260628_123336/benchmark_results.json --media-duration-sec 180.0 --output-dir output/manual_verification/latest/nle_fixed_cut_boundary_fixture_gate_nas_heydealer_20260628/acceptance` -> `accepted=true`.

## NLE Preview Skimming Trace Events - 2026-06-28 KST

- 실행 모드: source-app NLE preview/skimming trace-event contract audit.
- 결과: pass; preview cache hit/miss/schedule/ready states now emit best-effort async trace events with preview-only provenance and exact fps fields.
- 저장 위치:
  - Audit report: `output/manual_verification/latest/nle_preview_skimming_trace_audit_20260628/nle_preview_skimming_cache_audit.md`
  - Audit JSON: `output/manual_verification/latest/nle_preview_skimming_trace_audit_20260628/nle_preview_skimming_cache_audit.json`
  - Jammini route probe: `.agents/sentinel/handoffs/20260628-115539-watchdog-handoff-probe.md`
  - Jammini scout: `.agents/sentinel/handoffs/20260628-115600-nle-preview-trace-event-scout.md`
- 수정 요약:
  - `VideoPlayerSurfaceMixin` now emits `nle_preview_frame_cache_hit`, `nle_preview_frame_cache_miss`, `nle_preview_frame_cache_schedule`, and `nle_preview_frame_cache_ready`.
  - Events use the existing async `TraceLogger` queue and safely no-op when tracing is unavailable.
  - Trace fields include `source=editor_preview_skimming`, `evidence_role=user_preview_only`, `cut_boundary_evidence=false`, `ui_thread_decode_allowed=false`, cache status, frame, fps, and `fps_num/fps_den`.
  - No UI layout/labels/colors/menus/popups, QML/GPU timeline surface, cut-boundary policy, STT/STT2 policy, App Store packaging/signing/upload, DMG behavior, persisted NLE disk fields, or timeline interaction behavior changed.
- 실제 감사 결과:
  - `ready=true`, `ui_runtime_change_applied=false`, `preview_cache_contract_applied=true`.
  - Trace event contract: trace queue `true`, best-effort `true`, events `true`, preview-only fields `true`, exact fps `true`, throttle `true`.
  - Preview workspace and manifest contract from the previous slice still pass in the same audit.
- 검증:
  - `./venv/bin/python -m py_compile ui/editor/video_player_surface.py tools/audit_nle_preview_skimming_cache.py tests/test_video_player_widget.py tests/test_nle_preview_skimming_cache_audit.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_video_player_widget.py -k "preview_frame_cache or paused_preview_seek or processing_thumbnail or nearest_preview_frame_trace"` -> `7 passed, 75 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_nle_preview_skimming_cache_audit.py tests/test_preview_frame_cache.py` -> `5 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_runtime_memory_manager.py tests/test_trace_log_bundle_audit.py -k "preview_cache or trace_log_bundle"` -> `3 passed, 25 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_nle_preview_skimming_cache.py --output-dir output/manual_verification/latest/nle_preview_skimming_trace_audit_20260628` -> pass.

## NLE Roughcut Range Edit Operation Coverage - 2026-06-28 KST

- 실행 모드: source-app NLE output-domain `roughcut_range_edit` dual-write support plus NAS HeyDealer first-180s regression.
- 결과: pass; roughcut candidate order/range edits can be recorded as output-time NLE operations without changing final subtitle rows, global canvas ownership, roughcut UI schemas, or persisted NLE disk fields.
- 저장 위치:
  - Operation journal audit: `output/manual_verification/latest/nle_roughcut_range_edit_operation_journal_20260628/nle_operation_journal_audit.md`
  - Owner-map audit: `output/manual_verification/latest/nle_roughcut_range_edit_owner_map_20260628/nle_runtime_owner_map_audit.md`
  - NAS preflight: `output/manual_verification/latest/nle_roughcut_range_edit_nas_heydealer_20260628/preflight/reference_fixture_availability.md`
  - NAS acceptance: `output/manual_verification/latest/nle_roughcut_range_edit_nas_heydealer_20260628/acceptance/reference_benchmark_acceptance.md`
  - NAS benchmark: `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_143939/benchmark_results.json`
  - Jammini scout: `.agents/sentinel/handoffs/20260628-153300-nle-roughcut-range-edit-owner-map.md`
- 수정 요약:
  - `core/project/nle_dual_write.py` now exposes `apply_roughcut_range_edit_dual_write_pilot(...)`.
  - `roughcut_range_edit` uses `time_domain=output`, target roughcut ids, release commit/source metadata, undo snapshot metadata, and runtime-only NLE operation-journal entries.
  - `tools/audit_nle_operation_journal.py` and `tools/audit_nle_runtime_owner_map.py` now include the 12th operation family and the 24th owner evidence row.
  - No UI layout/labels/colors/menus/popups, roughcut sidecar schema, final subtitle timing/text, STT/STT2 policy, detector thresholds, persisted NLE project fields, App Store packaging/signing/upload, or DMG behavior changed.
- 실제 감사 결과:
  - Operation journal ready `true`; operation families `12`; release metadata `12`; undo snapshots `12`; runtime journal `12`; storage clean `12`.
  - `roughcut_range_edit` row: domain `output`, release `true`, undo release `true`, runtime journal `true`, undo rows `3`, final invalid/non-monotonic/overlap `0/0/0`, max active `1`, storage clean `true`.
  - Owner map ready `true`; covered owners `24/24`; missing owners `0`; `roughcut_range_edit_candidate_order` covered `2/2`.
- NAS HeyDealer regression:
  - Preflight ready `true`; media and reference SRT exist; clipped reference rows `89`.
  - Acceptance `true`; elapsed `51.429s`; raw/final/reference `58/56/89`.
  - Quality/text/timing `93.766/94.267/0.5808s`.
  - Final invalid/non-monotonic/overlap `0/0/0`; final last end/duration bound `180.0/180.0`; final short/long `0/0`; global max active `1`.
  - Stage spans: STT1 `18.578131s`, STT2 `17.372568s`, word precision `14.804677s`, subtitle postprocess `0.582754s`.
- 검증:
  - `./venv/bin/python -m py_compile core/project/nle_dual_write.py tools/audit_nle_operation_journal.py tools/audit_nle_runtime_owner_map.py tests/test_project_nle_dual_write.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_dual_write.py` -> `32 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_nle_operation_journal_audit.py tests/test_nle_runtime_owner_map_audit.py` -> `5 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_operations.py tests/test_project_nle_dual_write.py tests/test_nle_operation_journal_audit.py tests/test_nle_runtime_owner_map_audit.py` -> `43 passed`.
  - `./venv/bin/python tools/audit_nle_operation_journal.py --output-dir output/manual_verification/latest/nle_roughcut_range_edit_operation_journal_20260628` -> pass.
  - `./venv/bin/python tools/audit_nle_runtime_owner_map.py --output-dir output/manual_verification/latest/nle_roughcut_range_edit_owner_map_20260628` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/evaluate_reference_benchmark_acceptance.py .codex_work/benchmarks/subtitle_pipeline_variants/20260628_143939/benchmark_results.json --output-dir output/manual_verification/latest/nle_roughcut_range_edit_nas_heydealer_20260628/acceptance` -> accepted `true`.

## NLE Preview Skimming Cache Contract - 2026-06-28 KST

- 실행 모드: source-app NLE preview/skimming frame-cache provenance contract audit.
- 결과: pass; preview frame cache is isolated under the temp Preview workspace, writes user-preview-only manifests, and remains separated from cut-boundary evidence.
- 저장 위치:
  - Audit report: `output/manual_verification/latest/nle_preview_skimming_cache_audit_20260628/nle_preview_skimming_cache_audit.md`
  - Audit JSON: `output/manual_verification/latest/nle_preview_skimming_cache_audit_20260628/nle_preview_skimming_cache_audit.json`
  - Jammini route probe: `.agents/sentinel/handoffs/20260628-114704-watchdog-handoff-probe.md`
  - Jammini scout: `.agents/sentinel/handoffs/20260628-114700-nle-preview-skimming-contract-scout.md`
- 수정 요약:
  - `core/runtime/preview_frame_cache.py` now writes sidecar manifests for preview frame thumbnails.
  - Manifest provenance marks `purpose=editor_preview_skimming`, `evidence_role=user_preview_only`, `cut_boundary_evidence=false`, and `ui_thread_decode_allowed=false`.
  - `tools/audit_nle_preview_skimming_cache.py` verifies Preview workspace isolation, nearest-frame cache lookup, source-fps frame-grid metadata, and video surface non-blocking preview miss routing.
  - No UI layout/labels/colors/menus/popups, QML/GPU timeline surface, cut-boundary policy, STT/STT2 policy, App Store packaging/signing/upload, DMG behavior, persisted NLE disk fields, or timeline interaction behavior changed.
- 실제 감사 결과:
  - `ready=true`, `ui_runtime_change_applied=false`, `preview_cache_contract_applied=true`.
  - Preview workspace isolated `true`; cache dir uses `Preview/FrameThumbnails`.
  - Nearest cached preview frame hit `true`.
  - Manifest purpose/evidence/cut-boundary/UI-thread-decode fields: `editor_preview_skimming/user_preview_only/false/false`.
  - Source-fps grid ok `true` with manifest frame `60` at `59.94005994005994fps`.
  - Video surface contract: nearest lookup before worker scheduling `true`, worker scheduling present `true`, worker uses `ensure_preview_frame` `true`, legacy sync cached-thumbnail helper not called by unprimed preview `true`.
- 검증:
  - `./venv/bin/python -m py_compile core/runtime/preview_frame_cache.py tools/audit_nle_preview_skimming_cache.py tests/test_preview_frame_cache.py tests/test_nle_preview_skimming_cache_audit.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_preview_frame_cache.py tests/test_nle_preview_skimming_cache_audit.py` -> `5 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_nle_preview_skimming_cache.py --output-dir output/manual_verification/latest/nle_preview_skimming_cache_audit_20260628` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_video_player_widget.py -k "preview_frame_cache or paused_preview_seek or processing_thumbnail"` -> `5 passed, 75 deselected`.

## NLE Runtime Operation Journal - 2026-06-28 KST

- 실행 모드: source-app NLE runtime operation journal recording plus NAS HeyDealer first-180s regression.
- 결과: pass; all current NLE dual-write operation families append bounded runtime-only journal entries without persisting journal schemas.
- 저장 위치:
  - NLE report: `output/manual_verification/latest/nle_runtime_operation_journal_20260628/nle_operation_journal_audit.md`
  - NLE JSON: `output/manual_verification/latest/nle_runtime_operation_journal_20260628/nle_operation_journal_audit.json`
  - NAS preflight: `output/manual_verification/latest/nle_runtime_operation_journal_nas_heydealer_20260628/preflight/reference_fixture_availability.md`
  - NAS acceptance: `output/manual_verification/latest/nle_runtime_operation_journal_nas_heydealer_20260628/acceptance/reference_benchmark_acceptance.md`
  - NAS benchmark: `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_113906/benchmark_results.json`
  - Jammini route probe: `.agents/sentinel/handoffs/20260628-113253-watchdog-handoff-probe.md`
  - Jammini scout: `.agents/sentinel/handoffs/20260628-113300-in-memory-nle-transaction-journal-scout.md`
- 수정 요약:
  - Added runtime-only `NLEOperationJournalEntry` records to `NLEProjectState`.
  - Every successful NLE dual-write commit boundary now records operation id, family/kind, target ids, commit boundary/source, undo snapshot id, projected count, and final projection stability counts.
  - The journal is bounded and session/runtime only; legacy project storage remains clean of operation/undo/journal/runtime NLE schemas.
  - No persisted NLE disk fields, runtime undo/redo UI behavior, per-pixel drag writes, QML/GPU timeline defaults, App Store packaging/signing/upload, DMG behavior, STT/STT2 policy, or user-visible UI/UX behavior changed.
- 실제 감사 결과:
  - `ready=true`, `runtime_change_applied=false`, `runtime_nle_journal_applied=true`.
  - Operation families `11`, release metadata count `11`, undo snapshot count `11`, runtime journal count `11`, storage clean count `11`.
  - Every audited operation had final invalid/non-monotonic/overlap `0/0/0`, max active `1`, clean legacy storage, and no persisted operation/undo/journal/runtime NLE schema.
  - Blocked scope remains persisted operation journal, runtime undo/redo UI behavior changes, per-pixel NLE writes, and QML/GPU timeline defaults.
- NAS HeyDealer regression:
  - Preflight ready `true`; media and reference SRT exist; clipped reference rows `89`.
  - Acceptance `true`; elapsed `45.491s`; raw/final/reference `58/56/89`.
  - Quality/text/timing `93.766/94.267/0.5808s`.
  - Final invalid/non-monotonic/overlap `0/0/0`; final last end/duration bound `180.0/180.0`; final short/long `0/0`; global max active `1`.
  - STT1/STT2/word selected `21/37/7`.
- 검증:
  - `./venv/bin/python -m py_compile core/project/nle_project_state.py core/project/nle_dual_write.py tools/audit_nle_operation_journal.py tests/test_project_nle_dual_write.py tests/test_project_nle_operations.py tests/test_nle_operation_journal_audit.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_operations.py tests/test_project_nle_dual_write.py tests/test_nle_operation_journal_audit.py` -> `39 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_operations.py tests/test_project_nle_dual_write.py tests/test_nle_operation_journal_audit.py tests/test_nle_adapter_consistency_audit.py tests/test_nle_persistence_cutover_audit.py` -> `47 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_nle_operation_journal.py --output-dir output/manual_verification/latest/nle_runtime_operation_journal_20260628` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/evaluate_reference_benchmark_acceptance.py .codex_work/benchmarks/subtitle_pipeline_variants/20260628_113906/benchmark_results.json --output-dir output/manual_verification/latest/nle_runtime_operation_journal_nas_heydealer_20260628/acceptance` -> `accepted=true`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py tests/test_subtitle_live_editor_feed_facade.py tests/test_native_subtitle_segments.py tests/test_native_subtitle_stt_segments.py` -> `203 passed`.

## NLE Operation Journal Contract Audit - 2026-06-28 KST

- 실행 모드: source-app NLE operation journal/undo contract audit plus NAS HeyDealer first-180s regression.
- 결과: pass; all current NLE operation families carry release commit provenance and undo metadata without persisting operation journal schemas.
- 저장 위치:
  - NLE report: `output/manual_verification/latest/nle_operation_journal_audit_20260628/nle_operation_journal_audit.md`
  - NLE JSON: `output/manual_verification/latest/nle_operation_journal_audit_20260628/nle_operation_journal_audit.json`
  - NAS preflight: `output/manual_verification/latest/nle_operation_journal_nas_heydealer_20260628/preflight/reference_fixture_availability.md`
  - NAS acceptance: `output/manual_verification/latest/nle_operation_journal_nas_heydealer_20260628/acceptance/reference_benchmark_acceptance.md`
  - NAS benchmark: `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_112647/benchmark_results.json`
  - Jammini route probe: `.agents/sentinel/handoffs/20260628-111733-watchdog-handoff-probe.md`
  - Jammini scout: `.agents/sentinel/handoffs/20260628-111900-nle-operation-journal-undo-scout.md`
- 수정 요약:
  - Added `tools/audit_nle_operation_journal.py`.
  - Added `tests/test_nle_operation_journal_audit.py`.
  - Added release commit provenance to NLE dual-write builders and current UI call sites for `gap_generate`, `caption_merge`, `candidate_confirm`, `caption_delete`, `caption_resize`, and `gap_delete`.
  - No persisted NLE disk fields, runtime undo/redo UI behavior, per-pixel drag writes, QML/GPU timeline defaults, App Store packaging/signing/upload, DMG behavior, STT/STT2 policy, or user-visible UI/UX behavior changed.
- 실제 감사 결과:
  - `ready=true`, `runtime_change_applied=false`.
  - Operation families `11`, release metadata count `11`, undo snapshot count `11`, storage clean count `11`.
  - Every audited operation had final invalid/non-monotonic/overlap `0/0/0`, max active `1`, clean legacy storage, and no persisted operation/undo/runtime NLE schema.
  - Blocked scope remains persisted operation journal, runtime undo/redo UI behavior changes, per-pixel NLE writes, and QML/GPU timeline defaults.
- NAS HeyDealer regression:
  - Preflight ready `true`; media and reference SRT exist; clipped reference rows `89`.
  - Acceptance `true`; elapsed `45.846s`; raw/final/reference `58/56/89`.
  - Quality/text/timing `93.766/94.267/0.5808s`.
  - Final invalid/non-monotonic/overlap `0/0/0`; final last end/duration bound `180.0/180.0`; final short/long `0/0`; global max active `1`.
  - STT1/STT2/word selected `21/37/7`.
- 검증:
  - `./venv/bin/python -m py_compile core/project/nle_dual_write.py ui/editor/ux/editor_timeline_video.py ui/editor/editor_segments_stt_selection_flow.py ui/editor/editor_segments_block_surgery.py tools/audit_nle_operation_journal.py tests/test_nle_operation_journal_audit.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_nle_operation_journal_audit.py tests/test_project_nle_dual_write.py tests/test_project_nle_operations.py` -> `37 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_nle_operation_journal.py --output-dir output/manual_verification/latest/nle_operation_journal_audit_20260628` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/evaluate_reference_benchmark_acceptance.py .codex_work/benchmarks/subtitle_pipeline_variants/20260628_112647/benchmark_results.json --output-dir output/manual_verification/latest/nle_operation_journal_nas_heydealer_20260628/acceptance` -> `accepted=true`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py tests/test_subtitle_live_editor_feed_facade.py tests/test_native_subtitle_segments.py tests/test_native_subtitle_stt_segments.py` -> `203 passed`.

## NLE Adapter Cache Consistency Audit - 2026-06-28 KST

- 실행 모드: source-app NLE adapter/cache consistency audit plus current NAS HeyDealer preflight.
- 결과: pass; runtime-only NLE state remains cache/session scoped across repeated save/reopen, and NAS HeyDealer MP4/SRT are currently reachable.
- 저장 위치:
  - NLE report: `output/manual_verification/latest/nle_adapter_consistency_audit_20260628/nle_adapter_consistency_audit.md`
  - NLE JSON: `output/manual_verification/latest/nle_adapter_consistency_audit_20260628/nle_adapter_consistency_audit.json`
  - NAS preflight: `output/manual_verification/latest/heydealer_nas_preflight_current_20260628/reference_fixture_availability.md`
  - Jammini route probe: `.agents/sentinel/handoffs/20260628-110737-watchdog-handoff-probe.md`
  - Jammini scout: `.agents/sentinel/handoffs/20260628-110800-nle-adapter-cache-consistency-scout.md`
- 수정 요약:
  - Added `tools/audit_nle_adapter_consistency.py`.
  - Added `tests/test_nle_adapter_consistency_audit.py`.
  - The audit checks repeated save/reopen cycles, same-cache runtime-state identity, cache-clear rehydration, runtime marker non-persistence, storage stripping, projection parity, and `_PROJECT_FILE_CACHE` LRU limit.
  - No runtime editor behavior, UI/UX, STT/STT2, subtitle timing, save-file format, persisted NLE disk fields, packaging, signing, upload, notarization, App Store Connect, or DMG behavior changed.
- 실제 감사 결과:
  - `ready=true`, `runtime_change_applied=false`, cycles `6/6`.
  - Runtime state schema `ai_subtitle_studio.nle_project_state.v1`, runtime caption count `4`.
  - All repeated cycles: storage clean `true`, marker before clear `true`, marker after clear `false`, row signature stable `true`.
  - Final projection gates: invalid/non-monotonic/overlap `0/0/0`, max active `1`, global canvas stable `true`, save/reload stable `true`.
  - LRU cache owner `core.project.project_io._PROJECT_FILE_CACHE`, max entries `4`, paths written `6`, cache entry count `4`.
  - NAS current preflight: ready `true`, media exists `true`, reference SRT exists `true`, clipped reference rows `89`.
- 검증:
  - `./venv/bin/python -m py_compile tools/audit_nle_adapter_consistency.py tests/test_nle_adapter_consistency_audit.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_nle_adapter_consistency_audit.py` -> `3 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_nle_adapter_consistency.py --output-dir output/manual_verification/latest/nle_adapter_consistency_audit_20260628` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/verify_reference_fixture_availability.py --media "/Volumes/photo/.../헤이딜러_최종.MP4" --reference-srt "/Volumes/photo/.../헤이딜러_최종.srt" --start-sec 0 --duration-sec 180 --output-dir output/manual_verification/latest/heydealer_nas_preflight_current_20260628` -> pass.

## NLE Runtime Owner Map Audit - 2026-06-28 KST

- 실행 모드: source-app NLE runtime mutation owner-map audit; no runtime behavior change.
- 결과: pass; current release/commit NLE mutation owners are covered `23/23`.
- 저장 위치:
  - Report: `output/manual_verification/latest/nle_runtime_owner_map_audit_20260628/nle_runtime_owner_map_audit.md`
  - JSON: `output/manual_verification/latest/nle_runtime_owner_map_audit_20260628/nle_runtime_owner_map_audit.json`
  - Jammini route probe: `.agents/sentinel/handoffs/20260628-105700-watchdog-handoff-probe.md`
  - Jammini scout: `.agents/sentinel/handoffs/20260628-105800-nle-next-safe-slice-scout.md`
- 수정 요약:
  - Added `tools/audit_nle_runtime_owner_map.py`.
  - Added `tests/test_nle_runtime_owner_map_audit.py`.
  - The audit checks 23 release/commit owners across 11 NLE operation families and reports blocked candidates for persisted NLE project fields, per-pixel NLE writes, and QML/GPU timeline default surfaces.
  - No runtime editor behavior, STT/STT2, subtitle timing, UI/UX, save-file format, persisted NLE disk fields, packaging, signing, upload, notarization, App Store Connect, or DMG behavior changed.
- 실제 감사 결과:
  - `runtime_owner_map_ready=true`.
  - `runtime_change_applied=false`.
  - `covered_owner_count=23`, `missing_owner_count=0`.
  - Operation families: `candidate_confirm`, `caption_delete`, `caption_merge`, `caption_move`, `caption_range_replace`, `caption_resize`, `caption_split`, `caption_text_edit`, `gap_delete`, `gap_generate`, `marker_edit`.
  - Next adoption gate requires fresh owner-map plus Taption release-commit/no-per-pixel-write/final-overlap/global-canvas/save-reopen proof.
- 검증:
  - `./venv/bin/python -m py_compile tools/audit_nle_runtime_owner_map.py tests/test_nle_runtime_owner_map_audit.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_nle_runtime_owner_map_audit.py` -> `3 passed`.
  - `./venv/bin/python tools/audit_nle_runtime_owner_map.py --output-dir output/manual_verification/latest/nle_runtime_owner_map_audit_20260628` -> pass.

## STT Cache Tail-Bound Fix And Real-Media Backfill Acceptance - 2026-06-28 KST

- 실행 모드: NAS HeyDealer first-180s representative real-media collect-cache write/hit replay after benchmark-window projection repair.
- 결과: strict acceptance passed for both write and hit; collect-cache production defaults remain `false/false` pending explicit owner review.
- 저장 위치:
  - Evidence root: `output/manual_verification/latest/stt_cache_tail_bound_fix_20260628_1048/`
  - Preflight: `output/manual_verification/latest/stt_cache_tail_bound_fix_20260628_1048/preflight/reference_fixture_availability.md`
  - Write benchmark: `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_105017/benchmark_results.json`
  - Hit benchmark: `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_105119/benchmark_results.json`
  - Write acceptance: `output/manual_verification/latest/stt_cache_tail_bound_fix_20260628_1048/acceptance_write/reference_benchmark_acceptance.md`
  - Hit acceptance: `output/manual_verification/latest/stt_cache_tail_bound_fix_20260628_1048/acceptance_hit/reference_benchmark_acceptance.md`
  - Readiness refresh: `output/manual_verification/latest/stt_cache_tail_bound_fix_20260628_1048/readiness_refresh/stt_cache_backfill_readiness.md`
  - Jammini route probe: `.agents/sentinel/handoffs/20260628-104613-watchdog-handoff-probe.md`
  - Jammini scout: `.agents/sentinel/handoffs/20260628-104600-nle-benchmark-tail-bound-projection-scout.md`
- 수정 요약:
  - `tools/benchmark_subtitle_pipeline_variants.py` now projects final benchmark hypothesis rows into the requested benchmark window after cut-boundary alignment, matching the already clipped reference window.
  - `tests/test_benchmark_mode_profiles.py` covers tail clamp plus outside-window drop diagnostics.
  - No runtime STT/STT2 policy, word precision policy, cache default, subtitle engine timing, editor UI/UX, save/load, render/export, packaging, signing, upload, notarization, App Store Connect, or DMG behavior changed.
- 실제 결과:
  - Preflight ready `true`; reference SRT rows `615`, clipped rows `89`.
  - Write/hit elapsed `46.073s -> 1.266s`.
  - Raw/final/reference `58/56/89` on both runs.
  - Quality/text/timing `93.766/94.267/0.5808s` on both runs.
  - Final invalid/non-monotonic/overlap `0/0/0`, final last end/duration bound `180.0/180.0`, final short/long `0/0`, global max active `1`, global stable `true`.
  - Benchmark projection diagnostics: input/output `56/56`, clamped tail-end count `1`, dropped before/after/invalid `0/0/0`.
  - Hit replay STT1/STT2/word collect cache hit `true/true/true`, provider calls `false/false/false`.
  - Readiness refresh reports `real_backfill_present_owner_review_required` for STT1, STT2/word, and combined collect-cache families, with `production_default_recommendation=hold_default_off`.
- 검증:
  - `./venv/bin/python -m py_compile tools/benchmark_subtitle_pipeline_variants.py tests/test_benchmark_mode_profiles.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_benchmark_mode_profiles.py -k "benchmark_window or native_segments_summary_includes_strict_duration_bounds or stage_wall_clock_summary"` -> `3 passed, 33 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_reference_benchmark_acceptance.py tests/test_stt_cache_backfill_readiness.py` -> `10 passed`.
  - HeyDealer write benchmark with STT1/STT2/word/macro cache paths -> run `20260628_105017`, pass.
  - Same command with the same cache paths -> hit run `20260628_105119`, pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/evaluate_reference_benchmark_acceptance.py .codex_work/benchmarks/subtitle_pipeline_variants/20260628_105017/benchmark_results.json --output-dir output/manual_verification/latest/stt_cache_tail_bound_fix_20260628_1048/acceptance_write` -> `accepted=true`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/evaluate_reference_benchmark_acceptance.py .codex_work/benchmarks/subtitle_pipeline_variants/20260628_105119/benchmark_results.json --output-dir output/manual_verification/latest/stt_cache_tail_bound_fix_20260628_1048/acceptance_hit` -> `accepted=true`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_stt_cache_backfill_readiness.py --glob '.codex_work/benchmarks/subtitle_pipeline_variants/*/benchmark_results.json' --output-dir output/manual_verification/latest/stt_cache_tail_bound_fix_20260628_1048/readiness_refresh --representative-media "/Volumes/photo/.../헤이딜러_최종.MP4" --representative-reference-srt "/Volumes/photo/.../헤이딜러_최종.srt"` -> pass.

## STT Cache Real-Media Backfill Attempt - 2026-06-28 KST

- 실행 모드: NAS HeyDealer first-180s representative real-media collect-cache write/hit replay.
- 결과: cache efficiency proved, but strict acceptance blocked; collect-cache production defaults remain `false/false`.
- 저장 위치:
  - Evidence root: `output/manual_verification/latest/stt_cache_real_media_backfill_20260628_1035/`
  - Preflight: `output/manual_verification/latest/stt_cache_real_media_backfill_20260628_1035/preflight/reference_fixture_availability.md`
  - Write benchmark: `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_103556/benchmark_results.json`
  - Hit benchmark: `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_103745/benchmark_results.json`
  - Write acceptance: `output/manual_verification/latest/stt_cache_real_media_backfill_20260628_1035/acceptance_write/reference_benchmark_acceptance.md`
  - Hit acceptance: `output/manual_verification/latest/stt_cache_real_media_backfill_20260628_1035/acceptance_hit/reference_benchmark_acceptance.md`
  - Readiness refresh: `output/manual_verification/latest/stt_cache_real_media_backfill_20260628_1035/readiness_refresh/stt_cache_backfill_readiness.md`
  - Jammini route probe: `.agents/sentinel/handoffs/20260628-103424-watchdog-handoff-probe.md`
  - Jammini checklist: `.agents/sentinel/handoffs/20260628-103500-stt-cache-real-media-backfill-checklist.md`
- 실제 결과:
  - Preflight ready `true`; reference SRT rows `615`, clipped rows `89`.
  - Write/hit elapsed `62.492s -> 1.186s`.
  - Raw/final/reference `58/56/89` on both runs.
  - Quality/text/timing `93.745/94.267/0.583s` on both runs.
  - Final invalid/non-monotonic/overlap `0/0/0`, final short/long `0/0`, global max active `1`, global stable `true`.
  - Hit replay STT1/STT2/word collect cache hit `true/true/true`, provider calls `false/false/false`, collect elapsed `0.0/0.0/0.0s`.
  - Hit replay high-context keep-cache hit count `2`, high-context LLM calls `0`.
- Strict acceptance:
  - Write and hit acceptance both `accepted=false`.
  - Rejection reason: `final_last_end_beyond_duration_bound`.
  - Final last end / duration bound: `180.256/180.0`, max final-end slack `0.25`; failure margin `0.006s`.
  - Readiness refresh remains `production_default_recommendation=hold_default_off`; strict real-media write/hit counts remain `0/0` because failed strict acceptance is not promotion evidence.
- 검증:
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/verify_reference_fixture_availability.py --media "/Volumes/photo/.../헤이딜러_최종.MP4" --reference-srt "/Volumes/photo/.../헤이딜러_최종.srt" --start-sec 0 --duration-sec 180 --output-dir output/manual_verification/latest/stt_cache_real_media_backfill_20260628_1035/preflight` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/benchmark_subtitle_pipeline_variants.py --suite modes --variants mode_high ...` with STT1/STT2/word/macro cache paths -> write run `20260628_103556`, pass.
  - Same command with same cache paths -> hit run `20260628_103745`, pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/evaluate_reference_benchmark_acceptance.py .codex_work/benchmarks/subtitle_pipeline_variants/20260628_103556/benchmark_results.json --output-dir output/manual_verification/latest/stt_cache_real_media_backfill_20260628_1035/acceptance_write` -> expected exit `2`, `accepted=false`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/evaluate_reference_benchmark_acceptance.py .codex_work/benchmarks/subtitle_pipeline_variants/20260628_103745/benchmark_results.json --output-dir output/manual_verification/latest/stt_cache_real_media_backfill_20260628_1035/acceptance_hit` -> expected exit `2`, `accepted=false`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_stt_cache_backfill_readiness.py --glob '.codex_work/benchmarks/subtitle_pipeline_variants/*/benchmark_results.json' --output-dir output/manual_verification/latest/stt_cache_real_media_backfill_20260628_1035/readiness_refresh --representative-media "/Volumes/photo/.../헤이딜러_최종.MP4" --representative-reference-srt "/Volumes/photo/.../헤이딜러_최종.srt"` -> pass, still hold.

## Active Queue Gate Refresh - 2026-06-28 KST

- 실행 모드: non-destructive active gate refresh after all parked candidates were closed.
- 결과: blocked by external prerequisites; no implementation slice remains safe without NAS media/reference SRT or owner-approved App Store submission steps.
- 저장 위치:
  - STT cache backfill refresh: `output/manual_verification/latest/stt_cache_backfill_gate_refresh_20260628/stt_cache_backfill_readiness.md`
  - App Store readiness refresh: `output/manual_verification/latest/app_store_readiness_gate_refresh_20260628/app_store_readiness_audit.md`
  - Jammini route probe: `.agents/sentinel/handoffs/20260628-093036-watchdog-handoff-probe.md`
  - Jammini blocker scout: `.agents/sentinel/handoffs/20260628-093300-active-queue-blocker-refresh.md`
- STT 실제 감사 결과:
  - `production_default_recommendation=hold_default_off`.
  - `current_real_inputs_available=false`.
  - Defaults remain `stt_primary_collect_cache_enabled=false` and `stt_recheck_collect_cache_enabled=false`.
  - STT1, STT2/word, and combined collect-cache families all remain `hold_real_media_backfill_required` with missing representative real-media cache-write and cache-hit replay.
- App Store 실제 감사 결과:
  - `status=blocked`.
  - `local_packaging_ready=true`.
  - `app_store_submission_ready=false`.
  - blocker count `14`, `submission_content_audit.status=blocked`, pending owner-input items `8/8`, drafted item count `8`.
  - Apple Distribution codesign identity and installer identity are not configured.
- 검증:
  - `find /Volumes -maxdepth 5 \( -iname '*헤이딜러*' -o -iname '*heydealer*' \) 2>/dev/null | head -40` -> no visible representative NAS HeyDealer media.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_stt_cache_backfill_readiness.py --glob '.codex_work/benchmarks/subtitle_pipeline_variants/*/benchmark_results.json' --output-dir output/manual_verification/latest/stt_cache_backfill_gate_refresh_20260628 --representative-media '/Volumes/photo/헤이딜러_최종.MP4' --representative-reference-srt '/Volumes/photo/헤이딜러_최종.srt'` -> pass, blocked/hold report written.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_app_store_readiness.py --output-dir output/manual_verification/latest/app_store_readiness_gate_refresh_20260628` -> pass, blocked readiness report written.

## Playhead Dirty-Rect Candidate Gate - 2026-06-28 KST

- 실행 모드: parked candidate fresh quality gate; no runtime repaint behavior change.
- 결과: pass; playhead-only dirty-rect runtime optimization remains held.
- 저장 위치:
  - Audit report: `output/manual_verification/latest/playhead_dirty_rect_gate_20260628/editor_rendering_ownership_audit.md`
  - Audit JSON: `output/manual_verification/latest/playhead_dirty_rect_gate_20260628/editor_rendering_ownership_audit.json`
  - Jammini route probe: `.agents/sentinel/handoffs/20260628-092519-watchdog-handoff-probe.md`
  - Jammini scout: `.agents/sentinel/handoffs/20260628-092600-nle-playhead-dirty-rect-scout.md`
- 수정 요약:
  - `tools/audit_editor_rendering_ownership.py` now emits `playhead_dirty_rect_candidate` gate data.
  - The audit CLI now supports `--output-dir` and writes JSON/Markdown evidence.
  - `tests/test_editor_rendering_ownership_audit.py` now asserts `hold_full_canvas_repaint`, `runtime_change_allowed=false`, and the required `fresh_macau_visual_smoke_no_residue` gate.
  - Removed the parked candidate from `ACTION_ITEMS.md`, archived it in `COMPLETED_ACTION_ITEMS.md`, and recorded the rejected runtime-optimization direction in `waste_action_item.md`.
  - No runtime repaint behavior, UI/UX, timeline drawing, NLE state, subtitle generation, STT/STT2, App Store readiness, packaging, signing, upload, notarization, or DMG behavior changed.
- 실제 감사 결과:
  - `ok=true`, issue count `0`.
  - `playhead_dirty_rect_candidate.status=hold_full_canvas_repaint`.
  - `runtime_change_allowed=false`.
  - `current_backend=qwidget-2d-full-canvas-repaint`.
- 검증:
  - `./venv/bin/python -m py_compile tools/audit_editor_rendering_ownership.py tests/test_editor_rendering_ownership_audit.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_editor_rendering_ownership_audit.py tests/test_timeline_playhead_fit.py -k "single_owner_playhead_invalidation or playhead_canvas_repaints_full_2d_owner or shadow_playhead_repaints_canvas_full_2d_owner"` -> `3 passed, 194 deselected`.
  - `./venv/bin/python tools/audit_editor_rendering_ownership.py --output-dir output/manual_verification/latest/playhead_dirty_rect_gate_20260628` -> pass.

## App Command/Snapshot Acknowledgement Cleanup - 2026-06-28 KST

- 실행 모드: parked candidate artifact-trust cleanup; no runtime bridge handler behavior change.
- 결과: pass; direct `appctl` output now carries stronger evidence for queued snapshot artifacts and guided-run timeout follow-up status.
- Jammini:
  - Route probe: `.agents/sentinel/handoffs/20260628-091814-watchdog-handoff-probe.md`
  - Scout: `.agents/sentinel/handoffs/20260628-091900-app-command-ack-cleanup-scout.md`
  - Dex classification: accept the artifact-trust goal, but narrow implementation to `tools/appctl.py` reporting because `tools/remote_verify.py` already validates saved capture artifacts.
- 수정 요약:
  - `tools/appctl.py` now annotates `capture-snapshot` / `snapshot` results with `data.artifact` and `data.artifact_ready`.
  - `tools/appctl.py` now annotates `guided-subtitle-run` `command_timeout` results with `post_timeout_status` and `post_timeout_evidence` while preserving the original timeout as non-ok.
  - `tests/test_appctl.py` now covers ready artifact, missing artifact, and guided-run timeout follow-up evidence.
  - Removed the parked candidate from `ACTION_ITEMS.md` and archived the completion in `COMPLETED_ACTION_ITEMS.md`.
  - No runtime bridge handler behavior, UI/UX, subtitle generation, STT/STT2, NLE state, App Store readiness, packaging, signing, upload, notarization, or DMG behavior changed.
- 검증:
  - `./venv/bin/python -m py_compile tools/appctl.py tests/test_appctl.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_appctl.py tests/test_automation_command_client.py tests/test_remote_verify_actions.py` -> `14 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_app_command_bridge.py -k "guided_subtitle_run or capture_snapshot or command_timeout"` -> `7 passed, 71 deselected`.

## Completed Action Item Archive Separation - 2026-06-28 KST

- 실행 모드: documentation-only action-item archive separation.
- 결과: pass; completed action-item history is kept in `COMPLETED_ACTION_ITEMS.md`.
- 수정 요약:
  - `NLE_Action.md` no longer carries the completed-workstream list in its current status.
  - `COMPLETED_ACTION_ITEMS.md` now includes `NLE_Action Completed Workstream Baseline`.
  - `ACTION_ITEMS.md` was reviewed and already contained only active items, open gates, rollback rules, and archive pointers, so no content move was required there.
  - No runtime behavior, UI/UX, subtitle generation, STT/STT2, word precision, save/load, render/export, packaging, signing, upload, notarization, App Store Connect state, or DMG behavior changed.
- 검증:
  - `rg -n "(?i)(^## |^### |status:|완료|completed|complete|done|archiv|moved out|removed from ACTION_ITEMS|no longer active|closed)" ACTION_ITEMS.md NLE_Action.md COMPLETED_ACTION_ITEMS.md` -> reviewed.
  - `git diff --check -- ACTION_ITEMS.md COMPLETED_ACTION_ITEMS.md NLE_Action.md docs/HANDOFF.md test_result.md` -> pass.

## Mac App Store Submission Contents Audit - 2026-06-28 KST

- 실행 모드: non-destructive App Store submission contents readiness audit; no packaging, signing, notarization, upload, tag, release, or DMG command was run.
- 결과: pass for submission content itemization; App Store submission remains blocked.
- 저장 위치:
  - Report: `output/manual_verification/latest/app_store_submission_contents_audit_20260628/app_store_readiness_audit.md`
  - JSON: `output/manual_verification/latest/app_store_submission_contents_audit_20260628/app_store_readiness_audit.json`
  - Jammini review: `.agents/sentinel/handoffs/20260628-090900-app-store-submission-contents-audit-review.md`
- 수정 요약:
  - `tools/audit_app_store_readiness.py` now emits `submission_content_audit` plus per-item `status`, `draft`, `owner_decision_required`, and `acceptance_gate` fields for privacy policy URL, App Privacy answers, export compliance, screenshots, support URL, app review notes, age rating, and release notes.
  - `docs/APP_STORE_SUBMISSION_READINESS.md` now points to the latest submission contents audit and records pending owner-input status `8/8`.
  - No runtime behavior, UI/UX, subtitle generation, STT/STT2, word precision, save/load, render/export, packaging, signing, upload, notarization, App Store Connect state, or DMG behavior changed.
- 실제 감사 결과:
  - `local_packaging_ready=true`.
  - `app_store_submission_ready=false`, `status=blocked`, blocker count `14`.
  - `submission_content_audit.status=blocked`.
  - pending owner-input items `8/8`; drafted item count `8`.
  - Mac App Store `.pkg` remains the primary submission target; Developer ID beta `.dmg` remains `opt_in_hold` and not submission evidence.
- 검증:
  - `./venv/bin/python -m py_compile tools/audit_app_store_readiness.py tests/test_app_store_readiness_audit.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_app_store_readiness_audit.py` -> `5 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_app_store_readiness.py --output-dir output/manual_verification/latest/app_store_submission_contents_audit_20260628` -> pass.
- 다음 gate:
  - Owner must provide/approve privacy policy URL, App Privacy answers, export compliance answers, screenshots, support URL, app review notes, age rating answers, and release notes before the non-code submission blocker can clear.
  - Packaging/signing/upload/notarization/DMG steps still require explicit owner approval.

## STT Cache Backfill Command Plan Gate - 2026-06-28 KST

- 실행 모드: NAS-off analysis-only readiness audit hardening for STT collect-cache real-media backfill.
- 결과: pass; production collect-cache defaults remain `hold_default_off`.
- 저장 위치:
  - Report: `output/manual_verification/latest/stt_cache_backfill_command_plan_20260628/stt_cache_backfill_readiness.md`
  - JSON: `output/manual_verification/latest/stt_cache_backfill_command_plan_20260628/stt_cache_backfill_readiness.json`
  - Jammini route probe: `.agents/sentinel/handoffs/20260628-085829-watchdog-handoff-probe.md`
  - Jammini review: `.agents/sentinel/handoffs/20260628-085900-stt-cache-backfill-readiness-plan-review.md`
- 수정 요약:
  - `tools/audit_stt_cache_backfill_readiness.py` now requires both strict real-media cache-write and cache-hit evidence before reporting owner-review readiness.
  - The readiness JSON/Markdown now includes `next_run_plan` with preflight, cache-write, cache-hit, write acceptance, hit acceptance, and readiness-refresh commands for the NAS HeyDealer first-180s gate.
  - The report now lists forbidden substitutes: generated/local fixtures, X5/project-reference fixtures, fallback cached audio without matching SRT, preflight-only proof, real-media write without matching hit replay, and profiler elapsed as speed truth.
  - No runtime behavior, STT/STT2 policy, word precision policy, cache default, subtitle timing, save/load, render/export, packaging, App Store behavior, or UI changed.
- 실제 감사 결과:
  - `run_count=739`, `real_media_run_count=288`, `generated_or_local_run_count=451`.
  - `current_real_inputs_available=false`.
  - `stt_primary_collect_cache_enabled=false`, `stt_recheck_collect_cache_enabled=false`.
  - strict real-media cache-write/cache-hit counts are `0/0` for STT1, STT2/word, and combined collect-cache families.
  - each family remains `hold_real_media_backfill_required` with blockers `representative_real_media_currently_unavailable`, `missing_strict_real_media_cache_write_run`, and `missing_strict_real_media_cache_hit_replay`.
  - generated strict cache-hit evidence remains context only and does not promote defaults.
- 검증:
  - `./venv/bin/python -m py_compile tools/audit_stt_cache_backfill_readiness.py tests/test_stt_cache_backfill_readiness.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_stt_cache_backfill_readiness.py tests/test_stage_variance_summary.py` -> `8 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_stt_cache_backfill_readiness.py --glob '.codex_work/benchmarks/subtitle_pipeline_variants/*/benchmark_results.json' --output-dir output/manual_verification/latest/stt_cache_backfill_command_plan_20260628 --representative-media '/Volumes/photo/.../헤이딜러_최종.MP4' --representative-reference-srt '/Volumes/photo/.../헤이딜러_최종.srt'` -> pass.
- 다음 gate:
  - When the NAS HeyDealer MP4 and matching SRT are mounted, run the report's `preflight`, `cache_write`, `cache_hit`, `accept_write`, `accept_hit`, and `readiness_refresh` commands in order before any owner review of collect-cache defaults.
  - Do not substitute generated fixtures, X5/project-reference fixtures, fallback cached audio, preflight-only proof, or profiler elapsed for this gate.

## Trace Log Bundle Contract And Retention - 2026-06-28 KST

- 실행 모드: source-app Trace Log Bundle contract/retention audit; no runtime editor behavior change.
- 결과: pass for Trace Log Bundle required directories, manifest/latest/events JSONL, exact-frame fps rational fields, bounded media fingerprint, trace package collection, and run-directory retention.
- 저장 위치:
  - Audit report: `output/manual_verification/latest/trace_log_bundle_retention_audit_20260628/trace_log_bundle_audit.md`
  - Audit JSON: `output/manual_verification/latest/trace_log_bundle_retention_audit_20260628/trace_log_bundle_audit.json`
  - Jammini route probe: `.agents/sentinel/handoffs/20260628-084655-watchdog-handoff-probe.md`
  - Jammini scout: `.agents/sentinel/handoffs/20260628-084700-trace-retention-next-gap-scout.md`
- 수정 요약:
  - Added `tools/audit_trace_log_bundle.py` and `tests/test_trace_log_bundle_audit.py`.
  - Added `prune_trace_run_directories(...)` and `trace_runs_workspace_dir(...)` to `core/runtime/temp_workspace.py`.
  - `TraceLogger` now prunes old trace run directories before creating a new run; the current post-start retention limit is 20 run directories.
  - No UI/UX, subtitle generation, STT/STT2, word precision, save-file format, packaging, App Store, or runtime editor behavior changed.
- 실제 감사 결과:
  - `passed=true`.
  - Required dirs created `true`; manifest missing fields `none`; event missing fields `none`.
  - Event count `4`, latest event count `1`.
  - Frame precision `true`; bounded media fingerprint `true`.
  - Package complete `true`; package event count `3`.
  - Retention `true`; retained run count `20/20`; retention removed count `5`.
  - Trace disabled `false`; trace drop counts `{}`.
- 검증:
  - `./venv/bin/python -m py_compile core/runtime/temp_workspace.py core/runtime/trace_logger.py tools/audit_trace_log_bundle.py tests/test_trace_logger.py tests/test_trace_log_bundle_audit.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_trace_logger.py tests/test_trace_log_bundle_audit.py` -> `16 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_trace_log_bundle.py --output-dir output/manual_verification/latest/trace_log_bundle_retention_audit_20260628` -> pass.

## NLE Marker Edit Persistence Gate - 2026-06-28 KST

- 실행 모드: source-app NLE persistence cutover audit strengthening; legacy `.aissproj` disk shape remains unchanged.
- 결과: pass for provisional cut-boundary `marker_edit` save/reopen coverage; persisted NLE project fields remain blocked.
- 저장 위치:
  - Audit report: `output/manual_verification/latest/nle_marker_edit_persistence_gate_20260628/nle_persistence_cutover_audit.md`
  - Audit JSON: `output/manual_verification/latest/nle_marker_edit_persistence_gate_20260628/nle_persistence_cutover_audit.json`
  - Jammini route probe: `.agents/sentinel/handoffs/20260628-083545-watchdog-handoff-probe.md`
  - Jammini scout: `.agents/sentinel/handoffs/20260628-083600-nle-next-safe-slice-scout.md`
- 수정 요약:
  - `tools/audit_nle_persistence_cutover.py` now includes `marker_edit` in the operation roundtrip matrix.
  - The audit now compares provisional cut-boundary marker signatures after legacy project reopen, not only editor subtitle rows.
  - `tests/test_nle_persistence_cutover_audit.py` now expects all 11 current NLE dual-write operation families and checks marker preservation.
  - No UI/UX, subtitle generation, STT/STT2, word precision, save-file format, packaging, App Store, or runtime editor behavior changed.
- 실제 감사 결과:
  - `prep_ready=true`, `persistence_cutover_ready=false`.
  - Operation roundtrip families `11`, all passed.
  - `marker_edit` projected/reopened marker count `1/1`, `reopened_markers_preserved=true`.
  - Render/export parity stable `true`, storage clean `true`.
  - Final invalid/non-monotonic/overlap `0/0/0`; global max active `1`.
- 검증:
  - `./venv/bin/python -m py_compile tools/audit_nle_persistence_cutover.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_nle_persistence_cutover_audit.py` -> `5 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_dual_write.py tests/test_project_nle_persistence_guard.py tests/test_project_nle_render_export_parity.py tests/test_nle_persistence_cutover_audit.py` -> `41 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_nle_persistence_cutover.py --output-dir output/manual_verification/latest/nle_marker_edit_persistence_gate_20260628` -> pass.
- 남은 gate:
  - Do not persist `nle`, `nle_snapshot`, or `_nle_project_state` to `.aissproj` until a separate compatibility gate is explicitly approved.

## NLE Persistence Render/Export Gate - 2026-06-28 KST

- 실행 모드: source-app NLE persistence cutover audit strengthening; legacy `.aissproj` disk shape remains unchanged.
- 결과: pass for the new save/render/export parity gate; persisted NLE project fields remain blocked.
- 저장 위치:
  - Audit report: `output/manual_verification/latest/nle_persistence_render_export_gate_20260628/nle_persistence_cutover_audit.md`
  - Audit JSON: `output/manual_verification/latest/nle_persistence_render_export_gate_20260628/nle_persistence_cutover_audit.json`
  - Jammini route probe: `.agents/sentinel/handoffs/20260628-082348-watchdog-handoff-probe.md`
  - Jammini scout: `.agents/sentinel/handoffs/20260628-083300-nle-persistence-next-gap-scout.md`
  - Dex closeout handoff: `.agents/sentinel/handoffs/20260628-084900-nle-persistence-render-export-gate.md`
- 수정 요약:
  - `tools/audit_nle_persistence_cutover.py` now writes and reopens a render/export fixture through legacy project I/O, then requires NLE render/export parity before reporting `prep_ready=true`.
  - `tests/test_nle_persistence_cutover_audit.py` now verifies the new `render_export_parity` check, surface list, final overlap/max-active gates, and markdown output.
  - No UI/UX, subtitle generation, STT/STT2, word precision, save-file format, packaging, App Store, or runtime editor behavior changed.
- 실제 감사 결과:
  - `prep_ready=true`, `persistence_cutover_ready=false`.
  - Operation roundtrip families `10`, all passed.
  - Render/export parity stable `true`, storage clean `true`.
  - Stable surfaces: `source_subtitles`, `final_overlay`, `global_canvas`, `roughcut_sidecar`, `exported_assets`.
  - Captions/gaps/candidates `2/1/2`; render segments/manifest/stitched `2/2/1`.
  - Final invalid/non-monotonic/overlap `0/0/0`; global max active `1`.
- 검증:
  - `./venv/bin/python -m py_compile tools/audit_nle_persistence_cutover.py tests/test_nle_persistence_cutover_audit.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_nle_persistence_cutover_audit.py tests/test_project_nle_render_export_parity.py` -> `7 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_nle_persistence_cutover.py --output-dir output/manual_verification/latest/nle_persistence_render_export_gate_20260628` -> pass.
- 남은 gate:
  - Do not persist `nle`, `nle_snapshot`, or `_nle_project_state` to `.aissproj` until a separate compatibility gate is explicitly approved.

## STT Strict Synthetic Collect-Cache Replay And Completed-Item Split - 2026-06-28 KST

- 실행 모드: NAS-off strict synthetic collect-cache write/hit replay after the tail-collapse fix.
- 결과: pass for generated-fixture evidence; production collect-cache defaults remain blocked by real-media backfill.
- 저장 위치:
  - Strict replay report: `output/manual_verification/latest/strict_synthetic_collect_cache_replay_20260628/strict_replay_report.md`
  - Write benchmark: `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_081537/benchmark_results.json`
  - Hit benchmark: `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_081711/benchmark_results.json`
  - Write acceptance: `output/manual_verification/latest/strict_synthetic_collect_cache_replay_20260628/acceptance_write/reference_benchmark_acceptance.md`
  - Hit acceptance: `output/manual_verification/latest/strict_synthetic_collect_cache_replay_20260628/acceptance_hit/reference_benchmark_acceptance.md`
  - Readiness after strict replay: `output/manual_verification/latest/stt_cache_backfill_readiness_after_strict_replay_20260628/stt_cache_backfill_readiness.md`
  - Jammini route probe: `.agents/sentinel/handoffs/20260628-081437-watchdog-handoff-probe.md`
  - Jammini prep: `.agents/sentinel/handoffs/20260628-082000-strict-synthetic-cache-replay-prep.md`
  - Dex closeout handoff: `.agents/sentinel/handoffs/20260628-084500-strict-synthetic-cache-replay.md`
- 실제 검증 결과:
  - Write run accepted: elapsed `79.948s`, raw/final/reference `54/54/54`, quality/text/timing `93.411/91.676/0.1391s`.
  - Hit run accepted: elapsed `1.131s`, raw/final/reference `54/54/54`, quality/text/timing `93.411/91.676/0.1391s`.
  - Both runs kept final invalid/non-monotonic/overlap `0/0/0`, final last end/duration bound `180.12/180.584`, final short/long segment counts `0/0`, global max active `1`, and global stable `true`.
  - Hit replay showed STT1/STT2/word collect cache hit/provider-call `true/false`, macro cache hit/write/provider groups `1/0/0`, and macro proofread elapsed `0.319095s`.
  - Readiness re-audit now reports strict generated cache-hit runs `1`, strict real-media cache-hit runs `0`, family status `hold_real_media_backfill_required`, and production recommendation `hold_default_off`.
- 완료 항목 분리:
  - The completed strict synthetic replay slice moved to `COMPLETED_ACTION_ITEMS.md`.
  - `ACTION_ITEMS.md` now keeps only the remaining representative NAS HeyDealer first-180s write plus hit replay/default-review gate for collect-cache promotion.
- 자막 품질 영향:
  - No runtime behavior, STT/STT2 policy, word precision policy, cache default, subtitle timing, save/load, render/export, packaging, App Store behavior, or UI changed.

## STT Cache Backfill Readiness Audit - 2026-06-28 KST

- 실행 모드: NAS-off analysis-only readiness audit for STT collect-cache default promotion.
- 결과: pass; production recommendation remains `hold_default_off`.
- 저장 위치:
  - Report: `output/manual_verification/latest/stt_cache_backfill_readiness_20260628/stt_cache_backfill_readiness.md`
  - JSON: `output/manual_verification/latest/stt_cache_backfill_readiness_20260628/stt_cache_backfill_readiness.json`
  - Jammini route probe: `.agents/sentinel/handoffs/20260628-080428-watchdog-handoff-probe.md`
  - Jammini support audit: `.agents/sentinel/handoffs/20260628-081500-stt-cache-readiness-support-audit.md`
- 수정 요약:
  - Added `tools/audit_stt_cache_backfill_readiness.py`.
  - Added focused tests in `tests/test_stt_cache_backfill_readiness.py`.
  - The audit reads existing `benchmark_results.json` artifacts, checks collect-cache hit/provider flags, strict final gates, real-media availability, and config defaults.
  - No runtime behavior, STT/STT2 policy, word precision policy, cache default, subtitle timing, save/load, render/export, packaging, App Store behavior, or UI changed.
- 실제 감사 결과:
  - `run_count=36`, `real_media_run_count=10`, `generated_or_local_run_count=26`.
  - `current_real_inputs_available=false`.
  - `stt_primary_collect_cache_enabled=false`, `stt_recheck_collect_cache_enabled=false`.
  - strict real-media cache-hit replay count is `0` for STT1, STT2/word, and combined collect-cache families.
  - existing generated cache-hit artifacts are classified as strict final-gate failures because they fail the duration-bound gate.
- 검증:
  - `./venv/bin/python -m py_compile tools/audit_stt_cache_backfill_readiness.py tests/test_stt_cache_backfill_readiness.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_stt_cache_backfill_readiness.py tests/test_stage_variance_summary.py` -> `7 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_stt_recheck_service.py tests/test_media_processor_overlap.py tests/test_subtitle_engine_settings.py -k "collect_cache or macro_response_cache"` -> `4 passed, 228 deselected`.
- 다음 gate:
  - Before real NAS backfill can be used for default review, refresh a tail-collapse-fixed synthetic cache write/hit pair and require strict final gates.
  - When NAS is available, run representative HeyDealer first-180s write plus cache-hit replay before any owner review of collect-cache defaults.

## NLE Shortcut Split Commit Sync And Completed-Item Split - 2026-06-28 KST

- 실행 모드: source-app NLE mutable sync at shortcut split-at-playhead release commit; no drag-time per-pixel NLE write.
- 결과: pass.
- 저장 위치:
  - Report: `output/manual_verification/latest/nle_shortcut_split_commit_sync_20260628/shortcut_split_report.md`
  - Quick QA: `output/manual_verification/latest/qa_suite_quick_nle_shortcut_split_20260628`
  - Jammini route probe: `.agents/sentinel/handoffs/20260628-075011-watchdog-handoff-probe.md`
  - Jammini remaining-source audit: `.agents/sentinel/handoffs/20260628-075500-nle-remaining-release-source-audit.md`
  - Dex closeout handoff: `.agents/sentinel/handoffs/20260628-081000-nle-shortcut-split-commit-sync.md`
- 수정 요약:
  - `_split_at_playhead_or_cut(...)` now attempts runtime NLE `caption_split` for stable final-caption playhead insert/split commits.
  - NLE operation metadata records `commit_boundary=release` and `commit_source=shortcut_split_at_playhead`.
  - Existing QTextDocument/source-app fallback remains active for selection cuts, STT/live preview rows, gap rows, unsupported rows, invalid split positions, and NLE rejection.
  - Completed NLE mutable-sync details now live in `COMPLETED_ACTION_ITEMS.md`; `ACTION_ITEMS.md` contains only remaining active work.
  - Existing UI/UX, labels, menus, shortcuts, popups, save/export behavior, subtitle generation policy, packaging, and App Store behavior are unchanged.
- 검증:
  - `./venv/bin/python -m py_compile ui/editor/ux/editor_video_controls.py tests/test_timeline_playhead_fit.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py -k "split_shortcut"` -> `2 passed, 191 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py -k "split_shortcut or smart_split or gap or magnet or reorder"` -> `25 passed, 168 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_dual_write.py -k "caption_split"` -> `2 passed, 28 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_runtime_cutover.py tests/test_timeline_render_cache.py -k "timeline_canvas or projection or final_surface or save_export"` -> `5 passed, 53 deselected`.
  - `AI_SUBTITLE_STUDIO_QA_USE_SOURCE=1 ./venv/bin/python tools/qa_suite_runner.py quick --output-dir output/manual_verification/latest/qa_suite_quick_nle_shortcut_split_20260628` -> pass, `failed_count=0`.
- 자막 품질 영향:
  - Final overlap projection stayed `0` with global max active `1` in the focused shortcut split route test.
  - STT2, word precision, LLM, LoRA, VAD, timing policy, visible UI layout, packaging, and App Store behavior were not changed.
- 완료 항목 분리:
  - `NLE Timeline Canvas State Ownership: Commit-Boundary Mutable Sync` completed status was moved out of the active queue and into `COMPLETED_ACTION_ITEMS.md`.
  - `ACTION_ITEMS.md` now starts with the remaining STT2 / word precision latency item and keeps App Store submission readiness as the second active item.

## NLE Partial Range Replace Commit Sync - 2026-06-28 KST

- 실행 모드: source-app NLE mutable sync at partial subtitle replacement commit; no drag-time per-pixel NLE write.
- 결과: pass.
- 저장 위치:
  - Report: `output/manual_verification/latest/nle_partial_range_replace_commit_sync_20260628/range_replace_report.md`
  - Persistence audit: `output/manual_verification/latest/nle_persistence_identity_preservation_range_replace_20260628/nle_persistence_cutover_audit.md`
  - Quick QA: `output/manual_verification/latest/qa_suite_quick_nle_range_replace_20260628`
  - Jammini route probe: `.agents/sentinel/handoffs/20260628-073020-watchdog-handoff-probe.md`
  - Jammini support audit: `.agents/sentinel/handoffs/20260628-062800-nle-range-replace-audit.md`
- 수정 요약:
  - Added `caption_range_replace` to the NLE operation model and persistence audit matrix.
  - `clear_segments_in_range(...)` / `insert_partial_segments(...)` now attempts runtime NLE range replacement after the source-app edit commits final rows.
  - The NLE route preserves rows outside the target range, assigns unique identities to inserted rows, rejects STT/live preview or unsupported rows, and reloads projected rows only when safe.
  - Existing QTextDocument/source-app fallback remains active for NLE rejection or unsupported states.
  - Existing UI/UX, labels, menus, shortcuts, popups, save/export behavior, subtitle generation policy, packaging, and App Store behavior are unchanged.
- 검증:
  - `./venv/bin/python -m py_compile core/project/nle_operations.py core/project/nle_dual_write.py ui/editor/ux/editor_timeline_video.py ui/editor/editor_segments_manual_edits.py tests/test_project_nle_dual_write.py tests/test_timeline_playhead_fit.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_dual_write.py tests/test_project_nle_operations.py tests/test_nle_persistence_cutover_audit.py` -> `39 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py -k "partial_insert or gap or magnet or reorder"` -> `25 passed, 166 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_hit_targets.py tests/test_project_segment_reload.py -k "gap or magnet or reorder or caption_range_replace or identity or reload"` -> `125 passed, 116 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_runtime_cutover.py tests/test_timeline_render_cache.py -k "timeline_canvas or projection or final_surface or save_export"` -> `5 passed, 53 deselected`.
  - `./venv/bin/python tools/audit_nle_persistence_cutover.py --output-dir output/manual_verification/latest/nle_persistence_identity_preservation_range_replace_20260628` -> pass; `operation_roundtrip_family_count=10`, `operation_roundtrip_all_passed=true`.
  - `AI_SUBTITLE_STUDIO_QA_USE_SOURCE=1 ./venv/bin/python tools/qa_suite_runner.py quick --output-dir output/manual_verification/latest/qa_suite_quick_nle_range_replace_20260628` -> pass, `failed_count=0`.
- 자막 품질 영향:
  - Final overlap stayed `0` and global max active stayed `1` in focused NLE route/audit checks.
  - Save/reopen operation identity was preserved for all 10 then-current NLE dual-write operation families.
  - STT2, word precision, LLM, LoRA, VAD, timing policy, visible UI layout, packaging, and App Store behavior were not changed.
- 완료 항목 분리:
  - Completed slice summary moved to `COMPLETED_ACTION_ITEMS.md`.
  - `ACTION_ITEMS.md` keeps the NLE item active only for future uncovered release/commit sources, gates, and rollback.

## NLE Quality Review Text Commit Sync - 2026-06-28 KST

- 실행 모드: source-app NLE mutable sync at quality-review candidate / one-click subtitle text commits; no drag-time per-pixel NLE write.
- 결과: pass.
- 저장 위치:
  - Report: `output/manual_verification/latest/nle_quality_review_text_commit_sync_20260628/quality_text_commit_report.md`
  - Quick QA: `output/manual_verification/latest/qa_suite_quick_nle_quality_text_commit_20260628`
  - Jammini route probe: `.agents/sentinel/handoffs/20260628-071837-watchdog-handoff-probe.md`
  - Jammini fresh audit scout: `.agents/sentinel/handoffs/20260628-062700-nle-final-exclusions-audit.md`
- 수정 요약:
  - `_replace_segment_text_by_line(...)` now attempts runtime NLE `caption_text_edit` for stable final-caption quality candidate / one-click text replacements.
  - NLE operation metadata records `commit_boundary=release` and `commit_source=quality_candidate_text`.
  - Quality-review metadata is restored after NLE projection reload, preserving `candidate_applied`, `manual_confirmed`, candidate reason, and quality candidates.
  - Unchanged text, STT/live preview rows, unsupported rows, and NLE rejection keep the existing QTextDocument fallback path.
  - Existing UI/UX, labels, menus, shortcuts, popups, save/export behavior, subtitle generation policy, packaging, and App Store behavior are unchanged.
- 검증:
  - `./venv/bin/python -m py_compile ui/editor/editor_quality_review.py tests/test_timeline_playhead_fit.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py -k "quality_candidate_text_commit"` -> `2 passed, 187 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py -k "quality_candidate_text_commit or replace_text_in_all_subtitles or manual_confirmed or inline_text"` -> `6 passed, 183 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_dual_write.py -k "caption_text_edit"` -> `2 passed, 26 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_hit_targets.py tests/test_timeline_playhead_fit.py -k "gap or magnet or reorder"` -> `58 passed, 284 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_runtime_cutover.py tests/test_timeline_render_cache.py -k "timeline_canvas or projection or final_surface or save_export"` -> `5 passed, 53 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_segment_reload.py -k "caption_text_edit or identity or reload"` -> `88 passed`.
  - `git diff --check -- .` -> pass.
  - `AI_SUBTITLE_STUDIO_QA_USE_SOURCE=1 ./venv/bin/python tools/qa_suite_runner.py quick --output-dir output/manual_verification/latest/qa_suite_quick_nle_quality_text_commit_20260628` -> pass, `failed_count=0`.
- 자막 품질 영향:
  - Final overlap projection stayed `0` with global max active `1` in the focused NLE quality text route test.
  - STT2, word precision, LLM, LoRA, VAD, timing policy, visible UI layout, packaging, and App Store behavior were not changed.
- 남은 위험:
  - This checkpoint predates the later `caption_range_replace` slice; the current active queue no longer treats partial range replacement as deferred.
  - Persisted NLE project fields remain gated.

## NLE Popup Replace-All Commit Sync - 2026-06-28 KST

- 실행 모드: source-app NLE mutable sync at popup replace-all subtitle text commit; no drag-time per-pixel NLE write.
- 결과: pass.
- 저장 위치:
  - Report: `output/manual_verification/latest/nle_popup_replace_all_commit_sync_20260628/popup_replace_all_report.md`
  - Quick QA: `output/manual_verification/latest/qa_suite_quick_nle_popup_replace_all_20260628`
  - Jammini route probe: `.agents/sentinel/handoffs/20260628-070530-watchdog-handoff-probe.md`
  - Jammini fresh audit scout: `.agents/sentinel/handoffs/20260628-062600-nle-remaining-fresh-audit.md`
- 수정 요약:
  - `_replace_text_in_all_subtitles(...)` now attempts sequential runtime NLE `caption_text_edit` operations for safe final-caption popup replace-all commits.
  - NLE operation metadata records `commit_boundary=release` and `commit_source=popup_replace_all`.
  - Visible gap text, STT/live preview rows, unsupported row sets, and NLE rejection keep the existing QTextDocument fallback path.
  - Existing UI/UX, labels, menus, shortcuts, popups, save/export behavior, subtitle generation policy, packaging, and App Store behavior are unchanged.
- 검증:
  - `./venv/bin/python -m py_compile ui/editor/editor_segments_text_ops.py tests/test_timeline_playhead_fit.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py -k "replace_text_in_all_subtitles"` -> `3 passed, 184 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_segment_reload.py -k "replace_text_in_all_subtitles"` -> `1 passed, 87 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py tests/test_project_segment_reload.py -k "replace_text_in_all_subtitles or inline_text or text_edit or change_speaker_for_line"` -> `12 passed, 263 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_dual_write.py -k "caption_text_edit"` -> `2 passed, 26 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_hit_targets.py tests/test_timeline_playhead_fit.py -k "gap or magnet or center_reorder or center_drag or reorder"` -> `66 passed, 274 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_runtime_cutover.py -k "timeline_canvas or final_surface or global_canvas or save_export"` -> `7 passed, 3 deselected`.
  - `AI_SUBTITLE_STUDIO_QA_USE_SOURCE=1 ./venv/bin/python tools/qa_suite_runner.py quick --output-dir output/manual_verification/latest/qa_suite_quick_nle_popup_replace_all_20260628` -> pass, `failed_count=0`.
- 자막 품질 영향:
  - Final overlap projection stayed `0` with global max active `1` in the focused NLE replace-all route test.
  - STT2, word precision, LLM, LoRA, VAD, timing policy, visible UI layout, packaging, and App Store behavior were not changed.
- 남은 위험:
  - Fresh audit still needs to continue for any remaining safe release/commit source.
  - Persisted NLE project fields remain gated.

## NLE Shortcut Resize Commit Sync - 2026-06-28 KST

- 실행 모드: source-app NLE mutable sync at shortcut start/end-to-playhead release commits; no drag-time per-pixel NLE write.
- 결과: pass.
- 저장 위치:
  - Report: `output/manual_verification/latest/nle_shortcut_resize_commit_sync_20260628/shortcut_resize_report.md`
  - Quick QA: `output/manual_verification/latest/qa_suite_quick_nle_shortcut_resize_20260628`
  - Jammini route probe: `.agents/sentinel/handoffs/20260628-065025-watchdog-handoff-probe.md`
  - Jammini guard scout: `.agents/sentinel/handoffs/20260628-062500-nle-shortcut-resize-guard-scout.md`
- 수정 요약:
  - `_set_segment_start_to_playhead` / `_set_segment_end_to_playhead` now attempt runtime NLE `caption_resize` for safe single-block explicit-gap absorption shapes.
  - NLE operation metadata keeps `edge=square_left` / `square_right` and records shortcut provenance as `commit_source=shortcut_start_to_playhead` or `shortcut_end_to_playhead`.
  - Legacy QTextBlock fallback remains active when a new gap must be created, a gap must be extended, NLE rejects the row, or the row is STT/live-preview/unsupported.
  - Existing UI/UX, labels, menus, shortcuts, popups, save/export behavior, subtitle generation policy, packaging, and App Store behavior are unchanged.
- 검증:
  - `./venv/bin/python -m py_compile ui/editor/editor_segments_block_surgery.py tests/test_timeline_playhead_fit.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py -k "segment_start_shortcut or segment_end_shortcut or shortcut"` -> `6 passed, 178 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_dual_write.py -k "caption_resize"` -> `4 passed, 24 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_hit_targets.py tests/test_timeline_playhead_fit.py -k "gap or magnet or center_reorder or center_drag or reorder"` -> `65 passed, 272 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_runtime_cutover.py -k "timeline_canvas or final_surface or global_canvas or save_export"` -> `7 passed, 3 deselected`.
  - `AI_SUBTITLE_STUDIO_QA_USE_SOURCE=1 ./venv/bin/python tools/qa_suite_runner.py quick --output-dir output/manual_verification/latest/qa_suite_quick_nle_shortcut_resize_20260628` -> pass, `failed_count=0`.
- 자막 품질 영향:
  - Final overlap projection stayed `0` with global max active `1` in the focused shortcut route tests.
  - STT2, word precision, LLM, LoRA, VAD, timing policy, visible UI layout, packaging, and App Store behavior were not changed.
- 남은 위험:
  - No named uncovered release/commit candidate is currently promoted. Next step is a fresh audit for remaining safe release/commit sources.
  - Persisted NLE project fields remain gated.

## NLE Provisional Cut Boundary Marker Edit - 2026-06-28 KST

- 실행 모드: source-app NLE mutable sync at provisional cut-boundary create/delete release commits; no drag-time per-pixel NLE write.
- 결과: pass.
- 저장 위치:
  - Report: `output/manual_verification/latest/nle_provisional_cut_boundary_marker_edit_20260628/marker_edit_report.md`
  - Jammini route probe: `.agents/sentinel/handoffs/20260628-063735-watchdog-handoff-probe.md`
  - Jammini next-slice scout: `.agents/sentinel/handoffs/20260628-061300-nle-next-slice-recommendation.md`
- 수정 요약:
  - `apply_marker_edit_dual_write_pilot(...)` records runtime NLE `marker_edit` operations for provisional cut-boundary create/delete.
  - `_on_provisional_cut_boundary_requested(...)` records `action=create` after the existing scan-boundary row commit.
  - `_on_provisional_cut_boundary_delete_requested(...)` records `action=delete` after the existing scan-boundary row removal.
  - Existing UI/UX, right-click behavior, scan-boundary rows, and info-label text are unchanged.
- 검증:
  - `./venv/bin/python -m py_compile core/project/nle_dual_write.py ui/editor/editor_scan_cut_core.py tests/test_project_nle_dual_write.py tests/test_timeline_hit_targets.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_dual_write.py -k "marker_edit or gap_delete"` -> `5 passed, 23 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_hit_targets.py -k "scan_boundary_create_records_nle_marker_edit_operation or scan_boundary_delete_removes_requested_boundary_from_editor_state"` -> `2 passed, 151 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_operations.py tests/test_project_nle_dual_write.py` -> `33 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_hit_targets.py -k "scan_boundary or provisional_cut_boundary or playhead_auto_cut_magnet or gap_generate"` -> `24 passed, 129 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_hit_targets.py tests/test_timeline_playhead_fit.py -k "gap or magnet or center_reorder or center_drag or reorder"` -> `62 passed, 271 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_runtime_cutover.py -k "timeline_canvas or final_surface or global_canvas or save_export"` -> `7 passed, 3 deselected`.
  - `AI_SUBTITLE_STUDIO_QA_USE_SOURCE=1 ./venv/bin/python tools/qa_suite_runner.py quick --output-dir output/manual_verification/latest/qa_suite_quick_nle_marker_edit_20260628` -> pass, `failed_count=0`.
- 자막 품질 영향:
  - Final caption text/timing, STT2, word precision, LLM, LoRA, VAD, cut-boundary detection policy, save/export final surfaces, packaging, and App Store behavior were not changed.
- 남은 위험:
  - `_set_segment_start_to_playhead` / `_set_segment_end_to_playhead` remains the next named uncovered release/commit candidate and needs a separate QTextBlock-shape guard before NLE `caption_resize` sync is accepted.

## NLE Speaker Change Commit Sync - 2026-06-28 KST

- 실행 모드: source-app NLE mutable sync at direct speaker menu change release commit; no drag-time per-pixel NLE write.
- 결과: pass.
- 저장 위치:
  - Report: `output/manual_verification/latest/nle_speaker_change_commit_sync_20260628/speaker_change_sync_report.md`
  - Quick QA: `output/manual_verification/latest/qa_suite_quick_nle_speaker_change_commit_20260628`
  - Jammini route probe: `.agents/sentinel/handoffs/20260628-062324-watchdog-handoff-probe.md`
  - Jammini guard scout: `.agents/sentinel/handoffs/20260628-062400-nle-speaker-change-guard-scout.md`
- 수정 요약:
  - Direct speaker menu changes now attempt NLE `caption_text_edit` on single-block stable final captions.
  - The NLE operation records `commit_boundary=release` and `commit_source=timeline_speaker_change`.
  - Text and timing stay unchanged; only `speaker` / `speaker_list` metadata changes.
  - Multi-block captions keep the existing QTextDocument path to preserve visible QTextBlock shape.
  - NLE rejection keeps the existing rehighlight/finalize fallback path.
- 검증:
  - `./venv/bin/python -m py_compile ui/editor/editor_speaker_ops.py tests/test_timeline_playhead_fit.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py -k "change_speaker_for_line or speaker_circle_drop or speaker_split"` -> `10 passed, 170 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_dual_write.py -k "caption_text_edit"` -> `2 passed, 24 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py tests/test_timeline_hit_targets.py -k "speaker or drag or gap or magnet or center_reorder or center_drag or diamond"` -> `115 passed, 217 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_dual_write.py tests/test_project_nle_runtime_cutover.py -k "caption_text_edit or timeline_canvas or final_surface or global_canvas"` -> `6 passed, 30 deselected`.
  - `AI_SUBTITLE_STUDIO_QA_USE_SOURCE=1 ./venv/bin/python tools/qa_suite_runner.py quick --output-dir output/manual_verification/latest/qa_suite_quick_nle_speaker_change_commit_20260628` -> pass, `failed_count=0`.
  - `git diff --check -- .` -> pass.
- 자막 품질 영향:
  - Final text, start/end timing, frame bounds, overlap count, STT2, word precision, LLM, LoRA, VAD, visible UI layout, packaging, and App Store behavior were not changed.
- 남은 위험:
  - Remaining NLE timeline mutable-sync work is now a fresh audit problem; no currently named `_change_speaker_for_line` follow-up remains.
  - Persisted NLE project fields remain gated.

## NLE Smart Split Commit Sync - 2026-06-28 KST

- 실행 모드: source-app NLE mutable sync at timeline smart split release commit; no drag-time per-pixel NLE write.
- 결과: pass.
- 저장 위치:
  - Report: `output/manual_verification/latest/nle_smart_split_commit_sync_20260628/smart_split_sync_report.md`
  - Quick QA: `output/manual_verification/latest/qa_suite_quick_nle_smart_split_commit_20260628`
  - Jammini route probe: `.agents/sentinel/handoffs/20260628-061052-watchdog-handoff-probe.md`
  - Jammini retry scout: `.agents/sentinel/handoffs/20260628-061200-nle-speaker-change-scout.md`
- 수정 요약:
  - Timeline smart split now attempts NLE `caption_split` for stable final captions before mutating the QTextDocument.
  - The NLE operation records `commit_boundary=release` and `commit_source=timeline_smart_split`.
  - New-left and new-right smart split flows preserve the existing Taption/source-app visible result and final row timing.
  - NLE rejection keeps the existing QTextDocument fallback path.
- 검증:
  - `./venv/bin/python -m py_compile core/project/nle_dual_write.py ui/editor/ux/editor_timeline_video.py ui/editor/ux/editor_timeline_gap_split.py tests/test_timeline_playhead_fit.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py -k "smart_split or caption_split"` -> `2 passed, 175 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py tests/test_timeline_hit_targets.py -k "smart_split or split or drag or gap or magnet or center_reorder or center_drag or diamond"` -> `113 passed, 216 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_dual_write.py tests/test_project_nle_runtime_cutover.py -k "caption_split or caption_text_edit or timeline_canvas or final_surface or global_canvas"` -> `8 passed, 28 deselected`.
  - `AI_SUBTITLE_STUDIO_QA_USE_SOURCE=1 ./venv/bin/python tools/qa_suite_runner.py quick --output-dir output/manual_verification/latest/qa_suite_quick_nle_smart_split_commit_20260628` -> pass, `failed_count=0`.
  - `git diff --check -- .` -> pass.
- 자막 품질 영향:
  - Final split rows keep shared-boundary timing with final overlap `0` and max active `1` in the NLE projection.
  - STT2, word precision, LLM, LoRA, VAD, timing policy, visible UI layout, packaging, and App Store behavior were not changed.
- 남은 위험:
  - `_change_speaker_for_line` remains an uncovered release/commit candidate and needs a separate QTextBlock/UI-shape guard before NLE sync is safe.
  - Persisted NLE project fields remain gated.

## NLE Speaker Drop Commit Sync - 2026-06-28 KST

- 실행 모드: source-app NLE mutable sync at same-caption speaker-circle drag/drop release commit; no drag-time per-pixel NLE write.
- 결과: pass.
- 저장 위치:
  - Report: `output/manual_verification/latest/nle_speaker_drop_commit_sync_20260628/speaker_drop_sync_report.md`
  - Quick QA: `output/manual_verification/latest/qa_suite_quick_nle_speaker_drop_commit_20260628`
  - Jammini scout: `.agents/sentinel/handoffs/20260628-060000-nle-remaining-release-source-scout.md`
- 수정 요약:
  - Same-caption speaker-circle drag/drop now attempts NLE `caption_text_edit` with `commit_boundary=release` and `commit_source=timeline_speaker_drop`.
  - The NLE path preserves ordered `speaker_list` and final caption timing while keeping one final multi-speaker row.
  - Distinct-caption speaker drops do not route through NLE because that would be a broader row-order operation with different UI-shape risk.
  - NLE rejection keeps the existing QTextDocument fallback path.
- 검증:
  - `./venv/bin/python -m py_compile ui/editor/editor_speaker_ops.py tests/test_timeline_playhead_fit.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py -k "speaker_circle_drop or speaker_split"` -> `7 passed, 168 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py tests/test_timeline_hit_targets.py -k "speaker or drag or gap or magnet or center_reorder or center_drag or diamond"` -> `112 passed, 215 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_dual_write.py tests/test_project_nle_runtime_cutover.py -k "caption_text_edit or timeline_canvas or final_surface or global_canvas"` -> `6 passed, 30 deselected`.
  - `AI_SUBTITLE_STUDIO_QA_USE_SOURCE=1 ./venv/bin/python tools/qa_suite_runner.py quick --output-dir output/manual_verification/latest/qa_suite_quick_nle_speaker_drop_commit_20260628` -> pass, `failed_count=0`.
- 자막 품질 영향:
  - Final timing and frame bounds are unchanged for same-caption speaker-line reorder.
  - STT2, word precision, LLM, LoRA, VAD, timing policy, save format, visible UI layout, packaging, and App Store behavior were not changed.
- 남은 위험:
  - `_change_speaker_for_line` and `_on_smart_split` remain uncovered release/commit candidates.
  - Persisted NLE project fields remain gated.

## NLE Diamond Delete Commit Sync - 2026-06-28 KST

- 실행 모드: source-app NLE mutable sync at diamond drag delete release commit; no drag-time per-pixel NLE write.
- 결과: pass.
- 저장 위치:
  - Report: `output/manual_verification/latest/nle_diamond_delete_commit_sync_20260628/diamond_delete_sync_report.md`
  - Quick QA: `output/manual_verification/latest/qa_suite_quick_nle_diamond_delete_commit_20260628`
  - Jammini scout: `.agents/sentinel/handoffs/20260628-054900-nle-diamond-delete-scout.md`
- 수정 요약:
  - Diamond delete now builds the source-app final row set before QTextDocument mutation and attempts NLE `caption_move` commit adoption.
  - NLE operation metadata records `commit_boundary=release`, `commit_source=diamond_delete`, and keep-left/keep-right `commit_mode`.
  - Keep-left and keep-right delete-plus-resize are validated as one final NLE projection with final overlap `0`.
  - Line-mismatch resolution still uses the existing Taption/source-app canvas/document mapping.
  - STT/live preview rows and NLE rejection keep the existing QTextDocument fallback path.
- 검증:
  - `./venv/bin/python -m py_compile ui/editor/ux/editor_timeline_segment_merge.py ui/editor/ux/editor_timeline_video.py tests/test_timeline_playhead_fit.py tests/test_project_nle_dual_write.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py -k "diamond_delete"` -> `7 passed, 165 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py -k "diamond or merge or delete or center_drag or center_reorder"` -> `35 passed, 137 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_dual_write.py -k "caption_move or caption_delete or caption_resize"` -> `12 passed, 13 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_dual_write.py -k "diamond_delete or caption_move_commit"` -> `3 passed, 23 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py -k "diamond or magnet"` -> `22 passed, 150 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_hit_targets.py tests/test_timeline_playhead_fit.py -k "diamond_delete or diamond or merge or delete or drag or gap or magnet or center_reorder or center_drag"` -> `114 passed, 210 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_dual_write.py` -> `26 passed`.
  - `git diff --check -- .` -> pass.
  - `AI_SUBTITLE_STUDIO_QA_USE_SOURCE=1 ./venv/bin/python tools/qa_suite_runner.py quick --output-dir output/manual_verification/latest/qa_suite_quick_nle_diamond_delete_commit_20260628` -> pass, `failed_count=0`.
- 자막 품질 영향:
  - Diamond delete no longer depends on a separate NLE delete plus resize sequence; it adopts the already-computed final rows atomically.
  - STT2, word precision, LLM, LoRA, VAD, timing policy, save format, visible UI layout, packaging, and App Store behavior were not changed.
- 남은 위험:
  - Remaining uncovered release/commit sources still need audit before claiming full mutable timeline ownership.
  - Persisted NLE project fields remain gated.

## NLE Speaker Split Text Commit Sync - 2026-06-28 KST

- 실행 모드: source-app NLE mutable sync at speaker split release commit; no drag-time per-pixel NLE write.
- 결과: pass.
- 저장 위치:
  - Report: `output/manual_verification/latest/nle_speaker_split_text_commit_sync_20260628/speaker_split_sync_report.md`
  - Quick QA: `output/manual_verification/latest/qa_suite_quick_nle_speaker_split_commit_20260628`
  - Jammini scout: `.agents/sentinel/handoffs/20260628-053800-nle-speaker-split-scout.md`
- 수정 요약:
  - Extended NLE `caption_text_edit` dual-write to optionally preserve `speaker` and `speaker_list`.
  - Added a live editor NLE text-edit helper for stable final-caption commit paths.
  - `split_speaker_segment_with_text(...)` now attempts NLE `caption_text_edit` with `commit_boundary=release` and `commit_source=timeline_speaker_split`.
  - The visible editor result remains two dashed dialogue blocks, while the final segment model remains one multi-speaker row with `speaker_list`.
  - STT/live preview rows and NLE rejection keep the existing QTextDocument fallback path.
- 검증:
  - `./venv/bin/python -m py_compile core/project/nle_dual_write.py ui/editor/ux/editor_timeline_video.py ui/editor/editor_segments_manual_edits.py tests/test_project_nle_dual_write.py tests/test_timeline_playhead_fit.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_dual_write.py -k "caption_text_edit"` -> `2 passed, 23 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py -k "speaker_split"` -> `4 passed, 165 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_hit_targets.py tests/test_timeline_playhead_fit.py -k "speaker_split or inline_text_commit or caption_split or drag or gap or magnet or center_reorder or center_drag"` -> `86 passed, 235 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py -k "split or speaker or timing"` -> `10 passed, 159 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_dual_write.py` -> `25 passed`.
  - `git diff --check -- .` -> pass.
  - `AI_SUBTITLE_STUDIO_QA_USE_SOURCE=1 ./venv/bin/python tools/qa_suite_runner.py quick --output-dir output/manual_verification/latest/qa_suite_quick_nle_speaker_split_commit_20260628` -> pass, `failed_count=0`.
- 자막 품질 영향:
  - Speaker split no longer creates two final subtitle rows at the same time in the NLE path; it preserves one final multi-speaker row.
  - STT2, word precision, LLM, LoRA, VAD, timing policy, save format, visible UI layout, packaging, and App Store behavior were not changed.
- 남은 위험:
  - Diamond drag delete remains a separate uncovered release source because it is delete-plus-resize and needs an atomic NLE operation slice.
  - Persisted NLE project fields remain gated.

## NLE Persistence Identity Matrix Refresh - 2026-06-28 KST

- 실행 모드: source-app NLE persistence identity audit refresh after `caption_text_edit`; no disk-format cutover.
- 결과: pass for audit/prep; blocked for persisted NLE format cutover.
- 저장 위치:
  - Report: `output/manual_verification/latest/nle_persistence_identity_preservation_inline_text_20260628/nle_persistence_cutover_audit.md`
  - JSON: `output/manual_verification/latest/nle_persistence_identity_preservation_inline_text_20260628/nle_persistence_cutover_audit.json`
- 수정 요약:
  - Extended `tools/audit_nle_persistence_cutover.py` so the operation roundtrip matrix includes `caption_text_edit`.
  - Updated the persistence cutover audit test to expect all 9 then-current NLE dual-write operation families.
  - Kept completed action-item history in `COMPLETED_ACTION_ITEMS.md`; `ACTION_ITEMS.md` remains active work, current gates, and rollback only.
- 검증:
  - `./venv/bin/python -m py_compile tools/audit_nle_persistence_cutover.py tests/test_nle_persistence_cutover_audit.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_nle_persistence_cutover_audit.py` -> `4 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_nle_persistence_cutover.py --output-dir output/manual_verification/latest/nle_persistence_identity_preservation_inline_text_20260628` -> pass; `operation_roundtrip_family_count=9`, `operation_roundtrip_all_passed=true`.
- 핵심 결과:
  - All 9 then-current NLE dual-write operation families reopen with `reopened_identity_preserved=true`.
  - `caption_text_edit` reports `reopened_matches_projected=true`, `reopened_identity_preserved=true`, final overlap `0`, and max active `1`.
  - Disk storage still stays clean of unapproved top-level `nle`, `nle_snapshot`, and `_nle_project_state` fields.

## NLE Inline Text Commit Sync - 2026-06-28 KST

- 실행 모드: source-app NLE mutable sync at timeline inline text commit release; no drag-time per-pixel NLE write.
- 결과: pass.
- 저장 위치:
  - Report: `output/manual_verification/latest/nle_inline_text_commit_sync_20260628/inline_text_commit_report.md`
  - Quick QA: `output/manual_verification/latest/qa_suite_quick_nle_inline_text_commit_20260628`
  - Jammini scout: `.agents/sentinel/handoffs/20260628-051400-nle-inline-text-commit-scout.md`
- 수정 요약:
  - Added NLE operation kind `caption_text_edit`.
  - Added `apply_caption_text_edit_dual_write_pilot(...)` with final projection stability and save/reopen text roundtrip coverage.
  - Timeline inline editor commits now attempt NLE `caption_text_edit` with `commit_boundary=release` and `commit_source=timeline_inline_text`.
  - STT pending/live preview rows and NLE rejection keep the existing source-app fallback path.
- 검증:
  - `./venv/bin/python -m py_compile core/project/nle_operations.py core/project/nle_dual_write.py ui/editor/ux/timeline_canvas_editing.py tests/test_project_nle_dual_write.py tests/test_timeline_hit_targets.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_operations.py tests/test_project_nle_dual_write.py` -> `29 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_hit_targets.py -k "inline_text_commit or inline_editor_speaker_split or new_subtitle_placeholder"` -> `4 passed, 148 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_hit_targets.py tests/test_timeline_playhead_fit.py -k "inline_text_commit or inline_editor_speaker_split or new_subtitle_placeholder or line_text_edit or drag or gap or magnet or center_reorder or center_drag"` -> `85 passed, 234 deselected`.
  - `AI_SUBTITLE_STUDIO_QA_USE_SOURCE=1 ./venv/bin/python tools/qa_suite_runner.py quick --output-dir output/manual_verification/latest/qa_suite_quick_nle_inline_text_commit_20260628` -> pass, `failed_count=0`.
- 자막 품질 영향:
  - Timing/frame bounds remain unchanged; only final-caption text changes are adopted into NLE state.
  - Empty inline text still uses the existing gap conversion path.
  - STT2, word precision, LLM, LoRA, VAD, timing policy, save format, visible UI layout, packaging, and App Store behavior were not changed.
- 남은 위험:
  - Remaining uncovered release/commit sources still need audit before claiming full timeline mutable ownership. Persisted NLE project fields remain gated.

## NLE Complex Center Commit Sync - 2026-06-28 KST

- 실행 모드: source-app NLE mutable sync at Taption-style complex body `center` release; no drag-time per-pixel NLE write.
- 결과: pass.
- 저장 위치:
  - Report: `output/manual_verification/latest/nle_complex_center_commit_sync_20260628/complex_center_sync_report.md`
  - Quick QA: `output/manual_verification/latest/qa_suite_quick_nle_complex_center_commit_20260628`
  - Jammini scout: `.agents/sentinel/handoffs/20260628-050000-nle-complex-center-move-scout.md`
- 수정 요약:
  - Added `apply_caption_move_commit_dual_write_pilot(...)` to adopt an already-computed Taption/source-app center commit result as runtime NLE `caption_move`.
  - Live editor complex body `center` release commits now route explicit silence gap absorption as `commit_mode=center_gap_absorb`.
  - Previous/next overwrite trim now routes as `commit_mode=center_overwrite_trim`.
  - STT pending/live preview rows remain rejected for this NLE route, and NLE rejection falls back to the existing Taption/source-app document edit path.
- 검증:
  - `./venv/bin/python -m py_compile core/project/nle_dual_write.py ui/editor/ux/editor_timeline_video.py tests/test_project_nle_dual_write.py tests/test_timeline_playhead_fit.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_dual_write.py -k "caption_move"` -> `6 passed, 17 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py -k "center_drag or center_reorder"` -> `9 passed, 158 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_dual_write.py tests/test_project_nle_runtime_cutover.py tests/test_timeline_render_cache.py` -> `81 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py tests/test_timeline_hit_targets.py tests/test_app_command_bridge.py -k "drag or gap or magnet or stt_candidate or nle"` -> `94 passed, 301 deselected`.
  - `AI_SUBTITLE_STUDIO_QA_USE_SOURCE=1 ./venv/bin/python tools/qa_suite_runner.py quick --output-dir output/manual_verification/latest/qa_suite_quick_nle_complex_center_commit_20260628` -> pass, `failed_count=0`.
- 자막 품질 영향:
  - Final subtitle projection remains `overlap_count=0` and global max active `1` in the new live editor coverage.
  - STT2, word precision, LLM, LoRA, VAD, timing policy, save format, visible UI layout, packaging, and App Store behavior were not changed.
- 남은 위험:
  - Remaining uncovered release/commit sources still need audit before claiming full timeline mutable ownership. Persisted NLE project fields remain gated.

## NLE Center Move Commit Sync - 2026-06-28 KST

- 실행 모드: source-app NLE mutable sync at safe pure body `center` move release only; no drag-time per-pixel NLE write.
- 결과: pass.
- 저장 위치:
  - Report: `output/manual_verification/latest/nle_center_move_commit_sync_20260628/center_move_sync_report.md`
  - Quick QA: `output/manual_verification/latest/qa_suite_quick_nle_center_move_commit_20260628`
  - Jammini scout: `.agents/sentinel/handoffs/20260628-044700-nle-center-body-move-sync-scout.md`
- 수정 요약:
  - Live editor `center` release commits now attempt NLE `caption_move` only when the moved final caption stays between its existing previous/next final captions and does not overlap a final caption or explicit silence gap.
  - Pure center shift records `caption_move`, `commit_boundary=release`, `commit_source=center`, and `taption_reorder=false`.
  - At this earlier slice boundary, explicit gap absorption and previous/next overwrite trim still used the Taption/source-app timing path. They are superseded by the newer `NLE Complex Center Commit Sync - 2026-06-28 KST` section above.
- 검증:
  - `./venv/bin/python -m py_compile core/project/nle_dual_write.py ui/editor/ux/editor_timeline_video.py tests/test_project_nle_dual_write.py tests/test_timeline_playhead_fit.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_dual_write.py -k "caption_move"` -> `4 passed, 17 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py -k "center_drag or center_reorder"` -> `7 passed, 158 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py -k "center_reorder or center_drag or diamond or gap or magnet"` -> `34 passed, 131 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_hit_targets.py tests/test_app_command_bridge.py -k "drag or gap or magnet or stt_candidate or save_project_command"` -> `66 passed, 162 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_snapshot.py tests/test_project_nle_persistence_guard.py tests/test_nle_persistence_cutover_audit.py tests/test_project_nle_dual_write.py tests/test_project_nle_runtime_cutover.py tests/test_project_nle_render_export_parity.py -k "nle or persistence or candidate_confirm or caption_split or caption_merge or caption_move or gap_generate or save_export or final_overlay or timeline_canvas or overlap"` -> `56 passed, 4 subtests passed`.
  - `AI_SUBTITLE_STUDIO_QA_USE_SOURCE=1 ./venv/bin/python tools/qa_suite_runner.py quick --output-dir output/manual_verification/latest/qa_suite_quick_nle_center_move_commit_20260628` -> pass, `failed_count=0`.
- 자막 품질 영향:
  - Positive ownership/provenance guard only. Final subtitle projection remains `overlap_count=0` and global max active `1` in the new live editor coverage.
  - STT2, word precision, LLM, LoRA, VAD, timing policy, save format, visible UI layout, packaging, and App Store behavior were not changed.
- 남은 위험:
  - Superseded by `NLE Complex Center Commit Sync - 2026-06-28 KST` for complex center overwrite/trim and gap absorption. Persisted NLE project fields remain gated.

## NLE Commit-Boundary Reorder Sync - 2026-06-28 KST

- 실행 모드: source-app NLE mutable sync at Taption immediate-neighbor center-reorder release only; no drag-time per-pixel NLE write.
- 결과: pass.
- 저장 위치:
  - Report: `output/manual_verification/latest/nle_commit_boundary_reorder_sync_20260628/reorder_sync_report.md`
  - Quick QA: `output/manual_verification/latest/qa_suite_quick_nle_commit_boundary_reorder_20260628`
  - Jammini scout: `.agents/sentinel/handoffs/20260628-043700-nle-center-reorder-sync-test-scout.md`
- 수정 요약:
  - `apply_caption_move_dual_write_pilot(...)` now records optional `commit_boundary` and `commit_source` metadata in the operation and undo UI state.
  - Live editor `center_reorder_left` / `center_reorder_right` release commits now attempt NLE `caption_move` dual-write before reloading projected rows.
  - If NLE move projection rejects or cannot resolve a supported final-caption shape, the existing Taption/source-app reorder fallback remains unchanged.
  - Both right and left immediate-neighbor reorder paths are covered.
- 검증:
  - `./venv/bin/python -m py_compile core/project/nle_dual_write.py ui/editor/ux/editor_timeline_video.py tests/test_project_nle_dual_write.py tests/test_timeline_playhead_fit.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_dual_write.py -k "caption_move"` -> `4 passed, 17 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py -k "center_reorder"` -> `3 passed, 161 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py -k "center_reorder or center_drag or diamond or gap or magnet"` -> `33 passed, 131 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_hit_targets.py tests/test_app_command_bridge.py -k "drag or gap or magnet or stt_candidate or save_project_command"` -> `66 passed, 162 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_snapshot.py tests/test_project_nle_persistence_guard.py tests/test_nle_persistence_cutover_audit.py tests/test_project_nle_dual_write.py tests/test_project_nle_runtime_cutover.py tests/test_project_nle_render_export_parity.py -k "nle or persistence or candidate_confirm or caption_split or caption_merge or caption_move or gap_generate or save_export or final_overlay or timeline_canvas or overlap"` -> `55 passed, 4 subtests passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_dual_write.py` -> `20 passed`.
  - `AI_SUBTITLE_STUDIO_QA_USE_SOURCE=1 ./venv/bin/python tools/qa_suite_runner.py quick --output-dir output/manual_verification/latest/qa_suite_quick_nle_commit_boundary_reorder_20260628` -> pass, `failed_count=0`.
- 자막 품질 영향:
  - Positive ownership/provenance guard only. Final subtitle projection remains `overlap_count=0` and global max active `1` in the new live editor coverage.
  - STT2, word precision, LLM, LoRA, VAD, timing policy, save format, visible UI layout, packaging, and App Store behavior were not changed.
- 남은 위험:
  - Normal body `center` move and any remaining commit sources still need separate commit-boundary NLE sync slices. Persisted NLE project fields remain gated.

## NLE Timeline Canvas Projection Cutover - 2026-06-28 KST

- 실행 모드: source-app NLE runtime projection for the main timeline canvas read path; no drag-time mutable write.
- 결과: pass.
- 저장 위치:
  - Report: `output/manual_verification/latest/nle_timeline_canvas_projection_cutover_20260628/timeline_canvas_projection_report.md`
  - Quick QA: `output/manual_verification/latest/qa_suite_quick_nle_timeline_canvas_projection_20260628`
  - Jammini scout: `.agents/sentinel/handoffs/20260628-042200-nle-timeline-canvas-state-scout.md`
- 수정 요약:
  - Added `nle_timeline_canvas_segments_from_editor_rows(...)` to project final caption rows through NLE caption state for the `timeline_canvas` surface.
  - `TimelineCanvas.update_segments(...)` now uses that projection before building `self.segments`, gap rows, render caches, and hit-test indexes.
  - STT1/STT2/live subtitle preview rows remain visible on the main timeline canvas as editor/diagnostic lanes.
  - Explicit silence gaps remain gap rows and still flow through the existing canvas gap rebuild logic.
  - Global canvas still receives its separate final-only NLE projection.
- 검증:
  - `./venv/bin/python -m py_compile core/project/nle_runtime_cutover.py ui/timeline/timeline_canvas.py tests/test_project_nle_runtime_cutover.py tests/test_timeline_playhead_fit.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_runtime_cutover.py` -> `10 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py -k "project_final_only_rows_to_global_canvas or global_canvas or stt_candidate"` -> `8 passed, 154 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_render_cache.py -k "update_segments_invalidates_render_cache or visible_segment_lane_cache or stt_candidate or gap_cache"` -> `6 passed, 42 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_hit_targets.py tests/test_app_command_bridge.py -k "drag or gap or magnet or stt_candidate or save_project_command"` -> `66 passed, 162 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_snapshot.py tests/test_project_nle_persistence_guard.py tests/test_nle_persistence_cutover_audit.py tests/test_project_nle_dual_write.py tests/test_project_nle_runtime_cutover.py tests/test_project_nle_render_export_parity.py -k "nle or persistence or candidate_confirm or caption_split or caption_merge or gap_generate or save_export or final_overlay or timeline_canvas or overlap"` -> `55 passed, 4 subtests passed`.
  - `AI_SUBTITLE_STUDIO_QA_USE_SOURCE=1 ./venv/bin/python tools/qa_suite_runner.py quick --output-dir output/manual_verification/latest/qa_suite_quick_nle_timeline_canvas_projection_20260628` -> pass, `failed_count=0`, `editor_compact_macau: ok`.
- 자막 품질 영향:
  - Positive guard/read-path only. Final caption rows on the main timeline canvas now share the NLE final-surface no-overlap projection policy.
  - STT2, word precision, LLM, LoRA, VAD, timing policy, model selection, save format, render/export behavior, UI layout, packaging, release, commit, and push behavior were not changed.
- 남은 위험:
  - This is not full drag-time mutable NLE ownership. Commit/release-boundary mutable sync remains active in `ACTION_ITEMS.md`.
  - Per-pixel drag movement must not write NLE mutable state.

## NLE Operation Identity Preservation - 2026-06-28 KST

- 실행 모드: source-app runtime NLE dual-write identity preservation; no disk-format cutover.
- 결과: pass.
- 저장 위치:
  - Report: `output/manual_verification/latest/nle_persistence_identity_preservation_20260628/nle_persistence_cutover_audit.md`
  - JSON: `output/manual_verification/latest/nle_persistence_identity_preservation_20260628/nle_persistence_cutover_audit.json`
- 수정 요약:
  - `build_editor_state(...)` gained an opt-in `preserve_segment_identity` flag; default remains `false`, so general legacy import/canonicalization still emits `subtitle_vector_*` IDs as before.
  - NLE dual-write shadow projection enables the flag so generated operation identities such as gap-generated captions, split children, and merge survivors persist through save/reopen.
  - `candidate_confirm` canonicalizes generic confirmed-row IDs such as `caption_1` / `caption_2` back to the existing `subtitle_vector_*` identity when rows overlap existing final captions.
  - Live editor `SubtitleBlockData` now carries `segment_id` through bulk load, queue flush, runtime cache, current-state serialization, and undo metadata so NLE operation identities survive document reload/edit cycles.
  - Explicit automation `save-project` now flushes pending editor segment queues, passes the current editor rows into project save, and invalidates stale deferred project-save snapshots so pre-merge rows cannot be saved after a diamond merge.
- 검증:
  - `./venv/bin/python -m py_compile ui/main/app_command_bridge_handlers.py ui/project/project_panel.py ui/editor/editor_save_manager.py tests/test_app_command_bridge.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_app_command_bridge.py -k "save_project_command"` -> `3 passed, 75 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_context.py -k "save_project_externalize or save_project_persists_editor or build_editor_state"` -> `7 passed, 79 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_dual_write.py tests/test_nle_persistence_cutover_audit.py tests/test_project_context.py -k "identity or nle or build_editor_state or subtitle_canvas or vector"` -> `30 passed, 80 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_segment_reload.py tests/test_timeline_playhead_fit.py tests/test_editor_split_undo.py -k "caption_split or caption_merge or candidate_confirm or gap_generate or undo or nle"` -> `17 passed, 236 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_snapshot.py tests/test_project_nle_persistence_guard.py tests/test_nle_persistence_cutover_audit.py tests/test_project_nle_dual_write.py tests/test_project_nle_runtime_cutover.py tests/test_project_nle_render_export_parity.py -k "nle or persistence or candidate_confirm or caption_split or caption_merge or gap_generate or save_export or final_overlay or overlap"` -> `53 passed, 4 subtests passed`.
  - `./venv/bin/python tools/audit_nle_persistence_cutover.py --output-dir output/manual_verification/latest/nle_persistence_identity_preservation_20260628` -> pass; the then-current 8 operation families report `reopened_identity_preserved=true`.
  - `AI_SUBTITLE_STUDIO_QA_USE_SOURCE=1 ./venv/bin/python tools/qa_suite_runner.py quick --output-dir output/manual_verification/latest/qa_suite_quick_nle_identity_save_project_fix_20260628` -> pass, `failed_count=0`, `editor_compact_macau: ok`.
- 자막 품질 영향:
  - None intended. This changes runtime/project identity preservation and explicit project-save row ownership only. STT2, word precision, LLM, LoRA, VAD, timing policy, final overlap gates, visible UI/UX, and persisted NLE disk fields were not changed.
- 남은 위험:
  - Persisted top-level `nle`, `nle_snapshot`, or `_nle_project_state` fields remain blocked until a separate owner-approved compatibility gate exists.

## NLE Persistence Cutover Audit - 2026-06-28 KST

- 실행 모드: source-app NLE persistence cutover readiness audit; no disk-format cutover.
- 결과: pass for audit/prep; blocked for persisted NLE format cutover.
- 저장 위치:
  - Report: `output/manual_verification/latest/nle_persistence_cutover_audit_20260628/nle_persistence_cutover_audit.md`
  - JSON: `output/manual_verification/latest/nle_persistence_cutover_audit_20260628/nle_persistence_cutover_audit.json`
  - Roundtrip fixture: `output/manual_verification/latest/nle_persistence_cutover_audit_20260628/roundtrip_fixture/nle-persistence-cutover-audit.aissproj`
- 수정 요약:
  - Added `tools/audit_nle_persistence_cutover.py`.
  - Added `tests/test_nle_persistence_cutover_audit.py`.
  - The audit writes a temp project fixture, verifies runtime `NLEProjectState` hydration, confirms disk storage stays clean of `nle`, `nle_snapshot`, `_nle_project_state`, and quarantine runtime keys, and records future-payload quarantine behavior.
  - Extended the audit to run the then-current eight NLE dual-write operation families through save/reopen roundtrip while keeping the legacy disk shape unchanged.
  - The operation matrix separates semantic row roundtrip from ID preservation, exposing legacy ID renumbering where it still exists without approving persisted NLE fields.
- 검증:
  - `./venv/bin/python -m py_compile tools/audit_nle_persistence_cutover.py tests/test_nle_persistence_cutover_audit.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_nle_persistence_cutover_audit.py` -> `4 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_nle_persistence_cutover.py --output-dir output/manual_verification/latest/nle_persistence_cutover_audit_20260628` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_persistence_guard.py tests/test_nle_persistence_cutover_audit.py tests/test_project_nle_dual_write.py -k "persistence or cutover or dual_write or gap_delete or caption_move or caption_resize or caption_split or caption_merge or caption_delete or candidate_confirm"` -> `28 passed`.
- 핵심 결과:
  - `prep_ready=true`.
  - `persistence_cutover_ready=false`.
  - Historical operation roundtrip families at this checkpoint: `8`; operation roundtrip all passed: `true`.
  - ID preserved: `true` for `gap_delete`, `caption_move`, `caption_resize`, `caption_delete`; `false` for `gap_generate`, `caption_split`, `caption_merge`, `candidate_confirm` under the legacy disk projection.
  - Blockers: `persisted_nle_project_fields_not_approved`, `legacy_disk_shape_required_for_compatibility`, `owner_approval_required_before_disk_format_change`.
- 자막 품질 영향:
  - None. This touched audit tooling/tests/docs only and did not change STT, LLM, VAD, timing, UI, save format, render/export behavior, or App Store packaging.
- 남은 위험:
  - Persisting top-level `nle`, `nle_snapshot`, or `_nle_project_state` remains blocked until a separate owner-approved compatibility gate exists.

## NLE Final Surface Overlap Guard - 2026-06-28 KST

- 실행 모드: source-app runtime NLE final-surface projection guard.
- 결과: pass.
- 저장 위치:
  - Report: `output/manual_verification/latest/nle_final_surface_overlap_guard_20260628/final_surface_overlap_guard_report.md`
  - Jammini review: `.agents/sentinel/handoffs/20260628-033000-next-safe-action-review.md`
- 수정 요약:
  - `core/project/nle_runtime_cutover.py` now repairs one-frame final-surface micro-overlap to a shared boundary when the current caption still keeps at least one frame.
  - Final overlay/global-canvas projections drop unfixable overlapped final rows rather than drawing two active final subtitles together.
  - Save/export projection rejects unfixable final overlap with `nle_save_export_final_overlap` instead of writing an overlapped final SRT.
- 검증:
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m py_compile core/project/nle_runtime_cutover.py tests/test_project_nle_runtime_cutover.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_runtime_cutover.py` -> `8 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_editor_video_context_window.py tests/test_project_assets.py -k "nle_runtime_projection or final_overlay or save_export or externalize_project_text_assets_routes_final_srt"` -> `2 passed, 12 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_runtime_cutover.py tests/test_project_nle_render_export_parity.py tests/test_project_nle_persistence_guard.py tests/test_project_nle_dual_write.py tests/test_project_nle_operations.py tests/test_project_nle_snapshot.py` -> `54 passed, 4 subtests passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py tests/test_subtitle_live_editor_feed_facade.py -k "overlap or final_overlay or global_canvas or save_export or nle"` -> `21 passed, 144 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_native_subtitle_segments.py tests/test_native_subtitle_stt_segments.py` -> `7 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_assets.py -k "externalize_project_text_assets or nle_save_export"` -> `3 passed, 3 deselected`.
- 자막 품질 영향:
  - Positive guard only. Final subtitle surfaces now have a stricter no-overlap contract at projection time.
  - STT2, word precision, LLM, LoRA, VAD, timing policy, model selection, persisted save format, packaging, and UI layout were not changed.
- 남은 위험:
  - Persisted NLE project fields remain gated; this is not a disk-format cutover.

## Mac App Store Submission Target Lock - 2026-06-28 KST

- 실행 모드: non-destructive App Store submission readiness target lock; no packaging, signing, notarization, upload, release, or DMG build.
- 결과: pass for static audit/tooling; blocked for real App Store submission until owner-approved signing/package/validation artifacts exist.
- 저장 위치:
  - Audit report: `output/manual_verification/latest/app_store_readiness_target_lock_20260628/app_store_readiness_audit.md`
  - Audit JSON: `output/manual_verification/latest/app_store_readiness_target_lock_20260628/app_store_readiness_audit.json`
  - Jammini review: `.agents/sentinel/handoffs/20260628-031000-app-store-readiness-next-step-review.md`
- 수정 요약:
  - `tools/audit_app_store_readiness.py` now reports `submission_target=mac_app_store_pkg`.
  - The audit separates the Mac App Store `.pkg` track from the Developer ID beta `.dmg` track and marks DMG as non-submission evidence.
  - `docs/APP_STORE_SUBMISSION_READINESS.md` and `packaging/macos/README.md` now document the track boundary and non-code metadata checklist.
- 검증:
  - `./venv/bin/python -m py_compile tools/audit_app_store_readiness.py tests/test_app_store_readiness_audit.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_app_store_readiness_audit.py` -> `4 passed`.
  - `./venv/bin/python tools/audit_app_store_readiness.py --output-dir output/manual_verification/latest/app_store_readiness_target_lock_20260628` -> pass.
- 핵심 결과:
  - `local_packaging_ready=true`, `app_store_submission_ready=false`, `status=blocked`, blocker count `14`.
  - `mac_app_store_pkg` status is `blocked`; `developer_id_beta_dmg` status is `opt_in_hold`.
- 자막 품질 영향:
  - None. This touched readiness audit/docs only and did not change generation, STT2, word precision, LLM, LoRA, VAD, timing, UI, save/load, render/export, or cache defaults.
- 남은 위험:
  - Signed `.app`, signed `.pkg`, sandbox smoke, App Store Connect validation, and owner-provided metadata are still missing.

## STT Latency Stage Variance Analysis - 2026-06-28 KST

- 실행 모드: NAS-off analysis-only generation latency evidence; no runtime behavior change.
- 결과: pass for analysis tooling and focused tests; hold for algorithm/default changes until real-media backfill.
- 저장 위치:
  - Report: `output/manual_verification/latest/stt_latency_stage_variance_20260628/stage_variance_summary.md`
  - JSON: `output/manual_verification/latest/stt_latency_stage_variance_20260628/stage_variance_summary.json`
  - Jammini review: `.agents/sentinel/handoffs/20260628-025200-stt-latency-nas-off-variance-review.md`
- 수정 요약:
  - Added `tools/summarize_stage_variance.py`, an analysis-only CLI for existing `benchmark_results.json` artifacts.
  - The tool summarizes elapsed variance, stage totals, cache hit/provider-call flags, memory-pressure distribution, final overlap/global-canvas gates, and duration-bound failures.
  - Added `tests/test_stage_variance_summary.py`.
- 검증:
  - `./venv/bin/python -m py_compile tools/summarize_stage_variance.py tests/test_stage_variance_summary.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_stage_variance_summary.py` -> `3 passed`.
  - Generated the variance report from 10 existing generated/cache benchmark artifacts.
- 핵심 결과:
  - Elapsed avg/min/max/range: `41.66/1.312/82.433/81.121s`.
  - Stage ranges: STT1 `20.134950s`, STT2 `15.939524s`, word precision `20.271760s`, subtitle postprocess `30.410655s`.
  - Worst memory-pressure counts: `unknown=4`, `normal=4`, `critical=2`.
  - Invalid/non-monotonic/overlap/global max-active gates stayed pass across the selected artifacts, while old generated tail-collapse runs are still marked as duration-bound failures.
- 자막 품질 영향:
  - None. This reads existing artifacts only and does not change STT2, word precision, LLM, LoRA, VAD, timing, save/load, render/export, UI, or cache defaults.
- 남은 위험:
  - This is generated/synthetic and artifact-only evidence. It does not approve production speed claims or default cache enablement without NAS HeyDealer or another representative owner fixture.

## NLE Live Editor Candidate Confirm Cutover - 2026-06-28 02:55 KST

- 실행 모드: source-app NLE runtime editing adoption, live editor STT1/STT2 candidate confirmation.
- 결과: pass.
- 저장 위치:
  - Report: `output/manual_verification/latest/nle_live_editor_candidate_confirm_cutover_20260628/candidate_confirm_cutover_report.md`
  - Quick QA: `output/manual_verification/latest/qa_suite_quick_nle_candidate_confirm_20260628`
- 수정 요약:
  - Added `apply_candidate_confirm_dual_write_pilot(...)` to route STT1/STT2 candidate confirmation through runtime `NLEProjectState`, record a `candidate_confirm` `NLEEditorOperation`, and preserve candidate-lane evidence in the undo snapshot.
  - `select_stt_candidate_as_subtitle(...)` now attempts NLE `candidate_confirm` only after the existing Taption/source-app placement logic computes confirmed final rows.
  - The live route accepts NLE projection only when projected rows preserve the confirmed source-app rows within `0.001s`; otherwise it falls back to the existing Taption/source-app path.
  - Accepted Jammini/서린 review checkpoint for STT/live-preview isolation, final overlap gates, fallback preservation, and undo/focus evidence.
- 검증:
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m py_compile core/project/nle_dual_write.py ui/editor/editor_segments_stt_selection_flow.py tests/test_project_nle_dual_write.py tests/test_project_segment_reload.py tests/test_timeline_hit_targets.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_dual_write.py -k "candidate_confirm"` -> `2 passed, 18 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_segment_reload.py -k "select_stt_candidate"` -> `15 passed, 73 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_hit_targets.py -k "stt_candidate"` -> `6 passed, 144 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_dual_write.py tests/test_project_nle_operations.py tests/test_project_nle_snapshot.py tests/test_project_nle_persistence_guard.py tests/test_project_nle_runtime_cutover.py tests/test_project_nle_render_export_parity.py -k "candidate_confirm or caption_split or caption_merge or caption_delete or gap_generate or caption_resize or caption_move or nle_operation or runtime_nle or final_overlay or save_export"` -> `29 passed, 21 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_native_subtitle_stt_segments.py tests/test_project_segment_reload.py -k "stt_candidate or selected_source or select_stt_candidate"` -> `17 passed, 74 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py tests/test_subtitle_live_editor_feed_facade.py -k "candidate or stt or feed or preview or final_overlay or overlap"` -> `12 passed, 153 deselected`.
  - `AI_SUBTITLE_STUDIO_QA_USE_SOURCE=1 QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/qa_suite_runner.py quick --output-dir output/manual_verification/latest/qa_suite_quick_nle_candidate_confirm_20260628` -> pass, `failed_count=0`.
- 자막 품질 영향:
  - None. This only routes an existing editor candidate-confirm mutation through runtime NLE dual-write while preserving legacy fallback and final overlap gates.
  - STT2, word precision, LLM, LoRA, VAD, timing policy, model selection, save format, packaging, release, commit, and push were not changed.
- 남은 위험:
  - Persisted NLE project fields remain gated.
  - No live manual screenshot/video proof was captured for this slice; coverage is offscreen PyQt, domain tests, focused feed tests, and source-app quick QA.

## NLE Live Editor Caption Split Cutover - 2026-06-28 02:20 KST

- 실행 모드: source-app NLE runtime editing adoption, live editor text/smart caption split.
- 결과: pass.
- 저장 위치:
  - Report: `output/manual_verification/latest/nle_live_editor_caption_split_cutover_20260628/caption_split_cutover_report.md`
- 수정 요약:
  - Added `apply_caption_split_dual_write_pilot(...)` to route final subtitle split through runtime `NLEProjectState`, record a `caption_split` `NLEEditorOperation`, and project back into legacy `editor_state`.
  - `split_segment_with_text(...)` now attempts NLE `caption_split` for stable final captions and reloads projected rows through `_reload_segments_from_list(..., preserve_view=True, mark_dirty=True)`.
  - STT/live-preview rows, NLE rejection, missing caption identity, unsupported timeline shape, or invalid rows keep the existing Taption/source-app QTextDocument split fallback path.
  - Snapshot undo routing now supports content-signature matching for NLE reload edits, preventing delayed Qt document revision changes from sending split undo into QTextEdit's internal undo stack.
  - Delegated and accepted a bounded Jammini/서린 review for STT/live-preview isolation, final overlap gates, Taption fallback preservation, and undo/focus evidence gaps.
- 검증:
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m py_compile core/project/nle_dual_write.py ui/editor/ux/editor_timeline_video.py ui/editor/editor_segments_manual_edits.py ui/editor/editor_multiclip_context.py tests/test_project_nle_dual_write.py tests/test_editor_split_undo.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_dual_write.py -k "caption_split"` -> `2 passed, 16 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_editor_split_undo.py` -> `3 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_dual_write.py` -> `18 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_operations.py tests/test_project_nle_snapshot.py tests/test_project_nle_persistence_guard.py tests/test_project_nle_runtime_cutover.py tests/test_project_nle_render_export_parity.py -k "caption_split or caption_merge or caption_delete or gap_generate or caption_resize or caption_move or nle_operation or runtime_nle or final_overlay or save_export"` -> `11 passed, 19 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_app_command_bridge.py -k "smart_split or inline_cursor or commit_inline_edit"` -> `7 passed, 69 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_hit_targets.py -k "split or gap_generate_undo_routes_to_snapshot_before_textedit_undo"` -> `8 passed, 142 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py -k "split or gap or merge"` -> `20 passed, 142 deselected`.
  - `AI_SUBTITLE_STUDIO_QA_USE_SOURCE=1 QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/qa_suite_runner.py quick --output-dir output/manual_verification/latest/qa_suite_quick_nle_caption_split_20260628` -> pass, `failed_count=0`.
- 자막 품질 영향:
  - None. This only routes an existing Taption-style split mutation through runtime NLE dual-write while preserving legacy fallback and final overlap gates.
  - STT2, word precision, LLM, LoRA, VAD, timing policy, model selection, save format, packaging, release, commit, and push were not changed.
- 남은 위험:
  - Persisted NLE project fields remain gated.
  - No live manual screenshot/video proof was captured for this slice; coverage is offscreen PyQt and domain tests.

## Taption Jammini Communication Pack Adoption - 2026-06-28 KST

- 실행 모드: Taption `docs/agent_communication` review and AI Subtitle Studio documentation adoption.
- 결과: pass.
- 저장 위치:
  - Report: `output/manual_verification/latest/taption_jammini_pack_adoption_20260628/jammini_pack_adoption_report.md`
- 수정 요약:
  - Added AI Subtitle Studio-specific 한결/서린/유진 role cards under `.agents/sentinel/agents/`.
  - Added `docs/agent_communication/README.md` to map Taption's Jammini pack to this repo's `.agents/sentinel` and `tools/jammini_*` paths.
  - Updated `cooperation.md`, `AGENTS.md`, `docs/README.md`, and `docs/HANDOFF.md` with the Taption-derived clean-room import boundary, NLE parallel packet protocol, routing discipline, and unknown-cause debugging protocol.
- 검증:
  - Compared Taption helper scripts with this repo's adapted `tools/jammini_watchdog.sh`, `tools/jammini_delegate.sh`, and `tools/lib/jammini_conversation_resolver.py`; no script replacement needed.
  - `bash -n tools/jammini_watchdog.sh tools/jammini_delegate.sh` -> pass.
  - `tools/jammini_watchdog.sh --status` -> pass, canonical conversation `d2075935-3595-4188-baed-4ee0b45cb7a8`; no current Jammini Teamwork worker id visible.
  - `git diff --check` on touched docs/role-card files -> pass.
- 자막 품질 영향:
  - None. This was documentation and delegation-contract work only.

## NLE Live Editor Caption Merge Cutover - 2026-06-28 01:52 KST

- 실행 모드: source-app NLE runtime editing adoption, live editor diamond caption merge.
- 결과: pass.
- 저장 위치:
  - Report: `output/manual_verification/latest/nle_live_editor_caption_merge_cutover_20260628/caption_merge_cutover_report.md`
- 수정 요약:
  - Added `apply_caption_merge_dual_write_pilot(...)` to route final subtitle merge through runtime `NLEProjectState`, record a `caption_merge` `NLEEditorOperation`, and project back into legacy `editor_state`.
  - Live editor diamond merge now attempts NLE `caption_merge` when both sides are stable final captions, then reloads projected rows through `_reload_segments_from_list(..., preserve_view=True, mark_dirty=True)`.
  - STT/live-preview rows, NLE rejection, missing caption identity, unsupported timeline shape, or invalid rows keep the existing Taption/source-app QTextDocument merge fallback path.
  - Delegated bounded Jammini review for STT/live-preview isolation, final overlap gates, Taption fallback preservation, and doc/test evidence gaps.
- 검증:
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m py_compile core/project/nle_dual_write.py ui/editor/ux/editor_timeline_video.py ui/editor/ux/editor_timeline_segment_merge.py tests/test_project_nle_dual_write.py tests/test_timeline_playhead_fit.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_dual_write.py -k "caption_merge or caption_delete or gap_generate"` -> `6 passed, 10 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py -k "diamond_merge_routes_live_editor_mutation or diamond_merge_falls_back or diamond_merge_extends_left_segment or diamond_merge_resolves_timeline_row_line_to_document_block"` -> `4 passed, 158 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_dual_write.py tests/test_project_nle_operations.py tests/test_project_nle_snapshot.py tests/test_project_nle_persistence_guard.py tests/test_project_nle_runtime_cutover.py tests/test_project_nle_render_export_parity.py -k "caption_merge or caption_delete or gap_generate or caption_resize or caption_move or nle_operation or runtime_nle or final_overlay or save_export"` -> `25 passed, 21 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py tests/test_timeline_hit_targets.py -k "diamond_merge or merge_preview or resize or gap_generate or segment_delete"` -> `45 passed, 267 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py tests/test_subtitle_live_editor_feed_facade.py` -> `165 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/evaluate_reference_benchmark_acceptance.py .codex_work/benchmarks/subtitle_pipeline_variants/20260628_013224/benchmark_results.json` -> `accepted=true`.
  - `git diff --check -- core/project/nle_dual_write.py ui/editor/ux/editor_timeline_video.py ui/editor/ux/editor_timeline_segment_merge.py tests/test_project_nle_dual_write.py tests/test_timeline_playhead_fit.py` -> pass.
- 자막 품질 영향:
  - No subtitle-generation, STT2, word precision, LLM, LoRA, VAD, timing, or mode-selection behavior changed.
  - This routes an existing Taption-style adjacent-caption merge mutation through runtime NLE dual-write while preserving legacy fallback and final overlap gates.

## NLE Roughcut State Render Plan Cutover - 2026-06-28 01:42 KST

- 실행 모드: source-app internal NLE ownership adoption slice.
- 결과: pass.
- 저장 위치:
  - Report: `output/manual_verification/latest/nle_roughcut_state_render_plan_cutover_20260628/roughcut_state_render_plan_report.md`
- 수정 요약:
  - `ui/roughcut/roughcut_state.py` now builds saved roughcut candidate `outputs.render_plan` through the NLE snapshot adapter path used by roughcut export/render actions.
  - Legacy render command, concat command, segment manifest, and stitched-boundary parity are guarded by a new focused test.
- 검증:
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m py_compile ui/roughcut/roughcut_state.py tests/test_roughcut_ui_v2.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_roughcut_ui_v2.py -k "saved_candidate_render_plan_uses_nle_snapshot_adapter_with_legacy_parity or render_plan_builders_route_through_nle_snapshot_adapter_with_legacy_parity or app_command_roughcut_export_and_render_use_nle_snapshot_route"` -> `3 passed, 35 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_roughcut_v2_output_compat.py tests/test_project_nle_snapshot.py -k "nle_snapshot_render_plan_matches_legacy_concat_builder or render_plan or roughcut_exact_join or save_reload"` -> `3 passed, 16 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_runtime_cutover.py tests/test_project_nle_render_export_parity.py tests/test_project_nle_persistence_guard.py tests/test_project_nle_dual_write.py tests/test_project_nle_operations.py tests/test_project_nle_snapshot.py tests/test_roughcut_v2_output_compat.py` -> `48 passed, 4 subtests passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/evaluate_reference_benchmark_acceptance.py .codex_work/benchmarks/subtitle_pipeline_variants/20260628_013224/benchmark_results.json` -> `accepted=true`.
  - `git diff --check -- ui/roughcut/roughcut_state.py tests/test_roughcut_ui_v2.py` -> pass.
- 자막 품질 영향:
  - No subtitle-generation, STT2, word precision, LLM, LoRA, VAD, timing, or mode-selection behavior changed.
  - This only moves stored roughcut candidate render-plan construction to the NLE projection path while preserving legacy render command parity.

## Generated Video Tail Collapse Fix - 2026-06-28 01:55 KST

- 실행 모드: NAS-off generated 180s Korean fixture, source-app `mode_high` generation after VAD/STT consensus guard.
- 결과: pass.
- 저장 위치:
  - Report: `output/manual_verification/latest/generated_video_tail_collapse_fix_20260628/tail_collapse_fix_report.md`
  - Fixed acceptance: `output/manual_verification/latest/generated_video_tail_collapse_fix_20260628/reference_benchmark_acceptance.md`
  - Fixed SRT: `output/manual_verification/latest/generated_video_tail_collapse_fix_20260628/generated_final_subtitles_fixed.srt`
  - Fixed SRT validation: `output/manual_verification/latest/generated_video_tail_collapse_fix_20260628/fixed_srt_validation.json`
- 수정 요약:
  - `vad_stt_timing_consensus` no longer applies the STT1/VAD-only union path unless VAD and STT1 spans are similar.
  - This blocks broad full-file VAD spans from stretching later STT1 subtitles into tail fragments.
- 검증:
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m py_compile core/subtitle_quality/vad_alignment_checker.py tools/evaluate_reference_benchmark_acceptance.py tools/benchmark_subtitle_pipeline_variants.py tests/test_subtitle_quality_models.py tests/test_reference_benchmark_acceptance.py tests/test_benchmark_mode_profiles.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_subtitle_quality_models.py -k "vad_voice_start_priority or vad_stt_timing_consensus"` -> `10 passed, 8 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_reference_benchmark_acceptance.py tests/test_benchmark_mode_profiles.py -k "reference_benchmark_acceptance or native_segments_summary"` -> `7 passed, 33 deselected`.
  - Fixed benchmark `20260628_013224`: elapsed `44.307s`, raw/final/reference `54/54/54`, quality/text/timing `93.411/91.676/0.1391s`, final invalid/non-monotonic/overlap `0/0/0`, final last end/duration bound `180.12/180.584`, short/long `0/0`, global max active/stable `1/true`, strict acceptance `true`.
  - Fixed SRT direct parse: rows `54`, invalid/non-monotonic/overlap `0/0/0`, short/long `0/0`, beyond media duration `0`, last end `180.12s`.
- 자막 품질 영향:
  - Positive on the generated fixture: the previous 59.792s tail segment and 0.05s fragments are gone.
  - No STT model, STT2, word precision, LLM, LoRA, VAD extraction, or mode-selection policy was changed.

## Generated Video Strict Acceptance Gate - 2026-06-28 01:50 KST

- 실행 모드: strict reference benchmark acceptance gate hardening.
- 결과: pass for the gate change; the known generated-video benchmark is now correctly rejected.
- 저장 위치:
  - Acceptance report: `output/manual_verification/latest/generated_video_strict_acceptance_gate_20260628/reference_benchmark_acceptance.md`
  - Acceptance JSON: `output/manual_verification/latest/generated_video_strict_acceptance_gate_20260628/reference_benchmark_acceptance.json`
- 수정 요약:
  - `tools/evaluate_reference_benchmark_acceptance.py` now computes a media/window duration bound and rejects final `last_end` beyond that bound.
  - `tools/benchmark_subtitle_pipeline_variants.py` now records final segment min/max duration and short/long segment counts in `native_segments_summary`.
- 검증:
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m py_compile tools/evaluate_reference_benchmark_acceptance.py tools/benchmark_subtitle_pipeline_variants.py tests/test_reference_benchmark_acceptance.py tests/test_benchmark_mode_profiles.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_reference_benchmark_acceptance.py tests/test_benchmark_mode_profiles.py -k "reference_benchmark_acceptance or native_segments_summary"` -> `7 passed, 33 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/evaluate_reference_benchmark_acceptance.py .codex_work/benchmarks/subtitle_pipeline_variants/20260628_010403/benchmark_results.json --output-dir output/manual_verification/latest/generated_video_strict_acceptance_gate_20260628` -> `accepted=false`, exit code `2`, reason `final_last_end_beyond_duration_bound`.
- 자막 품질 영향:
  - No subtitle-generation, STT, LLM, LoRA, VAD, timing, or model-selection behavior changed.
  - This only hardens the proof gate so a duration-bound subtitle failure cannot be reported as accepted.

## Generated Video Strict Duration Validation - 2026-06-28 01:35 KST

- 실행 모드: NAS-off generated 180s Korean fixture, direct media/SRT duration-bound validation.
- 결과: fail under stricter verification. The legacy benchmark acceptance for the same run remains recorded separately, but it is not sufficient for production-quality proof.
- 저장 위치:
  - Strict report: `output/manual_verification/latest/generated_video_strict_duration_validation_20260628/strict_duration_report.md`
  - Strict JSON: `output/manual_verification/latest/generated_video_strict_duration_validation_20260628/strict_duration_report.json`
  - Generated final SRT: `output/manual_verification/latest/generated_video_subtitle_validation_20260628_latest/generated_final_subtitles.srt`
- 검증:
  - `ffprobe` media duration: `180.584s`.
  - Generated final SRT direct parse: rows `54`, invalid/non-monotonic/overlap `0/0/0`.
  - Strict bounds: generated last end `182.032s`, reference last end `180.583s`, rows beyond media duration `17`, short segments under `0.3s` `16`, long segments over `12.0s` `1`.
- 판정:
  - The output does not overlap internally, but it is not production-acceptable because final subtitles extend beyond the video and tail segments collapse to 0.05s rows.
  - The benchmark acceptance path must add media-duration, min-duration, and long-tail gates before generated-fixture pass claims can be trusted.

## NLE Save/Export Projection Cutover - 2026-06-28 01:20 KST

- 실행 모드: source-app internal NLE runtime adoption slice.
- 결과: pass.
- 저장 위치:
  - Report: `output/manual_verification/latest/nle_save_export_projection_cutover_20260628/save_export_projection_report.md`
- 수정 요약:
  - Added `nle_save_export_segments_from_editor_rows(...)` as the `save_export` final-caption projection surface.
  - Routed `externalize_project_text_assets(...)` final SRT/cache rows through the NLE save/export projection.
  - Kept silence/gap rows on the existing vector-canvas gap metadata path, and kept STT1/STT2 reference tracks separate from final SRT output.
- 검증:
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m py_compile core/project/nle_runtime_cutover.py core/project/project_assets.py tests/test_project_nle_runtime_cutover.py tests/test_project_assets.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_runtime_cutover.py tests/test_project_assets.py -k "save_export or externalize_project_text_assets"` -> `4 passed, 6 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_runtime_cutover.py tests/test_project_nle_render_export_parity.py tests/test_project_nle_persistence_guard.py tests/test_project_nle_dual_write.py tests/test_project_nle_operations.py tests/test_project_nle_snapshot.py` -> `44 passed, 4 subtests passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_context.py -k "externalize_project_text_assets or external_text_assets or hot_open_subtitle_segments_cache"` -> `1 passed, 84 deselected`.
- 자막 품질 영향:
  - No subtitle-generation policy, STT, LLM, LoRA, VAD, timing, or model-selection behavior changed.
  - Final SRT/cache rows now use NLE final-caption projection, while live STT/subtitle preview and candidate payloads remain out of final output.
- 남은 위험:
  - This is not persisted NLE project-field approval and not a visible NLE UI redesign. Broader save/reload/export smoke remains required before legacy cleanup.

## Generated Video Subtitle Validation - 2026-06-28 01:05 KST

- 실행 모드: NAS-off generated 180s Korean fixture, source-app `mode_high` generation on the current worktree.
- 결과: legacy benchmark gate pass, stricter duration-bound validation fail. NAS was not used.
- 저장 위치:
  - Report: `output/manual_verification/latest/generated_video_subtitle_validation_20260628_latest/validation_report.md`
  - Generated final SRT: `output/manual_verification/latest/generated_video_subtitle_validation_20260628_latest/generated_final_subtitles.srt`
  - SRT validation: `output/manual_verification/latest/generated_video_subtitle_validation_20260628_latest/generated_final_subtitles_srt_report.json`
  - Benchmark: `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_010403/benchmark_results.md`
  - Acceptance: `output/manual_verification/latest/generated_video_subtitle_validation_20260628_latest/acceptance/reference_benchmark_acceptance.md`
- 검증:
  - Generated fixture preflight -> ready, clipped reference rows `54`.
  - Benchmark `20260628_010403`: elapsed `44.968s`, raw/final/reference `54/54/54`, quality/text/timing `80.153/91.676/1.437s`, final invalid/non-monotonic/overlap `0/0/0`, final stable `true`, global max active/stable `1/true`, acceptance `true`.
  - Generated final SRT: rows `54`, invalid/non-monotonic/overlap `0/0/0`, `ready_for_review=true`.
  - Follow-up strict duration-bound report: `fail`, generated last end `182.032s` against media duration `180.584s`, rows beyond duration `17`, sub-0.3s rows `16`, long tail row `1`.
- 자막 품질 영향:
  - No subtitle-generation policy, STT2, word precision, LLM, LoRA, VAD, timing, or model-selection behavior was changed for this validation.
  - STT1/STT2/word collect caches remained default-off during the run.
- 남은 위험:
  - Generated-fixture proof only and currently not production-acceptable under strict media-bound validation.
  - Representative real-footage NAS backfill is still required before production-wide speed claims.

## Recheck Prepared Clip Reuse Candidate - 2026-06-28 01:05 KST

- 실행 모드: cache-hit prepare-time candidate review.
- 결과: rejected and reverted. No runtime code kept.
- 저장 위치:
  - Report: `output/manual_verification/latest/recheck_prepared_clip_reuse_rejected_20260628/recheck_prepared_clip_reuse_rejection_report.md`
  - Waste record: `waste_action_item.md`
- 검증:
  - Prior warmup-skip hit `20260628_005314`: elapsed `1.312s`, word prepare `0.527071s`, STT2 prepare `0.098612s`.
  - Candidate runs `20260628_010037` / `20260628_010050`: elapsed `1.149s` / `1.183s`, word prepare `0.496650s` / `0.512973s`, STT2 prepare `0.086384s` / `0.079436s`.
  - Quality stayed raw/final/reference `54/54/54`, quality/text/timing `80.153/91.676/1.437s`, final overlap `0`.
- 판정:
  - Prepare-time improvement was not material; directory retention plus metadata sidecar complexity was not accepted.

## Macro Cache Warmup Skip - 2026-06-28 00:58 KST

- 실행 모드: NAS-off generated 180s Korean fixture, `mode_high`, exact cache-hit path for STT1/STT2/word collect and macro proofread response.
- 결과: pass. NAS was off, so no real-footage backfill is claimed.
- 저장 위치:
  - Report: `output/manual_verification/latest/macro_cache_warmup_skip_20260628/macro_cache_warmup_skip_report.md`
  - Generated final SRT: `output/manual_verification/latest/macro_cache_warmup_skip_20260628/synthetic_final_warmup_skip.srt`
  - SRT validation: `output/manual_verification/latest/macro_cache_warmup_skip_20260628/synthetic_final_warmup_skip_srt_report.json`
  - Benchmark: `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_005314/benchmark_results.md`
  - Acceptance: `output/manual_verification/latest/macro_cache_warmup_skip_20260628/acceptance/reference_benchmark_acceptance.md`
- 수정 요약:
  - Added a macro response-cache preflight before local LLM worker preparation.
  - When every LLM macro candidate group has an exact response-cache hit, runtime LLM model resolution and Ollama warmup are skipped.
  - Any cache miss or uncertain preflight falls back to the existing provider preparation path.
- 검증:
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m py_compile core/engine/subtitle_macro_chunks.py core/engine/subtitle_engine.py tests/test_subtitle_engine_settings.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_subtitle_engine_settings.py -k "macro_chunk_response_cache or macro_gate_zero_llm_rows or optimize_segments_batches_llm_into_macro_chunks"` -> `3 passed, 81 deselected`.
  - Generated fixture benchmark `20260628_005314`: elapsed `1.312s`, raw/final/reference `54/54/54`, quality/text/timing `80.153/91.676/1.437s`, final invalid/non-monotonic/overlap `0/0/0`, global max active `1`, acceptance `true`.
  - Macro proofread detail `3.606041s -> 0.400186s` compared with the previous combined cache-hit run `20260628_004504`; macro hit/write/provider groups stayed `1/0/0`.
  - Generated final SRT block count `54`, invalid/non-monotonic/overlap `0/0/0`, `ready_for_review=true`.
- 자막 품질 영향:
  - No subtitle-generation policy, STT, word precision, LLM verifier, LoRA, VAD, timing, or model-selection behavior changed.
  - Replay still runs candidate-lock verification, subtitle verifier, Deep rerank, final integrity, and reference acceptance.
- 남은 위험:
  - Generated-fixture exact-repeat proof only. Keep STT collect caches disabled by default and require NAS HeyDealer or another representative owner fixture before claiming production-wide speed.

## Combined Collect Cache Generated-Fixture Subtitle Proof - 2026-06-28 00:52 KST

- 실행 모드: NAS-off generated 180s Korean fixture, `mode_high`, exact replay caches enabled together for STT1 primary collect, STT2 collect, word precision collect, and macro proofread response.
- 결과: pass. NAS was off, so no real-footage backfill is claimed.
- 저장 위치:
  - Report: `output/manual_verification/latest/combined_collect_cache_20260628/combined_collect_cache_report.md`
  - Generated final SRT: `output/manual_verification/latest/combined_collect_cache_20260628/synthetic_final_from_second_run.srt`
  - SRT validation: `output/manual_verification/latest/combined_collect_cache_20260628/synthetic_final_from_second_run_srt_report.json`
  - First benchmark: `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_004231/benchmark_results.md`
  - Second benchmark: `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_004504/benchmark_results.md`
  - First acceptance: `output/manual_verification/latest/combined_collect_cache_20260628/acceptance_first/reference_benchmark_acceptance.md`
  - Second acceptance: `output/manual_verification/latest/combined_collect_cache_20260628/acceptance_second/reference_benchmark_acceptance.md`
- 수정 요약:
  - STT1 primary collect and STT2/word collect cache keys now ignore unrelated cache enable/path/max-entry controls.
  - This prevents duplicate provider collect work when multiple exact replay caches are enabled together for the same media/settings run.
  - Defaults remain off: `stt_primary_collect_cache_enabled=false` and `stt_recheck_collect_cache_enabled=false`.
- 검증:
  - First write benchmark `20260628_004231`: elapsed `72.570s`, raw/final/reference `54/54/54`, quality/text/timing `80.153/91.676/1.437s`, final invalid/non-monotonic/overlap `0/0/0`, global max active `1`, `accepted=true`.
  - Second cache-hit benchmark `20260628_004504`: elapsed `4.449s`, same quality/text/timing/final gates, STT1/STT2/word collect `0.0s/0.0s/0.0s`, STT1/STT2/word collect hit/write/provider `true/false/false`, macro hit/write/provider groups `1/0/0`, `accepted=true`.
  - Generated final SRT: block count `54`, invalid/non-monotonic/overlap `0/0/0`, `ready_for_review=true`.
- 자막 품질 영향:
  - No subtitle-generation policy, STT2 selection, word precision selection, LLM/LoRA/VAD, timing, or model-selection behavior changed.
  - Replay still runs downstream annotation, STT2 replacement selection, word precision timing application, VAD/STT consensus, LLM/LoRA postprocess, final integrity, and scored reference acceptance.
- 남은 위험:
  - Generated-fixture exact-repeat proof only. Keep STT collect caches disabled by default until NAS HeyDealer or another representative owner fixture passes.

## STT1 Primary Collect Cache Candidate - 2026-06-28 00:35 KST

- 실행 모드: source-app generation latency candidate, opt-in exact STT1 primary collect replay cache.
- 결과: pass on owner-approved generated 180s Korean fixture; NAS was off, so no real-footage backfill is claimed.
- 저장 위치:
  - Report: `output/manual_verification/latest/stt_primary_collect_cache_20260628/primary_collect_cache_report.md`
  - Cache file: `output/manual_verification/latest/stt_primary_collect_cache_20260628/primary_collect_cache_diagnostics.json`
  - First benchmark: `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_003224/benchmark_results.md`
  - Second benchmark: `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_003326/benchmark_results.md`
  - First acceptance: `output/manual_verification/latest/stt_primary_collect_cache_20260628/acceptance_diag_first/reference_benchmark_acceptance.md`
  - Second acceptance: `output/manual_verification/latest/stt_primary_collect_cache_20260628/acceptance_diag_second/reference_benchmark_acceptance.md`
- 수정 요약:
  - Added `stt_primary_collect_cache_enabled=false` and `stt_primary_collect_cache_max_entries=64`.
  - Added an exact STT1 primary collect cache keyed by chunk audio hashes, model, language, target duration, and effective settings.
  - Cache hits are disabled when a `preview_callback` exists, preserving live STT preview events.
  - Cache-hit diagnostics preserve provider backend/model from the write run.
- 검증:
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m py_compile core/audio/media_processor_transcribe.py core/runtime/config.py tools/verify_full_media_pipeline.py tests/test_media_processor_overlap.py tests/test_verify_full_media_pipeline.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_media_processor_overlap.py -k "collect_transcribe_result"` -> `4 passed, 103 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_verify_full_media_pipeline.py -k "stage_wall_clock_rollup"` -> `1 passed, 14 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_verify_full_media_pipeline.py tests/test_benchmark_mode_profiles.py -k "stage_wall_clock or parse_setting_overrides or cli_setting_overrides"` -> `4 passed, 45 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_media_processor_overlap.py -k "collect_transcribe_result or word_precision_recheck_uses_user_selected_stt1_model or word_precision_recheck_allows_explicit_precision_model or selective or recheck"` -> `18 passed, 89 deselected`.
  - `git diff --check -- core/audio/media_processor_transcribe.py core/runtime/config.py tools/verify_full_media_pipeline.py tests/test_media_processor_overlap.py tests/test_verify_full_media_pipeline.py` -> pass.
  - First write benchmark `20260628_003224`: elapsed `51.964s`, raw/final/reference `54/54/54`, quality/text/timing `80.153/91.676/1.437s`, final invalid/non-monotonic/overlap `0/0/0`, global max active `1`, STT1 collect `17.717081s`, cache hit/write/provider `false/true/true`, `accepted=true`.
  - Second cache-hit benchmark `20260628_003326`: elapsed `37.715s`, raw/final/reference `54/54/54`, same quality/text/timing/final gates, STT1 collect `0.0s`, STT1 parent `0.049428s`, cache hit/write/provider `true/false/false`, `accepted=true`.
- 자막 품질 영향:
  - No subtitle-generation policy, STT2 selection, word precision selection, LLM/LoRA/VAD, timing, or model-selection behavior changed.
  - Cache replay still runs downstream STT2/word/postprocess/final integrity and reference acceptance.
- 남은 위험:
  - This is exact repeated-input synthetic-fixture proof only. Keep `stt_primary_collect_cache_enabled=false` until NAS HeyDealer or another representative real-media backfill passes.

## STT1 Primary Collect Diagnostics - 2026-06-28 00:17 KST

- 실행 모드: source-app generation latency diagnostics, behavior-preserving STT1 collect breakdown.
- 결과: pass.
- 저장 위치:
  - Report: `output/manual_verification/latest/stt_primary_collect_diagnostics_20260628/stt_primary_collect_report.md`
  - Benchmark: `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_001645/benchmark_results.md`
  - Acceptance: `output/manual_verification/latest/stt_primary_collect_diagnostics_20260628/acceptance/reference_benchmark_acceptance.md`
- 수정 요약:
  - Added STT collect diagnostics to `core/audio/media_processor_transcribe_run.py` and `core/audio/media_processor_transcribe.py`.
  - `stt_primary_transcribe` now exposes backend, chunk count, submitted chunk count, worker count, setup time, collect time, received/processed chunks, emitted segment count, and worker-cache state.
  - Added nested collect spans: `stt_primary_collect_transcribe`, `stt2_collect_transcribe`, and `word_precision_collect_transcribe`.
  - `tools/verify_full_media_pipeline.py` now propagates the new collect diagnostics into summary metrics.
- 검증:
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m py_compile core/audio/media_processor_transcribe_run.py core/audio/media_processor_transcribe.py tools/verify_full_media_pipeline.py tests/test_verify_full_media_pipeline.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_verify_full_media_pipeline.py -k "stage_wall_clock_rollup"` -> `1 passed, 14 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_verify_full_media_pipeline.py tests/test_benchmark_mode_profiles.py -k "stage_wall_clock or parse_setting_overrides or cli_setting_overrides"` -> `4 passed, 45 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_media_processor_overlap.py -k "word_precision_recheck_uses_user_selected_stt1_model or word_precision_recheck_allows_explicit_precision_model or selective or recheck"` -> `14 passed, 91 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_stt_recheck_service.py -k "prepare_and_collect_recheck_segments or collect_and_annotate_segments"` -> `4 passed, 35 deselected`.
  - Generated fixture `mode_high` run `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_001645/benchmark_results.md` -> elapsed `49.380s`, raw/final/reference `54/54/54`, quality/text/timing `80.153/91.676/1.437s`, final invalid/non-monotonic/overlap `0/0/0`, global max active `1`.
  - `tools/evaluate_reference_benchmark_acceptance.py` on the generated-fixture benchmark -> `accepted=true`.
- 자막 품질 영향:
  - No subtitle-generation policy, STT2, word precision range selection, LLM/LoRA/VAD, timing, or model-selection behavior changed.
  - STT1 finding: total `20.135353s`, setup `0.046327s`, collect `19.986159s`, chunks `2`, worker count `2`, backend `whisperkit_persistent`.
- 남은 위험:
  - This proves ownership of the STT1 cost on the generated fixture only. It does not justify skipping STT1, downgrading the model, shrinking windows, or enabling STT collect cache by default.

## Generated Video Subtitle Validation - 2026-06-28 00:08 KST

- 실행 모드: NAS-off owner fallback validation, source-app `mode_high` generation on Dex-generated 180s Korean fixture.
- 결과: pass.
- 저장 위치:
  - Report: `output/manual_verification/latest/generated_video_subtitle_validation_20260628/validation_report.md`
  - Generated final SRT: `output/manual_verification/latest/generated_video_subtitle_validation_20260628/generated_final_subtitles.srt`
  - Preflight: `output/manual_verification/latest/generated_video_subtitle_validation_20260628/preflight/reference_fixture_availability.md`
  - Benchmark: `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_000644/benchmark_results.md`
  - Acceptance: `output/manual_verification/latest/generated_video_subtitle_validation_20260628/acceptance/reference_benchmark_acceptance.md`
- 수정 요약:
  - Code was not changed.
  - Reused the Dex-generated `180.583s` Korean fixture and matching `54`-row reference SRT after the owner said NAS was off.
- 검증:
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/verify_reference_fixture_availability.py --media "output/manual_verification/latest/high_context_keep_cache_20260627/synthetic_fixture/synthetic_high_context_keep_cache.mp4" --reference-srt "output/manual_verification/latest/high_context_keep_cache_20260627/synthetic_fixture/synthetic_high_context_keep_cache.srt" --start-sec 0 --duration-sec 180 --output-dir output/manual_verification/latest/generated_video_subtitle_validation_20260628/preflight` -> ready, clipped reference rows `54`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/benchmark_subtitle_pipeline_variants.py --suite modes --variants mode_high --media "output/manual_verification/latest/high_context_keep_cache_20260627/synthetic_fixture/synthetic_high_context_keep_cache.mp4" --reference-srt "output/manual_verification/latest/high_context_keep_cache_20260627/synthetic_fixture/synthetic_high_context_keep_cache.srt" --start-sec 0 --duration-sec 180 --keep-artifacts` -> elapsed `78.344s`, raw/final/reference `54/54/54`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/evaluate_reference_benchmark_acceptance.py .codex_work/benchmarks/subtitle_pipeline_variants/20260628_000644/benchmark_results.json --output-dir output/manual_verification/latest/generated_video_subtitle_validation_20260628/acceptance` -> `accepted=true`.
- 자막 품질 영향:
  - Final invalid/non-monotonic/overlap `0/0/0`, save/reopen stable `true`, global canvas max active `1`.
  - Quality/text/timing MAE `80.153/91.676/1.437s`; STT1/STT2/word precision counts `17/37/9`.
- 남은 위험:
  - This is owner-requested generated-fixture fallback evidence while NAS is off. It does not replace representative real-footage backfill before enabling STT collect cache by default or approving broad latency trims.

## NLE Global Canvas Final Projection Cutover - 2026-06-27

- 실행 모드: source-app runtime NLE adoption slice, global canvas final-only projection.
- 결과: pass.
- 저장 위치:
  - Report: `output/manual_verification/latest/nle_global_canvas_final_projection_20260627/global_canvas_projection_report.md`
- 원인 후보 또는 수정 요약:
  - Added `nle_global_canvas_segments_from_editor_rows(...)` beside the existing final-overlay NLE runtime projection helper.
  - `TimelineWidget.update_segments(..., global_rows=...)` now allows the timeline canvas to keep live STT/subtitle preview rows while the global canvas subtitle lane receives final-only NLE rows.
  - Editor redraw and live-preview update paths pass confirmed final rows through the NLE global-canvas projection, preventing final subtitle minimap rows from being mixed with live STT/subtitle preview rows.
- 검증:
  - `./venv/bin/python -m py_compile core/project/nle_runtime_cutover.py ui/editor/editor_segments_timeline_context.py ui/editor/editor_segments_stt_selection_flow.py ui/timeline/timeline_widget.py tests/test_project_nle_runtime_cutover.py tests/test_timeline_playhead_fit.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_runtime_cutover.py tests/test_timeline_playhead_fit.py -k "nle_runtime_cutover or final_overlay_cutover or global_canvas_cutover or final_only_rows_to_global_canvas or project_loaded_stt_preview"` -> `5 passed, 158 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py -k "global_canvas or project_loaded_stt_preview or final_only_rows_to_global_canvas"` -> `9 passed, 151 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_runtime_cutover.py tests/test_project_nle_render_export_parity.py tests/test_project_nle_snapshot.py` -> `20 passed, 4 subtests passed`.
  - `git diff --check -- core/project/nle_runtime_cutover.py ui/editor/editor_segments_timeline_context.py ui/editor/editor_segments_stt_selection_flow.py ui/timeline/timeline_widget.py tests/test_project_nle_runtime_cutover.py tests/test_timeline_playhead_fit.py` -> pass.
- 자막 품질 영향:
  - No subtitle-generation, STT2, LLM, LoRA, VAD, timing, or model-selection policy changed.
  - Timeline preview behavior is preserved; only the global canvas subtitle-lane data source can now be final-only when editor code supplies NLE `global_rows`.
- 남은 위험:
  - This is a focused runtime projection cutover, not full timeline/save/render/export ownership cleanup. Broader persistence and render/export cutover remain gated.

## STT Recheck Collect Cache Candidate - 2026-06-27 23:50 KST

- 실행 모드: source-app generation latency candidate, opt-in STT2/word precision collect replay cache.
- 결과: pass on owner-approved generated 3-minute fixture; NAS acceptance not run because NAS was off.
- 저장 위치:
  - Report: `output/manual_verification/latest/stt_recheck_collect_cache_20260627/collect_cache_report.md`
  - Final cache-hit SRT: `output/manual_verification/latest/stt_recheck_collect_cache_20260627/synthetic_final_subtitles_cache_hit.srt`
  - Cache file: `output/manual_verification/latest/stt_recheck_collect_cache_20260627/stt_recheck_collect_cache.json`
  - First acceptance: `output/manual_verification/latest/stt_recheck_collect_cache_20260627/acceptance_first/reference_benchmark_acceptance.md`
  - Second acceptance: `output/manual_verification/latest/stt_recheck_collect_cache_20260627/acceptance_second/reference_benchmark_acceptance.md`
- 원인 후보 또는 수정 요약:
  - Added an opt-in exact collect replay cache for STT2 and word precision recheck batches.
  - Cache hits skip the provider collect call only; annotation, STT2 replacement selection, word precision timing application, final integrity, and reference acceptance still run.
  - Live STT2 preview callback paths disable this cache so candidate-lane preview events are not skipped.
  - `stt_recheck_collect_cache_enabled` remains default `false` until real-media backfill is accepted.
- Synthetic fixture verification:
  - First write run: `.codex_work/benchmarks/subtitle_pipeline_variants/20260627_234839/benchmark_results.md`; elapsed `46.498s`, raw/final/reference `54/54/54`, quality `80.153`, text `91.676`, timing MAE `1.437s`, final invalid/non-monotonic/overlap `0/0/0`, global max active `1`, STT2 collect `14.284272s`, word precision collect `10.930693s`, cache hit/write/provider `false/true/true`, accepted `true`.
  - Second cache-hit run: `.codex_work/benchmarks/subtitle_pipeline_variants/20260627_234935/benchmark_results.md`; elapsed `20.105s`, same quality/text/timing/final gates, STT2 collect `0.0s`, word precision collect `0.0s`, cache hit/write/provider `true/false/false`, accepted `true`.
- 검증:
  - `./venv/bin/python -m py_compile core/audio/stt_recheck_service.py core/audio/media_processor_transcribe_recheck.py core/runtime/config.py tools/benchmark_subtitle_pipeline_variants.py tools/verify_full_media_pipeline.py tests/test_stt_recheck_service.py tests/test_verify_full_media_pipeline.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_stt_recheck_service.py -k "prepare_and_collect_recheck_segments or collect_and_annotate_segments"` -> `4 passed, 35 deselected`.
  - `./venv/bin/python -m pytest -q tests/test_verify_full_media_pipeline.py -k "stage_wall_clock_rollup"` -> `1 passed, 14 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_media_processor_overlap.py -k "word_precision_recheck_uses_user_selected_stt1_model or word_precision_recheck_allows_explicit_precision_model or selective or recheck"` -> `14 passed, 91 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_media_processor_overlap.py -k "ensemble_preview_callback_receives_stt2_segments or word_precision_recheck_uses_user_selected_stt1_model or word_precision_recheck_allows_explicit_precision_model or selective or recheck"` -> `15 passed, 90 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_stt_recheck_service.py -k "prepare_and_collect_recheck_segments"` -> `3 passed, 36 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_benchmark_mode_profiles.py -k "stage_wall_clock_summary"` -> `1 passed, 33 deselected`.
  - `git diff --check -- core/audio/stt_recheck_service.py core/audio/media_processor_transcribe_recheck.py core/runtime/config.py tools/benchmark_subtitle_pipeline_variants.py tools/verify_full_media_pipeline.py tests/test_stt_recheck_service.py tests/test_verify_full_media_pipeline.py` -> pass.
  - `tools/evaluate_reference_benchmark_acceptance.py` on both synthetic collect-cache benchmark results -> `accepted=true`.
- 자막 품질 영향:
  - No quality regression on the generated fixture. Both runs kept raw/final/reference `54/54/54`, quality `80.153`, text `91.676`, timing MAE `1.437s`, final invalid/non-monotonic/overlap `0/0/0`, and global max active `1`.
- 남은 위험:
  - Synthetic fixture proof is not production-wide real-footage proof. Backfill on NAS HeyDealer or another representative owner fixture before enabling this cache by default.

## Macro Proofread Response Cache Candidate - 2026-06-27 23:37 KST

- 실행 모드: source-app generation latency candidate, exact macro proofread response replay cache.
- 결과: pass on owner-approved generated 3-minute fixture; NAS acceptance not run because NAS was off.
- 저장 위치:
  - Report: `output/manual_verification/latest/macro_response_cache_20260627/macro_response_cache_report.md`
  - Cache file: `output/manual_verification/latest/macro_response_cache_20260627/macro_response_cache_replay.json`
  - First acceptance: `output/manual_verification/latest/macro_response_cache_20260627/acceptance_first/reference_benchmark_acceptance.md`
  - Second acceptance: `output/manual_verification/latest/macro_response_cache_20260627/acceptance_second/reference_benchmark_acceptance.md`
- 원인 후보 또는 수정 요약:
  - Added an exact prompt/model/provider cache for macro proofread LLM response chunks.
  - Cache hits skip the external provider call only; candidate-lock verification, subtitle verifier, and Deep rerank still run before accepting or rejecting the replayed chunks.
  - Benchmark postprocess diagnostics now expose macro response cache enabled/hit/write/provider-call group counts.
- Synthetic fixture verification:
  - First write run: `.codex_work/benchmarks/subtitle_pipeline_variants/20260627_233240/benchmark_results.md`; elapsed `82.433s`, raw/final/reference `54/54/54`, quality `80.153`, text `91.676`, timing MAE `1.437s`, final invalid/non-monotonic/overlap `0/0/0`, global max active `1`, proofread elapsed `30.731199s`, accepted `true`, cache entries `1`.
  - Second cache-hit run: `.codex_work/benchmarks/subtitle_pipeline_variants/20260627_233531/benchmark_results.md`; elapsed `55.247s`, same quality/text/timing/final gates, proofread elapsed `0.545337s`, macro cache hit/write/provider groups `1/0/0`, accepted `true`.
- 검증:
  - `./venv/bin/python -m py_compile core/engine/subtitle_engine.py core/engine/subtitle_macro_chunks.py tools/benchmark_subtitle_pipeline_variants.py tests/test_subtitle_engine_settings.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_subtitle_engine_settings.py tests/test_benchmark_mode_profiles.py -k "macro_chunk_response_cache or optimize_segments_batches_llm_into_macro_chunks or macro_gate_zero_llm_rows or macro_chunk_stt_rows_reject_freeform_llm_rewrite or parse_setting_overrides or cli_setting_overrides"` -> `6 passed, 112 deselected`.
  - `tools/evaluate_reference_benchmark_acceptance.py` on both synthetic macro-cache benchmark results -> `accepted=true`.
- 자막 품질 영향:
  - No quality regression on the generated fixture. Both runs kept raw/final/reference `54/54/54`, quality `80.153`, text `91.676`, timing MAE `1.437s`, final invalid/non-monotonic/overlap `0/0/0`, and global max active `1`.
- 남은 위험:
  - Synthetic fixture proof is not production-wide real-footage proof. Current latest cache-hit run still spends STT1 `20.176462s`, STT2 collect `15.227744s`, and word precision collect `18.462423s`; backfill on NAS HeyDealer or another representative owner fixture when available.

## High Context Keep Cache Candidate - 2026-06-27 23:19 KST

- 실행 모드: source-app generation latency candidate, strict High context-boundary keep/no-correction cache.
- 결과: pass on owner-approved generated 3-minute fixture; NAS acceptance not run because NAS was off.
- 저장 위치:
  - Report: `output/manual_verification/latest/high_context_keep_cache_20260627/keep_cache_report.md`
  - Fixture: `output/manual_verification/latest/high_context_keep_cache_20260627/synthetic_fixture/fixture_report.md`
  - Summary: `output/manual_verification/latest/high_context_keep_cache_20260627/synthetic_keep_cache_summary.json`
- 원인 후보 또는 수정 요약:
  - Implemented an exact prompt/model/settings cache that reuses only prior High context-boundary `keep` decisions with no correction request and no applied change.
  - Move, merge, invalid, correction-requested, or changed decisions are not cached.
  - Candidate budget still counts candidate pairs, so cache hits cannot expand the checked pair set.
  - Benchmark/verifier artifacts now expose keep-cache enabled/hit/miss/write counts, and the benchmark tool accepts `--setting key=value` overrides to isolate cache-path validation.
  - Fixed benchmark CLI override precedence so explicit `--setting` values win over mode-profile defaults.
  - Generated a 180.583s Korean validation video plus matching SRT with 54 reference rows after the owner stated NAS was off.
- Synthetic fixture verification:
  - First write run: `.codex_work/benchmarks/subtitle_pipeline_variants/20260627_231459/benchmark_results.md`; elapsed `144.476s`, raw/final/reference `54/54/54`, quality `80.153`, text `91.676`, timing MAE `1.437s`, final invalid/non-monotonic/overlap `0/0/0`, global max active `1`, High context calls/cache hit-miss-write `8/0-8-8`, accepted `true`.
  - Second cache-hit run: `.codex_work/benchmarks/subtitle_pipeline_variants/20260627_231734/benchmark_results.md`; elapsed `83.281s`, same quality/text/timing/final gates, High context calls/cache hit-miss-write `0/8-0-0`, High context elapsed `67.699701s -> 0.003326s`, accepted `true`.
- 검증:
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m py_compile core/engine/subtitle_context_refiner.py core/runtime/config.py tools/benchmark_subtitle_pipeline_variants.py tools/verify_full_media_pipeline.py tests/test_subtitle_context_refiner.py tests/test_verify_full_media_pipeline.py tests/test_benchmark_mode_profiles.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_subtitle_context_refiner.py` -> `8 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_verify_full_media_pipeline.py -k "stage_wall_clock or repeat_summary_rolls_up_accuracy_preserving_stt2_metrics"` -> `2 passed, 13 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_benchmark_mode_profiles.py -k "parse_setting_overrides or cli_setting_overrides"` -> `2 passed, 32 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_subtitle_context_refiner.py tests/test_verify_full_media_pipeline.py tests/test_benchmark_mode_profiles.py -k "context_refiner or stage_wall_clock or repeat_summary_rolls_up_accuracy_preserving_stt2_metrics or parse_setting_overrides or cli_setting_overrides"` -> `13 passed, 44 deselected`.
  - `tools/evaluate_reference_benchmark_acceptance.py` on both synthetic benchmark results -> `accepted=true`.
- 자막 품질 영향:
  - No quality regression on the generated fixture. Both runs kept raw/final/reference `54/54/54`, quality `80.153`, text `91.676`, timing MAE `1.437s`, final invalid/non-monotonic/overlap `0/0/0`, and global max active `1`.
- 남은 위험:
  - Synthetic fixture proof is not production-wide real-footage proof. Backfill on NAS HeyDealer or another representative owner fixture when available.

## High Context Decision Diagnostics - 2026-06-27 22:47 KST

- 실행 모드: owner-required source-app generation latency diagnostics, NAS HeyDealer first 180 seconds only.
- 결과: pass.
- 저장 위치:
  - Report: `output/manual_verification/latest/high_context_decision_diagnostics_20260627/decision_diagnostics_report.md`
  - Benchmark: `.codex_work/benchmarks/subtitle_pipeline_variants/20260627_224543/benchmark_results.md`
  - Acceptance: `output/manual_verification/latest/high_context_decision_diagnostics_20260627/acceptance/reference_benchmark_acceptance.md`
- 원인 후보 또는 수정 요약:
  - Added behavior-preserving decision-action diagnostics for High context-boundary checks.
  - Re-ran the owner-required NAS HeyDealer MP4/SRT first 180 seconds with `mode_high`.
  - Result: elapsed `59.559s`, raw/final/reference `58/56/89`, quality `81.335`, text `94.267`, timing MAE `1.5958s`.
  - Final subtitle gates: invalid/non-monotonic/overlap `0/0/0`, `stable_for_save_reopen=true`; global canvas `max_active_segments=1`.
  - High context-boundary: candidate/skipped/call/failed/changed/max pairs `2/55/2/0/0/8`; keep/move/merge/invalid `2/0/0/0`; correction requested/applied `0/0`.
  - Interpretation: current NAS fixture points to a decision-equivalent no-change gate as the only safe High context-boundary speed candidate. It does not approve batching or broad skipping.
- 검증:
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m py_compile core/engine/subtitle_context_refiner.py tools/verify_full_media_pipeline.py tools/benchmark_subtitle_pipeline_variants.py tests/test_subtitle_context_refiner.py tests/test_verify_full_media_pipeline.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_subtitle_context_refiner.py` -> `6 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_verify_full_media_pipeline.py -k "stage_wall_clock or repeat_summary_rolls_up_accuracy_preserving_stt2_metrics"` -> `2 passed, 13 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/benchmark_subtitle_pipeline_variants.py --suite modes --variants mode_high --media "/Volumes/photo/.../헤이딜러_최종.MP4" --reference-srt "/Volumes/photo/.../헤이딜러_최종.srt" --start-sec 0 --duration-sec 180 --keep-artifacts` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/evaluate_reference_benchmark_acceptance.py .codex_work/benchmarks/subtitle_pipeline_variants/20260627_224543/benchmark_results.json --output-dir output/manual_verification/latest/high_context_decision_diagnostics_20260627/acceptance` -> `accepted=true`.
- 자막 품질 영향:
  - None. This adds diagnostics and validation evidence only; STT2, word precision, LLM/LoRA/VAD policy, timing policy, final subtitle stability, save/render/export, visible UI/UX, packaging, commit, and push behavior were not changed.
- 남은 위험:
  - This does not approve a runtime latency trim. The next candidate still needs same NAS fixture before/after reference scoring.

## STT Recheck Reason Breakdown - 2026-06-27 22:36 KST

- 실행 모드: owner-required source-app generation latency diagnostics, NAS HeyDealer first 180 seconds only.
- 결과: pass.
- 저장 위치:
  - Report: `output/manual_verification/latest/stt_recheck_reason_breakdown_20260627/reason_breakdown_report.md`
  - Benchmark: `.codex_work/benchmarks/subtitle_pipeline_variants/20260627_223426/benchmark_results.md`
  - Acceptance: `output/manual_verification/latest/stt_recheck_reason_breakdown_20260627/acceptance/reference_benchmark_acceptance.md`
- 원인 후보 또는 수정 요약:
  - Added behavior-preserving reason breakdown diagnostics for STT2 selective recheck and word precision.
  - Re-ran the owner-required NAS HeyDealer MP4/SRT first 180 seconds with `mode_high`.
  - Result: elapsed `58.820s`, raw/final/reference `58/56/89`, quality `81.335`, text `94.267`, timing MAE `1.5958s`.
  - Final subtitle gates: invalid/non-monotonic/overlap `0/0/0`, `stable_for_save_reopen=true`; global canvas `max_active_segments=1`.
  - STT2 selective recheck: missing voice / route hint / low score / empty text `1/0/0/1`; applied segment count `37`; range/prepared audio `180.096s/120.000s`.
  - Word precision: selected / precision review / needs review `0/0/0`; red / yellow / risk / missing word `0/0/0/0`; range/prepared count `25/25`; applied `7`.
  - Interpretation: current NAS fixture points away from STT2 skip and review-critical word-range removal. The next speed candidate should focus on collect scheduling/cache reuse or a decision-equivalent High context-boundary gate.
- 검증:
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m py_compile core/audio/media_processor_transcribe_recheck.py tools/verify_full_media_pipeline.py tests/test_media_processor_overlap.py tests/test_verify_full_media_pipeline.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_media_processor_overlap.py -k "word_precision_recheck_uses_user_selected_stt1_model or selective_ensemble_runs_stt2_only_for_low_score_ranges"` -> `2 passed, 103 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_verify_full_media_pipeline.py -k "stage_wall_clock or repeat_summary_rolls_up_accuracy_preserving_stt2_metrics"` -> `2 passed, 13 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/benchmark_subtitle_pipeline_variants.py --suite modes --variants mode_high --media "/Volumes/photo/.../헤이딜러_최종.MP4" --reference-srt "/Volumes/photo/.../헤이딜러_최종.srt" --start-sec 0 --duration-sec 180 --keep-artifacts` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/evaluate_reference_benchmark_acceptance.py .codex_work/benchmarks/subtitle_pipeline_variants/20260627_223426/benchmark_results.json --output-dir output/manual_verification/latest/stt_recheck_reason_breakdown_20260627/acceptance` -> `accepted=true`.
- 자막 품질 영향:
  - None. This adds diagnostics and validation evidence only; STT2, word precision, LLM/LoRA/VAD policy, timing policy, final subtitle stability, save/render/export, visible UI/UX, packaging, commit, and push behavior were not changed.
- 남은 위험:
  - This does not approve a runtime latency trim. It narrows the next safe investigation target to collect scheduling/cache reuse or decision-equivalent postprocess work.

## STT Recheck Duration Diagnostics - 2026-06-27 22:24 KST

- 실행 모드: owner-required source-app generation latency diagnostics, NAS HeyDealer first 180 seconds only.
- 결과: pass.
- 저장 위치:
  - Report: `output/manual_verification/latest/stt_recheck_duration_diagnostics_20260627/diagnostics_report.md`
  - Benchmark: `.codex_work/benchmarks/subtitle_pipeline_variants/20260627_222233/benchmark_results.md`
  - Acceptance: `output/manual_verification/latest/stt_recheck_duration_diagnostics_20260627/acceptance/reference_benchmark_acceptance.md`
- 원인 후보 또는 수정 요약:
  - Added behavior-preserving STT2/word precision diagnostics for range audio duration, prepared clip duration, and STT2 applied segment count.
  - Re-ran the owner-required NAS HeyDealer MP4/SRT first 180 seconds with `mode_high`.
  - Result: elapsed `59.255s`, raw/final/reference `58/56/89`, quality `81.335`, text `94.267`, timing MAE `1.5958s`.
  - Final subtitle gates: invalid/non-monotonic/overlap `0/0/0`, `stable_for_save_reopen=true`; global canvas `max_active_segments=1`.
  - STT2 selective recheck: elapsed `13.843705s`, raw/range/prepared `1/1/1`, collected/applied ranges/applied segments `37/1/37`, range audio `180.096s`, prepared audio `120.000s`.
  - Word precision: elapsed `12.253285s`, range/prepared `25/25`, collected/applied `26/7`, range audio `67.640s`, prepared audio `89.690s`.
  - Interpretation: STT2 `applied_count=1` is a single broad rescue range, not a safe single-segment trim target; the next latency candidate must still use same NAS fixture before/after reference scoring.
- 검증:
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m py_compile core/audio/media_processor_transcribe_recheck.py tools/verify_full_media_pipeline.py tests/test_media_processor_overlap.py tests/test_verify_full_media_pipeline.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_media_processor_overlap.py -k "word_precision_recheck_uses_user_selected_stt1_model or selective_ensemble_runs_stt2_only_for_low_score_ranges"` -> `2 passed, 103 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_verify_full_media_pipeline.py -k "stage_wall_clock or repeat_summary_rolls_up_accuracy_preserving_stt2_metrics"` -> `2 passed, 13 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/benchmark_subtitle_pipeline_variants.py --suite modes --variants mode_high --media "/Volumes/photo/.../헤이딜러_최종.MP4" --reference-srt "/Volumes/photo/.../헤이딜러_최종.srt" --start-sec 0 --duration-sec 180 --keep-artifacts` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/evaluate_reference_benchmark_acceptance.py .codex_work/benchmarks/subtitle_pipeline_variants/20260627_222233/benchmark_results.json --output-dir output/manual_verification/latest/stt_recheck_duration_diagnostics_20260627/acceptance` -> `accepted=true`.
- 자막 품질 영향:
  - None. This adds diagnostics and validation evidence only; STT2, word precision, LLM/LoRA/VAD policy, timing policy, final subtitle stability, save/render/export, visible UI/UX, packaging, commit, and push behavior were not changed.
- 남은 위험:
  - This proves the measurement surface and NAS HeyDealer gate. It does not approve a runtime latency trim; the next candidate still needs same-fixture before/after proof.

## NAS HeyDealer 3-Minute Reference Benchmark - 2026-06-27 22:13 KST

- 실행 모드: owner-required source-app generation latency acceptance gate, NAS HeyDealer first 180 seconds only.
- 결과: pass.
- 저장 위치:
  - Report: `output/manual_verification/latest/heydealer_nas_reference_180s_20260627_2215/reference_benchmark_report.md`
  - Preflight: `output/manual_verification/latest/heydealer_nas_reference_180s_20260627_2215_preflight/reference_fixture_availability.md`
  - Benchmark: `.codex_work/benchmarks/subtitle_pipeline_variants/20260627_221152/benchmark_results.md`
  - Acceptance: `output/manual_verification/latest/heydealer_nas_reference_180s_20260627_2215_acceptance/reference_benchmark_acceptance.md`
- 원인 후보 또는 수정 요약:
  - Mounted `/Volumes/photo` via the NAS route and verified the exact HeyDealer MP4/SRT pair exists.
  - Ran `mode_high` against `/Volumes/photo/.../[20260209]헤이딜러광고/헤이딜러_최종.MP4` with matching `헤이딜러_최종.srt`, span `0s~180s`.
  - Result: elapsed `60.187s`, raw/final/reference `58/56/89`, quality `81.335`, text `94.267`, timing MAE `1.5958s`.
  - Final subtitle gates: invalid/non-monotonic/overlap `0/0/0`, `stable_for_save_reopen=true`; global canvas `max_active_segments=1`, `stable_for_global_canvas=true`.
  - Stage spans: STT1 `18.089376s`, STT2 selective recheck `13.769461s`, word precision `12.176120s`, subtitle postprocess `16.049834s`, High context-boundary `15.531674s`.
  - Candidate lane counts: STT1 selected `21`, STT2 selected `37`, word precision `7`.
- 검증:
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/verify_reference_fixture_availability.py --media "/Volumes/photo/.../헤이딜러_최종.MP4" --reference-srt "/Volumes/photo/.../헤이딜러_최종.srt" --fallback-media "output/_audio_fingerprint/.../헤이딜러_최종_cleaned.wav" --start-sec 0 --duration-sec 180 --output-dir output/manual_verification/latest/heydealer_nas_reference_180s_20260627_2215_preflight` -> ready `true`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/benchmark_subtitle_pipeline_variants.py --suite modes --variants mode_high --media "/Volumes/photo/.../헤이딜러_최종.MP4" --reference-srt "/Volumes/photo/.../헤이딜러_최종.srt" --start-sec 0 --duration-sec 180 --keep-artifacts` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/evaluate_reference_benchmark_acceptance.py .codex_work/benchmarks/subtitle_pipeline_variants/20260627_221152/benchmark_results.json --output-dir output/manual_verification/latest/heydealer_nas_reference_180s_20260627_2215_acceptance` -> `accepted=true`.
- 자막 품질 영향:
  - None. This is a validation run only; STT2, word precision, LLM/LoRA/VAD policy, timing policy, final subtitle stability, save/render/export, visible UI/UX, packaging, commit, and push behavior were not changed.
- 남은 위험:
  - This proves the current baseline on the owner-required NAS HeyDealer 3-minute fixture. It does not approve a new latency trim by itself; the next trim candidate still needs same-fixture before/after proof.

## NLE Live Editor Gap Generate Cutover - 2026-06-27

- 실행 모드: source-app NLE runtime editing adoption, live editor silence-gap subtitle generation.
- 결과: pass.
- 저장 위치:
  - Report: `output/manual_verification/latest/nle_live_editor_gap_generate_cutover_20260627/gap_generate_cutover_report.md`
  - Runtime operation: `core/project/nle_dual_write.py`
  - Live editor route: `ui/editor/ux/editor_timeline_video.py`, `ui/editor/ux/editor_timeline_gap_split.py`
  - Focused tests: `tests/test_project_nle_dual_write.py`, `tests/test_timeline_playhead_fit.py`
- 수정 요약:
  - Added `apply_gap_generate_dual_write_pilot(...)` to route silence-gap subtitle generation through runtime `NLEProjectState`, record a `gap_generate` `NLEEditorOperation`, and project back into legacy `editor_state`.
  - Live editor gap generation now attempts NLE `gap_generate` when the gap row is stable, then reloads projected rows through `_reload_segments_from_list(..., preserve_view=True, mark_dirty=True)`.
  - Taption-style `to/from` behavior is preserved: generated subtitles keep the selected gap span, while left/right silence gap rows remain around the new subtitle when needed.
  - Live STT preview rows, NLE rejection, missing gap identity/range, unsupported timeline shape, or invalid rows keep the existing Taption/source-app direct gap generation path.
- 검증:
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m py_compile core/project/nle_dual_write.py ui/editor/ux/editor_timeline_video.py ui/editor/ux/editor_timeline_gap_split.py tests/test_project_nle_dual_write.py tests/test_timeline_playhead_fit.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_dual_write.py -k "gap_generate or caption_delete or gap_delete"` -> `7 passed, 7 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py -k "gap_generate_routes_live_editor_mutation or gap_generate_skips_nle or segment_delete_routes_live_editor_mutation"` -> `3 passed, 156 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_hit_targets.py -k "gap_generate or gap_delete or gap_to_segs or segment_delete"` -> `13 passed, 137 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_dual_write.py tests/test_project_nle_operations.py tests/test_project_nle_snapshot.py tests/test_project_nle_persistence_guard.py tests/test_project_nle_runtime_cutover.py tests/test_project_nle_render_export_parity.py` -> `42 passed, 4 subtests passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py -k "gap_generate or delete or resize or diamond or single_gap or center_drag"` -> `36 passed, 123 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py tests/test_subtitle_live_editor_feed_facade.py` -> `162 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_hit_targets.py tests/test_app_command_bridge.py -k "drag or gap or magnet or stt_candidate or delete"` -> `68 passed, 158 deselected`.
  - `git diff --check -- core/project/nle_dual_write.py ui/editor/ux/editor_timeline_video.py ui/editor/ux/editor_timeline_gap_split.py tests/test_project_nle_dual_write.py tests/test_timeline_playhead_fit.py` -> pass.
- 자막 품질 영향:
  - None intended. This routes an existing silence-gap subtitle generation mutation through runtime NLE dual-write while preserving legacy fallback, STT preview preservation, final overlap gates, save format, render/export behavior, visible UI/UX, packaging, release, commit, and push behavior.
- 남은 위험:
  - Historical note: at this checkpoint, broader live mutation routing was still incremental and split/merge/candidate-confirm were not yet cut over. Later entries in this file record the completed split, merge, and candidate-confirm NLE routes.

## NLE Live Editor Caption Delete Cutover - 2026-06-27

- 실행 모드: source-app NLE runtime editing adoption, live editor segment delete-to-gap.
- 결과: pass.
- 저장 위치:
  - Report: `output/manual_verification/latest/nle_live_editor_caption_delete_cutover_20260627/caption_delete_cutover_report.md`
  - Runtime operation: `core/project/nle_dual_write.py`
  - Live editor route: `ui/editor/ux/editor_timeline_video.py`, `ui/editor/ux/editor_timeline_gap_split.py`
  - Focused tests: `tests/test_project_nle_dual_write.py`, `tests/test_timeline_playhead_fit.py`
- 수정 요약:
  - Added `apply_caption_delete_dual_write_pilot(...)` to route final subtitle delete-to-gap through runtime `NLEProjectState`, record a `caption_delete` `NLEEditorOperation`, and project back into legacy `editor_state`.
  - Live editor segment deletion now attempts NLE `caption_delete` when the row is a stable final caption, then reloads projected rows through `_reload_segments_from_list(..., preserve_view=True, mark_dirty=True)`.
  - Delete mode is recorded as `replace_with_silence_gap`, so Taption-style subtitle deletion still becomes an editable silence gap rather than a final-overlap or disappearing-time mutation.
  - Live STT preview rows, NLE rejection, missing caption identity, unsupported timeline shape, or invalid rows keep the existing Taption/source-app direct gap conversion path.
- 검증:
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m py_compile core/project/nle_dual_write.py ui/editor/ux/editor_timeline_video.py ui/editor/ux/editor_timeline_gap_split.py tests/test_project_nle_dual_write.py tests/test_timeline_playhead_fit.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_dual_write.py -k "caption_delete or gap_delete or caption_resize"` -> `9 passed, 3 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py -k "segment_delete_routes_live_editor_mutation or segment_delete_skips_nle or square_left_resize_routes_live_editor_mutation or diamond_resize_routes_live_editor_mutation"` -> `4 passed, 153 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_hit_targets.py -k "segment_delete or gap_generate or gap_delete or gap_to_segs"` -> `13 passed, 137 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_dual_write.py tests/test_project_nle_operations.py tests/test_project_nle_snapshot.py tests/test_project_nle_persistence_guard.py tests/test_project_nle_runtime_cutover.py tests/test_project_nle_render_export_parity.py` -> `40 passed, 4 subtests passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py -k "delete or resize or diamond or single_gap or center_drag"` -> `34 passed, 123 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py tests/test_subtitle_live_editor_feed_facade.py` -> `160 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_hit_targets.py tests/test_app_command_bridge.py -k "drag or gap or magnet or stt_candidate or delete"` -> `68 passed, 158 deselected`.
  - `git diff --check -- core/project/nle_dual_write.py ui/editor/ux/editor_timeline_video.py ui/editor/ux/editor_timeline_gap_split.py tests/test_project_nle_dual_write.py tests/test_timeline_playhead_fit.py` -> pass.
- 자막 품질 영향:
  - None intended. This routes an existing editor delete-to-gap mutation through runtime NLE dual-write while preserving legacy fallback, STT preview preservation, final overlap gates, save format, render/export behavior, visible UI/UX, packaging, release, commit, and push behavior.
- 남은 위험:
  - Historical note: at this checkpoint, broader live mutation routing was still incremental and split/merge/candidate-confirm were not yet cut over. Later entries in this file record the completed split, merge, and candidate-confirm NLE routes.

## NAS HeyDealer 3-Minute Reference Preflight Refresh - 2026-06-27 21:52 KST

- 실행 모드: owner-required source-app generation latency acceptance gate, NAS HeyDealer first 180 seconds only.
- 결과: blocked. The NAS HeyDealer MP4 and matching SRT are still not mounted in this session, so no X5, project-reference, or cached-audio substitute was run for acceptance.
- 저장 위치:
  - Report: `output/manual_verification/latest/heydealer_nas_reference_preflight_20260627_latest/reference_fixture_availability.md`
  - JSON: `output/manual_verification/latest/heydealer_nas_reference_preflight_20260627_latest/reference_fixture_availability.json`
- 원인 후보 또는 수정 요약:
  - Preflight returned `reference_media_missing` and `reference_srt_missing`.
  - `/Volumes` currently exposes only `Macintosh HD` and `action6`; `/Volumes/photo` is not mounted.
  - `find /Volumes/action6 -maxdepth 7` found no HeyDealer-named media or SRT candidates.
  - Cached HeyDealer WAV exists, but remains fallback-only for instrumentation/structural stability and must not approve latency trims.
- 검증:
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/verify_reference_fixture_availability.py --media "/Volumes/photo/22_유튜브영상_개인/[20260209]헤이딜러광고/헤이딜러_최종.MP4" --reference-srt "/Volumes/photo/22_유튜브영상_개인/[20260209]헤이딜러광고/헤이딜러_최종.srt" --fallback-media "output/_audio_fingerprint/헤이딜러_최종_2c274c4ab434764a8546/헤이딜러_최종_cleaned.wav" --start-sec 0 --duration-sec 180 --output-dir output/manual_verification/latest/heydealer_nas_reference_preflight_20260627_latest` -> expected exit `2`, `blocking_reasons=["reference_media_missing","reference_srt_missing"]`, `ready_for_reference_scored_benchmark=false`, fallback available.
- 자막 품질 영향:
  - None. This is a validation gate/documentation refresh only; STT2, word precision, LLM/LoRA/VAD policy, timing policy, final subtitle stability, save/render/export, visible UI/UX, packaging, commit, and push behavior were not changed.
- 남은 위험:
  - Next latency optimization remains blocked until the exact NAS HeyDealer MP4 plus matching SRT are mounted/restored.
  - X5/project-reference/cached-audio runs are regression or instrumentation surfaces only under the current owner directive.

## NLE Live Editor Boundary Resize Cutover - 2026-06-27

- 실행 모드: source-app NLE runtime editing adoption, live editor boundary-handle caption resize.
- 결과: pass.
- 저장 위치:
  - Report: `output/manual_verification/latest/nle_live_editor_boundary_resize_cutover_20260627/boundary_resize_cutover_report.md`
  - Runtime route: `ui/editor/ux/editor_timeline_video.py`
  - Focused tests: `tests/test_timeline_playhead_fit.py`
- 수정 요약:
  - `_on_seg_time_changed(...)` now attempts runtime NLE `caption_resize` dual-write for `square_left` and `square_right` subtitle boundary-handle resizes, in addition to the existing `diamond` route.
  - Safe projection applies through `_reload_segments_from_list(..., preserve_view=True, mark_dirty=True)`.
  - NLE rejection, transient STT/live-preview rows, unsupported runtime shape, and invalid/collapsing rows keep the existing legacy Taption/source-app timing path.
  - Existing trim/delete behavior and final-overlap rejection are preserved by the `caption_resize` NLE dual-write operation gate.
- 검증:
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m py_compile ui/editor/ux/editor_timeline_video.py tests/test_timeline_playhead_fit.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py -k "square_left_resize_routes_live_editor_mutation or square_right_resize_routes_live_editor_mutation or square_resize_falls_back or diamond_resize_routes_live_editor_mutation"` -> `4 passed, 151 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py -k "resize or diamond or single_gap or center_drag"` -> `32 passed, 123 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_dual_write.py tests/test_project_nle_operations.py tests/test_project_nle_snapshot.py tests/test_project_nle_persistence_guard.py tests/test_project_nle_runtime_cutover.py tests/test_project_nle_render_export_parity.py` -> `38 passed, 4 subtests passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_hit_targets.py tests/test_app_command_bridge.py -k "drag or gap or magnet or stt_candidate"` -> `63 passed, 163 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py tests/test_subtitle_live_editor_feed_facade.py` -> `158 passed`.
  - `git diff --check -- ui/editor/ux/editor_timeline_video.py tests/test_timeline_playhead_fit.py` -> pass.
- 자막 품질 영향:
  - None intended. This routes existing boundary resize mutations through runtime NLE dual-write while preserving legacy fallback and final overlap gates. STT2, word precision, LLM/LoRA/VAD quality policy, timing policy, model selection, save format, render/export behavior, visible UI/UX, packaging, release, commit, and push behavior were not changed.
- 남은 위험:
  - Broader live mutation routing remains incremental. Current live editor NLE coverage includes `diamond`, `square_left`, and `square_right` caption resize; other mutation families should stay behind focused operation/projection parity gates.

## Mac App Store Readiness Audit - 2026-06-27

- 실행 모드: non-destructive Mac App Store submission readiness audit; no packaging, signing, notarization, upload, tag, release, or DMG build.
- 결과: blocked for submission, pass for local audit coverage.
- 저장 위치:
  - Audit report: `output/manual_verification/latest/app_store_readiness_audit_20260627/app_store_readiness_audit.md`
  - Audit JSON: `output/manual_verification/latest/app_store_readiness_audit_20260627/app_store_readiness_audit.json`
  - Non-code submission draft: `docs/APP_STORE_SUBMISSION_READINESS.md`
- 수정 요약:
  - Added `tools/audit_app_store_readiness.py` to inspect packaging scripts, entitlements, Info.plist template, signing/auth environment presence, submission artifacts, and owner-input metadata without running release tooling.
  - Added `tests/test_app_store_readiness_audit.py` to prove the audit blocks when signed app/pkg/validation artifacts are missing and that required sandbox entitlements are present.
  - Added a non-code submission readiness draft for privacy, export compliance, screenshots, support URL, review notes, age rating, release notes, and entitlement explanation.
- 검증:
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m py_compile tools/audit_app_store_readiness.py tests/test_app_store_readiness_audit.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_app_store_readiness_audit.py` -> `3 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_app_store_readiness.py --output-dir output/manual_verification/latest/app_store_readiness_audit_20260627` -> `local_packaging_ready=true`, `app_store_submission_ready=false`, blocker count `14`.
- 자막 품질 영향:
  - None. This is packaging-readiness audit/documentation only; STT2, word precision, LLM/LoRA/VAD quality policy, timing policy, final subtitle stability, NLE runtime routing, save format, render/export behavior, visible UI/UX, commit, and push behavior were not changed.
- 남은 위험:
  - Missing signed `.app`, signed `.pkg`, sandbox smoke, App Store Connect validation artifact, Apple Distribution codesign identity, installer identity, and owner-provided App Store metadata.
  - Source-app pytest or QA must not be treated as App Store readiness proof.

## NAS HeyDealer 3-Minute Reference Preflight - 2026-06-27

- 실행 모드: owner-required source-app generation latency test gate, NAS HeyDealer first 180 seconds.
- 결과: blocked. The NAS HeyDealer MP4 and matching SRT are not mounted in this session, so no substitute X5 or fallback-audio benchmark was used for acceptance.
- 저장 위치:
  - Report: `output/manual_verification/latest/heydealer_nas_reference_preflight_20260627/reference_fixture_availability.md`
  - JSON: `output/manual_verification/latest/heydealer_nas_reference_preflight_20260627/reference_fixture_availability.json`
- 원인 후보 또는 수정 요약:
  - Owner required the next test to use the NAS HeyDealer 3-minute video.
  - Preflight found `/Volumes/photo/.../헤이딜러_최종.MP4` and matching `.srt` missing.
  - Cached HeyDealer WAV exists, but the preflight marks it fallback-only for instrumentation/structural stability, not latency-trim approval.
- 검증:
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/verify_reference_fixture_availability.py --media "/Volumes/photo/22_유튜브영상_개인/[20260209]헤이딜러광고/헤이딜러_최종.MP4" --reference-srt "/Volumes/photo/22_유튜브영상_개인/[20260209]헤이딜러광고/헤이딜러_최종.srt" --fallback-media "output/_audio_fingerprint/헤이딜러_최종_2c274c4ab434764a8546/헤이딜러_최종_cleaned.wav" --start-sec 0 --duration-sec 180 --output-dir output/manual_verification/latest/heydealer_nas_reference_preflight_20260627` -> expected exit `2`, `blocking_reasons=["reference_media_missing","reference_srt_missing"]`, `ready_for_reference_scored_benchmark=false`, fallback available.
- 자막 품질 영향:
  - None. This is a validation gate/documentation update only; STT2, word precision, LLM/LoRA/VAD quality policy, timing policy, final subtitle stability, save format, render/export, packaging, release, commit, and push behavior were not changed.
- 남은 위험:
  - The next latency candidate is blocked until `/Volumes/photo` is mounted with the HeyDealer MP4 and matching SRT.
  - X5/project-reference smokes remain useful regression surfaces, but they cannot replace the owner-required NAS HeyDealer 3-minute acceptance test.

## X5 Project Reference 180s Acceptance - 2026-06-27

- 실행 모드: source-app generation latency validation hardening, long local project-reference X5 smoke.
- 결과: pass for aligned project-reference fixture; rejected one semantic mismatch fixture.
- 저장 위치:
  - Report: `output/manual_verification/latest/x5_project_reference_180s_20260627/reference_benchmark_report.md`
  - Accepted preflight: `output/manual_verification/latest/x5_project_reference_180s_20260627/preflight_front/reference_fixture_availability.md`
  - Accepted benchmark JSON: `.codex_work/benchmarks/subtitle_pipeline_variants/20260627_211807/benchmark_results.json`
  - Accepted benchmark markdown: `.codex_work/benchmarks/subtitle_pipeline_variants/20260627_211807/benchmark_results.md`
  - Accepted gate: `output/manual_verification/latest/x5_project_reference_180s_20260627/acceptance_front/reference_benchmark_acceptance.md`
  - Rejected mismatch gate: `output/manual_verification/latest/x5_project_reference_180s_20260627/acceptance_rejected_back/reference_benchmark_acceptance.md`
- 수정 요약:
  - Added `tools/evaluate_reference_benchmark_acceptance.py` to classify a single reference-scored benchmark with absolute quality/text/timing/final-stability gates.
  - Added `tests/test_reference_benchmark_acceptance.py` to prove stable results pass, semantic mismatches fail, and final overlap fails.
  - Verified the cached 180s X5 WAV is semantically aligned with `projects/X5_시승기_전반.assets/subtitles/final.srt`, not with the similarly named `X5_후반` project SRT.
- 검증:
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m py_compile tools/evaluate_reference_benchmark_acceptance.py tests/test_reference_benchmark_acceptance.py tools/materialize_reference_srt.py tests/test_materialize_reference_srt.py tools/verify_reference_fixture_availability.py tests/test_reference_fixture_availability.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_reference_benchmark_acceptance.py tests/test_materialize_reference_srt.py tests/test_reference_fixture_availability.py` -> `8 passed`.
  - X5 accepted 180s project-reference run -> elapsed `70.383s`, raw/final/reference `43/50/67`, quality `76.387`, text `90.767`, timing MAE `1.5457s`, final invalid/non-monotonic/overlap `0/0/0`, global canvas `max_active_segments=1`.
  - X5 rejected mismatch run -> quality `23.234`, text `4.756`, timing MAE `3.3362s`, rejected for `quality_score_below_floor`, `text_score_below_floor`, and `timing_mae_above_ceiling`.
- 자막 품질 영향:
  - None intended. This adds acceptance classification and fixture validation only. STT2, word precision, LLM/LoRA/VAD quality policy, timing policy, final subtitle stability, save format, render/export, packaging, release, commit, and push behavior were not changed.
- 남은 위험:
  - The accepted 180s X5 run is a project-reference smoke, not NAS HeyDealer ground truth.
  - Under the current owner directive, it must not be used as the next latency-trim acceptance substitute; the NAS HeyDealer 3-minute reference is required first.

## X5 Local Reference Fixture Smoke - 2026-06-27

- 실행 모드: source-app generation latency validation hardening, short-loop reference-scored X5 smoke.
- 결과: pass for local 60s reference smoke; not sufficient for broad latency-trim acceptance.
- 저장 위치:
  - Report: `output/manual_verification/latest/x5_local_reference_fixture_20260627/reference_benchmark_report.md`
  - Materialized SRT: `output/manual_verification/latest/x5_local_reference_fixture_20260627/x5_120_3s_180_3s_reference.srt`
  - Preflight: `output/manual_verification/latest/x5_local_reference_fixture_20260627/preflight/reference_fixture_availability.md`
  - Benchmark JSON: `.codex_work/benchmarks/subtitle_pipeline_variants/20260627_210811/benchmark_results.json`
  - Benchmark markdown: `.codex_work/benchmarks/subtitle_pipeline_variants/20260627_210811/benchmark_results.md`
- 수정 요약:
  - Added `tools/materialize_reference_srt.py` to convert cached reference JSON rows into a relative-time SRT fixture with a materialization report.
  - Added `tests/test_materialize_reference_srt.py` to prove clipped absolute rows become relative SRT rows with millisecond timestamps.
  - Restored a local X5 60s reference-scored smoke path using `.codex_work/bench/x5_120_3s_180_3s.wav` and `.codex_work/bench/x5_120_3s_180_3s_reference.json`.
- 검증:
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m py_compile tools/materialize_reference_srt.py tests/test_materialize_reference_srt.py tools/verify_reference_fixture_availability.py tests/test_reference_fixture_availability.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_materialize_reference_srt.py tests/test_reference_fixture_availability.py` -> `5 passed`.
  - X5 local preflight -> `ready_for_reference_scored_benchmark=true`, reference clipped segments `26`.
  - X5 local `mode_high` reference benchmark -> elapsed `29.831s`, raw/final `28/23`, quality `80.914`, text `81.734`, timing MAE `0.5608s`, final invalid/non-monotonic/overlap `0/0/0`, `stable_for_save_reopen=true`, global canvas `max_active_segments=1`.
- 자막 품질 영향:
  - None intended. This adds a fixture-materialization and validation surface only. STT2, word precision, LLM/LoRA/VAD quality policy, timing policy, final subtitle stability, save format, render/export, packaging, release, commit, and push behavior were not changed.
- 남은 위험:
  - This is only a cached 60s X5 local reference smoke.
  - The owner-required NAS HeyDealer 3-minute reference-scored acceptance run is still required before adopting STT2 collect, word precision collect, High context-boundary, worker scheduling, or cleanup latency trims.

## Reference Fixture Availability Preflight - 2026-06-27

- 실행 모드: source-app generation latency validation hardening, reference-scored fixture preflight.
- 결과: pass for preflight guard; blocked for reference-scored latency-trim acceptance until the real media/SRT fixture is restored.
- 저장 위치:
  - Report: `output/manual_verification/latest/reference_fixture_availability_20260627/reference_fixture_availability.md`
  - JSON: `output/manual_verification/latest/reference_fixture_availability_20260627/reference_fixture_availability.json`
- 수정 요약:
  - Added `tools/verify_reference_fixture_availability.py` to check real media and reference SRT readiness before running or accepting a reference-scored generation-latency benchmark.
  - Added `tests/test_reference_fixture_availability.py` to prove ready, missing-reference, and fallback-only states are classified correctly.
  - The preflight emits a warning when fallback media exists: fallback media can prove instrumentation and structural stability only, and must not approve latency trims.
- 검증:
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m py_compile tools/verify_reference_fixture_availability.py tests/test_reference_fixture_availability.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_reference_fixture_availability.py` -> `3 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/verify_reference_fixture_availability.py --fallback-media "output/_audio_fingerprint/헤이딜러_최종_2c274c4ab434764a8546/헤이딜러_최종_cleaned.wav" --output-dir output/manual_verification/latest/reference_fixture_availability_20260627` -> expected exit `2`, `blocking_reasons=["reference_media_missing","reference_srt_missing"]`, `non_reference_media_available=true`.
- 자막 품질 영향:
  - None. This changes validation readiness only; STT2, word precision, LLM/LoRA/VAD quality policy, timing policy, final subtitle stability, save format, render/export, packaging, release, commit, and push behavior were not changed.
- 남은 위험:
  - `/Volumes/photo/.../헤이딜러_최종.MP4` and the matching `.srt` are missing in this session.
  - Cached HeyDealer WAV exists but remains fallback-only; it cannot approve text/timing/segmentation-affecting latency changes.

## STT High Context Boundary Diagnostics And Accurate Test Surface - 2026-06-27

- 실행 모드: source-app generation latency instrumentation, stricter accuracy-first test method applied.
- 결과: pass for measurement coverage; no subtitle algorithm or quality policy change.
- 저장 위치:
  - Report: `output/manual_verification/latest/stt_high_context_diag_x5_audio_20260627/high_context_diag_report.md`
  - X5 audio verifier: `output/manual_verification/latest/stt_high_context_diag_x5_audio_20260627/tinyping_full_verify.json`
  - Repeat summary: `output/manual_verification/latest/stt_high_context_diag_x5_audio_20260627/repeat_summary.json`
  - Repeat CSV: `output/manual_verification/latest/stt_high_context_diag_x5_audio_20260627/repeat_summary.csv`
  - QE review handoff: `.agents/sentinel/handoffs/20260627-stt-accuracy-test-review.md`
- 수정 요약:
  - `core/engine/subtitle_context_refiner.py` now collects optional High context-boundary diagnostics without changing output rows.
  - `core/engine/subtitle_engine.py` forwards the diagnostics through the existing stage preview callback.
  - `tools/benchmark_subtitle_pipeline_variants.py` and `tools/verify_full_media_pipeline.py` now surface candidate pairs, skipped pairs, LLM calls, failed calls, changed pairs, max pairs, and elapsed time in stage spans, summary metrics, repeat JSON/CSV, and compact CLI output.
- 검증:
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m py_compile core/engine/subtitle_context_refiner.py core/engine/subtitle_engine.py tools/benchmark_subtitle_pipeline_variants.py tools/verify_full_media_pipeline.py tests/test_subtitle_context_refiner.py tests/test_benchmark_mode_profiles.py tests/test_verify_full_media_pipeline.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_subtitle_context_refiner.py tests/test_verify_full_media_pipeline.py -k "context_refiner or stage_wall_clock or repeat_summary"` -> `7 passed, 13 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_benchmark_mode_profiles.py -k "run_postprocess or stage_wall_clock_summary"` -> `3 passed, 29 deselected`.
  - X5 cached-audio 180s verifier -> pipeline `74.919s`, raw/final `43/50`, final invalid/non-monotonic/overlap `0/0/0`, `stable_for_save_reopen=true`, global max active `1`, STT2 selected `28`, word precision `9`, memory pressure `critical`; High context-boundary candidate/call/changed `4/4/0`, failed calls `0`, elapsed `32.230357s`.
  - `git diff --check -- core/engine/subtitle_context_refiner.py core/engine/subtitle_engine.py tools/benchmark_subtitle_pipeline_variants.py tools/verify_full_media_pipeline.py tests/test_subtitle_context_refiner.py tests/test_benchmark_mode_profiles.py tests/test_verify_full_media_pipeline.py` -> pass.
- 자막 품질 영향:
  - None intended. STT2, word precision, LLM/LoRA/VAD quality policy, model selection, timing policy, final subtitle stability, save format, render/export, packaging, release, commit, and push behavior were not changed.
- 남은 위험:
  - X5 cached-audio verification is not reference-scored quality acceptance.
  - The owner-required NAS HeyDealer media/SRT under `/Volumes/photo/...` are unavailable, so the next optimization candidate is blocked until that reference-scored gate can run.
  - Memory pressure still reached `critical`; pass/fail alone is not enough to close the latency item.

## STT Collect Fallback Precision Instrumentation - 2026-06-27

- 실행 모드: source-app generation latency instrumentation, stricter collect/worker test method applied.
- 결과: pass; no subtitle algorithm or quality policy change.
- 저장 위치:
  - Report: `output/manual_verification/latest/stt_collect_fallback_precision_20260627/fallback_precision_report.md`
  - Benchmark smoke: `.codex_work/benchmarks/subtitle_pipeline_variants/20260627_201523/benchmark_results.json`
  - Verifier smoke: `output/manual_verification/latest/stt_collect_fallback_precision_20260627/verify_smoke/tinyping_full_verify.json`
  - Repeat summary: `output/manual_verification/latest/stt_collect_fallback_precision_20260627/verify_smoke/repeat_summary.json`
- 수정 요약:
  - `core/audio/media_processor_transcribe_run.py` records `stt_collect_whisperkit_fallback` spans for WhisperKit zero-chunk, empty-segment, and timeout fallback into MLX.
  - `core/audio/media_processor_transcribe.py` merges child collect-worker `stt_collect_*` spans back into the parent stage-wall-clock artifact.
  - `tools/verify_full_media_pipeline.py` now exposes fallback count/total/max elapsed in `summary_metrics`, repeat summary JSON/CSV, and compact CLI output.
- 검증:
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m py_compile tools/verify_full_media_pipeline.py core/audio/media_processor_transcribe.py core/audio/media_processor_transcribe_run.py core/audio/media_processor_transcribe_recheck.py tests/test_media_processor_overlap.py tests/test_verify_full_media_pipeline.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_media_processor_overlap.py -k "collect_transcribe_result"` -> `2 passed, 103 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_verify_full_media_pipeline.py tests/test_benchmark_mode_profiles.py -k "stage_wall_clock or repeat_summary"` -> `3 passed, 43 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_stt_recheck_service.py -k "prepare_and_collect_recheck_segments or collect_and_annotate_segments"` -> `3 passed, 35 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_media_processor_overlap.py tests/test_verify_full_media_pipeline.py tests/test_benchmark_mode_profiles.py -k "collect_transcribe_result or stage_wall_clock or repeat_summary"` -> `5 passed, 146 deselected`.
  - Local 60s benchmark smoke -> elapsed `24.355s`, raw/final `2/2`, final overlap `0`, `stable_for_save_reopen=true`, global `max_active_segments=1`; fallback count `2`, total `7.962836s`, max `7.493920s`; STT2 collect `10.661352s`, word precision collect `3.640260s`.
  - Local 60s verifier smoke -> pipeline `30.374s`, raw/final `2/2`, final overlap `0`, `stable_for_save_reopen=true`, global `max_active_segments=1`; fallback count `2`, total `14.900298s`, max `7.530310s`; repeat CSV includes the fallback total column.
  - `git diff --check -- .` -> pass.
- 자막 품질 영향:
  - None intended. This is measurement and test-surface improvement only. STT2, word precision, LLM/LoRA/VAD quality policy, model selection, timing policy, final subtitle stability, save format, render/export, packaging, release, commit, and push behavior were not changed.
- 남은 위험:
  - Local 60s smoke proves the new metrics and stability fields, but it is not a NAS HeyDealer 3-minute quality acceptance substitute.
  - Next candidate should compare long-fixture collect time against fallback overhead before touching worker scheduling or cache behavior.

## STT2 / Word Precision Substage Timing Instrumentation - 2026-06-27

- 실행 모드: source-app generation latency instrumentation, stricter test method applied.
- 결과: pass; no subtitle algorithm or quality policy change.
- 저장 위치:
  - Report: `output/manual_verification/latest/stt2_word_precision_substage_timing_20260627/substage_timing_report.md`
  - Local reference smoke: `.codex_work/benchmarks/subtitle_pipeline_variants/20260627_200405/benchmark_results.json`
- 수정 요약:
  - `core/audio/stt_recheck_service.py` now records `prepare_elapsed_sec`, `collect_elapsed_sec`, `annotate_elapsed_sec`, and `total_elapsed_sec` for `prepare_and_collect_recheck_segments(...)`.
  - `core/audio/media_processor_transcribe_recheck.py` carries those values into `stt2_selective_recheck` and `word_precision` stage wall-clock spans.
  - `tools/benchmark_subtitle_pipeline_variants.py` and `tools/verify_full_media_pipeline.py` aggregate the substage elapsed fields into benchmark JSON and repeat-summary metrics/CSV.
- 검증:
  - `./venv/bin/python -m py_compile core/audio/stt_recheck_service.py core/audio/media_processor_transcribe_recheck.py tools/benchmark_subtitle_pipeline_variants.py tools/verify_full_media_pipeline.py tests/test_stt_recheck_service.py tests/test_benchmark_mode_profiles.py tests/test_verify_full_media_pipeline.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_stt_recheck_service.py -k "prepare_and_collect_recheck_segments or collect_and_annotate_segments"` -> `3 passed, 35 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_benchmark_mode_profiles.py -k "stage_wall_clock_summary"` -> `1 passed, 30 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_verify_full_media_pipeline.py -k "stage_wall_clock or repeat_summary"` -> `2 passed, 13 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_verify_full_media_pipeline.py tests/test_benchmark_mode_profiles.py` -> `46 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_stt_recheck_service.py tests/test_media_processor_overlap.py -k "word_precision or stt_recheck or duration_first or prepare_and_collect"` -> `46 passed, 96 deselected`.
  - `git diff --check -- .` -> pass.
  - Local 60s reference smoke -> elapsed `28.641s`, raw/final `2/2`, final overlap `0`, `stable_for_save_reopen=true`, global `max_active_segments=1`; STT2 total `11.258246s` with collect `11.201352s`; word precision total `4.368781s` with collect `4.304654s`.
- 자막 품질 영향:
  - None intended. This is timing instrumentation only. STT2, word precision, LLM/LoRA/VAD quality policy, model selection, timing policy, final subtitle stability, save format, render/export, packaging, release, commit, and push behavior were not changed.
- 남은 위험:
  - HeyDealer/NAS fixture path was unavailable in this session because `/Volumes` access hung, so long-fixture quality comparison was not rerun for this instrumentation slice.
  - The next latency candidate should focus on collect-time scheduling/worker behavior, not clip preparation or annotation.

## STT2 / Word Precision Context-Boundary Batch Candidate Rejection - 2026-06-27

- 실행 모드: source-app generation latency candidate, stricter test method applied.
- 결과: pass for investigation and rollback; candidate rejected, no context-boundary batch code kept.
- 저장 위치:
  - Report: `output/manual_verification/latest/stt2_word_precision_context_batch_20260627/context_batch_rejection_report.md`
  - Non-profile repeat: `output/manual_verification/latest/stt2_word_precision_context_batch_20260627/baseline_repeat2/repeat_summary.json`
  - Reference benchmark: `.codex_work/benchmarks/subtitle_pipeline_variants/20260627_194512/benchmark_results.json`
- 후보 요약:
  - Tried batching non-overlapping High context-boundary LLM pair checks into one Ollama JSON call.
  - Focused tests for the temporary batch path passed, but the real reference fixture showed output drift, so the code and added tests were reverted.
- 더 정확한 테스트 방식:
  - Non-profile repeat stayed the speed truth.
  - Reference-scored HeyDealer 180s SRT benchmark stayed the acceptance truth for quality, text score, timing MAE, final count, and overlap stability.
  - cProfile remained diagnostic only and was not used as elapsed-speed proof.
- 검증:
  - Temporary focused candidate guards passed before rejection: `tests/test_subtitle_context_refiner.py` -> `6 passed`; macro LLM focused subset -> `4 passed, 79 deselected`.
  - HeyDealer 180s non-profile repeat with candidate -> pipeline elapsed `[69.223, 67.564]`, avg `68.393s`, raw/final `58/55`, final overlap `0`, `stable_for_save_reopen=true`, global `max_active_segments=1`, STT2 selected `37`, word precision `14`, memory pressure `critical`.
  - HeyDealer 180s reference benchmark with candidate -> elapsed `64.222s`, raw/final `58/56`, quality `81.316`, text `94.241`, timing MAE `1.5958s`, segmentation `87.812`, final overlap `0`, `stable_for_save_reopen=true`, global `max_active_segments=1`; subtitle postprocess `9.879991s`, word precision `20.835965s`.
  - Accepted prior reference baseline -> quality `81.335`, text `94.267`, timing MAE `1.5958s`, segmentation `87.879`, subtitle postprocess `12.518010s`.
  - Rollback validation: `./venv/bin/python -m py_compile core/engine/subtitle_context_refiner.py tests/test_subtitle_context_refiner.py core/engine/subtitle_engine.py tests/test_subtitle_engine_settings.py` -> pass.
  - Rollback validation: `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_subtitle_context_refiner.py` -> `4 passed`.
  - Existing accepted trim guard: `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_subtitle_engine_settings.py -k "macro_gate_zero_llm_rows or batches_llm_into_macro_chunks or llm_confidence_gate_skips"` -> `4 passed, 79 deselected`.
  - Verifier/benchmark guard: `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_verify_full_media_pipeline.py tests/test_benchmark_mode_profiles.py` -> `46 passed`.
  - `git diff -- core/engine/subtitle_context_refiner.py tests/test_subtitle_context_refiner.py` -> no diff, confirming the rejected candidate code/test patch was removed.
  - `git diff --check -- .` -> pass.
- 자막 품질 영향:
  - None kept. The candidate was rejected and reverted because it slightly reduced reference quality/text/segmentation. STT2, word precision, LLM/LoRA/VAD quality policy, timing policy, final subtitle stability, save format, render/export, packaging, release, commit, and push behavior were not changed by this rejected candidate.
- 남은 위험:
  - Context-boundary LLM batching should not be retried unless batch-vs-per-pair decision parity is proven first.
  - Generation latency remains open; next candidates must target redundant waiting/cache/scheduling or proven cleanup churn without changing subtitle decisions.

## STT2 / Word Precision LLM Zero-Candidate Defer Trim - 2026-06-27

- 실행 모드: source-app generation latency trim, stricter test method applied.
- 결과: pass, first safe trim applied; overall latency remains open.
- 저장 위치:
  - Report: `output/manual_verification/latest/stt2_word_precision_llm_defer_20260627/llm_defer_report.md`
  - Non-profile repeat: `output/manual_verification/latest/stt2_word_precision_llm_defer_20260627/baseline_repeat2/repeat_summary.json`
  - Profile diagnostic: `output/manual_verification/latest/stt2_word_precision_llm_defer_20260627/profile_diagnostic/function_profile_generation_summary.json`
  - Reference benchmark: `.codex_work/benchmarks/subtitle_pipeline_variants/20260627_192926/benchmark_results.json`
- 수정 요약:
  - `core/engine/subtitle_engine.py` now defers runtime LLM model resolution and Ollama warmup until a macro LLM gate proves `llm_rows > 0`.
  - Zero-candidate macro rows continue through LoRA/Deep/STT confirmed output without preparing a local LLM that will not be called.
  - Added a regression test proving zero-candidate macro rows do not call `_resolve_runtime_llm_model`, `warmup_ollama_model`, or `ollama_split_text`.
- 더 정확한 테스트 방식:
  - Unit no-call guard for the exact zero-candidate path.
  - Focused LLM macro/gate tests for neighboring behavior.
  - Non-profile repeat for wall-clock speed truth.
  - cProfile diagnostic for ownership only.
  - Reference-scored HeyDealer 180s SRT benchmark for quality score, timing MAE, final counts, and overlap stability.
- 검증:
  - `./venv/bin/python -m py_compile core/engine/subtitle_engine.py tests/test_subtitle_engine_settings.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_subtitle_engine_settings.py -k "macro_gate_zero_llm_rows or batches_llm_into_macro_chunks or llm_confidence_gate_skips"` -> `4 passed, 79 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_subtitle_engine_settings.py -k "llm or macro or gate"` -> `17 passed, 66 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_verify_full_media_pipeline.py tests/test_benchmark_mode_profiles.py` -> `46 passed`.
  - HeyDealer 180s non-profile repeat -> pipeline elapsed `[65.317, 61.873]`, avg `63.595s`, raw/final `58/55`, final overlap `0`, `stable_for_save_reopen=true`, global `max_active_segments=1`, STT2 selected `37`, word precision `14`, memory pressure `critical`.
  - HeyDealer 180s profile diagnostic -> pipeline elapsed `65.057s`, raw/final `58/55`, final overlap `0`, `stable_for_save_reopen=true`, global `max_active_segments=1`, stage wall-clock top `word_precision=20.302507s`, cut-boundary top cumulative `0.000941s`.
  - HeyDealer 180s reference benchmark `mode_high` -> elapsed `66.007s`, raw/final `58/56`, quality `81.335`, text `94.267`, timing MAE `1.5958s`, final overlap `0`, `stable_for_save_reopen=true`, global `max_active_segments=1`; stage spans STT1 `18.117848s`, STT2 `14.458806s`, word precision `20.851735s`, subtitle postprocess `12.518010s`.
- 자막 품질 영향:
  - None. STT2, word precision, LLM/LoRA/VAD quality policy, timing policy, model selection, final subtitle stability, save format, render/export, packaging, release, commit, and push behavior were not changed.
- 남은 위험:
  - Total wall-clock did not materially improve because word precision variance rose in the reference run even though subtitle postprocess dropped. Keep the latency action item active.
  - Memory pressure still reached `critical`; next work must remain behavior-preserving and target measured redundant waiting/cache/scheduling only.

## STT2 / Word Precision Wall-Clock Stage Spans - 2026-06-27

- 실행 모드: source-app generation latency profiling with accurate wall-clock stage spans.
- 결과: pass
- 저장 위치:
  - Report: `output/manual_verification/latest/stt2_word_precision_wall_clock_20260627/wall_clock_stage_report.md`
  - Non-reference wall-clock probe: `output/manual_verification/latest/stt2_word_precision_wall_clock_20260627/wall_clock_probe/tinyping_full_verify.json`
  - Repeat summary: `output/manual_verification/latest/stt2_word_precision_wall_clock_20260627/wall_clock_probe/repeat_summary.json`
  - Reference-scored benchmark: `.codex_work/benchmarks/subtitle_pipeline_variants/20260627_191323/benchmark_results.json`
- 수정 요약:
  - `core/audio/media_processor_transcribe.py` and `core/audio/media_processor_transcribe_recheck.py` now record direct `perf_counter` spans for STT1 primary transcription, selective STT2 rescue, word timestamp precision, and VAD/STT consensus.
  - `tools/benchmark_subtitle_pipeline_variants.py` records subtitle postprocess wall-clock spans and writes a `stage_wall_clock_summary` into each variant result.
  - `tools/verify_full_media_pipeline.py` exposes stage wall-clock rollups in `summary_metrics`, markdown summaries, repeat JSON/CSV, and CLI output.
  - No runtime trim was applied in this slice; this only made the performance test more exact before any scheduling/cache change.
- 검증:
  - `./venv/bin/python -m py_compile core/audio/media_processor_transcribe.py core/audio/media_processor_transcribe_recheck.py tools/benchmark_subtitle_pipeline_variants.py tools/verify_full_media_pipeline.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_verify_full_media_pipeline.py tests/test_benchmark_mode_profiles.py` -> `46 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_stt_ensemble.py tests/test_subtitle_quality_models.py -k "word_precision or stt_anchor or vad_stt_timing_consensus or selective"` -> `6 passed, 48 deselected`.
  - HeyDealer 180s non-reference wall-clock probe -> elapsed `65.222s`, raw/final `58/55`, final overlap `0`, `stable_for_save_reopen=true`, global `max_active_segments=1`, STT2 selected `37`, word precision `14`, memory pressure `critical`; stage spans STT1 `18.162010s`, STT2 `14.360250s`, word precision `12.489603s`, VAD/STT consensus `0.000227s`, subtitle postprocess `20.108474s`.
  - HeyDealer 180s reference benchmark `mode_high` -> elapsed `65.824s`, raw/final `58/56`, quality `81.335`, text `94.267`, timing MAE `1.5958s`, final overlap `0`, `stable_for_save_reopen=true`, global `max_active_segments=1`; stage spans STT1 `19.519015s`, STT2 `14.229755s`, word precision `12.560951s`, VAD/STT consensus `0.000222s`, subtitle postprocess `19.406983s`.
- 자막 품질 영향:
  - None. STT2, word precision, LLM, LoRA, VAD, model selection, timing policy, and final subtitle behavior were not changed.
- 남은 위험:
  - The next trim candidate must come from redundant waiting, duplicate cache work, or scheduling serialization inside the measured stages; do not reduce model coverage or loosen quality gates.
  - Memory pressure still reached `critical`, so pass/fail alone is not enough performance proof.

## STT2 / Word Precision Latency Profile And Accurate Test Method - 2026-06-27

- 실행 모드: source-app generation latency profiling, stricter test method applied.
- 결과: pass
- 저장 위치:
  - Report: `output/manual_verification/latest/stt2_word_precision_latency_20260627/latency_profile_report.md`
  - Baseline repeat: `output/manual_verification/latest/stt2_word_precision_latency_20260627/baseline_repeat2/repeat_summary.json`
  - Profile diagnostic: `output/manual_verification/latest/stt2_word_precision_latency_20260627/profile_diagnostic/function_profile_generation_summary.json`
  - Reference benchmark: `.codex_work/benchmarks/subtitle_pipeline_variants/20260627_185402/benchmark_results.json`
- 수정 요약:
  - `tools/verify_full_media_pipeline.py` now records STT2/word precision counts, final invalid/non-monotonic/overlap stability, global canvas max-active stability, memory pressure, and reference-quality fields in `summary_metrics`.
  - Non-trivial verification now fails if the final native summary has invalid duration, non-monotonic order, overlap, or `stable_for_save_reopen=false`.
  - Function profile artifacts now include `function_profile_generation_summary.json/.md` with generation owner groups: STT primary, STT2 recheck, word precision, LLM refinement, VAD/STT consensus, subtitle postprocess, and cleanup trim.
  - No runtime trim was applied because the safe next step is true wall-clock stage spans inside STT/word precision before scheduling changes.
- 검증:
  - `./venv/bin/python -m py_compile tools/verify_full_media_pipeline.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_verify_full_media_pipeline.py` -> `14 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_verify_full_media_pipeline.py tests/test_benchmark_mode_profiles.py` -> `44 passed`.
  - `git diff --check -- tools/verify_full_media_pipeline.py tests/test_verify_full_media_pipeline.py` -> pass.
  - HeyDealer 180s non-profile repeat -> elapsed `[65.648, 59.402]`, avg `62.525s`, raw/final `58/55`, final overlap `0`, `stable_for_save_reopen=true`, global `max_active_segments=1`, STT2 selected `37`, word precision `14`, memory pressure `critical`.
  - HeyDealer 180s profile diagnostic -> top generation stage `stt_primary_transcribe` `45.702069s`; STT2 `27.404475s`, word precision `12.976476s`, LLM refinement `16.734457s`, subtitle postprocess `17.731724s`, cleanup trim `0.085355s`; cut-boundary top cumulative `0.000572s`.
  - HeyDealer 180s reference benchmark `mode_high` -> elapsed `62.640s`, raw/final `58/56`, quality `81.335`, text `94.267`, timing MAE `1.5958s`, final overlap `0`, `stable_for_save_reopen=true`, global `max_active_segments=1`.
- 자막 품질 영향:
  - None. STT2, word precision, LLM, LoRA, VAD, model selection, timing policy, and final subtitle generation behavior were not changed.
- 남은 위험:
  - cProfile cumulative times are non-additive and diagnostic only. Next trim work needs true wall-clock stage spans before touching scheduling/cache behavior.
  - Memory pressure still reached `critical`; do not treat pass/fail alone as performance proof.

## NLE Live Editor Diamond Cutover - 2026-06-27

- 실행 모드: source-app internal NLE runtime adoption, one live editor mutation surface cutover.
- 결과: pass
- 저장 위치:
  - Report: `output/manual_verification/latest/nle_live_editor_diamond_cutover_20260627/live_editor_diamond_cutover_report.md`
  - Passing quick QA: `output/manual_verification/latest/qa_suite_quick_nle_live_diamond_retry_20260627`
  - First failed quick QA retained for QE traceability: `output/manual_verification/latest/qa_suite_quick_nle_live_diamond_20260627`
  - Runtime route: `ui/editor/ux/editor_timeline_video.py`
  - Focused tests: `tests/test_timeline_playhead_fit.py`
- 수정 요약:
  - Routed `diamond` shared-boundary subtitle resize in `_on_seg_time_changed(...)` through runtime NLE `caption_resize` dual-write when safe.
  - On success, projected NLE rows are applied through `_reload_segments_from_list(..., preserve_view=True, mark_dirty=True)`.
  - On NLE rejection, unsupported runtime shape, or project floor-frame micro-row collapse risk, the existing Taption/legacy direct-edit path remains the fallback.
  - Removed the completed NLE runtime editing adoption item from `ACTION_ITEMS.md`; next active item is STT2 / word precision latency profiling.
- QE note:
  - First quick QA failed at `editor_compact_macau / merge_diamond` because a one-frame-ish smart-split row collapsed to zero duration in the shadow project floor-frame normalization and was removed by the NLE route.
  - Added a micro-row fallback guard and a regression test; retry quick QA passed.
- 검증:
  - `./venv/bin/python -m py_compile ui/editor/ux/editor_timeline_video.py tests/test_timeline_playhead_fit.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py -k "diamond_resize"` -> `4 passed, 148 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py -k "resize or diamond"` -> `26 passed, 126 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_dual_write.py tests/test_project_nle_operations.py tests/test_project_nle_snapshot.py tests/test_project_nle_persistence_guard.py tests/test_project_nle_runtime_cutover.py tests/test_project_nle_render_export_parity.py` -> `38 passed, 4 subtests passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_hit_targets.py tests/test_app_command_bridge.py -k "drag or gap or magnet or stt_candidate"` -> `63 passed, 163 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py tests/test_subtitle_live_editor_feed_facade.py` -> `155 passed`.
  - `AI_SUBTITLE_STUDIO_QA_USE_SOURCE=1 ./venv/bin/python tools/qa_suite_runner.py quick --output-dir output/manual_verification/latest/qa_suite_quick_nle_live_diamond_retry_20260627` -> pass, `failed_count=0`.
- 자막 품질 영향:
  - None. Runtime edit routing only. STT2, LLM, LoRA, VAD, timing policy, generation quality, visible UI/UX, save format, render/export, packaging, release, commit, and push were not changed.
- 남은 위험:
  - Only the `diamond` shared-boundary live editor surface is routed through NLE dual-write.
  - Broader live editor mutation routing should preserve the micro-row fallback or first improve project-frame normalization for one-frame subtitles.

## NLE Caption Resize Dual-Write And Accurate Test Slice - 2026-06-27

- 실행 모드: source-app internal NLE adoption, subtitle boundary resize / diamond shared-boundary slice, stricter test method applied.
- 결과: pass
- 저장 위치:
  - Report: `output/manual_verification/latest/nle_caption_resize_dual_write_20260627/caption_resize_dual_write_report.md`
  - Quick QA: `output/manual_verification/latest/qa_suite_quick_nle_caption_resize_20260627`
  - Dual-write helper: `core/project/nle_dual_write.py`
  - Focused tests: `tests/test_project_nle_dual_write.py`
  - Active queue: `ACTION_ITEMS.md`
- 수정 요약:
  - Added `apply_caption_resize_dual_write_pilot(...)` to route boundary-handle and diamond-style resize operations through runtime `NLEProjectState`, record a `caption_resize` `NLEEditorOperation`, and project back into legacy `editor_state`.
  - Preserved Taption-derived resize behavior by trimming/deleting affected neighbor rows and absorbing silence gaps before the final-overlap gate.
  - Kept final-overlap rejection in the NLE operation projection gate, so overlapped final subtitles are rejected instead of saved.
  - Updated the active queue so the next remaining NLE adoption step is one live editor mutation surface cutover.
- 더 정확한 테스트 방식:
  - New tests check operation metadata, runtime NLE projection rows, legacy editor rows, save/reload storage shape, final release-stability metrics, silent-gap absorption, diamond shared-boundary behavior, and no-mutation-on-reject behavior.
  - Existing Taption resize/diamond UI regressions and source-app quick QA were run after focused NLE tests.
- 검증:
  - `./venv/bin/python -m py_compile core/project/nle_dual_write.py tests/test_project_nle_dual_write.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_dual_write.py` -> `10 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_dual_write.py tests/test_project_nle_operations.py tests/test_project_nle_snapshot.py tests/test_project_nle_persistence_guard.py tests/test_project_nle_runtime_cutover.py tests/test_project_nle_render_export_parity.py` -> `38 passed, 4 subtests passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py -k "resize or diamond"` -> `23 passed, 126 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_hit_targets.py tests/test_app_command_bridge.py -k "drag or gap or magnet or stt_candidate"` -> `63 passed, 163 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py tests/test_subtitle_live_editor_feed_facade.py` -> `152 passed`.
  - `AI_SUBTITLE_STUDIO_QA_USE_SOURCE=1 ./venv/bin/python tools/qa_suite_runner.py quick --output-dir output/manual_verification/latest/qa_suite_quick_nle_caption_resize_20260627` -> pass, `failed_count=0`.
- 자막 품질 영향:
  - None. This adds runtime NLE operation/dual-write coverage only. STT2, LLM, LoRA, VAD, timing policy, generation quality, visible UI/UX, save format, render/export, packaging, release, commit, and push were not changed.
- 남은 위험:
  - This is not yet a live editor routing cutover. The next item must connect one editor mutation surface through NLE dual-write while preserving the existing Taption-derived behavior.
  - Persisted NLE project fields remain unapproved.

## NLE Caption Move Dual-Write And Taption Reorder Slice - 2026-06-27

- 실행 모드: source-app internal NLE adoption, subtitle segment body move / Taption neighbor reorder slice.
- 결과: pass
- 저장 위치:
  - Report: `output/manual_verification/latest/nle_caption_move_dual_write_20260627/caption_move_dual_write_report.md`
  - Dual-write helper: `core/project/nle_dual_write.py`
  - Focused tests: `tests/test_project_nle_dual_write.py`
  - Active queue: `ACTION_ITEMS.md`
- 수정 요약:
  - Added `apply_caption_move_dual_write_pilot(...)` to route final subtitle body moves through runtime `NLEProjectState`, record a `caption_move` `NLEEditorOperation`, and project back into legacy `editor_state`.
  - Added Taption-style neighbor reorder metadata: `taption_reorder`, `reorder_direction`, and `reorder_neighbor_id`.
  - Kept final-overlap rejection in the existing NLE operation projection gate, so an overlapping final subtitle move is rejected instead of saved.
  - Promoted the next active queue item to source-app NLE runtime editing adoption. Current status: `caption_resize` is now complete; one live editor mutation surface remains next.
- 검증:
  - `./venv/bin/python -m py_compile core/project/nle_dual_write.py tests/test_project_nle_dual_write.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_dual_write.py` -> `6 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_dual_write.py tests/test_project_nle_operations.py tests/test_project_nle_snapshot.py tests/test_roughcut_v2_output_compat.py` -> `30 passed, 4 subtests passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py tests/test_timeline_hit_targets.py -k "center_reorder or reorder_release or center_drag_reorders"` -> `3 passed, 296 deselected`.
- 자막 품질 영향:
  - None. This adds runtime NLE operation/dual-write coverage only. STT2, LLM, LoRA, VAD, timing policy, generation quality, visible UI/UX, save format, render/export, packaging, release, commit, and push were not changed.
- 남은 위험:
  - This is not yet a live editor routing cutover. The next item must connect one editor mutation surface through NLE dual-write before broader runtime adoption.
  - Persisted NLE project fields remain unapproved.

## Cut-Boundary Generation Latency Profile Closeout - 2026-06-27

- 실행 모드: source-app High generation profiling, owner-relevant HeyDealer first 180s, precision testing method applied.
- 결과: pass, no cut-boundary runtime trim applied.
- 저장 위치:
  - Closeout report: `output/manual_verification/latest/cut_boundary_latency_profile_20260627/latency_profile_report.md`
  - Baseline repeat: `output/manual_verification/latest/cut_boundary_latency_profile_20260627/baseline_repeat2/repeat_summary.json`
  - Profile diagnostic: `output/manual_verification/latest/cut_boundary_latency_profile_20260627/profile_diagnostic/function_profile_cut_boundary_summary.json`
  - Reference-scored benchmark: `.codex_work/benchmarks/subtitle_pipeline_variants/20260627_180138/benchmark_results.json`
  - Active queue: `ACTION_ITEMS.md`
- 수정 요약:
  - `tools/verify_full_media_pipeline.py` now writes a cut-boundary-specific cProfile summary with owner-stage grouping.
  - Added focused tests for cut-boundary profile grouping and `summary_metrics` exposure.
  - Separated real elapsed timing from profiler diagnosis: non-profile repeat is wall-clock truth, cProfile is owner diagnosis only.
  - Completed the cut-boundary latency item without changing runtime behavior because cut-boundary owner cost measured below 1ms.
  - Added the next active performance item for STT2 / word precision latency profiling with accuracy-preserving gates.
- 검증:
  - `./venv/bin/python -m py_compile tools/verify_full_media_pipeline.py tests/test_verify_full_media_pipeline.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_verify_full_media_pipeline.py -k "cut_boundary_profile or summary_metrics"` -> `4 passed, 6 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_verify_full_media_pipeline.py` -> `10 passed`.
  - Non-profile repeat HeyDealer 180s: pipeline elapsed `[63.911, 59.479]`, avg `61.695s`, raw/final `58/55`, readability `87.225`, stage trim `360.205ms`, pass.
  - Profile diagnostic HeyDealer 180s: pipeline elapsed `64.514s`, raw/final `58/55`, cut-boundary top cumulative `0.000602s`, confirmed split/snap `0.000525s`, pass.
  - Reference-scored HeyDealer 180s `mode_high`: elapsed `63.617s`, raw/final `58/56`, quality `81.335`, text score `94.267`, timing MAE `1.5958s`, final overlap `0`, `stable_for_save_reopen=true`, `stable_for_global_canvas=true`.
- 자막 품질 영향:
  - None. No generation policy, STT2, LLM, LoRA, VAD, timing, model selection, final subtitle behavior, editor UI/UX, save format, render/export, packaging, release, commit, or push behavior was changed.
- 남은 위험:
  - The wall-clock generation delay remains, but the current evidence points away from cut-boundary work and toward STT2 rescue / selective word timestamps / LLM gate / cleanup pressure.
  - The next item must not skip STT2 or loosen quality gates; it should only measure and trim redundant scheduling/cache/wait work.

## Full NLE Transition Phase 11 Cleanup - 2026-06-27

- 실행 모드: source-app internal NLE transition, rollback-preserving cleanup closeout.
- 결과: pass, no-op code cleanup
- 저장 위치:
  - Cleanup artifact: `output/manual_verification/latest/nle_phase11_cleanup_20260627/cleanup_report.md`
  - Active queue: `ACTION_ITEMS.md`
  - Handoff: `docs/HANDOFF.md`
- 수정 요약:
  - Audited the final-overlay NLE runtime cutover owner path for proven-dead legacy write paths.
  - Confirmed phase 8 cutover was a final-overlay read/provider cutover, not a broad write-path replacement.
  - Kept `_subtitle_context_window_from_segments(...)` and `_subtitle_memory_visible_window(...)` because they remain live preview, multiclip, video controls, context fallback, and rollback dependencies.
  - Removed the completed `Full NLE Transition Plan` from `ACTION_ITEMS.md`; the next active item is `Cut-Boundary Generation Latency Profiling And Safe Trim`.
- 검증:
  - `rg`/direct code reads over `core/project/nle_runtime_cutover.py`, `ui/editor/editor_segments_timeline_context.py`, runtime cache/context helpers, and focused tests -> no proven-dead legacy write path found.
  - `./venv/bin/python -m py_compile core/project/nle_runtime_cutover.py core/project/nle_render_export_parity.py core/project/nle_persistence_guard.py ui/editor/editor_segments_timeline_context.py tests/test_project_nle_runtime_cutover.py tests/test_project_nle_render_export_parity.py tests/test_project_nle_persistence_guard.py tests/test_editor_video_context_window.py tests/test_video_player_widget.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_runtime_cutover.py tests/test_editor_video_context_window.py tests/test_video_player_widget.py tests/test_project_nle_render_export_parity.py tests/test_project_nle_persistence_guard.py tests/test_project_nle_dual_write.py tests/test_project_nle_operations.py tests/test_project_nle_snapshot.py tests/test_roughcut_v2_output_compat.py` -> `123 passed, 4 subtests passed`.
  - `AI_SUBTITLE_STUDIO_QA_USE_SOURCE=1 ./venv/bin/python tools/qa_suite_runner.py quick --output-dir output/manual_verification/latest/nle_phase11_cleanup_20260627/quick_after_cleanup` -> pass, `failed_count=0`.
  - `git diff --check -- .` -> pass.
- 자막 품질 영향:
  - None. No app code was removed or changed. STT2, LLM, LoRA, VAD, cut-boundary/timing policy, model selection, final subtitle generation, render/export runtime, project save format, and visible editor UI/UX are unchanged.
- 남은 위험:
  - Full NLE transition remains a source-app internal ownership baseline, not persisted NLE project-format approval or timeline/global-canvas/save/render/export runtime cutover.

## Full NLE Transition Phase 10 Release Checkpoint Parity And Rollback Proof - 2026-06-27

- 실행 모드: source-app internal NLE transition, two consecutive post-cutover checkpoint proof.
- 결과: pass
- 저장 위치:
  - Parity artifact: `output/manual_verification/latest/nle_release_checkpoint_parity_20260627/release_checkpoint_parity_report.md`
  - Checkpoint A quick QA: `output/manual_verification/latest/nle_release_checkpoint_parity_20260627/checkpoint_a_quick`
  - Checkpoint B quick QA: `output/manual_verification/latest/nle_release_checkpoint_parity_20260627/checkpoint_b_quick`
  - Active queue: `ACTION_ITEMS.md`
  - Handoff: `docs/HANDOFF.md`
- 수정 요약:
  - Produced two consecutive post-cutover checkpoint bundles after final-overlay runtime cutover.
  - Each checkpoint ran the focused NLE runtime/save/reload/render/export/editor parity guard set and source-app quick QA.
  - Preserved rollback by removing no legacy write paths, changing no save format, and switching no timeline/global-canvas/save/render/export owner.
  - Marked phase 10 complete in `ACTION_ITEMS.md`; phase 11 narrow cleanup is now the next NLE transition item.
- 검증:
  - Checkpoint A py_compile -> pass.
  - Checkpoint A focused parity guard -> `123 passed, 4 subtests passed`.
  - `AI_SUBTITLE_STUDIO_QA_USE_SOURCE=1 ./venv/bin/python tools/qa_suite_runner.py quick --output-dir output/manual_verification/latest/nle_release_checkpoint_parity_20260627/checkpoint_a_quick` -> pass, `failed_count=0`.
  - Checkpoint B py_compile -> pass.
  - Checkpoint B focused parity guard -> `123 passed, 4 subtests passed`.
  - `AI_SUBTITLE_STUDIO_QA_USE_SOURCE=1 ./venv/bin/python tools/qa_suite_runner.py quick --output-dir output/manual_verification/latest/nle_release_checkpoint_parity_20260627/checkpoint_b_quick` -> pass, `failed_count=0`.
- 자막 품질 영향:
  - None. This phase is verification and documentation only. It does not change STT2, LLM, LoRA, VAD, cut-boundary/timing policy, model selection, final subtitle generation, render/export runtime, project save format, or visible editor UI/UX.
- 남은 위험:
  - Phase 11 cleanup can now be considered, but only as a narrow deletion pass that preserves rollback and reruns the same guard set.

## Full NLE Transition Phase 9 Cleanup Gate Audit - 2026-06-27

- 실행 모드: source-app internal NLE transition, cleanup gate audit.
- 결과: blocked for deletion, pass for gate execution
- 저장 위치:
  - Gate artifact: `output/manual_verification/latest/nle_cleanup_gate_audit_20260627/cleanup_gate_audit.md`
  - Active queue: `ACTION_ITEMS.md`
  - Handoff: `docs/HANDOFF.md`
- 수정 요약:
  - Audited whether phase 9 could remove legacy write paths.
  - Found that only one post-cutover quick QA checkpoint exists after final-overlay runtime cutover.
  - Treated the older full QA checkpoint as pre-cutover evidence, not as a post-cutover cleanup release checkpoint.
  - Did not remove any legacy write path.
  - Converted the next NLE step to phase 10 release checkpoint parity and rollback proof.
- 검증:
  - `rg`/direct file reads over `ACTION_ITEMS.md`, `AGENTS.md`, `docs/HANDOFF.md`, `docs/PROJECT_STATE.md`, `test_result.md`, and phase 8 artifacts -> completed.
  - `git diff --check -- .` -> pass.
- 자막 품질 영향:
  - None. This gate audit is documentation and execution-queue management only. It does not change STT2, LLM, LoRA, VAD, cut-boundary/timing policy, model selection, final subtitle generation, render/export runtime, project save format, or visible editor UI/UX.
- 남은 위험:
  - Legacy write-path cleanup remains unsafe until two consecutive post-cutover release checkpoints prove save/reload/export/editor parity and rollback safety.

## Full NLE Transition Phase 8 Runtime Cutover: Final Overlay - 2026-06-27

- 실행 모드: source-app internal NLE transition, single-surface runtime cutover.
- 결과: pass
- 저장 위치:
  - Cutover artifact: `output/manual_verification/latest/nle_runtime_cutover_final_overlay_20260627/final_overlay_cutover_report.md`
  - Runtime cutover helper: `core/project/nle_runtime_cutover.py`
  - Provider integration: `ui/editor/editor_segments_timeline_context.py`
  - Focused tests: `tests/test_project_nle_runtime_cutover.py`, `tests/test_editor_video_context_window.py`
  - Active queue: `ACTION_ITEMS.md`
  - Handoff: `docs/HANDOFF.md`
- 수정 요약:
  - Selected `final_overlay` as the single low-risk runtime surface.
  - Added `nle_final_overlay_segments_from_editor_rows()` to project final overlay rows through NLE caption state.
  - Normal video subtitle provider now uses NLE final-overlay rows.
  - Gap rows, live preview rows, STT preview rows, and STT candidate metadata are excluded from the final overlay.
  - Live generation preview, timeline, global canvas, save/reload, render/export execution, and project persistence remain on their existing paths.
  - Marked phase 8 complete in `ACTION_ITEMS.md`; phase 9 cleanup remains blocked until release-checkpoint parity and rollback proof exist.
  - No broad runtime conversion, visible editor UI route, subtitle quality policy, save-format approval, packaging, release, commit, or push was performed.
- 검증:
  - `tools/jammini_watchdog.sh --status` -> route visible.
  - `tools/jammini_watchdog.sh --handoff-probe` -> `20260627-161935`, handoff file visible, first line `DEX_REVIEW_READY`.
  - `./venv/bin/python -m py_compile core/project/nle_runtime_cutover.py ui/editor/editor_segments_timeline_context.py tests/test_project_nle_runtime_cutover.py tests/test_editor_video_context_window.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_runtime_cutover.py tests/test_editor_video_context_window.py -k "nle_runtime or video_context or live_preview"` -> `10 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_runtime_cutover.py tests/test_editor_video_context_window.py tests/test_video_player_widget.py tests/test_project_nle_render_export_parity.py tests/test_project_nle_persistence_guard.py tests/test_project_nle_dual_write.py tests/test_project_nle_operations.py tests/test_project_nle_snapshot.py tests/test_roughcut_v2_output_compat.py` -> `123 passed, 4 subtests passed`.
  - `AI_SUBTITLE_STUDIO_QA_USE_SOURCE=1 ./venv/bin/python tools/qa_suite_runner.py quick` -> first run `output/manual_verification/latest/qa_suite_quick_20260627_162452` failed at `open_project` with `app_unreachable`; immediate rerun `output/manual_verification/latest/qa_suite_quick_20260627_162641` passed with `failed_count=0`.
- 자막 품질 영향:
  - None. This cutover changes only the runtime provider for final overlay rows. It does not change STT2, LLM, LoRA, VAD, cut-boundary/timing policy, model selection, final subtitle generation, project save format, render/export execution, or visible editor UI/UX.
- 남은 위험:
  - Only `final_overlay` was cut over. Timeline, global canvas, save/reload, render/export, and persistence ownership remain on existing paths.
  - Phase 9 cleanup must not delete legacy write paths until two consecutive release checkpoints prove parity and rollback safety.

## Full NLE Transition Phase 7 Render/Export Parity - 2026-06-27

- 실행 모드: source-app internal NLE transition planning, phase 7 render/export parity.
- 결과: pass
- 저장 위치:
  - Parity artifact: `output/manual_verification/latest/nle_render_export_parity_20260627/render_export_parity_report.md`
  - Render/export parity helper: `core/project/nle_render_export_parity.py`
  - Focused tests: `tests/test_project_nle_render_export_parity.py`
  - Active queue: `ACTION_ITEMS.md`
  - Handoff: `docs/HANDOFF.md`
- 수정 요약:
  - Added `RenderExportParityReport` and `RenderExportSurfaceReport`.
  - Added `build_project_nle_render_export_parity_report()` and `assert_project_nle_render_export_parity()`.
  - Compared one final caption frame projection across `source_subtitles`, `final_overlay`, `global_canvas`, `roughcut_sidecar`, and `exported_assets`.
  - Locked final overlay to final captions only: no gaps and no STT candidate rows.
  - Preserved global-canvas gap and STT candidate evidence while requiring the final caption projection hash to match.
  - Checked roughcut exact-join sidecar rows against NLE markers and export render-plan rows against EDL/manifest rows.
  - Added a negative guard where export manifest drift fails the parity assertion.
  - Marked phase 7 complete in `ACTION_ITEMS.md`; the next action is phase 8 runtime cutover, one owner-approved surface at a time.
  - No runtime ownership cutover, visible editor UI route, subtitle quality policy, save-format approval, packaging, release, commit, or push was performed.
- 검증:
  - `tools/jammini_watchdog.sh --status` -> route visible.
  - `tools/jammini_watchdog.sh --handoff-probe` -> `20260627-161256`, handoff file visible, first line `DEX_REVIEW_READY`.
  - `./venv/bin/python -m py_compile core/project/nle_render_export_parity.py tests/test_project_nle_render_export_parity.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_render_export_parity.py` -> `2 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_render_export_parity.py tests/test_project_nle_persistence_guard.py tests/test_project_nle_dual_write.py tests/test_project_nle_operations.py tests/test_project_nle_snapshot.py tests/test_roughcut_v2_output_compat.py` -> `33 passed, 4 subtests passed`.
- 자막 품질 영향:
  - None. This read-only parity proof does not change STT2, LLM, LoRA, VAD, cut-boundary/timing policy, model selection, final subtitle timing/text, render execution, export execution, or visible editor UI/UX.
- 남은 위험:
  - Phase 7 proves read-only parity only; it does not switch runtime rendering/export ownership.
  - Phase 8 needs a separate owner-approved single-surface cutover target and focused rollback gate.

## Full NLE Transition Phase 6 Save/Reload Compatibility - 2026-06-27

- 실행 모드: source-app internal NLE transition planning, phase 6 save/reload compatibility.
- 결과: pass
- 저장 위치:
  - Compatibility artifact: `output/manual_verification/latest/nle_save_reload_compat_20260627/save_reload_compat_report.md`
  - Persistence guard: `core/project/nle_persistence_guard.py`
  - Focused tests: `tests/test_project_nle_persistence_guard.py`
  - Active queue: `ACTION_ITEMS.md`
  - Handoff: `docs/HANDOFF.md`
- 수정 요약:
  - Added `strip_unapproved_nle_persistence_fields()` and `assert_no_unapproved_nle_persistence_fields()`.
  - Guarded `project_io`, `project_format`, and `project_manager` save/reload boundaries.
  - Unapproved persisted `nle`, `nle_snapshot`, and disk-shaped `_nle_project_state` fields are stripped.
  - Reload/hydration can record metadata-only `_nle_persistence_quarantine`, but that quarantine report is runtime-only and removed before disk write.
  - Runtime `NLEProjectState` remains allowed in memory and is still never persisted.
  - Marked phase 6 complete in `ACTION_ITEMS.md`; the next action is phase 7 render/export parity.
  - No visible editor UI route, subtitle quality policy, save-format approval, packaging, release, commit, or push was performed.
- 검증:
  - `tools/jammini_watchdog.sh --status` -> route visible.
  - `tools/jammini_watchdog.sh --handoff-probe` -> `20260627-160313`, handoff file visible, first line `DEX_REVIEW_READY`.
  - `./venv/bin/python -m py_compile core/project/nle_persistence_guard.py core/project/project_format.py core/project/project_io.py core/project/project_manager.py tests/test_project_nle_persistence_guard.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_persistence_guard.py` -> `4 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_persistence_guard.py tests/test_project_nle_dual_write.py tests/test_project_nle_operations.py tests/test_project_nle_snapshot.py tests/test_roughcut_v2_output_compat.py` -> `31 passed, 4 subtests passed`.
- 자막 품질 영향:
  - None. This persistence guard does not change STT2, LLM, LoRA, VAD, cut-boundary/timing policy, model selection, final subtitle text/timing, render/export runtime, or visible editor UI/UX.
- 남은 위험:
  - Persisted NLE project fields remain unapproved; this phase only strips/quarantines them.
  - Phase 7 must still prove render/export parity across final projection consumers.

## Full NLE Transition Phase 5 Gap-Delete Dual-Write Pilot - 2026-06-27

- 실행 모드: source-app internal NLE transition planning, phase 5 dual-write pilot.
- 결과: pass
- 저장 위치:
  - Pilot artifact: `output/manual_verification/latest/nle_dual_write_pilot_20260627/gap_delete_pilot_report.md`
  - Dual-write helper: `core/project/nle_dual_write.py`
  - Focused tests: `tests/test_project_nle_dual_write.py`
  - Active queue: `ACTION_ITEMS.md`
  - Handoff: `docs/HANDOFF.md`
- 수정 요약:
  - Selected `gap_delete` as the low-risk dual-write pilot family.
  - Added `apply_gap_delete_dual_write_pilot()` to route one explicit gap deletion through runtime `NLEProjectState`.
  - Projected runtime NLE rows back into legacy `editor_state`.
  - Built before/after `ProjectionParityReport` and a `gap_delete` `NLEEditorOperation` with a matching undo snapshot.
  - Focused fixture proves before `gap_count=1`, after `gap_count=0`, final `overlap_count=0`, `max_active_segments=1`, candidate evidence retained in undo snapshot, and disk payload free of `_nle_project_state`, `nle`, and `nle_snapshot`.
  - Marked phase 5 complete in `ACTION_ITEMS.md`; the next action is phase 6 save/reload compatibility.
  - No visible editor UI route, save-format change, packaging, release, commit, or push was performed.
- 검증:
  - `tools/jammini_watchdog.sh --status` -> route visible.
  - `tools/jammini_watchdog.sh --handoff-probe` -> `20260627-155406`, handoff file visible, first line `DEX_REVIEW_READY`.
  - `./venv/bin/python -m py_compile core/project/nle_dual_write.py tests/test_project_nle_dual_write.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_dual_write.py` -> `3 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_dual_write.py tests/test_project_nle_operations.py tests/test_project_nle_snapshot.py tests/test_roughcut_v2_output_compat.py` -> `27 passed, 4 subtests passed`.
  - `git diff --check -- .` -> pass.
- 자막 품질 영향:
  - None. The pilot deletes only an explicit gap row and keeps final caption rows, STT2, LLM, LoRA, VAD, cut-boundary/timing policy, model selection, render/export runtime, and UI behavior unchanged.
- 남은 위험:
  - Phase 5 proves only the `gap_delete` operation family, not broad runtime NLE write ownership.
  - Phase 6 must harden save/reload compatibility against unapproved persisted NLE payloads before additional operation families are routed.

## Full NLE Transition Phase 4 Operation Model - 2026-06-27

- 실행 모드: source-app internal NLE transition planning, phase 4 operation model.
- 결과: pass
- 저장 위치:
  - Operation model artifact: `output/manual_verification/latest/nle_operation_model_20260627/operation_model_report.md`
  - Operation contract helper: `core/project/nle_operations.py`
  - Focused tests: `tests/test_project_nle_operations.py`
  - Active queue: `ACTION_ITEMS.md`
  - Handoff: `docs/HANDOFF.md`
- 수정 요약:
  - Added `NLEEditorOperation`, `NLEUndoSnapshot`, `build_nle_editor_operation()`, and `build_nle_undo_snapshot()`.
  - Covered `caption_move`, `caption_resize`, `caption_split`, `caption_merge`, `caption_delete`, `gap_generate`, `gap_delete`, `candidate_confirm`, `marker_edit`, and `roughcut_range_edit`.
  - Required a matching undo snapshot for every operation.
  - Rejected final-caption operations when after-projection has invalid duration, non-monotonic rows, final overlap, or `max_active_segments>1`.
  - Required `candidate_confirm` provenance such as `candidate_source=STT1` or `STT2`.
  - Required `roughcut_range_edit` to use `time_domain=output`.
  - Marked phase 4 complete in `ACTION_ITEMS.md`; the next action is phase 5 dual-write pilot.
  - No runtime write routing, save-format change, visible UI/UX change, packaging, release, commit, or push was performed.
- 검증:
  - `tools/jammini_watchdog.sh --status` -> route visible.
  - `tools/jammini_watchdog.sh --handoff-probe` -> `20260627-154738`, handoff file visible, first line `DEX_REVIEW_READY`.
  - `./venv/bin/python -m py_compile core/project/nle_operations.py tests/test_project_nle_operations.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_operations.py` -> `5 passed`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_operations.py tests/test_project_nle_snapshot.py tests/test_roughcut_v2_output_compat.py` -> `24 passed, 4 subtests passed`.
  - `git diff --check -- .` -> pass.
- 자막 품질 영향:
  - None. Operation/undo contract code only; STT2, LLM, LoRA, VAD, cut-boundary/timing policy, model selection, save format, render/export runtime, and UI behavior were not changed.
- 남은 위험:
  - Phase 4 defines transaction contracts but does not prove a live dual-write route.
  - Phase 5 must choose exactly one low-risk operation family and keep rollback behind projection/adapter parity gates.

## Full NLE Transition Phase 3 Read-Only Projection Parity - 2026-06-27

- 실행 모드: source-app internal NLE transition planning, phase 3 read-only projection parity.
- 결과: pass
- 저장 위치:
  - Parity artifact: `output/manual_verification/latest/nle_read_only_parity_20260627/projection_parity_report.md`
  - Read-only parity helper: `core/project/nle_projection_parity.py`
  - Focused tests: `tests/test_project_nle_snapshot.py`
  - Active queue: `ACTION_ITEMS.md`
  - Handoff: `docs/HANDOFF.md`
- 수정 요약:
  - Added `ProjectionSurfaceParity` and `ProjectionParityReport` for read-only NLE projection proof.
  - Added `build_project_nle_projection_parity_report()` and `assert_project_nle_read_only_parity()`.
  - Covered timeline, video overlay, global canvas, save/export, and roughcut parity without runtime write routing.
  - Focused fixture proves `caption_count=2`, `gap_count=1`, `candidate_count=3`, `invalid_duration_count=0`, `non_monotonic_count=0`, `overlap_count=0`, `max_active_segments=1`, `save_reload_stable=true`, `global_canvas_stable=true`, and `render_export_stable=true`.
  - Marked phase 3 complete in `ACTION_ITEMS.md`; the next action is phase 4 operation model.
  - No runtime cutover, save-format change, visible UI/UX change, packaging, release, commit, or push was performed.
- 검증:
  - `tools/jammini_watchdog.sh --status` -> route visible.
  - `tools/jammini_watchdog.sh --handoff-probe` -> `20260627-153926`, handoff file visible, first line `DEX_REVIEW_READY`.
  - `./venv/bin/python -m py_compile core/project/nle_projection_parity.py tests/test_project_nle_snapshot.py` -> pass.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_snapshot.py -k "read_only_projection_parity or compatibility_characterization or direct_srt or roughcut_exact_join"` -> `5 passed, 10 deselected`.
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_snapshot.py tests/test_roughcut_v2_output_compat.py` -> `19 passed, 4 subtests passed`.
  - `git diff --check -- .` -> pass.
- 자막 품질 영향:
  - None. Read-only projection/assertion code only; STT2, LLM, LoRA, VAD, cut-boundary/timing policy, model selection, save format, render/export runtime, and UI behavior were not changed.
- 남은 위험:
  - Phase 3 proves read-only projection parity, not live runtime NLE write ownership.
  - Phase 4 must define operation/undo transaction contracts before any dual-write pilot is considered.

## Full NLE Transition Phase 2 Domain Contract - 2026-06-27

- 실행 모드: source-app internal NLE transition planning, phase 2 domain contract.
- 결과: pass
- 저장 위치:
  - Domain contract artifact: `output/manual_verification/latest/nle_domain_contract_20260627/domain_contract.md`
  - Active queue: `ACTION_ITEMS.md`
  - Handoff: `docs/HANDOFF.md`
- 수정 요약:
  - Defined the internal NLE domain contract for `NLEDocument`, `MediaAsset`, `Clip`, `Sequence`, `CaptionSegment`, `SilenceGap`, `CandidateLane`, `TimelineMarker`, `RoughcutRange`, `EditorOperation`, `UndoSnapshot`, and `ProjectionParityReport`.
  - Separated `source`, `sequence`, `output`, and `ui` time domains.
  - Set the phase 3 read-only parity validation checklist.
  - Marked phase 2 complete in `ACTION_ITEMS.md`; the next action is phase 3 read-only parity.
  - No runtime cutover, save-format change, visible UI/UX change, packaging, release, commit, or push was performed.
- 검증:
  - `tools/jammini_watchdog.sh --status` -> route visible.
  - `tools/jammini_watchdog.sh --handoff-probe` -> `20260627-153303`, handoff file visible, first line `DEX_REVIEW_READY`.
  - `rg`/direct file reads over owner inventory, NLE snapshot/state files, and sentinel review files -> completed.
  - `git diff --check -- .` -> pass.
- 자막 품질 영향:
  - None. Planning/documentation-only; STT2, LLM, LoRA, VAD, cut-boundary/timing policy, model selection, save format, render/export runtime, and UI behavior were not changed.
- 남은 위험:
  - This contract artifact is not implementation proof.
  - Phase 3 must add or extend read-only projection parity tests before any runtime write-path cutover.

## Full NLE Transition Phase 1 Owner Inventory - 2026-06-27

- 실행 모드: source-app internal NLE transition planning, phase 1 owner inventory.
- 결과: pass
- 저장 위치:
  - Owner inventory artifact: `output/manual_verification/latest/nle_owner_inventory_20260627/owner_inventory.md`
  - Active queue: `ACTION_ITEMS.md`
  - Handoff: `docs/HANDOFF.md`
- 수정 요약:
  - Mapped current mutable owners for final subtitle rows, silence/gap rows, STT1/STT2 candidate lanes, timeline canvas state, video overlay feed, global canvas/minimap, roughcut/cut boundaries, project save/load, export/render, and undo/redo.
  - Classified current NLE surfaces as runtime-only `NLEProjectState` save projection plus read-only `NLESnapshot` render/export projection.
  - Marked phase 1 complete in `ACTION_ITEMS.md`; the next NLE planning action is phase 2 domain contract.
  - No runtime cutover, project persistence change, visible UI/UX change, packaging, release, commit, or push was performed.
- 검증:
  - `tools/jammini_watchdog.sh --status` -> route visible.
  - `tools/jammini_watchdog.sh --handoff-probe` -> `20260627-152654`, handoff file visible, first line `DEX_REVIEW_READY`.
  - `rg`/direct file reads over NLE owner files, sentinel review files, editor/timeline/project/roughcut owners -> completed.
- 자막 품질 영향:
  - None. Planning/documentation-only inventory; STT2, LLM, LoRA, VAD, cut-boundary policy, timing-quality, model selection, save format, render/export runtime, and UI behavior were not changed.
- 남은 위험:
  - This is an owner-map artifact, not implementation proof.
  - Phase 2 must define the domain contract before any new NLE runtime write path is routed.

## Taption Segment UI/UX Parity Checklist Slice - 2026-06-27

- 실행 모드: source-app Taption segment UI/UX parity checklist and focused PyQt guards.
- 결과: pass
- 저장 위치:
  - Active queue: `ACTION_ITEMS.md`
  - Checklist artifact: `output/manual_verification/latest/taption_segment_uiux_parity_20260627/checklist.md`
  - Handoff: `docs/HANDOFF.md`
- 수정 요약:
  - Added a Taption-to-source-app segment UI/UX parity matrix with `covered`, `patched-now`, and `macOS-mapped` statuses.
  - Added a canvas guard proving center segment move suppresses a single silence/gap snap candidate when no subtitle boundary owns the target.
  - Added a boundary release guard proving commit uses the visible snapped boundary rather than raw pointer intent.
  - Added an editor timing guard proving center move over one silence/gap absorbs the gap without saving a final subtitle overlap.
  - Added an inline editor guard proving one-word up/down arrow navigation stays in edit mode.
  - Added Taption-style immediate neighbor reorder preview for center body drag while preserving existing overwrite/trim behavior for partial overlap moves.
  - Added release/commit routing for `center_reorder_left/right` so the document reloads in timeline order and does not save a final overlap.
  - Completed and removed the Taption segment parity item from `ACTION_ITEMS.md`; evidence remains in this result, `docs/HANDOFF.md`, and the checklist artifact.
- 검증:
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_hit_targets.py -k "one_word_arrow or center_segment_move or boundary_release or stt_candidate"` -> `10 passed, 138 deselected`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py -k "single_gap or center_drag or resize_overwrites"` -> `4 passed, 144 deselected`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_hit_targets.py -k "reorders_across_adjacent or reorder_release or center_drag_can_move_across"` -> `3 passed, 147 deselected`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py -k "center_reorder_commit or center_drag_right_preserves or center_drag_left_preserves"` -> `3 passed, 146 deselected`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_hit_targets.py tests/test_app_command_bridge.py -k "drag or gap or magnet or stt_candidate or boundary_release or one_word_arrow or reorder"` -> `65 passed, 161 deselected`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py tests/test_subtitle_live_editor_feed_facade.py` -> `152 passed`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py -k "center_reorder or center_drag or single_gap or resize_overwrites"` -> `5 passed, 144 deselected`
  - `./venv/bin/python -m py_compile ui/editor/ux/timeline_canvas_editing.py ui/editor/ux/timeline_subtitle_segment_editing.py ui/editor/ux/editor_timeline_video.py tests/test_timeline_hit_targets.py tests/test_timeline_playhead_fit.py` -> pass
  - `git diff --check -- .` -> pass
- 자막 품질 영향:
  - None. No STT2, LLM, LoRA, VAD, cut-boundary, timing-quality, model-selection, save-format, release, tag, push, packaging, or DMG behavior changed.
- 남은 위험:
  - No live manual screenshot/video proof was captured for this checklist slice; coverage is focused offscreen widget/unit tests plus the earlier source-app quick QA in the parent parity patch.
  - Taption touch-only haptic gestures remain intentionally macOS-mapped and were not copied as new visible input behavior.

## Taption Segment Editing Parity - 2026-06-27

- 실행 모드: source-app Taption-derived segment editing parity patch.
- 결과: pass
- 저장 위치:
  - Handoff: `docs/HANDOFF.md`
  - Quick QA artifact: `output/manual_verification/latest/qa_suite_quick_20260627_141230`
  - Active queue source: `ACTION_ITEMS.md`
- 수정 요약:
  - Preserved STT1/STT2 raw candidate lanes as editor evidence while preventing STT preview rows from drawing on the video subtitle overlay once final rows exist.
  - Strengthened final subtitle summary stability so `stable_for_save_reopen` requires `invalid_duration_count=0`, `non_monotonic_count=0`, and `overlap_count=0`.
  - Added Taption-style center segment drag snap filtering: when movement crosses a silence/gap toward a real subtitle boundary, the gap candidate is suppressed so the subtitle boundary owns the snap guide.
  - Added regression coverage for video overlay final-only filtering, gap-beyond-subtitle snap priority, and overlap-as-unstable final summary behavior.
- 검증:
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py tests/test_subtitle_live_editor_feed_facade.py` -> `150 passed`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_hit_targets.py tests/test_app_command_bridge.py -k "drag or gap or magnet or stt_candidate"` -> `60 passed, 161 deselected`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_native_subtitle_segments.py tests/test_native_subtitle_stt_segments.py tests/test_video_player_widget.py` -> `87 passed`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_segment_reload.py -k "stt_candidate or live_stt_preview or stt_preview"` -> `32 passed, 56 deselected`
  - `./venv/bin/python -m py_compile ui/editor/editor_segments_timeline_context.py ui/editor/editor_segments_stt_selection_flow.py ui/editor/video_player_subtitles.py core/native_subtitle_segments.py tools/benchmark_subtitle_pipeline_variants.py ui/editor/ux/timeline_subtitle_segment_editing.py ui/editor/ux/timeline_canvas_editing.py tests/test_timeline_playhead_fit.py tests/test_timeline_hit_targets.py tests/test_video_player_widget.py tests/test_native_subtitle_segments.py tests/test_benchmark_mode_profiles.py` -> pass
  - `git diff --check -- .` -> pass
  - `AI_SUBTITLE_STUDIO_QA_USE_SOURCE=1 ./venv/bin/python tools/qa_suite_runner.py quick` -> pass, `failed_count=0`
- 자막 품질 영향:
  - None intended. STT2, LLM, LoRA, VAD, cut-boundary quality policy, model selection, save format, release, tag, push, packaging, and DMG behavior were not changed.
- 남은 위험:
  - No live screenshot/video proof was captured for this patch; coverage is focused offscreen tests plus source-app quick QA.

## Post-Generation Editor Readiness And Verification Index Closeout - 2026-06-27

- 실행 모드: source-app post-generation editor readiness closeout with owner-limited NAS HeyDealer 180s proof.
- 결과: pass
- 저장 위치:
  - Active queue cleanup: `ACTION_ITEMS.md`
  - Handoff: `docs/HANDOFF.md`
  - Verification index: `output/manual_verification/latest/post_generation_editor_readiness_index_20260627/verification_index.md`
  - HeyDealer benchmark JSON: `.codex_work/benchmarks/subtitle_pipeline_variants/20260627_031030/benchmark_results.json`
  - HeyDealer benchmark summary: `.codex_work/benchmarks/subtitle_pipeline_variants/20260627_031030/benchmark_results.md`
- 수정 요약:
  - Added a post-generation pending-cleanup guard proving `status`, playback, edit/commit, timeline fit, and global save commands stay responsive before heavier cleanup finishes.
  - Added a subtitle-time-edit interaction guard proving zoom in/out, fit, time-window, subtitle magnet, playback, save, footer, and global menu surfaces remain responsive after a time edit.
  - Added an offscreen editor-shell geometry guard proving post-generation cleanup does not resize `MainWindow`, workspace splitter, editor frame, video frame, timeline frame, bottom work panel, or global menu bar.
  - Added the requested dimmed neon-green completed state for the bottom `정밀` button after successful precision refinement.
  - Removed the completed `Post-Generation Editor Readiness And Verification Index` item from `ACTION_ITEMS.md` and compacted `docs/HANDOFF.md` to current rolling state.
- 검증:
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_app_command_bridge.py tests/test_sidebar_terminal_layout.py tests/test_global_menu_bar.py tests/test_editor_precision_refine.py -k "post_generation_pending_cleanup_keeps_editor_commands_interactive or subtitle_time_edit_leaves_editor_controls_interactive or post_generation_cleanup_keeps_editor_shell_geometry_stable or precision_button or precision_refine_applies_quality_timing_and_magnet_result"` -> `7 passed, 190 deselected`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/benchmark_subtitle_pipeline_variants.py --suite modes --variants mode_high --media "/Volumes/photo/22_유튜브영상_개인/[20260209]헤이딜러광고/헤이딜러_최종.MP4" --reference-srt "/Volumes/photo/22_유튜브영상_개인/[20260209]헤이딜러광고/헤이딜러_최종.srt" --start-sec 0 --duration-sec 180 --keep-artifacts` -> pass
- HeyDealer 180s result:
  - variant: `mode_high`
  - elapsed_sec: `65.383`
  - raw/final: `58/56`
  - quality_score: `81.335`
  - text_score: `94.267`
  - timing_mae_sec: `1.5958`
  - readability_score: `88.406`
  - `stable_for_save_reopen=true`
  - `stable_for_global_canvas=true`
- 자막 품질 영향:
  - No subtitle quality policy, STT2, LLM, LoRA, VAD, timing, model-selection, save-format, release, tag, push, packaging, or DMG behavior changed.
  - Real-media validation was limited to the owner-requested NAS HeyDealer first 180 seconds.
- 남은 위험:
  - Macau/X5/Tinyping artifacts in the verification index are historical or manual-only references, not fresh gates for this closeout.
  - No live screenshot/video proof was captured; UI-frame stability is covered by offscreen geometry assertions.

## Post-Generation Editor Command Readiness Guard - 2026-06-27

- 실행 모드: source-app command-surface regression guard for post-generation editor readiness.
- 결과: pass
- 저장 위치:
  - Active queue: `ACTION_ITEMS.md`
  - Guard test: `tests/test_app_command_bridge.py`
  - Handoff: `docs/HANDOFF.md`
- 수정 요약:
  - Added `test_post_generation_pending_cleanup_keeps_editor_commands_interactive`.
  - The test holds post-generation GC/model-release in a pending state, then verifies `status`, playback, smart-split edit/commit, timeline fit, and global save commands still respond before cleanup completes.
  - Runtime code was not changed.
- 검증:
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_app_command_bridge.py -k "post_generation_pending_cleanup_keeps_editor_commands_interactive"` -> `1 passed, 74 deselected`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_app_command_bridge.py tests/test_editor_autosave_cleanup.py tests/test_sidebar_terminal_layout.py -k "post_generation_pending_cleanup_keeps_editor_commands_interactive or status_command_reports_current_runtime_snapshot or editor_playback_play_command_marks_center_lock or editor_timeline_view_command_exercises_zoom_and_fit or global_menu_action_save_uses_center_save_button_path or set_process_completed_defers_cleanup_bundle_until_next_event_turn or generation_idle_cleanup_clears_busy_surfaces_and_prefetch_cache or post_generation_gc_defers_cache_trim_while_playback_runtime_is_reserved or prioritize_video_playback_runtime_defers_heavy_release_while_starting_playback or prioritize_manual_editor_interaction_runtime_defers_heavy_release_while_editing"` -> `10 passed, 218 deselected`
- 자막 품질 영향:
  - None. Test-only command readiness guard; no subtitle timing, STT2, LLM, LoRA, VAD, model-selection, save-format, UI/UX, release, tag, push, or DMG behavior changed.
- 남은 위험:
  - `ACTION_ITEMS.md` item 1 step 3 still needs a fuller editor interaction-lock regression after timestamp/subtitle editing.

## NLE Slice 4 mutable owner pilot - 2026-06-27

- 실행 모드: source-app runtime-only NLE mutable owner pilot for project load/save.
- 결과: pass
- 저장 위치:
  - Action source: `NLE_Action.md`
  - Runtime owner: `core/project/nle_project_state.py`
  - Persistence guards: `core/project/project_io.py`, `core/project/project_format.py`, `core/project/project_manager.py`
  - Guard tests: `tests/test_project_nle_snapshot.py`, `tests/test_project_context.py`, `tests/test_project_segment_reload.py`, `tests/test_editor_srt_open_refresh.py`, `tests/test_roughcut_engine1.py`, `tests/test_roughcut_v2_output_compat.py`, `tests/test_roughcut_ui_v2.py`
  - Jammini review: `.agents/sentinel/handoffs/20260627-015946-nle-slice-4-mutable-owner-review.md`
- 수정 요약:
  - Added runtime-only `NLEProjectState` hydration from legacy project payloads.
  - Routed `save_project()` editor rows through NLE state before writing the existing legacy project shape.
  - Added dual-write assertions for row count, frame timing, gap status, and text drift.
  - Stripped `_nle_project_state`, `nle`, and `nle_snapshot` before `.aissproj` writes.
  - Preserved explicit save gap rows through the NLE/save projection route.
  - Removed completed Slice 4 from `NLE_Action.md`.
- 검증:
  - `./venv/bin/python -m py_compile core/project/nle_project_state.py core/project/project_io.py core/project/project_format.py core/project/project_manager.py tests/test_project_nle_snapshot.py` -> pass
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_snapshot.py -k "runtime_nle or save_project_routes or direct_srt_rows or roughcut_exact_join_marker_parity or compatibility_characterization or project_file_roundtrip"` -> `6 passed, 8 deselected`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_snapshot.py tests/test_project_context.py tests/test_project_segment_reload.py tests/test_editor_srt_open_refresh.py` -> `204 passed, 4 subtests passed`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_roughcut_engine1.py tests/test_roughcut_v2_output_compat.py tests/test_roughcut_ui_v2.py` -> `71 passed`
  - `git diff --check -- .` -> pass
- 자막 품질 영향:
  - None intended. This changes runtime project state ownership and save projection only; no STT2, LLM, LoRA, VAD, model-selection, UI/UX labels/layout/colors/menus/popups, release, tag, push, or DMG behavior changed.
- 남은 위험:
  - Timeline canvas state ownership remains future work and requires a new explicit slice before implementation.

## NLE Slice 3 preview cache / skimming - 2026-06-27

- 실행 모드: source-app preview/skimming cache with nonblocking UI-thread behavior.
- 결과: pass
- 저장 위치:
  - Action source: `NLE_Action.md`
  - Runtime cache: `core/runtime/preview_frame_cache.py`, `core/runtime/temp_workspace.py`
  - UI owners: `ui/editor/video_player_surface.py`, `ui/editor/video_player_widget.py`
  - Guard tests: `tests/test_preview_frame_cache.py`, `tests/test_video_player_widget.py`, `tests/test_timeline_playhead_fit.py`
  - Jammini prep/review: `.agents/sentinel/handoffs/20260627-014209-nle-slice-3-preview-cache-prep.md`, `.agents/sentinel/handoffs/20260627-014650-nle-slice-3-workflow-review.md`
- 수정 요약:
  - Added temp-workspace `Preview/FrameThumbnails` cache and nearest-frame lookup for skimming thumbnails.
  - Changed paused `preview_seek()` thumbnail handling so cache hits display immediately and cache misses schedule a throttled background worker instead of synchronous UI-thread thumbnail generation.
  - Added worker flood and stale-paint protection while a preview-frame worker is active.
  - Removed completed Slice 3 from `NLE_Action.md`.
- 검증:
  - `./venv/bin/python -m py_compile core/runtime/temp_workspace.py core/runtime/preview_frame_cache.py ui/editor/video_player_widget.py ui/editor/video_player_surface.py tests/test_preview_frame_cache.py tests/test_video_player_widget.py` -> pass
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_preview_frame_cache.py tests/test_video_player_widget.py -k "preview_frame_cache or preview_seek or processing_thumbnail"` -> `8 passed, 72 deselected`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py -k "scrub_updates_playhead_immediately_and_uses_lightweight_preview_seek or scrub_throttles_video_seek_during_fast_mouse_moves or timing_drag_preview_updates_playhead_and_uses_lightweight_preview_seek or auto_cut_boundary_preview_moves_playhead_without_thumbnail_work"` -> `4 passed, 143 deselected`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_video_preview_proxy.py tests/test_preview_frame_cache.py` -> `6 passed`
  - `git diff --check -- .` -> pass
- 자막 품질 영향:
  - None. Preview/skimming UI responsiveness only; no cut-boundary proof route, subtitle timing, STT2, LLM, LoRA, VAD, model-selection, save-format, release, tag, push, or DMG behavior changed.

## NLE Slice 2 source-fps cut-boundary scout - 2026-06-27

- 실행 모드: source-app source-fps cut-boundary scout and exact-frame fixture proof.
- 결과: pass with remaining false-negative risk
- 저장 위치:
  - Action source: `NLE_Action.md`
  - Runtime owner: `core/cut_boundary_auto_scan.py`
  - Verifier: `tools/verify_cut_boundary_source_fps_scout.py`
  - Fixture artifact: `output/manual_verification/latest/nle_slice2_source_fps_scout_20260627/source_fps_scout.json`
  - Jammini review: `.agents/sentinel/handoffs/20260627-013802-nle-slice-2-scout-review.md`
- 수정 요약:
  - Preserved exact source-fps frame timing before display-second rounding, preventing 60000/1001fps target frames such as `2677` from falling to `2676`.
  - Added 60fps/source-fps opt-in proof for the fixed 60000/1001fps fixture.
  - Added bounded score metadata trace events for early and late cut-boundary candidates.
  - Added a target-frame verifier and removed completed Slice 2 from `NLE_Action.md`.
- 검증:
  - `./venv/bin/python -m py_compile core/cut_boundary_auto_scan.py tools/verify_cut_boundary_source_fps_scout.py tests/test_cut_boundary_auto_scan_backend.py` -> pass
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_cut_boundary_auto_scan_backend.py` -> `34 passed`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_cut_boundary_auto_scan_backend.py tests/test_mode_policy.py -k "pipe_fps or source_fps or precise_timing or trace_cut_boundary_rows or dense_flow or runtime_modes_apply_stage_policy"` -> `9 passed, 35 deselected`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_subtitle_boundary_alignment.py tests/test_project_context.py -k "cut_boundary or cut_boundaries or cut_frame_2677"` -> `6 passed, 93 deselected`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/verify_cut_boundary_source_fps_scout.py "/Users/u_mo_c/Library/Mobile Documents/com~apple~CloudDocs/AI_EDIT/내 프로젝트 (3).MP4" --output-dir output/manual_verification/latest/nle_slice2_source_fps_scout_20260627` -> pass; `frame_preserved=true` for `2766` and `2677`, `candidate_detected=false` for both.
  - `git diff --check -- .` -> pass
- 자막 품질 영향:
  - Confirmed-cut split/snap behavior remains covered by existing tests; no STT2, LLM, LoRA, VAD, model-selection, save-format, UI/UX, release, tag, push, or DMG behavior changed.
- 남은 위험:
  - The fixed frames are preserved but not newly detected by the current low-res score threshold. Automatic detection tuning remains open if the owner expects these frames to be found without preexisting confirmed cut evidence.

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
