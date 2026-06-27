DEX_REVIEW_READY
역할: 잼민이 (lightweight chores / prep work)
프로젝트: AI Subtitle Studio
레포지토리 경로: /Users/u_mo_c/Downloads/ai_subtitle_studio
범위: NLE timeline commit-boundary mutable sync scout

읽은 파일:
- `ACTION_ITEMS.md` ([ACTION_ITEMS.md](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/ACTION_ITEMS.md))
- `ui/editor/ux/timeline_canvas_editing.py` ([timeline_canvas_editing.py](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/ui/editor/ux/timeline_canvas_editing.py))
- `ui/editor/ux/timeline_subtitle_segment_editing.py` ([timeline_subtitle_segment_editing.py](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/ui/editor/ux/timeline_subtitle_segment_editing.py))
- `ui/editor/ux/editor_timeline_video.py` ([editor_timeline_video.py](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/ui/editor/ux/editor_timeline_video.py))
- `core/project/nle_dual_write.py` ([nle_dual_write.py](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/core/project/nle_dual_write.py))
- `ui/timeline/timeline_canvas.py` ([timeline_canvas.py](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/ui/timeline/timeline_canvas.py))

결론: 타임라인 드래그 완료 및 편집 확정 시점(Commit-Boundary)에서 NLE Project State 에 안전하게 변경 사항을 동기화(Sync)하기 위한 핵심 오너 심볼, 최소 적용 슬라이스, 리스크 존을 조사 완료하여 리포트합니다.

findings:
1) **Commit/Release Boundary 핵심 오너 심볼**:
   - **Body & Edge Timing Drag Release**: `timeline_subtitle_segment_editing.py:mouseReleaseEvent` 에서 마우스 릴리즈를 감지하여 `self.seg_time_changed.emit(line_num, start, end, edge_type)` 을 방출.
   - **Diamond (Cut) Timing Drag Release**: `mouseReleaseEvent` -> `_emit_diamond_pair_time_changed()` (in `timeline_input.py:142`) 가 루프 내에서 동일하게 `self.seg_time_changed.emit(...)` 을 최종 방출.
   - **수신 및 처리 병목**: `editor_timeline_video.py:_on_seg_time_changed` 가 수신하여 NLE Project State를 생성하고 `apply_caption_resize_dual_write_pilot`을 호출하여 write를 진행.
   - **Merge Release**: `mouseReleaseEvent` -> `self.diamond_merge.emit(left_line, right_line)` 방출.
   - **Split Commit**: `timeline_canvas_editing.py:_commit_inline_edit_or_split` -> `self.sig_split_request.emit(line, split_sec, cursor)` 방출.

2) **최소 Sync/Provenance 적용 슬라이스 제안**:
   - **Body Drag (center) 의 NLE Dual-Write 통합**:
     - 현재 `_on_seg_time_changed`는 `edge_type`이 `center`일 때 NLE write-path를 우회하고 레거시 timing planning을 호출합니다.
     - `_nle_live_editor_caption_resize_result` 의 `edge_type` 가드 조건에 `center`를 편입시켜 `apply_caption_resize_dual_write_pilot` 이 자막 body shift Retiming도 NLE State의 mutable write-path를 타도록 연동하는 것이 가장 안전한 첫 번째 슬라이스입니다.
     - 드래그 진행 중에는 segments dict 시간 값만 수정(per-pixel NLE write 방지)하다가, 마우스 릴리즈 직후 `_on_seg_time_changed` 진입 시점에 1회 NLE dual-write 및 projection reload가 일어나므로 성능 오버헤드가 없고 검증이 매우 쉽습니다.

3) **Taption Magnet/Gap/Reorder/Overlap 회귀 테스트 후보**:
   - `test_project_nle_runtime_cutover.py`: 자막 바디(center) 이동 후 NLE dual write retiming 및 neighbor block trimming/drop 검증.
   - `test_timeline_playhead_fit.py`: NLE rational FPS 변환 후 타임라인 playhead 오차 검증.
   - `test_timeline_hit_targets.py`: NLE write 및 reload 후 타임라인 자막 handle hover/click hit target 영역 검증.
   - `test_timeline_magnet_behavior.py` (신규 제안): Taption gap snap suppression, neighbor block reordering(완전 교차 조건) 규칙이 NLE retiming 후에도 보존되는지 검증.

4) **지금 바로 변경하면 위험한 지점 (Risky Zones)**:
   - **center_reorder 분기 이중화 위험**: `_on_seg_time_changed:1340` 에 있는 `center_reorder_left/right` 분기는 현재 NLE write를 타지 않고 `_center_reorder_rows()` 레거시로 빠집니다. 이 로직이 NLE State와 싱크되지 않으면 save 시점 projection mismatch가 납니다. reorder 또한 NLE write-path로 안전하게 수렴시켜야 합니다.
   - **QTextCursor Edit Block Lifecycle**: `_on_seg_time_changed` 내에서 `cur.beginEditBlock()`이 동작 중일 때 block userData(start/end)가 reload로 덮어씌워지면 Qt가 블록 병합 복구 과정에서 시간을 원래 상태로 되돌리는 오작동이 있습니다. QTextCursor edit block이 완전히 `endEditBlock()`을 통해 커밋된 후에 NLE reload를 타야 합니다.

defer: (none)
덱스 확인 포인트:
- `_on_seg_time_changed` 내부의 `center` 드래그 릴리즈 및 `center_reorder` 분기를 NLE dual-write pilot 연산으로 수렴시키는 변경 설계를 구현 단계에 반영.
