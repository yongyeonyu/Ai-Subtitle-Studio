<!--
Document-Version: 04.00.15-mac-native
Phase: MAC_NATIVE_APPSTORE_V4_0_15_RELEASED
Last-Updated: 2026-05-26
Updated-By: Codex
Purpose: Consolidated active execution queue. Former `idea_item.md` and `NATIVE_LIB_PLAN.md` content lives here.
-->
# ACTION_ITEMS.md - Active Execution Queue

This file is now the single source of truth for active performance ideas,
action items, native migration candidates, execution order, QA gates, and
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
- native 승격은 Swift/C++가 Python과 parity를 갖고 real fixture에서 같거나 빠를 때만 한다.
- live Qt widget, mutable editor state, subprocess orchestration, model-worker ownership, UI callback은 native로 통째 이전하지 않는다.
- 자막 에디터 상호작용 표면은 2D-only이다. 자막 본문 편집, 자막 세그먼트 편집/생성/삭제, 플레이헤드 이동, 컷 경계, 다이아몬드, waveform/minimap 렌더링에 3D view, QML SceneGraph, OpenGL/Metal-backed UI surface를 새 default로 도입하지 않는다.
- 전체 앱 shell, 메뉴, 팝업, 다이얼로그의 새 UI 기본값은 `Qt Widgets`로 고정한다. QML은 새 UI default에서 제외하고, Metal은 UI renderer가 아니라 native compute 후보로만 검토한다.
- 아이디어 발굴 또는 실행 전 `waste_action_item.md`와 `lesson_n_learned.md`를 먼저 읽고, 폐기된 아이디어를 새 근거 없이 반복하지 않는다.
- 실패/무효 후보는 `waste_action_item.md`에 hypothesis, change, metrics, quality, artifact, rejection reason을 남긴다.
- 반복하면 안 되는 진단/실험/운영 실수는 `lesson_n_learned.md`에 남긴다.
- 정상 완료된 idea/action/native item은 이 파일에서 삭제한다. 완료 이력은 필요할 때만 `test_result.md`, release note, `output/manual_verification/latest/`, `waste_action_item.md`, 또는 `lesson_n_learned.md`에 남긴다.

## Active Execution Queue

### 1. High-Refresh 2D Playback Validation And Promotion

Goal: Keep the Qt Widgets/QPainter 2D editor path intact while making playback, playhead follow, and footer time UI track the display refresh rate instead of only the source video fps.

Status: active

Scope:

- `ui/timeline/render_clock.py`
- `ui/timeline/timeline_widget.py`
- `ui/timeline/timeline_canvas.py`
- `ui/timeline/timeline_paint.py`
- `ui/editor/ux/editor_timeline_video.py`
- `ui/editor/video_player_transport.py`
- `ui/editor/ux/timeline_input.py`
- `tests/test_timeline_playhead_fit.py`
- `tests/test_video_player_widget.py`
- `tests/test_timeline_render_cache.py`
- `tests/test_editor_rendering_ownership_audit.py`

Current baseline:

- Local commit `9967c7f7` (`perf: smooth high-refresh timeline playback`) landed display-refresh-aware timers plus logical/visual playhead separation.
- Focused guard set currently passes:
  - `./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py tests/test_video_player_widget.py tests/test_editor_rendering_ownership_audit.py tests/test_timeline_render_cache.py`
  - Result: `272 passed`
- No new real-app Macau/X5 verification artifact has been captured yet for this local patch.

Execution order:

1. Reopen the source app on Macau and X5 fixtures and verify playback smoothness, visible playhead, footer time label, and subtitle overlay stay aligned.
2. Re-check save/open/seek, shadow playhead, handle hit targets, and selected-playhead behavior so the visual-only playhead path does not change subtitle timing persistence or interaction semantics.
3. If command surface or bundle-facing paths change, rebuild the app bundle before bundle-based QA. Otherwise validate on the source app first.
4. If drift or ghosting appears, back out display-only wiring first. Do not reintroduce QML, SceneGraph, OpenGL, Metal UI surfaces, or playhead-only dirty-strip defaults.

Acceptance gates:

- Subtitle timing/save policy remains frame-snapped and unchanged.
- No `00:00 / 00:00` regression, ghost playhead, or visible handle-hit mismatch appears.
- `AI_SUBTITLE_UI_REFRESH_HZ` override remains available for deterministic reproduction and rollback.
- Real-app Macau and X5 verification artifacts are stored under `output/manual_verification/latest/`.

Rollback:

- Revert `render_clock.py` integrations first.
- Preserve logical frame snap even if visual sub-frame motion is disabled.
- Keep Qt Widgets/QPainter as the only default visible editor/timeline renderer.

### 2. X5 High Post-STT UI And Status Hot Path Trim

Goal: Continue the preexisting X5 High post-STT UI/status cleanup only after item 1 has real-app proof, and reduce avoidable UI churn without changing subtitle quality policy.

Status: pending

Scope:

- `ui/editor/editor_segments_live_preview.py`
- `ui/editor/editor_pipeline_status.py`
- `ui/editor/editor_pipeline_signal_bridge.py`
- `ui/editor/editor_save_manager.py`
- `output/memory_monitor/subtitle_generation_latest.json`

Execution order:

1. Prevent live preview text updates from triggering heavy thumbnail/probe churn during backend processing.
2. Keep compact guided status fields available even when full status payloads are busy or truncated.
3. Add short pressure-aware guards around roughcut/LLM follow-up work only when pressure stays at `critical`.
4. Validate on X5 High real-app flow before widening scope.

Acceptance gates:

- X5 High final subtitle count and roughcut completion stay equivalent.
- Memory pressure evidence is captured without changing subtitle quality policy.
- If command or app automation surface changes, rebuild the app bundle before `major` or `full` QA.

Rollback:

- Revert status/preview throttles before touching subtitle-generation logic.
- Do not skip STT2, LoRA, LLM, or lower quality gates as a speed shortcut.

## Native Migration Rules

- Native migration follows the same active queue above; do not maintain a separate native queue.
- Native candidates graduate only when Swift/C++ parity is proven against Python behavior and real fixtures show equal or better performance.
- Do not migrate live Qt widget ownership, mutable editor state, subprocess orchestration, model-worker lifetime, or UI callback surfaces wholesale into native code.
- Prefer native compute helpers for bounded hot paths with stable inputs and outputs.
- Completed native-library items must be removed from this file instead of kept as checked history.

## Parked Candidates

These are not active queue items. Before executing one, create a fresh quality
gate and rollback branch.

- Playhead-only dirty-rect repaint: 현재 single-owner 2D full-canvas repaint가 잔상을 막는다. Macau visual smoke로 잔상 없음이 증명될 때만 별도 실험.
- App command/snapshot acknowledgement cleanup: `guided-subtitle-run`과 `capture-snapshot`이 실제 작업은 시작/저장했는데 CLI 응답은 timeout 또는 queued로 남는 관찰이 있었다. 성능 핵심 경로는 아니므로 active item 뒤에, artifact 신뢰도 개선으로만 다룬다.
- Larger real-index Swift/native policy helper: corrected 500-doc synthetic에서 parity는 통과했지만 speedup이 `< 1.0`이다. 큰 payload에서 새 speedup 근거가 나오기 전까지 Python 유지.

## Waste And Lessons

- 폐기 후보 상세: `waste_action_item.md`
- 반복 금지 교훈: `lesson_n_learned.md`
- 공식 테스트 결과: `test_result.md`

## Metadata

```yaml
app_version: "04.00.15"
document_version: "04.00.15-mac-native"
phase: "MAC_NATIVE_APPSTORE_V4_0_15_RELEASED"
queue_source_of_truth: "ACTION_ITEMS.md"
commit_policy: "Commit only when the user explicitly asks."
product_priority: "Accuracy before speed; optimize generation time only with behavior-preserving changes."
```
