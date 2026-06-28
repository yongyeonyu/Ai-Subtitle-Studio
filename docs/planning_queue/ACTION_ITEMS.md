<!--
Document-Version: 04.01.06-source-app
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

Status: active blocker-closure group. Owner approval for App Store packaging/signing/upload/metadata execution was granted on 2026-06-28; final App Store `.pkg`, validation, upload, and submission remain blocked until the required Apple Distribution/Installer identities and owner metadata values are available.

Current baseline:

- App version: `04.01.06`.
- Submission target: Mac App Store signed `.pkg` built from a sandboxed signed `.app`.
- Packaging scripts: `packaging/macos/build_app_bundle.sh`, `packaging/macos/sign_app_bundle.sh`, `packaging/macos/validate_app_bundle.sh`, `packaging/macos/build_app_store_pkg.sh`, `packaging/macos/upload_app_store_build.sh`.
- Entitlements: `packaging/macos/AI Subtitle Studio.entitlements`.
- Current readiness doc: `docs/APP_STORE_SUBMISSION_READINESS.md`.
- Latest audit artifact: `output/manual_verification/latest/app_store_v040101_identity_check_20260629_0036/app_store_readiness_audit.md`.
- Latest packaging evidence: `output/manual_verification/latest/app_store_owner_approval_packaging_20260628_2220/`.
- Current audit state: `local_packaging_ready=true`, `app_store_submission_ready=false`, blocker count `13`; local Apple Development `.app` signing smoke passed, but the keychain currently exposes only Apple Development signing, so App Store Distribution `.app`, signed `.pkg`, sandbox workflow smoke, App Store Connect validation, and owner metadata remain incomplete.
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
   - Submit only after owner approval.

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

Status: active owner-review gate. Archive pointer: `docs/planning_queue/COMPLETED_ACTION_ITEMS.md#stt2--word-precision-generation-latency-profiling-and-accuracy-preserving-trim`.

Current baseline:

- Representative HeyDealer first-180s STT1 plus STT2/word collect-cache write/hit backfill is strict-accepted.
- `stt_recheck_collect_cache_enabled=false` and `stt_primary_collect_cache_enabled=false` remain production defaults until explicit owner approval.
- Latest strict real-media collect-cache backfill refresh: `output/manual_verification/latest/stt_cache_backfill_real_nas_20260628_2202/`; preflight passed, write/hit accepted, elapsed `177.888s -> 1.183s`, raw/final/reference `58/56/89`, quality/text/timing `93.766/94.267/0.5808s`, final invalid/non-monotonic/overlap `0/0/0`, final last end/duration bound `180.0/180.0`, global max active `1`, STT1/STT2/word provider calls `true -> false`, and timeout audit reported `timeout_detected=false`.
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

Status: active approved-persistence guard. Owner approval for persisted NLE/UI structure was granted on 2026-06-28; approved `nle_snapshot` compatibility metadata and top-level `nle` shadow metadata persistence are now available behind explicit `nle_persistence` flags plus `owner_approved_20260628`, while persisted `_nle_project_state`, canonical load ownership, and per-pixel drag writes remain gated. Close/deferred-save vector-time boundary blocker is completed and archived in `docs/planning_queue/COMPLETED_ACTION_ITEMS.md#v040102-nle-close--deferred-save-boundary-fix`.

Current baseline:

- Native migration is not an active direction for this repository.
- The current Python/PyQt6 source app remains the working product line.
- Bounded runtime/session NLE mutation ownership is adopted for covered release-commit paths.
- Approved `nle_snapshot` persistence metadata can be written as compatibility metadata for explicitly marked projects.
- Approved top-level `nle` shadow metadata can be written for explicitly marked projects, but `canonical_load_owner` remains `legacy_editor_state`.
- Persisted `_nle_project_state`, making `nle` or `nle_snapshot` the canonical load owner, and full NLE disk-format cutover remain gated.
- Legacy save/reopen compatibility remains mandatory.
- Latest top-level NLE shadow metadata proof: `output/manual_verification/latest/nle_top_level_shadow_metadata_20260629_0020/nle_persistence_cutover_audit.md`; `prep_ready=true`, `top_level_nle_shadow_ready=true`, storage has approved top-level `nle` plus `nle_snapshot`, `canonical_load_owner=legacy_editor_state`, legacy rows and read-back parity are stable, runtime report/runtime state/quarantine do not persist, operation roundtrip all passed across `11` families, render/export parity passed, and full cutover remains `persistence_cutover_ready=false`.
- Completed close/deferred-save blocker proof: `output/manual_verification/latest/nle_close_deferred_save_v040102_20260629/close_deferred_save_report.md`; raw vector `time.start_frame/end_frame` rows no longer collapse into `nle_save_export_invalid_duration`, close-triggered deferred-save failures no longer reschedule stale retry loops, and true final overlaps still raise `nle_save_export_final_overlap`.

Detailed plan:

1. Keep `docs/nle_engine/NLE_Action.md` as the NLE plan and status file.
2. Keep completed NLE slices out of this active queue; use archive pointers and validation evidence instead.
3. Require fresh compatibility proof before widening beyond approved `nle_snapshot` and top-level `nle` shadow metadata.
4. Require final-overlap, global-canvas, save/reopen, render/export, and Taption rule parity proof for any new editing-owner cutover.
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

Status: active planning item. This is a runtime/session visualization and scheduling plan only; it does not approve persisted NLE disk-format cutover, STT2 skipping, model downsizing, quality-gate loosening, UI/UX redesign, or production default cache promotion.

Current baseline:

- First runtime owner-map/read-only projection slice is complete and archived in `docs/planning_queue/COMPLETED_ACTION_ITEMS.md#v040103-g3-runtime-nle-lane-owner-map--final-authority-guard`.
- Compact live status/feed wiring slice is complete and archived in `docs/planning_queue/COMPLETED_ACTION_ITEMS.md#v040104-g3-compact-live-status-feed`.
- Scheduler-budget telemetry slice is complete and archived in `docs/planning_queue/COMPLETED_ACTION_ITEMS.md#v040105-g3-live-nle-projection-scheduler-budget-telemetry`.
- Live runtime observability proof harness slice is complete and archived in `docs/planning_queue/COMPLETED_ACTION_ITEMS.md#v040106-g3-live-runtime-observability-proof-harness`.
- Existing runtime surfaces already preserve live STT preview rows through `_live_stt_preview_segments`, `stt_preview_source=STT1/STT2`, and global-canvas STT lane tests.
- `core/engine/subtitle_live_editor_feed.py` now exposes runtime-only `VAD`, `STT1`, `STT2`, `subtitle_preview`, and `final` track metadata. Only `final` carries save/export authority; VAD/STT/subtitle-preview tracks are reference-only.
- `status`, `ping`, and `guided-subtitle-status` now expose compact `nle_runtime_track_counts` / `nle_runtime_tracks` metadata without raw STT/VAD/subtitle-preview row text or large segment payloads, and UDP compaction preserves the count summary.
- `core/project/nle_runtime_cutover.py` rejects `_nle_runtime_role=runtime_reference_only`, non-final `_nle_runtime_track`, and `_nle_save_export_authority=false` rows from final overlay, global canvas, and save/export projection even if those rows carry text.
- Existing project state can store STT candidate tracks and VAD/voice activity as separate diagnostic/reference rows, while final subtitle rows remain the save/export authority.
- Existing Apple Silicon worker planning lives under `core/runtime/multi_process.py` and `core/runtime/subtitle_resource_manager.py`, with `RuntimeResourceCoordinator`, `apply_apple_m_subtitle_pipeline_plan(...)`, active runtime labels, memory pressure snapshots, and benchmark-locked cut-boundary worker counts.
- `RuntimeResourceCoordinator` now reports `live_nle_projection_budget` telemetry: live projection uses existing row snapshots, dedicated projection workers `0`, subtitle worker-pool sharing `false`, coalesced updates, stale preview-frame drops, interactive reserve cores, foreground save/export/close labels, and critical/exit projection disablement. This is telemetry only; it does not change worker fan-out.
- `tools/remote_verify.py live-nle-proof` can now collect a compact `guided-subtitle-status` time-series and optional existing-window snapshots, then write `live_nle_runtime_proof.md/json` plus `status_samples.json` for G3 runtime observability review. The harness rejects missing pre-final `VAD`/`STT1`/`STT2` counts, raw runtime payload leakage, final-authority drift, and live projection budget drift on active samples.
- Prior lessons prohibit treating full-parallel STT, forced smaller STT windows, or speed-only native adoption as safe defaults without quality parity and real-media proof.

Detailed plan:

1. Runtime track ownership map
   - Completed for the read-only feed/authority contract. Continue from the next slice only if it widens live status/feed wiring without changing final authority.

2. Live projection and status feed
   - Completed for compact automation/status feed counts. Continue from the next slice only if it adds visual/runtime proof without raw payload leakage or final-authority changes.

3. Resource-balanced parallel scheduling
   - Completed the read-only live projection budget telemetry slice: reserve at least one interactive core where applicable, expose foreground save/export/close and pressure labels, keep projection worker count at `0`, and prove the live display/status path does not take subtitle worker-pool threads.
   - Continue from the next slice only with a real-media `live-nle-proof` run plus visual/runtime artifact review or a separately measured worker enforcement change; keep STT1 on the current high-quality native path and run STT2/word precision only within selective, quality-preserving budgets.
   - On Apple Silicon, describe accelerator use as ANE/GPU/CPU in docs and logs where user-visible. Do not make PyTorch MPS a production default.
   - Avoid full-core aggressive scheduling as a default. Let worker counts ramp only when memory pressure is normal and active runtime labels show no competing foreground save/export/close action.
   - Prevent the live NLE display path from taking threads away from the actual subtitle conversion path. Projection and painting should coalesce updates, reuse existing row snapshots, and drop stale preview frames rather than blocking STT workers.

4. Performance and quality proof
   - Measure baseline and candidate on the same representative media with non-profile elapsed truth, stage spans, memory pressure, active worker counts, and UI/app-command responsiveness.
   - Required proof includes raw/final/reference counts, quality/text/timing, final invalid/non-monotonic/overlap `0/0/0`, save/reopen stability, global canvas `max_active_segments=1`, and no increase in total subtitle conversion time beyond measurement noise.
   - Record before/after artifacts under `output/manual_verification/latest/`, including timeline/global-canvas evidence that STT1/STT2/VAD appear progressively during generation.

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

## Parked Candidates

No parked candidates are currently open. Any new candidate must create a fresh
quality gate and rollback branch before execution.

## Metadata

```yaml
app_version: "04.01.06"
document_version: "04.01.06-source-app"
phase: "SOURCE_APP_CONTINUATION_V4_1_0"
queue_source_of_truth: "docs/planning_queue/ACTION_ITEMS.md"
commit_policy: "Commit only when the user explicitly asks."
product_priority: "Accuracy before speed; optimize generation time only with behavior-preserving changes."
root_development_docs_policy: "AGENTS.md only; all other development docs live under docs/."
```
