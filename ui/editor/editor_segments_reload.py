"""Editor segment reload helpers shared by editor and multiclip flows."""

from __future__ import annotations


class EditorSegmentsReloadMixin:
    def _reload_segment_order_key(self, seg: dict) -> tuple[float, float, int]:
        try:
            start = float(seg.get("start", 0.0) or 0.0)
        except Exception:
            start = 0.0
        try:
            end = float(seg.get("end", 0.0) or 0.0)
        except Exception:
            end = 0.0
        try:
            line = int(seg.get("line", 0) or 0)
        except Exception:
            line = 0
        return (start, end, line)

    def _reload_segments_normalized(self, segs) -> list[dict]:
        normalizer = getattr(self, "_normalize_multiclip_segment_order", None)
        if callable(normalizer):
            return list(normalizer(segs))
        rows = [dict(seg) for seg in (segs or []) if isinstance(seg, dict)]
        rows.sort(key=self._reload_segment_order_key)
        for i, seg in enumerate(rows):
            seg["line"] = i
        return rows

    def _reload_segments_clear_runtime_queues(self) -> None:
        try:
            if getattr(self, "_queue_timer", None) is not None:
                self._queue_timer.stop()
        except Exception:
            pass
        if hasattr(self, "_segment_queue"):
            self._segment_queue.clear()
        for attr, value in (
            ("_live_editor_preview_queue", []),
            ("_live_editor_preview_segments", []),
            ("_live_editor_preview_keys", set()),
        ):
            if hasattr(self, attr):
                setattr(self, attr, value.copy() if hasattr(value, "copy") else value)

    def _reload_segments_suspend_updates(self) -> tuple[object, object, object]:
        text_edit = getattr(self, "text_edit", None)
        timestamp_area = getattr(text_edit, "timestampArea", None) if text_edit is not None else None
        timeline = getattr(self, "timeline", None)
        if text_edit is not None and hasattr(text_edit, "setUpdatesEnabled"):
            text_edit.setUpdatesEnabled(False)
        if timestamp_area is not None and hasattr(timestamp_area, "setUpdatesEnabled"):
            timestamp_area.setUpdatesEnabled(False)
        if timeline is not None and hasattr(timeline, "setUpdatesEnabled"):
            timeline.setUpdatesEnabled(False)
        return text_edit, timestamp_area, timeline

    def _reload_segments_restore_updates(self, *, text_edit, timestamp_area, timeline) -> None:
        if timeline is not None and hasattr(timeline, "setUpdatesEnabled"):
            timeline.setUpdatesEnabled(True)
        if timestamp_area is not None and hasattr(timestamp_area, "setUpdatesEnabled"):
            timestamp_area.setUpdatesEnabled(True)
        if text_edit is not None and hasattr(text_edit, "setUpdatesEnabled"):
            text_edit.setUpdatesEnabled(True)
        self._reload_segments_refresh_timestamp_layer_after_restore()

    def _reload_segments_refresh_timestamp_layer_after_restore(self) -> None:
        refresher = getattr(self, "_refresh_editor_timestamp_metadata", None)
        if not callable(refresher):
            return
        try:
            refresher(full=False)
        except Exception:
            return
        try:
            from PyQt6.QtCore import QTimer

            for delay_ms in (0, 120, 360):
                QTimer.singleShot(
                    delay_ms,
                    lambda e=self: e._refresh_editor_timestamp_metadata(full=False),
                )
        except Exception:
            pass

    def _reload_segments_apply_rows(self, segs: list[dict], *, preserve_view: bool) -> list[dict]:
        loaded_segments = None
        fast_loader = getattr(self, "_bulk_load_segments_to_document", None)
        if callable(fast_loader):
            loaded_segments = fast_loader(segs, preserve_view=preserve_view)
        if loaded_segments is None:
            self.text_edit.clear()
            self.append_segments(segs)
            if hasattr(self, "_flush_queue"):
                self._flush_queue()
                try:
                    if getattr(self, "_queue_timer", None) is not None:
                        self._queue_timer.stop()
                except Exception:
                    pass
        return loaded_segments if isinstance(loaded_segments, list) else segs

    def _reload_segments_refresh_runtime(self, timeline_segments: list[dict], *, mark_dirty: bool) -> None:
        if hasattr(self, "_rebuild_subtitle_memory_cache"):
            self._rebuild_subtitle_memory_cache(timeline_segments)
        else:
            self._cached_segs = timeline_segments
        capture_canonical = getattr(self, "_capture_canonical_editor_sync_snapshot", None)
        if callable(capture_canonical):
            try:
                # 변경 금지: 수동 시간 편집/화살표 병합 직후에는 기존 canonical
                # timestamp snapshot이 방금 바뀐 end_sec를 되돌릴 수 있다.
                # 런타임 캐시를 갱신한 같은 tick에서 canonical도 현재 문서 상태로
                # 갱신해야 에디터/세그먼트/타임라인 시간이 다시 갈라지지 않는다.
                capture_canonical(segments=timeline_segments)
            except Exception:
                pass
        refresher = getattr(self, "_refresh_editor_timestamp_metadata", None)
        if callable(refresher):
            refresher(full=True)
            try:
                from PyQt6.QtCore import QTimer
                for delay_ms in (0, 120, 360):
                    QTimer.singleShot(
                        delay_ms,
                        lambda e=self: e._refresh_editor_timestamp_metadata(full=False),
                    )
            except Exception:
                pass
        total_dur = timeline_segments[-1]["end"] if timeline_segments else 0.0
        if hasattr(self, "video_player") and self.video_player.total_time > 0:
            total_dur = max(total_dur, self.video_player.total_time)
        self.timeline.update_segments(timeline_segments, self._active_seg_start, total_dur)
        if mark_dirty:
            self._mark_dirty()
        self._schedule_timeline()

    def _reload_segments_from_list(self, segs, *, preserve_view: bool = False, mark_dirty: bool = True):
        segs = self._reload_segments_normalized(segs)
        self._reload_segments_clear_runtime_queues()
        self._is_initial_load = (True if segs else False) and not bool(preserve_view)
        prev_suspend_autoseek = bool(getattr(self, "_suspend_append_segments_autoseek", False))
        timeline_segments = list(segs)
        if preserve_view:
            self._suspend_append_segments_autoseek = True
        text_edit, timestamp_area, timeline = self._reload_segments_suspend_updates()
        try:
            timeline_segments = self._reload_segments_apply_rows(segs, preserve_view=preserve_view)
            self._reload_segments_refresh_runtime(timeline_segments, mark_dirty=mark_dirty)
        finally:
            self._suspend_append_segments_autoseek = prev_suspend_autoseek
            self._reload_segments_restore_updates(
                text_edit=text_edit,
                timestamp_area=timestamp_area,
                timeline=timeline,
            )
        sync_guard = getattr(self, "_enforce_editor_segment_sync_after_reload", None)
        if callable(sync_guard):
            try:
                sync_guard(list(timeline_segments or []))
            except Exception:
                pass
        timeline_sync_guard = getattr(self, "_enforce_timeline_segment_sync_after_reload", None)
        if callable(timeline_sync_guard):
            try:
                timeline_sync_guard(list(timeline_segments or []))
            except Exception:
                pass
