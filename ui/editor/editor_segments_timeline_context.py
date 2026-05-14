"""Timeline redraw, video context, and drag lifecycle helpers for editor segments."""

from __future__ import annotations

from PyQt6.QtGui import QTextCursor

from ui.editor.editor_helpers import build_segment_lookup


class EditorSegmentsTimelineContextMixin:
    def _timeline_segments_with_live_preview(self, segs: list[dict]) -> list[dict]:
        timeline_segs = list(segs or [])
        preview = list(getattr(self, "_live_stt_preview_segments", []) or [])
        if not preview:
            return timeline_segs
        confirmed = [seg for seg in timeline_segs if not seg.get("is_gap")]
        subtitle_preview = self._build_live_subtitle_preview_segments(preview, confirmed)
        return sorted(
            confirmed + subtitle_preview + preview,
            key=lambda seg: (float(seg.get("start", 0.0) or 0.0), float(seg.get("end", 0.0) or 0.0)),
        )

    def _timeline_total_duration_for_segments(self, timeline_segs: list[dict]) -> float:
        total_dur = timeline_segs[-1]["end"] if timeline_segs else 0.0
        if hasattr(self, "video_player") and self.video_player.total_time > 0.0:
            total_dur = max(total_dur, self.video_player.total_time)
        return total_dur

    def _video_context_segments_for_redraw(self):
        canvas = getattr(getattr(self, "timeline", None), "canvas", None)
        mc_boxes = list(getattr(canvas, "_multiclip_boxes", []) or []) if canvas is not None else []
        if mc_boxes and hasattr(self, "_resolve_active_context"):
            try:
                global_sec = float(getattr(canvas, "playhead_sec", 0.0) or 0.0)
                ctx = self._resolve_active_context(global_sec=global_sec)
                local_sec = float(ctx.get("local_sec", 0.0) or 0.0)
                return self._subtitle_context_window_from_segments(
                    list(ctx.get("local_segments", []) or []),
                    center_sec=local_sec,
                )
            except Exception:
                return self._subtitle_memory_visible_window()
        return self._subtitle_memory_visible_window()

    def _apply_video_context_segments(self, segs) -> None:
        if not hasattr(self, "video_player"):
            return
        try:
            if hasattr(self.video_player, "refresh_subtitle_context"):
                self.video_player.refresh_subtitle_context(segs)
            else:
                self.video_player.set_context_segments(segs)
        except Exception:
            pass

    def _apply_initial_timeline_fit_if_needed(self, segs: list[dict]) -> None:
        if not (getattr(self, "_needs_fit_view", False) and segs and hasattr(self.timeline, "fit_to_view")):
            return
        auto_fit = getattr(self.timeline, "auto_fit_to_view", None)
        if callable(auto_fit):
            auto_fit()
        else:
            self.timeline.fit_to_view()
        self._needs_fit_view = False

    def _redraw_timeline(self):
        segs = self._get_current_segments()
        if not isinstance(getattr(self, "_subtitle_memory_cache", None), dict):
            self._rebuild_subtitle_memory_cache(segs)
        timeline_segs = self._timeline_segments_with_live_preview(segs)
        if hasattr(self, "_highlighter"):
            self._refresh_visible_quality_map()
        total_dur = self._timeline_total_duration_for_segments(timeline_segs)
        self.timeline.update_segments(timeline_segs, self._active_seg_start, total_dur)
        if hasattr(self, "video_player") and hasattr(self.video_player, "set_context_segments"):
            self.video_player.set_context_segments(self._video_context_segments_for_redraw())
        self._apply_initial_timeline_fit_if_needed(segs)

    def _refresh_video_subtitle_context(self):
        if not hasattr(self, "video_player"):
            return
        self._apply_video_context_segments(self._video_subtitle_context_for_player())

    def _video_subtitle_context_for_player(self):
        cache = getattr(self, "_subtitle_memory_cache", None)
        if not isinstance(cache, dict):
            cached = getattr(self, "_cached_segs", None)
            cache = build_segment_lookup(cached) if cached is not None else self._rebuild_subtitle_memory_cache()
            self._subtitle_memory_cache = cache
        try:
            mc_boxes = list(getattr(self.timeline.canvas, "_multiclip_boxes", []) or []) if hasattr(self, "timeline") else []
            if mc_boxes and hasattr(self, "_resolve_active_context"):
                global_sec = float(getattr(self.timeline.canvas, "playhead_sec", 0.0) or 0.0)
                ctx = self._resolve_active_context(global_sec=global_sec)
                if ctx:
                    return self._subtitle_context_window_from_segments(
                        list(ctx.get("local_segments", []) or []),
                        center_sec=float(ctx.get("local_sec", 0.0) or 0.0),
                    )
        except Exception:
            pass
        return self._subtitle_memory_visible_window()

    def _schedule_timeline(self):
        if getattr(self, "_inline_updating", False):
            return
        self._timeline_timer.start(120)

    def _on_drag_started(self):
        self._timeline_drag_in_progress = True
        self._undo_mgr.push_immediate()
        self._drag_cursor = QTextCursor(self.text_edit.document())
        self._drag_cursor.beginEditBlock()

    def _on_drag_finished(self):
        if hasattr(self, "_drag_cursor") and self._drag_cursor:
            self._drag_cursor.endEditBlock()
            self._drag_cursor = None
        self._timeline_drag_in_progress = False
        self._schedule_timeline()
