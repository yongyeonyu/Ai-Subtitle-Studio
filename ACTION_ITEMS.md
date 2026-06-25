<!--
Document-Version: 04.00.16-source-app
Phase: SOURCE_APP_CONTINUATION_V4_0_16
Last-Updated: 2026-06-26
Updated-By: Codex
Purpose: Consolidated active execution queue for the current source-app line.
-->
# ACTION_ITEMS.md - Active Execution Queue

This file is now the single source of truth for active performance ideas,
action items, execution order, QA gates, and
rollback rules.

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
- 정상 완료된 idea/action item은 이 파일에서 삭제한다. 완료 이력은 필요할 때만 `test_result.md`, release note, `output/manual_verification/latest/`, `waste_action_item.md`, 또는 `lesson_n_learned.md`에 남긴다.

## Active Execution Queue

### 1. Source-App Internal NLE Timeline Architecture Plan

Goal: Move the current subtitle-first project, timeline, roughcut, and export ownership toward a Premiere-style NLE internal structure while keeping the existing Python/PyQt6 source app, current UI/UX, and subtitle quality policy unchanged.

Status: active, top-priority planning and adapter sequence

Why this is first:

- Recent roughcut exact-join, render-plan sidecar, save/reopen, cut-boundary seed, and subtitle-sync work all need one auditable time model.
- A small internal NLE domain layer can make media assets, sequences, tracks, clips, captions, markers, and render plans explicit before more editor-readiness or status-path work piles on top.
- This is not native migration, Swift rewrite, QML adoption, or a Premiere UI clone. It is a source-app architecture cleanup that should remain invisible to users until explicitly approved otherwise.

Agent-role execution goals:

- `덱스`: define the smallest domain boundary and adapter path first, then land it in behavior-preserving slices with tests.
- `한결`: review ownership boundaries, rollback shape, schema compatibility, and whether the layer reduces coupling instead of becoming another parallel state store.
- `서린`: require fixture evidence for save/reload, subtitle count, cut-boundary round trip, render sidecars, seek/playhead, and export timing before promotion.
- `유진`: ensure the current subtitle editing workflow still feels unchanged; UI lanes/tracks are deferred unless the owner explicitly asks for visible workflow changes.

Scope:

- `core/project/project_format.py`
- `core/project/project_io.py`
- `core/project/project_assets.py`
- `core/project/project_context.py`
- `core/project/project_roughcut_store.py`
- `core/roughcut/models.py`
- `core/roughcut/edl_generator.py`
- `core/roughcut/render_executor.py`
- `core/roughcut/renderer_skeleton.py`
- `core/renderer.py`
- `ui/editor/editor_widget.py`
- `ui/editor/editor_save_manager.py`
- `ui/editor/editor_project_open_native.py`
- `ui/editor/editor_roughcut_draft.py`
- `ui/timeline/timeline_canvas.py`
- `ui/roughcut/roughcut_state.py`
- `ui/roughcut/roughcut_export.py`
- `tools/verify_full_media_pipeline.py`
- `tools/qa_suite_runner.py`
- `docs/ARCHITECTURE.md`
- `docs/FEATURE_REGISTRY.md`
- `docs/HANDOFF.md`

Execution order:

1. Map current ownership and invariants for project payloads, media assets, editor segments, roughcut candidates, cut-boundary seeds, render plans, sidecars, timeline canvas state, and save/reopen behavior. Explicitly separate cut boundary point data from clip boundary span data before proposing code.
2. Draft the source-app NLE domain contract in docs first: `ProjectAsset`, `Sequence`, `Track`, `Clip`, `CaptionSegment`, `TimelineMarker`, and `RenderPlan`. Define timebase, source time, sequence time, output time, and exact-join metadata in one place.
3. Add read-only adapters that build an NLE snapshot from the existing project/editor/roughcut state without changing save files, UI state, subtitle timing, STT, LLM, VAD, or render output. Tests must prove the snapshot matches current SRT/project/roughcut data.
4. Route roughcut exact joins and cut-boundary seeds through sequence markers or edit points while keeping existing `.aissproj`, `_edl.json`, and `_render_plan.json` fields as compatibility sources.
5. Route render/export plan construction through the NLE snapshot, but require byte/metadata-equivalent sidecars and unchanged output duration for the current roughcut fixture before widening.
6. Add save/reload round-trip compatibility: legacy projects load into the NLE snapshot, new snapshots still preserve old project fields, and missing-media/relink/proxy/cache metadata remains non-destructive.
7. Only after the internal model and adapter path are proven, decide whether visible timeline lanes, asset bins, markers, or track controls are worth exposing. Any visible UI/UX work needs a new explicit owner approval and separate acceptance gate.

Acceptance gates:

- No UI/UX labels, layout, colors, shortcuts, popup behavior, or visible workflow changes without explicit owner approval.
- No subtitle quality policy, STT2, LLM, LoRA, VAD, timing, or model-selection changes.
- Legacy `.aissproj`, direct SRT open, roughcut sidecars, and rendered roughcut reopen paths must continue to load.
- Subtitle count, final segment count, first/last subtitle time, save/reload, seek/playhead, overlay, gutter, minimap, and roughcut selected candidate state must match the pre-change baseline.
- Focused tests must cover project save/load, editor segment reload, roughcut state, sidecar exact-join restore, render-plan creation, and app-command smoke before any source-app proof.
- Source-app Macau and X5 fixture proof must be stored under `output/manual_verification/latest/` before promoting this architecture as the new baseline.

Rollback:

- Land docs/schema/adapters before replacing owners. Each slice must be reversible without changing subtitle-generation algorithms.
- Keep old project fields and sidecar readers until source-app proof shows the NLE snapshot fully round-trips legacy and new artifacts.
- If the layer creates duplicate mutable state or timing drift, stop and revert the adapter slice before routing render/export or editor state through it.

### 2. Post-Generation Editor Readiness And Verification Index

Goal: Make the editor reliably interactive immediately after subtitle generation completes, keep heavier cleanup/status work from blocking playback or editing, and make latest real-fixture proof easy to audit without changing subtitle quality policy or UI/UX.

Status: active, next after the internal NLE plan's docs/schema/adapter baseline unless the owner directs a hotfix

Current baseline:

- X5 High post-STT UI/status hot-path trim proof is stored at `output/manual_verification/latest/20260527_x5_hot_path_trim_proof/`.
- High-refresh/editor-timeline source-app proof is stored at `output/manual_verification/latest/20260526_225507_high_refresh_source_app_proof/verification_summary.md`.
- Related guard set passes:
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_segment_reload.py tests/test_app_command_bridge.py tests/test_editor_roughcut_draft.py tests/test_editor_autosave_cleanup.py tests/test_verify_full_media_pipeline.py tests/test_qa_suite_runner.py`
  - Result: `267 passed`
- X5 hot-path verifier result:
  - `ok=true`, `pipeline_elapsed_sec=66.576`, `total_elapsed_sec=71.285`, `peak_rss_bytes=1776435200`, `raw/final=49/56`, pressure transitions `critical -> warning`.
- Diagnostic caveat: `x5_hot_path_golden_regression_0_180.*` is recorded as evidence only, not a release gate. The current golden regression evaluator scores the prior accepted `qa_suite_full_20260523_100114` X5 output similarly low, so its semantics must be fixed before it can block release.

Agent-role execution goals:

- `덱스`: primary owner for completion-to-idle/UI-frame stability bugs. Map the completion-to-idle path first, keep patches narrow, and update proof artifacts.
- `한결`: separate editor-ready state from cleanup/model-release/layout-rebalance work and preserve rollback boundaries.
- `서린`: require Macau/X5/Tinyping evidence that distinguishes real regressions from stale artifact, scorer mismatch, or one-frame layout noise.
- `유진`: protect editing trust signals after generation: visible subtitles, playable preview, stable selection, save/reload consistency, no apparent subtitle loss, and no full-window frame shake.

Scope:

- `ui/editor/editor_pipeline_completion.py`
- `ui/editor/editor_save_manager.py`
- `ui/editor/editor_widget.py`
- `ui/editor/editor_lifecycle.py`
- `ui/editor/ux/editor_video_controls.py`
- `ui/editor/ux/timestamp_area.py`
- `ui/editor/ux/editor_tab_timing.py`
- `ui/editor/editor_precision_refine.py`
- `ui/timeline/timeline_widget.py`
- `ui/menu_bar.py`
- `ui/main/main_runtime_cleanup.py`
- `core/runtime/memory_manager.py`
- `tools/verify_full_media_pipeline.py`
- `tools/qa_suite_runner.py`
- `output/manual_verification/latest/`

Execution order:

1. Map current generation completion, autosave, editor idle-ready, roughcut follow-up, and cleanup timing.
2. Add or verify tests proving playback/edit/status commands can proceed before heavier cleanup completes.
3. Add a regression check for the reported editor interaction lock: click the subtitle editor/timestamp editing surface, change a subtitle time, commit or cancel the edit, then verify timeline zoom in, zoom out, fit-to-view, time-window, subtitle magnet, playback controls, save, and bottom/global menu buttons still respond.
4. Add a post-generation UI-frame stability investigation and fix plan for the reported full-frame shake: capture before/during/after geometry for `MainWindow`, workspace splitter, editor frame, video frame, timeline frame, bottom work panel, and global menu bar; identify whether completion cleanup, model release, status/log panel refresh, video/timeline rebalance, or home/sidebar rebuild causes the transient resize; then make completion apply layout changes once, after the editor is idle, without moving the approved timeline/global-canvas border positions.
5. Add a precision-refine completion affordance: when 정밀 작업 finishes successfully, the bottom `정밀` icon/button must switch to a dimmed neon green completed state so it is visually distinct from available-but-not-run, running, disabled, and failed states.
6. Build a compact latest-verification index for Macau, X5, and Tinyping artifacts so release readiness is auditable.
7. Validate the chosen slice with source-app or official QA evidence before widening scope.

#### Jammini Delegation Queue

These are explicit `잼민이` queue items for the current active execution item. They are intentionally limited to simple, bounded, draft/review/doc/prep-only support work so `잼민이` can keep moving without waiting between each small item.

| Queue ID | Status | Owner | Scope | Required Output |
| --- | --- | --- | --- | --- |
| JQ-01 | completed | `잼민이` | Map the owner-file path for `project open -> roughcut auto-open -> roughcut state restore -> save/reopen` across `ui/project/project_panel.py`, `ui/editor/editor_project_open_native.py`, `ui/roughcut/roughcut_state.py`, `core/roughcut/models.py`, `tests/test_project_segment_reload.py`, `tests/test_roughcut_candidates.py` | `DEX_REVIEW_READY` packet with file-role map and the most fragile handoff points |
| JQ-02 | completed | `잼민이` | Write a source-app smoke checklist for `candidate 전환 -> safety filter 변경 -> chapter 선택 -> 저장 -> 재열기 -> roughcut 자동 진입` | `DEX_REVIEW_READY` packet with an ordered real-app checklist and pass/fail observations to capture |
| JQ-03 | completed | `잼민이` | Review `core/roughcut/models.py`, `ui/roughcut/roughcut_state.py`, and the new round-trip tests for hidden restore edge cases only | `DEX_REVIEW_READY` findings-first review, limited to restore/cache/compact-payload risks |
| JQ-04 | completed | `잼민이` | Prepare the narrow validation command bundle and artifact naming pattern for the next roughcut real-app proof under `output/manual_verification/latest/` | `DEX_REVIEW_READY` packet with exact commands, artifact folder suggestion, and minimal evidence checklist |
| JQ-05 | completed | `잼민이` | Draft the next doc-sync delta that should be applied after roughcut source-app proof lands, limited to `docs/HANDOFF.md`, `idea.md`, and `test_result.md` touch points | `DEX_REVIEW_READY` packet with only the proposed doc deltas, no code patch |
| JQ-06 | completed | `잼민이` | Build a no-patch shortlist of unused/simple cleanup candidates in roughcut owner files (`ui/roughcut/*`, related tests) that are safe to inspect later | `DEX_REVIEW_READY` packet separating harmless cleanup from anything that could alter restore/save semantics |

Queue rules:

- Consume this queue top-to-bottom only while each item stays simple and draft/review/doc/prep-only.
- Do not make code changes from this queue unless `덱스` or the owner explicitly upgrades one item into an implementation task.
- Begin every queue result with `DEX_REVIEW_READY` and include the `Queue ID`.
- Stop the whole queue immediately if the owner says `잼민이 멈춰` or `잼민이 하던 일 모두 취소`.

Acceptance gates:

- No subtitle quality policy, STT2, LoRA, LLM, VAD, timing, or UI/UX default changes without explicit owner approval.
- Generation completion returns the editor to a trustworthy interactive state before heavy cleanup can stall playback/editing.
- Editing a subtitle time from the editor pane must not leave focus capture, modal state, drag/inline-edit lock, cursor override, or disabled toolbar/menu state behind; zoom in/out, fit-to-view, and all timeline/global buttons must remain clickable immediately after the edit.
- Subtitle generation completion must not visibly shake or resize the whole UI frame. Geometry for the editor/video/timeline/bottom-menu surfaces should remain stable except for intentional progress/status text changes, and any one-shot rebalance must be measured and proven not to move approved borders.
- 정밀 작업 success state must be visible on the `정밀` button as a dimmed fluorescent green icon/button state, without changing other bottom-menu labels or altering subtitle timing/quality behavior.
- Verification index points to current artifacts and calls out stale or diagnostic-only evidence separately from release gates.

Rollback:

- Revert completion/readiness orchestration before touching subtitle-generation algorithms.
- Do not skip cleanup entirely; defer or stage it only when evidence shows editor responsiveness improves without memory-pressure harm.

## Migration Status

- Native migration is not an active direction for this repository.
- Keep the current Python/PyQt6 source app as the working product line.
- The NLE-style plan above is an internal source-app domain/adapter plan only. It does not reopen native migration, Swift rewrite, QML migration, or a visible Premiere-style UI clone.
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
app_version: "04.00.16"
document_version: "04.00.16-source-app"
phase: "SOURCE_APP_CONTINUATION_V4_0_16"
queue_source_of_truth: "ACTION_ITEMS.md"
commit_policy: "Commit only when the user explicitly asks."
product_priority: "Accuracy before speed; optimize generation time only with behavior-preserving changes."
```
