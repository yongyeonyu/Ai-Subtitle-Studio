<!--
Document-Version: 04.00.18-source-app
Phase: SOURCE_APP_CONTINUATION_V4_0_18
Last-Updated: 2026-06-27
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

No active execution queue items are open.

The previous `Post-Generation Editor Readiness And Verification Index` item was completed on 2026-06-27 and removed from this queue per the completed-item rule. Completion evidence is recorded in:

- `test_result.md`
- `docs/HANDOFF.md`
- `output/manual_verification/latest/post_generation_editor_readiness_index_20260627/verification_index.md`

Add a new active item only when the owner gives a fresh scope or a verified regression creates a concrete next action.

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
app_version: "04.00.18"
document_version: "04.00.18-source-app"
phase: "SOURCE_APP_CONTINUATION_V4_0_18"
queue_source_of_truth: "ACTION_ITEMS.md"
commit_policy: "Commit only when the user explicitly asks."
product_priority: "Accuracy before speed; optimize generation time only with behavior-preserving changes."
```
