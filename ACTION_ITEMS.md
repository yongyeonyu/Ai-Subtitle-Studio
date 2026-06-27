<!--
Document-Version: 04.00.18-source-app
Phase: SOURCE_APP_CONTINUATION_V4_0_18
Last-Updated: 2026-06-28
Updated-By: Codex
Purpose: Consolidated active execution queue for the current source-app line.
-->
# ACTION_ITEMS.md - Active Execution Queue

This file is now the single source of truth for active performance ideas,
action items, execution order, QA gates, and rollback rules. Completed action
item history is archived only in `COMPLETED_ACTION_ITEMS.md`; do not duplicate
completed-item summaries back into this active queue.

Former sources merged into this file:

- `idea_item.md`
- `NATIVE_LIB_PLAN.md`

Those standalone files were intentionally removed after consolidation.

## Hard Rules

- 자막 품질이 속도보다 우선이다.
- UI/UX는 명시 요청 없이 변경하지 않는다.
- 모델 축소, STT2 생략, LLM 생략, 품질 게이트 완화는 기본 최적화 후보가 아니다.
- Apple Silicon에서는 Apple Neural Engine, 즉 `ANE` 기준으로 표현한다. Core ML이 ANE/GPU/CPU 배치를 결정하고, Metal/MLX/whisper.cpp는 주로 GPU/CPU 경로로 검증한다.
- PyTorch MPS는 과거 `metal gpu stream` crash 근거가 있으므로 production default가 아니라 격리 실험 후보로만 둔다.
- owner 명시 재지시가 있기 전까지 native migration, Swift 재작성, 별도 네이티브 앱 전환은 active queue에 올리지 않는다.
- 자막 에디터 상호작용 표면은 2D-only이다. 자막 본문 편집, 자막 세그먼트 편집/생성/삭제, 플레이헤드 이동, 컷 경계, 다이아몬드, waveform/minimap 렌더링에 3D view, QML SceneGraph, OpenGL/Metal-backed UI surface를 새 default로 도입하지 않는다.
- 전체 앱 shell, 메뉴, 팝업, 다이얼로그의 기본값은 계속 `Qt Widgets` source app으로 유지한다. QML은 새 UI default에서 제외한다.
- 아이디어 발굴 또는 실행 전 `waste_action_item.md`와 `lesson_n_learned.md`를 먼저 읽고, 폐기된 아이디어를 새 근거 없이 반복하지 않는다.
- 실패/무효 후보는 `waste_action_item.md`에 hypothesis, change, metrics, quality, artifact, rejection reason을 남긴다.
- 반복하면 안 되는 진단/실험/운영 실수는 `lesson_n_learned.md`에 남긴다.
- owner 파일, 검증 절차, 구조 경계, 다음 세션 인수인계에 영향을 주는 변경은 같은 작업 안에서 관련 `docs/*.md`와 `docs/HANDOFF.md`까지 함께 갱신한다.
- 정상 완료된 idea/action item은 이 파일에서 삭제하고 `COMPLETED_ACTION_ITEMS.md`로 분리한다. `ACTION_ITEMS.md`에는 남은 작업, 현재 기준, acceptance gate, rollback만 둔다.
- 완료 이력은 active queue 번호가 아니라 완료 항목 제목/앵커로 참조한다. 큐 순서가 바뀌어도 `COMPLETED_ACTION_ITEMS.md`의 archive source가 stale 번호를 가리키지 않게 유지한다.
- 상세 검증 증거는 필요할 때 `test_result.md`, release note, `output/manual_verification/latest/`, `waste_action_item.md`, 또는 `lesson_n_learned.md`에 남긴다.

## Active Execution Queue

### 1. NLE Timeline Canvas State Ownership: Commit-Boundary Mutable Sync

Goal: Continue the owner-directed NLE transition by moving the main timeline canvas from legacy-only display rows toward NLE-owned state while preserving Taption-derived segment editing behavior.

Status: active. Archive pointer: `COMPLETED_ACTION_ITEMS.md#source-app-nle-runtime-adoption-and-migration-status`. The open requirement is to audit and cover any remaining safe release/commit sources not already owned by NLE dual-write; do not write NLE state on every drag pixel, and prove Taption magnet/gap/reorder behavior plus final subtitle no-overlap rules again after each slice.

Current baseline:

- `TimelineCanvas.update_segments(...)` now normalizes incoming rows through `nle_timeline_canvas_segments_from_editor_rows(...)`.
- Final caption rows are NLE-projected on the `timeline_canvas` surface.
- STT1/STT2/live subtitle preview rows remain visible on the main timeline canvas as editor/diagnostic lanes.
- Explicit silence gap rows remain gap rows and are still rebuilt by the existing canvas gap logic.
- Global canvas, final overlay, save/export, and roughcut render-plan projection keep their separate NLE routes.
- Completed NLE release-sync/evidence details, including shortcut start/end-to-playhead coverage, live only in the archive pointer above; do not duplicate completed slice summaries in this active queue.
- No named uncovered release/commit candidate is currently promoted. Next step is a fresh audit for remaining safe release/commit sources that can move to NLE dual-write without per-pixel writes or Taption UX drift.

Scope:

- `core/project/nle_runtime_cutover.py`
- `core/project/nle_dual_write.py`
- `ui/timeline/timeline_canvas.py`
- `ui/timeline/segment_store.py`
- `ui/editor/editor_segments_timeline_context.py`
- `ui/editor/ux/timeline_canvas_editing.py`
- `ui/editor/ux/timeline_subtitle_segment_editing.py`
- `tests/test_timeline_render_cache.py`
- `tests/test_timeline_playhead_fit.py`
- `tests/test_timeline_hit_targets.py`
- `tests/test_project_nle_runtime_cutover.py`

Execution order:

1. Keep the current read/projection cutover as the baseline; do not remove Taption/source-app fallback paths.
2. Continue commit/release-boundary sync only after identifying the next exact source that is not already covered by NLE dual-write: remaining drag-finished paths or other safe release/commit sources that need a richer NLE operation model.
3. Preserve STT candidate lane visibility in the main timeline canvas; do not mix those rows into final overlay/global canvas/save/export final surfaces.
4. Re-run Taption-derived gap/magnet/reorder focused tests and NLE projection tests after each mutable-sync slice.
5. Run source-app quick QA before marking a slice complete.

Acceptance gates:

- No visible UI/UX layout, label, color, shortcut, menu, or popup change unless the owner explicitly asks.
- No per-pixel NLE mutable writes during drag/scrub/skimming.
- Main timeline canvas may show STT preview/candidate lanes, but final caption rows must not be drawn as overlapping final captions.
- Global canvas, video overlay, save/export, and rendered final SRT remain final-only where already cut over.
- Taption rules remain intact: gap snap suppression, subtitle-boundary priority beyond silence gaps, magnet-off gap suppression, one-gap attach behavior, immediate neighbor reorder only after full crossing, and final overlap rejection.
- Save/reopen operation identity stays preserved for all current NLE dual-write operation families.
- Persisted top-level `nle`, `nle_snapshot`, or `_nle_project_state` fields remain blocked until a separate owner-approved compatibility gate exists.

Rollback:

- Revert the timeline-canvas mutable-sync slice first; keep the already-proven final-overlay/global/save-export NLE projection routes intact unless they are the direct regression source.
- If drag latency, hit targets, or Taption magnet behavior regresses, fall back to read/projection-only timeline canvas rows and keep mutable sync disabled.

### 2. STT2 / Word Precision Generation Latency Profiling And Accuracy-Preserving Trim

Goal: The latest cut-boundary profile did not confirm cut-boundary work as the generation bottleneck. Continue the owner's generation-speed concern by measuring the real wall-clock cost of STT2 rescue, selective word timestamps, and downstream quality cleanup before proposing any behavior-preserving trim.

Status: active. Archive pointer: `COMPLETED_ACTION_ITEMS.md#stt2--word-precision-generation-latency-profiling-and-accuracy-preserving-trim`. The open requirement is to keep `stt_recheck_collect_cache_enabled=false` and `stt_primary_collect_cache_enabled=false` by default, then run representative HeyDealer first-180s backfill for STT1 plus STT2/word collect caches when NAS is available again. If NAS remains off, stay in analysis/measurement-only work such as scheduling or memory-pressure variance.

Owner signal and current pointers:

- 2026-06-27: "지금 자막 생성이 너무 늦어지는데..."
- Latest strict generated-video pass: `output/manual_verification/latest/generated_video_tail_collapse_fix_20260628/tail_collapse_fix_report.md`
- Latest NAS-off stage/memory variance review: `output/manual_verification/latest/stt_latency_stage_variance_20260628/stage_variance_summary.md`; Jammini/서린 verdict is `HOLD` for algorithm/default changes while NAS remains unavailable.
- Latest owner-required NAS HeyDealer accepted real-media proof, for use when NAS returns: `output/manual_verification/latest/heydealer_nas_reference_180s_20260627_2215/reference_benchmark_report.md`
- Latest X5 short-loop reference smoke: `output/manual_verification/latest/x5_local_reference_fixture_20260627/reference_benchmark_report.md`; short-loop evidence cannot approve broad latency trims.
- Latest X5 project-reference 180s evidence: `output/manual_verification/latest/x5_project_reference_180s_20260627/reference_benchmark_report.md`; media/SRT semantic mismatch must still be rejected by scored acceptance.

Scope:

- `core/audio/`
- `core/engine/`
- `core/stt_mode/`
- `core/subtitle_quality/`
- `tools/verify_full_media_pipeline.py`
- `tools/benchmark_subtitle_pipeline_variants.py`
- `.codex_work/benchmarks/subtitle_pipeline_variants/`
- `output/manual_verification/latest/`

Execution order:

1. Keep the separated profiling method: non-profile repeat elapsed for speed truth, cProfile only for ownership diagnosis, reference benchmark for quality/timing truth.
2. Keep both `stt_recheck_collect_cache_enabled=false` and `stt_primary_collect_cache_enabled=false` by default. When NAS is available again, run a representative HeyDealer first-180s backfill for STT1 plus STT2/word collect caches before using cache speed deltas as production evidence. If NAS remains off, stay in analysis/measurement-only work such as scheduling or memory-pressure variance; do not skip STT1/STT2, downgrade models, shrink windows, remove word precision coverage, or loosen final stability gates.

Acceptance gates:

- Do not skip STT2, disable word precision, lower LLM/LoRA/VAD quality policy, shrink STT windows, promote Fast mode defaults, or loosen final subtitle stability gates.
- Do not use `stt2_selective_recheck.applied_count=1` as a trim signal by itself; first inspect `applied_segment_count`, `range_audio_sec`, `prepared_audio_sec`, and same-fixture reference quality.
- Do not remove word precision ranges from review flags without checking `selected_range_count`, `precision_review_range_count`, `needs_review_range_count`, `red_range_count`, `yellow_range_count`, `risk_range_count`, and `missing_word_range_count` on the accepted NAS fixture.
- Do not treat profiler elapsed as performance truth; use non-profile repeat elapsed for speed comparisons and profiler output only for ownership diagnosis.
- If final subtitle timing, counts, or segmentation change, run a reference-scored real fixture and keep `invalid_duration_count=0`, `non_monotonic_count=0`, `overlap_count=0`, and `stable_for_save_reopen=true`.
- Owner-level next-test gate is NAS HeyDealer first 180 seconds. The latest accepted fixture proof is `output/manual_verification/latest/heydealer_nas_reference_180s_20260627_2215/reference_benchmark_report.md`; if the NAS media or matching SRT becomes missing again, report blocked and do not substitute X5 or fallback cached audio to approve or tune latency changes.
- Do not batch High context-boundary LLM pair decisions unless a stricter parity guard first proves batch output is decision-equivalent to the per-pair path on the same rows.
- Do not skip or short-circuit High context-boundary checks only because a non-reference run reports `changed_pair_count=0`; first prove reference quality/text/timing/segmentation parity.
- Treat High context keep-cache as accepted for the owner-approved generated fixture only: second run must show cache hits and scored acceptance. For representative real footage, run a NAS or other owner-provided backfill before using the speed delta as production-wide proof.
- Treat macro proofread response cache as accepted for the owner-approved generated fixture only: replay must show cache hit/provider-call `1/0`, candidate-lock/verifier still active, and scored acceptance. For representative real footage, run a NAS or other owner-provided backfill before using the speed delta as production-wide proof.
- Treat STT2/word collect cache as accepted for the owner-approved generated fixture only: replay must show collect cache hit/provider-call `true/false`, annotation and final gates still active, and scored acceptance. Keep the default disabled until representative real footage is accepted.
- Treat STT1 primary collect cache as accepted for the owner-approved generated fixture only: replay must show collect cache hit/provider-call `true/false`, STT2/word/postprocess/final gates still active, and scored acceptance. Keep the default disabled until representative real footage is accepted.
- Treat combined collect-cache proof as accepted for the owner-approved generated fixture only: replay must show STT1/STT2/word collect cache hit/provider-call `true/false`, macro provider-call group `0`, final SRT overlap `0`, and scored acceptance. Keep defaults disabled until representative real footage is accepted.
- Treat macro warmup-skip as accepted for the owner-approved generated fixture only: every macro LLM group must be response-cache hit before LLM preparation is skipped; any miss/uncertainty must preserve the old provider preparation path. Keep using reference acceptance and final/SRT overlap gates before claiming speed.
- A media/SRT pair is not reference-fit just because `verify_reference_fixture_availability.py` passes; `evaluate_reference_benchmark_acceptance.py` must accept the scored run before it is used for trim decisions.
- Do not revive rejected shortcuts from `waste_action_item.md`: cleanup removal, Fast mode default promotion, STT window shrinking, or speed-only native adoption.
- If an experiment is slower, lower quality, or only wins on a short fixture while risking X5, add it to `waste_action_item.md` with metrics and rejection reason.

Rollback:

- Revert scheduling/cache/deferment changes before touching subtitle-generation algorithms or quality thresholds.
- Keep old STT/word precision behavior as the default until a measured pass proves the new path.

### 3. Mac App Store Submission Readiness

Goal: Track the work required to move the current macOS source app from development/QA state to a Mac App Store submission candidate.

Status: active planning item. Archive pointer: `COMPLETED_ACTION_ITEMS.md#mac-app-store-submission-readiness`. Do not execute packaging/signing/upload/notarization/DMG steps until the owner explicitly asks.

Current baseline:

- Packaging scripts exist under `packaging/macos/`.
- `packaging/macos/AI Subtitle Studio.entitlements` enables App Sandbox, user-selected read/write, app-scope bookmarks, network client, and audio input entitlements.
- Readiness audit evidence: `output/manual_verification/latest/app_store_readiness_audit_20260627/app_store_readiness_audit.md`
- Submission target lock evidence: `output/manual_verification/latest/app_store_readiness_target_lock_20260628/app_store_readiness_audit.md`
- Non-code submission draft: `docs/APP_STORE_SUBMISSION_READINESS.md`
- Current target decision: Mac App Store `.pkg` is the primary submission target; Developer ID beta `.dmg` is a separate opt-in track and is not App Store submission proof.
- Current audit result: `local_packaging_ready=true`, `app_store_submission_ready=false`; the latest target-lock audit reports blocker count `14`.
- There is no current checked App Store `.app` / `.pkg` artifact in `dist/macos/`.
- Current blockers include missing signed `.app`, signed `.pkg`, sandbox smoke, App Store Connect validation artifact, Apple Distribution codesign identity, installer identity, privacy answers, export compliance answers, screenshots, support URL, review notes, age rating, and release notes.
- App Store packaging, notarization, DMG, upload, and release work remain opt-in.

Execution order:

1. Next owner-approved execution step: build the app bundle with `packaging/macos/build_app_bundle.sh`.
2. Sign nested binaries and the outer app with the correct Apple Distribution identity and `AI Subtitle Studio.entitlements`; do not rely on ad-hoc signing for submission proof.
3. Validate sandboxed app launch, file access, audio/STT, model/network access, save/reopen, export, and source-app QA smoke.
4. Build a signed App Store `.pkg` with `packaging/macos/build_app_store_pkg.sh` using `INSTALLER_IDENTITY`.
5. Run App Store Connect validation with `packaging/macos/upload_app_store_build.sh validate` or Transporter before any upload.
6. Prepare non-code submission material separately: privacy answers, sandbox entitlement explanation, export compliance, screenshots, support URL, version metadata, and release notes.

Acceptance gates:

- Do not upload, tag, release, notarize, build DMG, or submit to App Store Connect without explicit owner approval for that step.
- App Store proof requires signed `.app`, signed `.pkg`, strict `codesign` verification, package signature verification, sandbox smoke, and App Store Connect validation output.
- Do not claim App Store readiness from source-app pytest or QA alone.
- Keep user-visible UI/UX and subtitle quality behavior unchanged unless the owner explicitly approves submission-driven changes.

Rollback:

- Packaging/signing changes should remain isolated under `packaging/macos/` and release docs unless a runtime entitlement issue requires app code changes.
- If sandbox breaks normal editor workflows, stop packaging and create a separate sandbox-compatibility fix item before retrying submission packaging.

## Migration Status

- Native migration is not an active direction for this repository.
- Keep the current Python/PyQt6 source app as the working product line.
- Source-app NLE runtime adoption archive: `COMPLETED_ACTION_ITEMS.md#source-app-nle-runtime-adoption-and-migration-status`; commit-boundary mutable timeline sync remains active only for uncovered release/commit sources.
- Persisted NLE project fields remain gated; broader persistence/save/render/export ownership cleanup requires a fresh owner-approved item and compatibility gate.
- Revisit migration only if the owner explicitly reopens it with a new scope and acceptance gate.

## Parked Candidates

These are not active queue items. Before executing one, create a fresh quality
gate and rollback branch.

- Playhead-only dirty-rect repaint: 현재 single-owner 2D full-canvas repaint가 잔상을 막는다. Macau visual smoke로 잔상 없음이 증명될 때만 별도 실험.
- App command/snapshot acknowledgement cleanup: `guided-subtitle-run`과 `capture-snapshot`이 실제 작업은 시작/저장했는데 CLI 응답은 timeout 또는 queued로 남는 관찰이 있었다. 성능 핵심 경로는 아니므로 active item 뒤에, artifact 신뢰도 개선으로만 다룬다.

## Waste And Lessons

- 폐기 후보 상세: `waste_action_item.md`
- 반복 금지 교훈: `lesson_n_learned.md`
- 공식 테스트 결과: `test_result.md`

## Metadata

```yaml
app_version: "04.00.18"
document_version: "04.00.18-source-app"
phase: "SOURCE_APP_CONTINUATION_V4_0_18"
queue_source_of_truth: "ACTION_ITEMS.md"
commit_policy: "Commit only when the user explicitly asks."
product_priority: "Accuracy before speed; optimize generation time only with behavior-preserving changes."
```
