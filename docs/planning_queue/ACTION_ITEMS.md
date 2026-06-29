<!--
Document-Version: 04.01.32-source-app
Phase: SOURCE_APP_CONTINUATION_V4_1_0
Last-Updated: 2026-06-29
Updated-By: Codex
Purpose: Grouped active execution plan, release gates, QA gates, and rollback rules.
-->
# ACTION_ITEMS.md - Grouped Active Execution Plan

This file is the single source of truth for active execution groups. Completed
history lives in `docs/planning_queue/COMPLETED_ACTION_ITEMS.md`; do not copy
completed proof logs back into this active queue.

## Hard Rules

- 자막 품질이 속도보다 우선입니다.
- UI/UX는 대표님 명시 요청 없이 변경하지 않습니다.
- 모델 축소, STT2 생략, LLM 생략, 품질 게이트 완화는 기본 최적화 후보가 아닙니다.
- Apple Silicon에서는 Apple Neural Engine, 즉 `ANE` 기준으로 표현합니다.
- PyTorch MPS는 과거 `metal gpu stream` crash 근거가 있으므로 production default가 아니라 격리 실험 후보로만 둡니다.
- 대표님 명시 재지시 전까지 native migration, Swift 재작성, 별도 네이티브 앱 전환은 active queue에 올리지 않습니다.
- 자막 에디터 상호작용 표면은 2D-only입니다. QML SceneGraph, OpenGL/Metal-backed UI surface, 3D view를 새 default로 도입하지 않습니다.
- 아이디어 발굴 또는 실행 전 `docs/planning_queue/waste_action_item.md`와 `docs/planning_queue/lesson_n_learned.md`를 먼저 읽고, 폐기된 아이디어를 새 근거 없이 반복하지 않습니다.
- 실패/무효 후보는 `docs/planning_queue/waste_action_item.md`에 hypothesis, change, metrics, quality, artifact, rejection reason을 남깁니다.
- 반복하면 안 되는 진단/실험/운영 실수는 `docs/planning_queue/lesson_n_learned.md`에 남깁니다.
- owner 파일, 검증 절차, 구조 경계, 다음 세션 인수인계에 영향을 주는 변경은 같은 작업 안에서 관련 `docs/*.md`와 `docs/HANDOFF.md`까지 함께 갱신합니다.
- 정상 완료된 item은 이 파일에서 삭제하고 `docs/planning_queue/COMPLETED_ACTION_ITEMS.md`로 분리합니다.
- 상세 검증 증거는 필요할 때 `docs/quality_validation/test_result.md`, release note, `output/manual_verification/latest/`, `docs/planning_queue/waste_action_item.md`, 또는 `docs/planning_queue/lesson_n_learned.md`에 남깁니다.
- Root development docs policy: repository root keeps `AGENTS.md` only. New or moved development docs must live under `docs/`.

## Active Execution Groups

### G0. Mac App Store Launch Program

Goal: Make the current macOS source app releasable through the Mac App Store by closing packaging, signing, sandbox, App Store Connect validation, and owner-metadata gates without weakening subtitle quality or changing UI/UX.

Status: active blocker-closure group. Owner approval for App Store packaging/signing/upload/metadata execution was granted on 2026-06-28 and reconfirmed on 2026-06-29; final App Store `.pkg`, validation, upload, and submission remain blocked until the required Apple Distribution/Installer identities and owner metadata values are available. Latest current-version refresh is archived in `docs/planning_queue/COMPLETED_ACTION_ITEMS.md#v040131-g0-app-store-current-version-readiness-refresh`.

Current baseline:

- App version: `04.01.32`.
- Submission target: Mac App Store signed `.pkg` built from a sandboxed signed `.app`.
- Packaging scripts: `packaging/macos/build_app_bundle.sh`, `packaging/macos/sign_app_bundle.sh`, `packaging/macos/validate_app_bundle.sh`, `packaging/macos/build_app_store_pkg.sh`, `packaging/macos/upload_app_store_build.sh`.
- Entitlements: `packaging/macos/AI Subtitle Studio.entitlements`.
- Current readiness doc: `docs/APP_STORE_SUBMISSION_READINESS.md`.
- Latest audit artifact: `output/manual_verification/latest/app_store_current_blocker_recheck_v040131_20260629_1608/app_store_readiness_audit.md`.
- Latest metadata owner-input package: `output/manual_verification/latest/app_store_metadata_owner_input_template_v040131_20260629_1625/app_store_metadata_owner_input_package.md`.
- Latest source quick QA baseline: `output/manual_verification/latest/qa_suite_quick_v040117_20260629_0929/suite_result.md`.
- Latest packaging evidence: `output/manual_verification/latest/app_store_owner_approval_packaging_20260628_2220/`.
- Current audit state: `local_packaging_ready=true`, `app_store_submission_ready=false`, overall stoplight `red`, blocker count `25`; version lock and packaging template gates are green, while signed-artifact proof, sandbox smoke, App Store Connect validation, signing identities, and owner metadata remain red. The current blocker groups are `signed_artifacts=3`, `sandbox_smoke=1`, `app_store_connect=1`, `signing_identities=4`, and `owner_metadata=16`. Owner approval for packaging/signing/upload/metadata execution exists, but the exact signed `.pkg`, strict App Store-candidate `codesign`, `pkgutil --check-signature`, sandbox workflow smoke, App Store Connect validation, upload/submission proof, and owner metadata values JSON remain incomplete. Upload mode now also requires `AI_SUBTITLE_STUDIO_APP_STORE_UPLOAD_CONFIRMED=1`, `APP_STORE_READINESS_JSON`, exact `.pkg` binding, no blockers, and all submission gates true. Owner metadata is not ready until explicit values JSON supplies field values, owner approval evidence, public URL owner-control confirmation, App Store Connect metadata, screenshot signed-candidate binding, and forbidden-copy scan pass. The latest owner-input package is collection evidence only: `not_submission_proof=true`, `owner_input_complete=false`, `app_store_submission_ready=false`, pending owner-input metadata `8/8`, pending App Store Connect metadata `8`, owner values preflight `false`, and forbidden-claim scan `pass`. The latest source quick QA baseline passed with `profile=quick`, `scenario_count=1`, `failed_count=0`, scenario `editor_compact_macau`; this is source-app editor workflow baseline only and not signed package, sandbox smoke, App Store validation/upload/submission, or owner metadata proof.
- Developer ID beta `.dmg` remains a separate opt-in track and is not App Store submission proof.

Detailed plan:

1. Owner input package
   - Decide app name, subtitle, category, keywords, support URL, privacy policy URL, marketing URL, review notes, age rating, screenshots, and release-note copy.
   - Confirm App Privacy answers for local media, audio/STT, optional network/model calls, diagnostics, crash/analytics collection, and user data retention.
   - Confirm Export Compliance answers, including encryption/network behavior.
   - Verify Apple Developer team, App Store Connect app record, bundle ID, SKU, primary locale, and paid/free availability.

2. Runtime sandbox compatibility
   - Run current source quick QA before packaging to freeze behavior baseline.
   - Build a local app bundle only after owner approval. The 2026-06-28 owner-approved local bundle/signing smoke completed with Apple Development identity only; rerun with Apple Distribution identity for submission proof.
   - Smoke sandboxed launch, user-selected media open, subtitle generation path, audio/STT access, network/model behavior, save/reopen, SRT export, rendered subtitle output, and cleanup/quit.
   - If sandbox breaks normal editor workflows, stop release packaging and create a separate sandbox-compatibility fix item.

3. Signing and package proof
   - Sign nested binaries and the outer `.app` with the correct Apple Distribution identity and App Store entitlements.
   - Run strict `codesign --verify --deep --strict --verbose=2`.
   - Build the Mac App Store `.pkg` with the installer identity.
   - Run `pkgutil --check-signature` and store the output under `output/manual_verification/latest/`.

4. App Store Connect validation
   - Run Transporter/App Store Connect validation with `packaging/macos/upload_app_store_build.sh validate`.
   - Treat validation output as proof only when it names the exact package and exits cleanly.
   - Upload approval has been granted by the owner for this App Store lane, but do not upload until the exact signed `.pkg`, validation output, and owner metadata package are ready.

5. Submission assembly
   - Attach screenshots, release notes, privacy answers, export compliance, sandbox entitlement explanation, and review notes.
   - Confirm no metadata overclaims speed, native migration, App Store readiness, or unsupported format behavior.
   - Submission approval exists for this App Store lane; submit only after the exact signed `.pkg`, validation output, and owner metadata package are complete.

6. Post-submission / release readiness
   - Track Apple review questions separately from local QA.
   - If Apple rejects for sandbox, privacy, entitlement, package, or metadata reasons, create a narrow fix item with the rejection text and proof target.
   - After approval, prepare a release announcement and update `docs/release_notes/`.

Acceptance gates:

- Do not claim App Store readiness from source-app pytest or QA alone.
- Required proof for readiness: signed `.app`, strict `codesign`, signed `.pkg`, `pkgutil --check-signature`, sandbox smoke, App Store Connect validation output, and completed owner metadata.
- Do not submit, notarize, tag, build DMG, or release externally beyond the owner-approved Mac App Store lane without explicit owner approval; upload still requires an exact signed `.pkg` and validation artifact.
- Keep user-visible UI/UX and subtitle quality behavior unchanged unless the owner explicitly approves submission-driven changes.

Rollback:

- Packaging/signing changes should stay under `packaging/macos/` and release docs unless a sandbox runtime defect requires app code changes.
- If a packaging step fails, preserve logs and return to the last known source-app QA baseline before making runtime changes.

### G1. STT2 / Word Precision Generation Latency Profiling And Accuracy-Preserving Trim

Goal: Reduce subtitle-generation latency only where same-fixture proof shows no subtitle-quality, timing, segmentation, save/reopen, or final-overlay regression.

Status: active owner-review gate. Archive pointer: `docs/planning_queue/COMPLETED_ACTION_ITEMS.md#stt2--word-precision-generation-latency-profiling-and-accuracy-preserving-trim`. Latest review-packet refresh is archived in `docs/planning_queue/COMPLETED_ACTION_ITEMS.md#v040131-g1-stt-cache-default-review-packet-evidence-binding-refresh`.

Current baseline:

- Representative HeyDealer first-180s STT1 plus STT2/word collect-cache write/hit backfill is strict-accepted.
- `stt_recheck_collect_cache_enabled=false` and `stt_primary_collect_cache_enabled=false` remain production defaults until explicit owner approval.
- Latest strict real-media collect-cache backfill refresh: `output/manual_verification/latest/stt_cache_backfill_real_nas_20260628_2202/`; preflight passed, write/hit accepted, elapsed `177.888s -> 1.183s`, raw/final/reference `58/56/89`, quality/text/timing `93.766/94.267/0.5808s`, final invalid/non-monotonic/overlap `0/0/0`, final last end/duration bound `180.0/180.0`, global max active `1`, STT1/STT2/word provider calls `true -> false`, and timeout audit reported `timeout_detected=false`.
- Latest collect-cache default review packet: `output/manual_verification/latest/stt_cache_default_review_packet_v040131_20260629_1527/stt_cache_default_review_packet.md`; status `owner_review_required`, `production_defaults_unchanged=true`, `default_promotion_allowed=false`, current defaults `false/false`, selected write run `20260628_220327`, selected hit run `20260628_220718`, and decision matrix keeps STT1, STT2 recheck, and word precision cache promotion owner-approved and one-cache-at-a-time only.
- NAS HeyDealer first 180 seconds remains the owner-level gate for production-facing latency/default decisions.

Detailed plan:

1. Evidence refresh
   - Use non-profile repeat elapsed for speed truth.
   - Use cProfile only for ownership diagnosis.
   - Use reference benchmark for quality, timing, final stability, and segmentation truth.

2. Slow-run diagnosis
   - When a run is slow, run `tools/audit_stt_worker_timeout.py` against the latest slow artifact and nearest accepted baseline before proposing runtime trims.
   - Inspect `applied_segment_count`, `range_audio_sec`, `prepared_audio_sec`, STT1/STT2 collect spans, word precision spans, VAD/STT consensus, and subtitle postprocess.

3. Default-promotion review
   - Keep both collect caches disabled by default until representative NAS evidence and owner review approve promotion.
   - If approved, promote one cache at a time with a rollback commit boundary and focused proof.

4. Quality guard
   - Maintain `invalid_duration_count=0`, `non_monotonic_count=0`, `overlap_count=0`, `stable_for_save_reopen=true`, and global canvas `max_active_segments=1`.
   - Do not skip STT2, disable word precision, lower LLM/LoRA/VAD quality policy, shrink STT windows, promote Fast mode defaults, or loosen final subtitle stability gates.

5. Rejected-candidate discipline
   - Do not revive rejected shortcuts from `docs/planning_queue/waste_action_item.md`: cleanup removal, Fast mode default promotion, STT window shrinking, or speed-only native adoption.
   - If an experiment is slower, lower quality, or only wins on a short fixture while risking X5/NAS, archive it as rejected evidence.

Acceptance gates:

- Owner-level next-test gate is NAS HeyDealer first 180 seconds.
- A media/SRT pair is not reference-fit just because preflight passes; `evaluate_reference_benchmark_acceptance.py` must accept the scored run.
- Generated/X5 evidence is supporting evidence only unless the owner explicitly changes the gate.

Rollback:

- Revert scheduling/cache/deferment changes before touching subtitle-generation algorithms or quality thresholds.
- Keep old STT/word precision behavior as the default until measured proof and owner review approve a new path.

### G2. Source-App NLE / Taption Editing Continuity

Goal: Preserve the current source-app NLE runtime/session editing line while preventing accidental persisted disk-format cutover or native migration scope creep.

Status: active approved-persistence guard. Owner approval for persisted NLE/UI structure was granted on 2026-06-28 and reconfirmed on 2026-06-29; approved `nle_snapshot` compatibility metadata, top-level `nle` shadow metadata, explicit top-level `nle` canonical load opt-in, explicit standalone `nle_snapshot` canonical load-source opt-in, explicit supplemental `_nle_project_state` persistence opt-in, explicit legacy-compatible `editor_state` row replacement opt-in, and explicit final source-app project persistence load-owner policy are now available behind owner-approved policy flags. The final policy keeps the `editor_state` key as a compatibility projection and does not mean dual canonical ownership. Per-pixel drag writes and any further editor-owner expansion remain gated. Latest completed slice is archived in `docs/planning_queue/COMPLETED_ACTION_ITEMS.md#v040131-g2-final-cutover-ready-opt-in-proof`; previous legacy replacement slice is archived in `docs/planning_queue/COMPLETED_ACTION_ITEMS.md#v040130-g2-legacy-disk-shape-replacement-opt-in-proof`; previous runtime-state slice is archived in `docs/planning_queue/COMPLETED_ACTION_ITEMS.md#v040129-g2-runtime-_nle_project_state-persistence-opt-in-proof`; previous snapshot opt-in slice is archived in `docs/planning_queue/COMPLETED_ACTION_ITEMS.md#v040128-g2-nle-snapshot-standalone-canonical-load-opt-in-proof`; prior top-level opt-in slice is archived in `docs/planning_queue/COMPLETED_ACTION_ITEMS.md#v040127-g2-top-level-nle-canonical-load-opt-in-proof`; close/deferred-save vector-time boundary blocker is archived in `docs/planning_queue/COMPLETED_ACTION_ITEMS.md#v040102-nle-close--deferred-save-boundary-fix`; final-overlap deferred-save retry guard is archived in `docs/planning_queue/COMPLETED_ACTION_ITEMS.md#v040109-g3g2-final-overlap-deferred-save-retry-guard`; final save/export micro-overlap shared-boundary repair is archived in `docs/planning_queue/COMPLETED_ACTION_ITEMS.md#v040110-g2g3-final-save-export-micro-overlap-shared-boundary-repair`.

Current baseline:

- Native migration is not an active direction for this repository.
- The current Python/PyQt6 source app remains the working product line.
- Bounded runtime/session NLE mutation ownership is adopted for covered release-commit paths.
- Approved `nle_snapshot` persistence metadata can be written as compatibility metadata for explicitly marked projects.
- Approved top-level `nle` shadow metadata can be written for explicitly marked projects.
- Approved top-level `nle` canonical load opt-in can be used only when the explicit canonical-load policy is present and paired `nle` / `nle_snapshot` rows agree.
- Approved standalone `nle_snapshot` canonical load-source opt-in can be used only when the explicit snapshot canonical-load policy is present; compatibility-only, forged, empty, and ambiguous dual-owner payloads fall back to legacy `editor_state`.
- Persisted `_nle_project_state` is allowed only as an explicit supplemental runtime-state payload tied to standalone `nle_snapshot` canonical load-source opt-in. Legacy-compatible `editor_state` row replacement is allowed only as an explicit opt-in projection from the approved standalone `nle_snapshot` canonical source; the `editor_state` key remains present for compatibility. Final source-app project persistence load-owner policy is allowed only under the distinct final approval schema, with `default_project_authority=nle_snapshot`, forged final policy blocked, Direct SRT precedence preserved, roughcut/readback/cache-hit guards preserved, and no App Store/UI/STT proof implied.
- Legacy save/reopen compatibility remains mandatory.
- Latest final cutover-ready opt-in audit: `output/manual_verification/latest/nle_final_cutover_ready_v040131_20260629_150156/nle_persistence_cutover_audit.md`; `status=ready`, `app_version=04.01.31`, `prep_ready=true`, `persistence_cutover_ready=true`, `blockers=[]`, overall stoplight `green`, ready/blocked gates `12/0`, current canonical owner `nle_snapshot`, and `not_runtime_change/not_disk_format_cutover/not_ui_change=false/false/true`. The final proof is explicit owner-approved source-app project persistence load-owner evidence only: loaded/runtime/reloaded/storage snapshot/runtime/editor_state first caption text stays `final cutover canonical first`, the `editor_state` key remains as a compatibility projection, cache-hit read/resave hydrates runtime state, forged final policy is blocked, Direct SRT precedence is preserved, top-level/readback/quarantine payloads do not persist, operation roundtrip covers `11` families, and render/export/roughcut sidecar guards pass. Completed detail: `docs/planning_queue/COMPLETED_ACTION_ITEMS.md#v040131-g2-final-cutover-ready-opt-in-proof`.
- Latest legacy disk-shape replacement opt-in audit: `output/manual_verification/latest/nle_legacy_disk_shape_replacement_v040130_20260629_143522/nle_persistence_cutover_audit.md`; `status=blocked`, `app_version=04.01.30`, `prep_ready=true`, `persistence_cutover_ready=false`, `overall_stoplight=red`, ready/blocked gates `11/1`, current canonical owner `nle_snapshot`, and `not_runtime_change/not_disk_format_cutover/not_ui_change=false/true/true`. `legacy_disk_shape_replacement_allowed` is ready only for explicit owner-approved legacy-compatible `editor_state` row projection from the approved standalone `nle_snapshot` canonical source: loaded/runtime/reloaded/storage snapshot/runtime/editor_state first caption text stays `legacy replacement canonical first`, `editor_state` remains present, cache-hit read/resave hydrates runtime state, forged replacement policy is blocked, Direct SRT precedence is preserved, top-level/readback/quarantine payloads do not persist, and final cutover remains blocked. Completed detail: `docs/planning_queue/COMPLETED_ACTION_ITEMS.md#v040130-g2-legacy-disk-shape-replacement-opt-in-proof`.
- Previous runtime `_nle_project_state` persistence opt-in audit: `output/manual_verification/latest/nle_runtime_state_persistence_v040129_20260629_140053/nle_persistence_cutover_audit.md`; `runtime_project_state_persistence_allowed=ready` for explicit owner-approved supplemental payloads only, while legacy `editor_state` first caption text after resave remains `first`.
- Previous standalone NLE snapshot canonical load-source audit: `output/manual_verification/latest/nle_snapshot_canonical_load_source_v040128_20260629_1325/nle_persistence_cutover_audit.md`; `nle_snapshot_canonical_load_source_allowed=ready`, loaded/runtime/reloaded/storage `nle_snapshot` first caption text stays `snapshot canonical first`, legacy `editor_state` first caption text after resave remains `first`, and compatibility-only/forged/empty/ambiguous dual-owner payloads fall back to legacy.
- Previous canonical load-owner rollback-boundary audit: `output/manual_verification/latest/nle_load_owner_rollback_boundary_v040124_20260629_1138/nle_persistence_cutover_audit.md`; `rollback_boundary_defined=ready`, default load/resave keep legacy text `first`, and candidate `nle`/`nle_snapshot`/`_nle_project_state` ownership claims are stripped/quarantined when not explicitly approved.
- Previous canonical load-owner gate matrix audit: `output/manual_verification/latest/nle_canonical_load_owner_gate_matrix_v040123_20260629_1115/nle_persistence_cutover_audit.md`; `status=blocked`, ready/blocked gates `6/6`, and `rollback_boundary_defined` was still blocked before the current rollback-boundary proof.
- Previous top-level NLE gap projection coverage audit: `output/manual_verification/latest/nle_top_level_gap_projection_v040121_20260629_1041/nle_persistence_cutover_audit.md`; `top_level_nle_compatibility_projection_passed=true`, `top_level_nle_canonical_projection_complete=false`, `status=gap_projection_coverage_ready_blocked`, `not_runtime_change=true`, default project load remains `legacy_editor_state`, explicit top-level `nle` projection includes the legacy gap row as non-caption gap metadata, explicit/default row-caption-gap counts are both `3/2/1`, `gap_coverage_ready=true`, runtime state remains hydrated from legacy rows, resave rebuilds the shadow from legacy rows, and canonical load-owner / disk-format cutover remain disallowed. Completed detail: `docs/planning_queue/COMPLETED_ACTION_ITEMS.md#v040121-g2-top-level-nle-gap-projection-coverage-audit`.
- Previous top-level NLE compatibility projection audit: `output/manual_verification/latest/nle_top_level_compatibility_projection_v040120_20260629_1018/nle_persistence_cutover_audit.md`; this is the previous partial proof where explicit projection had caption/gap count `2/0` and `gap_coverage_ready=false`.
- Latest top-level NLE shadow metadata proof: `output/manual_verification/latest/nle_top_level_shadow_metadata_20260629_0020/nle_persistence_cutover_audit.md`; `prep_ready=true`, `top_level_nle_shadow_ready=true`, storage has approved top-level `nle` plus `nle_snapshot`, `canonical_load_owner=legacy_editor_state`, legacy rows and read-back parity are stable, runtime report/runtime state/quarantine do not persist, operation roundtrip all passed across `11` families, render/export parity passed, and full cutover remains `persistence_cutover_ready=false`.
- Latest canonical load-owner review packet: `output/manual_verification/latest/nle_canonical_load_owner_review_packet_v040119_20260629_095907/nle_canonical_load_owner_review_packet.md`; status `owner_review_required_blocked`, `canonical_load_owner_unchanged=true`, current canonical owner `legacy_editor_state`, `canonical_load_owner_change_allowed=false`, `disk_format_cutover_allowed=false`, top-level `nle` remains `shadow_metadata`, operation roundtrip `11` families passed, render/export final invalid/non-monotonic/overlap `0/0/0`, and full NLE disk-format cutover remains blocked.
- Completed close/deferred-save blocker proof: `output/manual_verification/latest/nle_close_deferred_save_v040102_20260629/close_deferred_save_report.md`; raw vector `time.start_frame/end_frame` rows no longer collapse into `nle_save_export_invalid_duration`, close-triggered deferred-save failures no longer reschedule stale retry loops, and true final overlaps still raise `nle_save_export_final_overlap`.
- Completed final-overlap deferred-save retry guard: `docs/planning_queue/COMPLETED_ACTION_ITEMS.md#v040109-g3g2-final-overlap-deferred-save-retry-guard`; `nle_save_export_final_overlap` remains a strict save/export failure, but deferred project save now treats it as nonretryable and clears stale pending snapshots instead of scheduling repeated retries. Ordinary writer failures still reschedule.
- Completed final save/export micro-overlap repair: `docs/planning_queue/COMPLETED_ACTION_ITEMS.md#v040110-g2g3-final-save-export-micro-overlap-shared-boundary-repair`; final save/export rows now repair tiny SRT/frame-quantization overlaps up to the greater of one frame or `0.035s` to a shared boundary when the later row remains valid. Broader or collapse-risk final overlaps still raise `nle_save_export_final_overlap`.

Detailed plan:

1. Keep `docs/nle_engine/NLE_Action.md` as the NLE plan and status file.
2. Keep completed NLE slices out of this active queue; use archive pointers and validation evidence instead.
3. Require fresh compatibility proof before widening beyond approved `nle_snapshot` and top-level `nle` shadow metadata.
4. Require final-overlap, global-canvas, save/reopen, render/export, and Taption rule parity proof for any new editing-owner expansion beyond the approved final source-app persistence policy.
5. Do not reopen native migration, Swift rewrite, QML/GPU timeline defaults, or per-pixel NLE writes unless the owner explicitly creates a new acceptance gate.
6. Continue only with a fresh, bounded owner-map for the next mutation or runtime-track slice; completed close/deferred-save blocker details stay in the completed archive.

Acceptance gates:

- Fresh owner-map plus focused tests before adopting any new mutation source.
- Final subtitle surfaces must preserve `invalid=0`, `non_monotonic=0`, `overlap_count=0`, and no final/STT candidate lane mixing.
- UI/UX labels, layout, shortcuts, menus, colors, and popup behavior stay unchanged without explicit owner scope.

Rollback:

- Revert new NLE owner routing before touching editor UI layout or project persistence.
- If compatibility proof fails, keep legacy subtitle rows as the save/export source and archive the failed NLE attempt.
- If the close-blocker fix risks weakening `nle_save_export_final_overlap`, rollback the close/deferred-save change first and keep the final-overlap guard strict.

### G3. Realtime NLE STT/VAD Track Visibility And Resource-Balanced Scheduling

Goal: Show STT1, STT2, and VAD as live NLE runtime tracks while subtitle generation is running, without slowing the full subtitle conversion path or weakening final subtitle quality.

Status: active guard-only queue. The representative real-media live runtime observability proof, same-media quality/speed proof, direct save/reopen/export proof, open/start/cancel/close/quit responsiveness proof, active global-canvas responsiveness proof, active-worker export final-surface regression guard, and selected stronger live active-final artifact audit are complete. No additional G3 active-final gate is currently selected; future G3 work requires a fresh bounded owner-selected gate. This is a runtime/session visualization and scheduling plan only; it does not approve persisted NLE disk-format cutover, STT2 skipping, model downsizing, quality-gate loosening, UI/UX redesign, or production default cache promotion.

Current baseline:

- First runtime owner-map/read-only projection slice is complete and archived in `docs/planning_queue/COMPLETED_ACTION_ITEMS.md#v040103-g3-runtime-nle-lane-owner-map--final-authority-guard`.
- Compact live status/feed wiring slice is complete and archived in `docs/planning_queue/COMPLETED_ACTION_ITEMS.md#v040104-g3-compact-live-status-feed`.
- Scheduler-budget telemetry slice is complete and archived in `docs/planning_queue/COMPLETED_ACTION_ITEMS.md#v040105-g3-live-nle-projection-scheduler-budget-telemetry`.
- Live runtime observability proof harness slice is complete and archived in `docs/planning_queue/COMPLETED_ACTION_ITEMS.md#v040106-g3-live-runtime-observability-proof-harness`.
- Live runtime observability strong-evidence gate slice is complete and archived in `docs/planning_queue/COMPLETED_ACTION_ITEMS.md#v040107-g3-live-runtime-observability-strong-evidence-gate`.
- Representative real-media live runtime observability proof slice is complete and archived in `docs/planning_queue/COMPLETED_ACTION_ITEMS.md#v040108-g3-real-media-live-runtime-observability-proof`.
- Final-overlap deferred-save retry guard slice is complete and archived in `docs/planning_queue/COMPLETED_ACTION_ITEMS.md#v040109-g3g2-final-overlap-deferred-save-retry-guard`.
- Final save/export micro-overlap shared-boundary repair slice is complete and archived in `docs/planning_queue/COMPLETED_ACTION_ITEMS.md#v040110-g2g3-final-save-export-micro-overlap-shared-boundary-repair`.
- Same-media benchmark acceptance and editor-sequence proof-harness guard slice is complete and archived in `docs/planning_queue/COMPLETED_ACTION_ITEMS.md#v040111-g3-same-media-benchmark-acceptance-and-editor-sequence-guard`.
- Direct-SRT app-command save/reopen/export proof slice is complete and archived in `docs/planning_queue/COMPLETED_ACTION_ITEMS.md#v040112-g3-direct-srt-app-command-savereopenexport-proof`.
- Active global-canvas responsiveness proof slice is complete and archived in `docs/planning_queue/COMPLETED_ACTION_ITEMS.md#v040114-g3-active-global-canvas-responsiveness-proof`.
- Active-worker export final-surface regression guard is complete and archived in `docs/planning_queue/COMPLETED_ACTION_ITEMS.md#v040131-g3-active-worker-export-final-surface-regression-guard`.
- Stronger live active-final artifact audit is complete and archived in `docs/planning_queue/COMPLETED_ACTION_ITEMS.md#v040131-g3-stronger-live-active-final-artifact-audit`.
- Latest real-media live proof: `output/manual_verification/latest/g3_live_nle_real_media_observability_timeout20_20260629/live_nle_runtime_proof.md`; `status=passed`, `issues=[]`, `failed_sample_count=0`, `generation_completed=true`, pre-final VAD/STT1/STT2 observations `16/172/44`, no raw leak, no final-authority drift, no projection-budget drift, and `21` snapshots.
- The same live proof run exposed an existing post-SRT-save `nle_save_export_final_overlap` save/export failure. The `v04.01.09` guard stops that failure from causing repeated deferred-save retries, and the `v04.01.10` slice repairs the observed tiny live-SRT quantization overlap for final save/export projection. Full same-media save/reopen, final-export, quality/speed, and global-canvas acceptance remain separate G2/G3 proof gates.
- The `v04.01.11` same-media benchmark proof accepted the NAS HeyDealer 0-180s High-mode run with final `0/0/0`, save/reopen stable `true`, and global max active `1`.
- The `v04.01.12` direct-SRT app-command proof closed the reachable-bridge save/project/SRT/video export and reopened-project export slice for the same media: direct save/export and reopened export both held `64` final rows/SRT blocks, and MOV output bytes were nonzero.
- The `v04.01.13` open-media generation responsiveness proof closed the same-media app-command open/start/status/cancel/close/quit slice. Evidence: `output/manual_verification/latest/g3_open_media_generation_responsiveness_v040113_cancel_20260629_083050/report.md`, `output/manual_verification/latest/g3_open_media_generation_responsiveness_v040113_close_20260629_083123/report.json`, and `output/manual_verification/latest/g3_open_media_generation_responsiveness_v040113_quit_20260629_083225/report.json`. `open-media` and `start-current-pipeline` succeeded, active samples reported `ST_PROC` with `backend_active=true`, status/guided-status command elapsed samples stayed below `0.01s` during the sampled active window, cancel returned `current_pipeline_cancel_requested` and then `ST_IDLE/backend_active=false`, and close/quit requests returned while active before the bridge became unreachable after the app exited.
- The `v04.01.14` active global-canvas responsiveness proof closed the same-media timeline/global-canvas view-control slice. Evidence: `output/manual_verification/latest/g3_global_canvas_responsiveness_v040114_20260629_084817/report.md`; `open-media` and `start-current-pipeline` succeeded, active samples reported `ST_PROC/backend_active=true`, timeline zoom/fit/time-window/max, zoom-max, play/pause, status, and guided-status all returned `ok=true`, max command elapsed was `0.267435s`, all `19` snapshots were nonzero, final track count stayed `0` in the sampled active pre-final window, and cancel returned to `backend_active=false`. Do not reuse this run as live final-surface proof because its sampled active final track count was `0`.
- The `v04.01.31` active-worker export final-surface regression guard proves the app-command `export-subtitles` boundary keeps VAD/STT1/STT2/subtitle-preview runtime-reference rows out of the exported final SRT while compact `guided-subtitle-status` keeps counts `1/1/1/1/2`, final-only save/export authority, and no raw runtime text leakage. This is a focused synthetic active-worker regression guard, not a live real-media active `final > 0` final-surface proof.
- The `v04.01.31` stronger live active-final artifact audit closes the selected stronger runtime/status artifact gate using the existing representative live proof. Evidence: `output/manual_verification/latest/g3_active_final_surface_audit_v040131_20260629_1558/g3_active_final_surface_audit.md`; `status=passed`, source live proof status `passed`, source samples `206`, failed source samples `0`, valid active-final observations `12`, max active final count `47`, exact snapshot pair `snapshots/live_nle_13_107317ms.png` at `107.317s`, final-only authority preserved, projection budget preserved, and issues `[]`. This is an offline audit of existing artifacts: source proof app version is not rebound, raw-leak evidence is derived from saved compact-contract flags and source failure lists, and it is not new live execution or save/export artifact-count proof.
- Existing runtime surfaces already preserve live STT preview rows through `_live_stt_preview_segments`, `stt_preview_source=STT1/STT2`, and global-canvas STT lane tests.
- `core/engine/subtitle_live_editor_feed.py` now exposes runtime-only `VAD`, `STT1`, `STT2`, `subtitle_preview`, and `final` track metadata. Only `final` carries save/export authority; VAD/STT/subtitle-preview tracks are reference-only.
- `status`, `ping`, and `guided-subtitle-status` now expose compact `nle_runtime_track_counts` / `nle_runtime_tracks` metadata without raw STT/VAD/subtitle-preview row text or large segment payloads, and UDP compaction preserves the count summary.
- `core/project/nle_runtime_cutover.py` rejects `_nle_runtime_role=runtime_reference_only`, non-final `_nle_runtime_track`, and `_nle_save_export_authority=false` rows from final overlay, global canvas, and save/export projection even if those rows carry text.
- Existing project state can store STT candidate tracks and VAD/voice activity as separate diagnostic/reference rows, while final subtitle rows remain the save/export authority.
- Existing Apple Silicon worker planning lives under `core/runtime/multi_process.py` and `core/runtime/subtitle_resource_manager.py`, with `RuntimeResourceCoordinator`, `apply_apple_m_subtitle_pipeline_plan(...)`, active runtime labels, memory pressure snapshots, and benchmark-locked cut-boundary worker counts.
- `RuntimeResourceCoordinator` now reports `live_nle_projection_budget` telemetry: live projection uses existing row snapshots, dedicated projection workers `0`, subtitle worker-pool sharing `false`, coalesced updates, stale preview-frame drops, interactive reserve cores, foreground save/export/close labels, and critical/exit projection disablement. This is telemetry only; it does not change worker fan-out.
- `tools/remote_verify.py live-nle-proof` can now collect a compact `guided-subtitle-status` time-series and optional existing-window snapshots, then write `live_nle_runtime_proof.md/json`, `status_samples.json`, and `observability_samples.jsonl` for G3 runtime observability review. The harness requires each required runtime track (`VAD`, `STT1`, `STT2`) to be observed in at least two distinct pre-final active polls by default, requires generation completion, and rejects missing/insufficient pre-final observations, non-compact payloads, raw runtime payload leakage, final-authority drift, and live projection budget drift on active samples.
- Prior lessons prohibit treating full-parallel STT, forced smaller STT windows, or speed-only native adoption as safe defaults without quality parity and real-media proof.

Detailed plan:

1. Runtime track ownership map
   - Completed for the read-only feed/authority contract. Continue from the next slice only if it widens live status/feed wiring without changing final authority.

2. Live projection and status feed
   - Completed for compact automation/status feed counts. Continue from the next slice only if it adds visual/runtime proof without raw payload leakage or final-authority changes.

3. Resource-balanced parallel scheduling
   - Completed the read-only live projection budget telemetry slice: reserve at least one interactive core where applicable, expose foreground save/export/close and pressure labels, keep projection worker count at `0`, and prove the live display/status path does not take subtitle worker-pool threads.
   - Real-media `live-nle-proof` runtime/status/snapshot evidence and final-overlap deferred-save retry cleanup are complete for the current slices. Continue from the next slice only with the underlying final-overlap data fix, same-media quality/speed/save-reopen evidence, or a separately measured worker enforcement change; keep STT1 on the current high-quality native path and run STT2/word precision only within selective, quality-preserving budgets.
   - On Apple Silicon, describe accelerator use as ANE/GPU/CPU in docs and logs where user-visible. Do not make PyTorch MPS a production default.
   - Avoid full-core aggressive scheduling as a default. Let worker counts ramp only when memory pressure is normal and active runtime labels show no competing foreground save/export/close action.
   - Prevent the live NLE display path from taking threads away from the actual subtitle conversion path. Projection and painting should coalesce updates, reuse existing row snapshots, and drop stale preview frames rather than blocking STT workers.

4. Performance and quality proof
   - Measure baseline and candidate on the same representative media with non-profile elapsed truth, stage spans, memory pressure, active worker counts, and UI/app-command responsiveness.
   - Required proof includes raw/final/reference counts, quality/text/timing, final invalid/non-monotonic/overlap `0/0/0`, save/reopen stability, global canvas `max_active_segments=1`, and no increase in total subtitle conversion time beyond measurement noise. The same-media benchmark part passed in `v04.01.11`; direct-SRT app-command save/reopen/export passed in `v04.01.12`; open-media generation plus active-worker status/cancel/close/quit responsiveness passed in `v04.01.13`; active global-canvas responsiveness passed in `v04.01.14`; active-worker export final-surface regression guard passed in `v04.01.31`; selected stronger live active-final artifact audit passed in `v04.01.31`; any future G3 proof requires a fresh bounded owner-selected gate.
   - Record before/after artifacts under `output/manual_verification/latest/`. Runtime/status evidence that STT1/STT2/VAD appear progressively during generation is now available; same-media benchmark acceptance is now available; direct-SRT app-command save/export/reopen evidence is now available; open/start/status/cancel/close/quit responsiveness evidence is now available; active global-canvas responsiveness evidence is now available; active-worker export final-surface regression evidence is now available in the focused test suite; selected stronger live active-final artifact audit evidence is now available. No additional G3 active-final proof is selected at this time.

5. Implementation guardrails
   - Implement in narrow slices: first runtime owner-map and read-only projection, then live status feed, then scheduler budget telemetry, then visual/runtime proof.
   - Keep caches opt-in unless representative real-media evidence and owner review approve default promotion.
   - If the display path causes generation slowdown, command timeouts, memory pressure regression, or final subtitle drift, disable the live NLE track projection before changing STT/VAD quality policy.

Acceptance gates:

- During a live generation run, VAD, STT1, and STT2 progress must be observable as separate NLE runtime tracks or status-backed projected lanes before final generation completes.
- Full subtitle conversion speed must not regress versus the same-media baseline; any extra display/projection overhead must be measured and bounded.
- Final subtitle quality gates remain strict: no invalid durations, non-monotonic rows, final overlaps, final/STT lane mixing, or save/reopen drift.
- UI/app command responsiveness must survive while workers are active: `status`, cancel/quit, save, and close-path checks must not starve behind STT/VAD preview updates.

Rollback:

- If resource sharing slows generation or raises memory pressure, disable live NLE track projection first and return to the prior generation scheduler.
- If STT/VAD preview rows contaminate final save/export or render/export surfaces, revert the projection bridge and keep final rows as the only authoritative output.

### G4. Roughcut Scenario Composer And Generation Plan

Goal: Reframe the roughcut page into a scenario-composer workspace with four fixed regions while preserving existing roughcut functions, automation commands, state persistence, save/reopen behavior, and final subtitle authority.

Status: active planning item. Owner explicitly approved this UI/UX planning scope on 2026-06-29 and requested that the plan be added to `ACTION_ITEMS.md`. This item is a staged roughcut UI/flow plan, not a completed implementation, not a new roughcut algorithm approval, and not a save/export authority change.

Current baseline:

- Roughcut UI owner files are `ui/roughcut/roughcut_widget.py` and `ui/roughcut/roughcut_major_panel.py`.
- Existing roughcut automation and proof surfaces already cover `open-roughcut`, `roughcut-select-candidate`, `roughcut-select-chapter`, `roughcut-move-segment`, `roughcut-move-chapter`, `roughcut-play-sequence`, and `roughcut-export-srt`.
- Existing roughcut tests include `tests/test_roughcut_ui_v2.py`, `tests/test_roughcut_candidates.py`, `tests/test_app_command_bridge.py -k "roughcut"`, and `tests/test_project_segment_reload.py -k "roughcut or open_project_file"`.
- The current page has visible legacy content such as `LLM 후보`, `핵심 메뉴`, `현재 상태`, `후보 / 필터`, `내보내기`, `보조 참조`, logs, guide/detail text, and auxiliary tabs. The owner requested that existing UI elements inside the roughcut boxes be removed from the screen for the next scenario-composer direction.
- Existing major/minor roughcut cards already support drag/drop ordering, thumbnail preview hooks, subtitle snippets, candidate selection, ordered preview, save/reopen, and export paths. These functions must remain callable even if the old visible controls are hidden.
- Existing roughcut detail/table paths already expose chapter title/tag user edits through roughcut-local edit state. The next slice should promote that seed into an explicit middle-segment topic/tag metadata contract instead of inventing a second metadata owner.

Owner-approved region contract:

1. White region: `시나리오박스`
   - Scenario editing/composition area.
   - Acts like a screenplay writing desk: the primary mental model is assembling filmed cuts into a script-like sequence, not accepting an auto-generated roughcut list.
   - Combines middle-category roughcut segments into a scenario order.
   - Owns cut-edit planning for extending, shortening, and splitting video ranges so additional middle-category segments can be created.
   - Supports multiple saved scenario practice notebooks before final scenario confirmation.
   - On first roughcut entry, provides two default selectable order seeds: `LLM 추천 순서` and `기본순서(에디터 편집 순서)`.
   - Restores saved notebook order/state from the project file when the project is reopened.
   - Shows an LLM-generated whole-video explanation/summary based on the reassembled middle-segment order, selected cards, segment lengths, topics, tags, and subtitle snippets.
   - Shows the overall storyline that changes according to how the user assembles middle-segment cards, including logline, synopsis, act/beat flow, and plotline/lane view.
   - Shows a script outline view for sequence, scene, beat, dialogue/action, shot role, cut purpose, and continuity review.
   - Shows middle-segment compatibility links as score, color, and connector lines so the owner can see which cuts fit well together before rewriting a scenario.
   - Recommends intro, outro, and highlight video segment candidates as non-destructive cards that the user may preview and insert.
   - Collects scenario/material clips into a 60-second-or-less shortform candidate basket for handoff to the shortform maker.
2. Blue region: `재료박스`
   - Material/card inventory area.
   - Lists middle-category segments as cards.
   - Cards support drag/drop ordering, drag/drop merge, cut-edit-style split, x-axis time movement, vertical growth, wrapped subtitle text, and an in-card video preview.
   - Cards expose shot assembly metadata such as A-roll, B-roll, insert, reaction, alternate take, cut purpose, and director-note presence.
   - Cards expose compatibility badges and relationship connectors for high-fit, weak-fit, conflict, callback, continuation, and user-overridden links.
   - Lets middle-segment cards be added to the shortform candidate basket without changing final subtitle/export authority.
3. Video region: `비디오박스`
   - Remaining G4 planning after the completed first player slice.
   - Future scenario-composer order changes must keep the implemented player synchronized with `시나리오박스` order and matching subtitle timing.
   - Previews recommended intro, outro, and highlight candidate ranges before the user inserts them into the scenario.
   - Previews the collected shortform clip sequence and shows total duration before handoff.
4. Red region: `설정박스`
   - Scenario suggestion and detail area.
   - Shows scenario suggestions, selected scenario detail, generation rationale, review state, and scenario mode controls.
   - Shows order provenance and rewrite controls for `LLM 추천 순서`, `기본순서(에디터 편집 순서)`, and the currently user-edited scenario order.
   - Shows each middle-category segment's content, start/end time, duration/length, topic, tags, summary, script hierarchy, cut purpose, shot role, continuity state, director notes, and edit/review status.
   - Provides relation controls so the owner can manually input which cuts are highly related, relation type, score, directionality, reason, and whether the link should be used for scenario rewrite suggestions.
   - Provides the roughcut-editor-only edit surface for segment topic/tags and roughcut metadata while keeping subtitle text and timecode authority guarded by NLE/final-subtitle rules.

Detailed plan:

1. Documentation / handoff setup
   - Keep this G4 item active until the first scenario-composer implementation slice is verified.
   - Preserve the owner approval note and the four-region contract in this section.
   - Preserve Jammini's source opinion verbatim under `잼민이 의견 (원문)` and keep Dex's mapping under `Dex 반영 메모`.

2. Legacy roughcut UI removal from the screen
   - Hide or remove from layout flow the old visible UI elements inside the roughcut boxes, including `LLM 후보`, `핵심 메뉴`, `현재 상태`, `후보 / 필터`, `내보내기`, `보조 참조`, logs, guide/detail text, and auxiliary text tabs.
   - Do not delete the underlying methods, buttons, commands, signal/slot wiring, save/export helpers, candidate state, roughcut state persistence, or automation handlers.
   - Hidden legacy controls must not consume visible layout space. If a widget is hidden only with `.hide()` but still damages layout, move it to a zero-size hidden legacy container or remove it from the visible layout while retaining references.

3. Scenario-composer region implementation
   - Build the four owner-defined regions as the only visible roughcut page structure.
   - Use region object names and stable test hooks so screenshots and tests can identify `scenario_box`, `material_box`, `video_box`, and `settings_box`.
   - Keep the current dark app baseline while visually expressing the owner color roles through restrained border/background accents instead of breaking the app theme.
   - Avoid unrelated sidebar, editor, timeline, global-canvas, shortcut, popup, or color-system changes outside the roughcut page.

4. Roughcut generation policy
   - First implementation slice is scenario-composer structure and state wiring, not a broad new algorithm.
   - Deterministic candidates come first, based on existing cut boundaries, subtitle timing, roughcut segments, and safety/review state.
   - LLM is limited to scenario title, summary, rationale, and scenario suggestion assistance.
   - The planned scenario modes are `conservative`, `balanced`, and `highlight`.
   - No candidate is auto-finalized. Scenario output remains user-reviewable in `시나리오박스`.

5. State, authority, and compatibility guardrails
   - Do not change final subtitle authority, STT1/STT2/VAD runtime track ownership, final save/export authority, render/export core, or project subtitle/NLE disk schema.
   - Preserve save/reopen for selected roughcut candidate, safety filter, chapter order, segment order, scenario mode, and selected scenario state.
   - Preserve current app-command behavior for roughcut selection, movement, ordered preview, SRT export, and render-plan/export helpers.
   - Preserve original SRT and original media files. Scenario reassembly/export must write derived artifacts with `_시나리오.srt` and `_시나리오.mp4` suffixes instead of overwriting the original subtitle/video files.

6. Jammini / Dex collaboration requirement
   - Before implementation, send a bounded Jammini review or UI-draft packet if this G4 item is resumed after this insertion.
   - Treat chat `ACK` / `WORKING` as diagnostic only. Use the physical handoff file under `.agents/sentinel/handoffs/` as the source for `잼민이 의견`.
   - Dex must classify and map Jammini feedback before merging the first UI implementation slice.

7. Roughcut <-> Editor NLE shared-state contract
   - Use `NLEProjectState` as the runtime sharing contract between the main editor and roughcut editor. Do not create independent subtitle copies that can drift.
   - Editor -> Roughcut: editor subtitle text, timing, split, merge, delete, speaker, and candidate-confirm changes update NLE state first, then refresh roughcut material/scenario cards from the projected rows.
   - Roughcut -> Editor: scenario reorder, middle-segment reassembly, range trim, range extension, and split create NLE roughcut operations, then project back to editor rows through the existing editor reload/dirty path.
   - Commit roughcut drag/resize changes only at release/confirm boundaries, not on every drag pixel.
   - If NLE projection drift is detected, disable roughcut write-back and keep the main editor/final subtitle rows authoritative until the drift is fixed.

8. UML-style middle segment card composer
   - Treat `UML-style` as a PyQt6 2D node-and-connector composer for middle-category roughcut segments, not as a strict UML modeling tool.
   - Render middle-segment cards as node-like cards with title, topic, tags, time range, subtitle preview, review status, and video preview hooks.
   - Use connectors to show scenario order, alternative candidates, branch suggestions, merge relationships, and review-required conflicts.
   - Use x-axis movement for time/order, y-axis placement for grouping, alternatives, and branch layers.
   - Implement with PyQt6 2D `QGraphicsView` / `QPainter` or equivalent existing 2D widgets only. Do not introduce QML SceneGraph, OpenGL, Metal, Three.js, or 3D rendering for this editor surface.
   - Preserve text wrapping and vertical card growth so subtitle/topic/tag text does not overflow the card.

9. Reference-driven card arrangement model
   - Use external app/web references as inspiration only, not as a reason to import cloud collaboration, web views, or new rendering frameworks.
   - NLE/media-browser references:
     - Adobe Premiere Pro Project panel freeform/icon workflows: use free placement, thumbnail visibility, and visual grouping as inspiration for material-card browsing. Reference: `https://helpx.adobe.com/premiere-pro/using/customizing-project-panel.html`
     - Apple Final Cut Pro browser/timeline workflows: use filmstrip-style clip inspection, keyword-like metadata, and timeline-safe ordering as inspiration. References: `https://support.apple.com/guide/final-cut-pro/intro-to-organizing-media-ver1bd1d7c7/mac`, `https://support.apple.com/guide/final-cut-pro/intro-to-the-magnetic-timeline-ver8e3f20ea/mac`
     - DaVinci Resolve Cut page / source-tape style browsing: use fast clip scanning and source preview as inspiration for material-card video previews. Reference: `https://documents.blackmagicdesign.com/UserManuals/DaVinci_Resolve_19_Reference_Manual.pdf`
   - Whiteboard/node references:
     - Miro cards/connectors/Kanban/timeline: use structured cards, connector direction, story-map grouping, and lane grouping as inspiration. References: `https://help.miro.com/hc/en-us/articles/360020911193-Cards`, `https://help.miro.com/hc/en-us/articles/360017572174-Connection-lines`, `https://help.miro.com/hc/en-us/articles/360017571934-Kanban`
     - FigJam sticky notes/connectors/sections: use lightweight node creation, section grouping, and visible connector labels as inspiration. References: `https://help.figma.com/hc/en-us/articles/1500004362321-Guide-to-FigJam`, `https://help.figma.com/hc/en-us/articles/360039956914-Create-and-use-FigJam-connectors`
     - Milanote boards/cards/columns/lines: use board, column, and visual relationship patterns for scenario grouping. Reference: `https://help.milanote.com/`
     - Mural sticky notes/connectors/frameworks: use board-level grouping and connector clarity for review states. Reference: `https://support.mural.co/`
     - Obsidian Canvas: use local-first canvas/card/link inspiration only; do not adopt plugin-dependent behavior as a requirement. Reference: `https://help.obsidian.md/canvas`
   - Kanban/database-card references:
     - Trello boards/lists/cards: use simple card movement, list grouping, and card-detail drilldown as inspiration. References: `https://trello.com/guide/trello-101`, `https://trello.com/guide/board-basics`
     - Notion board/database cards: use property-driven card display, grouping, sorting, and preview density as inspiration. Reference: `https://www.notion.com/help/boards`
     - Airtable Kanban/gallery views: use field-driven grouping, card field visibility, and status lanes as inspiration. Reference: `https://support.airtable.com/docs/kanban-view`
   - Storyboard/writing references:
     - Scrivener Corkboard/index cards: use index-card rearrangement and synopsis-first review as inspiration for scene/segment ordering. Reference: `https://www.literatureandlatte.com/learn-and-support/user-guides`
     - Canva whiteboards/storyboards: use presentation-friendly storyboard grouping as secondary inspiration only. Reference: `https://www.canva.com/whiteboards/`
   - Adopted layout rules:
     - Default view is a time-aware storyboard grid: x-axis preserves sequence/time, rows group by scenario, topic/tag, review state, or candidate branch.
     - Optional node mode shows connectors for scenario flow, alternatives, merge/split relationships, and review conflicts.
     - Cards expose density modes: compact title/time/tag, normal subtitle preview, expanded video preview/details.
     - Grid snapping, auto-align, fit-to-selection, zoom, pan, and minimap/overview are planned as usability helpers; they must never change NLE order until the user commits.
     - Card order changes must be visible as both physical position and explicit connector/order labels, so visual arrangement cannot silently disagree with NLE sequence order.
   - Non-goals from references:
     - Do not add cloud collaboration, remote comments, account sync, browser embeds, plugin ecosystems, or generic database builders.
     - Do not make freeform canvas position the canonical source of subtitle order. NLE commit state remains the source of truth.
     - Do not add GPU/web/3D rendering just because reference apps use web canvases or high-scale whiteboards.

10. Middle segment topic/tag metadata authority and LoRA feedback
   - During roughcut extraction, derive a `topic` and `tags` metadata draft for each middle-category segment from subtitle text, roughcut chapter summary, story role, cut-boundary context, and deterministic/LLM-assist metadata where available.
   - Pass editor-generated or roughcut-extracted topic/tag metadata into the roughcut editor cards and detail panel as the editable metadata surface.
   - Only the roughcut editor may edit middle-segment `topic` and `tags`. The main editor may display projected metadata but must not become the edit authority for these fields.
   - Roughcut editor topic/tag edits must update the shared NLE/runtime metadata projection immediately so the main editor display, save/reopen state, and roughcut state stay consistent.
   - Record accepted topic/tag edits as local deep-learning/LoRA personalization feedback rows with before/after values, segment id, time range, project/media identity, source surface, and user-edit status.
   - The first slice records safe feedback data only. It must not mutate LoRA model weights, STT/VAD engines, or training accelerator drivers directly without a later explicit training gate.
   - Topic/tag feedback logging must be transactional enough to reject cancelled edits, corrupt rows, missing segment ids, or drifted time ranges before they contaminate the personalization store.

11. Settings box middle-segment detail inspector
   - The red `설정박스` must include both an all-segment overview and a selected-segment inspector for middle-category segments.
   - Required per-segment fields: segment id/order, title, content/subtitle body or snippet, summary, source start/end, scenario/output start/end where available, duration/length, topic, tags, major/minor group, story role, review state, dirty/edit state, trim delta, and NLE sync status.
   - Time and duration fields are read-only display fields by default. They may show current source/output values and pending trim deltas, but direct text editing of timecodes is not allowed from the settings box.
   - Length changes must route through the approved roughcut cut-edit/NLE commit path, not through freeform timecode text entry.
   - Content/subtitle body fields are projected from editor/NLE rows and are read-only unless a later explicit owner-approved text-edit path is added. The settings box must not silently become a second subtitle text editor.
   - Editable settings-box fields are roughcut metadata only: topic, tags, roughcut summary/note, review state, and scenario suggestion/reason fields where they do not alter final subtitle text/timing directly.
   - Topic/tag inputs may use a line edit, combo, chip editor, or text area, but every edit must set dirty state and survive selection changes, focus loss, save, and reopen.
   - On selection change, focus out, app focus loss, or tab/page switch, dirty metadata must auto-commit safely or block with an explicit warning before discarding edits.
   - Multi-select state should show aggregate duration, segment count, common tags/topics, and mixed-value markers, but bulk edits must remain a later explicit slice unless separately approved.

12. Scenario practice notebook candidates and project persistence
   - The middle-segment card composition window must let the user save and reload multiple scenario practice candidates before the final scenario is confirmed.
   - Treat each saved candidate as a scenario practice notebook, not as final subtitle/export authority.
   - Each notebook should preserve candidate id, title/name, created/updated time, source media/project signature, scenario mode, selected segment/card, middle-segment card order, chapter order, connector/order labels, roughcut metadata overrides, settings-box selection state, review notes, and generation rationale where available.
   - Persist notebook candidates in the project file through the roughcut state path with `candidates`, `selected_candidate_id`, `segment_order`, `chapter_order`, and `candidate_count`; any new fields must be versioned and legacy-compatible rather than silently replacing the project subtitle/NLE schema.
   - Project reopen must restore the roughcut notebook list, selected notebook, scenario order, card order, settings-box selected segment, and review/detail state together with the editor state.
   - Loading or switching a practice notebook must not auto-confirm the scenario, overwrite final subtitle rows, change export authority, or mutate editor rows until the user commits through the approved NLE boundary.
   - If editor-side delete/merge/split changes remove a segment referenced by a saved notebook, restore must filter or mark orphan segment references instead of crashing.
   - If a notebook source signature no longer matches the current subtitle/NLE projection, show a stale/review-required state and keep preview available where safe, but do not silently overwrite the current editor state.
   - Visible notebook management may replace the legacy candidate UI, but existing roughcut candidate automation and command references must remain callable for tests and QA.

13. Scenario-driven whole-video LLM summary
   - The `시나리오박스` must show a whole-video explanation/summary generated from the currently assembled scenario, not from the unedited original timeline alone.
   - Summary inputs are the committed or previewed scenario order, enabled/disabled middle segments, segment lengths, source/output time ranges, subtitle snippets or compressed subtitle summaries, topics, tags, roughcut notes, and review state.
   - The summary prompt builder must preserve scenario order and explicitly identify omitted, stale, review-required, trimmed, split, and extended segments.
   - LLM output is descriptive scenario assistance only. It must not become final subtitle authority, timing authority, export authority, or automatic scenario confirmation.
   - LLM summary requests must run through a background worker or existing async task path so PyQt6 GUI interaction, playback, scrolling, card dragging, and editor navigation do not block.
   - Do not regenerate on every drag pixel or every selection change. Use a debounce window, dirty-state gate, or explicit `요약 업데이트` command before requesting a new summary.
   - Token control is required: large subtitle bodies must be compressed into structured segment summaries before prompt construction so the request does not overflow the active model context.
   - Save the generated summary, prompt input signature, source notebook/candidate id, scenario order hash, model/provider metadata, created time, and stale/review state in roughcut state where compatible.
   - Project reopen should display the saved summary immediately without requiring a fresh API call; mark it stale when scenario order, segment content, topic/tag metadata, or source signature changes.
   - Network/API failure, timeout, token overflow, provider-disabled mode, or privacy/offline mode must degrade to a placeholder or cached stale summary without changing the scenario/order/editor state.

14. Middle-segment split/merge operations
   - The middle-segment card window must support splitting and merging middle-category segments as first-class roughcut operations.
   - Merge interaction should use drag/drop: dropping a segment card onto a compatible target segment creates a merge preview, shows the combined time range/subtitle count/topic/tag result, and requires an explicit commit or undoable release boundary before changing NLE state.
   - Split interaction should feel like cut editing: the user chooses a split point on the segment card/video preview/playhead range, sees the proposed left/right segments, and commits through the approved roughcut cut-edit/NLE path.
   - Prefer subtitle-boundary split points. If the split point cuts through an active subtitle row, the plan must define whether to snap to the nearest subtitle boundary, split subtitle text with timing interpolation, or block with a review-required warning.
   - Merge must preserve monotonic subtitle order, avoid overlaps, and record how source segment ids, subtitle row ids, topic/tags, summaries, preview thumbnails, and scenario notebook references were combined.
   - Split must create stable child segment ids, assign source subtitle rows and metadata to left/right children, update topic/tag/summary draft state, and keep traceability to the parent segment.
   - Topic/tag/summary metadata rules: merge should union tags and create a review-required combined summary/topic; split should copy parent metadata as provisional child metadata and mark both children for review until accepted.
   - Split/merge operations must be atomic NLE mutations with preview, commit, undo, rollback, stale-state marking, and save/reopen persistence. A failed operation must leave editor rows, roughcut cards, notebooks, LLM summary input signatures, and export state unchanged.
   - Practice notebooks, scenario order, settings-box selection, and LLM summary signatures must update after committed split/merge and become stale/review-required when they referenced the old segment shape.
   - Do not perform split/merge write-back on every drag hover or playhead movement. Hover/drag/cut positioning is preview-only until the explicit commit boundary.

15. Intro/outro and highlight segment recommendation
   - The `시나리오박스` must recommend candidate video ranges for intro, outro, and highlight use at the start of scenario composition.
   - Recommendations are non-destructive candidate cards. They may be previewed, inserted, appended, or ignored by the user, but they must never overwrite the current scenario canvas or notebook automatically.
   - Candidate discovery is deterministic-first: score segment ranges using available cut boundaries, subtitle timing, topic/tag metadata, keyword density, VAD density, silence/transition context, RMS/audio energy where available, thumbnail/scene-change hints, review state, and safe duration windows.
   - LLM may assist with labels, rationale, and ranking explanation only. It must not be the only source of timing decisions and must not auto-insert intro/outro/highlight clips.
   - Intro recommendations should favor clear topic setup, strong opening hook, clean audio/visual start, low abruptness, representative context, and short usable duration.
   - Outro recommendations should favor closure, summary, call-to-action or emotional finish, clean ending, low abruptness, and safe trailing silence/transition boundaries.
   - Highlight recommendations should favor high-value or high-energy utterances, dense key topics/tags, strong scene/audio changes, high subtitle importance, and ranges that remain understandable when previewed independently.
   - Recommendations must be generated in a background worker/backfill path so long videos do not block playback, subtitle editing, card dragging, or scenario navigation.
   - Store candidate type, source range, score components, rationale, topic/tags, source notebook/candidate id, thumbnail reference, generated time, and stale/review state in roughcut state where compatible.
   - Project reopen should restore accepted/inserted recommendation choices and cached recommendation candidates when their source signature still matches; changed subtitles, split/merge operations, topic/tag edits, or media changes must mark recommendations stale.
   - If media is missing, VAD/audio features are unavailable, or analysis fails, show safe empty-state/retry messaging and keep the current scenario unchanged.

16. Roughcut-to-shortform maker handoff
   - The middle-segment and scenario boxes must support collecting clips from the whole video into a shortform candidate basket for a 60-second-or-less shortform maker handoff.
   - This is a handoff structure, not the full PHASE3 shortform maker implementation. The existing `shortform` mode/menu and `ui/home_ui.py` placeholder must remain loosely coupled.
   - The basket can contain middle segments, split child segments, intro/outro/highlight recommendations, or manually trimmed scenario ranges, but total selected output duration must be validated at handoff time and remain `<= 60.0` seconds.
   - The basket UI should show ordered clips, source range, output duration, running total duration, matching subtitle count, topic/tags, recommended role, stale state, and whether each clip needs review.
   - Handoff payload should be a versioned roughcut-to-shortform state packet containing clip ids, source segment ids, source media identity, source/output time ranges, subtitle row references/snippets, topic/tags, title/summary/rationale, thumbnail references, vertical/shortform framing metadata, order, total duration, source notebook/candidate id, and stale/review flags.
   - Vertical/shortform metadata may include target aspect ratio, crop/fit mode, safe-area hints, subject/face/object focus hints where available, caption placement preference, and whether framing still needs manual review.
   - The handoff bridge must be loose: roughcut produces and persists a payload; the shortform maker receives or previews it through a narrow bridge/stub without importing roughcut UI internals or mutating roughcut state directly.
   - Shortform handoff must not alter final subtitle rows, roughcut scenario order, export output, or notebook state unless the user explicitly accepts/imports the payload in a later owner-approved shortform flow.
   - Project save/reopen should restore the shortform basket and last handoff payload where compatible; subtitle/topic/split/merge/media changes must mark the payload stale rather than silently reusing invalid ranges.
   - If the basket exceeds 60 seconds, media is missing, subtitle sync is stale, or the shortform receiver is still unavailable, block handoff with clear review-required state while preserving the basket for editing.

17. AlphaCut-inspired shortform maker implementation reference
   - Use AlphaCut web materials as product/workflow references only. Do not copy AlphaCut proprietary UI text, assets, layouts, templates, prompts, or cloud/account behavior.
   - Reference sources reviewed on 2026-06-30:
     - `https://alphacut.video/`
     - `https://alphacut.video/en`
     - `https://alphacut.video/en/blog/how-to-create-youtube-shorts-from-existing-video`
     - `https://alphacut.video/en/shorts-cropper`
     - `https://alphacut.video/en/auto-captions`
   - Adopt the high-level workflow pattern: long-form source or roughcut handoff -> AI/deterministic highlight candidates -> multiple shortform drafts -> title/hook/caption/template/aspect-ratio controls -> preview -> regenerate/refine -> local export.
   - Our first implementation remains local-project-first. The shortform maker should ingest the G4 roughcut handoff payload before supporting external URL import, account sync, cloud upload, or scheduled social publishing.
   - Candidate generation should reuse deterministic roughcut signals first: cut boundaries, intro/outro/highlight recommendations, topic/tags, subtitle importance, VAD/RMS/scene-change hints, and 60-second duration budget.
   - LLM may help with short title, hook line, summary, rationale, caption style suggestion, and draft ranking explanation. It must not be the only source for clip timing and must not auto-export.
   - Shortform draft cards should show source range, output duration, title/hook suggestion, subtitle/caption preview, aspect ratio, crop/framing status, template/style preset, score/rationale, and stale/review state.
   - Default output should target vertical shortform framing, with 9:16 as the first-class preview target and later optional aspect ratios such as 1:1 or 4:5 only after the vertical path is proven.
   - Captions should come from existing final subtitle/NLE projection or the roughcut handoff subtitle references, not a new STT pass by default. Caption styling is a shortform overlay/template choice, not subtitle text authority.
   - Crop/framing metadata should start as safe-area/crop hints and manual review state. Automatic speaker/subject tracking can be a later enhancement only when it does not require new GPU/3D/web surfaces or weaken playback performance.
   - Regenerate/refine must be non-destructive: recompute candidate selection, title/hook, caption style, or template suggestions without overwriting accepted clips or roughcut notebooks.
   - Keep export local-first for the first slice. Direct TikTok/YouTube/Instagram upload, web account login, cloud processing, billing, or public link ingestion are out of scope unless separately approved.
   - Persist shortform draft cards, selected draft id, source payload signature, duration budget, caption/template/framing choices, and stale/review flags in a versioned shortform state payload compatible with project save/reopen.

18. Scenario storyline visualization and writing view
   - The `시나리오박스` must show the overall storyline based on the current assembled middle-segment order, not the original media order.
   - Reference sources reviewed on 2026-06-30:
     - Plottr visual timeline, scene-card, plotline, and auto-outline workflow: `https://docs.plottr.com/article/54-timeline-overview`, `https://docs.plottr.com/article/57-timeline-scene-cards`, `https://docs.plottr.com/article/68-outline-overview`
     - Miro user story map card/backbone workflow: `https://miro.com/templates/user-story-map/`, `https://help.miro.com/hc/en-us/articles/360020712554-User-story-mapping`
     - Milanote story outline/storyboard planning workflow: `https://milanote.com/templates/creative-writing/story-outline`
     - Scrivener/Scapple official corkboard/index-card and freeform mind-map references: `https://www.literatureandlatte.com/blog/organize-your-scrivener-project-with-the-corkboard`, `https://www.literatureandlatte.com/learn-and-support/user-guides`
     - StudioBinder beat-sheet/story-structure references: `https://www.studiobinder.com/blog/save-the-cat-beat-sheet/`
     - Reedsy story-structure overview: `https://reedsy.com/blog/guide/story-structure/`
   - Adopt reference-level ideas only: scene cards, corkboard/index cards, beat labels, act lanes, plotline/character/theme lanes, storyboard frames, and story-map backbone. Do not copy proprietary UI, templates, account/cloud collaboration, or external story-writing workflows wholesale.
   - Storyline view modes should include: compact ordered synopsis, act/beat board, storyboard strip, corkboard card grid, and optional subway-map/parallel plotline view for themes, people, topics, or emotional arcs.
   - Each middle-segment card should expose a story role and logline: setup, hook, context, conflict, escalation, evidence/example, turn, climax/highlight, resolution, outro, or review-required.
   - Deterministic structure comes first: use card order, segment duration, intro/outro/highlight tags, topic/tags, split/merge lineage, subtitle density, and recommendation scores to infer act/beat placement before asking LLM for text.
   - LLM may generate or refresh logline, synopsis, beat label, storyline summary, and narrative rationale. It must not reorder cards, mutate subtitle text/timing, or commit scenario changes automatically.
   - The storyline summary must update when card order, enable/disable state, split/merge state, topic/tags, subtitle text, or selected practice notebook changes. Use debounce/background workers so storyline refresh does not block card dragging or playback.
   - Storyline layout must remain PyQt6 2D-only. Use `QGraphicsView`/`QPainter` or existing 2D widgets for lanes, arrows, connectors, and cards; do not introduce QML SceneGraph, OpenGL/Metal, web canvases, or 3D rendering.
   - To avoid spaghetti UI, plotline connectors must use grid snapping, lane grouping, connector routing, fit-to-story, and fallback to a simple ordered synopsis when the node count or connector crossings exceed safe thresholds.
   - Persist storyline state with the practice notebook: selected view mode, act/beat labels, segment story roles, generated loglines, generated synopsis, lane/group assignments, connector routing hints, layout positions, source signature, and stale/review flags.
   - Project reopen should restore the last storyline view immediately. If source order/content metadata changed, show the stale storyline with review-required state and require refresh before it can be used as current rationale.

19. Screenplay-oriented shot assembly composer
   - Reframe the roughcut surface as a screenplay composer for filmed cuts. The user should feel that they are writing a movie/script from captured shots by deciding what each cut means and where it belongs.
   - Map middle-segment cards into a script hierarchy: `Sequence > Scene > Beat > Dialogue/Action`. The hierarchy is roughcut metadata and must not replace subtitle/NLE row authority.
   - Add a script outline view in the `시나리오박스`. Clicking a sequence, scene, beat, or dialogue/action item should focus the matching 2D scenario canvas card and video preview range.
   - Each card should expose a cut purpose/story function such as hook, setup, information, emotional beat, conflict, proof, bridge, B-roll, insert, reaction, punchline, resolution, outro, or review-required.
   - Support shot assembly roles as roughcut metadata: A-roll, B-roll, insert, reaction shot, bridge shot, alternate take, missing-shot placeholder, and continuity warning.
   - Support B-roll/insert/reaction layers under a scene without treating their visual layer position as subtitle order. NLE commit order remains explicit and reviewable.
   - Support alternate takes as non-destructive variants for the same scene/beat purpose. Switching an alternate take updates preview and notebook metadata, but it must not overwrite source clips or final subtitle rows without an explicit commit.
   - Add missing shot/gap detection planning: subtitle gaps, audio/VAD gaps, missing video ranges, abrupt topic discontinuity, or unresolved scene intent can create red placeholder cards for review.
   - Add director notes per card, scene, and practice notebook. Notes may include intent, continuity warning, needed pickup shot, reason for using a take, or edit instruction, but they are roughcut metadata only.
   - Add revision/history planning for screenplay assembly: card movement, split/merge, alternate take selection, cut purpose changes, director-note edits, and table-read refresh should be journaled enough for review and undo planning.
   - Add table-read style preview: a text-only screenplay scroll view that reads the assembled scenario in order as sequence/scene headings, action lines, dialogue/subtitle lines, B-roll/insert cues, and notes/review markers.
   - Table-read preview should sync scroll/playhead to video time and selected cards, but it should remain usable without video playback and should not create a new subtitle text authority.
   - Add a shot-to-subtitle authority guard before any NLE commit. It must check missing source refs, invalid durations, overlaps, non-monotonic rows, subtitle text drift, and timeline conflicts before roughcut screenplay edits can project back to the editor.
   - Persist screenplay composer state per practice notebook: hierarchy, cut purpose, shot role, B-roll/insert/reaction layers, alternate take choice, missing-shot placeholders, director notes, revision journal pointers, table-read view state, source signature, and stale/review flags.
   - Use async/debounced layout generation for large script outlines and table-read views so thousands of subtitles or deep scene hierarchy do not block playback, card movement, or editor navigation.

20. Scenario-derived SRT and video export isolation
   - Reassembly, integration, edit, split, merge, and screenplay-composer operations must preserve the original SRT file as-is. The original SRT is never overwritten by scenario output.
   - When the user exports subtitles from the roughcut scenario, write a separate scenario SRT using the source/export basename plus `_시나리오.srt`.
   - When the user exports video from the roughcut scenario, write a separate scenario MP4 using the source/export basename plus `_시나리오.mp4`.
   - Scenario SRT timing should be based on the assembled scenario output timeline, starting from the scenario sequence rather than the original media timeline, so it matches `_시나리오.mp4`.
   - The scenario MP4 must render the reassembled scenario order and matching subtitles from the scenario SRT/projection. It must be visually and temporally distinct from the original video when the scenario order, trims, split/merge, or selected clips differ.
   - Original media files must never be rewritten, renamed, replaced, moved, or treated as the rendered scenario artifact.
   - Scenario exports are derived artifacts. The project may store their latest output paths, export signature, source notebook/candidate id, scenario order hash, and stale/review state, but these files do not become final subtitle authority or source media authority.
   - If `_시나리오.srt` or `_시나리오.mp4` already exists, the app must not silently overwrite it. Require explicit replace approval or generate a safe numbered/timestamped variant while preserving the original and previous scenario exports.
   - Scenario export preflight must block output when source media is missing, scenario order has unresolved stale/missing segments, subtitle rows are invalid, durations collapse, overlaps occur, or video/SRT duration parity cannot be proven.
   - Normal editor SRT export and roughcut scenario SRT export must remain separate commands/surfaces so the owner can keep original subtitles and scenario subtitles side by side.

21. Editor restore-to-original and combined editor/roughcut snapshots
   - Add an editor-side `원본으로 돌리기` plan that restores the editor subtitle/timing state back to the original imported/opened baseline without overwriting original SRT/media files or deleting derived scenario exports.
   - Define the original baseline at project/media/SRT open time: original media path/identity, original SRT path/content hash when present, initial editor rows, initial NLE projection, and import/open metadata. If no external SRT exists, the baseline is the first accepted source-app subtitle state for that session/project.
   - Running `원본으로 돌리기` must require explicit confirmation and must create a pre-restore safety snapshot before applying the restore.
   - Restore-to-original resets editor rows and NLE projection to the original baseline, then marks roughcut notebooks, scenario summaries, storyline views, screenplay hierarchy, shortform baskets, and scenario export signatures stale/review-required when they referenced the changed editor state.
   - Restore-to-original must not delete practice notebooks, director notes, topic/tag feedback records, LoRA feedback rows, `_시나리오.srt`, or `_시나리오.mp4`; it only disconnects or stale-marks derived roughcut state that no longer matches.
   - Add a combined editor + roughcut snapshot feature. A snapshot must capture editor rows, NLE state/projection identity, selected segment/playhead where safe, roughcut notebooks, selected notebook/candidate, material card order, scenario order, split/merge lineage, topic/tags, summaries, storyline state, screenplay hierarchy, director notes, shortform basket, scenario export paths/signatures, stale flags, and relevant UI selection state.
   - Combined snapshots must be atomic: restore should apply editor and roughcut state together or not at all. Partial restore is a later separately approved mode.
   - Snapshots should have explicit names, created/updated time, source media/project signature, app/schema version, dirty/stale flags, and a short human-readable description of what changed.
   - Snapshot restore must run the same subtitle/NLE preflight checks used for roughcut commits: missing refs, invalid duration, overlap, non-monotonic rows, subtitle text drift, stale media signature, and scenario export parity checks where relevant.
   - Snapshot state may live in the project file as versioned compatibility metadata, but it must not replace the approved project subtitle/NLE canonical load-owner policy or original file authority.
   - Project save/reopen should restore the snapshot list and selected snapshot metadata. Snapshot payloads that reference missing media/SRT/project signatures must remain visible but blocked from restore until reviewed.
   - Snapshot storage must avoid unbounded project growth. Large preview thumbnails, rendered videos, or binary media are not embedded; use paths, hashes, compact metadata, and recomputable previews.

22. App Store-safe observability and UI/UX scenario tracing
   - All G4 roughcut, scenario composer, screenplay composer, restore, snapshot, and scenario export work must remain compatible with the Mac App Store lane. This is a planning guard only and does not claim App Store readiness by itself.
   - Reference the current official Apple surfaces before release validation: App Review Guidelines `https://developer.apple.com/app-store/review/guidelines/`, App Review checklist/privacy issues `https://developer.apple.com/distribute/app-review/`, App Privacy Details `https://developer.apple.com/app-store/app-privacy-details/`, App Store Connect app privacy management `https://developer.apple.com/help/app-store-connect/manage-app-information/manage-app-privacy/`, macOS App Sandbox file access `https://developer.apple.com/documentation/security/accessing-files-from-the-macos-app-sandbox`, and third-party SDK privacy manifest/signature requirements `https://developer.apple.com/support/third-party-SDK-requirements/`.
   - Observability must be local-first and review-safe: logs/traces stay on the user's machine unless the user explicitly exports a diagnostic bundle. No hidden upload, account sync, analytics SDK, tracking domain, cloud telemetry, or social upload is introduced by this G4 work.
   - Trace data must be minimal and redacted by default. Do not log raw subtitle text, full media paths, raw prompt payloads, full LLM responses, personal filenames, account identifiers, or rendered media frames unless the user explicitly creates a local debug bundle after being warned.
   - Log stable ids and hashes instead of sensitive data: project id/hash, media fingerprint hash, scenario notebook id, segment/card id, subtitle row id, operation id, correlation id, source signature, before/after state hash, duration, validation status, error code, and stale/review flags.
   - UI/UX scenario tracing must cover user-visible workflows end to end: roughcut open, notebook create/switch/save, card drag/drop, split, merge, trim/extend, topic/tag edit, scenario summary refresh, storyline view switch, screenplay outline focus, table-read preview, shortform basket add/remove, restore-to-original, combined snapshot create/restore, `_시나리오.srt` export, and `_시나리오.mp4` export.
   - Each UI/UX trace event should carry at least: timestamp, app version/schema version, surface id, region id (`scenario_box`, `material_box`, `video_box`, `settings_box`), command/action id, input state hash, output state hash, selected notebook/candidate id where relevant, elapsed time, result (`ok`, `blocked`, `cancelled`, `failed`), and redacted error reason.
   - Trace spans should make debugging possible across layers: UI action -> roughcut command -> NLE operation/preflight -> persistence/snapshot/export -> playback/render/export result. A single correlation id should connect the spans without exposing raw media or subtitle text.
   - App Store/privacy guard: if a feature sends subtitle text, prompts, logs, traces, media metadata, or user-generated content to an external LLM/provider, it must be explicitly user-initiated, privacy-disclosed, cancellable, and reflected in owner metadata/privacy review before App Store submission.
   - Third-party dependency guard: do not add analytics, crash-reporting, cloud logging, AI SDKs, web canvases, or tracking dependencies for this tracing layer without a separate App Store/privacy manifest review. Required-reason APIs and SDK privacy manifests must be inventoried before release.
   - Sandbox guard: traces and debug bundles must use app-container or user-selected output locations. User media/SRT paths require normal sandbox-safe access; do not broaden entitlements solely for tracing.
   - Trace retention must be bounded. Use log rotation, size caps, and explicit cleanup; scenario snapshots/export artifacts and trace logs must not grow the project file or app container without limit.
   - A user-facing diagnostic export should be a local redacted bundle containing trace spans, validation reports, state hashes, app/version info, and selected screenshots only when explicitly requested. It must not include raw media, raw subtitles, or full prompts by default.
   - App Store readiness for G4 requires separate G0 proof: signed sandboxed `.app`, signed `.pkg`, strict codesign/pkgutil proof, sandbox workflow smoke, App Store Connect validation, owner metadata/privacy answers, and forbidden-copy/privacy scan. G4 trace proof is necessary debugging evidence, not submission proof by itself.

23. Dedicated roughcut source ownership folders
   - Manage roughcut source code in roughcut-owned folders instead of scattering new scenario-composer logic across editor, timeline, main-window, project, or settings modules.
   - Use `core/roughcut/` as the canonical non-UI roughcut engine package for scenario composition, screenplay hierarchy, cut assembly, split/merge planning, scenario SRT/video export planning, snapshot payload building, trace schema, and validation/preflight helpers.
   - Use `ui/roughcut/` as the canonical roughcut UI package for the four-region page, scenario/material/video/settings widgets, cards, table-read view, storyboard/corkboard/storyline views, and roughcut-local UI controllers.
   - Keep non-roughcut modules as adapters only. `ui/editor`, `ui/timeline`, `ui/main`, `ui/settings`, `core/project`, and app-command/QA bridge code may call roughcut APIs or expose integration hooks, but must not own roughcut business logic or duplicate roughcut state rules.
   - If a new sub-area becomes large, create roughcut subpackages under the roughcut owners, for example `core/roughcut/scenario_composer/`, `core/roughcut/exports/`, `core/roughcut/snapshots/`, `core/roughcut/tracing/`, `ui/roughcut/scenario_composer/`, or `ui/roughcut/cards/`, rather than placing more files beside unrelated editor/timeline code.
   - Existing roughcut-adjacent files outside roughcut folders should be treated as compatibility adapters unless a later implementation slice explicitly migrates them. Do not move files mechanically without focused tests and import-path proof.
   - Public APIs crossing folder boundaries must be narrow and typed: roughcut state DTOs, NLE operation requests, export requests, snapshot descriptors, trace events, and read-only projections. Avoid importing PyQt UI classes into `core/roughcut/`.
   - Add or update CODEMAP / feature-registry references when implementation starts so future agents can find the roughcut owner folders before widening a search.
   - New tests for G4 should be grouped by roughcut ownership. Use existing `tests/test_roughcut_*.py` patterns for compatibility, and consider a `tests/roughcut/` grouping only as a separate test-tree cleanup slice.
   - Folder ownership proof is required before the first G4 implementation merge: list new/changed files by owner folder, explain any exception outside roughcut folders, and verify there is no new root-level development doc or ad hoc roughcut module.

24. Middle-segment compatibility scoring and relationship graph
   - Add a middle-segment compatibility graph so cuts that work well together are visible as score, color, and connector lines in the `시나리오박스` and `재료박스`.
   - Score range is `0..100` with clear buckets for high-fit, medium-fit, weak-fit, conflict/contrast, and review-required. The exact thresholds are implementation details, but they must be visible and testable.
   - Visual encoding should use PyQt6 2D-only connectors: line thickness for strength, color for relation quality, style for relation state, and optional compact score badges. Do not introduce OpenGL, 3D, web canvas, or GPU-only graph rendering.
   - Planned relation types include: continuation, cause/effect, complement, contrast/conflict, callback, topic/tag match, emotional transition, A-roll/B-roll support, insert/reaction support, intro/outro support, highlight build-up, and user-defined.
   - Relationships may be bidirectional or asymmetric. Direction must be visible through arrowheads or labels and must affect scenario rewrite suggestions only when the owner opts into using that relation.
   - The `설정박스` must let the owner create/edit/delete relation overrides by choosing a source cut, target cut, relation type, score, directionality, reason/note, active/inactive state, and whether the relation should influence rewrite suggestions.
   - Manual owner-authored relation overrides have highest priority. Deterministic scoring and LLM scoring can suggest or refresh scores, but they cannot override a manual relation without explicit owner confirmation.
   - Deterministic base score inputs may include adjacent timing, topic/tag overlap, subtitle similarity hash, story role, cut purpose, VAD/audio continuity, intro/outro/highlight labels, split/merge lineage, alternate-take lineage, and prior accepted scenario order.
   - LLM may assist with context compatibility labels, rationale, and candidate relation suggestions only through an explicit or background-approved path. It must not see raw subtitle text unless the G4 App Store/privacy guard allows it; prefer redacted summaries, ids, hashes, tags, and short sanitized snippets.
   - Scenario rewrite based on compatibility graph is suggestion-first. It may propose a rewritten order, grouped scene clusters, bridge cuts, conflict warnings, or missing connector notes, but it must not auto-commit NLE/editor rows, final subtitle rows, scenario exports, or practice notebooks.
   - Rewriting should produce multiple non-destructive alternatives, for example `relationship_best`, `story_continuity`, and `contrast_cut`, stored as practice notebook candidates until the owner accepts one.
   - Split, merge, trim, editor subtitle changes, topic/tag edits, restore-to-original, snapshot restore, and media/SRT signature changes must stale-mark affected relation links and scenario rewrite suggestions before reuse.
   - Relationship state must persist per project/notebook: relation id, source segment id, target segment id, relation type, score, directionality, origin (`manual`, `deterministic`, `llm`, `imported`), rationale hash, active state, stale state, source signature, and updated time.
   - Relationship graph traces must be App Store-safe and redacted: log relation ids, source/target ids, scores, states, and hashes, not raw subtitles, full paths, raw prompts, or full LLM responses.
   - This feature belongs under roughcut-owned source folders such as `core/roughcut/scenario_composer/`, `core/roughcut/tracing/`, and `ui/roughcut/cards/` or equivalent roughcut subpackages. Non-roughcut files should remain thin adapters.

25. Initial roughcut order seeds and user-order scenario rewrite
   - When the editor hands a roughcut draft into the roughcut editor, the roughcut workspace must create two default selectable scenario seeds: `기본순서(에디터 편집 순서)` and `LLM 추천 순서`.
   - `기본순서(에디터 편집 순서)` is the authoritative baseline order from the current editor/NLE projection at handoff time. It preserves the editor user's current cut/subtitle order and must always remain available.
   - `LLM 추천 순서` is a separate roughcut candidate generated by roughcut LLM/scoring assistance. It may use topic/tags, storyline, screenplay roles, compatibility graph, intro/outro/highlight recommendations, and subtitle summaries, but it must not replace the baseline editor order.
   - Both default seeds should appear as selectable practice notebook candidates with explicit provenance labels, created time, source signature, order hash, rationale/state, and stale/review flags.
   - Switching between the two default seeds changes only the roughcut scenario canvas/notebook selection until the owner explicitly commits through the approved NLE boundary.
   - If the user has manually edited card order, split/merge state, notes, compatibility links, or scenario text, seed switching must first protect that work through an explicit warning, save-as-practice-note prompt, or automatic temporary backup notebook.
   - The user's currently edited order becomes the primary source for scenario rewriting. LLM rewrite prompts must use the current user order, not silently fall back to the original media order or LLM-recommended order.
   - Scenario rewrite from user order may regenerate synopsis, storyline, screenplay outline, loglines, bridge suggestions, compatibility rationale, and alternative practice notebooks. It must not auto-reorder the active notebook unless the owner accepts the proposal.
   - Rewrite results should be stored as non-destructive alternatives, for example `user_order_rewrite`, `llm_order_rewrite`, and `editor_order_rewrite`, with clear provenance and diff/compare against the current user order.
   - If editor rows, NLE projection, topic/tags, split/merge lineage, compatibility graph, restore-to-original, snapshot restore, or source media/SRT signatures change, affected seeds and rewrite outputs must become stale/review-required before reuse.
   - Save/reopen must restore both default seeds, selected seed, current user-edited order, rewrite alternatives, provenance labels, order hashes, stale flags, and any temporary backup notebooks.
   - Trace order-seed and rewrite flows with redacted correlation ids: editor-to-roughcut handoff, seed creation, seed switch, manual order edit, backup creation, rewrite request, rewrite result, accept/reject, stale marking, and save/reopen restore.
   - LLM seed generation and rewrite are assistive only. They must not auto-commit editor rows, final subtitle rows, scenario exports, `_시나리오` files, source media, or accepted notebooks.

26. Unified save contract for original subtitles, roughcut, and shortform editor
   - Pressing the existing project `저장` button must persist the full editing workspace, not only the current visible page.
   - The saved project must include the original subtitle/editor state: generated subtitle rows, editor-edited subtitle text/timing, final subtitle/NLE projection, speaker/review metadata, media identity, source SRT/import identity where available, and the original-subtitle baseline needed for `원본으로 돌리기`.
   - The saved project must also include the roughcut scenario-composer state: default editor-order seed, LLM-order seed, selected seed, user-edited order, practice notebooks, material card layout, scenario order, split/merge lineage, trim/extend edits, topic/tags, summaries, compatibility graph, storyline/screenplay state, recommendation candidates, stale flags, and export signatures.
   - The saved project must also include the shortform editor state: roughcut handoff payload, shortform basket, draft cards, selected draft, clip order, 60-second duration budget, caption/template/framing choices, title/hook/summary suggestions, crop/safe-area metadata, stale flags, and local export signatures.
   - Use one project-save transaction boundary for the three domains. Save success means all required domains are serialized and validated together; partial save must fail clearly or preserve the last known good project instead of writing mixed old/new state.
   - Keep domain authority explicit: original subtitle/editor rows remain the subtitle authority; roughcut scenario state remains derived scenario/editorial state; shortform state remains derived vertical/shortform draft state.
   - Saving roughcut or shortform state must not overwrite the original subtitle-only baseline, original media, original SRT, final subtitle authority, or accepted editor rows unless the owner performs an approved NLE commit.
   - Project reopen must restore the editor, roughcut, and shortform workspaces together so changing pages after reopen shows the last saved state without requiring a new LLM call, roughcut regeneration, or shortform handoff rebuild.
   - If one workspace has stale source signatures because editor subtitles, roughcut scenario order, shortform clips, media identity, restore-to-original, or snapshot restore changed, save the stale/review-required state instead of silently dropping it.
   - The save path should store compact metadata, ids, hashes, and recomputable preview references, not rendered media blobs, raw prompts, raw LLM responses, or large thumbnail/video caches.
   - Save logs/traces must record the three-domain save transaction with redacted correlation ids, domain hashes, validation result, elapsed time, and failure domain, while avoiding raw subtitles, full paths, raw prompts, rendered frames, and personal filenames.

27. Full scenario meeting gap coverage and expanded demo board
   - Preserve the owner-facing expanded demo board under `output/manual_verification/latest/g4_roughcut_demo_board_20260630/` as a visual planning artifact. It is not runtime proof and does not mean G4 behavior has been implemented.
   - Physical handoffs reviewed for this scenario gap pass: `.agents/sentinel/handoffs/20260629-161338-roughcut-scenarios-meeting-scout.md`, `.agents/sentinel/handoffs/20260629-161354-roughcut-architecture-scout.md`, `.agents/sentinel/handoffs/20260629-161411-roughcut-qe-scout.md`, and `.agents/sentinel/handoffs/20260629-161429-roughcut-workflow-scout.md`.
   - Add editor-to-roughcut stale/sync as a first-class user scenario: if the main editor subtitle text/timing changes while roughcut notebooks, relation scores, LLM summaries, or shortform drafts exist, roughcut cards refresh from the NLE projection and dependent derived state becomes stale/review-required.
   - Add seed/split/merge safety as a first-class negative scenario: seed switching after manual edits requires warning and backup; split/merge overlap, negative duration, or text-drift failure requires transaction rollback and unchanged editor/final rows.
   - Add alternate-take and B-roll layer scenario: A-roll, B-roll, insert, reaction, and alternate takes are non-destructive metadata layers until an explicit NLE commit; alternate takes may carry VAD-derived offset metadata for subtitle sync preview without rewriting original subtitle timing.
   - Add shortform over-limit triage scenario: the shortform basket must show live duration budget, block `>= 60.0` seconds, let the user remove/trim clips to pass, and keep the handoff payload stale/review-aware after source changes.
   - Add export/restore clarity scenario: original SRT/media remain protected, `_시나리오.srt` and `_시나리오.mp4` remain derived outputs, and `원본으로 돌리기` uses the original baseline plus a pre-restore snapshot while stale-marking dependent roughcut/shortform state.
   - Add practice-notebook clarity scenario: active notebook/seed provenance must stay visible so the user can tell whether they are editing `기본순서`, `LLM 추천 순서`, or a user-created practice notebook.

28. Reference NLE structures and built-in responsiveness baseline
   - G4 must be designed as a 100% NLE structure, not as a separate roughcut sidecar UI. Scenario order, subtitle timing, split/merge/trim, shortform handoff, save/reopen, restore, and export must all route through versioned NLE state, preview state, and explicit NLE commit boundaries.
   - Responsiveness and optimization are baseline requirements, not later polish. Every visible G4 surface must preserve editor interaction, playback, card dragging, page switching, and save/close responsiveness on large projects.
   - Official/reference sources reviewed for structure:
     - Final Cut Pro Magnetic Timeline, Roles, proxy/optimized media, generated media, render files: `https://support.apple.com/guide/final-cut-pro/intro-to-the-magnetic-timeline-verb8fcfc133/mac`, `https://support.apple.com/guide/final-cut-pro/intro-to-roles-verb71cbcbe/mac`, `https://support.apple.com/guide/final-cut-pro/create-optimized-and-proxy-files-verb8e5f6fd/mac`, `https://support.apple.com/guide/final-cut-pro/what-are-libraries-verfdd5c590e/mac`, `https://support.apple.com/guide/final-cut-pro/manage-render-files-ver68a8c250/mac`
     - Adobe Premiere Productions, bins, and proxy workflow: `https://helpx.adobe.com/premiere/desktop/collaborate-with-others/collaborate-using-productions/about-productions.html`, `https://helpx.adobe.com/premiere/desktop/organize-media/ingest-proxy-workflow/ingest-and-proxy-workflow.html`, `https://helpx.adobe.com/premiere/desktop/organize-media/file-organization/add-and-delete-bins.html`
     - DaVinci Resolve Cut/Edit reference and proxy/cache-oriented editing reference: `https://documents.blackmagicdesign.com/UserManuals/DaVinci_Resolve_19_Reference_Manual.pdf`
     - Avid Media Composer bin autosave/attic and project/bin compatibility references: `https://kb.avid.com/articles/en_US/Knowledge/How-to-configure-auto-save-in-Media-Composer`, `https://kb.avid.com/pkb/articles/en_US/user_guide/en275293`
     - Lightworks NLE/project/bin/proxy/background-render reference: `https://cdn.lwks.com/docs/2021.1/Lightworks%2B2021.1%2BQuick%2BStart%2BGuide.pdf`, `https://cdn.lwks.com/docs/2020.1/Lightworks_2020.1_User_Guide.pdf`, `https://lwks.com/`
     - Descript transcript/scenes/storyboard-style editing reference: `https://help.descript.com/hc/en-us/articles/15726742913933-Edit-like-a-doc`, `https://help.descript.com/hc/en-us/articles/10248939749517-Scenes-overview`, `https://www.descript.com/storyboard`
     - CapCut shortform caption/template reference: `https://www.capcut.com/tools/add-subtitles-to-video`, `https://www.capcut.com/resource/capcut-template-editing-made-easy-a-comprehensive-guide-to-enhancing-your-videos`
   - Adopted structure from Final Cut Pro: use a Magnetic Timeline-like NLE invariant for roughcut cards. Split, merge, delete, insert, trim, and reorder must prevent accidental gaps, collisions, and subtitle sync drift through snap/close-up behavior and explicit review states.
   - Adopted structure from Final Cut Pro Roles: treat segment roles as first-class metadata lanes: A-roll, B-roll, insert, reaction, alternate take, title/caption, dialogue/subtitle, music/effects, intro, outro, highlight, and review-required. Roles affect display/filter/export planning but do not replace final subtitle authority.
   - Adopted structure from Adobe Premiere Productions: practice notebooks, roughcut candidates, shortform drafts, and scenario alternatives should switch by lightweight ids/references, not by duplicating video/audio buffers or subtitle row payloads.
   - Adopted structure from Adobe/Premiere and Final Cut Pro proxy workflows: G4 preview must prefer proxy/thumbnail/waveform/subtitle-summary caches for card and video preview while preserving original media for final export and source authority.
   - Adopted structure from DaVinci Resolve/Lightworks performance workflows: use background cache/build tasks for thumbnails, waveforms, VAD density, compatibility scores, intro/outro/highlight candidates, and shortform previews. UI interaction must use cached/proxy data and coalesced updates rather than blocking on analysis.
   - Adopted structure from Avid: save/reopen and undo/redo should use journaled transaction snapshots and recovery-friendly autosave/attic-like metadata for roughcut notebooks, shortform drafts, and NLE commit attempts.
   - Adopted structure from Descript: transcript-linked editing is allowed only as a projection into NLE operations. Text/card/script edits can drive media proposals, but every proposal must resolve into NLE segment operations before it can affect editor rows or exports.
   - Adopted structure from CapCut/shortform editors: shortform draft cards may use caption style/template/framing presets, but caption text authority stays with existing subtitle/NLE projection and social/cloud/account upload flows remain out of scope.
   - Performance rules:
     - Large G4 projects must virtualize/clip card rendering, relation connectors, thumbnails, subtitles, and settings rows so offscreen items do not repaint unnecessarily.
     - Card drag, canvas pan/zoom, seed switch, notebook switch, and settings selection should be bounded by lightweight DTO swaps and viewport repaint, not media decode or LLM calls.
     - Video preview should use cached thumbnails/proxy preview first and defer high-cost decode, waveform, VAD, LLM, or export validation to background workers.
     - LLM, VAD, compatibility scoring, transcript summarization, proxy generation, thumbnail extraction, and waveform analysis must be cancellable, deduplicated, and resource-budgeted so they do not steal cores from active subtitle conversion or playback.
     - Save/close must not wait on optional cache generation. Optional proxy/cache jobs should persist as stale/rebuildable metadata and resume later.
   - Jammini reference review: `.agents/sentinel/handoffs/20260629-162317-roughcut-nle-responsiveness-scout.md` recommended magnetic node snapping, reference-id practice notebook switching, in-memory transaction journal, viewport clipping, low-latency trim preview, and do-not-touch protection for OpenGL/3D/STT/VAD/final subtitle kernels. Dex adopts these as planning constraints, except Lightworks-style database ideas are mapped to local project metadata/journals rather than a new external database.

잼민이 의견 (원문):

```text
DEX_REVIEW_READY
SCOUT_ID=20260629-145414

### UI draft risk
- 러프컷 내의 기존 UI 요소를 단순히 화면에서 숨김(hide) 처리할 때, 숨겨진 레이아웃이 잔존하여 4영역(흰색, 파란색, 노란색, 빨간색)의 고정 레이아웃 배치를 훼손하거나 UI가 깨질 위험이 있습니다. 완전히 layout flow에서 제외하거나 크기를 0으로 만드는 조치가 수반되어야 합니다.
- 색상 테마가 지정되었으나, 기존 AI Subtitle Studio의 다크 모드 및 브랜드 컬러 가이드라인을 어기지 않는 선에서 자연스러운 보더/배경 톤 조절이 필요합니다.

### action item wording
- "G4. Roughcut Scenario Composer Integration and Region Consolidation"
  - 러프컷(Roughcut) 레이아웃 내에서 기존의 개별 컨트롤러들을 정리하고, 4개의 핵심 박스(흰색: 시나리오박스, 파란색: 재료박스, 노란색: 비디오박스, 빨간색: 설정박스) 영역으로 역할을 고정합니다.
  - 시나리오 컷 편집 시 deterministic 규칙(컷 경계, 자막 매칭 기준)을 최우선으로 제공하고, LLM 연동은 시나리오 요약, 제목 추천 및 시나리오 제안 보조 역할에만 제한합니다.
  - 시나리오 생성 모드로 conservative, balanced, highlight 3가지의 후보 제안 알고리즘을 도입합니다.

### validation checklist
- [ ] 4대 영역(시나리오박스, 재료박스, 비디오박스, 설정박스)의 고정된 배경색/보더 및 영역 배치 정합성 확인
- [ ] 기존 러프컷 화면 컨트롤러들이 레이아웃에서 숨겨졌으나, 내부 시그널/슬롯 및 함수가 정상 보존되어 호출 시 오동작하지 않는지 확인
- [ ] deterministic 방식의 컷 후보 탐색 결과와 LLM 보조 결과의 UI 표시 및 합성 파이프라인 검증
- [ ] 시나리오 모드(conservative, balanced, highlight) 전환 및 각각의 시나리오 persistence 정상 작동 여부 검증
- [ ] 편집 이후의 최종 자막 export 및 세션 세이브 파일 무결성(기존 스키마 호환성) 검증

### do-not-touch list
- [ ] STT1, STT2, VAD 연동부 등 core 자막 분석 알고리즘
- [ ] 최종 자막 결정 권한(final subtitle authority) 제어 엔진 및 타임라인 편집 커밋 모델
- [ ] 프로젝트 세이브(.json) 스키마 중 기존 자막 데이터 구조 및 NLE 타임라인 데이터 구조 보존 상태
- [ ] 비디오 렌더러/플레이헤드 및 NLE Export Core 모듈

### verdict
- G4 Roughcut Scenario Composer 초안의 요구사항은 현재 NLE 아키텍처 및 자막 무결성 규칙을 위배하지 않으며 구현 가능한 수준입니다. 단, 기존 UI 요소의 hide 처리가 레이아웃 붕괴를 초래하지 않도록 QLayout 계층 구조에서 정교한 분리 제어가 필요하며, 이 조건이 지켜질 경우 승인(Ready to active) 판정을 내립니다.
```

Dex 반영 메모:

- Jammini의 layout-flow 위험 지적은 detailed plan 2번에 반영한다. 단순 `.hide()`만으로 충분하다고 간주하지 않고, visible layout에서 제외하거나 zero-size hidden legacy container로 이동하는 기준을 둔다.
- Jammini의 색상/브랜드 우려는 detailed plan 3번에 반영한다. 대표님 색상 역할은 유지하되 기존 dark app baseline과 충돌하지 않게 border/background accent로 적용한다.
- Jammini의 deterministic-first, LLM-assist-only, conservative/balanced/highlight 제안은 detailed plan 4번에 그대로 반영한다.
- Jammini의 validation checklist는 acceptance gates와 test plan에 반영한다.
- Jammini의 do-not-touch list는 state/authority guardrails와 rollback 기준에 반영한다.

잼민이 의견 (원문) - roughcut NLE sync and UML-style segment cards:

```text
DEX_REVIEW_READY
SCOUT_ID=20260629-150127

### UI/UX & 데이터 흐름 Risk
- UML 스타일의 노드/커넥터 구조를 PyQt6 GUI 상에 구현할 때, AGENTS.md의 Hard Rules에 명시된 '자막 에디터 상호작용 표면은 2D-only' 규칙을 반드시 준수해야 합니다. QML, OpenGL/Metal 기반의 3D 렌더링 도입은 엄격히 차단되며, 오직 PyQt6의 2D QGraphicsView/QPainter를 통해서만 안전하게 구현되어야 합니다.
- 자막/시나리오/길이 재조립 시 메인 에디터 타임라인의 전체 타임스탬프 일관성이 깨질 위험이 크므로, NLE Mutation 작업 시 트랜잭션 단위 롤백 제어가 동반되어야 합니다.

### action item wording
- "G4. Roughcut Editor NLE Sync & 2D UML-style Segment Nodes"
  - 러프컷과 메인 에디터 간의 자막, 시나리오 순서, 세그먼트 길이 조정 데이터를 NLE 데이터 구조로 연동 및 즉각 양방향 전파를 설계합니다.
  - 중분류 세그먼트 카드를 PyQt6 2D QGraphicsView/QPainter 기반의 UML node 및 connector 방식으로 렌더링하고 레이아웃 흐름을 동기화합니다.

### validation checklist
- [ ] 메인 에디터 자막 수정 시 러프컷 세그먼트 카드 내의 텍스트가 정상 전파 및 즉시 반영되는지 검증
- [ ] 러프컷 세그먼트 순서 변경(Reordering) 및 길이 트림 시 메인 에디터 자막 구조가 정상 재배치되는지 무결성 검증
- [ ] UML 노드/커넥터 렌더링 시 QML/OpenGL 가속이 아닌 순수 PyQt6 2D GraphicsView API만 사용되었는지 소스 검증
- [ ] 대용량 프로젝트(자막 1000개 이상) 로드 상태에서 노드 그래픽 렌더링의 FPS 저하 및 메모리 누수 발생 여부 스트레스 테스트
- [ ] NLE 데이터 동기화 동작 중 자막 타임코드 간 중첩(Overlap)이나 꼬임 현상이 발생하는지 검증

### do-not-touch list
- [ ] QML SceneGraph, OpenGL/Metal-backed UI surface 및 3D 렌더링 라이브러리 도입 차단
- [ ] STT1/STT2 및 VAD 핵심 자막 분석/정밀도 향상 모듈
- [ ] 타임라인 최종 자막 권한(Final Subtitle Authority)의 핵심 트랜잭션 관리 커널

### verdict
- 하드 룰인 2D-only UI 원칙을 위배하지 않는 설계(PyQt6 QGraphicsView 기반)를 유지하고 NLE Sync 무결성 보장을 위한 롤백 기능이 전제된다면, 본 요구사항은 안전하게 구현 가능(Ready to active)합니다.
```

Dex 반영 메모 - roughcut NLE sync and UML-style segment cards:

- Jammini의 양방향 NLE sync 제안은 detailed plan 7번에 반영한다. editor -> roughcut, roughcut -> editor 방향과 commit boundary를 분리한다.
- Jammini의 2D-only UML node/connector 제안은 detailed plan 8번에 반영한다. `QGraphicsView` / `QPainter` 기반으로 제한하고 QML/OpenGL/Metal/3D 도입을 금지한다.
- Jammini의 timestamp consistency 및 transaction rollback 우려는 detailed plan 7번 drift guard, acceptance gates, rollback 기준에 반영한다.
- Jammini의 1000+ subtitle stress-test 제안은 test plan에 반영한다.

잼민이 의견 (원문) - reference-driven card arrangement:

```text
DEX_REVIEW_READY
SCOUT_ID=20260629-150551

### 분석 레퍼런스 대상 및 벤치마킹 포인트
1. **Obsidian Canvas & Figma FigJam (2D 노드 그래프 / 화이트보드)**
   - **영감 포인트**: 2D 무한 캔버스 위에 텍스트 카드(노드)를 자유롭게 배치하고, 커넥터(선)로 관계 및 흐름을 연결하는 직관적 레이아웃.
   - **G4 적용**: 중분류 세그먼트 카드를 2D 노드로 시각화하고, 시나리오 진행 순서를 화살표 커넥터로 연결하여 전체 시나리오 흐름을 시각적으로 파악하도록 구성.
2. **Scrivener Index Card & Trello (스토리보드 / 칸반)**
   - **영감 포인트**: 시나리오의 씬(Scene)을 개별 인덱스 카드로 카드화하여, 카드 순서를 재배치하면 전체 글/시나리오 구성 순서가 동기화되어 재조립되는 흐름.
   - **G4 적용**: 러프컷 에디터에서 세그먼트 카드의 위치를 물리적으로 드래그 앤 드롭하여 재정렬(Reordering)하면 메인 에디터의 자막 타임라인 구조와 길이가 실시간 동기화되는 NLE Sync 모델의 기초로 활용.
3. **DaVinci Resolve Storyboard Mode (NLE Bin / Storyboard)**
   - **영감 포인트**: 미디어 클립을 타임라인이 아닌 스토리보드 형태의 썸네일 카드로 나열하고 각각의 인/아웃 포인트를 시각적으로 트림 조절하는 구조.
   - **G4 적용**: 노란색 비디오박스 내에 컷의 대표 프레임 썸네일을 표시하고, 카드 상에서 직접 길이를 줄이거나 트림할 수 있는 인터페이스 차용.

### UI/UX & 데이터 흐름 Risk
- **2D-only 규칙 준수**: 캔버스의 확대/축소(Zooming) 및 드래그 스크롤 구현 시, 하드 룰에 맞춰 WebGL이나 OpenGL 3D 기법을 일절 배제해야 합니다. 오직 PyQt6 `QGraphicsView`의 CPU 기반 2D Transform 및 `QPainterPath` 렌더링으로 최적화하여 1000개 이상의 자막 노드가 렌더링될 때의 FPS 저하를 방지해야 합니다.
- **레이아웃 꼬임**: 노드 재배치 시 커넥터 라인들이 복잡하게 얽히는 현상(Spaghetti code style UI)을 막기 위해, 기본적인 격자 정렬(Grid snapping) 및 위상 정렬(Topological sort) 기반 자동 배치 알고리즘이 보조적으로 지원되어야 합니다.

### G4 계획 반영 문구 (action item wording)
- "G4. Reference-driven 2D Node Layout and Segment Card Storyboarding"
  - Obsidian Canvas 및 Scrivener의 카드 지향 재조립 개념을 벤치마킹하여, PyQt6 2D GraphicsView 환경 하에 세그먼트 카드 정렬 및 노드 인터페이스 레이아웃을 구현합니다.
  - 마우스 드래그 기반 격자 스냅 및 자동 커넥터 라우팅 엔진을 2D-only 환경에서 순수 수학적 좌표 계산을 통해 설계합니다.

### validation checklist
- [ ] Obsidian Canvas 스타일의 노드 연결 상태 시각화 및 커넥터 렌더링 성능 검증 (OpenGL/QML 호출 전무함 검증)
- [ ] 마우스 드래그 앤 드롭을 통한 세그먼트 카드 순서 재조립 및 그리드 스냅 정상 작동 확인
- [ ] 카드가 100개 이상 배치된 대형 프로젝트 캔버스에서 Zoom In/Out 및 패닝(Panning) 시 프레임 유지력(최소 30 FPS 이상) 검증
- [ ] 노드 연결선(Connector) 드로잉 시 순수 `QPainter`만을 사용해 라인과 화살표 머리가 깨짐 없이 부드럽게 그려지는지 검사

### do-not-touch list
- [ ] OpenGL 가속 레이어, QML WebEngine 뷰어 등 3D 및 웹 가속 기반 렌더링 모듈 도입 절대 차단
- [ ] 타임라인 자막 트랜잭션 코어 모듈 및 STT/VAD 음성 인식 백엔드

### verdict
- 제안된 벤치마킹 레퍼런스는 하드 룰(2D-only) 범주 내인 PyQt6 `QGraphicsView` 기술 셋으로 충분히 커버가 가능하며, 러프컷의 스토리보드 조립 UX 사용성을 극대화하므로 안전하게 추진 가능(Ready to active)합니다.
```

Dex 반영 메모 - reference-driven card arrangement:

- Jammini의 Obsidian/FigJam 2D node graph 제안은 detailed plan 9번의 whiteboard/node reference와 adopted layout rules에 반영한다.
- Jammini의 Scrivener/Trello card rearrangement 제안은 detailed plan 9번의 storyboarding, Kanban/database-card reference, commit-boundary rule에 반영한다.
- Jammini의 DaVinci Resolve storyboard/bin 제안은 detailed plan 9번의 NLE/media-browser reference와 card video preview rule에 반영한다.
- Jammini의 grid snapping, topological sort, connector-routing, and 2D-only performance risk는 detailed plan 9번 adopted layout rules, non-goals, test plan, acceptance gates, rollback 기준에 반영한다.

잼민이 의견 (원문) - roughcut segment topic/tag metadata and LoRA feedback:

```text
DEX_REVIEW_READY
SCOUT_ID=20260629-150029

### UI/UX & 데이터 흐름 Risk
- 러프컷 에디터 내에서 주제 및 태그의 수정 권한을 독점하되 에디터로 반영되어야 하므로, 두 컴포넌트 간 메타데이터 동기화 시점(실시간 vs 저장 시점)에 따라 메모리 내 객체 불일치가 발생할 위험이 있습니다. 안정적인 동기화 브릿지가 필요합니다.
- LoRA 학습 피드백 수집 로그에 예외 사항(수정 취소, 파일 파손 등) 발생 시 누적 데이터가 오염되지 않도록 트랜잭션 단위 기록 혹은 검증 로직이 필요합니다.

### action item wording
- "G4. Roughcut Segment Topic/Tag Metadata Flow and LoRA Feedback Logging"
  - 러프컷 중분류 세그먼트 생성 시 주제와 주요 태그를 추출 및 저장하고, 이 메타데이터를 러프컷 에디터와 메인 에디터 간에 일관되게 전파합니다.
  - 수정 권한을 러프컷 에디터에 한정하고, 수정된 최신 결과를 메인 에디터 상태 및 프로젝트 파일 스키마에 동기화합니다.
  - 주제/태그 수정 결과를 딥러닝/LoRA 학습용 피드백 데이터 포맷으로 로컬 저장소에 안전하게 수집 및 기록합니다.

### validation checklist
- [ ] 러프컷 추출 단계에서 중분류 세그먼트의 주제/태그 메타데이터가 정상 생성되고 러프컷 에디터로 전송되는지 검증
- [ ] 러프컷 에디터에서 주제/태그 수정 시 메인 에디터의 메모리 내 메타데이터에 즉각 반영되는지 확인
- [ ] 프로젝트 세이브(.json) 파일 저장 후 재로드 시 수정된 주제/태그 정보가 그대로 복원되는지 무결성 검증
- [ ] 주제/태그가 수정될 때마다 LoRA 피드백 로그 파일(예: JSON 또는 JSONL 규격)에 수정 전/후 데이터와 세그먼트 정보가 정확히 기록 및 누적되는지 확인
- [ ] 메타데이터 동기화 도중 타임라인의 자막 텍스트나 타임코드 등 원본 데이터 훼손이 없는지 역행 검증

### do-not-touch list
- [ ] 자막 원본 텍스트 및 타임라인 경계(Final Subtitle Authority)의 구조적 정보
- [ ] core STT 엔진 및 VAD 분석 모듈
- [ ] LoRA 모델 자체의 가중치(Weights) 파일 및 파인튜닝 가속기(ANE) 호출 코어 드라이버
- [ ] 기존 프로젝트 파일(.json) 로드 시 메타데이터 필드가 누락된 레거시 세이브 파일의 하위 호환성 지원 로직

### verdict
- 본 초안 계획은 데이터 수집 루프 및 러프컷 활용성 향상에 매우 기여하며, 타임라인의 핵심 자막 데이터 영역을 건드리지 않으므로 안전하게 구현 가능(Ready to active)합니다.
```

Dex 반영 메모 - roughcut segment topic/tag metadata and LoRA feedback:

- Jammini의 metadata sync bridge 우려는 detailed plan 10번에 반영한다. roughcut editor를 topic/tag edit authority로 두고 NLE/runtime projection으로 main editor display와 save/reopen state에 반영한다.
- Jammini의 LoRA feedback contamination 우려는 detailed plan 10번 transactional feedback logging 조건에 반영한다. cancelled/corrupt/missing-id/drifted-range rows는 personalization store에 넣지 않는다.
- Jammini의 project reload integrity checklist는 test plan과 acceptance gates에 반영한다.
- Jammini의 do-not-touch list는 state/authority guardrails와 rollback 기준에 반영한다. LoRA feedback rows는 수집하되 model weights나 accelerator driver는 건드리지 않는다.

잼민이 의견 (원문) - settings box segment detail fields:

```text
DEX_REVIEW_READY
SCOUT_ID=20260629-151426

### UI/UX & 데이터 흐름 Risk
- **데이터 유실 위험**: 사용자가 설정박스 내 필드(주제, 태그, 요약 텍스트)를 편집하다가 다른 노드를 선택(Selection change)할 때 변경 사항이 커밋되지 않고 날아가는 포커스 유실 위험이 높습니다. Selection 변경 이벤트 핸들러에서 임시 데이터의 Auto-commit 혹은 Dirty 감지 후 팝업 경고 등의 예방 장치가 필수적입니다.
- **타임코드 변조 위험**: 설정박스 내에 표시되는 시간/길이(Duration) 정보 필드를 실수로 편집하게 허용하면 자막 경계의 무결성이 붕괴하므로, 시간 정보 필드는 엄격하게 Read-only(QTextEdit/QLineEdit readOnly=True 또는 QLabel)로 제약해야 합니다.

### G4 계획 반영 문구 (action item wording)
- "G4. Settings Box Sub-component and Metadata Editor Panel"
  - 빨간색 설정박스(Settings Box) 영역 내에 선택된 중분류 세그먼트 카드의 상세 속성(요약 내용, 시작/종료 시간 및 길이, 주제, 태그 목록)을 렌더링하는 UI 컴포넌트를 설계합니다.
  - 주제(QComboBox / QLineEdit) 및 태그(QTextEdit / Chip editor) 입력 필드 구현 및 변경 사항 발생 시 Dirty state 감지기 및 selection-change 기반 자동 커밋 루틴을 개발합니다.

### validation checklist
- [ ] 노드 카드 선택 변경 시 설정박스의 상세 필드 내용들이 올바르게 갱신(Binding)되는지 검증
- [ ] 설정박스 내의 데이터(주제/태그 등) 수정 도중 노드 선택을 바꿨을 때 자동 저장이 누락 없이 작동하는지 검증
- [ ] 시간/길이 정보 표시 필드가 비활성화(Read-only) 상태로 키보드 입력이 차단되어 있는지 검증
- [ ] 비정상적인 포커스 아웃(앱 포커스 아웃 등) 상태에서도 편집 중이던 임시 데이터가 유실되지 않는지 강제 종료 테스트
- [ ] 저장 및 재로딩 시 설정박스에서 수정한 주제/태그 메타데이터가 프로젝트 세이브 파일에 정확하게 영속화되는지 검증

### do-not-touch list
- [ ] 세그먼트 시간/타임스탬프 정보의 강제 오버라이트 편집 입력기 차단
- [ ] STT/VAD 분석 모듈 및 최종 자막 무결성 관리자
- [ ] 세이브 포맷(.json)의 코어 자막 레코드 필드 구조

### verdict
- 제안된 상세 필드 및 PyQt6 컴포넌트 구성은 기존 NLE 아키텍처 및 2D-only UI 원칙을 침해하지 않으며, 포커스 아웃/Selection 변경 시점의 Auto-commit 메커니즘을 동반하면 안전하게 구현 가능(Ready to active)합니다.
```

Dex 반영 메모 - settings box segment detail fields:

- Jammini의 설정박스 상세 필드 제안은 owner-approved region contract의 `설정박스`와 detailed plan 11번에 반영한다.
- Jammini의 dirty-state/selection-change 데이터 유실 우려는 detailed plan 11번 auto-commit/warning 조건과 test plan에 반영한다.
- Jammini의 time/duration read-only guardrail은 detailed plan 11번, acceptance gates, rollback 기준에 반영한다.
- Jammini의 save/reload metadata persistence checklist는 test plan과 acceptance gates에 반영한다.

잼민이 의견 (원문) - scenario practice notebook candidates:

```text
DEX_REVIEW_READY
SCOUT_ID=20260629-151734

### UI/UX & 데이터 흐름 Risk
- **참조 무결성 위험**: 일반 에디터에서 특정 자막을 삭제하여 중분류 세그먼트가 사라졌으나, 연습노트 후보군 내부의 순서 리스트가 해당 세그먼트의 ID를 여전히 참조하여 로딩 시 널포인터 크래시(Null Pointer Crash)를 유발할 수 있습니다.
- **마이그레이션 위험**: 연습노트 스키마 추가로 인해 기존 저장 파일(.json) 구조와 호환되지 않아 구버전 프로젝트 파일을 열었을 때 오류가 발생할 위험이 있습니다.

### G4 계획 반영 문구 (action item wording)
- "G4. Multiple Scenario Practice Notebooks and Project State Persistence"
  - 러프컷 조립 창에서 독립적인 여러 시나리오 조립 후보군(순서, 연결선, 카드 선택 상태)을 '연습노트' 목록 형태로 관리하고 전환할 수 있는 기능을 설계합니다.
  - 연습노트 내역을 프로젝트 세이브 포맷(.json)에 직렬화(Serialization)하고, 파일 로딩 시 복원하는 프로젝트 IO 및 복구 파이프라인을 구현합니다.
  - 고아 세그먼트 ID 참조 검증 및 필터링 가드를 탑재하여 참조 무결성을 보장합니다.

### validation checklist
- [ ] 여러 개의 시나리오 조립 후보 생성, 수정 후 세이브 및 정상 로드 여부 검증
- [ ] 세그먼트 카드가 일반 에디터 조작으로 인해 삭제/병합되었을 때, 연습노트 후보군 목록 내에서도 안전하게 필터링되어 복원 크래시를 유발하지 않는지 에러 핸들링 검증
- [ ] 후보군 간 전환 속도 및 빈번한 전환 시 발생할 수 있는 메모리 누수나 UI 갱신 성능 체크
- [ ] 연습노트 메타데이터가 없는 구버전 프로젝트 세이브 파일을 열었을 때 기본 상태(Empty Candidate)로 오류 없이 초기화되는지 역호환성 검증

### do-not-touch list
- [ ] 최종 자막 텍스트와 타임코드 편집 핵심 트랜잭션 로직
- [ ] 레거시 저장 파일 포맷 파싱 코어 모듈
- [ ] STT/VAD 음성 처리 백엔드

### verdict
- 복수 후보의 상태 직렬화 및 마이그레이션 호환성을 고려한 가드(Referential check)가 확보된다면, 본 연습노트 요구사항은 안정적인 NLE sync 구현의 일환으로 안전하게 진행 가능(Ready to active)합니다.
```

Dex 반영 메모 - scenario practice notebook candidates:

- Jammini의 복수 연습노트 후보 제안은 owner-approved `시나리오박스` contract와 detailed plan 12번에 반영한다.
- Jammini의 순서/연결선/카드 선택 상태 저장 요구는 detailed plan 12번의 notebook payload 필드와 project persistence 조건에 반영한다.
- Jammini의 프로젝트 IO 직렬화/복원 요구는 roughcut state 기반 `candidates`, `selected_candidate_id`, `segment_order`, `chapter_order`, `candidate_count` 저장 계획에 반영한다.
- Jammini의 고아 세그먼트 ID 및 널포인터 크래시 위험은 orphan reference filtering/stale review state, acceptance gates, rollback 기준에 반영한다.
- Jammini의 구버전 프로젝트 호환성 우려는 versioned legacy-compatible fields, empty-candidate fallback, test plan에 반영한다.

잼민이 의견 (원문) - scenario-window whole-video LLM summary:

```text
DEX_REVIEW_READY
SCOUT_ID=20260629-152143

### UI/UX & 데이터 흐름 Risk
- **UI 블로킹 위험**: LLM 요약 API 호출 시 네트워크 대기 시간 동안 PyQt6의 메인 GUI 스레드가 대기 상태에 빠져 앱이 먹통이 되는 크리티컬한 현상이 발생할 수 있습니다. 반드시 QThread나 Worker 비동기 백그라운드 스레드를 사용해야 합니다.
- **과도한 API 호출 및 비용**: 카드를 드래그하여 순서를 바꿀 때마다 실시간으로 LLM 요약을 재요청하면 불필요한 API 비용 및 성능 저하가 발생합니다. 편집 후 일정 시간(예: 3~5초) 이상 입력이 멈췄을 때 트리거되는 디바운싱(Debouncing) 타이머 제어 혹은 명시적인 '요약 업데이트' 버튼(UI) 구조가 필요합니다.
- **토큰 제한 초과**: 자막 전체 텍스트와 메타데이터가 초대형일 경우 컨텍스트 윈도우가 넘칠 수 있으므로 프롬프트 빌더에서 데이터 정제 및 요약 위주의 적정 토큰 관리가 수반되어야 합니다.

### G4 계획 반영 문구 (action item wording)
- "G4. Scenario-driven Whole-video LLM Summary Engine"
  - 시나리오창에 조립된 세그먼트 카드의 순서, 활성화 여부, 자막 요약문, 주제, 태그를 종합 수집하여 구조화된 프롬프트를 구성합니다.
  - PyQt6 비동기 Worker 스레드를 설계하여 LLM 요약을 호출하고, 완료 시그널을 통해 시나리오 창의 요약 패널을 업데이트합니다.
  - 불필요한 중복 호출 방지를 위해 디바운싱(Debouncing) 혹은 명시적 생성 버튼 게이트웨이를 구축합니다.

### validation checklist
- [ ] LLM 요약 API 호출 중 자막 탐색, 동영상 재생 등 메인 GUI 스레드가 멈추지 않고 반응성을 유지하는지 확인
- [ ] API 타임아웃, 네트워크 단절, 토큰 초과 에러 발생 시 UI 단에서 정상적으로 플레이스홀더 복구 및 오류 메시지를 안내하는지 검증
- [ ] 노드 순서가 빈번하게 변경될 때 디바운스 처리를 통해 API 다중 중복 호출이 정확히 1회로 제한되는지 모니터링 검사
- [ ] 생성된 요약문이 프로젝트 세이브(.json)에 안전하게 저장되고, 재로딩 시 API 호출 없이 저장본을 즉시 노출하는지 복원 무결성 검증

### do-not-touch list
- [ ] STT1/STT2 및 VAD 핵심 음성 분석 백엔드
- [ ] 타임라인 최종 자막 결정 모델 및 입출력 하위 호환성 레이어

### verdict
- GUI 블로킹을 방지하기 위한 비동기 백그라운드 스레드 설계 및 디바운스/수동 업데이트 버튼 가이드가 확보된다면, 본 계획안은 안정적으로 구현 가능(Ready to active)합니다.
```

Dex 반영 메모 - scenario-window whole-video LLM summary:

- Jammini의 scenario-driven summary 제안은 owner-approved `시나리오박스` contract와 detailed plan 13번에 반영한다.
- Jammini의 UI blocking 우려는 background worker/async task requirement, acceptance gates, rollback 기준에 반영한다.
- Jammini의 과도한 API 호출/비용 우려는 debounce/dirty-state/explicit update gate 조건에 반영한다.
- Jammini의 token limit 우려는 prompt builder compression/token control 조건에 반영한다.
- Jammini의 save/reload checklist는 saved summary, prompt input signature, scenario order hash, stale marking, test plan에 반영한다.
- Jammini의 do-not-touch list는 final subtitle/timing/export authority, STT1/STT2/VAD guardrails에 반영한다.

잼민이 의견 (원문) - middle-segment split and merge:

```text
DEX_REVIEW_READY
SCOUT_ID=20260629-152434

### UI/UX & 데이터 흐름 Risk
- **자막 무결성 붕괴**: 드래그앤드롭으로 두 카드를 병합(Merge)할 때 속한 자막들의 타임라인상 타임스탬프 중첩(Overlap)이나 꼬임 현상이 일어날 수 있습니다.
- **분할(Split) 지점의 예외 상황**: 자막 텍스트의 중간 한가운데 프레임에서 분할을 수행할 때, 해당 자막의 분할 방식(자막 경계 우선 분할 vs 자막 텍스트 쪼개기 및 타임코드 보간)이 명확해야 하며, 보간 실패 시 자막 누락 위험이 큽니다.
- **트랜잭션 롤백 불가**: 분할/병합은 고단도 NLE Mutation이므로 조작 실패 시 프로젝트 데이터를 손상시킬 수 있습니다. 반드시 완전한 롤백을 보장하는 트랜잭션 가드가 필요합니다.

### G4 계획 반영 문구 (action item wording)
- "G4. Middle-segment Split/Merge Operations and Timeline Recalculation"
  - 드래그앤드롭 기반의 중분류 세그먼트 카드 병합(Merge) 및 타임코드/자막 경계 기반의 카드 분할(Split) 기능의 UI/UX 및 단일 컷 편집 상호작용을 설계합니다.
  - 분할/병합 연산 시 자막 텍스트의 분리/결합 및 타임스탬프 재계산 규칙을 탑재하고, 트랜잭션 무결성을 보호할 NLE Rollback Guard를 구축합니다.

### validation checklist
- [ ] 카드 드래그앤드롭 병합 시, 내포된 모든 자막이 시간 순으로 정합성 있게 단일 세그먼트로 결합 및 썸네일 통합이 이루어지는지 검증
- [ ] 임의 프레임 기준 분할 시, 경계면에 걸친 자막이 유실되거나 겹치지 않고 안전한 경계 자막 분할(Split)이 수행되는지 검증
- [ ] 분할/병합 작업 성공 직후 실행 취소(Undo) 시 1프레임 오차 없이 온전하게 이전 카드 및 자막 상태로 복원되는지 검증
- [ ] 0.1초 미만의 극소 간격을 가진 자막들 사이에서 병합/분할 시 충돌이 발생해 롤백 안전장치가 성공적으로 작동하는지 경계 조건 검사
- [ ] 변경된 분할/병합 상태가 프로젝트 저장 파일(.json)에 정상 직렬화 및 복원되는지 검증

### do-not-touch list
- [ ] 타임라인 최종 자막 결정 모델 및 코어 데이터 커널
- [ ] STT1/STT2 정밀 음성 인식 및 VAD 백엔드 모듈
- [ ] 프로젝트 세이브(.json) 파일 IO의 하위 호환성 필터

### verdict
- 분할 경계면에서의 자막 유실 방지 가드 및 Atomic 트랜잭션 롤백 장치가 확실히 수립된다면, 본 계획안은 안전하게 구현 가능(Ready to active)합니다.
```

Dex 반영 메모 - middle-segment split and merge:

- Jammini의 drag/drop merge 제안은 owner-approved `재료박스` contract와 detailed plan 14번에 반영한다.
- Jammini의 cut-edit-style split 제안은 detailed plan 14번의 split interaction, subtitle-boundary preference, active-subtitle split policy에 반영한다.
- Jammini의 timestamp overlap/corruption 위험은 atomic NLE mutation, monotonic order, no-overlap acceptance gate, rollback 기준에 반영한다.
- Jammini의 undo/rollback 요구는 preview/commit/undo/rollback boundary와 test plan에 반영한다.
- Jammini의 save/reopen checklist는 split/merge persistence, practice notebook stale marking, LLM summary signature stale marking에 반영한다.
- Jammini의 do-not-touch list는 final subtitle/timing authority, STT1/STT2/VAD, legacy project IO compatibility guardrails에 반영한다.

잼민이 의견 (원문) - intro/outro and highlight recommendation:

```text
DEX_REVIEW_READY
SCOUT_ID=20260629-152728

### UI/UX & 데이터 흐름 Risk
- **연산 오버헤드**: 전체 영상 오디오의 RMS 에너지와 자막/태그 정보를 종합 연산해야 하므로 영상 길이가 길 경우 과도한 CPU 연산으로 GUI 스레드가 일시 정지(UI Lag)할 위험이 있습니다. 분석 알고리즘은 비동기 방식으로 백그라운드에서 백필(Backfill) 처리되어야 합니다.
- **파괴적 자동 적용**: 시스템이 인트로/아웃트로라고 판단한 구간을 사용자 승인 없이 시나리오 타임라인에 강제 삽입할 경우, 사용자가 작성 중이던 조립 상태를 덮어씌워 유실을 야기할 수 있습니다. 반드시 '추천 후보 카드 목록'을 띄우고 사용자가 승인(Accept)해야 삽입되는 비파괴적(Non-destructive) 설계가 보장되어야 합니다.

### G4 계획 반영 문구 (action item wording)
- "G4. Intro/Outro and Highlight Segment Recommendation Engine"
  - 음성 에너지(RMS), VAD 밀도, 자막 텍스트 키워드 빈도를 복합 가중치 분석하여 영상 내 인트로(도입), 아웃트로(결말), 하이라이트(핵심 발화) 구간 후보를 탐색하는 알고리즘을 설계합니다.
  - 시나리오창 내에 추천 후보를 컴팩트한 카드 리스트 UI로 제시하고, 사용자의 선택적 삽입(Insert/Append) 인터페이스를 구현합니다.
  - 추천 연산을 GUI 스레드와 격리하기 위해 비동기 분석 스레드 핸들러를 구축합니다.

### validation checklist
- [ ] 추천 엔진 연산 동작 중 재생, 자막 편집 등 GUI 반응성이 실시간으로 유지되는지 검증
- [ ] 추천 카드 클릭 시, 사용자가 기존에 조립해 둔 시나리오 캔버스의 데이터가 유실되지 않고 안전하게 추천 노드가 삽입(Insert)되는지 검증
- [ ] 30분 이상의 장비디오 로드 상태에서 추천 연산 처리 시 CPU 점유율 및 메모리 누수 한계선 측정
- [ ] 미디어 파일이 지정되지 않은 상태에서 추천 호출 시 크래시를 방지하고 안전한 예외 경고 창을 띄우는지 검증
- [ ] 추천을 통해 조립된 연습노트를 저장 후 재로드했을 때 타임라인의 자막 싱크와 노드 배치가 정상 복원되는지 검증

### do-not-touch list
- [ ] STT1/STT2 정밀 음성 인식 및 VAD 특징 벡터 추출 모듈
- [ ] 타임라인 최종 자막 권한의 데이터 커널 구조
- [ ] 프로젝트 입출력 파서의 레거시 호환성 필터

### verdict
- 비파괴적 사용자 선택형 UI 가이드 및 CPU 연산 격리를 위한 비동기 스레드 처리가 전제된다면, 본 추천 기능 설계는 안전하게 구현 가능(Ready to active)합니다.
```

Dex 반영 메모 - intro/outro and highlight recommendation:

- Jammini의 intro/outro/highlight recommendation 제안은 owner-approved `시나리오박스` 및 `비디오박스` contract와 detailed plan 15번에 반영한다.
- Jammini의 RMS/VAD/keyword weighted analysis 제안은 deterministic-first scoring 기준에 반영한다.
- Jammini의 GUI lag/CPU overhead 우려는 background worker/backfill requirement, test plan, rollback 기준에 반영한다.
- Jammini의 destructive auto-apply 위험은 non-destructive candidate cards, preview/insert/append-only interaction, acceptance gates에 반영한다.
- Jammini의 save/reload checklist는 accepted/inserted choices, cached candidates, source signature stale marking에 반영한다.
- Jammini의 do-not-touch list는 STT1/STT2/VAD feature extraction, final subtitle authority, legacy project IO compatibility guardrails에 반영한다.

잼민이 의견 (원문) - roughcut to shortform maker handoff:

```text
DEX_REVIEW_READY
SCOUT_ID=20260629-153042

### UI/UX & 데이터 흐름 Risk
- **60초 상한선 초과 위험**: 숏폼 제작기의 핵심 요건인 '1분 이내' 제약 조건이 데이터 인계 시점에 검증되지 않으면, 60초를 초과한 대량의 클립이 전송되어 숏폼 렌더러가 타임라인 렌더링 오류를 유발하거나 오동작을 일으킬 수 있습니다. 반드시 Handoff 시점에 60s Limit Validation 가드가 필요합니다.
- **강한 결합도(Tight Coupling)로 인한 사이드 이펙트**: 러프컷 뷰와 숏폼 뷰가 강하게 얽히면, 향후 PHASE3 숏폼 제작기 실제 기능 구현 시 러프컷 코드까지 연쇄적으로 붕괴될 위험이 있습니다. 느슨한 데이터 전달 브릿지 API 형식으로 입출력을 격리해야 합니다.

### G4 계획 반영 문구 (action item wording)
- "G4. Roughcut-to-Shortform Data Handoff Bridge and 60s Limit Validation"
  - 러프컷 내 중분류 세그먼트 및 시나리오 조립 상태에서 수집된 클립들을 숏폼 제작기로 전송할 Handoff State Payload 규격과 느슨하게 결합된 Bridge 모듈을 선제 구축합니다.
  - 선택된 클립들의 총 길이가 60초를 초과할 경우 전송을 원천 차단하고 UI 가이드를 제시하는 60s Limit Guardrail을 구현합니다.

### validation checklist
- [ ] 선택한 클립들의 총 연장 시간이 60.0초를 넘길 때 숏폼 인계 시도가 차단되고 사용자 제한 경고창이 정확히 유도되는지 검증
- [ ] 숏폼으로 전달될 데이터 패키지(클립 시간대, 매칭 자막 등)가 NLE 데이터 구조를 훼손하지 않고 규격에 맞춰 인계되는지 출력 데이터 정합성 검증
- [ ] 숏폼 메이커 임시 모드 수신 스텁(Stub)에서 데이터 수신 직후 크래시 없이 대기(Idle) 상태를 유지하는지 통합 검증
- [ ] 전송된 숏폼 메타데이터가 프로젝트 저장(.json) 시에 영속화되어, 재로드했을 때 숏폼 에디터 상태 역시 동일하게 재현 복구되는지 검증

### do-not-touch list
- [ ] ui/home_ui.py 내 숏폼 제작기(PHASE3 영역)의 미구현 핵심 뼈대 및 스텁 UI 구성
- [ ] 최종 자막 결정 권한 트랜잭션 모듈 및 STT/VAD 음성 처리 엔진

### verdict
- 60초 시간 한계 검증 가드 및 숏폼 컴포넌트와의 느슨한 데이터 브릿지 구조화 계획이 철저히 준비된다면, 본 핸드오프 설계안은 안전하게 추진 가능(Ready to active)합니다.
```

Dex 반영 메모 - roughcut to shortform maker handoff:

- Jammini의 60초 상한선 초과 위험은 detailed plan 16번의 `<= 60.0` duration budget, handoff-time validation, acceptance gates, rollback 기준에 반영한다.
- Jammini의 tight coupling 우려는 versioned handoff payload, loose bridge/stub, shortform placeholder do-not-touch 조건에 반영한다.
- Jammini의 handoff state payload 제안은 clip ids, source/output ranges, subtitle references, metadata, vertical framing, total duration, stale/review flags payload 구조에 반영한다.
- Jammini의 NLE data integrity checklist는 final subtitle authority guard, read-only payload generation, test plan에 반영한다.
- Jammini의 save/reload checklist는 shortform basket and last payload persistence, source signature stale marking에 반영한다.
- Jammini의 do-not-touch list는 `ui/home_ui.py` PHASE3 shortform stub, final subtitle transaction authority, STT/VAD guardrails에 반영한다.

Dex reference note - AlphaCut-inspired shortform maker:

- AlphaCut's public workflow is used only as an implementation reference for long-form-to-shorts flow, not as a UI/content clone target.
- The reference-informed flow is mapped to local-first AI Subtitle Studio behavior: roughcut handoff payload input, multiple shortform draft cards, 9:16 preview, caption/template/framing controls, non-destructive regenerate, and local export.
- AlphaCut-style external URL import, direct social upload, account/cloud behavior, billing, and public-hosted processing are explicitly out of first-slice scope.
- Existing final subtitle/NLE projection remains caption authority; shortform captions are styling/overlay decisions, not a new STT/default subtitle owner.
- This note extends detailed plan 17, acceptance gates, test plan, and rollback with reference-driven shortform proof requirements.

잼민이 의견 (원문) - scenario storyline visualization:

```text
DEX_REVIEW_READY
SCOUT_ID=20260629-153901

### 분석 레퍼런스 및 적용 모델
1. **Plottr (Subway-map Visual Timeline / Storyline)**
   - **벤치마킹**: 스토리의 캐릭터 궤적이나 테마(Plot line)를 가로축 시간에 따라 노선도 형태로 시각화하는 방식.
   - **G4 적용**: 중분류 세그먼트 카드를 주제, 주요 인물, 또는 자막 톤에 따라 병렬 궤적(Plot lines)으로 배치하여 교차 편집 흐름을 한눈에 보여주는 2D 지하철 노선도 형태의 타임라인을 제공.
2. **Scrivener Index Card Flow (Index Card Grid/Flow)**
   - **벤치마킹**: 카드의 표면에 핵심 로그라인(Logline) 및 요약 시놉시스를 배치하여 전체 플롯 흐름을 텍스트와 레이아웃으로 동시에 추적하는 방식.
   - **G4 적용**: 각 세그먼트 카드 내부에 LLM이 추출한 대표 로그라인(요약 줄거리)을 시각적으로 결합하여 직관성을 극대화.

### UI/UX & 데이터 흐름 Risk
- **레이아웃 꼬임 및 성능 저하**: 노선도 형태의 스토리라인(Plot lines)을 수많은 노드 사이에 드로잉할 때, 노드 수가 50개 이상만 되어도 선이 꼬여 spaghetti UI가 될 위험이 있습니다. 최단 경로 라우팅 계산 및 격자 스냅(Snapping) 가이드가 필수적입니다.
- **2D-only UI 원칙 준수**: 복잡한 노선도와 줌 기능 렌더링에 QML, OpenGL 또는 3D 캔버스를 도입하려는 유혹을 피하고, 오직 PyQt6 `QGraphicsView`의 CPU 2D 좌표 변환만 사용하여 렌더링 부하를 제어해야 합니다.

### G4 계획 반영 문구 (action item wording)
- "G4. Scenario Storyline Visualization and Subway-map Timeline"
  - Plottr의 지하철 노선도(Subway-map) 스타일 벤치마킹을 통해, 중분류 세그먼트 카드를 테마/인물별 병렬 궤적의 2D 스토리라인 타임라인으로 시각화하는 PyQt6 뷰를 설계합니다.
  - 각 세그먼트 카드 내부에 로그라인(요약)을 삽입하는 2D 템플릿과 2D 캔버스 내에서의 노선 경로 연산 모듈을 구축합니다.

### validation checklist
- [ ] 2D QGraphicsView 내에서 노선도 및 화살표 커넥터가 겹침 없이 부드럽게 그려지는지 레이아웃 가시성 검증
- [ ] 스토리라인 캔버스 드래그 패닝(Panning) 및 줌인/줌아웃 시 프레임이 30 FPS 밑으로 떨어지지 않는지 드로잉 부하 테스트
- [ ] 노드 내 텍스트 로그라인이 영역을 벗어나지 않고 엘립시스(...) 처리로 깔끔히 정렬되는지 확인
- [ ] 저장 및 재로딩 시 연습노트별 스토리라인 배치 상태와 궤적 메타데이터가 정상 영속화되는지 검증
- [ ] 구버전 세이브 파일 로드 시 예외 크래시 방지 및 기본 1개 단일 라인으로의 안전한 마이그레이션 확인

### do-not-touch list
- [ ] QML SceneGraph, OpenGL/Metal 가속 뷰어 등 3D 드로잉 라이브러리 도입 금지
- [ ] 최종 자막 결정 모델 및 코어 데이터 모델
- [ ] STT/VAD 음성 분석 엔진

### verdict
- 복잡한 3D 가속 없이 PyQt6 2D GraphicsView를 유지하고, 선 꼬임 방지를 위한 격자 및 최단 경로 스냅 규칙이 구현된다면 본 줄거리 시각화 계획안은 안전하게 추진 가능(Ready to active)합니다.
```

Dex 반영 메모 - scenario storyline visualization:

- Jammini의 Plottr/subway-map parallel plotline 제안은 detailed plan 18번의 optional subway-map/parallel plotline view, lane grouping, connector routing에 반영한다.
- Jammini의 Scrivener index-card/logline 제안은 middle-segment card logline, synopsis, corkboard card grid view에 반영한다.
- Jammini의 connector clutter/spaghetti UI 위험은 grid snapping, lane grouping, safe-threshold fallback, acceptance gates, rollback 기준에 반영한다.
- Jammini의 2D-only 요구는 PyQt6 `QGraphicsView`/`QPainter`만 허용하고 QML/OpenGL/Metal/web/3D rendering 금지 조건에 반영한다.
- Jammini의 save/reload checklist는 storyline state persistence, source signature stale marking, legacy one-line migration fallback에 반영한다.
- Jammini의 do-not-touch list는 final subtitle/core data authority and STT/VAD guardrails에 반영한다.

잼민이 의견 (원문) - screenplay-oriented shot assembly composer:

```text
DEX_REVIEW_READY
SCOUT_ID=20260629-154450

### Screenplay Composer 관점 추가/수정 기능 설계안
1. **대본 계층 구조화 (Sequence/Scene/Beat/Dialogue)**
   - 중분류 카드를 대본의 Sequence > Scene > Beat > Dialogue/Action 계층에 매핑하고, 설정박스 내에 '씬 목적(Cut purpose)' 및 '비트 성격' 분류 필드를 지원합니다.
2. **샷 어셈블리 및 아웃라인 (Shot Assembly & Script Outline)**
   - 대본 목차(Script Outline) 패널을 좌측 트리 뷰로 구현하고, 트리 항목 클릭 시 2D 시나리오 캔버스의 매칭 노드로 화면이 즉시 포커스 스크롤되도록 연동합니다.
3. **연속성 및 B-roll/대체 테이크 (Continuity, Alternate Takes & B-roll/Insert/Reaction)**
   - 씬 카드 내에 주영상(A-roll) 외에 B-roll, 인서트, 리액션 샷을 레이어 구조로 할당하여 연속성(Continuity)을 시각화합니다.
   - 동일 구간에 대해 복수의 촬영본(Alternate takes)이 존재할 경우 카드 내 스위처를 통해 손쉽게 전환할 수 있도록 구조화합니다.
4. **누락/갭 감지 및 감독 메모 (Missing Shot/Gap Detection & Director Note)**
   - 자막이 비어 있거나 오디오 신호가 없는 갭(Gap) 구간을 자동 스캔하여 적색 빈 슬롯 플레이스홀더 카드로 캔버스 상에 노출합니다.
   - 각 카드마다 연출 지시사항을 기록할 Director Note 메모 필드와 변경 기록(Revision History) 저널링을 탑재합니다.
5. **테이블 리드 프리뷰 (Table-read Style Preview)**
   - 비디오 없이 대본 형식의 텍스트 스크롤 뷰어 형태로 시나리오 조립본을 순서대로 읽고, 스크롤 플레이헤드를 비디오 프레임 시간대와 2D 싱크 연동하여 추적합니다.

### UI/UX & 데이터 흐름 Risk
- **대형 아웃라인 연산 성능**: 대본의 계층이 깊어지고 자막 수천 개가 결합되면 대본 뷰어와 아웃라인 트리의 렌더링 성능이 하락할 수 있어 비동기 레이아웃 생성 모델이 필수적입니다.
- **Shot-to-subtitle Authority Guard**: 대본 재조립 연산 시 자막의 시간 경계가 어긋나거나 중첩되지 않도록, NLE Commit Boundary 진입 전에 타임코드 충돌 및 자막 무결성 규칙을 선제 검사해야 합니다.

### validation checklist
- [ ] 대본 아웃라인 트리 항목 클릭 시 2D 캔버스의 노드 카드로 부드럽게 화면 이동이 유기적으로 이루어지는지 검증
- [ ] Gap 감지기가 타임라인 내 자막/영상 공백 구간을 ms 단위로 정확히 찾아내어 적색 Placeholder 카드로 시각화하는지 정밀도 검증
- [ ] Alternate take 전환 스위치 작동 시, 메모리 상의 대상 클립 영상 정보가 즉시 갱신 및 재생 싱크와 맞물리는지 검증
- [ ] 테이블 리드 뷰어의 텍스트 줄바꿈 및 스크롤 추적 시 플레이헤드 싱크와 2D 오차가 없는지 프레임 정밀도 측정
- [ ] 저장 및 재로딩 시 대본 구조, 감독 메모, B-roll 레이어 및 Alternate take 선택 상태가 프로젝트 json 스키마에 안전하게 영속화되는지 검증

### do-not-touch list
- [ ] QML/OpenGL 기반의 가속 대본 렌더링 엔진 차단 (순수 2D PyQt GUI 유지)
- [ ] 최종 자막 권한 트랜잭션 관리자 및 STT/VAD 음성 처리 모듈
- [ ] 프로젝트 세이브(.json) 파일 포맷 파서 하위 호환성 레이어

### verdict
- 2D-only UI 원칙을 엄격하게 지키고, 대본 조립 데이터와 자막 데이터의 동기화 무결성을 지킬 Shot-to-subtitle guardrail이 전제된다면 본 대본 지향 컷 조립 계획안은 안전하게 구현 가능(Ready to active)합니다.
```

Dex 반영 메모 - screenplay-oriented shot assembly composer:

- Jammini의 Sequence/Scene/Beat/Dialogue 계층 제안은 detailed plan 19번의 script hierarchy, script outline, settings-box script fields에 반영한다.
- Jammini의 shot assembly/script outline 제안은 `시나리오박스` script outline click-to-focus, 2D scenario canvas focus, video preview range sync에 반영한다.
- Jammini의 A-roll/B-roll/insert/reaction/alternate take 제안은 shot role metadata, layered scene planning, non-destructive alternate take switcher에 반영한다.
- Jammini의 missing shot/gap detection 제안은 subtitle/audio/video/topic discontinuity gap detection and red placeholder cards에 반영한다.
- Jammini의 director note/revision history 제안은 roughcut-only director notes, notebook/card/scene notes, and revision journal pointers에 반영한다.
- Jammini의 table-read preview 제안은 text-only screenplay scroll view with playhead/video sync and no new subtitle authority에 반영한다.
- Jammini의 performance risk는 async/debounced script outline and table-read layout generation에 반영한다.
- Jammini의 Shot-to-subtitle Authority Guard는 NLE commit boundary preflight, invalid duration/overlap/non-monotonic/text-drift/source-ref checks, acceptance gates, and rollback에 반영한다.
- Jammini의 do-not-touch list는 PyQt6 2D-only, final subtitle transaction authority, STT/VAD, and legacy project parser compatibility guardrails에 반영한다.

잼민이 의견 (원문) - middle-segment compatibility scoring:

```text
DEX_READY
SCOUT_ID=20260629-155507

### G4 궁합 점수 및 관계 그래프 설계안
1. **궁합 점수 모델 및 시각화 인코딩 (Compatibility Score & Visual Encoding)**
   - 세그먼트 간 궁합 점수(0~100)를 연산하여, 2D 캔버스 상에서 선의 두께, 형태(실선/점선), 색상(녹색: 고연관, 적색: 대립/충돌)으로 렌더링합니다.
2. **사용자 정의 관계 오버라이드 (Author-defined Relation Overrides)**
   - 설정박스(Settings Box) 내에 관계 제어 필드를 두어 사용자가 두 노드 간의 관계 유형(인과, 보완, 대립 등)과 점수를 수동 기입하고 비대칭(Asymmetric) 및 양방향(Bidirectional) 링크를 설정하게 지원합니다.
3. **Deterministic + LLM 복합 스코어링**
   - 컷 연속성 및 키워드 매칭(Deterministic) 점수를 베이스로 잡고, 백그라운드 LLM 비동기 스레드를 활용해 문맥 궁합 점수를 산출하되, 사용자의 수동 오버라이드를 최종 우선권으로 둡니다.
4. **시나리오 재작성 제안 및 만료 관리 (Rewrite Suggestions & Stale Handling)**
   - 최적 관계 그래프에 기반하여 시나리오 카드를 재정렬해주는 자동 재작성(Rewrite) 가이드를 제공합니다.
   - 분할/병합 및 에디터 자막 수정 발생 시, 연관 노드의 링크를 Stale(만료) 표시하고 비동기 재계산 스레드로 백그라운드 재연산 후 반영합니다.

### UI/UX & 데이터 흐름 Risk & App Store Safety
- **개인정보 및 App Store Connect**: LLM 문맥 평가 시 로컬 정보 노출이 없도록 세그먼트 텍스트 및 메타데이터를 완벽히 익명화(Anonymize) 처리하여 호출해야 합니다.
- **NLE/Final Subtitle Authority Guard**: 관계 그래프 연산 및 자동 재배치가 메인 자막 데이터 영역을 강제로 훼손할 수 없도록, 오직 시나리오 후보군의 순서 배열에만 영향을 미치게 샌드박스 격리해야 합니다.

### validation checklist
- [ ] 설정박스에서 관계 유형 및 오버라이드 점수 입력 시 2D 연결선의 색상/두께가 실시간 정상 갱신되는지 검증
- [ ] 세그먼트 분할/병합 직후 기존 관계 링크들이 Stale(만료) 상태로 정상 판정되고 비동기 재계산 스레드가 GUI 프리징 없이 작동하는지 확인
- [ ] LLM API 호출 전송 데이터 내에 개인정보(PII)가 유실되어 완벽히 익명화된 상태로 호출되는지 검증
- [ ] 관계 그래프에 따른 시나리오 재작성 가이드 적용 시, 기존 자막의 타임코드가 충돌 없이 정렬 재배치되는지 NLE 트랜잭션 무결성 검증
- [ ] 수동 입력 관계 메트릭 정보가 프로젝트 세이브 json에 영속화되고 재로드 시 고스란히 복원되는지 검증

### do-not-touch list
- [ ] OpenGL 가속 및 3D 궤적 렌더링 라이브러리 도입 절대 차단
- [ ] 최종 자막 결정 모델 및 코어 STT/VAD 음성 엔진

### verdict
- 비동기 Stale 재계산 스레드 및 LLM 개인정보 익명화 가이드가 철저히 지켜진다면, 본 세그먼트 궁합 점수 계획안은 안전하게 구현 가능(Ready to active)합니다.
```

Dex 반영 메모 - middle-segment compatibility scoring:

- Jammini의 0~100 궁합 점수 및 색/선/두께/형태 인코딩 제안은 detailed plan 24번의 score buckets, visual encoding, and PyQt6 2D connector rendering에 반영한다.
- Jammini의 설정박스 수동 관계 오버라이드 제안은 relation controls, source/target selection, relation type, score, directionality, reason, active state, and rewrite influence fields에 반영한다.
- Jammini의 비대칭/양방향 링크 제안은 directional relation metadata, visible arrows/labels, and rewrite-only influence에 반영한다.
- Jammini의 deterministic + LLM 복합 스코어링 제안은 deterministic base inputs, LLM-assist-only rationale/label suggestions, and manual override highest priority에 반영한다.
- Jammini의 시나리오 재작성 가이드 제안은 non-destructive rewrite suggestions, alternative practice notebook candidates, and no auto-commit to editor/NLE/final exports에 반영한다.
- Jammini의 split/merge/editor-change stale handling 제안은 affected relation stale marking, async recalculation, save/reopen persistence, and trace requirements에 반영한다.
- Jammini의 개인정보/App Store 안전 요구는 redacted/anonymized LLM inputs, local-first traces, no raw subtitle/path/prompt logging, and G4 App Store/privacy guard에 반영한다.
- Jammini의 NLE/final subtitle guard는 relationship graph sandboxing, final subtitle authority preservation, and rollback gates에 반영한다.
- Jammini의 do-not-touch list는 OpenGL/3D/web-canvas 금지와 final subtitle/STT/VAD engine non-goals에 반영한다.

잼민이 의견 (원문) - initial roughcut order seeds and user-order rewrite:

```text
DEX_READY
SCOUT_ID=20260629-155855

### G4 초기 시드 스위처 및 시나리오 재작성 설계안
1. **초기 순서 시드 스위처 (Initial Order Seeds Selector)**
   - 러프컷 최초 생성 단계에서 2가지 초기 시드(1. LLM 문맥 기반 추천 순서, 2. 에디터 시간축 기본 순서)를 선택하여 2D 캔버스 노드 정렬을 즉시 전환할 수 있는 스위처 UI를 설계합니다.
2. **수동 정렬 기반 시나리오 재작성 (User-order Scenario Rewrite)**
   - 사용자가 드래그로 조립한 임의의 카드 순서를 입력 피드로 받아, LLM이 조립 상태의 논리 흐름을 보완해 시나리오 시놉시스 및 구성을 재작성(Rewrite) 및 요약하는 비동기 프롬프트 엔진을 구축합니다.

### UI/UX & 데이터 흐름 Risk
- **수동 작업 유실 위험**: 사용자가 카드를 정성껏 정렬해 둔 상태에서 실수로 시드 스위처를 누르면 기존 수동 레이아웃 정보가 덮어씌워져 파손됩니다. 수동 조작 상태가 감지된 경우, 시드 전환 시 경고 경보창(Warning Dialog)을 호출하거나 해당 상태를 연습노트의 임시 슬롯으로 자동 백업하는 안전장치가 동반되어야 합니다.
- **NLE/Final Subtitle Authority Guard**: 추천 순서 적용 및 시나리오 재작성 결과의 즉각 적용 시, 메인 타임라인의 자막 구조와 싱크가 꼬이지 않도록 커밋 경계(Commit Boundary) 전까지는 러프컷 뷰 상의 샌드박스로 연산을 철저히 가둬야 합니다.

### validation checklist
- [ ] 최초 진입 시 LLM 추천 순서와 기본 타임라인 순서 시드가 각각 정상 맵핑 및 2D 노드로 시각화되는지 검증
- [ ] 수동 드래그 정렬 변경 후 시드 스위처 조작 시, 작업 유실 방지 경고 팝업이 유효하게 트리거되는지 안전성 검사
- [ ] '시나리오 재작성(Rewrite)' 호출 시 현재 캔버스의 카드 순서 메타데이터가 비동기 LLM 스레드로 누락 없이 피딩되는지 데이터 정합성 검증
- [ ] LLM 재작성 요약 결과가 수락될 때, 2D 노드 카드의 텍스트와 시나리오 요약문이 즉시 정상 연동/갱신되는지 렌더링 검사
- [ ] 수동 변경한 정렬 이력과 선택된 시드 메타데이터가 프로젝트 json 세이브에 포함되어 재로드 시 완벽 복원되는지 영속성 검증

### do-not-touch list
- [ ] OpenGL 가속 및 QML 3D 레이아웃 드로잉 모듈 차단
- [ ] 최종 자막 결정 모델 및 코어 STT/VAD 음성 백엔드

### verdict
- 시드 전환 시점의 수동 작업 유실 방지 가드(임시 백업/경고 팝업) 및 비동기 LLM 호출 구조가 반영된다면, 본 초기 시드 및 재작성 계획안은 안전하게 구현 가능(Ready to active)합니다.
```

Dex 반영 메모 - initial roughcut order seeds and user-order rewrite:

- Jammini의 2가지 초기 시드 제안은 detailed plan 25번의 `기본순서(에디터 편집 순서)` and `LLM 추천 순서` default practice notebook candidates에 반영한다.
- Jammini의 2D 캔버스 노드 전환 제안은 seed switching as roughcut canvas/notebook selection only, not editor/NLE commit, 조건에 반영한다.
- Jammini의 수동 정렬 기반 재작성 제안은 current user-edited order as the primary rewrite source and async rewrite alternatives에 반영한다.
- Jammini의 수동 작업 유실 위험은 warning / save-as-practice-note / automatic temporary backup notebook 조건에 반영한다.
- Jammini의 NLE/final subtitle guard는 LLM seed/rewrite sandboxing, commit-boundary-only editor projection, and no auto-commit to final rows/export에 반영한다.
- Jammini의 validation checklist는 initial seed visualization, seed-switch safety, rewrite input parity, LLM result rendering, and save/reopen persistence proof에 반영한다.
- Jammini의 do-not-touch list는 OpenGL/QML/3D 금지와 final subtitle/STT/VAD non-goals에 반영한다.

Test plan:

- Focused tests:
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_roughcut_ui_v2.py tests/test_roughcut_candidates.py`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_app_command_bridge.py -k "roughcut"`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_segment_reload.py -k "roughcut or open_project_file"`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_dual_write.py`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_lora_personalization_storage.py`
- QA/app-command proof:
  - `AI_SUBTITLE_STUDIO_QA_USE_SOURCE=1 ./venv/bin/python tools/qa_suite_runner.py major`
  - Confirm the roughcut scenarios `roughcut_reopen_macau`, `roughcut_interaction_macau`, `roughcut_candidate_macau`, and `roughcut_release_audit_macau`.
- Manual evidence:
  - Save screenshots showing the four-region scenario-composer layout and confirming that legacy roughcut UI elements are no longer visible.
  - Save proof for material-card drag/drop, scenario order playback, subtitle playback in scenario order, save/reopen, SRT/EDL/export parity, and scenario mode persistence.
  - Save proof that editor subtitle edits update roughcut cards, roughcut scenario/range edits update editor rows, and 1000+ subtitle node rendering remains responsive without QML/OpenGL/Metal surfaces.
  - Save a reference-review artifact that compares the implemented roughcut card layout against the selected reference families: NLE media browser, whiteboard/node graph, Kanban/database card, and storyboarding.
  - Save proof that selecting each middle-category segment updates the settings box with content, source/output time, duration, topic, tags, summary, review state, and dirty state.
  - Save proof that settings-box topic/tag/summary edits auto-commit or warn on selection change and survive save/reopen without making timecode fields editable.
  - Save proof that topic/tag extraction, roughcut-only metadata editing, editor projection, save/reopen, and LoRA feedback row logging preserve subtitle text/timing.
  - Save proof that multiple scenario practice notebooks can be created, switched, saved to the project file, reopened with the selected notebook/order restored, and shown as stale/review-required instead of crashing when referenced segments were deleted or merged in the editor.
  - Save proof that the scenario-window LLM summary is generated from the assembled scenario order, does not block playback/editor interaction, debounces repeated card movement, saves/reopens without a fresh API call, and marks itself stale when scenario/order/content metadata changes.
  - Save proof that middle-segment drag/drop merge and cut-edit-style split preserve subtitle order, avoid overlaps, support undo with frame-accurate restoration, update topic/tag/summary review state, persist through save/reopen, and mark dependent notebooks/summaries stale.
  - Save proof that intro/outro/highlight recommendation runs without GUI lag on long media, shows non-destructive candidate cards, supports preview/insert/append without overwriting the current scenario, persists accepted choices through save/reopen, and stale-marks candidates after subtitle/topic/split/merge/media changes.
  - Save proof that the shortform basket enforces the 60.0-second limit, preserves subtitle sync in the handoff payload, restores through save/reopen, marks stale inputs after source changes, and can be received by the shortform stub without mutating roughcut or final subtitle state.
  - Save proof for the AlphaCut-inspired local shortform workflow: roughcut handoff input, multiple shortform draft cards, 9:16 preview, caption/template/framing controls, non-destructive regenerate, save/reopen, and local export without cloud/account/social-upload dependencies.
  - Save proof that rearranging middle-segment cards updates the scenario storyline view, including ordered synopsis, act/beat board, logline cards, optional plotline lanes, stale marking, save/reopen persistence, and 2D-only rendering performance.
  - Save proof that the screenplay composer maps cards to sequence/scene/beat/dialogue-action hierarchy, script outline click focuses the matching 2D card and video range, cut purpose/shot role/director notes persist through save/reopen, table-read preview stays synced, missing-shot/gap placeholders are review-only, alternate takes are non-destructive, and shot-to-subtitle preflight blocks invalid NLE commits.
  - Save proof that scenario subtitle/video export preserves the original SRT and original media bytes, creates separate `_시나리오.srt` and `_시나리오.mp4` outputs, keeps scenario SRT timing aligned to the scenario MP4 timeline, blocks invalid/stale exports, and never silently overwrites an existing scenario export.
  - Save proof that editor `원본으로 돌리기` restores the original baseline after roughcut/editor mutations, creates a pre-restore safety snapshot, preserves derived `_시나리오` files, stale-marks dependent roughcut state, and keeps original SRT/media hashes unchanged.
  - Save proof that combined editor + roughcut snapshots capture and restore editor rows, NLE projection, roughcut notebooks, scenario order, material card order, split/merge lineage, metadata, storyline/screenplay/shortform state, export signatures, and UI selection state atomically across save/reopen.
  - Save proof that G4 UI/UX scenario traces cover roughcut open, card drag/drop, split/merge, metadata edit, storyline/screenplay/table-read, restore-to-original, snapshot create/restore, shortform handoff, and `_시나리오` exports with correlation ids, state hashes, elapsed times, result codes, and redacted error reasons.
  - Save proof that G4 logs/traces are App Store-safe: no raw subtitle text, no full media paths, no raw prompts/LLM responses, no hidden network upload, bounded retention, sandbox-safe debug bundle export, and current G0 App Store readiness checks still separate from source-app QA.
  - Save proof that new G4 source files are owned by `core/roughcut/` or `ui/roughcut/` roughcut packages, with any files outside those folders documented as thin adapters and covered by focused import/app-command tests.
  - Save proof that middle-segment compatibility scoring displays score/color/line indicators, settings-box manual relation overrides update the graph live, deterministic/LLM scores never override manual owner scores without confirmation, relation-based scenario rewrite suggestions create non-destructive notebook candidates, stale links update after split/merge/editor changes, and save/reopen restores relation metadata.
  - Save proof that first roughcut entry creates both `기본순서(에디터 편집 순서)` and `LLM 추천 순서`, switching seeds does not overwrite manual user order without warning/backup, user-edited order is fed into scenario rewrite, rewrite outputs are non-destructive alternatives, and save/reopen restores selected seed, user order, provenance, and stale flags.
  - Save proof that pressing the project `저장` button persists the original subtitle/editor state, roughcut scenario-composer state, and shortform editor state in one atomic project transaction, then project reopen restores all three workspaces with correct authority, stale flags, and without requiring new LLM/regeneration work.
  - Save proof for the expanded 12-step demo scenarios: editor-to-roughcut stale/sync, seed/split/merge warning and rollback, alternate-take/B-roll metadata-layer preview, shortform over-limit triage, separated `_시나리오` export, and restore-to-original stale marking.
  - Save proof that G4 follows the reference NLE structure: magnetic/snap gap prevention, role/lane metadata, reference-id notebook switching, proxy/cache preview, async background analysis, transaction journal rollback, and transcript-linked edits resolving into NLE operations.
  - Save responsiveness proof for at least 100 middle-segment cards and relation connectors: canvas pan/zoom, card drag, seed switch, notebook switch, settings selection, video preview, save, and close remain responsive without OpenGL/QML/3D/web-canvas dependencies.

Acceptance gates:

- Four visible regions exist with the owner-defined roles: `시나리오박스`, `재료박스`, `비디오박스`, and `설정박스`.
- Existing roughcut controls are removed from the visible box interiors, but existing functions, state wiring, app commands, save/reopen, and export helpers remain callable.
- Material cards support drag/drop, time-axis movement planning, vertical growth, wrapped subtitle text, and in-card preview without text overflow.
- Future scenario-composer order changes preserve the implemented `비디오박스` playback, matching subtitles, and playbar behavior.
- Scenario suggestions and details are visible only through `설정박스`.
- Final subtitle authority, STT1/STT2/VAD runtime tracks, final save/export authority, project subtitle schema, and render/export core remain unchanged.
- Original SRT files and original media files are preserved; scenario exports are separate derived artifacts and cannot overwrite or replace originals.
- Roughcut scenario subtitle export writes `_시나리오.srt`, while normal editor/final SRT export remains a separate surface.
- Roughcut scenario video export writes `_시나리오.mp4`, while original media remains unchanged and is never renamed or replaced.
- Scenario SRT timing is based on the assembled scenario output timeline and matches the scenario MP4, not the unedited source timeline when order/trims differ.
- Existing `_시나리오.srt` or `_시나리오.mp4` paths are never overwritten silently; explicit replace approval or safe numbered/timestamped output is required.
- Scenario export paths/signatures may be stored for restore/review, but scenario artifacts do not become final subtitle authority or source media authority.
- Editor `원본으로 돌리기` restores the original imported/opened subtitle baseline with explicit confirmation and pre-restore safety snapshot.
- Restore-to-original preserves original files and derived scenario outputs, while stale-marking roughcut notebooks, summaries, storyline, screenplay, shortform, and scenario export signatures that no longer match.
- Combined editor + roughcut snapshots are atomic, versioned, named, save/reopen-stable, and blocked from restore when media/SRT/project signatures or NLE preflight checks fail.
- Snapshot metadata never replaces the approved subtitle/NLE canonical load-owner policy, final subtitle authority, original SRT authority, or source media authority.
- Snapshot storage avoids embedding rendered media or large binary previews; use compact metadata, paths, hashes, and recomputable thumbnails/previews.
- G4 observability is local-first, redacted, bounded, sandbox-safe, and does not introduce hidden analytics, cloud telemetry, account sync, tracking, or social upload behavior.
- UI/UX scenario tracing records user-visible roughcut workflows with correlation ids across UI, command, NLE preflight, persistence, snapshot, playback, and export layers.
- Trace records use ids, hashes, status codes, elapsed times, and stale/review flags instead of raw subtitles, full media paths, raw prompts, full LLM responses, personal filenames, or rendered media frames.
- External LLM/provider calls that include user content are explicitly user-initiated, cancellable, privacy-reviewed, and blocked from App Store release until reflected in owner metadata/privacy answers where required.
- Any new SDK/dependency used for logging, tracing, AI, web rendering, crash reporting, or analytics is blocked until App Store/privacy manifest, required-reason API, sandbox, and third-party SDK signature requirements are reviewed.
- G4 trace proof is debugging evidence only; it does not replace G0 signed app/pkg, sandbox smoke, App Store Connect validation, owner metadata, or privacy-answer proof.
- New G4 roughcut source lives under roughcut-owned folders: non-UI logic under `core/roughcut/`, UI logic under `ui/roughcut/`, and cross-surface files outside those folders are limited to thin adapters.
- Roughcut business logic, scenario state rules, export naming, snapshot policy, and trace schema are not duplicated in `ui/editor`, `ui/timeline`, `ui/main`, `ui/settings`, or `core/project`.
- Any exception outside roughcut folders is documented with owner rationale, import-path proof, and focused tests before merge.
- Middle-segment compatibility graph shows relation score, color, line thickness/style, direction, and stale/review state without overlapping cards or making the canvas unreadable.
- Settings box supports manual relation input between cuts, including source/target, relation type, 0..100 score, bidirectional/asymmetric direction, reason/note, active state, and whether it affects scenario rewrite suggestions.
- Manual owner relation overrides have priority over deterministic and LLM scoring until explicitly changed or deleted by the owner.
- Relationship-based scenario rewrite creates non-destructive suggestions or practice notebook candidates only; it never auto-commits editor rows, final subtitle rows, scenario exports, or source media changes.
- Split, merge, trim, topic/tag edit, editor subtitle edit, restore-to-original, snapshot restore, and media/SRT signature changes stale-mark affected relation links before reuse.
- Relation graph state persists across project save/reopen with relation ids, source/target ids, type, score, directionality, origin, active/stale flags, source signature, and updated time.
- LLM compatibility scoring uses redacted/anonymized inputs under the App Store-safe tracing guard and cannot log raw subtitles, full prompts, full responses, or full media paths.
- First roughcut entry always provides two default selectable seeds: `기본순서(에디터 편집 순서)` and `LLM 추천 순서`.
- `기본순서(에디터 편집 순서)` remains available as the editor/NLE handoff baseline and cannot be overwritten by LLM recommendation output.
- `LLM 추천 순서` is a separate roughcut candidate with provenance/rationale/stale metadata and cannot auto-commit editor rows, final subtitle rows, exports, or accepted notebooks.
- User-edited scenario order is the primary input for scenario rewrite after manual card edits; rewrite must not silently use original media order or LLM order instead.
- Switching order seeds after manual edits requires warning, save-as-practice-note, or automatic temporary backup to prevent loss of user work.
- Scenario rewrite from user order creates non-destructive alternatives with compare/provenance against current order and requires explicit owner acceptance before changing active notebook state.
- Save/reopen restores both default seeds, selected seed, current user order, rewrite alternatives, order hashes, provenance labels, temporary backups, and stale/review flags.
- Pressing project `저장` persists all three workspace domains: original subtitle/editor state, roughcut scenario-composer state, and shortform editor state.
- Project save is atomic across those domains: it must not write a project where editor rows are current but roughcut or shortform state is stale from a previous transaction without clear stale/review markers.
- Project reopen restores editor, roughcut, and shortform state together, including selected roughcut notebook, user order, relation graph, storyline/screenplay metadata, shortform basket, selected shortform draft, caption/template/framing choices, and stale flags.
- Saving roughcut/shortform derived state cannot overwrite original subtitle-only baseline, original media, original SRT, final subtitle authority, or accepted editor rows without an explicit approved NLE commit.
- Editor-to-roughcut sync marks dependent roughcut and shortform derived state stale/review-required after editor subtitle/timing changes, rather than leaving stale card text, stale rewrite text, or stale caption sync visible as current.
- Seed switching after manual edits cannot overwrite user work without warning, save-as-practice-note, or automatic temporary backup.
- Split/merge/cut-edit failure paths roll back without changing editor rows, final subtitles, roughcut notebooks, shortform payloads, or export signatures.
- Alternate takes, B-roll, insert, and reaction layers are metadata/preview state until explicit NLE commit; VAD offset preview cannot rewrite original subtitle timing by itself.
- Shortform duration budget is visible before handoff, `>= 60.0` seconds is blocked, and user trim/remove actions can bring the basket back under the limit without corrupting roughcut notebooks.
- Original SRT/media, scenario `_시나리오` outputs, and restore-to-original baseline remain visibly separate in the workflow.
- G4 editing is represented as NLE state plus preview/cache state only; no feature may create an independent non-NLE roughcut authority that bypasses approved NLE commit and save/load guards.
- Magnetic-style gap/collision/sync prevention is active for card reorder, insert, delete, split, merge, trim, and scenario assembly.
- Segment role/lane metadata is visible and filterable without changing subtitle text/timing authority.
- Practice notebook and scenario candidate switching uses lightweight ids/references and must not duplicate media buffers or large subtitle payloads.
- Proxy/cache/thumbnail/waveform/subtitle-summary preview data is used for responsive card/video UI, while original media remains the source for final export.
- Optional background jobs for thumbnails, VAD density, compatibility score, intro/outro/highlight recommendations, LLM summaries, and shortform drafts are cancellable, deduplicated, resource-budgeted, and safe to resume after save/reopen.
- Transcript-linked or script-like editing proposals must resolve into NLE operations before they can affect editor rows, roughcut commits, scenario exports, or shortform drafts.
- Shortform caption/style/template controls cannot become a second subtitle text authority or a cloud/social-upload path in the first slice.
- Editor subtitle changes project into roughcut cards without stale card text, timing, or preview ranges.
- Roughcut scenario reorder, middle-segment reassembly, range trim/extension, and split project back into editor rows through NLE commit boundaries without invalid durations, non-monotonic rows, overlaps, or subtitle text drift.
- UML-style card rendering uses PyQt6 2D surfaces only and stays usable on large projects.
- Card layout implements the selected reference-inspired patterns: time-aware storyboard grid, optional node connectors, density modes, grid snapping, explicit order labels, and commit-only NLE changes.
- Settings box displays each middle-category segment's content, time range, duration/length, topic, tags, summary, review state, and dirty/NLE sync state.
- Settings-box time/duration fields are read-only; length changes only happen through approved roughcut cut-edit/NLE commit controls.
- Settings-box metadata edits cannot be lost on selection change, focus loss, save, or reopen.
- Middle-segment topic/tag drafts are extracted, editable only in the roughcut editor, visible in the main editor as projection, and stable across save/reopen.
- Accepted topic/tag edits create safe local LoRA/personalization feedback rows without mutating model weights or STT/VAD behavior.
- Multiple scenario practice notebooks can be saved, loaded, switched, and restored from the project file with selected notebook, card order, scenario order, connector/order labels, and settings-box selection intact.
- Practice notebook switching does not auto-confirm a scenario, overwrite final subtitle rows, or change export authority.
- Missing/deleted/merged segment references in saved notebooks are filtered or marked stale/review-required without project-open crashes.
- Scenario-window LLM summary uses the reassembled scenario order and roughcut metadata as input, not only the original timeline order.
- LLM summary generation is async/debounced or explicitly gated and does not block GUI interaction, playback, editor navigation, or card movement.
- Saved LLM summaries restore on project reopen and become stale/review-required when their scenario/order/input signature no longer matches.
- LLM summary output never mutates final subtitles, timing, export output, or scenario confirmation without an explicit owner-approved commit path.
- Middle-segment merge works through drag/drop preview plus explicit commit and preserves monotonic subtitle order, subtitle text, topic/tag traceability, and thumbnail/preview continuity.
- Middle-segment split works through cut-edit-style range/playhead selection and handles active subtitle boundary cases without subtitle loss or overlaps.
- Split/merge operations are undoable, atomic, persisted across project save/reopen, and update or stale-mark practice notebooks, settings-box selection, and LLM summary signatures.
- Failed split/merge operations roll back without changing editor rows, final subtitle authority, export output, or roughcut notebook state.
- Intro, outro, and highlight recommendations are shown as non-destructive candidate cards and never auto-overwrite the current scenario canvas or notebook.
- Recommendation scoring is deterministic-first and records score components/rationale for RMS, VAD density, keyword/topic/tag density, cut-boundary context, and safe duration windows where available.
- Recommendation analysis runs in the background and does not block playback, subtitle editing, card movement, or scenario navigation.
- Accepted recommendation inserts/appends persist through save/reopen, while stale source signatures mark candidates review-required instead of silently reusing invalid ranges.
- Shortform candidate basket total output duration is validated at handoff time and cannot exceed 60.0 seconds.
- Roughcut-to-shortform handoff uses a versioned payload/bridge and does not tightly couple roughcut UI internals to the PHASE3 shortform maker placeholder.
- Handoff payload preserves clip order, source/output ranges, subtitle references, topic/tags, thumbnail references, vertical framing metadata, total duration, source notebook/candidate id, and stale/review flags.
- Shortform handoff does not mutate final subtitles, roughcut scenario order, export output, or notebook state without an explicit later owner-approved import/accept path.
- Shortform maker implementation follows the AlphaCut-inspired high-level workflow while remaining local-first, non-destructive, and source-app owned.
- Shortform draft cards include title/hook, duration, caption preview, 9:16 framing, template/style choice, score/rationale, and stale/review state.
- Caption text authority remains the existing final subtitle/NLE projection; shortform caption controls only affect overlay/style/framing.
- Regenerate/refine never overwrites accepted clips, roughcut notebooks, final subtitle rows, or export output without explicit user confirmation.
- External URL import, cloud processing, account login, direct social upload, and billing flows are out of scope for the first shortform implementation slice.
- Scenario storyline view changes according to assembled middle-segment order and never uses original media order as the only storyline source.
- Storyline view supports ordered synopsis, act/beat board, storyboard/corkboard cards, loglines, and optional 2D plotline lanes.
- Storyline generation uses deterministic structure first and LLM only for logline/synopsis/label/rationale assistance; LLM output cannot reorder cards or mutate subtitle/timing state.
- Storyline layout is PyQt6 2D-only, remains responsive on large card counts, and falls back to simple ordered synopsis when connectors become too dense.
- Storyline state persists per practice notebook and restores on project reopen with stale/review marking after source changes.
- Roughcut screenplay composer treats assembled filmed cuts as script material and supports sequence, scene, beat, dialogue/action, cut purpose, shot role, continuity state, and director-note metadata without replacing subtitle/NLE row authority.
- Script outline click-to-focus keeps outline, 2D scenario canvas, selected card, and video preview range in sync.
- B-roll, insert, reaction, and alternate take layers are non-destructive roughcut metadata until an explicit NLE commit boundary is crossed.
- Missing-shot/gap placeholders are visible as review-required cards and cannot silently create subtitle rows, delete media ranges, or alter final exports.
- Table-read preview presents the assembled scenario as a script-like text view synced with playhead/video time, but remains display/review only and does not become a subtitle text editor.
- Shot-to-subtitle authority guard blocks screenplay assembly commits that would create invalid durations, overlaps, non-monotonic rows, missing source refs, subtitle text drift, or timeline conflicts.
- Screenplay hierarchy, cut purpose, shot roles, director notes, alternate take choices, gap placeholders, revision pointers, and table-read view state persist per practice notebook and restore with stale/review marking.

Rollback:

- If the new visible layout breaks roughcut selection, preview, save/reopen, export, or app-command automation, revert the visible layout composition before touching roughcut state or core roughcut generation.
- If hidden legacy controls still consume layout space or break the four-region layout, move them to a hidden zero-size legacy container before deleting or rewriting any function.
- If scenario generation contaminates final subtitle/save/export authority, disable scenario-composer generation wiring and keep the existing roughcut candidate/export path as the fallback.
- If NLE roughcut write-back produces drift, overlaps, or stale editor rows, disable roughcut -> editor write-back and keep editor/final subtitle rows as the authoritative surface.
- If reference-inspired freeform placement creates ambiguous order or connector clutter, fall back to the time-aware storyboard grid with explicit order labels before changing NLE state.
- If settings-box edits are lost on selection change or focus loss, disable inline metadata editing and require explicit apply/revert until dirty-state handling is fixed.
- If settings-box time/duration fields become directly editable or mutate subtitle boundaries outside the NLE commit path, revert those controls to read-only labels immediately.
- If topic/tag metadata sync corrupts subtitle text/timing or save/reopen compatibility, disable metadata write-back while retaining read-only roughcut extraction.
- If LoRA feedback logging records cancelled/corrupt/drifted rows or attempts to mutate model weights, disable the feedback sink and preserve existing personalization storage unchanged.
- If practice notebook persistence breaks project save/reopen or legacy file loading, disable notebook management and fall back to the existing selected roughcut candidate state path.
- If notebook switching mutates editor rows, final subtitle authority, or export output without explicit confirmation, disable notebook write-back and keep notebooks read-only until the NLE commit boundary is fixed.
- If orphan segment references cause restore crashes or invalid card state, filter those references and mark the notebook stale before allowing any editor write-back.
- If LLM summary generation blocks the GUI, floods the provider with duplicate requests, or causes playback/editor lag, disable automatic summary refresh and require an explicit manual update command.
- If summary persistence corrupts project save/reopen or legacy compatibility, stop saving generated summaries and keep them as disposable UI cache until the schema guard is fixed.
- If generated summary text starts driving subtitle/timing/export/scenario confirmation state, disconnect the summary output from write paths and keep it display-only.
- If split/merge creates overlaps, non-monotonic rows, subtitle loss, broken undo, or stale editor/roughcut divergence, disable split/merge commit and keep preview-only card interaction.
- If drag/drop merge commits accidentally on hover/drop without explicit confirmation, revert merge to preview-only until the commit boundary is fixed.
- If cut-edit split cannot safely resolve an active subtitle boundary, block the split with review-required status rather than interpolating or deleting subtitle text silently.
- If recommendation analysis causes GUI lag, high CPU pressure, memory leak, or playback/editor slowdown, disable automatic recommendation backfill and require manual analysis.
- If recommendation insertion overwrites or reorders existing scenario cards without explicit user approval, disable insert/append write paths and keep recommendations preview-only.
- If recommendation persistence corrupts project save/reopen or legacy compatibility, stop saving cached recommendation candidates and preserve only accepted scenario edits through the existing roughcut state path.
- If shortform handoff allows payloads over 60.0 seconds, disable handoff and keep the basket editable until duration validation is fixed.
- If the handoff bridge mutates roughcut/editor/final subtitle state or creates tight dependency on the PHASE3 shortform UI stub, disconnect the bridge and keep payload generation read-only.
- If shortform basket or payload persistence corrupts project save/reopen or legacy compatibility, stop persisting cached handoff payloads and preserve only roughcut-side scenario/notebook state.
- If AlphaCut-inspired shortform work drifts into cloud/account/social-upload behavior or copies external UI/content instead of using reference-level workflow patterns, stop that slice and return to local-first draft-card generation.
- If shortform regenerate overwrites accepted clips, roughcut notebooks, caption authority, or export output, disable regenerate and keep it preview-only until transaction boundaries are fixed.
- If 9:16 framing/caption/template controls degrade playback or create text overlap, disable the affected styling control and keep source clip selection/export proof intact.
- If storyline connector routing creates unreadable spaghetti UI or drops below the responsiveness target, disable plotline lanes and fall back to ordered synopsis plus act/beat board.
- If storyline generation mutates card order, subtitle text/timing, final subtitle authority, or export state, disconnect storyline output from write paths and keep it display-only.
- If storyline state persistence breaks project save/reopen or legacy compatibility, stop persisting generated layout metadata and recompute display-only storyline from the current notebook.
- If screenplay hierarchy or script outline rendering causes playback/editor lag, disable automatic outline/table-read refresh and regenerate them manually or asynchronously.
- If B-roll/insert/reaction/alternate take layers create ambiguous subtitle order, keep layers display-only and require explicit NLE commit preview before any editor projection.
- If missing-shot/gap detection produces false edits or tries to create/delete subtitle rows automatically, disable write paths and keep placeholders review-only.
- If director notes or revision history persistence corrupts project save/reopen or legacy compatibility, stop persisting those metadata fields and keep them as disposable roughcut UI state until schema guards are fixed.
- If shot-to-subtitle guard misses invalid durations, overlaps, non-monotonic rows, source-ref loss, or text drift, disable roughcut screenplay commit and keep editor/final subtitle rows authoritative.
- If scenario export overwrites or mutates the original SRT/original media path, disable scenario export immediately and restore the prior normal editor/final export path unchanged.
- If `_시나리오.srt` and `_시나리오.mp4` timing/parity fails, disable scenario MP4 export and keep scenario SRT generation blocked or review-only until duration alignment is proven.
- If scenario export collision handling silently replaces an existing `_시나리오` file, require explicit save-as/replace UI before any further scenario export is allowed.
- If scenario export metadata starts acting as source-media authority or final-subtitle authority, stop persisting export paths/signatures and treat scenario outputs as disposable derived files only.
- If restore-to-original can run without confirmation, without a pre-restore safety snapshot, or while original baseline identity is ambiguous, disable the command until the baseline and confirmation gates are fixed.
- If restore-to-original deletes notebooks, derived `_시나리오` exports, topic/tag feedback, director notes, or LoRA feedback rows instead of stale-marking/disconnecting them, disable restore and keep manual project reopen as fallback.
- If combined snapshot restore applies editor state but not roughcut state, or roughcut state but not editor state, disable snapshot restore and keep snapshots read-only until atomic restore is proven.
- If snapshot persistence corrupts project save/reopen, causes unbounded project growth, or bypasses approved NLE load-owner guards, stop persisting snapshot payloads and retain only lightweight snapshot metadata until schema guards are fixed.
- If logs/traces expose raw subtitle text, full media paths, raw prompts, full LLM responses, personal filenames, or rendered media frames by default, disable the offending trace category and keep only redacted ids/hashes until privacy review passes.
- If tracing introduces hidden network upload, analytics, tracking, account sync, cloud logging, or an unreviewed third-party SDK, remove that path before any App Store candidate build.
- If trace retention grows without bounds or bloats project/app-container storage, disable verbose tracing and keep only size-capped rotating logs plus explicit local diagnostic export.
- If UI/UX trace spans cannot correlate UI action to NLE preflight/persistence/export result, do not claim the G4 workflow is debuggable; keep the feature behind a trace-completeness blocker.
- If App Store/privacy checks find G4 logs, LLM calls, SDKs, entitlements, or metadata wording incompatible with submission, keep G4 work source-app/local-only and do not include it in the App Store candidate until corrected.
- If a G4 implementation scatters roughcut logic into editor/timeline/main/settings/project modules, stop the slice and move the logic behind `core/roughcut/` or `ui/roughcut/` APIs before adding more behavior.
- If folder cleanup risks broad import churn or regressions, keep existing files in place as adapters and defer mechanical migration until a separate owner-approved cleanup slice with focused tests.
- If a new roughcut subpackage creates circular imports between `core/roughcut/` and `ui/roughcut/`, move shared DTOs/state schemas into core and keep UI imports one-way.
- If compatibility connectors create visual clutter, overlap, or slow canvas interaction, disable connector rendering first and fall back to compact score badges/filtering.
- If deterministic or LLM scoring overrides manual owner-authored relation scores without explicit confirmation, disable automatic score write-back and keep suggestions read-only.
- If relationship rewrite suggestions mutate editor rows, final subtitles, scenario exports, source media, or accepted notebooks automatically, disable rewrite apply and keep relation graph display-only.
- If stale relation links survive split/merge/editor/restore/snapshot changes as current recommendations, block relation-based rewrite until stale detection and recomputation are fixed.
- If LLM compatibility scoring leaks raw subtitles, full paths, prompts, responses, or user content into logs/traces/provider calls outside the privacy guard, disable LLM scoring and keep deterministic/manual scoring only.
- If first roughcut entry cannot produce both baseline editor order and LLM recommended order, disable LLM seed selection and keep `기본순서(에디터 편집 순서)` as the only safe initial seed.
- If seed switching overwrites manual user order, card layout, notes, relation links, or rewrite text without warning/backup, disable seed switching until temporary backup or save-as-practice-note is proven.
- If scenario rewrite uses original media order or LLM order instead of the current user-edited order, mark the rewrite output invalid and keep the previous scenario state unchanged.
- If LLM seed/rewrite output commits editor rows, final subtitles, scenario exports, `_시나리오` files, or accepted notebooks automatically, disconnect rewrite output from write paths and keep it display-only.
- If project `저장` cannot persist original subtitle/editor state, roughcut state, and shortform editor state together, block the new multi-domain save path and keep the previous stable editor-only or editor+roughcut save contract until atomic persistence is proven.
- If save/reopen restores one domain but drops or corrupts another domain, mark the project save invalid, preserve the last known good project where possible, and disable roughcut/shortform persistence until compatibility guards pass.
- If roughcut or shortform persistence overwrites the original subtitle baseline, original SRT/media identity, final subtitle authority, or accepted editor rows without an approved NLE commit, disconnect derived-state persistence from editor write paths immediately.
- If three-domain save traces expose raw subtitles, full paths, prompts, LLM responses, rendered frames, or personal filenames, disable detailed save tracing and keep only redacted ids/hashes/status codes.
- If editor-to-roughcut sync leaves dependent rewrite/shortform/relation state looking current after editor changes, disable derived-state reuse and require explicit refresh.
- If alternate-take or B-roll preview mutates original subtitle timing, final rows, or source media before explicit NLE commit, disable layer write-back and keep it preview-only.
- If shortform duration math lets `>= 60.0` seconds pass or blocks a valid under-limit basket, disable handoff and keep the basket editable until duration calculation is corrected.
- If any G4 feature stores or mutates a non-NLE roughcut authority that can bypass NLE commit, save/reopen, restore, or final subtitle guards, block that feature and route it through NLE state DTOs first.
- If card/canvas responsiveness depends on synchronous media decode, LLM calls, VAD analysis, or full connector repaint, disable that expensive path and fall back to cached/proxy/viewport-clipped rendering.
- If proxy/cache generation blocks save, close, editor navigation, playback, or active subtitle conversion, make the cache job optional/resumable and keep project state saveable without it.
- If transcript-linked editing directly mutates media/subtitle rows without NLE preflight, disable transcript apply and keep it as suggestion-only.
- If shortform caption/templates introduce cloud/account/social upload behavior or a second caption authority, keep the shortform slice local-preview-only until separately approved.

## Parked Candidates

No parked candidates are currently open. Any new candidate must create a fresh
quality gate and rollback branch before execution.

## Metadata

```yaml
app_version: "04.01.32"
document_version: "04.01.32-source-app"
phase: "SOURCE_APP_CONTINUATION_V4_1_0"
queue_source_of_truth: "docs/planning_queue/ACTION_ITEMS.md"
commit_policy: "Commit only when the user explicitly asks."
product_priority: "Accuracy before speed; optimize generation time only with behavior-preserving changes."
root_development_docs_policy: "AGENTS.md only; all other development docs live under docs/."
```
