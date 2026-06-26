<!--
Document-Version: 04.00.17-source-app
Phase: SOURCE_APP_CONTINUATION_V4_0_17
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

### 1. Post-Generation Editor Readiness And Verification Index

Goal: Make the editor reliably interactive immediately after subtitle generation completes, keep heavier cleanup/status work from blocking playback or editing, and make latest real-fixture proof easy to audit without changing subtitle quality policy or UI/UX.

Status: active, top priority now that the internal NLE baseline is complete

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
- The completed internal NLE baseline is a source-app domain/adapter layer only. It does not reopen native migration, Swift rewrite, QML migration, or a visible Premiere-style UI clone.
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
app_version: "04.00.17"
document_version: "04.00.17-source-app"
phase: "SOURCE_APP_CONTINUATION_V4_0_17"
queue_source_of_truth: "ACTION_ITEMS.md"
commit_policy: "Commit only when the user explicitly asks."
product_priority: "Accuracy before speed; optimize generation time only with behavior-preserving changes."
```
