DEX_REVIEW_READY
역할: 잼민이 (lightweight chores / prep work)
프로젝트: AI Subtitle Studio
레포지토리 경로: /Users/u_mo_c/Downloads/ai_subtitle_studio
범위: NLE timeline canvas state ownership scout

읽은 파일:
- `NLE_Action.md` ([NLE_Action.md](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/NLE_Action.md))
- `ui/timeline/timeline_canvas.py` ([timeline_canvas.py](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/ui/timeline/timeline_canvas.py))
- `ui/editor/editor_segments_timeline_context.py` ([editor_segments_timeline_context.py](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/ui/editor/editor_segments_timeline_context.py))
- `ui/editor/editor_save_manager.py` ([editor_save_manager.py](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/ui/editor/editor_save_manager.py))

결론: TimelineCanvas가 소유한 segments 상태 관리 흐름을 NLEProjectState 기반으로 안전하게 통합하기 위한 소유 필드, 업데이트 경로, 리스크 존 및 첫 안전 슬라이스를 조사 완료하여 리포트합니다.

findings:
1) **TimelineCanvas 소유 상태 필드 및 업데이트 경로**:
   - **소유 필드**: `self.segments` (자막 리스트), `self.gap_segments` (공백 자막 리스트), `self.total_duration` (전체 길이), `self.frame_rate` (FPS), `self.playhead_sec` (재생헤드 시간), `self.active_seg_start` (활성 자막 시작 시간).
   - **하향식 업데이트**: `editor_segments_timeline_context.py` 의 `_redraw_timeline()`이 에디터의 segments를 읽은 뒤 `self.timeline.update_segments(...)` 를 호출하여 타임라인의 `self.segments`를 셋업하고 `_rebuild_gap_segments_from_canvas_state()`를 통해 갭을 자동 빌드한 후 렌더 캐시(`_invalidate_render_cache`)를 무효화합니다.
   - **상향식 전파**: 타임라인 드래그나 다이아몬드 편집 시 `TimelineInputMixin` 및 `TimelineInlineEditMixin` 이 내부 `self.segments` 데이터의 시간을 변조(mutate)하고, 마우스 이벤트를 마친 시점에 `seg_time_changed`나 `diamond_merge` 시그널을 방출하여 에디터 상태를 업데이트한 후 다시 하향식 redraw를 유도합니다.

2) **첫 번째 최소 안전 슬라이스 제안**:
   - **Read-Only Single Source of Truth Projection**:
     - 에디터가 `_redraw_timeline()` 시점에 쌩 list를 던지는 대신, 에디터의 `NLEProjectState` 인스턴스에서 직접 추출한 frame-accurate projection segments 데이터를 `update_segments()`에 바인딩하는 읽기 경로 단일화.
     - 기존의 NLE projection 및 save-project verification 파이프라인(`nle_save_export_segments_from_editor_rows` 등)의 검증 로직에 영향을 주지 않으면서 타임라인의 데이터 소스를 NLE로 안전하게 대체할 수 있습니다.

3) **Taption UX 규칙을 깨지 않는 회귀 테스트 후보 (4개)**:
   - `test_timeline_render_cache.py`: NLE state로의 소스 대체 후에도 geometry signature 기반 렌더 캐시 무효화와 Qt widget 리페인트 플리커링이 100% 억제되는지 확인.
   - `test_timeline_playhead_fit.py` 연계: NLE의 exact rational frame boundary와 타임라인 픽셀 매핑 계산(`_pixels_per_frame`) 간의 오차가 1ms 미만인지 검증.
   - `test_timeline_nle_sync.py` (신규 제안): 타임라인 드래그 완료 시 NLE state의 mutable write 가 동작하고 다시 타임라인에 무결하게 sync되는지 연동 확인.
   - `test_roughcut_v2_output_compat.py`: NLE state로 관리되는 타임라인 자막이 roughcut join point 및 exact boundary marker 와의 정합성을 깨뜨리지 않는지 검증.

4) **지금 바로 변경하면 위험한 지점 (Risky Zones)**:
   - **드래그 중 실시간 NLE mutable write 금지**: 마우스 드래그 스크러빙(`self._is_scrubbing` 또는 `_timeline_drag_in_progress` 상태) 중 매 픽셀마다 NLE mutable state를 재계약/re-projection하면 UI가 급격히 끊길 수(lag) 있습니다. 드래그 중에는 경량화된 in-memory raw dict를 활용하고, 드래그가 끝난 시점(`_on_drag_finished`)에만 NLE에 1회 flush 하도록 격리해야 합니다.
   - **_normalize_canvas_row의 frame rounding 불일치**: Canvas 자체에서 rounding하는 frame/time 변환 방식이 NLE rational fps math와 불일치할 경우, 1프레임 미세 오차(drift)가 누적되어 세이브 시 overlap 에러가 발생할 수 있습니다.

defer: (none)
덱스 확인 포인트:
- `TimelineCanvas.update_segments` 에 주입되는 자막 소스를 에디터의 `NLEProjectState` projection으로 우회하여 단일화하는 아키텍처 설계를 덱스의 mutable 구현 단계에 반영.
